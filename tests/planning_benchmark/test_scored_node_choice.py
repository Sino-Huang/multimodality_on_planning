"""Issue #149 learned-heuristic driver and h* labeller."""

from __future__ import annotations

import copy
import importlib.util

import pytest

from examples.planning_benchmark_slice.node_choice import NodeChoiceSession, NodeChoiceTask, run_control_episode
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.scored_node_choice import (
    FunctionScorer,
    goal_count_scorer,
    hadd_scorer,
    run_scored_episode,
    verify_scored_episode,
)

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


ADDITIVE = ("best_first_add_greedy", "best_first_add_w3")


def task(algorithm: str, r: int = 10**6) -> NodeChoiceTask:
    return NodeChoiceTask("t", "bw", algorithm, r)


@pytest.mark.parametrize("algorithm", ADDITIVE)
def test_hadd_scorer_reproduces_the_exact_reference(algorithm):
    """Key s (GBFS) / g + 3 s (WA*) with serial ties is the runtime's kappa: same expansions, same result."""

    a = authority()
    exact = run_control_episode(a, task(algorithm), "text", "exact_reference", 17)
    scored = run_scored_episode(a, task(algorithm), hadd_scorer(a))
    assert expanded_ids(scored) == expanded_ids(exact)
    assert scored.result() == exact.result()


def test_ties_break_by_generation_serial():
    """A constant scorer makes GBFS breadth-first in generation order."""

    a = authority()
    scored = run_scored_episode(a, task("best_first_add_greedy", 50), FunctionScorer("zero", lambda s: 0.0))
    serials = []
    for event in scored.events:
        result = event["trusted_runtime_result"]
        if result["status"] == "expanded":
            serials.append(int(result["expanded_state_id"][1:]))
    assert serials == sorted(serials)


def test_goal_count_episode_replays_and_tampering_fails():
    a = authority()
    session = run_scored_episode(a, task("best_first_add_greedy", 20), goal_count_scorer(a))
    report = session.episode()
    assert report["arm"] == "scored_heuristic"
    verified = verify_scored_episode(authority(), task("best_first_add_greedy", 20), report, scorer=goal_count_scorer(a))
    assert verified["result"] == report["result"]
    menus = [i for i, e in enumerate(report["events"]) if len(e["menu"]) >= 2]
    event = copy.deepcopy(report["events"][menus[0]])
    tampered = {**report, "events": [*report["events"][: menus[0]], event, *report["events"][menus[0] + 1 :]]}
    chosen_ref = event["trusted_runtime_result"]["expanded_state_id"]
    chosen = next(i for i, e in enumerate(event["menu"]) if e["state_ref"] == chosen_ref)
    event["scores"][chosen] = max(s for s in event["scores"] if s is not None) + 100
    with pytest.raises(ValueError, match=r"argmin"):
        verify_scored_episode(authority(), task("best_first_add_greedy", 20), tampered)


@pytest.mark.skipif(importlib.util.find_spec("up_fast_downward") is None, reason="Fast Downward wheel not installed")
def test_fast_downward_hstar_matches_blind_distance():
    from examples.planning_benchmark_slice.optimal_cost import blind_distance, optimal_cost

    a = authority()
    states = [a.initial_state]
    for action in a.applicable_actions(a.initial_state):
        states.append(a.apply(a.initial_state, action).target_state)
    for state in states:
        label = optimal_cost(DOMAIN, PROBLEM, a, state)
        assert label["status"] == "solved"
        assert label["hstar"] == blind_distance(a, state, state_limit=10**5)
