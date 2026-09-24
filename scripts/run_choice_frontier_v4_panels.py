#!/usr/bin/env python
"""Choice-frontier v4 (#139) 3-seed adapter evaluation on the fresh held-out panels.

Copy of ``scripts/run_choice_frontier_v2.py`` (#135) with ``--panel {p2,p2u}``
(docs/experiments/choice-frontier/issue-139-protocol.md). Changed: membership
(``configs/experiments/choice-frontier-v4/membership-<panel>.json``), output root
``outputs/choice-frontier/v4/panels/<panel>`` (views are shared under
``outputs/choice-frontier/v4/panels/views``), the shared v4 ledger/schedule, and the
bindings: per task and algorithm, ``learned_adapter`` for training seeds 17 (#136,
``outputs/choice-frontier/v3/training``) and 29/71 (#138,
``outputs/choice-frontier/v4/seeds/training``) plus ``pretrained_base``. Model and
inference settings are the frozen #136 protocol (greedy, inference seed 17); the
base keeps its frozen 1-call cap; learned cap 2 x R_t.

Stages:

- ``prepare-views --panel P`` — native reference traces + planimation scene-only views
  for the frozen panel tasks (the #135 recipe; CPU, render backend).
- ``evaluate-inputs --panel P`` / ``evaluate-worker --panel P --algorithm A`` (one job
  per panel x algorithm: every training seed present + base, all panel tasks).
- ``audit-evaluate-worker`` — completion hook (attempt dir = terminal path's parent,
  the #136 fix).
- ``finalize --panel P`` — independent replay of every model episode.
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
    ChoiceFrontierModelSession,
    ChoiceFrontierTask,
)
from examples.planning_benchmark_slice.choice_frontier_views import ChoiceFrontierTaskViews  # noqa: E402
from examples.planning_benchmark_slice.modality_view_preparation import write_json  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402

V3_PROTOCOL_PATH = Path("configs/experiments/choice-frontier-v3/protocol.json")
CONFIG = ROOT / "configs/experiments/choice-frontier-v4"
SCHEDULE_PATH = Path("docs/experiments/choice-frontier/schedule-v4.json")
LEDGER_PATH = ROOT / "outputs/choice-frontier/v4/budget.json"
PANELS_ROOT = "outputs/choice-frontier/v4/panels"
PANELS = ("p2", "p2u")
TRAINING_SEEDS = (17, 29, 71)
ALGORITHMS = ("best_first_add_greedy", "best_first_add_w3")
# Only the two evaluated additive cells (the #135 recipe): the reference traces only
# seed the state catalog (unseen states are rendered live).
VIEW_ALGORITHMS = ("best_first_add_w3", "best_first_add_greedy")
VIEW_ENDPOINT_INDEX = 0  # prepare_task renders at 18092 + index % 4; only 18092 is required
BASE_MODEL_CALL_CAP = 1
EPISODE_SCHEMA = "choice_frontier_episode_v1"
ENGINE_ARM = {"learned_adapter": "process_sft", "pretrained_base": "pretrained_base"}


def adapter_dir(algorithm: str, training_seed: int) -> Path:
    if training_seed == 17:
        return ROOT / "outputs/choice-frontier/v3/training" / algorithm / "seed-17" / "final"
    return ROOT / "outputs/choice-frontier/v4/seeds/training" / algorithm / f"seed-{training_seed}" / "final"


def smoke_path(training_seed: int) -> Path:
    """#136 smoke gate for seed 17; the #138 gate (run on seed 29) for seeds 29/71."""

    if training_seed == 17:
        return ROOT / "outputs/choice-frontier/v3/smoke/smoke.json"
    return ROOT / "outputs/choice-frontier/v4/seeds/smoke/smoke.json"


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, payload) -> None:
    write_json(path, payload)


def load_protocol(panel: str) -> dict:
    """Frozen #136 protocol (model, inference) with only the v4 identity and paths replaced."""

    if panel not in PANELS:
        raise ValueError(panel)
    protocol = read_json(ROOT / V3_PROTOCOL_PATH)
    protocol["root"] = str(ROOT)
    protocol["protocol_id"] = f"choice-frontier-v4-panels-{panel}"
    protocol["panel"] = panel
    protocol["output_root"] = f"{PANELS_ROOT}/{panel}"
    protocol["ledger"] = str(LEDGER_PATH.relative_to(ROOT))
    protocol["schedule"] = str(SCHEDULE_PATH)
    return protocol


def output_root(protocol: dict) -> Path:
    return ROOT / protocol["output_root"]


