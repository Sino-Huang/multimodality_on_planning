#!/usr/bin/env python
"""Choice-frontier v7 (#146): node choice for all four algorithms x text / visual / multimodal.

Protocol: ``docs/experiments/choice-frontier/issue-146-protocol.md`` (twin
``configs/experiments/choice-frontier-v7/protocol.json``). Frozen #132-#141 machinery
is imported read-only. Every output resolves under ``outputs/choice-frontier/v7``.

Stages (CPU unless noted):

- ``validate``       frozen pins (protocol, panels, #136 pool/membership, study-v5).
- ``panels``         R_t for all four algorithms on P2/P2u and the smoke subset, native-prefix gate
                     -> ``configs/experiments/choice-frontier-v7/panels.json``.
- ``prepare``        BFS/BFWS teacher derivation, scene catalogs (backend 18880), additive
                     text/multimodal records from the #136 store, membership, augmentation check.
- ``audit-prepare``  independent bit-exact re-derivation and every corpus gate.
- ``controls``       exact / random-valid for 12 cells x 23 tasks under the overflow rule, replayed.
- ``identity-gate``  random_valid vs exact divergence per algorithm and observation.
- ``worker --gpu N`` (GPU) resumable queue: train (+ seed-17 smoke), learned evaluation, zero-shot.
- ``launch`` / ``resume`` / ``status`` / ``hook``  scheduler plumbing (``scripts/run_expanded_study.py``).
- ``finalize``       independent replay of every model episode.
- ``analyze``        pre-registered tests -> ``outputs/choice-frontier/v7/metrics/analysis.json``.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import gc
import gzip
import hashlib
import json
import math
import os
import random
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.choice_frontier import (  # noqa: E402
    ChoiceFrontierModelSession,
    ChoiceFrontierTask,
)
from examples.planning_benchmark_slice.node_choice import (  # noqa: E402
    ADDITIVE_ALGORITHMS,
    ALGORITHMS,
    KEYED_ALGORITHMS,
    NODE_CHOICE_SCHEMA,
    OBSERVATIONS,
    REPRESENTATIONS,
    SYSTEM_MESSAGES,
    NodeChoiceSession,
    NodeChoiceTask,
    canonical_choice,
    replay_node_choice_episode,
    run_control_episode,
)
from examples.planning_benchmark_slice.node_choice_views import (  # noqa: E402
    TOKEN_LIMIT,
    NodeChoiceTaskViews,
    build_node_observation,
    node_payload,
    placeholder_counter,
    text_context,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402
from scripts import run_choice_frontier_v3 as v3  # noqa: E402
from scripts import run_choice_frontier_v4_panels as v4p  # noqa: E402

PROTOCOL_PATH = Path("configs/experiments/choice-frontier-v7/protocol.json")
CONFIG = Path("configs/experiments/choice-frontier-v7")
PANELS_PATH = CONFIG / "panels.json"
MEMBERSHIP_PATH = CONFIG / "membership.json"
SCHEDULE = Path("docs/experiments/choice-frontier/schedule-v7.json")
OUT = Path("outputs/choice-frontier/v7")
LEDGER = OUT / "budget.json"
QUEUE = OUT / "queue"
V3_TRAINING_TASKS = Path("configs/experiments/choice-frontier-v3/training-tasks.json")
V3_MEMBERSHIP = Path("configs/experiments/choice-frontier-v3/membership.json")
V3_STORE = Path("outputs/choice-frontier/v3/preparation/store.json")
V3_TRAIN_VIEWS = Path("outputs/choice-frontier/v3/train-views")
V3_EPISODES = Path("outputs/choice-frontier/v3/preparation/episodes")
RENDER_PROFILES = Path("configs/experiments/issue71/v2/render.json")
PANELS = ("p2", "p2u")
SEEDS = (17, 29, 71)
TEACHER_SEED = 17
INFERENCE_SEED = 17
RANDOM_SEEDS = (17, 5077, 6131, 7409, 8527)
UNCAPPED = 10**6
TARGET_RECORDS = 2048
RECORDS_PER_TASK = 64
DIAGNOSTIC_RECORDS = 16
AUGMENTATIONS = 2
DERIVATION_TIMEOUT = 600
ORDER_SEED = "order:17"
GPU_HOURS_CAP = 400.0
BUDGET_STOP_GPU_HOURS = 380.0
WORKER_MAX_SECONDS = 7 * 24 * 3600
MIN_CLAIM_SECONDS = 1800
DEADLINE_MARGIN_SECONDS = 900
MAX_SLOT_FAILURES = 2
MAX_CONSECUTIVE_FAILURES = 3
CHECKPOINT_EVERY = 16
GPU_BACKEND_PORTS = {0: 18878, 1: 18879}
PREP_BACKEND_PORT = 18880
MASTER_PORT_POOL = (18870, 18871, 18872, 18873)
ENV_SCRIPT = "~/cd_vlaplan"
BACKEND_PYTHON = Path(".cache/issue70-backend-venv/bin/python")
SMOKE_THRESHOLD = 0.5
EPISODE_SCHEMA = "choice_frontier_v7_episode_v1"
STUDY_V5 = Path("configs/experiments/matched-modalities/study-v5.json")
ZERO_SHOT_PREFIX = (
    ' Reply with exactly one JSON object and nothing else, of the form {"expand_choice": "<label>"}, '
    "where <label> is one of the frontier_menu choices (c0, c1, ...). "
)
ZERO_SHOT_CLAUSE = {
    "visual": "Choose the frontier state whose scene appears closest to satisfying the goal pages.",
    "text": "Choose the frontier state whose facts appear closest to satisfying the goal constraints.",
    "multimodal": (
        "Choose the frontier state whose scene and facts appear closest to satisfying the goal constraints and pages."
    ),
}


# ============================================================================ io


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, payload: Any) -> None:
    path = path if path.is_absolute() else ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if path.name.endswith(".gz"):
        with gzip.open(temporary, "wt") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
    else:
        temporary.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    temporary.replace(path)


def load(path: Path) -> Any:
    return read_json(path if path.is_absolute() else ROOT / path)


def protocol() -> dict:
    return load(PROTOCOL_PATH)


def zero_shot_system(algorithm: str, observation: str) -> str:
    return SYSTEM_MESSAGES[algorithm] + ZERO_SHOT_PREFIX + ZERO_SHOT_CLAUSE[observation]


def model_input_for(model_input: dict, observation: str) -> dict:
    return {**model_input, "representation": REPRESENTATIONS[observation]}


class StateView:
    """A state as the views need it (atoms/fluents), from a stored catalog entry."""

    __slots__ = ("atoms", "fluents")

    def __init__(self, atoms, fluents):
        self.atoms = tuple(atoms)
        self.fluents = tuple(fluents)


def authority_of(task_path: str) -> tuple[PDDLStateAuthority, dict]:
    source = load(Path(task_path))
    return PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"]), source


# ============================================================================ validate


def validate_stage() -> dict:
    p = protocol()
    checks = {
        "task_pool_sha256": sha256_file(ROOT / V3_TRAINING_TASKS) == p["corpus"]["task_pool_sha256"],
        "additive_membership_sha256": load(V3_MEMBERSHIP)["membership_sha256"]
        == p["corpus"]["additive_membership_sha256"],
        "study_sha256": sha256_file(ROOT / STUDY_V5) == p["training"]["study_sha256"],
        "p2_sha": v4p.membership("p2")["membership_sha256"] == p["panels"]["p2"]["membership_sha256"],
        "p2u_sha": v4p.membership("p2u")["membership_sha256"] == p["panels"]["p2u"]["membership_sha256"],
        "study_backbone": (load(STUDY_V5)["model_id"], load(STUDY_V5)["model_revision"])
        == (p["model_id"], p["model_revision"]),
        "token_limit": TOKEN_LIMIT == p["contract"]["overflow_rule"]["token_limit"],
        "zero_shot_suffix": all(
            ZERO_SHOT_PREFIX + ZERO_SHOT_CLAUSE[o] == p["evaluation"]["zero_shot_suffix"][o] for o in OBSERVATIONS
        ),
        "ports": list(MASTER_PORT_POOL) == p["ports"]["master_port_pool"],
    }
    return {"checks": checks, "ok": all(checks.values())}


# ============================================================================ panels


def exact_expansions(authority, task_id: str, domain: str, algorithm: str) -> tuple[int, list[str], str]:
    session = run_control_episode(
        authority, NodeChoiceTask(task_id, domain, algorithm, UNCAPPED), "text", "exact_reference", TEACHER_SEED
    )
    sequence = [
        session.controller._states_by_ref[e["trusted_runtime_result"]["expanded_state_id"]].state_id
        for e in session.events
        if e["trusted_runtime_result"]["status"] == "expanded"
    ]
    return session.controller.expansion_count, sequence, session.termination_reason or ""


def native_prefix(source: dict, algorithm: str, sequence: list[str], *, truncated: bool) -> bool:
    """Gate 1: the node-choice kappa order reproduces the frozen native runtime's order."""

    from examples.planning_benchmark_slice.bfs_pilot import exact_fifo_bfs
    from examples.planning_benchmark_slice.bfws_episode import run_best_first_width

    if algorithm == "bfs":
        native = exact_fifo_bfs(source["domain_pddl"], source["problem_pddl"], max_expansions=max(1, len(sequence)))
        expanded = list(native.expanded_state_ids)
        return expanded == sequence if not truncated else expanded[: len(sequence)] == sequence[: len(expanded)]
    if algorithm == "best_first_width":
        steps = []
        authority = PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"])
        run_best_first_width(authority, max_expansions=max(1, len(sequence)), on_step=steps.append)
        order: list[str] = []
        last = None
        for step in steps:
            if step.expansion_index != last:
                order.append(step.expanded_state_id)
                last = step.expansion_index
        length = min(len(order), len(sequence))
        return order[:length] == sequence[:length] and (truncated or len(order) <= len(sequence))
    raise ValueError(algorithm)


def _panel_row(item: tuple[str, dict, dict | None]) -> dict:
    group, row, frozen = item
    authority, source = authority_of(row["task_path"])
    result = {
        "task_id": row["task_id"],
        "domain": row["domain"],
        "task_path": row["task_path"],
        "group": group,
        "R": {},
        "native_prefix_gate": {},
        "exact_termination": {},
    }
    for algorithm in ALGORITHMS:
        authority, _ = authority_of(row["task_path"])
        r, sequence, termination = exact_expansions(authority, row["task_id"], row["domain"], algorithm)
        result["R"][algorithm] = r
        result["exact_termination"][algorithm] = termination
        if algorithm in KEYED_ALGORITHMS:
            result["native_prefix_gate"][algorithm] = native_prefix(source, algorithm, sequence, truncated=False)
        elif frozen is not None:
            result["native_prefix_gate"][algorithm] = r == frozen[algorithm]["expansions"]
        else:
            result["native_prefix_gate"][algorithm] = termination == "goal_reached"
    return result


def smoke_task_rows() -> list[dict]:
    from examples.planning_benchmark_slice.expanded_modality_stress import load_panel_tasks

    gate = protocol()["smoke_gate"]
    shim = {
        "panel": gate["panel"],
        "panel_view_report": gate["panel_view_report"],
        "panel_id": "expanded-panel-v2-qualified",
        "membership_rule": {"membership": list(gate["subset"])},
    }
    return load_panel_tasks(ROOT, shim)


