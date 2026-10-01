#!/usr/bin/env python
"""Choice-frontier v8 (#149): node choice beyond imitating h_add.

Protocol: ``docs/experiments/choice-frontier/issue-149-protocol.md`` (twin
``configs/experiments/choice-frontier-v8/protocol.json``). Frozen #132-#146 machinery is imported
read-only (``run_choice_frontier_v7`` supplies the node-choice episode helpers, training dataset and
policy loading). Every output resolves under ``outputs/choice-frontier/v8``.

Stages (CPU unless noted):

- ``validate``        frozen pins.
- ``panels``          S1/S2 generation (serial), FD C*, R_t; S0 C* gate -> ``panels.json``.
- ``prepare-views``   S1/S2 reference views (#139 recipe, backend 18896).
- ``labels``          FD h* + h_add of every #136 corpus menu state -> ``hstar-labels.json``.
- ``prepare-hstar``   h*-target membership + store (v7 greedy records, new teacher).
- ``controls``        exact / random-valid (overflow rule) and CPU scorer arms on S0-S2, replayed.
- ``worker --gpu N``  (GPU) queue: h* training + smoke, EI rollouts, EI training + smoke, D3 models,
                      evaluations, zero-shot, D3 scoring.
- ``prepare-ei``      expert-iteration membership + store from the rollouts.
- ``launch`` / ``resume`` / ``status`` / ``hook``  scheduler plumbing.
- ``finalize``        independent replay of every GPU episode.
- ``analyze``         pre-registered tests -> ``outputs/choice-frontier/v8/metrics/analysis.json``.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import gc
import json
import math
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.node_choice import (  # noqa: E402
    NodeChoiceSession,
    NodeChoiceTask,
    replay_node_choice_episode,
    run_control_episode,
)
from examples.planning_benchmark_slice.node_choice_views import (  # noqa: E402
    TOKEN_LIMIT,
    NodeChoiceTaskViews,
    placeholder_counter,
    text_context,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority  # noqa: E402
from examples.planning_benchmark_slice.scored_node_choice import (  # noqa: E402
    DEAD_END,
    goal_count_scorer,
    run_scored_episode,
    verify_scored_episode,
)
from scripts import run_choice_frontier_v3 as v3  # noqa: E402
from scripts import run_choice_frontier_v4_panels as v4p  # noqa: E402
from scripts import run_choice_frontier_v7 as v7  # noqa: E402

PROTOCOL_PATH = Path("configs/experiments/choice-frontier-v8/protocol.json")
CONFIG = Path("configs/experiments/choice-frontier-v8")
PANELS_PATH = CONFIG / "panels.json"
LABELS_PATH = CONFIG / "hstar-labels.json"
HSTAR_MEMBERSHIP = CONFIG / "membership-hstar.json"
EI_MEMBERSHIP = CONFIG / "membership-ei.json"
SCHEDULE = Path("docs/experiments/choice-frontier/schedule-v8.json")
OUT = Path("outputs/choice-frontier/v8")
LEDGER = OUT / "budget.json"
QUEUE = OUT / "queue"
V7_STORE = Path("outputs/choice-frontier/v7/preparation/store.json.gz")
V7_MEMBERSHIP = Path("configs/experiments/choice-frontier-v7/membership.json")
V3_TRAIN_VIEWS = Path("outputs/choice-frontier/v3/train-views")
GREEDY, W3 = "best_first_add_greedy", "best_first_add_w3"
ALGORITHMS = (GREEDY, W3)
OBSERVATIONS = ("visual", "text")
STRATA = ("s0", "s1", "s2")
NEW_STRATA = ("s1", "s2")
SEEDS = (17, 29, 71)
RANDOM_SEEDS = (17, 5077, 6131, 7409, 8527)
INFERENCE_SEED = 17
PANEL_EXPANSION_LIMIT = 100_000
PER_DOMAIN_LEVEL = 2
CSTAR_TIME_LIMIT = 600
VIEW_CEILING = {"decisions": 4096, "expansions": 2048}
TARGET_RECORDS, RECORDS_PER_TASK, DIAGNOSTIC_RECORDS, AUGMENTATIONS = 2048, 64, 16, 2
GPU_HOURS_CAP = 320.0
BUDGET_STOP_GPU_HOURS = 300.0
WORKER_MAX_SECONDS = 7 * 24 * 3600
MIN_CLAIM_SECONDS = 1800
DEADLINE_MARGIN_SECONDS = 900
MAX_SLOT_FAILURES = 2
MAX_CONSECUTIVE_FAILURES = 3
GPU_BACKEND_PORTS = {0: 18894, 1: 18895}
PREP_BACKEND_PORT = 18896
MASTER_PORT_POOL = (18884, 18885, 18886, 18887)
EPISODE_SCHEMA = "choice_frontier_v8_episode_v1"
METHODS = ("hadd", "hstar", "ei")
D3_BACKBONES = ("cnn", "vit")
D3_TARGETS = ("hstar", "hadd", "rank")
BLIND_FRACTION, BLIND_SEED, BLIND_LIMIT = 0.1, 149, 2_000_000

canonical, sha256_text, sha256_file, write, load = v7.canonical, v7.sha256_text, v7.sha256_file, v7.write, v7.load


def protocol() -> dict:
    return load(PROTOCOL_PATH)


def domain_of(task_id: str) -> str:
    return task_id.split("/", 1)[1].rsplit("-", 2)[0]


# ============================================================================ validate


def validate_stage() -> dict:
    from examples.planning_benchmark_slice.optimal_cost import fast_downward_driver

    p = protocol()
    v7p = load(v7.PROTOCOL_PATH)
    checks = {
        "p2_sha": v4p.membership("p2")["membership_sha256"] == p["panels"]["s0"]["p2_membership_sha256"],
        "p2u_sha": v4p.membership("p2u")["membership_sha256"] == p["panels"]["s0"]["p2u_membership_sha256"],
        "v7_membership_sha": v7.membership_sha(load(V7_MEMBERSHIP)) == load(V7_MEMBERSHIP)["membership_sha256"],
        "backbone": (v7p["model_id"], v7p["model_revision"]) == (p["model_id"], p["model_revision"]),
        "token_limit": TOKEN_LIMIT == p["contract"]["overflow_rule"]["token_limit"],
        "inference": v7p["evaluation"]["inference"] == p["evaluation"]["inference"],
        "fast_downward": fast_downward_driver().is_file(),
        "ports": list(MASTER_PORT_POOL) == p["ports"]["master_port_pool"],
        "seeds": list(SEEDS) == p["training_seeds"] and list(RANDOM_SEEDS) == p["evaluation"]["random_seeds"],
    }
    return {"checks": checks, "ok": all(checks.values())}


# ============================================================================ panels


def objects_count(problem_pddl: str) -> int:
    import re

    match = re.search(r"\(:objects\b", problem_pddl, flags=re.IGNORECASE)
    if match is None:
        return 0
    depth = 0
    for end in range(match.start(), len(problem_pddl)):
        depth += (problem_pddl[end] == "(") - (problem_pddl[end] == ")")
        if depth == 0:
            tokens = problem_pddl[match.end() : end].split()
            return sum(1 for i, t in enumerate(tokens) if t != "-" and (i == 0 or tokens[i - 1] != "-"))
    raise ValueError("unbalanced :objects")


def exact_run(authority, task_id: str, algorithm: str, limit: int = PANEL_EXPANSION_LIMIT) -> dict:
    session = run_control_episode(
        authority, NodeChoiceTask(task_id, domain_of(task_id), algorithm, limit), "text", "exact_reference", 17
    )
    return {"R": session.controller.expansion_count, "termination": session.termination_reason}


def exclusion_hashes() -> dict[str, str]:
    from scripts.build_choice_frontier_v4_panels import exclusion_hashes as v4_hashes

    hashes = v4_hashes()
    for record in load(Path("configs/experiments/choice-frontier-v4/candidates.json"))["candidates"]:
        if record.get("problem_sha256"):
            hashes.setdefault(record["problem_sha256"], f"e:choice-frontier-v4-candidate:{record['task_id']}")
    return hashes


def _candidate_cpu(item) -> dict:
    """FD C* and uncapped exact R_t of one generated candidate (parallel after serial generation)."""

    from examples.planning_benchmark_slice.optimal_cost import optimal_cost

    record = dict(item)
    task = load(Path(record["task_path"]))
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    label = optimal_cost(
        task["domain_pddl"], task["problem_pddl"], authority, authority.initial_state, time_limit=CSTAR_TIME_LIMIT
    )
    record.update(cstar=label["hstar"], cstar_status=label["status"], cstar_plan=label["plan"])
    if label["status"] != "solved":
        return {**record, "reject_reason": f"cstar_{label['status']}"}
    record["R"], terminations = {}, {}
    for algorithm in ALGORITHMS:
        run = exact_run(authority, record["task_id"], algorithm)
        record["R"][algorithm], terminations[algorithm] = run["R"], run["termination"]
    record["exact_termination"] = terminations
    if any(t != "goal_reached" for t in terminations.values()):
        return {**record, "reject_reason": "exact_not_goal"}
    return {**record, "reject_reason": None}


def panels_stage(workers: int = 6) -> dict:
    """Serial generation, then parallel C*/R_t, admission walk, S0 C* gate -> panels.json."""

    from concurrent.futures import ProcessPoolExecutor

    from examples.planning_benchmark_slice.expanded_candidates import generate
    from examples.planning_benchmark_slice.optimal_cost import optimal_cost

    if (ROOT / PANELS_PATH).exists():
        raise ValueError(f"{PANELS_PATH} is frozen; refusing to regenerate")
    p = protocol()
    excluded = exclusion_hashes()
    seen: dict[str, str] = {}
    candidates: list[dict] = []
    for stratum in p["panels"]["new_strata"]:
        for seed in stratum["seeds"]:
            name = f"{stratum['domain']}-{stratum['stratum']}-{seed}"
            task_id = f"choice-frontier-v8/{name}"
            path = OUT / "panels" / "candidates" / name / "task.json"
            record = {
                "task_id": task_id,
                "domain": stratum["domain"],
                "stratum": stratum["stratum"],
                "seed": seed,
                "task_path": str(path),
            }
            if not (ROOT / path).exists():
                with tempfile.TemporaryDirectory(prefix="cfv8-gen-") as directory:
                    try:
                        task = generate(ROOT, stratum, seed, Path(directory))
                    except Exception as error:  # recorded, never retried
                        candidates.append({**record, "reject_reason": f"generator_failed: {error}"[:300]})
                        continue
                write(path, task)
            task = load(path)
            sha = sha256_text(task["problem_pddl"])
            record.update(
                problem_sha256=sha,
                objects=objects_count(task["problem_pddl"]),
                generator_command=task["generator_command"],
            )
            authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
            if authority.is_goal(authority.initial_state):
                reason = "initial_goal"
            elif sha in excluded:
                reason = f"overlap:{excluded[sha]}"
            elif sha in seen:
                reason = f"duplicate_candidate:{seen[sha]}"
            else:
                reason = None
            seen.setdefault(sha, task_id)
            candidates.append({**record, "reject_reason": reason})
    pending = [c for c in candidates if c["reject_reason"] is None]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        computed = {r["task_id"]: r for r in pool.map(_candidate_cpu, pending)}
    candidates = [computed.get(c["task_id"], c) for c in candidates]
    rows, counts = [], {}
    for stratum in p["panels"]["new_strata"]:
        kept = [
            c
            for c in candidates
            if c["domain"] == stratum["domain"] and c["stratum"] == stratum["stratum"] and c["reject_reason"] is None
        ]
        kept.sort(key=lambda c: c["seed"])
        chosen = kept[:PER_DOMAIN_LEVEL]
        counts[f"{stratum['domain']}-{stratum['stratum']}"] = len(chosen)
        rows.extend(chosen)
    s0 = []
    for group in ("p2", "p2u"):
        frozen = v4p.membership(group)
        for task in frozen["tasks"]:
            row = task["row"]
            v7row = next(r for r in v7.panel_rows(group) if r["task_id"] == row["task_id"])
            source = load(Path(row["task_path"]))
            authority = PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"])
            label = optimal_cost(source["domain_pddl"], source["problem_pddl"], authority, authority.initial_state)
            cstar_139 = int(frozen["per_task"][row["task_id"]]["cstar"])
            s0.append(
                {
                    "task_id": row["task_id"],
                    "domain": row["domain"],
                    "stratum": "s0",
                    "group": group,
                    "task_path": row["task_path"],
                    "objects": objects_count(source["problem_pddl"]),
                    "cstar": label["hstar"],
                    "cstar_plan": label["plan"],
                    "cstar_139": cstar_139,
                    "R": {a: v7row["R"][a] for a in ALGORITHMS},
                    "problem_sha256": sha256_text(source["problem_pddl"]),
                }
            )
    gate = all(r["cstar"] == r["cstar_139"] for r in s0)
    tasks = s0 + [
        {
            k: r[k]
            for k in (
                "task_id",
                "domain",
                "stratum",
                "seed",
                "task_path",
                "objects",
                "cstar",
                "cstar_plan",
                "R",
                "problem_sha256",
                "generator_command",
            )
        }
        for r in rows
    ]
    document = {
        "schema_version": "choice_frontier_v8_panels_v1",
        "protocol_id": p["protocol_id"],
        "r_t_rule": "uncapped exact_reference node-choice expansions (no overflow rule)",
        "cstar_rule": "Fast Downward astar(lmcut()), plan replay-verified",
        "s0_cstar_equals_139": gate,
        "per_domain_level_counts": counts,
        "strata_counts": {s: sum(t["stratum"] == s for t in tasks) for s in STRATA},
        "tasks": tasks,
        "membership_sha256": sha256_text(canonical(sorted(t["task_id"] for t in tasks))),
    }
    write(OUT / "panels" / "candidates.json", {"candidates": candidates})
    if not gate:
        write(OUT / "panels" / "s0-cstar-gate-failed.json", s0)
        raise ValueError("S0 FD C* differs from the #139 BFS C*")
    write(PANELS_PATH, document)
    return {"strata": document["strata_counts"], "counts": counts, "s0_cstar_gate": gate}


def panel_rows(stratum: str | None = None) -> list[dict]:
    rows = load(PANELS_PATH)["tasks"]
    return [r for r in rows if stratum is None or r["stratum"] == stratum]


def panel_row(task_id: str) -> dict:
    return next(r for r in panel_rows() if r["task_id"] == task_id)


def reference_costs(row: dict) -> dict:
    return {a: {"decisions": row["R"][a] + 1, "expansions": row["R"][a]} for a in ALGORITHMS}


# ============================================================================ views


VIEWS_ROOT = OUT / "panels"
VIEW_REPORT = VIEWS_ROOT / "reference-views.json"


def _view_task(item: tuple[dict, dict]) -> dict:
    from examples.planning_benchmark_slice.matched_tasks import exact_reference
    from scripts.prepare_expanded_views import prepare_task

    protocol_, row = item
    name = row["task_id"].split("/", 1)[1]
    domain, stratum, seed = name.rsplit("-", 2)
    candidate = ROOT / VIEWS_ROOT / "candidates" / name
    base = {
        "task_id": row["task_id"],
        "domain": domain,
        "difficulty": stratum,
        "split": "test",
        "task_path": row["task_path"],
        "trace_paths": {},
    }
    ceiling = {**base, "reference_costs": {a: dict(VIEW_CEILING) for a in v4p.VIEW_ALGORITHMS}}
    study = {
        "output_root": str(VIEWS_ROOT),
        "study_id": protocol_["study_id"],
        "final": {"max_exact_decisions_per_algorithm": VIEW_CEILING["decisions"]},
    }
    native = {}
    for algorithm in v4p.VIEW_ALGORITHMS:
        result = exact_reference(ROOT, ceiling, algorithm, study)["result"]
        native[algorithm] = {"decisions": result["decision_count"], "expansions": result["expansion_count"]}
        if native[algorithm]["expansions"] != row["R"][algorithm]:
            raise ValueError(f"native exact expansions differ from the node-choice R_t: {name} {algorithm}")
    view_row = {**base, "reference_costs": native}
    for algorithm in v4p.VIEW_ALGORITHMS:
        path = candidate / f"reference-{algorithm}.json.gz"
        if not (ROOT / path).exists():
            write(path, exact_reference(ROOT, view_row, algorithm, study))
    group = {"domain": domain, "stratum": stratum, "selected": {"seed": int(seed), "row": view_row}}
    result = prepare_task(protocol_, group, 0, endpoint=f"http://127.0.0.1:{PREP_BACKEND_PORT}")
    source = load(Path(row["task_path"]))
    pages = (len(result["native_views"]["static_pages"]), len(result["native_views"]["goal_pages"]))
    if pages != v3.page_counts(source):
        raise ValueError(f"view page counts differ from the recipe page counts: {name}")
    return result


def prepare_views_stage(workers: int = 4) -> dict:
    from concurrent.futures import ProcessPoolExecutor

    v7.ensure_backend([PREP_BACKEND_PORT])
    protocol_ = {
        "study_id": "choice-frontier-v8-panels-views",
        "output_root": str(VIEWS_ROOT),
        "reference": {"algorithms": list(v4p.VIEW_ALGORITHMS)},
        "membership_sha256": load(PANELS_PATH)["membership_sha256"],
    }
    rows = [r for r in panel_rows() if r["stratum"] in NEW_STRATA]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        tasks = list(pool.map(_view_task, [(protocol_, row) for row in rows]))
    write(VIEW_REPORT, {"protocol": protocol_, "tasks": tasks})
    return {"tasks": len(tasks), "outcomes": sorted({t["outcome"] for t in tasks})}


_PANEL_TASKS: dict[str, dict] = {}


def panel_task(task_id: str) -> dict:
    """Reference-view task dict (native views + row with R_t) for any S0/S1/S2 or smoke task."""

    if task_id not in _PANEL_TASKS:
        if task_id.startswith("choice-frontier-v8/"):
            for view in load(VIEW_REPORT)["tasks"]:
                _PANEL_TASKS[view["row"]["task_id"]] = view
        else:
            _PANEL_TASKS[task_id] = v7.panel_views_task(task_id)
    task = _PANEL_TASKS[task_id]
    if task_id.startswith("expanded-final/"):
        return task  # #146 smoke rows carry their v7 R_t
    row = panel_row(task_id)
    return {**task, "row": {**task["row"], "domain": row["domain"], "reference_costs": reference_costs(row)}}


def page_counts_of(task: dict) -> tuple[int, int]:
    return v7.page_counts_of(task)


# ============================================================================ h* labels


def _teacher_replay(task_id: str) -> dict:
    """Replay both #136 additive teachers; per v7 record: menu (view index, h_add, g, serial)."""

    store = _v7_store()
    view_key = f"additive:{task_id}"
    task = store["tasks"][view_key]
    authority, _source = v7.authority_of(task["task_path"])
    records = {rid: r for rid, r in store["records"].items() if r["view_key"] == view_key}
    out: dict[str, list] = {}
    for algorithm in ALGORITHMS:
        wanted = {r["decision_index"]: rid for rid, r in records.items() if r["algorithm"] == algorithm}
        if not wanted:
            continue
        session = NodeChoiceSession(
            authority=authority,
            task=NodeChoiceTask(task_id, domain_of(task_id), algorithm, v7.UNCAPPED),
            observation="text",
            arm="exact_reference",
            seed=17,
        )
        while (request := session.next_request()) is not None and request.decision_index <= max(wanted):
            rid = wanted.get(request.decision_index)
            if rid is not None:
                record = records[rid]
                if [dict(e) for e in request.menu_binding] != record["menu"]:
                    raise ValueError(f"#136 teacher menu does not re-bind: {rid}")
                rows = []
                for entry, index in zip(record["menu"], record["menu_indices"], strict=True):
                    state = session.controller._states_by_ref[entry["state_ref"]]
                    atoms, fluents = task["states"][str(index)]
                    if list(state.atoms) != atoms or list(state.fluents) != fluents:
                        raise ValueError(f"#136 menu state differs from the stored catalog state: {rid}")
                    _priority, serial, g, h = session.controller._frontier_entries[state.state_id]
                    rows.append({"index": index, "state_ref": entry["state_ref"], "h_add": h, "g": g, "serial": serial})
                if session.kappa_head_ref() != record["teacher_state_ref"]:
                    raise ValueError(f"#136 teacher head differs: {rid}")
                out[rid] = rows
            session.submit_output(session.reference_output())
    missing = set(records) - set(out)
    if missing:
        raise ValueError(f"records not reached by the teacher replay: {sorted(missing)[:3]}")
    return {"task_id": task_id, "records": out}


