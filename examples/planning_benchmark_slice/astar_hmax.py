"""Trusted delete-relaxed h_max for the supported deterministic PDDL slice."""

from __future__ import annotations

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

    def __call__(self, state: CanonicalState) -> int:
        if state.authority_id != self._authority.authority_id:
            raise ValueError("h_max state belongs to a different PDDL authority")
        costs = {fact: 0 for fact in (*state.atoms, *self._static)}
        changed = True
        while changed:
            changed = False
            for operator in self._operators:
                if not operator.preconditions <= costs.keys():
                    continue
                candidate = 1 + max((costs[item] for item in operator.preconditions), default=0)
                for effect in operator.add_effects:
                    if candidate < costs.get(effect, HMAX_UNREACHABLE):
                        costs[effect] = candidate
                        changed = True
        if not self._goals:
            return 0
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
