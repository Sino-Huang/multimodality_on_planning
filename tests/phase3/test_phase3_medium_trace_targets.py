from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.phase3.pddl import estimate_grounded_action_count, ground_actions, parse_task, replay_plan
from scripts.phase3.pipeline import generate_supervised_data

VISITALL_MEDIUM_0000 = Path("data/curriculum_pddl/visitall/dev/medium/visitall-dev-medium-0000")
VISITALL_MEDIUM_0000_ID = "visitall-dev-medium-0000"
GRIPPER_MEDIUM_0000 = Path("data/curriculum_pddl/gripper/dev/medium/gripper-dev-medium-0000")
GRIPPER_MEDIUM_0000_ID = "gripper-dev-medium-0000"
LOGISTICS_MEDIUM_0000_ID = "logistics-dev-medium-0000"


def test_visitall_medium_0000_typed_grounding_stays_small_for_gbfs() -> None:
    task = parse_task(VISITALL_MEDIUM_0000 / "domain.pddl", VISITALL_MEDIUM_0000 / "problem.pddl")
    grounded, status = ground_actions(task, max_grounded_actions=100000, max_grounded_atoms=100000)

    assert task.unsupported_features == ()
    assert status is None
    assert len(grounded) == 80
    assert estimate_grounded_action_count(task) == len(grounded)
    assert len(grounded) < 2000


def test_gripper_medium_0000_grounding_uses_static_unary_sort_predicates() -> None:
    task = parse_task(GRIPPER_MEDIUM_0000 / "domain.pddl", GRIPPER_MEDIUM_0000 / "problem.pddl")
    grounded, status = ground_actions(task, max_grounded_actions=100000, max_grounded_atoms=100000)

    assert task.unsupported_features == ()
    assert status is None
    assert len(grounded) == 164
    assert estimate_grounded_action_count(task) == len(grounded)


def test_gripper_medium_0000_narrowed_grounding_replays_known_plan() -> None:
    task = parse_task(GRIPPER_MEDIUM_0000 / "domain.pddl", GRIPPER_MEDIUM_0000 / "problem.pddl")
    grounded, status = ground_actions(task, max_grounded_actions=100000, max_grounded_atoms=100000)
    plan: list[str] = []
    balls = sorted(atom[1] for atom in task.goal if atom[0] == "at" and atom[2] == "roomb")
    for index, ball in enumerate(balls):
        plan.extend([f"(pick {ball} rooma left)", "(move rooma roomb)", f"(drop {ball} roomb left)"])
        if index < len(balls) - 1:
            plan.append("(move roomb rooma)")

    assert status is None
    replay = replay_plan(task, plan, grounded_actions=grounded)
    assert replay["replay_ok"] is True
    assert replay["goal_satisfied"] is True


def test_gripper_medium_0000_pipeline_defaults_emit_all_planner_traces(tmp_path: Path) -> None:
    _assert_pipeline_defaults_emit_all_planner_traces(tmp_path, GRIPPER_MEDIUM_0000_ID)


def test_visitall_medium_0000_pipeline_defaults_emit_all_planner_traces(tmp_path: Path) -> None:
    _assert_pipeline_defaults_emit_all_planner_traces(tmp_path, VISITALL_MEDIUM_0000_ID)


def test_logistics_medium_0000_pipeline_defaults_emit_all_planner_traces(tmp_path: Path) -> None:
    _assert_pipeline_defaults_emit_all_planner_traces(tmp_path, LOGISTICS_MEDIUM_0000_ID)


def _assert_pipeline_defaults_emit_all_planner_traces(tmp_path: Path, instance_id: str) -> None:
    fixture_root = Path("tmp") / f"phase3_medium_target_{instance_id}_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = fixture_root / "input"
    output_root = fixture_root / "phase3"
    _write_single_instance_manifest(input_root, instance_id)

    try:
        summary = generate_supervised_data(input_root, output_root, planners=("gbfs", "ff", "iw", "graphplan"))["summary"]

        assert summary["planner_status_summary"] == {
            "gbfs": {"success_full_trace": 1},
            "ff": {"success_full_trace": 1},
            "graphplan": {"success_full_trace": 1},
            "iw": {"success_full_trace": 1},
        }
        rows = [json.loads(line) for line in (output_root / "dev.jsonl").read_text(encoding="utf-8").splitlines() if line]
        assert {row["planner"] for row in rows} == {"gbfs", "ff", "iw", "graphplan"}
        assert all(row["trace_fidelity"] == "success_full_trace" for row in rows)
    finally:
        shutil.rmtree(fixture_root)


def _write_single_instance_manifest(input_root: Path, instance_id: str) -> None:
    input_root.mkdir(parents=True, exist_ok=True)
    manifest_path = Path("data/curriculum_pddl/accepted_manifest.jsonl")
    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line]
    selected = next(row for row in rows if row["instance_id"] == instance_id)
    (input_root / "accepted_manifest.jsonl").write_text(json.dumps(selected, sort_keys=True) + "\n", encoding="utf-8")