def panels_stage(workers: int = 8) -> dict:
    from concurrent.futures import ProcessPoolExecutor

    items = []
    for panel in PANELS:
        for task in v4p.membership(panel)["tasks"]:
            items.append((panel, task["row"], task["row"]["reference_costs"]))
    for task in smoke_task_rows():
        items.append(("smoke", task["row"], None))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(_panel_row, items))
    gate = all(all(r["native_prefix_gate"].values()) for r in rows)
    solved = all(t == "goal_reached" for r in rows for t in r["exact_termination"].values())
    document = {
        "schema_version": "choice_frontier_v7_panels_v1",
        "protocol_id": protocol()["protocol_id"],
        "panels": {p: protocol()["panels"][p]["membership_sha256"] for p in PANELS},
        "r_t_rule": protocol()["panels"]["r_t"],
        "native_prefix_gate": gate,
        "all_exact_reach_goal": solved,
        "tasks": rows,
    }
    write(PANELS_PATH, document)
    return {"tasks": len(rows), "native_prefix_gate": gate, "all_exact_reach_goal": solved}


def panel_rows(group: str | None = None) -> list[dict]:
    rows = load(PANELS_PATH)["tasks"]
    return [r for r in rows if group is None or r["group"] == group]


def pooled_task_ids() -> list[str]:
    return [r["task_id"] for r in panel_rows() if r["group"] in PANELS]


# ============================================================================ prepare: keyed teacher derivation


def _derive_keyed(item: tuple[str, str]) -> dict:
    task_id, task_path = item
    authority, source = authority_of(task_path)
    pages = v3.page_counts(source)
    context = text_context(authority, source["domain_pddl"], source["problem_pddl"])
    result = {"task_id": task_id, "pages": list(pages), "episodes": {}, "timeouts": []}
    for algorithm in KEYED_ALGORITHMS:
        previous = signal.signal(signal.SIGALRM, v3._timeout)
        signal.setitimer(signal.ITIMER_REAL, DERIVATION_TIMEOUT)
        try:
            result["episodes"][algorithm] = derive_keyed_episode(task_id, source, algorithm, pages, context)
        except TimeoutError:
            result["timeouts"].append(algorithm)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
    return result


def derive_keyed_episode(task_id: str, source: dict, algorithm: str, pages, context) -> dict:
    authority = PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"])
    domain = task_id.split("/")[1].rsplit("-", 2)[0]
    session = NodeChoiceSession(
        authority=authority,
        task=NodeChoiceTask(task_id, domain, algorithm, UNCAPPED),
        observation="multimodal",
        arm="exact_reference",
        seed=TEACHER_SEED,
    )
    counters = {o: placeholder_counter(algorithm, o, context, tuple(pages)) for o in OBSERVATIONS}
    decisions, eligible, overflow = [], 0, 0
    while eligible < RECORDS_PER_TASK and (request := session.next_request()) is not None:
        menu = [dict(entry) for entry in request.menu_binding]
        tokens, is_eligible = None, False
        if len(menu) >= 2:
            states = session.menu_states(request)
            tokens = {o: counters[o](model_input_for(dict(request.model_input), o), states) for o in OBSERVATIONS}
            is_eligible = tokens["multimodal"] <= TOKEN_LIMIT
            overflow += int(not is_eligible)
        teacher = session.reference_output()
        session.submit_output(teacher)
        result = session.events[-1]["trusted_runtime_result"]
        decisions.append(
            {
                "decision_index": request.decision_index,
                "menu": menu,
                "menu_size": len(menu),
                "teacher_choice": json.loads(teacher)["expand_choice"],
                "teacher_state_ref": result["expanded_state_id"],
                "status": result["status"],
                "input_tokens": tokens,
                "eligible": is_eligible,
                "admissions": [
                    [a["action"], a["trusted_runtime_result"]["target_state_id"]] for a in result.get("admissions", [])
                ],
            }
        )
        eligible += int(is_eligible)
    sequence = [
        session.controller._states_by_ref[d["teacher_state_ref"]].state_id
        for d in decisions
        if d["status"] == "expanded"
    ]
    return {
        "task_id": task_id,
        "algorithm": algorithm,
        "decisions": decisions,
        "eligible": eligible,
        "overflow_skipped": overflow,
        "complete": session.complete,
        "termination_reason": session.termination_reason,
        "native_prefix_gate": native_prefix(source, algorithm, sequence, truncated=True),
    }


def eligible_records(episode: dict) -> list[dict]:
    return [d for d in episode["decisions"] if d["eligible"]][:RECORDS_PER_TASK]


def select_keyed(order: list[str], derived: dict, dropped: set[str]) -> dict:
    selection = {}
    for algorithm in KEYED_ALGORITHMS:
        training, diagnostic, task_order = [], [], []
        for task_id in order:
            if task_id in dropped:
                continue
            if task_id not in derived:
                break
            episode = derived[task_id]["episodes"].get(algorithm)
            if episode is None:
                continue
            for decision in eligible_records(episode):
                rid = f"{task_id}:{algorithm}:{decision['decision_index']}"
                if len(training) < TARGET_RECORDS:
                    training.append(rid)
                elif len(diagnostic) < DIAGNOSTIC_RECORDS:
                    diagnostic.append(rid)
                else:
                    break
                if task_id not in task_order:
                    task_order.append(task_id)
            if len(diagnostic) >= DIAGNOSTIC_RECORDS:
                break
        selection[algorithm] = {"training": training, "diagnostic": diagnostic, "task_order": task_order}
    return selection


def selection_complete(selection: dict) -> bool:
    return all(
        len(s["training"]) >= TARGET_RECORDS and len(s["diagnostic"]) >= DIAGNOSTIC_RECORDS for s in selection.values()
    )


def derived_path(task_id: str) -> Path:
    return OUT / "preparation" / "episodes" / f"{task_id.split('/', 1)[1]}.json.gz"


def keyed_catalog(task: dict, episodes: dict, last_decision: dict) -> dict:
    """Initial state + every admission of each teacher expansion before the last used decision."""

    from examples.planning_benchmark_slice.expanded_views import ReferenceStateCatalog
    from examples.planning_benchmark_slice.pddl_state import GroundedAction

    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    catalog = ReferenceStateCatalog(authority)
    decisions, refs = [], {}
    for algorithm in KEYED_ALGORITHMS:
        if algorithm not in last_decision:
            continue
        states = {"s0": authority.initial_state}
        expansion = 0
        for decision in episodes[algorithm]["decisions"]:
            if decision["decision_index"] >= last_decision[algorithm]:
                break
            if decision["status"] != "expanded":
                continue
            source = states[decision["teacher_state_ref"]]
            decisions.append({"algorithm": algorithm, "index": expansion, "state": catalog.indices[source.state_id]})
            expansion += 1
            for action, target_ref in decision["admissions"]:
                successor = authority.apply(source, GroundedAction(action["name"], tuple(action["args"]))).target_state
                states.setdefault(target_ref, successor)
                if states[target_ref].state_id != successor.state_id:
                    raise ValueError("teacher admission target reference differs from replay")
                catalog.register(source, action)
        refs[algorithm] = states
    return {
        "catalog": {
            "task_context": authority.task_context(),
            "states": catalog.states,
            "decisions": decisions,
            "scope": "initial state plus every admission of the truncated exact node-choice teacher episodes",
        },
        "indices": {a: {ref: catalog.indices[s.state_id] for ref, s in states.items()} for a, states in refs.items()},
    }


def build_task_views(item: tuple[dict, dict, dict]) -> dict:
    """The #136 ``build_task_views`` recipe over a keyed teacher catalog (backend 18880)."""

    import torch

    from examples.planning_benchmark_slice.modality_pages import compose_page, fact_blocks, paginate
    from examples.planning_benchmark_slice.modality_view_preparation import _state_goal_checks
    from examples.planning_benchmark_slice.scene_assets import collect_task_scenes
    from examples.planning_benchmark_slice.scene_only_views import materialize_task
    from examples.planning_benchmark_slice.source_goal import source_task

    torch.set_num_threads(2)
    record, episodes, last_decision = item
    name = record["task_id"].split("/", 1)[1]
    output = ROOT / OUT / "train-views" / name
    saved = output / "result.json"
    task = load(Path(record["task_path"]))
    built = keyed_catalog(task, episodes, last_decision)
    catalog = built["catalog"]
    counts: dict[str, int] = {}
    for decision in catalog["decisions"]:
        counts[decision["algorithm"]] = counts.get(decision["algorithm"], 0) + 1
    row = {
        "task_id": record["task_id"],
        "domain": record["domain"],
        "difficulty": record["difficulty"],
        "split": "train",
        "task_path": record["task_path"],
        "trace_paths": {},
        "reference_costs": {a: {"decisions": n, "expansions": n} for a, n in counts.items()},
    }
    binding = {"row": row, "last_decision": last_decision, "catalog_sha256": sha256_text(canonical(catalog))}
    if saved.exists():
        result = load(saved)
        if result["binding"] == binding:
            return result
        raise ValueError(f"retained training view binding differs: {name}")
    try:
        source = source_task(task["domain_pddl"], task["problem_pddl"])
        authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
        _state_goal_checks(authority, catalog, source)
        scene_output = output / "scenes"
        if not (scene_output / "catalog.json.gz").exists():
            if scene_output.exists():
                number = 1
                while scene_output.with_name(f"scenes-interrupted-{number}").exists():
                    number += 1
                scene_output.rename(scene_output.with_name(f"scenes-interrupted-{number}"))
            profiles = load(RENDER_PROFILES)["domain_profiles"]
            collect_task_scenes(
                root=ROOT,
                row=row,
                profile=ROOT / profiles[row["domain"]],
                endpoint=f"http://127.0.0.1:{PREP_BACKEND_PORT}",
                output=scene_output,
                timeout=30,
                preflight=False,
                progress=lambda detail: None,
                catalog=catalog,
            )
        collected = load(scene_output / "catalog.json.gz")
        goal_recipes = paginate("goal", fact_blocks(collected["task_context"], collected["states"][0], source)["goal"])
        goal_paths = []
        for recipe in goal_recipes:
            path = output / f"goal-{recipe.index}.png"
            image = compose_page(recipe, ROOT)
            image.save(path)
            image.close()
            goal_paths.append(str(path.relative_to(ROOT)))
        manifest_path = output / "manifest.json"
        write(
            manifest_path,
            dict(
                task_id=row["task_id"],
                split="train",
                scene_catalog=str((scene_output / "catalog.json.gz").relative_to(ROOT)),
                source=source,
                task_context=collected["task_context"],
                reusable_pages={"goal": goal_paths},
                reusable_recipes={"goal": [r.to_dict() for r in goal_recipes]},
                reference_costs=row["reference_costs"],
                complete_reference_coverage=True,
                full_reachable_closure=False,
            ),
        )
        native = materialize_task(
            ROOT,
            row["task_id"],
            str(manifest_path.relative_to(ROOT)),
            range(len(collected["states"])),
            output / "unlabelled",
            lambda *args, **kwargs: None,
        )
    except Exception as error:  # a render/view failure is a recorded task drop
        return {"binding": binding, "outcome": "view_render_failed", "error": f"{type(error).__name__}: {error}"}
    result = {
        "binding": binding,
        "outcome": "TRAIN_VIEWS_PASS",
        "native_views": native,
        "indices": built["indices"],
        "catalog": str((scene_output / "catalog.json.gz").relative_to(ROOT)),
        "states": len(collected["states"]),
    }
    write(saved, result)
    return result


def last_decisions(selection: dict, task_id: str) -> dict:
    last = {}
    for algorithm, chosen in selection.items():
        ids = [rid for rid in chosen["training"] + chosen["diagnostic"] if rid.startswith(task_id + ":")]
        if ids:
            last[algorithm] = max(int(rid.rsplit(":", 1)[1]) for rid in ids)
    return last


