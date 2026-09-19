#!/usr/bin/env python
"""Run and audit expanded curriculum-by-modality training."""

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

from examples.planning_benchmark_slice.expanded_curriculum_training import (
    ORDERINGS,
    REPORT_SCHEMA,
    train_cell,
    training_root,
    validate_protocol,
    verify_all_cells_same_set,
    verify_training_cell,
)
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, timestamp, write

PROTOCOL = ROOT / "configs/experiments/expanded-study/curriculum-protocol.json"


def assigned(protocol, worker):
    return protocol["launch"]["training_worker_cells"][str(worker)]


def require_worker_environment(protocol, worker):
    if worker not in (0, 1):
        raise ValueError("curriculum worker is outside the frozen mapping")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != str(protocol["launch"]["devices"][worker]):
        raise ValueError("curriculum worker GPU differs from frozen mapping")
    try:
        port = int(os.environ["MASTER_PORT"])
    except (KeyError, ValueError) as error:
        raise ValueError("curriculum worker MASTER_PORT is missing or invalid") from error
    if port not in protocol["launch"]["master_port_pool"]:
        raise ValueError("curriculum worker MASTER_PORT is outside the frozen pool")
    return port


def _head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def run(protocol, context, worker):
    if time.time() >= timestamp(protocol["budget"]["gpu_cutoff_utc"]):
        raise RuntimeError("VALID_STOP: curriculum training cutoff has passed")
    port = require_worker_environment(protocol, worker)
    cells = assigned(protocol, worker)
    total = len(cells) * protocol["training"]["records_per_cell"]
    completed_before = 0
    reports = []
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    started = time.monotonic()
    for cell in cells:
        modality, ordering = cell["modality"], cell["ordering"]
        report_path = training_root(ROOT, protocol, modality, ordering) / "report.json"
        if report_path.is_file():
            verify_training_cell(ROOT, protocol, context, modality=modality, ordering=ordering)
            reports.append(read(report_path))
            completed_before += 512
            continue

        def progress(*, completed, total, eta_seconds, base=completed_before, cell=cell):
            records = min(completed * protocol["training"]["global_batch_size"], 512)
            values = {
                "completed": base + records,
                "total": len(cells) * 512,
                "cell": cell,
                "cell_update": completed,
                "cell_updates": total,
                "eta_seconds": eta_seconds,
            }
            write(progress_path, values)
            print(json.dumps({"stage": "curriculum_training", **values}), flush=True)

        reports.append(train_cell(ROOT, protocol, context, modality=modality, ordering=ordering, progress=progress))
        completed_before += 512
        gc.collect()
        import torch

        torch.cuda.empty_cache()
    result = {
        "schema_version": "expanded_curriculum_training_worker_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "cells": cells,
        "reports": reports,
        "records": len(reports) * 512,
        "optimizer_updates": len(reports) * 16,
        "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
        "master_port": port,
        "runtime_head": _head(),
        "elapsed_seconds": time.monotonic() - started,
    }
    write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json", result)
    write(progress_path, {"completed": total, "total": total, "terminal": True})


def audit_training_worker(protocol, context, worker):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if terminal.get("status") != "succeeded":
        raise RuntimeError("curriculum training worker did not succeed")
    result = read(Path(terminal["directory"]) / "worker-result.json")
    cells = assigned(protocol, worker)
    if (
        result.get("outcome") != "PASS"
        or result.get("cells") != cells
        or terminal.get("gpus") != [protocol["launch"]["devices"][worker]]
        or result.get("master_port") != terminal.get("master_port")
    ):
        raise ValueError("curriculum worker provenance differs")
    verified = [
        verify_training_cell(ROOT, protocol, context, modality=row["modality"], ordering=row["ordering"])
        for row in cells
    ]
    write(
        Path(terminal["directory"]) / "checkpoint-audit.json", {"outcome": "PASS", "worker": worker, "cells": verified}
    )
    print(json.dumps({"outcome": "PASS", "worker": worker, "cells": verified}, indent=2))


def _latest(ledger, job_id):
    rows = [row for row in ledger["attempts"] if row["job_id"] == job_id]
    if not rows:
        raise ValueError(f"missing curriculum scheduler attempt: {job_id}")
    return rows[-1]


def _fresh_init_evidence(cells):
    fingerprints = {row.get("fresh_lora_init_sha256") for row in cells}
    tensor_counts = {row.get("fresh_lora_init_tensors") for row in cells}
    if len(fingerprints) != 1 or None in fingerprints or len(tensor_counts) != 1 or None in tensor_counts:
        raise ValueError("curriculum fresh LoRA initialization differs across cells")
    return {"sha256": next(iter(fingerprints)), "parameter_tensors": next(iter(tensor_counts))}


def finalize_training(protocol, context):
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    attempts = [_latest(ledger, f"curriculum-train-{worker}") for worker in range(2)]
    if any(
        row["status"] != "succeeded" or read(Path(row["directory"]) / "hook-result.json").get("returncode") != 0
        for row in attempts
    ):
        raise ValueError("curriculum workers or hooks are incomplete")
    cells = [
        verify_training_cell(ROOT, protocol, context, modality=modality, ordering=ordering)
        for modality in protocol["modalities"]
        for ordering in ORDERINGS
    ]
    verify_all_cells_same_set(protocol, cells)
    fresh_init = _fresh_init_evidence(cells)
    report = {
        "schema_version": REPORT_SCHEMA,
        "status": "PASS",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "cells": cells,
        "records": sum(row["records"] for row in cells),
        "optimizer_updates": sum(row["optimizer_updates"] for row in cells),
        "same_record_set_all_cells": True,
        "exact_protocol_orders_all_cells": True,
        "fresh_lora_init_identical_all_cells": True,
        "fresh_lora_init": fresh_init,
        "jobs": [
            {key: row[key] for key in ("job_id", "attempt", "gpus", "master_port", "gpu_hours")} for row in attempts
        ],
    }
    write(ROOT / protocol["output_root"] / "training" / "training-report.json", report)
    write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": 9, "total": 9})
    print(json.dumps(report, indent=2))


def audit_training_final(protocol, context):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    report = read(ROOT / protocol["output_root"] / "training" / "training-report.json")
    cells = [
        verify_training_cell(ROOT, protocol, context, modality=modality, ordering=ordering)
        for modality in protocol["modalities"]
        for ordering in ORDERINGS
    ]
    verify_all_cells_same_set(protocol, cells)
    fresh_init = _fresh_init_evidence(cells)
    if (
        terminal.get("status") != "succeeded"
        or report.get("status") != "PASS"
        or report.get("cells") != cells
        or report.get("fresh_lora_init_identical_all_cells") is not True
        or report.get("fresh_lora_init") != fresh_init
    ):
        raise ValueError("curriculum aggregate report differs from independent audit")
    print("PASS: all nine curriculum checkpoints and exact exposures independently verified")


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("stage", choices=("run", "audit-training-worker", "finalize-training", "audit-training-final"))
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--worker", type=int, choices=(0, 1))
    args = parser.parse_args(argv)
    protocol = read(args.protocol)
    context = validate_protocol(ROOT, protocol)
    if args.stage in {"run", "audit-training-worker"} and args.worker is None:
        parser.error(f"{args.stage} requires --worker")
    {
        "run": lambda: run(protocol, context, args.worker),
        "audit-training-worker": lambda: audit_training_worker(protocol, context, args.worker),
        "finalize-training": lambda: finalize_training(protocol, context),
        "audit-training-final": lambda: audit_training_final(protocol, context),
    }[args.stage]()


if __name__ == "__main__":
    main()
