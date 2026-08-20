from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.bfs_pilot import (
    BAND_BOUNDS,
    BANDS,
    DOMAINS,
    SPLITS,
    ExactBFSResult,
    QualifiedCandidate,
    exact_fifo_bfs,
    expansion_band,
    replay_exact_fifo_bfs,
    select_qualified_tasks,
)
from examples.planning_benchmark_slice.validate_instance import load_fixture

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_nontrivial.json"


@pytest.mark.parametrize(
    ("count", "band"),
    [(1, "easy"), (64, "easy"), (65, "medium"), (256, "medium"), (257, "hard"), (1024, "hard")],
)
def test_expansion_band_boundaries(count: int, band: str) -> None:
    assert expansion_band(count) == band


@pytest.mark.parametrize("count", [0, 1025])
def test_rejects_trivial_and_over_budget_counts(count: int) -> None:
    assert expansion_band(count) is None


def _candidate(candidate_id: str, problem_hash: str, *, split: str = "train") -> QualifiedCandidate:
    fixture = load_fixture(FIXTURE)
    return QualifiedCandidate(
        candidate_id=candidate_id,
        domain_id="blocksworld",
        split=split,
        size_tier="easy",
        seed=1,
        normalized_problem_hash=problem_hash,
        domain_pddl=fixture.domain_pddl,
        problem_pddl=fixture.problem_pddl,
        authority_domain_pddl=fixture.domain_pddl,
        authority_problem_pddl=fixture.problem_pddl,
        authority_transformations=(),
        result=ExactBFSResult(1, True, ("a",), "0" * 64),
    )


def test_selection_is_deterministic_under_reordered_candidates() -> None:
    candidates = [_candidate("b", "b" * 64), _candidate("a", "a" * 64)]
    forward = select_qualified_tasks(candidates)
    reverse = select_qualified_tasks(reversed(candidates))
    assert forward == reverse


def test_selection_rejects_test_data() -> None:
    with pytest.raises(ValueError, match="train or dev"):
        select_qualified_tasks([_candidate("held-out", "a" * 64, split="test")])


def test_selection_covers_all_15_domain_band_split_cells() -> None:
    candidates = []
    for domain_index, domain_id in enumerate(DOMAINS):
        for band_index, band in enumerate(BANDS):
            for split_index, split in enumerate(SPLITS):
                count = BAND_BOUNDS[band][0]
                candidate = replace(
                    _candidate(
                        f"{domain_id}-{band}-{split}",
                        f"{domain_index:02x}{band_index:x}{split_index:x}".ljust(64, "0"),
                        split=split,
                    ),
                    domain_id=domain_id,
                    result=ExactBFSResult(count, True, ("a",), "0" * 64),
                )
                candidates.append(candidate)

    selected = select_qualified_tasks(reversed(candidates))

    assert len(selected) == 90
    assert set(selected) == {
        (domain_id, band, split) for domain_id in DOMAINS for band in BANDS for split in SPLITS
    }


def test_exact_fifo_result_replays_byte_for_byte() -> None:
    fixture = load_fixture(FIXTURE)
    result = exact_fifo_bfs(fixture.domain_pddl, fixture.problem_pddl)
    candidate = replace(_candidate("fixture", "a" * 64), result=result)
    assert result.goal_reached is True
    assert result.expansion_count > 0
    assert replay_exact_fifo_bfs(candidate)
    assert not replay_exact_fifo_bfs(replace(candidate, result=replace(result, trace_sha256="f" * 64)))
