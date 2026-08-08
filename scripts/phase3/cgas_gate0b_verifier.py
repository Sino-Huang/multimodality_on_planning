from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from . import cgas_trace_contract_v3
from .cgas_candidate_characterization_contracts import (
    CandidateCharacterizationError,
    confined,
    model_bytes,
    parse_canonical_model,
    selector_binding,
    validate_approval,
)
from .cgas_candidate_characterization_models import (
    CheckpointModel,
    CurrentIndexModel,
    JsonObject,
    TraceBindingModel,
)
from .cgas_candidate_characterization_publication import CheckpointEntry, scan_chain
from .cgas_candidate_characterization_replay import validate_external_bindings
from .cgas_candidate_characterization_traces import trace_binding
from .cgas_candidate_contracts import load_config
from .cgas_trace_stream_v2 import TraceVerification, verify_trace_stream


@dataclass(frozen=True, slots=True)
class Gate0bStreamSummary:
    path: Path
    planner: str
    contract_id: str
    contract_sha256: str
    record_count: int
    completion_status: str
    success_plan_sha256: str | None
    byte_count: int


@dataclass(frozen=True, slots=True)
class Gate0bReport:
    round: int
    checkpoint_path: Path
    checkpoint_sha256: str
    accounting_row_count: int
    candidate_count: int
    stream_count: int
    total_stream_bytes: int
    streams: tuple[Gate0bStreamSummary, ...]


def verify_gate0b_round(
    repository_root: Path,
    output_root: Path,
    approved_trace_contract: Path,
    candidate_config: Path,
    checkpoint_path: Path | None = None,
) -> Gate0bReport:
    """Verify one isolated trace-v3 round without mutating its files."""
    approval, approval_digest = validate_approval(approved_trace_contract)
    config = load_config(candidate_config)
    chain = scan_chain(output_root, repository_root)
    if len(chain) != 1 or chain[0].checkpoint.round != 1:
        raise CandidateCharacterizationError("gate0b_checkpoint_chain_invalid", output_root)
    entry = chain[0]
    if checkpoint_path is not None and checkpoint_path.resolve() != entry.path.resolve():
        raise CandidateCharacterizationError("gate0b_checkpoint_path_invalid", checkpoint_path)
    checkpoint = entry.checkpoint
    validate_external_bindings(entry, approval_digest, approval.contract_sha256, config.sha256, selector_binding())
    if (
        checkpoint.predecessor_checkpoint_sha256 is not None
        or checkpoint.approved_trace_sha256 != approval_digest
        or checkpoint.approved_trace_contract_sha256 != cgas_trace_contract_v3.NEW_CONTRACT_SHA256
    ):
        raise CandidateCharacterizationError("gate0b_checkpoint_binding_invalid", entry.path)
    _verify_current_index(repository_root, output_root, entry)
    rows = _artifact_rows(checkpoint, entry.path)
    stream_summaries = tuple(
        _verify_row_streams(repository_root, row, entry.path, approval_digest) for row in rows
    )
    flattened = tuple(item for pair in stream_summaries for item in pair)
    bound_paths = {item.path.resolve() for item in flattened}
    actual_paths = {path.resolve() for path in (output_root / "traces").rglob("*.jsonl")}
    if bound_paths != actual_paths:
        raise CandidateCharacterizationError("gate0b_stream_set_invalid", output_root / "traces")
    return Gate0bReport(
        checkpoint.round,
        entry.path,
        entry.digest,
        checkpoint.accounting.row_count,
        checkpoint.characterization.row_count,
        len(flattened),
        sum(item.byte_count for item in flattened),
        flattened,
    )


def _verify_current_index(repository_root: Path, output_root: Path, entry: CheckpointEntry) -> None:
    path = output_root / "current.json"
    parsed, contents = parse_canonical_model(path, CurrentIndexModel, "gate0b_current_index_invalid")
    checkpoint_path = entry.path.resolve().relative_to(repository_root.resolve()).as_posix()
    expected = CurrentIndexModel(checkpoint_path=checkpoint_path, checkpoint_sha256=entry.digest, round=1)
    if parsed != expected or contents != model_bytes(expected) + b"\n":
        raise CandidateCharacterizationError("gate0b_current_index_invalid", path)


def _artifact_rows(checkpoint: CheckpointModel, path: Path) -> tuple[JsonObject, ...]:
    contents = checkpoint.characterization.canonical_jsonl.encode()
    if hashlib.sha256(contents).hexdigest() != checkpoint.characterization.sha256:
        raise CandidateCharacterizationError("gate0b_characterization_digest_invalid", path)
    try:
        rows = tuple(TypeAdapter(JsonObject).validate_json(line) for line in contents.splitlines())
    except ValidationError as error:
        raise CandidateCharacterizationError("gate0b_characterization_rows_invalid", path) from error
    if len(rows) != checkpoint.characterization.row_count:
        raise CandidateCharacterizationError("gate0b_characterization_count_invalid", path)
    return rows


def _verify_row_streams(
    repository_root: Path,
    row: JsonObject,
    error_path: Path,
    approval_digest: str,
) -> tuple[Gate0bStreamSummary, ...]:
    summaries: list[Gate0bStreamSummary] = []
    for planner, row_key in (("bfs", "bfs"), ("iw", "iw_width_1")):
        planner_value = row.get(row_key)
        if not isinstance(planner_value, dict):
            raise CandidateCharacterizationError("gate0b_planner_binding_invalid", error_path)
        if (
            row.get("approved_trace_sha256") != approval_digest
            or row.get("trace_contract_sha256") != cgas_trace_contract_v3.NEW_CONTRACT_SHA256
            or row.get("trace_policy_sha256") != cgas_trace_contract_v3.POLICY_SHA256
        ):
            raise CandidateCharacterizationError("gate0b_row_contract_binding_invalid", error_path)
        value = planner_value.get("trace_v3")
        try:
            binding = TraceBindingModel.model_validate(value)
            relative = Path(binding.path)
            path = repository_root / relative
            if confined(path, repository_root) != relative or binding.planner != planner:
                raise CandidateCharacterizationError("gate0b_stream_binding_invalid", error_path)
            verification = verify_trace_stream(path)
        except (ValidationError, CandidateCharacterizationError, OSError) as error:
            raise CandidateCharacterizationError("gate0b_stream_binding_invalid", error_path) from error
        if (
            verification.contract_id != cgas_trace_contract_v3.CONTRACT_ID
            or verification.contract_sha256 != cgas_trace_contract_v3.NEW_CONTRACT_SHA256
        ):
            raise CandidateCharacterizationError("gate0b_stream_contract_invalid", path)
        if binding != trace_binding(repository_root, path, verification):
            raise CandidateCharacterizationError("gate0b_stream_binding_invalid", error_path)
        summaries.append(_summary(path, verification))
    return tuple(summaries)


def _summary(path: Path, verification: TraceVerification) -> Gate0bStreamSummary:
    return Gate0bStreamSummary(
        path,
        verification.planner,
        verification.contract_id,
        verification.contract_sha256,
        verification.record_count,
        verification.completion_status,
        verification.success_plan_sha256,
        path.stat().st_size,
    )
