"""Observable-input and teacher-target audits for issue-57 BFWS traces."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from .bfws_episode import build_bfws_evaluator
from .bfws_generation import preflight_frozen_bfws_trace_generation, verify_frozen_bfws_episode
from .bfws_model_input import (
    bfws_text_policy_training_messages,
    build_bounded_bfws_model_input,
    compact_bfws_teacher_operation,
    resolve_bfws_model_operation,
    validate_bfws_teacher_operation,
)
from .bfws_phase import BFWSPhaseGate
from .episode_evidence import read_episode_evidence
from .model_search_episode import _parse_model_output
from .pddl_state import PDDLStateAuthority
from .search_context import (
    AcceptedSearchDelta,
    _apply_persisted_transition,
)
from .search_memory import (
    AcceptedRetirement,
    AcceptedTransition,
    SearchMemory,
    SearchRetireRequest,
    SearchTransitionRequest,
    apply_search_retirement,
    apply_search_transition,
)
from .search_trace import TraceSegmentLimits, _decode_operation, _validated_envelope

_AUDIT_SCHEMA = "bfws_trace_release_audit_v1"
_AUDIT_PART_SCHEMA = "bfws_trace_audit_part_v1"
_SNAPSHOT_SCHEMA = "bfws_teacher_snapshot_v1"


def audit_frozen_bfws_trace(
    *,
    row: Mapping[str, Any],
    evidence_path: str | Path,
    search_trace_path: str | Path,
    phase_gate: BFWSPhaseGate,
    input_token_counter: Callable[[Mapping[str, Any]], int],
    target_token_counter: Callable[[str], int],
) -> dict[str, Any]:
    """Audit every bounded model input and teacher target in one frozen trace."""

    phase_gate.require_run(
        stage="trace_generation",
        contract_id=phase_gate.phase_id,
        split=str(row.get("split")),
    )
    episode = read_episode_evidence(evidence_path)
    verify_frozen_bfws_episode(episode, row)
    task = episode["evidence"]["header"]["task"]
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    trace_bytes = gzip.decompress(Path(search_trace_path).read_bytes())
    trace_payload = json.loads(trace_bytes)
    limits = _trace_limits(trace_bytes, trace_payload["record_count"])
    records = _validated_envelope(trace_bytes, limits=limits)["records"]
    corpus = phase_gate.components["corpus"]
    accepted_delta_limit = corpus["accepted_delta_limit"]
    events = episode["evidence"]["events"]
    if len(events) != len(records):
        raise ValueError(f"BFWS trace event count differs from its derived records: {row['instance_id']}")

    live_memory = SearchMemory.initial(authority)
    replay_memory = SearchMemory.initial(authority)
    live_deltas: deque[AcceptedSearchDelta] = deque(maxlen=accepted_delta_limit)
    replay_deltas: deque[AcceptedSearchDelta] = deque(maxlen=accepted_delta_limit)
    teacher_records: list[dict[str, Any]] = []
    for index, (event, record) in enumerate(zip(events, records, strict=True)):
        if event["operation"] != record["operation"] or event["rationale"] != record["rationale"]:
            raise ValueError(f"BFWS evidence and derived trace differ: {row['instance_id']} record {index}")
        validate_bfws_teacher_operation(event["observation"], record["operation"])
        model_input, dropped = build_bounded_bfws_model_input(
            observation=event["observation"],
            checkpoint=_checkpoint_for_memory(replay_memory),
            accepted_deltas=tuple(replay_deltas),
            max_bytes=corpus["model_input_byte_preference"],
            max_input_tokens=corpus["model_input_token_limit"],
            token_counter=input_token_counter,
        )
        live_input, live_dropped = build_bounded_bfws_model_input(
            observation=event["observation"],
            checkpoint=_checkpoint_for_memory(live_memory),
            accepted_deltas=tuple(live_deltas),
            max_bytes=corpus["model_input_byte_preference"],
            max_input_tokens=corpus["model_input_token_limit"],
            token_counter=input_token_counter,
        )
        if _canonical_bytes(live_input) != _canonical_bytes(model_input) or live_dropped != dropped:
            raise ValueError(f"BFWS live/replay model input differs: {row['instance_id']} record {index}")
        target = _teacher_target(record, event["observation"])
        target_text = _canonical_text(target)
        parsed_target, parse_error = _parse_model_output(target_text)
        if parsed_target is None or parsed_target["rationale"] != record["rationale"]:
            raise ValueError(
                f"BFWS teacher target failed strict parse: {row['instance_id']} record {index}: {parse_error}"
            )
        live_operation = resolve_bfws_model_operation(parsed_target["operation"], event["observation"])
        if live_operation != _decode_operation(event["operation"]):
            raise ValueError(f"BFWS parsed teacher target differs: {row['instance_id']} record {index}")
        input_tokens = input_token_counter(model_input)
        target_tokens = target_token_counter(target_text)
        if input_tokens > corpus["model_input_token_limit"]:
            raise ValueError(f"BFWS model input exceeds its frozen token allowance: {row['instance_id']} record {index}")
        if target_tokens > corpus["model_output_token_limit"]:
            raise ValueError(
                f"BFWS teacher target exceeds its frozen token allowance: {row['instance_id']} record {index}"
            )
        teacher_records.append(
            {
                "difficulty": row["difficulty"],
                "dropped_delta_count": dropped,
                "input_tokens": input_tokens,
                "instance_id": row["instance_id"],
                "record_index": index,
                "split": row["split"],
                "target_tokens": target_tokens,
            }
        )
        live_result = _apply_live_operation(live_memory, live_operation, event["observation"])
        replay_operation = _decode_operation(record["operation"])
        replay_result = _apply_persisted_transition(replay_memory, record["operation"], record["result"])
        if not isinstance(live_result, (AcceptedTransition, AcceptedRetirement)) or not isinstance(
            replay_result, (AcceptedTransition, AcceptedRetirement)
        ):
            raise ValueError(f"BFWS teacher operation was rejected: {row['instance_id']} record {index}")
        if live_result.memory.to_bytes() != replay_result.memory.to_bytes():
            raise ValueError(f"BFWS live/replay Search Memory differs: {row['instance_id']} record {index}")
        _append_delta(live_deltas, index, live_operation, live_result)
        _append_delta(replay_deltas, index, replay_operation, replay_result)
        live_memory = live_result.memory
        replay_memory = replay_result.memory

    return {
        "decision_count": len(records),
        "input_over_budget_count": 0,
        "live_replay_input_mismatch_count": 0,
        "max_input_tokens": max(record["input_tokens"] for record in teacher_records),
        "max_target_tokens": max(record["target_tokens"] for record in teacher_records),
        "target_over_budget_count": 0,
        "target_parse_rejection_count": 0,
        "teacher_decision_rejection_count": 0,
        "teacher_records": teacher_records,
    }


def audit_frozen_bfws_trace_release(
    manifest_path: str | Path,
    *,
    phase_gate: BFWSPhaseGate,
    audit_path: str | Path,
    snapshot_path: str | Path,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Audit all frozen trace positions and write deterministic throughput snapshots."""

    trace_manifest_path = Path(manifest_path).resolve()
    trace_root = trace_manifest_path.parent.parent
    manifest = json.loads(trace_manifest_path.read_bytes())
    frozen_rows = preflight_frozen_bfws_trace_generation(phase_gate)
    rows_by_id = {row["instance_id"]: row for row in frozen_rows}
    items = manifest.get("traces")
    if not isinstance(items, list) or len(items) != len(frozen_rows):
        raise ValueError("BFWS trace manifest is incomplete")
    items_by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        instance_id = item.get("instance_id") if isinstance(item, dict) else None
        if not isinstance(instance_id, str) or instance_id in items_by_id:
            raise ValueError("BFWS trace manifest contains a malformed or duplicate instance")
        items_by_id[instance_id] = item
    if set(items_by_id) != set(rows_by_id):
        raise ValueError("BFWS trace manifest differs from the frozen development panel")

    raw_input_counter, target_counter, tokenizer_contract = _pinned_token_counters(phase_gate)
    input_counter = _LastValueTokenCounter(raw_input_counter)
    all_teacher_records: list[dict[str, Any]] = []
    per_trace: list[dict[str, Any]] = []
    part_root = trace_root / "audit-parts"
    started = monotonic()
    completed_decisions = 0
    total_decisions = sum(row["exact_reference_decision_count"] for row in frozen_rows)
    for index, row in enumerate(frozen_rows, start=1):
        item = items_by_id[row["instance_id"]]
        part_path = part_root / f"{row['instance_id']}.json"
        expected_binding = _audit_part_binding(
            row=row,
            item=item,
            trace_root=trace_root,
            phase_gate=phase_gate,
            tokenizer_contract=tokenizer_contract,
        )
        reused = part_path.is_file()
        if reused:
            part = json.loads(part_path.read_bytes())
            if (
                not isinstance(part, dict)
                or set(part) != {"binding", "result"}
                or part["binding"] != expected_binding
                or not isinstance(part["result"], dict)
            ):
                raise ValueError(f"BFWS retained audit part differs: {row['instance_id']}")
            result = part["result"]
        else:
            result = audit_frozen_bfws_trace(
                row=row,
                evidence_path=trace_root / item["evidence"]["path"],
                search_trace_path=trace_root / item["search_trace"]["path"],
                phase_gate=phase_gate,
                input_token_counter=input_counter,
                target_token_counter=target_counter,
            )
        _validate_audit_result(result, row=row, phase_gate=phase_gate)
        if not reused:
            _atomic_write(part_path, _canonical_bytes({"binding": expected_binding, "result": result}))
        all_teacher_records.extend(result["teacher_records"])
        per_trace.append(
            {
                "instance_id": row["instance_id"],
                **{name: value for name, value in result.items() if name != "teacher_records"},
            }
        )
        completed_decisions += result["decision_count"]
        elapsed = monotonic() - started
        eta = (
            0.0
            if completed_decisions == total_decisions
            else elapsed * (total_decisions - completed_decisions) / completed_decisions
        )
        _report(
            progress,
            f"[{index}/{len(frozen_rows)}] {'reused audit' if reused else 'audited'} {row['instance_id']}; "
            f"elapsed {_duration(elapsed)}; ETA {_duration(eta)}",
        )

    selections, token_bins = _select_teacher_snapshots(all_teacher_records)
    snapshots = _materialize_snapshots(
        selections,
        rows_by_id=rows_by_id,
        items_by_id=items_by_id,
        trace_root=trace_root,
        phase_gate=phase_gate,
        input_token_counter=input_counter,
        target_token_counter=target_counter,
    )
    snapshot_target = Path(snapshot_path).resolve()
    _atomic_write(snapshot_target, b"".join(_canonical_bytes(snapshot) for snapshot in snapshots))
    audit = {
        "accepted_delta_limit": phase_gate.components["corpus"]["accepted_delta_limit"],
        "audit_results": {
            "input_over_budget_count": sum(item["input_over_budget_count"] for item in per_trace),
            "live_replay_input_mismatch_count": sum(item["live_replay_input_mismatch_count"] for item in per_trace),
            "target_over_budget_count": sum(item["target_over_budget_count"] for item in per_trace),
            "target_parse_rejection_count": sum(item["target_parse_rejection_count"] for item in per_trace),
            "teacher_decision_rejection_count": sum(item["teacher_decision_rejection_count"] for item in per_trace),
        },
        "decision_count": sum(item["decision_count"] for item in per_trace),
        "input_builder": phase_gate.components["corpus"]["input_builder"],
        "max_input_tokens": max(item["max_input_tokens"] for item in per_trace),
        "max_target_tokens": max(item["max_target_tokens"] for item in per_trace),
        "model_input_token_limit": phase_gate.components["corpus"]["model_input_token_limit"],
        "model_output_token_limit": phase_gate.components["corpus"]["model_output_token_limit"],
        "phase_receipt": phase_gate.receipt(stage="trace_generation"),
        "schema_version": _AUDIT_SCHEMA,
        "snapshot_count": len(snapshots),
        "snapshot_path": snapshot_target.relative_to(trace_root).as_posix(),
        "source_issue": 57,
        "source_trace_manifest_path": trace_manifest_path.relative_to(trace_root).as_posix(),
        "tokenizer": tokenizer_contract,
        "tokenizer_input_bins": token_bins,
    }
    if any(audit["audit_results"].values()) or audit["decision_count"] != total_decisions:
        raise ValueError("BFWS trace release audit did not satisfy the frozen zero-error contract")
    _atomic_write(Path(audit_path).resolve(), _canonical_bytes(audit))
    return audit


