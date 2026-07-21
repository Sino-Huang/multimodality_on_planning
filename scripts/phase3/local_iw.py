from __future__ import annotations

from collections import deque
from itertools import combinations
from typing import Final

from .local_goal_regression import GoalRegressionRequest, recover_goal_regression_plan, should_try_goal_regression_first
from .local_planner_types import JSONValue, LocalPlannerRequest, LocalPlannerResult, SearchNode
from .local_serial import bounded_serial_plan
from .pddl import Atom, GroundAction, canonical_atom

DEFAULT_MAX_APPLICABLE_ACTIONS: Final = 2000
DEFAULT_LOCAL_IW_MAX_WIDTH: Final = 3
MAX_IW_TRACE_NOVELTY_ITEMS: Final = 200


def run_iterated_width(request: LocalPlannerRequest) -> LocalPlannerResult:
    width = _limit(request, "local_iw_width", 1)
    max_width = _limit(request, "local_iw_max_width", DEFAULT_LOCAL_IW_MAX_WIDTH)
    if width < 1 or width > max_width:
        return LocalPlannerResult([], _iw_trace(width, []), "skipped_resource_limit")
    start = frozenset(request.task.init)
    if request.task.goal.issubset(start):
        return LocalPlannerResult([], _iw_trace(width, []), "success_full_trace")
    if should_try_goal_regression_first(request.task, request.limits):
        early_recovery = recover_goal_regression_plan(GoalRegressionRequest(request.task, request.grounded, request.limits, "goal_regression_before_iw_novelty", "many_goal_recovery_preferred"))
        if early_recovery.status == "success_full_trace":
            trace = _iw_trace(width, [])
            trace["plan_recovery"] = {
                **early_recovery.trace,
                "is_exact_iw": False,
                "reason": "many_goal_recovery_preferred",
            }
            return LocalPlannerResult(early_recovery.plan, trace, "success_full_trace")
    frontier: deque[SearchNode] = deque([SearchNode(start, tuple())])
    novelty_table: set[tuple[str, ...]] = set()
    visited = {start}
    events: list[JSONValue] = []
    expansions = 0
    while frontier:
        node = frontier.popleft()
        current_items = _novelty_items(node.state, width)
        novel_item = _first_novel(current_items, novelty_table) or (() if not node.plan else None)
        if novel_item is None:
            if len(events) < request.limits["max_trace_steps"]:
                events.append({"decision": "prune", "event_kind": "backtrack", "state_atoms": _atoms(node.state), "frontier_size_after": len(frontier)})
            continue
        novelty_before = _serialized_novelty_table(novelty_table)
        novelty_table.update(current_items)
        expansions += 1
        if expansions > _limit(request, "local_iw_novelty_max_expansions", request.limits["gbfs_max_expansions"]):
            return _recover_at_max_width(request, start, width, max_width, events, "novelty_expansion_cap_reached", "skipped_resource_limit")
        successors: list[JSONValue] = []
        applicable = _applicable_actions(request.grounded, node.state)
        if len(applicable) > _limit(request, "local_max_applicable_actions", DEFAULT_MAX_APPLICABLE_ACTIONS):
            return LocalPlannerResult([], _iw_trace(width, events), "skipped_resource_limit")
        for action in applicable:
            next_state = _apply(action, node.state)
            is_novel = _first_novel(_novelty_items(next_state, width), novelty_table) is not None
            enqueued = is_novel and next_state not in visited
            event_kind = "generation" if enqueued else "revisit" if next_state in visited else "backtrack"
            successors.append({"action": action.canonical, "event_kind": event_kind, "is_goal": request.task.goal.issubset(next_state), "is_novel": is_novel, "enqueued": enqueued})
            if not enqueued:
                continue
            next_plan = (*node.plan, action.canonical)
            if len(next_plan) > request.limits["max_plan_length"]:
                return LocalPlannerResult([], _iw_trace(width, events), "skipped_resource_limit")
            if request.task.goal.issubset(next_state):
                if len(events) < request.limits["max_trace_steps"]:
                    events.append(_iw_event(node.state, novelty_before, novelty_table, novel_item, successors, frontier))
                return LocalPlannerResult(list(next_plan), _iw_trace(width, events), "success_full_trace")
            visited.add(next_state)
            frontier.append(SearchNode(next_state, next_plan))
        if len(events) < request.limits["max_trace_steps"]:
            events.append(_iw_event(node.state, novelty_before, novelty_table, novel_item, successors, frontier))
    return _recover_at_max_width(request, start, width, max_width, events, "novelty_search_exhausted", "failed_no_plan_extracted")


