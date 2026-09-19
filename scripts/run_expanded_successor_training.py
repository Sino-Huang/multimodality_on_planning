#!/usr/bin/env python
"""Run and independently audit frozen expanded successor SFT training."""

from __future__ import annotations

import argparse
import gc
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, timestamp, write
from examples.planning_benchmark_slice.expanded_successor_protocol import load_views, validate_protocol
from examples.planning_benchmark_slice.expanded_successor_training import (
    train_cell,
    training_root,
    verify_training_cell,
)

PROTOCOL = ROOT / "configs/experiments/expanded-study/successor-protocol.json"


def assigned(protocol, worker):
    return protocol["launch"]["qualification_worker_modalities"][str(worker)]


def head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def require_worker_environment(protocol, worker):
    if worker not in (0, 1):
        raise ValueError("successor training worker is outside the frozen mapping")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != str(protocol["launch"]["devices"][worker]):
        raise ValueError("successor training worker GPU differs from the frozen mapping")
    try:
        port = int(os.environ["MASTER_PORT"])
    except (KeyError, ValueError) as error:
        raise ValueError("successor training worker MASTER_PORT is missing or invalid") from error
    if port not in protocol["launch"]["master_port_pool"]:
        raise ValueError("successor training worker MASTER_PORT is outside the frozen pool")
    return port


def require_before_cutoff(protocol):
    if time.time() >= timestamp(protocol["budget"]["gpu_cutoff_utc"]):
        raise RuntimeError("VALID_STOP: successor training GPU cutoff has passed")


def _empty_cuda_cache():
    import torch

    torch.cuda.empty_cache()


def run_training(protocol, context, views, worker):
    require_before_cutoff(protocol)
    port = require_worker_environment(protocol, worker)
    modalities = assigned(protocol, worker)
    records_per_cell = protocol["training"]["records_per_modality"]
    total = len(modalities) * records_per_cell
    completed_before = 0
    reports = []
    started = time.monotonic()
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    for modality in modalities:
        report_path = training_root(ROOT, protocol, modality) / "report.json"
        if report_path.is_file():
            verify_training_cell(ROOT, protocol, context, views, modality=modality)
            report = read(report_path)
            reports.append(report)
            completed_before += records_per_cell
            write(
                progress_path,
                {
                    "completed": completed_before,
                    "total": total,
                    "modality": modality,
                    "modality_completed": records_per_cell,
                    "resumed_skip": True,
                    "eta_seconds": 0,
                },
            )
            continue

        def progress(*, completed, total, eta_seconds, base=completed_before, modality=modality):
            modality_records = min(completed * protocol["training"]["global_batch_size"], records_per_cell)
            overall = base + modality_records
            values = {
                "completed": overall,
                "total": len(modalities) * records_per_cell,
                "modality": modality,
                "modality_completed": modality_records,
                "cell_update": completed,
                "cell_updates": total,
                "eta_seconds": eta_seconds,
            }
            write(progress_path, values)
            print(json.dumps({"stage": "successor_training", **values}), flush=True)

        reports.append(
            train_cell(ROOT, protocol, context, views, modality=modality, progress=progress)
        )
        completed_before += records_per_cell
        gc.collect()
        _empty_cuda_cache()
    report = {
        "schema_version": "expanded_successor_training_worker_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "modalities": modalities,
        "cells": reports,
        "records": sum(row["records"] for row in reports),
        "optimizer_updates": sum(row["optimizer_updates"] for row in reports),
        "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
        "master_port": port,
        "runtime_head": head(),
        "elapsed_seconds": time.monotonic() - started,
    }
    write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json", report)
    write(progress_path, {"completed": total, "total": total, "terminal": True})


