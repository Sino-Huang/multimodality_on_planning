from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.blocksworld import BlocksworldAction, canonical_atom, parse_blocksworld
from examples.planning_benchmark_slice.validate_instance import InstanceValidationError, validate_fixture


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "planning"
NONTRIVIAL_FIXTURE = FIXTURE_DIR / "blocksworld_nontrivial.json"
EMPTY_GOAL_FIXTURE = FIXTURE_DIR / "blocksworld_empty_goal.json"


def _fixture_payload(path: Path = NONTRIVIAL_FIXTURE) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_fixture(tmp_path: Path, *, domain_pddl: str, problem_pddl: str) -> Path:
    path = tmp_path / "fixture.json"
    path.write_text(
        json.dumps({"domain_pddl": domain_pddl, "problem_pddl": problem_pddl}, indent=2),
        encoding="utf-8",
    )
    return path


def _run_validate(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "examples.planning_benchmark_slice.validate_instance", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def test_parser_extracts_canonical_blocksworld_problem() -> None:
    payload = _fixture_payload()
    problem = parse_blocksworld(payload["domain_pddl"], payload["problem_pddl"])

    assert problem.domain_name == "blocksworld-4ops"
    assert problem.problem_name == "bw-nontrivial-3"
    assert problem.objects == ("a", "b", "c")
    assert problem.action_vocabulary == ("pickup", "putdown", "stack", "unstack")
    assert problem.goal_atoms == frozenset({"on(a,b)"})
    assert sorted(problem.initial_atoms) == [
        "arm-empty",
        "clear(a)",
        "clear(b)",
        "clear(c)",
        "on-table(a)",
        "on-table(b)",
        "on-table(c)",
    ]


def test_state_id_is_stable_and_independent_of_pddl_atom_order() -> None:
    payload = _fixture_payload()
    reordered_problem = """
(define (problem bw-nontrivial-3-reordered)
  (:domain blocksworld-4ops)
  (:objects c a b)
  (:init
    (clear c)
    (on-table b)
    (arm-empty)
    (clear a)
    (on-table c)
    (clear b)
    (on-table a))
  (:goal (and (on a b)))
)
"""

    first = parse_blocksworld(payload["domain_pddl"], payload["problem_pddl"])
    second = parse_blocksworld(payload["domain_pddl"], reordered_problem)

    assert first.initial_atoms == second.initial_atoms
    assert first.state_id(first.initial_atoms) == second.state_id(second.initial_atoms)
    assert first.state_id(first.initial_atoms) == first.state_id(set(reversed(sorted(first.initial_atoms))))


def test_legal_actions_transition_and_goal_check_are_symbolic() -> None:
    payload = _fixture_payload()
    problem = parse_blocksworld(payload["domain_pddl"], payload["problem_pddl"])

    assert problem.legal_action_strings() == ("pickup(a)", "pickup(b)", "pickup(c)")

    holding_a = problem.transition(problem.initial_atoms, BlocksworldAction("pickup", ("a",)))
    assert canonical_atom("holding", "a") in holding_a
    assert canonical_atom("arm-empty") not in holding_a
    assert problem.legal_action_strings(holding_a) == ("putdown(a)", "stack(a,b)", "stack(a,c)")

    goal_state = problem.transition(holding_a, BlocksworldAction("stack", ("a", "b")))
    assert canonical_atom("on", "a", "b") in goal_state
    assert problem.is_goal(goal_state) is True
    assert problem.shortest_plan_length() == 2


def test_validate_instance_accepts_nontrivial_min_plan() -> None:
    payload = validate_fixture(NONTRIVIAL_FIXTURE, min_plan_length=2, require_non_empty_goal=True)

    assert payload["valid"] is True
    assert payload["goal_is_empty"] is False
    assert payload["already_solved"] is False
    assert payload["min_plan_length_satisfied"] is True
    assert payload["shortest_plan_length"] == 2
    assert payload["legal_actions_count"] == 3


def test_validate_instance_cli_emits_json_only_on_success() -> None:
    result = _run_validate(
        "--fixture",
        str(NONTRIVIAL_FIXTURE),
        "--min-plan-length",
        "2",
        "--require-non-empty-goal",
        "--json",
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert result.stderr == ""
    assert payload["valid"] is True
    assert payload["shortest_plan_length"] == 2


def test_empty_goal_is_rejected_with_structured_error() -> None:
    result = _run_validate("--fixture", str(EMPTY_GOAL_FIXTURE), "--require-non-empty-goal", "--json")

    payload = json.loads(result.stdout)

    assert result.returncode != 0
    assert payload["valid"] is False
    assert payload["error"]["code"] == "empty_goal"
    assert "empty_goal" in result.stderr


def test_validation_rejects_missing_action_vocabulary(tmp_path: Path) -> None:
    payload = _fixture_payload()
    fixture = _write_fixture(
        tmp_path,
        domain_pddl=payload["domain_pddl"].replace("(:action unstack", "(:action unstack-missing"),
        problem_pddl=payload["problem_pddl"],
    )

    with pytest.raises(InstanceValidationError) as error:
        validate_fixture(fixture, require_non_empty_goal=True)

    assert error.value.code == "missing_action_vocabulary"


def test_validation_rejects_malformed_pddl(tmp_path: Path) -> None:
    payload = _fixture_payload()
    fixture = _write_fixture(tmp_path, domain_pddl=payload["domain_pddl"], problem_pddl="(define (problem broken)")

    with pytest.raises(InstanceValidationError) as error:
        validate_fixture(fixture)

    assert error.value.code == "malformed_pddl"


def test_validation_rejects_missing_render_artifacts_when_required() -> None:
    with pytest.raises(InstanceValidationError) as error:
        validate_fixture(NONTRIVIAL_FIXTURE, require_render_artifacts=True)

    assert error.value.code == "missing_render_artifacts"


def test_validation_rejects_already_solved_and_below_min_plan(tmp_path: Path) -> None:
    payload = _fixture_payload()
    already_solved_problem = payload["problem_pddl"].replace("(and (on a b))", "(and (clear a))")
    already_solved_fixture = _write_fixture(
        tmp_path,
        domain_pddl=payload["domain_pddl"],
        problem_pddl=already_solved_problem,
    )

    with pytest.raises(InstanceValidationError) as solved_error:
        validate_fixture(already_solved_fixture, require_non_empty_goal=True)
    assert solved_error.value.code == "already_solved"

    with pytest.raises(InstanceValidationError) as short_error:
        validate_fixture(NONTRIVIAL_FIXTURE, min_plan_length=3, require_non_empty_goal=True)
    assert short_error.value.code == "below_min_plan_length"
