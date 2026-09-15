#!/usr/bin/env python
"""Run the interleaved update and second-collection stages of expanded DAgger."""

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

from examples.planning_benchmark_slice.expanded_dagger import collection_checkpoint, validate_protocol
from examples.planning_benchmark_slice.expanded_dagger_collection import (
    _target_token_count,
    cell_report_path,
    collect_cell,
    verify_cell,
)
from examples.planning_benchmark_slice.expanded_dagger_training import (
    prepare_membership,
    train_cell,
    verify_training_cell,
)
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write

PROTOCOL = ROOT / "configs/experiments/expanded-study/dagger-protocol.json"


def assigned(protocol, worker):
    return protocol["launch"]["collection_worker_modalities"][str(worker)]


def head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def require_worker_environment(protocol, worker):
    if os.environ.get("CUDA_VISIBLE_DEVICES") != str(protocol["launch"]["devices"][worker]):
        raise ValueError("DAgger worker GPU differs from the frozen mapping")
    port = int(os.environ["MASTER_PORT"])
    if port not in protocol["launch"]["master_port_pool"]:
        raise ValueError("DAgger worker MASTER_PORT is outside the frozen pool")
    return port


def prepare_training(protocol, context, iteration):
    if iteration == 1:
        evidence = read(ROOT / "docs/experiments/expanded-study/dagger-iteration-1.json")
        if (
            evidence.get("outcome") != "PASS"
            or evidence["scope"]["iteration_one_collection_and_replay_complete"] is not True
        ):
            raise ValueError("Goal 5 iteration-one evidence is incomplete")
    else:
        evidence = read(ROOT / protocol["output_root"] / "collection" / "iteration-2" / "evidence.json")
        if evidence.get("outcome") != "PASS":
            raise ValueError("iteration-two collection evidence is incomplete")
    cells = []
    for modality in protocol["modalities"]:
        for arm in protocol["training"]["arms"]:
            path, membership = prepare_membership(
                ROOT,
                protocol,
                context["source_records"],
                modality=modality,
                arm=arm,
                iteration=iteration,
                target_token_counter=_target_token_count,
            )
            cells.append(
                {
                    "modality": modality,
                    "arm": arm,
                    "membership": str(path.relative_to(ROOT)),
                    "records": membership["record_count"],
                    "unique_corrections": membership["unique_corrections"],
                }
            )
    print(json.dumps({"outcome": "PASS", "iteration": iteration, "cells": cells}, indent=2))


def run_training(protocol, context, worker, iteration):
    port = require_worker_environment(protocol, worker)
    modalities = assigned(protocol, worker)
    total = len(modalities) * len(protocol["training"]["arms"]) * protocol["training"]["optimizer_updates"]
    completed_before = 0
    reports = []
    started = time.monotonic()
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    for modality in modalities:
        for arm in protocol["training"]["arms"]:

            def progress(*, completed, total, eta_seconds, base=completed_before, modality=modality, arm=arm):
                overall = base + completed
                write(
                    progress_path,
                    {
                        "completed": overall,
                        "total": len(modalities)
                        * len(protocol["training"]["arms"])
                        * protocol["training"]["optimizer_updates"],
                        "modality": modality,
                        "arm": arm,
                        "iteration": iteration,
                        "cell_update": completed,
                        "eta_seconds": eta_seconds,
                    },
                )
                print(
                    {
                        "stage": "dagger_training",
                        "modality": modality,
                        "arm": arm,
                        "iteration": iteration,
                        "update": completed,
                    },
                    flush=True,
                )

            reports.append(
                train_cell(
                    ROOT,
                    protocol,
                    context,
                    modality=modality,
                    arm=arm,
                    iteration=iteration,
                    endpoint=protocol["launch"]["backend_endpoints"][worker],
                    progress=progress,
                )
            )
            completed_before += protocol["training"]["optimizer_updates"]
            gc.collect()
            import torch

            torch.cuda.empty_cache()
    report = {
        "schema_version": "expanded_dagger_training_worker_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "iteration": iteration,
        "modalities": modalities,
        "cells": reports,
        "optimizer_updates": sum(row["optimizer_updates"] for row in reports),
        "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
        "master_port": port,
        "runtime_head": head(),
        "elapsed_seconds": time.monotonic() - started,
    }
    write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json", report)
    write(progress_path, {"completed": total, "total": total, "terminal": True})