_STORE: dict | None = None


def _v7_store() -> dict:
    global _STORE
    if _STORE is None:
        _STORE = load(V7_STORE)
    return _STORE


def _hstar_one(item) -> dict:
    from examples.planning_benchmark_slice.optimal_cost import optimal_cost

    task_id, index, atoms, fluents, task_path = item
    authority, source = v7.authority_of(task_path)
    state = authority.canonical_state(tuple(atoms), tuple(fluents))
    label = optimal_cost(source["domain_pddl"], source["problem_pddl"], authority, state)
    return {
        "task_id": task_id,
        "index": int(index),
        "atoms_sha256": sha256_text(canonical([atoms, fluents])),
        "status": label["status"],
        "hstar": label["hstar"],
        "fd_seconds": round(label["seconds"], 3),
    }


def _blind_one(item) -> dict:
    from examples.planning_benchmark_slice.optimal_cost import blind_distance, state_authority, state_problem

    task_id, index, atoms, fluents, task_path, hstar = item
    authority, source = v7.authority_of(task_path)
    state = authority.canonical_state(tuple(atoms), tuple(fluents))
    rooted = state_authority(source["domain_pddl"], state_problem(source["problem_pddl"], authority, state), state)
    distance = blind_distance(rooted, rooted.initial_state, state_limit=BLIND_LIMIT)
    return {
        "task_id": task_id,
        "index": index,
        "hstar": hstar,
        "blind": distance,
        "agree": None if distance is None and hstar is not None else distance == hstar,
    }


