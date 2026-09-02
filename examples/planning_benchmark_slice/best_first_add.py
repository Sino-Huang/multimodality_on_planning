"""Trusted delete-relaxed additive heuristic for positive grounded STRIPS."""

from __future__ import annotations

import heapq

from .pddl_state import CanonicalState, PDDLStateAuthority
from .strips_relaxation import UnsupportedSTRIPSTaskError, extract_grounded_positive_strips

HADD_UNREACHABLE = 1_000_000_000


class UnsupportedAdditiveTaskError(ValueError):
    """Raised when the additive heuristic is used outside its trusted subset."""


class AdditiveHeuristic:
    """Compute h_add by summing relaxed precondition and goal costs."""

    name = "h_add"

    def __init__(self, authority: PDDLStateAuthority) -> None:
        self._authority = authority
        try:
            task = extract_grounded_positive_strips(
                authority,
                prune_type_impossible_groundings=True,
            )
        except UnsupportedSTRIPSTaskError as error:
            raise UnsupportedAdditiveTaskError(f"h_add {error}") from error
        self._goals = task.goals
        self._static = task.static_facts
        self._operators = task.operators
        operators_by_precondition: dict[str, list[int]] = {}
        for index, operator in enumerate(self._operators):
            for fact in operator.preconditions:
                operators_by_precondition.setdefault(fact, []).append(index)
        self._operators_by_precondition = {fact: tuple(indices) for fact, indices in operators_by_precondition.items()}
        self._zero_precondition_operators = tuple(
            index for index, operator in enumerate(self._operators) if not operator.preconditions
        )

    def __call__(self, state: CanonicalState) -> int:
        if state.authority_id != self._authority.authority_id:
            raise ValueError("h_add state belongs to a different PDDL authority")
        if not self._goals:
            return 0
        costs = {fact: 0 for fact in (*state.atoms, *self._static)}
        if self._goals <= costs.keys():
            return 0
        frontier = [(0, fact) for fact in costs]
        heapq.heapify(frontier)
        remaining = [len(operator.preconditions) for operator in self._operators]
        precondition_sum = [0] * len(self._operators)
        for index in self._zero_precondition_operators:
            self._relax_effects(index, 1, costs, frontier)

        while frontier:
            cost, fact = heapq.heappop(frontier)
            if costs[fact] != cost:
                continue
            for index in self._operators_by_precondition.get(fact, ()):
                remaining[index] -= 1
                precondition_sum[index] += cost
                if remaining[index] == 0:
                    self._relax_effects(index, precondition_sum[index] + 1, costs, frontier)
        return sum(costs.get(goal, HADD_UNREACHABLE) for goal in self._goals)

    def _relax_effects(
        self,
        operator_index: int,
        candidate: int,
        costs: dict[str, int],
        frontier: list[tuple[int, str]],
    ) -> None:
        for effect in self._operators[operator_index].add_effects:
            if candidate < costs.get(effect, HADD_UNREACHABLE):
                costs[effect] = candidate
                heapq.heappush(frontier, (candidate, effect))


__all__ = ["HADD_UNREACHABLE", "AdditiveHeuristic", "UnsupportedAdditiveTaskError"]
