from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.blocksworld import BlocksworldAction, parse_blocksworld
from examples.planning_benchmark_slice.experts.graphplan import (
    GRAPHPLAN_APPROXIMATION_ID,
    action_mutex_pairs,
    build_graphplan_layers,
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


def test_graphplan_generator_creates_valid_solving_trajectory(tmp_path: Path) -> None:
    output = tmp_path / "experts"
    payload = generate_experts(
        fixture_path=NONTRIVIAL_FIXTURE,
        algorithms=("graphplan",),
        output_dir=output,
    )

    assert payload["valid"] is True
    assert payload["algorithms"]["graphplan"]["trajectory_count"] == 1
    assert payload["algorithms"]["graphplan"]["selected_actions"] == ["pickup(a)", "stack(a,b)"]
    assert payload["algorithms"]["graphplan"]["layer_count"] > 0
    assert payload["algorithms"]["graphplan"]["mutex_pair_count"] > 0
    assert payload["algorithms"]["graphplan"]["goal_present_without_mutex"] == [True, True]

    validation = validate_path(output)
    assert validation["valid"] is True
    assert validation["by_algorithm"] == {"graphplan": 2}
    assert validation["trajectory_count"] == 2

    steps = _load_steps(output / "blocksworld-dev-fixture-0000__graphplan.json")
    for step in steps:
        graphplan = step["graphplan"]
        assert graphplan["proposition_layers"]
        assert graphplan["action_layers"]
        assert graphplan["mutex_pairs"]
        assert graphplan["extraction"]["approximation"] == GRAPHPLAN_APPROXIMATION_ID
        assert graphplan["extraction"]["mutex_scope"] == "action_level_only"
        assert graphplan["extraction"]["proposition_mutex_computed"] is False


def test_graphplan_layers_record_initial_actions_next_layer_and_goal_status() -> None:
    problem = _load_problem()
    graph = build_graphplan_layers(problem, problem.initial_state())
    payload = graph.to_payload()

    assert payload["proposition_layers"][0]["atoms"] == sorted(problem.initial_state())
    assert payload["action_layers"][0]["actions"] == ["pickup(a)", "pickup(b)", "pickup(c)"]
    assert payload["action_layers"][0]["next_layer_index"] == 1
    assert "holding(a)" in payload["proposition_layers"][1]["atoms"]
    assert "holding(b)" in payload["proposition_layers"][1]["atoms"]
    assert "holding(c)" in payload["proposition_layers"][1]["atoms"]
    assert payload["extraction"]["goal_present_without_mutex"] is True
    assert payload["extraction"]["selected_goal_layer"] == 2


def test_action_mutex_pairs_are_recorded() -> None:
    problem = _load_problem()
    graph = build_graphplan_layers(problem, problem.initial_state(), max_layers=1)
    layer_mutex_pairs = graph.action_layers[0]["mutex_pairs"]

    assert ["pickup(a)", "pickup(b)"] in layer_mutex_pairs
    assert ["pickup(a)", "pickup(c)"] in layer_mutex_pairs
    assert ["pickup(b)", "pickup(c)"] in layer_mutex_pairs
    assert graph.mutex_pairs == layer_mutex_pairs

    direct_pairs = [
        [left.serialize(), right.serialize()]
        for left, right in action_mutex_pairs(
            [BlocksworldAction("pickup", ("a",)), BlocksworldAction("pickup", ("b",))]
        )
    ]
    assert direct_pairs == [["pickup(a)", "pickup(b)"]]


def test_graphplan_goal_status_is_true_after_selecting_pickup_a() -> None:
    problem = _load_problem()
    holding_a = problem.transition(problem.initial_state(), BlocksworldAction("pickup", ("a",)))
    graph = build_graphplan_layers(problem, holding_a)
    payload = graph.to_payload()

    assert payload["action_layers"][0]["actions"] == ["putdown(a)", "stack(a,b)", "stack(a,c)"]
    assert ["putdown(a)", "stack(a,b)"] in payload["action_layers"][0]["mutex_pairs"]
    assert "on(a,b)" in payload["proposition_layers"][1]["atoms"]
    assert payload["extraction"]["goal_present_without_mutex"] is True
    assert payload["extraction"]["selected_goal_layer"] == 1


def test_graphplan_cli_writes_schema_valid_json(tmp_path: Path) -> None:
    output = tmp_path / "experts"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "examples.planning_benchmark_slice.generate_experts",
            "--fixture",
            str(NONTRIVIAL_FIXTURE),
            "--algorithms",
            "graphplan",
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
    assert payload["algorithms"]["graphplan"]["record_count"] == 2
    assert payload["algorithms"]["graphplan"]["layer_count"] > 0
    assert payload["algorithms"]["graphplan"]["mutex_pair_count"] > 0
    assert (output / "blocksworld-dev-fixture-0000__graphplan.json").exists()
