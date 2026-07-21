from __future__ import annotations

from heapq import heappop, heappush
from itertools import count
from typing import Final, NoReturn

from .local_goal_regression import GoalRegressionRequest, recover_goal_regression_plan, should_try_goal_regression_first
from .local_graphplan import run_graphplan
from .local_iw import run_iterated_width
from .local_serial import bounded_serial_plan
from .local_planner_types import JSONValue, LocalPlannerRequest, LocalPlannerResult
from .pddl import Atom, GroundAction, PDDLTask, canonical_atom

UNREACHABLE_HEURISTIC: Final = 1_000_000
DEFAULT_MAX_APPLICABLE_ACTIONS: Final = 2000


def assert_never(value: NoReturn) -> NoReturn:
    raise AssertionError(f"unreachable planner variant: {value}")


def run_local_planner(request: LocalPlannerRequest) -> LocalPlannerResult:
    match request.planner:
        case "ff":
            return _fast_forward(request)
        case "iw":
            return run_iterated_width(request)
        case "graphplan":
            return run_graphplan(request)
        case unreachable:
            assert_never(unreachable)


def _fast_forward(request: LocalPlannerRequest) -> LocalPlannerResult:
    state = frozenset(request.task.init)
    if request.task.goal.issubset(state):
        return LocalPlannerResult([], _ff_trace(request.task, []), "success_full_trace")
    if should_try_goal_regression_first(request.task, request.limits):
        early_recovery = recover_goal_regression_plan(GoalRegressionRequest(request.task, request.grounded, request.limits, "goal_regression_before_ff_best_first", "many_goal_recovery_preferred"))
        if early_recovery.status == "success_full_trace":
            trace = _ff_trace(request.task, _ff_trace_events(request, state, early_recovery.plan))
            trace["plan_recovery"] = early_recovery.trace
            return LocalPlannerResult(early_recovery.plan, trace, "success_full_trace")
    plan, status = _ff_best_first_plan(request, state)
    recovery: dict[str, JSONValue] | None = None
    if status != "success_full_trace":
        best_first_status = status
        recovered_plan, recovery_trace, recovery_status = bounded_serial_plan(request, state)
        if recovery_status == "success_full_trace":
            plan = recovered_plan
            status = recovery_status
            recovery = {
                "source": "bounded_serial_recovery_after_ff_best_first",
                "is_exact_fast_downward_ff": False,
                "best_first_status": best_first_status,
                "expansion_count": recovery_trace["expansion_count"],
                "visited_count": recovery_trace["visited_count"],
            }
        else:
            goal_recovery = recover_goal_regression_plan(GoalRegressionRequest(request.task, request.grounded, request.limits, "goal_regression_after_ff_best_first", best_first_status))
            if goal_recovery.status == "success_full_trace":
                plan = goal_recovery.plan
                status = goal_recovery.status
                recovery = goal_recovery.trace
    events = _ff_trace_events(request, state, plan)
    trace = _ff_trace(request.task, events)
    if recovery is not None:
        trace["plan_recovery"] = recovery
    return LocalPlannerResult(plan, trace, status)


def _ff_best_first_plan(request: LocalPlannerRequest, start: frozenset[Atom]) -> tuple[list[str], str]:
    frontier: list[tuple[int, int, str, int, frozenset[Atom], tuple[str, ...]]] = []
    sequence = count()
    start_heuristic = _relaxed_heuristic(request.task, request.grounded, start)
    heappush(frontier, (0, int(start_heuristic["heuristic_value"]), "", next(sequence), start, tuple()))
    best_depth_by_state = {start: 0}
    expansions = 0
    hit_plan_length_limit = False
    while frontier:
        depth, _heuristic_value, _last_action, _sequence_id, state, plan = heappop(frontier)
        if request.task.goal.issubset(state):
            return list(plan), "success_full_trace"
        if depth >= request.limits["max_plan_length"]:
            hit_plan_length_limit = True
            continue
        expansions += 1
        if expansions > _limit(request, "local_ff_best_first_max_expansions", request.limits["gbfs_max_expansions"]):
            return [], "skipped_resource_limit"
        applicable = _applicable_actions(request.grounded, state)
        if len(applicable) > _limit(request, "local_max_applicable_actions", DEFAULT_MAX_APPLICABLE_ACTIONS):
            return [], "skipped_resource_limit"
        for action in applicable:
            next_state = _apply(action, state)
            next_depth = depth + 1
            if best_depth_by_state.get(next_state, request.limits["max_plan_length"] + 1) <= next_depth:
                continue
            next_plan = (*plan, action.canonical)
            heuristic = _relaxed_heuristic(request.task, request.grounded, next_state)
            best_depth_by_state[next_state] = next_depth
            heappush(frontier, (next_depth, int(heuristic["heuristic_value"]), action.canonical, next(sequence), next_state, next_plan))
    return [], "skipped_resource_limit" if hit_plan_length_limit else "failed_no_plan_extracted"


