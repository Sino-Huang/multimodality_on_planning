from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .cgas_candidate_characterization_contracts import (
    CandidateCharacterizationError,
    model_bytes,
    sha256,
)
from .cgas_candidate_characterization_models import AccountingRowModel, PlannerInputModel
from .cgas_candidate_contracts import CandidateContractError
from .cgas_candidate_publication import materialize_slice, range_root


@dataclass(frozen=True, slots=True)
class RangeLoadRequest:
    candidate_config: Path
    candidate_root: Path
    object_count: int
    start_rank: int
    count: int


@dataclass(frozen=True, slots=True)
class CandidateBatch:
    accounting: tuple[AccountingRowModel, ...]
    planner_inputs: tuple[PlannerInputModel, ...]
    receipt_sha256: str


def load_candidate_batch(request: RangeLoadRequest) -> CandidateBatch:
    try:
        materialize_slice(
            request.candidate_config,
            request.candidate_root,
            request.object_count,
            request.start_rank,
            request.count,
        )
    except CandidateContractError as error:
        raise CandidateCharacterizationError(error.code, error.path or request.candidate_root) from error
    root = range_root(
        request.candidate_root,
        request.object_count,
        request.start_rank,
        request.count,
    )
    accounting = _accounting_rows(root / "raw-accounting.jsonl")
    planners = _planner_rows(root / "planner-inputs.jsonl")
    _validate_batch(request, accounting, planners, root)
    return CandidateBatch(accounting, planners, sha256((root / "receipt.json").read_bytes()))


def _accounting_rows(path: Path) -> tuple[AccountingRowModel, ...]:
    try:
        lines = path.read_bytes().splitlines(keepends=True)
        rows = tuple(AccountingRowModel.model_validate_json(line) for line in lines)
    except (OSError, ValidationError) as error:
        raise CandidateCharacterizationError("accounting_rows_invalid", path) from error
    if any(line != model_bytes(row) + b"\n" for line, row in zip(lines, rows, strict=True)):
        raise CandidateCharacterizationError("accounting_rows_invalid", path)
    return rows


def _planner_rows(path: Path) -> tuple[PlannerInputModel, ...]:
    try:
        lines = path.read_bytes().splitlines(keepends=True)
        rows = tuple(PlannerInputModel.model_validate_json(line) for line in lines)
    except (OSError, ValidationError) as error:
        raise CandidateCharacterizationError("planner_rows_invalid", path) from error
    if any(line != model_bytes(row) + b"\n" for line, row in zip(lines, rows, strict=True)):
        raise CandidateCharacterizationError("planner_rows_invalid", path)
    return rows


def _validate_batch(
    request: RangeLoadRequest,
    accounting: tuple[AccountingRowModel, ...],
    planners: tuple[PlannerInputModel, ...],
    root: Path,
) -> None:
    expected_ranks = tuple(range(request.start_rank, request.start_rank + request.count))
    if tuple(row.raw_rank for row in accounting) != expected_ranks:
        raise CandidateCharacterizationError("accounting_range_noncontiguous", root)
    if any(row.object_count != request.object_count for row in accounting):
        raise CandidateCharacterizationError("accounting_object_mismatch", root)
    emitted = tuple(row for row in accounting if row.status == "emitted")
    if len({row.candidate_id for row in emitted}) != len(emitted):
        raise CandidateCharacterizationError("duplicate_emitted_candidate", root)
    expected = tuple((row.object_count, row.raw_rank, row.candidate_id, row.first_raw_rank) for row in emitted)
    actual = tuple((row.object_count, row.raw_rank, row.candidate_id, row.first_raw_rank) for row in planners)
    if actual != expected:
        raise CandidateCharacterizationError("planner_rows_not_emitted_only", root)
