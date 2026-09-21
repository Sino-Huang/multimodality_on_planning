"""Single-host expanded-study admission and background worker supervision."""

import argparse
import fcntl
import json
import math
import os
import re
import resource
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEDULE = ROOT / "docs/experiments/expanded-study/schedule.json"
LEDGER = ROOT / "outputs/expanded-study/v1/budget.json"


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def repository_head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def identity(pid):
    try:
        # start ticks distinguish a reused PID; zombies have already stopped.
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19] if fields[0] != "Z" else None
    except FileNotFoundError:
        return None


def alive(handle):
    return bool(handle and identity(handle["pid"]) == handle["start_ticks"])


def handle(pid):
    return {"pid": pid, "start_ticks": identity(pid)}


def group_alive(pid):
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = path.read_text().rsplit(")", 1)[1].split()
            if fields[0] != "Z" and int(fields[2]) == pid:
                return True
        except FileNotFoundError:
            continue
    return False


@contextmanager
def locked(path, schedule):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = (
            read(path)
            if path.exists()
            else {
                "schedule": schedule,
                "allocations_gpu_hours": schedule["allocations_gpu_hours"].copy(),
                "transfers": [],
                "attempts": [],
            }
        )
        if ledger["schedule"] != schedule:
            raise ValueError("schedule differs from existing ledger; the clock cannot reset")
        yield ledger
        write(path, ledger)


def charged(attempt):
    if attempt["status"] in ("reserved", "running"):
        return attempt["max_seconds"] * len(attempt["gpus"]) / 3600
    return attempt["gpu_hours"]


def admit(ledger, job, now):
    schedule = ledger["schedule"]
    seconds = job["max_seconds"]
    gpus = job["gpus"]
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", job["job_id"]):
        raise ValueError("job_id must be a simple directory name")
    if not math.isfinite(seconds) or seconds <= 0 or not job["command"] or job["total"] <= 0:
        raise ValueError("positive finite runtime, total and command required")
    if not job.get("completion_hook"):
        raise ValueError("a CPU completion audit/failure-diagnosis hook is required")
    if len(gpus) != len(set(gpus)) or any(g not in (0, 1) for g in gpus):
        raise ValueError("GPUs must be distinct device indices 0 and/or 1")
    if gpus and now + seconds > timestamp(schedule["gpu_cutoff_utc"]):
        raise ValueError("job would cross the absolute GPU cutoff")
    if now + seconds > timestamp(schedule["handoff_deadline_utc"]):
        raise ValueError("job would cross the absolute handoff cutoff")
    previous = [a for a in ledger["attempts"] if a["job_id"] == job["job_id"]]
    if previous:
        if previous[-1]["status"] in ("reserved", "running", "succeeded"):
            raise ValueError("duplicate launch refused")
        if not job.get("resume_reason"):
            raise ValueError("failed attempt retained; explicit resume_reason required")
        for key in ("branch", "gpus", "total"):
            if previous[-1][key] != job[key]:
                raise ValueError(f"resume changes {key}")
    active = [a for a in ledger["attempts"] if a["status"] in ("reserved", "running")]
    if any(set(gpus) & set(a["gpus"]) for a in active):
        raise ValueError("GPU already reserved")
    cost = seconds * len(gpus) / 3600
    branch = job["branch"]
    if branch == "recovery_reserve":
        raise ValueError("transfer recovery allocation prospectively to a research branch")
    if (
        sum(charged(a) for a in ledger["attempts"] if a["branch"] == branch) + cost
        > ledger["allocations_gpu_hours"][branch]
    ):
        raise ValueError("branch GPU-hour ceiling exceeded")
    if sum(charged(a) for a in ledger["attempts"]) + cost > schedule["experiment_gpu_hours_cap"]:
        raise ValueError("total GPU-hour ceiling exceeded")
    port = None
    if gpus:
        for candidate in schedule["master_port_pool"]:
            if any(a["master_port"] == candidate for a in active):
                continue
            with socket.socket() as sock:
                try:
                    sock.bind(("", candidate))
                except OSError:
                    continue
            port = candidate
            break
        if port is None:
            raise ValueError("no free MASTER_PORT")
    return dict(job, attempt=len(previous) + 1, status="reserved", master_port=port, admitted=now, gpu_hours=0)


