"""Launch one authorized frozen BFS LoRA SFT run through ms-swift."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import BinaryIO

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_sft import build_ms_swift_sft_command
from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    StopOutcome,
    evaluate_execution_permission,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PHASE_MANIFESTS = {
    "v1": (
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json",
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json",
    ),
    "v3": (
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v3.json",
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v3.json",
    ),
    "v5": (
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v5.json",
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v5.json",
    ),
    "v6": (
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v6.json",
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v6.json",
    ),
}


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=tuple(_PHASE_MANIFESTS), required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--view", choices=("operational", "process"), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--world-size", type=int, required=True)
    parser.add_argument("--devices", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--reference-manifest", type=Path, action="append", default=[])
    parser.add_argument("--master-port", type=int, default=29500)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--progress-interval-seconds", type=float, default=60.0)
    args = parser.parse_args(arguments)
    if args.progress_interval_seconds <= 0:
        raise ValueError("progress interval must be positive")
    if not 1024 <= args.master_port <= 65535:
        raise ValueError("master port must be between 1024 and 65535")

    dataset_root = args.dataset_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    if output_root.exists() and not args.dry_run:
        raise FileExistsError(f"BFS SFT output root already exists: {output_root}")
    freeze, authorization_manifest = _PHASE_MANIFESTS[args.phase]
    phase_gate = load_bfs_phase_gate(freeze, authorization_manifest)
    stage = "operational_sft" if args.view == "operational" else "process_sft_and_sanity_gate"
    phase_gate.require_run(stage=stage, contract_id=phase_gate.phase_id)
    conversion = _validate_conversion(dataset_root, phase_gate.receipt(stage=stage), args.view)
    if args.phase in {"v3", "v5", "v6"}:
        _validate_v3_reference_gate(args.reference_manifest, phase_gate.receipt(stage="base_and_references"))

    binding = ReceiptBinding(
        contract_id=phase_gate.phase_id,
        attempt_id=args.attempt_id,
        output_root=output_root,
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_id=gate.receipt_id)
    permission = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )
    if not permission.start_permitted:
        raise RuntimeError("frozen BFS authorization did not permit SFT")

    checkpoint_root = output_root / "checkpoints"
    command = build_ms_swift_sft_command(
        dataset_root=dataset_root,
        output_root=checkpoint_root,
        phase_gate=phase_gate,
        seed=args.seed,
        world_size=args.world_size,
        smoke=args.smoke,
    )
    expected_steps = _expected_optimizer_steps(conversion, phase_gate.freeze, smoke=args.smoke)
    environment = os.environ.copy()
    environment.update(
        {
            "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
            "CUDA_VISIBLE_DEVICES": args.devices,
            "MASTER_PORT": str(args.master_port),
            "NPROC_PER_NODE": str(args.world_size),
            "PYTHONHASHSEED": str(args.seed),
        }
    )
    launch = {
        "authorization_receipt": authorization.to_dict(),
        "command": command,
        "environment": {
            key: environment[key]
            for key in sorted(environment)
            if key
            in {
                "CUBLAS_WORKSPACE_CONFIG",
                "CUDA_VISIBLE_DEVICES",
                "MASTER_PORT",
                "NPROC_PER_NODE",
                "PYTHONHASHSEED",
            }
        },
        "framework": {
            package: importlib.metadata.version(package)
            for package in ("accelerate", "ms-swift", "peft", "torch", "transformers")
        },
        "gate_receipt": gate.to_dict(),
        "phase_receipt": phase_gate.receipt(stage=stage),
        "estimated_optimizer_steps": expected_steps,
        "progress_interval_seconds": args.progress_interval_seconds,
        "schema_version": "bfs_ms_swift_launch_v3" if args.phase == "v3" else "bfs_ms_swift_launch_v1",
        "seed": args.seed,
        "smoke": args.smoke,
        "view": args.view,
    }
    if args.dry_run:
        print(_canonical_text({**launch, "dry_run": True, "output_root": str(output_root)}))
        return 0

    output_root.mkdir(parents=True)
    (output_root / "launch.json").write_text(_canonical_text(launch) + "\n", encoding="utf-8")

    started = time.monotonic()
    with (output_root / "training.log").open("wb") as log:
        process = subprocess.Popen(
            command,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        assert process.stdout is not None
        output_thread = threading.Thread(
            target=_tee_output,
            args=(process.stdout, log, sys.stdout.buffer),
        )
        output_thread.start()
        _write_progress(
            output_root,
            status="training",
            elapsed_seconds=0.0,
            completed_steps=0,
            total_steps=expected_steps,
        )
        while True:
            try:
                returncode = process.wait(timeout=args.progress_interval_seconds)
                break
            except subprocess.TimeoutExpired:
                _write_progress(
                    output_root,
                    status="training",
                    elapsed_seconds=time.monotonic() - started,
                    completed_steps=_latest_completed_step(output_root / "training.log", expected_steps),
                    total_steps=expected_steps,
                )
        output_thread.join()
    completed_steps = _latest_completed_step(output_root / "training.log", expected_steps)
    if returncode == 0:
        completed_steps = expected_steps
    _write_progress(
        output_root,
        status="completed" if returncode == 0 else "failed",
        elapsed_seconds=time.monotonic() - started,
        completed_steps=completed_steps,
        total_steps=expected_steps,
    )
    report = {
        "checkpoint_paths": [
            str(path.resolve()) for path in sorted(checkpoint_root.glob("checkpoint-*")) if path.is_dir()
        ],
        "elapsed_seconds": time.monotonic() - started,
        "outcome": StopOutcome.PASS.value if returncode == 0 else StopOutcome.INVALID.value,
        "returncode": returncode,
        "schema_version": "bfs_ms_swift_training_report_v3" if args.phase == "v3" else "bfs_ms_swift_training_report_v1",
        "scientific_completion": False,
        "status": "training_completed" if returncode == 0 else "training_failed",
    }
    (output_root / "training-report.json").write_text(_canonical_text(report) + "\n", encoding="utf-8")
    print(_canonical_text({**report, "output_root": str(output_root)}))
    return returncode


def _validate_conversion(dataset_root: Path, expected_phase_receipt: dict[str, object], view: str) -> dict[str, object]:
    manifest_path = dataset_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_schema = (
        "bfs_process_ms_swift_conversion_v3"
        if expected_phase_receipt.get("phase_id") == "issue-111-bfs-expansion-qualified-pilot-v3"
        else "bfs_ms_swift_conversion_v1"
    )
    if (
        manifest.get("schema_version") != expected_schema
        or manifest.get("framework") != {"name": "ms-swift", "version": "4.2.2"}
        or manifest.get("phase_receipt") != expected_phase_receipt
        or manifest.get("view") != view
        or not manifest.get("counts", {}).get("train")
        or not manifest.get("counts", {}).get("dev")
    ):
        raise ValueError("ms-swift dataset conversion does not match this frozen SFT run")
    return manifest


def _expected_optimizer_steps(conversion: dict[str, object], freeze: dict[str, object], *, smoke: bool) -> int:
    if smoke:
        return 1
    counts = conversion["counts"]
    training = freeze["training"]
    assert isinstance(counts, dict) and isinstance(training, dict)
    optimization = training["optimization"]
    assert isinstance(optimization, dict)
    return math.ceil(int(counts["train"]) / int(optimization["global_batch_size"])) * int(optimization["epochs"])


def _validate_v3_reference_gate(paths: list[Path], expected_phase_receipt: dict[str, object]) -> None:
    if not paths:
        raise ValueError("BFS v3 SFT requires the complete PASS reference manifest set")
    shard_count: int | None = None
    shard_indices: set[int] = set()
    task_count = 0
    for supplied in paths:
        path = supplied.expanduser().resolve()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != "bfs_base_and_references_v3"
            or manifest.get("phase_receipt") != expected_phase_receipt
            or manifest.get("gate_outcome") != StopOutcome.PASS.value
            or manifest.get("exact_reference_invariant_valid_success") != 1.0
        ):
            raise ValueError(f"BFS v3 reference manifest is not a matching PASS gate: {path}")
        current_count = int(manifest["shard_count"])
        if shard_count is None:
            shard_count = current_count
        if current_count != shard_count:
            raise ValueError("BFS v3 reference manifests disagree on shard count")
        shard_indices.add(int(manifest["shard_index"]))
        counts = manifest.get("counts")
        if (
            not isinstance(counts, dict)
            or counts.get("exact_classical") != counts.get("tasks")
            or counts.get("random_valid") != int(counts.get("tasks", 0)) * 5
        ):
            raise ValueError(f"BFS v3 reference manifest has incomplete exact coverage: {path}")
        task_count += int(counts["tasks"])
    if shard_count is None or len(paths) != shard_count or shard_indices != set(range(shard_count)) or task_count != 45:
        raise ValueError("BFS v3 references do not cover the complete 45-task development product")


def _latest_completed_step(log_path: Path, expected_steps: int) -> int:
    if not log_path.exists():
        return 0
    with log_path.open("rb") as stream:
        stream.seek(max(0, stream.seek(0, os.SEEK_END) - 1_000_000))
        text = stream.read().decode("utf-8", errors="replace")
    matches = re.findall(r"(?<![\d.])(\d+)\s*/\s*(\d+)(?![\d.])", text)
    completed = [int(current) for current, total in matches if int(total) == expected_steps]
    return max(completed, default=0)


def _tee_output(source: BinaryIO, log: BinaryIO, terminal: BinaryIO) -> None:
    while chunk := source.read(8192):
        log.write(chunk)
        log.flush()
        terminal.write(chunk)
        terminal.flush()


def _write_progress(
    output_root: Path,
    *,
    status: str,
    elapsed_seconds: float,
    completed_steps: int,
    total_steps: int,
) -> None:
    remaining = (elapsed_seconds / completed_steps) * (total_steps - completed_steps) if completed_steps else None
    record = {
        "completed_steps": completed_steps,
        "elapsed_seconds": elapsed_seconds,
        "estimated_remaining_seconds": remaining,
        "recorded_at_unix": time.time(),
        "schema_version": "bfs_sft_progress_v1",
        "status": status,
        "total_steps": total_steps,
    }
    progress_path = output_root / "progress.json"
    temporary = progress_path.with_suffix(".json.tmp")
    temporary.write_text(_canonical_text(record) + "\n", encoding="utf-8")
    temporary.replace(progress_path)
    with (output_root / "progress.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(_canonical_text(record) + "\n")
    print(_canonical_text(record), flush=True)


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
