#!/usr/bin/env python
"""Qualify the frozen successor interface without collecting or training."""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import time
from pathlib import Path

from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write
from examples.planning_benchmark_slice.expanded_successor_protocol import (
    load_views,
    training_example,
    validate_protocol,
)
from examples.planning_benchmark_slice.modality_view_preparation import frozen_processor

PROTOCOL = ROOT / "configs/experiments/expanded-study/successor-protocol.json"
EVIDENCE = ROOT / "docs/experiments/expanded-study/successor-qualification.json"


def _examples(protocol, context, views_report, views, modality):
    indexed = {record_id: index for index, record_id in enumerate(protocol["source_record_ids"])}
    ordered = sorted(
        views_report["measurements"],
        key=lambda record_id: views_report["measurements"][record_id]["tokens"][modality]["input"],
    )
    small_id, large_id = ordered[0], ordered[-1]
    return (
        (small_id, training_example(ROOT, protocol, context, views, indexed[small_id], modality)),
        (large_id, training_example(ROOT, protocol, context, views, indexed[large_id], modality)),
    )


def _close(example):
    for image in example["images"]:
        image.close()


def prepare(protocol, context):
    views_report, views = load_views(ROOT, protocol, context)
    processor = frozen_processor()
    envelope = {}
    for modality in protocol["modalities"]:
        rows = []
        for record_id, example in _examples(protocol, context, views_report, views, modality):
            processor.verify_complete(example["messages"], example["images"])
            rows.append(
                {
                    "record_id": record_id,
                    "input_tokens": views_report["measurements"][record_id]["tokens"][modality]["input"],
                    "target_tokens": views_report["measurements"][record_id]["target"],
                }
            )
            _close(example)
        envelope[modality] = rows
    print(
        json.dumps(
            {
                "outcome": "PASS",
                "protocol_id": protocol["protocol_id"],
                "records": 512,
                "training_tasks": protocol["selection"]["task_count"],
                "target_tokens": protocol["model"]["measured_target_tokens"],
                "modalities": envelope,
                "collection_decisions": 0,
                "persistent_training_updates": 0,
            },
            indent=2,
        )
    )


def _inference_probe(protocol, context, views_report, views, modality):
    import torch

    from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
    from examples.planning_benchmark_slice.visual_model import VisualPolicy

    checkpoint = ROOT / protocol["starting_checkpoints"][modality]
    (small_id, small), (large_id, large) = _examples(protocol, context, views_report, views, modality)
    small = {**small, "messages": small["messages"][:-1]}
    large = {**large, "messages": large["messages"][:-1]}
    started = time.monotonic()
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
    with policy._adapter_context("bfs"):
        pass
    load_seconds = time.monotonic() - started
    cases = []
    for name, examples in (("scalar", [large]), ("batch", [large, small]), ("batch_repeat", [large, small])):
        torch.cuda.synchronize()
        then = time.monotonic()
        outputs = policy.generate(examples, adapter_id="bfs", force_full_output=True)
        torch.cuda.synchronize()
        cases.append(
            {
                "name": name,
                "seconds": time.monotonic() - then,
                "input_tokens": policy.last_generation_usage["input_tokens"],
                "generated_tokens": policy.last_generation_usage["generated_sequence_tokens"],
                "raw_unscored_outputs": outputs,
            }
        )
    result = {
        "checkpoint": str(checkpoint.relative_to(ROOT)),
        "small_record_id": small_id,
        "large_record_id": large_id,
        "load_seconds": load_seconds,
        "cases": cases,
        "repeated_batch_byte_identical": cases[1]["raw_unscored_outputs"] == cases[2]["raw_unscored_outputs"],
        "scalar_batch_byte_identical": cases[0]["raw_unscored_outputs"][0] == cases[1]["raw_unscored_outputs"][0],
    }
    del policy
    _close(small)
    _close(large)
    gc.collect()
    torch.cuda.empty_cache()
    return result


def _training_probe(protocol, context, views_report, views, modality):
    import torch

    from examples.planning_benchmark_slice.visual_model import VisualCollator, load_training_model

    checkpoint = ROOT / protocol["starting_checkpoints"][modality]
    tensor = checkpoint / "adapter_model.safetensors"
    before = {"size": tensor.stat().st_size, "mtime_ns": tensor.stat().st_mtime_ns}
    (_small_id, _small), (_large_id, example) = _examples(protocol, context, views_report, views, modality)
    _close(_small)
    batch = VisualCollator(frozen_processor().processor)([example]).to("cuda:0")
    _close(example)
    torch.cuda.reset_peak_memory_stats()
    then = time.monotonic()
    model = load_training_model(context["study"], str(checkpoint))
    load_seconds = time.monotonic() - then
    parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(parameters, lr=protocol["training"]["learning_rate"])
    torch.cuda.synchronize()
    then = time.monotonic()
    optimizer.zero_grad()
    with torch.autocast("cuda", dtype=torch.bfloat16):
        loss = model(**batch).loss
    loss.backward()
    optimizer.step()
    torch.cuda.synchronize()
    step_seconds = time.monotonic() - then
    value = float(loss.detach().cpu())
    result = {
        "load_seconds": load_seconds,
        "optimizer_microstep_seconds": step_seconds,
        "loss": value,
        "loss_finite": math.isfinite(value),
        "trainable_parameters": sum(parameter.numel() for parameter in parameters),
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "source_checkpoint_unchanged": before
        == {"size": tensor.stat().st_size, "mtime_ns": tensor.stat().st_mtime_ns},
        "discarded_in_memory_update": True,
    }
    del batch, loss, optimizer, parameters, model
    gc.collect()
    torch.cuda.empty_cache()
    return result


