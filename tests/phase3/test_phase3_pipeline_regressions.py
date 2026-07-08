from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.phase3 import local_graphplan
from scripts.phase3.local_planner_types import LocalPlannerRequest
from scripts.phase3.local_planners import run_local_planner
from scripts.phase3.pddl import ground_actions, parse_task
from scripts.phase3.pipeline import generate_supervised_data
from tests.phase3.test_phase3_pipeline import _fixture_dataset


def test_generate_supervised_data_rejects_input_root_as_output_root(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_reject_input_root_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    manifest = input_root / "accepted_manifest.jsonl"

    with pytest.raises(RuntimeError, match="unsafe output root"):
        generate_supervised_data(input_root, input_root, planners=("gbfs",))

    assert manifest.exists()
    shutil.rmtree(fixture_root)


def test_generate_supervised_data_rejects_output_root_that_contains_input_root(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_reject_input_parent_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    manifest = input_root / "accepted_manifest.jsonl"

    with pytest.raises(RuntimeError, match="unsafe output root"):
        generate_supervised_data(input_root, fixture_root, planners=("gbfs",))

    assert manifest.exists()
    shutil.rmtree(fixture_root)


def test_generate_supervised_data_uses_configured_external_planner_before_local_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_root = Path("tmp") / f"phase3_external_first_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    output_root = fixture_root / "phase3"
    script = tmp_path / "ff_planner.py"
    script.write_text("#!/usr/bin/env python3\nprint('0: (move a b)')\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PHASE3_FF_PLANNER", str(script))

    summary = generate_supervised_data(input_root, output_root, planners=("ff",))["summary"]

    assert summary["planner_status_summary"] == {"ff": {"success_plan_replayed": 1}}
    row = json.loads((output_root / "train.jsonl").read_text(encoding="utf-8"))
    assert row["trace_fidelity"] == "success_plan_replayed"
    assert row["supervised_target"]["planner_trace"] == {"external_plan_only": True}
    shutil.rmtree(fixture_root)


def test_generate_supervised_data_checks_actual_example_size(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_size_guard_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    output_root = fixture_root / "phase3"

    summary = generate_supervised_data(input_root, output_root, planners=("ff",), limits={"max_jsonl_target_chars": 10})["summary"]
    attempts = [json.loads(line) for line in (output_root / "diagnostics" / "planner_attempts.jsonl").read_text(encoding="utf-8").splitlines() if line]

    assert summary["emitted_examples"] == 0
    assert attempts[0]["status"] == "skipped_resource_limit"
    assert attempts[0]["trace_fidelity"] == "none"
    assert attempts[0]["replay_validation_id"] is None
    assert attempts[0]["plan_hash"] is None
    shutil.rmtree(fixture_root)


def test_generate_supervised_data_records_merged_resource_limits(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_merged_limits_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    output_root = fixture_root / "phase3"

    generate_supervised_data(input_root, output_root, planners=("gbfs",), limits={"max_trace_steps": 1})

    row = json.loads((output_root / "train.jsonl").read_text(encoding="utf-8"))
    replay = json.loads((output_root / "diagnostics" / "replay_validation.jsonl").read_text(encoding="utf-8"))
    assert row["evaluation_metadata"]["generation_config"]["resource_limits"]["max_trace_steps"] == 1
    assert len(replay["transitions"]) == 1
    shutil.rmtree(fixture_root)


def test_fast_forward_trace_records_relaxed_planning_graph_and_selected_relaxed_plan(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_ff_relaxed_trace_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    output_root = fixture_root / "phase3"

    generate_supervised_data(input_root, output_root, planners=("ff",))

    row = json.loads((output_root / "train.jsonl").read_text(encoding="utf-8"))
    trace = row["supervised_target"]["planner_trace"]
    first_step = trace["steps"][0]
    current = first_step["current_heuristic"]
    selected = first_step["selected_successor"]

    assert trace["goal_atoms"]
    assert trace["planner_source"] == "local_delete_relaxed_hmax_supporter_closure"
    assert first_step["relaxation_metadata"] == {
        "ignored_delete_effects": True,
        "approximation": "local_delete_relaxed_hmax_supporter_closure",
        "is_exact_fast_downward_ff": False,
    }
    assert current["heuristic_source"] == "delete_relaxed_planning_graph"
    assert current["heuristic_value"] == current["relaxed_plan"]["length"]
    assert current["relaxed_plan"]["actions"]
    assert current["relaxed_proposition_layers"]
    assert current["relaxed_action_layers"]
    assert selected["action"] == first_step["selected_action"]
    assert selected["heuristic_value"] <= current["heuristic_value"]
    assert selected["relaxed_plan"]["length"] == selected["heuristic_value"]
    assert first_step["successor_heuristics"]
    assert first_step["successor_heuristics"][0]["state_atoms"]
    assert "relaxed_plan_actions" in first_step["successor_heuristics"][0]
    shutil.rmtree(fixture_root)


def test_iw_expands_empty_initial_state_with_zero_precondition_action(tmp_path: Path) -> None:
    domain, problem = _write_empty_init_goal_pddl(tmp_path)
    task = parse_task(domain, problem)
    grounded, status = ground_actions(task, max_grounded_actions=100, max_grounded_atoms=100)

    result = run_local_planner(LocalPlannerRequest(planner="iw", task=task, grounded=tuple(grounded), limits=_limits()))

    assert status is None
    assert result.status == "success_full_trace"
    assert result.plan == ["(make-done)"]


def test_iw_enforces_max_plan_length(tmp_path: Path) -> None:
    domain, problem = _write_empty_init_goal_pddl(tmp_path)
    task = parse_task(domain, problem)
    grounded, _status = ground_actions(task, max_grounded_actions=100, max_grounded_atoms=100)

    result = run_local_planner(LocalPlannerRequest(planner="iw", task=task, grounded=tuple(grounded), limits={**_limits(), "max_plan_length": 0}))

    assert result.status == "skipped_resource_limit"


def test_iw_enforces_applicable_action_cap(tmp_path: Path) -> None:
    domain, problem = _write_multi_zero_action_pddl(tmp_path)
    task = parse_task(domain, problem)
    grounded, _status = ground_actions(task, max_grounded_actions=100, max_grounded_atoms=100)

    result = run_local_planner(LocalPlannerRequest(planner="iw", task=task, grounded=tuple(grounded), limits={**_limits(), "local_max_applicable_actions": 1}))

    assert result.status == "skipped_resource_limit"


def test_iw_rejects_width_below_one(tmp_path: Path) -> None:
    domain, problem = _write_empty_init_goal_pddl(tmp_path)
    task = parse_task(domain, problem)
    grounded, _status = ground_actions(task, max_grounded_actions=100, max_grounded_atoms=100)

    result = run_local_planner(LocalPlannerRequest(planner="iw", task=task, grounded=tuple(grounded), limits={**_limits(), "local_iw_width": 0}))

    assert result.status == "skipped_resource_limit"
    assert result.trace["width"] == 0


def test_graphplan_extraction_enforces_applicable_action_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    domain, problem = _write_multi_zero_action_pddl(tmp_path)
    task = parse_task(domain, problem)
    grounded, _status = ground_actions(task, max_grounded_actions=100, max_grounded_atoms=100)

    def fail_if_extraction_ignores_cap(_action, _state):
        raise AssertionError("graphplan extraction ignored local_max_applicable_actions")

    monkeypatch.setattr(local_graphplan, "_apply", fail_if_extraction_ignores_cap)

    result = run_local_planner(LocalPlannerRequest(planner="graphplan", task=task, grounded=tuple(grounded), limits={**_limits(), "local_max_applicable_actions": 1}))

    assert result.status == "skipped_resource_limit"


def test_graphplan_extraction_uses_graphplan_specific_expansion_cap(tmp_path: Path) -> None:
    domain, problem = _write_multi_zero_action_pddl(tmp_path)
    task = parse_task(domain, problem)
    grounded, _status = ground_actions(task, max_grounded_actions=100, max_grounded_atoms=100)

    result = run_local_planner(LocalPlannerRequest(planner="graphplan", task=task, grounded=tuple(grounded), limits={**_limits(), "local_graphplan_max_expansions": 0}))

    assert result.status == "skipped_resource_limit"


def test_generate_supervised_data_reports_planner_progress(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_progress_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    output_root = fixture_root / "phase3"
    events = []

    generate_supervised_data(input_root, output_root, planners=("gbfs",), progress_callback=events.append)

    assert events[0]["phase"] == "attempt_started"
    assert events[0]["planner"] == "gbfs"
    assert events[1]["phase"] == "attempt_finished"
    assert events[1]["status"] == "success_full_trace"
    shutil.rmtree(fixture_root)


def test_graphplan_full_trace_uses_graphplan_extraction_metadata(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_graphplan_trace_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    output_root = fixture_root / "phase3"

    summary = generate_supervised_data(input_root, output_root, planners=("graphplan",))["summary"]

    row = json.loads((output_root / "train.jsonl").read_text(encoding="utf-8"))
    trace = row["supervised_target"]["planner_trace"]

    assert summary["planner_status_summary"] == {"graphplan": {"success_full_trace": 1}}
    assert trace["algorithm"] == "graphplan"
    assert "proposition_layers" in trace
    assert "action_layers" in trace
    assert "mutex_pairs" in trace
    assert trace["extraction"]["proposition_mutex_computed"] is False
    assert trace["extraction"]["source"] != "local_bfs_backward_extraction_approximation"
    shutil.rmtree(fixture_root)


def _limits() -> dict[str, int]:
    return {"gbfs_max_expansions": 50, "max_plan_length": 5, "max_trace_steps": 10, "local_max_applicable_actions": 2000}


def _write_empty_init_goal_pddl(root: Path) -> tuple[Path, Path]:
    domain = root / "domain.pddl"
    problem = root / "problem.pddl"
    domain.write_text(
        """
(define (domain empty-start)
  (:requirements :strips)
  (:predicates (done))
  (:action make-done
    :parameters ()
    :precondition (and)
    :effect (and (done)))
)
""",
        encoding="utf-8",
    )
    problem.write_text(
        """
(define (problem empty-start-p1)
  (:domain empty-start)
  (:init)
  (:goal (and (done)))
)
""",
        encoding="utf-8",
    )
    return domain, problem


def _write_multi_zero_action_pddl(root: Path) -> tuple[Path, Path]:
    domain = root / "domain.pddl"
    problem = root / "problem.pddl"
    domain.write_text(
        """
(define (domain many-actions)
  (:requirements :strips)
  (:predicates (a) (b))
  (:action make-a
    :parameters ()
    :precondition (and)
    :effect (and (a)))
  (:action make-b
    :parameters ()
    :precondition (and)
    :effect (and (b)))
)
""",
        encoding="utf-8",
    )
    problem.write_text(
        """
(define (problem many-actions-p1)
  (:domain many-actions)
  (:init)
  (:goal (and (a)))
)
""",
        encoding="utf-8",
    )
    return domain, problem
