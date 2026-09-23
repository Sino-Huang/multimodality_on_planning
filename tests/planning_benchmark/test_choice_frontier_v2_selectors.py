"""Issue #135 selector-ladder contracts: exact-eps endpoints, determinism, hadd-greedy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.best_first_add import AdditiveHeuristic
from examples.planning_benchmark_slice.choice_frontier import ChoiceFrontierModelSession, canonical_choice
from scripts import run_choice_frontier_v2_zoo as zoo

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
ALGORITHMS = ("best_first_add_greedy", "best_first_add_w3")


@pytest.fixture
def row(tmp_path: Path) -> dict:
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps({"domain_pddl": DOMAIN, "problem_pddl": PROBLEM}))
    return {
        "task_id": "choice-frontier-v2/test-bw-tower-4",
        "domain": "blocksworld",
        "task_path": str(task_path),
        "reference_costs": {algorithm: {"decisions": 40, "expansions": 20} for algorithm in ALGORITHMS},
    }


def drive(row: dict, algorithm: str, selector: str, seed: int, check) -> list[str]:
    """Run one capped episode, calling ``check(session, request, state_ref)`` per decision."""

    task = zoo.task_identity(row, algorithm)
    session = ChoiceFrontierModelSession(
        authority=zoo.authority_for(row), task=task, arm="exact_reference", seed=seed, decision_cap=40
    )
    memory = zoo.NoveltyMemory()
    outputs = []
    while (request := session.next_request()) is not None:
        state_ref, _atoms, _evidence = zoo.select_ref(session, selector, memory, request)
        check(session, request, state_ref)
        label = next(entry["choice"] for entry in request.menu_binding if entry["state_ref"] == state_ref)
        outputs.append(canonical_choice(label))
        session.submit_output(outputs[-1])
    return outputs


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_exact_eps_zero_always_selects_the_exact_heap_head(row, algorithm, monkeypatch):
    monkeypatch.setitem(zoo.EPSILONS, "exact-eps-0.25", 0.0)

    def check(session, request, state_ref):
        head = session.controller.frontier_head_state_id()
        assert state_ref == session.controller._state_ref_by_id[head]
        assert session.reference_output() == canonical_choice(
            next(entry["choice"] for entry in request.menu_binding if entry["state_ref"] == state_ref)
        )

    outputs = drive(row, algorithm, "exact-eps-0.25", 17, check)
    assert outputs


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_exact_eps_one_always_selects_a_valid_menu_member(row, algorithm, monkeypatch):
    monkeypatch.setitem(zoo.EPSILONS, "exact-eps-0.75", 1.0)
    decisions = []

    def check(session, request, state_ref):
        assert state_ref in {entry["state_ref"] for entry in request.menu_binding}
        decisions.append(len(request.menu_binding))

    drive(row, algorithm, "exact-eps-0.75", 5077, check)
    assert any(size >= 2 for size in decisions)


@pytest.mark.parametrize("selector", ["exact-eps-0.50", "hadd-greedy"])
def test_same_seed_reproduces_the_choice_sequence(row, selector):
    first = zoo.run_episode(row, "best_first_add_w3", selector, 2, 6131)
    second = zoo.run_episode(row, "best_first_add_w3", selector, 2, 6131)
    assert [e["raw_output"] for e in first["events"]] == [e["raw_output"] for e in second["events"]]
    assert first["result"] == second["result"]


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_hadd_greedy_selects_a_minimum_additive_heuristic_state(row, algorithm):
    heuristic = None

    def check(session, request, state_ref):
        nonlocal heuristic
        heuristic = heuristic or AdditiveHeuristic(session.authority)
        controller = session.controller
        # Independent recomputation of h_add for every menu state, not the stored value.
        values = {
            entry["state_ref"]: heuristic(controller._states_by_ref[entry["state_ref"]])
            for entry in request.menu_binding
        }
        assert values[state_ref] == min(values.values())

    outputs = drive(row, algorithm, "hadd-greedy", 8527, check)
    assert outputs
