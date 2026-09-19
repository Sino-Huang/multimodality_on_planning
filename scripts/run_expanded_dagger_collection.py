#!/usr/bin/env python
"""Collect and independently verify expanded DAgger iteration one."""

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
from examples.planning_benchmark_slice.expanded_dagger import validate_protocol
from examples.planning_benchmark_slice.expanded_dagger_collection import (
    cell_report_path,
    collect_cell,
    verify_cell,
)
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write

PROTOCOL = ROOT / "configs/experiments/expanded-study/dagger-protocol.json"
EVIDENCE = ROOT / "docs/experiments/expanded-study/dagger-iteration-1.json"


def _assigned(protocol, worker):
    return protocol["launch"]["collection_worker_modalities"][str(worker)]


def _head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def prepare(protocol, context):
    report = {
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "iteration": 1,
        "source_records": len(context["source_records"]),
        "training_tasks": len(protocol["collection"]["task_order"]),
        "modalities": protocol["modalities"],
        "decision_quota_per_modality": protocol["collection"]["max_decisions_per_modality_iteration"],
        "correction_quota_per_modality": protocol["collection"]["max_corrections_per_modality_iteration"],
        "existing_cells": [
            modality
            for modality in protocol["modalities"]
            if cell_report_path(ROOT, protocol, modality, 1).exists()
        ],
        "training_updates": 0,
    }
    print(json.dumps(report, indent=2))


def run(protocol, context, worker):
    if not protocol.get("goal5_runner_commit"):
        raise ValueError("DAgger collection protocol must pin the Goal 5 runner commit")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != str(protocol["launch"]["devices"][worker]):
        raise ValueError("DAgger collection GPU differs from frozen worker mapping")
    master_port = int(os.environ["MASTER_PORT"])
    if master_port not in protocol["launch"]["master_port_pool"]:
        raise ValueError("DAgger collection MASTER_PORT is outside the frozen pool")
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    assigned = _assigned(protocol, worker)
    maximum = len(assigned) * protocol["collection"]["max_decisions_per_modality_iteration"]
    completed_before = 0
    cell_reports = []
    started = time.monotonic()
    runtime_head = _head()
    for modality in assigned:
        output = cell_report_path(ROOT, protocol, modality, 1)
        policy = None
        if not output.exists():
            from transformers import set_seed

            from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
            from examples.planning_benchmark_slice.visual_model import VisualPolicy

            set_seed(protocol["collection"]["seed"])
            checkpoint = ROOT / protocol["starting_checkpoints"][modality]
            policy = VisualPolicy(
                model_id=protocol["model"]["id"],
                revision=protocol["model"]["revision"],
                adapter_paths={modality: checkpoint},
                device="cuda:0",
                max_context_tokens=protocol["model"]["context_tokens"],
                max_new_tokens=protocol["model"]["output_tokens"],
                max_batch_size=1,
                max_batch_input_tokens=protocol["model"]["maximum_input_tokens"],
                inference_dtype=protocol["model"]["inference_dtype"],
            )
            configure_visual_attention(policy.model, protocol["model"]["attention"])
            policy.identity.update(memoize_identical_inputs=False)

        def generate(example, policy=policy, modality=modality):
            output_text = policy.generate([example], modality)[0]
            return output_text, policy.last_generation_usage["generated_sequence_tokens"]

        def progress(modality=modality, completed_before=completed_before, **values):
            completed = completed_before + values["decisions"]
            elapsed = time.monotonic() - started
            write(
                progress_path,
                {
                    "completed": completed,
                    "total": maximum,
                    "modality": modality,
                    "task_id": values["task_id"],
                    "collection_decisions": values["decisions"],
                    "corrections": values["corrections"],
                    "eta_seconds": elapsed * (maximum - completed) / completed if completed else None,
                },
            )
            print({"stage": "dagger_collection", "modality": modality, **values}, flush=True)

        report, retained = collect_cell(
            ROOT,
            protocol,
            context["source_records"],
            modality=modality,
            iteration=1,
            endpoint=protocol["launch"]["backend_endpoints"][worker],
            generate=generate,
            progress=progress,
            runtime_provenance={
                "goal5_runner_commit": protocol["goal5_runner_commit"],
                "runtime_head": runtime_head,
                "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
                "master_port": master_port,
                "backend_endpoint": protocol["launch"]["backend_endpoints"][worker],
                "model_identity": None if policy is None else policy.identity,
            },
        )
        report = dict(report, retained_cell=retained)
        cell_reports.append(report)
        completed_before += report["collection_decisions"]
        if policy is not None:
            del policy
            gc.collect()
            import torch

            torch.cuda.empty_cache()
    worker_report = {
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "iteration": 1,
        "modalities": assigned,
        "cells": cell_reports,
        "collection_decisions": sum(row["collection_decisions"] for row in cell_reports),
        "corrections": sum(row["corrections"] for row in cell_reports),
        "training_updates": 0,
        "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
        "master_port": master_port,
        "runtime_head": runtime_head,
        "elapsed_seconds": time.monotonic() - started,
    }
    path = ROOT / protocol["output_root"] / "collection" / "iteration-1" / "workers" / f"worker-{worker}.json"
    write(path, worker_report)
    write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json", worker_report)
    write(progress_path, {"completed": completed_before, "total": maximum, "terminal": True})


