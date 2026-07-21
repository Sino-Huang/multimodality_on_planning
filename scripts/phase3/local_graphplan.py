from __future__ import annotations

from collections import deque
from itertools import combinations
from typing import Final

from .local_goal_regression import GoalRegressionRequest, recover_goal_regression_plan, should_try_goal_regression_first
from .local_planner_types import JSONValue, LocalPlannerRequest, LocalPlannerResult, SearchNode
from .pddl import Atom, GroundAction, canonical_atom

DEFAULT_MAX_APPLICABLE_ACTIONS: Final = 2000
DEFAULT_MAX_MUTEX_PAIRS: Final = 10000


def run_graphplan(request: LocalPlannerRequest) -> LocalPlannerResult:
    grounded = _sorted_grounded(request.grounded)
    if should_try_goal_regression_first(request.task, request.limits):
        recovery = recover_goal_regression_plan(GoalRegressionRequest(request.task, grounded, request.limits, "goal_regression_before_graphplan_extraction", "many_goal_recovery_preferred"))
        if recovery.status == "success_full_trace":
            plan_result = LocalPlannerResult(recovery.plan, {"expansion_count": recovery.trace["attempt_count"]}, "success_full_trace")
            trace, status = _planning_graph_trace(request, plan_result, grounded)
            trace["extraction"]["plan_recovery"] = {
                **recovery.trace,
                "is_exact_graphplan_extraction": False,
            }
            if status is None:
                return LocalPlannerResult(recovery.plan, trace, "success_full_trace")
    plan_result = _bounded_serial_extraction(request, grounded)
    trace, status = _planning_graph_trace(request, plan_result, grounded)
    if status is not None:
        return LocalPlannerResult([], trace, status)
    if plan_result.status != "success_full_trace":
        if should_try_goal_regression_first(request.task, request.limits):
            recovery = recover_goal_regression_plan(GoalRegressionRequest(request.task, request.grounded, request.limits, "goal_regression_after_graphplan_extraction", plan_result.status))
            if recovery.status == "success_full_trace":
                trace["extraction"]["selected_plan"] = recovery.plan
                trace["extraction"]["plan_recovery"] = {
                    **recovery.trace,
                    "is_exact_graphplan_extraction": False,
                }
                return LocalPlannerResult(recovery.plan, trace, "success_full_trace")
        return LocalPlannerResult([], trace, plan_result.status)
    return LocalPlannerResult(plan_result.plan, trace, "success_full_trace")


def _bounded_serial_extraction(request: LocalPlannerRequest, grounded: tuple[GroundAction, ...]) -> LocalPlannerResult:
    start = frozenset(request.task.init)
    frontier: deque[SearchNode] = deque([SearchNode(start, tuple())])
    visited = {start}
    expansions = 0
    while frontier:
        node = frontier.popleft()
        if request.task.goal.issubset(node.state):
            return LocalPlannerResult(list(node.plan), {"expansion_count": expansions}, "success_full_trace")
        expansions += 1
        if expansions > _limit(request, "local_graphplan_max_expansions", request.limits["gbfs_max_expansions"]):
            return LocalPlannerResult([], {"expansion_count": expansions}, "skipped_resource_limit")
        actions = _applicable_actions(grounded, node.state)
        if len(actions) > _limit(request, "local_max_applicable_actions", DEFAULT_MAX_APPLICABLE_ACTIONS):
            return LocalPlannerResult([], {"expansion_count": expansions}, "skipped_resource_limit")
        for action in actions:
            next_state = _apply(action, node.state)
            if next_state in visited:
                continue
            next_plan = (*node.plan, action.canonical)
            if len(next_plan) > request.limits["max_plan_length"]:
                return LocalPlannerResult([], {"expansion_count": expansions}, "skipped_resource_limit")
            visited.add(next_state)
            frontier.append(SearchNode(next_state, next_plan))
    return LocalPlannerResult([], {"expansion_count": expansions}, "failed_no_plan_extracted")


