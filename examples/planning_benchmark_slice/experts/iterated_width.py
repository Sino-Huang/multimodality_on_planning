from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

from ..blocksworld import AtomSet, BlocksworldAction, BlocksworldProblem
from ..trajectory_schema import SCHEMA_VERSION, canonicalize_trajectory_step
from .bfs import BFS_TIE_BREAK_RULE, WORLD_MODEL


DEFAULT_WIDTH = 1

NoveltyItem = tuple[str, ...]


@dataclass(frozen=True)
class IWNode:
    state: AtomSet
    plan: tuple[BlocksworldAction, ...]


@dataclass(frozen=True)
class IWSuccessor:
    action: str
    state_id: str
    state_atoms: list[str]
    is_goal: bool
    is_novel: bool
    enqueued: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "enqueued": self.enqueued,
            "is_goal": self.is_goal,
            "is_novel": self.is_novel,
            "state_atoms": self.state_atoms,
            "state_id": self.state_id,
        }


def generate_iterated_width_trajectory(
    *,
    problem: BlocksworldProblem,
    instance_id: str,
    fixture_path: Path,
    width: int = DEFAULT_WIDTH,
    max_steps: int = 64,
) -> list[dict[str, Any]]:
    """Generate step-level IW(k) expert records for a deterministic Blocksworld plan."""

    if width <= 0:
        raise ValueError("width must be positive")

    records: list[dict[str, Any]] = []
    current_state = problem.initial_state()

    for step_index in range(max_steps):
        if problem.is_goal(current_state):
            break
        plan = iterated_width_plan(problem, current_state, width=width, max_expansions=max_steps * 16)
        if not plan:
            break
        selected_action = plan[0]
        records.append(
            build_iterated_width_step_record(
                problem=problem,
                instance_id=instance_id,
                fixture_path=fixture_path,
                state=current_state,
                step_index=step_index,
                selected_action=selected_action,
                width=width,
            )
        )
        current_state = problem.transition(current_state, selected_action)

    return records


def iterated_width_plan(
    problem: BlocksworldProblem,
    start_state: Iterable[str],
    *,
    width: int = DEFAULT_WIDTH,
    max_expansions: int = 1024,
) -> tuple[BlocksworldAction, ...] | None:
    start = frozenset(start_state)
    if problem.is_goal(start):
        return tuple()

    frontier: deque[IWNode] = deque([IWNode(state=start, plan=tuple())])
    visited = {problem.state_id(start)}
    novelty_table: set[NoveltyItem] = set()
    expansions = 0

    while frontier and expansions < max_expansions:
        node = frontier.popleft()
        current_items = novelty_items(node.state, width=width)
        if first_novel_item(current_items, novelty_table) is None:
            continue

        novelty_table.update(current_items)
        expansions += 1

        for action in problem.legal_actions(node.state):
            next_state = problem.transition(node.state, action)
            next_id = problem.state_id(next_state)
            if next_id in visited:
                continue
            successor_items = novelty_items(next_state, width=width)
            if first_novel_item(successor_items, novelty_table) is None:
                continue
            next_plan = (*node.plan, action)
            if problem.is_goal(next_state):
                return next_plan
            visited.add(next_id)
            frontier.append(IWNode(state=next_state, plan=next_plan))

    return None


def build_iterated_width_step_record(
    *,
    problem: BlocksworldProblem,
    instance_id: str,
    fixture_path: Path,
    state: Iterable[str],
    step_index: int,
    selected_action: BlocksworldAction,
    width: int = DEFAULT_WIDTH,
) -> dict[str, Any]:
    atom_set = frozenset(state)
    state_id = problem.state_id(atom_set)
    novelty_table_before: set[NoveltyItem] = set()
    current_items = novelty_items(atom_set, width=width)
    novel_item = first_novel_item(current_items, novelty_table_before)
    decision = "expand" if novel_item is not None else "prune"
    novelty_table_after = set(novelty_table_before)
    if decision == "expand":
        novelty_table_after.update(current_items)

    successors: list[IWSuccessor] = []
    frontier_after: list[str] = []
    for action in problem.legal_actions(atom_set):
        next_state = problem.transition(atom_set, action)
        next_items = novelty_items(next_state, width=width)
        is_novel = first_novel_item(next_items, novelty_table_after) is not None
        enqueued = decision == "expand" and is_novel
        if enqueued:
            frontier_after.append(problem.state_id(next_state))
        successors.append(
            IWSuccessor(
                action=action.serialize(),
                enqueued=enqueued,
                is_goal=problem.is_goal(next_state),
                is_novel=is_novel,
                state_atoms=sorted(next_state),
                state_id=problem.state_id(next_state),
            )
        )

    selected_successor = problem.transition(atom_set, selected_action)
    record = {
        "algorithm": "iterated_width",
        "domain": "blocksworld",
        "goal_atoms": sorted(problem.goal_atoms),
        "instance_id": instance_id,
        "is_terminal": problem.is_goal(atom_set),
        "iterated_width": {
            "atoms": sorted(atom_set),
            "decision": decision,
            "frontier_after": frontier_after,
            "novel_item": serialize_novelty_item(novel_item) if novel_item is not None else None,
            "novelty_table_after": serialize_novelty_table(novelty_table_after),
            "novelty_table_before": serialize_novelty_table(novelty_table_before),
            "selected_successor_id": problem.state_id(selected_successor),
            "successors": [successor.to_dict() for successor in successors],
            "tie_break_rule": BFS_TIE_BREAK_RULE,
            "tuples": [serialize_novelty_item(item) for item in current_items],
            "width": width,
        },
        "legal_actions": list(problem.legal_action_strings(atom_set)),
        "metadata": {
            "fixture": str(fixture_path),
            "schema_version": SCHEMA_VERSION,
            "source": "local_iterated_width_expert_generator",
            "world_model": WORLD_MODEL,
        },
        "selected_action": selected_action.serialize(),
        "state_atoms": sorted(atom_set),
        "state_id": state_id,
        "step_index": step_index,
        "trajectory_id": f"{instance_id}__iterated_width",
    }
    return canonicalize_trajectory_step(record)


def novelty_items(state: Iterable[str], *, width: int) -> tuple[NoveltyItem, ...]:
    if width <= 0:
        raise ValueError("width must be positive")
    atoms = sorted(frozenset(state))
    if width == 1:
        return tuple((atom,) for atom in atoms)
    return tuple(tuple(item) for item in combinations(atoms, width))


def first_novel_item(items: Iterable[NoveltyItem], novelty_table: set[NoveltyItem]) -> NoveltyItem | None:
    for item in items:
        if item not in novelty_table:
            return item
    return None


def serialize_novelty_item(item: NoveltyItem) -> str | list[str]:
    if len(item) == 1:
        return item[0]
    return list(item)


def serialize_novelty_table(items: Iterable[NoveltyItem]) -> list[str | list[str]]:
    return [serialize_novelty_item(item) for item in sorted(items)]


__all__ = [
    "DEFAULT_WIDTH",
    "build_iterated_width_step_record",
    "first_novel_item",
    "generate_iterated_width_trajectory",
    "iterated_width_plan",
    "novelty_items",
    "serialize_novelty_item",
    "serialize_novelty_table",
]