def audit_worker(protocol, context, worker):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if terminal["status"] != "succeeded":
        raise RuntimeError(f"DAgger collection worker stopped: inspect {terminal['directory']}/worker.log")
    worker_report = read(Path(terminal["directory"]) / "worker-result.json")
    assigned = _assigned(protocol, worker)
    if (
        worker_report["outcome"] != "PASS"
        or worker_report["protocol_id"] != protocol["protocol_id"]
        or worker_report["worker"] != worker
        or worker_report["modalities"] != assigned
        or worker_report["training_updates"] != 0
        or worker_report["master_port"] != terminal["master_port"]
        or terminal["master_port"] not in protocol["launch"]["master_port_pool"]
        or terminal["gpus"] != [protocol["launch"]["devices"][worker]]
        or terminal["max_seconds"] != protocol["launch"]["collection_worker_max_seconds"][str(worker)]
    ):
        raise ValueError("DAgger collection worker provenance differs")
    verified = [
        verify_cell(
            ROOT,
            protocol,
            context["source_records"],
            modality=modality,
            iteration=1,
            endpoint=protocol["launch"]["backend_endpoints"][worker],
        )
        for modality in assigned
    ]
    report = {
        "outcome": "PASS",
        "worker": worker,
        "iteration": 1,
        "cells": verified,
        "episodes_replayed": sum(row["episodes_replayed"] for row in verified),
        "corrections_replayed": sum(row["corrections_replayed"] for row in verified),
    }
    write(Path(terminal["directory"]) / "independent-replay.json", report)
    print(json.dumps(report, indent=2))


def _latest_attempt(ledger, job_id):
    return [attempt for attempt in ledger["attempts"] if attempt["job_id"] == job_id][-1]


