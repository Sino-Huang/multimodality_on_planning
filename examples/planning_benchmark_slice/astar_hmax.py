"""Trusted delete-relaxed h_max for the supported deterministic PDDL slice."""

from __future__ import annotations

import heapq

from .pddl_state import CanonicalState, PDDLStateAuthority
from .strips_relaxation import UnsupportedSTRIPSTaskError, extract_grounded_positive_strips

HMAX_UNREACHABLE = 1_000_000_000


class UnsupportedHMaxTaskError(ValueError):
    """Raised when h_max is asked to approximate outside its trusted subset."""


class HMaxHeuristic:
    """Exact h_max recurrence over grounded positive STRIPS operators."""

    name = "h_max"
    algorithm = "astar_hmax"

    def __init__(self, authority: PDDLStateAuthority) -> None:
        self._authority = authority
        try:
            task = extract_grounded_positive_strips(authority)
        except UnsupportedSTRIPSTaskError as error:
            raise UnsupportedHMaxTaskError(f"h_max {error}") from error
        self._goals = task.goals
        self._static = task.static_facts
        self._operators = task.operators
        operators_by_precondition: dict[str, list[int]] = {}
        for index, operator in enumerate(self._operators):
            for fact in operator.preconditions:
                operators_by_precondition.setdefault(fact, []).append(index)
        self._operators_by_precondition = {
            fact: tuple(indices) for fact, indices in operators_by_precondition.items()
        }
        self._zero_precondition_operators = tuple(
            index for index, operator in enumerate(self._operators) if not operator.preconditions
        )

    def __call__(self, state: CanonicalState) -> int:
        if state.authority_id != self._authority.authority_id:
            raise ValueError("h_max state belongs to a different PDDL authority")
        if not self._goals:
            return 0
        costs = {fact: 0 for fact in (*state.atoms, *self._static)}
        if self._goals <= costs.keys():
            return 0
        frontier = [(0, fact) for fact in costs]
        heapq.heapify(frontier)
        remaining = [len(operator.preconditions) for operator in self._operators]
        maximum_precondition_cost = [0] * len(self._operators)
        for index in self._zero_precondition_operators:
            for effect in self._operators[index].add_effects:
                if 1 < costs.get(effect, HMAX_UNREACHABLE):
                    costs[effect] = 1
                    heapq.heappush(frontier, (1, effect))

        pending_goals = set(self._goals)
        while frontier:
            cost, fact = heapq.heappop(frontier)
            if costs[fact] != cost:
                continue
            pending_goals.discard(fact)
            if not pending_goals:
                return max(costs[goal] for goal in self._goals)
            for index in self._operators_by_precondition.get(fact, ()):
                remaining[index] -= 1
                maximum_precondition_cost[index] = max(maximum_precondition_cost[index], cost)
                if remaining[index] != 0:
                    continue
                candidate = maximum_precondition_cost[index] + 1
                for effect in self._operators[index].add_effects:
                    if candidate < costs.get(effect, HMAX_UNREACHABLE):
                        costs[effect] = candidate
                        heapq.heappush(frontier, (candidate, effect))
        return max(costs.get(goal, HMAX_UNREACHABLE) for goal in self._goals)

    def initial(self, state: CanonicalState) -> None:
        del state
        return None

    def advance(
        self,
        progress: object,
        source_state: CanonicalState,
        target_state: CanonicalState,
    ) -> None:
        del progress, source_state, target_state
        return None

    def value(self, state: CanonicalState, progress: object) -> int:
        del progress
        return self(state)

    def progress_key(self, progress: object) -> str:
        del progress
        return "singleton"

    def progress_payload(self, state: CanonicalState, progress: object) -> dict[str, object]:
        del state, progress
        return {}

    def transition_payload(
        self,
        before: object,
        after: object,
        source_state: CanonicalState,
        target_state: CanonicalState,
    ) -> dict[str, object]:
        del before, after, source_state, target_state
        return {}

    def task_payload(self) -> dict[str, object]:
        return {}


__all__ = ["HMAX_UNREACHABLE", "HMaxHeuristic", "UnsupportedHMaxTaskError"]
