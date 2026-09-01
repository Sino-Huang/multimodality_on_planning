"""Qualify both exact A* adapters on all 75 frozen issue-62 tasks."""

from __future__ import annotations

import argparse
import hashlib
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

from examples.planning_benchmark_slice.astar_phase import (  # noqa: E402
    AStarPairedPhaseGate,
    load_astar_paired_phase_gate,
)
from examples.planning_benchmark_slice.astar_qualification import (  # noqa: E402
    ASTAR_QUALIFICATION_ADAPTERS,
    run_astar_qualification,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority  # noqa: E402

_DEFAULT_FREEZE = _REPO_ROOT / "configs/experiments/astar-paired-freeze-v1.json"
_DEFAULT_AUTHORIZATION = _REPO_ROOT / "configs/experiments/astar-paired-authorization-v1.json"
_DEFAULT_OUTPUT = _REPO_ROOT / "data/astar_paired_phase_v1/qualification-v1"
_DEFAULT_MEMORY_LIMIT_MIB = 8192


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
    parser.add_argument("--worker-adapter", help=argparse.SUPPRESS)
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
            "estimated_remaining_seconds": None,
            "stage": "qualification_preflight",
            "status": "started",
            "total": 1,
        }
    )
    gate = load_astar_paired_phase_gate(_DEFAULT_FREEZE, _DEFAULT_AUTHORIZATION, repo_root=_REPO_ROOT)
    jobs = qualification_jobs(gate)
    panel_binding = {
        "freeze": _artifact_binding(_DEFAULT_FREEZE),
        "task_component": _artifact_binding(
            _REPO_ROOT / gate.freeze["component_manifests"]["task"]
        ),
    }
    _print(
        {
            "completed": 1,
            "elapsed_seconds": round(time.monotonic() - preflight_started, 6),
            "estimated_remaining_seconds": 0.0,
            "stage": "qualification_preflight",
            "status": "complete",
            "total": 1,
        }
    )
    output_root = args.output_root.resolve()
    if args.dry_run:
        _print(
            {
                "adapter_count": len(ASTAR_QUALIFICATION_ADAPTERS),
                "job_count": len(jobs),
                "memory_limit_mib": args.memory_limit_mib,
                "pair_count": len(gate.components["task"]["pairs"]),
                "panel_changed": False,
                "panel_binding": panel_binding,
                "status": "authorized_dry_run",
                "writes": 0,
            }
        )
        return 0
    if args.check:
        manifest = _checked_manifest(output_root, jobs, panel_binding, args.memory_limit_mib)
        _print({"job_count": len(manifest["measurements"]), "status": "checked", "writes": 0})
        return 0

    started = time.monotonic()
    measurements: list[dict[str, Any]] = []
    _print(_overall_progress(jobs, completed=0, started=started, status="started"))
    for index, job in enumerate(jobs):
        result_path = output_root / "measurements" / f"{index:03d}-{job['adapter']}.json"
        if result_path.is_file():
            if not args.resume:
                raise FileExistsError(f"qualification measurement already exists; use --resume: {result_path}")
            measurement = _json_object(result_path)
            _validate_measurement(measurement, job, index, args.memory_limit_mib)
            measurements.append(measurement)
            _print(_job_progress(jobs, job, measurement, index + 1, started, "resumed"))
            continue
        measurement = _run_job(
            job,
            index=index,
            completed=len(measurements),
            total=len(jobs),
            started=started,
            memory_limit_mib=args.memory_limit_mib,
            progress_interval_seconds=args.progress_interval_seconds,
        )
        _write_immutable(result_path, _canonical_bytes(measurement))
        measurements.append(measurement)
        _print(_job_progress(jobs, job, measurement, index + 1, started, "complete"))

    manifest = _manifest(panel_binding, measurements, args.memory_limit_mib)
    _write_immutable(output_root / "qualification.json", _canonical_bytes(manifest))
    _print(
        {
            "job_count": len(measurements),
            "max_expansions_by_adapter": manifest["max_expansions_by_adapter"],
            "qualification_complete": manifest["qualification_complete"],
            "status": "complete",
        }
    )
    return 0 if manifest["qualification_complete"] else 1


