"""Generate compact paired additive best-first expert traces."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from examples.planning_benchmark_slice.best_first_episode import (  # noqa: E402
    BestFirstTraceLimitError,
    run_best_first,
    serialize_best_first_trace,
)
from examples.planning_benchmark_slice.best_first_phase import (  # noqa: E402
    BestFirstPhase,
    load_best_first_phase,
    qualification_jobs,
)
from examples.planning_benchmark_slice.best_first_replay import (  # noqa: E402
    replay_best_first_trace,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority  # noqa: E402

_DESIGN = _REPO_ROOT / "configs/experiments/best-first-paired-design-v3.json"
_AUTHORIZATION = _REPO_ROOT / "configs/experiments/best-first-paired-authorization-v3.json"
_DEFAULT_QUALIFICATION = _REPO_ROOT / "data/best_first_paired_phase_v3/qualification-v1"
_DEFAULT_OUTPUT = _REPO_ROOT / "data/best_first_paired_phase_v3/exact-traces"
_DEFAULT_MEMORY_LIMIT_MIB = 2048
_DEFAULT_WORKERS = min(8, len(os.sched_getaffinity(0)))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fixture-dry-run", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--qualification-root", type=Path, default=_DEFAULT_QUALIFICATION)
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--memory-limit-mib", type=int, default=_DEFAULT_MEMORY_LIMIT_MIB)
    parser.add_argument("--progress-interval-seconds", type=float, default=10.0)
    parser.add_argument("--workers", type=int, default=_DEFAULT_WORKERS)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--worker-pair-id", help=argparse.SUPPRESS)
    parser.add_argument("--verify-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return _worker(args)
    if args.fixture_dry_run:
        return _fixture_dry_run()
    if args.resume and (args.dry_run or args.check):
        parser.error("--resume cannot be combined with --dry-run or --check")
    if args.memory_limit_mib <= 0:
        parser.error("--memory-limit-mib must be positive")
    if args.workers <= 0:
        parser.error("--workers must be positive")

    phase = load_best_first_phase(_DESIGN, _AUTHORIZATION, repo_root=_REPO_ROOT)
    phase.require_stage("trace_generation")
    pairs = list(phase.pairs)
    _print(
        {
            "completed": 1,
            "memory_limit_mib": args.memory_limit_mib,
            "pair_count": len(pairs),
            "phase_id": phase.phase_id,
            "stage": "generation_preflight",
            "status": "complete",
            "trace_count": len(pairs) * len(phase.algorithm_names),
            "workers": args.workers,
        }
    )
    if args.dry_run:
        _print(
            {
                "memory_limit_mib": args.memory_limit_mib,
                "pair_count": len(pairs),
                "phase_id": phase.phase_id,
                "status": "authorized_dry_run",
                "trace_count": len(pairs) * len(phase.algorithm_names),
                "workers": args.workers,
                "writes": 0,
            }
        )
        return 0
    output_root = args.output_root.resolve()
    if args.check:
        manifest = _verify_release(
            output_root,
            phase,
            workers=args.workers,
            memory_limit_mib=args.memory_limit_mib,
            progress_interval_seconds=args.progress_interval_seconds,
        )
        _print(
            {
                "pair_count": manifest["pair_count"],
                "status": "checked",
                "trace_count": manifest["trace_count"],
                "writes": 0,
            }
        )
        return 0

    _require_complete_qualification(args.qualification_root.resolve(), phase)
    if output_root.exists() and not args.resume:
        raise FileExistsError(f"best-first trace output exists; use --resume: {output_root}")
    started = time.monotonic()
    items, valid_stop_reason, invalid_reason = _run_pairs(
        pairs,
        output_root=output_root,
        resume=args.resume,
        workers=args.workers,
        memory_limit_mib=args.memory_limit_mib,
        progress_interval_seconds=args.progress_interval_seconds,
        stage="trace_generation",
        started=started,
    )
    if invalid_reason is not None:
        receipt = _receipt(phase, "INVALID", invalid_reason, len(items))
        _write_immutable(output_root / "generation-receipt.json", _canonical_bytes(receipt))
        _print(receipt)
        return 1
    if valid_stop_reason is not None:
        reason = valid_stop_reason
        receipt = _receipt(phase, "VALID_STOP", reason, len(items))
        _write_immutable(output_root / "generation-receipt.json", _canonical_bytes(receipt))
        _print(receipt)
        return 0

    manifest = {
        "algorithms": list(phase.algorithm_names),
        "pair_count": len(items),
        "pairs": items,
        "phase_id": phase.phase_id,
        "schema_version": "best_first_paired_expert_traces_v1",
        "source_issue": 63,
        "trace_count": len(items) * len(phase.algorithm_names),
    }
    _write_immutable(output_root / "manifest.json", _canonical_bytes(manifest))
    receipt = _receipt(phase, "PASS", None, len(items))
    _write_immutable(output_root / "generation-receipt.json", _canonical_bytes(receipt))
    _print(receipt)
    return 0


def _worker(args: argparse.Namespace) -> int:
    if args.worker_pair_id is None:
        raise ValueError("trace-generation worker pair is missing")
    memory_bytes = args.memory_limit_mib * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    phase = load_best_first_phase(_DESIGN, _AUTHORIZATION, repo_root=_REPO_ROOT)
    phase.require_stage("trace_generation")
    row = next(item for item in phase.pairs if item["pair_id"] == args.worker_pair_id)
    output_root = args.output_root.resolve()
    try:
        if args.verify_only:
            pair_root = output_root / "pairs" / str(row["pair_id"])
            item = _json_object(pair_root / "pair.json")
            _verify_pair(row, item, pair_root, phase)
        else:
            item = _generate_pair(
                row,
                phase,
                output_root,
                resume=args.resume,
                progress_interval_seconds=args.progress_interval_seconds,
            )
    except (BestFirstTraceLimitError, MemoryError) as error:
        _print({"kind": "valid_stop", "reason": str(error) or type(error).__name__})
        return 0
    except ValueError as error:
        _print({"kind": "invalid", "reason": str(error)})
        return 0
    _print({"item": item, "kind": "result"})
    return 0


def _run_pairs(
    pairs: Sequence[Mapping[str, Any]],
    *,
    output_root: Path,
    resume: bool,
    workers: int,
    memory_limit_mib: int,
    progress_interval_seconds: float,
    stage: str,
    started: float,
    verify_only: bool = False,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    items_by_pair: dict[str, dict[str, Any]] = {}
    valid_stop_reason: str | None = None
    invalid_reason: str | None = None
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for pair_index, row in enumerate(pairs):
            kwargs = {
                "output_root": output_root,
                "resume": resume,
                "pair_index": pair_index,
                "total": len(pairs),
                "started": started,
                "memory_limit_mib": memory_limit_mib,
                "progress_interval_seconds": progress_interval_seconds,
            }
            if verify_only:
                kwargs["verify_only"] = True
            future = executor.submit(_run_pair, row, **kwargs)
            futures[future] = row

        for future in as_completed(futures):
            row = futures[future]
            if future.cancelled():
                continue
            try:
                item = future.result()
            except CancelledError:
                continue
            except BestFirstTraceLimitError as error:
                valid_stop_reason = valid_stop_reason or str(error) or type(error).__name__
                for pending in futures:
                    pending.cancel()
                continue
            except ValueError as error:
                invalid_reason = invalid_reason or str(error)
                for pending in futures:
                    pending.cancel()
                continue
            items_by_pair[str(row["pair_id"])] = item
            completed = len(items_by_pair)
            elapsed = time.monotonic() - started
            _print(
                {
                    "completed": completed,
                    "elapsed_seconds": round(elapsed, 6),
                    "estimated_remaining_seconds": _eta(elapsed, completed, len(pairs)),
                    "pair_id": row["pair_id"],
                    "stage": stage,
                    "status": "complete",
                    "total": len(pairs),
                }
            )
    items = [items_by_pair[str(row["pair_id"])] for row in pairs if str(row["pair_id"]) in items_by_pair]
    return items, valid_stop_reason, invalid_reason


def _run_pair(
    row: Mapping[str, Any],
    *,
    output_root: Path,
    resume: bool,
    pair_index: int,
    total: int,
    started: float,
    memory_limit_mib: int,
    progress_interval_seconds: float,
    verify_only: bool = False,
) -> dict[str, Any]:
    _print(
        {
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "instance_id": row["instance_id"],
            "pair_index": pair_index,
            "pair_id": row["pair_id"],
            "stage": "trace_check" if verify_only else "trace_generation",
            "status": "started",
            "total": total,
        }
    )
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--worker-pair-id",
        str(row["pair_id"]),
        "--output-root",
        str(output_root),
        "--memory-limit-mib",
        str(memory_limit_mib),
        "--progress-interval-seconds",
        str(progress_interval_seconds),
    ]
    if resume:
        command.append("--resume")
    if verify_only:
        command.append("--verify-only")
    process = subprocess.Popen(
        command,
        cwd=_REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if process.stdout is None:
        raise AssertionError("trace-generation worker output is unavailable")
    item: dict[str, Any] | None = None
    valid_stop_reason: str | None = None
    invalid_reason: str | None = None
    for line in process.stdout:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            _print({"message": line.rstrip(), "stage": "trace_generation_worker", "status": "log"})
            continue
        kind = payload.pop("kind", None)
        if kind == "result" and isinstance(payload.get("item"), dict):
            item = payload["item"]
        elif kind == "valid_stop":
            valid_stop_reason = str(payload.get("reason"))
        elif kind == "invalid":
            invalid_reason = str(payload.get("reason"))
        else:
            _print(payload)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"trace-generation worker failed for {row['pair_id']} with exit {return_code}")
    if invalid_reason is not None:
        raise ValueError(invalid_reason)
    if valid_stop_reason is not None:
        raise BestFirstTraceLimitError(valid_stop_reason)
    if item is None:
        raise RuntimeError(f"trace-generation worker returned no result for {row['pair_id']}")
    return item


def _fixture_dry_run() -> int:
    path = _REPO_ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json"
    row = {
        "instance_id": "fixture-best-first",
        "pair_id": "fixture-best-first-pair",
        "task_path": path.relative_to(_REPO_ROOT).as_posix(),
        "task_sha256": _sha256(path),
    }
    phase = BestFirstPhase(
        design={
            "accepted_delta_limit": 16,
            "caps": {
                "max_decisions_per_trace": 256,
                "max_expansions_per_trace": 64,
                "max_uncompressed_trace_bytes": 1_000_000,
            },
            "phase_id": "issue-63-best-first-paired-v3",
        },
        authorization={},
        pairs=(row,),
        repo_root=_REPO_ROOT,
    )
    with tempfile.TemporaryDirectory(prefix="best-first-fixture-") as temporary:
        output_root = Path(temporary) / "exact-traces"
        item = _generate_pair(
            row,
            phase,
            output_root,
            resume=False,
            progress_interval_seconds=10.0,
        )
        _verify_pair(row, item, output_root / "pairs" / row["pair_id"], phase)
    _print(
        {
            "fixture_only": True,
            "replayed_trace_count": len(phase.algorithm_names),
            "status": "contract_validation_only",
            "writes": 0,
        }
    )
    return 0


def _generate_pair(
    row: Mapping[str, Any],
    phase: BestFirstPhase,
    output_root: Path,
    *,
    resume: bool,
    progress_interval_seconds: float,
) -> dict[str, Any]:
    pair_root = output_root / "pairs" / str(row["pair_id"])
    pair_manifest = pair_root / "pair.json"
    if pair_manifest.is_file():
        if not resume:
            raise FileExistsError(f"best-first pair exists: {pair_root}")
        item = _json_object(pair_manifest)
        _verify_pair(row, item, pair_root, phase)
        return item
    if pair_root.exists():
        raise FileExistsError(f"incomplete best-first pair requires inspection: {pair_root}")

    task_path = phase.repo_root / str(row["task_path"])
    task_bytes = task_path.read_bytes()
    task = json.loads(task_bytes)
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    caps = phase.design["caps"]
    output_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="best-first-pair-", dir=output_root.parent) as raw_staging:
        staging = Path(raw_staging)
        (staging / "task.json").write_bytes(task_bytes)
        traces: dict[str, dict[str, Any]] = {}
        for algorithm in phase.algorithm_names:
            adapter_started = time.monotonic()

            def progress(value: dict[str, object], *, selected: str = algorithm) -> None:
                _print(
                    {
                        **value,
                        "algorithm": selected,
                        "pair_id": row["pair_id"],
                        "stage": "trace_generation",
                        "status": "running",
                    }
                )

            search = run_best_first(
                authority,
                algorithm=algorithm,
                max_expansions=caps["max_expansions_per_trace"],
                max_trace_records=caps["max_decisions_per_trace"],
                max_trace_bytes=caps["max_uncompressed_trace_bytes"],
                accepted_delta_limit=phase.design["accepted_delta_limit"],
                progress=progress,
                progress_interval_seconds=progress_interval_seconds,
            )
            replay = replay_best_first_trace(search.trace_payload, authority=authority)
            if not replay.goal_reached or replay.termination != "goal_reached":
                raise BestFirstTraceLimitError(f"{row['pair_id']} {algorithm} stopped with {replay.termination}")
            trace_bytes = serialize_best_first_trace(search.trace_payload)
            trace_path = staging / f"{algorithm}.json.gz"
            trace_path.write_bytes(gzip.compress(trace_bytes, compresslevel=9, mtime=0))
            traces[algorithm] = {
                "decision_count": replay.decision_count,
                "expansion_count": replay.expansion_count,
                "path": f"{algorithm}.json.gz",
                "reopen_count": replay.reopen_count,
                "sha256": _sha256(trace_path),
                "solution_cost": replay.solution_cost,
                "stored_size_bytes": trace_path.stat().st_size,
                "uncompressed_size_bytes": len(trace_bytes),
            }
            _print(
                {
                    "algorithm": algorithm,
                    "decision_count": replay.decision_count,
                    "elapsed_seconds": round(time.monotonic() - adapter_started, 6),
                    "expansion_count": replay.expansion_count,
                    "pair_id": row["pair_id"],
                    "stage": "trace_generation",
                    "status": "adapter_complete",
                }
            )
        item = {
            "instance_id": row["instance_id"],
            "pair_id": row["pair_id"],
            "schema_version": "best_first_paired_trace_item_v1",
            "task_path": "task.json",
            "task_sha256": hashlib.sha256(task_bytes).hexdigest(),
            "traces": traces,
        }
        (staging / "pair.json").write_bytes(_canonical_bytes(item))
        pair_root.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(pair_root)
    _verify_pair(row, item, pair_root, phase)
    return item


def _verify_release(
    output_root: Path,
    phase: BestFirstPhase,
    *,
    workers: int,
    memory_limit_mib: int,
    progress_interval_seconds: float,
) -> dict[str, Any]:
    manifest = _json_object(output_root / "manifest.json")
    if (
        manifest.get("schema_version") != "best_first_paired_expert_traces_v1"
        or manifest.get("phase_id") != phase.phase_id
        or manifest.get("pair_count") != 75
        or manifest.get("trace_count") != 150
        or manifest.get("algorithms") != list(phase.algorithm_names)
        or not isinstance(manifest.get("pairs"), list)
        or len(manifest["pairs"]) != 75
    ):
        raise ValueError("best-first trace release manifest is invalid")
    receipt = _json_object(output_root / "generation-receipt.json")
    if receipt != _receipt(phase, "PASS", None, 75):
        raise ValueError("best-first generation receipt is not PASS")
    items, valid_stop_reason, invalid_reason = _run_pairs(
        phase.pairs,
        output_root=output_root,
        resume=False,
        workers=workers,
        memory_limit_mib=memory_limit_mib,
        progress_interval_seconds=progress_interval_seconds,
        stage="trace_check",
        started=time.monotonic(),
        verify_only=True,
    )
    if invalid_reason is not None or valid_stop_reason is not None or items != manifest["pairs"]:
        raise ValueError("best-first trace release differs from its replay-verified pairs")
    return manifest


def _verify_pair(
    row: Mapping[str, Any],
    item: Mapping[str, Any],
    pair_root: Path,
    phase: BestFirstPhase,
) -> None:
    if (
        item.get("pair_id") != row["pair_id"]
        or item.get("instance_id") != row["instance_id"]
        or item.get("schema_version") != "best_first_paired_trace_item_v1"
        or item.get("task_path") != "task.json"
        or item.get("task_sha256") != row["task_sha256"]
        or set(item.get("traces", {})) != set(phase.algorithm_names)
    ):
        raise ValueError(f"best-first pair manifest differs: {row['pair_id']}")
    task_path = pair_root / "task.json"
    if not task_path.is_file() or _sha256(task_path) != row["task_sha256"]:
        raise ValueError(f"best-first pair task differs: {row['pair_id']}")
    task = _json_object(task_path)
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    for algorithm, trace_item in item["traces"].items():
        trace_path = pair_root / str(trace_item["path"])
        if (
            not trace_path.is_file()
            or _sha256(trace_path) != trace_item["sha256"]
            or trace_path.stat().st_size != trace_item["stored_size_bytes"]
        ):
            raise ValueError(f"best-first trace artifact differs: {row['pair_id']} {algorithm}")
        with gzip.open(trace_path, "rb") as source:
            trace_bytes = source.read()
        trace = json.loads(trace_bytes)
        replay = replay_best_first_trace(trace, authority=authority)
        if trace_item != {
            "decision_count": replay.decision_count,
            "expansion_count": replay.expansion_count,
            "path": f"{algorithm}.json.gz",
            "reopen_count": replay.reopen_count,
            "sha256": _sha256(trace_path),
            "solution_cost": replay.solution_cost,
            "stored_size_bytes": trace_path.stat().st_size,
            "uncompressed_size_bytes": len(trace_bytes),
        }:
            raise ValueError(f"best-first trace counts differ: {row['pair_id']} {algorithm}")


def _require_complete_qualification(root: Path, phase: BestFirstPhase) -> None:
    manifest = _json_object(root / "qualification.json")
    jobs = qualification_jobs(phase)
    measurements = manifest.get("measurements")
    if (
        manifest.get("schema_version") != "best_first_paired_qualification_v1"
        or manifest.get("phase_id") != phase.phase_id
        or manifest.get("qualification_complete") is not True
        or manifest.get("job_count") != len(jobs)
        or not isinstance(measurements, list)
        or len(measurements) != len(jobs)
    ):
        raise ValueError("complete best-first qualification is required before generation")
    for job, measurement in zip(jobs, measurements, strict=True):
        if (
            any(measurement.get(field) != job[field] for field in job)
            or measurement.get("termination") != "goal_reached"
        ):
            raise ValueError("best-first qualification does not match the fixed generation panel")
    qualification_receipt = _json_object(root / "qualification-receipt.json")
    if qualification_receipt != {
        "authorization_id": phase.authorization["authorization_id"],
        "completed_jobs": 150,
        "contract_id": phase.phase_id,
        "gate_receipt_id": phase.authorization["gate_receipt"]["receipt_id"],
        "outcome": "PASS",
        "reason": None,
        "receipt_id": phase.authorization["qualification_receipt_id"],
        "schema_version": "best_first_qualification_receipt_v2",
        "scientific_completion": False,
        "source_issue": 63,
    }:
        raise ValueError("best-first qualification receipt is not PASS")


def _receipt(
    phase: BestFirstPhase,
    outcome: str,
    reason: str | None,
    completed_pairs: int,
) -> dict[str, Any]:
    is_v3 = phase.phase_id == "issue-63-best-first-paired-v3"
    receipt = {
        "authorization_id": phase.authorization["authorization_id"],
        "completed_pairs": completed_pairs,
        "contract_id": phase.phase_id,
        "gate_receipt_id": phase.authorization["gate_receipt"]["receipt_id"],
        "outcome": outcome,
        "reason": reason,
        "schema_version": "best_first_generation_receipt_v2" if is_v3 else "best_first_generation_receipt_v1",
        "scientific_completion": outcome == "PASS" and completed_pairs == 75,
        "source_issue": 63,
    }
    if is_v3:
        receipt["receipt_id"] = phase.authorization["generation_receipt_id"]
    return receipt


def _eta(elapsed: float, completed: int, total: int) -> float:
    return round(elapsed / completed * (total - completed), 6)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.is_file():
        if path.read_bytes() != payload:
            raise ValueError(f"immutable artifact differs: {path}")
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
