"""Issue #146 node-choice contract: kappa order, choice semantics, goal-at-selection, overflow rule, payloads."""

from __future__ import annotations

import json

import pytest

from examples.planning_benchmark_slice.bfs_pilot import exact_fifo_bfs
from examples.planning_benchmark_slice.bfws_episode import run_best_first_width
from examples.planning_benchmark_slice.node_choice import (
    NodeChoiceSession,
    NodeChoiceTask,
    canonical_choice,
    replay_node_choice_episode,
    run_control_episode,
)
from examples.planning_benchmark_slice.node_choice_views import node_payload, text_context
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority

DOMAIN = """(define (domain bw)
  (:requirements :strips)
  (:predicates (on ?x ?y) (ontable ?x) (clear ?x) (handempty) (holding ?x))
  (:action pick-up :parameters (?x)
    :precondition (and (clear ?x) (ontable ?x) (handempty))
    :effect (and (not (ontable ?x)) (not (clear ?x)) (not (handempty)) (holding ?x)))
  (:action put-down :parameters (?x)
    :precondition (holding ?x)
    :effect (and (not (holding ?x)) (clear ?x) (handempty) (ontable ?x)))
  (:action stack :parameters (?x ?y)
    :precondition (and (holding ?x) (clear ?y))
    :effect (and (not (holding ?x)) (not (clear ?y)) (clear ?x) (handempty) (on ?x ?y)))
  (:action unstack :parameters (?x ?y)
    :precondition (and (on ?x ?y) (clear ?x) (handempty))
    :effect (and (holding ?x) (clear ?y) (not (clear ?x)) (not (handempty)) (not (on ?x ?y)))))
"""
PROBLEM = """(define (problem bw3) (:domain bw)
  (:objects a b c)
  (:init (ontable a) (ontable b) (on c a) (clear b) (clear c) (handempty))
  (:goal (and (on a b) (on b c))))
"""


def authority() -> PDDLStateAuthority:
    return PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)


def expanded_ids(session: NodeChoiceSession) -> list[str]:
    return [
        session.controller._states_by_ref[e["trusted_runtime_result"]["expanded_state_id"]].state_id
        for e in session.events
        if e["trusted_runtime_result"]["status"] == "expanded"
    ]


def exact(algorithm: str, **kwargs) -> NodeChoiceSession:
    return run_control_episode(
        authority(), NodeChoiceTask("t", "bw", algorithm, 10**6), "text", "exact_reference", 17, **kwargs
    )


def test_exact_bfs_node_choice_reproduces_native_fifo_bfs():
    session = exact("bfs")
    native = exact_fifo_bfs(DOMAIN, PROBLEM, max_expansions=10**6)
    assert session.result()["goal_reached"]
    assert expanded_ids(session) == list(native.expanded_state_ids)
    assert session.controller.expansion_count == native.expansion_count


def test_exact_bfws_node_choice_has_the_native_bfws_order_as_prefix():
    session = exact("best_first_width")
    steps = []
    run_best_first_width(authority(), max_expansions=10**6, on_step=steps.append)
    native = list(dict.fromkeys((s.expansion_index, s.expanded_state_id) for s in steps))
    native_ids = [state_id for _index, state_id in native]
    assert session.result()["goal_reached"]
    assert expanded_ids(session)[: len(native_ids)] == native_ids


@pytest.mark.parametrize("algorithm", ["bfs", "best_first_width", "best_first_add_greedy", "best_first_add_w3"])
def test_choosing_a_non_head_node_expands_that_node(algorithm):
    session = NodeChoiceSession(
        authority=authority(),
        task=NodeChoiceTask("t", "bw", algorithm, 50),
        observation="text",
        arm="process_sft",
        seed=17,
    )
    request = session.next_request()
    assert request is not None
    session.submit_output(canonical_choice(request.menu_binding[0]["choice"]))  # the only node: s0
    request = session.next_request()
    assert request is not None
    head = session.kappa_head_ref()
    other = next(e for e in request.menu_binding if e["state_ref"] != head)
    session.submit_output(canonical_choice(other["choice"]))
    result = session.events[-1]["trusted_runtime_result"]
    assert result["status"] == "expanded"
    assert result["expanded_state_id"] == other["state_ref"] != head
    assert other["state_ref"] not in {m["state_id"] for m in session.controller.frontier_members()}


