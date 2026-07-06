from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.blocksworld import BlocksworldAction, parse_blocksworld
from examples.planning_benchmark_slice.experts.fast_forward import (
    FAST_FORWARD_TIE_BREAK_RULE,
    P0_APPROXIMATION_ID,
    build_fast_forward_step_record,
    rank_legal_successors,
    relaxed_plan_heuristic,
    select_fast_forward_action,
)
from examples.planning_benchmark_slice.generate_experts import generate_experts
from examples.planning_benchmark_slice.trajectory_schema import validate_path
from examples.planning_benchmark_slice.validate_instance import load_fixture


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "planning"
NONTRIVIAL_FIXTURE = FIXTURE_DIR / "blocksworld_nontrivial.json"


def _load_problem():
    fixture = load_fixture(NONTRIVIAL_FIXTURE)
    return parse_blocksworld(fixture.domain_pddl, fixture.problem_pddl)


def _load_steps(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload["steps"])


def test_fast_forward_generator_creates_valid_solving_trajectory(tmp_path: Path) -> None:
    output = tmp_path / "experts"
    payload = generate_experts(
        fixture_path=NONTRIVIAL_FIXTURE,
        algorithms=("fast_forward",),
        output_dir=output,
    )

    assert payload["valid"] is True
    assert payload["algorithms"]["fast_forward"]["trajectory_count"] == 1
    assert payload["algorithms"]["fast_forward"]["selected_actions"] == ["pickup(a)", "stack(a,b)"]

    validation = validate_path(output)
    assert validation["valid"] is True
    assert validation["by_algorithm"] == {"fast_forward": 2}
    assert validation["trajectory_count"] == 2

    steps = _load_steps(output / "blocksworld-dev-fixture-0000__fast_forward.json")
    for step in steps:
        fast_forward = step["fast_forward"]
        assert fast_forward["successor_heuristics"]
        assert fast_forward["selected_successor_id"]
        assert fast_forward["selected_action"] == step["selected_action"]
        assert isinstance(fast_forward["heuristic_value"], int)
        assert fast_forward["tie_break_rule"] == FAST_FORWARD_TIE_BREAK_RULE
        assert fast_forward["relaxed_plan_metadata"]["approximation"] == P0_APPROXIMATION_ID
        assert fast_forward["relaxed_plan_metadata"]["is_exact_ff_delete_relaxation"] is False


def test_fast_forward_heuristic_values_are_deterministic_for_three_fixture_states() -> None:
    problem = _load_problem()
    initial = problem.initial_state()
    holding_a = problem.transition(initial, BlocksworldAction("pickup", ("a",)))
    solved = problem.transition(holding_a, BlocksworldAction("stack", ("a", "b")))
    holding_b = problem.transition(initial, BlocksworldAction("pickup", ("b",)))

    assert relaxed_plan_heuristic(problem, initial).heuristic_value == 2
    assert relaxed_plan_heuristic(problem, holding_a).heuristic_value == 1
    assert relaxed_plan_heuristic(problem, solved).heuristic_value == 0
    assert relaxed_plan_heuristic(problem, holding_b).heuristic_value == 3

    repeat_values = [relaxed_plan_heuristic(problem, initial).heuristic_value for _ in range(3)]
    assert repeat_values == [2, 2, 2]


def test_fast_forward_step_records_all_successor_heuristics() -> None:
    problem = _load_problem()
    step = build_fast_forward_step_record(
        problem=problem,
        instance_id="blocksworld-dev-fixture-0000",
        fixture_path=NONTRIVIAL_FIXTURE,
        state=problem.initial_state(),
        step_index=0,
    )
    fast_forward = step["fast_forward"]

    assert fast_forward["heuristic_value"] == 2
    assert fast_forward["failure_reason"] is None
    assert fast_forward["selected_action"] == "pickup(a)"
    assert step["selected_action"] == "pickup(a)"

    successor_values = {
        successor["action"]: successor["heuristic_value"]
        for successor in fast_forward["successor_heuristics"]
    }
    assert successor_values == {"pickup(a)": 1, "pickup(b)": 3, "pickup(c)": 3}


def test_fast_forward_tie_break_is_stable() -> None:
    problem = _load_problem()
    holding_b = problem.transition(problem.initial_state(), BlocksworldAction("pickup", ("b",)))

    ranked = rank_legal_successors(problem, holding_b)
    ranked_actions = [action.serialize() for _, action, _ in ranked]
    ranked_values = [heuristic.heuristic_value for heuristic, _, _ in ranked]

    assert ranked_values[:2] == [2, 2]
    assert ranked_actions[:2] == ["putdown(b)", "stack(b,c)"]
    assert select_fast_forward_action(problem, holding_b).serialize() == "putdown(b)"

    repeated = [select_fast_forward_action(problem, holding_b).serialize() for _ in range(5)]
    assert repeated == ["putdown(b)"] * 5


def test_fast_forward_cli_writes_schema_valid_json(tmp_path: Path) -> None:
    output = tmp_path / "experts"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "examples.planning_benchmark_slice.generate_experts",
            "--fixture",
            str(NONTRIVIAL_FIXTURE),
            "--algorithms",
            "fast_forward",
            "--output",
            str(output),
            "--json",
        ],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert result.stderr == ""
    assert payload["valid"] is True
    assert payload["algorithms"]["fast_forward"]["record_count"] == 2
    assert (output / "blocksworld-dev-fixture-0000__fast_forward.json").exists()
