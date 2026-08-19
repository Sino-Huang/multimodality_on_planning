from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Mapping, TypeAlias

from .pddl_state import (
    CanonicalState,
    GroundedAction,
    InvalidActionError,
    PDDLStateAuthority,
    PDDLTransition,
    TransitionProvenance,
)


@dataclass(frozen=True, slots=True)
class FrontierIntent:
    retire_source: bool
    target_position: int

    def __post_init__(self) -> None:
        if self.target_position < 0:
            raise ValueError("target_position must be non-negative")


@dataclass(frozen=True, slots=True)
class HeuristicValue:
    name: str
    value: int

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("heuristic name must not be empty")


@dataclass(frozen=True, slots=True)
class StateEvaluation:
    novelty: int
    heuristic: HeuristicValue

    def __post_init__(self) -> None:
        if self.novelty < 0:
            raise ValueError("novelty must be non-negative")


@dataclass(frozen=True, slots=True)
class SearchTransitionRequest:
    source_state_id: str
    action: GroundedAction
    frontier_intent: FrontierIntent
    visit_target: bool
    evaluate_target: bool


@dataclass(frozen=True, slots=True)
class SearchMemory:
    authority: PDDLStateAuthority
    frontier: tuple[str, ...]
    visited: frozenset[str]
    novelty: Mapping[str, int]
    heuristics: Mapping[str, HeuristicValue]
    provenance: tuple[TransitionProvenance, ...]
    _known_states: Mapping[str, CanonicalState] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "frontier", tuple(self.frontier))
        object.__setattr__(self, "visited", frozenset(self.visited))
        object.__setattr__(self, "novelty", MappingProxyType(dict(self.novelty)))
        object.__setattr__(self, "heuristics", MappingProxyType(dict(self.heuristics)))
        object.__setattr__(self, "provenance", tuple(self.provenance))
        initial = self.authority.initial_state
        object.__setattr__(self, "_known_states", MappingProxyType({initial.state_id: initial}))

    @classmethod
    def initial(cls, authority: PDDLStateAuthority) -> SearchMemory:
        state_id = authority.initial_state.state_id
        return cls(
            authority=authority,
            frontier=(state_id,),
            visited=frozenset((state_id,)),
            novelty={},
            heuristics={},
            provenance=(),
        )

    def to_bytes(self) -> bytes:
        payload = {
            "authority_id": self.authority.authority_id,
            "frontier": self.frontier,
            "heuristics": {
                state_id: {"name": value.name, "value": value.value} for state_id, value in self.heuristics.items()
            },
            "novelty": dict(self.novelty),
            "provenance": [item.to_dict() for item in self.provenance],
            "visited": sorted(self.visited),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _with_transition(
        self,
        transition: PDDLTransition,
        request: SearchTransitionRequest,
        evaluation: StateEvaluation | None,
    ) -> SearchMemory:
        target_id = transition.target_state.state_id
        frontier = list(self.frontier)
        if request.frontier_intent.retire_source:
            frontier = [item for item in frontier if item != request.source_state_id]
        if target_id in frontier:
            frontier.remove(target_id)
        frontier.insert(request.frontier_intent.target_position, target_id)

        visited = self.visited | {target_id} if request.visit_target else self.visited
        novelty = dict(self.novelty)
        heuristics = dict(self.heuristics)
        if evaluation is not None:
            novelty[target_id] = evaluation.novelty
            heuristics[target_id] = evaluation.heuristic

        updated = SearchMemory(
            authority=self.authority,
            frontier=tuple(frontier),
            visited=visited,
            novelty=novelty,
            heuristics=heuristics,
            provenance=(*self.provenance, transition.provenance),
        )
        known_states = dict(self._known_states)
        known_states[target_id] = transition.target_state
        object.__setattr__(updated, "_known_states", MappingProxyType(known_states))
        return updated


@dataclass(frozen=True, slots=True)
class AcceptedTransition:
    memory: SearchMemory


@dataclass(frozen=True, slots=True)
class RejectedTransition:
    memory: SearchMemory
    budget_charge: int
    reason: str


SearchTransitionResult: TypeAlias = AcceptedTransition | RejectedTransition
StateEvaluator: TypeAlias = Callable[[CanonicalState], StateEvaluation]


def apply_search_transition(
    memory: SearchMemory,
    request: SearchTransitionRequest,
    *,
    evaluator: StateEvaluator,
) -> SearchTransitionResult:
    source = memory._known_states.get(request.source_state_id)
    if source is None:
        return RejectedTransition(memory, 1, f"unknown source state: {request.source_state_id}")

    try:
        transition = memory.authority.apply(source, request.action)
    except InvalidActionError as error:
        return RejectedTransition(memory, 1, str(error))

    evaluation = evaluator(transition.target_state) if request.evaluate_target else None
    updated = memory._with_transition(transition, request, evaluation)
    return AcceptedTransition(updated)
