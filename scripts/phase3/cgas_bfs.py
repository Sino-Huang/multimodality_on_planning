from __future__ import annotations

import hashlib
import json
from bisect import insort
from collections import deque
from dataclasses import dataclass
from typing import Final

from .local_planner_types import JSONValue, TraceEventSink, record_trace_event
from .pddl import Atom, GroundAction, PDDLTask, canonical_atom

ALGORITHM: Final = "breadth_first_search"
TIE_BREAK: Final = "legal_actions_sorted_by_canonical_action_string"


@dataclass(frozen=True, slots=True)
class BFSResult:
    plan: tuple[str, ...]
    trace: dict[str, JSONValue]
    status: str


def run_fifo_bfs(
    task: PDDLTask,
    grounded: tuple[GroundAction, ...],
    limits: dict[str, int],
    trace_sink: TraceEventSink | None = None,
) -> BFSResult:
    """Run canonical FIFO BFS over the repository PDDL state transition model."""
    start = frozenset(task.init)
    if task.goal.issubset(start):
        return BFSResult((), _trace([], 0, trace_sink is not None), "success_full_trace")
    ordered_grounded = tuple(sorted(grounded, key=lambda candidate: candidate.canonical))
    frontier: deque[tuple[frozenset[Atom], tuple[str, ...]]] = deque([(start, tuple())])
    visited = {start}
    state_index = _StateIndex(start)
    expansions: list[dict[str, JSONValue]] = []
    expansion_count = 0
    while frontier:
        state, plan = frontier.popleft()
        expansion_count += 1
        if expansion_count > limits["max_expansions"]:
            return BFSResult((), _trace(expansions, expansion_count, trace_sink is not None), "skipped_resource_limit")
        actions = [action for action in ordered_grounded if action.preconditions.issubset(state)]
        retain_expansion = trace_sink is not None or len(expansions) < limits["max_trace_steps"]
        successor_rows: list[dict[str, JSONValue]] = []
        for action in actions:
            successor = _apply(action, state)
            successor_id = state_index.identify(successor)
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
                        "state_id": successor_id,
                        "was_visited": was_visited,
                    }
                )
            if not enqueued:
                continue
            next_plan = (*plan, action.canonical)
            if len(next_plan) > limits["max_plan_length"]:
                return BFSResult(
                    (), _trace(expansions, expansion_count, trace_sink is not None), "skipped_resource_limit"
                )
            visited.add(successor)
            state_index.add(successor_id)
            frontier.append((successor, next_plan))
            if is_goal:
                if retain_expansion:
                    record_trace_event(expansions, trace_sink, state_index.expansion(state, frontier, successor_rows))
                trace = _trace(expansions, expansion_count, trace_sink is not None)
                return BFSResult(
                    next_plan,
                    trace,
                    "success_full_trace" if trace["trace_complete"] is True else "success_truncated_trace",
                )
        if retain_expansion:
            record_trace_event(expansions, trace_sink, state_index.expansion(state, frontier, successor_rows))
    return BFSResult((), _trace(expansions, expansion_count, trace_sink is not None), "failed_no_plan_extracted")


def _trace(
    expansions: list[dict[str, JSONValue]],
    expansion_count: int,
    streamed: bool = False,
) -> dict[str, JSONValue]:
    return {
        "algorithm": ALGORITHM,
        "expansion_count": expansion_count,
        "expansions": expansions,
        "tie_break_rule": TIE_BREAK,
        "trace_complete": streamed or len(expansions) == expansion_count,
        "trace_contract_version": "cgas_p0_trace_v1",
    }


class _StateIndex:
    __slots__ = ("_identities", "_visited")

    def __init__(self, start: frozenset[Atom]) -> None:
        identity = _state_id(start)
        self._identities = {start: identity}
        self._visited = [identity]

    def identify(self, state: frozenset[Atom]) -> str:
        identity = self._identities.get(state)
        if identity is None:
            identity = _state_id(state)
            self._identities[state] = identity
        return identity

    def add(self, identity: str) -> None:
        insort(self._visited, identity)

    def expansion(
        self,
        state: frozenset[Atom],
        frontier: deque[tuple[frozenset[Atom], tuple[str, ...]]],
        successors: list[dict[str, JSONValue]],
    ) -> dict[str, JSONValue]:
        state_id = self.identify(state)
        return {
            "actions_considered": [row["action"] for row in successors],
            "frontier_after": [self.identify(item[0]) for item in frontier],
            "frontier_before": [state_id],
            "state_atoms": _atoms(state),
            "state_id": state_id,
            "successors": successors,
            "visited_after": list(self._visited),
        }


def _apply(action: GroundAction, state: frozenset[Atom]) -> frozenset[Atom]:
    return frozenset((state - action.del_effects) | action.add_effects)


def _atoms(state: frozenset[Atom]) -> list[str]:
    return sorted(canonical_atom(atom) for atom in state)


def _state_id(state: frozenset[Atom]) -> str:
    return hashlib.sha256(json.dumps(_atoms(state), separators=(",", ":")).encode("utf-8")).hexdigest()
