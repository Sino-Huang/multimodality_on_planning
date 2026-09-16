#!/usr/bin/env python
"""Collect, replay and release the frozen expanded successor dataset."""

from __future__ import annotations

import argparse
import gc
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, timestamp, write
from examples.planning_benchmark_slice.expanded_successor_collection import (
    cell_report_path,
    collect_cell,
    publish_release,
    release_root,
    verify_cell,
    verify_release,
)
from examples.planning_benchmark_slice.expanded_successor_protocol import load_views, validate_protocol
from examples.planning_benchmark_slice.scene_assets import read_json

PROTOCOL = ROOT / "configs/experiments/expanded-study/successor-protocol.json"
QUALIFICATION = ROOT / "docs/experiments/expanded-study/successor-qualification.json"
EVIDENCE = ROOT / "docs/experiments/expanded-study/successor-data.json"


def _assigned(protocol, worker):
    return protocol["launch"]["qualification_worker_modalities"][str(worker)]


def _head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _latest_attempt(ledger, job_id):
    rows = [attempt for attempt in ledger["attempts"] if attempt["job_id"] == job_id]
    if not rows:
        raise ValueError(f"missing scheduler attempt: {job_id}")
    return rows[-1]


def prepare(protocol, context):
    qualification = read(QUALIFICATION)
    views_report, _views = load_views(ROOT, protocol, context)
    if (
        qualification.get("outcome") != "PASS"
        or qualification.get("protocol_id") != protocol["protocol_id"]
        or not qualification.get("minimum_coverage_retained")
        or qualification.get("collection_started")
        or qualification.get("persistent_training_updates") != 0
    ):
        raise ValueError("successor collection requires the frozen passing Goal 7 qualification")
    report = {
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "membership_id": context["membership_id"],
        "records_per_modality": protocol["collection"]["records_per_modality"],
        "modalities": protocol["modalities"],
        "training_tasks": protocol["selection"]["task_count"],
        "prepared_view_records": views_report["counts"]["records"],
        "existing_cells": [
            modality for modality in protocol["modalities"] if cell_report_path(ROOT, protocol, modality).exists()
        ],
        "existing_release": (release_root(ROOT, protocol) / "report.json").exists(),
        "training_updates": 0,
    }
    print(json.dumps(report, indent=2))


def run(protocol, context, worker):
    expected_device = str(protocol["launch"]["devices"][worker])
    master_port = int(os.environ["MASTER_PORT"])
    if (
        os.environ.get("CUDA_VISIBLE_DEVICES") != expected_device
        or master_port not in protocol["launch"]["master_port_pool"]
    ):
        raise ValueError("successor collection worker differs from its frozen GPU/port mapping")
    views_report, views = load_views(ROOT, protocol, context)
    assigned = _assigned(protocol, worker)
    maximum = len(assigned) * protocol["collection"]["records_per_modality"]
    completed_before = 0
    results = []
    started = time.monotonic()
    runtime_head = _head()
    cutoff = timestamp(protocol["budget"]["gpu_cutoff_utc"])
    for modality in assigned:
        policy = None
        if not cell_report_path(ROOT, protocol, modality).exists():
            from transformers import set_seed

            from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
            from examples.planning_benchmark_slice.visual_model import VisualPolicy

            set_seed(protocol["training"]["seed"])
            checkpoint = ROOT / protocol["starting_checkpoints"][modality]
            policy = VisualPolicy(
                model_id=protocol["model"]["id"],
                revision=protocol["model"]["revision"],
                adapter_paths={"bfs": str(checkpoint)},
                device="cuda:0",
                max_context_tokens=protocol["model"]["context_tokens"],
                max_new_tokens=protocol["model"]["output_tokens"],
                max_batch_size=2,
                max_batch_input_tokens=24000,
                inference_dtype=protocol["model"]["inference_dtype"],
            )
            configure_visual_attention(policy.model, protocol["model"]["attention"])
            policy.identity.update(memoize_identical_inputs=False)
            policy.stop_at = time.monotonic() + max(0, cutoff - time.time())

        def generate(examples, policy=policy):
            outputs = policy.generate(examples, adapter_id="bfs")
            return outputs, dict(policy.last_generation_usage)

        def progress(completed, total, record_id, modality=modality, completed_before=completed_before):
            overall = completed_before + completed
            elapsed = time.monotonic() - started
            values = {
                "completed": overall,
                "total": maximum,
                "modality": modality,
                "modality_completed": completed,
                "record_id": record_id,
                "eta_seconds": elapsed * (maximum - overall) / overall if overall else None,
            }
            write(os.environ["EXPANDED_PROGRESS_PATH"], values)
            print(json.dumps({"stage": "successor_collection", **values}), flush=True)

        provenance = {
            "runtime_head": runtime_head,
            "cuda_visible_devices": expected_device,
            "master_port": master_port,
            "checkpoint": protocol["starting_checkpoints"][modality],
            "model_identity": None if policy is None else policy.identity,
            "decoding": protocol["model"]["decoding"],
        }
        report, retained = collect_cell(
            ROOT,
            protocol,
            context,
            views,
            modality=modality,
            generate=generate,
            progress=progress,
            runtime_provenance=provenance,
        )
        results.append({**report, "retained_cell": retained})
        completed_before += report["records"]
        if policy is not None:
            del policy
            gc.collect()
            import torch

            torch.cuda.empty_cache()
    worker_report = {
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "modalities": assigned,
        "cells": results,
        "records": sum(row["records"] for row in results),
        "training_updates": 0,
        "cuda_visible_devices": expected_device,
        "master_port": master_port,
        "runtime_head": runtime_head,
        "elapsed_seconds": time.monotonic() - started,
        "prepared_membership_id": views_report["membership_id"],
    }
    write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json", worker_report)
    write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": completed_before, "total": maximum, "terminal": True})


