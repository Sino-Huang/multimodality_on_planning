"""Qualify both additive best-first settings on the fixed 75-task panel."""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from examples.planning_benchmark_slice.best_first_phase import (  # noqa: E402
    load_best_first_phase,
    qualification_jobs,
)
from examples.planning_benchmark_slice.best_first_qualification import (  # noqa: E402
    run_best_first_qualification,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority  # noqa: E402

_DESIGN = _REPO_ROOT / "configs/experiments/best-first-paired-design-v2.json"
_AUTHORIZATION = _REPO_ROOT / "configs/experiments/best-first-paired-authorization-v2.json"
_DEFAULT_OUTPUT = _REPO_ROOT / "data/best_first_paired_phase_v2/qualification-v1"
_DEFAULT_MEMORY_LIMIT_MIB = 2048


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--memory-limit-mib", type=int, default=_DEFAULT_MEMORY_LIMIT_MIB)
    parser.add_argument("--progress-interval-seconds", type=float, default=10.0)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--worker-task", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-algorithm", help=argparse.SUPPRESS)
    parser.add_argument("--worker-max-expansions", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--worker-max-decisions", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return _worker(args)
    if args.resume and (args.dry_run or args.check):
        parser.error("--resume cannot be combined with --dry-run or --check")
    if args.memory_limit_mib <= 0:
        parser.error("--memory-limit-mib must be positive")

    preflight_started = time.monotonic()
    _print(
        {
            "completed": 0,
            "elapsed_seconds": 0.0,
            "stage": "qualification_preflight",
            "status": "started",
            "total": 1,
        }
    )
    phase = load_best_first_phase(_DESIGN, _AUTHORIZATION, repo_root=_REPO_ROOT)
    jobs = list(qualification_jobs(phase))
    _print(
        {
            "completed": 1,
            "elapsed_seconds": round(time.monotonic() - preflight_started, 6),
            "stage": "qualification_preflight",
            "status": "complete",
            "total": 1,
        }
    )
    if args.dry_run:
        _print(
            {
                "algorithm_count": 2,
                "job_count": len(jobs),
                "memory_limit_mib": args.memory_limit_mib,
                "pair_count": len(phase.pairs),
                "phase_id": phase.phase_id,
                "status": "authorized_dry_run",
                "writes": 0,
            }
        )
        return 0

    output_root = args.output_root.resolve()
    if args.check:
        manifest = _check(output_root, jobs, phase.phase_id, args.memory_limit_mib)
        _print(
            {
                "job_count": manifest["job_count"],
                "qualification_complete": True,
                "status": "checked",
                "writes": 0,
            }
        )
        return 0

    started = time.monotonic()
    measurements: list[dict[str, Any]] = []
    for index, job in enumerate(jobs):
        path = output_root / "measurements" / f"{index:03d}-{job['algorithm']}.json"
        if path.is_file():
            if not args.resume:
                raise FileExistsError(f"qualification measurement exists; use --resume: {path}")
            measurement = _json_object(path)
            _validate_measurement(measurement, job, index, args.memory_limit_mib)
            measurements.append(measurement)
            _print(_job_progress(job, measurement, len(measurements), len(jobs), started, "resumed"))
            continue
        _print(
            {
                "algorithm": job["algorithm"],
                "completed": len(measurements),
                "elapsed_seconds": round(time.monotonic() - started, 6),
                "instance_id": job["instance_id"],
                "pair_id": job["pair_id"],
                "stage": "qualification",
                "status": "started",
                "total": len(jobs),
            }
        )
        measurement = _run_job(
            job,
            index=index,
            completed=len(measurements),
            total=len(jobs),
            started=started,
            memory_limit_mib=args.memory_limit_mib,
            progress_interval_seconds=args.progress_interval_seconds,
        )
        _write_immutable(path, _canonical_bytes(measurement))
        measurements.append(measurement)
        _print(_job_progress(job, measurement, len(measurements), len(jobs), started, "complete"))

    manifest = _manifest(measurements, phase.phase_id, args.memory_limit_mib)
    _write_immutable(output_root / "qualification.json", _canonical_bytes(manifest))
    _print(
        {
            "job_count": manifest["job_count"],
            "max_decisions_by_algorithm": manifest["max_decisions_by_algorithm"],
            "max_expansions_by_algorithm": manifest["max_expansions_by_algorithm"],
            "qualification_complete": manifest["qualification_complete"],
            "status": "complete",
        }
    )
    return 0 if manifest["qualification_complete"] else 1


def _worker(args: argparse.Namespace) -> int:
    if (
        args.worker_task is None
        or args.worker_algorithm is None
        or args.worker_max_expansions is None
        or args.worker_max_decisions is None
    ):
        raise ValueError("qualification worker arguments are incomplete")
    memory_bytes = args.memory_limit_mib * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    task = _json_object(args.worker_task)
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])

    def progress(value: dict[str, object]) -> None:
        _print({"kind": "progress", **value})

    result = run_best_first_qualification(
        authority,
        args.worker_algorithm,
        max_expansions=args.worker_max_expansions,
        max_decisions=args.worker_max_decisions,
        progress=progress,
        progress_interval_seconds=args.progress_interval_seconds,
    ).to_dict()
    _print({"kind": "result", "peak_memory_mib": _peak_memory_mib(), **result})
    return 0


