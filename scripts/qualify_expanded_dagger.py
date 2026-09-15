#!/usr/bin/env python
"""Qualify the frozen expanded DAgger interface without collecting corrections."""

from __future__ import annotations

import argparse
import gc
import gzip
import json
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_dagger import validate_protocol  # noqa: E402
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write  # noqa: E402
from examples.planning_benchmark_slice.modality_view_preparation import frozen_processor  # noqa: E402


PROTOCOL = ROOT / "configs/experiments/expanded-study/dagger-protocol.json"


def _example(context, modality, *, largest):
    row = (max if largest else min)(context["source_records"], key=lambda item: item["tokens"]["input"][modality])
    return row, context["corpus"].training_example(row, modality)


def _close(example):
    for image in example["images"]:
        image.close()


def prepare(protocol, context):
    processor = frozen_processor()
    envelope = {}
    for modality in protocol["modalities"]:
        rows = []
        for largest in (False, True):
            row, example = _example(context, modality, largest=largest)
            processor.verify_complete(example["messages"], example["images"])
            rows.append({"record_id": row["record_id"], "input_tokens": row["tokens"]["input"][modality]})
            _close(example)
        envelope[modality] = rows
    report = {
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "source_records": len(context["source_records"]),
        "training_tasks": len(protocol["collection"]["task_order"]),
        "modalities": envelope,
        "collection_decisions": 0,
        "corrections": 0,
        "training_updates": 0,
    }
    print(json.dumps(report, indent=2))


def _inference_probe(protocol, context, modality):
    import torch

    from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
    from examples.planning_benchmark_slice.visual_model import VisualPolicy

    checkpoint = ROOT / protocol["starting_checkpoints"][modality]
    small_row, small = _example(context, modality, largest=False)
    large_row, large = _example(context, modality, largest=True)
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
        "small_record_id": small_row["record_id"],
        "large_record_id": large_row["record_id"],
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


def _training_probe(protocol, context, modality):
    import torch

    from examples.planning_benchmark_slice.visual_model import VisualCollator, load_training_model

    checkpoint = ROOT / protocol["starting_checkpoints"][modality]
    tensor = checkpoint / "adapter_model.safetensors"
    before = {"size": tensor.stat().st_size, "mtime_ns": tensor.stat().st_mtime_ns}
    _, example = _example(context, modality, largest=True)
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
        "optimizer_step_seconds": step_seconds,
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
    if protocol["goal4_runner_commit"] is None:
        raise ValueError("DAgger protocol must pin the implemented runner commit before GPU qualification")
    assigned = protocol["launch"]["qualification_worker_modalities"][str(worker)]
    results = []
    for index, modality in enumerate(assigned, start=1):
        result = {
            "modality": modality,
            "inference": _inference_probe(protocol, context, modality),
            "training": _training_probe(protocol, context, modality),
        }
        results.append(result)
        write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": index, "total": len(assigned)})
        print(json.dumps({"modality": modality, "completed": index, "total": len(assigned)}), flush=True)
    report = {
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "modalities": results,
        "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
        "master_port": int(os.environ["MASTER_PORT"]),
        "scored_model_episodes": 0,
        "collection_decisions": 0,
        "corrections": 0,
        "persistent_training_updates": 0,
    }
    write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "qualification.json", report)


def audit_worker(protocol, worker):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if terminal["status"] != "succeeded":
        raise RuntimeError(f"DAgger GPU qualification failed: {terminal['directory']}/worker.log")
    report = read(Path(terminal["directory"]) / "qualification.json")
    assigned = protocol["launch"]["qualification_worker_modalities"][str(worker)]
    if (
        report["outcome"] != "PASS"
        or report["protocol_id"] != protocol["protocol_id"]
        or [row["modality"] for row in report["modalities"]] != assigned
        or report["master_port"] != protocol["launch"]["master_ports"][worker]
        or (report["collection_decisions"], report["corrections"], report["persistent_training_updates"])
        != (0, 0, 0)
    ):
        raise ValueError("DAgger GPU qualification provenance differs")
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
            raise ValueError("DAgger GPU inference or trainable-adapter qualification failed")
    print(f"PASS: DAgger qualification worker {worker}: {', '.join(assigned)}")


def _latest_attempt(ledger, job_id):
    return [attempt for attempt in ledger["attempts"] if attempt["job_id"] == job_id][-1]


def _historical_calls(modality):
    unseen = ROOT / "outputs/expanded-study/v1/baseline/episodes" / modality
    unseen_calls = 0
    for path in unseen.rglob("bfs-process_sft.json.gz"):
        with gzip.open(path, "rt") as stream:
            unseen_calls += json.load(stream)["result"]["decision_count"]
    development = ROOT / "outputs/matched_modalities/v5/evaluation" / modality
    development_calls = 0
    for path in development.rglob("bfs-process_sft.json.gz"):
        with gzip.open(path, "rt") as stream:
            development_calls += json.load(stream)["result"]["decision_count"]
    return unseen_calls + development_calls