def audit_training_worker(protocol, context, views, worker):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if terminal["status"] != "succeeded":
        raise RuntimeError(f"successor training worker stopped: inspect {terminal['directory']}/worker.log")
    report = read(Path(terminal["directory"]) / "worker-result.json")
    modalities = assigned(protocol, worker)
    expected_records = len(modalities) * protocol["training"]["records_per_modality"]
    if (
        report.get("outcome") != "PASS"
        or report.get("protocol_id") != protocol["protocol_id"]
        or report.get("worker") != worker
        or report.get("modalities") != modalities
        or report.get("records") != expected_records
        or report.get("master_port") != terminal["master_port"]
        or terminal["master_port"] not in protocol["launch"]["master_port_pool"]
        or terminal["gpus"] != [protocol["launch"]["devices"][worker]]
    ):
        raise ValueError("successor training worker provenance differs")
    verified = [
        verify_training_cell(ROOT, protocol, context, views, modality=modality)
        for modality in modalities
    ]
    result = {"outcome": "PASS", "worker": worker, "modalities": modalities, "cells": verified}
    write(Path(terminal["directory"]) / "checkpoint-audit.json", result)
    print(json.dumps(result, indent=2))


def latest_attempt(ledger, job_id):
    attempts = [row for row in ledger["attempts"] if row["job_id"] == job_id]
    if not attempts:
        raise ValueError(f"missing scheduler attempt for {job_id}")
    return attempts[-1]


def finalize_training(protocol, context, views):
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    attempts = [latest_attempt(ledger, f"successor-train-{worker}") for worker in range(2)]
    if any(row["status"] != "succeeded" for row in attempts) or any(
        read(Path(row["directory"]) / "hook-result.json").get("returncode") != 0 for row in attempts
    ):
        raise ValueError("successor training workers or checkpoint hooks are incomplete")
    cells = [
        verify_training_cell(ROOT, protocol, context, views, modality=modality)
        for modality in protocol["modalities"]
    ]
    if (
        len(cells) != len(protocol["modalities"])
        or [row.get("modality") for row in cells] != protocol["modalities"]
        or any(row.get("outcome") != "PASS" for row in cells)
    ):
        raise ValueError("successor training cells did not all pass final verification")
    report = {
        "schema_version": "expanded_successor_training_report_v1",
        # `status` is the cross-lane gate field; `outcome` preserves this report schema's convention.
        "status": "PASS",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "arm": protocol["training"]["arm"],
        "cells": cells,
        "records": sum(row["records"] for row in cells),
        "optimizer_updates": sum(row["optimizer_updates"] for row in cells),
        "jobs": [
            {key: row[key] for key in ("job_id", "attempt", "gpus", "master_port", "gpu_hours")}
            for row in attempts
        ],
    }
    path = ROOT / protocol["output_root"] / "training" / "training-report.json"
    write(path, report)
    write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": len(cells), "total": len(cells)})
    print(json.dumps(report, indent=2))


def audit_training_final(protocol, context, views):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    path = ROOT / protocol["output_root"] / "training" / "training-report.json"
    report = read(path)
    if (
        terminal["status"] != "succeeded"
        or report.get("status") != "PASS"
        or report.get("outcome") != "PASS"
    ):
        raise RuntimeError("successor training final audit did not complete")
    actual = [
        verify_training_cell(ROOT, protocol, context, views, modality=modality)
        for modality in protocol["modalities"]
    ]
    if actual != report["cells"]:
        raise ValueError("successor training evidence differs from independent checkpoint verification")
    print("PASS: all three successor-SFT final checkpoints independently verified")


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "stage",
        choices=("run", "audit-training-worker", "finalize-training", "audit-training-final"),
    )
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--worker", type=int, choices=(0, 1))
    args = parser.parse_args(argv)
    protocol = read(args.protocol)
    context = validate_protocol(ROOT, protocol)
    _views_report, views = load_views(ROOT, protocol, context)
    if args.stage in {"run", "audit-training-worker"} and args.worker is None:
        parser.error(f"{args.stage} requires --worker")
    functions = {
        "run": lambda: run_training(protocol, context, views, args.worker),
        "audit-training-worker": lambda: audit_training_worker(protocol, context, views, args.worker),
        "finalize-training": lambda: finalize_training(protocol, context, views),
        "audit-training-final": lambda: audit_training_final(protocol, context, views),
    }
    functions[args.stage]()


if __name__ == "__main__":
    main()
