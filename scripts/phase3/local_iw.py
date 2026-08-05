from __future__ import annotations

from collections import deque
from typing import Final

from .local_goal_regression import GoalRegressionRequest, recover_goal_regression_plan, should_try_goal_regression_first
from .local_iw_novelty import first_novel, novelty_items, serialize_tuple, serialized_novelty_table, state_atoms
from .local_planner_types import (
    JSONValue,
    LocalPlannerRequest,
    LocalPlannerResult,
    RecoveryPolicy,
    SearchNode,
    record_trace_event,
)
from .local_serial import bounded_serial_plan
from .pddl import Atom, GroundAction

DEFAULT_MAX_APPLICABLE_ACTIONS: Final = 2000
DEFAULT_LOCAL_IW_MAX_WIDTH: Final = 3


def run_iterated_width(request: LocalPlannerRequest) -> LocalPlannerResult:
    width = _limit(request, "local_iw_width", 1)
    max_width = _limit(request, "local_iw_max_width", DEFAULT_LOCAL_IW_MAX_WIDTH)
    if width < 1 or width > max_width:
        return LocalPlannerResult([], _iw_trace(width, [], 0, 0), "skipped_resource_limit")
    start = frozenset(request.task.init)
    if request.task.goal.issubset(start):
        return LocalPlannerResult([], _iw_trace(width, [], 0, 0), "success_full_trace")
    ordered_grounded = tuple(sorted(request.grounded, key=lambda item: item.canonical))
    if request.recovery_policy is RecoveryPolicy.ENABLED and should_try_goal_regression_first(
        request.task, request.limits
    ):
        early_recovery = recover_goal_regression_plan(
            GoalRegressionRequest(
                request.task,
                request.grounded,
                request.limits,
                "goal_regression_before_iw_novelty",
                "many_goal_recovery_preferred",
            )
        )
        if early_recovery.status == "success_full_trace":
            trace = _iw_trace(width, [], 0, 0)
            trace["plan_recovery"] = {
                **early_recovery.trace,
                "is_exact_iw": False,
                "reason": "many_goal_recovery_preferred",
            }
            return LocalPlannerResult(early_recovery.plan, trace, "success_full_trace")
    frontier: deque[SearchNode] = deque([SearchNode(start, tuple())])
    novelty_table: set[tuple[str, ...]] = set()
    visited = {start}
    events: list[dict[str, JSONValue]] = []
    expansions = 0
    trace_event_count = 0
    while frontier:
        node = frontier.popleft()
        current_items = novelty_items(node.state, width)
        novel_item = first_novel(current_items, novelty_table) or (() if not node.plan else None)
        if novel_item is None:
            trace_event_count += 1
            if request.trace_sink is not None or len(events) < request.limits["max_trace_steps"]:
                table = serialized_novelty_table(novelty_table)
                record_trace_event(events, request.trace_sink, _iw_prune_event(node.state, table, len(frontier), width))
            continue
        retain_event = request.trace_sink is not None or len(events) < request.limits["max_trace_steps"]
        novelty_before = serialized_novelty_table(novelty_table) if retain_event else []
        novelty_table.update(current_items)
        expansions += 1
        if expansions > _limit(request, "local_iw_novelty_max_expansions", request.limits["gbfs_max_expansions"]):
            return _recover_at_max_width(
                request,
                start,
                width,
                max_width,
                events,
                expansions,
                trace_event_count,
                "novelty_expansion_cap_reached",
                "skipped_resource_limit",
            )
        successors: list[JSONValue] = []
        applicable = _applicable_actions(ordered_grounded, node.state)
        if len(applicable) > _limit(request, "local_max_applicable_actions", DEFAULT_MAX_APPLICABLE_ACTIONS):
            return LocalPlannerResult(
                [],
                _iw_trace(width, events, expansions, trace_event_count, request.trace_sink is not None),
                "skipped_resource_limit",
            )
        for action in applicable:
            next_state = _apply(action, node.state)
            is_novel = first_novel(novelty_items(next_state, width), novelty_table) is not None
            enqueued = is_novel and next_state not in visited
            event_kind = "generation" if enqueued else "revisit" if next_state in visited else "backtrack"
            is_goal = request.task.goal.issubset(next_state)
            if retain_event:
                successors.append(
                    {
                        "action": action.canonical,
                        "event_kind": event_kind,
                        "is_goal": is_goal,
                        "is_novel": is_novel,
                        "enqueued": enqueued,
                    }
                )
            if not enqueued:
                continue
            next_plan = (*node.plan, action.canonical)
            if len(next_plan) > request.limits["max_plan_length"]:
                return LocalPlannerResult(
                    [],
                    _iw_trace(width, events, expansions, trace_event_count, request.trace_sink is not None),
                    "skipped_resource_limit",
                )
            if is_goal:
                trace_event_count += 1
                if retain_event:
                    record_trace_event(
                        events,
                        request.trace_sink,
                        _iw_event(node.state, novelty_before, novelty_table, novel_item, successors, frontier, width),
                    )
                trace = _iw_trace(width, events, expansions, trace_event_count, request.trace_sink is not None)
                return LocalPlannerResult(
                    list(next_plan),
                    trace,
                    "success_full_trace" if trace["trace_complete"] is True else "success_truncated_trace",
                )
            visited.add(next_state)
            frontier.append(SearchNode(next_state, next_plan))
        trace_event_count += 1
        if retain_event:
            record_trace_event(
                events,
                request.trace_sink,
                _iw_event(node.state, novelty_before, novelty_table, novel_item, successors, frontier, width),
            )
    return _recover_at_max_width(
        request,
        start,
        width,
        max_width,
        events,
        expansions,
        trace_event_count,
        "novelty_search_exhausted",
        "failed_no_plan_extracted",
    )


