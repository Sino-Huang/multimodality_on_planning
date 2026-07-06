from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..blocksworld import AtomSet, BlocksworldAction, BlocksworldProblem
from ..benchmark_loop import shortest_action_plan
from ..trajectory_schema import SCHEMA_VERSION, canonicalize_trajectory_step


BFS_TIE_BREAK_RULE = "legal_actions_sorted_by_canonical_action_string"
WORLD_MODEL = "deterministic_symbolic_v0"


@dataclass(frozen=True)
class BFSSuccessor:
    action: str
    state_id: str
    state_atoms: list[str]
    is_goal: bool
    was_visited: bool
    enqueued: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "enqueued": self.enqueued,
            "is_goal": self.is_goal,
            "state_atoms": self.state_atoms,
            "state_id": self.state_id,
            "was_visited": self.was_visited,
        }


def generate_bfs_trajectory(
    *,
    problem: BlocksworldProblem,
    instance_id: str,
    fixture_path: Path,
    max_steps: int = 64,
) -> list[dict[str, Any]]:
    """Generate step-level BFS expert records for a deterministic Blocksworld plan."""

    records: list[dict[str, Any]] = []
    current_state = problem.initial_state()

    for step_index in range(max_steps):
        if problem.is_goal(current_state):
            break
        plan = shortest_action_plan(problem, current_state, max_depth=max_steps)
        if not plan:
            break
        selected_action = plan[0]
        records.append(
            build_bfs_step_record(
                problem=problem,
                instance_id=instance_id,
                fixture_path=fixture_path,
                state=current_state,
                step_index=step_index,
                selected_action=selected_action,
            )
        )
        current_state = problem.transition(current_state, selected_action)

    return records


def build_bfs_step_record(
    *,
    problem: BlocksworldProblem,
    instance_id: str,
    fixture_path: Path,
    state: Iterable[str],
    step_index: int,
    selected_action: BlocksworldAction,
) -> dict[str, Any]:
    atom_set = frozenset(state)
    state_id = problem.state_id(atom_set)
    frontier: deque[AtomSet] = deque([atom_set])
    visited_before = {state_id}
    frontier_before = [problem.state_id(item) for item in frontier]
    dequeued_state = frontier.popleft()
    dequeued_state_id = problem.state_id(dequeued_state)

    visited_after = set(visited_before)
    successors: list[BFSSuccessor] = []
    for action in problem.legal_actions(dequeued_state):
        next_state = problem.transition(dequeued_state, action)
        next_id = problem.state_id(next_state)
        was_visited = next_id in visited_after
        enqueued = not was_visited
        if enqueued:
            visited_after.add(next_id)
            frontier.append(next_state)
        successors.append(
            BFSSuccessor(
                action=action.serialize(),
                enqueued=enqueued,
                is_goal=problem.is_goal(next_state),
                state_atoms=sorted(next_state),
                state_id=next_id,
                was_visited=was_visited,
            )
        )

    record = {
        "algorithm": "bfs",
        "bfs": {
            "dequeued_state_id": dequeued_state_id,
            "frontier_after": [problem.state_id(item) for item in frontier],
            "frontier_before": frontier_before,
            "selected_successor_id": problem.state_id(problem.transition(atom_set, selected_action)),
            "successors": [successor.to_dict() for successor in successors],
            "tie_break_rule": BFS_TIE_BREAK_RULE,
            "visited_after": sorted(visited_after),
            "visited_before": sorted(visited_before),
        },
        "domain": "blocksworld",
        "goal_atoms": sorted(problem.goal_atoms),
        "instance_id": instance_id,
        "is_terminal": problem.is_goal(atom_set),
        "legal_actions": list(problem.legal_action_strings(atom_set)),
        "metadata": {
            "fixture": str(fixture_path),
            "schema_version": SCHEMA_VERSION,
            "source": "local_bfs_expert_generator",
            "world_model": WORLD_MODEL,
        },
        "selected_action": selected_action.serialize(),
        "state_atoms": sorted(atom_set),
        "state_id": state_id,
        "step_index": step_index,
        "trajectory_id": f"{instance_id}__bfs",
    }
    return canonicalize_trajectory_step(record)


__all__ = ["BFS_TIE_BREAK_RULE", "build_bfs_step_record", "generate_bfs_trajectory"]
