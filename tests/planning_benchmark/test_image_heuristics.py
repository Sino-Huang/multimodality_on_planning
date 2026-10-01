from __future__ import annotations

import pytest

from examples.planning_benchmark_slice.image_heuristics import ranker_pairs, validation_tasks

TASKS = [f"task-{n:03d}" for n in range(100)]


def test_validation_split_is_the_frozen_sha256_rule() -> None:
    assert validation_tasks(TASKS) == {"task-023", "task-037", "task-039", "task-093", "task-098"}


def test_validation_membership_depends_only_on_the_task_id() -> None:
    subset = ["task-098", "task-000", "task-037"]
    assert validation_tasks(reversed(subset)) == {"task-037", "task-098"}
    assert validation_tasks(subset) == validation_tasks(TASKS) & set(subset)


def test_ranker_pairs_label_orientation_and_exclusions() -> None:
    hstar = {"a": 3.0, "b": 1.0, "c": 3.0, "d": None, "e": 5.0}
    pairs = ranker_pairs([["e", "a", "b", "c", "d"]], hstar)
    # Equal h* (a/c) and dead ends (d) form no pair; label 1 means the first key is farther.
    assert pairs == [("a", "b", 1.0), ("a", "e", 0.0), ("b", "c", 0.0), ("b", "e", 0.0), ("c", "e", 0.0)]


def test_ranker_pairs_stay_within_menus_and_deduplicate_across_menus() -> None:
    hstar = {"a": 2.0, "b": 1.0, "c": 0.0}
    pairs = ranker_pairs([["a", "b"], ["b", "a", "a"], ["c"]], hstar)
    assert pairs == [("a", "b", 1.0)]


def test_ranker_pairs_reject_unknown_menu_keys() -> None:
    with pytest.raises(ValueError, match="unknown state key 'z'"):
        ranker_pairs([["a", "z"]], {"a": 1.0})
