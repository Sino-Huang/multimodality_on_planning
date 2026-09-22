#!/usr/bin/env python
"""Choice-frontier (#132) preparation, training, evaluation and audit runner.

Stages (all driven by the frozen protocol
``configs/experiments/choice-frontier/choice-frontier-protocol-v1.json``):

- ``validate`` — re-check every sha pin and code/protocol byte-match.
- ``prepare`` — CPU corpus materialization (membership -> store + report).
- ``audit-prepare`` — independent re-derivation of every episode + gates.
- ``train --worker {0,1}`` — one LoRA cell per worker (greedy / w3).
- ``audit-train`` — post-hoc recipe checks.
- ``smoke`` / ``audit-smoke`` — frozen pre-evaluation gate (6 episodes).
- ``evaluate-inputs`` / ``evaluate-worker --worker {0,1} --kind {models,controls}``.
- ``finalize`` — independent replay of every episode + evaluation.json.
- ``identity-audit`` — the pre-registered headroom gate on control episodes.
- ``analyze`` — frozen paired bootstrap contrasts.
- ``audit-final`` — terminal audit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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
)
from examples.planning_benchmark_slice.choice_frontier_corpus import (  # noqa: E402
    ADDITIVE_ALGORITHMS,
    ChoiceFrontierStore,
    ChoiceFrontierTrainingDataset,
    derive_membership,
)
from examples.planning_benchmark_slice.choice_frontier_views import (  # noqa: E402
    CONTEXT_TOKENS,
    FORBIDDEN_USER_TEXT_MARKERS,
    OUTPUT_TOKENS,
    PAYLOAD_KEYS,
    ChoiceFrontierTaskViews,
)
from examples.planning_benchmark_slice.expanded_modality_stress import (  # noqa: E402
    load_panel_tasks as stress_panel_tasks,
)
from examples.planning_benchmark_slice.modality_view_preparation import write_json  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402

PROTOCOL_PATH = Path("configs/experiments/choice-frontier/choice-frontier-protocol-v1.json")
SCHEDULE_PATH = Path("docs/experiments/choice-frontier/schedule.json")
LEDGER_PATH = ROOT / "outputs/choice-frontier/v1/budget.json"
BOOTSTRAP_SEED = 61813
BOOTSTRAP_RESAMPLES = 10000
TINY_STRATUM_LIMIT = 8
BASE_MODEL_CALL_CAP = 1
EPISODE_SCHEMA = "choice_frontier_episode_v1"
ENGINE_ARM = {
    "learned_adapter": "process_sft",
    "pretrained_base": "pretrained_base",
    "random_valid": "random_valid",
    "exact_reference": "exact_reference",
}


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, payload) -> None:
    write_json(path, payload)


def load_protocol() -> dict:
    protocol = read_json(ROOT / PROTOCOL_PATH)
    protocol["root"] = str(ROOT)
    return protocol


def output_root(protocol: dict) -> Path:
    return ROOT / protocol["output_root"]


def progress_writer():
    path = Path(os.environ.get("EXPANDED_PROGRESS_PATH", "/tmp/choice-frontier-progress.json"))

    def progress(stage: str, **fields):
        write(path, {"stage": stage, "updated": time.time(), **fields})

    return progress


def load_tasks(protocol: dict) -> list[dict]:
    evaluation = protocol["evaluation"]
    shim = {
        "panel": evaluation["panel"],
        "panel_view_report": evaluation["panel_view_report"],
        "panel_id": evaluation["panel_id"],
        "membership_rule": {"membership": evaluation["membership"]},
    }
    tasks = stress_panel_tasks(ROOT, shim)
    if len(tasks) != len(evaluation["membership"]):
        raise ValueError("choice-frontier task loading differs from the frozen membership")
    return tasks


def reference_expansions(task: dict, algorithm: str) -> int:
    return int(task["row"]["reference_costs"][algorithm]["expansions"])


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #


def validate_stage() -> dict:
    protocol = load_protocol()
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    corpus = protocol["corpus"]
    check(sha256_file(ROOT / corpus["membership"]) == corpus["membership_sha256"], "membership sha differs")
    check(
        sha256_file(ROOT / corpus["source_membership"]) == corpus["source_membership_sha256"],
        "source membership sha differs",
    )
    check(
        sha256_file(ROOT / protocol["training"]["study"]) == protocol["training"]["study_sha256"],
        "study-v5 sha differs",
    )
    evaluation = protocol["evaluation"]
    check(sha256_file(ROOT / evaluation["panel"]) == evaluation["panel_sha256"], "panel sha differs")
    check(
        sha256_file(ROOT / evaluation["panel_view_report"]) == evaluation["panel_view_report_sha256"],
        "panel view report sha differs",
    )
    recomputed = hashlib.sha256(canonical(sorted(evaluation["membership"])).encode()).hexdigest()
    check(recomputed == evaluation["membership_sha256"], "evaluation membership sha differs")

    arm = protocol["arms"][CHOICE_ARM]
    check(arm["recipe_id"] == CHOICE_RECIPE_ID, "recipe id byte-match differs")
    check(arm["schema"] == CHOICE_SCHEMA, "schema byte-match differs")
    check(arm["legend"] == CHOICE_LEGEND, "legend byte-match differs")
    check(arm["system_message"] == CHOICE_SYSTEM_MESSAGE, "system message byte-match differs")
    check(sorted(arm["payload_keys"]) == sorted(PAYLOAD_KEYS), "payload keys byte-match differs")
    check(
        list(arm["forbidden_user_text_markers"]) == list(FORBIDDEN_USER_TEXT_MARKERS),
        "forbidden markers byte-match differs",
    )
    check(int(arm["context_tokens"]) == CONTEXT_TOKENS, "context tokens byte-match differs")
    check(int(arm["output_tokens"]) == OUTPUT_TOKENS, "output tokens byte-match differs")
    check(protocol["contract"]["menu"]["master_seed"] == 51131, "menu master seed differs")

    membership = read_json(ROOT / corpus["membership"])
    rederived = derive_membership(ROOT, corpus["source_membership"])
    check(rederived == membership, "frozen membership does not re-derive deterministically")
    for algorithm in ADDITIVE_ALGORITHMS:
        check(
            len(membership["training_record_ids"][algorithm])
            == corpus["records_per_algorithm"]
            == 512,
            "membership training count differs",
        )
        check(
            len(membership["diagnostic_record_ids"][algorithm])
            == corpus["diagnostic_records_per_algorithm"]
            == 11,
            "membership diagnostic count differs",
        )
        for record_id in (
            membership["training_record_ids"][algorithm] + membership["diagnostic_record_ids"][algorithm]
        ):
            task_id, rid_algorithm, _index = record_id.split(":")
            check(rid_algorithm == algorithm, "membership record algorithm differs")
            pair_dir = ROOT / corpus["trace_source"] / task_id
            check((pair_dir / "task.json").is_file(), f"membership task missing: {task_id}")
            check((pair_dir / f"{algorithm}.json.gz").is_file(), f"membership trace missing: {task_id}")

    for path in (corpus["corpus_report"], corpus["v5_scene_views"], SCHEDULE_PATH):
        check((ROOT / path).is_file(), f"dependency missing: {path}")
    result = {
        "schema_version": "choice_frontier_validation_v1",
        "protocol_id": protocol["protocol_id"],
        "checks": "all" if not failures else failures,
        "ok": not failures,
    }
    write(output_root(protocol) / "validation.json", result)
    return result


# --------------------------------------------------------------------------- #
# prepare / audit-prepare
# --------------------------------------------------------------------------- #


def _derive_worker(task_id: str, page_counts: tuple[int, int], corpus_row: dict) -> dict:
    from examples.planning_benchmark_slice.choice_frontier_corpus import derive_task_episode

    return {
        algorithm: derive_task_episode(ROOT, task_id, algorithm, page_counts=page_counts, corpus_row=corpus_row)
        for algorithm in ADDITIVE_ALGORITHMS
    }


def prepare_stage(workers: int = 8) -> dict:
    protocol = load_protocol()
    corpus = protocol["corpus"]
    membership = read_json(ROOT / corpus["membership"])
    if sha256_file(ROOT / corpus["membership"]) != corpus["membership_sha256"]:
        raise ValueError("membership sha differs")
    from concurrent.futures import ProcessPoolExecutor

    from examples.planning_benchmark_slice import choice_frontier_corpus as cfc
    from examples.planning_benchmark_slice.native_arm_corpus import _render_states

    v5 = read_json(ROOT / cfc.V5_SCENE_VIEWS)
    corpus_rows = {row["task_id"]: row for row in read_json(ROOT / cfc.CORPUS_REPORT)["results"]}
    algorithms = list(ADDITIVE_ALGORITHMS)
    task_order: list[str] = []
    for algorithm in algorithms:
        for task_id in membership["task_order"][algorithm]:
            if task_id not in task_order:
                task_order.append(task_id)
        for record_id in membership["diagnostic_record_ids"][algorithm]:
            task_id = record_id.split(":")[0]
            if task_id not in task_order:
                task_order.append(task_id)
    out = output_root(protocol) / "preparation" / CHOICE_ARM
    out.mkdir(parents=True, exist_ok=True)
    progress = progress_writer()

    manifests = {task_id: read_json(ROOT / corpus_rows[task_id]["view_manifest"]) for task_id in task_order}
    page_counts = {task_id: cfc._page_counts(ROOT, v5, task_id, manifests[task_id]) for task_id in task_order}
    derived: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_derive_worker, task_id, page_counts[task_id], corpus_rows[task_id]): task_id
            for task_id in task_order
        }
        done = 0
        for future in futures:
            task_id = futures[future]
            derived[task_id] = future.result()
            done += 1
            progress("choice_prepare", completed=done, total=len(task_order), task=task_id)

    store = {
        "schema_version": cfc.STORE_SCHEMA,
        "arm": CHOICE_ARM,
        "recipe_id": CHOICE_RECIPE_ID,
        "study": {
            "corpus_report": cfc.CORPUS_REPORT,
            "v5_scene_views": cfc.V5_SCENE_VIEWS,
            "source_membership": corpus["source_membership"],
            "state_representation": CHOICE_RECIPE_ID,
        },
        "tasks": {},
        "records": {},
        "counts": {},
    }
    needed_scenes = {task_id: {0} for task_id in task_order}
    for task_id in task_order:
        for algorithm in algorithms:
            for decision in derived[task_id][algorithm]["decisions"]:
                needed_scenes[task_id].update(decision["menu_indices"])
    for task_id in task_order:
        manifest = manifests[task_id]
        catalog = read_json(ROOT / manifest["scene_catalog"])
        if task_id in v5["tasks"]:
            v5_task = v5["tasks"][task_id]
            scenes = dict(v5_task["scenes"])
            static_pages = list(v5_task["static_pages"])
            goal_pages = list(v5_task["goal_pages"])
            scene_bindings = dict(v5_task["scene_bindings"])
        else:
            scenes, static_pages, goal_pages, scene_bindings = {}, [], [], {}
            reusable = manifest["reusable_pages"]
            static_pages = list(reusable["task-context"])
            goal_pages = list(reusable["goal"])
        wanted = needed_scenes[task_id]
        missing = wanted - {int(index) for index in scenes}
        if missing:
            rendered = _render_states(ROOT, catalog, manifest, missing, out / "scenes" / task_id)
            scenes.update(rendered)
        unresolved = [index for index in wanted if not (ROOT / scenes[str(index)]).is_file()]
        if unresolved:
            raise ValueError(f"choice-frontier scenes do not resolve: {unresolved[:3]}")
        store["tasks"][task_id] = {
            "source_manifest": corpus_rows[task_id]["view_manifest"],
            "static_pages": static_pages,
            "goal_pages": goal_pages,
            "scenes": scenes,
            "scene_bindings": scene_bindings,
            "view_id": f"choice-frontier/{task_id}",
        }

    from examples.planning_benchmark_slice.choice_frontier_views import (
        assert_no_text_leak,
        build_choice_observation,
        choice_payload,
    )

    for algorithm in algorithms:
        ids = list(membership["training_record_ids"][algorithm]) + list(
            membership["diagnostic_record_ids"][algorithm]
        )
        training_ids = set(membership["training_record_ids"][algorithm])
        for record_id in ids:
            task_id, _algorithm, expansion = record_id.split(":")
            episode = derived[task_id][algorithm]
            decision = episode["decisions"][int(expansion)]
            if decision["status"] != "expanded":
                raise ValueError("choice-frontier membership selects a non-expansion decision")
            task = store["tasks"][task_id]
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
                task["static_pages"],
                task["goal_pages"],
                choices,
                lambda state_index, task=task: task["scenes"][str(state_index)],
                decision["menu_indices"],
            )
            assert_no_text_leak(example)
            if example["binding"]["input_tokens"] != decision["input_tokens"]:
                raise ValueError("choice-frontier store token count differs from derivation")
            store["records"][record_id] = {
                "record_id": record_id,
                "task_id": task_id,
                "domain": episode["domain"],
                "algorithm": algorithm,
                "split": "train" if record_id in training_ids else "diagnostic",
                "expansion_index": int(expansion),
                "menu": decision["menu"],
                "menu_indices": decision["menu_indices"],
                "teacher_choice": decision["teacher_choice"],
                "expanded_state_id": decision["expanded_state_id"],
                "input_tokens": decision["input_tokens"],
                "input_pages": example["binding"]["input_pages"],
                "menu_size": decision["menu_size"],
                "reference_expansions": episode["trace"]["expansion_count"],
            }
    expected_ids = {
        rid
        for algorithm in algorithms
        for rid in list(membership["training_record_ids"][algorithm])
        + list(membership["diagnostic_record_ids"][algorithm])
    }
    if set(store["records"]) != expected_ids:
        raise ValueError("choice-frontier materialized membership differs from the frozen membership")
    store["counts"] = {
        "records": len(store["records"]),
        "tasks": len(store["tasks"]),
        "scenes": sum(len(task["scenes"]) for task in store["tasks"].values()),
        "episodes_verified": len(task_order) * len(algorithms),
    }
    write(out / "store.json", store)
    tokens = [record["input_tokens"] for record in store["records"].values()]
    menus = [record["menu_size"] for record in store["records"].values()]
    report = {
        "schema_version": "choice_frontier_preparation_v1",
        "protocol_id": protocol["protocol_id"],
        "arm": CHOICE_ARM,
        "membership_counts": {
            algorithm: {
                "training": len(membership["training_record_ids"][algorithm]),
                "diagnostic": len(membership["diagnostic_record_ids"][algorithm]),
            }
            for algorithm in algorithms
        },
        "counts": store["counts"],
        "token_range": {"min": min(tokens), "max": max(tokens)},
        "menu_size_range": {"min": min(menus), "max": max(menus)},
        "expansion_gate": "every derived episode matched its stored exact trace expansion for expansion",
        "outcome": "PASS",
    }
    write(out / "report.json", report)
    return report


def audit_prepare_stage(workers: int = 8) -> dict:
    """Independent re-derivation of every corpus episode plus every frozen gate."""

    protocol = load_protocol()
    corpus = protocol["corpus"]
    membership = read_json(ROOT / corpus["membership"])
    from concurrent.futures import ProcessPoolExecutor

    from examples.planning_benchmark_slice import choice_frontier_corpus as cfc

    v5 = read_json(ROOT / cfc.V5_SCENE_VIEWS)
    corpus_rows = {row["task_id"]: row for row in read_json(ROOT / cfc.CORPUS_REPORT)["results"]}
    algorithms = list(ADDITIVE_ALGORITHMS)
    store = read_json(output_root(protocol) / "preparation" / CHOICE_ARM / "store.json")
    if store.get("schema_version") != cfc.STORE_SCHEMA or store.get("arm") != CHOICE_ARM:
        raise ValueError("choice-frontier store schema/arm differs")
    task_order = sorted({record["task_id"] for record in store["records"].values()})
    manifests = {task_id: read_json(ROOT / corpus_rows[task_id]["view_manifest"]) for task_id in task_order}
    page_counts = {task_id: cfc._page_counts(ROOT, v5, task_id, manifests[task_id]) for task_id in task_order}
    derived: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_derive_worker, task_id, page_counts[task_id], corpus_rows[task_id]): task_id
            for task_id in task_order
        }
        for future in futures:
            derived[futures[future]] = future.result()

    checks = {}
    mismatches = []
    for record_id, record in store["records"].items():
        episode = derived[record["task_id"]][record["algorithm"]]
        decision = episode["decisions"][record["expansion_index"]]
        for field in ("menu", "menu_indices", "teacher_choice", "expanded_state_id", "menu_size"):
            if decision[field] != record[field]:
                mismatches.append((record_id, field))
        if decision["input_tokens"] != record["input_tokens"]:
            mismatches.append((record_id, "input_tokens"))
    checks["independent_rederivation_matches"] = not mismatches
    tokens = [record["input_tokens"] for record in store["records"].values()]
    checks["token_gate"] = all(count + OUTPUT_TOKENS <= CONTEXT_TOKENS for count in tokens)
    checks["images_resolve"] = all(
        (ROOT / store["tasks"][record["task_id"]]["scenes"][str(index)]).is_file()
        for record in store["records"].values()
        for index in record["menu_indices"]
    )
    expected_ids = {
        rid
        for algorithm in algorithms
        for rid in list(membership["training_record_ids"][algorithm])
        + list(membership["diagnostic_record_ids"][algorithm])
    }
    checks["membership_gate"] = set(store["records"]) == expected_ids
    headroom = {}
    for task_id in task_order:
        for algorithm in algorithms:
            episode = derived[task_id][algorithm]
            headroom[f"{task_id}:{algorithm}"] = sum(
                1 for decision in episode["decisions"] if decision["menu_size"] >= 2
            )
    checks["headroom_present"] = all(count >= 1 for count in headroom.values())
    audit = {
        "schema_version": "choice_frontier_prepare_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "checks": checks,
        "mismatches": mismatches[:10],
        "headroom_decisions_per_episode": headroom,
        "episodes_rederived": len(task_order) * len(algorithms),
        "outcome": "PASS" if all(checks.values()) else "FAIL",
    }
    write(output_root(protocol) / "preparation" / CHOICE_ARM / "audit.json", audit)
    return audit


# --------------------------------------------------------------------------- #
# train / audit-train
# --------------------------------------------------------------------------- #


def train_stage(worker: int) -> dict:
    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError("choice-frontier training requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("choice-frontier training requires an explicit scheduler MASTER_PORT")
    protocol = load_protocol()
    training = protocol["training"]
    algorithm = protocol["learned_algorithms"][worker]
    membership = read_json(ROOT / protocol["corpus"]["membership"])
    store = ChoiceFrontierStore(ROOT, output_root(protocol) / "preparation" / CHOICE_ARM / "store.json")
    progress = progress_writer()

    def factory(root, config, algo, split):
        return ChoiceFrontierTrainingDataset(root, store, membership, algo, split)

    from examples.planning_benchmark_slice.visual_model import train_visual

    config = {
        **read_json(ROOT / training["study"]),
        "modality": CHOICE_ARM,
        "training_seed": int(protocol["training_seed"]),
    }
    output = output_root(protocol) / "training" / CHOICE_ARM / algorithm
    deadline = time.monotonic() + float(training["max_seconds_per_cell"])
    result = train_visual(
        config,
        ROOT,
        algorithm,
        output,
        deadline=deadline,
        progress=progress,
        dataset_factory=factory,
    )
    result["arm"] = CHOICE_ARM
    summary = {
        "schema_version": "choice_frontier_training_v1",
        "protocol_id": protocol["protocol_id"],
        "arm": CHOICE_ARM,
        "worker": worker,
        "cells": [result],
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": os.environ.get("MASTER_PORT"),
        "outcome": "PASS",
    }
    write(output_root(protocol) / "training" / CHOICE_ARM / f"report-{worker}.json", summary)
    return summary


def audit_train_stage() -> dict:
    protocol = load_protocol()
    ok = True
    cells = []
    for worker, _algorithm in enumerate(protocol["learned_algorithms"]):
        summary_path = output_root(protocol) / "training" / CHOICE_ARM / f"report-{worker}.json"
        if not summary_path.is_file():
            ok = False
            continue
        summary = read_json(summary_path)
        for cell in summary["cells"]:
            checkpoint = output_root(protocol) / "training" / CHOICE_ARM / cell["algorithm"] / "final"
            adapter = checkpoint / "adapter_model.safetensors"
            config_file = checkpoint / "adapter_config.json"
            cell_ok = adapter.is_file() and config_file.is_file()
            adapter_config = read_json(config_file) if config_file.is_file() else {}
            cell_ok = cell_ok and adapter_config.get("r") == 64 and adapter_config.get("lora_alpha") == 128
            cell_ok = cell_ok and cell["steps"] == 16 and cell["seed"] == 17 and cell["train_records"] == 512
            cells.append({"algorithm": cell["algorithm"], "ok": cell_ok})
            ok = ok and cell_ok
    audit = {
        "schema_version": "choice_frontier_train_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "cells": cells,
        "ok": ok,
    }
    write(output_root(protocol) / "training" / CHOICE_ARM / "audit.json", audit)
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
        "output": str(episode.relative_to(ROOT)),
        "view_output": str(view_output.relative_to(ROOT)),
        "checkpoint": checkpoint,
        "model_id": protocol["model_id"],
        "model_revision": protocol["model_revision"],
        "oracle_assisted_valid_operation_control": binding["condition"] == "random_valid",
    }


def episode_paths(protocol: dict, binding: dict, *, smoke: bool = False) -> tuple[Path, Path, Path]:
    base = output_root(protocol) / ("smoke" if smoke else "evaluation")
    task_name = binding["task_id"].replace("/", "__")
    name = f"{binding['algorithm']}-{binding['condition']}-{binding['seed']}"
    episode = base / "episodes" / task_name / f"{name}.json.gz"
    view_output = base / "views" / task_name / name
    partial = episode.with_name(episode.name + ".partial.json.gz")
    return episode, partial, view_output


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
        arm=ENGINE_ARM[binding["condition"]],
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
        binding = views.observe_choices(
            dict(request.model_input), session.menu_states(request), pixels=False
        )["binding"]
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
        example = views.observe_choices(raw, session.menu_states(request), pixels=generate is not None)
        call_started = time.monotonic()
        try:
            if generate is None:
                generated = session.reference_output()
                generated_tokens = None
            else:
                generated, generated_tokens = generate(example)
        finally:
            for image in example["images"]:
                if isinstance(image, Image.Image):
                    image.close()
        measurement = {
            "event_index": len(session.events),
            "model_call": binding["condition"] in {"learned_adapter", "pretrained_base"},
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
    _episode, _partial, view_output = episode_paths(
        protocol,
        {
            "index": report["binding_index"],
            "worker": report["worker"],
            "kind": report["kind"],
            "task_id": report["task_id"],
            "algorithm": report["algorithm"],
            "condition": report["condition"],
            "seed": report["seed"],
        },
        smoke=smoke,
    )
    views = ChoiceFrontierTaskViews(root, task, view_output, endpoint, read_only=True)
    binding = {
        "condition": report["condition"],
        "algorithm": report["algorithm"],
        "seed": report["seed"],
    }
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


# --------------------------------------------------------------------------- #
# smoke gate
# --------------------------------------------------------------------------- #


def smoke_gate(protocol: dict) -> str | None:
    path = output_root(protocol) / "smoke" / "smoke.json"
    if not path.is_file():
        return None
    return read_json(path)["gate"]


def smoke_bindings(protocol: dict, tasks: list[dict]) -> list[dict]:
    gate = protocol["smoke_gate"]
    subset = list(gate["subset"])
    rows = []
    index = 0
    for task in tasks:
        if task["row"]["task_id"] not in subset:
            continue
        for algorithm in protocol["learned_algorithms"]:
            rows.append(
                {
                    "index": index,
                    "worker": 0,
                    "kind": "models",
                    "task_id": task["row"]["task_id"],
                    "algorithm": algorithm,
                    "condition": gate["condition"],
                    "seed": int(gate["seed"]),
                }
            )
            index += 1
    if len(rows) != int(gate["episodes"]):
        raise ValueError("choice-frontier smoke binding count differs from the frozen gate")
    return rows


def smoke_stage(endpoint: str) -> dict:
    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError("choice-frontier smoke requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("choice-frontier smoke requires an explicit scheduler MASTER_PORT")
    protocol = load_protocol()
    gate = smoke_gate(protocol)
    if gate is not None:
        raise ValueError("choice-frontier smoke gate already exists; refusing an outcome-selected rerun")
    tasks = load_tasks(protocol)
    rows = smoke_bindings(protocol, tasks)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    adapters = {
        algorithm: str(output_root(protocol) / "training" / CHOICE_ARM / algorithm / "final")
        for algorithm in protocol["learned_algorithms"]
    }
    for path in adapters.values():
        if not (ROOT / path / "adapter_model.safetensors").is_file():
            raise ValueError(f"choice-frontier adapter checkpoint missing: {path}")
    from transformers import set_seed

    from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
    from examples.planning_benchmark_slice.visual_model import VisualPolicy

    set_seed(int(protocol["training_seed"]))
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
    model_calls = 0
    accepted_calls = 0
    episodes = []
    progress = progress_writer()
    for position, binding in enumerate(rows):
        checkpoint = adapters[binding["algorithm"]]

        def generate(example, algorithm=binding["algorithm"]):
            nonlocal model_calls
            output = policy.generate([example], algorithm)[0]
            model_calls += 1
            return output, policy.last_generation_usage["generated_sequence_tokens"]

        report, _retained = run_binding(
            ROOT, protocol, task_by_id[binding["task_id"]], binding, checkpoint, endpoint, generate, smoke=True
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
    tasks = load_tasks(protocol)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    rows = smoke_bindings(protocol, tasks)
    replayed = 0
    accepted_calls = 0
    model_calls = 0
    for binding in rows:
        episode, _partial, _views = episode_paths(protocol, binding, smoke=True)
        stored = read_json(episode)
        independently_replay(ROOT, protocol, task_by_id[binding["task_id"]], stored, endpoint, smoke=True)
        replayed += 1
        model_calls += len(stored["events"])
        accepted_calls += len(stored["events"]) - stored["result"]["invalid_operation_count"]
    rate = accepted_calls / model_calls if model_calls else 0.0
    threshold = float(protocol["smoke_gate"]["threshold"])
    audit = {
        "schema_version": "choice_frontier_smoke_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "episodes_replayed": replayed,
        "recomputed_rate": rate,
        "stored_rate": report["schema_valid_grounded_rate"],
        "gate": "PASS" if rate >= threshold else "FAIL",
        "matches_stored": report["gate"] == ("PASS" if rate >= threshold else "FAIL")
        and abs(rate - report["schema_valid_grounded_rate"]) < 1e-9,
    }
    audit["ok"] = audit["matches_stored"] and replayed == int(protocol["smoke_gate"]["episodes"])
    write(output_root(protocol) / "smoke" / "audit.json", audit)
    return audit


# --------------------------------------------------------------------------- #
# evaluation
# --------------------------------------------------------------------------- #


def bindings(protocol: dict, tasks: list[dict]) -> list[dict]:
    rows = []
    index = 0
    seeds = protocol["evaluation"]["seeds"]
    for task in tasks:
        for algorithm in protocol["learned_algorithms"]:
            for condition in ("learned_adapter", "pretrained_base"):
                rows.append(
                    {
                        "index": index,
                        "worker": index % 2,
                        "kind": "models",
                        "task_id": task["row"]["task_id"],
                        "algorithm": algorithm,
                        "condition": condition,
                        "seed": int(seeds["learned"][0]),
                    }
                )
                index += 1
    for task in tasks:
        for algorithm in protocol["learned_algorithms"]:
            for seed in seeds["random_valid"]:
                rows.append(
                    {
                        "index": index,
                        "worker": index % 2,
                        "kind": "controls",
                        "task_id": task["row"]["task_id"],
                        "algorithm": algorithm,
                        "condition": "random_valid",
                        "seed": int(seed),
                    }
                )
                index += 1
            rows.append(
                {
                    "index": index,
                    "worker": index % 2,
                    "kind": "controls",
                    "task_id": task["row"]["task_id"],
                    "algorithm": algorithm,
                    "condition": "exact_reference",
                    "seed": int(seeds["exact_reference"][0]),
                }
            )
            index += 1
    return rows


def evaluate_inputs_stage() -> dict:
    protocol = load_protocol()
    tasks = load_tasks(protocol)
    rows = bindings(protocol, tasks)
    manifest = {
        "schema_version": "choice_frontier_evaluation_inputs_v1",
        "protocol_id": protocol["protocol_id"],
        "bindings": rows,
        "counts": {
            "models": sum(1 for row in rows if row["kind"] == "models"),
            "controls": sum(1 for row in rows if row["kind"] == "controls"),
        },
    }
    expected = protocol["evaluation"]
    if manifest["counts"]["models"] != expected["gpu_episodes"] or manifest["counts"]["controls"] != expected[
        "cpu_control_episodes"
    ]:
        raise ValueError("choice-frontier evaluation matrix differs from the frozen protocol")
    write(output_root(protocol) / "evaluation" / "bindings.json", manifest)
    return manifest


def evaluate_worker(worker: int, kind: str, endpoint: str) -> dict:
    protocol = load_protocol()
    tasks = load_tasks(protocol)
    manifest = read_json(output_root(protocol) / "evaluation" / "bindings.json")
    rows = [row for row in manifest["bindings"] if row["worker"] == worker and row["kind"] == kind]
    expected = sum(1 for row in manifest["bindings"] if row["kind"] == kind) // 2
    if len(rows) != expected:
        raise ValueError("choice-frontier worker partition differs from frozen equal coverage")
    if kind == "models":
        if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
            raise ValueError("choice-frontier model worker requires CUDA_VISIBLE_DEVICES isolation")
        if not os.environ.get("MASTER_PORT"):
            raise ValueError("choice-frontier model worker requires an explicit scheduler MASTER_PORT")
        gate = smoke_gate(protocol)
        if gate is None:
            raise ValueError("choice-frontier evaluation requires the frozen smoke gate")
        if gate == "FAIL":
            result = {
                "schema_version": "choice_frontier_evaluate_worker_v1",
                "worker": worker,
                "kind": kind,
                "gated_out_by_smoke": True,
                "episodes_completed": 0,
            }
            write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json", result)
            return result
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    completed = 0
    retained = 0
    model_calls = 0
    started = time.monotonic()
    adapters = {}
    policy = None
    if kind == "models":
        adapters = {
            algorithm: str(output_root(protocol) / "training" / CHOICE_ARM / algorithm / "final")
            for algorithm in protocol["learned_algorithms"]
        }
        for path in adapters.values():
            if not (ROOT / path / "adapter_model.safetensors").is_file():
                raise ValueError(f"choice-frontier adapter checkpoint missing: {path}")
        pending = [row for row in rows if not episode_paths(protocol, row)[0].exists()]
        if pending:
            from transformers import set_seed

            from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
            from examples.planning_benchmark_slice.visual_model import VisualPolicy

            set_seed(int(protocol["training_seed"]))
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
    reports = []
    for binding in rows:
        condition = binding["condition"]
        checkpoint = adapters.get(binding["algorithm"]) if condition == "learned_adapter" else None

        def generate(example, condition=condition, algorithm=binding["algorithm"]):
            nonlocal model_calls
            adapter = algorithm if condition == "learned_adapter" else None
            output = policy.generate([example], adapter)[0]
            model_calls += 1
            return output, policy.last_generation_usage["generated_sequence_tokens"]

        generate_fn = generate if kind == "models" else None
        report, was_retained = run_binding(
            ROOT,
            protocol,
            task_by_id[binding["task_id"]],
            binding,
            checkpoint,
            endpoint,
            generate_fn,
        )
        retained += int(was_retained)
        reports.append(report["output"])
        completed += 1
        write(
            progress_path,
            {
                "completed": completed,
                "total": len(rows),
                "retained": retained,
                "model_calls": model_calls,
                "worker": worker,
                "kind": kind,
            },
        )
    if policy is not None:
        import torch

        del policy
        torch.cuda.empty_cache()
    result = {
        "schema_version": "choice_frontier_evaluate_worker_v1",
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "kind": kind,
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
    result = read_json(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json")
    ok = terminal["status"] == "succeeded" and (
        result.get("episodes_completed", 0) > 0 or result.get("gated_out_by_smoke") is True
    )
    return {
        "schema_version": "choice_frontier_evaluate_audit_v1",
        "worker": result.get("worker"),
        "kind": result.get("kind"),
        "ok": ok,
    }


# --------------------------------------------------------------------------- #
# finalize / identity-audit / analyze
# --------------------------------------------------------------------------- #


def _load_episode(protocol: dict, binding: dict) -> dict:
    episode, _partial, _views = episode_paths(protocol, binding)
    return read_json(episode)


def finalize_stage(endpoint: str) -> dict:
    """Independent replay of every episode; complete coverage or explicit missingness."""

    protocol = load_protocol()
    tasks = load_tasks(protocol)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    manifest = read_json(output_root(protocol) / "evaluation" / "bindings.json")
    gate = smoke_gate(protocol)
    if gate is None:
        raise ValueError("choice-frontier finalize requires the frozen smoke gate")
    replayed = 0
    missing = []
    gated = []
    cells = {}
    for binding in manifest["bindings"]:
        episode, partial, _views = episode_paths(protocol, binding)
        if not episode.exists():
            if binding["kind"] == "models" and gate == "FAIL":
                gated.append(binding["index"])
                continue
            missing.append(binding["index"])
            continue
        if partial.exists():
            raise ValueError("choice-frontier finalize found a partial journal beside a completed episode")
        report = read_json(episode)
        independently_replay(ROOT, protocol, task_by_id[binding["task_id"]], report, endpoint)
        replayed += 1
        key = (binding["task_id"], binding["algorithm"])
        cell = cells.setdefault(key, {})
        if binding["condition"] == "random_valid":
            cell.setdefault("random_valid", {})[str(binding["seed"])] = report["result"]
        else:
            cell[binding["condition"]] = report["result"]
    evaluation = {
        "schema_version": "choice_frontier_evaluation_v1",
        "protocol_id": protocol["protocol_id"],
        "episodes_replayed": replayed,
        "bindings_total": len(manifest["bindings"]),
        "missing_bindings": missing,
        "gated_out_by_smoke": gated,
        "smoke_gate": gate,
        "complete": not missing,
    }
    write(output_root(protocol) / "evaluation" / "evaluation.json", evaluation)
    serialized = {
        f"{task_id}|{algorithm}": cell
        for (task_id, algorithm), cell in sorted(cells.items())
    }
    write(
        output_root(protocol) / "evaluation" / "cells.json",
        {"schema_version": "choice_frontier_cells_v1", "cells": serialized},
    )
    return evaluation


def identity_audit_stage() -> dict:
    """Pre-registered gate: random_valid must differ from exact_reference here."""

    protocol = load_protocol()
    evaluation = read_json(output_root(protocol) / "evaluation" / "evaluation.json")
    if not evaluation["complete"]:
        raise ValueError("choice-frontier identity audit requires complete evaluation coverage")
    cells = read_json(output_root(protocol) / "evaluation" / "cells.json")["cells"]
    pairs = []
    divergent = 0
    for key, cell in sorted(cells.items()):
        exact = cell.get("exact_reference")
        random17 = (cell.get("random_valid") or {}).get("17")
        if exact is None or random17 is None:
            pairs.append({"cell": key, "status": "missing"})
            continue
        same = (
            exact["decision_count"] == random17["decision_count"]
            and exact["expansion_count"] == random17["expansion_count"]
            and exact["termination_reason"] == random17["termination_reason"]
        )
        divergent += int(not same)
        pairs.append(
            {
                "cell": key,
                "status": "identical" if same else "divergent",
                "exact": {
                    "decisions": exact["decision_count"],
                    "expansions": exact["expansion_count"],
                    "goal_reached": exact["goal_reached"],
                    "termination": exact["termination_reason"],
                },
                "random_valid_seed17": {
                    "decisions": random17["decision_count"],
                    "expansions": random17["expansion_count"],
                    "goal_reached": random17["goal_reached"],
                    "termination": random17["termination_reason"],
                },
            }
        )
    checked = sum(1 for pair in pairs if pair["status"] != "missing")
    verdict = (
        "CHOICE_SENSITIVE"
        if checked and divergent >= 1
        else "ZERO_DECISION_HEADROOM"
    )
    audit = {
        "schema_version": "choice_frontier_identity_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "pairs_checked": checked,
        "pairs_divergent": divergent,
        "pairs": pairs,
        "verdict": verdict,
        "basis": (
            "the policy selects which live frontier state the trusted runtime expands next; "
            "random_valid (uniform menu choice) and exact_reference (heap head) diverge whenever "
            "a decision sees a frontier of size >= 2"
        ),
        "pre_registered": True,
    }
    write(output_root(protocol) / "evaluation" / "identity-audit.json", audit)
    return audit


def bootstrap_delta(differences: list[float]) -> dict:
    import random

    resamples = BOOTSTRAP_RESAMPLES
    generator = random.Random(BOOTSTRAP_SEED)
    count = len(differences)
    means = []
    for _ in range(resamples):
        means.append(sum(generator.choice(differences) for _ in range(count)) / count)
    means.sort()
    low = means[int(0.025 * resamples)]
    high = means[int(0.975 * resamples) - 1]
    return {
        "cells": count,
        "mean": sum(differences) / count,
        "ci95": [low, high],
        "material": low > 0 or high < 0,
        "descriptive_only": count < TINY_STRATUM_LIMIT,
    }


def _success(result: dict) -> float:
    return 1.0 if result["invariant_valid_success"] else 0.0


def analyze_stage() -> dict:
    protocol = load_protocol()
    cells = read_json(output_root(protocol) / "evaluation" / "cells.json")["cells"]
    learned_base = []
    learned_random = []
    random_exact = []
    per_cell = {}
    for key, cell in sorted(cells.items()):
        learned = cell.get("learned_adapter")
        base = cell.get("pretrained_base")
        exact = cell.get("exact_reference")
        randoms = list((cell.get("random_valid") or {}).values())
        random_frequency = sum(_success(r) for r in randoms) / len(randoms) if randoms else None
        row = {
            "learned": _success(learned) if learned else None,
            "base": _success(base) if base else None,
            "random_valid_frequency": random_frequency,
            "exact": _success(exact) if exact else None,
            "learned_decisions": learned["decision_count"] if learned else None,
            "random_decisions_seed17": (cell.get("random_valid") or {}).get("17", {}).get("decision_count"),
            "exact_decisions": exact["decision_count"] if exact else None,
        }
        per_cell[key] = row
        if learned is not None and base is not None:
            learned_base.append(_success(learned) - _success(base))
        if learned is not None and random_frequency is not None:
            learned_random.append(_success(learned) - random_frequency)
        if random_frequency is not None and exact is not None:
            random_exact.append(random_frequency - _success(exact))
    analysis = {
        "schema_version": "choice_frontier_analysis_v1",
        "protocol_id": protocol["protocol_id"],
        "bootstrap": {
            "seed": BOOTSTRAP_SEED,
            "resamples": BOOTSTRAP_RESAMPLES,
            "confidence": 0.95,
            "interval": "percentile",
            "materiality": "interval excludes 0",
            "tiny_subgroup_rule": f"strata with < {TINY_STRATUM_LIMIT} cells are descriptive-only",
        },
        "contrasts": {
            "learned_minus_pretrained_base": bootstrap_delta(learned_base) if learned_base else None,
            "learned_minus_random_valid": bootstrap_delta(learned_random) if learned_random else None,
            "random_valid_minus_exact_reference": bootstrap_delta(random_exact) if random_exact else None,
        },
        "cells": per_cell,
    }
    write(output_root(protocol) / "evaluation" / "analysis.json", analysis)
    return analysis


def audit_final_stage() -> dict:
    protocol = load_protocol()
    evaluation = read_json(output_root(protocol) / "evaluation" / "evaluation.json")
    audit = read_json(output_root(protocol) / "evaluation" / "identity-audit.json")
    analysis = read_json(output_root(protocol) / "evaluation" / "analysis.json")
    ok = (
        evaluation["complete"] is True
        and evaluation["episodes_replayed"] + len(evaluation["gated_out_by_smoke"]) == evaluation["bindings_total"]
        and audit["pairs_checked"] == 18
        and analysis["contrasts"]["learned_minus_pretrained_base"] is not None
    )
    result = {
        "schema_version": "choice_frontier_final_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "episodes_replayed": evaluation["episodes_replayed"],
        "identity_audit_verdict": audit["verdict"],
        "ok": ok,
    }
    write(output_root(protocol) / "evaluation" / "final-audit.json", result)
    return result


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=[
            "validate",
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
            "identity-audit",
            "analyze",
            "audit-final",
        ],
    )
    parser.add_argument("--worker", type=int, choices=[0, 1], default=None)
    parser.add_argument("--kind", choices=["models", "controls"], default=None)
    parser.add_argument("--workers", type=int, default=8, help="CPU parallelism for prepare stages")
    parser.add_argument("--endpoint", default="http://127.0.0.1:18092")
    args = parser.parse_args(argv)

    if args.stage == "validate":
        result = validate_stage()
    elif args.stage == "prepare":
        result = prepare_stage(workers=args.workers)
    elif args.stage == "audit-prepare":
        result = audit_prepare_stage(workers=args.workers)
    elif args.stage == "train":
        if args.worker is None:
            raise ValueError("train requires --worker {0,1}")
        result = train_stage(args.worker)
    elif args.stage == "audit-train":
        result = audit_train_stage()
    elif args.stage == "smoke":
        result = smoke_stage(args.endpoint)
    elif args.stage == "audit-smoke":
        result = audit_smoke_stage(args.endpoint)
    elif args.stage == "evaluate-inputs":
        result = evaluate_inputs_stage()
    elif args.stage == "evaluate-worker":
        if args.worker is None or args.kind is None:
            raise ValueError("evaluate-worker requires --worker {0,1} --kind {models,controls}")
        result = evaluate_worker(args.worker, args.kind, args.endpoint)
    elif args.stage == "audit-evaluate-worker":
        result = audit_evaluate_worker()
    elif args.stage == "finalize":
        result = finalize_stage(args.endpoint)
    elif args.stage == "identity-audit":
        result = identity_audit_stage()
    elif args.stage == "analyze":
        result = analyze_stage()
    elif args.stage == "audit-final":
        result = audit_final_stage()
    else:  # pragma: no cover
        raise ValueError(args.stage)
    print(json.dumps(result, indent=2, sort_keys=True, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
