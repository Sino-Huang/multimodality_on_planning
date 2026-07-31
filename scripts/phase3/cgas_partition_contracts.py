from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterable


SCHEMA_VERSION: Final = "cgas_partition_characterization_v2"
EXPECTED_SPLIT_COUNTS: Final = {"dev": 39, "test": 40, "train": 402}
EXPECTED_OBJECT_COUNTS: Final = {4: 190, 8: 198, 12: 93}
EXPECTED_ROW_COUNT: Final = 481
CHARACTERIZATION_FILE: Final = "characterization.jsonl"
MANIFEST_FILE: Final = "characterization_manifest.json"
DEFAULT_LIMITS: Final = {
    "max_expansions": 10_000,
    "max_plan_length": 128,
    "max_trace_steps": 10_000,
    "max_grounded_actions": 100_000,
    "max_grounded_atoms": 100_000,
    "gbfs_max_depth": 128,
    "gbfs_max_expansions": 10_000,
    "local_iw_width": 1,
    "local_iw_max_width": 1,
    "local_iw_novelty_max_expansions": 10_000,
    "local_max_applicable_actions": 2_000,
}


@dataclass(frozen=True, slots=True)
class CharacterizationInput:
    """Immutable source identity and local PDDL paths for one accepted instance."""

    instance_id: str
    split: str
    domain_path: Path
    problem_path: Path
    source_record_sha256: str


class CharacterizationContractError(RuntimeError):
    """Raised when the accepted Blocksworld source contract is violated."""


def require_full_trace_source(record: dict[str, object]) -> None:
    """Reject characterization rows that cannot provide a complete transition trace."""
    eligibility = record.get("source_eligibility")
    match eligibility:
        case "eligible_complete_trace":
            return
        case "ineligible_bounded_trace":
            raise CharacterizationContractError("bounded_trace_not_source_ready")
        case "ineligible_search_failure":
            raise CharacterizationContractError("search_failure_not_source_ready")
        case _:
            raise CharacterizationContractError("unknown_source_eligibility")


def assert_expected_population(rows: Iterable[dict[str, object]]) -> None:
    """Require the complete accepted Blocksworld population before characterization."""
    materialized = tuple(rows)
    split_counts = Counter(_text(row, "split") for row in materialized)
    object_counts = Counter(_integer(row, "object_count") for row in materialized)
    if len(materialized) != EXPECTED_ROW_COUNT:
        raise CharacterizationContractError("unexpected_accepted_blocksworld_row_count")
    if dict(sorted(split_counts.items())) != EXPECTED_SPLIT_COUNTS:
        raise CharacterizationContractError("unexpected_accepted_blocksworld_split_counts")
    if dict(sorted(object_counts.items())) != EXPECTED_OBJECT_COUNTS:
        raise CharacterizationContractError("unexpected_accepted_blocksworld_object_counts")


def _text(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise CharacterizationContractError(f"missing_{key}")
    return value


def _integer(row: dict[str, object], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int):
        raise CharacterizationContractError(f"missing_{key}")
    return value
