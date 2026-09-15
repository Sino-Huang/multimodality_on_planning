"""Resumable iteration collection and independent replay for expanded DAgger."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .expanded_dagger import (
    DaggerBFSSession,
    aggregate_update,
    certify_corrections,
    collection_checkpoint,
    replay_dagger_episode,
)
from .modality_corpus_replay import canonical
from .modality_view_preparation import frozen_processor, write_json
from .scene_assets import read_json
from .visual_episode import VisualSession, VisualTaskViews

CELL_SCHEMA = "expanded_dagger_collection_cell_v1"
JOURNAL_SCHEMA = "expanded_dagger_collection_journal_v1"
EPISODE_FIELDS = (
    "schema_version",
    "protocol_id",
    "algorithm",
    "task_id",
    "split",
    "modality",
    "iteration",
    "starting_checkpoint",
    "collection_offset",
    "decisions",
    "result",
)


def cell_root(root: Path, protocol: Mapping[str, Any], modality: str, iteration: int) -> Path:
    return root / protocol["output_root"] / "collection" / f"iteration-{iteration}" / modality


def cell_report_path(root: Path, protocol: Mapping[str, Any], modality: str, iteration: int) -> Path:
    return cell_root(root, protocol, modality, iteration) / "collection.json"


def _task_name(task_id: str) -> str:
    return task_id.replace("/", "__")


def _episode_paths(base: Path, task_id: str) -> tuple[Path, Path, Path]:
    episode = base / "episodes" / f"{_task_name(task_id)}.json.gz"
    journal = episode.with_name(episode.name.removesuffix(".json.gz") + ".journal.json.gz")
    views = base / "views" / _task_name(task_id)
    return episode, journal, views


def _replay_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    return {field: report[field] for field in EPISODE_FIELDS}


def _identity(
    protocol: Mapping[str, Any],
    *,
    task_id: str,
    modality: str,
    iteration: int,
    checkpoint: str,
    collection_offset: int,
    episode: Path,
    views: Path,
    root: Path,
) -> dict[str, Any]:
    return {
        "protocol_id": protocol["protocol_id"],
        "task_id": task_id,
        "split": protocol["collection"]["allowed_split"],
        "algorithm": protocol["algorithm"],
        "modality": modality,
        "iteration": iteration,
        "starting_checkpoint": checkpoint,
        "collection_offset": collection_offset,
        "episode_path": str(episode.relative_to(root)),
        "view_output": str(views.relative_to(root)),
        "model_id": protocol["model"]["id"],
        "model_revision": protocol["model"]["revision"],
        "view_serializer": protocol["views"]["serializer"],
    }


def _restore(wrapper: DaggerBFSSession, views: VisualTaskViews, decisions: list[dict[str, Any]]) -> None:
    views.read_only = True
    try:
        for expected in decisions:
            request = wrapper.next_request(views, pixels=False)
            if request is None or request.model_input != expected["student_input"]:
                raise ValueError("DAgger journal replay student input differs")
            if request.example["binding"] != expected["student_view"]:
                raise ValueError("DAgger journal replay view binding differs")
            actual = wrapper.submit_student(
                expected["student_raw_output"], allow_expert=expected["correction"] is not None
            )
            if actual != expected:
                raise ValueError("DAgger journal replay decision differs")
    finally:
        views.read_only = False


def _commit_pending(
    wrapper: DaggerBFSSession,
    views: VisualTaskViews,
    saved: dict[str, Any],
) -> None:
    pending = saved.get("pending")
    if pending is None:
        return
    request = wrapper.next_request(views, pixels=False)
    if request is None or request.model_input != pending["student_input"]:
        raise ValueError("persisted DAgger output no longer matches its student input")
    if request.example["binding"] != pending["student_view"]:
        raise ValueError("persisted DAgger output no longer matches its view binding")
    actual = wrapper.submit_student(pending["student_raw_output"], allow_expert=pending["allow_expert"])
    saved["decisions"].append(actual)
    saved["call_measurements"].append(pending["measurement"])
    saved["pending"] = None
    views.save()


def _collect_episode(
    root: Path,
    protocol: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    modality: str,
    iteration: int,
    checkpoint: str,
    endpoint: str,
    collection_offset: int,
    corrections_before: int,
    generate: Callable[[dict[str, Any]], tuple[str, int]],
    progress: Callable[..., None],
) -> tuple[dict[str, Any], bool]:
    base = cell_root(root, protocol, modality, iteration)
    episode_path, journal_path, view_output = _episode_paths(base, row["task_id"])
    expected = _identity(
        protocol,
        task_id=row["task_id"],
        modality=modality,
        iteration=iteration,
        checkpoint=checkpoint,
        collection_offset=collection_offset,
        episode=episode_path,
        views=view_output,
        root=root,
    )
    if episode_path.exists():
        if journal_path.exists():
            raise ValueError("completed DAgger episode retains a conflicting journal")
        report = read_json(episode_path)
        if any(report.get(key) != value for key, value in expected.items()):
            raise ValueError("retained DAgger episode identity differs")
        views = VisualTaskViews(
            root,
            dict(row),
            row["view_manifest"],
            view_output,
            endpoint,
            read_only=True,
            scene_views=protocol["views"]["source"],
        )
        session = VisualSession(
            root,
            dict(row),
            "bfs",
            "exact_reference",
            protocol["collection"]["seed"],
            episode_path,
            protocol["protocol_id"],
            views=views,
        )
        replay_dagger_episode(_replay_payload(report), protocol, session, views)
        return report, True

    views = VisualTaskViews(
        root,
        dict(row),
        row["view_manifest"],
        view_output,
        endpoint,
        scene_views=protocol["views"]["source"],
    )
    session = VisualSession(
        root,
        dict(row),
        "bfs",
        "exact_reference",
        protocol["collection"]["seed"],
        episode_path,
        protocol["protocol_id"],
        views=views,
    )
    wrapper = DaggerBFSSession(
        session,
        protocol,
        task_id=row["task_id"],
        split="train",
        modality=modality,
        iteration=iteration,
        starting_checkpoint=checkpoint,
        collection_offset=collection_offset,
    )
    saved = read_json(journal_path) if journal_path.exists() else {
        "schema_version": JOURNAL_SCHEMA,
        **expected,
        "decisions": [],
        "call_measurements": [],
        "pending": None,
        "started": time.time(),
        "active_wall_seconds": 0.0,
    }
    if saved.get("schema_version") != JOURNAL_SCHEMA or any(
        saved.get(key) != value for key, value in expected.items()
    ):
        raise ValueError("DAgger episode journal identity differs")
    attempt_started = time.monotonic()
    _restore(wrapper, views, saved["decisions"])
    _commit_pending(wrapper, views, saved)
    saved["active_wall_seconds"] += time.monotonic() - attempt_started
    write_json(journal_path, saved)

    decision_cap = protocol["collection"]["max_decisions_per_modality_iteration"]
    correction_cap = protocol["collection"]["max_corrections_per_modality_iteration"]
    checkpoint_started = time.monotonic()
    stop_reason = None
    while stop_reason is None:
        total_decisions = collection_offset + len(wrapper.decisions)
        total_corrections = corrections_before + sum(d["correction"] is not None for d in wrapper.decisions)
        if total_decisions >= decision_cap:
            stop_reason = "collection_decision_quota"
            break
        request = wrapper.next_request(views)
        if request is None:
            stop_reason = "correction_quota" if wrapper.stopped_without_correction else "session_complete"
            break
        call_started = time.monotonic()
        try:
            raw_output, generated_tokens = generate(request.example)
        finally:
            for image in request.example["images"]:
                image.close()
        measurement = {
            "collection_decision_index": total_decisions,
            "input_tokens": request.example["binding"]["input_tokens"],
            "generated_sequence_tokens": generated_tokens,
            "call_wall_seconds": time.monotonic() - call_started,
        }
        saved["pending"] = {
            "student_input": request.model_input,
            "student_view": request.example["binding"],
            "student_raw_output": raw_output,
            "allow_expert": total_corrections < correction_cap,
            "measurement": measurement,
        }
        saved["active_wall_seconds"] += time.monotonic() - checkpoint_started
        write_json(journal_path, saved)
        checkpoint_started = time.monotonic()
        _commit_pending(wrapper, views, saved)
        saved["active_wall_seconds"] += time.monotonic() - checkpoint_started
        write_json(journal_path, saved)
        checkpoint_started = time.monotonic()
        last = wrapper.decisions[-1]
        progress(
            task_id=row["task_id"],
            decisions=collection_offset + len(wrapper.decisions),
            corrections=corrections_before + sum(d["correction"] is not None for d in wrapper.decisions),
        )
        if last["invalid_operation_charge"] and last["correction"] is None:
            stop_reason = "correction_quota"

    report = {
        **wrapper.finish(stop_reason),
        **expected,
        "call_measurements": saved["call_measurements"],
        "started": saved["started"],
        "finished": time.time(),
        "active_wall_seconds": saved["active_wall_seconds"] + time.monotonic() - checkpoint_started,
    }
    views.save()
    write_json(episode_path, report)
    journal_path.unlink()
    return report, False


def _rows_by_task(protocol: Mapping[str, Any], source_records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in source_records:
        rows.setdefault(row["task_id"], row)
    if list(rows) != protocol["collection"]["task_order"]:
        raise ValueError("DAgger task rows differ from frozen collection order")
    return rows


def collect_cell(
    root: Path,
    protocol: Mapping[str, Any],
    source_records: list[dict[str, Any]],
    *,
    modality: str,
    iteration: int,
    endpoint: str,
    generate: Callable[[dict[str, Any]], tuple[str, int]],
    progress: Callable[..., None],
    runtime_provenance: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    output = cell_report_path(root, protocol, modality, iteration)
    if output.exists():
        return read_json(output), True
    checkpoint = collection_checkpoint(protocol, modality, iteration)
    rows = _rows_by_task(protocol, source_records)
    episodes = []
    decisions = 0
    corrections: list[dict[str, Any]] = []
    retained = 0
    overall_stop = "task_schedule_exhausted"
    for task_id in protocol["collection"]["task_order"]:
        report, was_retained = _collect_episode(
            root,
            protocol,
            rows[task_id],
            modality=modality,
            iteration=iteration,
            checkpoint=checkpoint,
            endpoint=endpoint,
            collection_offset=decisions,
            corrections_before=len(corrections),
            generate=generate,
            progress=progress,
        )
        episodes.append(report["episode_path"])
        retained += int(was_retained)
        decisions += report["result"]["collection_decisions"]
        corrections.extend(d["correction"] for d in report["decisions"] if d["correction"] is not None)
        if report["result"]["stop_reason"] in {"collection_decision_quota", "correction_quota"}:
            overall_stop = report["result"]["stop_reason"]
            break

    task_count = len(episodes)
    correction_path = output.with_name("corrections.json.gz")
    write_json(
        correction_path,
        {
            "schema_version": "expanded_dagger_correction_set_v1",
            "protocol_id": protocol["protocol_id"],
            "modality": modality,
            "iteration": iteration,
            "corrections": corrections,
        },
    )
    result = {
        "schema_version": CELL_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "iteration": iteration,
        "starting_checkpoint": checkpoint,
        "scheduled_tasks": len(protocol["collection"]["task_order"]),
        "completed_task_prefix": protocol["collection"]["task_order"][:task_count],
        "unstarted_tasks": protocol["collection"]["task_order"][task_count:],
        "episodes": episodes,
        "collection_decisions": decisions,
        "accepted_student_operations": sum(
            d["applied_operation_source"] == "student"
            for path in episodes
            for d in read_json(root / path)["decisions"]
        ),
        "invalid_student_operations": sum(
            d["invalid_operation_charge"] for path in episodes for d in read_json(root / path)["decisions"]
        ),
        "expert_queries": len(corrections),
        "corrections": len(corrections),
        "stop_reason": overall_stop,
        "unused_decision_quota": protocol["collection"]["max_decisions_per_modality_iteration"] - decisions,
        "unused_correction_quota": protocol["collection"]["max_corrections_per_modality_iteration"] - len(corrections),
        "correction_dataset": str(correction_path.relative_to(root)),
        "retained_episodes": retained,
        "runtime_provenance": dict(runtime_provenance),
        "training_updates": 0,
    }
    write_json(output, result)
    return result, False


def _target_token_count(target: Mapping[str, Any]) -> int:
    tokenizer = frozen_processor().processor.tokenizer
    return len(tokenizer(canonical(target), add_special_tokens=False)["input_ids"])


def verify_cell(
    root: Path,
    protocol: Mapping[str, Any],
    source_records: list[dict[str, Any]],
    *,
    modality: str,
    iteration: int,
    endpoint: str,
) -> dict[str, Any]:
    report = read_json(cell_report_path(root, protocol, modality, iteration))
    if (
        report.get("schema_version") != CELL_SCHEMA
        or report.get("protocol_id") != protocol["protocol_id"]
        or report.get("modality") != modality
        or report.get("iteration") != iteration
        or report.get("starting_checkpoint") != collection_checkpoint(protocol, modality, iteration)
        or report.get("training_updates") != 0
    ):
        raise ValueError("DAgger collection cell identity differs")
    rows = _rows_by_task(protocol, source_records)
    decisions = []
    corrections = []
    episode_stops = []
    expected_offset = 0
    for task_id, relative in zip(report["completed_task_prefix"], report["episodes"], strict=True):
        episode = read_json(root / relative)
        expected_path, journal_path, view_output = _episode_paths(
            cell_root(root, protocol, modality, iteration), task_id
        )
        if root / relative != expected_path or journal_path.exists() or episode["collection_offset"] != expected_offset:
            raise ValueError("DAgger episode membership or offset differs")
        views = VisualTaskViews(
            root,
            rows[task_id],
            rows[task_id]["view_manifest"],
            view_output,
            endpoint,
            read_only=True,
            scene_views=protocol["views"]["source"],
        )
        session = VisualSession(
            root,
            rows[task_id],
            "bfs",
            "exact_reference",
            protocol["collection"]["seed"],
            expected_path,
            protocol["protocol_id"],
            views=views,
        )
        replay_dagger_episode(_replay_payload(episode), protocol, session, views)
        decisions.extend(episode["decisions"])
        corrections.extend(d["correction"] for d in episode["decisions"] if d["correction"] is not None)
        episode_stops.append(episode["result"]["stop_reason"])
        if (
            len(episode["call_measurements"]) != len(episode["decisions"])
            or [row["collection_decision_index"] for row in episode["call_measurements"]]
            != [row["collection_decision_index"] for row in episode["decisions"]]
            or any(
                row["input_tokens"] > protocol["model"]["maximum_input_tokens"]
                or row["generated_sequence_tokens"] > protocol["model"]["output_tokens"]
                for row in episode["call_measurements"]
            )
        ):
            raise ValueError("DAgger model-call accounting differs from the frozen allowances")
        expected_offset += len(episode["decisions"])
    if [d["collection_decision_index"] for d in decisions] != list(range(len(decisions))):
        raise ValueError("DAgger decision identities are not contiguous")
    correction_set = read_json(root / report["correction_dataset"])
    if (
        correction_set.get("schema_version") != "expanded_dagger_correction_set_v1"
        or correction_set.get("protocol_id") != protocol["protocol_id"]
        or correction_set.get("modality") != modality
        or correction_set.get("iteration") != iteration
        or correction_set.get("corrections") != corrections
    ):
        raise ValueError("DAgger correction dataset differs from replayed episodes")
    unique = certify_corrections(
        corrections,
        protocol,
        modality=modality,
        iteration=iteration,
        target_token_counter=_target_token_count,
    )
    aggregate = aggregate_update(
        source_records,
        corrections,
        protocol,
        modality=modality,
        through_iteration=iteration,
        arm="dagger",
        target_token_counter=_target_token_count,
    )
    aggregation_path = cell_root(root, protocol, modality, iteration) / "aggregation.json.gz"
    if aggregation_path.exists() and read_json(aggregation_path) != aggregate:
        raise ValueError("retained DAgger aggregation differs from independent reconstruction")
    write_json(aggregation_path, aggregate)
    expected_values = {
        "collection_decisions": len(decisions),
        "accepted_student_operations": sum(d["applied_operation_source"] == "student" for d in decisions),
        "invalid_student_operations": sum(d["invalid_operation_charge"] for d in decisions),
        "expert_queries": len(corrections),
        "corrections": len(corrections),
        "unused_decision_quota": protocol["collection"]["max_decisions_per_modality_iteration"] - len(decisions),
        "unused_correction_quota": protocol["collection"]["max_corrections_per_modality_iteration"] - len(corrections),
    }
    if any(report.get(key) != value for key, value in expected_values.items()):
        raise ValueError("DAgger cell totals differ from episode evidence")
    if (
        report["scheduled_tasks"] != len(protocol["collection"]["task_order"])
        or len(report["episodes"]) != len(report["completed_task_prefix"])
        or len(decisions) > protocol["collection"]["max_decisions_per_modality_iteration"]
        or len(corrections) > protocol["collection"]["max_corrections_per_modality_iteration"]
        or report["completed_task_prefix"]
        != protocol["collection"]["task_order"][: len(report["completed_task_prefix"])]
        or report["unstarted_tasks"]
        != protocol["collection"]["task_order"][len(report["completed_task_prefix"]):]
    ):
        raise ValueError("DAgger collection order, quota, or missingness differs")
    if episode_stops[:-1] and any(reason != "session_complete" for reason in episode_stops[:-1]):
        raise ValueError("DAgger collection continued after a terminal cell stop")
    if not episode_stops or episode_stops[-1] not in {"session_complete", report["stop_reason"]}:
        raise ValueError("DAgger collection cell stop differs from its final episode")
    if report["stop_reason"] == "task_schedule_exhausted" and report["unstarted_tasks"]:
        raise ValueError("DAgger task schedule was reported exhausted with unstarted tasks")
    if report["stop_reason"] == "collection_decision_quota" and len(decisions) != protocol["collection"][
        "max_decisions_per_modality_iteration"
    ]:
        raise ValueError("DAgger decision quota stop occurred below quota")
    if report["stop_reason"] == "correction_quota" and (
        len(corrections) != protocol["collection"]["max_corrections_per_modality_iteration"]
        or not decisions
        or decisions[-1]["invalid_operation_charge"] != 1
        or decisions[-1]["correction"] is not None
    ):
        raise ValueError("DAgger correction quota stop lacks the retained uncorrected rejection")
    provenance = report.get("runtime_provenance", {})
    if (
        provenance.get("goal5_runner_commit") != protocol["goal5_runner_commit"]
        or provenance.get("master_port") not in protocol["launch"]["master_port_pool"]
        or not provenance.get("runtime_head")
    ):
        raise ValueError("DAgger collection runtime provenance differs")
    return {
        "outcome": "PASS",
        "modality": modality,
        "iteration": iteration,
        **expected_values,
        "episodes_replayed": len(report["episodes"]),
        "corrections_replayed": len(corrections),
        "unique_corrections_for_training": len(unique),
        "aggregation_records": aggregate["record_count"],
        "aggregation_optimizer_updates": aggregate["optimizer_updates"],
        "correction_dataset": report["correction_dataset"],
        "aggregation_dataset": str(aggregation_path.relative_to(root)),
        "stop_reason": report["stop_reason"],
        "unstarted_tasks": report["unstarted_tasks"],
    }