def _materialize_snapshots(
    selections: list[dict[str, Any]],
    *,
    rows_by_id: Mapping[str, Mapping[str, Any]],
    items_by_id: Mapping[str, Mapping[str, Any]],
    trace_root: Path,
    phase_gate: BFWSPhaseGate,
    input_token_counter: Callable[[Mapping[str, Any]], int],
    target_token_counter: Callable[[str], int],
) -> list[dict[str, Any]]:
    corpus = phase_gate.components["corpus"]
    cache: dict[str, tuple[dict[str, Any], list[dict[str, Any]], Any]] = {}
    snapshots: list[dict[str, Any]] = []
    for selection in selections:
        instance_id = selection["instance_id"]
        row = rows_by_id[instance_id]
        if instance_id not in cache:
            item = items_by_id[instance_id]
            episode = read_episode_evidence(trace_root / item["evidence"]["path"])
            trace_bytes = gzip.decompress((trace_root / item["search_trace"]["path"]).read_bytes())
            task = episode["evidence"]["header"]["task"]
            authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
            trace_payload = json.loads(trace_bytes)
            records = _validated_envelope(
                trace_bytes,
                limits=_trace_limits(trace_bytes, trace_payload["record_count"]),
            )["records"]
            cache[instance_id] = (episode, records, authority)
        episode, records, authority = cache[instance_id]
        record_index = selection["record_index"]
        record = records[record_index]
        event = episode["evidence"]["events"][record_index]
        checkpoint, accepted_deltas = _replay_context_before(
            records,
            authority=authority,
            record_index=record_index,
            accepted_delta_limit=corpus["accepted_delta_limit"],
        )
        model_input, dropped = build_bounded_bfws_model_input(
            observation=event["observation"],
            checkpoint=checkpoint,
            accepted_deltas=accepted_deltas,
            max_bytes=corpus["model_input_byte_preference"],
            max_input_tokens=corpus["model_input_token_limit"],
            token_counter=input_token_counter,
        )
        target = _teacher_target(record, event["observation"])
        input_tokens = input_token_counter(model_input)
        target_tokens = target_token_counter(_canonical_text(target))
        if input_tokens != selection["input_tokens"] or target_tokens != selection["target_tokens"]:
            raise ValueError("BFWS teacher snapshot differs from its audited token counts")
        snapshots.append(
            {
                "difficulty": row["difficulty"],
                "dropped_delta_count": dropped,
                "input": model_input,
                "input_tokens": input_tokens,
                "instance_id": instance_id,
                "record_index": record_index,
                "schema_version": _SNAPSHOT_SCHEMA,
                "selection_axis": selection["selection_axis"],
                "selection_bin": selection["selection_bin"],
                "selection_rule": "median_token_rank_then_instance_and_record",
                "split": row["split"],
                "target": target,
                "target_tokens": target_tokens,
            }
        )
    return snapshots