def _run_job(
    job: Mapping[str, Any],
    *,
    index: int,
    completed: int,
    total: int,
    started: float,
    memory_limit_mib: int,
    progress_interval_seconds: float,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--worker-task",
        str((_REPO_ROOT / job["task_path"]).resolve()),
        "--worker-algorithm",
        str(job["algorithm"]),
        "--worker-max-expansions",
        str(job["max_expansions"]),
        "--worker-max-decisions",
        str(job["max_decisions"]),
        "--memory-limit-mib",
        str(memory_limit_mib),
        "--progress-interval-seconds",
        str(progress_interval_seconds),
    ]
    process = subprocess.Popen(
        command,
        cwd=_REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if process.stdout is None:
        raise AssertionError("qualification worker output is unavailable")
    result: dict[str, Any] | None = None
    for line in process.stdout:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            _print({"message": line.rstrip(), "stage": "qualification_worker", "status": "log"})
            continue
        kind = payload.pop("kind", None)
        if kind == "progress":
            elapsed = time.monotonic() - started
            _print(
                {
                    **payload,
                    "algorithm": job["algorithm"],
                    "completed": completed,
                    "elapsed_seconds": round(elapsed, 6),
                    "estimated_remaining_seconds": _eta(elapsed, completed, total),
                    "instance_id": job["instance_id"],
                    "pair_id": job["pair_id"],
                    "stage": "qualification",
                    "status": "running",
                    "total": total,
                }
            )
        elif kind == "result":
            result = payload
        else:
            _print({"message": line.rstrip(), "stage": "qualification_worker", "status": "log"})
    return_code = process.wait()
    if return_code != 0 or result is None:
        raise RuntimeError(
            f"qualification worker failed for {job['pair_id']} {job['algorithm']} with exit {return_code}"
        )
    measurement = {
        **job,
        **result,
        "job_index": index,
        "memory_limit_mib": memory_limit_mib,
        "schema_version": "best_first_qualification_measurement_v1",
    }
    _validate_measurement(measurement, job, index, memory_limit_mib)
    return measurement


def _manifest(
    measurements: list[dict[str, Any]],
    phase_id: str,
    memory_limit_mib: int,
) -> dict[str, Any]:
    algorithms = tuple(sorted({job["algorithm"] for job in measurements}))
    complete = len(measurements) == 150 and all(row["termination"] == "goal_reached" for row in measurements)
    return {
        "algorithms": list(algorithms),
        "job_count": len(measurements),
        "max_decisions_by_algorithm": {
            algorithm: max(
                (row["decision_count"] for row in measurements if row["algorithm"] == algorithm),
                default=None,
            )
            for algorithm in algorithms
        },
        "max_expansions_by_algorithm": {
            algorithm: max(
                (row["expansion_count"] for row in measurements if row["algorithm"] == algorithm),
                default=None,
            )
            for algorithm in algorithms
        },
        "measurements": measurements,
        "memory_limit_mib": memory_limit_mib,
        "pair_count": 75,
        "phase_id": phase_id,
        "qualification_complete": complete,
        "schema_version": "best_first_paired_qualification_v1",
        "source_issue": 63,
    }


def _check(
    output_root: Path,
    jobs: list[dict[str, Any]],
    phase_id: str,
    memory_limit_mib: int,
) -> dict[str, Any]:
    measurements = []
    for index, job in enumerate(jobs):
        path = output_root / "measurements" / f"{index:03d}-{job['algorithm']}.json"
        measurement = _json_object(path)
        _validate_measurement(measurement, job, index, memory_limit_mib)
        measurements.append(measurement)
    expected = _manifest(measurements, phase_id, memory_limit_mib)
    actual = _json_object(output_root / "qualification.json")
    if actual != expected or not actual["qualification_complete"]:
        raise ValueError("best-first qualification is incomplete or differs from its measurements")
    return actual


def _validate_measurement(
    value: Mapping[str, Any],
    job: Mapping[str, Any],
    index: int,
    memory_limit_mib: int,
) -> None:
    identity_fields = (
        "algorithm",
        "difficulty",
        "domain_id",
        "instance_id",
        "max_decisions",
        "max_expansions",
        "pair_id",
        "split",
        "task_path",
        "task_sha256",
    )
    if (
        any(value.get(field) != job[field] for field in identity_fields)
        or value.get("job_index") != index
        or value.get("memory_limit_mib") != memory_limit_mib
        or value.get("schema_version") != "best_first_qualification_measurement_v1"
        or value.get("termination")
        not in {"decision_budget", "expansion_budget", "frontier_exhausted", "goal_reached", "memory_limit"}
        or any(
            not _nonnegative_int(value.get(field))
            for field in ("decision_count", "expansion_count", "reopen_count", "visited_count")
        )
        or not _nonnegative_number(value.get("runtime_seconds"))
        or not _nonnegative_number(value.get("peak_memory_mib"))
        or (value.get("termination") == "goal_reached") != (value.get("solution_cost") is not None)
    ):
        raise ValueError("best-first qualification measurement differs from its fixed job")


def _job_progress(
    job: Mapping[str, Any],
    measurement: Mapping[str, Any],
    completed: int,
    total: int,
    started: float,
    status: str,
) -> dict[str, Any]:
    elapsed = time.monotonic() - started
    return {
        "algorithm": job["algorithm"],
        "completed": completed,
        "decision_count": measurement["decision_count"],
        "elapsed_seconds": round(elapsed, 6),
        "estimated_remaining_seconds": _eta(elapsed, completed, total),
        "expansion_count": measurement["expansion_count"],
        "instance_id": job["instance_id"],
        "pair_id": job["pair_id"],
        "peak_memory_mib": measurement["peak_memory_mib"],
        "stage": "qualification",
        "status": status,
        "termination": measurement["termination"],
        "total": total,
    }


def _eta(elapsed: float, completed: int, total: int) -> float | None:
    return None if completed == 0 else round(elapsed / completed * (total - completed), 6)


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _nonnegative_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _peak_memory_mib() -> float:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmHWM:"):
            fields = line.split()
            if len(fields) == 3 and fields[2] == "kB":
                return round(int(fields[1]) / 1024, 3)
    raise RuntimeError("Linux VmHWM is unavailable for best-first qualification")


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.is_file():
        if path.read_bytes() != payload:
            raise ValueError(f"immutable qualification artifact differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode()


def _print(value: object) -> None:
    print(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False),
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
