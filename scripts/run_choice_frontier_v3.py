#!/usr/bin/env python
"""Choice-frontier v3 (#136) adapter scale-up runner.

Copy of ``scripts/run_choice_frontier.py`` (#132) with v3 paths and the #136
changes (protocol ``configs/experiments/choice-frontier-v3/protocol.json``,
frozen doc ``docs/experiments/choice-frontier/issue-136-protocol.md``):

- ``generate-train-tasks`` — serial generation of fresh training tasks from the
  24 expanded-study snapshots (seeds 945000-945099) plus the exclusion rule;
  writes ``configs/experiments/choice-frontier-v3/training-tasks.json``.
- ``prepare`` — derives exact choice-contract teacher episodes from PDDL (no
  stored traces: ``trace_gate: not_applicable_fresh_tasks``), takes records by
  the frozen corpus rule, renders per-task scene catalogs, applies the
  menu-order augmentation check and writes the store, report and membership.
- ``audit-prepare`` — independent bit-exact re-derivation of every episode.
- ``train --algorithm A --seed S`` / ``audit-train`` — one LoRA cell per job.
- ``smoke`` / ``audit-smoke`` — the #132 smoke gate on the seed-17 adapters.
- ``evaluate-inputs`` / ``evaluate-worker --algorithm A --seed S`` — learned
  adapters on the frozen #135 panel (controls and base are reused from #135).
- ``finalize`` — independent replay of every model episode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.choice_frontier import (  # noqa: E402
    CHOICE_ARM,
    CHOICE_LEGEND,
    CHOICE_RECIPE_ID,
    CHOICE_SCHEMA,
    CHOICE_SYSTEM_MESSAGE,
    ChoiceFrontierModelSession,
    ChoiceFrontierTask,
    canonical_choice,
)
from examples.planning_benchmark_slice.choice_frontier_views import (  # noqa: E402
    CONTEXT_TOKENS,
    OUTPUT_TOKENS,
    ChoiceFrontierTaskViews,
    assert_no_text_leak,
    build_choice_observation,
    choice_payload,
)
from examples.planning_benchmark_slice.modality_view_preparation import write_json  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402

PROTOCOL_PATH = Path("configs/experiments/choice-frontier-v3/protocol.json")
SCHEDULE_PATH = Path("docs/experiments/choice-frontier/schedule-v3.json")
LEDGER_PATH = ROOT / "outputs/choice-frontier/v3/budget.json"
CONFIG = ROOT / "configs/experiments/choice-frontier-v3"
TRAINING_TASKS = CONFIG / "training-tasks.json"
MEMBERSHIP = CONFIG / "membership.json"
PANEL_MEMBERSHIP = ROOT / "configs/experiments/choice-frontier-v2/membership.json"
PANEL_VIEW_REPORT = ROOT / "outputs/choice-frontier/v2/reference-views.json"
V1_PROTOCOL = ROOT / "configs/experiments/choice-frontier/choice-frontier-protocol-v1.json"
PANEL_PROTOCOL = ROOT / "configs/experiments/expanded-study/panel-protocol-v2.json"
SNAPSHOTS = ROOT / "configs/experiments/expanded-study/tasks"
RENDER_PROFILES = ROOT / "configs/experiments/issue71/v2/render.json"
ENDPOINT = "http://127.0.0.1:18092"
PRIMARY_SEEDS = tuple(range(945000, 945100))
EXTENSION_SEEDS = tuple(range(945100, 945300))
ALGORITHMS = ("best_first_add_greedy", "best_first_add_w3")
TEACHER_SEED = 17
UNCAPPED = 10**6
RECORD_LADDER = (2048, 1536, 1024)
MINIMUM_RECORDS = 1024
MAX_RECORDS_PER_TASK = 64
DIAGNOSTIC_RECORDS = 16
AUGMENTATIONS = 2
DERIVATION_TIMEOUT = 600
BASIS_SECONDS_PER_SAMPLE = 2.75
BASIS_MEAN_TOKENS = 4867.078125
BASE_MODEL_CALL_CAP = 1
EPISODE_SCHEMA = "choice_frontier_episode_v1"
TASK_PREFIX = "choice-frontier-v3-train"


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def write(path: Path, payload) -> None:
    write_json(path, payload)


def load_protocol() -> dict:
    protocol = read_json(ROOT / PROTOCOL_PATH)
    protocol["root"] = str(ROOT)
    return protocol


def output_root(protocol: dict | None = None) -> Path:
    return ROOT / (protocol or load_protocol())["output_root"]


def progress_writer():
    path = Path(os.environ.get("EXPANDED_PROGRESS_PATH", "/tmp/choice-frontier-v3-progress.json"))

    def progress(stage: str, **fields):
        write(path, {"stage": stage, "updated": time.time(), **fields})

    return progress


# --------------------------------------------------------------------------- #
# menu-order augmentation
# --------------------------------------------------------------------------- #


def augment_menu(
    record_id: str, menu: list[dict], menu_indices: list[int], teacher_state_ref: str, copy: int
) -> tuple[list[dict], list[int], str]:
    """Permute a record's menu with seed ``aug:{record_id}:{copy}``; relabel c0..cK.

    Scenes stay bound to their states; the target is the label the teacher's
    (exact heap head) state carries after the permutation.
    """

    order = list(range(len(menu)))
    random.Random(f"aug:{record_id}:{copy}").shuffle(order)
    permuted = [{"choice": f"c{i}", "state_ref": menu[j]["state_ref"]} for i, j in enumerate(order)]
    indices = [menu_indices[j] for j in order]
    target = next(entry["choice"] for entry in permuted if entry["state_ref"] == teacher_state_ref)
    return permuted, indices, target


def label_position(label: str, size: int) -> str:
    index = int(label[1:])
    return "first" if index == 0 else ("last" if index == size - 1 else "middle")


# --------------------------------------------------------------------------- #
# generate-train-tasks
# --------------------------------------------------------------------------- #


def stratum_profiles() -> dict[tuple[str, str], dict]:
    protocol = read_json(PANEL_PROTOCOL)
    result = {(s["domain"], s["stratum"]): s for s in protocol["strata"]}
    if len(result) != 24:
        raise ValueError("expanded-study panel protocol does not hold 24 strata")
    for domain, stratum in result:
        if not (SNAPSHOTS / f"{domain}-{stratum}.json").is_file():
            raise ValueError(f"generator snapshot missing: {domain}-{stratum}")
    return result


def walk(seeds) -> list[tuple[str, str, int]]:
    """Seed-major walk; within a seed the 24 strata in (domain, difficulty) order."""

    strata = sorted(stratum_profiles())
    return [(domain, stratum, seed) for seed in seeds for domain, stratum in strata]


def task_name(domain: str, stratum: str, seed: int) -> str:
    return f"{domain}-{stratum}-{seed}"


def exclusion_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for record in read_json(ROOT / "configs/experiments/choice-frontier-v2/candidates.json")["candidates"]:
        if record.get("problem_sha256"):
            hashes.setdefault(record["problem_sha256"], f"a:choice-frontier-v2-candidate:{record['task_id']}")
    for task in read_json(ROOT / "configs/experiments/expanded-study/final-panel.json")["tasks"]:
        row = task.get("row", task)
        problem = read_json(ROOT / row["task_path"])["problem_pddl"]
        hashes.setdefault(sha256_text(problem), f"b:expanded-study-final-panel:{row['task_id']}")
    membership = read_json(ROOT / "configs/experiments/choice-frontier/membership.json")
    task_ids = sorted(
        {
            rid.split(":")[0]
            for key in ("training_record_ids", "diagnostic_record_ids")
            for ids in membership[key].values()
            for rid in ids
        }
    )
    for task_id in task_ids:
        problem = read_json(ROOT / "data/best_first_paired_phase_v3/exact-traces/pairs" / task_id / "task.json")[
            "problem_pddl"
        ]
        hashes.setdefault(sha256_text(problem), f"c:choice-frontier-v1-corpus:{task_id}")
    return hashes


def exclusion_source_counts() -> dict[str, int]:
    counts = {"a": 0, "b": 0, "c": 0}
    for reason in exclusion_hashes().values():
        counts[reason[0]] += 1
    return counts


def generate_one(domain: str, stratum: str, profile: dict, seed: int) -> dict:
    """Run the frozen profile generator once (serial only: shared cwd temp files)."""

    from examples.planning_benchmark_slice.expanded_candidates import generate

    name = task_name(domain, stratum, seed)
    directory = output_root() / "train-tasks" / name
    task_path = directory / "task.json"
    if not task_path.exists():
        try:
            task = generate(ROOT, profile, seed, directory / "generator")
        except Exception as error:  # generator failure is a recorded drop
            return {"task_path": task_path, "error": f"{type(error).__name__}: {error}"}
        task["authority_transformations"] = list(task["authority_transformations"])
        write(task_path, task)
    return {"task_path": task_path}


def generate_train_tasks_stage(extend: bool = False) -> dict:
    from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority

    profiles = stratum_profiles()
    excluded_by = exclusion_hashes()
    prior = read_json(TRAINING_TASKS) if extend else None
    seeds = list(PRIMARY_SEEDS) + (list(EXTENSION_SEEDS) if extend else [])
    records = []
    seen: dict[str, str] = {}
    progress = progress_writer()
    order = walk(seeds)
    for position, (domain, stratum, seed) in enumerate(order):
        name = task_name(domain, stratum, seed)
        generation = generate_one(domain, stratum, profiles[(domain, stratum)], seed)
        record = {
            "task_id": f"{TASK_PREFIX}/{name}",
            "domain": domain,
            "difficulty": stratum,
            "seed": seed,
            "walk_position": position,
            "task_path": str(generation["task_path"].relative_to(ROOT)),
            "generator_command": None,
            "problem_sha256": None,
            "excluded": True,
            "exclude_reason": None,
        }
        if "error" in generation:
            record["exclude_reason"] = "generator_failed"
            record["error"] = generation["error"]
        else:
            task = read_json(generation["task_path"])
            record["generator_command"] = [c.replace(str(ROOT) + "/", "") for c in task["generator_command"]]
            record["problem_sha256"] = sha256_text(task["problem_pddl"])
            authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
            if record["problem_sha256"] in excluded_by:
                record["exclude_reason"] = "overlap:" + excluded_by[record["problem_sha256"]]
            elif record["problem_sha256"] in seen:
                record["exclude_reason"] = f"duplicate_training_task:{seen[record['problem_sha256']]}"
            elif authority.is_goal(authority.initial_state):
                record["exclude_reason"] = "initial_goal"
            else:
                record["excluded"] = False
                seen[record["problem_sha256"]] = record["task_id"]
        records.append(record)
        progress("generate_train_tasks", completed=position + 1, total=len(order), task=record["task_id"])
        print(record["task_id"], record["excluded"], record["exclude_reason"], flush=True)
    reasons: dict[str, int] = {}
    for record in records:
        if record["excluded"]:
            key = record["exclude_reason"].split(":")[0]
            reasons[key] = reasons.get(key, 0) + 1
    payload = {
        "schema_version": "choice_frontier_v3_training_tasks_v1",
        "protocol": str(PROTOCOL_PATH),
        "seeds": [seeds[0], seeds[-1]],
        "extended": extend,
        "walk_order": "seed-major; within a seed the 24 strata in (domain, difficulty) order",
        "exclusion_key": "sha256(problem_pddl)",
        "exclusion_sources": {
            "a": "configs/experiments/choice-frontier-v2/candidates.json",
            "b": "configs/experiments/expanded-study/final-panel.json",
            "c": "configs/experiments/choice-frontier/membership.json",
        },
        "exclusion_source_hash_counts": exclusion_source_counts(),
        "counts": {
            "generated": len(records),
            "eligible": sum(1 for r in records if not r["excluded"]),
            "dropped_by_reason": dict(sorted(reasons.items())),
        },
        "tasks": records,
    }
    if prior is not None and prior["tasks"] != records[: len(prior["tasks"])]:
        raise ValueError("extended generation does not reproduce the primary training tasks")
    write(TRAINING_TASKS, payload)
    return payload["counts"]


# --------------------------------------------------------------------------- #
# prepare: teacher derivation from PDDL
# --------------------------------------------------------------------------- #


def page_counts(task: dict) -> tuple[int, int]:
    """Static-context and goal page counts of the scene-only view recipe."""

    from examples.planning_benchmark_slice.modality_pages import fact_blocks, paginate
    from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
    from examples.planning_benchmark_slice.scene_only_views import static_blocks
    from examples.planning_benchmark_slice.source_goal import source_task

    source = source_task(task["domain_pddl"], task["problem_pddl"])
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    initial = {
        "index": 0,
        "atoms": list(authority.initial_state.atoms),
        "fluents": list(authority.initial_state.fluents),
        "parent": None,
    }
    blocks = fact_blocks(authority.task_context(), initial, source)
    return len(paginate("task-context", static_blocks(blocks))), len(paginate("goal", blocks["goal"]))


def derive_fresh_episode(task_path: str, task_id: str, algorithm: str, pages: tuple[int, int]) -> dict:
    """Exact choice-contract teacher from PDDL, up to the 64th eligible decision."""

    from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority

    source = read_json(ROOT / task_path)
    authority = PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"])
    task = ChoiceFrontierTask(
        instance_id=task_id, pair_id=task_id, domain=task_id.split("/")[1].rsplit("-", 2)[0],
        algorithm=algorithm, exact_expansions=UNCAPPED,
    )
    session = ChoiceFrontierModelSession(authority=authority, task=task, arm="exact_reference", seed=TEACHER_SEED)
    static_count, goal_count = pages
    decisions: list[dict] = []
    eligible = 0
    overflow = 0
    while eligible < MAX_RECORDS_PER_TASK and (request := session.next_request()) is not None:
        menu = [dict(entry) for entry in request.menu_binding]
        tokens = None
        is_eligible = False
        if len(menu) >= 2:
            payload = choice_payload(dict(request.model_input))
            try:
                placeholder = build_choice_observation(
                    payload,
                    ["static"] * static_count,
                    ["goal"] * goal_count,
                    list(request.model_input["frontier_menu"]["choices"]),
                    lambda index: f"scenes/state-{index:06d}.png",
                    list(range(1, len(menu) + 1)),
                )
                assert_no_text_leak(placeholder)
                tokens = placeholder["binding"]["input_tokens"]
                is_eligible = tokens + OUTPUT_TOKENS <= CONTEXT_TOKENS
            except RuntimeError as error:
                if "OBSERVATION_OVERFLOW" not in str(error):
                    raise
                overflow += 1
        teacher = session.reference_output()
        session.submit_output(teacher)
        event = session.events[-1]
        result = event["trusted_runtime_result"]
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
                    [admission["action"], admission["trusted_runtime_result"]["target_state_id"]]
                    for admission in result.get("admissions", [])
                ],
            }
        )
        eligible += int(is_eligible)
    return {
        "task_id": task_id,
        "algorithm": algorithm,
        "pages": list(pages),
        "decisions": decisions,
        "eligible": eligible,
        "overflow_skipped": overflow,
        "complete": session.complete,
        "termination_reason": session.termination_reason,
        "trace_gate": "not_applicable_fresh_tasks",
    }


def _timeout(signum, frame):
    raise TimeoutError("derivation_timeout")


def _derive_task(item: tuple[str, str]) -> dict:
    import signal

    task_id, task_path = item
    source = read_json(ROOT / task_path)
    pages = page_counts(source)
    result = {"task_id": task_id, "pages": list(pages), "episodes": {}, "timeouts": []}
    for algorithm in ALGORITHMS:
        previous = signal.signal(signal.SIGALRM, _timeout)
        signal.setitimer(signal.ITIMER_REAL, DERIVATION_TIMEOUT)
        try:
            result["episodes"][algorithm] = derive_fresh_episode(task_path, task_id, algorithm, pages)
        except TimeoutError:
            result["timeouts"].append(algorithm)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
    return result


def episode_digest(episode: dict) -> str:
    return sha256_text(canonical(episode))


def eligible_records(episode: dict) -> list[dict]:
    return [d for d in episode["decisions"] if d["eligible"]][:MAX_RECORDS_PER_TASK]


def select_records(order: list[str], derived: dict[str, dict], dropped: set[str], target: int) -> dict:
    """Per-algorithm walk: records up to ``target`` then the next 16 diagnostics."""

    selection = {}
    for algorithm in ALGORITHMS:
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
                if len(training) < target:
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


def selection_complete(selection: dict, target: int) -> bool:
    return all(
        len(s["training"]) >= target and len(s["diagnostic"]) >= DIAGNOSTIC_RECORDS for s in selection.values()
    )


# --------------------------------------------------------------------------- #
# prepare: per-task scene catalogs (planimation backend)
# --------------------------------------------------------------------------- #


def truncated_catalog(task: dict, episodes: dict[str, dict], last_decision: dict[str, int]) -> dict:
    """Initial state + every admission of each expansion before the last used decision."""

    from examples.planning_benchmark_slice.expanded_views import ReferenceStateCatalog
    from examples.planning_benchmark_slice.pddl_state import GroundedAction, PDDLStateAuthority

    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    catalog = ReferenceStateCatalog(authority)
    decisions = []
    refs: dict[str, dict[str, object]] = {}
    for algorithm in ALGORITHMS:
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
            "scope": "initial state plus every admission of the truncated exact choice-contract teacher episodes",
        },
        "indices": {
            algorithm: {ref: catalog.indices[state.state_id] for ref, state in states.items()}
            for algorithm, states in refs.items()
        },
    }


def build_task_views(item: tuple[dict, dict, dict]) -> dict:
    """The prepare_expanded_views.prepare_task recipe over a truncated teacher catalog."""

    import torch

    from examples.planning_benchmark_slice.modality_pages import compose_page, fact_blocks, paginate
    from examples.planning_benchmark_slice.modality_view_preparation import _state_goal_checks
    from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
    from examples.planning_benchmark_slice.scene_assets import collect_task_scenes
    from examples.planning_benchmark_slice.scene_only_views import materialize_task
    from examples.planning_benchmark_slice.source_goal import source_task

    torch.set_num_threads(2)
    record, episodes, last_decision = item
    name = record["task_id"].split("/", 1)[1]
    output = output_root() / "train-views" / name
    saved = output / "result.json"
    task = read_json(ROOT / record["task_path"])
    built = truncated_catalog(task, episodes, last_decision)
    catalog = built["catalog"]
    counts = {}
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
        result = read_json(saved)
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
            profiles = read_json(RENDER_PROFILES)["domain_profiles"]
            collect_task_scenes(
                root=ROOT,
                row=row,
                profile=ROOT / profiles[row["domain"]],
                endpoint=ENDPOINT,
                output=scene_output,
                timeout=30,
                preflight=False,
                progress=lambda detail: None,
                catalog=catalog,
            )
        collected = read_json(scene_output / "catalog.json.gz")
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
        "states": len(collected["states"]),
    }
    write(saved, result)
    return result


# --------------------------------------------------------------------------- #
# prepare / audit-prepare
# --------------------------------------------------------------------------- #


def eligible_tasks() -> list[dict]:
    return [record for record in read_json(TRAINING_TASKS)["tasks"] if not record["excluded"]]


def derived_path(task_id: str) -> Path:
    return output_root() / "preparation" / "episodes" / f"{task_id.split('/', 1)[1]}.json.gz"


def derive_in_walk_order(tasks: list[dict], derived: dict, needed, workers: int, progress) -> None:
    """Derive tasks in walk order, in parallel chunks, until ``needed()`` is false."""

    from concurrent.futures import ProcessPoolExecutor

    pending = [t for t in tasks if t["task_id"] not in derived]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        cursor = 0
        while needed() and cursor < len(pending):
            chunk = pending[cursor : cursor + workers]
            cursor += len(chunk)
            for task, result in zip(
                chunk, pool.map(_derive_task, [(t["task_id"], t["task_path"]) for t in chunk]), strict=True
            ):
                write(derived_path(task["task_id"]), result)
                derived[task["task_id"]] = result
            progress("choice_v3_derive", completed=len(derived), total=len(tasks))


def build_record(task_id: str, algorithm: str, decision: dict, task_view: dict, domain: str, split: str) -> dict:
    native = task_view["native_views"]
    indices = task_view["indices"][algorithm]
    menu_indices = [indices[entry["state_ref"]] for entry in decision["menu"]]
    choices = [entry["choice"] for entry in decision["menu"]]
    payload = choice_payload(
        {
            "algorithm": algorithm,
            "frontier_menu": {"choices": choices},
            "representation": "visual-choice-frontier",
            "schema_version": CHOICE_SCHEMA,
        }
    )
    example = build_choice_observation(
        payload,
        native["static_pages"],
        native["goal_pages"],
        choices,
        lambda state_index: native["scenes"][str(state_index)],
        menu_indices,
    )
    assert_no_text_leak(example)
    if example["binding"]["input_tokens"] != decision["input_tokens"]:
        raise ValueError("choice-frontier v3 store token count differs from derivation")
    return {
        "record_id": f"{task_id}:{algorithm}:{decision['decision_index']}",
        "task_id": task_id,
        "domain": domain,
        "algorithm": algorithm,
        "split": split,
        "decision_index": decision["decision_index"],
        "status": decision["status"],
        "menu": decision["menu"],
        "menu_indices": menu_indices,
        "teacher_choice": decision["teacher_choice"],
        "teacher_state_ref": decision["teacher_state_ref"],
        "input_tokens": decision["input_tokens"],
        "input_pages": example["binding"]["input_pages"],
        "menu_size": decision["menu_size"],
    }


def augmentation_check(records: list[dict]) -> dict:
    histogram = {"first": 0, "middle": 0, "last": 0}
    original = {"first": 0, "middle": 0, "last": 0}
    chance_last = []
    identical_orders = 0
    for record in records:
        orders = []
        original[label_position(record["teacher_choice"], record["menu_size"])] += 1
        for copy in range(AUGMENTATIONS):
            permuted, _indices, target = augment_menu(
                record["record_id"], record["menu"], record["menu_indices"], record["teacher_state_ref"], copy
            )
            if next(e["state_ref"] for e in permuted if e["choice"] == target) != record["teacher_state_ref"]:
                raise ValueError("augmented target does not bind the teacher state")
            histogram[label_position(target, record["menu_size"])] += 1
            chance_last.append(1 / record["menu_size"])
            orders.append([e["state_ref"] for e in permuted])
        identical_orders += int(orders[0] == orders[1])
    samples = sum(histogram.values())
    last_share = histogram["last"] / samples
    chance = sum(chance_last) / len(chance_last)
    return {
        "samples": samples,
        "target_position_histogram": histogram,
        "target_last_share": last_share,
        "chance_last_rate_mean_inverse_menu_size": chance,
        "difference_percentage_points": 100 * (last_share - chance),
        "tolerance_percentage_points": 5.0,
        "pass": abs(last_share - chance) <= 0.05,
        "unaugmented_teacher_position_histogram": original,
        "records_with_identical_copy_orders": identical_orders,
    }


def runtime_projection(training_records: dict[str, list[dict]], samples_per_record: int) -> dict:
    result = {}
    for algorithm, records in training_records.items():
        mean_tokens = sum(r["input_tokens"] for r in records) / len(records)
        samples = len(records) * samples_per_record
        result[algorithm] = {
            "records": len(records),
            "samples": samples,
            "mean_input_tokens": mean_tokens,
            "projected_seconds": samples * BASIS_SECONDS_PER_SAMPLE * mean_tokens / BASIS_MEAN_TOKENS,
        }
    return result


def membership_sha(membership: dict) -> str:
    return sha256_text(
        canonical(
            {
                "training_record_ids": membership["training_record_ids"],
                "diagnostic_record_ids": membership["diagnostic_record_ids"],
            }
        )
    )


def prepare_stage(workers: int = 8) -> dict:
    protocol = load_protocol()
    tasks = eligible_tasks()
    order = [t["task_id"] for t in tasks]
    by_id = {t["task_id"]: t for t in tasks}
    progress = progress_writer()
    derived: dict[str, dict] = {}
    for task in tasks:
        path = derived_path(task["task_id"])
        if path.exists():
            derived[task["task_id"]] = read_json(path)
    dropped: dict[str, str] = {}
    views: dict[str, dict] = {}
    target = RECORD_LADDER[0]
    while True:
        derive_in_walk_order(
            tasks, derived, lambda: not selection_complete(select_records(order, derived, set(dropped), target), target),
            workers, progress,
        )
        for task_id, result in derived.items():
            if len(result["timeouts"]) == len(ALGORITHMS):
                dropped.setdefault(task_id, "derivation_timeout")
        selection = select_records(order, derived, set(dropped), target)
        used = [t for t in order if any(t in s["task_order"] for s in selection.values()) and t not in views]
        from concurrent.futures import ProcessPoolExecutor

        items = []
        for task_id in used:
            last = {}
            for algorithm, chosen in selection.items():
                ids = [rid for rid in chosen["training"] + chosen["diagnostic"] if rid.startswith(task_id + ":")]
                if ids:
                    last[algorithm] = max(int(rid.rsplit(":", 1)[1]) for rid in ids)
            items.append((by_id[task_id], derived[task_id]["episodes"], last))
        with ProcessPoolExecutor(max_workers=min(4, workers)) as pool:
            for task_id, result in zip(used, pool.map(build_task_views, items), strict=True):
                if result["outcome"] != "TRAIN_VIEWS_PASS":
                    dropped[task_id] = "view_render_failed"
                    print(task_id, result["outcome"], result.get("error"), flush=True)
                else:
                    views[task_id] = result
                progress("choice_v3_views", completed=len(views), total=len(used), task=task_id)
        if not any(t in dropped for t in used):
            # views bind the last used decision; re-render if the selection moved
            stale = [
                t for t in views
                if any(t in s["task_order"] for s in selection.values())
                and views[t]["binding"]["last_decision"]
                != {
                    a: max(int(r.rsplit(":", 1)[1]) for r in s["training"] + s["diagnostic"] if r.startswith(t + ":"))
                    for a, s in selection.items()
                    if any(r.startswith(t + ":") for r in s["training"] + s["diagnostic"])
                }
            ]
            if not stale:
                break
            for task_id in stale:
                del views[task_id]
    counts = {a: len(s["training"]) for a, s in selection.items()}
    if min(counts.values()) < MINIMUM_RECORDS:
        raise ValueError(f"choice-frontier v3 corpus below {MINIMUM_RECORDS} records per algorithm: {counts}")

    def records_for(selection_):
        store_records = {}
        for algorithm, chosen in selection_.items():
            for split, ids in (("train", chosen["training"]), ("diagnostic", chosen["diagnostic"])):
                for rid in ids:
                    task_id, _alg, index = rid.rsplit(":", 2)
                    decision = next(
                        d for d in derived[task_id]["episodes"][algorithm]["decisions"]
                        if d["decision_index"] == int(index)
                    )
                    store_records[rid] = build_record(
                        task_id, algorithm, decision, views[task_id], by_id[task_id]["domain"], split
                    )
        return store_records

    store_records = records_for(selection)
    ladder = []
    for rung in RECORD_LADDER:
        trimmed = {
            a: [store_records[r] for r in s["training"][:rung]] for a, s in selection.items()
        }
        projection = runtime_projection(trimmed, AUGMENTATIONS)
        over = any(p["projected_seconds"] > protocol["training"]["max_seconds_per_cell"] for p in projection.values())
        ladder.append({"records": rung, "projection": projection, "exceeds_max_seconds_per_cell": over})
        if not over:
            break
    chosen_target = min(ladder[-1]["records"], min(counts.values()))
    if chosen_target != target:
        # Records are a prefix of the walk; diagnostics are the next 16 in the same walk.
        selection = select_records(order, derived, set(dropped), chosen_target)
        store_records = {rid: rec for rid, rec in records_for(selection).items()}
    used_tasks = sorted({t for s in selection.values() for t in s["task_order"]})
    out = output_root(protocol) / "preparation"
    store = {
        "schema_version": "choice_frontier_v3_store_v1",
        "arm": CHOICE_ARM,
        "recipe_id": CHOICE_RECIPE_ID,
        "trace_gate": "not_applicable_fresh_tasks",
        "tasks": {
            t: {
                "static_pages": views[t]["native_views"]["static_pages"],
                "goal_pages": views[t]["native_views"]["goal_pages"],
                "scenes": views[t]["native_views"]["scenes"],
                "view_id": views[t]["native_views"]["view_id"],
                "episode_sha256": {a: episode_digest(e) for a, e in derived[t]["episodes"].items()},
            }
            for t in used_tasks
        },
        "records": store_records,
    }
    store["counts"] = {
        "records": len(store_records),
        "tasks": len(used_tasks),
        "scenes": sum(len(t["scenes"]) for t in store["tasks"].values()),
    }
    write(out / "store.json", store)
    training = [r for r in store_records.values() if r["split"] == "train"]
    augmentation = augmentation_check(training)
    membership = {
        "schema_version": "choice_frontier_v3_membership_v1",
        "protocol": str(PROTOCOL_PATH),
        "training_tasks": str(TRAINING_TASKS.relative_to(ROOT)),
        "training_tasks_sha256": sha256_file(TRAINING_TASKS),
        "selection_rule": protocol["corpus"]["records_rule"],
        "walk_order": protocol["training_tasks"]["walk_order"],
        "records_per_algorithm": {a: len(s["training"]) for a, s in selection.items()},
        "diagnostic_records_per_algorithm": {a: len(s["diagnostic"]) for a, s in selection.items()},
        "augmentations": AUGMENTATIONS,
        "samples_per_algorithm": {a: AUGMENTATIONS * len(s["training"]) for a, s in selection.items()},
        "record_ladder": ladder,
        "task_order": {a: s["task_order"] for a, s in selection.items()},
        "training_record_ids": {a: s["training"] for a, s in selection.items()},
        "diagnostic_record_ids": {a: s["diagnostic"] for a, s in selection.items()},
    }
    membership["membership_sha256"] = membership_sha(membership)
    write(MEMBERSHIP, membership)
    tokens = [r["input_tokens"] for r in training]
    menus = [r["menu_size"] for r in training]
    per_domain: dict[str, dict[str, int]] = {}
    for record in training:
        per_domain.setdefault(record["algorithm"], {}).setdefault(record["domain"], 0)
        per_domain[record["algorithm"]][record["domain"]] += 1
    report = {
        "schema_version": "choice_frontier_v3_preparation_v1",
        "protocol_id": protocol["protocol_id"],
        "trace_gate": "not_applicable_fresh_tasks",
        "membership_sha256": membership["membership_sha256"],
        "records_per_algorithm": membership["records_per_algorithm"],
        "samples_per_algorithm": membership["samples_per_algorithm"],
        "record_ladder": ladder,
        "counts": store["counts"],
        "tasks_derived": len(derived),
        "tasks_dropped": dropped,
        "overflow_skipped_decisions": sum(
            e["overflow_skipped"] for t in used_tasks for e in derived[t]["episodes"].values()
        ),
        "token_range": {"min": min(tokens), "max": max(tokens), "mean": sum(tokens) / len(tokens)},
        "menu_size_range": {"min": min(menus), "max": max(menus), "mean": sum(menus) / len(menus)},
        "goal_selection_records": sum(1 for r in training if r["status"] == "goal_reached"),
        "records_per_domain": per_domain,
        "augmentation_check": augmentation,
        "outcome": "PASS" if augmentation["pass"] else "AUGMENTATION_CHECK_FAIL",
    }
    write(out / "report.json", report)
    return report


def audit_prepare_stage(workers: int = 8) -> dict:
    """Independent re-derivation of every used episode plus every frozen gate."""

    from concurrent.futures import ProcessPoolExecutor

    protocol = load_protocol()
    out = output_root(protocol) / "preparation"
    store = read_json(out / "store.json")
    membership = read_json(MEMBERSHIP)
    tasks = {t["task_id"]: t for t in read_json(TRAINING_TASKS)["tasks"]}
    task_ids = sorted(store["tasks"])
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rederived = dict(
            zip(task_ids, pool.map(_derive_task, [(t, tasks[t]["task_path"]) for t in task_ids]), strict=True)
        )
    checks = {}
    mismatches = []
    for task_id in task_ids:
        for algorithm, digest in store["tasks"][task_id]["episode_sha256"].items():
            episode = rederived[task_id]["episodes"].get(algorithm)
            if episode is None or episode_digest(episode) != digest:
                mismatches.append((task_id, algorithm, "episode"))
    for rid, record in store["records"].items():
        episode = rederived[record["task_id"]]["episodes"][record["algorithm"]]
        decision = next(d for d in episode["decisions"] if d["decision_index"] == record["decision_index"])
        for field in ("menu", "teacher_choice", "teacher_state_ref", "menu_size", "input_tokens", "status"):
            if decision[field] != record[field]:
                mismatches.append((rid, field))
        if not decision["eligible"]:
            mismatches.append((rid, "eligible"))
    checks["independent_rederivation_bit_exact"] = not mismatches
    checks["token_gate"] = all(r["input_tokens"] + OUTPUT_TOKENS <= CONTEXT_TOKENS for r in store["records"].values())
    checks["images_resolve"] = all(
        (ROOT / store["tasks"][r["task_id"]]["scenes"][str(i)]).is_file()
        for r in store["records"].values()
        for i in r["menu_indices"]
    ) and all(
        (ROOT / page).is_file() for t in store["tasks"].values() for page in t["static_pages"] + t["goal_pages"]
    )
    expected = {
        rid
        for key in ("training_record_ids", "diagnostic_record_ids")
        for ids in membership[key].values()
        for rid in ids
    }
    checks["membership_gate"] = set(store["records"]) == expected and membership_sha(membership) == membership[
        "membership_sha256"
    ]
    checks["teacher_label_binds_state"] = all(
        next(e["choice"] for e in r["menu"] if e["state_ref"] == r["teacher_state_ref"]) == r["teacher_choice"]
        for r in store["records"].values()
    )
    excluded_by = exclusion_hashes()
    overlaps = [
        t
        for t in task_ids
        if tasks[t]["excluded"]
        or sha256_text(read_json(ROOT / tasks[t]["task_path"])["problem_pddl"]) in excluded_by
    ]
    checks["no_overlap_with_135_candidates_panel_or_132_corpus"] = not overlaps
    augmentation = augmentation_check([r for r in store["records"].values() if r["split"] == "train"])
    checks["augmentation_check"] = augmentation["pass"]
    audit = {
        "schema_version": "choice_frontier_v3_prepare_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "trace_gate": "not_applicable_fresh_tasks",
        "checks": checks,
        "mismatches": mismatches[:10],
        "overlaps": overlaps,
        "episodes_rederived": sum(len(r["episodes"]) for r in rederived.values()),
        "augmentation_check": augmentation,
        "outcome": "PASS" if all(checks.values()) else "FAIL",
    }
    write(out / "audit.json", audit)
    return audit


# --------------------------------------------------------------------------- #
# train / audit-train
# --------------------------------------------------------------------------- #


class AugmentedChoiceDataset:
    """Seed-shuffled (record, augmentation) samples over the v3 store."""

    def __init__(self, store: dict, membership: dict, algorithm: str, seed: int, split: str):
        self.store = store
        if split == "train":
            ids = membership["training_record_ids"][algorithm]
            self.samples = [(rid, copy) for rid in ids for copy in range(AUGMENTATIONS)]
            random.Random(f"order:{seed}").shuffle(self.samples)
        else:
            self.samples = [(rid, None) for rid in membership["diagnostic_record_ids"][algorithm]]
        for rid, _copy in self.samples:
            if rid not in store["records"]:
                raise ValueError("choice-frontier v3 dataset record lacks a frozen binding")
        # train_visual reads ``dataset.records`` for the ordered sample ids.
        self.records = [{"record_id": f"{rid}#aug{copy}" if copy is not None else rid} for rid, copy in self.samples]

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        rid, copy = self.samples[index]
        record = self.store["records"][rid]
        task = self.store["tasks"][record["task_id"]]
        if copy is None:
            menu, indices, target = record["menu"], record["menu_indices"], record["teacher_choice"]
        else:
            menu, indices, target = augment_menu(
                rid, record["menu"], record["menu_indices"], record["teacher_state_ref"], copy
            )
        choices = [entry["choice"] for entry in menu]
        payload = choice_payload(
            {
                "algorithm": record["algorithm"],
                "frontier_menu": {"choices": choices},
                "representation": "visual-choice-frontier",
                "schema_version": CHOICE_SCHEMA,
            }
        )

        def loader(label: str, path: str):
            from PIL import Image

            with Image.open(ROOT / path) as stored:
                return stored.convert("RGB")

        example = build_choice_observation(
            payload,
            task["static_pages"],
            task["goal_pages"],
            choices,
            lambda state_index: task["scenes"][str(state_index)],
            indices,
            loader,
        )
        assert_no_text_leak(example)
        if example["binding"]["input_tokens"] != record["input_tokens"]:
            raise ValueError("choice-frontier v3 input tokens differ from the frozen preparation")
        example["messages"].append({"role": "assistant", "content": canonical_choice(target)})
        return example


def cell_dir(protocol: dict, algorithm: str, seed: int) -> Path:
    return output_root(protocol) / "training" / algorithm / f"seed-{seed}"


def train_stage(algorithm: str, seed: int) -> dict:
    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError("choice-frontier training requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("choice-frontier training requires an explicit scheduler MASTER_PORT")
    protocol = load_protocol()
    if algorithm not in protocol["learned_algorithms"] or seed not in protocol["training_seeds"]:
        raise ValueError("choice-frontier v3 cell is not in the frozen protocol")
    training = protocol["training"]
    membership = read_json(MEMBERSHIP)
    if membership_sha(membership) != membership["membership_sha256"]:
        raise ValueError("choice-frontier v3 membership sha differs")
    store = read_json(output_root(protocol) / "preparation" / "store.json")
    progress = progress_writer()

    def factory(root, config, algo, split):
        return AugmentedChoiceDataset(store, membership, algo, seed, split)

    from examples.planning_benchmark_slice.visual_model import train_visual

    study = read_json(ROOT / training["study"])
    if sha256_file(ROOT / training["study"]) != training["study_sha256"]:
        raise ValueError("study-v5 sha differs")
    if (study["model_id"], study["model_revision"]) != (protocol["model_id"], protocol["model_revision"]):
        raise ValueError("study-v5 backbone differs from the frozen protocol")
    config = {**study, "modality": CHOICE_ARM, "training_seed": int(seed)}
    output = cell_dir(protocol, algorithm, seed)
    deadline = time.monotonic() + float(training["max_seconds_per_cell"])
    started = time.monotonic()
    result = train_visual(config, ROOT, algorithm, output, deadline=deadline, progress=progress, dataset_factory=factory)
    result["arm"] = CHOICE_ARM
    result["train_samples"] = result.pop("train_records")
    result["train_records"] = len(membership["training_record_ids"][algorithm])
    result["training_record_ids"] = [*result["training_record_ids"][:8], "..."]
    summary = {
        "schema_version": "choice_frontier_v3_training_v1",
        "protocol_id": protocol["protocol_id"],
        "arm": CHOICE_ARM,
        "algorithm": algorithm,
        "seed": seed,
        "cell": result,
        "wall_seconds": time.monotonic() - started,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": os.environ.get("MASTER_PORT"),
        "outcome": "PASS",
    }
    write(output / "report.json", summary)
    return summary


def audit_cell(protocol: dict, membership: dict, algorithm: str, seed: int) -> dict:
    output = cell_dir(protocol, algorithm, seed)
    report_path = output / "report.json"
    if not report_path.is_file():
        return {"algorithm": algorithm, "seed": seed, "ok": False, "reason": "report missing"}
    cell = read_json(report_path)["cell"]
    checkpoint = output / "final"
    config_file = checkpoint / "adapter_config.json"
    adapter_config = read_json(config_file) if config_file.is_file() else {}
    records = len(membership["training_record_ids"][algorithm])
    samples = records * AUGMENTATIONS
    checks = {
        "adapter_present": (checkpoint / "adapter_model.safetensors").is_file(),
        "r_64": adapter_config.get("r") == 64,
        "alpha_128": adapter_config.get("lora_alpha") == 128,
        "dropout_0_05": adapter_config.get("lora_dropout") == 0.05,
        "steps": cell["steps"] == math.ceil(samples / 32),
        "seed": cell["seed"] == seed,
        "records": cell["train_records"] == records,
        "samples": cell["train_samples"] == samples,
    }
    return {"algorithm": algorithm, "seed": seed, "checks": checks, "ok": all(checks.values())}


def audit_train_stage(algorithm: str | None = None, seed: int | None = None) -> dict:
    protocol = load_protocol()
    membership = read_json(MEMBERSHIP)
    cells = [
        audit_cell(protocol, membership, a, s)
        for a in protocol["learned_algorithms"]
        for s in protocol["training_seeds"]
        if (algorithm is None or a == algorithm) and (seed is None or s == seed)
    ]
    audit = {
        "schema_version": "choice_frontier_v3_train_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "cells": cells,
        "ok": bool(cells) and all(c["ok"] for c in cells),
    }
    name = "audit.json" if algorithm is None else f"audit-{algorithm}-s{seed}.json"
    write(output_root(protocol) / "training" / name, audit)
    return audit


# --------------------------------------------------------------------------- #
# episodes: identity, runner, replay
# --------------------------------------------------------------------------- #


def _identity(protocol: dict, binding: dict, episode: Path, view_output: Path, checkpoint) -> dict:
    return {
        "schema_version": EPISODE_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "binding_index": binding["index"],
        "worker": binding["worker"],
        "kind": binding["kind"],
        "arm": CHOICE_ARM,
        "task_id": binding["task_id"],
        "algorithm": binding["algorithm"],
        "condition": binding["condition"],
        "seed": binding["seed"],
        "training_seed": binding["training_seed"],
        "output": str(episode.relative_to(ROOT)),
        "view_output": str(view_output.relative_to(ROOT)),
        "checkpoint": checkpoint,
        "model_id": protocol["model_id"],
        "model_revision": protocol["model_revision"],
        "oracle_assisted_valid_operation_control": binding["condition"] == "random_valid",
    }


def episode_paths(protocol: dict, binding: dict, *, smoke: bool = False) -> tuple[Path, Path, Path]:
    base = output_root(protocol) / ("smoke" if smoke else "evaluation")
    task_name_ = binding["task_id"].replace("/", "__")
    name = f"{binding['algorithm']}-{binding['condition']}-s{binding['training_seed']}-{binding['seed']}"
    episode = base / "episodes" / task_name_ / f"{name}.json.gz"
    view_output = base / "views" / task_name_ / name
    partial = episode.with_name(episode.name + ".partial.json.gz")
    return episode, partial, view_output


def reference_expansions(task: dict, algorithm: str) -> int:
    return int(task["row"]["reference_costs"][algorithm]["expansions"])


def _session_for(protocol: dict, task: dict, binding: dict, views: ChoiceFrontierTaskViews, checkpoint):
    algorithm = binding["algorithm"]
    choice_task = ChoiceFrontierTask(
        instance_id=task["row"]["task_id"],
        pair_id=task["row"]["task_id"],
        domain=task["row"]["domain"],
        algorithm=algorithm,
        exact_expansions=reference_expansions(task, algorithm),
    )
    decision_cap = BASE_MODEL_CALL_CAP if binding["condition"] == "pretrained_base" else None
    return ChoiceFrontierModelSession(
        authority=views.authority,
        task=choice_task,
        arm={"learned_adapter": "process_sft", "pretrained_base": "pretrained_base"}[binding["condition"]],
        seed=int(binding["seed"]),
        adapter_id=checkpoint,
        decision_cap=decision_cap,
    )


def _register_admissions(session, views, event) -> None:
    result = event["trusted_runtime_result"]
    if result.get("status") != "expanded":
        return
    expanded_state = session.controller._states_by_ref[result["expanded_state_id"]]
    for admission in result["admissions"]:
        views.register(expanded_state, admission["action"])


def _restore_events(session, views, saved) -> None:
    for event in saved["events"]:
        request = session.next_request()
        if request is None or dict(request.model_input) != event["input"]:
            raise ValueError("partial choice-frontier episode replay input differs")
        if [dict(entry) for entry in request.menu_binding] != event["menu"]:
            raise ValueError("partial choice-frontier episode replay menu differs")
        binding = views.observe_choices(dict(request.model_input), session.menu_states(request), pixels=False)[
            "binding"
        ]
        if binding != event["view"]:
            raise ValueError("partial choice-frontier episode replay page binding differs")
        session.submit_output(event["raw_output"])
        committed = session.events[-1]
        if committed["trusted_runtime_result"] != event["trusted_runtime_result"]:
            raise ValueError("partial choice-frontier episode replay runtime result differs")
        committed["view"] = binding
        _register_admissions(session, views, committed)


def _commit_pending(session, views, saved) -> None:
    pending = saved.get("pending")
    if pending is None:
        return
    request = session.next_request()
    if request is None or dict(request.model_input) != pending["input"]:
        raise ValueError("persisted pending choice-frontier output no longer matches the request")
    observed = views.observe_choices(dict(request.model_input), session.menu_states(request), pixels=False)[
        "binding"
    ]
    if observed != pending["binding"]:
        raise ValueError("persisted pending choice-frontier output has a different view binding")
    session.submit_output(pending["raw_output"])
    committed = session.events[-1]
    committed["view"] = observed
    _register_admissions(session, views, committed)
    saved["events"].append(committed)
    saved["call_measurements"].append(pending["measurement"])
    saved["pending"] = None
    views.save()


def run_binding(root, protocol, task, binding, checkpoint, endpoint, generate, *, smoke=False):
    from PIL import Image

    episode, partial_path, view_output = episode_paths(protocol, binding, smoke=smoke)
    expected = _identity(protocol, binding, episode, view_output, checkpoint)
    if episode.exists():
        if partial_path.exists():
            raise ValueError("completed choice-frontier episode retains a conflicting partial journal")
        report = read_json(episode)
        if any(report.get(key) != value for key, value in expected.items()):
            raise ValueError("retained choice-frontier episode binding differs")
        independently_replay(root, protocol, task, report, endpoint, smoke=smoke)
        return report, True
    views = ChoiceFrontierTaskViews(root, task, view_output, endpoint)
    session = _session_for(protocol, task, binding, views, checkpoint)
    saved = (
        read_json(partial_path)
        if partial_path.exists()
        else {
            **expected,
            "decision_cap": session.decision_cap,
            "events": [],
            "call_measurements": [],
            "pending": None,
            "started": time.time(),
            "active_wall_seconds": 0.0,
        }
    )
    if any(saved.get(key) != value for key, value in expected.items()):
        raise ValueError("partial choice-frontier episode binding differs")
    attempt_started = time.monotonic()
    _restore_events(session, views, saved)
    _commit_pending(session, views, saved)
    saved["active_wall_seconds"] += time.monotonic() - attempt_started
    write(partial_path, saved)
    checkpoint_started = time.monotonic()

    while (request := session.next_request()) is not None:
        raw = dict(request.model_input)
        example = views.observe_choices(raw, session.menu_states(request), pixels=True)
        call_started = time.monotonic()
        try:
            generated, generated_tokens = generate(example)
        finally:
            for image in example["images"]:
                if isinstance(image, Image.Image):
                    image.close()
        measurement = {
            "event_index": len(session.events),
            "model_call": True,
            "input_tokens": example["binding"]["input_tokens"],
            "generated_sequence_tokens": generated_tokens,
            "call_wall_seconds": time.monotonic() - call_started,
        }
        saved["pending"] = {
            "input": raw,
            "binding": example["binding"],
            "raw_output": generated,
            "measurement": measurement,
        }
        saved["active_wall_seconds"] += time.monotonic() - checkpoint_started
        write(partial_path, saved)
        checkpoint_started = time.monotonic()
        _commit_pending(session, views, saved)
        saved["active_wall_seconds"] += time.monotonic() - checkpoint_started
        write(partial_path, saved)
        checkpoint_started = time.monotonic()
    report = {
        **expected,
        "decision_cap": session.decision_cap,
        "outcome": "RECORDED",
        "events": saved["events"],
        "result": session.result(),
        "call_measurements": saved["call_measurements"],
        "started": saved["started"],
        "finished": time.time(),
        "active_wall_seconds": saved["active_wall_seconds"] + time.monotonic() - checkpoint_started,
        "raw_invalid_outputs_preserved": sum(
            1 for event in saved["events"] if event["trusted_runtime_result"].get("status") == "rejected"
        ),
    }
    views.save()
    write(episode, report)
    partial_path.unlink()
    return report, False


def independently_replay(root, protocol, task, report, endpoint, *, smoke=False) -> dict:
    binding = {
        "index": report["binding_index"],
        "worker": report["worker"],
        "kind": report["kind"],
        "task_id": report["task_id"],
        "algorithm": report["algorithm"],
        "condition": report["condition"],
        "seed": report["seed"],
        "training_seed": report["training_seed"],
    }
    _episode, _partial, view_output = episode_paths(protocol, binding, smoke=smoke)
    views = ChoiceFrontierTaskViews(root, task, view_output, endpoint, read_only=True)
    session = _session_for(protocol, task, binding, views, report.get("checkpoint"))
    if session.decision_cap != int(report["decision_cap"]):
        raise ValueError("choice-frontier replay decision cap differs")
    for event in report["events"]:
        request = session.next_request()
        if request is None:
            raise ValueError("choice-frontier replay ended before the stored events")
        if dict(request.model_input) != event["input"]:
            raise ValueError("choice-frontier replay input differs")
        if [dict(entry) for entry in request.menu_binding] != event["menu"]:
            raise ValueError("choice-frontier replay menu binding differs")
        observed = views.observe_choices(dict(request.model_input), session.menu_states(request), pixels=False)[
            "binding"
        ]
        if observed != event["view"]:
            raise ValueError("choice-frontier replay view binding differs")
        session.submit_output(event["raw_output"])
        if session.events[-1]["trusted_runtime_result"] != event["trusted_runtime_result"]:
            raise ValueError("choice-frontier replay trusted runtime result differs")
    if session.next_request() is not None:
        raise ValueError("choice-frontier replay continued past the stored events")
    if not session.complete:
        raise ValueError("choice-frontier replay remained incomplete")
    if session.result() != report["result"]:
        raise ValueError("choice-frontier replay result differs")
    return session.result()


def load_policy(protocol: dict, adapters: dict[str, str]):
    from transformers import set_seed

    from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
    from examples.planning_benchmark_slice.visual_model import VisualPolicy

    set_seed(int(protocol["inference_seed"]))
    policy = VisualPolicy(
        model_id=protocol["model_id"],
        revision=protocol["model_revision"],
        adapter_paths={key: ROOT / value for key, value in adapters.items()},
        device="cuda:0",
        max_context_tokens=32768,
        max_new_tokens=384,
        max_batch_size=protocol["inference"]["max_batch_size"],
        max_batch_input_tokens=protocol["inference"]["max_padded_batch_input_tokens"],
        inference_dtype=protocol["inference"]["dtype"],
    )
    configure_visual_attention(policy.model, protocol["inference"]["attention"])
    policy.identity.update(memoize_identical_inputs=False)
    return policy


def adapter_path(protocol: dict, algorithm: str, seed: int) -> str:
    path = cell_dir(protocol, algorithm, seed) / "final"
    if not (path / "adapter_model.safetensors").is_file():
        raise ValueError(f"choice-frontier v3 adapter checkpoint missing: {path}")
    return str(path.relative_to(ROOT))


# --------------------------------------------------------------------------- #
# smoke gate (the #132 definition on the seed-17 v3 adapters)
# --------------------------------------------------------------------------- #


def smoke_tasks(protocol: dict) -> list[dict]:
    from examples.planning_benchmark_slice.expanded_modality_stress import load_panel_tasks

    gate = protocol["smoke_gate"]
    shim = {
        "panel": gate["panel"],
        "panel_view_report": gate["panel_view_report"],
        "panel_id": gate["panel_id"],
        "membership_rule": {"membership": list(gate["subset"])},
    }
    return load_panel_tasks(ROOT, shim)


def smoke_gate(protocol: dict) -> str | None:
    path = output_root(protocol) / "smoke" / "smoke.json"
    return read_json(path)["gate"] if path.is_file() else None


def smoke_bindings(protocol: dict, tasks: list[dict]) -> list[dict]:
    gate = protocol["smoke_gate"]
    rows = []
    for task in tasks:
        for algorithm in protocol["learned_algorithms"]:
            rows.append(
                {
                    "index": len(rows),
                    "worker": 0,
                    "kind": "models",
                    "task_id": task["row"]["task_id"],
                    "algorithm": algorithm,
                    "condition": gate["condition"],
                    "seed": int(gate["seed"]),
                    "training_seed": 17,
                }
            )
    if len(rows) != int(gate["episodes"]):
        raise ValueError("choice-frontier smoke binding count differs from the frozen gate")
    return rows


def smoke_stage(endpoint: str) -> dict:
    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError("choice-frontier smoke requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("choice-frontier smoke requires an explicit scheduler MASTER_PORT")
    protocol = load_protocol()
    if smoke_gate(protocol) is not None:
        raise ValueError("choice-frontier smoke gate already exists; refusing an outcome-selected rerun")
    tasks = smoke_tasks(protocol)
    rows = smoke_bindings(protocol, tasks)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    adapters = {a: adapter_path(protocol, a, 17) for a in protocol["learned_algorithms"]}
    policy = load_policy(protocol, adapters)
    model_calls = 0
    accepted_calls = 0
    episodes = []
    progress = progress_writer()
    for position, binding in enumerate(rows):

        def generate(example, algorithm=binding["algorithm"]):
            nonlocal model_calls
            output = policy.generate([example], algorithm)[0]
            model_calls += 1
            return output, policy.last_generation_usage["generated_sequence_tokens"]

        report, _retained = run_binding(
            ROOT, protocol, task_by_id[binding["task_id"]], binding, adapters[binding["algorithm"]], endpoint,
            generate, smoke=True,
        )
        calls = len(report["events"])
        invalid = report["result"]["invalid_operation_count"]
        accepted_calls += calls - invalid
        episodes.append(
            {
                "task_id": binding["task_id"],
                "algorithm": binding["algorithm"],
                "calls": calls,
                "accepted": calls - invalid,
                "goal_reached": report["result"]["goal_reached"],
                "termination_reason": report["result"]["termination_reason"],
            }
        )
        progress("choice_smoke", completed=position + 1, total=len(rows))
    rate = accepted_calls / model_calls if model_calls else 0.0
    threshold = float(protocol["smoke_gate"]["threshold"])
    result = {
        "schema_version": "choice_frontier_smoke_v1",
        "protocol_id": protocol["protocol_id"],
        "episodes": episodes,
        "model_calls": model_calls,
        "accepted_calls": accepted_calls,
        "schema_valid_grounded_rate": rate,
        "threshold": threshold,
        "gate": "PASS" if rate >= threshold else "FAIL",
    }
    write(output_root(protocol) / "smoke" / "smoke.json", result)
    return result


def audit_smoke_stage(endpoint: str) -> dict:
    protocol = load_protocol()
    report = read_json(output_root(protocol) / "smoke" / "smoke.json")
    tasks = smoke_tasks(protocol)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    replayed = accepted_calls = model_calls = 0
    for binding in smoke_bindings(protocol, tasks):
        episode, _partial, _views = episode_paths(protocol, binding, smoke=True)
        stored = read_json(episode)
        independently_replay(ROOT, protocol, task_by_id[binding["task_id"]], stored, endpoint, smoke=True)
        replayed += 1
        model_calls += len(stored["events"])
        accepted_calls += len(stored["events"]) - stored["result"]["invalid_operation_count"]
    rate = accepted_calls / model_calls if model_calls else 0.0
    threshold = float(protocol["smoke_gate"]["threshold"])
    gate = "PASS" if rate >= threshold else "FAIL"
    audit = {
        "schema_version": "choice_frontier_smoke_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "episodes_replayed": replayed,
        "recomputed_rate": rate,
        "stored_rate": report["schema_valid_grounded_rate"],
        "gate": gate,
        "matches_stored": report["gate"] == gate and abs(rate - report["schema_valid_grounded_rate"]) < 1e-9,
    }
    audit["ok"] = audit["matches_stored"] and replayed == int(protocol["smoke_gate"]["episodes"])
    write(output_root(protocol) / "smoke" / "audit.json", audit)
    return audit


# --------------------------------------------------------------------------- #
# evaluation on the frozen #135 panel
# --------------------------------------------------------------------------- #


def load_tasks(protocol: dict) -> list[dict]:
    frozen = read_json(PANEL_MEMBERSHIP)
    if frozen["membership_sha256"] != protocol["evaluation"]["membership_sha256"]:
        raise ValueError("#135 panel membership_sha256 differs from the frozen protocol")
    recomputed = sha256_text(json.dumps(sorted(frozen["task_ids"]), sort_keys=True, separators=(",", ":")))
    if recomputed != frozen["membership_sha256"]:
        raise ValueError("#135 panel membership does not re-hash to its membership_sha256")
    views = {task["row"]["task_id"]: task for task in read_json(PANEL_VIEW_REPORT)["tasks"]}
    tasks = []
    for index, panel in enumerate(frozen["tasks"]):
        task_id = panel["row"]["task_id"]
        view = views[task_id]
        if view["outcome"] != "REFERENCE_VIEWS_PASS" or view["row"]["task_path"] != panel["row"]["task_path"]:
            raise ValueError(f"#135 native views differ from the frozen panel task: {task_id}")
        # Choice-contract R_t (uncapped exact expansions) comes from the frozen membership row.
        tasks.append({**view, "row": panel["row"], "task_index": index})
    if [task["row"]["task_id"] for task in tasks] != frozen["task_ids"]:
        raise ValueError("#135 task loading differs from the frozen membership")
    return tasks


def bindings(protocol: dict, tasks: list[dict]) -> list[dict]:
    rows = []
    for worker, algorithm in enumerate(protocol["learned_algorithms"]):
        for training_seed in protocol["training_seeds"]:
            for task in tasks:
                rows.append(
                    {
                        "index": len(rows),
                        "worker": worker,
                        "kind": "models",
                        "task_id": task["row"]["task_id"],
                        "algorithm": algorithm,
                        "condition": "learned_adapter",
                        "seed": int(protocol["evaluation"]["seeds"]["learned"][0]),
                        "training_seed": int(training_seed),
                    }
                )
    return rows


def evaluate_inputs_stage() -> dict:
    protocol = load_protocol()
    tasks = load_tasks(protocol)
    rows = bindings(protocol, tasks)
    if len(rows) != protocol["evaluation"]["gpu_episodes"]:
        raise ValueError("choice-frontier v3 evaluation matrix differs from the frozen protocol")
    manifest = {
        "schema_version": "choice_frontier_evaluation_inputs_v1",
        "protocol_id": protocol["protocol_id"],
        "membership_sha256": protocol["evaluation"]["membership_sha256"],
        "bindings": rows,
        "counts": {"models": len(rows)},
    }
    write(output_root(protocol) / "evaluation" / "bindings.json", manifest)
    return manifest


def evaluate_worker(algorithm: str, seed: int, endpoint: str) -> dict:
    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError("choice-frontier model worker requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("choice-frontier model worker requires an explicit scheduler MASTER_PORT")
    protocol = load_protocol()
    tasks = load_tasks(protocol)
    manifest = read_json(output_root(protocol) / "evaluation" / "bindings.json")
    rows = [r for r in manifest["bindings"] if r["algorithm"] == algorithm and r["training_seed"] == seed]
    if len(rows) != len(tasks):
        raise ValueError("choice-frontier v3 worker partition differs from frozen coverage")
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    gate = smoke_gate(protocol)
    if gate is None:
        raise ValueError("choice-frontier evaluation requires the frozen smoke gate")
    if gate == "FAIL":
        result = {"schema_version": "choice_frontier_evaluate_worker_v1", "gated_out_by_smoke": True,
                  "episodes_completed": 0}
        write(attempt_dir / "worker-result.json", result)
        return result
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    checkpoint = adapter_path(protocol, algorithm, seed)
    policy = None
    if any(not episode_paths(protocol, row)[0].exists() for row in rows):
        policy = load_policy(protocol, {algorithm: checkpoint})
    completed = retained = model_calls = 0
    started = time.monotonic()
    reports = []
    for binding in rows:

        def generate(example):
            nonlocal model_calls
            output = policy.generate([example], algorithm)[0]
            model_calls += 1
            return output, policy.last_generation_usage["generated_sequence_tokens"]

        report, was_retained = run_binding(
            ROOT, protocol, task_by_id[binding["task_id"]], binding, checkpoint, endpoint, generate
        )
        retained += int(was_retained)
        reports.append(report["output"])
        completed += 1
        write(
            progress_path,
            {"completed": completed, "total": len(rows), "retained": retained, "model_calls": model_calls,
             "algorithm": algorithm, "training_seed": seed},
        )
    result = {
        "schema_version": "choice_frontier_evaluate_worker_v1",
        "protocol_id": protocol["protocol_id"],
        "algorithm": algorithm,
        "training_seed": seed,
        "episodes_completed": completed,
        "episodes_retained": retained,
        "model_calls": model_calls,
        "elapsed_seconds": time.monotonic() - started,
        "outputs": reports,
    }
    write(attempt_dir / "worker-result.json", result)
    return result


def audit_evaluate_worker() -> dict:
    terminal = read_json(Path(os.environ["EXPANDED_TERMINAL_PATH"]))
    path = Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json"
    result = read_json(path) if path.is_file() else {}
    ok = terminal["status"] == "succeeded" and (
        result.get("episodes_completed", 0) > 0 or result.get("gated_out_by_smoke") is True
    )
    return {"schema_version": "choice_frontier_evaluate_audit_v1", "algorithm": result.get("algorithm"), "ok": ok}


def finalize_stage(endpoint: str) -> dict:
    """Independent replay of every model episode; complete coverage or explicit missingness."""

    protocol = load_protocol()
    tasks = load_tasks(protocol)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    manifest = read_json(output_root(protocol) / "evaluation" / "bindings.json")
    gate = smoke_gate(protocol)
    if gate is None:
        raise ValueError("choice-frontier finalize requires the frozen smoke gate")
    replayed = 0
    missing, mismatches, gated = [], [], []
    cells = {}
    for binding in manifest["bindings"]:
        episode, partial, _views = episode_paths(protocol, binding)
        if not episode.exists():
            (gated if gate == "FAIL" else missing).append(binding["index"])
            continue
        if partial.exists():
            mismatches.append({"index": binding["index"], "error": "partial journal beside completed episode"})
            continue
        report = read_json(episode)
        try:
            independently_replay(ROOT, protocol, task_by_id[binding["task_id"]], report, endpoint)
        except ValueError as error:
            mismatches.append({"index": binding["index"], "error": str(error)})
            continue
        replayed += 1
        key = f"{binding['task_id']}|{binding['algorithm']}|s{binding['training_seed']}"
        cells[key] = report["result"]
    evaluation = {
        "schema_version": "choice_frontier_evaluation_v1",
        "protocol_id": protocol["protocol_id"],
        "episodes_replayed": replayed,
        "bindings_total": len(manifest["bindings"]),
        "missing_bindings": missing,
        "replay_mismatches": mismatches,
        "gated_out_by_smoke": gated,
        "smoke_gate": gate,
        "complete": not missing and not mismatches,
    }
    write(output_root(protocol) / "evaluation" / "evaluation.json", evaluation)
    write(
        output_root(protocol) / "evaluation" / "cells.json",
        {"schema_version": "choice_frontier_cells_v1", "cells": dict(sorted(cells.items()))},
    )
    return evaluation


def validate_stage() -> dict:
    protocol = load_protocol()
    arm = protocol["arms"][CHOICE_ARM]
    checks = {
        "recipe_id": arm["recipe_id"] == CHOICE_RECIPE_ID,
        "schema": arm["schema"] == CHOICE_SCHEMA,
        "legend": arm["legend"] == CHOICE_LEGEND,
        "system_message": arm["system_message"] == CHOICE_SYSTEM_MESSAGE,
        "v1_model_pin": read_json(V1_PROTOCOL)["model_revision"] == protocol["model_revision"],
        "panel_membership_sha": read_json(PANEL_MEMBERSHIP)["membership_sha256"]
        == protocol["evaluation"]["membership_sha256"],
    }
    return {"checks": checks, "ok": all(checks.values())}


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=[
            "validate",
            "generate-train-tasks",
            "prepare",
            "audit-prepare",
            "train",
            "audit-train",
            "smoke",
            "audit-smoke",
            "evaluate-inputs",
            "evaluate-worker",
            "audit-evaluate-worker",
            "finalize",
        ],
    )
    parser.add_argument("--algorithm", choices=list(ALGORITHMS), default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--extend", action="store_true", help="add extension seeds 945100-945299 (once)")
    parser.add_argument("--workers", type=int, default=8, help="CPU parallelism for prepare stages")
    parser.add_argument("--endpoint", default=ENDPOINT)
    args = parser.parse_args(argv)

    if args.stage == "validate":
        result = validate_stage()
    elif args.stage == "generate-train-tasks":
        result = generate_train_tasks_stage(extend=args.extend)
    elif args.stage == "prepare":
        result = prepare_stage(workers=args.workers)
    elif args.stage == "audit-prepare":
        result = audit_prepare_stage(workers=args.workers)
    elif args.stage == "train":
        if args.algorithm is None or args.seed is None:
            raise ValueError("train requires --algorithm and --seed")
        result = train_stage(args.algorithm, args.seed)
    elif args.stage == "audit-train":
        result = audit_train_stage(args.algorithm, args.seed)
    elif args.stage == "smoke":
        result = smoke_stage(args.endpoint)
    elif args.stage == "audit-smoke":
        result = audit_smoke_stage(args.endpoint)
    elif args.stage == "evaluate-inputs":
        result = evaluate_inputs_stage()
    elif args.stage == "evaluate-worker":
        if args.algorithm is None or args.seed is None:
            raise ValueError("evaluate-worker requires --algorithm and --seed")
        result = evaluate_worker(args.algorithm, args.seed, args.endpoint)
    elif args.stage == "audit-evaluate-worker":
        result = audit_evaluate_worker()
    elif args.stage == "finalize":
        result = finalize_stage(args.endpoint)
    else:  # pragma: no cover
        raise ValueError(args.stage)
    print(json.dumps(result, indent=2, sort_keys=True, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
