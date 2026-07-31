from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Final

from .local_planner_types import JSONValue
from .pddl import Atom, GroundAction, PDDLTask, canonical_atom


ALGORITHM: Final = "breadth_first_search"
TIE_BREAK: Final = "legal_actions_sorted_by_canonical_action_string"


@dataclass(frozen=True, slots=True)
class BFSResult:
    plan: tuple[str, ...]
    trace: dict[str, JSONValue]
    status: str


def run_fifo_bfs(task: PDDLTask, grounded: tuple[GroundAction, ...], limits: dict[str, int]) -> BFSResult:
    """Run canonical FIFO BFS over the repository PDDL state transition model."""
    start = frozenset(task.init)
    if task.goal.issubset(start):
        return BFSResult((), _trace([], 0), "success_full_trace")
    ordered_grounded = tuple(sorted(grounded, key=lambda candidate: candidate.canonical))
    frontier: deque[tuple[frozenset[Atom], tuple[str, ...]]] = deque([(start, tuple())])
    visited = {start}
    expansions: list[dict[str, JSONValue]] = []
    expansion_count = 0
    while frontier:
        state, plan = frontier.popleft()
        expansion_count += 1
        if expansion_count > limits["max_expansions"]:
            return BFSResult((), _trace(expansions, expansion_count), "skipped_resource_limit")
        actions = [action for action in ordered_grounded if action.preconditions.issubset(state)]
        retain_expansion = len(expansions) < limits["max_trace_steps"]
        successor_rows: list[dict[str, JSONValue]] = []
        for action in actions:
            successor = _apply(action, state)
            was_visited = successor in visited
            enqueued = not was_visited
            is_goal = task.goal.issubset(successor)
            if retain_expansion:
                successor_rows.append(
                    {
                        "action": action.canonical,
                        "enqueued": enqueued,
                        "is_goal": is_goal,
                        "state_atoms": _atoms(successor),
                        "state_id": _state_id(successor),
                        "was_visited": was_visited,
                    }
                )
            if not enqueued:
                continue
            next_plan = (*plan, action.canonical)
            if len(next_plan) > limits["max_plan_length"]:
                return BFSResult((), _trace(expansions, expansion_count), "skipped_resource_limit")
            visited.add(successor)
            frontier.append((successor, next_plan))
            if is_goal:
                if retain_expansion:
                    expansions.append(_expansion(state, frontier, visited, successor_rows))
                trace = _trace(expansions, expansion_count)
                return BFSResult(
                    next_plan,
                    trace,
                    "success_full_trace"
                    if trace["trace_complete"] is True
                    else "success_truncated_trace",
                )
        if retain_expansion:
            expansions.append(_expansion(state, frontier, visited, successor_rows))
    return BFSResult((), _trace(expansions, expansion_count), "failed_no_plan_extracted")


def _trace(expansions: list[dict[str, JSONValue]], expansion_count: int) -> dict[str, JSONValue]:
    return {
        "algorithm": ALGORITHM,
        "expansion_count": expansion_count,
        "expansions": expansions,
        "tie_break_rule": TIE_BREAK,
        "trace_complete": len(expansions) == expansion_count,
        "trace_contract_version": "cgas_p0_trace_v1",
    }


def _expansion(
    state: frozenset[Atom],
    frontier: deque[tuple[frozenset[Atom], tuple[str, ...]]],
    visited: set[frozenset[Atom]],
    successors: list[dict[str, JSONValue]],
) -> dict[str, JSONValue]:
    return {
        "actions_considered": [row["action"] for row in successors],
        "frontier_after": [_state_id(item[0]) for item in frontier],
        "frontier_before": [_state_id(state)],
        "state_atoms": _atoms(state),
        "state_id": _state_id(state),
        "successors": successors,
        "visited_after": sorted(_state_id(item) for item in visited),
    }


def _apply(action: GroundAction, state: frozenset[Atom]) -> frozenset[Atom]:
    return frozenset((state - action.del_effects) | action.add_effects)


def _atoms(state: frozenset[Atom]) -> list[str]:
    return sorted(canonical_atom(atom) for atom in state)


def _state_id(state: frozenset[Atom]) -> str:
    import hashlib
    import json

    return hashlib.sha256(json.dumps(_atoms(state), separators=(",", ":")).encode("utf-8")).hexdigest()
