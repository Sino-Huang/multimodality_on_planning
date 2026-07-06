from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.phase3.local_planner_types import LocalPlannerRequest
from scripts.phase3.local_planners import run_local_planner
from scripts.phase3.pddl import GroundAction, PDDLTask, ground_actions, parse_task, replay_plan
from scripts.phase3.pipeline import RESOURCE_LIMITS, _bfs, _bfs_estimate_exceeds_resource_gate, generate_supervised_data

PUZZLE_EASY_0000 = Path("data/curriculum_pddl/15puzzle/dev/easy/15puzzle-dev-easy-0000")
PUZZLE_EASY_0000_ID = "15puzzle-dev-easy-0000"
PUZZLE_EASY_0002_ID = "15puzzle-dev-easy-0002"


def test_15puzzle_easy_0000_bfs_gate_uses_typed_grounding_estimate() -> None:
    task, grounded = _puzzle_easy_0000_task()

    assert len(task.objects_by_type["object"]) == 17
    assert len(task.objects_by_type["position"]) == 9
    assert len(task.objects_by_type["tile"]) == 8
    assert len(task.goal) == 8
    assert len(grounded) == 648
    assert _bfs_estimate_exceeds_resource_gate(task) is False


@pytest.mark.parametrize("instance_id", [PUZZLE_EASY_0000_ID, PUZZLE_EASY_0002_ID])
def test_15puzzle_easy_local_planners_emit_replay_valid_plans(instance_id: str) -> None:
    task, grounded = _puzzle_easy_task(instance_id)
    limits = _puzzle_easy_limits()

    bfs_plan, bfs_trace, bfs_status = _bfs(task, grounded, limits=limits)
    planner_results = {
        "bfs": (bfs_plan, bfs_trace, bfs_status),
        "ff": _local_planner_result("ff", task, grounded, limits),
        "iw": _local_planner_result("iw", task, grounded, limits),
        "graphplan": _local_planner_result("graphplan", task, grounded, limits),
    }

    for planner, (plan, trace, status) in planner_results.items():
        replay = replay_plan(task, plan, grounded_actions=grounded)
        assert status == "success_full_trace", planner
        assert plan, planner
        assert replay["replay_ok"] is True, planner
        assert replay["goal_satisfied"] is True, planner
        assert trace["algorithm"], planner

    assert planner_results["iw"][1]["plan_recovery"]["is_exact_iw"] is False
    assert planner_results["ff"][1]["plan_recovery"]["is_exact_fast_downward_ff"] is False


def test_15puzzle_easy_first_ten_curriculum_trace_cli_defaults_emit_all_planner_traces(tmp_path: Path) -> None:
    output_root = Path("tmp") / f"phase3_15puzzle_easy_first_ten_cli_{tmp_path.name}"
    if output_root.exists():
        shutil.rmtree(output_root)

    try:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/phase3/generate_curriculum_trace_dataset.py",
                "--instance-id",
                PUZZLE_EASY_0000_ID,
                "--instance-id",
                "15puzzle-dev-easy-0001",
                "--instance-id",
                PUZZLE_EASY_0002_ID,
                "--instance-id",
                "15puzzle-dev-easy-0003",
                "--instance-id",
                "15puzzle-dev-easy-0004",
                "--instance-id",
                "15puzzle-dev-easy-0005",
                "--instance-id",
                "15puzzle-dev-easy-0006",
                "--instance-id",
                "15puzzle-dev-easy-0007",
                "--instance-id",
                "15puzzle-dev-easy-0008",
                "--instance-id",
                "15puzzle-dev-easy-0009",
                "--planner",
                "bfs",
                "--planner",
                "ff",
                "--planner",
                "iw",
                "--planner",
                "graphplan",
                "--local-ff-best-first-max-expansions",
                "500",
                "--local-iw-novelty-max-expansions",
                "500",
                "--output-root",
                output_root.as_posix(),
                "--quiet",
            ],
            check=True,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=2400,
        )

        summary = json.loads(result.stdout)
        assert summary["attempt_status_summary"] == {"success_full_trace": 40}
        assert summary["extracted_trace_count"] == 40
        for index in range(10):
            trace_root = output_root / "traces" / "15puzzle" / "dev" / f"15puzzle-dev-easy-{index:04d}"
            assert {path.name for path in trace_root.glob("*.planner_trace.json")} == {
                "bfs.planner_trace.json",
                "ff.planner_trace.json",
                "graphplan.planner_trace.json",
                "iw.planner_trace.json",
            }
    finally:
        if output_root.exists():
            shutil.rmtree(output_root)


def test_15puzzle_easy_0002_pipeline_defaults_emit_all_planner_traces(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_15puzzle_easy_0002_pipeline_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = fixture_root / "input"
    output_root = fixture_root / "phase3"
    _write_single_instance_manifest(input_root, PUZZLE_EASY_0002_ID)

    try:
        summary = generate_supervised_data(input_root, output_root, planners=("bfs", "ff", "iw", "graphplan"))["summary"]

        assert summary["planner_status_summary"] == {
            "bfs": {"success_full_trace": 1},
            "ff": {"success_full_trace": 1},
            "graphplan": {"success_full_trace": 1},
            "iw": {"success_full_trace": 1},
        }
        rows = [json.loads(line) for line in (output_root / "dev.jsonl").read_text(encoding="utf-8").splitlines() if line]
        assert {row["planner"] for row in rows} == {"bfs", "ff", "iw", "graphplan"}
    finally:
        if fixture_root.exists():
            shutil.rmtree(fixture_root)


def _local_planner_result(planner: str, task: PDDLTask, grounded: list[GroundAction], limits: dict[str, int]) -> tuple[list[str], dict[str, object], str]:
    result = run_local_planner(LocalPlannerRequest(planner=planner, task=task, grounded=tuple(grounded), limits=limits))
    return result.plan, result.trace, result.status


def _puzzle_easy_limits() -> dict[str, int]:
    return {
        **RESOURCE_LIMITS,
        "max_jsonl_target_chars": 10000000,
        "local_ff_best_first_max_expansions": 500,
        "local_iw_novelty_max_expansions": 500,
        "local_max_mutex_pairs": 1000000,
    }


def _puzzle_easy_0000_task() -> tuple[PDDLTask, list[GroundAction]]:
    return _puzzle_easy_task(PUZZLE_EASY_0000_ID)


def _puzzle_easy_task(instance_id: str) -> tuple[PDDLTask, list[GroundAction]]:
    root = PUZZLE_EASY_0000.parent / instance_id
    task = parse_task(root / "domain.pddl", root / "problem.pddl")
    grounded, status = ground_actions(task, max_grounded_actions=100000, max_grounded_atoms=100000)
    assert status is None
    return task, grounded


def _write_single_instance_manifest(input_root: Path, instance_id: str) -> None:
    input_root.mkdir(parents=True, exist_ok=True)
    manifest_path = Path("data/curriculum_pddl/accepted_manifest.jsonl")
    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line]
    selected = next(row for row in rows if row["instance_id"] == instance_id)
    (input_root / "accepted_manifest.jsonl").write_text(json.dumps(selected, sort_keys=True) + "\n", encoding="utf-8")
