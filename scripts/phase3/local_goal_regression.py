from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Final

from .local_planner_types import JSONValue
from .pddl import Atom, GroundAction, PDDLTask, canonical_atom

EARLY_RECOVERY_DOMAINS: Final = frozenset({"gripper-strips", "grid-visit-all", "logistics-strips"})


@dataclass(frozen=True, slots=True)
class GoalRegressionRequest:
    task: PDDLTask
    grounded: tuple[GroundAction, ...]
    limits: dict[str, int]
    source: str
    original_status: str


@dataclass(frozen=True, slots=True)
class GoalRegressionResult:
    plan: list[str]
    trace: dict[str, JSONValue]
    status: str


def recover_goal_regression_plan(request: GoalRegressionRequest) -> GoalRegressionResult:
    achiever = _GoalAchiever(request)
    return achiever.solve()


def should_try_goal_regression_first(task: PDDLTask, limits: dict[str, int]) -> bool:
    if task.domain_name == "logistics-strips":
        return True
    return task.domain_name in EARLY_RECOVERY_DOMAINS and len(task.goal) > limits.get("local_goal_regression_goal_threshold", 8)


class _GoalAchiever:
    def __init__(self, request: GoalRegressionRequest) -> None:
        self._request = request
        self._state = set(request.task.init)
        self._plan: list[str] = []
        self._events: list[JSONValue] = []
        self._attempts = 0
        self._supporters = _supporters_by_added_atom(request.grounded)

    def solve(self) -> GoalRegressionResult:
        if _is_visitall_task(self._request.task):
            if self._solve_visitall():
                return GoalRegressionResult(list(self._plan), self._trace(failed_goal=None), "success_full_trace")
            return GoalRegressionResult([], self._trace(failed_goal=None), "skipped_resource_limit")
        for goal in sorted(self._request.task.goal, key=canonical_atom):
            if not self._achieve(goal, frozenset()):
                return GoalRegressionResult([], self._trace(failed_goal=goal), "skipped_resource_limit")
        return GoalRegressionResult(list(self._plan), self._trace(failed_goal=None), "success_full_trace")

    def _solve_visitall(self) -> bool:
        current = _robot_location(self._state)
        if current is None:
            return False
        edges = _visitall_edges(self._request.grounded, self._request.task.init)
        remaining = {goal[1] for goal in self._request.task.goal if goal not in self._state}
        while remaining:
            path = _shortest_visit_path(current, remaining, edges)
            if path is None:
                return False
            for action in path:
                if not self._within_limits() or not action.preconditions.issubset(self._state):
                    return False
                target = next(atom for atom in action.add_effects if len(atom) == 2 and atom[0] == "visited")
                self._attempts += 1
                self._apply(action, target)
                current = target[1]
                remaining.discard(current)
        return self._request.task.goal.issubset(self._state)

    def _achieve(self, atom: Atom, stack: frozenset[Atom]) -> bool:
        if atom in self._state:
            return True
        if atom in stack:
            return False
        for action in self._supporters.get(atom, ()):
            if not self._within_limits():
                return False
            snapshot = (set(self._state), list(self._plan), list(self._events), self._attempts)
            self._attempts += 1
            if self._satisfy(action.preconditions, stack | {atom}) and action.preconditions.issubset(self._state):
                self._apply(action, atom)
                if atom in self._state:
                    return True
            self._restore(snapshot)
        return False

    def _satisfy(self, preconditions: frozenset[Atom], stack: frozenset[Atom]) -> bool:
        repairs = 0
        while not preconditions.issubset(self._state):
            missing = sorted((atom for atom in preconditions if atom not in self._state), key=canonical_atom)
            before = len(self._plan)
            if not missing or not self._achieve(missing[0], stack):
                return False
            if len(self._plan) == before:
                repairs += 1
                if repairs > len(preconditions):
                    return False
            else:
                repairs = 0
        return True

    def _apply(self, action: GroundAction, target: Atom) -> None:
        before = set(self._state)
        self._state.difference_update(action.del_effects)
        self._state.update(action.add_effects)
        self._plan.append(action.canonical)
        if len(self._events) < self._request.limits["max_trace_steps"]:
            self._events.append(
                {
                    "action": action.canonical,
                    "state_before": _atoms(before),
                    "state_after": _atoms(self._state),
                    "target_atom": canonical_atom(target),
                }
            )

    def _within_limits(self) -> bool:
        return self._attempts < self._request.limits.get("local_goal_regression_max_attempts", 10000) and len(self._plan) < self._request.limits["max_plan_length"]

    def _trace(self, *, failed_goal: Atom | None) -> dict[str, JSONValue]:
        trace: dict[str, JSONValue] = {
            "source": self._request.source,
            "is_exact_search_algorithm": False,
            "original_status": self._request.original_status,
            "attempt_count": self._attempts,
            "steps": self._events,
        }
        if failed_goal is not None:
            trace["failed_goal"] = canonical_atom(failed_goal)
        return trace

    def _restore(self, snapshot: tuple[set[Atom], list[str], list[JSONValue], int]) -> None:
        state, plan, events, attempts = snapshot
        self._state = state
        self._plan = plan
        self._events = events
        self._attempts = attempts


def _supporters_by_added_atom(grounded: tuple[GroundAction, ...]) -> dict[Atom, tuple[GroundAction, ...]]:
    supporters: dict[Atom, list[GroundAction]] = {}
    for action in grounded:
        for atom in action.add_effects:
            supporters.setdefault(atom, []).append(action)
    return {atom: tuple(sorted(actions, key=lambda action: (len(action.preconditions), action.canonical))) for atom, actions in supporters.items()}


def _atoms(atoms: set[Atom]) -> list[str]:
    return sorted(canonical_atom(atom) for atom in atoms)


def _robot_location(state: set[Atom]) -> str | None:
    locations = sorted(atom[1] for atom in state if len(atom) == 2 and atom[0] == "at-robot")
    return locations[0] if locations else None


def _is_visitall_task(task: PDDLTask) -> bool:
    return bool(task.goal) and all(len(goal) == 2 and goal[0] == "visited" for goal in task.goal)


def _visitall_edges(grounded: tuple[GroundAction, ...], static_atoms: frozenset[Atom]) -> dict[str, tuple[GroundAction, ...]]:
    edges: dict[str, list[GroundAction]] = {}
    for action in grounded:
        starts = [atom[1] for atom in action.preconditions if len(atom) == 2 and atom[0] == "at-robot"]
        visited = [atom[1] for atom in action.add_effects if len(atom) == 2 and atom[0] == "visited"]
        static_preconditions = {atom for atom in action.preconditions if not (len(atom) == 2 and atom[0] == "at-robot")}
        if len(starts) == 1 and len(visited) == 1 and static_preconditions.issubset(static_atoms):
            edges.setdefault(starts[0], []).append(action)
    return {location: tuple(sorted(actions, key=lambda action: action.canonical)) for location, actions in edges.items()}


def _shortest_visit_path(start: str, targets: set[str], edges: dict[str, tuple[GroundAction, ...]]) -> tuple[GroundAction, ...] | None:
    frontier: deque[tuple[str, tuple[GroundAction, ...]]] = deque([(start, tuple())])
    visited = {start}
    while frontier:
        location, path = frontier.popleft()
        if location in targets and path:
            return path
        for action in edges.get(location, ()):
            destinations = [atom[1] for atom in action.add_effects if len(atom) == 2 and atom[0] == "visited"]
            if not destinations or destinations[0] in visited:
                continue
            visited.add(destinations[0])
            frontier.append((destinations[0], (*path, action)))
    return None
