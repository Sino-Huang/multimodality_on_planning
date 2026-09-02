"""Release the governed BFWS operational and process text corpus."""

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
from typing import Any, cast

from src.data_collect.generate import GenerationRequest, GenerationRunReceipt, run_authorized_generation
from src.data_collect.splits import split_assignment_id

from .bfws_generation import preflight_frozen_bfws_trace_generation
from .bfws_model_input import (
    bfws_text_policy_training_messages,
    build_bounded_bfws_model_input,
    compact_bfws_teacher_operation,
    resolve_bfws_model_operation,
)
from .bfws_phase import BFWSPhaseGate
from .bfws_trace_audit import _audit_part_binding, _validate_audit_result
from .model_search_episode import _parse_model_output
from .pddl_state import CanonicalState, GroundedAction, PDDLTransition, TransitionProvenance
from .search_context import AcceptedSearchDelta
from .search_memory import (
    HeuristicValue,
    SearchRetireRequest,
    SearchTransitionRequest,
    StateEvaluation,
)
from .search_trace import _decode_operation

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = Path("manifests/bfws-text-corpus.json")
_AUDIT_PATH = Path("audits/corpus.json")
_PROCESS_CURRICULUM_PATH = Path("curricula/process.jsonl")
_OPERATIONAL_CURRICULUM_PATH = Path("curricula/operational.jsonl")
_SPLIT_LEDGER_PATH = Path("splits/assignments.jsonl")
_TRAINING_MANIFEST_PATH = Path("training/manifest.json")
_RELEASE_SCHEMA = "bfws_text_corpus_release_v1"
_RECORD_SCHEMA = "bfws_text_corpus_record_v1"
_CURRICULUM_SCHEMA = "bfws_text_corpus_curriculum_v1"
_AUDIT_SCHEMA = "bfws_text_corpus_audit_v1"
_TRAINING_SCHEMA = "bfws_process_training_projection_v1"
_DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}
_RETAINED_TRACE_AUDIT_IMPLEMENTATION_SHA256 = "8e474a83ce694def62c64c510bd82ab368cb47b8cfb4743107afee9d1e45cbc4"


@dataclass(frozen=True, slots=True)
class BFWSCorpusTrace:
    """All released views derived from one replay-verified expert trace."""

    process_rows: tuple[dict[str, Any], ...]
    operational_rows: tuple[dict[str, Any], ...]
    training_rows: tuple[dict[str, Any], ...]
    audit: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _CorpusSnapshot:
    frontier: tuple[str, ...]
    visited: frozenset[str]
    known_states: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _CorpusCheckpoint:
    authority_id: str
    snapshot: _CorpusSnapshot


