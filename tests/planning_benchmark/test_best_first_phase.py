from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

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
    assert phase.authorization["gate_receipt"]["receipt_id"] == ("gate:issue-63-best-first-paired-v2:PASS")
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
        [
            sys.executable,
            str(ROOT / "scripts/qualify_best_first_paired_panel.py"),
            "--dry-run",
            "--workers",
            "3",
        ],
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
        "workers": 3,
        "writes": 0,
    }


def test_parallel_qualification_publishes_each_job_once_in_canonical_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import qualify_best_first_paired_panel as command

    phase = SimpleNamespace(
        authorization={
            "authorization_id": "fixture-authorization",
            "gate_receipt": {"receipt_id": "fixture-gate"},
        },
        pairs=tuple(range(75)),
        phase_id="fixture-parallel-phase",
    )
    jobs = [
        {
            "algorithm": "best_first_add_w2" if index % 2 == 0 else "best_first_add_greedy",
            "difficulty": "easy",
            "domain_id": "fixture",
            "instance_id": f"fixture-{index:03d}",
            "max_decisions": 55_000,
            "max_expansions": 15_000,
            "pair_id": f"pair-{index // 2:03d}",
            "split": "dev",
            "task_path": f"fixture-{index:03d}.json",
            "task_sha256": "fixture",
        }
        for index in range(150)
    ]
    lock = threading.Lock()
    active = 0
    maximum_active = 0
    calls: list[int] = []

    def run_job(job, *, index, total, started, memory_limit_mib, progress_interval_seconds):
        del total, started, progress_interval_seconds
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.002)
        with lock:
            active -= 1
            calls.append(index)
        return {
            **job,
            "decision_count": 1,
            "expansion_count": 1,
            "job_index": index,
            "memory_limit_mib": memory_limit_mib,
            "peak_memory_mib": 1.0,
            "reopen_count": 0,
            "runtime_seconds": 0.002,
            "schema_version": "best_first_qualification_measurement_v1",
            "solution_cost": 1,
            "termination": "goal_reached",
            "visited_count": 2,
        }

    monkeypatch.setattr(command, "load_best_first_phase", lambda *args, **kwargs: phase)
    monkeypatch.setattr(command, "qualification_jobs", lambda selected: tuple(jobs))
    monkeypatch.setattr(command, "_run_job", run_job)

    assert command.main(["--output-root", str(tmp_path), "--workers", "4"]) == 0
    manifest = json.loads((tmp_path / "qualification.json").read_bytes())

    assert maximum_active == 4
    assert sorted(calls) == list(range(150))
    assert [row["job_index"] for row in manifest["measurements"]] == list(range(150))

    stopped = dict(manifest["measurements"][0])
    stopped.update(
        {
            "decision_count": 55_000,
            "solution_cost": None,
            "termination": "decision_budget",
        }
    )
    (tmp_path / "measurements/000-best_first_add_w2.json").write_bytes(command._canonical_bytes(stopped))
    measurements = [stopped, *manifest["measurements"][1:]]
    (tmp_path / "qualification.json").write_bytes(
        command._canonical_bytes(command._manifest(measurements, phase.phase_id, 2048))
    )
    (tmp_path / "qualification-receipt.json").write_bytes(
        command._canonical_bytes(command._qualification_receipt(phase, measurements))
    )

    assert command.main(["--output-root", str(tmp_path), "--check"]) == 0


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