def keyed_record(task_id: str, algorithm: str, decision: dict, view: dict, domain: str, split: str) -> dict:
    indices = view["indices"][algorithm]
    return {
        "record_id": f"{task_id}:{algorithm}:{decision['decision_index']}",
        "task_id": task_id,
        "domain": domain,
        "algorithm": algorithm,
        "split": split,
        "decision_index": decision["decision_index"],
        "status": decision["status"],
        "menu": decision["menu"],
        "menu_indices": [indices[entry["state_ref"]] for entry in decision["menu"]],
        "teacher_choice": decision["teacher_choice"],
        "teacher_state_ref": decision["teacher_state_ref"],
        "menu_size": decision["menu_size"],
        "input_tokens": decision["input_tokens"],
        "view_key": f"keyed:{task_id}",
    }


def catalog_states(catalog_path: str, indices) -> dict[str, list]:
    states = load(Path(catalog_path))["states"]
    return {str(i): [states[i]["atoms"], states[i]["fluents"]] for i in sorted(set(indices))}


def prepare_keyed(workers: int, progress) -> tuple[dict, dict, dict, dict]:
    from concurrent.futures import ProcessPoolExecutor

    tasks = [t for t in load(V3_TRAINING_TASKS)["tasks"] if not t["excluded"]]
    order = [t["task_id"] for t in tasks]
    by_id = {t["task_id"]: t for t in tasks}
    derived: dict[str, dict] = {}
    for task in tasks:
        path = ROOT / derived_path(task["task_id"])
        if path.exists():
            derived[task["task_id"]] = load(path)
    dropped: dict[str, str] = {}
    views: dict[str, dict] = {}
    while True:
        pending = [t for t in tasks if t["task_id"] not in derived]
        cursor = 0
        with ProcessPoolExecutor(max_workers=workers) as pool:
            while not selection_complete(select_keyed(order, derived, set(dropped))) and cursor < len(pending):
                chunk = pending[cursor : cursor + workers]
                cursor += len(chunk)
                for task, result in zip(
                    chunk, pool.map(_derive_keyed, [(t["task_id"], t["task_path"]) for t in chunk]), strict=True
                ):
                    write(derived_path(task["task_id"]), result)
                    derived[task["task_id"]] = result
                progress("v7_derive", completed=len(derived), total=len(tasks))
        for task_id, result in derived.items():
            if len(result["timeouts"]) == len(KEYED_ALGORITHMS):
                dropped.setdefault(task_id, "derivation_timeout")
        selection = select_keyed(order, derived, set(dropped))
        used = [t for t in order if any(t in s["task_order"] for s in selection.values())]
        stale = [t for t in used if t in views and views[t]["binding"]["last_decision"] != last_decisions(selection, t)]
        for task_id in stale:
            del views[task_id]
        todo = [t for t in used if t not in views]
        with ProcessPoolExecutor(max_workers=min(4, workers)) as pool:
            items = [(by_id[t], derived[t]["episodes"], last_decisions(selection, t)) for t in todo]
            for task_id, result in zip(todo, pool.map(build_task_views, items), strict=True):
                if result["outcome"] != "TRAIN_VIEWS_PASS":
                    dropped[task_id] = "view_render_failed"
                    print(task_id, result["outcome"], result.get("error"), flush=True)
                else:
                    views[task_id] = result
                progress("v7_views", completed=len(views), total=len(used), task=task_id)
        if not any(t in dropped for t in todo) and all(
            views[t]["binding"]["last_decision"] == last_decisions(selection, t) for t in used
        ):
            break
    return derived, views, selection, {"dropped": dropped, "by_id": by_id}


# ============================================================================ prepare: additive text/multimodal


def additive_states(task_id: str, task_path: str, records: list[dict], catalog_path: str) -> dict:
    """Replay the #136 exact teacher from PDDL; menus must re-bind to the stored records and catalog states."""

    authority, source = authority_of(task_path)
    domain = task_id.split("/")[1].rsplit("-", 2)[0]
    by_algorithm: dict[str, list[dict]] = {}
    for record in records:
        by_algorithm.setdefault(record["algorithm"], []).append(record)
    catalog = load(Path(catalog_path))["states"]
    pages = v3.page_counts(source)
    context = text_context(authority, source["domain_pddl"], source["problem_pddl"])
    out = {}
    for algorithm, rows in by_algorithm.items():
        wanted = {r["decision_index"]: r for r in rows}
        session = ChoiceFrontierModelSession(
            authority=PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"]),
            task=ChoiceFrontierTask(task_id, task_id, domain, algorithm, UNCAPPED),
            arm="exact_reference",
            seed=TEACHER_SEED,
        )
        counters = {o: placeholder_counter(algorithm, o, context, tuple(pages)) for o in ("text", "multimodal")}
        last = max(wanted)
        while (request := session.next_request()) is not None and request.decision_index <= last:
            record = wanted.get(request.decision_index)
            if record is not None:
                if [dict(e) for e in request.menu_binding] != record["menu"]:
                    raise ValueError(f"#136 record menu does not re-bind: {record['record_id']}")
                states = session.menu_states(request)
                for state, index in zip(states, record["menu_indices"], strict=True):
                    entry = catalog[index]
                    if list(state.atoms) != entry["atoms"] or list(state.fluents) != entry["fluents"]:
                        raise ValueError(f"#136 record scene state differs from replay: {record['record_id']}")
                model_input = {
                    "algorithm": algorithm,
                    "frontier_menu": {"choices": [e["choice"] for e in record["menu"]]},
                    "representation": "",
                    "schema_version": NODE_CHOICE_SCHEMA,
                }
                out[record["record_id"]] = {
                    o: counters[o](model_input_for(model_input, o), states) for o in ("text", "multimodal")
                }
            session.submit_output(session.reference_output())
    return out


def _additive_task(item) -> dict:
    task_id, task_path, records, catalog_path = item
    return {"task_id": task_id, "tokens": additive_states(task_id, task_path, records, catalog_path)}


def prepare_additive(workers: int) -> tuple[dict, dict, dict]:
    from concurrent.futures import ProcessPoolExecutor

    store = load(V3_STORE)
    pool_rows = {t["task_id"]: t for t in load(V3_TRAINING_TASKS)["tasks"]}
    by_task: dict[str, list[dict]] = {}
    for record in store["records"].values():
        by_task.setdefault(record["task_id"], []).append(record)
    items = []
    for task_id, records in by_task.items():
        catalog_path = str(V3_TRAIN_VIEWS / task_id.split("/", 1)[1] / "scenes" / "catalog.json.gz")
        items.append((task_id, pool_rows[task_id]["task_path"], records, catalog_path))
    tokens = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(_additive_task, items):
            tokens.update(result["tokens"])
    records, tasks = {}, {}
    for task_id, task_path, rows, catalog_path in items:
        tasks[f"additive:{task_id}"] = {
            **{k: store["tasks"][task_id][k] for k in ("static_pages", "goal_pages", "scenes", "view_id")},
            "task_path": task_path,
            "states": catalog_states(catalog_path, [i for r in rows for i in r["menu_indices"]]),
        }
        for record in rows:
            records[record["record_id"]] = {
                **{
                    k: record[k]
                    for k in (
                        "record_id",
                        "task_id",
                        "domain",
                        "algorithm",
                        "split",
                        "decision_index",
                        "status",
                        "menu",
                        "menu_indices",
                        "teacher_choice",
                        "teacher_state_ref",
                        "menu_size",
                    )
                },
                "input_tokens": {"visual_v1": record["input_tokens"], **tokens[record["record_id"]]},
                "view_key": f"additive:{task_id}",
            }
    membership = load(V3_MEMBERSHIP)
    selection, overflow = {}, {}
    for algorithm in ADDITIVE_ALGORITHMS:
        keep = {}
        for key, split in (("training_record_ids", "training"), ("diagnostic_record_ids", "diagnostic")):
            ids = membership[key][algorithm]
            over = [rid for rid in ids if records[rid]["input_tokens"]["multimodal"] > TOKEN_LIMIT]
            overflow.setdefault(algorithm, {})[split] = over
            keep[split] = [rid for rid in ids if rid not in over]
        selection[algorithm] = keep
    return tasks, records, {"selection": selection, "overflow_dropped": overflow}


# ============================================================================ prepare / audit-prepare


def augmentation_check(records: list[dict]) -> dict:
    histogram = {"first": 0, "middle": 0, "last": 0}
    chance = []
    for record in records:
        for copy in range(AUGMENTATIONS):
            permuted, _indices, target = v3.augment_menu(
                record["record_id"], record["menu"], record["menu_indices"], record["teacher_state_ref"], copy
            )
            if next(e["state_ref"] for e in permuted if e["choice"] == target) != record["teacher_state_ref"]:
                raise ValueError("augmented target does not bind the teacher state")
            histogram[v3.label_position(target, record["menu_size"])] += 1
            chance.append(1 / record["menu_size"])
    samples = sum(histogram.values())
    last_share = histogram["last"] / samples
    rate = sum(chance) / len(chance)
    return {
        "samples": samples,
        "target_position_histogram": histogram,
        "target_last_share": last_share,
        "chance_last_rate": rate,
        "difference_percentage_points": 100 * (last_share - rate),
        "pass": abs(last_share - rate) <= 0.05,
    }


def membership_sha(membership: dict) -> str:
    return sha256_text(canonical({a: membership["cells"][a] for a in sorted(membership["cells"])}))


def prepare_stage(workers: int = 8) -> dict:
    progress = v3.progress_writer()
    derived, views, selection, info = prepare_keyed(workers, progress)
    by_id, dropped = info["by_id"], info["dropped"]
    tasks, records = {}, {}
    for algorithm, chosen in selection.items():
        for split, ids in (("train", chosen["training"]), ("diagnostic", chosen["diagnostic"])):
            for rid in ids:
                task_id, _alg, index = rid.rsplit(":", 2)
                decision = next(
                    d for d in derived[task_id]["episodes"][algorithm]["decisions"] if d["decision_index"] == int(index)
                )
                records[rid] = keyed_record(
                    task_id, algorithm, decision, views[task_id], by_id[task_id]["domain"], split
                )
    for task_id in sorted({r["task_id"] for r in records.values()}):
        native = views[task_id]["native_views"]
        tasks[f"keyed:{task_id}"] = {
            "static_pages": native["static_pages"],
            "goal_pages": native["goal_pages"],
            "scenes": native["scenes"],
            "view_id": native["view_id"],
            "task_path": by_id[task_id]["task_path"],
            "states": catalog_states(
                views[task_id]["catalog"],
                [i for r in records.values() if r["task_id"] == task_id for i in r["menu_indices"]],
            ),
            "episode_sha256": {a: sha256_text(canonical(e)) for a, e in derived[task_id]["episodes"].items()},
            "native_prefix_gate": {a: e["native_prefix_gate"] for a, e in derived[task_id]["episodes"].items()},
        }
        if (len(native["static_pages"]), len(native["goal_pages"])) != tuple(derived[task_id]["pages"]):
            raise ValueError(f"page counts differ from the derivation: {task_id}")
    additive_tasks, additive_records, additive = prepare_additive(workers)
    tasks.update(additive_tasks)
    records.update(additive_records)
    cells = {a: {"training": s["training"], "diagnostic": s["diagnostic"]} for a, s in selection.items()}
    cells.update(additive["selection"])
    membership = {
        "schema_version": "choice_frontier_v7_membership_v1",
        "protocol": str(PROTOCOL_PATH),
        "task_pool_sha256": sha256_file(ROOT / V3_TRAINING_TASKS),
        "additive_source_membership_sha256": load(V3_MEMBERSHIP)["membership_sha256"],
        "additive_overflow_dropped": additive["overflow_dropped"],
        "keyed_task_order": {a: s["task_order"] for a, s in selection.items()},
        "keyed_tasks_dropped": dropped,
        "augmentations": AUGMENTATIONS,
        "sample_order": ORDER_SEED,
        "cells": cells,
    }
    membership["membership_sha256"] = membership_sha(membership)
    write(MEMBERSHIP_PATH, membership)
    store = {"schema_version": "choice_frontier_v7_store_v1", "tasks": tasks, "records": records}
    write(OUT / "preparation" / "store.json.gz", store)
    augmentation = {a: augmentation_check([records[r] for r in cells[a]["training"]]) for a in ALGORITHMS}
    tokens = {
        a: {o: max(records[r]["input_tokens"][o] for r in cells[a]["training"]) for o in ("text", "multimodal")}
        for a in ALGORITHMS
    }
    report = {
        "schema_version": "choice_frontier_v7_preparation_v1",
        "membership_sha256": membership["membership_sha256"],
        "records_per_algorithm": {a: len(cells[a]["training"]) for a in ALGORITHMS},
        "diagnostics_per_algorithm": {a: len(cells[a]["diagnostic"]) for a in ALGORITHMS},
        "keyed_tasks_derived": len(derived),
        "keyed_tasks_used": {a: len(s["task_order"]) for a, s in selection.items()},
        "keyed_tasks_dropped": dropped,
        "keyed_overflow_skipped_decisions": sum(
            e["overflow_skipped"]
            for t in {r["task_id"] for r in records.values() if r["algorithm"] in KEYED_ALGORITHMS}
            for e in derived[t]["episodes"].values()
        ),
        "native_prefix_gate": all(all(t.get("native_prefix_gate", {}).values()) for t in tasks.values()),
        "additive_overflow_dropped": {
            a: {s: len(v) for s, v in d.items()} for a, d in additive["overflow_dropped"].items()
        },
        "max_input_tokens": tokens,
        "menu_size_mean": {
            a: sum(records[r]["menu_size"] for r in cells[a]["training"]) / len(cells[a]["training"]) for a in ALGORITHMS
        },
        "augmentation_check": augmentation,
        "outcome": "PASS" if all(v["pass"] for v in augmentation.values()) else "AUGMENTATION_CHECK_FAIL",
    }
    write(OUT / "preparation" / "report.json", report)
    return report


