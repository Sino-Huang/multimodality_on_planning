"""One owner, two GPU workers, cumulative stage clocks and retained attempts."""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .modality_view_preparation import write_json
from .scene_assets import read_json


def process_identity(pid):
    try:
        with open(f"/proc/{pid}/stat") as stream:
            return stream.read().rsplit(")", 1)[1].split()[19]
    except FileNotFoundError:
        return None


class StageBudget:
    def __init__(self, root, study, stage):
        self.root, self.study, self.stage = root, study, stage
        self.output = root / study["output_root"]
        self.path = self.output / "budget.json"
        self.cap = study["budget"][
            {
                "qualify": "qualification_seconds",
                "train": "training_development_seconds",
                "evaluate": "final_evaluation_seconds",
            }[stage]
        ]
        self.lock = None

    def __enter__(self):
        self.output.mkdir(parents=True, exist_ok=True)
        self.lock = (self.output / "gpu-stage.lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise RuntimeError("another matched-study GPU stage is live") from None
        try:
            self.ledger = read_json(self.path) if self.path.exists() else {"study": self.study, "segments": []}
            if self.ledger["study"] != self.study:
                raise ValueError("budget ledger settings differ; no reset or budget borrowing")
            for segment in self.ledger["segments"]:
                if segment.get("ended") is not None:
                    continue
                children = segment.get("children", [])
                if any(c["identity"] is not None and process_identity(c["pid"]) == c["identity"] for c in children):
                    raise RuntimeError("prior owned GPU worker is still live; do not duplicate it")
                finishes = [
                    read_json(self.root / c["status"])["finished"]
                    for c in children
                    if (self.root / c["status"]).exists()
                ]
                segment["ended"] = (
                    max(finishes)
                    if len(finishes) == len(children) and finishes
                    else min(time.time(), segment["hard_deadline"])
                )
                segment["recovered"] = True
                segment["conservative_recovery"] = not children or len(finishes) != len(children)
            spent = sum(s["ended"] - s["started"] for s in self.ledger["segments"] if s["stage"] == self.stage)
            remaining = self.cap - spent
            if remaining <= self.study["budget"]["shutdown_reserve_seconds_per_stage"]:
                write_json(self.path, self.ledger)
                raise RuntimeError("VALID_STOP: cumulative stage allowance exhausted")
            now = time.time()
            self.segment = {
                "stage": self.stage,
                "started": now,
                "ended": None,
                "prior_spent": spent,
                "hard_deadline": now + remaining,
                "children": [],
                "owner": os.getpid(),
            }
            self.ledger["segments"].append(self.segment)
            self.hard = time.monotonic() + remaining
            self.soft = self.hard - self.study["budget"]["shutdown_reserve_seconds_per_stage"]
            self.flush()
            return self
        except BaseException:
            self.lock.close()
            raise

    def flush(self):
        write_json(self.path, self.ledger)

    def __exit__(self, *args):
        self.segment["ended"] = time.time()
        self.flush()
        assert self.lock is not None
        self.lock.close()


def run_gpu_jobs(root, study, stage, jobs, progress, *, resume=False):
    """Jobs are ordered; a modality finishes before the next modality starts."""
    if not jobs:
        return []
    results = []
    with StageBudget(root, study, stage) as clock:
        attempt = root / study["output_root"] / "launches" / f"{stage}-{len(clock.ledger['segments']):03d}"
        attempt.mkdir(parents=True, exist_ok=False)
        active, readers = {}, []
        waiting = list(enumerate(jobs))
        try:
            while waiting or active:
                if time.monotonic() >= clock.hard:
                    raise RuntimeError("VALID_STOP: hard stage deadline")
                for worker, device in enumerate(study["launch"]["devices"]):
                    if worker in active or not waiting or time.monotonic() >= clock.soft:
                        continue
                    index, job = waiting[0]
                    if job.get("assigned_worker", worker) != worker:
                        continue
                    if active and any(x[1].get("modality") != job.get("modality") for x in active.values()):
                        continue
                    waiting.pop(0)
                    job_path = attempt / f"job-{index}.json"
                    status = attempt / f"status-{index}.json"
                    payload = {
                        "study": study,
                        "stage": stage,
                        "job": job,
                        "worker": worker,
                        "soft_deadline": clock.soft,
                        "hard_deadline": clock.hard,
                        "resume": resume,
                        "status": str(status.relative_to(root)),
                        "parent_pid": os.getpid(),
                        "code_revision": (
                            subprocess.check_output(
                                ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True
                            ).strip()
                        ),
                    }
                    write_json(job_path, payload)
                    command = [
                        sys.executable,
                        "-u",
                        str(root / "scripts/run_matched_modalities.py"),
                        "_worker",
                        "--job",
                        str(job_path),
                    ]
                    env = {
                        **os.environ,
                        "CUDA_VISIBLE_DEVICES": str(device),
                        "MASTER_PORT": str(study["launch"]["master_ports"][worker]),
                        "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
                        "TOKENIZERS_PARALLELISM": "false",
                    }
                    proc = subprocess.Popen(
                        command,
                        cwd=root,
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        errors="replace",
                        start_new_session=True,
                        bufsize=1,
                    )
                    clock.segment["children"].append(
                        {
                            "pid": proc.pid,
                            "identity": process_identity(proc.pid),
                            "status": str(status.relative_to(root)),
                            "job": str(job_path.relative_to(root)),
                            "device": device,
                            "master_port": env["MASTER_PORT"],
                        }
                    )
                    clock.flush()

                    def read(process=proc, log_path=attempt / f"worker-{index}.log", label=f"{stage}:{index}"):
                        assert process.stdout is not None
                        with log_path.open("w") as log:
                            for line in process.stdout:
                                log.write(line)
                                log.flush()
                                print(f"[{label}] {line}", end="", flush=True)

                    thread = threading.Thread(target=read, daemon=True)
                    thread.start()
                    readers.append(thread)
                    active[worker] = (proc, job, status)
                    progress(f"{stage}:launched", completed=len(results), total=len(jobs), worker=worker, job=job)
                for worker, (proc, _job, status) in list(active.items()):
                    if proc.poll() is None:
                        continue
                    if proc.returncode or not status.exists():
                        reason = read_json(status).get("reason") if status.exists() else f"exit {proc.returncode}"
                        outcome = (
                            read_json(status)["outcome"]
                            if status.exists()
                            else ("VALID_STOP" if proc.returncode == 124 else "INVALID")
                        )
                        raise RuntimeError(f"{outcome}: {stage} worker failed: {reason}")
                    result = read_json(status)
                    results.append(result)
                    del active[worker]
                    progress(f"{stage}:progress", completed=len(results), total=len(jobs))
                if waiting and not active and time.monotonic() >= clock.soft:
                    raise RuntimeError("VALID_STOP: cutoff before next job; unfinished coverage retained")
                time.sleep(0.1)
        finally:
            for proc, _, _ in active.values():
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
            for proc, _, _ in active.values():
                try:
                    proc.wait(timeout=max(0.1, min(5, clock.hard - time.monotonic())))
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
            for thread in readers:
                thread.join(timeout=2)
    return results
