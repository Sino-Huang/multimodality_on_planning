from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.best_first_phase import (
    load_best_first_phase,
    qualification_jobs,
)

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "configs/experiments/best-first-paired-design-v2.json"
AUTHORIZATION = ROOT / "configs/experiments/best-first-paired-authorization-v2.json"


def test_replacement_phase_binds_the_fixed_panel_and_two_scalar_settings() -> None:
    phase = load_best_first_phase(DESIGN, AUTHORIZATION, repo_root=ROOT)
    jobs = qualification_jobs(phase)

    assert phase.phase_id == "issue-63-best-first-paired-v2"
    assert len(phase.pairs) == 75
    assert len(jobs) == 150
    assert {job["algorithm"] for job in jobs} == {
        "best_first_add_w2",
        "best_first_add_greedy",
    }
    assert all(job["max_expansions"] == 15_000 for job in jobs)
    assert all(job["max_decisions"] == 55_000 for job in jobs)


def test_qualification_command_dry_run_checks_authority_without_writes() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/qualify_best_first_paired_panel.py"), "--dry-run"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.splitlines()[-1])
    assert result == {
        "algorithm_count": 2,
        "job_count": 150,
        "memory_limit_mib": 2048,
        "pair_count": 75,
        "phase_id": "issue-63-best-first-paired-v2",
        "status": "authorized_dry_run",
        "writes": 0,
    }


def test_trace_generation_fixture_dry_run_executes_and_replays_both_settings() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/generate_best_first_paired_expert_traces.py"),
            "--fixture-dry-run",
        ],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "fixture_only": True,
        "replayed_trace_count": 2,
        "status": "contract_validation_only",
        "writes": 0,
    }