def labels_stage(workers: int = 8) -> dict:
    from concurrent.futures import ProcessPoolExecutor

    if (ROOT / LABELS_PATH).exists():
        raise ValueError(f"{LABELS_PATH} is frozen; refusing to relabel")
    store = _v7_store()
    membership = load(V7_MEMBERSHIP)
    rids = [rid for a in ALGORITHMS for split in ("training", "diagnostic") for rid in membership["cells"][a][split]]
    task_ids = sorted({store["records"][rid]["task_id"] for rid in rids})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        replays = list(pool.map(_teacher_replay, task_ids))
    kappa = {rid: rows for r in replays for rid, rows in r["records"].items() if rid in set(rids)}
    write(OUT / "preparation" / "kappa-menus.json.gz", kappa)
    h_add: dict[tuple[str, int], int] = {}
    for rid, rows in kappa.items():
        task_id = store["records"][rid]["task_id"]
        for row in rows:
            key = (task_id, row["index"])
            if h_add.setdefault(key, row["h_add"]) != row["h_add"]:
                raise ValueError(f"h_add differs between menus for one state: {key}")
    items = []
    for task_id, index in sorted(h_add):
        task = store["tasks"][f"additive:{task_id}"]
        atoms, fluents = task["states"][str(index)]
        items.append((task_id, index, atoms, fluents, task["task_path"]))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        labels = list(pool.map(_hstar_one, items, chunksize=8))
    for label in labels:
        label["h_add"] = h_add[(label["task_id"], label["index"])]
    rng = random.Random(BLIND_SEED)
    sample = sorted(rng.sample(range(len(labels)), math.ceil(BLIND_FRACTION * len(labels))))
    blind_items = [(*items[i][:4], items[i][4], labels[i]["hstar"]) for i in sample]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        blind = list(pool.map(_blind_one, blind_items))
    disagreements = [b for b in blind if b["agree"] is False]
    status_counts = {s: sum(label["status"] == s for label in labels) for s in ("solved", "dead_end", "timeout")}
    document = {
        "schema_version": "choice_frontier_v8_hstar_labels_v1",
        "protocol_id": protocol()["protocol_id"],
        "fast_downward": protocol()["fast_downward"],
        "source": {
            "store": str(V7_STORE),
            "membership": str(V7_MEMBERSHIP),
            "membership_sha256": membership["membership_sha256"],
            "records": len(rids),
        },
        "status_counts": status_counts,
        "blind_check": {
            "sampled": len(blind),
            "agree": sum(b["agree"] is True for b in blind),
            "limit_hit": sum(b["agree"] is None for b in blind),
            "disagreements": disagreements,
        },
        "labels": labels,
    }
    if disagreements:
        write(OUT / "preparation" / "hstar-labels-FAILED.json", document)
        raise ValueError(f"h* blind check disagrees on {len(disagreements)} states")
    write(LABELS_PATH, document)
    return {
        "states": len(labels),
        "status": status_counts,
        "blind_check": document["blind_check"] | {"disagreements": 0},
    }


def hstar_table() -> dict[tuple[str, int], dict]:
    return {(row["task_id"], row["index"]): row for row in load(LABELS_PATH)["labels"]}


# ============================================================================ h*-target corpus


def hstar_teacher(rows: list[dict], labels: dict, task_id: str) -> str:
    """Min h*; ties by kappa (h_add, serial); dead ends / timeouts last; all dead -> the kappa head."""

    def key(row):
        hstar = labels[(task_id, row["index"])]["hstar"]
        return (math.inf if hstar is None else hstar, row["h_add"], row["serial"])

    return min(rows, key=key)["state_ref"]


def membership_sha(cells: dict) -> str:
    return sha256_text(canonical({a: cells[a] for a in sorted(cells)}))


def augmentation_report(store: dict, rids: list[str]) -> dict:
    return v7.augmentation_check([store["records"][rid] for rid in rids])


