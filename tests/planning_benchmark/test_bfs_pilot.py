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
    _easy_sokoban_problem,
    _npuzzle_problem,
    _partitioned_npuzzle_states,
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


def _candidate(
    candidate_id: str,
    problem_hash: str,
    *,
    split: str = "train",
    identity_key: str | None = None,
) -> QualifiedCandidate:
    fixture = load_fixture(FIXTURE)
    problem_pddl = fixture.problem_pddl.replace("bw-nontrivial-3", f"bw-{identity_key or candidate_id}")
    return QualifiedCandidate(
        candidate_id=candidate_id,
        domain_id="blocksworld",
        split=split,
        size_tier="easy",
        seed=1,
        normalized_problem_hash=problem_hash,
        domain_pddl=fixture.domain_pddl,
        problem_pddl=problem_pddl,
        authority_domain_pddl=fixture.domain_pddl,
        authority_problem_pddl=problem_pddl,
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


def test_joint_selection_skips_three_cross_split_identity_collisions() -> None:
    candidates = []
    for index, band in enumerate(BANDS):
        result = ExactBFSResult(BAND_BOUNDS[band][0], True, ("a",), "0" * 64)
        candidates.extend(
            replace(candidate, result=result)
            for candidate in (
                _candidate(
                    f"{band}-train-first",
                    f"{index}0".ljust(64, "0"),
                    split="train",
                    identity_key=f"{band}-collision",
                ),
                _candidate(
                    f"{band}-train-alternative",
                    f"{index}f".ljust(64, "f"),
                    split="train",
                    identity_key=f"{band}-train-only",
                ),
                _candidate(
                    f"{band}-dev-first",
                    f"{index}1".ljust(64, "1"),
                    split="dev",
                    identity_key=f"{band}-collision",
                ),
                _candidate(
                    f"{band}-dev-alternative",
                    f"{index}e".ljust(64, "e"),
                    split="dev",
                    identity_key=f"{band}-dev-only",
                ),
            )
        )

    selected = select_qualified_tasks(reversed(candidates))

    for band in BANDS:
        assert (
            selected[("blocksworld", band, "train")].whole_instance_id
            != selected[("blocksworld", band, "dev")].whole_instance_id
        )


def test_joint_selection_marks_a_cell_missing_without_a_split_isolated_pair() -> None:
    candidates = [
        _candidate("train", "0" * 64, split="train", identity_key="collision"),
        _candidate("dev", "1" * 64, split="dev", identity_key="collision"),
    ]

    assert select_qualified_tasks(candidates) == {}


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
    assert set(selected) == {(domain_id, band, split) for domain_id in DOMAINS for band in BANDS for split in SPLITS}


def test_exact_fifo_result_replays_byte_for_byte() -> None:
    fixture = load_fixture(FIXTURE)
    result = exact_fifo_bfs(fixture.domain_pddl, fixture.problem_pddl)
    candidate = replace(_candidate("fixture", "a" * 64), result=result)
    assert result.goal_reached is True
    assert result.expansion_count > 0
    assert replay_exact_fifo_bfs(candidate)
    assert not replay_exact_fifo_bfs(replace(candidate, result=replace(result, trace_sha256="f" * 64)))


def test_corrected_npuzzle_constructions_fill_their_intended_bands() -> None:
    domain = (REPO_ROOT / "modules" / "pddl-generators" / "npuzzle" / "domain.pddl").read_text(encoding="utf-8")
    cases = (("easy", 2, (1, 5)), ("medium", 3, (7, 8)), ("hard", 3, (9, 10)))
    for split in SPLITS:
        for tier, size, depths in cases:
            results = [
                exact_fifo_bfs(domain, _npuzzle_problem(size, state, split=split, tier=tier, attempt=index))
                for index, state in enumerate(_partitioned_npuzzle_states(size, depths, split)[:20])
            ]
            assert any(result.goal_reached and expansion_band(result.expansion_count) == tier for result in results)


def test_corrected_sokoban_easy_layouts_are_split_distinct_and_qualified() -> None:
    domain = (REPO_ROOT / "data" / "pddl_instances" / "sokoban" / "domain.pddl").read_text(encoding="utf-8")
    problems = {(split, attempt): _easy_sokoban_problem(split, attempt) for split in SPLITS for attempt in range(2)}

    assert set(problems.values()).__len__() == 4
    assert {exact_fifo_bfs(domain, problem).expansion_count for problem in problems.values()} == {3, 10}
