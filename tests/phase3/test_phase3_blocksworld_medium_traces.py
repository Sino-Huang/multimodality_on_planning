from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.phase3.local_planner_types import LocalPlannerRequest
from scripts.phase3.local_planners import run_local_planner
from scripts.phase3.pddl import GroundAction, PDDLTask, ground_actions, parse_task, replay_plan
from scripts.phase3.pipeline import generate_supervised_data

BLOCKSWORLD_MEDIUM_0011 = Path("data/curriculum_pddl/blocksworld/train/medium/blocksworld-train-medium-0011")
BLOCKSWORLD_MEDIUM_0011_ID = "blocksworld-train-medium-0011"


def test_blocksworld_medium_0011_iw_width_three_succeeds_after_width_one_two_fail() -> None:
    task, grounded = _blocksworld_medium_0011_task()

    width_one = run_local_planner(LocalPlannerRequest(planner="iw", task=task, grounded=tuple(grounded), limits={**_blocksworld_medium_limits(), "local_iw_width": 1}))
    width_two = run_local_planner(LocalPlannerRequest(planner="iw", task=task, grounded=tuple(grounded), limits={**_blocksworld_medium_limits(), "local_iw_width": 2}))
    width_three = run_local_planner(LocalPlannerRequest(planner="iw", task=task, grounded=tuple(grounded), limits={**_blocksworld_medium_limits(), "local_iw_width": 3}))

    assert width_one.status != "success_full_trace"
    assert width_two.status != "success_full_trace"
    assert width_three.status == "success_full_trace"
    assert width_three.trace["algorithm"] == "iterated_width"
    assert width_three.trace["width"] == 3
    assert len(width_three.plan) == 10
    replay = replay_plan(task, width_three.plan, grounded_actions=grounded)
    assert replay["replay_ok"] is True
    assert replay["goal_satisfied"] is True


def test_blocksworld_medium_0011_ff_style_recovers_from_local_dead_end() -> None:
    task, grounded = _blocksworld_medium_0011_task()

    result = run_local_planner(LocalPlannerRequest(planner="ff", task=task, grounded=tuple(grounded), limits=_blocksworld_medium_limits()))

    assert result.status == "success_full_trace"
    assert len(result.plan) == 10
    assert result.trace["planner_source"] == "local_delete_relaxed_hmax_supporter_closure"
    assert result.trace["steps"]
    first_step = result.trace["steps"][0]
    assert first_step["relaxation_metadata"]["is_exact_fast_downward_ff"] is False
    replay = replay_plan(task, result.plan, grounded_actions=grounded)
    assert replay["replay_ok"] is True
    assert replay["goal_satisfied"] is True


def test_blocksworld_medium_0011_graphplan_requires_configured_high_expansion_cap() -> None:
    task, grounded = _blocksworld_medium_0011_task()

    default_cap = run_local_planner(LocalPlannerRequest(planner="graphplan", task=task, grounded=tuple(grounded), limits={**_blocksworld_medium_limits(), "local_graphplan_max_expansions": 5000}))
    high_cap = run_local_planner(LocalPlannerRequest(planner="graphplan", task=task, grounded=tuple(grounded), limits={**_blocksworld_medium_limits(), "local_graphplan_max_expansions": 100000}))

    assert default_cap.status == "skipped_resource_limit"
    assert high_cap.status == "success_full_trace"
    assert len(high_cap.plan) == 10
    replay = replay_plan(task, high_cap.plan, grounded_actions=grounded)
    assert replay["replay_ok"] is True
    assert replay["goal_satisfied"] is True


def test_blocksworld_medium_0011_all_local_planners_emit_pipeline_examples(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_blocksworld_medium_0011_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = fixture_root / "input"
    output_root = fixture_root / "phase3"
    _write_blocksworld_medium_0011_manifest(input_root)

    try:
        summary = generate_supervised_data(
            input_root,
            output_root,
            planners=("bfs", "ff", "iw", "graphplan"),
            limits={**_blocksworld_medium_limits(), "local_iw_width": 3, "local_graphplan_max_expansions": 100000},
        )["summary"]

        assert summary["planner_status_summary"] == {
            "bfs": {"success_full_trace": 1},
            "ff": {"success_full_trace": 1},
            "graphplan": {"success_full_trace": 1},
            "iw": {"success_full_trace": 1},
        }
        rows = [json.loads(line) for line in (output_root / "train.jsonl").read_text(encoding="utf-8").splitlines() if line]
        assert {row["planner"] for row in rows} == {"bfs", "ff", "iw", "graphplan"}
        for row in rows:
            assert row["trace_fidelity"] == "success_full_trace"
            assert row["supervised_target"]["plan"]
            assert row["supervised_target"]["planner_trace"]
    finally:
        shutil.rmtree(fixture_root)


def test_blocksworld_medium_0011_curriculum_trace_cli_defaults_emit_all_planner_traces(tmp_path: Path) -> None:
    output_root = Path("tmp") / f"phase3_blocksworld_medium_0011_cli_{tmp_path.name}"
    if output_root.exists():
        shutil.rmtree(output_root)

    try:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/phase3/generate_curriculum_trace_dataset.py",
                "--instance-id",
                BLOCKSWORLD_MEDIUM_0011_ID,
                "--planner",
                "bfs",
                "--planner",
                "ff",
                "--planner",
                "iw",
                "--planner",
                "graphplan",
                "--output-root",
                output_root.as_posix(),
                "--quiet",
            ],
            check=True,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
        )

        summary = json.loads(result.stdout)
        trace_root = output_root / "traces" / "blocksworld" / "train" / BLOCKSWORLD_MEDIUM_0011_ID
        assert summary["attempt_status_summary"] == {"success_full_trace": 4}
        assert summary["extracted_trace_count"] == 4
        assert {path.name for path in trace_root.glob("*.planner_trace.json")} == {
            "bfs.planner_trace.json",
            "ff.planner_trace.json",
            "graphplan.planner_trace.json",
            "iw.planner_trace.json",
        }
    finally:
        if output_root.exists():
            shutil.rmtree(output_root)


def _blocksworld_medium_limits() -> dict[str, int]:
    return {
        "bfs_max_expansions": 50000,
        "max_grounded_actions": 100000,
        "max_grounded_atoms": 100000,
        "max_jsonl_target_chars": 10000000,
        "max_plan_length": 500,
        "max_trace_steps": 500,
        "local_max_applicable_actions": 2000,
        "local_max_mutex_pairs": 1000000,
    }


def _blocksworld_medium_0011_task() -> tuple[PDDLTask, list[GroundAction]]:
    task = parse_task(BLOCKSWORLD_MEDIUM_0011 / "domain.pddl", BLOCKSWORLD_MEDIUM_0011 / "problem.pddl")
    grounded, status = ground_actions(task, max_grounded_actions=100000, max_grounded_atoms=100000)
    assert status is None
    return task, grounded


def _write_blocksworld_medium_0011_manifest(input_root: Path) -> None:
    input_root.mkdir(parents=True, exist_ok=True)
    manifest_path = Path("data/curriculum_pddl/accepted_manifest.jsonl")
    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line]
    selected = next(row for row in rows if row["instance_id"] == BLOCKSWORLD_MEDIUM_0011_ID)
    (input_root / "accepted_manifest.jsonl").write_text(json.dumps(selected, sort_keys=True) + "\n", encoding="utf-8")