def _iw_trace(width: int, events: list[JSONValue]) -> dict[str, JSONValue]:
    return {"trace_contract_version": "phase3_traversal_trace_v1", "algorithm": "iterated_width", "width": width, "events": events}


def _recover_at_max_width(request: LocalPlannerRequest, start: frozenset[Atom], width: int, max_width: int, events: list[JSONValue], reason: str, original_status: str) -> LocalPlannerResult:
    if width != max_width:
        return LocalPlannerResult([], _iw_trace(width, events), original_status)
    plan, recovery_trace, status = bounded_serial_plan(request, start)
    trace = _iw_trace(width, events[: _limit(request, "local_iw_recovery_trace_steps", 20)])
    if status != "success_full_trace":
        goal_recovery = recover_goal_regression_plan(GoalRegressionRequest(request.task, request.grounded, request.limits, "goal_regression_after_iw_novelty", original_status))
        if goal_recovery.status == "success_full_trace":
            trace["plan_recovery"] = {
                **goal_recovery.trace,
                "is_exact_iw": False,
                "reason": reason,
            }
            return LocalPlannerResult(goal_recovery.plan, trace, "success_full_trace")
        return LocalPlannerResult([], trace, status)
    trace["plan_recovery"] = {
        "source": "bounded_serial_recovery_after_iw_novelty",
        "is_exact_iw": False,
        "reason": reason,
        "original_status": original_status,
        "expansion_count": recovery_trace["expansion_count"],
        "visited_count": recovery_trace["visited_count"],
    }
    return LocalPlannerResult(plan, trace, "success_full_trace")


def _iw_event(state: frozenset[Atom], before: list[str], table: set[tuple[str, ...]], novel: tuple[str, ...], successors: list[JSONValue], frontier: deque[SearchNode]) -> dict[str, JSONValue]:
    return {"decision": "expand", "event_kind": "expansion", "state_atoms": _atoms(state), "novel_item": _serialize_tuple(novel), "novelty_table_before": before, "novelty_table_after": _serialized_novelty_table(table), "successors": successors, "frontier_size_after": len(frontier)}


def _serialized_novelty_table(table: set[tuple[str, ...]]) -> list[str]:
    return sorted(_serialize_tuple(item) for item in table)[:MAX_IW_TRACE_NOVELTY_ITEMS]


def _applicable_actions(grounded: tuple[GroundAction, ...], state: frozenset[Atom]) -> list[GroundAction]:
    return [action for action in sorted(grounded, key=lambda item: item.canonical) if action.preconditions.issubset(state)]


def _limit(request: LocalPlannerRequest, key: str, default: int) -> int:
    return request.limits.get(key, default)


def _apply(action: GroundAction, state: frozenset[Atom]) -> frozenset[Atom]:
    next_state = set(state)
    next_state.difference_update(action.del_effects)
    next_state.update(action.add_effects)
    return frozenset(next_state)


def _atoms(state: frozenset[Atom]) -> list[str]:
    return sorted(canonical_atom(atom) for atom in state)


def _novelty_items(state: frozenset[Atom], width: int) -> tuple[tuple[str, ...], ...]:
    atoms = tuple(canonical_atom(atom) for atom in sorted(state))
    return tuple(item for size in range(1, width + 1) for item in combinations(atoms, size))


def _first_novel(items: tuple[tuple[str, ...], ...], table: set[tuple[str, ...]]) -> tuple[str, ...] | None:
    for item in items:
        if item not in table:
            return item
    return None


def _serialize_tuple(item: tuple[str, ...]) -> str:
    return " | ".join(item)