def materialize_frozen_bfws_corpus_trace(
    *,
    row: Mapping[str, Any],
    trace_item: Mapping[str, Any],
    trace_root: str | Path,
    phase_gate: BFWSPhaseGate,
) -> BFWSCorpusTrace:
    """Materialize one atomic corpus shard from its retained #57 evidence."""

    phase_gate.require_run(
        stage="corpus_release",
        contract_id=phase_gate.phase_id,
        split=str(row.get("split")),
    )
    if trace_item.get("instance_id") != row.get("instance_id"):
        raise ValueError("BFWS corpus trace item differs from its frozen development row")
    root = Path(trace_root).resolve()
    _artifact_path(root, trace_item, "evidence")
    search_trace_path = _artifact_path(root, trace_item, "search_trace")
    audit_part_path = root / "audit-parts" / f"{row['instance_id']}.json"
    audit_part = _json_object(audit_part_path.read_bytes(), "BFWS trace audit part")
    training = phase_gate.components["training"]
    expected_binding = _audit_part_binding(
        row=row,
        item=trace_item,
        trace_root=root,
        phase_gate=phase_gate,
        tokenizer_contract={
            "model_id": training["model"]["model_id"],
            "revision": training["model"]["revision"],
        },
    )
    # The retained v1 audit binds the implementation used to create it; replay
    # below validates the trace against the current runtime without rewriting history.
    expected_binding["implementation_sha256"] = _RETAINED_TRACE_AUDIT_IMPLEMENTATION_SHA256
    if set(audit_part) != {"binding", "result"} or audit_part["binding"] != expected_binding:
        raise ValueError(f"BFWS corpus source audit binding differs: {row['instance_id']}")
    source_audit = audit_part["result"]
    _validate_audit_result(source_audit, row=row, phase_gate=phase_gate)

    trace_bytes = gzip.decompress(search_trace_path.read_bytes())
    trace = _json_object(trace_bytes, "BFWS search trace")
    records = trace.get("records")
    if (
        trace.get("record_count") != row["exact_reference_decision_count"]
        or not isinstance(records, list)
        or len(records) != trace["record_count"]
    ):
        raise ValueError(f"BFWS corpus source trace is incomplete: {row['instance_id']}")

    corpus = phase_gate.components["corpus"]
    accepted_deltas: deque[AcceptedSearchDelta] = deque(maxlen=corpus["accepted_delta_limit"])
    identity = str(row["semantic_task_identity"])
    assignment_id = split_assignment_id(identity, str(row["split"]))
    process_rows: list[dict[str, Any]] = []
    operational_rows: list[dict[str, Any]] = []
    training_rows: list[dict[str, Any]] = []
    future_leaks = 0
    dropped_deltas = 0
    max_input_bytes = 0

    positions = source_audit["teacher_records"]
    for index, (record, position) in enumerate(zip(records, positions, strict=True)):
        if record.get("index") != index:
            raise ValueError(f"BFWS trace index differs at {row['instance_id']} record {index}")
        observation = record["observation"]
        if any(delta.record_index >= index for delta in accepted_deltas):
            future_leaks += 1
        expected_dropped = position["dropped_delta_count"]
        if expected_dropped > len(accepted_deltas):
            raise ValueError(f"BFWS retained delta count is invalid at {row['instance_id']} record {index}")
        retained_deltas = tuple(accepted_deltas)[expected_dropped:]
        model_input, additionally_dropped = build_bounded_bfws_model_input(
            observation=observation,
            checkpoint=_checkpoint_from_observation(observation, str(trace["authority_id"])),
            accepted_deltas=retained_deltas,
            max_bytes=corpus["model_input_byte_preference"],
        )
        if additionally_dropped:
            raise ValueError(f"BFWS retained token audit no longer reproduces record {row['instance_id']}:{index}")
        target = {
            "canonical_rationale": record["rationale"],
            "runtime_result": None,
            "typed_operation": compact_bfws_teacher_operation(observation, record["operation"]),
        }
        target_text = _canonical_text(target)
        parsed, parse_error = _parse_model_output(target_text)
        if parsed is None or parsed["rationale"] != record["rationale"]:
            raise ValueError(
                f"BFWS corpus target failed strict parse at {row['instance_id']} record {index}: {parse_error}"
            )
        operation = resolve_bfws_model_operation(parsed["operation"], observation)
        if operation != _decode_operation(record["operation"]):
            raise ValueError(f"BFWS corpus target differs after parse at {row['instance_id']} record {index}")

        metadata = _record_metadata(
            row,
            trace_item,
            assignment_id=assignment_id,
            record_index=index,
        )
        process = {
            **metadata,
            "input": model_input,
            "record_id": f"{row['instance_id']}:{index}:process",
            "target": target,
            "view": "process",
        }
        process_rows.append(process)
        messages = bfws_text_policy_training_messages(model_input, target)
        if messages[1]["content"] != _canonical_text(model_input):
            raise ValueError(f"BFWS corpus/training serializer differs at {row['instance_id']} record {index}")
        training_rows.append({"messages": messages})
        if record["result"].get("status") == "accepted":
            transition = record["result"]["transition"]
            operational_rows.append(
                {
                    **metadata,
                    "input": {
                        "action": transition["action"],
                        "source_state": transition["source_state"],
                        "task_context": observation["task_context"],
                    },
                    "record_id": f"{row['instance_id']}:{index}:operational",
                    "target": {
                        "target_state": transition["target_state"],
                        "validity": "accepted",
                    },
                    "view": "operational",
                }
            )
        accepted_delta = _accepted_delta(index, operation, record["result"])
        if accepted_delta is not None:
            accepted_deltas.append(accepted_delta)
        dropped_deltas += expected_dropped
        max_input_bytes = max(max_input_bytes, len(_canonical_bytes(model_input)))

    audit = {
        "decision_count": len(process_rows),
        "future_step_leakage_count": future_leaks,
        "input_over_budget_count": source_audit["input_over_budget_count"],
        "live_training_input_mismatch_count": source_audit["live_replay_input_mismatch_count"],
        "max_input_bytes": max_input_bytes,
        "max_input_tokens": source_audit["max_input_tokens"],
        "max_target_tokens": source_audit["max_target_tokens"],
        "operational_record_count": len(operational_rows),
        "rolling_context_deltas_dropped": dropped_deltas,
        "target_over_budget_count": source_audit["target_over_budget_count"],
        "target_parse_rejection_count": source_audit["target_parse_rejection_count"],
        "teacher_decision_rejection_count": source_audit["teacher_decision_rejection_count"],
    }
    zero_counters = (
        "input_over_budget_count",
        "live_training_input_mismatch_count",
        "target_over_budget_count",
        "target_parse_rejection_count",
        "teacher_decision_rejection_count",
    )
    if future_leaks or any(audit[name] for name in zero_counters):
        raise ValueError(f"BFWS corpus trace audit failed: {row['instance_id']}")
    return BFWSCorpusTrace(tuple(process_rows), tuple(operational_rows), tuple(training_rows), audit)