def run(protocol, context, worker):
    if not protocol.get("goal7_runner_commit"):
        raise ValueError("successor protocol must pin the implemented runner before GPU qualification")
    expected_device = str(protocol["launch"]["devices"][worker])
    expected_port = protocol["launch"]["master_ports"][str(worker)]
    if os.environ.get("CUDA_VISIBLE_DEVICES") != expected_device or int(os.environ["MASTER_PORT"]) != expected_port:
        raise ValueError("successor qualification worker differs from the frozen GPU/port mapping")
    views_report, views = load_views(ROOT, protocol, context)
    assigned = protocol["launch"]["qualification_worker_modalities"][str(worker)]
    results = []
    for index, modality in enumerate(assigned, start=1):
        results.append(
            {
                "modality": modality,
                "inference": _inference_probe(protocol, context, views_report, views, modality),
                "training": _training_probe(protocol, context, views_report, views, modality),
            }
        )
        write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": index, "total": len(assigned)})
        print(json.dumps({"modality": modality, "completed": index, "total": len(assigned)}), flush=True)
    write(
        Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "qualification.json",
        {
            "outcome": "PASS",
            "protocol_id": protocol["protocol_id"],
            "worker": worker,
            "modalities": results,
            "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
            "master_port": int(os.environ["MASTER_PORT"]),
            "scored_model_episodes": 0,
            "collection_decisions": 0,
            "persistent_training_updates": 0,
        },
    )


def audit_worker(protocol, worker):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if terminal["status"] != "succeeded":
        raise RuntimeError(f"successor GPU qualification failed: {terminal['directory']}/worker.log")
    report = read(Path(terminal["directory"]) / "qualification.json")
    assigned = protocol["launch"]["qualification_worker_modalities"][str(worker)]
    if (
        report["outcome"] != "PASS"
        or report["protocol_id"] != protocol["protocol_id"]
        or [row["modality"] for row in report["modalities"]] != assigned
        or report["master_port"] != protocol["launch"]["master_ports"][str(worker)]
        or report["cuda_visible_devices"] != str(protocol["launch"]["devices"][worker])
        or (report["collection_decisions"], report["persistent_training_updates"]) != (0, 0)
    ):
        raise ValueError("successor GPU qualification provenance differs")
    for row in report["modalities"]:
        inference, training = row["inference"], row["training"]
        if (
            [case["name"] for case in inference["cases"]] != ["scalar", "batch", "batch_repeat"]
            or any(case["generated_tokens"] != protocol["model"]["output_tokens"] for case in inference["cases"])
            or not inference["repeated_batch_byte_identical"]
            or not training["loss_finite"]
            or not training["source_checkpoint_unchanged"]
            or not training["discarded_in_memory_update"]
        ):
            raise ValueError("successor inference or trainable-adapter qualification failed")
    print(f"PASS: successor qualification worker {worker}: {', '.join(assigned)}")


def _latest_attempt(ledger, job_id):
    rows = [attempt for attempt in ledger["attempts"] if attempt["job_id"] == job_id]
    if not rows:
        raise ValueError(f"missing scheduler attempt: {job_id}")
    return rows[-1]


