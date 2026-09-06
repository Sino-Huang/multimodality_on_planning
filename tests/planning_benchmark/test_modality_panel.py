from copy import deepcopy

import pytest

from examples.planning_benchmark_slice.modality_panel import select_modality_panel


def row(task_id, costs, split="train"):
    return {
        "task_id": task_id,
        "split": split,
        "reference_costs": {name: {"decisions": count, "expansions": 2} for name, count in costs.items()},
    }


def test_complete_additive_pair_is_excluded_when_only_one_arm_exceeds_ceiling():
    pair = row("pair", {"best_first_add_w3": 1025, "best_first_add_greedy": 4})
    boundary = row("boundary", {"bfs": 1024})
    result = select_modality_panel([pair, boundary])
    assert result["selected"] == [boundary]
    assert result["excluded"][0]["outcome"] == "VALID_STOP"
    assert len(result["excluded"][0]["reference_costs"]) == 2
    assert result["selection_uses_model_outcomes"] is False


def test_selection_does_not_use_model_success():
    rows = [row("task", {"bfs": 10})]
    changed = deepcopy(rows)
    changed[0]["model_success"] = False
    assert select_modality_panel(rows)["counts"] == select_modality_panel(changed)["counts"]


@pytest.mark.parametrize("split,cost", [("test", 10), ("train", 0)])
def test_test_split_and_missing_positive_costs_are_rejected(split, cost):
    with pytest.raises(ValueError):
        select_modality_panel([row("bad", {"bfs": cost}, split)])