def launch(path, schedule, job, *, production_ledger=None):
    production = Path(production_ledger) if production_ledger is not None else LEDGER
    if job["gpus"] and Path(path).resolve() != production.resolve():
        raise ValueError("GPU launches must use the shared production ledger")
    with locked(path, schedule) as ledger:
        attempt = admit(ledger, job, time.time())
        attempt["launch_head"] = repository_head()
        directory = Path(path).resolve().parent / "jobs" / job["job_id"] / str(attempt["attempt"])
        directory.mkdir(parents=True, exist_ok=False)
        attempt["directory"] = str(directory)
        ledger["attempts"].append(attempt)
        # Persist reservation before spawning; worker blocks on the same lock.
        write(path, ledger)
        with (directory / "supervisor.log").open("a") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "scripts/run_expanded_study.py"),
                    "_worker",
                    "--ledger",
                    str(Path(path).resolve()),
                    "--job-id",
                    job["job_id"],
                    "--attempt",
                    str(attempt["attempt"]),
                ],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        attempt["supervisor"] = handle(process.pid)
    return attempt


def update(path, schedule, job_id, number, **values):
    with locked(path, schedule) as ledger:
        attempt = next(a for a in ledger["attempts"] if a["job_id"] == job_id and a["attempt"] == number)
        attempt.update(values)
        result = dict(attempt)
    return result


