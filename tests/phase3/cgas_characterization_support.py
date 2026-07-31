from __future__ import annotations

from dataclasses import dataclass
from typing import Final


SYNTHETIC_POPULATION_LABEL: Final = "synthetic-characterization-test-only"


@dataclass(frozen=True, slots=True)
class SyntheticCharacterizationRow:
    instance_id: str
    split: str
    object_count: int


def synthetic_characterization_population() -> tuple[SyntheticCharacterizationRow, ...]:
    """Return explicit test-only synthetic rows; this never reads production data."""
    return tuple(
        SyntheticCharacterizationRow(
            instance_id=f"synthetic-characterization-{split}-{index:04d}",
            split=split,
            object_count=object_count,
        )
        for split, object_count, count in (("train", 4, 190), ("train", 8, 198), ("train", 12, 14), ("dev", 12, 39), ("test", 12, 40))
        for index in range(count)
    )
