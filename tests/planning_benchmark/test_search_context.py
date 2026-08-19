from __future__ import annotations

import json
from typing import cast

import pytest

from examples.planning_benchmark_slice import search_context
from examples.planning_benchmark_slice.pddl_state import GroundedAction, PDDLStateAuthority
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
from examples.planning_benchmark_slice.search_trace import (
    TraceSegmentLimits,
    append_search_trace_record,
    start_search_trace,
)

DOMAIN = """
(define (domain context-memory)
  (:requirements :strips :typing)
  (:types item)
  (:predicates (ready ?x - item) (done ?x - item))
  (:action advance
    :parameters (?x - item)
    :precondition (ready ?x)
    :effect (and (not (ready ?x)) (done ?x))))
"""

PROBLEM = """
(define (problem context-memory-problem)
  (:domain context-memory)
  (:objects a b - item)
  (:init (ready a) (ready b))
  (:goal (and (done a) (done b))))
"""

LIMITS = TraceSegmentLimits(max_records=3, max_bytes=100_000)


def _materialization_error() -> type[Exception]:
    error = search_context.TraceMaterializationError
    assert isinstance(error, type) and issubclass(error, Exception)
    return error


def _three_record_trace(
    sentinel: str,
) -> tuple[bytes, PDDLStateAuthority, tuple[SearchMemory, ...]]:
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    initial_memory = SearchMemory.initial(authority)

    first_request = SearchTransitionRequest(
        source_state_id=authority.initial_state.state_id,
        action=GroundedAction("advance", ("a",)),
        frontier_intent=FrontierIntent(retire_source=True, target_position=0),
        visit_target=True,
        evaluate_target=False,
    )

    def unexpected_evaluator(_state: object) -> StateEvaluation:
        raise AssertionError("the transition did not request evaluation")

    first_result = apply_search_transition(
        initial_memory,
        first_request,
        evaluator=unexpected_evaluator,
    )
    assert isinstance(first_result, AcceptedTransition)

    if sentinel == "left-future":
        rejected_request = SearchTransitionRequest(
            source_state_id=first_result.memory.frontier[0],
            action=GroundedAction("advance", ("b",)),
            frontier_intent=FrontierIntent(retire_source=True, target_position=0),
            visit_target=False,
            evaluate_target=False,
        )
        final_evaluate_target = False
    else:
        rejected_request = SearchTransitionRequest(
            source_state_id=first_result.memory.frontier[0],
            action=GroundedAction("advance", ("b",)),
            frontier_intent=FrontierIntent(retire_source=True, target_position=2),
            visit_target=True,
            evaluate_target=False,
        )
        final_evaluate_target = True

    rejected_result = apply_search_transition(
        first_result.memory,
        rejected_request,
        evaluator=unexpected_evaluator,
    )
    assert isinstance(rejected_result, RejectedTransition)
    assert rejected_result.memory.to_bytes() == first_result.memory.to_bytes()

    final_request = SearchTransitionRequest(
        source_state_id=first_result.memory.frontier[0],
        action=GroundedAction("advance", ("b",)),
        frontier_intent=FrontierIntent(retire_source=True, target_position=0),
        visit_target=True,
        evaluate_target=final_evaluate_target,
    )

    def sentinel_evaluator(_state: object) -> StateEvaluation:
        return StateEvaluation(
            novelty=7,
            heuristic=HeuristicValue(name=sentinel, value=11),
        )

    final_result = apply_search_transition(
        rejected_result.memory,
        final_request,
        evaluator=sentinel_evaluator if final_evaluate_target else unexpected_evaluator,
    )
    assert isinstance(final_result, AcceptedTransition)

    trace = start_search_trace(initial_memory, limits=LIMITS)
    trace = append_search_trace_record(
        trace,
        memory_before=initial_memory,
        observation={"state_id": authority.initial_state.state_id},
        rationale="Shared accepted record before either future.",
        operation=first_request,
        result=first_result,
        limits=LIMITS,
    )
    trace = append_search_trace_record(
        trace,
        memory_before=first_result.memory,
        observation={"sentinel": sentinel, "step": "rejected"},
        rationale=f"{sentinel}: rejected rationale",
        operation=rejected_request,
        result=rejected_result,
        limits=LIMITS,
    )
    trace = append_search_trace_record(
        trace,
        memory_before=rejected_result.memory,
        observation={"sentinel": sentinel, "step": "accepted"},
        rationale=f"{sentinel}: accepted rationale",
        operation=final_request,
        result=final_result,
        limits=LIMITS,
    )
    return (
        trace.to_bytes(),
        authority,
        (initial_memory, first_result.memory, rejected_result.memory, final_result.memory),
    )


