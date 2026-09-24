"""#138 pre-registered 3-seed bootstrap and separation-verdict rules."""

from __future__ import annotations

import pytest

from scripts.analyze_choice_frontier_v2 import bootstrap
from scripts.analyze_choice_frontier_v4_seeds import point, seed_averaged_bootstrap, separation_verdict


def test_seed_averaged_bootstrap_matches_hand_computed_two_task_case():
    # Per-task seed means: A = (0.2 + 0.4) / 2 = 0.3, B = (0.6 + 1.0) / 2 = 0.8.
    # With two tasks a draw is AA (0.3, p 1/4), AB/BA (0.55, p 1/2) or BB (0.8, p 1/4),
    # so the 2.5% / 97.5% percentiles are exactly the all-A and all-B draws.
    values = {"17": {"A": 0.2, "B": 0.6}, "29": {"A": 0.4, "B": 1.0}}
    lo, hi = seed_averaged_bootstrap(values, ["A", "B"])
    assert point(values, ["A", "B"]) == pytest.approx(0.55)
    assert lo == pytest.approx(0.3)
    assert hi == pytest.approx(0.8)


def test_seed_averaged_bootstrap_single_draw_averages_seeds_inside_the_draw():
    import random

    tasks = ["A", "B", "C"]
    rng = random.Random(7)
    picks = [rng.choice(tasks) for _ in tasks]
    values = {"s1": {"A": 0.0, "B": 1.0, "C": 3.0}, "s2": {"A": 2.0, "B": 1.0, "C": -1.0}}
    expected = (sum(values["s1"][t] for t in picks) / 3 + sum(values["s2"][t] for t in picks) / 3) / 2
    lo, hi = seed_averaged_bootstrap(values, tasks, seed=7, draws=1)
    assert lo == pytest.approx(expected) and hi == pytest.approx(expected)


def test_one_seed_reduces_to_the_135_task_cluster_bootstrap():
    values = {"t1": 0.1, "t2": -0.3, "t3": 0.7, "t4": 0.0, "t5": 0.25}
    tasks = list(values)
    ours = seed_averaged_bootstrap({"17": values}, tasks)
    frozen = bootstrap(values, tasks)
    assert ours == pytest.approx(frozen)


@pytest.mark.parametrize(
    ("lo", "hi", "expected"),
    [
        (1e-12, 0.4, "SEPARATED_ABOVE"),
        (0.0, 0.4, "NOT_SEPARATED"),
        (-0.1, 0.4, "NOT_SEPARATED"),
        (-0.4, 0.0, "NOT_SEPARATED"),
        (-0.4, -1e-12, "SEPARATED_BELOW"),
    ],
)
def test_separation_verdict_boundaries(lo, hi, expected):
    assert separation_verdict(lo, hi) == expected
