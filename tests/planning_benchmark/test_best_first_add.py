from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.best_first_add import AdditiveHeuristic
from examples.planning_benchmark_slice.best_first_controller import (
    BEST_FIRST_SETTINGS,
    BestFirstController,
)
from examples.planning_benchmark_slice.best_first_episode import (
    BestFirstTraceLimitError,
    run_best_first,
    serialize_best_first_trace,
)
from examples.planning_benchmark_slice.best_first_model_input import (
    build_best_first_live_model_input,
    build_best_first_teacher_model_input,
    serialize_best_first_message_prefix,
)
from examples.planning_benchmark_slice.best_first_qualification import (
    run_best_first_qualification,
)
from examples.planning_benchmark_slice.best_first_replay import (
    BestFirstReplayError,
    replay_best_first_events,
    replay_best_first_trace,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority


def test_additive_heuristic_sums_independent_relaxed_subgoals() -> None:
    domain = """(define (domain independent-goals)
      (:requirements :strips)
      (:predicates (start) (left) (right))
      (:action make-left :parameters () :precondition (start) :effect (left))
      (:action make-right :parameters () :precondition (start) :effect (right)))"""
    problem = """(define (problem independent-goals-p)
      (:domain independent-goals)
      (:init (start))
      (:goal (and (left) (right))))"""
    authority = PDDLStateAuthority.from_pddl(domain, problem)

    heuristic = AdditiveHeuristic(authority)

    assert heuristic(authority.initial_state) == 2


def test_declared_settings_expose_only_their_scalar_priority() -> None:
    domain = """(define (domain priority-example)
      (:requirements :strips)
      (:predicates (start) (near) (far) (middle) (goal))
      (:action choose-near :parameters () :precondition (start)
        :effect (and (near) (not (start))))
      (:action choose-far :parameters () :precondition (start)
        :effect (and (far) (not (start))))
      (:action finish-near :parameters () :precondition (near) :effect (goal))
      (:action advance-far :parameters () :precondition (far)
        :effect (and (middle) (not (far))))
      (:action finish-far :parameters () :precondition (middle) :effect (goal)))"""
    problem = """(define (problem priority-example-p)
      (:domain priority-example) (:init (start)) (:goal (goal)))"""
    authority = PDDLStateAuthority.from_pddl(domain, problem)

    quality = BestFirstController(authority, BEST_FIRST_SETTINGS["best_first_add_w3"])
    quality.start_expansion()
    assert quality.setting.priority_name == "g_plus_3h"
    assert [candidate.priority for candidate in quality.current_candidates()] == [7, 4]

    compact = BestFirstController(authority, BEST_FIRST_SETTINGS["best_first_add_greedy"])
    compact.start_expansion()
    assert [candidate.priority for candidate in compact.current_candidates()] == [2, 1]


def test_teacher_and_live_share_one_canonical_best_first_input() -> None:
    domain = """(define (domain one-step) (:requirements :strips)
      (:predicates (start) (goal))
      (:action finish :parameters () :precondition (start) :effect (goal)))"""
    problem = """(define (problem one-step-p) (:domain one-step)
      (:init (start)) (:goal (goal)))"""
    authority = PDDLStateAuthority.from_pddl(domain, problem)
    controller = BestFirstController(authority, BEST_FIRST_SETTINGS["best_first_add_greedy"])
    controller.start_expansion()

    teacher = build_best_first_teacher_model_input(authority, controller)
    live = build_best_first_live_model_input(authority, controller)

    assert teacher == live
    assert teacher["algorithm"] == "best_first_add_greedy"
    assert teacher["current"]["priority"] == 1
    assert serialize_best_first_message_prefix(teacher)[1]["content"].startswith('{"accepted_deltas":[]')


def test_compact_trace_replays_without_persisting_full_frontiers_or_inputs() -> None:
    domain = """(define (domain two-step) (:requirements :strips)
      (:predicates (start) (middle) (goal))
      (:action advance :parameters () :precondition (start)
        :effect (and (middle) (not (start))))
      (:action finish :parameters () :precondition (middle) :effect (goal)))"""
    problem = """(define (problem two-step-p) (:domain two-step)
      (:init (start)) (:goal (goal)))"""
    authority = PDDLStateAuthority.from_pddl(domain, problem)

    search = run_best_first(
        authority,
        algorithm="best_first_add_w3",
        max_expansions=8,
        max_trace_records=8,
        max_trace_bytes=20_000,
    )
    replay = replay_best_first_events(
        search.states_payload,
        list(search.events),
        authority=authority,
        algorithm="best_first_add_w3",
        max_expansions=8,
        accepted_delta_limit=16,
    )

    assert search.goal_reached
    assert search.termination == "goal_reached"
    assert replay.expansion_count == 2
    assert replay.decision_count == 2
    assert set(search.events[0]) == {
        "decisions",
        "expanded_state_id",
        "expansion_index",
        "frontier_after",
        "frontier_before",
        "index",
    }
    assert set(search.events[0]["frontier_before"]) == {"count", "head"}
    assert "input" not in search.events[0]["decisions"][0]
    assert len(search.events[0]["decisions"][0]["input_sha256"]) == 64
    assert search.events[0]["expanded_state_id"] == "s0"
    assert json.loads(search.events[0]["decisions"][0]["target"])["source_state_id"] == "s0"
    assert set(search.states_payload) == {"s0", "s1", "s2"}
    assert search.trace_size_bytes == len(serialize_best_first_trace(search.trace_payload))
    assert replay_best_first_trace(search.trace_payload, authority=authority) == replay

    tampered = deepcopy(search.trace_payload)
    tampered["events"][0]["decisions"][0]["input_sha256"] = "0" * 64
    with pytest.raises(BestFirstReplayError, match="model-input bytes differ"):
        replay_best_first_trace(tampered, authority=authority)

    with pytest.raises(BestFirstTraceLimitError, match="limit is 100"):
        run_best_first(
            authority,
            algorithm="best_first_add_w3",
            max_expansions=8,
            max_trace_records=8,
            max_trace_bytes=100,
        )


def test_eventless_qualification_obeys_both_search_ceilings() -> None:
    domain = """(define (domain two-step) (:requirements :strips)
      (:predicates (start) (middle) (goal))
      (:action advance :parameters () :precondition (start)
        :effect (and (middle) (not (start))))
      (:action finish :parameters () :precondition (middle) :effect (goal)))"""
    problem = """(define (problem two-step-p) (:domain two-step)
      (:init (start)) (:goal (goal)))"""
    authority = PDDLStateAuthority.from_pddl(domain, problem)

    solved = run_best_first_qualification(
        authority,
        "best_first_add_greedy",
        max_expansions=8,
        max_decisions=8,
    )
    stopped = run_best_first_qualification(
        authority,
        "best_first_add_greedy",
        max_expansions=1,
        max_decisions=8,
    )

    assert (solved.termination, solved.expansion_count, solved.decision_count) == (
        "goal_reached",
        2,
        2,
    )
    assert solved.solution_cost == 2
    assert stopped.termination == "expansion_budget"


def test_w3_reduces_expansions_on_the_frozen_visitall_regression() -> None:
    root = Path(__file__).resolve().parents[2]
    design = json.loads((root / "configs/experiments/best-first-paired-design-v3.json").read_bytes())
    regression = design["selection_evidence"]["bounded_expansion_regression"]
    task = json.loads((root / regression["task_path"]).read_bytes())
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])

    results = {
        algorithm: run_best_first_qualification(
            authority,
            algorithm,
            max_expansions=2_000,
            max_decisions=10_000,
        )
        for algorithm in ("best_first_add_w2", "best_first_add_w3")
    }

    assert regression == {
        "best_first_add_w2": {"decision_count": 1689, "expansion_count": 448, "solution_cost": 44},
        "best_first_add_w3": {"decision_count": 1261, "expansion_count": 331, "solution_cost": 48},
        "task_path": "data/astar_paired_phase_v1/tasks/visitall/easy/train/visitall-train-easy-0038.json",
    }
    for algorithm, expected in regression.items():
        if algorithm == "task_path":
            continue
        result = results[algorithm]
        assert result.termination == "goal_reached"
        assert {
            "decision_count": result.decision_count,
            "expansion_count": result.expansion_count,
            "solution_cost": result.solution_cost,
        } == expected
    assert results["best_first_add_w3"].expansion_count < results["best_first_add_w2"].expansion_count
