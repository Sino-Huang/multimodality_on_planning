from __future__ import annotations

from typing import Any, Iterable

from .pddl_state import CanonicalState, PDDLStateAuthority
from .search_memory import SearchMemory

IW_WIDTH = 1
NoveltyItem = tuple[str, ...]


def iw_novelty_items(state: CanonicalState) -> tuple[NoveltyItem, ...]:
    """Return canonical IW(1) features for one dynamic state."""

    return tuple((atom,) for atom in state.atoms)


def first_novel_item(
    items: Iterable[NoveltyItem],
    novelty_table: set[NoveltyItem],
) -> NoveltyItem | None:
    return next((item for item in items if item not in novelty_table), None)


def serialize_novelty_table(items: Iterable[NoveltyItem]) -> list[list[str]]:
    return [list(item) for item in sorted(items)]


def build_iw_observation(
    *,
    authority: PDDLStateAuthority,
    state: CanonicalState,
    memory: SearchMemory,
    novelty_table: set[NoveltyItem],
) -> dict[str, Any]:
    """Build the shared Markov-sufficient view used by exact traces and replay."""

    candidates: list[dict[str, Any]] = []
    for action in authority.applicable_actions(state):
        target = authority.preview_apply(state, action).target_state
        target_novel_item = first_novel_item(iw_novelty_items(target), novelty_table)
        visited = target.state_id in memory.visited
        candidates.append(
            {
                "action": action.serialize(),
                "enqueue_eligible": not visited and target_novel_item is not None,
                "novel_item": None if target_novel_item is None else list(target_novel_item),
                "pruned": visited or target_novel_item is None,
                "target_atoms": list(target.atoms),
                "target_fluents": list(target.fluents),
                "target_state_id": target.state_id,
                "visited": visited,
            }
        )
    return {
        "algorithm": "iterated_width",
        "expanded_state": {
            "atoms": list(state.atoms),
            "fluents": list(state.fluents),
            "state_id": state.state_id,
        },
        "search_memory": {
            "frontier": list(memory.frontier),
            "novelty_by_state": dict(sorted(memory.novelty.items())),
            "novelty_table": serialize_novelty_table(novelty_table),
            "visited": sorted(memory.visited),
        },
        "successor_candidates": candidates,
        "task_context": authority.task_context(),
        "width": IW_WIDTH,
    }


__all__ = [
    "IW_WIDTH",
    "NoveltyItem",
    "build_iw_observation",
    "first_novel_item",
    "iw_novelty_items",
    "serialize_novelty_table",
]
