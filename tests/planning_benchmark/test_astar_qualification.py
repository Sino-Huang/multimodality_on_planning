from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.astar_controller import AStarController, AStarOperation
from examples.planning_benchmark_slice.astar_hmax import HMaxHeuristic
from examples.planning_benchmark_slice.astar_phase import AStarPairedPhaseGate
from examples.planning_benchmark_slice.astar_qualification import run_astar_qualification
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from scripts.qualify_astar_paired_panel import qualification_jobs

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json"
SCRIPT = ROOT / "scripts/qualify_astar_paired_panel.py"


def _authority() -> PDDLStateAuthority:
    task = json.loads(FIXTURE.read_bytes())
    return PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])


def test_eventless_qualification_records_exact_metrics_for_both_adapters() -> None:
    progress: list[dict[str, object]] = []
    results = [
        run_astar_qualification(
            _authority(),
            adapter,
            progress=progress.append,
            progress_interval_seconds=0.0,
        )
        for adapter in ("astar_hmax", "astar_landmark_count")
    ]

    assert [result.termination for result in results] == ["goal_reached", "goal_reached"]
    assert [result.expansion_count for result in results] == [2, 2]
    assert [result.solution_cost for result in results] == [2, 2]
    assert all(result.decision_count == 6 for result in results)
    assert all(result.composite_node_count >= result.world_state_count for result in results)
    assert progress


def test_controller_can_count_decisions_without_retaining_evidence() -> None:
    authority = _authority()
    controller = AStarController(
        authority,
        HMaxHeuristic(authority),
        accepted_delta_limit=16,
        retain_decision_evidence=False,
    )
    node_id = controller.frontier_head_state_id()
    assert node_id is not None
    controller.start_expansion()
    for candidate in controller.expansion_candidates():
        assert controller.apply_operation(AStarOperation(node_id, candidate.action)).accepted
    controller.finish_expansion()

    assert controller.decision_count > 0
    assert controller.decision_evidence() == ()


def test_qualification_jobs_expand_every_fixed_pair_for_both_adapters() -> None:
    pairs = [
        {
            "difficulty": "easy",
            "domain_id": "blocksworld",
            "instance_id": f"instance-{index:03d}",
            "pair_id": f"pair-{index:03d}",
            "split": "train" if index % 2 else "dev",
            "task_path": FIXTURE.relative_to(ROOT).as_posix(),
            "task_sha256": f"{index:064x}",
        }
        for index in range(75)
    ]
    gate = AStarPairedPhaseGate(
        freeze={"phase_id": "issue-62-astar-paired-development-v1"},
        components={"task": {"pairs": pairs}},
        authorization={},
        freeze_manifest_path=ROOT / "freeze.json",
        authorization_manifest_path=ROOT / "authorization.json",
        repo_root=ROOT,
    )

    jobs = qualification_jobs(gate)

    assert len(jobs) == 150
    assert [job["pair_id"] for job in jobs[0:4]] == ["pair-000", "pair-000", "pair-001", "pair-001"]
    assert [job["adapter"] for job in jobs[0:4]] == [
        "astar_hmax",
        "astar_landmark_count",
        "astar_hmax",
        "astar_landmark_count",
    ]


def test_isolated_worker_streams_progress_and_all_required_metrics() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--worker",
            "--worker-task",
            str(FIXTURE),
            "--worker-adapter",
            "astar_landmark_count",
            "--memory-limit-mib",
            "1024",
            "--progress-interval-seconds",
            "0",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    records = [json.loads(line) for line in completed.stdout.splitlines()]
    assert any(record["kind"] == "progress" for record in records)
    result = records[-1]
    assert result["kind"] == "result"
    assert {
        "composite_node_count",
        "decision_count",
        "expansion_count",
        "peak_memory_mib",
        "reopen_count",
        "runtime_seconds",
        "solution_cost",
        "termination",
        "world_state_count",
    } <= result.keys()
    assert result["termination"] == "goal_reached"