def audit_training_worker(protocol, context, worker, iteration):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if terminal["status"] != "succeeded":
        raise RuntimeError(f"DAgger training worker stopped: inspect {terminal['directory']}/worker.log")
    report = read(Path(terminal["directory"]) / "worker-result.json")
    modalities = assigned(protocol, worker)
    if (
        report.get("outcome") != "PASS"
        or report.get("worker") != worker
        or report.get("iteration") != iteration
        or report.get("modalities") != modalities
        or report.get("master_port") != terminal["master_port"]
        or terminal["gpus"] != [protocol["launch"]["devices"][worker]]
    ):
        raise ValueError("DAgger training worker provenance differs")
    verified = [
        verify_training_cell(
            ROOT,
            protocol,
            context["source_records"],
            modality=modality,
            arm=arm,
            iteration=iteration,
        )
        for modality in modalities
        for arm in protocol["training"]["arms"]
    ]
    result = {"outcome": "PASS", "worker": worker, "iteration": iteration, "cells": verified}
    write(Path(terminal["directory"]) / "checkpoint-audit.json", result)
    print(json.dumps(result, indent=2))


def latest_attempt(ledger, job_id):
    attempts = [row for row in ledger["attempts"] if row["job_id"] == job_id]
    if not attempts:
        raise ValueError(f"missing scheduler attempt for {job_id}")
    return attempts[-1]


def finalize_training(protocol, context, iteration):
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    attempts = [latest_attempt(ledger, f"dagger-train-{iteration}-{worker}") for worker in range(2)]
    if any(row["status"] != "succeeded" for row in attempts) or any(
        read(Path(row["directory"]) / "hook-result.json").get("returncode") != 0 for row in attempts
    ):
        raise ValueError("DAgger training workers or checkpoint hooks are incomplete")
    cells = [
        verify_training_cell(
            ROOT,
            protocol,
            context["source_records"],
            modality=modality,
            arm=arm,
            iteration=iteration,
        )
        for modality in protocol["modalities"]
        for arm in protocol["training"]["arms"]
    ]
    report = {
        "schema_version": "expanded_dagger_training_iteration_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "iteration": iteration,
        "cells": cells,
        "records": sum(row["records"] for row in cells),
        "optimizer_updates": sum(row["optimizer_updates"] for row in cells),
        "jobs": [
            {key: row[key] for key in ("job_id", "attempt", "gpus", "master_port", "gpu_hours")}
            for row in attempts
        ],
    }
    path = ROOT / protocol["output_root"] / "training" / f"iteration-{iteration}.json"
    write(path, report)
    write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": len(cells), "total": len(cells)})
    print(json.dumps(report, indent=2))


def audit_training_final(protocol, context, iteration):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    path = ROOT / protocol["output_root"] / "training" / f"iteration-{iteration}.json"
    report = read(path)
    if terminal["status"] != "succeeded" or report.get("outcome") != "PASS":
        raise RuntimeError("DAgger training final audit did not complete")
    actual = [
        verify_training_cell(
            ROOT,
            protocol,
            context["source_records"],
            modality=modality,
            arm=arm,
            iteration=iteration,
        )
        for modality in protocol["modalities"]
        for arm in protocol["training"]["arms"]
    ]
    if actual != report["cells"]:
        raise ValueError("DAgger training evidence differs from independent checkpoint verification")
    print(f"PASS: DAgger iteration {iteration} and continued-SFT checkpoints independently verified")