def _ff_trace_events(request: LocalPlannerRequest, start: frozenset[Atom], plan: list[str]) -> list[JSONValue]:
    state = start
    events: list[JSONValue] = []
    for step_index, selected_action in enumerate(plan[: request.limits["max_trace_steps"]]):
        current_heuristic = _relaxed_heuristic(request.task, request.grounded, state)
        ranked = _ranked_ff_successors(request, state)
        selected = next(item for item in ranked if item[1] == selected_action)
        selected_value, _action, next_state, selected_heuristic = selected
        events.append(
            {
                "event_kind": "expansion",
                "step_index": step_index,
                "state_atoms": _atoms(state),
                "current_heuristic": _heuristic_payload(current_heuristic),
                "relaxation_metadata": {
                    "ignored_delete_effects": True,
                    "approximation": "local_delete_relaxed_hmax_supporter_closure",
                    "is_exact_fast_downward_ff": False,
                },
                "selected_action": selected_action,
                "selected_successor": _successor_payload(selected_action, selected_value, next_state, request.task.goal.issubset(next_state), selected_heuristic),
                "successor_heuristics": [
                    _successor_payload(action, value, successor, request.task.goal.issubset(successor), heuristic)
                    for value, action, successor, heuristic in ranked
                ],
                "tie_break_rule": "min_relaxed_plan_length_then_action_lexicographic",
            }
        )
        state = next_state
    return events


def _ranked_ff_successors(request: LocalPlannerRequest, state: frozenset[Atom]) -> list[tuple[JSONValue, str, frozenset[Atom], dict[str, JSONValue]]]:
    ranked = []
    for action in _applicable_actions(request.grounded, state):
        next_state = _apply(action, state)
        heuristic = _relaxed_heuristic(request.task, request.grounded, next_state)
        ranked.append((heuristic["heuristic_value"], action.canonical, next_state, heuristic))
    ranked.sort(key=lambda item: (int(item[0]), item[1]))
    return ranked


def _ff_trace(task: PDDLTask, events: list[JSONValue]) -> dict[str, JSONValue]:
    return {
        "trace_contract_version": "phase3_traversal_trace_v1",
        "algorithm": "fast_forward",
        "goal_atoms": _atoms(task.goal),
        "planner_source": "local_delete_relaxed_hmax_supporter_closure",
        "steps": events,
    }


def _relaxed_heuristic(task: PDDLTask, grounded: tuple[GroundAction, ...], state: frozenset[Atom]) -> dict[str, JSONValue]:
    costs: dict[Atom, int] = {atom: 0 for atom in state}
    supporters: dict[Atom, GroundAction] = {}
    proposition_layers: list[JSONValue] = [{"layer_index": 0, "propositions": _atoms(state), "goal_present": task.goal.issubset(state)}]
    action_layers: list[JSONValue] = []
    propositions = state
    layer_index = 0
    changed = True
    while changed:
        changed = False
        applicable = _applicable_actions(grounded, propositions)
        next_propositions = set(propositions)
        for action in grounded:
            if not action.preconditions.issubset(costs):
                continue
            candidate = 1 + max((costs[atom] for atom in action.preconditions), default=0)
            for atom in action.add_effects:
                next_propositions.add(atom)
                current = costs.get(atom)
                if current is None or candidate < current:
                    costs[atom] = candidate
                    supporters[atom] = action
                    changed = True
        if not changed:
            break
        layer_index += 1
        action_layers.append({"layer_index": layer_index - 1, "actions": [action.canonical for action in applicable], "next_layer_index": layer_index})
        propositions = frozenset(next_propositions)
        proposition_layers.append({"layer_index": layer_index, "propositions": _atoms(propositions), "goal_present": task.goal.issubset(propositions)})
        if task.goal.issubset(propositions):
            break
    unreachable = sorted(canonical_atom(atom) for atom in task.goal if atom not in costs)
    relaxed_plan = _relaxed_supporter_closure(task.goal, state, supporters)
    return {
        "heuristic_value": UNREACHABLE_HEURISTIC if unreachable else len(relaxed_plan),
        "heuristic_source": "delete_relaxed_planning_graph",
        "relaxed_action_layers": action_layers,
        "relaxed_plan_actions": relaxed_plan,
        "relaxed_proposition_layers": proposition_layers,
        "unreachable_goal_atoms": unreachable,
    }


def _heuristic_payload(heuristic: dict[str, JSONValue]) -> dict[str, JSONValue]:
    return {
        "heuristic_source": heuristic["heuristic_source"],
        "heuristic_value": heuristic["heuristic_value"],
        "relaxed_action_layers": heuristic["relaxed_action_layers"],
        "relaxed_plan": _relaxed_plan_payload(heuristic),
        "relaxed_proposition_layers": heuristic["relaxed_proposition_layers"],
    }


def _relaxed_plan_payload(heuristic: dict[str, JSONValue]) -> dict[str, JSONValue]:
    actions = heuristic["relaxed_plan_actions"]
    return {"actions": actions, "length": len(actions) if isinstance(actions, list) else 0, "unreachable_goal_atoms": heuristic["unreachable_goal_atoms"]}


def _successor_payload(action: str, heuristic_value: JSONValue, state: frozenset[Atom], is_goal: bool, heuristic: dict[str, JSONValue]) -> dict[str, JSONValue]:
    return {
        "action": action,
        "event_kind": "generation",
        "heuristic_value": heuristic_value,
        "is_goal": is_goal,
        "relaxed_plan": _relaxed_plan_payload(heuristic),
        "relaxed_plan_actions": heuristic["relaxed_plan_actions"],
        "state_atoms": _atoms(state),
    }


def _relaxed_supporter_closure(goals: frozenset[Atom], state: frozenset[Atom], supporters: dict[Atom, GroundAction]) -> list[str]:
    selected: set[str] = set()
    pending = list(goals - state)
    while pending:
        atom = pending.pop()
        supporter = supporters.get(atom)
        if supporter is None:
            continue
        selected.add(supporter.canonical)
        pending.extend(precondition for precondition in supporter.preconditions if precondition not in state)
    return sorted(selected)


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