def final(protocol, context):
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    worker_reports = {}
    attempts = []
    for worker in range(2):
        attempt = _latest_attempt(ledger, f"successor-qualification-{worker}")
        attempts.append(attempt)
        if attempt["status"] != "succeeded" or read(Path(attempt["directory"]) / "hook-result.json").get(
            "returncode"
        ) != 0:
            raise ValueError("both successor qualification workers and hooks must succeed")
        worker_reports.update(
            {
                row["modality"]: row
                for row in read(Path(attempt["directory"]) / "qualification.json")["modalities"]
            }
        )
    if set(worker_reports) != set(protocol["modalities"]):
        raise ValueError("successor GPU qualification omitted a modality")
    branch_attempts = [attempt for attempt in ledger["attempts"] if attempt["branch"] == "successor_prediction"]
    spent = sum(attempt["gpu_hours"] for attempt in branch_attempts)
    coverage = protocol["qualification"]["coverage_admission"]
    safety = coverage["projection_safety_factor"]
    by_modality = {}
    for modality, row in worker_reports.items():
        inference, training = row["inference"], row["training"]
        batch_seconds = max(case["seconds"] for case in inference["cases"] if case["name"].startswith("batch"))
        collection_seconds = inference["load_seconds"] + math.ceil(512 / 2) * batch_seconds
        training_seconds = training["load_seconds"] + 512 * training["optimizer_microstep_seconds"]
        full_evaluation_seconds = (
            inference["load_seconds"] + math.ceil(coverage["full_model_call_allowance"] / 3 / 2) * batch_seconds
        )
        fallback_evaluation_seconds = (
            inference["load_seconds"] + math.ceil(coverage["fallback_model_call_allowance"] / 3 / 2) * batch_seconds
        )
        by_modality[modality] = {
            "full_output_batch_two_seconds": batch_seconds,
            "trainable_adapter_microstep_seconds": training["optimizer_microstep_seconds"],
            "collection_projection_seconds": collection_seconds,
            "training_projection_seconds": training_seconds,
            "full_evaluation_projection_seconds": full_evaluation_seconds,
            "fallback_evaluation_projection_seconds": fallback_evaluation_seconds,
        }

    base = sum(row["collection_projection_seconds"] + row["training_projection_seconds"] for row in by_modality.values())
    full = spent + safety * (
        base + sum(row["full_evaluation_projection_seconds"] for row in by_modality.values())
    ) / 3600
    fallback = spent + safety * (
        base + sum(row["fallback_evaluation_projection_seconds"] for row in by_modality.values())
    ) / 3600
    cap = protocol["budget"]["gpu_hours"]
    if full <= cap:
        selected = "full"
        unseen_ids = coverage["full_unseen_task_ids"]
        projected = full
    elif fallback <= cap:
        selected = "exact_cost_fallback"
        unseen_ids = coverage["fallback_unseen_task_ids"]
        projected = fallback
    else:
        selected = None
        unseen_ids = []
        projected = fallback
    report = {
        "schema_version": "expanded_successor_qualification_v1",
        "outcome": "PASS" if selected else "VALID_STOP",
        "protocol_id": protocol["protocol_id"],
        "hardware_qualified": True,
        "modalities": by_modality,
        "target_token_measurement": protocol["model"]["measured_target_tokens"],
        "input_token_maxima": read(ROOT / protocol["views"]["successor_scene_report"])["max_tokens"],
        "qualification_gpu_hours_spent": spent,
        "full_coverage_projected_gpu_hours": full,
        "fallback_coverage_projected_gpu_hours": fallback,
        "branch_cap_gpu_hours": cap,
        "selected_coverage": selected,
        "selected_unseen_task_ids": unseen_ids,
        "selected_unseen_task_count": len(unseen_ids),
        "selected_projected_gpu_hours": projected,
        "minimum_coverage_retained": selected is not None,
        "model_outcomes_used_for_coverage_selection": False,
        "collection_started": False,
        "persistent_training_updates": 0,
        "scalar_batch_divergence_reported": {
            modality: not row["inference"]["scalar_batch_byte_identical"] for modality, row in worker_reports.items()
        },
        "jobs": [
            {key: attempt[key] for key in ("job_id", "attempt", "gpus", "master_port", "gpu_hours")}
            for attempt in attempts
        ],
    }
    write(EVIDENCE, report)
    write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": 3, "total": 3})
    print(json.dumps(report, indent=2))
    if report["outcome"] != "PASS":
        raise RuntimeError("VALID_STOP: successor exact-cost fallback exceeds the branch cap")


def audit_final(protocol, context):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    report = read(EVIDENCE)
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    attempts = [_latest_attempt(ledger, f"successor-qualification-{worker}") for worker in range(2)]
    if (
        terminal["status"] != "succeeded"
        or report["outcome"] != "PASS"
        or not report["hardware_qualified"]
        or any(attempt["status"] != "succeeded" for attempt in attempts)
        or [attempt["master_port"] for attempt in attempts] != [18802, 18803]
        or any(read(Path(attempt["directory"]) / "hook-result.json").get("returncode") != 0 for attempt in attempts)
        or report["qualification_gpu_hours_spent"]
        != sum(attempt["gpu_hours"] for attempt in ledger["attempts"] if attempt["branch"] == "successor_prediction")
        or not report["minimum_coverage_retained"]
        or report["model_outcomes_used_for_coverage_selection"]
        or report["collection_started"]
        or report["persistent_training_updates"] != 0
        or report["target_token_measurement"] != protocol["model"]["measured_target_tokens"]
        or len(context["contracts"]) != 512
    ):
        raise RuntimeError("successor protocol qualification did not pass")
    print(
        f"PASS: frozen successor protocol, hardware paths and {report['selected_coverage']} cost admission"
    )


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
        audit_worker(protocol, args.worker)
    elif args.stage == "final":
        final(protocol, context)
    else:
        audit_final(protocol, context)


if __name__ == "__main__":
    main()
