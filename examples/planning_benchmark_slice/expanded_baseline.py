"""Frozen bindings and resumable episodes for the expanded matched baseline."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .expanded_views import ExpandedTaskViews
from .modality_view_preparation import write_json
from .scene_assets import read_json
from .visual_episode import VisualSession, replay_visual_episode


def validate_protocol(root: Path, protocol: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    panel = read_json(root / protocol["panel"])
    study = read_json(root / protocol["checkpoint_study"])
    readiness = read_json(root / protocol["checkpoint_readiness"])
    if (
        protocol["program_id"] != panel["program_id"]
        or protocol["panel_id"] != panel["panel_id"]
        or protocol["source_panel_commit"] != "7235bbdf7027055ff11451aec46d2157e58499b8"
        or protocol["algorithms"] != panel["algorithms"]
        or protocol["modalities"] != panel["modalities"]
        or protocol["conditions"] != panel["conditions"]
        or protocol["evaluation_seed"] != panel["evaluation_seed"]
        or protocol["logical_bindings"] != panel["logical_bindings"] != 1152
        or protocol["model_episodes"] != panel["model_episodes"] != 576
        or len(panel["tasks"]) != 24
        or panel["new_training"]
    ):
        raise ValueError("expanded baseline protocol differs from the frozen panel")
    if (
        protocol["model_id"] != study["model_id"]
        or protocol["model_revision"] != study["model_revision"]
        or protocol["context_tokens"] != study["context_tokens"]
        or protocol["output_tokens"] != study["output_tokens"]
        or protocol["inference"] != study["inference"]
        or readiness["outcome"] != "PASS"
        or len(readiness["checkpoints"]) != 12
    ):
        raise ValueError("expanded baseline model contract differs from verified v5")
    checkpoints = {(c["modality"], c["algorithm"]): c for c in readiness["checkpoints"]}
    if set(checkpoints) != {(m, a) for m in protocol["modalities"] for a in protocol["algorithms"]}:
        raise ValueError("verified checkpoint bank is incomplete")
    for checkpoint in checkpoints.values():
        if not (root / checkpoint["checkpoint"] / "adapter_model.safetensors").is_file():
            raise ValueError(f"missing verified adapter: {checkpoint['checkpoint']}")
    if set(protocol["execution_groups"]["controls"]) != {"random_valid", "exact_reference"} or set(
        protocol["execution_groups"]["models"]
    ) != {"pretrained_base", "process_sft"}:
        raise ValueError("baseline execution groups do not cover the four frozen conditions")
    return panel, study, readiness


def bindings(panel: dict[str, Any], protocol: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    index = 0
    for modality in protocol["modalities"]:
        for task_index, task in enumerate(panel["tasks"]):
            for algorithm in protocol["algorithms"]:
                for condition in protocol["conditions"]:
                    result.append(
                        {
                            "index": index,
                            "worker": task_index % protocol["workers"],
                            "task_index": task_index,
                            "task_id": task["row"]["task_id"],
                            "modality": modality,
                            "algorithm": algorithm,
                            "condition": condition,
                        }
                    )
                    index += 1
    if len(result) != protocol["logical_bindings"] or len({tuple(sorted(b.items())) for b in result}) != len(result):
        raise ValueError("expanded baseline binding enumeration is incomplete or duplicated")
    return result


def assigned_bindings(panel: dict[str, Any], protocol: dict[str, Any], worker: int, kind: str) -> list[dict[str, Any]]:
    if worker not in range(protocol["workers"]) or kind not in protocol["execution_groups"]:
        raise ValueError("unknown expanded baseline worker or execution group")
    conditions = set(protocol["execution_groups"][kind])
    return [b for b in bindings(panel, protocol) if b["worker"] == worker and b["condition"] in conditions]


def checkpoint_bank(root: Path, protocol: dict[str, Any], readiness: dict[str, Any], modality: str) -> dict[str, str]:
    return {
        c["algorithm"]: str(root / c["checkpoint"])
        for c in readiness["checkpoints"]
        if c["modality"] == modality
    }


def binding_paths(root: Path, protocol: dict[str, Any], binding: dict[str, Any]) -> tuple[Path, Path, Path]:
    task = binding["task_id"].replace("/", "__")
    episode = (
        root
        / protocol["output_root"]
        / "episodes"
        / binding["modality"]
        / task
        / f"{binding['algorithm']}-{binding['condition']}.json.gz"
    )
    partial = episode.with_name(episode.name.removesuffix(".json.gz") + ".partial.json.gz")
    view_output = (
        root
        / protocol["output_root"]
        / "views"
        / binding["modality"]
        / task
        / f"{binding['algorithm']}-{binding['condition']}"
    )
    return episode, partial, view_output


def _identity(protocol: dict[str, Any], binding: dict[str, Any], episode: Path, view_output: Path, checkpoint: str | None):
    return {
        "schema_version": "expanded_baseline_episode_v1",
        "protocol_id": protocol["protocol_id"],
        "panel_id": protocol["panel_id"],
        "binding_index": binding["index"],
        "worker": binding["worker"],
        "task_id": binding["task_id"],
        "modality": binding["modality"],
        "algorithm": binding["algorithm"],
        "arm": binding["condition"],
        "seed": protocol["evaluation_seed"],
        "output": str(episode.relative_to(Path(protocol["root"]))),
        "view_output": str(view_output.relative_to(Path(protocol["root"]))),
        "checkpoint": checkpoint,
        "model_id": protocol["model_id"],
        "model_revision": protocol["model_revision"],
        "oracle_assisted_valid_operation_control": binding["condition"] == "random_valid",
    }


def _restore_events(session: VisualSession, views: ExpandedTaskViews, saved: dict[str, Any]) -> None:
    for event in saved["events"]:
        request = session.next_request()
        if request is None or dict(request.model_input) != event["input"]:
            raise ValueError("partial episode replay input differs")
        binding = views.observe(dict(request.model_input), saved["algorithm"], modality=saved["modality"], pixels=False)[
            "binding"
        ]
        if binding != event["view"]:
            raise ValueError("partial episode replay page binding differs")
        session.submit(event["raw_output"], binding)
        if session.events[-1] != event:
            raise ValueError("partial episode replay operation/result differs")


def _commit_pending(session: VisualSession, views: ExpandedTaskViews, saved: dict[str, Any]) -> None:
    pending = saved.get("pending")
    if pending is None:
        return
    request = session.next_request()
    if request is None or dict(request.model_input) != pending["input"]:
        raise ValueError("persisted pending model output no longer matches the request")
    observed = views.observe(
        dict(request.model_input), saved["algorithm"], modality=saved["modality"], pixels=False
    )["binding"]
    if observed != pending["binding"]:
        raise ValueError("persisted pending model output has a different view binding")
    session.submit(pending["raw_output"], pending["binding"])
    saved["events"].append(session.events[-1])
    saved["call_measurements"].append(pending["measurement"])
    saved["pending"] = None
    views.save()


def run_binding(
    root: Path,
    protocol: dict[str, Any],
    task: dict[str, Any],
    binding: dict[str, Any],
    checkpoint: str | None,
    endpoint: str,
    generate: Callable[[dict[str, Any]], tuple[str, int | None]] | None,
) -> tuple[dict[str, Any], bool]:
    episode, partial_path, view_output = binding_paths(root, protocol, binding)
    expected = _identity(protocol, binding, episode, view_output, checkpoint)
    if episode.exists():
        if partial_path.exists():
            raise ValueError("completed episode retains a conflicting partial journal")
        report = read_json(episode)
        if any(report.get(k) != v for k, v in expected.items()):
            raise ValueError("retained episode binding differs")
        views = ExpandedTaskViews(root, task, view_output, endpoint, read_only=True)
        replay_visual_episode(root, task["row"], report, views)
        return report, True

    views = ExpandedTaskViews(root, task, view_output, endpoint)
    session = VisualSession(
        root,
        task["row"],
        binding["algorithm"],
        binding["condition"],
        protocol["evaluation_seed"],
        episode,
        protocol["protocol_id"],
        views=views,
    )
    saved = read_json(partial_path) if partial_path.exists() else {
        **expected,
        "events": [],
        "call_measurements": [],
        "pending": None,
        "started": time.time(),
        "active_wall_seconds": 0.0,
    }
    if any(saved.get(k) != v for k, v in expected.items()):
        raise ValueError("partial episode binding differs")
    attempt_started = time.monotonic()
    _restore_events(session, views, saved)
    _commit_pending(session, views, saved)
    saved["active_wall_seconds"] += time.monotonic() - attempt_started
    write_json(partial_path, saved)
    checkpoint_started = time.monotonic()
    while (request := session.next_request()) is not None:
        raw = dict(request.model_input)
        example = views.observe(raw, binding["algorithm"], modality=binding["modality"])
        call_started = time.monotonic()
        try:
            if generate is None:
                generated, generated_tokens = session.reference_output(), None
            else:
                generated, generated_tokens = generate(example)
        finally:
            for image in example["images"]:
                image.close()
        measurement = {
            "event_index": len(session.events),
            "model_call": binding["condition"] in {"pretrained_base", "process_sft"},
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
        write_json(partial_path, saved)
        checkpoint_started = time.monotonic()
        _commit_pending(session, views, saved)
        saved["active_wall_seconds"] += time.monotonic() - checkpoint_started
        write_json(partial_path, saved)
        checkpoint_started = time.monotonic()
    report = {
        **expected,
        "outcome": "RECORDED",
        "events": saved["events"],
        "result": session.result(),
        "call_measurements": saved["call_measurements"],
        "started": saved["started"],
        "finished": time.time(),
        "active_wall_seconds": saved["active_wall_seconds"] + time.monotonic() - checkpoint_started,
        "raw_invalid_outputs_preserved": sum(not event["accepted"] for event in saved["events"]),
    }
    views.save()
    write_json(episode, report)
    partial_path.unlink()
    return report, False


def independently_replay(root: Path, task: dict[str, Any], report: dict[str, Any], endpoint: str) -> dict[str, Any]:
    views = ExpandedTaskViews(root, task, root / report["view_output"], endpoint, read_only=True)
    return replay_visual_episode(root, task["row"], report, views)
