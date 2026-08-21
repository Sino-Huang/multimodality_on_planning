from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

import pytest

from examples.planning_benchmark_slice import search_context
from examples.planning_benchmark_slice.pddl_state import (
    CanonicalState,
    GroundedAction,
    PDDLStateAuthority,
    PDDLTransition,
    TransitionProvenance,
)
from examples.planning_benchmark_slice.search_memory import (
    AcceptedRetirement,
    AcceptedTransition,
    FrontierIntent,
    HeuristicValue,
    RejectedTransition,
    SearchMemory,
    SearchRetireRequest,
    SearchTransitionRequest,
    StateEvaluation,
    apply_search_retirement,
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
) -> tuple[
    bytes,
    PDDLStateAuthority,
    tuple[SearchMemory, ...],
    tuple[SearchTransitionRequest, ...],
]:
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
        (first_request, rejected_request, final_request),
    )


def test_materializes_every_checkpoint_and_one_record_atomic_segment() -> None:
    trace_bytes, authority, boundary_memories, _ = _three_record_trace("left-future")

    materialized = search_context.materialize_search_trace(
        trace_bytes,
        authority=authority,
        limits=LIMITS,
    )

    assert len(materialized.checkpoints) == 4
    assert [checkpoint.restore(authority).to_bytes() for checkpoint in materialized.checkpoints] == [
        memory.to_bytes() for memory in boundary_memories
    ]
    assert len(materialized.atomic_segments) == 3

    original_records = json.loads(trace_bytes)["records"]
    for record_index, atomic_segment in enumerate(materialized.atomic_segments):
        atomic_bytes = atomic_segment.to_bytes()
        atomic_payload = json.loads(atomic_bytes)
        assert atomic_payload["record_count"] == 1
        assert len(atomic_payload["records"]) == 1
        checkpoint_payload = atomic_payload["checkpoint"]
        assert set(checkpoint_payload) == {
            "accepted_transitions",
            "authority_id",
            "snapshot",
        }
        snapshot_payload = checkpoint_payload["snapshot"]
        assert {
            "frontier",
            "visited",
            "novelty",
            "heuristics",
            "provenance",
            "known_states",
        } <= set(snapshot_payload)
        assert snapshot_payload["frontier"] == list(boundary_memories[record_index].frontier)
        assert snapshot_payload["visited"] == sorted(boundary_memories[record_index].visited)
        assert {
            field: atomic_payload["records"][0][field] for field in ("observation", "rationale", "operation", "result")
        } == {
            field: original_records[record_index][field] for field in ("observation", "rationale", "operation", "result")
        }

        rematerialized = search_context.materialize_search_trace(
            atomic_bytes,
            authority=authority,
            limits=LIMITS,
        )
        assert len(rematerialized.atomic_segments) == 1
        assert rematerialized.checkpoints[0].restore(authority).to_bytes() == boundary_memories[record_index].to_bytes()
        assert (
            rematerialized.checkpoints[-1].restore(authority).to_bytes()
            == boundary_memories[record_index + 1].to_bytes()
        )


