from __future__ import annotations

from collections import deque
from typing import Final

from .local_planner_types import JSONValue, LocalPlannerRequest, SearchNode
from .pddl import Atom, GroundAction, canonical_atom

DEFAULT_MAX_APPLICABLE_ACTIONS: Final = 2000


def bounded_serial_plan(request: LocalPlannerRequest, start: frozenset[Atom]) -> tuple[list[str], dict[str, JSONValue], str]:
    frontier: deque[SearchNode] = deque([SearchNode(start, tuple())])
    visited = {start}
    events: list[JSONValue] = []
    expansions = 0
    while frontier:
        node = frontier.popleft()
        if request.task.goal.issubset(node.state):
            return list(node.plan), _trace(expansions, events, len(visited)), "success_full_trace"
        if len(node.plan) >= request.limits["gbfs_max_depth"]:
            continue
        expansions += 1
        if expansions > _limit(request, "local_serial_recovery_max_expansions", request.limits["gbfs_max_expansions"]):
            return [], _trace(expansions, events, len(visited)), "skipped_resource_limit"
        actions = _applicable_actions(request.grounded, node.state)
        if len(actions) > _limit(request, "local_max_applicable_actions", DEFAULT_MAX_APPLICABLE_ACTIONS):
            return [], _trace(expansions, events, len(visited)), "skipped_resource_limit"
        successors: list[JSONValue] = []
        for action in actions:
            next_state = _apply(action, node.state)
            is_new = next_state not in visited
            successors.append({"action": action.canonical, "is_goal": request.task.goal.issubset(next_state), "new_state": is_new})
            if not is_new:
                continue
            next_plan = (*node.plan, action.canonical)
            if len(next_plan) > request.limits["max_plan_length"]:
                return [], _trace(expansions, events, len(visited)), "skipped_resource_limit"
            if request.task.goal.issubset(next_state):
                if len(events) < request.limits["max_trace_steps"]:
                    events.append(_event(node.state, successors, len(frontier), len(visited) + 1))
                return list(next_plan), _trace(expansions, events, len(visited) + 1), "success_full_trace"
            visited.add(next_state)
            frontier.append(SearchNode(next_state, next_plan))
        if len(events) < request.limits["max_trace_steps"]:
            events.append(_event(node.state, successors, len(frontier), len(visited)))
    return [], _trace(expansions, events, len(visited)), "failed_no_plan_extracted"


def _trace(expansions: int, events: list[JSONValue], visited_count: int) -> dict[str, JSONValue]:
    return {"expansion_count": expansions, "events": events, "visited_count": visited_count}


def _event(state: frozenset[Atom], successors: list[JSONValue], frontier_size: int, visited_count: int) -> dict[str, JSONValue]:
    return {"state_atoms": _atoms(state), "successors": successors, "frontier_size_after": frontier_size, "visited_count_after": visited_count}


def _applicable_actions(grounded: tuple[GroundAction, ...], state: frozenset[Atom]) -> list[GroundAction]:
    return [action for action in sorted(grounded, key=lambda item: item.canonical) if action.preconditions.issubset(state)]


def _apply(action: GroundAction, state: frozenset[Atom]) -> frozenset[Atom]:
    next_state = set(state)
    next_state.difference_update(action.del_effects)
    next_state.update(action.add_effects)
    return frozenset(next_state)


def _atoms(state: frozenset[Atom]) -> list[str]:
    return sorted(canonical_atom(atom) for atom in state)


def _limit(request: LocalPlannerRequest, key: str, default: int) -> int:
    return request.limits.get(key, default)
