"""Hashing helpers for curriculum PDDL data collection contracts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable


_PDDL_COMMENT_PATTERN = re.compile(r";[^\n\r]*")
_PDDL_TOKEN_PATTERN = re.compile(r"[()]|[^()\s]+")


def sha256_text(text: str) -> str:
    """Return the SHA-256 digest for *text* as a hexadecimal string."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_pddl_comments(text: str) -> str:
    """Remove line comments from PDDL text.

    PDDL uses ``;`` for end-of-line comments, so comment removal must happen
    before whitespace normalization.
    """

    return _PDDL_COMMENT_PATTERN.sub("", text)


def normalize_pddl(text: str) -> str:
    """Normalize PDDL by ignoring whitespace and comment-only differences."""

    uncommented = strip_pddl_comments(text)
    tokens = _PDDL_TOKEN_PATTERN.findall(uncommented)
    return " ".join(tokens)


def normalized_pddl_sha256(text: str) -> str:
    """Return a whitespace/comment-insensitive SHA-256 digest for PDDL text."""

    return sha256_text(normalize_pddl(text))


@dataclass(frozen=True)
class PDDLHashInfo:
    """Raw and normalized hash material for a PDDL asset."""

    raw_sha256: str
    normalized_sha256: str
    normalized_text: str


def build_pddl_hash_info(text: str) -> PDDLHashInfo:
    """Build both raw and normalized hashes for a PDDL string."""

    normalized_text = normalize_pddl(text)
    return PDDLHashInfo(
        raw_sha256=sha256_text(text),
        normalized_sha256=sha256_text(normalized_text),
        normalized_text=normalized_text,
    )


@dataclass(frozen=True)
class AcceptedProblemFingerprint:
    """Identifies one accepted problem hash within the dataset."""

    normalized_problem_hash: str
    instance_id: str
    domain_id: str
    split: str
    bucket: str


@dataclass(frozen=True)
class DuplicateProblemHash:
    """Describes a duplicate candidate discovered during accepted dedupe."""

    normalized_problem_hash: str
    duplicate_identifier: str
    existing_instance_id: str
    existing_domain_id: str
    existing_split: str
    existing_bucket: str


class AcceptedProblemHashIndex:
    """Track accepted normalized problem hashes across all splits.

    The index is intentionally split-agnostic: once a normalized problem hash is
    accepted for one split, later occurrences should be rejected even if they
    come from a different split.
    """

    def __init__(self, fingerprints: Iterable[AcceptedProblemFingerprint] | None = None) -> None:
        self._by_hash: dict[str, AcceptedProblemFingerprint] = {}
        if fingerprints is None:
            return

        for fingerprint in fingerprints:
            self._by_hash[fingerprint.normalized_problem_hash] = fingerprint

    def has_hash(self, normalized_problem_hash: str) -> bool:
        """Return whether the normalized problem hash is already accepted."""

        return normalized_problem_hash in self._by_hash

    def get(self, normalized_problem_hash: str) -> AcceptedProblemFingerprint | None:
        """Return the accepted fingerprint for *normalized_problem_hash*, if any."""

        return self._by_hash.get(normalized_problem_hash)

    def register(
        self,
        *,
        normalized_problem_hash: str,
        instance_id: str,
        domain_id: str,
        split: str,
        bucket: str,
        duplicate_identifier: str | None = None,
    ) -> DuplicateProblemHash | None:
        """Register an accepted hash or describe the conflicting existing one."""

        existing = self._by_hash.get(normalized_problem_hash)
        if existing is not None:
            return DuplicateProblemHash(
                normalized_problem_hash=normalized_problem_hash,
                duplicate_identifier=duplicate_identifier or instance_id,
                existing_instance_id=existing.instance_id,
                existing_domain_id=existing.domain_id,
                existing_split=existing.split,
                existing_bucket=existing.bucket,
            )

        self._by_hash[normalized_problem_hash] = AcceptedProblemFingerprint(
            normalized_problem_hash=normalized_problem_hash,
            instance_id=instance_id,
            domain_id=domain_id,
            split=split,
            bucket=bucket,
        )
        return None

    def fingerprints(self) -> tuple[AcceptedProblemFingerprint, ...]:
        """Return the currently accepted fingerprints in insertion order."""

        return tuple(self._by_hash.values())


__all__ = [
    "AcceptedProblemFingerprint",
    "AcceptedProblemHashIndex",
    "DuplicateProblemHash",
    "PDDLHashInfo",
    "build_pddl_hash_info",
    "normalize_pddl",
    "normalized_pddl_sha256",
    "sha256_text",
    "strip_pddl_comments",
]
