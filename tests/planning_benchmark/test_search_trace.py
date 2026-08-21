from __future__ import annotations

import json

import pytest

from examples.planning_benchmark_slice.pddl_state import GroundedAction, PDDLStateAuthority
from examples.planning_benchmark_slice.search_memory import (
    AcceptedRetirement,
    AcceptedTransition,
    FrontierIntent,
    HeuristicValue,
    SearchMemory,
    SearchRetireRequest,
    SearchTransitionRequest,
    StateEvaluation,
    apply_search_retirement,
    apply_search_transition,
)
from examples.planning_benchmark_slice.search_trace import (
    SearchTraceError,
    SearchTraceValidationError,
    TraceSegmentLimits,
    append_search_trace_record,
    append_trusted_search_trace_record,
    replay_search_trace_segment,
    start_search_trace,
    verify_search_trace_segment,
)

DOMAIN = """
(define (domain trace-memory)
  (:requirements :strips :typing)
  (:types item)
  (:predicates (ready ?x - item) (done ?x - item))
  (:action advance
    :parameters (?x - item)
    :precondition (ready ?x)
    :effect (and (not (ready ?x)) (done ?x))))
"""

PROBLEM = """
(define (problem trace-memory-problem)
  (:domain trace-memory)
  (:objects a b - item)
  (:init (ready a) (ready b))
  (:goal (and (done a) (done b))))
"""


def test_accepted_transition_round_trips_as_one_atomic_trace_record() -> None:
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    memory = SearchMemory.initial(authority)
    request = SearchTransitionRequest(
        source_state_id=authority.initial_state.state_id,
        action=GroundedAction("advance", ("a",)),
        frontier_intent=FrontierIntent(retire_source=True, target_position=0),
        visit_target=True,
        evaluate_target=False,
    )

    def unexpected_evaluator(_state: object) -> StateEvaluation:
        raise AssertionError("the transition did not request evaluation")

    result = apply_search_transition(memory, request, evaluator=unexpected_evaluator)
    assert isinstance(result, AcceptedTransition)

    limits = TraceSegmentLimits(max_records=1, max_bytes=10_000)
    trace = start_search_trace(memory, limits=limits)
    trace = append_search_trace_record(
        trace,
        memory_before=memory,
        observation={"state_id": authority.initial_state.state_id},
        rationale="Advance ready item a toward the goal.",
        operation=request,
        result=result,
        limits=limits,
    )
    trace_bytes = trace.to_bytes()
    payload = json.loads(trace_bytes)

    assert len(payload["records"]) == 1
    record = payload["records"][0]
    assert all(record[field] for field in ("observation", "rationale", "operation", "result"))
    assert set(record) == {"index", "observation", "rationale", "operation", "result"}
    assert set(payload) == {"schema_version", "authority_id", "record_count", "records"}
    assert verify_search_trace_segment(trace_bytes, limits=limits) is True

    replayed = replay_search_trace_segment(trace_bytes, authority=authority, limits=limits)
    assert replayed.to_bytes() == result.memory.to_bytes()


def test_trusted_runtime_append_is_byte_identical_after_final_validation() -> None:
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    memory = SearchMemory.initial(authority)
    request = SearchTransitionRequest(
        source_state_id=authority.initial_state.state_id,
        action=GroundedAction("advance", ("a",)),
        frontier_intent=FrontierIntent(retire_source=True, target_position=0),
        visit_target=True,
        evaluate_target=False,
    )

    def unexpected_evaluator(_state: object) -> StateEvaluation:
        raise AssertionError("the transition did not request evaluation")

    result = apply_search_transition(memory, request, evaluator=unexpected_evaluator)
    assert isinstance(result, AcceptedTransition)
    limits = TraceSegmentLimits(max_records=1, max_bytes=10_000)
    arguments = {
        "memory_before": memory,
        "observation": {"state_id": authority.initial_state.state_id},
        "rationale": "Advance ready item a toward the goal.",
        "operation": request,
        "result": result,
        "limits": limits,
    }

    public = append_search_trace_record(start_search_trace(memory, limits=limits), **arguments)
    trusted = append_trusted_search_trace_record(start_search_trace(memory, limits=limits), **arguments)

    assert trusted.to_bytes() == public.to_bytes()
    assert verify_search_trace_segment(trusted.to_bytes(), limits=limits) is True


def test_frontier_retirement_round_trips_through_public_trace_seam() -> None:
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    memory = SearchMemory.initial(authority)
    request = SearchRetireRequest(memory.frontier[0])
    result = apply_search_retirement(memory, request)
    assert isinstance(result, AcceptedRetirement)

    limits = TraceSegmentLimits(max_records=1, max_bytes=10_000)
    trace = append_search_trace_record(
        start_search_trace(memory, limits=limits),
        memory_before=memory,
        observation={"state_id": authority.initial_state.state_id},
        rationale="Retire the exhausted frontier head.",
        operation=request,
        result=result,
        limits=limits,
    )
    trace_bytes = trace.to_bytes()

    assert verify_search_trace_segment(trace_bytes, limits=limits) is True
    replayed = replay_search_trace_segment(trace_bytes, authority=authority, limits=limits)
    assert replayed.to_bytes() == result.memory.to_bytes()