def test_bfs_never_reenqueues_a_generated_state():
    session = exact("bfs")
    enqueued = [
        a["trusted_runtime_result"]["target_state_id"]
        for e in session.events
        for a in e["trusted_runtime_result"].get("admissions", [])
        if a["trusted_runtime_result"]["status"] == "enqueued"
    ]
    assert len(enqueued) == len(set(enqueued))
    assert "s0" not in enqueued
    assert any(
        a["trusted_runtime_result"]["status"] == "duplicate"
        for e in session.events
        for a in e["trusted_runtime_result"].get("admissions", [])
    )


@pytest.mark.parametrize("algorithm", ["bfs", "best_first_width"])
def test_selecting_the_goal_node_solves_without_budget_charge(algorithm):
    session = exact(algorithm)
    last = session.events[-1]["trusted_runtime_result"]
    assert last == {**last, "accepted": True, "budget_charge": 0, "status": "goal_reached"}
    assert session.result()["expansion_count"] == session.result()["decision_count"] - 1


@pytest.mark.parametrize(
    "output", ["not json", json.dumps({"expand_choice": "c99"}), json.dumps({"expand_choice": "c0", "x": 1})]
)
def test_an_invalid_choice_terminates_the_episode(output):
    session = NodeChoiceSession(
        authority=authority(),
        task=NodeChoiceTask("t", "bw", "bfs", 20),
        observation="visual",
        arm="process_sft",
        seed=17,
    )
    session.next_request()
    session.submit_output(output)
    assert session.termination_reason == "deterministic_invalid_operation"
    assert session.result()["invalid_operation_count"] == 1
    assert session.next_request() is None


def test_random_valid_diverges_from_exact_under_bfs():
    r = exact("bfs").controller.expansion_count
    task = NodeChoiceTask("t", "bw", "bfs", r)
    exact_ids = expanded_ids(run_control_episode(authority(), task, "text", "exact_reference", 17))
    randoms = [expanded_ids(run_control_episode(authority(), task, "text", "random_valid", s)) for s in (17, 5077, 6131)]
    assert any(ids != exact_ids for ids in randoms)


def test_overflow_ends_the_episode_before_the_decision_and_replays():
    def counter(_model_input, menu_states):
        return 100 * len(menu_states)

    task = NodeChoiceTask("t", "bw", "bfs", 50)
    session = run_control_episode(authority(), task, "text", "random_valid", 17, token_limit=250, token_counter=counter)
    result = session.result()
    assert result["termination_reason"] == "observation_overflow"
    assert not result["goal_reached"]
    assert result["observation_overflow"]["decision_index"] == len(session.events)
    assert all(len(e["menu"]) <= 2 for e in session.events)
    report = session.episode()
    assert replay_node_choice_episode(authority(), task, report, token_counter=counter).result() == result
    with pytest.raises(ValueError):
        replay_node_choice_episode(authority(), task, report, token_counter=lambda m, s: 100 * len(s) - 1)


def test_text_payload_binds_facts_to_menu_order_and_exposes_no_search_values():
    session = NodeChoiceSession(
        authority=authority(),
        task=NodeChoiceTask("t", "bw", "best_first_width", 50),
        observation="text",
        arm="exact_reference",
        seed=17,
    )
    request = session.next_request()
    while request is not None and len(request.menu_binding) < 3:
        session.submit_output(session.reference_output())
        request = session.next_request()
    assert request is not None
    states = session.menu_states(request)
    context = text_context(authority(), DOMAIN, PROBLEM)
    payload = node_payload(dict(request.model_input), "text", context, states)
    assert set(payload) == {
        "algorithm",
        "frontier_menu",
        "representation",
        "schema_version",
        "view_legend",
        "static_context",
        "initial_state",
        "goal_constraints",
    }
    assert [e["choice"] for e in payload["frontier_menu"]["states"]] == payload["frontier_menu"]["choices"]
    assert [e["facts"] for e in payload["frontier_menu"]["states"]] == [context.state_facts(s) for s in states]
    assert set(payload["frontier_menu"]["states"][0]) == {"choice", "facts"}
    text = json.dumps(payload)
    for state in states:
        assert state.state_id not in text
    visual = node_payload({**request.model_input, "representation": "visual-node-choice"}, "visual", None, states)
    assert set(visual) == {"algorithm", "frontier_menu", "representation", "schema_version", "view_legend"}
    assert set(visual["frontier_menu"]) == {"choices"}