def _iw_trace(
    width: int,
    events: list[dict[str, JSONValue]],
    expansion_count: int,
    trace_event_count: int,
    streamed: bool = False,
) -> dict[str, JSONValue]:
    return {
        "trace_contract_version": "phase3_traversal_trace_v1",
        "algorithm": "iterated_width",
        "width": width,
        "events": events,
        "expansion_count": expansion_count,
        "trace_complete": streamed or len(events) == trace_event_count,
    }


def _recover_at_max_width(
    request: LocalPlannerRequest,
    start: frozenset[Atom],
    width: int,
    max_width: int,
    events: list[dict[str, JSONValue]],
    expansion_count: int,
    trace_event_count: int,
    reason: str,
    original_status: str,
) -> LocalPlannerResult:
    if width != max_width or request.recovery_policy is RecoveryPolicy.DISABLED:
        return LocalPlannerResult(
            [],
            _iw_trace(width, events, expansion_count, trace_event_count, request.trace_sink is not None),
            original_status,
        )
    plan, recovery_trace, status = bounded_serial_plan(request, start)
    trace = _iw_trace(
        width,
        events[: _limit(request, "local_iw_recovery_trace_steps", 20)],
        expansion_count,
        trace_event_count,
        request.trace_sink is not None,
    )
    if status != "success_full_trace":
        goal_recovery = recover_goal_regression_plan(
            GoalRegressionRequest(
                request.task, request.grounded, request.limits, "goal_regression_after_iw_novelty", original_status
            )
        )
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


def _iw_event(
    state: frozenset[Atom],
    before: list[str],
    table: set[tuple[str, ...]],
    novel: tuple[str, ...],
    successors: list[JSONValue],
    frontier: deque[SearchNode],
    width: int,
) -> dict[str, JSONValue]:
    return {
        "decision": "expand",
        "event_kind": "expansion",
        "state_atoms": list(state_atoms(state)),
        "novel_item": serialize_tuple(novel),
        "novelty_table_before": list(before),
        "novelty_table_after": list(serialized_novelty_table(table)),
        "successors": successors,
        "frontier_size_after": len(frontier),
        "width_decision": f"width_{width}_novel",
    }


def _iw_prune_event(state: frozenset[Atom], table: list[str], frontier_size: int, width: int) -> dict[str, JSONValue]:
    return {
        "decision": "prune",
        "event_kind": "backtrack",
        "state_atoms": list(state_atoms(state)),
        "frontier_size_after": frontier_size,
        "novel_item": [],
        "novelty_table_before": list(table),
        "novelty_table_after": list(table),
        "width_decision": f"width_{width}_seen",
    }


def _applicable_actions(ordered_grounded: tuple[GroundAction, ...], state: frozenset[Atom]) -> list[GroundAction]:
    return [action for action in ordered_grounded if action.preconditions.issubset(state)]


def _limit(request: LocalPlannerRequest, key: str, default: int) -> int:
    return request.limits.get(key, default)


def _apply(action: GroundAction, state: frozenset[Atom]) -> frozenset[Atom]:
    next_state = set(state)
    next_state.difference_update(action.del_effects)
    next_state.update(action.add_effects)
    return frozenset(next_state)
