"""Admission safety and real background-process lifecycle checks."""

import sys
import time
from pathlib import Path

import pytest

from examples.planning_benchmark_slice import expanded_scheduler as s


def ledger():
    schedule = s.read(s.SCHEDULE)
    return {
        "schedule": schedule,
        "allocations_gpu_hours": schedule["allocations_gpu_hours"].copy(),
        "transfers": [],
        "attempts": [],
    }


def job(**changes):
    result = dict(
        job_id="test",
        branch="expanded_baseline",
        gpus=[0],
        max_seconds=10,
        total=1,
        command=[sys.executable, "-c", "pass"],
        completion_hook=[sys.executable, "-c", "pass"],
    )
    result.update(changes)
    return result


def test_admission_caps_ports_and_duplicates():
    state = ledger()
    now = s.timestamp(state["schedule"]["start_utc"])
    first = s.admit(state, job(), now)
    state["attempts"].append(first)
    with pytest.raises(ValueError, match="duplicate"):
        s.admit(state, job(), now)
    with pytest.raises(ValueError, match="GPU already"):
        s.admit(state, job(job_id="other"), now)
    second = s.admit(state, job(job_id="other", gpus=[1]), now)
    assert first["master_port"] != second["master_port"]
    with pytest.raises(ValueError, match="branch"):
        s.admit(ledger(), job(max_seconds=57 * 3600), now)
    state = ledger()
    state["allocations_gpu_hours"]["expanded_baseline"] = 500
    with pytest.raises(ValueError, match="total"):
        s.admit(state, job(max_seconds=169 * 3600, gpus=[0, 1]), now - 3600 * 24)
    with pytest.raises(ValueError, match="cutoff"):
        s.admit(ledger(), job(), s.timestamp(state["schedule"]["gpu_cutoff_utc"]) - 1)


def test_resume_preserves_cost_and_success_is_not_repeated():
    state = ledger()
    first = dict(job(), status="failed", gpu_hours=55.999, master_port=18800)
    state["attempts"].append(first)
    now = s.timestamp(state["schedule"]["start_utc"])
    with pytest.raises(ValueError, match="resume_reason"):
        s.admit(state, job(), now)
    with pytest.raises(ValueError, match="ceiling"):
        s.admit(state, job(resume_reason="technical retry"), now)
    first["status"] = "succeeded"
    with pytest.raises(ValueError, match="duplicate"):
        s.admit(state, job(resume_reason="retry"), now)