def collect_iteration_two(protocol, context, worker):
    iteration = 2
    port = require_worker_environment(protocol, worker)
    modalities = assigned(protocol, worker)
    maximum = len(modalities) * protocol["collection"]["max_decisions_per_modality_iteration"]
    completed_before = 0
    reports = []
    started = time.monotonic()
    runtime_head = head()
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    for modality in modalities:
        output = cell_report_path(ROOT, protocol, modality, iteration)
        policy = None
        if not output.exists():
            from transformers import set_seed

            from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
            from examples.planning_benchmark_slice.visual_model import VisualPolicy

            set_seed(protocol["collection"]["seed"])
            checkpoint = ROOT / collection_checkpoint(protocol, modality, iteration)
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
            value = policy.generate([example], modality)[0]
            return value, policy.last_generation_usage["generated_sequence_tokens"]

        def progress(modality=modality, base=completed_before, **values):
            completed = base + values["decisions"]
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
            print({"stage": "dagger_collection", "iteration": 2, "modality": modality, **values}, flush=True)

        report, retained = collect_cell(
            ROOT,
            protocol,
            context["source_records"],
            modality=modality,
            iteration=iteration,
            endpoint=protocol["launch"]["backend_endpoints"][worker],
            generate=generate,
            progress=progress,
            runtime_provenance={
                "goal5_runner_commit": protocol["goal5_runner_commit"],
                "runtime_head": runtime_head,
                "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
                "master_port": port,
                "backend_endpoint": protocol["launch"]["backend_endpoints"][worker],
                "model_identity": None if policy is None else policy.identity,
            },
        )
        reports.append(dict(report, retained_cell=retained))
        completed_before += report["collection_decisions"]
        if policy is not None:
            del policy
            gc.collect()
            import torch

            torch.cuda.empty_cache()
    result = {
        "schema_version": "expanded_dagger_collection_worker_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "iteration": iteration,
        "modalities": modalities,
        "cells": reports,
        "collection_decisions": sum(row["collection_decisions"] for row in reports),
        "corrections": sum(row["corrections"] for row in reports),
        "training_updates_before_collection": len(modalities) * protocol["training"]["optimizer_updates"],
        "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
        "master_port": port,
        "runtime_head": runtime_head,
        "elapsed_seconds": time.monotonic() - started,
    }
    write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json", result)
    write(progress_path, {"completed": completed_before, "total": maximum, "terminal": True})


def audit_collection_worker(protocol, context, worker):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if terminal["status"] != "succeeded":
        raise RuntimeError(f"DAgger iteration-two collector stopped: inspect {terminal['directory']}/worker.log")
    report = read(Path(terminal["directory"]) / "worker-result.json")
    modalities = assigned(protocol, worker)
    if (
        report.get("outcome") != "PASS"
        or report.get("worker") != worker
        or report.get("iteration") != 2
        or report.get("modalities") != modalities
        or report.get("master_port") != terminal["master_port"]
        or terminal["gpus"] != [protocol["launch"]["devices"][worker]]
    ):
        raise ValueError("DAgger iteration-two collection worker provenance differs")
    verified = [
        verify_cell(
            ROOT,
            protocol,
            context["source_records"],
            modality=modality,
            iteration=2,
            endpoint=protocol["launch"]["backend_endpoints"][worker],
        )
        for modality in modalities
    ]
    result = {"outcome": "PASS", "worker": worker, "iteration": 2, "cells": verified}
    write(Path(terminal["directory"]) / "independent-replay.json", result)
    print(json.dumps(result, indent=2))


