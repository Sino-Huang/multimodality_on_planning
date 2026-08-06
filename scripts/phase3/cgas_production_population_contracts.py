from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from .cgas_candidate_characterization_contracts import (
    CandidateCharacterizationError,
    parse_canonical_model,
    selector_binding,
    sha256,
)
from .cgas_candidate_characterization_models import (
    ArtifactBindingModel,
    CheckpointModel,
    CurrentIndexModel,
    JsonObject,
    JsonValue,
)
from .cgas_partition_selection import CALIBRATION_SIZE, SelectionFeasibilityError


@dataclass(frozen=True, slots=True)
class PopulationInput:
    path: Path
    checkpoint: CheckpointModel
    digest: str
    rows: tuple[JsonObject, ...]


def load_population_input(
    repository: Path,
    checkpoint_path: Path | None,
    index_path: Path | None,
) -> PopulationInput:
    if (checkpoint_path is None) == (index_path is None):
        raise CandidateCharacterizationError("exactly_one_checkpoint_input_required", Path("checkpoint"))
    if index_path is None:
        return _load_checkpoint(_repository_file(checkpoint_path or Path(), repository, "checkpoint_invalid"))
    canonical_index = _repository_file(index_path, repository, "current_index_invalid")
    if canonical_index.name != "current.json":
        raise CandidateCharacterizationError("current_index_path_invalid", canonical_index)
    index, _ = parse_canonical_model(canonical_index, CurrentIndexModel, "current_index_invalid")
    candidate = _repository_file(Path(index.checkpoint_path), repository, "current_index_path_invalid")
    try:
        candidate.relative_to(canonical_index.parent)
    except ValueError as error:
        raise CandidateCharacterizationError("current_index_path_invalid", canonical_index) from error
    if candidate.parent != canonical_index.parent / "checkpoints":
        raise CandidateCharacterizationError("current_index_path_invalid", canonical_index)
    loaded = _load_checkpoint(candidate)
    if loaded.checkpoint.round != index.round or loaded.digest != index.checkpoint_sha256:
        raise CandidateCharacterizationError("current_index_binding_invalid", canonical_index)
    return loaded


def diagnostics(population: PopulationInput) -> JsonObject:
    counts = Counter(_integer(row.get("object_count"), "object_count") for row in population.rows)
    value: JsonObject = {
        "calibration_required": CALIBRATION_SIZE,
        "object_counts": {str(key): counts[key] for key in sorted(counts)},
        "paired_exact_rows": len(population.rows),
        "reservoir_rows": population.checkpoint.reservoir.row_count,
        "signature_count": population.checkpoint.reservoir.signature_count,
    }
    return TypeAdapter(JsonObject).validate_python(value)


def _load_checkpoint(path: Path) -> PopulationInput:
    checkpoint, contents = parse_canonical_model(path, CheckpointModel, "checkpoint_invalid")
    expected = f"reservoir_checkpoint_{checkpoint.round:06d}.json"
    if path.name != expected or path.parent.name != "checkpoints":
        raise CandidateCharacterizationError("checkpoint_path_invalid", path)
    if checkpoint.selector != selector_binding():
        raise CandidateCharacterizationError("checkpoint_selector_binding_invalid", path)
    accounting = _artifact_rows(checkpoint.accounting, path)
    characterizations = _artifact_rows(checkpoint.characterization, path)
    reservoir = _artifact_rows(checkpoint.reservoir, path)
    emitted_ids = tuple(
        _text(row.get("candidate_id"), "candidate_id", path)
        for row in accounting
        if row.get("status") == "emitted"
    )
    characterized_ids = tuple(_text(row.get("candidate_id"), "candidate_id", path) for row in characterizations)
    if (
        len(set(emitted_ids)) != len(emitted_ids)
        or len(set(characterized_ids)) != len(characterized_ids)
        or set(emitted_ids) != set(characterized_ids)
    ):
        raise CandidateCharacterizationError("checkpoint_emitted_characterization_invalid", path)
    paired = tuple(row for row in characterizations if _paired_exact(row))
    if reservoir != paired:
        raise CandidateCharacterizationError("checkpoint_reservoir_invalid", path)
    signatures = sorted({_text(row.get("composition_signature"), "composition_signature", path) for row in reservoir})
    if signatures != checkpoint.reservoir.signatures or len(signatures) != checkpoint.reservoir.signature_count:
        raise CandidateCharacterizationError("checkpoint_reservoir_invalid", path)
    _validate_accounting(checkpoint, accounting, path)
    return PopulationInput(path, checkpoint, sha256(contents), reservoir)


def _artifact_rows(binding: ArtifactBindingModel, path: Path) -> tuple[JsonObject, ...]:
    contents = binding.canonical_jsonl.encode()
    if sha256(contents) != binding.sha256:
        raise CandidateCharacterizationError("checkpoint_artifact_invalid", path)
    try:
        rows = tuple(TypeAdapter(JsonObject).validate_json(line) for line in contents.splitlines())
    except ValidationError as error:
        raise CandidateCharacterizationError("checkpoint_artifact_invalid", path) from error
    if len(rows) != binding.row_count:
        raise CandidateCharacterizationError("checkpoint_artifact_invalid", path)
    return rows


def _validate_accounting(
    checkpoint: CheckpointModel,
    rows: tuple[JsonObject, ...],
    path: Path,
) -> None:
    keys = tuple(
        (_integer(row.get("object_count"), "object_count"), _integer(row.get("raw_rank"), "raw_rank"))
        for row in rows
    )
    if len(set(keys)) != len(keys) or keys != tuple(sorted(keys)):
        raise CandidateCharacterizationError("checkpoint_accounting_invalid", path)
    counts = Counter(_text(row.get("status"), "status", path) for row in rows)
    expected_counts = checkpoint.accounting.counts
    if (counts["duplicate"], counts["emitted"], counts["solved"]) != (
        expected_counts.duplicate,
        expected_counts.emitted,
        expected_counts.solved,
    ):
        raise CandidateCharacterizationError("checkpoint_accounting_invalid", path)
    expected_keys: set[tuple[int, int]] = set()
    for stream in checkpoint.streams:
        next_rank = 0
        for item in (item for item in checkpoint.ranges if item.object_count == stream.object_count):
            if item.start_rank != next_rank or item.end_rank != item.start_rank + item.count:
                raise CandidateCharacterizationError("checkpoint_range_invalid", path)
            expected_keys.update((stream.object_count, rank) for rank in range(item.start_rank, item.end_rank))
            next_rank = item.end_rank
        if next_rank != stream.next_raw_rank:
            raise CandidateCharacterizationError("checkpoint_cursor_invalid", path)
    if set(keys) != expected_keys:
        raise CandidateCharacterizationError("checkpoint_range_accounting_invalid", path)


def _repository_file(path: Path, repository: Path, code: str) -> Path:
    candidate = path if path.is_absolute() else repository / path
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(repository)
    except (OSError, ValueError) as error:
        raise CandidateCharacterizationError(code, path) from error
    if candidate.is_symlink() or not resolved.is_file():
        raise CandidateCharacterizationError(code, path)
    return resolved


def _paired_exact(row: JsonObject) -> bool:
    return row.get("status") == "characterized" and all(_planner_exact(row.get(key)) for key in ("bfs", "iw_width_1"))


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


def _text(value: JsonValue | None, label: str, path: Path) -> str:
    if not isinstance(value, str) or not value:
        raise CandidateCharacterizationError(f"invalid_{label}", path)
    return value


def _integer(value: JsonValue | None, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SelectionFeasibilityError(f"invalid_{label}")
    return value