def wait_terminal(path, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists():
            return s.read(path)
        time.sleep(0.05)
    pytest.fail(f"missing terminal evidence: {path}")


def test_background_exit_hook_and_resume(tmp_path):
    path = tmp_path / "budget.json"
    schedule = s.read(s.SCHEDULE)
    hook = [sys.executable, "-c", "import os; assert os.environ['CUDA_VISIBLE_DEVICES'] == ''; print('audited')"]
    first = s.launch(path, schedule, job(gpus=[], completion_hook=hook))
    folder = Path(first["directory"])
    terminal = wait_terminal(folder / "terminal.json")
    assert terminal["status"] == "succeeded"
    assert terminal["gpu_hours"] == 0
    assert terminal["cpu_seconds"] >= 0
    assert wait_terminal(folder / "hook-result.json")["returncode"] == 0
    with pytest.raises(ValueError, match="duplicate"):
        s.launch(path, schedule, job(gpus=[]))
    failed = s.launch(
        path, schedule, job(job_id="failure", gpus=[], command=[sys.executable, "-c", "raise RuntimeError('expected')"])
    )
    assert wait_terminal(Path(failed["directory"]) / "terminal.json")["status"] == "failed"
    resumed = s.launch(path, schedule, job(job_id="failure", gpus=[], resume_reason="corrected technical error"))
    assert resumed["attempt"] == 2
    assert wait_terminal(Path(resumed["directory"]) / "terminal.json")["status"] == "succeeded"
    assert len(s.read(path)["attempts"]) == 3


def test_launch_persists_repository_head_before_worker_starts(tmp_path, monkeypatch):
    path = tmp_path / "budget.json"
    expected = "a" * 40
    monkeypatch.setattr(s, "repository_head", lambda: expected)
    attempt = s.launch(path, s.read(s.SCHEDULE), job(gpus=[]))
    assert attempt["launch_head"] == expected
    assert s.read(path)["attempts"][0]["launch_head"] == expected
    terminal = wait_terminal(Path(attempt["directory"]) / "terminal.json")
    assert terminal["launch_head"] == expected


def test_runtime_cutoff_kills_worker(tmp_path):
    path = tmp_path / "budget.json"
    attempt = s.launch(
        path,
        s.read(s.SCHEDULE),
        job(gpus=[], max_seconds=1.5, command=[sys.executable, "-c", "import time; time.sleep(60)"]),
    )
    terminal = wait_terminal(Path(attempt["directory"]) / "terminal.json")
    assert terminal["status"] == "cutoff"
    assert not s.alive(terminal["worker"])
    assert terminal["elapsed_seconds"] < 4


def test_reconcile_does_not_release_live_handle(tmp_path):
    path = tmp_path / "budget.json"
    state = ledger()
    state["attempts"] = [
        dict(job(), status="running", supervisor=s.handle(__import__("os").getpid()), master_port=18800)
    ]
    s.write(path, state)
    assert s.reconcile(path, state["schedule"])["attempts"][0]["status"] == "running"
    state["attempts"][0]["worker"] = state["attempts"][0].pop("supervisor")
    s.write(path, state)
    with pytest.raises(ValueError, match="orphan worker still live"):
        s.reconcile(path, state["schedule"])


def test_transfers_preserve_total_and_committed_cost(tmp_path):
    path = tmp_path / "budget.json"
    schedule = s.read(s.SCHEDULE)
    state = s.transfer(path, schedule, "recovery_reserve", "expanded_baseline", 2, "bounded technical recovery")
    assert sum(state["allocations_gpu_hours"].values()) == 336
    assert state["allocations_gpu_hours"]["expanded_baseline"] == 58
    assert state["transfers"][0]["reason"] == "bounded technical recovery"
    with pytest.raises(ValueError, match="spent or reserved"):
        s.transfer(path, schedule, "recovery_reserve", "expanded_baseline", 23, "too much")


def test_supervisor_crash_worker_times_out_without_relaunch(tmp_path):
    import os
    import signal

    path = tmp_path / "budget.json"
    schedule = s.read(s.SCHEDULE)
    attempt = s.launch(
        path, schedule, job(gpus=[], max_seconds=2, command=[sys.executable, "-c", "import time; time.sleep(60)"])
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        current = s.read(path)["attempts"][0]
        if current.get("worker"):
            break
        time.sleep(0.02)
    else:
        pytest.fail("worker not launched")
    os.kill(attempt["supervisor"]["pid"], signal.SIGKILL)
    time.sleep(0.1)
    with pytest.raises(ValueError, match="orphan worker still live"):
        s.reconcile(path, schedule)
    while time.monotonic() < deadline and s.group_alive(current["worker"]["pid"]):
        time.sleep(0.05)
    assert not s.group_alive(current["worker"]["pid"])
    reconciled = s.reconcile(path, schedule)
    assert reconciled["attempts"][0]["status"] == "interrupted"
    assert reconciled["attempts"][0]["accounting"] == "conservative elapsed until verified dead"


def test_two_gpu_reservation_and_occupied_ports():
    import socket

    state = ledger()
    now = s.timestamp(state["schedule"]["start_utc"])
    with socket.socket() as sock:
        sock.bind(("", state["schedule"]["master_port_pool"][0]))
        attempt = s.admit(state, job(gpus=[0, 1], max_seconds=3600), now)
        assert attempt["master_port"] != sock.getsockname()[1]
    assert s.charged(attempt) == 2
    state["attempts"].append(attempt)
    for gpu in (0, 1):
        with pytest.raises(ValueError, match="GPU already reserved"):
            s.admit(state, job(job_id="other", gpus=[gpu]), now)


def test_cpu_handoff_and_immutable_schedule(tmp_path):
    state = ledger()
    now = s.timestamp(state["schedule"]["gpu_cutoff_utc"])
    assert s.admit(state, job(gpus=[]), now)["master_port"] is None
    with pytest.raises(ValueError, match="handoff"):
        s.admit(state, job(gpus=[]), s.timestamp(state["schedule"]["handoff_deadline_utc"]))
    path = tmp_path / "budget.json"
    s.write(path, state)
    changed = dict(state["schedule"], start_utc="2026-09-15T11:55:19Z")
    with pytest.raises(ValueError, match="clock cannot reset"):
        with s.locked(path, changed):
            pass


def test_concurrent_duplicate_launch_is_atomic(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "budget.json"

    def run():
        try:
            return s.launch(path, s.read(s.SCHEDULE), job(gpus=[]))
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert "duplicate launch refused" in results
    attempt = next(r for r in results if isinstance(r, dict))
    assert wait_terminal(Path(attempt["directory"]) / "terminal.json")["status"] == "succeeded"
    assert len(s.read(path)["attempts"]) == 1


def test_gpu_ledger_cannot_be_forked(tmp_path):
    with pytest.raises(ValueError, match="shared production ledger"):
        s.launch(tmp_path / "budget.json", s.read(s.SCHEDULE), job())
    assert not (tmp_path / "budget.json").exists()


def test_internal_worker_cannot_restart_terminal_attempt(tmp_path):
    path = tmp_path / "budget.json"
    state = ledger()
    state["attempts"] = [dict(job(), attempt=1, status="succeeded", gpu_hours=1)]
    s.write(path, state)
    with pytest.raises(ValueError, match="duplicate or unowned"):
        s.supervise(path, "test", 1)
    assert s.read(path) == state