def audit_prepare_stage(workers: int = 8) -> dict:
    from concurrent.futures import ProcessPoolExecutor

    store = load(OUT / "preparation" / "store.json.gz")
    membership = load(MEMBERSHIP_PATH)
    pool_rows = {t["task_id"]: t for t in load(V3_TRAINING_TASKS)["tasks"]}
    keyed_tasks = sorted({r["task_id"] for r in store["records"].values() if r["algorithm"] in KEYED_ALGORITHMS})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rederived = dict(
            zip(keyed_tasks, pool.map(_derive_keyed, [(t, pool_rows[t]["task_path"]) for t in keyed_tasks]), strict=True)
        )
    mismatches = []
    for task_id in keyed_tasks:
        for algorithm, digest in store["tasks"][f"keyed:{task_id}"]["episode_sha256"].items():
            episode = rederived[task_id]["episodes"].get(algorithm)
            if episode is None or sha256_text(canonical(episode)) != digest:
                mismatches.append((task_id, algorithm, "episode"))
    for rid, record in store["records"].items():
        if record["algorithm"] not in KEYED_ALGORITHMS:
            continue
        episode = rederived[record["task_id"]]["episodes"][record["algorithm"]]
        decision = next(d for d in episode["decisions"] if d["decision_index"] == record["decision_index"])
        for field in ("menu", "teacher_choice", "teacher_state_ref", "menu_size", "input_tokens", "status"):
            if decision[field] != record[field]:
                mismatches.append((rid, field))
        if not decision["eligible"]:
            mismatches.append((rid, "eligible"))
    additive_tasks = sorted({r["task_id"] for r in store["records"].values() if r["algorithm"] in ADDITIVE_ALGORITHMS})
    items = [
        (
            t,
            pool_rows[t]["task_path"],
            [r for r in store["records"].values() if r["view_key"] == f"additive:{t}"],
            str(V3_TRAIN_VIEWS / t.split("/", 1)[1] / "scenes" / "catalog.json.gz"),
        )
        for t in additive_tasks
    ]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(_additive_task, items):
            for rid, tokens in result["tokens"].items():
                stored = store["records"][rid]["input_tokens"]
                if any(stored[o] != tokens[o] for o in tokens):
                    mismatches.append((rid, "additive_tokens"))
    ids = {rid for cell in membership["cells"].values() for split in cell.values() for rid in split}
    checks = {
        "independent_rederivation_bit_exact": not mismatches,
        "native_prefix_gate": all(all(t.get("native_prefix_gate", {}).values()) for t in store["tasks"].values()),
        "token_gate": all(store["records"][r]["input_tokens"]["multimodal"] <= TOKEN_LIMIT for r in ids),
        "images_resolve": all(
            (ROOT / store["tasks"][store["records"][r]["view_key"]]["scenes"][str(i)]).is_file()
            for r in ids
            for i in store["records"][r]["menu_indices"]
        )
        and all((ROOT / p).is_file() for t in store["tasks"].values() for p in t["static_pages"] + t["goal_pages"]),
        "states_bound": all(
            str(i) in store["tasks"][store["records"][r]["view_key"]]["states"]
            for r in ids
            for i in store["records"][r]["menu_indices"]
        ),
        "membership_rehash": membership_sha(membership) == membership["membership_sha256"],
        "membership_records_stored": ids <= set(store["records"]),
        "records_per_algorithm": all(
            len(membership["cells"][a]["training"])
            == TARGET_RECORDS - len(membership["additive_overflow_dropped"].get(a, {}).get("training", []))
            for a in ALGORITHMS
        ),
        "teacher_label_binds_state": all(
            next(
                e["choice"]
                for e in store["records"][r]["menu"]
                if e["state_ref"] == store["records"][r]["teacher_state_ref"]
            )
            == store["records"][r]["teacher_choice"]
            for r in ids
        ),
        "no_overlap_with_panels": not (
            {v3.sha256_text(load(Path(pool_rows[t]["task_path"]))["problem_pddl"]) for t in keyed_tasks + additive_tasks}
            & {v3.sha256_text(load(Path(r["task_path"]))["problem_pddl"]) for r in panel_rows()}
        ),
        "augmentation_check": all(
            augmentation_check([store["records"][r] for r in membership["cells"][a]["training"]])["pass"]
            for a in ALGORITHMS
        ),
    }
    audit = {
        "schema_version": "choice_frontier_v7_prepare_audit_v1",
        "checks": checks,
        "mismatches": mismatches[:20],
        "episodes_rederived": sum(len(r["episodes"]) for r in rederived.values()),
        "outcome": "PASS" if all(checks.values()) else "FAIL",
    }
    write(OUT / "preparation" / "audit.json", audit)
    return audit


# ============================================================================ controls + identity gate


_PANEL_TASKS: dict[str, dict] = {}


def panel_views_task(task_id: str) -> dict:
    """The #139 / expanded-study reference-view task dict with the v7 row (R_t for all four algorithms)."""

    row = next(r for r in panel_rows() if r["task_id"] == task_id)
    if task_id not in _PANEL_TASKS:
        source = smoke_task_rows() if row["group"] == "smoke" else v4p.load_tasks({"panel": row["group"]})
        _PANEL_TASKS.update({t["row"]["task_id"]: t for t in source})
    task = _PANEL_TASKS[task_id]
    costs = {a: {"decisions": row["R"][a] + 1, "expansions": row["R"][a]} for a in ALGORITHMS}
    return {**task, "row": {**task["row"], "reference_costs": costs}}


def page_counts_of(task: dict) -> tuple[int, int]:
    native = task["native_views"]
    return len(native["static_pages"]), len(native["goal_pages"])


def control_path(task_id: str, algorithm: str, observation: str, arm: str, seed: int) -> Path:
    return OUT / "controls" / task_id.replace("/", "__") / f"{algorithm}-{observation}-{arm}-{seed}.json.gz"


def _control(item) -> dict:
    task_id, algorithm, observation, arm, seed, r, task_path, pages = item
    path = ROOT / control_path(task_id, algorithm, observation, arm, seed)
    authority, source = authority_of(task_path)
    context = text_context(authority, source["domain_pddl"], source["problem_pddl"])
    counter = placeholder_counter(algorithm, observation, context, pages)
    task = NodeChoiceTask(task_id, task_id.split("/")[1].rsplit("-", 2)[0], algorithm, r)
    if path.exists():
        report = load(path)
    else:
        session = run_control_episode(
            authority, task, observation, arm, seed, token_limit=TOKEN_LIMIT, token_counter=counter
        )
        report = {**session.episode(), "task_id": task_id, "condition": arm}
        write(path, report)
    fresh, fresh_source = authority_of(task_path)
    fresh_context = text_context(fresh, fresh_source["domain_pddl"], fresh_source["problem_pddl"])
    replay_node_choice_episode(
        fresh, task, report, token_counter=placeholder_counter(algorithm, observation, fresh_context, pages)
    )
    return {
        "path": str(control_path(task_id, algorithm, observation, arm, seed)),
        "result": report["result"],
        "replayed": True,
    }


def controls_stage(workers: int = 16) -> dict:
    from concurrent.futures import ProcessPoolExecutor

    items = []
    for row in panel_rows():
        if row["group"] not in PANELS:
            continue
        pages = page_counts_of(panel_views_task(row["task_id"]))
        for algorithm in ALGORITHMS:
            for observation in OBSERVATIONS:
                for arm, seeds in (("exact_reference", (TEACHER_SEED,)), ("random_valid", RANDOM_SEEDS)):
                    for seed in seeds:
                        items.append(
                            (
                                row["task_id"],
                                algorithm,
                                observation,
                                arm,
                                seed,
                                row["R"][algorithm],
                                row["task_path"],
                                pages,
                            )
                        )
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_control, items, chunksize=4))
    equality = additive_visual_equality()
    receipt = {
        "episodes": len(results),
        "replayed": sum(r["replayed"] for r in results),
        "overflow": sum(1 for r in results if r["result"]["termination_reason"] == "observation_overflow"),
        "additive_visual_equals_139_zoo": equality,
    }
    write(OUT / "controls" / "receipt.json", receipt)
    return receipt


def additive_visual_equality() -> dict:
    """§4: v7 additive visual controls vs the #139 zoo (same choices, same results) wherever no overflow fired."""

    compared, differing, overflowed = 0, [], 0
    for panel in PANELS:
        zoo = ROOT / "outputs/choice-frontier/v4/panels" / panel / "zoo"
        for row in panel_rows(panel):
            for algorithm in ADDITIVE_ALGORITHMS:
                for arm, seeds in (("exact_reference", (TEACHER_SEED,)), ("random_valid", RANDOM_SEEDS)):
                    for seed in seeds:
                        mine = load(control_path(row["task_id"], algorithm, "visual", arm, seed))
                        if mine["result"]["termination_reason"] == "observation_overflow":
                            overflowed += 1
                            continue
                        name = f"{algorithm}-{arm}-m2-{seed}.json.gz"
                        path = zoo / "episodes" / row["task_id"].replace("/", "__") / name
                        if not path.exists():
                            differing.append([row["task_id"], algorithm, arm, seed, "zoo_episode_not_found"])
                            continue
                        theirs = load(path)
                        compared += 1
                        same = [e["raw_output"] for e in theirs["events"]] == [
                            e["raw_output"] for e in mine["events"]
                        ] and [e["trusted_runtime_result"] for e in theirs["events"]] == [
                            e["trusted_runtime_result"] for e in mine["events"]
                        ]
                        if not same:
                            differing.append([row["task_id"], algorithm, arm, seed, "events_differ"])
    return {"compared": compared, "differing": differing, "overflowed": overflowed, "equal": not differing}


def expanded_sequence(report: dict) -> list[str]:
    return [
        e["trusted_runtime_result"]["expanded_state_id"]
        for e in report["events"]
        if e["trusted_runtime_result"]["status"] == "expanded"
    ]


