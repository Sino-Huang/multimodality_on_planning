from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from .cgas_candidate_characterization_contracts import (
    CandidateCharacterizationError,
    sha256,
)
from .cgas_candidate_characterization_models import (
    AccountingBindingModel,
    AccountingCountsModel,
    AccountingRowModel,
    ArtifactBindingModel,
    CheckpointModel,
    JsonObject,
    JsonValue,
    RangeBindingModel,
    ReservoirBindingModel,
    SelectorBindingModel,
    StreamCursorModel,
)


@dataclass(frozen=True, slots=True)
class CheckpointBuildRequest:
    repository_root: Path
    round: int
    predecessor_sha256: str | None
    feedback_sha256: str | None
    approved_trace_sha256: str
    approved_trace_contract_sha256: str
    candidate_config_sha256: str
    selector: SelectorBindingModel
    previous: CheckpointModel | None
    streams: tuple[StreamCursorModel, ...]
    accounting: tuple[AccountingRowModel, ...]
    characterizations: tuple[JsonObject, ...]
    ranges: tuple[RangeBindingModel, ...]


def build_checkpoint(request: CheckpointBuildRequest) -> CheckpointModel:
    previous_accounting = _artifact_rows(request.previous.accounting) if request.previous else ()
    previous_characterizations = _artifact_rows(request.previous.characterization) if request.previous else ()
    accounting = tuple(
        sorted(
            (*previous_accounting, *(_accounting_record(row) for row in request.accounting)),
            key=lambda row: (_integer(row, "object_count"), _integer(row, "raw_rank")),
        )
    )
    characterizations = tuple(
        sorted(
            (*previous_characterizations, *request.characterizations),
            key=lambda row: _text(row, "candidate_id"),
        )
    )
    _require_unique_accounting(accounting)
    _require_unique_characterizations(characterizations)
    expected_candidates = {row.candidate_id for row in request.accounting if row.status == "emitted"}
    actual_candidates = {_text(row, "candidate_id") for row in request.characterizations}
    if actual_candidates != expected_candidates:
        raise CandidateCharacterizationError("emitted_characterization_incomplete", Path("characterization"))
    reservoir = tuple(row for row in characterizations if _paired_exact(row))
    status_counts = Counter(_text(row, "status") for row in accounting)
    prior_ranges = tuple(request.previous.ranges) if request.previous else ()
    checkpoint = CheckpointModel(
        accounting=AccountingBindingModel(
            **_artifact(accounting).model_dump(),
            counts=AccountingCountsModel(
                duplicate=status_counts["duplicate"],
                emitted=status_counts["emitted"],
                solved=status_counts["solved"],
            ),
        ),
        approved_trace_contract_sha256=request.approved_trace_contract_sha256,
        approved_trace_sha256=request.approved_trace_sha256,
        candidate_config_sha256=request.candidate_config_sha256,
        characterization=_artifact(characterizations),
        feedback_sha256=request.feedback_sha256,
        predecessor_checkpoint_sha256=request.predecessor_sha256,
        ranges=[*prior_ranges, *request.ranges],
        reservoir=_reservoir(reservoir),
        round=request.round,
        schema_version="cgas_candidate_characterization_checkpoint_v1",
        selector=request.selector,
        streams=list(request.streams),
    )
    validate_checkpoint(checkpoint, Path("checkpoint"), request.repository_root)
    return checkpoint


def validate_checkpoint(checkpoint: CheckpointModel, path: Path, repository_root: Path) -> None:
    accounting = _artifact_rows(checkpoint.accounting)
    characterizations = _artifact_rows(checkpoint.characterization)
    reservoir = _artifact_rows(checkpoint.reservoir)
    _require_unique_accounting(accounting)
    _require_unique_characterizations(characterizations)
    if checkpoint.accounting != AccountingBindingModel(
        **_artifact(accounting).model_dump(),
        counts=AccountingCountsModel(
            duplicate=sum(_text(row, "status") == "duplicate" for row in accounting),
            emitted=sum(_text(row, "status") == "emitted" for row in accounting),
            solved=sum(_text(row, "status") == "solved" for row in accounting),
        ),
    ):
        raise CandidateCharacterizationError("checkpoint_accounting_invalid", path)
    if checkpoint.characterization != _artifact(characterizations):
        raise CandidateCharacterizationError("checkpoint_characterization_invalid", path)
    if checkpoint.reservoir != _reservoir(tuple(row for row in characterizations if _paired_exact(row))):
        raise CandidateCharacterizationError("checkpoint_reservoir_invalid", path)
    if reservoir != tuple(row for row in characterizations if _paired_exact(row)):
        raise CandidateCharacterizationError("checkpoint_reservoir_invalid", path)
    if [stream.object_count for stream in checkpoint.streams] != [4, 8, 12]:
        raise CandidateCharacterizationError("checkpoint_streams_invalid", path)
    _validate_range_progression(checkpoint, accounting, path)
    from .cgas_candidate_characterization_traces import TraceValidationRequest, validate_trace_binding

    for row in characterizations:
        bfs = row.get("bfs")
        bfs_binding = bfs.get("trace_v2") if isinstance(bfs, dict) else None
        validate_trace_binding(TraceValidationRequest(repository_root, bfs_binding, "bfs", path))
        iw = row.get("iw_width_1")
        iw_binding = iw.get("trace_v2") if isinstance(iw, dict) else None
        validate_trace_binding(TraceValidationRequest(repository_root, iw_binding, "iw", path))


