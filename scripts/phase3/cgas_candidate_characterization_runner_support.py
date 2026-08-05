from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

from .cgas_candidate_characterization_contracts import (
    CandidateCharacterizationError,
    confined,
    model_bytes,
    sha256,
)
from .cgas_candidate_characterization_models import CheckpointModel, JsonObject, PlannerInputModel, RangeBindingModel
from .cgas_candidate_characterization_ranges import CandidateBatch
from .cgas_trace_contract_v2 import POLICY_SHA256


def validate_paths(
    repository_root: Path,
    approval: Path,
    config: Path,
    candidate_root: Path,
    output: Path,
    checkpoint: Path | None,
    feedback: Path | None,
    round_number: int,
) -> None:
    if round_number < 1:
        raise CandidateCharacterizationError("round_invalid", output)
    for path in (repository_root, approval, config, candidate_root, output):
        confined(path, repository_root)
    if checkpoint is not None:
        confined(checkpoint, repository_root)
    if feedback is not None:
        confined(feedback, repository_root)


def validate_batch(batch: CandidateBatch, object_count: int, start: int, count: int, path: Path) -> None:
    if len(batch.accounting) != count or tuple(row.raw_rank for row in batch.accounting) != tuple(
        range(start, start + count)
    ):
        raise CandidateCharacterizationError("accounting_range_invalid", path)
    if any(row.object_count != object_count for row in batch.accounting):
        raise CandidateCharacterizationError("accounting_object_invalid", path)
    emitted = tuple(row.candidate_id for row in batch.accounting if row.status == "emitted")
    if tuple(planner.candidate_id for planner in batch.planner_inputs) != emitted:
        raise CandidateCharacterizationError("planner_inputs_not_emitted_only", path)


def validate_characterization(
    row: JsonObject,
    planner: PlannerInputModel,
    approval_digest: str,
    trace_contract_digest: str,
    path: Path,
) -> None:
    identity_matches = (
        text(row, "candidate_id") == planner.candidate_id
        and integer(row, "raw_rank") == planner.raw_rank
        and integer(row, "object_count") == planner.object_count
    )
    if not identity_matches:
        raise CandidateCharacterizationError("characterization_identity_invalid", path)
    if row.get("approved_trace_sha256") != approval_digest or row.get("trace_contract_sha256") != trace_contract_digest:
        raise CandidateCharacterizationError("characterization_trace_binding_invalid", path)
    if row.get("trace_policy_sha256") != POLICY_SHA256:
        raise CandidateCharacterizationError("characterization_trace_binding_invalid", path)
    source = row.get("source_identity")
    if not isinstance(source, dict) or source.get("source_record_sha256") != planner_input_sha256(planner):
        raise CandidateCharacterizationError("characterization_source_binding_invalid", path)
    if row.get("composition_signature") != planner.canonical_composition_signature:
        raise CandidateCharacterizationError("characterization_source_binding_invalid", path)


def range_binding(batch: CandidateBatch, object_count: int, start: int, count: int) -> RangeBindingModel:
    return RangeBindingModel(
        object_count=object_count,
        start_rank=start,
        count=count,
        end_rank=start + count,
        receipt_sha256=batch.receipt_sha256,
    )


def characterization_ids(checkpoint: CheckpointModel) -> set[str]:
    rows = (
        TypeAdapter(JsonObject).validate_json(line)
        for line in checkpoint.characterization.canonical_jsonl.splitlines()
        if line
    )
    return {text(row, "candidate_id") for row in rows}


def planner_input_sha256(planner: PlannerInputModel) -> str:
    return sha256(model_bytes(planner) + b"\n")


def text(row: JsonObject, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise CandidateCharacterizationError(f"invalid_{key}", Path("characterization"))
    return value


def integer(row: JsonObject, key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CandidateCharacterizationError(f"invalid_{key}", Path("characterization"))
    return value
