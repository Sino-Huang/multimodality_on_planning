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


@dataclass(frozen=True, slots=True, init=False)
class SearchMemory:
    authority: PDDLStateAuthority
    frontier: tuple[str, ...]
    visited: frozenset[str]
    novelty: Mapping[str, int]
    heuristics: Mapping[str, HeuristicValue]
    provenance: tuple[TransitionProvenance, ...]
    _known_states: Mapping[str, CanonicalState] = field(init=False, repr=False, compare=False)

    def __init__(self) -> None:
        raise TypeError("SearchMemory construction is internal; use SearchMemory.initial")

    @classmethod
    def _create(
        cls,
        *,
        authority: PDDLStateAuthority,
        frontier: tuple[str, ...],
        visited: frozenset[str],
        novelty: Mapping[str, int],
        heuristics: Mapping[str, HeuristicValue],
        provenance: tuple[TransitionProvenance, ...],
        known_states: Mapping[str, CanonicalState],
    ) -> SearchMemory:
        immutable_frontier = tuple(frontier)
        immutable_visited = frozenset(visited)
        immutable_novelty = MappingProxyType(dict(novelty))
        immutable_heuristics = MappingProxyType(dict(heuristics))
        immutable_provenance = tuple(provenance)
        immutable_known_states = MappingProxyType(dict(known_states))

        initial = authority.initial_state
        if immutable_known_states.get(initial.state_id) != initial:
            raise ValueError("search memory must contain the authority's initial state")
        known_state_ids = frozenset(immutable_known_states)
        if known_state_ids != immutable_visited:
            raise ValueError("known state IDs must equal visited state IDs")
        if not set(immutable_frontier).issubset(immutable_visited):
            raise ValueError("frontier state IDs must be visited")
        if not immutable_novelty.keys() <= immutable_visited:
            raise ValueError("novelty state IDs must be visited")
        if not immutable_heuristics.keys() <= immutable_visited:
            raise ValueError("heuristic state IDs must be visited")
        for state_id, state in immutable_known_states.items():
            if state_id != state.state_id:
                raise ValueError(f"known state key does not match state ID: {state_id}")
            authority.is_goal(state)

        memory: SearchMemory = object.__new__(cls)
        object.__setattr__(memory, "authority", authority)
        object.__setattr__(memory, "frontier", immutable_frontier)
        object.__setattr__(memory, "visited", immutable_visited)
        object.__setattr__(memory, "novelty", immutable_novelty)
        object.__setattr__(memory, "heuristics", immutable_heuristics)
        object.__setattr__(memory, "provenance", immutable_provenance)
        object.__setattr__(memory, "_known_states", immutable_known_states)
        return memory

    @classmethod
    def initial(cls, authority: PDDLStateAuthority) -> SearchMemory:
        initial = authority.initial_state
        return cls._create(
            authority=authority,
            frontier=(initial.state_id,),
            visited=frozenset((initial.state_id,)),
            novelty={},
            heuristics={},
            provenance=(),
            known_states={initial.state_id: initial},
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
        frontier: tuple[str, ...],
        evaluation: StateEvaluation | None,
    ) -> SearchMemory:
        target_id = transition.target_state.state_id
        novelty = dict(self.novelty)
        heuristics = dict(self.heuristics)
        if evaluation is not None:
            novelty[target_id] = evaluation.novelty
            heuristics[target_id] = evaluation.heuristic

        known_states = dict(self._known_states)
        known_states[target_id] = transition.target_state
        return self._create(
            authority=self.authority,
            frontier=frontier,
            visited=self.visited | {target_id},
            novelty=novelty,
            heuristics=heuristics,
            provenance=(*self.provenance, transition.provenance),
            known_states=known_states,
        )


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
    if not request.visit_target:
        return RejectedTransition(memory, 1, "target must be visited")

    source = memory._known_states.get(request.source_state_id)
    if source is None:
        return RejectedTransition(memory, 1, f"unknown source state: {request.source_state_id}")

    try:
        preview = memory.authority.preview_apply(source, request.action)
    except (InvalidActionError, ValueError) as error:
        return RejectedTransition(memory, 1, str(error))

    target_id = preview.target_state.state_id
    frontier = list(memory.frontier)
    if request.frontier_intent.retire_source:
        frontier = [item for item in frontier if item != request.source_state_id]
    frontier = [item for item in frontier if item != target_id]
    position = request.frontier_intent.target_position
    if position > len(frontier):
        return RejectedTransition(memory, 1, f"invalid target position: {position}")
    frontier.insert(position, target_id)

    try:
        transition = memory.authority.apply(source, request.action)
    except (InvalidActionError, ValueError) as error:
        return RejectedTransition(memory, 1, str(error))

    evaluation = evaluator(transition.target_state) if request.evaluate_target else None
    updated = memory._with_transition(transition, tuple(frontier), evaluation)
    return AcceptedTransition(updated)