def prepare_hstar_stage() -> dict:
    if (ROOT / HSTAR_MEMBERSHIP).exists():
        raise ValueError(f"{HSTAR_MEMBERSHIP} is frozen")
    store = _v7_store()
    v7m = load(V7_MEMBERSHIP)
    labels = hstar_table()
    kappa = load(OUT / "preparation" / "kappa-menus.json.gz")
    cell = v7m["cells"][GREEDY]
    records, changed = {}, 0
    for rid in cell["training"] + cell["diagnostic"]:
        record = store["records"][rid]
        teacher = hstar_teacher(kappa[rid], labels, record["task_id"])
        choice = next(e["choice"] for e in record["menu"] if e["state_ref"] == teacher)
        changed += teacher != record["teacher_state_ref"]
        records[rid] = {
            **record,
            "teacher_state_ref": teacher,
            "teacher_choice": choice,
            "hadd_teacher_state_ref": record["teacher_state_ref"],
        }
    view_keys = sorted({r["view_key"] for r in records.values()})
    hstore = {
        "schema_version": "choice_frontier_v8_store_v1",
        "records": records,
        "tasks": {k: store["tasks"][k] for k in view_keys},
    }
    write(OUT / "preparation" / "store-hstar.json.gz", hstore)
    cells = {GREEDY: {"training": list(cell["training"]), "diagnostic": list(cell["diagnostic"])}}
    check = augmentation_report(hstore, cell["training"])
    document = {
        "schema_version": "choice_frontier_v8_membership_v1",
        "kind": "hstar_target",
        "protocol_id": protocol()["protocol_id"],
        "source_membership_sha256": v7m["membership_sha256"],
        "labels_sha256": sha256_file(ROOT / LABELS_PATH),
        "store": str(OUT / "preparation" / "store-hstar.json.gz"),
        "store_records_sha256": sha256_text(canonical(records)),
        "cells": cells,
        "teacher_changed": {"records": changed, "of": len(records)},
        "teachers": {rid: records[rid]["teacher_state_ref"] for rid in sorted(records)},
        "augmentation_check": check,
        "membership_sha256": membership_sha(cells),
    }
    write(HSTAR_MEMBERSHIP, document)
    return {"records": len(records), "teacher_changed": changed, "augmentation_check": check}


def training_cells(method: str, observation: str) -> tuple[dict, dict]:
    """(membership document, the v7-dataset membership {"cells": {greedy: {training, diagnostic}}})."""

    document = load(membership_path(method))
    hashed = document["cells"] if method == "hstar" else document["cells_by_observation"]
    if membership_sha(hashed) != document["membership_sha256"]:
        raise ValueError(f"{method} membership sha differs")
    cell = hashed[GREEDY] if method == "hstar" else hashed[observation]
    check = document["augmentation_check"] if method == "hstar" else document["augmentation_check"][observation]
    if not check["pass"]:
        raise ValueError(f"augmentation check failed: {check}")
    return document, {"cells": {GREEDY: cell}}


# ============================================================================ controls (CPU)


def control_path(task_id: str, algorithm: str, observation: str, arm: str, seed: int) -> Path:
    return OUT / "controls" / task_id.replace("/", "__") / f"{algorithm}-{observation}-{arm}-{seed}.json.gz"


def scored_path(task_id: str, algorithm: str, scorer_id: str) -> Path:
    return OUT / "scored" / task_id.replace("/", "__") / f"{algorithm}-{scorer_id}.json.gz"


def task_source(row: dict) -> tuple[PDDLStateAuthority, dict]:
    return v7.authority_of(row["task_path"])


def page_counts_for(row: dict) -> tuple[int, int]:
    return (
        page_counts_of(panel_task(row["task_id"]))
        if row["stratum"] == "s0"
        else v3.page_counts(load(Path(row["task_path"])))
    )


def _control(item) -> dict:
    task_id, algorithm, observation, arm, seed = item
    row = panel_row(task_id)
    path = ROOT / control_path(task_id, algorithm, observation, arm, seed)
    pages = page_counts_for(row)
    task = NodeChoiceTask(task_id, row["domain"], algorithm, row["R"][algorithm])

    def counter():
        authority, source = task_source(row)
        return authority, placeholder_counter(
            algorithm, observation, text_context(authority, source["domain_pddl"], source["problem_pddl"]), pages
        )

    if path.exists():
        report = load(path)
    else:
        authority, count = counter()
        session = run_control_episode(
            authority, task, observation, arm, seed, token_limit=TOKEN_LIMIT, token_counter=count
        )
        report = {**session.episode(), "task_id": task_id, "condition": arm}
        write(path, report)
    fresh, count = counter()
    replay_node_choice_episode(fresh, task, report, token_counter=count)
    return {"key": [task_id, algorithm, observation, arm, seed], "result": report["result"]}


class HstarOracle:
    """FD h* per state (cached on disk per task); timeouts and dead ends score +inf."""

    def __init__(self, row: dict) -> None:
        self.scorer_id = "hstar_oracle"
        self.authority, self.source = task_source(row)
        self.cache_path = ROOT / OUT / "scored" / "hstar-cache" / f"{row['task_id'].replace('/', '__')}.json"
        self.cache = json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}

    def __call__(self, states) -> list[float]:
        from examples.planning_benchmark_slice.optimal_cost import optimal_cost

        scores = []
        for state in states:
            key = sha256_text(canonical([list(state.atoms), list(state.fluents)]))
            if key not in self.cache:
                label = optimal_cost(self.source["domain_pddl"], self.source["problem_pddl"], self.authority, state)
                self.cache[key] = {"status": label["status"], "hstar": label["hstar"]}
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(json.dumps(self.cache))
            hstar = self.cache[key]["hstar"]
            scores.append(DEAD_END if hstar is None else float(hstar))
        return scores


def cpu_scorer(row: dict, scorer_id: str):
    authority, _source = task_source(row)
    if scorer_id == "goal_count":
        return authority, goal_count_scorer(authority)
    if scorer_id == "hstar_oracle":
        oracle = HstarOracle(row)
        return oracle.authority, oracle
    raise ValueError(scorer_id)


def _scored_cpu(item) -> dict:
    task_id, algorithm, scorer_id = item
    row = panel_row(task_id)
    path = ROOT / scored_path(task_id, algorithm, scorer_id)
    task = NodeChoiceTask(task_id, row["domain"], algorithm, row["R"][algorithm])
    if path.exists():
        report = load(path)
    else:
        authority, scorer = cpu_scorer(row, scorer_id)
        session = run_scored_episode(authority, task, scorer)
        report = {**session.episode(), "task_id": task_id, "condition": scorer_id}
        write(path, report)
    authority, scorer = cpu_scorer(row, scorer_id)
    verify_scored_episode(authority, task, report, scorer=scorer)
    return {"key": [task_id, algorithm, scorer_id], "result": report["result"]}


CPU_SCORERS = {"goal_count": ALGORITHMS, "hstar_oracle": (GREEDY,)}


def controls_stage(workers: int = 8) -> dict:
    from concurrent.futures import ProcessPoolExecutor

    items = []
    for row in panel_rows():
        for algorithm in ALGORITHMS:
            for observation in OBSERVATIONS:
                for arm, seeds in (("exact_reference", (17,)), ("random_valid", RANDOM_SEEDS)):
                    items.extend((row["task_id"], algorithm, observation, arm, s) for s in seeds)
    scored = [(row["task_id"], a, s) for row in panel_rows() for s, algs in CPU_SCORERS.items() for a in algs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_control, items, chunksize=4))
        scored_results = list(pool.map(_scored_cpu, scored))
    equal = s0_controls_equal_v7()
    receipt = {
        "episodes": len(results),
        "replayed": len(results),
        "overflow": sum(r["result"]["termination_reason"] == "observation_overflow" for r in results),
        "scored_episodes": len(scored_results),
        "scored_verified": len(scored_results),
        "s0_controls_equal_v7": equal,
    }
    write(OUT / "controls" / "receipt.json", receipt)
    if equal["differing"]:
        raise ValueError(f"S0 controls differ from v7: {equal['differing'][:3]}")
    return receipt


def s0_controls_equal_v7() -> dict:
    compared, differing = 0, []
    for row in panel_rows("s0"):
        for algorithm in ALGORITHMS:
            for observation in OBSERVATIONS:
                for arm, seeds in (("exact_reference", (17,)), ("random_valid", RANDOM_SEEDS)):
                    for seed in seeds:
                        ours = load(control_path(row["task_id"], algorithm, observation, arm, seed))
                        theirs = load(v7.control_path(row["task_id"], algorithm, observation, arm, seed))
                        compared += 1
                        if ours["events"] != theirs["events"] or ours["result"] != theirs["result"]:
                            differing.append([row["task_id"], algorithm, observation, arm, seed])
    return {"compared": compared, "differing": differing}


# ============================================================================ GPU episodes


def adapter_dir(method: str, algorithm: str, observation: str, seed: int) -> Path:
    if method == "hadd":
        return v7.adapter_dir(algorithm, observation, seed)
    return training_dir(method, observation, seed) / "final"


def training_dir(method: str, observation: str, seed: int) -> Path:
    return OUT / "training" / method / GREEDY / observation / f"seed-{seed}"


def episode_paths(stage: str, cell: dict, task_id: str) -> tuple[Path, Path, Path]:
    base = ROOT / OUT / stage
    name = f"{cell['method']}-{cell['algorithm']}-{cell['observation']}-{cell['condition']}-s{cell.get('seed', 0)}"
    task_name = task_id.replace("/", "__")
    episode = base / "episodes" / task_name / f"{name}.json.gz"
    return episode, episode.with_name(episode.name + ".partial.json.gz"), base / "views" / task_name / name