def identity_gate_stage() -> dict:
    cells = {}
    verdicts = {}
    for algorithm in ALGORITHMS:
        per_observation = {}
        for observation in OBSERVATIONS:
            pairs = []
            for task_id in pooled_task_ids():
                exact = load(control_path(task_id, algorithm, observation, "exact_reference", TEACHER_SEED))
                rand = load(control_path(task_id, algorithm, observation, "random_valid", TEACHER_SEED))
                headroom = sum(1 for e in exact["events"] if len(e["menu"]) >= 2)
                pairs.append(
                    {
                        "task_id": task_id,
                        "headroom_decisions": headroom,
                        "non_trivial": headroom > 0,
                        "divergent": expanded_sequence(exact) != expanded_sequence(rand)
                        or exact["result"]["decision_count"] != rand["result"]["decision_count"],
                    }
                )
            divergent = sum(1 for p in pairs if p["divergent"] and p["non_trivial"])
            per_observation[observation] = {
                "pairs": pairs,
                "non_trivial": sum(p["non_trivial"] for p in pairs),
                "divergent_non_trivial": divergent,
            }
        cells[algorithm] = per_observation
        verdicts[algorithm] = (
            "CHOICE_SENSITIVE"
            if all(per_observation[o]["divergent_non_trivial"] >= 1 for o in OBSERVATIONS)
            else "ZERO_DECISION_HEADROOM"
        )
    report = {"schema_version": "choice_frontier_v7_identity_gate_v1", "verdicts": verdicts, "cells": cells}
    write(OUT / "controls" / "identity-gate.json", report)
    return {
        "verdicts": verdicts,
        "divergent": {a: {o: cells[a][o]["divergent_non_trivial"] for o in OBSERVATIONS} for a in ALGORITHMS},
    }


# ============================================================================ model episodes


def episode_paths(stage: str, cell: dict, task_id: str) -> tuple[Path, Path, Path]:
    base = ROOT / OUT / stage
    name = f"{cell['algorithm']}-{cell['observation']}-{cell['condition']}-s{cell.get('seed', 0)}"
    task_name = task_id.replace("/", "__")
    episode = base / "episodes" / task_name / f"{name}.json.gz"
    return episode, episode.with_name(episode.name + ".partial.json.gz"), base / "views" / task_name / name


def session_for(task: dict, cell: dict, views: NodeChoiceTaskViews, checkpoint: str | None) -> NodeChoiceSession:
    algorithm = cell["algorithm"]
    row = task["row"]
    arm = {"learned_adapter": "process_sft", "zero_shot_base": "zero_shot_base"}[cell["condition"]]
    return NodeChoiceSession(
        authority=views.authority,
        task=NodeChoiceTask(
            row["task_id"], row["domain"], algorithm, int(row["reference_costs"][algorithm]["expansions"])
        ),
        observation=cell["observation"],
        arm=arm,
        seed=INFERENCE_SEED,
        adapter_id=checkpoint,
        token_limit=TOKEN_LIMIT,
        token_counter=placeholder_counter(
            algorithm, cell["observation"], views.text, views.page_counts(), system=system_message(cell)
        ),
    )


def system_message(cell: dict) -> str:
    """The complete system message the model receives (zero-shot appends the #141 format sentence)."""

    if cell["condition"] == "zero_shot_base":
        return zero_shot_system(cell["algorithm"], cell["observation"])
    return SYSTEM_MESSAGES[cell["algorithm"]]


def observe(views: NodeChoiceTaskViews, session: NodeChoiceSession, request, cell: dict, *, pixels: bool) -> dict:
    """The model input; its binding token count covers the complete input, system message included."""

    return views.observe_nodes(
        cell["algorithm"],
        cell["observation"],
        dict(request.model_input),
        session.menu_states(request),
        pixels=pixels,
        system=system_message(cell),
    )


def submitted_output(cell: dict, raw: str) -> tuple[str, str | None]:
    if cell["condition"] != "zero_shot_base":
        return raw, None
    from scripts.run_choice_frontier_v6_zero_shot import extract_choice

    return extract_choice(raw)


def register_admissions(session, views, event) -> None:
    result = event["trusted_runtime_result"]
    if result.get("status") != "expanded":
        return
    expanded = session.controller._states_by_ref[result["expanded_state_id"]]
    for admission in result["admissions"]:
        views.register(expanded, admission["action"])


def binding_of(example: dict, session: NodeChoiceSession, request) -> dict:
    binding = example["binding"]
    expected = session.token_counter(dict(request.model_input), session.menu_states(request))
    if binding["input_tokens"] != expected:
        raise ValueError("node-choice observation token count differs from the overflow counter")
    return binding


def identity(stage: str, cell: dict, task_id: str, checkpoint: str | None) -> dict:
    episode, _partial, view_output = episode_paths(stage, cell, task_id)
    return {
        "schema_version": EPISODE_SCHEMA,
        "protocol_id": protocol()["protocol_id"],
        "stage": stage,
        "task_id": task_id,
        "algorithm": cell["algorithm"],
        "observation": cell["observation"],
        "condition": cell["condition"],
        "training_seed": cell.get("seed"),
        "inference_seed": INFERENCE_SEED,
        "checkpoint": checkpoint,
        "output": str(episode.relative_to(ROOT)),
        "view_output": str(view_output.relative_to(ROOT)),
        "model_id": protocol()["model_id"],
        "model_revision": protocol()["model_revision"],
    }


def _replay_events(session, views, cell, events) -> None:
    for event in events:
        request = session.next_request()
        if request is None or dict(request.model_input) != event["input"]:
            raise ValueError("node-choice journal replay input differs")
        if [dict(e) for e in request.menu_binding] != event["menu"]:
            raise ValueError("node-choice journal replay menu differs")
        binding = binding_of(observe(views, session, request, cell, pixels=False), session, request)
        if binding != event["view"]:
            raise ValueError("node-choice journal replay view binding differs")
        submitted, rule = submitted_output(cell, event["model_text"])
        if submitted != event["raw_output"] or rule != event.get("extraction_rule"):
            raise ValueError("node-choice journal replay extraction differs")
        session.submit_output(submitted)
        committed = session.events[-1]
        if committed["trusted_runtime_result"] != event["trusted_runtime_result"]:
            raise ValueError("node-choice journal replay runtime result differs")
        register_admissions(session, views, committed)


def run_model_episode(
    stage: str, task: dict, cell: dict, checkpoint: str | None, endpoint: str, generate
) -> tuple[dict, bool]:
    from PIL import Image

    task_id = task["row"]["task_id"]
    episode, partial_path, view_output = episode_paths(stage, cell, task_id)
    expected = identity(stage, cell, task_id, checkpoint)
    if episode.exists():
        if partial_path.exists():
            raise ValueError("completed node-choice episode retains a conflicting partial journal")
        report = load(episode)
        if any(report.get(k) != v for k, v in expected.items()):
            raise ValueError("retained node-choice episode binding differs")
        replay_model_episode(task, report, endpoint)
        return report, True
    views = NodeChoiceTaskViews(ROOT, task, view_output, endpoint)
    session = session_for(task, cell, views, checkpoint)
    saved = (
        load(partial_path)
        if partial_path.exists()
        else {
            **expected,
            "decision_cap": session.decision_cap,
            "events": [],
            "call_measurements": [],
            "pending": None,
            "started": time.time(),
        }
    )
    if any(saved.get(k) != v for k, v in expected.items()):
        raise ValueError("partial node-choice episode binding differs")
    _replay_events(session, views, cell, saved["events"])

    def commit(pending: dict) -> None:
        request = session.next_request()
        if request is None or dict(request.model_input) != pending["input"]:
            raise ValueError("persisted pending node-choice output no longer matches the request")
        submitted, rule = submitted_output(cell, pending["model_text"])
        session.submit_output(submitted)
        committed = dict(session.events[-1])
        committed.update(view=pending["binding"], model_text=pending["model_text"], extraction_rule=rule)
        session.events[-1] = committed
        register_admissions(session, views, committed)
        saved["events"].append(committed)
        saved["call_measurements"].append(pending["measurement"])
        saved["pending"] = None
        views.save()

    if saved.get("pending") is not None:
        pending = saved["pending"]
        request = session.next_request()
        if request is None:
            raise ValueError("persisted pending node-choice output has no request")
        if binding_of(observe(views, session, request, cell, pixels=False), session, request) != pending["binding"]:
            raise ValueError("persisted pending node-choice output has a different view binding")
        commit(pending)
    write(partial_path, saved)
    while (request := session.next_request()) is not None:
        example = observe(views, session, request, cell, pixels=True)
        binding = binding_of(example, session, request)
        started = time.monotonic()
        try:
            text, generated_tokens = generate(example)
        finally:
            for image in example["images"]:
                if isinstance(image, Image.Image):
                    image.close()
        saved["pending"] = {
            "input": dict(request.model_input),
            "binding": binding,
            "model_text": text,
            "measurement": {
                "event_index": len(session.events),
                "input_tokens": binding["input_tokens"],
                "generated_sequence_tokens": generated_tokens,
                "call_wall_seconds": time.monotonic() - started,
            },
        }
        write(partial_path, saved)
        commit(saved["pending"])
        write(partial_path, saved)
    report = {
        **expected,
        "decision_cap": session.decision_cap,
        "token_limit": session.token_limit,
        "events": saved["events"],
        "result": session.result(),
        "call_measurements": saved["call_measurements"],
        "started": saved["started"],
        "finished": time.time(),
        "outcome": "RECORDED",
    }
    views.save()
    write(episode, report)
    partial_path.unlink()
    return report, False


def replay_model_episode(task: dict, report: dict, endpoint: str) -> dict:
    cell = {
        "algorithm": report["algorithm"],
        "observation": report["observation"],
        "condition": report["condition"],
        "seed": report["training_seed"],
    }
    _episode, _partial, view_output = episode_paths(report["stage"], cell, report["task_id"])
    views = NodeChoiceTaskViews(ROOT, task, view_output, endpoint, read_only=True)
    session = session_for(task, cell, views, report.get("checkpoint"))
    if session.decision_cap != int(report["decision_cap"]):
        raise ValueError("node-choice replay decision cap differs")
    _replay_events(session, views, cell, report["events"])
    if session.next_request() is not None or not session.complete:
        raise ValueError("node-choice replay did not end where the stored episode ended")
    if session.result() != report["result"]:
        raise ValueError("node-choice replay result differs")
    return session.result()


# ============================================================================ training


class NodeChoiceDataset:
    """(record, augmentation) samples in the pinned ``order:17`` sequence, observation-specific."""

    def __init__(self, store: dict, membership: dict, algorithm: str, observation: str, split: str):
        self.store, self.algorithm, self.observation = store, algorithm, observation
        cell = membership["cells"][algorithm]
        if split == "train":
            self.samples = [(rid, copy) for rid in cell["training"] for copy in range(AUGMENTATIONS)]
            random.Random(ORDER_SEED).shuffle(self.samples)
        else:
            self.samples = [(rid, None) for rid in cell["diagnostic"]]
        self.records = [{"record_id": f"{rid}#aug{copy}" if copy is not None else rid} for rid, copy in self.samples]
        self._contexts: dict[str, Any] = {}

    def __len__(self):
        return len(self.samples)

    def context(self, view_key: str):
        if view_key not in self._contexts:
            authority, source = authority_of(self.store["tasks"][view_key]["task_path"])
            self._contexts[view_key] = text_context(authority, source["domain_pddl"], source["problem_pddl"])
        return self._contexts[view_key]

    def __getitem__(self, index):
        rid, copy = self.samples[index]
        return training_example(self.store, rid, copy, self.observation, self.context)


