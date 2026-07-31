from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NewType, Protocol


CanonicalRowIndex = NewType("CanonicalRowIndex", int)
SourceManifestDigest = NewType("SourceManifestDigest", str)
CharacterizationArtifactDigest = NewType("CharacterizationArtifactDigest", str)


class CharacterizationTypeErrorReason(str, Enum):
    INVALID_DIGEST = "invalid_digest"
    INVALID_ROW_INDEX = "invalid_row_index"


@dataclass(frozen=True, slots=True)
class CharacterizationTypeError(ValueError):
    reason: CharacterizationTypeErrorReason
    value: str

    def __str__(self) -> str:
        return f"{self.reason.value}:{self.value}"


@dataclass(frozen=True, slots=True)
class CharacterizationRun:
    row_index: CanonicalRowIndex
    source_digest: SourceManifestDigest


@dataclass(frozen=True, slots=True)
class CharacterizationReport:
    run: CharacterizationRun
    artifact_digest: CharacterizationArtifactDigest
    row_count: int


class Characterizer(Protocol):
    def characterize(self, run: CharacterizationRun) -> CharacterizationReport:
        ...


def parse_canonical_row_index(raw: object) -> CanonicalRowIndex:
    match raw:
        case bool():
            raise CharacterizationTypeError(CharacterizationTypeErrorReason.INVALID_ROW_INDEX, str(raw))
        case int() if raw >= 0:
            return CanonicalRowIndex(raw)
        case int():
            raise CharacterizationTypeError(CharacterizationTypeErrorReason.INVALID_ROW_INDEX, str(raw))
        case _:
            raise CharacterizationTypeError(CharacterizationTypeErrorReason.INVALID_ROW_INDEX, _type_name(raw))


def parse_source_manifest_digest(raw: object) -> SourceManifestDigest:
    return SourceManifestDigest(_parse_sha256(raw))


def parse_characterization_artifact_digest(raw: object) -> CharacterizationArtifactDigest:
    return CharacterizationArtifactDigest(_parse_sha256(raw))


def _parse_sha256(raw: object) -> str:
    match raw:
        case str() if len(raw) == 64 and all(character in "0123456789abcdef" for character in raw):
            return raw
        case str():
            raise CharacterizationTypeError(CharacterizationTypeErrorReason.INVALID_DIGEST, raw)
        case _:
            raise CharacterizationTypeError(CharacterizationTypeErrorReason.INVALID_DIGEST, _type_name(raw))


def _type_name(raw: object) -> str:
    return type(raw).__name__