def finalize_collection(protocol, context):
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    attempts = [latest_attempt(ledger, f"dagger-collection-2-{worker}") for worker in range(2)]
    if any(row["status"] != "succeeded" for row in attempts) or any(
        read(Path(row["directory"]) / "hook-result.json").get("returncode") != 0 for row in attempts
    ):
        raise ValueError("DAgger iteration-two collectors or replay hooks are incomplete")
    cells = []
    for modality in protocol["modalities"]:
        worker = next(index for index in range(2) if modality in assigned(protocol, index))
        cells.append(
            verify_cell(
                ROOT,
                protocol,
                context["source_records"],
                modality=modality,
                iteration=2,
                endpoint=protocol["launch"]["backend_endpoints"][worker],
            )
        )
    report = {
        "schema_version": "expanded_dagger_collection_iteration_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "iteration": 2,
        "cells": cells,
        "totals": {
            key: sum(row[key] for row in cells)
            for key in (
                "collection_decisions",
                "accepted_student_operations",
                "invalid_student_operations",
                "expert_queries",
                "corrections",
                "episodes_replayed",
                "corrections_replayed",
                "unique_corrections_for_training",
            )
        },
        "jobs": [
            {key: row[key] for key in ("job_id", "attempt", "gpus", "master_port", "gpu_hours")}
            for row in attempts
        ],
    }
    path = ROOT / protocol["output_root"] / "collection" / "iteration-2" / "evidence.json"
    write(path, report)
    write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": len(cells), "total": len(cells)})
    print(json.dumps(report, indent=2))


def audit_collection_final(protocol, context):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    path = ROOT / protocol["output_root"] / "collection" / "iteration-2" / "evidence.json"
    report = read(path)
    if terminal["status"] != "succeeded" or report.get("outcome") != "PASS":
        raise RuntimeError("DAgger iteration-two final replay did not complete")
    actual = []
    for modality in protocol["modalities"]:
        worker = next(index for index in range(2) if modality in assigned(protocol, index))
        actual.append(
            verify_cell(
                ROOT,
                protocol,
                context["source_records"],
                modality=modality,
                iteration=2,
                endpoint=protocol["launch"]["backend_endpoints"][worker],
            )
        )
    if actual != report["cells"]:
        raise ValueError("DAgger iteration-two evidence differs from independent replay")
    print("PASS: all three DAgger iteration-two correction sets independently replayed and aggregated")


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "prepare-training",
            "train",
            "audit-training-worker",
            "finalize-training",
            "audit-training-final",
            "collect-iteration-two",
            "audit-collection-worker",
            "finalize-collection",
            "audit-collection-final",
        ),
    )
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--worker", type=int, choices=(0, 1))
    parser.add_argument("--iteration", type=int, choices=(1, 2))
    args = parser.parse_args(argv)
    protocol = read(args.protocol)
    context = validate_protocol(ROOT, protocol)
    if args.stage in {
        "prepare-training",
        "train",
        "audit-training-worker",
        "finalize-training",
        "audit-training-final",
    } and args.iteration is None:
        parser.error(f"{args.stage} requires --iteration")
    worker_stages = {"train", "audit-training-worker", "collect-iteration-two", "audit-collection-worker"}
    if args.stage in worker_stages and args.worker is None:
        parser.error(f"{args.stage} requires --worker")
    functions = {
        "prepare-training": lambda: prepare_training(protocol, context, args.iteration),
        "train": lambda: run_training(protocol, context, args.worker, args.iteration),
        "audit-training-worker": lambda: audit_training_worker(protocol, context, args.worker, args.iteration),
        "finalize-training": lambda: finalize_training(protocol, context, args.iteration),
        "audit-training-final": lambda: audit_training_final(protocol, context, args.iteration),
        "collect-iteration-two": lambda: collect_iteration_two(protocol, context, args.worker),
        "audit-collection-worker": lambda: audit_collection_worker(protocol, context, args.worker),
        "finalize-collection": lambda: finalize_collection(protocol, context),
        "audit-collection-final": lambda: audit_collection_final(protocol, context),
    }
    functions[args.stage]()


if __name__ == "__main__":
    main()