def final(protocol, context):
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    attempts = [_latest_attempt(ledger, f"dagger-collection-{worker}") for worker in range(2)]
    if any(attempt["status"] != "succeeded" for attempt in attempts):
        raise ValueError("both DAgger iteration-one collection workers must succeed")
    if len({attempt["master_port"] for attempt in attempts}) != 2:
        raise ValueError("DAgger collection workers did not retain distinct MASTER_PORT values")
    if any(read(Path(attempt["directory"]) / "hook-result.json").get("returncode") != 0 for attempt in attempts):
        raise ValueError("a DAgger collection completion audit failed")
    verifications = []
    for modality in protocol["modalities"]:
        worker = next(index for index in range(2) if modality in _assigned(protocol, index))
        verifications.append(
            verify_cell(
                ROOT,
                protocol,
                context["source_records"],
                modality=modality,
                iteration=1,
                endpoint=protocol["launch"]["backend_endpoints"][worker],
            )
        )
    collection_gpu_hours = sum(attempt["gpu_hours"] for attempt in attempts)
    cumulative_gpu_hours = sum(attempt["gpu_hours"] for attempt in ledger["attempts"] if attempt["branch"] == "dagger")
    report = {
        "schema_version": "expanded_dagger_iteration_one_evidence_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "goal": 5,
        "iteration": 1,
        "source_records": len(context["source_records"]),
        "training_tasks": len(protocol["collection"]["task_order"]),
        "cells": verifications,
        "totals": {
            "collection_decisions": sum(row["collection_decisions"] for row in verifications),
            "invalid_student_operations": sum(row["invalid_student_operations"] for row in verifications),
            "expert_queries": sum(row["expert_queries"] for row in verifications),
            "corrections": sum(row["corrections"] for row in verifications),
            "unique_corrections_for_training": sum(
                row["unique_corrections_for_training"] for row in verifications
            ),
            "episodes_replayed": sum(row["episodes_replayed"] for row in verifications),
            "corrections_replayed": sum(row["corrections_replayed"] for row in verifications),
            "training_updates": 0,
        },
        "aggregation": {
            "records_per_modality": protocol["training"]["records_per_update"],
            "optimizer_updates_per_future_update": protocol["training"]["optimizer_updates"],
            "membership_verified": True,
            "split_isolation_verified": True,
            "invented_or_duplicated_corrections": 0,
        },
        "execution": {
            "jobs": [attempt["job_id"] for attempt in attempts],
            "attempts": [attempt["attempt"] for attempt in attempts],
            "physical_gpus": [attempt["gpus"] for attempt in attempts],
            "master_ports": [attempt["master_port"] for attempt in attempts],
            "collection_gpu_hours": collection_gpu_hours,
            "cumulative_dagger_gpu_hours": cumulative_gpu_hours,
            "branch_cap_gpu_hours": protocol["budget"]["gpu_hours"],
        },
        "scope": {
            "iteration_one_collection_and_replay_complete": True,
            "iteration_two_complete": False,
            "training_updates_run": False,
            "issues_80_through_83_remain_open_for_goal_6": True,
        },
    }
    if cumulative_gpu_hours > protocol["budget"]["gpu_hours"]:
        raise ValueError("DAgger branch GPU-hour ceiling exceeded")
    write(EVIDENCE, report)
    write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": 3, "total": 3})
    print(json.dumps(report, indent=2))


def audit_final(protocol, context):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    report = read(EVIDENCE)
    if terminal["status"] != "succeeded" or report["outcome"] != "PASS":
        raise RuntimeError("DAgger iteration-one final audit did not complete")
    actual = []
    for modality in protocol["modalities"]:
        worker = next(index for index in range(2) if modality in _assigned(protocol, index))
        actual.append(
            verify_cell(
                ROOT,
                protocol,
                context["source_records"],
                modality=modality,
                iteration=1,
                endpoint=protocol["launch"]["backend_endpoints"][worker],
            )
        )
    if report["cells"] != actual or report["totals"]["corrections_replayed"] != sum(
        row["corrections_replayed"] for row in actual
    ):
        raise ValueError("published DAgger iteration-one evidence differs from independent replay")
    print("PASS: all three DAgger iteration-one correction sets independently replayed and aggregated")


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("stage", choices=("prepare", "run", "audit-worker", "final", "audit-final"))
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--worker", type=int, choices=(0, 1))
    args = parser.parse_args(argv)
    protocol = read(args.protocol)
    context = validate_protocol(ROOT, protocol)
    if args.stage == "prepare":
        prepare(protocol, context)
    elif args.stage == "run":
        if args.worker is None:
            parser.error("run requires --worker")
        run(protocol, context, args.worker)
    elif args.stage == "audit-worker":
        if args.worker is None:
            parser.error("audit-worker requires --worker")
        audit_worker(protocol, context, args.worker)
    elif args.stage == "final":
        final(protocol, context)
    else:
        audit_final(protocol, context)


if __name__ == "__main__":
    main()
