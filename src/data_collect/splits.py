"""Content identities and append-only split assignments for PDDL instances."""

from __future__ import annotations

import hashlib
import json
import os
import fcntl
from pathlib import Path
from typing import TextIO

from .normalization import normalize_pddl


PddlSource = str | bytes | os.PathLike[str]


class SplitReassignmentError(ValueError):
    """Raised when an existing whole-instance identity is assigned a new split."""


class SplitLedgerFormatError(ValueError):
    """Raised when an existing split ledger is not a valid append-only ledger."""


def whole_instance_identity(domain_pddl: PddlSource, problem_pddl: PddlSource) -> str:
    """Return a content identity for a complete domain/problem pair.

    String arguments are interpreted as PDDL text. Bytes are decoded as UTF-8,
    and ``PathLike`` arguments are read as UTF-8. Only the normalized domain and
    problem texts enter the digest; locations and dataset metadata do not.
    """

    payload = _canonical_json(
        {
            "domain": normalize_pddl(_read_pddl(domain_pddl)),
            "problem": normalize_pddl(_read_pddl(problem_pddl)),
        }
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def split_assignment_id(identity: str, split: str) -> str:
    """Return the stable content ID for one whole-instance split assignment."""

    _require_nonempty("identity", identity)
    _require_nonempty("split", split)
    payload = _canonical_json({"identity": identity, "split": split}).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


class SplitLedger:
    """Persist immutable whole-instance split assignments as JSON Lines.

    New identities are appended. Assigning an identity to its current split is
    idempotent, while assigning it to a different split is rejected without
    modifying the ledger.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._assignments = self._load()

    def split_for(self, identity: str) -> str | None:
        """Return the assigned split, or ``None`` for an unknown identity."""

        return self._assignments.get(identity)

    def assignment_id_for(self, identity: str) -> str | None:
        """Return the stable assignment ID, or ``None`` for an unknown identity."""

        split = self.split_for(identity)
        return None if split is None else split_assignment_id(identity, split)

    def assignments(self) -> dict[str, str]:
        """Return a copy of all assignments in append order."""

        return dict(self._assignments)

    def assign(self, identity: str, split: str) -> str:
        """Append an unknown assignment or verify an existing immutable one."""

        _require_nonempty("identity", identity)
        _require_nonempty("split", split)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8", newline="") as ledger:
            fcntl.flock(ledger.fileno(), fcntl.LOCK_EX)
            ledger.seek(0)
            assignments = self._load_stream(ledger)
            existing = assignments.get(identity)
            if existing is not None:
                self._assignments = assignments
                if existing != split:
                    raise SplitReassignmentError(
                        f"Identity {identity!r} is already assigned to {existing!r}; cannot reassign it to {split!r}"
                    )
                return existing

            record = {
                "assignment_id": split_assignment_id(identity, split),
                "identity": identity,
                "split": split,
            }
            ledger.write(_canonical_json(record) + "\n")
            ledger.flush()
            os.fsync(ledger.fileno())
            assignments[identity] = split
            self._assignments = assignments
            return split

    def _load(self) -> dict[str, str]:
        assignments: dict[str, str] = {}
        if not self.path.exists():
            return assignments
        if not self.path.is_file():
            raise SplitLedgerFormatError(f"Split ledger is not a file: {self.path}")

        with self.path.open("r", encoding="utf-8", newline="") as ledger:
            return self._load_stream(ledger)

    @staticmethod
    def _load_stream(ledger: TextIO) -> dict[str, str]:
        assignments: dict[str, str] = {}
        for line_number, line in enumerate(ledger, start=1):
            if not line.strip():
                raise SplitLedgerFormatError(f"Blank line in split ledger at line {line_number}")
            record = _parse_record(line, line_number)
            identity = record["identity"]
            split = record["split"]
            existing = assignments.get(identity)
            if existing is not None and existing != split:
                raise SplitLedgerFormatError(
                    f"Conflicting assignments for {identity!r} at line {line_number}: {existing!r} and {split!r}"
                )
            assignments[identity] = split
        return assignments


def _read_pddl(source: PddlSource) -> str:
    if isinstance(source, bytes):
        return source.decode("utf-8")
    if isinstance(source, str):
        return source
    return Path(source).read_text(encoding="utf-8")


def _parse_record(line: str, line_number: int) -> dict[str, str]:
    if not line.endswith("\n"):
        raise SplitLedgerFormatError(f"Split ledger line {line_number} must end with a newline")
    try:
        record = json.loads(line)
    except json.JSONDecodeError as error:
        raise SplitLedgerFormatError(f"Invalid JSON in split ledger at line {line_number}") from error
    if not isinstance(record, dict) or set(record) != {"assignment_id", "identity", "split"}:
        raise SplitLedgerFormatError(
            f"Split ledger line {line_number} must contain exactly 'assignment_id', 'identity', and 'split'"
        )
    assignment_id = record["assignment_id"]
    identity = record["identity"]
    split = record["split"]
    if not isinstance(assignment_id, str) or not isinstance(identity, str) or not isinstance(split, str):
        raise SplitLedgerFormatError(f"Split ledger line {line_number} values must be strings")
    try:
        _require_nonempty("assignment_id", assignment_id)
        _require_nonempty("identity", identity)
        _require_nonempty("split", split)
    except ValueError as error:
        raise SplitLedgerFormatError(f"Invalid split ledger line {line_number}: {error}") from error
    expected_assignment_id = split_assignment_id(identity, split)
    if assignment_id != expected_assignment_id:
        raise SplitLedgerFormatError(
            f"Split ledger line {line_number} has assignment ID {assignment_id!r}; expected {expected_assignment_id!r}"
        )
    if line != _canonical_json(record) + "\n":
        raise SplitLedgerFormatError(f"Split ledger line {line_number} is not canonical JSON")
    return record


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _require_nonempty(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


__all__ = [
    "PddlSource",
    "SplitLedger",
    "SplitLedgerFormatError",
    "SplitReassignmentError",
    "split_assignment_id",
    "whole_instance_identity",
]
