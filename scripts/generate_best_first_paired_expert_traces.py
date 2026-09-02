"""Generate compact paired additive best-first expert traces."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from examples.planning_benchmark_slice.best_first_controller import (  # noqa: E402
    BEST_FIRST_SETTINGS,
)
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

_DESIGN = _REPO_ROOT / "configs/experiments/best-first-paired-design-v2.json"
_AUTHORIZATION = _REPO_ROOT / "configs/experiments/best-first-paired-authorization-v2.json"
_DEFAULT_QUALIFICATION = _REPO_ROOT / "data/best_first_paired_phase_v2/qualification-v1"
_DEFAULT_OUTPUT = _REPO_ROOT / "data/best_first_paired_phase_v2/exact-traces"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fixture-dry-run", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--qualification-root", type=Path, default=_DEFAULT_QUALIFICATION)
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--progress-interval-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)
    if args.fixture_dry_run:
        return _fixture_dry_run()
    if args.resume and (args.dry_run or args.check):
        parser.error("--resume cannot be combined with --dry-run or --check")

    phase = load_best_first_phase(_DESIGN, _AUTHORIZATION, repo_root=_REPO_ROOT)
    phase.require_stage("trace_generation")
    pairs = list(phase.pairs)
    _print(
        {
            "completed": 1,
            "pair_count": len(pairs),
            "phase_id": phase.phase_id,
            "stage": "generation_preflight",
            "status": "complete",
            "trace_count": len(pairs) * len(BEST_FIRST_SETTINGS),
        }
    )
    if args.dry_run:
        _print(
            {
                "pair_count": len(pairs),
                "phase_id": phase.phase_id,
                "status": "authorized_dry_run",
                "trace_count": len(pairs) * len(BEST_FIRST_SETTINGS),
                "writes": 0,
            }
        )
        return 0
    output_root = args.output_root.resolve()
    if args.check:
        manifest = _verify_release(output_root, phase)
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
    items: list[dict[str, Any]] = []
    try:
        for pair_index, row in enumerate(pairs, start=1):
            _print(
                {
                    "completed": pair_index - 1,
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                    "instance_id": row["instance_id"],
                    "pair_id": row["pair_id"],
                    "stage": "trace_generation",
                    "status": "started",
                    "total": len(pairs),
                }
            )
            items.append(
                _generate_pair(
                    row,
                    phase,
                    output_root,
                    resume=args.resume,
                    progress_interval_seconds=args.progress_interval_seconds,
                )
            )
            _print(
                {
                    "completed": pair_index,
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                    "estimated_remaining_seconds": _eta(time.monotonic() - started, pair_index, len(pairs)),
                    "pair_id": row["pair_id"],
                    "stage": "trace_generation",
                    "status": "complete",
                    "total": len(pairs),
                }
            )
    except (BestFirstTraceLimitError, MemoryError) as error:
        reason = str(error) or type(error).__name__
        receipt = _receipt(phase, "VALID_STOP", reason, len(items))
        _write_immutable(output_root / "generation-receipt.json", _canonical_bytes(receipt))
        _print(receipt)
        return 0

    manifest = {
        "algorithms": list(BEST_FIRST_SETTINGS),
        "pair_count": len(items),
        "pairs": items,
        "phase_id": phase.phase_id,
        "schema_version": "best_first_paired_expert_traces_v1",
        "source_issue": 63,
        "trace_count": len(items) * len(BEST_FIRST_SETTINGS),
    }
    _write_immutable(output_root / "manifest.json", _canonical_bytes(manifest))
    receipt = _receipt(phase, "PASS", None, len(items))
    _write_immutable(output_root / "generation-receipt.json", _canonical_bytes(receipt))
    _verify_release(output_root, phase)
    _print(receipt)
    return 0


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
            "phase_id": "fixture-best-first",
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
            "replayed_trace_count": len(BEST_FIRST_SETTINGS),
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
        for algorithm in BEST_FIRST_SETTINGS:
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


def _verify_release(output_root: Path, phase: BestFirstPhase) -> dict[str, Any]:
    manifest = _json_object(output_root / "manifest.json")
    if (
        manifest.get("schema_version") != "best_first_paired_expert_traces_v1"
        or manifest.get("phase_id") != phase.phase_id
        or manifest.get("pair_count") != 75
        or manifest.get("trace_count") != 150
        or manifest.get("algorithms") != list(BEST_FIRST_SETTINGS)
        or not isinstance(manifest.get("pairs"), list)
        or len(manifest["pairs"]) != 75
    ):
        raise ValueError("best-first trace release manifest is invalid")
    for row, item in zip(phase.pairs, manifest["pairs"], strict=True):
        _verify_pair(row, item, output_root / "pairs" / str(row["pair_id"]), phase)
    receipt = _json_object(output_root / "generation-receipt.json")
    if receipt != _receipt(phase, "PASS", None, 75):
        raise ValueError("best-first generation receipt is not PASS")
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
        or set(item.get("traces", {})) != set(BEST_FIRST_SETTINGS)
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


def _receipt(
    phase: BestFirstPhase,
    outcome: str,
    reason: str | None,
    completed_pairs: int,
) -> dict[str, Any]:
    return {
        "authorization_id": phase.authorization["authorization_id"],
        "completed_pairs": completed_pairs,
        "contract_id": phase.phase_id,
        "outcome": outcome,
        "reason": reason,
        "schema_version": "best_first_generation_receipt_v1",
        "scientific_completion": outcome == "PASS" and completed_pairs == 75,
        "source_issue": 63,
    }


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