def identity(stage: str, cell: dict, task_id: str, checkpoint: str | None) -> dict:
    episode, _partial, view_output = episode_paths(stage, cell, task_id)
    p = protocol()
    return {
        "schema_version": EPISODE_SCHEMA,
        "protocol_id": p["protocol_id"],
        "stage": stage,
        "task_id": task_id,
        "method": cell["method"],
        "algorithm": cell["algorithm"],
        "observation": cell["observation"],
        "condition": cell["condition"],
        "training_seed": cell.get("seed"),
        "inference_seed": INFERENCE_SEED,
        "checkpoint": checkpoint,
        "output": str(episode.relative_to(ROOT)),
        "view_output": str(view_output.relative_to(ROOT)),
        "model_id": p["model_id"],
        "model_revision": p["model_revision"],
    }


def run_model_episode(stage: str, task: dict, cell: dict, checkpoint: str | None, endpoint: str, generate):
    """The v7 journaled episode (resumable, pending output persisted) under v8 paths and identity."""

    from PIL import Image

    task_id = task["row"]["task_id"]
    episode, partial_path, view_output = episode_paths(stage, cell, task_id)
    expected = identity(stage, cell, task_id, checkpoint)
    if episode.exists():
        if partial_path.exists():
            raise ValueError("completed episode retains a conflicting partial journal")
        report = load(episode)
        if any(report.get(k) != v for k, v in expected.items()):
            raise ValueError("retained episode binding differs")
        return report, True
    views = NodeChoiceTaskViews(ROOT, task, view_output, endpoint)
    session = v7.session_for(task, cell, views, checkpoint)
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
        raise ValueError("partial episode binding differs")
    v7._replay_events(session, views, cell, saved["events"])

    def commit(pending: dict) -> None:
        request = session.next_request()
        if request is None or dict(request.model_input) != pending["input"]:
            raise ValueError("persisted pending output no longer matches the request")
        submitted, rule = v7.submitted_output(cell, pending["model_text"])
        session.submit_output(submitted)
        committed = dict(session.events[-1])
        committed.update(view=pending["binding"], model_text=pending["model_text"], extraction_rule=rule)
        session.events[-1] = committed
        v7.register_admissions(session, views, committed)
        saved["events"].append(committed)
        saved["call_measurements"].append(pending["measurement"])
        saved["pending"] = None
        views.save()

    if saved.get("pending") is not None:
        request = session.next_request()
        if request is None:
            raise ValueError("persisted pending output has no request")
        observed = v7.binding_of(v7.observe(views, session, request, cell, pixels=False), session, request)
        if observed != saved["pending"]["binding"]:
            raise ValueError("persisted pending output has a different view binding")
        commit(saved["pending"])
    write(partial_path, saved)
    while (request := session.next_request()) is not None:
        example = v7.observe(views, session, request, cell, pixels=True)
        binding = v7.binding_of(example, session, request)
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
    cell = {k: report[k] for k in ("method", "algorithm", "observation", "condition")} | {
        "seed": report["training_seed"]
    }
    _episode, _partial, view_output = episode_paths(report["stage"], cell, report["task_id"])
    views = NodeChoiceTaskViews(ROOT, task, view_output, endpoint, read_only=True)
    session = v7.session_for(task, cell, views, report.get("checkpoint"))
    if session.decision_cap != int(report["decision_cap"]):
        raise ValueError("replay decision cap differs")
    v7._replay_events(session, views, cell, report["events"])
    if session.next_request() is not None or not session.complete:
        raise ValueError("replay did not end where the stored episode ended")
    if session.result() != report["result"]:
        raise ValueError("replay result differs")
    return session.result()


def strata_tasks(strata) -> list[str]:
    return [r["task_id"] for r in panel_rows() if r["stratum"] in strata]


def eval_cells() -> list[dict]:
    cells = []
    for method in METHODS:
        algorithms = ALGORITHMS if method == "hadd" else (GREEDY,)
        for seed in SEEDS:
            for algorithm in algorithms:
                for observation in OBSERVATIONS:
                    cells.append(
                        {
                            "method": method,
                            "algorithm": algorithm,
                            "observation": observation,
                            "condition": "learned_adapter",
                            "seed": seed,
                            "strata": list(STRATA),
                        }
                    )
    for algorithm in ALGORITHMS:
        cells.append(
            {
                "method": "zeroshot",
                "algorithm": algorithm,
                "observation": "text",
                "condition": "zero_shot_base",
                "seed": 0,
                "strata": list(NEW_STRATA),
            }
        )
    return cells


def cell_key(cell: dict) -> str:
    return f"{cell['method']}:{cell['algorithm']}:{cell['observation']}:{cell['seed']}"


def run_evaluation(cell: dict, *, gpu: int, deadline: float, progress) -> dict:
    if cell["condition"] == "learned_adapter":
        if cell["method"] != "hadd":
            gate = smoke_verdict(cell["method"], cell["observation"])
            if gate != "PASS":
                if gate is None:
                    raise ValueError("learned evaluation before its smoke gate")
                return {"outcome": "SMOKE_GATED", "gate": gate}
        checkpoint = str(adapter_dir(cell["method"], cell["algorithm"], cell["observation"], cell["seed"]))
        adapters, key = {cell["algorithm"]: checkpoint}, cell["algorithm"]
    else:
        checkpoint, adapters, key = None, {}, None
    state: dict = {}
    generate = v7.generator(key, adapters, deadline, state)
    tasks = strata_tasks(cell["strata"])
    episodes = []
    try:
        for task_id in tasks:
            report, retained = run_model_episode(
                "evaluation", panel_task(task_id), cell, checkpoint, backend(gpu), generate
            )
            episodes.append({"task_id": task_id, "retained": retained, "result": report["result"]})
            progress("evaluation", cell=cell_key(cell), completed=len(episodes), total=len(tasks))
    finally:
        v7.free_policy(state)
    return {"outcome": "PASS", "episodes": episodes, "calls_this_attempt": state.get("calls", 0)}


# ---------------------------------------------------------------------------- smoke


def smoke_path(method: str, observation: str) -> Path:
    return OUT / "smoke" / f"{method}-{observation}.json"


def smoke_verdict(method: str, observation: str) -> str | None:
    path = ROOT / smoke_path(method, observation)
    return load(path)["gate"] if path.exists() else None


def run_smoke(method: str, observation: str, *, gpu: int, deadline: float, progress) -> dict:
    checkpoint = str(adapter_dir(method, GREEDY, observation, 17))
    cell = {
        "method": method,
        "algorithm": GREEDY,
        "observation": observation,
        "condition": "learned_adapter",
        "seed": 17,
    }
    state: dict = {}
    generate = v7.generator(GREEDY, {GREEDY: checkpoint}, deadline, state)
    rows = []
    try:
        for row in v7.panel_rows("smoke"):
            report, _ = run_model_episode(
                "smoke", v7.panel_views_task(row["task_id"]), cell, checkpoint, backend(gpu), generate
            )
            accepted = sum(1 for e in report["events"] if e["trusted_runtime_result"]["accepted"])
            rows.append(
                {
                    "task_id": row["task_id"],
                    "calls": len(report["events"]),
                    "accepted": accepted,
                    "result": report["result"],
                }
            )
    finally:
        v7.free_policy(state)
    calls = sum(r["calls"] for r in rows)
    rate = sum(r["accepted"] for r in rows) / calls if calls else 0.0
    result = {
        "method": method,
        "observation": observation,
        "rate": rate,
        "calls": calls,
        "threshold": v7.SMOKE_THRESHOLD,
        "gate": "PASS" if rate >= v7.SMOKE_THRESHOLD else "FAIL",
        "episodes": rows,
    }
    write(smoke_path(method, observation), result)
    return result


# ---------------------------------------------------------------------------- training


def membership_path(method: str) -> Path:
    return {"hstar": HSTAR_MEMBERSHIP, "ei": EI_MEMBERSHIP}[method]


def store_path(method: str) -> Path:
    return OUT / "preparation" / f"store-{method}.json.gz"


def run_train(method: str, observation: str, seed: int, *, deadline: float, progress) -> dict:
    from examples.planning_benchmark_slice.visual_model import train_visual

    membership_document, membership = training_cells(method, observation)
    output = ROOT / training_dir(method, observation, seed)
    if (output / "final" / "adapter_model.safetensors").is_file() and (output / "result.json").is_file():
        return {
            "cell": [method, observation, seed],
            "resumed_from": "final",
            "audit": audit_final(output, seed, membership),
        }
    if (output / "final").exists():
        shutil.rmtree(output / "final")
    checkpoints = sorted(output.glob("checkpoint-*"), key=lambda path: int(path.name.split("-")[-1]))
    for path in checkpoints:
        if not (path / "trainer_state.json").is_file():
            shutil.rmtree(path)
    checkpoints = sorted(output.glob("checkpoint-*"), key=lambda path: int(path.name.split("-")[-1]))
    resumed = checkpoints[-1].name if checkpoints else None
    store = load(store_path(method))
    if sha256_text(canonical(store["records"])) != membership_document["store_records_sha256"]:
        raise ValueError(f"{method} store differs from its membership")
    study = load(v7.STUDY_V5)
    if sha256_file(ROOT / v7.STUDY_V5) != load(v7.PROTOCOL_PATH)["training"]["study_sha256"]:
        raise ValueError("study-v5 sha differs")
    config = {**study, "modality": f"{observation}-node-choice", "training_seed": int(seed)}

    def factory(root, config_, algo, split):
        return v7.NodeChoiceDataset(store, membership, algo, observation, "train" if split == "train" else "dev")

    started = time.monotonic()
    result = train_visual(
        config,
        ROOT,
        GREEDY,
        output,
        deadline=deadline,
        progress=progress,
        resume=True,
        dataset_factory=factory,
        save_steps=v7.CHECKPOINT_EVERY,
        save_total_limit=1,
    )
    expected = [r["record_id"] for r in v7.NodeChoiceDataset(store, membership, GREEDY, observation, "train").records]
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
    for path in output.glob("checkpoint-*"):
        shutil.rmtree(path)
    return {"cell": [method, observation, seed], "resumed_from": resumed, "audit": audit_final(output, seed, membership)}