def test_materializes_single_pass_without_rebuilding_atomic_segments(monkeypatch: pytest.MonkeyPatch) -> None:
    trace_bytes, authority, boundary_memories, _ = _three_record_trace("left-future")

    def fail_if_atomic_segment_is_rebuilt(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("single-pass materialization rebuilt an atomic segment")

    monkeypatch.setattr(search_context, "_build_context_payload", fail_if_atomic_segment_is_rebuilt)

    materialized = search_context.materialize_search_trace(
        trace_bytes,
        authority=authority,
        limits=LIMITS,
        include_atomic_segments=False,
    )

    assert materialized.atomic_segments == ()
    assert len(materialized.checkpoints) == 4
    assert materialized.checkpoints[-1].restore(authority).to_bytes() == boundary_memories[-1].to_bytes()
    assert materialized.rolling_context_before(3, accepted_delta_limit=2).checkpoint is materialized.checkpoints[3]


def test_materializes_retirement_and_restores_its_checkpoint_memory() -> None:
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    memory = SearchMemory.initial(authority)
    request = SearchRetireRequest(memory.frontier[0])
    result = apply_search_retirement(memory, request)
    assert isinstance(result, AcceptedRetirement)

    trace = append_search_trace_record(
        start_search_trace(memory, limits=LIMITS),
        memory_before=memory,
        observation={"state_id": authority.initial_state.state_id},
        rationale="Retire the exhausted frontier head.",
        operation=request,
        result=result,
        limits=LIMITS,
    )

    materialized = search_context.materialize_search_trace(
        trace.to_bytes(),
        authority=authority,
        limits=LIMITS,
    )

    restored = materialized.checkpoints[-1].restore(authority)
    assert restored.to_bytes() == result.memory.to_bytes()


def test_checkpoints_expose_typed_markov_sufficient_search_memory_snapshots() -> None:
    trace_bytes, authority, boundary_memories, requests = _three_record_trace("left-future")
    materialized = search_context.materialize_search_trace(
        trace_bytes,
        authority=authority,
        limits=LIMITS,
    )

    for checkpoint, expected_memory in zip(
        materialized.checkpoints,
        boundary_memories,
        strict=True,
    ):
        snapshot = checkpoint.snapshot
        restored = checkpoint.restore(authority)

        assert not isinstance(snapshot, (bytes, str, Mapping))
        assert isinstance(snapshot.frontier, tuple)
        assert snapshot.frontier == expected_memory.frontier
        assert isinstance(snapshot.visited, frozenset)
        assert snapshot.visited == expected_memory.visited
        assert isinstance(snapshot.novelty, Mapping)
        assert dict(snapshot.novelty) == dict(expected_memory.novelty)
        assert all(isinstance(value, int) for value in snapshot.novelty.values())
        assert isinstance(snapshot.heuristics, Mapping)
        assert dict(snapshot.heuristics) == dict(expected_memory.heuristics)
        assert all(isinstance(value, HeuristicValue) for value in snapshot.heuristics.values())
        assert isinstance(snapshot.provenance, tuple)
        assert snapshot.provenance == expected_memory.provenance
        assert all(isinstance(value, TransitionProvenance) for value in snapshot.provenance)
        assert isinstance(snapshot.known_states, Mapping)
        assert frozenset(snapshot.known_states) == expected_memory.visited
        assert all(
            isinstance(state, CanonicalState)
            and state_id == state.state_id
            and state.authority_id == authority.authority_id
            for state_id, state in snapshot.known_states.items()
        )
        assert restored.to_bytes() == expected_memory.to_bytes()

    def unexpected_evaluator(_state: object) -> StateEvaluation:
        raise AssertionError("the continued transition did not request evaluation")

    continued = apply_search_transition(
        materialized.checkpoints[2].restore(authority),
        requests[2],
        evaluator=unexpected_evaluator,
    )
    assert isinstance(continued, AcceptedTransition)
    assert continued.memory.to_bytes() == boundary_memories[3].to_bytes()


def test_rolling_context_keeps_only_accepted_deltas_in_record_order() -> None:
    trace_bytes, authority, boundary_memories, requests = _three_record_trace("left-future")
    materialized = search_context.materialize_search_trace(
        trace_bytes,
        authority=authority,
        limits=LIMITS,
    )

    rolling = materialized.rolling_context_before(3, accepted_delta_limit=2)
    rolling_bytes = rolling.to_bytes()
    rolling_payload = json.loads(rolling_bytes)
    source_records = json.loads(trace_bytes)["records"]

    assert [delta.record_index for delta in rolling.accepted_deltas] == [0, 2]
    assert rolling.checkpoint is materialized.checkpoints[3]
    assert rolling.checkpoint.restore(authority).to_bytes() == boundary_memories[3].to_bytes()

    for delta, record_index, request in zip(
        rolling.accepted_deltas,
        (0, 2),
        (requests[0], requests[2]),
        strict=True,
    ):
        source_record = source_records[record_index]
        assert delta.record_index == record_index
        assert isinstance(delta.operation, SearchTransitionRequest)
        assert delta.operation == request
        assert isinstance(delta.transition, PDDLTransition)
        assert delta.transition.source_state.state_id == request.source_state_id
        assert (
            delta.transition.target_state.state_id == source_record["result"]["transition"]["target_state"]["state_id"]
        )
        assert delta.evaluation is None

    assert rolling_bytes == json.dumps(
        rolling_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    assert rolling_payload["context_type"] == "rolling_search_context"
    assert set(rolling_payload) - {"snapshot", "accepted_deltas"} <= {
        "schema_version",
        "context_type",
        "authority_id",
    }
    assert {
        "frontier",
        "visited",
        "novelty",
        "heuristics",
        "provenance",
        "known_states",
    } <= set(rolling_payload["snapshot"])
    assert [item["record_index"] for item in rolling_payload["accepted_deltas"]] == [0, 2]
    assert all(
        set(item)
        == {
            "record_index",
            "operation",
            "transition",
            "evaluation",
        }
        for item in rolling_payload["accepted_deltas"]
    )
    assert [item["operation"] for item in rolling_payload["accepted_deltas"]] == [
        source_records[0]["operation"],
        source_records[2]["operation"],
    ]
    assert [item["transition"] for item in rolling_payload["accepted_deltas"]] == [
        source_records[0]["result"]["transition"],
        source_records[2]["result"]["transition"],
    ]
    assert [item["evaluation"] for item in rolling_payload["accepted_deltas"]] == [None, None]
    for forbidden in (
        '"observation"',
        '"rationale"',
        '"status"',
        '"reason"',
        "target must be visited",
        "left-future",
    ):
        assert forbidden not in rolling_bytes.decode("utf-8")


def test_prefix_context_and_first_atomic_segment_have_no_future_leakage() -> None:
    left_bytes, left_authority, _, _ = _three_record_trace("left-future")
    right_bytes, right_authority, _, _ = _three_record_trace("right-future")
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

    left_context = left.rolling_context_before(1, accepted_delta_limit=2)
    right_context = right.rolling_context_before(1, accepted_delta_limit=2)
    left_prefix = left_context.to_bytes()
    right_prefix = right_context.to_bytes()
    left_atomic = left.atomic_segments[0].to_bytes()
    right_atomic = right.atomic_segments[0].to_bytes()

    assert left_context.checkpoint is left.checkpoints[1]
    assert right_context.checkpoint is right.checkpoints[1]
    assert left_prefix == right_prefix
    assert left_atomic == right_atomic
    assert left_prefix != left_atomic
    assert "snapshot" in json.loads(left_prefix)
    assert "record_count" in json.loads(left_atomic)
    for sentinel in (b"left-future", b"right-future"):
        assert sentinel not in left_prefix
        assert sentinel not in right_prefix
        assert sentinel not in left_atomic
        assert sentinel not in right_atomic


@pytest.mark.parametrize("record_index", [-1, 4, True, "1"])
def test_rolling_context_rejects_invalid_cutoff(record_index: object) -> None:
    trace_bytes, authority, _, _ = _three_record_trace("left-future")
    materialized = search_context.materialize_search_trace(
        trace_bytes,
        authority=authority,
        limits=LIMITS,
    )

    with pytest.raises((TypeError, ValueError)):
        materialized.rolling_context_before(cast(int, record_index), accepted_delta_limit=2)


@pytest.mark.parametrize("accepted_delta_limit", [-1, True, "2"])
def test_rolling_context_rejects_invalid_delta_limit(accepted_delta_limit: object) -> None:
    trace_bytes, authority, _, _ = _three_record_trace("left-future")
    materialized = search_context.materialize_search_trace(
        trace_bytes,
        authority=authority,
        limits=LIMITS,
    )

    with pytest.raises((TypeError, ValueError)):
        materialized.rolling_context_before(3, accepted_delta_limit=cast(int, accepted_delta_limit))


def test_materialization_rejects_semantically_tampered_persisted_payload() -> None:
    trace_bytes, authority, _, _ = _three_record_trace("left-future")
    tampered_payload = json.loads(trace_bytes)
    tampered_payload["records"][0]["operation"]["source_state_id"] = "unknown-state"
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
