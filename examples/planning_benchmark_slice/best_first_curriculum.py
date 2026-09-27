"""Whole-instance paired bootstrap interval shared by the expanded-study analyses."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence


def paired_bootstrap_interval(
    left: Mapping[str, float],
    right: Mapping[str, float],
    *,
    resamples: int,
    seed: int,
    confidence: float,
) -> dict[str, float]:
    """Return a whole-instance paired mean-difference interval."""

    ids = sorted(left)
    if not ids or set(ids) != set(right):
        raise ValueError("paired curriculum statistics require identical task coverage")
    differences = [float(left[item]) - float(right[item]) for item in ids]
    generator = random.Random(seed)
    draws = sorted(
        sum(differences[generator.randrange(len(differences))] for _ in differences) / len(differences)
        for _ in range(resamples)
    )
    tail = (1.0 - confidence) / 2.0
    return {
        "lower": _quantile(draws, tail),
        "point": sum(differences) / len(differences),
        "upper": _quantile(draws, 1.0 - tail),
    }


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot take a quantile of no values")
    position = probability * (len(values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[lower])
    fraction = position - lower
    return float(values[lower] * (1.0 - fraction) + values[upper] * fraction)


__all__ = ["paired_bootstrap_interval"]