def audit_worker(protocol, context, worker):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if terminal["status"] != "succeeded":
        raise RuntimeError(f"successor collection worker stopped: inspect {terminal['directory']}/worker.log")
    result = read(Path(terminal["directory"]) / "worker-result.json")
    assigned = _assigned(protocol, worker)
    _views_report, views = load_views(ROOT, protocol, context)
    cells = [verify_cell(ROOT, protocol, context, views, modality=modality) for modality in assigned]
    if (
        result.get("outcome") != "PASS"
        or result.get("protocol_id") != protocol["protocol_id"]
        or result.get("worker") != worker
        or result.get("modalities") != assigned
        or result.get("training_updates") != 0
        or result.get("master_port") != terminal["master_port"]
        or terminal["master_port"] not in protocol["launch"]["master_port_pool"]
        or terminal["gpus"] != [protocol["launch"]["devices"][worker]]
        or [dict(row, retained_cell=result["cells"][index]["retained_cell"]) for index, row in enumerate(cells)]
        != result["cells"]
    ):
        raise ValueError("successor collection worker evidence differs from independent replay")
    audit = {
        "outcome": "PASS",
        "worker": worker,
        "modalities": assigned,
        "records_replayed": sum(row["records"] for row in cells),
        "cells": cells,
    }
    write(Path(terminal["directory"]) / "independent-replay.json", audit)
    print(json.dumps(audit, indent=2))


def final(protocol, context):
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    attempts = [_latest_attempt(ledger, f"successor-collection-{worker}") for worker in range(2)]
    if (
        any(attempt["status"] != "succeeded" for attempt in attempts)
        or len({attempt["master_port"] for attempt in attempts}) != 2
        or any(read(Path(attempt["directory"]) / "hook-result.json").get("returncode") != 0 for attempt in attempts)
    ):
        raise ValueError("both successor collection workers and independent replay hooks must pass")
    _views_report, views = load_views(ROOT, protocol, context)
    release = publish_release(ROOT, protocol, context, views)
    collection_gpu_hours = sum(attempt["gpu_hours"] for attempt in attempts)
    cumulative = sum(
        attempt["gpu_hours"] for attempt in ledger["attempts"] if attempt["branch"] == "successor_prediction"
    )
    failure_kinds = Counter()
    for cell in release["cells"].values():
        failure_kinds.update(cell["verification_outcomes"])
    evidence = {
        "schema_version": "expanded_successor_data_evidence_v1",
        "outcome": "PASS",
        "goal": 8,
        "issues": [87, 88],
        "protocol_id": protocol["protocol_id"],
        "release": release,
        "coverage": {
            "modalities": protocol["modalities"],
            "records_per_modality": protocol["collection"]["records_per_modality"],
            "total_interactions": release["total_interactions"],
            "training_tasks": protocol["selection"]["task_count"],
            "split": "train",
            "verification_outcomes": dict(sorted(failure_kinds.items())),
            "missing_records": 0,
        },
        "execution": {
            "jobs": [attempt["job_id"] for attempt in attempts],
            "attempts": [attempt["attempt"] for attempt in attempts],
            "physical_gpus": [attempt["gpus"] for attempt in attempts],
            "master_ports": [attempt["master_port"] for attempt in attempts],
            "collection_gpu_hours": collection_gpu_hours,
            "cumulative_successor_gpu_hours": cumulative,
            "branch_cap_gpu_hours": protocol["budget"]["gpu_hours"],
            "runtime_heads": sorted(
                {
                    row["runtime_provenance"]["runtime_head"]
                    for modality in protocol["modalities"]
                    for row in [read_json(ROOT / release["cells"][modality]["record_paths"][0])]
                }
            ),
        },
        "controls": {
            "raw_predictions_retained": True,
            "trusted_labels_separate": True,
            "incorrect_predictions_repaired": 0,
            "trusted_states_substituted": 0,
            "final_or_development_records": 0,
            "persistent_training_updates": 0,
            "model_outcome_selected_membership": False,
        },
    }
    if cumulative > protocol["budget"]["gpu_hours"]:
        raise ValueError("successor collection exceeded its branch GPU-hour ceiling")
    write(EVIDENCE, evidence)
    write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": 3, "total": 3})
    print(json.dumps(evidence, indent=2))


def audit_final(protocol, context):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if terminal["status"] != "succeeded":
        raise RuntimeError("successor release finalizer did not succeed")
    _views_report, views = load_views(ROOT, protocol, context)
    release = verify_release(ROOT, protocol, context, views)
    evidence = read(EVIDENCE)
    if (
        evidence.get("outcome") != "PASS"
        or evidence.get("release") != release
        or evidence.get("coverage", {}).get("total_interactions") != 1536
        or evidence.get("coverage", {}).get("missing_records") != 0
        or evidence.get("controls", {}).get("persistent_training_updates") != 0
        or evidence.get("controls", {}).get("trusted_states_substituted") != 0
    ):
        raise ValueError("published successor data evidence differs from independent replay")
    print("PASS: all 1,536 successor interactions and separate training labels independently replayed")


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
