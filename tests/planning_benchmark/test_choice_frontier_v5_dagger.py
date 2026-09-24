"""#140 DAgger contracts: on-policy teacher label, replay sampler, pooled verdict rules."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.choice_frontier import (
    ChoiceFrontierModelSession,
    ChoiceFrontierTask,
    canonical_choice,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from scripts.analyze_choice_frontier_v5_dagger import co_primary_verdict, primary_verdict
from scripts.run_choice_frontier_v5_dagger import replay_sample, sample_order, teacher_label

DOMAIN = json.loads(
    (Path(__file__).resolve().parents[2] / "tests/fixtures/planning/blocksworld_nontrivial.json").read_text()
)["domain_pddl"]
PROBLEM = """(define (problem bw-tower-4)
  (:domain blocksworld-4ops)
  (:objects a b c d)
  (:init (arm-empty) (clear a) (clear b) (clear c) (clear d)
         (on-table a) (on-table b) (on-table c) (on-table d))
  (:goal (and (on a b) (on b c) (on c d))))
"""


def session_for(algorithm: str, arm: str) -> ChoiceFrontierModelSession:
    task = ChoiceFrontierTask(instance_id="t", pair_id="t", domain="blocksworld", algorithm=algorithm,
                              exact_expansions=20)
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    return ChoiceFrontierModelSession(authority=authority, task=task, arm=arm, seed=17, adapter_id="adapter")


def independent_head_label(session, request) -> str:
    """Minimum (priority, generation serial) over the live frontier, mapped to its menu label."""

    entries = session.controller._frontier_entries
    state_id = min(entries, key=lambda sid: (entries[sid][0], entries[sid][1]))
    ref = session.controller._state_ref_by_id[state_id]
    return next(e["choice"] for e in request.menu_binding if e["state_ref"] == ref)


@pytest.mark.parametrize("algorithm", ["best_first_add_greedy", "best_first_add_w3"])
def test_teacher_label_is_the_current_heap_head_on_a_deviating_rollout(algorithm):
    reference = session_for(algorithm, "exact_reference")
    teacher_path = []
    while (request := reference.next_request()) is not None:
        teacher_path.append(reference.menu_states(request))
        reference.submit_output(reference.reference_output())

    session = session_for(algorithm, "process_sft")
    deviations = 0
    labels_off_teacher_path = 0
    while (request := session.next_request()) is not None:
        label, ref = teacher_label(session, request)
        assert label == independent_head_label(session, request)
        assert next(e["state_ref"] for e in request.menu_binding if e["choice"] == label) == ref
        others = [e["choice"] for e in request.menu_binding if e["choice"] != label]
        index = request.decision_index
        if index >= len(teacher_path) or session.menu_states(request) != teacher_path[index]:
            labels_off_teacher_path += 1
        if others:  # the policy's own (non-teacher) choice drives the rollout
            deviations += 1
            session.submit_output(canonical_choice(others[-1]))
        else:
            session.submit_output(canonical_choice(label))
    assert deviations > 0
    # The frontier left the teacher's trajectory, and the label still tracked its heap head.
    assert labels_off_teacher_path > 0


def test_replay_sampler_is_deterministic_and_seeded_per_cell():
    ids = [f"task-{i}:alg:{i % 7}" for i in range(2048)]
    first = replay_sample(ids, "best_first_add_w3", 29)
    assert first == replay_sample(list(ids), "best_first_add_w3", 29)
    assert first == random.Random("replay:best_first_add_w3:29").sample(ids, 1024)
    assert len(first) == len(set(first)) == 1024 and set(first) <= set(ids)
    assert first != replay_sample(ids, "best_first_add_w3", 71)
    assert first != replay_sample(ids, "best_first_add_greedy", 29)
    order = sample_order(["d1", "d2"], ["r1"], "best_first_add_w3", 29)
    assert order == sample_order(["d1", "d2"], ["r1"], "best_first_add_w3", 29)
    assert sorted(order) == [("d1", 0), ("d1", 1), ("d2", 0), ("d2", 1), ("r1", 0), ("r1", 1)]


@pytest.mark.parametrize(
    ("lo", "hi", "expected"),
    [
        (1e-12, 0.4, "SEPARATED_ABOVE"),
        (0.0, 0.4, "NOT_SEPARATED"),
        (-0.4, 0.0, "NOT_SEPARATED"),
        (-0.4, -1e-12, "SEPARATED_BELOW"),
    ],
)
def test_primary_verdict_boundaries(lo, hi, expected):
    assert primary_verdict(lo, hi) == expected
    assert primary_verdict(lo, hi, "FAIL") == "SMOKE_FAIL"


@pytest.mark.parametrize(
    ("lo", "hi", "expected"),
    [
        (1e-12, 0.02, "IMPROVED"),  # IMPROVED takes precedence over EQUIVALENT
        (0.0, 0.049, "EQUIVALENT"),
        (-0.049, 0.049, "EQUIVALENT"),
        (-0.05, 0.02, "INCONCLUSIVE"),  # lo must be strictly above -0.05
        (-0.02, 0.05, "INCONCLUSIVE"),  # hi must be strictly below 0.05
        (-0.3, -1e-12, "WORSE"),
        (-0.04, -0.01, "EQUIVALENT"),  # EQUIVALENT takes precedence over WORSE
        (-0.3, 0.0, "INCONCLUSIVE"),
    ],
)
def test_co_primary_verdict_boundaries(lo, hi, expected):
    assert co_primary_verdict(lo, hi) == expected