def final(protocol):
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    worker_reports = {}
    for worker in range(2):
        attempt = _latest_attempt(ledger, f"dagger-qualification-{worker}")
        if attempt["status"] != "succeeded":
            raise ValueError("both DAgger GPU qualification workers must succeed")
        worker_reports.update(
            {
                row["modality"]: row
                for row in read(Path(attempt["directory"]) / "qualification.json")["modalities"]
            }
        )
    if set(worker_reports) != set(protocol["modalities"]):
        raise ValueError("DAgger GPU qualification omitted a modality")
    development = read(ROOT / protocol["evaluation"]["development_panel"])
    unseen = read(ROOT / protocol["evaluation"]["unseen_panel"])
    reference_decisions = sum(
        task["row"]["reference_costs"]["bfs"]["decisions"] for panel in (development, unseen) for task in panel["tasks"]
    )
    historical = {
        worker: read(ROOT / f"outputs/matched_modalities/v5/qualification/gpu-{worker}.json")
        for worker in range(2)
    }
    by_modality = {}
    for modality, row in worker_reports.items():
        inference, training = row["inference"], row["training"]
        call = max(case["seconds"] / len(case["input_tokens"]) for case in inference["cases"])
        historical_training = max(
            report["modalities"][modality]["training_microstep_seconds"] for report in historical.values()
        )
        microstep = max(training["optimizer_step_seconds"], historical_training)
        collection = 2 * (inference["load_seconds"] + 512 * call)
        train = 4 * (training["load_seconds"] + 512 * microstep)
        full_evaluation_calls = 2 * 2 * reference_decisions
        conditional_evaluation_calls = 2 * _historical_calls(modality)
        by_modality[modality] = {
            "full_output_seconds_per_decision": call,
            "trainable_adapter_microstep_seconds": microstep,
            "collection_allowance_seconds": collection,
            "training_allowance_seconds": train,
            "full_evaluation_call_allowance": full_evaluation_calls,
            "full_evaluation_allowance_seconds": inference["load_seconds"] + full_evaluation_calls * call,
            "historical_consumption_evaluation_calls": conditional_evaluation_calls,
            "conditional_evaluation_seconds": inference["load_seconds"] + conditional_evaluation_calls * call,
        }
    spent = sum(attempt["gpu_hours"] for attempt in ledger["attempts"] if attempt["branch"] == "dagger")
    safety = protocol["budget"]["qualification_safety_factor"]
    full = spent + safety * sum(
        row["collection_allowance_seconds"]
        + row["training_allowance_seconds"]
        + row["full_evaluation_allowance_seconds"]
        for row in by_modality.values()
    ) / 3600
    conditional = spent + safety * sum(
        row["collection_allowance_seconds"]
        + row["training_allowance_seconds"]
        + row["conditional_evaluation_seconds"]
        for row in by_modality.values()
    ) / 3600
    report = {
        "outcome": "PASS" if conditional <= protocol["budget"]["gpu_hours"] else "VALID_STOP",
        "protocol_id": protocol["protocol_id"],
        "hardware_qualified": True,
        "modalities": by_modality,
        "qualification_gpu_hours_spent": spent,
        "full_allowance_gpu_hours": full,
        "full_allowance_completion_guaranteed": full <= protocol["budget"]["gpu_hours"],
        "conditional_historical_consumption_gpu_hours": conditional,
        "conditional_cost_admission": conditional <= protocol["budget"]["gpu_hours"],
        "branch_cap_gpu_hours": protocol["budget"]["gpu_hours"],
        "model_outcomes_used_for_coverage_selection": False,
        "coverage_reduction": None,
        "collection_started": False,
        "persistent_training_updates": 0,
        "scalar_batch_divergence_reported": {
            modality: not row["inference"]["scalar_batch_byte_identical"] for modality, row in worker_reports.items()
        },
    }
    write(ROOT / "docs/experiments/expanded-study/dagger-qualification.json", report)
    write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": 3, "total": 3})
    print(json.dumps(report, indent=2))
    if report["outcome"] != "PASS":
        raise RuntimeError("VALID_STOP: DAgger conditional cost admission exceeds the branch cap")


def audit_final():
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    report = read(ROOT / "docs/experiments/expanded-study/dagger-qualification.json")
    if terminal["status"] != "succeeded" or report["outcome"] != "PASS" or not report["hardware_qualified"]:
        raise RuntimeError("DAgger protocol qualification did not pass")
    print("PASS: frozen DAgger protocol, hardware paths and conditional cost admission")


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
        final(protocol)
    else:
        audit_final()


if __name__ == "__main__":
    main()