def _validate_range_progression(
    checkpoint: CheckpointModel,
    accounting: tuple[JsonObject, ...],
    path: Path,
) -> None:
    accounting_keys = {(_integer(row, "object_count"), _integer(row, "raw_rank")) for row in accounting}
    expected_keys: set[tuple[int, int]] = set()
    for stream in checkpoint.streams:
        ranges = [item for item in checkpoint.ranges if item.object_count == stream.object_count]
        next_rank = 0
        for item in ranges:
            if item.start_rank != next_rank or item.end_rank != item.start_rank + item.count:
                raise CandidateCharacterizationError("checkpoint_range_invalid", path)
            expected_keys.update((stream.object_count, rank) for rank in range(item.start_rank, item.end_rank))
            next_rank = item.end_rank
        if next_rank != stream.next_raw_rank:
            raise CandidateCharacterizationError("checkpoint_cursor_invalid", path)
    if accounting_keys != expected_keys:
        raise CandidateCharacterizationError("checkpoint_range_accounting_invalid", path)


def _artifact(rows: tuple[JsonObject, ...]) -> ArtifactBindingModel:
    contents = "".join(
        json.dumps(row, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n" for row in rows
    )
    return ArtifactBindingModel(canonical_jsonl=contents, row_count=len(rows), sha256=sha256(contents.encode()))


def _reservoir(rows: tuple[JsonObject, ...]) -> ReservoirBindingModel:
    artifact = _artifact(rows)
    signatures = sorted({_text(row, "composition_signature") for row in rows})
    return ReservoirBindingModel(
        **artifact.model_dump(),
        signature_count=len(signatures),
        signatures=signatures,
    )


def _artifact_rows(artifact: ArtifactBindingModel) -> tuple[JsonObject, ...]:
    contents = artifact.canonical_jsonl.encode()
    if sha256(contents) != artifact.sha256:
        raise CandidateCharacterizationError("artifact_digest_invalid", Path("checkpoint"))
    try:
        rows = tuple(TypeAdapter(JsonObject).validate_json(line) for line in contents.splitlines())
    except ValidationError as error:
        raise CandidateCharacterizationError("artifact_rows_invalid", Path("checkpoint")) from error
    if _artifact(rows) != ArtifactBindingModel(
        canonical_jsonl=artifact.canonical_jsonl,
        row_count=artifact.row_count,
        sha256=artifact.sha256,
    ):
        raise CandidateCharacterizationError("artifact_rows_invalid", Path("checkpoint"))
    return rows


def _accounting_record(row: AccountingRowModel) -> JsonObject:
    return TypeAdapter(JsonObject).validate_python(row.model_dump(mode="json"))


def _require_unique_accounting(rows: tuple[JsonObject, ...]) -> None:
    keys = tuple((_integer(row, "object_count"), _integer(row, "raw_rank")) for row in rows)
    if len(set(keys)) != len(keys) or keys != tuple(sorted(keys)):
        raise CandidateCharacterizationError("accounting_merge_key_invalid", Path("accounting"))


def _require_unique_characterizations(rows: tuple[JsonObject, ...]) -> None:
    candidate_ids = tuple(_text(row, "candidate_id") for row in rows)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise CandidateCharacterizationError("duplicate_candidate_characterization", Path("characterization"))


def _paired_exact(row: JsonObject) -> bool:
    if row.get("status") != "characterized":
        return False
    return all(_planner_exact(row.get(key)) for key in ("bfs", "iw_width_1"))


def _planner_exact(value: JsonValue | None) -> bool:
    if not isinstance(value, dict):
        return False
    exact = value.get("exact_search")
    replay = value.get("replay")
    return (
        isinstance(exact, dict)
        and isinstance(replay, dict)
        and value.get("source_eligibility") == "eligible_complete_trace"
        and exact.get("status") == "exact_solution_replayed"
        and replay.get("replay_ok") is True
        and replay.get("goal_satisfied") is True
    )


def _text(row: JsonObject, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise CandidateCharacterizationError(f"invalid_{key}", Path("checkpoint"))
    return value


def _integer(row: JsonObject, key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CandidateCharacterizationError(f"invalid_{key}", Path("checkpoint"))
    return value
