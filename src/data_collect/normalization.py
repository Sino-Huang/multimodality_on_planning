"""Normalization helpers for curriculum PDDL data collection contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


_PDDL_COMMENT_PATTERN = re.compile(r";[^\n\r]*")
_PDDL_TOKEN_PATTERN = re.compile(r"[()]|[^()\s]+")


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


@dataclass(frozen=True)
class AcceptedProblemIdentity:
    """Identifies one accepted problem within the dataset."""

    normalized_problem_text: str
    instance_id: str
    domain_id: str
    split: str
    bucket: str


@dataclass(frozen=True)
class DuplicateProblem:
    """Describes a duplicate candidate discovered during accepted dedupe."""

    normalized_problem_text: str
    duplicate_identifier: str
    existing_instance_id: str
    existing_domain_id: str
    existing_split: str
    existing_bucket: str


class AcceptedProblemIndex:
    """Track accepted normalized problem texts across all splits.

    The index is intentionally split-agnostic: once a normalized problem text is
    accepted for one split, later occurrences should be rejected even if they
    come from a different split.
    """

    def __init__(self, identities: Iterable[AcceptedProblemIdentity] | None = None) -> None:
        self._by_text: dict[str, AcceptedProblemIdentity] = {}
        if identities is None:
            return

        for identity in identities:
            self._by_text[identity.normalized_problem_text] = identity

    def contains(self, normalized_problem_text: str) -> bool:
        """Return whether the normalized problem text is already accepted."""

        return normalized_problem_text in self._by_text

    def get(self, normalized_problem_text: str) -> AcceptedProblemIdentity | None:
        """Return the accepted identity for *normalized_problem_text*, if any."""

        return self._by_text.get(normalized_problem_text)

    def register(
        self,
        *,
        normalized_problem_text: str,
        instance_id: str,
        domain_id: str,
        split: str,
        bucket: str,
        duplicate_identifier: str | None = None,
    ) -> DuplicateProblem | None:
        """Register an accepted problem or describe the conflicting existing one."""

        existing = self._by_text.get(normalized_problem_text)
        if existing is not None:
            return DuplicateProblem(
                normalized_problem_text=normalized_problem_text,
                duplicate_identifier=duplicate_identifier or instance_id,
                existing_instance_id=existing.instance_id,
                existing_domain_id=existing.domain_id,
                existing_split=existing.split,
                existing_bucket=existing.bucket,
            )

        self._by_text[normalized_problem_text] = AcceptedProblemIdentity(
            normalized_problem_text=normalized_problem_text,
            instance_id=instance_id,
            domain_id=domain_id,
            split=split,
            bucket=bucket,
        )
        return None

    def identities(self) -> tuple[AcceptedProblemIdentity, ...]:
        """Return the currently accepted identities in insertion order."""

        return tuple(self._by_text.values())


__all__ = [
    "AcceptedProblemIdentity",
    "AcceptedProblemIndex",
    "DuplicateProblem",
    "normalize_pddl",
    "strip_pddl_comments",
]