def run_frozen_bfws_corpus_release(
    *,
    trace_manifest_path: str | Path,
    request: GenerationRequest,
    phase_gate: BFWSPhaseGate,
    resume: bool,
    progress: Callable[[str], None] | None = None,
) -> GenerationRunReceipt:
    """Materialize or resume the complete authorized BFWS corpus release."""

    def execute() -> dict[str, object]:
        phase_gate.require_run(stage="corpus_release", contract_id=request.binding.contract_id)
        output_root = Path(request.binding.output_root).resolve()
        if output_root.exists() and not resume:
            raise FileExistsError(f"BFWS corpus output already exists: {output_root}; pass resume=True")
        output_root.mkdir(parents=True, exist_ok=True)
        manifest_path = output_root / _MANIFEST_PATH
        if manifest_path.is_file():
            manifest = verify_frozen_bfws_corpus_release(
                trace_manifest_path=trace_manifest_path,
                corpus_root=output_root,
                phase_gate=phase_gate,
                progress=progress,
            )
            return _execution_result(manifest_path, manifest)

        source_path = Path(trace_manifest_path).resolve()
        trace_root = source_path.parent.parent
        manifest = _validated_trace_manifest(source_path, phase_gate)
        rows = preflight_frozen_bfws_trace_generation(phase_gate)
        rows_by_id = {row["instance_id"]: row for row in rows}
        items = cast(list[dict[str, Any]], manifest["traces"])
        items.sort(key=lambda item: _trace_sort_key(rows_by_id[str(item["instance_id"])]))
        result = _materialize_release(
            items=items,
            rows_by_id=rows_by_id,
            trace_root=trace_root,
            output_root=output_root,
            phase_gate=phase_gate,
            resume=resume,
            progress=progress,
        )
        _atomic_write(manifest_path, _canonical_bytes(result))
        verify_frozen_bfws_corpus_release(
            trace_manifest_path=trace_manifest_path,
            corpus_root=output_root,
            phase_gate=phase_gate,
            progress=progress,
        )
        return _execution_result(manifest_path, result)

    return run_authorized_generation(request, execute)


