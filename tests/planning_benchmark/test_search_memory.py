from __future__ import annotations

from examples.planning_benchmark_slice.pddl_state import (
    CanonicalState,
    GroundedAction,
    PDDLStateAuthority,
)
from examples.planning_benchmark_slice.search_memory import (
    AcceptedTransition,
    FrontierIntent,
    HeuristicValue,
    RejectedTransition,
    SearchMemory,
    SearchTransitionRequest,
    StateEvaluation,
    apply_search_transition,
)

DOMAIN = """
(define (domain branching-memory)
  (:requirements :strips :typing)
  (:types item)
  (:predicates (ready ?x - item) (done ?x - item))
  (:action advance
    :parameters (?x - item)
    :precondition (ready ?x)
    :effect (and (not (ready ?x)) (done ?x))))
"""

PROBLEM = """
(define (problem branching-memory-problem)
  (:domain branching-memory)
  (:objects a b - item)
  (:init (ready a) (ready b))
  (:goal (and (done a) (done b))))
"""


def _authority() -> PDDLStateAuthority:
    return PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)


def _request(source_state_id: str, action: GroundedAction) -> SearchTransitionRequest:
    return SearchTransitionRequest(
        source_state_id=source_state_id,
        action=action,
        frontier_intent=FrontierIntent(retire_source=True, target_position=0),
        visit_target=True,
        evaluate_target=True,
    )


def test_valid_transition_updates_only_memory_for_the_reproduced_target() -> None:
    authority = _authority()
    source = authority.initial_state
    action = GroundedAction("advance", ("a",))
    expected = _authority().apply(source, action)
    unchosen_successor = _authority().apply(source, GroundedAction("advance", ("b",))).target_state
    evaluation = StateEvaluation(
        novelty=2,
        heuristic=HeuristicValue(name="trusted-test", value=7),
    )
    evaluated_state_ids: list[str] = []

    def evaluator(state: CanonicalState) -> StateEvaluation:
        state_id = state.state_id
        evaluated_state_ids.append(state_id)
        return evaluation

    result = apply_search_transition(
        SearchMemory.initial(authority),
        _request(source.state_id, action),
        evaluator=evaluator,
    )

    assert isinstance(result, AcceptedTransition)
    assert result.memory.frontier == (expected.target_state.state_id,)
    assert result.memory.visited == frozenset((source.state_id, expected.target_state.state_id))
    assert result.memory.novelty == {expected.target_state.state_id: evaluation.novelty}
    assert result.memory.heuristics == {expected.target_state.state_id: evaluation.heuristic}
    assert result.memory.provenance == (expected.provenance,)
    assert evaluated_state_ids == [expected.target_state.state_id]
    assert unchosen_successor.state_id not in result.memory.frontier
    assert unchosen_successor.state_id not in result.memory.visited
    assert unchosen_successor.state_id not in result.memory.novelty
    assert unchosen_successor.state_id not in result.memory.heuristics


def test_invalid_transition_charges_once_without_changing_the_original_memory() -> None:
    authority = _authority()
    memory = SearchMemory.initial(authority)
    original_bytes = memory.to_bytes()

    def evaluator(_state: object) -> StateEvaluation:
        raise AssertionError("an invalid transition must not be evaluated")

    result = apply_search_transition(
        memory,
        _request(authority.initial_state.state_id, GroundedAction("advance", ("missing",))),
        evaluator=evaluator,
    )

    assert isinstance(result, RejectedTransition)
    assert result.budget_charge == 1
    assert result.memory is memory
    assert memory.to_bytes() == original_bytes