def test_trace_segment_public_bounds_and_tamper_validation() -> None:
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    memory = SearchMemory.initial(authority)
    first_request = SearchTransitionRequest(
        source_state_id=authority.initial_state.state_id,
        action=GroundedAction("advance", ("a",)),
        frontier_intent=FrontierIntent(retire_source=True, target_position=0),
        visit_target=True,
        evaluate_target=False,
    )

    def unexpected_evaluator(_state: object) -> StateEvaluation:
        raise AssertionError("the transition did not request evaluation")

    first_result = apply_search_transition(memory, first_request, evaluator=unexpected_evaluator)
    assert isinstance(first_result, AcceptedTransition)

    generous_limits = TraceSegmentLimits(max_records=1, max_bytes=10_000)
    first_segment = append_search_trace_record(
        start_search_trace(memory, limits=generous_limits),
        memory_before=memory,
        observation={"state_id": authority.initial_state.state_id},
        rationale="Advance ready item a toward the goal.",
        operation=first_request,
        result=first_result,
        limits=generous_limits,
    )
    first_bytes = first_segment.to_bytes()
    exact_limits = TraceSegmentLimits(max_records=1, max_bytes=len(first_bytes))

    assert verify_search_trace_segment(first_bytes, limits=exact_limits) is True
    with pytest.raises(SearchTraceValidationError):
        verify_search_trace_segment(
            first_bytes,
            limits=TraceSegmentLimits(max_records=1, max_bytes=len(first_bytes) - 1),
        )

    second_request = SearchTransitionRequest(
        source_state_id=first_result.memory.frontier[0],
        action=GroundedAction("advance", ("b",)),
        frontier_intent=FrontierIntent(retire_source=True, target_position=0),
        visit_target=True,
        evaluate_target=False,
    )
    second_result = apply_search_transition(
        first_result.memory,
        second_request,
        evaluator=unexpected_evaluator,
    )
    assert isinstance(second_result, AcceptedTransition)

    with pytest.raises(SearchTraceError):
        append_search_trace_record(
            first_segment,
            memory_before=first_result.memory,
            observation={"state_id": first_result.memory.frontier[0]},
            rationale="Advance ready item b toward the goal.",
            operation=second_request,
            result=second_result,
            limits=exact_limits,
        )
    assert first_segment.to_bytes() == first_bytes

    tampered_payload = json.loads(first_bytes)
    tampered_payload["records"][0]["index"] = 2
    tampered_bytes = json.dumps(
        tampered_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")

    with pytest.raises(SearchTraceValidationError):
        verify_search_trace_segment(tampered_bytes, limits=generous_limits)


def test_evaluated_accepted_transition_round_trips_through_public_trace_seam() -> None:
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    memory = SearchMemory.initial(authority)
    request = SearchTransitionRequest(
        source_state_id=authority.initial_state.state_id,
        action=GroundedAction("advance", ("a",)),
        frontier_intent=FrontierIntent(retire_source=True, target_position=0),
        visit_target=True,
        evaluate_target=True,
    )
    evaluation = StateEvaluation(
        novelty=1,
        heuristic=HeuristicValue(name="trace-test", value=1),
    )

    def evaluator(_state: object) -> StateEvaluation:
        return evaluation

    result = apply_search_transition(memory, request, evaluator=evaluator)
    assert isinstance(result, AcceptedTransition)

    limits = TraceSegmentLimits(max_records=1, max_bytes=10_000)
    trace = append_search_trace_record(
        start_search_trace(memory, limits=limits),
        memory_before=memory,
        observation={"state_id": authority.initial_state.state_id},
        rationale="Evaluate and advance ready item a.",
        operation=request,
        result=result,
        limits=limits,
    )
    trace_bytes = trace.to_bytes()

    assert verify_search_trace_segment(trace_bytes, limits=limits) is True
    replayed = replay_search_trace_segment(trace_bytes, authority=authority, limits=limits)
    assert replayed.to_bytes() == result.memory.to_bytes()


def test_start_search_trace_enforces_empty_envelope_byte_limit() -> None:
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    memory = SearchMemory.initial(authority)
    generous_limits = TraceSegmentLimits(max_records=1, max_bytes=10_000)
    empty_bytes = start_search_trace(memory, limits=generous_limits).to_bytes()
    exact_limits = TraceSegmentLimits(max_records=1, max_bytes=len(empty_bytes))

    assert start_search_trace(memory, limits=exact_limits).to_bytes() == empty_bytes
    with pytest.raises(SearchTraceValidationError):
        start_search_trace(
            memory,
            limits=TraceSegmentLimits(max_records=1, max_bytes=len(empty_bytes) - 1),
        )