def audit_final(output: Path, seed: int, membership: dict) -> dict:
    config = json.loads((output / "final" / "adapter_config.json").read_text())
    result = json.loads((output / "result.json").read_text())
    records = len(membership["cells"][GREEDY]["training"])
    checks = {
        "r_64": config.get("r") == 64,
        "alpha_128": config.get("lora_alpha") == 128,
        "dropout_0_05": config.get("lora_dropout") == 0.05,
        "steps": result["steps"] == math.ceil(records * AUGMENTATIONS / 32),
        "seed": result["seed"] == seed,
        "samples": result["train_records"] == records * AUGMENTATIONS,
    }
    if not all(checks.values()):
        raise ValueError(f"adapter audit failed: {checks}")
    return checks


# ---------------------------------------------------------------------------- expert-iteration rollouts


def corpus_task_order() -> list[str]:
    """#136 tasks contributing greedy records, in #136 walk order."""

    order = load(Path("configs/experiments/choice-frontier-v3/membership.json"))["task_order"]
    order = order[GREEDY] if isinstance(order, dict) else order
    return list(order)


_CORPUS_R: dict[str, int] = {}


def corpus_task(task_id: str) -> dict:
    name = task_id.split("/", 1)[1]
    view = load(V3_TRAIN_VIEWS / name / "result.json")
    row = dict(view["binding"]["row"])
    if task_id not in _CORPUS_R:
        authority, _ = v7.authority_of(row["task_path"])
        run = exact_run(authority, task_id, GREEDY, v7.UNCAPPED)
        if run["termination"] != "goal_reached":
            raise ValueError(f"corpus teacher does not reach the goal: {task_id}")
        _CORPUS_R[task_id] = run["R"]
    r = _CORPUS_R[task_id]
    row["reference_costs"] = {GREEDY: {"decisions": r + 1, "expansions": r}}
    return {"row": row, "native_views": view["native_views"]}


def run_rollouts(observation: str, seed: int, *, gpu: int, deadline: float, progress) -> dict:
    checkpoint = str(adapter_dir("hadd", GREEDY, observation, seed))
    cell = {
        "method": "hadd",
        "algorithm": GREEDY,
        "observation": observation,
        "condition": "learned_adapter",
        "seed": seed,
    }
    state: dict = {}
    generate = v7.generator(GREEDY, {GREEDY: checkpoint}, deadline, state)
    tasks = corpus_task_order()
    rows = []
    try:
        for task_id in tasks:
            report, retained = run_model_episode(
                "rollouts", corpus_task(task_id), cell, checkpoint, backend(gpu), generate
            )
            rows.append({"task_id": task_id, "retained": retained, "result": report["result"]})
            progress("rollouts", cell=f"{observation}/s{seed}", completed=len(rows), total=len(tasks))
    finally:
        v7.free_policy(state)
    return {"outcome": "PASS", "episodes": len(rows), "solved": sum(r["result"]["goal_reached"] for r in rows)}


def expansions_to_goal(report: dict) -> int | None:
    expanded = 0
    for event in report["events"]:
        status = event["trusted_runtime_result"]["status"]
        if status == "goal_reached":
            return expanded
        if status == "expanded":
            expanded += 1
    return None


def prepare_ei_stage() -> dict:
    """Select per task the fewest-expansion solved rollout; build EI records, store and membership."""

    if (ROOT / EI_MEMBERSHIP).exists():
        raise ValueError(f"{EI_MEMBERSHIP} is frozen")
    v7.ensure_backend([GPU_BACKEND_PORTS[0]])
    order = corpus_task_order()
    records: dict[str, dict] = {}
    tasks_out: dict[str, dict] = {}
    cells: dict[str, dict] = {}
    selection: dict[str, dict] = {}
    for observation in OBSERVATIONS:
        training, diagnostic = [], []
        selection[observation] = {}
        for task_id in order:
            best = None
            for seed in SEEDS:
                cell = {
                    "method": "hadd",
                    "algorithm": GREEDY,
                    "observation": observation,
                    "condition": "learned_adapter",
                    "seed": seed,
                }
                path = episode_paths("rollouts", cell, task_id)[0]
                if not path.exists():
                    raise ValueError(f"rollout missing: {path}")
                report = load(path)
                e = expansions_to_goal(report)
                if e is not None and (best is None or e < best[0]):
                    best = (e, seed, report, cell)
            if best is None:
                selection[observation][task_id] = None
                continue
            expansions, seed, report, cell = best
            selection[observation][task_id] = {"seed": seed, "expansions_to_goal": expansions}
            task = corpus_task(task_id)
            view_output = episode_paths("rollouts", cell, task_id)[2]
            views = NodeChoiceTaskViews(ROOT, task, view_output, backend(0), read_only=True)
            session = v7.session_for(task, cell, views, report["checkpoint"])
            view_key = f"ei-{observation}:{task_id}"
            catalog: dict[str, list] = {}
            scenes: dict[str, str] = {}
            eligible = []
            for event in report["events"]:
                request = session.next_request()
                if request is None or [dict(e) for e in request.menu_binding] != event["menu"]:
                    raise ValueError(f"rollout replay menu differs: {task_id}")
                menu_states = session.menu_states(request)
                if observation == "visual":
                    v7.observe(views, session, request, cell, pixels=False)
                indices = [views.indices[views.key(s.atoms, s.fluents)] for s in menu_states]
                native = views.scene_views.tasks[task["row"]["task_id"]]
                for s, i in zip(menu_states, indices, strict=True):
                    catalog[str(i)] = [list(s.atoms), list(s.fluents)]
                    if observation == "visual":
                        scenes[str(i)] = native["scenes"][str(i)]
                if observation == "visual":
                    scenes["0"] = native["scenes"]["0"]
                if len(event["menu"]) >= 2:
                    chosen = event["trusted_runtime_result"]["expanded_state_id"]
                    choice = next(e["choice"] for e in event["menu"] if e["state_ref"] == chosen)
                    eligible.append(
                        {
                            "record_id": f"{view_key}:{GREEDY}:{event['decision_index']}",
                            "task_id": task_id,
                            "view_key": view_key,
                            "algorithm": GREEDY,
                            "domain": domain_of(task_id),
                            "decision_index": event["decision_index"],
                            "menu": event["menu"],
                            "menu_indices": indices,
                            "menu_size": len(event["menu"]),
                            "teacher_choice": choice,
                            "teacher_state_ref": chosen,
                            "input_tokens": {observation: event["view"]["input_tokens"]},
                            "source_rollout": {"seed": seed, "output": report["output"]},
                        }
                    )
                session.submit_output(event["raw_output"])
                v7.register_admissions(session, views, session.events[-1])
            native = views.scene_views.tasks[task["row"]["task_id"]]
            tasks_out[view_key] = {
                "task_path": task["row"]["task_path"],
                "states": catalog,
                "scenes": scenes,
                "static_pages": native["static_pages"],
                "goal_pages": native["goal_pages"],
                "view_id": native["view_id"],
            }
            for record in eligible[:RECORDS_PER_TASK]:
                records[record["record_id"]] = record
                if len(training) < TARGET_RECORDS:
                    training.append(record["record_id"])
                elif len(diagnostic) < DIAGNOSTIC_RECORDS:
                    diagnostic.append(record["record_id"])
            if len(training) >= TARGET_RECORDS and len(diagnostic) >= DIAGNOSTIC_RECORDS:
                break
        cells[observation] = {"training": training, "diagnostic": diagnostic}
    used = {rid for c in cells.values() for split in c.values() for rid in split}
    records = {rid: r for rid, r in records.items() if rid in used}
    store = {
        "schema_version": "choice_frontier_v8_store_v1",
        "records": records,
        "tasks": {k: v for k, v in tasks_out.items() if any(r["view_key"] == k for r in records.values())},
    }
    write(store_path("ei"), store)
    document = {
        "schema_version": "choice_frontier_v8_membership_v1",
        "kind": "expert_iteration",
        "protocol_id": protocol()["protocol_id"],
        "store": str(store_path("ei")),
        "store_records_sha256": sha256_text(canonical(records)),
        "cells_by_observation": cells,
        "selection": selection,
        "counts": {
            o: {
                "training": len(c["training"]),
                "diagnostic": len(c["diagnostic"]),
                "tasks_with_solved_rollout": sum(v is not None for v in selection[o].values()),
            }
            for o, c in cells.items()
        },
        "augmentation_check": {o: augmentation_report(store, c["training"]) for o, c in cells.items()},
    }
    document["membership_sha256"] = membership_sha({o: c for o, c in cells.items()})
    write(EI_MEMBERSHIP, document)
    return document["counts"]