def _select_teacher_snapshots(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selections: list[dict[str, Any]] = []
    for difficulty in ("easy", "medium", "hard"):
        ranked = _ranked(record for record in records if record["difficulty"] == difficulty)
        selected = dict(ranked[len(ranked) // 2])
        selected.update({"selection_axis": "difficulty", "selection_bin": difficulty})
        selections.append(selected)

    ranked_all = _ranked(records)
    bins: list[dict[str, Any]] = []
    for index, label in enumerate(("low", "middle", "high")):
        start = index * len(ranked_all) // 3
        stop = (index + 1) * len(ranked_all) // 3
        members = ranked_all[start:stop]
        selected = dict(members[len(members) // 2])
        selected.update({"selection_axis": "input_token_bin", "selection_bin": label})
        selections.append(selected)
        bins.append(
            {
                "bin": label,
                "maximum_input_tokens": members[-1]["input_tokens"],
                "minimum_input_tokens": members[0]["input_tokens"],
                "record_count": len(members),
                "selection_rule": "equal_count_token_rank_tertile",
            }
        )
    return selections, bins


def _ranked(records: Any) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: (record["input_tokens"], record["instance_id"], record["record_index"]))


def _teacher_target(record: Mapping[str, Any], observation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "canonical_rationale": record["rationale"],
        "runtime_result": None,
        "typed_operation": compact_bfws_teacher_operation(observation, record["operation"]),
    }


def _audit_part_binding(
    *,
    row: Mapping[str, Any],
    item: Mapping[str, Any],
    trace_root: Path,
    phase_gate: BFWSPhaseGate,
    tokenizer_contract: Mapping[str, str],
) -> dict[str, Any]:
    evidence_path = trace_root / item["evidence"]["path"]
    search_trace_path = trace_root / item["search_trace"]["path"]
    implementation = hashlib.sha256()
    source_paths = {
        Path(__file__),
        Path(PDDLStateAuthority.is_goal.__code__.co_filename),
        Path(_apply_persisted_transition.__code__.co_filename),
        Path(_decode_operation.__code__.co_filename),
        Path(_parse_model_output.__code__.co_filename),
        Path(apply_search_retirement.__code__.co_filename),
        Path(apply_search_transition.__code__.co_filename),
        Path(build_bfws_evaluator.__code__.co_filename),
        Path(build_bounded_bfws_model_input.__code__.co_filename),
    }
    for source_path in sorted(source_paths):
        implementation.update(source_path.name.encode("utf-8"))
        implementation.update(source_path.read_bytes())
    return {
        "audit_schema": _AUDIT_SCHEMA,
        "evidence_sha256": _file_sha256(evidence_path),
        "implementation_sha256": implementation.hexdigest(),
        "input_builder": phase_gate.components["corpus"]["input_builder"],
        "instance_id": row["instance_id"],
        "phase_receipt": phase_gate.receipt(stage="trace_generation"),
        "row_sha256": hashlib.sha256(_canonical_bytes(row)).hexdigest(),
        "schema_version": _AUDIT_PART_SCHEMA,
        "search_trace_sha256": _file_sha256(search_trace_path),
        "token_limits": {
            "input": phase_gate.components["corpus"]["model_input_token_limit"],
            "output": phase_gate.components["corpus"]["model_output_token_limit"],
        },
        "tokenizer": dict(tokenizer_contract),
        "trace_item_sha256": hashlib.sha256(_canonical_bytes(item)).hexdigest(),
    }


def _validate_audit_result(
    result: Mapping[str, Any],
    *,
    row: Mapping[str, Any],
    phase_gate: BFWSPhaseGate,
) -> None:
    counter_names = {
        "input_over_budget_count",
        "live_replay_input_mismatch_count",
        "target_over_budget_count",
        "target_parse_rejection_count",
        "teacher_decision_rejection_count",
    }
    if (
        set(result)
        != {
            "decision_count",
            "max_input_tokens",
            "max_target_tokens",
            "teacher_records",
            *counter_names,
        }
        or result.get("decision_count") != row["exact_reference_decision_count"]
    ):
        raise ValueError(f"BFWS retained audit part differs: {row['instance_id']}")
    if any(result.get(name) != 0 for name in counter_names):
        raise ValueError(f"BFWS retained audit part has a nonzero rejection count: {row['instance_id']}")
    records = result.get("teacher_records")
    if not isinstance(records, list) or len(records) != result["decision_count"]:
        raise ValueError(f"BFWS retained audit part has incomplete positions: {row['instance_id']}")
    input_limit = phase_gate.components["corpus"]["model_input_token_limit"]
    target_limit = phase_gate.components["corpus"]["model_output_token_limit"]
    delta_limit = phase_gate.components["corpus"]["accepted_delta_limit"]
    fields = {
        "difficulty",
        "dropped_delta_count",
        "input_tokens",
        "instance_id",
        "record_index",
        "split",
        "target_tokens",
    }
    for index, record in enumerate(records):
        if (
            not isinstance(record, dict)
            or set(record) != fields
            or record["difficulty"] != row["difficulty"]
            or record["instance_id"] != row["instance_id"]
            or record["record_index"] != index
            or record["split"] != row["split"]
            or not _bounded_integer(record["dropped_delta_count"], minimum=0, maximum=delta_limit)
            or not _bounded_integer(record["input_tokens"], minimum=1, maximum=input_limit)
            or not _bounded_integer(record["target_tokens"], minimum=1, maximum=target_limit)
        ):
            raise ValueError(f"BFWS retained audit part has an invalid position: {row['instance_id']}")
    if result["max_input_tokens"] != max(record["input_tokens"] for record in records) or result[
        "max_target_tokens"
    ] != max(record["target_tokens"] for record in records):
        raise ValueError(f"BFWS retained audit part has invalid maxima: {row['instance_id']}")


def _bounded_integer(value: object, *, minimum: int, maximum: int) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and minimum <= value <= maximum


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class _AuditSnapshot:
    frontier: tuple[str, ...]
    visited: frozenset[str]
    known_states: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _AuditCheckpoint:
    authority_id: str
    snapshot: _AuditSnapshot


def _checkpoint_for_memory(memory: SearchMemory) -> _AuditCheckpoint:
    return _AuditCheckpoint(
        authority_id=memory.authority.authority_id,
        snapshot=_AuditSnapshot(
            frontier=memory.frontier,
            visited=memory.visited,
            known_states={state_id: memory.state(state_id) for state_id in memory.visited},
        ),
    )


def _apply_live_operation(
    memory: SearchMemory,
    operation: SearchTransitionRequest | SearchRetireRequest,
    observation: Mapping[str, Any],
) -> AcceptedTransition | AcceptedRetirement | object:
    if isinstance(operation, SearchRetireRequest):
        return apply_search_retirement(memory, operation)
    candidate = next(
        (
            item
            for item in observation["successor_candidates"]
            if isinstance(item, Mapping) and item.get("duplicate") is False
        ),
        None,
    )
    evaluation = candidate.get("evaluation") if isinstance(candidate, Mapping) else None
    if not isinstance(evaluation, Mapping):
        raise ValueError("BFWS live transition lacks its exact candidate evaluation")
    priority = evaluation.get("priority")
    novelty = evaluation.get("novelty_bucket")
    if (
        not isinstance(priority, list)
        or len(priority) != 4
        or isinstance(priority[1], bool)
        or not isinstance(priority[1], int)
        or isinstance(novelty, bool)
        or not isinstance(novelty, int)
    ):
        raise ValueError("BFWS live transition evaluation is malformed")
    return apply_search_transition(
        memory,
        operation,
        evaluator=build_bfws_evaluator(novelty, priority[1]),
    )


def _append_delta(
    deltas: deque[AcceptedSearchDelta],
    record_index: int,
    operation: SearchTransitionRequest | SearchRetireRequest,
    result: AcceptedTransition | AcceptedRetirement,
) -> None:
    if isinstance(result, AcceptedTransition):
        if not isinstance(operation, SearchTransitionRequest):
            raise ValueError("BFWS accepted transition has the wrong operation type")
        deltas.append(
            AcceptedSearchDelta(
                record_index=record_index,
                operation=operation,
                transition=result.transition,
                evaluation=result.evaluation,
            )
        )
    elif not isinstance(operation, SearchRetireRequest):
        raise ValueError("BFWS accepted retirement has the wrong operation type")


def _replay_context_before(
    records: list[dict[str, Any]],
    *,
    authority: PDDLStateAuthority,
    record_index: int,
    accepted_delta_limit: int,
) -> tuple[_AuditCheckpoint, tuple[AcceptedSearchDelta, ...]]:
    memory = SearchMemory.initial(authority)
    deltas: deque[AcceptedSearchDelta] = deque(maxlen=accepted_delta_limit)
    for index, record in enumerate(records[:record_index]):
        operation = _decode_operation(record["operation"])
        result = _apply_persisted_transition(memory, record["operation"], record["result"])
        if not isinstance(result, (AcceptedTransition, AcceptedRetirement)):
            raise ValueError(f"BFWS snapshot replay rejected record {index}")
        _append_delta(deltas, index, operation, result)
        memory = result.memory
    return _checkpoint_for_memory(memory), tuple(deltas)


def _pinned_token_counters(
    phase_gate: BFWSPhaseGate,
) -> tuple[Callable[[Mapping[str, Any]], int], Callable[[str], int], dict[str, str]]:
    from transformers import AutoProcessor

    model = phase_gate.components["training"]["model"]
    processor = AutoProcessor.from_pretrained(model["model_id"], revision=model["revision"])
    tokenizer = processor.tokenizer

    def count_input(model_input: Mapping[str, Any]) -> int:
        return len(
            tokenizer.apply_chat_template(
                bfws_text_policy_training_messages(model_input),
                tokenize=True,
                add_generation_prompt=True,
            )
        )

    def count_target(target: str) -> int:
        return len(tokenizer.encode(target, add_special_tokens=False))

    return count_input, count_target, {"model_id": model["model_id"], "revision": model["revision"]}


class _LastValueTokenCounter:
    """Reuse the builder's token count when its returned input is checked again."""

    def __init__(self, counter: Callable[[Mapping[str, Any]], int]) -> None:
        self._counter = counter
        self._last_input = b""
        self._last_count = 0

    def __call__(self, model_input: Mapping[str, Any]) -> int:
        serialized = _canonical_bytes(model_input)
        if serialized == self._last_input:
            return self._last_count
        self._last_input = serialized
        self._last_count = self._counter(model_input)
        return self._last_count


def _trace_limits(trace_bytes: bytes, record_count: int) -> TraceSegmentLimits:
    return TraceSegmentLimits(
        max_records=max(1, record_count),
        max_bytes=max(1_000_000, len(trace_bytes)),
    )


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _canonical_bytes(value: object) -> bytes:
    return (_canonical_text(value) + "\n").encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary_name).replace(path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _report(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _duration(seconds: float) -> str:
    total = max(0, round(seconds))
    hours, remainder = divmod(total, 3_600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


__all__ = ["audit_frozen_bfws_trace", "audit_frozen_bfws_trace_release"]
