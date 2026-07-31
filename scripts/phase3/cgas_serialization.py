from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TypeAlias


CanonicalJsonInput: TypeAlias = str | int | bool | None | dict[str, "CanonicalJsonInput"]


class CanonicalSerializationReason(str, Enum):
    ROOT_NOT_OBJECT = "root_not_object"
    ARRAY_UNSUPPORTED = "array_unsupported"
    FLOAT_UNSUPPORTED = "float_unsupported"
    NON_FINITE_FLOAT = "non_finite_float"
    BYTES_UNSUPPORTED = "bytes_unsupported"
    OBJECT_KEY_NOT_STRING = "object_key_not_string"
    UNSUPPORTED_VALUE = "unsupported_value"


@dataclass(frozen=True, slots=True)
class CanonicalSerializationError(ValueError):
    reason: CanonicalSerializationReason
    path: str

    def __str__(self) -> str:
        return f"{self.reason.value}:{self.path}"


@dataclass(frozen=True, slots=True)
class ProvenanceError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def canonical_json_object(value: object) -> bytes:
    """Serialize one strictly supported JSON object into deterministic UTF-8 bytes."""
    match value:
        case dict() as record:
            _validate_json_object(record, "$")
        case _:
            raise CanonicalSerializationError(CanonicalSerializationReason.ROOT_NOT_OBJECT, "$")
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CanonicalSerializationError(CanonicalSerializationReason.UNSUPPORTED_VALUE, "$") from error


def canonical_json_line(value: object) -> bytes:
    return canonical_json_object(value) + b"\n"


def _validate_json_object(value: dict[object, object], path: str) -> None:
    for key, nested in value.items():
        match key:
            case str() as name:
                _validate_json_value(nested, f"{path}.{name}")
            case _:
                raise CanonicalSerializationError(CanonicalSerializationReason.OBJECT_KEY_NOT_STRING, path)


def _validate_json_value(value: object, path: str) -> None:
    match value:
        case dict() as record:
            _validate_json_object(record, path)
        case bool() | int() | str() | None:
            return
        case float() as number:
            reason = (
                CanonicalSerializationReason.FLOAT_UNSUPPORTED
                if math.isfinite(number)
                else CanonicalSerializationReason.NON_FINITE_FLOAT
            )
            raise CanonicalSerializationError(reason, path)
        case list() | tuple():
            raise CanonicalSerializationError(CanonicalSerializationReason.ARRAY_UNSUPPORTED, path)
        case bytes():
            raise CanonicalSerializationError(CanonicalSerializationReason.BYTES_UNSUPPORTED, path)
        case _:
            raise CanonicalSerializationError(CanonicalSerializationReason.UNSUPPORTED_VALUE, path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_row_id(row: dict[str, object]) -> str:
    return "cgas-source-" + digest_text(canonical(row))[:24]


def read_jsonl(path: Path) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ProvenanceError("json_record_not_object")
            values.append(value)
    return values


def read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProvenanceError("json_document_not_object")
    return value


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(canonical(row) + "\n" for row in rows), encoding="utf-8")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(canonical(payload) + "\n", encoding="utf-8")


def corpus_digest(root: Path, splits: tuple[str, ...]) -> str:
    files = (root / "source_manifest.jsonl", root / "manifest.json", *(root / "source" / f"{split}.jsonl" for split in splits))
    return digest_text("|".join(digest(path) for path in files))