# ---------------------------------------------------------------------------- D3 image heuristics


def d3_states() -> tuple[list, list[list[str]]]:
    from examples.planning_benchmark_slice.image_heuristics import HeuristicState

    store = _v7_store()
    labels = hstar_table()
    kappa = load(OUT / "preparation" / "kappa-menus.json.gz")
    states, menus = {}, []
    for rid, rows in sorted(kappa.items()):
        record = store["records"][rid]
        task = store["tasks"][record["view_key"]]
        keys = []
        for row in rows:
            key = f"{record['task_id']}#{row['index']}"
            label = labels[(record["task_id"], row["index"])]
            states.setdefault(
                key,
                HeuristicState(
                    key=key,
                    task_id=record["task_id"],
                    scene=task["scenes"][str(row["index"])],
                    goal_pages=tuple(task["goal_pages"]),
                    hstar=None if label["hstar"] is None else float(label["hstar"]),
                    hadd=float(label["h_add"]),
                ),
            )
            keys.append(key)
        menus.append(keys)
    return [states[k] for k in sorted(states)], menus


def d3_dir(backbone: str, target: str, seed: int) -> Path:
    return OUT / "d3" / backbone / target / f"seed-{seed}"


def run_d3_train(backbone: str, target: str, *, gpu: int, deadline: float, progress) -> dict:
    from examples.planning_benchmark_slice.image_heuristics import train_model

    states, menus = d3_states()
    results = {}
    for seed in SEEDS:
        results[seed] = train_model(
            states,
            menus,
            backbone=backbone,
            target=target,
            seed=seed,
            output_dir=ROOT / d3_dir(backbone, target, seed),
            root=ROOT,
            device="cuda:0",
            progress=lambda record: progress("d3_train", detail=record),
        )
    return {
        "outcome": "PASS",
        "models": {str(s): {k: r.get(k) for k in ("best_epoch", "best_val_loss")} for s, r in results.items()},
    }


def d3_algorithms(target: str) -> tuple[str, ...]:
    return (GREEDY,) if target == "rank" else ALGORITHMS


class ImageScorer:
    """A D3 model scoring menu states from their rendered scenes and the task's goal pages."""

    def __init__(self, model, scorer_id: str, views: NodeChoiceTaskViews, algorithm: str, task_id: str) -> None:
        self.model, self.scorer_id, self.views, self.algorithm, self.task_id = (
            model,
            scorer_id,
            views,
            algorithm,
            task_id,
        )
        self._cache: dict[str, float] = {}

    def __call__(self, states) -> list[float]:
        native = self.views.scene_views.tasks[self.task_id]
        missing = [s for s in states if s.state_id not in self._cache]
        if missing:
            for s in missing:
                index = self.views.indices[self.views.key(s.atoms, s.fluents)]
                if str(index) not in native["scenes"]:
                    self.views._scene_only_current(index)
            paths = [native["scenes"][str(self.views.indices[self.views.key(s.atoms, s.fluents)])] for s in missing]
            for s, score in zip(missing, self.model.score(paths, tuple(native["goal_pages"]), ROOT), strict=True):
                self._cache[s.state_id] = float(score)
        return [self._cache[s.state_id] for s in states]


def scored_gpu_path(task_id: str, algorithm: str, scorer_id: str) -> tuple[Path, Path]:
    episode = ROOT / OUT / "scored-d3" / task_id.replace("/", "__") / f"{algorithm}-{scorer_id}.json.gz"
    return episode, ROOT / OUT / "scored-d3" / "views" / task_id.replace("/", "__") / f"{algorithm}-{scorer_id}"


def run_d3_scoring(backbone: str, target: str, *, gpu: int, deadline: float, progress) -> dict:
    from examples.planning_benchmark_slice.image_heuristics import load_model

    count = 0
    for seed in SEEDS:
        model = load_model(ROOT / d3_dir(backbone, target, seed), "cuda:0")
        scorer_id = f"{backbone}_{target}_s{seed}"
        for algorithm in d3_algorithms(target):
            for task_id in strata_tasks(STRATA):
                episode, view_output = scored_gpu_path(task_id, algorithm, scorer_id)
                if episode.exists():
                    continue
                task = panel_task(task_id)
                row = panel_row(task_id)
                if view_output.exists():
                    shutil.rmtree(view_output)  # an interrupted scorer episode restarts from scratch
                views = NodeChoiceTaskViews(ROOT, task, view_output, backend(gpu))
                scorer = ImageScorer(model, scorer_id, views, algorithm, task_id)
                session = run_scored_episode(
                    views.authority,
                    NodeChoiceTask(task_id, row["domain"], algorithm, row["R"][algorithm]),
                    scorer,
                    observation="visual",
                    on_event=lambda s, event, views=views: v7.register_admissions(s, views, event),
                )
                views.save()
                write(
                    episode,
                    {
                        **session.episode(),
                        "task_id": task_id,
                        "condition": scorer_id,
                        "backbone": backbone,
                        "target": target,
                        "training_seed": seed,
                    },
                )
                count += 1
                progress("d3_scoring", scorer=scorer_id, algorithm=algorithm, task=task_id)
        del model
        gc.collect()
    return {"outcome": "PASS", "episodes_this_attempt": count}


# ============================================================================ queue


def slots() -> list[dict]:
    result = []
    for observation in OBSERVATIONS:
        for seed in SEEDS:
            stages = [f"train:hstar:{observation}:{seed}"] + ([f"smoke:hstar:{observation}"] if seed == 17 else [])
            result.append(
                {
                    "key": f"train-hstar-{observation}-s{seed}",
                    "stages": stages,
                    "needs": [],
                    "files": [str(HSTAR_MEMBERSHIP)],
                }
            )
    for observation in OBSERVATIONS:
        for seed in SEEDS:
            result.append(
                {
                    "key": f"rollouts-{observation}-s{seed}",
                    "stages": [f"rollouts:{observation}:{seed}"],
                    "needs": [],
                    "files": [],
                }
            )
    for observation in OBSERVATIONS:
        for seed in SEEDS:
            stages = [f"train:ei:{observation}:{seed}"] + ([f"smoke:ei:{observation}"] if seed == 17 else [])
            result.append(
                {"key": f"train-ei-{observation}-s{seed}", "stages": stages, "needs": [], "files": [str(EI_MEMBERSHIP)]}
            )
    for backbone in D3_BACKBONES:
        for target in D3_TARGETS:
            result.append(
                {
                    "key": f"d3-train-{backbone}-{target}",
                    "stages": [f"d3train:{backbone}:{target}"],
                    "needs": [],
                    "files": [str(LABELS_PATH)],
                }
            )
    ordered = sorted(
        eval_cells(),
        key=lambda c: (
            c["method"] == "zeroshot",
            c["seed"] != 17,
            {"hstar": 0, "ei": 1, "hadd": 2, "zeroshot": 3}[c["method"]],
        ),
    )
    for cell in ordered:
        needs = []
        if cell["method"] in ("hstar", "ei"):
            needs = [
                f"train:{cell['method']}:{cell['observation']}:{cell['seed']}",
                f"smoke:{cell['method']}:{cell['observation']}",
            ]
        result.append(
            {
                "key": f"eval-{cell_key(cell).replace(':', '-')}",
                "stages": [f"eval:{cell_key(cell)}"],
                "needs": needs,
                "files": [str(VIEW_REPORT)],
            }
        )
    for backbone in D3_BACKBONES:
        for target in D3_TARGETS:
            result.append(
                {
                    "key": f"d3-score-{backbone}-{target}",
                    "stages": [f"d3score:{backbone}:{target}"],
                    "needs": [f"d3train:{backbone}:{target}"],
                    "files": [str(VIEW_REPORT)],
                }
            )
    return result


def find_cell(key: str) -> dict:
    return next(c for c in eval_cells() if cell_key(c) == key)


def receipt_path(unit: str) -> Path:
    return ROOT / QUEUE / "receipts" / f"{unit.replace(':', '__')}.json"


def unit_done(unit: str) -> bool:
    return receipt_path(unit).exists()


def slot_ready(slot: dict) -> bool:
    return all(unit_done(u) for u in slot["needs"]) and all((ROOT / f).exists() for f in slot["files"])


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
            if slot_done(slot) or not slot_ready(slot):
                continue
            claim = state["claims"].get(key)
            if claim is not None and v7.claim_live(claim):
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
    elif kind == "rollouts":
        body = run_rollouts(parts[0], int(parts[1]), gpu=gpu, deadline=deadline, progress=progress)
    elif kind == "eval":
        body = run_evaluation(find_cell(":".join(parts)), gpu=gpu, deadline=deadline, progress=progress)
    elif kind == "d3train":
        body = run_d3_train(parts[0], parts[1], gpu=gpu, deadline=deadline, progress=progress)
    elif kind == "d3score":
        body = run_d3_scoring(parts[0], parts[1], gpu=gpu, deadline=deadline, progress=progress)
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