def _planning_graph_trace(request: LocalPlannerRequest, plan_result: LocalPlannerResult, grounded: tuple[GroundAction, ...]) -> tuple[dict[str, JSONValue], str | None]:
    proposition_layers: list[JSONValue] = []
    action_layers: list[JSONValue] = []
    mutex_pairs: list[JSONValue] = []
    propositions = frozenset(request.task.init)
    max_layers = min(request.limits["max_plan_length"], 16)
    selected_goal_layer = 0 if request.task.goal.issubset(propositions) else None
    status: str | None = None
    for layer_index in range(max_layers):
        proposition_layers.append({"layer_index": layer_index, "propositions": _atoms(propositions), "goal_present": request.task.goal.issubset(propositions)})
        actions = _applicable_actions(grounded, propositions)
        if len(actions) > _limit(request, "local_max_applicable_actions", DEFAULT_MAX_APPLICABLE_ACTIONS):
            status = "skipped_resource_limit"
            break
        possible_pairs = len(actions) * max(0, len(actions) - 1) // 2
        if possible_pairs > _limit(request, "local_max_mutex_pairs", DEFAULT_MAX_MUTEX_PAIRS):
            status = "skipped_resource_limit"
            break
        layer_mutex_pairs = _mutex_pairs(actions)
        mutex_pairs.extend(layer_mutex_pairs)
        next_propositions = frozenset(set(propositions).union(*(action.add_effects for action in actions)))
        action_layers.append({"layer_index": layer_index, "actions": [action.canonical for action in actions], "mutex_pairs": layer_mutex_pairs, "next_layer_index": layer_index + 1})
        if selected_goal_layer is None and request.task.goal.issubset(next_propositions):
            selected_goal_layer = layer_index + 1
        if request.task.goal.issubset(propositions) or next_propositions == propositions:
            if next_propositions != propositions:
                proposition_layers.append({"layer_index": layer_index + 1, "propositions": _atoms(next_propositions), "goal_present": request.task.goal.issubset(next_propositions)})
            break
        propositions = next_propositions
    trace: dict[str, JSONValue] = {
        "trace_contract_version": "phase3_traversal_trace_v1",
        "algorithm": "graphplan",
        "proposition_layers": proposition_layers,
        "action_layers": action_layers,
        "mutex_pairs": mutex_pairs,
        "extraction": {
            "approximation": "deterministic_phase3_action_mutex_graphplan",
            "goal_present_without_mutex": selected_goal_layer is not None,
            "mutex_scope": "action_level_only",
            "no_goods": [],
            "proposition_mutex_computed": False,
            "selected_goal_layer": selected_goal_layer,
            "selected_plan": plan_result.plan,
            "source": "local_graphplan_serial_extraction",
        },
    }
    return trace, status


def _applicable_actions(grounded: tuple[GroundAction, ...], state: frozenset[Atom]) -> list[GroundAction]:
    return [action for action in grounded if action.preconditions.issubset(state)]


def _sorted_grounded(grounded: tuple[GroundAction, ...]) -> tuple[GroundAction, ...]:
    return tuple(sorted(grounded, key=lambda item: item.canonical))


def _apply(action: GroundAction, state: frozenset[Atom]) -> frozenset[Atom]:
    next_state = set(state)
    next_state.difference_update(action.del_effects)
    next_state.update(action.add_effects)
    return frozenset(next_state)


def _atoms(state: frozenset[Atom]) -> list[str]:
    return sorted(canonical_atom(atom) for atom in state)


def _mutex_pairs(actions: list[GroundAction]) -> list[list[str]]:
    pairs: list[list[str]] = []
    for left, right in combinations(actions, 2):
        inconsistent = bool((left.add_effects & right.del_effects) or (right.add_effects & left.del_effects))
        interference = bool((left.del_effects & right.preconditions) or (right.del_effects & left.preconditions))
        if inconsistent or interference:
            pairs.append([left.canonical, right.canonical])
    return pairs


def _limit(request: LocalPlannerRequest, key: str, default: int) -> int:
    return request.limits.get(key, default)