def qualification_jobs(gate: AStarPairedPhaseGate) -> list[dict[str, Any]]:
    pairs = gate.components["task"]["pairs"]
    if gate.phase_id != "issue-62-astar-paired-development-v1" or len(pairs) != 75:
        raise ValueError("qualification requires the complete frozen issue-62 v1 panel")
    return [
        {
            "adapter": adapter,
            "difficulty": row["difficulty"],
            "domain_id": row["domain_id"],
            "instance_id": row["instance_id"],
            "pair_id": row["pair_id"],
            "split": row["split"],
            "task_path": row["task_path"],
            "task_sha256": row["task_sha256"],
        }
        for row in pairs
        for adapter in ASTAR_QUALIFICATION_ADAPTERS
    ]


def _worker(args: argparse.Namespace) -> int:
    if args.worker_task is None or args.worker_adapter not in ASTAR_QUALIFICATION_ADAPTERS:
        raise ValueError("qualification worker requires a task and supported adapter")
    memory_bytes = args.memory_limit_mib * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    task = _json_object(args.worker_task)
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])

    def progress(value: dict[str, object]) -> None:
        _print({"kind": "progress", **value})

    result = run_astar_qualification(
        authority,
        args.worker_adapter,
        progress=progress,
        progress_interval_seconds=args.progress_interval_seconds,
    ).to_dict()
    result["peak_memory_mib"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 3)
    _print({"kind": "result", **result})
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
        "--worker-adapter",
        str(job["adapter"]),
        "--memory-limit-mib",
        str(memory_limit_mib),
        "--progress-interval-seconds",
        str(progress_interval_seconds),
    ]
    process = subprocess.Popen(
        command,
        cwd=_REPO_ROOT,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    if process.stdout is None:
        raise AssertionError("qualification worker stdout is unavailable")
    result: dict[str, Any] | None = None
    for line in process.stdout:
        payload = json.loads(line)
        kind = payload.pop("kind")
        if kind == "progress":
            elapsed = time.monotonic() - started
            _print(
                {
                    **payload,
                    "adapter": job["adapter"],
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
            raise ValueError(f"unknown qualification worker record: {kind}")
    return_code = process.wait()
    if return_code != 0 or result is None:
        raise RuntimeError(
            f"qualification worker failed for {job['pair_id']} {job['adapter']} with exit {return_code}"
        )
    measurement = {
        **job,
        **result,
        "job_index": index,
        "memory_limit_mib": memory_limit_mib,
        "schema_version": "astar_paired_qualification_measurement_v1",
    }
    _validate_measurement(measurement, job, index, memory_limit_mib)
    return measurement


def _manifest(
    panel_binding: Mapping[str, Any],
    measurements: list[dict[str, Any]],
    memory_limit_mib: int,
) -> dict[str, Any]:
    expected_count = 75 * len(ASTAR_QUALIFICATION_ADAPTERS)
    complete = len(measurements) == expected_count and all(
        row["termination"] == "goal_reached" for row in measurements
    )
    maxima = {
        adapter: max(
            (row["expansion_count"] for row in measurements if row["adapter"] == adapter),
            default=None,
        )
        for adapter in ASTAR_QUALIFICATION_ADAPTERS
    }
    return {
        "adapters": list(ASTAR_QUALIFICATION_ADAPTERS),
        "job_count": len(measurements),
        "max_expansions_by_adapter": maxima,
        "measurements": measurements,
        "memory_limit_mib": memory_limit_mib,
        "pair_count": 75,
        "panel_changed": False,
            "panel_binding": dict(panel_binding),
        "qualification_complete": complete,
        "schema_version": "astar_paired_qualification_v1",
        "source_issue": 62,
    }


def _checked_manifest(
    output_root: Path,
    jobs: list[dict[str, Any]],
    panel_binding: Mapping[str, Any],
    memory_limit_mib: int,
) -> dict[str, Any]:
    measurements = []
    for index, job in enumerate(jobs):
        path = output_root / "measurements" / f"{index:03d}-{job['adapter']}.json"
        value = _json_object(path)
        _validate_measurement(value, job, index, memory_limit_mib)
        measurements.append(value)
    expected = _manifest(panel_binding, measurements, memory_limit_mib)
    actual = _json_object(output_root / "qualification.json")
    if actual != expected or not actual["qualification_complete"]:
        raise ValueError("A* qualification manifest is incomplete or differs from its fixed measurements")
    return actual


def _validate_measurement(
    value: Mapping[str, Any],
    job: Mapping[str, Any],
    index: int,
    memory_limit_mib: int,
) -> None:
    expected_fields = {
        "adapter",
        "composite_node_count",
        "decision_count",
        "difficulty",
        "domain_id",
        "expansion_count",
        "instance_id",
        "job_index",
        "memory_limit_mib",
        "pair_id",
        "peak_memory_mib",
        "reopen_count",
        "runtime_seconds",
        "schema_version",
        "solution_cost",
        "split",
        "task_path",
        "task_sha256",
        "termination",
        "world_state_count",
    }
    identity_fields = (
        "adapter",
        "difficulty",
        "domain_id",
        "instance_id",
        "pair_id",
        "split",
        "task_path",
        "task_sha256",
    )
    count_fields = (
        "composite_node_count",
        "decision_count",
        "expansion_count",
        "reopen_count",
        "world_state_count",
    )
    if (
        set(value) != expected_fields
        or any(value.get(field) != job[field] for field in identity_fields)
        or value.get("job_index") != index
        or value.get("memory_limit_mib") != memory_limit_mib
        or value.get("schema_version") != "astar_paired_qualification_measurement_v1"
        or any(not _nonnegative_int(value.get(field)) for field in count_fields)
        or value.get("world_state_count", 0) < 1
        or value.get("composite_node_count", 0) < value.get("world_state_count", 0)
        or not _nonnegative_number(value.get("runtime_seconds"))
        or not _nonnegative_number(value.get("peak_memory_mib"))
        or value.get("termination") not in {"frontier_exhausted", "goal_reached"}
        or (
            value.get("solution_cost") is None
            if value.get("termination") == "goal_reached"
            else value.get("solution_cost") is not None
        )
        or (
            value.get("solution_cost") is not None
            and not _nonnegative_int(value.get("solution_cost"))
        )
    ):
        raise ValueError("qualification measurement does not match its fixed panel job")


def _job_progress(
    jobs: list[dict[str, Any]],
    job: Mapping[str, Any],
    measurement: Mapping[str, Any],
    completed: int,
    started: float,
    status: str,
) -> dict[str, Any]:
    elapsed = time.monotonic() - started
    return {
        "adapter": job["adapter"],
        "completed": completed,
        "decision_count": measurement["decision_count"],
        "elapsed_seconds": round(elapsed, 6),
        "estimated_remaining_seconds": _eta(elapsed, completed, len(jobs)),
        "expansion_count": measurement["expansion_count"],
        "instance_id": job["instance_id"],
        "pair_id": job["pair_id"],
        "peak_memory_mib": measurement["peak_memory_mib"],
        "stage": "qualification",
        "status": status,
        "termination": measurement["termination"],
        "total": len(jobs),
    }


def _overall_progress(
    jobs: list[dict[str, Any]], *, completed: int, started: float, status: str
) -> dict[str, Any]:
    elapsed = time.monotonic() - started
    return {
        "completed": completed,
        "elapsed_seconds": round(elapsed, 6),
        "estimated_remaining_seconds": _eta(elapsed, completed, len(jobs)),
        "stage": "qualification",
        "status": status,
        "total": len(jobs),
    }


def _eta(elapsed: float, completed: int, total: int) -> float | None:
    return None if completed == 0 else round(elapsed / completed * (total - completed), 6)


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _nonnegative_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _artifact_binding(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(_REPO_ROOT).as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


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
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n"
    ).encode()


def _print(value: object) -> None:
    print(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False),
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