def training_example(store: dict, rid: str, copy: int | None, observation: str, context_of) -> dict:
    record = store["records"][rid]
    task = store["tasks"][record["view_key"]]
    if copy is None:
        menu, indices, target = record["menu"], record["menu_indices"], record["teacher_choice"]
    else:
        menu, indices, target = v3.augment_menu(
            rid, record["menu"], record["menu_indices"], record["teacher_state_ref"], copy
        )
    choices = [entry["choice"] for entry in menu]
    states = [StateView(*task["states"][str(i)]) for i in indices]
    model_input = {
        "algorithm": record["algorithm"],
        "frontier_menu": {"choices": choices},
        "representation": REPRESENTATIONS[observation],
        "schema_version": NODE_CHOICE_SCHEMA,
    }
    payload = node_payload(model_input, observation, context_of(record["view_key"]), states)

    def loader(label: str, path: str):
        from PIL import Image

        with Image.open(ROOT / path) as stored:
            return stored.convert("RGB")

    example = build_node_observation(
        algorithm=record["algorithm"],
        observation=observation,
        payload=payload,
        static_pages=task["static_pages"] if observation != "text" else [],
        goal_pages=task["goal_pages"] if observation != "text" else [],
        scene_path=(lambda i: task["scenes"][str(i)]) if observation != "text" else None,
        menu_indices=indices if observation != "text" else None,
        loader=loader if observation != "text" else None,
    )
    tokens = example["binding"]["input_tokens"]
    if copy is None and observation in record["input_tokens"] and tokens != record["input_tokens"][observation]:
        raise ValueError(f"node-choice input tokens differ from the frozen preparation: {rid}")
    if tokens > TOKEN_LIMIT:
        raise ValueError(f"node-choice training example exceeds the token limit: {rid}")
    example["messages"].append({"role": "assistant", "content": canonical_choice(target)})
    return example


def training_dir(algorithm: str, observation: str, seed: int) -> Path:
    return OUT / "training" / algorithm / observation / f"seed-{seed}"


def adapter_dir(algorithm: str, observation: str, seed: int) -> Path:
    if algorithm in ADDITIVE_ALGORITHMS and observation == "visual":
        return v4p.adapter_dir(algorithm, seed).relative_to(ROOT)
    return training_dir(algorithm, observation, seed) / "final"


def verify_final(algorithm: str, observation: str, seed: int) -> dict:
    output = ROOT / training_dir(algorithm, observation, seed)
    config_path = output / "final" / "adapter_config.json"
    if not (output / "final" / "adapter_model.safetensors").is_file() or not config_path.is_file():
        raise ValueError("final adapter missing")
    result = load(output / "result.json")
    config = load(config_path)
    records = len(load(MEMBERSHIP_PATH)["cells"][algorithm]["training"])
    checks = {
        "r_64": config.get("r") == 64,
        "alpha_128": config.get("lora_alpha") == 128,
        "dropout_0_05": config.get("lora_dropout") == 0.05,
        "steps": result["steps"] == math.ceil(records * AUGMENTATIONS / 32),
        "seed": result["seed"] == seed,
        "samples": result["train_records"] == records * AUGMENTATIONS,
    }
    if not all(checks.values()):
        raise ValueError(f"trained cell audit failed: {checks}")
    return checks


def run_train(algorithm: str, observation: str, seed: int, *, deadline: float, progress) -> dict:
    from examples.planning_benchmark_slice.visual_model import train_visual

    p = protocol()
    output = ROOT / training_dir(algorithm, observation, seed)
    membership = load(MEMBERSHIP_PATH)
    if membership_sha(membership) != membership["membership_sha256"]:
        raise ValueError("v7 membership sha differs")
    try:
        checks = verify_final(algorithm, observation, seed)
        resumed = "final"
    except (ValueError, FileNotFoundError):
        checks = None
    if checks is None:
        if (output / "final").exists():
            shutil.rmtree(output / "final")
        checkpoints = sorted(output.glob("checkpoint-*"), key=lambda path: int(path.name.split("-")[-1]))
        for path in checkpoints:
            if not (path / "trainer_state.json").is_file():
                shutil.rmtree(path)
        checkpoints = sorted(output.glob("checkpoint-*"), key=lambda path: int(path.name.split("-")[-1]))
        resumed = checkpoints[-1].name if checkpoints else None
        store = load(OUT / "preparation" / "store.json.gz")
        study = load(STUDY_V5)
        if sha256_file(ROOT / STUDY_V5) != p["training"]["study_sha256"]:
            raise ValueError("study-v5 sha differs")
        config = {**study, "modality": f"{observation}-node-choice", "training_seed": int(seed)}

        def factory(root, config_, algo, split):
            return NodeChoiceDataset(store, membership, algo, observation, "train" if split == "train" else "dev")

        started = time.monotonic()
        result = train_visual(
            config,
            ROOT,
            algorithm,
            output,
            deadline=deadline,
            progress=progress,
            resume=True,
            dataset_factory=factory,
            save_steps=CHECKPOINT_EVERY,
            save_total_limit=1,
        )
        expected = [
            r["record_id"] for r in NodeChoiceDataset(store, membership, algorithm, observation, "train").records
        ]
        if result["training_record_ids"] != expected:
            raise ValueError("trained sample order differs from the pinned order:17 sequence")
        result["training_order_sha256"] = sha256_text(canonical(expected))
        result["training_record_ids"] = result["training_record_ids"][:8]
        write(
            output / "result.json",
            {
                **result,
                "wall_seconds_this_attempt": time.monotonic() - started,
                "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
                "master_port": os.environ.get("MASTER_PORT"),
                "resumed_from": resumed,
            },
        )
        checks = verify_final(algorithm, observation, seed)
    for path in output.glob("checkpoint-*"):
        shutil.rmtree(path)
    return {"cell": [algorithm, observation, seed], "resumed_from": resumed, "audit": checks}


# ============================================================================ evaluation units


def load_policy(adapters: dict[str, str]):
    from transformers import set_seed

    from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
    from examples.planning_benchmark_slice.visual_model import VisualPolicy

    inference = protocol()["evaluation"]["inference"]
    set_seed(INFERENCE_SEED)
    policy = VisualPolicy(
        model_id=protocol()["model_id"],
        revision=protocol()["model_revision"],
        adapter_paths={k: ROOT / v for k, v in adapters.items()},
        device="cuda:0",
        max_context_tokens=32768,
        max_new_tokens=384,
        max_batch_size=inference["max_batch_size"],
        max_batch_input_tokens=inference["max_padded_batch_input_tokens"],
        inference_dtype=inference["dtype"],
    )
    configure_visual_attention(policy.model, inference["attention"])
    policy.identity.update(memoize_identical_inputs=False)
    return policy


def generator(adapter_key: str | None, adapters: dict[str, str], deadline: float, state: dict) -> Callable:
    inference = protocol()["evaluation"]["inference"]

    def generate(example):
        if state.get("policy") is None:
            state["policy"] = load_policy(adapters)
            state["policy"].stop_at = deadline
        policy = state["policy"]
        cap = inference["max_padded_batch_input_tokens"]
        above = example["binding"]["input_tokens"] > cap
        policy.max_batch_input_tokens = inference["single_input_above_batch_cap_up_to"] if above else cap
        try:
            output = policy.generate([example], adapter_key)[0]
        finally:
            policy.max_batch_input_tokens = cap
        state["calls"] = state.get("calls", 0) + 1
        return output, policy.last_generation_usage["generated_sequence_tokens"]

    return generate


def free_policy(state: dict) -> None:
    if state.get("policy") is not None:
        del state["policy"]
        gc.collect()
        import torch

        torch.cuda.empty_cache()


def smoke_path(algorithm: str, observation: str) -> Path:
    return OUT / "smoke" / f"{algorithm}-{observation}.json"


def smoke_verdict(algorithm: str, observation: str) -> str | None:
    path = ROOT / smoke_path(algorithm, observation)
    return load(path)["gate"] if path.exists() else None


def run_smoke(algorithm: str, observation: str, *, gpu: int, deadline: float, progress) -> dict:
    checkpoint = str(adapter_dir(algorithm, observation, 17))
    cell = {"algorithm": algorithm, "observation": observation, "condition": "learned_adapter", "seed": 17}
    state: dict = {}
    generate = generator(algorithm, {algorithm: checkpoint}, deadline, state)
    rows = []
    try:
        for row in panel_rows("smoke"):
            task = panel_views_task(row["task_id"])
            report, _retained = run_model_episode("smoke", task, cell, checkpoint, backend(gpu), generate)
            accepted = sum(1 for e in report["events"] if e["trusted_runtime_result"]["accepted"])
            seconds = [m["call_wall_seconds"] for m in report["call_measurements"]]
            rows.append(
                {
                    "task_id": row["task_id"],
                    "calls": len(report["events"]),
                    "accepted": accepted,
                    "result": report["result"],
                    "seconds_per_call": sum(seconds) / len(seconds) if seconds else None,
                }
            )
            progress("smoke", cell=f"{algorithm}/{observation}", task=row["task_id"])
    finally:
        free_policy(state)
    calls = sum(r["calls"] for r in rows)
    rate = sum(r["accepted"] for r in rows) / calls if calls else 0.0
    result = {
        "algorithm": algorithm,
        "observation": observation,
        "rate": rate,
        "calls": calls,
        "threshold": SMOKE_THRESHOLD,
        "gate": "PASS" if rate >= SMOKE_THRESHOLD else "FAIL",
        "episodes": rows,
    }
    write(smoke_path(algorithm, observation), result)
    return result


def run_evaluation(
    stage: str, algorithm: str, observation: str, seed: int | None, *, gpu: int, deadline: float, progress
) -> dict:
    if stage == "evaluation":
        gate = smoke_verdict(algorithm, observation)
        if gate != "PASS":
            if gate is None:
                raise ValueError("learned evaluation before its smoke gate")
            return {"outcome": "SMOKE_GATED", "gate": gate}
        condition, checkpoint = "learned_adapter", str(adapter_dir(algorithm, observation, int(seed)))
        adapters, key = {algorithm: checkpoint}, algorithm
    else:
        condition, checkpoint, adapters, key = "zero_shot_base", None, {}, None
    cell = {"algorithm": algorithm, "observation": observation, "condition": condition, "seed": seed or 0}
    state: dict = {}
    generate = generator(key, adapters, deadline, state)
    episodes = []
    try:
        for task_id in pooled_task_ids():
            task = panel_views_task(task_id)
            report, retained = run_model_episode(stage, task, cell, checkpoint, backend(gpu), generate)
            episodes.append({"task_id": task_id, "retained": retained, "result": report["result"]})
            progress(stage, cell=f"{algorithm}/{observation}/s{seed}", completed=len(episodes), total=23)
    finally:
        free_policy(state)
    return {"outcome": "PASS", "episodes": episodes, "calls_this_attempt": state.get("calls", 0)}


# ============================================================================ queue


def new_cells() -> list[tuple[str, str]]:
    return [(a, o) for a in ALGORITHMS for o in OBSERVATIONS if not (a in ADDITIVE_ALGORITHMS and o == "visual")]


def slots() -> list[dict]:
    result = []
    for algorithm, observation in new_cells():
        for seed in SEEDS:
            stages = [f"train:{algorithm}:{observation}:{seed}"]
            if seed == 17:
                stages.append(f"smoke:{algorithm}:{observation}")
            result.append({"key": f"train-{algorithm}-{observation}-s{seed}", "stages": stages, "needs": []})
    for algorithm, observation in new_cells():
        for seed in SEEDS:
            result.append(
                {
                    "key": f"evaluation-{algorithm}-{observation}-s{seed}",
                    "stages": [f"evaluation:{algorithm}:{observation}:{seed}"],
                    "needs": [f"train:{algorithm}:{observation}:{seed}", f"smoke:{algorithm}:{observation}"],
                }
            )
    for algorithm in ALGORITHMS:
        for observation in OBSERVATIONS:
            result.append(
                {
                    "key": f"zeroshot-{algorithm}-{observation}",
                    "stages": [f"zeroshot:{algorithm}:{observation}"],
                    "needs": [],
                }
            )
    return result


