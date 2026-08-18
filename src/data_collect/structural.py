"""Versioned structural-strata policies and coverage verification.

This module deliberately accepts already measured values. It does not infer
structural measurements from PDDL or derive thresholds from a corpus.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must not be empty")


def _require_count(value: int, field_name: str, *, positive: bool = False) -> None:
    minimum = 1 if positive else 0
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{field_name} must be a {qualifier} integer")


@dataclass(frozen=True)
class StructuralRange:
    """One named inclusive interval in a structural policy."""

    name: str
    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "range name")
        _require_count(self.minimum, "range minimum")
        _require_count(self.maximum, "range maximum")
        if self.minimum > self.maximum:
            raise ValueError("range minimum must not exceed range maximum")

    def contains(self, value: int) -> bool:
        return self.minimum <= value <= self.maximum

    def to_dict(self) -> dict[str, int | str]:
        return {"name": self.name, "minimum": self.minimum, "maximum": self.maximum}


@dataclass(frozen=True)
class StructuralCell:
    """The three independent range names identifying one structural cell."""

    horizon: str
    branching: str
    object_count: str

    def __post_init__(self) -> None:
        _require_non_empty(self.horizon, "cell horizon")
        _require_non_empty(self.branching, "cell branching")
        _require_non_empty(self.object_count, "cell object_count")

    def to_dict(self) -> dict[str, str]:
        return {
            "horizon": self.horizon,
            "branching": self.branching,
            "object_count": self.object_count,
        }


@dataclass(frozen=True)
class StructuralRequirement:
    """Minimum coverage required for one cell in one whole-instance split."""

    split: str
    cell: StructuralCell
    minimum_count: int

    def __post_init__(self) -> None:
        _require_non_empty(self.split, "requirement split")
        _require_count(self.minimum_count, "minimum_count", positive=True)

    def to_dict(self) -> dict[str, object]:
        return {
            "split": self.split,
            "cell": self.cell.to_dict(),
            "minimum_count": self.minimum_count,
        }


@dataclass(frozen=True)
class StructuralProfile:
    """Declared structural measurements for one instance.

    ``legacy_bucket`` is retained only as provenance metadata. Structural cell
    assignment always uses the three measured integer dimensions.
    """

    instance_id: str
    split: str
    horizon: int
    branching_factor: int
    object_count: int
    legacy_bucket: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.instance_id, "instance_id")
        _require_non_empty(self.split, "split")
        _require_count(self.horizon, "horizon")
        _require_count(self.branching_factor, "branching_factor")
        _require_count(self.object_count, "object_count")
        if self.legacy_bucket is not None:
            _require_non_empty(self.legacy_bucket, "legacy_bucket")

    def to_dict(self) -> dict[str, object]:
        return {
            "instance_id": self.instance_id,
            "split": self.split,
            "horizon": self.horizon,
            "branching_factor": self.branching_factor,
            "object_count": self.object_count,
            "metadata": {"legacy_bucket": self.legacy_bucket},
        }


def _validate_axis(ranges: tuple[StructuralRange, ...], axis_name: str) -> None:
    if not ranges:
        raise ValueError(f"{axis_name}_ranges must not be empty")
    names = [item.name for item in ranges]
    if len(names) != len(set(names)):
        raise ValueError(f"{axis_name}_ranges must have unique names")
    ordered = sorted(ranges, key=lambda item: (item.minimum, item.maximum, item.name))
    for previous, current in zip(ordered, ordered[1:]):
        if current.minimum <= previous.maximum:
            raise ValueError(f"{axis_name}_ranges must not overlap")


@dataclass(frozen=True)
class StructuralStrataPolicy:
    """A versioned, fixed declaration of structural ranges and split coverage."""

    version: str
    horizon_ranges: tuple[StructuralRange, ...]
    branching_ranges: tuple[StructuralRange, ...]
    object_count_ranges: tuple[StructuralRange, ...]
    required_cells: tuple[StructuralRequirement, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.version, "policy version")
        object.__setattr__(self, "horizon_ranges", tuple(self.horizon_ranges))
        object.__setattr__(self, "branching_ranges", tuple(self.branching_ranges))
        object.__setattr__(self, "object_count_ranges", tuple(self.object_count_ranges))
        object.__setattr__(self, "required_cells", tuple(self.required_cells))

        _validate_axis(self.horizon_ranges, "horizon")
        _validate_axis(self.branching_ranges, "branching")
        _validate_axis(self.object_count_ranges, "object_count")

        horizon_names = {item.name for item in self.horizon_ranges}
        branching_names = {item.name for item in self.branching_ranges}
        object_count_names = {item.name for item in self.object_count_ranges}
        requirement_keys: set[tuple[str, StructuralCell]] = set()
        for requirement in self.required_cells:
            if requirement.cell.horizon not in horizon_names:
                raise ValueError(f"unknown horizon range in required cell: {requirement.cell.horizon}")
            if requirement.cell.branching not in branching_names:
                raise ValueError(f"unknown branching range in required cell: {requirement.cell.branching}")
            if requirement.cell.object_count not in object_count_names:
                raise ValueError(f"unknown object_count range in required cell: {requirement.cell.object_count}")
            key = (requirement.split, requirement.cell)
            if key in requirement_keys:
                raise ValueError("required cells must be unique by split and structural cell")
            requirement_keys.add(key)

    @staticmethod
    def _range_name(ranges: tuple[StructuralRange, ...], value: int) -> str | None:
        return next((item.name for item in ranges if item.contains(value)), None)

    def cell_for(self, profile: StructuralProfile) -> StructuralCell | None:
        """Return the declared cell for measured values, or ``None`` if unprofiled."""

        horizon = self._range_name(self.horizon_ranges, profile.horizon)
        branching = self._range_name(self.branching_ranges, profile.branching_factor)
        object_count = self._range_name(self.object_count_ranges, profile.object_count)
        if horizon is None or branching is None or object_count is None:
            return None
        return StructuralCell(horizon, branching, object_count)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "horizon_ranges": [item.to_dict() for item in self.horizon_ranges],
            "branching_ranges": [item.to_dict() for item in self.branching_ranges],
            "object_count_ranges": [item.to_dict() for item in self.object_count_ranges],
            "required_cells": [item.to_dict() for item in self.required_cells],
        }


@dataclass(frozen=True)
class StructuralCoverageGap:
    """An underfilled required structural cell."""

    split: str
    cell: StructuralCell
    minimum_count: int
    actual_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "split": self.split,
            "cell": self.cell.to_dict(),
            "minimum_count": self.minimum_count,
            "actual_count": self.actual_count,
        }


@dataclass(frozen=True)
class StructuralCoverageCount:
    """Observed count for one required structural cell."""

    split: str
    cell: StructuralCell
    minimum_count: int
    actual_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "split": self.split,
            "cell": self.cell.to_dict(),
            "minimum_count": self.minimum_count,
            "actual_count": self.actual_count,
        }


@dataclass(frozen=True)
class StructuralCoverage:
    """Successful structural coverage accounting for a specific policy version."""

    policy_version: str
    counts: tuple[StructuralCoverageCount, ...]

    def count_for(self, split: str, cell: StructuralCell) -> int:
        return next(
            (item.actual_count for item in self.counts if item.split == split and item.cell == cell),
            0,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "complete": True,
            "counts": [item.to_dict() for item in self.counts],
        }


class StructuralCoverageError(ValueError):
    """Raised when profiles cannot prove every declared coverage requirement."""

    def __init__(
        self,
        gaps: tuple[StructuralCoverageGap, ...],
        unprofiled_instance_ids: tuple[str, ...],
    ) -> None:
        self.gaps = gaps
        self.unprofiled_instance_ids = unprofiled_instance_ids
        details: list[str] = []
        if gaps:
            details.append(f"{len(gaps)} underfilled required cell(s)")
        if unprofiled_instance_ids:
            details.append(f"{len(unprofiled_instance_ids)} unprofiled instance(s)")
        super().__init__("structural coverage rejected: " + ", ".join(details))


def verify_structural_coverage(
    policy: StructuralStrataPolicy,
    profiles: Sequence[StructuralProfile],
) -> StructuralCoverage:
    """Verify measured profiles against fixed required cells and split minima."""

    observed: Counter[tuple[str, StructuralCell]] = Counter()
    unprofiled_instance_ids: list[str] = []
    for profile in profiles:
        cell = policy.cell_for(profile)
        if cell is None:
            unprofiled_instance_ids.append(profile.instance_id)
            continue
        observed[(profile.split, cell)] += 1

    counts = tuple(
        StructuralCoverageCount(
            split=requirement.split,
            cell=requirement.cell,
            minimum_count=requirement.minimum_count,
            actual_count=observed[(requirement.split, requirement.cell)],
        )
        for requirement in policy.required_cells
    )
    gaps = tuple(
        StructuralCoverageGap(
            split=count.split,
            cell=count.cell,
            minimum_count=count.minimum_count,
            actual_count=count.actual_count,
        )
        for count in counts
        if count.actual_count < count.minimum_count
    )
    if gaps or unprofiled_instance_ids:
        raise StructuralCoverageError(gaps, tuple(sorted(unprofiled_instance_ids)))
    return StructuralCoverage(policy_version=policy.version, counts=counts)


__all__ = [
    "StructuralCell",
    "StructuralCoverage",
    "StructuralCoverageCount",
    "StructuralCoverageError",
    "StructuralCoverageGap",
    "StructuralProfile",
    "StructuralRange",
    "StructuralRequirement",
    "StructuralStrataPolicy",
    "verify_structural_coverage",
]
