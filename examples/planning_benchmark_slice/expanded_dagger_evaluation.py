"""Batched, resumable final-checkpoint evaluation for expanded DAgger."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .expanded_baseline import _commit_pending, _restore_events
from .expanded_views import ExpandedTaskViews
from .modality_view_preparation import write_json
from .scene_assets import read_json
from .visual_episode import VisualSession, VisualTaskViews, replay_visual_episode

ARMS = ("dagger_iteration_2", "continued_sft_iteration_2")
COMPARATORS = ("original_process_sft", "random_valid", "exact_reference")


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
        or {task["row"]["task_id"] for task in unseen_tasks}
        != {task["row"]["task_id"] for task in unseen["tasks"]}
    ):
        raise ValueError("DAgger evaluation panels differ from the frozen contracts")
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
            scene_views=protocol["views"]["source"],
        )
    return ExpandedTaskViews(root, task, output, endpoint, read_only=read_only)


def _identity(root, protocol, panel, modality, task, arm, output, view_output):
    checkpoint = protocol["checkpoint_lineage"][arm].format(modality=modality)
    return {
        "schema_version": "expanded_dagger_evaluation_episode_v1",
        "protocol_id": protocol["protocol_id"],
        "contract_id": protocol["protocol_id"],
        "panel": panel,
        "task_id": task["row"]["task_id"],
        "modality": modality,
        "algorithm": "bfs",
        "arm": arm,
        "seed": protocol["evaluation"]["seed"],
        "output": str(output.relative_to(root)),
        "view_output": str(view_output.relative_to(root)),
        "checkpoint": checkpoint,
        "model_id": protocol["model"]["id"],
        "model_revision": protocol["model"]["revision"],
    }


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
    view_output = Path(report["view_output"])
    if not view_output.is_absolute():
        view_output = root / view_output
    expected = _identity(root, protocol, panel, modality, task, arm, path, view_output)
    if any(report.get(key) != value for key, value in expected.items()):
        raise ValueError("DAgger evaluation episode identity differs")
    views = _views(root, protocol, panel, task, view_output, endpoint, read_only=True)
    result = replay_visual_episode(root, task["row"], report, views)
    if (
        result != report["result"]
        or len(report["events"]) != len(report["call_measurements"])
        or any(
            row["input_tokens"] > protocol["model"]["maximum_input_tokens"]
            or row["generated_sequence_tokens"] > protocol["model"]["output_tokens"]
            for row in report["call_measurements"]
        )
    ):
        raise ValueError("DAgger evaluation episode replay or model-call accounting differs")
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
    if arm not in ARMS:
        raise ValueError("DAgger evaluation arm is outside the frozen final checkpoints")
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
                    raise ValueError("completed DAgger evaluation episode has a conflicting journal")
                journal.unlink()
            finished.append(report)
            progress(completed=len(finished), total=len(tasks), task_id=task_id, retained=True)
            continue
        views = _views(root, protocol, panel, task, view_output, endpoint)
        session = VisualSession(
            root,
            task["row"],
            "bfs",
            arm,
            protocol["evaluation"]["seed"],
            output,
            protocol["protocol_id"],
            views=views,
        )
        saved = read_json(journal) if journal.exists() else {
            **identity,
            "events": [],
            "call_measurements": [],
            "pending": None,
            "started": time.time(),
            "active_wall_seconds": 0.0,
        }
        if any(saved.get(key) != value for key, value in identity.items()):
            raise ValueError("DAgger evaluation journal identity differs")
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
            example = state["views"].observe(dict(request.model_input), "bfs", modality=modality)
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
        raise ValueError("DAgger evaluation cell omitted tasks")
    return [
        next(row for row in finished if row["task_id"] == task["row"]["task_id"])
        for task in tasks
    ]


def comparator_path(root, panel, modality, task_id, condition):
    base = (
        root / "outputs/matched_modalities/v5/evaluation"
        if panel == "development"
        else root / "outputs/expanded-study/v1/baseline/episodes"
    )
    return base / modality / _task_name(task_id) / f"bfs-{condition}.json.gz"


def verify_comparator(root, protocol, panel, modality, task, condition, endpoint):
    path = comparator_path(root, panel, modality, task["row"]["task_id"], condition)
    report = read_json(path)
    if panel == "development":
        study = read_json(root / protocol["source_study"])
        view_output = root / study["output_root"] / "live-views" / _task_name(task["row"]["task_id"])
    else:
        view_output = root / report["view_output"]
    views = _views(root, protocol, panel, task, view_output, endpoint, read_only=True)
    replay_report = dict(report, contract_id=report.get("contract_id", report.get("protocol_id")))
    replay_visual_episode(root, task["row"], replay_report, views)
    if (
        report.get("task_id") != task["row"]["task_id"]
        or report.get("modality") != modality
        or report.get("algorithm") != "bfs"
        or report.get("arm") != condition
        or report.get("seed") != protocol["evaluation"]["seed"]
    ):
        raise ValueError("reused DAgger comparator differs from its panel binding")
    return report


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
                "model_calls": decisions if arm not in {"random_valid", "exact_reference"} else 0,
                "decision_call_allowance": sum(row["result"]["model_call_limit"] for row in rows),
            }
        )
    return cells


def paired_rows(reports):
    indexed = {
        (row["panel"], row["modality"], row["task_id"], row["comparison_arm"]): row
        for row in reports
    }
    rows = []
    for panel, modality, task_id in sorted({key[:3] for key in indexed}):
        arms = {
            arm: {
                "invariant_valid_success": indexed[(panel, modality, task_id, arm)]["result"][
                    "invariant_valid_success"
                ],
                "goal_reached": indexed[(panel, modality, task_id, arm)]["result"]["goal_reached"],
                "invalid_operations": indexed[(panel, modality, task_id, arm)]["result"][
                    "invalid_operation_count"
                ],
                "decisions": indexed[(panel, modality, task_id, arm)]["result"]["decision_count"],
            }
            for arm in (*ARMS, *COMPARATORS)
        }
        rows.append({"panel": panel, "modality": modality, "task_id": task_id, "arms": arms})
    return rows