def receipt_path(unit: str) -> Path:
    return ROOT / QUEUE / "receipts" / f"{unit.replace(':', '__')}.json"


def unit_done(unit: str) -> bool:
    return receipt_path(unit).exists()


def this_boot() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except FileNotFoundError:
        return "unknown"


def worker_handle(gpu: int | None) -> dict:
    from examples.planning_benchmark_slice.expanded_scheduler import handle

    return {
        **handle(os.getpid()),
        "host": socket.gethostname(),
        "boot_id": this_boot(),
        "gpu": gpu,
        "claimed": time.time(),
    }


def claim_live(claim: dict | None) -> bool:
    from examples.planning_benchmark_slice.expanded_scheduler import alive

    return bool(
        claim and claim.get("host") == socket.gethostname() and claim.get("boot_id") == this_boot() and alive(claim)
    )


@contextlib.contextmanager
def queue_state():
    directory = ROOT / QUEUE
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "queue.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = directory / "claims.json"
        state = json.loads(path.read_text()) if path.exists() else {"claims": {}, "failures": {}, "history": []}
        yield state
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(state, indent=1) + "\n")
        temporary.replace(path)


def slot_done(slot: dict) -> bool:
    return all(unit_done(u) for u in slot["stages"])


def claim_next(gpu: int, handle: dict) -> dict | None:
    with queue_state() as state:
        for slot in slots():
            key = slot["key"]
            if slot_done(slot) or not all(unit_done(u) for u in slot["needs"]):
                continue
            claim = state["claims"].get(key)
            if claim is not None and claim_live(claim):
                continue
            if len(state["failures"].get(key, [])) >= MAX_SLOT_FAILURES:
                continue
            if claim is not None:
                state["history"].append({"event": "stale_reclaimed", "slot": key, "stale": claim, "time": time.time()})
            state["claims"][key] = handle
            state["history"].append({"event": "claimed", "slot": key, "gpu": gpu, "time": time.time()})
            return slot
    return None


def release(key: str, handle: dict, failure: str | None = None) -> None:
    with queue_state() as state:
        claim = state["claims"].get(key)
        if claim is not None and (claim["pid"], claim["start_ticks"]) != (handle["pid"], handle["start_ticks"]):
            raise ValueError("release by a worker that does not own the claim")
        state["claims"].pop(key, None)
        if failure is not None:
            state["failures"].setdefault(key, []).append({"time": time.time(), "error": failure[-4000:]})
        state["history"].append({"event": "failed" if failure else "released", "slot": key, "time": time.time()})


def charged_gpu_hours(ledger: dict, now: float | None = None) -> float:
    now = time.time() if now is None else now
    total = 0.0
    for attempt in ledger.get("attempts", []):
        if attempt["status"] == "running":
            total += max(0.0, now - attempt.get("started", now)) * len(attempt["gpus"]) / 3600
        elif attempt["status"] != "reserved":
            total += attempt.get("gpu_hours") or 0.0
    return total


def ledger() -> dict:
    path = ROOT / LEDGER
    return json.loads(path.read_text()) if path.exists() else {"attempts": []}


def backend(gpu: int) -> str:
    return f"http://127.0.0.1:{GPU_BACKEND_PORTS[gpu]}"


def run_unit(unit: str, *, gpu: int, deadline: float, progress) -> dict:
    kind, *parts = unit.split(":")
    started = time.time()
    if kind == "train":
        body = run_train(parts[0], parts[1], int(parts[2]), deadline=deadline, progress=progress)
    elif kind == "smoke":
        body = run_smoke(parts[0], parts[1], gpu=gpu, deadline=deadline, progress=progress)
    elif kind == "evaluation":
        body = run_evaluation(
            "evaluation", parts[0], parts[1], int(parts[2]), gpu=gpu, deadline=deadline, progress=progress
        )
    elif kind == "zeroshot":
        body = run_evaluation("zeroshot", parts[0], parts[1], None, gpu=gpu, deadline=deadline, progress=progress)
    else:
        raise ValueError(unit)
    receipt = {
        "unit": unit,
        **body,
        "gpu": gpu,
        "host": socket.gethostname(),
        "started": started,
        "finished": time.time(),
        "attempt_dir": os.environ.get("EXPANDED_ATTEMPT_DIR"),
    }
    write(receipt_path(unit), receipt)
    return receipt


def attempt_deadline() -> float:
    directory = os.environ.get("EXPANDED_ATTEMPT_DIR")
    if not directory or not (ROOT / LEDGER).exists():
        return float("inf")
    from examples.planning_benchmark_slice.expanded_scheduler import timestamp

    state = ledger()
    attempt = next((a for a in state["attempts"] if a.get("directory") == directory), None)
    if attempt is None:
        return float("inf")
    wall = min(attempt["admitted"] + attempt["max_seconds"], timestamp(state["schedule"]["gpu_cutoff_utc"]))
    return time.monotonic() + (wall - DEADLINE_MARGIN_SECONDS - time.time())


def worker(gpu: int, max_slots: int | None = None) -> dict:
    if os.environ.get("CUDA_VISIBLE_DEVICES") != str(gpu):
        raise ValueError(f"worker --gpu {gpu} requires CUDA_VISIBLE_DEVICES={gpu}")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("worker requires a scheduler-assigned MASTER_PORT")
    ensure_backend([GPU_BACKEND_PORTS[gpu]])
    deadline = attempt_deadline()
    handle = worker_handle(gpu)
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"]) if os.environ.get("EXPANDED_PROGRESS_PATH") else None
    log, stop_reason, consecutive, processed = [], "queue_empty", 0, 0

    def progress(stage, **values):
        record = {"time": time.time(), "stage": stage, **values}
        print(json.dumps(record), flush=True)
        if progress_path is not None:
            write(
                progress_path,
                {"completed": sum(slot_done(s) for s in slots()), "total": len(slots()), "current": record},
            )

    while True:
        charged = charged_gpu_hours(ledger())
        if charged > BUDGET_STOP_GPU_HOURS:
            stop_reason = f"budget: charged {charged:.1f} GPU-h > {BUDGET_STOP_GPU_HOURS}"
            break
        if deadline - time.monotonic() < MIN_CLAIM_SECONDS:
            stop_reason = "attempt deadline too close to claim a new slot"
            break
        if max_slots is not None and processed >= max_slots:
            stop_reason = "max_slots"
            break
        slot = claim_next(gpu, handle)
        if slot is None:
            if any(not slot_done(s) for s in slots()) and waiting_on_other_worker():
                time.sleep(120)
                continue
            break
        processed += 1
        progress("claimed", slot=slot["key"], charged_gpu_hours=charged)
        try:
            for unit in slot["stages"]:
                if not unit_done(unit):
                    run_unit(unit, gpu=gpu, deadline=deadline, progress=progress)
                    progress("unit_done", unit=unit)
            release(slot["key"], handle)
            log.append({"slot": slot["key"], "outcome": "PASS"})
            consecutive = 0
        except Exception as error:
            if time.monotonic() >= deadline and str(error).startswith("VALID_STOP"):
                release(slot["key"], handle)
                log.append({"slot": slot["key"], "outcome": "DEADLINE"})
                stop_reason = "attempt deadline (valid stop; resumable)"
                break
            text = traceback.format_exc()
            print(text, flush=True)
            release(slot["key"], handle, failure=text)
            log.append({"slot": slot["key"], "outcome": "FAILED", "error": repr(error)})
            consecutive += 1
            with contextlib.suppress(Exception):
                import torch

                gc.collect()
                torch.cuda.empty_cache()
            if consecutive >= MAX_CONSECUTIVE_FAILURES:
                raise RuntimeError(f"{consecutive} consecutive slot failures; stopping worker") from error
    result = {"gpu": gpu, "stop_reason": stop_reason, "slots": log, "queue": queue_summary()}
    if os.environ.get("EXPANDED_ATTEMPT_DIR"):
        write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json", result)
    return result


def waiting_on_other_worker() -> bool:
    """Pending slots blocked only by units another live worker is running."""

    path = ROOT / QUEUE / "claims.json"
    state = json.loads(path.read_text()) if path.exists() else {"claims": {}, "failures": {}}
    live = any(claim_live(c) and c.get("pid") != os.getpid() for c in state["claims"].values())
    return live


def queue_summary() -> dict:
    path = ROOT / QUEUE / "claims.json"
    state = json.loads(path.read_text()) if path.exists() else {"claims": {}, "failures": {}}
    counts = {"done": 0, "running": 0, "blocked": 0, "waiting": 0, "pending": 0}
    running, blocked = [], []
    for slot in slots():
        claim = state["claims"].get(slot["key"])
        if slot_done(slot):
            counts["done"] += 1
        elif claim is not None and claim_live(claim):
            counts["running"] += 1
            running.append({"slot": slot["key"], "gpu": claim.get("gpu")})
        elif len(state["failures"].get(slot["key"], [])) >= MAX_SLOT_FAILURES:
            counts["blocked"] += 1
            blocked.append({"slot": slot["key"], "error": state["failures"][slot["key"]][-1]["error"][-400:]})
        elif not all(unit_done(u) for u in slot["needs"]):
            counts["waiting"] += 1
        else:
            counts["pending"] += 1
    return {
        "slots": len(slots()),
        **counts,
        "running_slots": running,
        "blocked_slots": blocked,
        "failures": {k: len(v) for k, v in state["failures"].items()},
    }


# ============================================================================ scheduler plumbing


def schedule_document() -> dict:
    p = protocol()
    return {
        "program_id": "choice-frontier-v7",
        "status": "authorized_followup_window",
        "issue": 146,
        "authorization": {
            "granted_by": "author decision 2026-09-27 (docs/experiments/choice-frontier/issue-146-feasibility.md)",
            "window_gpu_hours_cap": GPU_HOURS_CAP,
            "basis": "30 training cells + 30 learned and 12 zero-shot evaluation cells on P2+P2u; ~227 GPU-h expected,"
            " ~325 at the 2R cap",
        },
        "start_utc": "2026-09-27T00:00:00Z",
        "gpu_cutoff_utc": p["hardware"]["gpu_cutoff_utc"],
        "handoff_deadline_utc": "2026-10-11T12:00:00Z",
        "deadline_kind": "soft_handoff",
        "hardware": {
            "gpus": 2,
            "model": p["hardware"]["model"],
            "host": p["hardware"]["host"],
            "preserve_unrelated_processes": True,
            "max_own_model_workers_per_gpu": 1,
        },
        "experiment_gpu_hours_cap": GPU_HOURS_CAP,
        "allocations_gpu_hours": {"choice_frontier": GPU_HOURS_CAP},
        "accounting": {
            "metric": "sum of own allocated model-worker GPU durations across devices; include model loading, saves, "
            "failures and retries",
            "ledger": str(LEDGER),
            "worker_stop_rule": f"a worker claims no new slot once charged GPU-h exceeds {BUDGET_STOP_GPU_HOURS}",
            "preserve_prior_ledgers": True,
            "reset_on_resume": False,
            "automatic_total_extension": False,
            "transfers": "none; independent of every prior window",
        },
        "master_port_pool": list(MASTER_PORT_POOL),
        "backend_ports": {"gpu0": GPU_BACKEND_PORTS[0], "gpu1": GPU_BACKEND_PORTS[1], "cpu": PREP_BACKEND_PORT},
        "qualification_safety_factor": 1.25,
        "execution_authorization": "protocol committed before any derivation; membership and panels committed before "
        "any control or training; code and job files committed before their first launch; "
        "no outcome-selected variants; independent replay of every episode",
    }