def live_claims_elsewhere() -> bool:
    path = ROOT / QUEUE / "claims.json"
    state = json.loads(path.read_text()) if path.exists() else {"claims": {}}
    return any(v7.claim_live(c) and c.get("pid") != os.getpid() for c in state["claims"].values())


def worker(gpu: int, max_slots: int | None = None) -> dict:
    if os.environ.get("CUDA_VISIBLE_DEVICES") != str(gpu):
        raise ValueError(f"worker --gpu {gpu} requires CUDA_VISIBLE_DEVICES={gpu}")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("worker requires a scheduler-assigned MASTER_PORT")
    v7.ensure_backend([GPU_BACKEND_PORTS[gpu]])
    deadline = attempt_deadline()
    handle = v7.worker_handle(gpu)
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"]) if os.environ.get("EXPANDED_PROGRESS_PATH") else None
    log, stop_reason, consecutive, processed = [], "queue_empty", 0, 0

    def progress(stage, **values):
        record = {"time": time.time(), "stage": stage, **values}
        print(json.dumps(record, default=str), flush=True)
        if progress_path is not None:
            write(
                progress_path,
                {"completed": sum(slot_done(s) for s in slots()), "total": len(slots()), "current": record},
            )

    while True:
        charged = v7.charged_gpu_hours(ledger())
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
            pending = [s for s in slots() if not slot_done(s)]
            if pending and (live_claims_elsewhere() or any(not slot_ready(s) for s in pending)):
                time.sleep(300)  # wait for a sibling's unit or a committed membership file
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


def queue_summary() -> dict:
    path = ROOT / QUEUE / "claims.json"
    state = json.loads(path.read_text()) if path.exists() else {"claims": {}, "failures": {}}
    counts = {"done": 0, "running": 0, "blocked": 0, "waiting": 0, "pending": 0}
    running, blocked = [], []
    for slot in slots():
        claim = state["claims"].get(slot["key"])
        if slot_done(slot):
            counts["done"] += 1
        elif claim is not None and v7.claim_live(claim):
            counts["running"] += 1
            running.append({"slot": slot["key"], "gpu": claim.get("gpu")})
        elif len(state["failures"].get(slot["key"], [])) >= MAX_SLOT_FAILURES:
            counts["blocked"] += 1
            blocked.append({"slot": slot["key"], "error": state["failures"][slot["key"]][-1]["error"][-400:]})
        elif not slot_ready(slot):
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
        "program_id": "choice-frontier-v8",
        "status": "authorized_followup_window",
        "issue": 149,
        "authorization": {
            "granted_by": "author decision 2026-10-01 (docs/experiments/choice-frontier/issue-149-feasibility.md)",
            "window_gpu_hours_cap": GPU_HOURS_CAP,
            "basis": "~243 GPU-h expected / ~318 at the 2R cap with margin (feasibility note)",
        },
        "start_utc": "2026-10-01T00:00:00Z",
        "gpu_cutoff_utc": "2026-10-11T08:00:00Z",
        "handoff_deadline_utc": "2026-10-11T08:00:00Z",
        "deadline_kind": "slurm_allocation_end",
        "hardware": {
            "gpus": 2,
            "model": "NVIDIA H100 80GB PCIe",
            "host": p["hardware"]["node"],
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
        "execution_authorization": "protocol committed before any derivation; panels, labels and memberships "
        "committed before any control or training; code and job files committed before their first launch; "
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
            f"source {v7.ENV_SCRIPT} && export CUDA_VISIBLE_DEVICES={gpu} && "
            "export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True && "
            f"exec python scripts/run_choice_frontier_v8.py worker --gpu {gpu}",
        ],
        "completion_hook": [
            "bash",
            "-lc",
            f"source {v7.ENV_SCRIPT} && export CUDA_VISIBLE_DEVICES= && "
            "exec python scripts/run_choice_frontier_v8.py hook",
        ],
    }
    if reason:
        job["resume_reason"] = reason
    return job


def launch(gpus=(0, 1), reason: str | None = None, dry_run: bool = False, write_only: bool = False) -> list[dict]:
    from examples.planning_benchmark_slice.expanded_scheduler import alive, charged, timestamp

    schedule = ensure_schedule()
    state = ledger()
    plan = []
    for gpu in gpus:
        base = f"cfv8-worker-gpu{gpu}"
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
            check=False,
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
        check=False,
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


def status() -> dict:
    from examples.planning_benchmark_slice.expanded_scheduler import alive

    state = ledger()
    return {
        "queue": queue_summary(),
        "gpu_hours_charged": round(v7.charged_gpu_hours(state), 3),
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
        "smoke": {f"{m}/{o}": smoke_verdict(m, o) for m in ("hstar", "ei") for o in OBSERVATIONS},
        "backends": {port: v7.backend_up(port) for port in (*GPU_BACKEND_PORTS.values(), PREP_BACKEND_PORT)},
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


def _finalize_model(item) -> dict:
    stage, cell, task_id = item
    episode, partial, _views = episode_paths(stage, cell, task_id)
    key = [stage, cell_key(cell), task_id]
    if not episode.exists():
        return {"key": key, "status": "missing", "partial": partial.exists()}
    report = load(episode)
    task = corpus_task(task_id) if stage == "rollouts" else panel_task(task_id)
    try:
        replay_model_episode(task, report, backend(0))
    except Exception as error:  # recorded, never repaired
        return {"key": key, "status": "mismatch", "error": f"{type(error).__name__}: {error}"}
    return {"key": key, "status": "replayed"}


def _finalize_d3(item) -> dict:
    task_id, algorithm, scorer_id = item
    episode, _views = scored_gpu_path(task_id, algorithm, scorer_id)
    key = ["d3", algorithm, scorer_id, task_id]
    if not episode.exists():
        return {"key": key, "status": "missing"}
    row = panel_row(task_id)
    authority, _ = task_source(row)
    try:
        verify_scored_episode(
            authority, NodeChoiceTask(task_id, row["domain"], algorithm, row["R"][algorithm]), load(episode)
        )
    except Exception as error:
        return {"key": key, "status": "mismatch", "error": f"{type(error).__name__}: {error}"}
    return {"key": key, "status": "replayed"}


def finalize_stage(workers: int = 8) -> dict:
    from concurrent.futures import ProcessPoolExecutor

    v7.ensure_backend([GPU_BACKEND_PORTS[0]])
    items = []
    for cell in eval_cells():
        if cell["method"] in ("hstar", "ei") and smoke_verdict(cell["method"], cell["observation"]) == "FAIL":
            continue
        items.extend(("evaluation", cell, t) for t in strata_tasks(cell["strata"]))
    for observation in OBSERVATIONS:
        for seed in SEEDS:
            cell = {
                "method": "hadd",
                "algorithm": GREEDY,
                "observation": observation,
                "condition": "learned_adapter",
                "seed": seed,
            }
            items.extend(("rollouts", cell, t) for t in corpus_task_order())
    d3 = [
        (t, a, f"{b}_{tg}_s{s}")
        for b in D3_BACKBONES
        for tg in D3_TARGETS
        for s in SEEDS
        for a in d3_algorithms(tg)
        for t in strata_tasks(STRATA)
    ]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(_finalize_model, items)) + list(pool.map(_finalize_d3, d3))
    summary = {
        "bindings": len(rows),
        "replayed": sum(r["status"] == "replayed" for r in rows),
        "missing": [r["key"] for r in rows if r["status"] == "missing"],
        "mismatches": [r for r in rows if r["status"] == "mismatch"],
        "smoke": {f"{m}/{o}": smoke_verdict(m, o) for m in ("hstar", "ei") for o in OBSERVATIONS},
    }
    summary["complete"] = not summary["missing"] and not summary["mismatches"]
    write(OUT / "evaluation-finalize.json", summary)
    return {k: (len(v) if isinstance(v, list) else v) for k, v in summary.items()}


# ============================================================================ cli


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("validate")
    for name in ("panels", "prepare-views", "labels", "controls", "finalize"):
        sub.add_parser(name).add_argument("--workers", type=int, default=6)
    sub.add_parser("prepare-hstar")
    sub.add_parser("prepare-ei")
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
    elif args.stage == "prepare-views":
        result = prepare_views_stage(args.workers)
    elif args.stage == "labels":
        result = labels_stage(args.workers)
    elif args.stage == "prepare-hstar":
        result = prepare_hstar_stage()
    elif args.stage == "controls":
        result = controls_stage(args.workers)
    elif args.stage == "prepare-ei":
        result = prepare_ei_stage()
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
        result = v7.ensure_backend(args.ports)
    else:
        from scripts.analyze_choice_frontier_v8 import main as analyze

        result = analyze()
    print(json.dumps(result, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
