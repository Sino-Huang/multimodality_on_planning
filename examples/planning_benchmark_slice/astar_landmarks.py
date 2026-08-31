"""Deterministic positive fact landmarks and path-dependent count progression."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .pddl_state import CanonicalState, PDDLStateAuthority
from .strips_relaxation import GroundedPositiveSTRIPSTask, extract_grounded_positive_strips


@dataclass(frozen=True, slots=True)
class LandmarkCatalog:
    landmarks: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, list[object]]:
        return {
            "edges": [list(edge) for edge in self.edges],
            "landmarks": list(self.landmarks),
        }


@dataclass(frozen=True, slots=True)
class LandmarkProgress:
    accepted: frozenset[str]


class LandmarkCountHeuristic:
    """Path-dependent landmark-count adapter for the shared A* controller."""

    name = "landmark_count"
    algorithm = "astar_landmark_count"

    def __init__(self, authority: PDDLStateAuthority) -> None:
        self.authority = authority
        self.task = extract_grounded_positive_strips(authority)
        self.catalog = extract_positive_fact_landmarks(self.task)
        predecessors: dict[str, set[str]] = {landmark: set() for landmark in self.catalog.landmarks}
        for predecessor, landmark in self.catalog.edges:
            predecessors[landmark].add(predecessor)
        self._predecessors = {key: frozenset(value) for key, value in predecessors.items()}

    def initial(self, state: CanonicalState) -> LandmarkProgress:
        return self._accept_eligible(LandmarkProgress(frozenset()), state)

    def advance(
        self,
        progress: object,
        source_state: CanonicalState,
        target_state: CanonicalState,
    ) -> LandmarkProgress:
        del source_state
        return self._accept_eligible(self._require_progress(progress), target_state)

    def value(self, state: CanonicalState, progress: object) -> int:
        current = self._require_progress(progress)
        unaccepted = set(self.catalog.landmarks) - current.accepted
        return len(unaccepted) + len(self._needed_again(state, current, unaccepted))

    def progress_key(self, progress: object) -> str:
        current = self._require_progress(progress)
        return json.dumps(sorted(current.accepted), ensure_ascii=True, separators=(",", ":"))

    def progress_payload(self, state: CanonicalState, progress: object) -> dict[str, list[str]]:
        current = self._require_progress(progress)
        unaccepted = set(self.catalog.landmarks) - current.accepted
        return {
            "accepted": sorted(current.accepted),
            "needed_again": sorted(self._needed_again(state, current, unaccepted)),
            "unaccepted": sorted(unaccepted),
        }

    def transition_payload(
        self,
        before: object,
        after: object,
        source_state: CanonicalState,
        target_state: CanonicalState,
    ) -> dict[str, list[str]]:
        previous = self._require_progress(before)
        current = self._require_progress(after)
        source_facts = set(source_state.atoms) | set(self.task.static_facts)
        target_facts = set(target_state.atoms) | set(self.task.static_facts)
        return {
            "newly_accepted": sorted(current.accepted - previous.accepted),
            "re_achieved": sorted(previous.accepted & (target_facts - source_facts)),
        }

    def task_payload(self) -> dict[str, list[object]]:
        return self.catalog.to_dict()

    def _accept_eligible(self, progress: LandmarkProgress, state: CanonicalState) -> LandmarkProgress:
        accepted = set(progress.accepted)
        true_facts = set(state.atoms) | set(self.task.static_facts)
        changed = True
        while changed:
            changed = False
            for landmark in self.catalog.landmarks:
                if (
                    landmark not in accepted
                    and landmark in true_facts
                    and self._predecessors[landmark] <= accepted
                ):
                    accepted.add(landmark)
                    changed = True
        return LandmarkProgress(frozenset(accepted))

    def _needed_again(
        self,
        state: CanonicalState,
        progress: LandmarkProgress,
        unaccepted: set[str],
    ) -> set[str]:
        true_facts = set(state.atoms) | set(self.task.static_facts)
        needed_predecessors = {
            predecessor
            for predecessor, landmark in self.catalog.edges
            if landmark in unaccepted
        }
        required = set(self.task.goals) | needed_predecessors
        return {fact for fact in progress.accepted if fact not in true_facts and fact in required}

    @staticmethod
    def _require_progress(progress: object) -> LandmarkProgress:
        if not isinstance(progress, LandmarkProgress):
            raise TypeError("landmark heuristic progress is invalid")
        return progress


def extract_positive_fact_landmarks(task: GroundedPositiveSTRIPSTask) -> LandmarkCatalog:
    landmarks = set(task.goals)
    edges: set[tuple[str, str]] = set()
    processed: set[str] = set()
    while pending := sorted(landmarks - processed):
        landmark = pending[0]
        processed.add(landmark)
        if landmark in task.initial_facts:
            continue
        reachable = _relaxed_reachable_without(task, landmark)
        achievers = tuple(
            operator
            for operator in task.operators
            if landmark in operator.add_effects and operator.preconditions <= reachable
        )
        if not achievers:
            continue
        common = set(achievers[0].preconditions)
        for achiever in achievers[1:]:
            common.intersection_update(achiever.preconditions)
        for predecessor in sorted(common - set(task.static_facts) - {landmark}):
            landmarks.add(predecessor)
            edges.add((predecessor, landmark))
    return LandmarkCatalog(tuple(sorted(landmarks)), tuple(sorted(edges)))


def _relaxed_reachable_without(task: GroundedPositiveSTRIPSTask, suppressed_fact: str) -> frozenset[str]:
    reachable = set(task.initial_facts)
    changed = True
    while changed:
        changed = False
        for operator in task.operators:
            if not operator.preconditions <= reachable:
                continue
            before = len(reachable)
            reachable.update(operator.add_effects - {suppressed_fact})
            changed = changed or len(reachable) != before
    return frozenset(reachable)


__all__ = [
    "LandmarkCatalog",
    "LandmarkCountHeuristic",
    "LandmarkProgress",
    "extract_positive_fact_landmarks",
]
