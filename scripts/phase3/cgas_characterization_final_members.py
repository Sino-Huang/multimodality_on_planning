from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from .cgas_characterization_final_validation import verify_final
from .cgas_partition_contracts import CHARACTERIZATION_FILE, MANIFEST_FILE
from .cgas_serialization import CanonicalSerializationError, canonical, canonical_json_object

FINAL_MEMBER_NAMES: Final = frozenset({"run-contract.json", CHARACTERIZATION_FILE, MANIFEST_FILE})


def verify_final_members(
    members: dict[str, bytes], contract_bytes: bytes, payload: dict[str, object], repository: Path, expected_rows: tuple[dict[str, object], ...]
) -> None:
    """Run the authoritative final checks over logical bytes from any read-only source."""
    if frozenset(members) != FINAL_MEMBER_NAMES:
        raise ValueError("unexpected_final_member_profile")
    if members["run-contract.json"] != contract_bytes:
        raise ValueError("final_contract_mismatch")
    rows_bytes = members[CHARACTERIZATION_FILE]
    verify_final(_canonical_rows(rows_bytes), rows_bytes, _canonical_document(members[MANIFEST_FILE], "manifest"), payload, repository, expected_rows)


def _canonical_document(contents: bytes, label: str) -> dict[str, object]:
    if not contents.endswith(b"\n"):
        raise ValueError(f"noncanonical_{label}")
    return _canonical_object(contents[:-1], label)


def _canonical_rows(contents: bytes) -> tuple[dict[str, object], ...]:
    if not contents or not contents.endswith(b"\n"):
        raise ValueError("noncanonical_jsonl")
    rows: list[dict[str, object]] = []
    for line in contents.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            raise ValueError("noncanonical_jsonl")
        raw = json.loads(line[:-1])
        if not isinstance(raw, dict) or canonical(raw).encode() != line[:-1]:
            raise ValueError("noncanonical_jsonl_row")
        rows.append(raw)
    return tuple(rows)


def _canonical_object(contents: bytes, label: str) -> dict[str, object]:
    try:
        raw = json.loads(contents)
    except json.JSONDecodeError as error:
        raise ValueError(f"noncanonical_{label}") from error
    try:
        canonical = canonical_json_object(raw)
    except CanonicalSerializationError as error:
        raise ValueError(f"noncanonical_{label}") from error
    if not isinstance(raw, dict) or canonical != contents:
        raise ValueError(f"noncanonical_{label}")
    return raw
