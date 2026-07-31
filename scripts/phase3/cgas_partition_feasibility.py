from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from .cgas_characterization_bundle import parse_bundle
from .cgas_partition_selection import (
    SelectionFeasibilityError,
    _groups,
    _is_paired_exact,
)


@dataclass(frozen=True, slots=True)
class PartitionFeasibilityReport:
    """Read-only paired-exact facts and downstream feasibility classification."""

    paired_exact_row_count: int
    paired_exact_signature_count: int
    paired_exact_object_counts: tuple[tuple[int, int], ...]
    ineligible_row_count: int
    downstream_feasibility: str
    failure_reasons: tuple[str, ...]


def analyze_bundle(bundle_contents: bytes) -> PartitionFeasibilityReport:
    """Parse final bundle bytes and return its read-only structural feasibility report."""
    parsed = parse_bundle(bundle_contents)
    members = {member.name: member.contents for member in parsed.members}
    rows = tuple(
        _row(json.loads(line))
        for line in members["characterization.jsonl"].splitlines()
    )
    return analyze_rows(rows)


def analyze_rows(rows: Sequence[dict[str, object]]) -> PartitionFeasibilityReport:
    """Calculate paired-exact facts without inferring unknown successor metrics."""
    ordered = tuple(sorted(rows, key=lambda row: _instance_id(row)))
    paired_exact = tuple(row for row in ordered if _is_paired_exact(row))
    paired_exact_groups = _groups(paired_exact)
    paired_exact_object_counts = tuple(sorted(Counter(_object_count(row) for row in paired_exact).items()))
    downstream_feasibility = (
        "indeterminate_non_exact_metrics"
        if len(paired_exact) != len(ordered)
        else "not_evaluated"
    )
    failure_reasons = (*_actual_failure_reasons(ordered, paired_exact),)
    if downstream_feasibility == "indeterminate_non_exact_metrics":
        failure_reasons = (*failure_reasons, downstream_feasibility)
    return PartitionFeasibilityReport(
        paired_exact_row_count=len(paired_exact),
        paired_exact_signature_count=len(paired_exact_groups),
        paired_exact_object_counts=paired_exact_object_counts,
        ineligible_row_count=len(ordered) - len(paired_exact),
        downstream_feasibility=downstream_feasibility,
        failure_reasons=failure_reasons,
    )


def _actual_failure_reasons(
    rows: Sequence[dict[str, object]], paired_exact: Sequence[dict[str, object]]
) -> tuple[str, ...]:
    paired_ids = {_instance_id(row) for row in paired_exact}
    has_ineligible_12_object_row = any(
        _object_count(row) == 12 and _instance_id(row) not in paired_ids for row in rows
    )
    return ("structural_ood_ineligible",) if has_ineligible_12_object_row else ()


def _row(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SelectionFeasibilityError("invalid_row")
    return value


def _instance_id(row: dict[str, object]) -> str:
    value = row.get("instance_id")
    if not isinstance(value, str) or not value:
        raise SelectionFeasibilityError("invalid_instance_id")
    return value


def _object_count(row: dict[str, object]) -> int:
    value = row.get("object_count")
    if isinstance(value, bool) or not isinstance(value, int):
        raise SelectionFeasibilityError("invalid_object_count")
    return value