def ensure_schedule() -> dict:
    path = ROOT / SCHEDULE
    document = schedule_document()
    if path.exists():
        if json.loads(path.read_text()) != document:
            raise ValueError(f"{SCHEDULE} differs from the frozen schedule")
        return document
    write(SCHEDULE, document)
    return document


def job_document(gpu: int, job_id: str, max_seconds: int, reason: str | None) -> dict:
    job = {
        "job_id": job_id,
        "branch": "choice_frontier",
        "gpus": [gpu],
        "max_seconds": int(max_seconds),
        "total": len(slots()),
        "command": [
            "bash",
            "-lc",
            f"source {ENV_SCRIPT} && export CUDA_VISIBLE_DEVICES={gpu} && "
            "export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True && "
            f"exec python scripts/run_choice_frontier_v7.py worker --gpu {gpu}",
        ],
        "completion_hook": [
            "bash",
            "-lc",
            f"source {ENV_SCRIPT} && export CUDA_VISIBLE_DEVICES= && exec python scripts/run_choice_frontier_v7.py hook",
        ],
    }
    if reason:
        job["resume_reason"] = reason
    return job


def launch(gpus=(0, 1), reason: str | None = None, dry_run: bool = False, write_only: bool = False) -> list[dict]:
    """Launch one queue worker per GPU; ``write_only`` writes the job files (for committing before launch)."""

    from examples.planning_benchmark_slice.expanded_scheduler import alive, charged, timestamp

    schedule = ensure_schedule()
    state = ledger()
    plan = []
    for gpu in gpus:
        base = f"cfv7-worker-gpu{gpu}"
        attempts = [a for a in state["attempts"] if a["job_id"].startswith(base)]
        active = [a for a in attempts if a["status"] in ("reserved", "running")]
        if active:
            plan.append(
                {
                    "gpu": gpu,
                    "action": "skip",
                    "job_id": active[-1]["job_id"],
                    "live": alive(active[-1].get("supervisor")),
                }
            )
            continue
        if not attempts:
            job_id, needs = base, False
        elif attempts[-1]["status"] == "succeeded":
            job_id, needs = f"{base}-r{len({a['job_id'] for a in attempts}) + 1}", False
        else:
            job_id, needs = attempts[-1]["job_id"], True
        plan.append({"gpu": gpu, "action": "launch", "job_id": job_id, "needs_reason": needs})
    launching = [p for p in plan if p["action"] == "launch"]
    if not launching or all(slot_done(s) for s in slots()):
        return plan
    remaining = GPU_HOURS_CAP - sum(charged(a) for a in state["attempts"])
    seconds = int(
        min(
            WORKER_MAX_SECONDS,
            remaining * 3600 / len(launching) - 60,
            timestamp(schedule["gpu_cutoff_utc"]) - time.time() - 300,
        )
    )
    if seconds < 3600:
        raise ValueError(f"cannot admit a worker: {seconds} s left under the budget/cutoff")
    for item in launching:
        text = reason if item["needs_reason"] else None
        if item["needs_reason"] and not text:
            text = "relaunch after an interrupted/failed attempt; queue claims, checkpoints and journals resume"
        job_path = CONFIG / f"{item['job_id']}-job.json"
        item.update(job=str(job_path), max_seconds=seconds)
        if dry_run:
            item["action"] = "would_launch"
            continue
        if (ROOT / job_path).exists() and not item["needs_reason"]:
            job = json.loads((ROOT / job_path).read_text())
            if job["job_id"] != item["job_id"] or job["gpus"] != [item["gpu"]]:
                raise ValueError(f"existing job file differs: {job_path}")
            item["max_seconds"] = job["max_seconds"]
        else:
            (ROOT / job_path).write_text(
                json.dumps(job_document(item["gpu"], item["job_id"], seconds, text), indent=1) + "\n"
            )
        if write_only:
            item["action"] = "job_written"
            continue
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/run_expanded_study.py",
                "launch",
                "--schedule",
                str(SCHEDULE),
                "--ledger",
                str(LEDGER),
                "--job",
                str(job_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        item["returncode"] = completed.returncode
        if completed.returncode:
            item["error"] = completed.stderr[-2000:]
        else:
            attempt = json.loads(completed.stdout)
            item.update(attempt=attempt["attempt"], master_port=attempt["master_port"])
    return plan


def reconcile() -> dict:
    if not (ROOT / LEDGER).exists():
        return {"skipped": "no ledger yet"}
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_expanded_study.py",
            "reconcile",
            "--schedule",
            str(SCHEDULE),
            "--ledger",
            str(LEDGER),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError("scheduler reconcile refused: " + completed.stderr[-2000:])
    return {
        "interrupted": [
            f"{a['job_id']}#{a['attempt']}"
            for a in json.loads(completed.stdout)["attempts"]
            if a["status"] == "interrupted"
        ]
    }


def backend_up(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(1.0)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def ensure_backend(ports, wait_seconds: float = 180) -> dict:
    down = [port for port in ports if not backend_up(port)]
    if not down:
        return {"backend": "already_up", "ports": list(ports)}
    directory = ROOT / OUT / "backend"
    directory.mkdir(parents=True, exist_ok=True)
    processes = {}
    for port in down:
        log = directory / f"backend-{port}-{int(time.time())}.log"
        command = f"source {ENV_SCRIPT} && exec {BACKEND_PYTHON} scripts/serve_issue70_planimation.py --port {port}"
        with log.open("a") as stream:
            processes[port] = subprocess.Popen(
                ["bash", "-lc", command], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True
            )
    deadline = time.time() + wait_seconds
    while time.time() < deadline and not all(backend_up(port) for port in down):
        if any(process.poll() is not None for process in processes.values()):
            break
        time.sleep(1)
    failed = [port for port in down if not backend_up(port)]
    if failed:
        raise RuntimeError(f"Planimation backend did not come up on {failed}; see {directory}")
    return {"backend": "started", "ports": list(ports), "pids": {p: pr.pid for p, pr in processes.items()}}


def status() -> dict:
    from examples.planning_benchmark_slice.expanded_scheduler import alive

    state = ledger()
    return {
        "queue": queue_summary(),
        "gpu_hours_charged": round(charged_gpu_hours(state), 3),
        "gpu_hours_stop_rule": BUDGET_STOP_GPU_HOURS,
        "attempts": [
            {
                "job": f"{a['job_id']}#{a['attempt']}",
                "status": a["status"],
                "gpus": a["gpus"],
                "live": alive(a.get("supervisor")) if a["status"] in ("reserved", "running") else None,
                "gpu_hours": round(a.get("gpu_hours") or 0.0, 3),
            }
            for a in state["attempts"]
        ],
        "smoke": {f"{a}/{o}": smoke_verdict(a, o) for a, o in new_cells()},
        "backends": {port: backend_up(port) for port in (*GPU_BACKEND_PORTS.values(), PREP_BACKEND_PORT)},
    }


def hook() -> dict:
    terminal_path = Path(os.environ["EXPANDED_TERMINAL_PATH"])
    terminal = json.loads(terminal_path.read_text())
    result_path = terminal_path.parent / "worker-result.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else {}
    summary = {
        "job": f"{terminal['job_id']}#{terminal['attempt']}",
        "status": terminal["status"],
        "returncode": terminal.get("returncode"),
        "stop_reason": result.get("stop_reason"),
        "queue": queue_summary(),
        "time": time.time(),
    }
    write(terminal_path.parent / "hook-summary.json", summary)
    return summary


# ============================================================================ finalize


def all_model_units() -> list[tuple[str, dict]]:
    units = []
    for algorithm, observation in new_cells():
        for seed in SEEDS:
            units.append(
                (
                    "evaluation",
                    {"algorithm": algorithm, "observation": observation, "condition": "learned_adapter", "seed": seed},
                )
            )
    for algorithm in ALGORITHMS:
        for observation in OBSERVATIONS:
            units.append(
                (
                    "zeroshot",
                    {"algorithm": algorithm, "observation": observation, "condition": "zero_shot_base", "seed": 0},
                )
            )
    return units


def _finalize_one(item) -> dict:
    stage, cell, task_id = item
    episode, partial, _views = episode_paths(stage, cell, task_id)
    key = [stage, cell["algorithm"], cell["observation"], cell["seed"], task_id]
    if not episode.exists():
        return {"key": key, "status": "missing", "partial": partial.exists()}
    report = load(episode)
    try:
        replay_model_episode(panel_views_task(task_id), report, backend(0))
    except Exception as error:  # recorded, never repaired
        return {"key": key, "status": "mismatch", "error": f"{type(error).__name__}: {error}"}
    return {"key": key, "status": "replayed"}


def finalize_stage(workers: int = 8) -> dict:
    from concurrent.futures import ProcessPoolExecutor

    ensure_backend([GPU_BACKEND_PORTS[0]])
    items = []
    for stage, cell in all_model_units():
        if stage == "evaluation" and smoke_verdict(cell["algorithm"], cell["observation"]) == "FAIL":
            continue
        for task_id in pooled_task_ids():
            items.append((stage, cell, task_id))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(_finalize_one, items))
    summary = {
        "bindings": len(rows),
        "replayed": sum(r["status"] == "replayed" for r in rows),
        "missing": [r["key"] for r in rows if r["status"] == "missing"],
        "mismatches": [r for r in rows if r["status"] == "mismatch"],
        "smoke": {f"{a}/{o}": smoke_verdict(a, o) for a, o in new_cells()},
    }
    summary["complete"] = not summary["missing"] and not summary["mismatches"]
    write(OUT / "evaluation-finalize.json", summary)
    return {k: (len(v) if isinstance(v, list) else v) for k, v in summary.items()}


# ============================================================================ cli


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("validate")
    for name in ("panels", "prepare", "audit-prepare", "controls", "finalize"):
        sub.add_parser(name).add_argument("--workers", type=int, default=8)
    sub.add_parser("identity-gate")
    w = sub.add_parser("worker")
    w.add_argument("--gpu", type=int, required=True)
    w.add_argument("--max-slots", type=int)
    lp = sub.add_parser("launch")
    lp.add_argument("--gpus", type=int, nargs="+", default=[0, 1])
    lp.add_argument("--dry-run", action="store_true")
    lp.add_argument("--write-only", action="store_true")
    rp = sub.add_parser("resume")
    rp.add_argument("--reason")
    sub.add_parser("status")
    sub.add_parser("hook")
    sub.add_parser("analyze")
    sub.add_parser("backend").add_argument("--ports", type=int, nargs="+", default=[PREP_BACKEND_PORT])
    args = parser.parse_args(argv)
    if args.stage == "validate":
        result = validate_stage()
    elif args.stage == "panels":
        result = panels_stage(args.workers)
    elif args.stage == "prepare":
        ensure_backend([PREP_BACKEND_PORT])
        result = prepare_stage(args.workers)
    elif args.stage == "audit-prepare":
        result = audit_prepare_stage(args.workers)
    elif args.stage == "controls":
        result = controls_stage(args.workers)
    elif args.stage == "identity-gate":
        result = identity_gate_stage()
    elif args.stage == "worker":
        result = worker(args.gpu, args.max_slots)
    elif args.stage == "launch":
        result = launch(tuple(args.gpus), dry_run=args.dry_run, write_only=args.write_only)
    elif args.stage == "resume":
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        reconciled = reconcile()
        result = {"reconcile": reconciled, "workers": launch(reason=args.reason or f"resume {stamp}: {reconciled}")}
    elif args.stage == "status":
        result = status()
    elif args.stage == "hook":
        result = hook()
    elif args.stage == "finalize":
        result = finalize_stage(args.workers)
    elif args.stage == "backend":
        result = ensure_backend(args.ports)
    else:
        from scripts.analyze_choice_frontier_v7 import main as analyze

        result = analyze()
    print(json.dumps(result, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
