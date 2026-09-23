"""Issue #136 menu-order augmentation contracts (scripts/run_choice_frontier_v3.augment_menu)."""

from __future__ import annotations

import pytest

from scripts.run_choice_frontier_v3 import augment_menu


def menu_of(size: int) -> tuple[list[dict], list[int]]:
    menu = [{"choice": f"c{i}", "state_ref": f"s{10 + i}"} for i in range(size)]
    return menu, [100 + i for i in range(size)]


@pytest.mark.parametrize("size", [2, 3, 5, 17])
@pytest.mark.parametrize("copy", [0, 1])
def test_target_is_the_teacher_state_after_permutation(size, copy):
    menu, indices = menu_of(size)
    for teacher in (entry["state_ref"] for entry in menu):
        permuted, permuted_indices, target = augment_menu("task/x:best_first_add_w3:4", menu, indices, teacher, copy)
        assert [entry["choice"] for entry in permuted] == [f"c{i}" for i in range(size)]
        assert sorted(entry["state_ref"] for entry in permuted) == sorted(entry["state_ref"] for entry in menu)
        assert next(entry["state_ref"] for entry in permuted if entry["choice"] == target) == teacher
        # Scenes stay bound to their states under the permutation.
        scene_of = {entry["state_ref"]: index for entry, index in zip(menu, indices, strict=True)}
        assert permuted_indices == [scene_of[entry["state_ref"]] for entry in permuted]


@pytest.mark.parametrize("size", [3, 4, 8, 40])
def test_the_two_augmentation_seeds_give_different_orders(size):
    menu, indices = menu_of(size)
    record_id = f"choice-frontier-v3-train/blocksworld-expanded-945000:best_first_add_greedy:{size}"
    first, _, _ = augment_menu(record_id, menu, indices, "s10", 0)
    second, _, _ = augment_menu(record_id, menu, indices, "s10", 1)
    assert [e["state_ref"] for e in first] != [e["state_ref"] for e in second]


def test_same_record_id_gives_the_same_permutation():
    menu, indices = menu_of(9)
    record_id = "choice-frontier-v3-train/depot-compact-945001:best_first_add_w3:7"
    assert augment_menu(record_id, menu, indices, "s13", 1) == augment_menu(record_id, menu, indices, "s13", 1)
    other = augment_menu("choice-frontier-v3-train/depot-compact-945001:best_first_add_w3:8", menu, indices, "s13", 1)
    assert other[0] != augment_menu(record_id, menu, indices, "s13", 1)[0]
