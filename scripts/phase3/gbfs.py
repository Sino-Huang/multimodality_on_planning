from __future__ import annotations

from heapq import heappop, heappush
from itertools import count
from typing import Any

from .pddl import GroundAction, PDDLTask, canonical_atom, estimate_grounded_action_count


def run_gbfs(task: PDDLTask, grounded: list[GroundAction], *, limits: dict[str, int]) -> tuple[list[str], dict[str, Any], str]:
    start = frozenset(task.init)
    if task.goal.issubset(start):
        return [], gbfs_trace([], 0, 1), "success_full_trace"
    frontier: list[tuple[int, int, int, frozenset[tuple[str, ...]], tuple[str, ...]]] = []
    sequence = count()
    heappush(frontier, (_unsatisfied_goal_count(task, start), 0, next(sequence), start, tuple()))
    best_depth_by_state = {start: 0}
    events: list[dict[str, Any]] = []
    expansions = 0
    hit_resource_limit = False
    while frontier:
        heuristic_value, _depth, _sequence_id, state, plan = heappop(frontier)
        if len(plan) > best_depth_by_state.get(state, limits["max_plan_length"] + 1):
            continue
        if len(plan) >= limits["gbfs_max_depth"]:
            hit_resource_limit = True
            continue
        expansions += 1
        if expansions > limits["gbfs_max_expansions"]:
            return [], gbfs_trace(events, expansions, len(best_depth_by_state)), "skipped_resource_limit"
        successors: list[dict[str, Any]] = []
        selected_goal_plan: list[str] | None = None
        selected_goal_successor: dict[str, Any] | None = None
        for action in grounded:
            if not action.preconditions.issubset(state):
                continue
            next_state = set(state)
            next_state.difference_update(action.del_effects)
            next_state.update(action.add_effects)
            frozen_next = frozenset(next_state)
            successor_heuristic = _unsatisfied_goal_count(task, frozen_next)
            next_plan = (*plan, action.canonical)
            best_known_depth = best_depth_by_state.get(frozen_next)
            improves_depth = best_known_depth is None or len(next_plan) < best_known_depth
            successor = {"action": action.canonical, "heuristic_value": successor_heuristic, "is_goal": successor_heuristic == 0, "enqueued": False}
            if len(next_plan) > limits["max_plan_length"]:
                hit_resource_limit = True
                successor["resource_limited"] = True
                successors.append(successor)
                continue
            if not improves_depth:
                successors.append(successor)
                continue
            if successor_heuristic == 0:
                if selected_goal_plan is None:
                    selected_goal_plan = list(next_plan)
                    selected_goal_successor = successor
                successors.append(successor)
                continue
            best_depth_by_state[frozen_next] = len(next_plan)
            successor["enqueued"] = True
            successors.append(successor)
            heappush(frontier, (successor_heuristic, len(next_plan), next(sequence), frozen_next, next_plan))
        if selected_goal_plan is not None:
            if len(events) < limits["max_trace_steps"]:
                events.append(_gbfs_event(state, heuristic_value, frontier, len(best_depth_by_state), successors, selected_goal_successor=selected_goal_successor))
            return selected_goal_plan, gbfs_trace(events[: limits["max_trace_steps"]], expansions, len(best_depth_by_state)), "success_full_trace"
        if len(events) < limits["max_trace_steps"]:
            events.append(_gbfs_event(state, heuristic_value, frontier, len(best_depth_by_state), successors))
    status = "skipped_resource_limit" if hit_resource_limit else "failed_no_plan_extracted"
    return [], gbfs_trace(events, expansions, len(best_depth_by_state)), status


def gbfs_trace(events: list[dict[str, Any]], expansions: int, visited_count: int) -> dict[str, Any]:
    return {
        "algorithm": "greedy_best_first",
        "heuristic_source": "unsatisfied_goal_count",
        "expansion_count": expansions,
        "frontier_events": events,
        "visited_count": visited_count,
    }


def gbfs_estimate_exceeds_resource_gate(task: PDDLTask, limits: dict[str, int]) -> bool:
    cap = limits["gbfs_max_applicable_actions"]
    return estimate_grounded_action_count(task, stop_after=cap) > cap


def _gbfs_event(state: frozenset[tuple[str, ...]], heuristic_value: int, frontier: list[tuple[int, int, int, frozenset[tuple[str, ...]], tuple[str, ...]]], visited_count: int, successors: list[dict[str, Any]], *, selected_goal_successor: dict[str, Any] | None = None) -> dict[str, Any]:
    event = {
        "selected_state_atoms": sorted(canonical_atom(atom) for atom in state),
        "current_heuristic": {"heuristic_value": heuristic_value, "unsatisfied_goal_count": heuristic_value},
        "frontier_size_after": len(frontier),
        "visited_count_after": visited_count,
        "successor_heuristics": sorted(successors, key=lambda item: (item["heuristic_value"], item["action"])),
        "tie_break_rule": "min_unsatisfied_goals_then_plan_length_then_generation_order",
    }
    if selected_goal_successor is not None:
        event["selected_goal_successor"] = selected_goal_successor
    return event


def _unsatisfied_goal_count(task: PDDLTask, state: frozenset[tuple[str, ...]]) -> int:
    return len(task.goal.difference(state))