def test_materializes_every_checkpoint_and_one_record_atomic_segment() -> None:
    trace_bytes, authority, boundary_memories = _three_record_trace("left-future")

    materialized = search_context.materialize_search_trace(
        trace_bytes,
        authority=authority,
        limits=LIMITS,
    )

    assert len(materialized.checkpoints) == 4
    assert [
        checkpoint.restore(authority).to_bytes() for checkpoint in materialized.checkpoints
    ] == [memory.to_bytes() for memory in boundary_memories]
    assert len(materialized.atomic_segments) == 3

    original_records = json.loads(trace_bytes)["records"]
    for record_index, atomic_segment in enumerate(materialized.atomic_segments):
        atomic_bytes = atomic_segment.to_bytes()
        atomic_payload = json.loads(atomic_bytes)
        assert atomic_payload["record_count"] == 1
        assert len(atomic_payload["records"]) == 1
        assert {
            field: atomic_payload["records"][0][field]
            for field in ("observation", "rationale", "operation", "result")
        } == {
            field: original_records[record_index][field]
            for field in ("observation", "rationale", "operation", "result")
        }

        rematerialized = search_context.materialize_search_trace(
            atomic_bytes,
            authority=authority,
            limits=LIMITS,
        )
        assert len(rematerialized.atomic_segments) == 1
        assert rematerialized.checkpoints[0].restore(authority).to_bytes() == boundary_memories[
            record_index
        ].to_bytes()
        assert rematerialized.checkpoints[-1].restore(authority).to_bytes() == boundary_memories[
            record_index + 1
        ].to_bytes()


def test_rolling_context_keeps_only_accepted_deltas_in_record_order() -> None:
    trace_bytes, authority, _ = _three_record_trace("left-future")
    materialized = search_context.materialize_search_trace(
        trace_bytes,
        authority=authority,
        limits=LIMITS,
    )

    rolling = materialized.rolling_context_before(3, accepted_delta_limit=2)

    assert [delta.record_index for delta in rolling.accepted_deltas] == [0, 2]
    assert isinstance(rolling.to_bytes(), bytes)


def test_prefix_context_and_first_atomic_segment_have_no_future_leakage() -> None:
    left_bytes, left_authority, _ = _three_record_trace("left-future")
    right_bytes, right_authority, _ = _three_record_trace("right-future")
    left_payload = json.loads(left_bytes)
    right_payload = json.loads(right_bytes)
    assert left_payload["records"][0] == right_payload["records"][0]
    assert left_payload["records"][1:] != right_payload["records"][1:]

    left = search_context.materialize_search_trace(
        left_bytes,
        authority=left_authority,
        limits=LIMITS,
    )
    right = search_context.materialize_search_trace(
        right_bytes,
        authority=right_authority,
        limits=LIMITS,
    )

    left_prefix = left.rolling_context_before(1, accepted_delta_limit=2).to_bytes()
    right_prefix = right.rolling_context_before(1, accepted_delta_limit=2).to_bytes()
    assert left_prefix == right_prefix
    assert left_prefix == left.atomic_segments[0].to_bytes()
    assert right_prefix == right.atomic_segments[0].to_bytes()


@pytest.mark.parametrize("record_index", [-1, 4, True, "1"])
def test_rolling_context_rejects_invalid_cutoff(record_index: object) -> None:
    trace_bytes, authority, _ = _three_record_trace("left-future")
    materialized = search_context.materialize_search_trace(
        trace_bytes,
        authority=authority,
        limits=LIMITS,
    )

    with pytest.raises((TypeError, ValueError)):
        materialized.rolling_context_before(cast(int, record_index), accepted_delta_limit=2)


@pytest.mark.parametrize("accepted_delta_limit", [-1, True, "2"])
def test_rolling_context_rejects_invalid_delta_limit(accepted_delta_limit: object) -> None:
    trace_bytes, authority, _ = _three_record_trace("left-future")
    materialized = search_context.materialize_search_trace(
        trace_bytes,
        authority=authority,
        limits=LIMITS,
    )

    with pytest.raises((TypeError, ValueError)):
        materialized.rolling_context_before(3, accepted_delta_limit=cast(int, accepted_delta_limit))


def test_materialization_rejects_hash_tampered_persisted_payload() -> None:
    trace_bytes, authority, _ = _three_record_trace("left-future")
    tampered_payload = json.loads(trace_bytes)
    tampered_payload["records"][1]["record_hash"] = "0" * 64
    tampered_bytes = json.dumps(
        tampered_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")

    with pytest.raises(_materialization_error()):
        search_context.materialize_search_trace(
            tampered_bytes,
            authority=authority,
            limits=LIMITS,
        )