def supervise(path, job_id, number):
    schedule = read(path)["schedule"]
    with locked(path, schedule) as ledger:
        record = next(a for a in ledger["attempts"] if a["job_id"] == job_id and a["attempt"] == number)
        if record["status"] != "reserved" or record.get("supervisor") != handle(os.getpid()):
            raise ValueError("duplicate or unowned supervisor refused")
        record.update(status="running", started=time.time())
        attempt = dict(record)
    directory = Path(attempt["directory"])
    started = attempt["started"]
    deadline = min(attempt["admitted"] + attempt["max_seconds"], timestamp(schedule["handoff_deadline_utc"]))
    if attempt["gpus"]:
        deadline = min(deadline, timestamp(schedule["gpu_cutoff_utc"]))
    env = dict(
        os.environ,
        CUDA_VISIBLE_DEVICES=",".join(map(str, attempt["gpus"])),
        EXPANDED_PROGRESS_PATH=str(directory / "progress.json"),
        EXPANDED_ATTEMPT_DIR=str(directory),
        PYTHONUNBUFFERED="1",
    )
    if attempt["master_port"] is not None:
        env["MASTER_PORT"] = str(attempt["master_port"])
    process = None
    status = "failed"
    error = None
    returncode = None

    def interrupted(signum, frame):
        raise InterruptedError(f"supervisor signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        with (directory / "worker.log").open("a") as log:
            # A separate timeout owns the process group even if this supervisor dies.
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError("cutoff reached before worker launch")
            if attempt["gpus"]:
                inventory = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=index,uuid,name,memory.total,memory.free", "--format=csv"], text=True
                )
                update(path, schedule, job_id, number, available_vram_at_launch_csv=inventory)
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError("cutoff reached during launch inventory")
            process = subprocess.Popen(
                ["timeout", "--signal=KILL", str(remaining), *attempt["command"]],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            update(path, schedule, job_id, number, worker=handle(process.pid))
            while process.poll() is None:
                now = time.time()
                if now >= deadline:
                    status = "cutoff"
                    break
                progress = read(directory / "progress.json") if (directory / "progress.json").exists() else {}
                completed = progress.get("completed", 0)
                elapsed = now - started
                write(
                    directory / "heartbeat.json",
                    {
                        "time": now,
                        "completed": completed,
                        "total": attempt["total"],
                        "elapsed_seconds": elapsed,
                        "eta_seconds": elapsed * (attempt["total"] - completed) / completed if completed else None,
                        "worker": handle(process.pid),
                        "master_port": attempt["master_port"],
                    },
                )
                time.sleep(min(1, max(0, deadline - now)))
            if process.poll() is not None:
                returncode = process.returncode
                status = "succeeded" if returncode == 0 else ("cutoff" if time.time() >= deadline else "failed")
    except Exception as exc:
        error = repr(exc)
        if isinstance(exc, TimeoutError):
            status = "cutoff"
    finally:
        # Kill the entire owned process group, including children left by a runner.
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            returncode = process.wait()
        ended = time.time()
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        attempt = update(
            path,
            schedule,
            job_id,
            number,
            status=status,
            ended=ended,
            elapsed_seconds=ended - started,
            gpu_hours=(ended - started) * len(attempt["gpus"]) / 3600,
            cpu_seconds=usage.ru_utime + usage.ru_stime,
            returncode=returncode,
            error=error,
        )
        write(directory / "terminal.json", attempt)
        completion(attempt)


def completion(attempt):
    directory = Path(attempt["directory"])
    write(
        directory / "completion.json",
        {"status": attempt["status"], "audit_required": True, "terminal": str(directory / "terminal.json")},
    )
    with (directory / "hook.log").open("a") as log:
        try:
            result = subprocess.run(
                attempt["completion_hook"],
                cwd=ROOT,
                env=dict(os.environ, CUDA_VISIBLE_DEVICES="", EXPANDED_TERMINAL_PATH=str(directory / "terminal.json")),
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=300,
            )
            hook = {"returncode": result.returncode}
        except Exception as exc:
            hook = {"error": repr(exc)}
        write(directory / "hook-result.json", hook)


def reconcile(path, schedule):
    """Never infer death from an expired heartbeat. Retain live orphan reservations."""
    interrupted = []
    with locked(path, schedule) as ledger:
        for attempt in ledger["attempts"]:
            if attempt["status"] not in ("reserved", "running") or alive(attempt.get("supervisor")):
                continue
            if alive(attempt.get("worker")) or (attempt.get("worker") and group_alive(attempt["worker"]["pid"])):
                raise ValueError("orphan worker still live; reservation retained, do not relaunch")
            if not attempt.get("supervisor") or (attempt["status"] == "running" and not attempt.get("worker")):
                raise ValueError("launch handle missing; reservation retained pending process inspection")
            # Crash stop time is unknown; conservatively account all time since admission.
            ended = time.time()
            attempt.update(
                status="interrupted",
                ended=ended,
                gpu_hours=(ended - attempt["admitted"]) * len(attempt["gpus"]) / 3600,
                accounting="conservative elapsed until verified dead",
                cpu_seconds=None,
            )
            write(Path(attempt["directory"]) / "terminal.json", attempt)
            interrupted.append(dict(attempt))
    for attempt in interrupted:
        completion(attempt)
    return ledger


def transfer(path, schedule, source, target, hours, reason):
    if not reason or not math.isfinite(hours) or hours <= 0 or source == target:
        raise ValueError("positive prospective transfer and reason required")
    with locked(path, schedule) as ledger:
        allocations = ledger["allocations_gpu_hours"]
        if target not in allocations:
            raise ValueError("unknown target branch")
        committed = sum(charged(a) for a in ledger["attempts"] if a["branch"] == source)
        if allocations[source] - hours < committed:
            raise ValueError("transfer would remove spent or reserved allocation")
        allocations[source] -= hours
        allocations[target] += hours
        ledger["transfers"].append(
            dict(
                source=source,
                target=target,
                hours=hours,
                reason=reason,
                time=time.time(),
                source_committed_hours=committed,
            )
        )
    return ledger


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("init", "launch", "status", "reconcile", "transfer", "_worker"))
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument(
        "--schedule",
        type=Path,
        default=None,
        help=(
            "Explicitly designate a follow-up program schedule; the --ledger then becomes "
            "that program's production ledger for GPU launches (#128 follow-up window)."
        ),
    )
    parser.add_argument("--job", type=Path)
    parser.add_argument("--job-id")
    parser.add_argument("--attempt", type=int)
    parser.add_argument("--source")
    parser.add_argument("--target")
    parser.add_argument("--hours", type=float)
    parser.add_argument("--reason")
    args = parser.parse_args()
    schedule = read(args.schedule) if args.schedule is not None else read(SCHEDULE)
    if args.action == "_worker":
        supervise(args.ledger, args.job_id, args.attempt)
        return
    production_ledger = args.ledger if args.schedule is not None else None
    if args.action == "launch":
        result = launch(args.ledger, schedule, read(args.job), production_ledger=production_ledger)
    elif args.action == "reconcile":
        result = reconcile(args.ledger, schedule)
    elif args.action == "transfer":
        result = transfer(args.ledger, schedule, args.source, args.target, args.hours, args.reason)
    else:
        with locked(args.ledger, schedule) as ledger:
            result = ledger
    print(json.dumps(result, indent=2))
