from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .cgas_characterization_types import (
    CanonicalRowIndex,
    CharacterizationArtifactDigest,
    CharacterizationTypeError,
    SourceManifestDigest,
    parse_canonical_row_index,
    parse_characterization_artifact_digest,
    parse_source_manifest_digest,
)
from .cgas_serialization import canonical


_CHECKPOINT_LIMIT: Final = 480


@dataclass(frozen=True, slots=True)
class CheckpointExpectation:
    run_fingerprint: SourceManifestDigest
    row_index: CanonicalRowIndex
    instance_id: str
    row_digest: CharacterizationArtifactDigest


@dataclass(frozen=True, slots=True)
class Checkpoint:
    expectation: CheckpointExpectation
    canonical_bytes: bytes
    row: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class CheckpointError(RuntimeError):
    rule: str
    path: Path
    residue: Path | None = None

    def __str__(self) -> str:
        suffix = f"; residue={self.residue}" if self.residue is not None else ""
        return f"checkpoint {self.rule}: {self.path}{suffix}"


def checkpoint_name(row_index: CanonicalRowIndex) -> str:
    try:
        index = parse_canonical_row_index(row_index)
    except CharacterizationTypeError as error:
        raise CheckpointError("row index is not canonical", Path(str(row_index))) from error
    if index > _CHECKPOINT_LIMIT:
        raise CheckpointError("row index is outside checkpoint range", Path(str(index)))
    return f"{index:04d}.json"


def normalize_expectation(expectation: CheckpointExpectation) -> CheckpointExpectation:
    try:
        return CheckpointExpectation(
            parse_source_manifest_digest(expectation.run_fingerprint),
            parse_canonical_row_index(expectation.row_index),
            expectation.instance_id,
            parse_characterization_artifact_digest(expectation.row_digest),
        )
    except CharacterizationTypeError as error:
        raise CheckpointError("checkpoint expectation is invalid", Path(expectation.instance_id)) from error


def envelope(expected: CheckpointExpectation, row: dict[str, object] | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "instance_id": expected.instance_id,
        "row_digest": str(expected.row_digest),
        "row_index": int(expected.row_index),
        "run_fingerprint": str(expected.run_fingerprint),
    }
    if row is not None:
        result["row"] = canonical(row)
    return result


def external_private_root(root: Path, private_root: Path) -> tuple[Path, Path]:
    if private_root.is_symlink():
        raise CheckpointError("checkpoint private root must not be a symlink", private_root)
    try:
        canonical_root = root.resolve(strict=True)
        canonical_private_root = private_root.resolve(strict=True)
    except OSError as error:
        raise CheckpointError("checkpoint roots must resolve canonically", private_root) from error
    if _contains(canonical_root, canonical_private_root) or _contains(canonical_private_root, canonical_root):
        raise CheckpointError("checkpoint private root must be external to checkpoint root", canonical_private_root)
    return canonical_root, canonical_private_root


def _contains(ancestor: Path, descendant: Path) -> bool:
    try:
        descendant.relative_to(ancestor)
    except ValueError:
        return False
    return True