def progress_writer():
    path = Path(os.environ.get("EXPANDED_PROGRESS_PATH", "/tmp/choice-frontier-progress.json"))

    def progress(stage: str, **fields):
        write(path, {"stage": stage, "updated": time.time(), **fields})

    return progress


def membership(panel: str) -> dict:
    frozen = read_json(CONFIG / f"membership-{panel}.json")
    recomputed = hashlib.sha256(
        json.dumps(sorted(frozen["task_ids"]), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if recomputed != frozen["membership_sha256"]:
        raise ValueError(f"v4 {panel} membership does not re-hash to its membership_sha256")
    return frozen


def view_report(panel: str) -> Path:
    return ROOT / PANELS_ROOT / panel / "reference-views.json"


def load_tasks(protocol: dict) -> list[dict]:
    frozen = membership(protocol["panel"])
    views = {task["row"]["task_id"]: task for task in read_json(view_report(protocol["panel"]))["tasks"]}
    tasks = []
    for index, panel in enumerate(frozen["tasks"]):
        task_id = panel["row"]["task_id"]
        view = views[task_id]
        if view["outcome"] != "REFERENCE_VIEWS_PASS" or view["row"]["task_path"] != panel["row"]["task_path"]:
            raise ValueError(f"v4 native views differ from the frozen panel task: {task_id}")
        # Choice-contract reference costs (R_t) come from the frozen membership row.
        tasks.append({**view, "row": panel["row"], "task_index": index})
    if [task["row"]["task_id"] for task in tasks] != frozen["task_ids"]:
        raise ValueError("choice-frontier v4 task loading differs from the frozen membership")
    return tasks


def reference_expansions(task: dict, algorithm: str) -> int:
    return int(task["row"]["reference_costs"][algorithm]["expansions"])


# --------------------------------------------------------------------------- #
# prepare-views: native reference traces + scene-only views (CPU, render backend)
# --------------------------------------------------------------------------- #


def _view_task(item: tuple[dict, dict]) -> dict:
    from examples.planning_benchmark_slice.matched_tasks import exact_reference
    from scripts.prepare_expanded_views import prepare_task

    protocol, panel_row = item
    name = panel_row["task_id"].split("/", 1)[1]
    domain, _stratum, seed = name.rsplit("-", 2)
    candidate = ROOT / protocol["output_root"] / "candidates" / name
    # Native exact references under the expanded-study screening ceilings, then
    # re-bound to the resulting per-instance budgets (expanded_candidates.screen);
    # the views renderer replays them to seed the reference state catalog.
    ceiling = {**panel_row, "reference_costs": {a: {"decisions": 256, "expansions": 128} for a in VIEW_ALGORITHMS}}
    study = {"output_root": protocol["output_root"], "study_id": protocol["study_id"],
             "final": {"max_exact_decisions_per_algorithm": 256}}
    native = {}
    for algorithm in VIEW_ALGORITHMS:
        result = exact_reference(ROOT, ceiling, algorithm, study)["result"]
        native[algorithm] = {"decisions": result["decision_count"], "expansions": result["expansion_count"]}
    for algorithm in ("best_first_add_greedy", "best_first_add_w3"):
        if native[algorithm]["expansions"] != panel_row["reference_costs"][algorithm]["expansions"]:
            raise ValueError(f"native exact expansions differ from choice-contract R: {name} {algorithm}")
    row = {**panel_row, "reference_costs": native}
    for algorithm in VIEW_ALGORITHMS:
        path = candidate / f"reference-{algorithm}.json.gz"
        if not path.exists():
            write(path, exact_reference(ROOT, row, algorithm, study))
    group = {"domain": domain, "stratum": "expanded", "selected": {"seed": int(seed), "row": row}}
    return prepare_task(protocol, group, VIEW_ENDPOINT_INDEX)


def prepare_views_stage(panel: str, workers: int = 4) -> dict:
    from concurrent.futures import ProcessPoolExecutor

    frozen = membership(panel)
    # Views and native references are shared under PANELS_ROOT (candidates live there; panels are disjoint).
    protocol = {
        "study_id": "choice-frontier-v4-panels-views",
        "output_root": PANELS_ROOT,
        "reference": {"algorithms": list(VIEW_ALGORITHMS)},
        "panel": panel,
        "membership_sha256": frozen["membership_sha256"],
    }
    rows = [task["row"] for task in frozen["tasks"]]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        tasks = list(pool.map(_view_task, [(protocol, row) for row in rows]))
    write(view_report(panel), {"protocol": protocol, "tasks": tasks, "complete_live_input_bounds": False,
                               "hardware_qualified": False})
    return {"tasks": len(tasks), "outcomes": sorted({t["outcome"] for t in tasks})}


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
    task_name = binding["task_id"].replace("/", "__")
    trained = "base" if binding["training_seed"] is None else f"s{binding['training_seed']}"
    name = f"{binding['algorithm']}-{binding['condition']}-{trained}-{binding['seed']}"
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
            "training_seed": report["training_seed"],
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
# smoke gates and adapters
# --------------------------------------------------------------------------- #


def smoke_gate(training_seed: int) -> str | None:
    path = smoke_path(training_seed)
    return read_json(path)["gate"] if path.is_file() else None


def available_training_seeds() -> list[int]:
    """Training seeds whose adapters exist for both algorithms and whose smoke gate passed."""

    seeds = []
    for seed in TRAINING_SEEDS:
        present = all((adapter_dir(a, seed) / "adapter_model.safetensors").is_file() for a in ALGORITHMS)
        if present and smoke_gate(seed) == "PASS":
            seeds.append(seed)
    return seeds


# --------------------------------------------------------------------------- #
# evaluation
# --------------------------------------------------------------------------- #


def bindings(protocol: dict, tasks: list[dict], training_seeds: list[int]) -> list[dict]:
    """Per algorithm (one worker/job): learned_adapter x training seeds, then pretrained_base."""

    rows = []
    inference_seed = int(protocol["inference_seed"])
    for worker, algorithm in enumerate(ALGORITHMS):
        conditions = [("learned_adapter", seed) for seed in training_seeds] + [("pretrained_base", None)]
        for condition, training_seed in conditions:
            for task in tasks:
                rows.append(
                    {
                        "index": len(rows),
                        "worker": worker,
                        "kind": "models",
                        "task_id": task["row"]["task_id"],
                        "algorithm": algorithm,
                        "condition": condition,
                        "seed": inference_seed,
                        "training_seed": training_seed,
                    }
                )
    return rows


def evaluate_inputs_stage(panel: str) -> dict:
    protocol = load_protocol(panel)
    tasks = load_tasks(protocol)
    training_seeds = available_training_seeds()
    rows = bindings(protocol, tasks, training_seeds)
    manifest = {
        "schema_version": "choice_frontier_evaluation_inputs_v1",
        "protocol_id": protocol["protocol_id"],
        "panel": panel,
        "membership_sha256": membership(panel)["membership_sha256"],
        "training_seeds": training_seeds,
        "missing_training_seeds": [s for s in TRAINING_SEEDS if s not in training_seeds],
        "adapters": {
            f"{a}-s{s}": str(adapter_dir(a, s).relative_to(ROOT)) for a in ALGORITHMS for s in training_seeds
        },
        "bindings": rows,
        "counts": {"models": len(rows)},
    }
    if len(rows) != len(ALGORITHMS) * (len(training_seeds) + 1) * len(tasks):
        raise ValueError("choice-frontier v4 evaluation matrix differs from the frozen protocol")
    write(output_root(protocol) / "evaluation" / "bindings.json", manifest)
    return {k: v for k, v in manifest.items() if k != "bindings"}


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


def evaluate_worker(panel: str, algorithm: str, endpoint: str) -> dict:
    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError("choice-frontier model worker requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("choice-frontier model worker requires an explicit scheduler MASTER_PORT")
    protocol = load_protocol(panel)
    tasks = load_tasks(protocol)
    manifest = read_json(output_root(protocol) / "evaluation" / "bindings.json")
    rows = [row for row in manifest["bindings"] if row["algorithm"] == algorithm]
    if len(rows) != (len(manifest["training_seeds"]) + 1) * len(tasks):
        raise ValueError("choice-frontier v4 worker partition differs from frozen coverage")
    for seed in manifest["training_seeds"]:
        if smoke_gate(seed) != "PASS":
            raise ValueError(f"training seed {seed} lacks a PASS smoke gate")
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    adapters = {f"{algorithm}-s{s}": manifest["adapters"][f"{algorithm}-s{s}"] for s in manifest["training_seeds"]}
    for path in adapters.values():
        if not (ROOT / path / "adapter_model.safetensors").is_file():
            raise ValueError(f"choice-frontier adapter checkpoint missing: {path}")
    policy = None
    if any(not episode_paths(protocol, row)[0].exists() for row in rows):
        policy = load_policy(protocol, adapters)
    completed = retained = model_calls = 0
    started = time.monotonic()
    reports = []
    for binding in rows:
        learned = binding["condition"] == "learned_adapter"
        adapter_key = f"{algorithm}-s{binding['training_seed']}" if learned else None
        checkpoint = adapters[adapter_key] if learned else None

        def generate(example, adapter_key=adapter_key):
            nonlocal model_calls
            output = policy.generate([example], adapter_key)[0]
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
             "panel": panel, "algorithm": algorithm},
        )
    result = {
        "schema_version": "choice_frontier_evaluate_worker_v1",
        "protocol_id": protocol["protocol_id"],
        "panel": panel,
        "algorithm": algorithm,
        "training_seeds": manifest["training_seeds"],
        "episodes_completed": completed,
        "episodes_retained": retained,
        "model_calls": model_calls,
        "elapsed_seconds": time.monotonic() - started,
        "outputs": reports,
    }
    write(attempt_dir / "worker-result.json", result)
    return result


def audit_evaluate_worker() -> dict:
    terminal_path = Path(os.environ["EXPANDED_TERMINAL_PATH"])
    terminal = read_json(terminal_path)
    # The completion hook only receives EXPANDED_TERMINAL_PATH; the attempt dir is its parent (#136 fix).
    path = terminal_path.parent / "worker-result.json"
    result = read_json(path) if path.is_file() else {}
    ok = terminal["status"] == "succeeded" and result.get("episodes_completed", 0) > 0
    return {"schema_version": "choice_frontier_evaluate_audit_v1", "panel": result.get("panel"),
            "algorithm": result.get("algorithm"), "ok": ok}


# --------------------------------------------------------------------------- #
# finalize
# --------------------------------------------------------------------------- #


def finalize_stage(panel: str, endpoint: str) -> dict:
    """Independent replay of every model episode; complete coverage or explicit missingness."""

    protocol = load_protocol(panel)
    tasks = load_tasks(protocol)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    manifest = read_json(output_root(protocol) / "evaluation" / "bindings.json")
    replayed = 0
    missing, mismatches = [], []
    cells = {}
    for binding in manifest["bindings"]:
        episode, partial, _views = episode_paths(protocol, binding)
        if not episode.exists():
            missing.append(binding["index"])
            continue
        if partial.exists():
            mismatches.append({"index": binding["index"], "error": "partial journal beside completed episode"})
            continue
        report = read_json(episode)
        try:
            if any(report.get(k) != binding[k] for k in ("task_id", "algorithm", "condition", "seed", "training_seed")):
                raise ValueError("episode identity differs from its binding")
            independently_replay(ROOT, protocol, task_by_id[binding["task_id"]], report, endpoint)
        except ValueError as error:
            mismatches.append({"index": binding["index"], "error": str(error)})
            continue
        replayed += 1
        trained = "base" if binding["training_seed"] is None else f"s{binding['training_seed']}"
        cells[f"{binding['task_id']}|{binding['algorithm']}|{binding['condition']}|{trained}"] = report["result"]
    evaluation = {
        "schema_version": "choice_frontier_evaluation_v1",
        "protocol_id": protocol["protocol_id"],
        "panel": panel,
        "training_seeds": manifest["training_seeds"],
        "episodes_replayed": replayed,
        "bindings_total": len(manifest["bindings"]),
        "missing_bindings": missing,
        "replay_mismatches": mismatches,
        "complete": not missing and not mismatches,
    }
    write(output_root(protocol) / "evaluation" / "evaluation.json", evaluation)
    write(
        output_root(protocol) / "evaluation" / "cells.json",
        {"schema_version": "choice_frontier_cells_v1", "cells": dict(sorted(cells.items()))},
    )
    return evaluation


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=["prepare-views", "evaluate-inputs", "evaluate-worker", "audit-evaluate-worker", "finalize"],
    )
    parser.add_argument("--panel", choices=PANELS, default=None)
    parser.add_argument("--algorithm", choices=ALGORITHMS, default=None)
    parser.add_argument("--workers", type=int, default=4, help="CPU parallelism for prepare-views")
    parser.add_argument("--endpoint", default="http://127.0.0.1:18092")
    args = parser.parse_args(argv)
    if args.stage != "audit-evaluate-worker" and args.panel is None:
        raise ValueError(f"{args.stage} requires --panel")

    if args.stage == "prepare-views":
        result = prepare_views_stage(args.panel, workers=args.workers)
    elif args.stage == "evaluate-inputs":
        result = evaluate_inputs_stage(args.panel)
    elif args.stage == "evaluate-worker":
        if args.algorithm is None:
            raise ValueError("evaluate-worker requires --algorithm")
        result = evaluate_worker(args.panel, args.algorithm, args.endpoint)
    elif args.stage == "audit-evaluate-worker":
        result = audit_evaluate_worker()
    elif args.stage == "finalize":
        result = finalize_stage(args.panel, args.endpoint)
    else:  # pragma: no cover
        raise ValueError(args.stage)
    print(json.dumps(result, indent=2, sort_keys=True, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
