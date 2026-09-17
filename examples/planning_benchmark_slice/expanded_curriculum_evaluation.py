"""Batched, resumable evaluation for expanded curriculum adapters and controls."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .expanded_baseline import _commit_pending, _restore_events
from .expanded_successor_training import _sha256
from .expanded_views import ExpandedTaskViews
from .modality_view_preparation import write_json
from .scene_assets import read_json
from .visual_episode import VisualSession, VisualTaskViews, replay_visual_episode

COMPARATORS = ("base", "sft_sequential_order_control", "random_valid", "exact_reference")
COMPARATOR_CONDITIONS = {
    "base": "pretrained_base",
    "sft_sequential_order_control": "process_sft",
    "random_valid": "random_valid",
    "exact_reference": "exact_reference",
}


def arms(protocol):
    return tuple(row["arm"] for row in protocol["evaluation"]["arms"])


def matched_arms(protocol, modality):
    return tuple(row["arm"] for row in protocol["evaluation"]["arms"] if row["training_modality"] == modality)


def panels(root: Path, protocol: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    development = read_json(root / protocol["evaluation"]["development_panel"])
    unseen = read_json(root / protocol["evaluation"]["unseen_panel"])
    unseen_views = read_json(root / unseen["view_report"])
    unseen_tasks = unseen_views["tasks"]
    if (
        development.get("outcome") != "PASS"
        or len(development.get("tasks", [])) != 3
        or len(unseen_tasks) != 24
        or unseen.get("panel_id") != "expanded-panel-v2-qualified"
        or {task["row"]["task_id"] for task in unseen_tasks} != {task["row"]["task_id"] for task in unseen["tasks"]}
    ):
        raise ValueError("curriculum evaluation panels differ from the frozen contracts")
    return {"development": development["tasks"], "unseen": unseen_tasks}


def _task_name(task_id: str) -> str:
    return task_id.replace("/", "__")


def evaluation_root(root: Path, protocol: dict[str, Any], panel: str, modality: str, task_id: str) -> Path:
    return root / protocol["output_root"] / "evaluation" / panel / modality / _task_name(task_id)


def episode_path(
    root: Path,
    protocol: dict[str, Any],
    panel: str,
    modality: str,
    task_id: str,
    arm: str,
) -> Path:
    return evaluation_root(root, protocol, panel, modality, task_id) / f"{arm}.json.gz"


def _views(root, protocol, panel, task, output, endpoint, *, read_only=False):
    if panel == "development":
        return VisualTaskViews(
            root,
            task["row"],
            task["view_manifest"],
            output,
            endpoint,
            read_only=read_only,
            scene_views=protocol["views"]["scene_views"],
        )
    return ExpandedTaskViews(root, task, output, endpoint, read_only=read_only)


def _identity(root, protocol, panel, modality, task, arm, output, view_output):
    checkpoint = protocol["_curriculum_checkpoints"][arm]
    fingerprints = protocol["_curriculum_fingerprints"][arm]
    try:
        producing_attempt = protocol["_producing_attempt"]
        runtime_head = protocol["_runtime_head"]
        policy_identity = protocol["_curriculum_policy_identity"][arm]
    except KeyError as error:
        raise ValueError("curriculum episode identity lacks producing policy provenance") from error
    return {
        "schema_version": "expanded_curriculum_evaluation_episode_v1",
        "protocol_id": protocol["protocol_id"],
        "contract_id": protocol["protocol_id"],
        "panel": panel,
        "task_id": task["row"]["task_id"],
        "modality": modality,
        "algorithm": protocol["algorithm"],
        "arm": arm,
        "comparison_arm": arm,
        "behavior_arm": "process_sft",
        "adapter_id": arm,
        "seed": protocol["evaluation"]["seed"],
        "output": str(output.relative_to(root)),
        "view_output": str(view_output.relative_to(root)),
        "checkpoint": checkpoint,
        **fingerprints,
        "model_id": protocol["base_model"]["model_id"],
        "model_revision": protocol["base_model"]["revision"],
        "producing_attempt": producing_attempt,
        "runtime_head": runtime_head,
        "policy_identity": policy_identity,
    }


def _curriculum_session(root, protocol, task, arm, output, *, views=None):
    """Map a curriculum comparison arm onto the historical process-SFT behavior contract."""
    session = VisualSession(
        root,
        task["row"],
        protocol["algorithm"],
        "process_sft",
        protocol["evaluation"]["seed"],
        output,
        protocol["protocol_id"],
        views=views,
    )
    inner = getattr(session, "session", None)
    if inner is not None and hasattr(inner, "adapter_id"):
        inner.adapter_id = arm
        inner.session_id = f"process_sft:{arm}:{protocol['evaluation']['seed']}:{task['row']['task_id']}"
    return session


def _replay_curriculum_episode(root, protocol, task, arm, report, views):
    original_read_only = getattr(views, "read_only", False) if views is not None else False
    if views is not None:
        views.read_only = True
    try:
        session = _curriculum_session(
            root,
            protocol,
            task,
            arm,
            root / report["output"],
            views=views,
        )
        for event in report["events"]:
            request = session.next_request()
            if request is None or dict(request.model_input) != event["input"]:
                raise ValueError("curriculum episode replay input differs")
            binding = (
                views.observe(
                    dict(request.model_input),
                    protocol["algorithm"],
                    modality=report["modality"],
                    pixels=False,
                )["binding"]
                if views is not None
                else None
            )
            if binding != event["view"]:
                raise ValueError("curriculum episode replay view binding differs")
            session.submit(event["raw_output"], binding)
            if session.events[-1] != event:
                raise ValueError("curriculum episode replay operation/result differs")
        if session.next_request() is not None or session.result() != report["result"]:
            raise ValueError("curriculum episode replay completion differs")
        return session.result()
    finally:
        if views is not None:
            views.read_only = original_read_only


def _validate_producing_identity(protocol, report):
    producing = report.get("producing_attempt")
    if not isinstance(producing, dict) or set(producing) != {"job_id", "attempt", "directory"}:
        raise ValueError("curriculum episode lacks a scheduler producing attempt")
    key = (producing["job_id"], producing["attempt"], producing["directory"])
    if protocol.get("_valid_producing_attempts", {}).get(key) not in {
        "succeeded",
        "failed",
        "cutoff",
        "interrupted",
    }:
        raise ValueError("curriculum episode producing attempt is unknown or non-terminal")
    arm = report.get("arm")
    worker_result_path = Path(producing["directory"]) / "worker-result.json"
    worker_result = read_json(worker_result_path) if worker_result_path.is_file() else None
    expected_runtime = worker_result.get("runtime_head") if worker_result is not None else protocol.get("_runtime_head")
    expected_policy = (
        worker_result.get("policy_identities", {}).get(arm)
        if worker_result is not None
        else protocol.get("_curriculum_policy_identity", {}).get(arm)
    )
    if (
        (worker_result is not None and worker_result.get("producing_attempt") != producing)
        or report.get("runtime_head") != expected_runtime
        or report.get("policy_identity") != expected_policy
    ):
        raise ValueError("curriculum episode policy/runtime provenance differs")
    return producing


def _finalize(root, state):
    saved, session, views = state["saved"], state["session"], state["views"]
    report = {
        **state["identity"],
        "outcome": "RECORDED",
        "events": saved["events"],
        "result": session.result(),
        "call_measurements": saved["call_measurements"],
        "started": saved["started"],
        "finished": time.time(),
        "active_wall_seconds": saved["active_wall_seconds"],
        "raw_invalid_outputs_preserved": sum(not event["accepted"] for event in saved["events"]),
    }
    views.save()
    write_json(state["episode"], report)
    state["journal"].unlink()
    return report


def verify_episode(root, protocol, panel, modality, task, arm, endpoint):
    path = episode_path(root, protocol, panel, modality, task["row"]["task_id"], arm)
    report = read_json(path)
    producing_attempt = _validate_producing_identity(protocol, report)
    identity_protocol = dict(protocol)
    identity_protocol["_producing_attempt"] = producing_attempt
    identity_protocol["_runtime_head"] = report["runtime_head"]
    identity_protocol["_curriculum_policy_identity"] = {arm: report["policy_identity"]}
    view_output = Path(report["view_output"])
    if not view_output.is_absolute():
        view_output = root / view_output
    expected = _identity(root, identity_protocol, panel, modality, task, arm, path, view_output)
    if any(report.get(key) != value for key, value in expected.items()):
        raise ValueError("curriculum evaluation episode identity differs")
    views = _views(root, protocol, panel, task, view_output, endpoint, read_only=True)
    result = _replay_curriculum_episode(root, protocol, task, arm, report, views)
    if (
        result != report["result"]
        or len(report["events"]) != len(report["call_measurements"])
        or any(
            row["input_tokens"] > protocol["training"]["maximum_input_tokens"]
            or row["generated_sequence_tokens"] > protocol["training"]["output_tokens"]
            for row in report["call_measurements"]
        )
    ):
        raise ValueError("curriculum evaluation episode replay or model-call accounting differs")
    return report


def run_cell(
    root: Path,
    protocol: dict[str, Any],
    *,
    panel: str,
    modality: str,
    arm: str,
    tasks: list[dict[str, Any]],
    endpoint: str,
    generate,
    progress,
) -> list[dict[str, Any]]:
    """Evaluate one arm in deterministic task rounds with batches of at most two."""
    if arm not in matched_arms(protocol, modality):
        raise ValueError("curriculum evaluation arm is outside the frozen final checkpoints")
    finished = []
    active = []
    for task in tasks:
        task_id = task["row"]["task_id"]
        output = episode_path(root, protocol, panel, modality, task_id, arm)
        journal = output.with_name(output.name.removesuffix(".json.gz") + ".partial.json.gz")
        view_output = output.parent / f"{arm}-views"
        identity = _identity(root, protocol, panel, modality, task, arm, output, view_output)
        if output.exists():
            report = verify_episode(root, protocol, panel, modality, task, arm, endpoint)
            if journal.exists():
                saved = read_json(journal)
                if (
                    saved.get("pending") is not None
                    or saved.get("events") != report["events"]
                    or saved.get("call_measurements") != report["call_measurements"]
                ):
                    raise ValueError("completed curriculum evaluation episode has a conflicting journal")
                journal.unlink()
            finished.append(report)
            progress(completed=len(finished), total=len(tasks), task_id=task_id, retained=True)
            continue
        views = _views(root, protocol, panel, task, view_output, endpoint)
        session = _curriculum_session(root, protocol, task, arm, output, views=views)
        saved = (
            read_json(journal)
            if journal.exists()
            else {
                **identity,
                "events": [],
                "call_measurements": [],
                "pending": None,
                "started": time.time(),
                "active_wall_seconds": 0.0,
            }
        )
        if any(saved.get(key) != value for key, value in identity.items()):
            raise ValueError("curriculum evaluation journal identity differs")
        restored = time.monotonic()
        _restore_events(session, views, saved)
        _commit_pending(session, views, saved)
        saved["active_wall_seconds"] += time.monotonic() - restored
        write_json(journal, saved)
        active.append(
            {
                "task": task,
                "episode": output,
                "journal": journal,
                "identity": identity,
                "views": views,
                "session": session,
                "saved": saved,
            }
        )

    while active:
        requests = []
        remaining = []
        for state in active:
            request = state["session"].next_request()
            if request is None:
                finished.append(_finalize(root, state))
                progress(
                    completed=len(finished),
                    total=len(tasks),
                    task_id=state["task"]["row"]["task_id"],
                    retained=False,
                )
                continue
            example = state["views"].observe(dict(request.model_input), protocol["algorithm"], modality=modality)
            requests.append((state, request, example))
            remaining.append(state)
        active = remaining
        for start in range(0, len(requests), 2):
            batch = requests[start : start + 2]
            examples = [row[2] for row in batch]
            called = time.monotonic()
            try:
                outputs, generated_tokens = generate(examples)
            finally:
                for example in examples:
                    for image in example["images"]:
                        image.close()
            elapsed = time.monotonic() - called
            for (state, request, example), raw_output, tokens in zip(batch, outputs, generated_tokens, strict=True):
                saved = state["saved"]
                saved["pending"] = {
                    "input": dict(request.model_input),
                    "binding": example["binding"],
                    "raw_output": raw_output,
                    "measurement": {
                        "event_index": len(saved["events"]),
                        "model_call": True,
                        "input_tokens": example["binding"]["input_tokens"],
                        "generated_sequence_tokens": tokens,
                        "call_wall_seconds": elapsed / len(batch),
                        "batch_size": len(batch),
                    },
                }
                saved["active_wall_seconds"] += elapsed / len(batch)
                write_json(state["journal"], saved)
            for state, _, _ in batch:
                committed = time.monotonic()
                _commit_pending(state["session"], state["views"], state["saved"])
                state["saved"]["active_wall_seconds"] += time.monotonic() - committed
                write_json(state["journal"], state["saved"])
    if len(finished) != len(tasks):
        raise ValueError("curriculum evaluation cell omitted tasks")
    return [next(row for row in finished if row["task_id"] == task["row"]["task_id"]) for task in tasks]


def comparator_path(root, panel, modality, task_id, condition):
    base = (
        root / "outputs/matched_modalities/v5/evaluation"
        if panel == "development"
        else root / "outputs/expanded-study/v1/baseline/episodes"
    )
    return base / modality / _task_name(task_id) / f"best_first_add_greedy-{condition}.json.gz"


def validate_comparator_sources(root, protocol):
    audit = protocol["evaluation"]["comparator_audit"]
    evidence_path = root / audit["goal3_evidence"]
    replay_path = root / audit["goal3_independent_replay"]
    readiness_path = root / audit["checkpoint_readiness"]
    evidence, replay, readiness = read_json(evidence_path), read_json(replay_path), read_json(readiness_path)
    if (
        _sha256(evidence_path) != audit["goal3_evidence_sha256"]
        or _sha256(replay_path) != audit["goal3_independent_replay_sha256"]
        or _sha256(readiness_path) != audit["checkpoint_readiness_sha256"]
        or evidence.get("outcome") != "PASS"
        or evidence.get("protocol_id") != audit["unseen_protocol_id"]
        or evidence.get("complete_coverage") is not True
        or evidence.get("missing_bindings") != []
        or replay.get("outcome") != "PASS"
        or replay.get("protocol_id") != audit["unseen_protocol_id"]
        or replay.get("episodes_replayed") != replay.get("expected_episodes")
        or replay.get("every_episode_replayed") is not True
        or replay.get("missing_bindings") != []
        or readiness.get("outcome") != "PASS"
    ):
        raise ValueError("curriculum comparator Goal 3 audit binding differs")
    readiness_rows = {(row["modality"], row["algorithm"]): row for row in readiness.get("checkpoints", [])}
    for modality, expected in audit["process_sft"].items():
        checkpoint = root / expected["checkpoint"]
        row = readiness_rows.get((modality, protocol["algorithm"]))
        if (
            row is None
            or row.get("checkpoint") != expected["checkpoint"]
            or row.get("steps") != 16
            or row.get("seed") != 17
            or row.get("provenance_passed") is not True
            or _sha256(checkpoint / "adapter_model.safetensors") != expected["adapter_model_sha256"]
            or _sha256(checkpoint / "adapter_config.json") != expected["adapter_config_sha256"]
        ):
            raise ValueError("curriculum process-SFT comparator checkpoint binding differs")
    return {
        "goal3_evidence": audit["goal3_evidence"],
        "goal3_evidence_sha256": audit["goal3_evidence_sha256"],
        "goal3_independent_replay": audit["goal3_independent_replay"],
        "goal3_independent_replay_sha256": audit["goal3_independent_replay_sha256"],
        "process_sft": audit["process_sft"],
    }


def verify_comparator(root, protocol, panel, modality, task, condition, endpoint):
    retained_condition = COMPARATOR_CONDITIONS[condition]
    path = comparator_path(root, panel, modality, task["row"]["task_id"], retained_condition)
    report = read_json(path)
    if panel == "development":
        study = read_json(root / protocol["source_study"])
        view_output = root / study["output_root"] / "live-views" / _task_name(task["row"]["task_id"])
    else:
        view_output = root / report["view_output"]
    views = _views(root, protocol, panel, task, view_output, endpoint, read_only=True)
    replay_report = dict(report, contract_id=report.get("contract_id", report.get("protocol_id")))
    replay_visual_episode(root, task["row"], replay_report, views)
    audit = protocol["evaluation"]["comparator_audit"]
    expected_contract = audit["development_contract_id"] if panel == "development" else audit["unseen_protocol_id"]
    actual_contract = report.get("contract_id", report.get("protocol_id"))
    expected_checkpoint = (
        audit["process_sft"][modality]["checkpoint"] if condition == "sft_sequential_order_control" else None
    )
    if (
        report.get("task_id") != task["row"]["task_id"]
        or report.get("modality") != modality
        or report.get("algorithm") != protocol["algorithm"]
        or report.get("arm") != retained_condition
        or report.get("seed") != protocol["evaluation"]["seed"]
        or actual_contract != expected_contract
        or report.get("model_id") != protocol["base_model"]["model_id"]
        or report.get("model_revision") != protocol["base_model"]["revision"]
        or report.get("checkpoint") != expected_checkpoint
    ):
        raise ValueError("reused curriculum comparator differs from its panel binding")
    if condition == "sft_sequential_order_control":
        expected = audit["process_sft"][modality]
        checkpoint = root / expected["checkpoint"]
        if (
            _sha256(checkpoint / "adapter_model.safetensors") != expected["adapter_model_sha256"]
            or _sha256(checkpoint / "adapter_config.json") != expected["adapter_config_sha256"]
        ):
            raise ValueError("reused curriculum process-SFT comparator fingerprint differs")
    return {
        **report,
        "comparison_arm": f"{modality}__{condition}",
        "comparator_source": str(path.relative_to(root)),
        "comparator_contract": expected_contract,
        "goal3_audit": protocol.get("_comparator_audit"),
    }


def summarize(reports):
    grouped = {}
    for report in reports:
        key = (report["panel"], report["modality"], report["comparison_arm"])
        grouped.setdefault(key, []).append(report)
    cells = []
    for (panel, modality, arm), rows in sorted(grouped.items()):
        decisions = sum(row["result"]["decision_count"] for row in rows)
        invalid = sum(row["result"]["invalid_operation_count"] for row in rows)
        cells.append(
            {
                "panel": panel,
                "modality": modality,
                "arm": arm,
                "episodes": len(rows),
                "invariant_valid_successes": sum(row["result"]["invariant_valid_success"] for row in rows),
                "goal_reached": sum(row["result"]["goal_reached"] for row in rows),
                "algorithm_invariants_hold": sum(row["result"]["algorithm_invariants_hold"] for row in rows),
                "decisions": decisions,
                "invalid_operations": invalid,
                "invalid_operation_rate": invalid / max(1, decisions),
                "model_calls": decisions if arm.rsplit("__", 1)[-1] not in {"random_valid", "exact_reference"} else 0,
                "decision_call_allowance": sum(row["result"]["model_call_limit"] for row in rows),
            }
        )
    return cells


def paired_rows(reports, protocol):
    indexed = {(row["panel"], row["modality"], row["task_id"], row["comparison_arm"]): row for row in reports}
    rows = []
    curriculum = {row["arm"]: row["training_modality"] for row in protocol["evaluation"]["arms"]}
    controls = {f"{modality}__{condition}": modality for modality in protocol["modalities"] for condition in COMPARATORS}
    for panel, task_id in sorted({(key[0], key[2]) for key in indexed}):
        arms = {
            arm: {
                "invariant_valid_success": indexed[(panel, modality, task_id, arm)]["result"]["invariant_valid_success"],
                "goal_reached": indexed[(panel, modality, task_id, arm)]["result"]["goal_reached"],
                "invalid_operations": indexed[(panel, modality, task_id, arm)]["result"]["invalid_operation_count"],
                "decisions": indexed[(panel, modality, task_id, arm)]["result"]["decision_count"],
            }
            for arm, modality in {**curriculum, **controls}.items()
        }
        rows.append({"panel": panel, "task_id": task_id, "arms": arms})
    return rows