def verify_frozen_bfws_corpus_release(
    *,
    trace_manifest_path: str | Path,
    corpus_root: str | Path,
    phase_gate: BFWSPhaseGate,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Regenerate every corpus shard and require byte-identical retained artifacts."""

    phase_gate.require_run(stage="corpus_release", contract_id=phase_gate.phase_id)
    root = Path(corpus_root).resolve()
    retained = _json_object((root / _MANIFEST_PATH).read_bytes(), "BFWS corpus release manifest")
    source_path = Path(trace_manifest_path).resolve()
    trace_root = source_path.parent.parent
    source = _validated_trace_manifest(source_path, phase_gate)
    rows = preflight_frozen_bfws_trace_generation(phase_gate)
    rows_by_id = {row["instance_id"]: row for row in rows}
    items = cast(list[dict[str, Any]], source["traces"])
    items.sort(key=lambda item: _trace_sort_key(rows_by_id[str(item["instance_id"])]))
    with tempfile.TemporaryDirectory(prefix="bfws-corpus-regeneration-") as temporary:
        regenerated_root = Path(temporary) / "release"
        regenerated_root.mkdir()
        regenerated = _materialize_release(
            items=items,
            rows_by_id=rows_by_id,
            trace_root=trace_root,
            output_root=regenerated_root,
            phase_gate=phase_gate,
            resume=False,
            progress=progress,
        )
        _atomic_write(regenerated_root / _MANIFEST_PATH, _canonical_bytes(regenerated))
        if not _trees_equal(root, regenerated_root):
            raise ValueError("BFWS corpus release regeneration is not byte-identical")
    if retained != regenerated:
        raise ValueError("BFWS corpus release manifest regeneration differs")
    return retained


def _materialize_release(
    *,
    items: list[dict[str, Any]],
    rows_by_id: Mapping[str, Mapping[str, Any]],
    trace_root: Path,
    output_root: Path,
    phase_gate: BFWSPhaseGate,
    resume: bool,
    progress: Callable[[str], None] | None,
) -> dict[str, Any]:
    artifacts: dict[str, int] = {}
    process_curriculum: list[dict[str, Any]] = []
    operational_curriculum: list[dict[str, Any]] = []
    split_rows: list[dict[str, Any]] = []
    input_digests: dict[str, set[str]] = {"train": set(), "dev": set()}
    pair_digests: dict[str, set[str]] = {"train": set(), "dev": set()}
    identities: dict[str, set[str]] = {"train": set(), "dev": set()}
    targets_by_input: dict[str, set[str]] = {}
    totals = {
        "decision_count": 0,
        "future_step_leakage_count": 0,
        "input_over_budget_count": 0,
        "live_training_input_mismatch_count": 0,
        "operational_record_count": 0,
        "rolling_context_deltas_dropped": 0,
        "target_over_budget_count": 0,
        "target_parse_rejection_count": 0,
        "teacher_decision_rejection_count": 0,
    }
    max_input_bytes = 0
    max_input_tokens = 0
    max_target_tokens = 0
    held_out_instances = sum(str(item.get("split")) not in {"train", "dev"} for item in items)
    started = monotonic()
    completed_decisions = 0
    total_decisions = sum(int(row["exact_reference_decision_count"]) for row in rows_by_id.values())

    for trace_index, item in enumerate(items, start=1):
        instance_id = str(item["instance_id"])
        row = rows_by_id[instance_id]
        shard = materialize_frozen_bfws_corpus_trace(
            row=row,
            trace_item=item,
            trace_root=trace_root,
            phase_gate=phase_gate,
        )
        split = str(row["split"])
        domain = str(row["domain_id"])
        difficulty = str(row["difficulty"])
        base = Path(split) / domain / difficulty / instance_id
        shard_payloads = {
            (Path("corpus/process") / base).with_suffix(".jsonl").as_posix(): _jsonl_bytes(shard.process_rows),
            (Path("corpus/operational") / base).with_suffix(".jsonl").as_posix(): _jsonl_bytes(
                shard.operational_rows
            ),
            (Path("training/process") / base).with_suffix(".jsonl").as_posix(): _jsonl_bytes(
                shard.training_rows
            ),
        }
        for relative_path, payload in shard_payloads.items():
            _write_or_verify(output_root / relative_path, payload, resume=resume)
            artifacts[relative_path] = len(payload)

        identity = str(row["semantic_task_identity"])
        identities[split].add(identity)
        split_rows.append(
            {
                "assignment_id": split_assignment_id(identity, split),
                "identity": identity,
                "split": split,
            }
        )
        for process in shard.process_rows:
            input_bytes = _canonical_bytes(process["input"])
            target_bytes = _canonical_bytes(process["target"])
            input_digest = hashlib.sha256(input_bytes).hexdigest()
            target_digest = hashlib.sha256(target_bytes).hexdigest()
            input_digests[split].add(input_digest)
            pair_digests[split].add(hashlib.sha256(input_bytes + target_bytes).hexdigest())
            targets_by_input.setdefault(input_digest, set()).add(target_digest)
            process_curriculum.append(_curriculum_row(process, len(process_curriculum)))
        for operational in shard.operational_rows:
            operational_curriculum.append(_curriculum_row(operational, len(operational_curriculum)))
        for name in totals:
            totals[name] += int(shard.audit[name])
        max_input_bytes = max(max_input_bytes, int(shard.audit["max_input_bytes"]))
        max_input_tokens = max(max_input_tokens, int(shard.audit["max_input_tokens"]))
        max_target_tokens = max(max_target_tokens, int(shard.audit["max_target_tokens"]))
        completed_decisions += int(shard.audit["decision_count"])
        elapsed = monotonic() - started
        eta = 0.0 if completed_decisions == total_decisions else elapsed * (
            total_decisions - completed_decisions
        ) / completed_decisions
        _report(
            progress,
            f"[{trace_index}/{len(items)}] materialized {instance_id}; "
            f"{completed_decisions}/{total_decisions} decisions; elapsed {_duration(elapsed)}; ETA {_duration(eta)}",
        )

    semantic_overlap = identities["train"] & identities["dev"]
    input_overlap = input_digests["train"] & input_digests["dev"]
    pair_overlap = pair_digests["train"] & pair_digests["dev"]
    conflicting_inputs = sum(len(targets) > 1 for targets in targets_by_input.values())
    corpus = phase_gate.components["corpus"]
    audit = {
        "accepted_delta_limit": corpus["accepted_delta_limit"],
        "canonical_input_overlap_count": len(input_overlap),
        "future_step_leakage_count": totals["future_step_leakage_count"],
        "held_out_instance_count": held_out_instances,
        "identical_input_conflicting_target_count": conflicting_inputs,
        "input_over_budget_count": totals["input_over_budget_count"],
        "input_target_overlap_count": len(pair_overlap),
        "live_training_input_mismatch_count": totals["live_training_input_mismatch_count"],
        "max_input_bytes": max_input_bytes,
        "max_input_tokens": max_input_tokens,
        "max_target_tokens": max_target_tokens,
        "model_input_byte_preference": corpus["model_input_byte_preference"],
        "model_input_token_limit": corpus["model_input_token_limit"],
        "model_output_token_limit": corpus["model_output_token_limit"],
        "rolling_context_deltas_dropped": totals["rolling_context_deltas_dropped"],
        "schema_version": _AUDIT_SCHEMA,
        "semantic_task_overlap_count": len(semantic_overlap),
        "status": "passed",
        "target_over_budget_count": totals["target_over_budget_count"],
        "target_parse_rejection_count": totals["target_parse_rejection_count"],
        "teacher_decision_rejection_count": totals["teacher_decision_rejection_count"],
    }
    required = phase_gate.components["corpus"]["required_audit_results"]
    if any(audit.get(name) != expected for name, expected in required.items()):
        raise ValueError("BFWS corpus release failed its frozen zero-error audit")
    if totals["decision_count"] != 69_019 or len(split_rows) != 105:
        raise ValueError("BFWS corpus release differs from its frozen coverage")

    process_curriculum.sort(key=_curriculum_sort_key)
    operational_curriculum.sort(key=_curriculum_sort_key)
    for index, curriculum in enumerate(process_curriculum):
        curriculum["curriculum_index"] = index
    for index, curriculum in enumerate(operational_curriculum):
        curriculum["curriculum_index"] = index
    split_rows.sort(key=lambda item: cast(str, item["identity"]))
    aggregate = {
        _PROCESS_CURRICULUM_PATH.as_posix(): _jsonl_bytes(process_curriculum),
        _OPERATIONAL_CURRICULUM_PATH.as_posix(): _jsonl_bytes(operational_curriculum),
        _SPLIT_LEDGER_PATH.as_posix(): _jsonl_bytes(split_rows),
        _AUDIT_PATH.as_posix(): _canonical_bytes(audit),
    }
    training_artifacts = [
        {"path": path, "size_bytes": size_bytes}
        for path, size_bytes in sorted(artifacts.items())
        if path.startswith("training/process/")
    ]
    training_manifest = {
        "artifacts": training_artifacts,
        "counts": {
            split: sum(
                int(row["exact_reference_decision_count"])
                for row in rows_by_id.values()
                if row["split"] == split
            )
            for split in ("train", "dev")
        },
        "framework": {"name": "ms-swift", "version": "4.2.2"},
        "phase_receipt": phase_gate.receipt(stage="process_sft_training"),
        "schema_version": _TRAINING_SCHEMA,
        "source_view": "process",
    }
    aggregate[_TRAINING_MANIFEST_PATH.as_posix()] = _canonical_bytes(training_manifest)
    for relative_path, payload in aggregate.items():
        _write_or_verify(output_root / relative_path, payload, resume=resume)
        artifacts[relative_path] = len(payload)

    source_manifest = trace_root / "manifests" / "bfws-expert-traces.json"
    source_audit = trace_root / "manifests" / "bfws-trace-audit.json"
    release = {
        "artifacts": [
            {"path": path, "size_bytes": size_bytes} for path, size_bytes in sorted(artifacts.items())
        ],
        "byte_identical_regeneration_required": corpus["byte_identical_regeneration_required"],
        "counts": {
            "operational_records": totals["operational_record_count"],
            "process_records": totals["decision_count"],
            "split_assignments": len(split_rows),
            "strata": len({(row["domain_id"], row["difficulty"]) for row in rows_by_id.values()}),
            "training_projection_records": totals["decision_count"],
        },
        "phase_receipt": phase_gate.receipt(stage="corpus_release"),
        "rolling_context": {
            "accepted_delta_limit": corpus["accepted_delta_limit"],
            "model_input_token_limit": corpus["model_input_token_limit"],
            "model_output_token_limit": corpus["model_output_token_limit"],
            "projection": corpus["model_input_schema"],
        },
        "schema_version": _RELEASE_SCHEMA,
        "segment_alignment": corpus["segment_alignment"],
        "source_trace_audit_path": _stable_path(source_audit),
        "source_trace_manifest_path": _stable_path(source_manifest),
        "split_unit": corpus["split_unit"],
        "views": corpus["views"],
    }
    return release


def _validated_trace_manifest(path: Path, phase_gate: BFWSPhaseGate) -> dict[str, Any]:
    manifest = _json_object(path.read_bytes(), "BFWS expert trace manifest")
    coverage = manifest.get("coverage")
    if (
        manifest.get("schema_version") != "bfws_expert_trace_generation_v1"
        or manifest.get("phase_receipt") != phase_gate.receipt(stage="trace_generation")
        or not isinstance(coverage, Mapping)
        or coverage.get("instance_count") != 105
        or coverage.get("exact_reference_decision_count") != 69_019
        or coverage.get("stratum_count") != 35
        or not isinstance(manifest.get("traces"), list)
    ):
        raise ValueError("BFWS corpus source trace manifest differs from issue #57")
    frozen_ids = {
        str(row["instance_id"])
        for row in preflight_frozen_bfws_trace_generation(phase_gate)
    }
    trace_ids = [
        item.get("instance_id") if isinstance(item, Mapping) else None
        for item in manifest["traces"]
    ]
    if len(set(trace_ids)) != len(trace_ids) or set(trace_ids) != frozen_ids:
        raise ValueError("BFWS corpus source traces do not exactly cover the frozen development panel")
    audit = _json_object((path.parent / "bfws-trace-audit.json").read_bytes(), "BFWS trace audit")
    if (
        audit.get("schema_version") != "bfws_trace_release_audit_v1"
        or audit.get("decision_count") != 69_019
        or any(audit.get("audit_results", {}).values())
        or audit.get("source_trace_manifest_path") != "manifests/bfws-expert-traces.json"
    ):
        raise ValueError("BFWS corpus source trace audit is not a complete zero-error release")
    return manifest


def _record_metadata(
    row: Mapping[str, Any],
    trace_item: Mapping[str, Any],
    *,
    assignment_id: str,
    record_index: int,
) -> dict[str, Any]:
    return {
        "algorithm": "best_first_width",
        "difficulty": row["difficulty"],
        "domain_id": row["domain_id"],
        "expert_evidence": {
            "episode_path": trace_item["evidence"]["path"],
            "trace_record_index": record_index,
        },
        "instance_id": row["instance_id"],
        "schema_version": _RECORD_SCHEMA,
        "split": row["split"],
        "split_assignment_id": assignment_id,
        "trace_record_index": record_index,
        "whole_instance_id": row["semantic_task_identity"],
    }


def _checkpoint_from_observation(
    observation: Mapping[str, Any],
    authority_id: str,
) -> _CorpusCheckpoint:
    memory = observation.get("search_memory")
    if not isinstance(memory, Mapping):
        raise ValueError("BFWS corpus observation Search Memory is malformed")
    frontier_size = memory.get("frontier_size")
    visited_count = memory.get("visited_count")
    known_state_count = memory.get("known_state_count")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (frontier_size, visited_count, known_state_count)
    ):
        raise ValueError("BFWS corpus observation Search Memory counts are malformed")
    assert isinstance(frontier_size, int)
    assert isinstance(visited_count, int)
    assert isinstance(known_state_count, int)
    head = memory.get("frontier_head")
    frontier = () if frontier_size == 0 else (str(head), *(f"frontier:{index}" for index in range(1, frontier_size)))
    return _CorpusCheckpoint(
        authority_id=authority_id,
        snapshot=_CorpusSnapshot(
            frontier=frontier,
            visited=frozenset(f"visited:{index}" for index in range(visited_count)),
            known_states={f"known:{index}": None for index in range(known_state_count)},
        ),
    )


def _accepted_delta(
    record_index: int,
    operation: SearchTransitionRequest | SearchRetireRequest,
    result: Mapping[str, Any],
) -> AcceptedSearchDelta | None:
    if result.get("status") == "retired":
        if not isinstance(operation, SearchRetireRequest):
            raise ValueError("BFWS retired corpus record has the wrong operation")
        return None
    if result.get("status") != "accepted" or not isinstance(operation, SearchTransitionRequest):
        raise ValueError("BFWS corpus source contains a rejected or malformed teacher decision")
    payload = result["transition"]
    source = _canonical_state(payload["source_state"])
    target = _canonical_state(payload["target_state"])
    action = GroundedAction(payload["action"]["name"], tuple(payload["action"]["args"]))
    provenance = TransitionProvenance(source.authority_id, source.state_id, action, target.state_id)
    if provenance.provenance_id != payload["provenance"]["provenance_id"]:
        raise ValueError("BFWS corpus transition provenance differs from its replay-verified trace")
    evaluation = result["evaluation"]
    return AcceptedSearchDelta(
        record_index=record_index,
        operation=operation,
        transition=PDDLTransition(source, action, target, provenance),
        evaluation=StateEvaluation(
            novelty=int(evaluation["novelty"]),
            heuristic=HeuristicValue(
                str(evaluation["heuristic"]["name"]),
                int(evaluation["heuristic"]["value"]),
            ),
        ),
    )


def _canonical_state(payload: Mapping[str, Any]) -> CanonicalState:
    state = CanonicalState(
        tuple(payload["atoms"]),
        str(payload["authority_id"]),
        tuple(payload["fluents"]),
    )
    if state.state_id != payload["state_id"]:
        raise ValueError("BFWS corpus transition state ID is not canonical")
    return state


def _curriculum_row(row: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "curriculum_index": index,
        "difficulty": row["difficulty"],
        "record_id": row["record_id"],
        "schema_version": _CURRICULUM_SCHEMA,
        "split": row["split"],
        "stage_index": _DIFFICULTY_ORDER[str(row["difficulty"])],
        "view": row["view"],
    }


def _curriculum_sort_key(row: Mapping[str, Any]) -> tuple[int, str, str]:
    return (
        int(row["stage_index"]),
        str(row["split"]),
        str(row["record_id"]),
    )


def _trace_sort_key(row: Mapping[str, Any]) -> tuple[int, str, str, str]:
    return (
        _DIFFICULTY_ORDER[str(row["difficulty"])],
        str(row["domain_id"]),
        str(row["split"]),
        str(row["instance_id"]),
    )


def _artifact_path(root: Path, item: Mapping[str, Any], field: str) -> Path:
    artifact = item.get(field)
    if not isinstance(artifact, Mapping):
        raise ValueError(f"BFWS trace item is missing {field}")
    relative = Path(str(artifact.get("path")))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("BFWS trace artifact path escapes its release")
    path = root / relative
    if not path.is_file() or path.stat().st_size != artifact.get("size_bytes"):
        raise ValueError(f"BFWS trace artifact differs: {relative}")
    return path


def _execution_result(path: Path, manifest: Mapping[str, Any]) -> dict[str, object]:
    counts = manifest["counts"]
    return {
        "corpus_manifest_path": str(path.resolve()),
        "corpus_manifest_size_bytes": path.stat().st_size,
        "byte_identical_regeneration": True,
        "operational_record_count": counts["operational_records"],
        "process_record_count": counts["process_records"],
        "split_assignment_count": counts["split_assignments"],
        "training_projection_record_count": counts["training_projection_records"],
    }


def _write_or_verify(path: Path, payload: bytes, *, resume: bool) -> None:
    if path.is_file():
        if not resume:
            raise FileExistsError(f"BFWS corpus artifact already exists: {path}")
        if path.read_bytes() != payload:
            raise ValueError(f"BFWS resumed corpus artifact differs: {path}")
        return
    _atomic_write(path, payload)


def _trees_equal(left: Path, right: Path) -> bool:
    left_paths = [path.relative_to(left) for path in sorted(left.rglob("*")) if path.is_file()]
    right_paths = [path.relative_to(right) for path in sorted(right.rglob("*")) if path.is_file()]
    if left_paths != right_paths:
        return False
    for relative in left_paths:
        with (left / relative).open("rb") as left_stream, (right / relative).open("rb") as right_stream:
            while True:
                left_chunk = left_stream.read(1024 * 1024)
                if left_chunk != right_stream.read(1024 * 1024):
                    return False
                if not left_chunk:
                    break
    return True


def _stable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _json_object(payload: bytes, name: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{name} is invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _jsonl_bytes(rows: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(row) for row in rows)


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


__all__ = [
    "BFWSCorpusTrace",
    "materialize_frozen_bfws_corpus_trace",
    "run_frozen_bfws_corpus_release",
    "verify_frozen_bfws_corpus_release",
]
