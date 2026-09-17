#!/usr/bin/env python
"""Run, replay, and summarize modality-matched expanded curriculum evaluation."""

from __future__ import annotations

import argparse
import copy
import gc
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.planning_benchmark_slice.expanded_curriculum_analysis import analyze
from examples.planning_benchmark_slice.expanded_curriculum_evaluation import (
    COMPARATORS,
    matched_arms,
    paired_rows,
    panels,
    run_cell,
    summarize,
    validate_comparator_sources,
    verify_comparator,
    verify_episode,
)
from examples.planning_benchmark_slice.expanded_curriculum_training import REPORT_SCHEMA, validate_protocol
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write
from examples.planning_benchmark_slice.expanded_successor_training import _sha256

PROTOCOL = ROOT / "configs/experiments/expanded-study/curriculum-protocol.json"


def assigned(protocol, worker):
    return protocol["launch"]["evaluation_worker_modalities"][str(worker)]


def _head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def require_training_gate(root: Path, protocol):
    path = root / protocol["output_root"] / "training" / "training-report.json"
    if not path.is_file():
        raise RuntimeError("curriculum evaluation requires a PASS training report")
    report = read(path)
    expected = {(m, o) for m in protocol["modalities"] for o in protocol["orderings"]}
    cells = report.get("cells", [])
    init_fingerprints = {row.get("fresh_lora_init_sha256") for row in cells}
    init_tensor_counts = {row.get("fresh_lora_init_tensors") for row in cells}
    if (
        report.get("schema_version") != REPORT_SCHEMA
        or report.get("status") != "PASS"
        or report.get("outcome") != "PASS"
        or report.get("protocol_id") != protocol["protocol_id"]
        or report.get("same_record_set_all_cells") is not True
        or report.get("exact_protocol_orders_all_cells") is not True
        or report.get("fresh_lora_init_identical_all_cells") is not True
        or len(init_fingerprints) != 1
        or None in init_fingerprints
        or len(init_tensor_counts) != 1
        or None in init_tensor_counts
        or report.get("fresh_lora_init")
        != {
            "sha256": next(iter(init_fingerprints), None),
            "parameter_tensors": next(iter(init_tensor_counts), None),
        }
        or {(row.get("modality"), row.get("ordering")) for row in cells} != expected
    ):
        raise RuntimeError("curriculum training gate is incomplete")
    checkpoints, fingerprints = {}, {}
    for cell in cells:
        arm = cell["arm"]
        checkpoint = root / cell["final_checkpoint"]
        actual = {
            "final_checkpoint_sha256": _sha256(checkpoint / "adapter_model.safetensors"),
            "final_adapter_config_sha256": _sha256(checkpoint / "adapter_config.json"),
        }
        if any(cell.get(key) != value for key, value in actual.items()):
            raise RuntimeError("curriculum training gate checkpoint fingerprint differs")
        checkpoints[arm] = cell["final_checkpoint"]
        fingerprints[arm] = actual
    bound = dict(protocol)
    bound["_curriculum_checkpoints"] = checkpoints
    bound["_curriculum_fingerprints"] = fingerprints
    return bound, report


def _require_worker_environment(protocol, worker):
    expected_gpu = str(protocol["launch"]["devices"][worker])
    if os.environ.get("CUDA_VISIBLE_DEVICES") != expected_gpu:
        raise ValueError("curriculum evaluation GPU differs from frozen mapping")
    try:
        port = int(os.environ["MASTER_PORT"])
    except (KeyError, ValueError) as error:
        raise ValueError("curriculum evaluation MASTER_PORT is missing or invalid") from error
    if port not in protocol["launch"]["master_port_pool"]:
        raise ValueError("curriculum evaluation MASTER_PORT is outside frozen pool")
    return expected_gpu, port


def _recorded_attempts(protocol):
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    expected_jobs = {f"curriculum-evaluate-{worker}" for worker in range(2)}
    registry, rows = {}, {}
    for attempt in ledger["attempts"]:
        if attempt.get("job_id") not in expected_jobs:
            continue
        if (
            attempt.get("branch") != "curriculum_modality"
            or "scripts/run_expanded_curriculum_evaluation.py" not in attempt.get("command", [])
            or "run" not in attempt.get("command", [])
        ):
            raise ValueError("curriculum evaluation attempt belongs to another protocol")
        identity = {
            "job_id": attempt["job_id"],
            "attempt": attempt["attempt"],
            "directory": str(Path(attempt["directory"]).resolve()),
        }
        key = (identity["job_id"], identity["attempt"], identity["directory"])
        registry[key] = attempt["status"]
        rows[key] = attempt
    bound = dict(protocol)
    bound["_valid_producing_attempts"] = registry
    return bound, rows


def _producing_attempt_from_environment(protocol, worker, rows):
    directory = Path(os.environ["EXPANDED_ATTEMPT_DIR"]).resolve()
    try:
        attempt_number = int(directory.name)
    except ValueError as error:
        raise ValueError("curriculum attempt directory is malformed") from error
    identity = {
        "job_id": directory.parent.name,
        "attempt": attempt_number,
        "directory": str(directory),
    }
    key = (identity["job_id"], identity["attempt"], identity["directory"])
    attempt = rows.get(key)
    if (
        identity["job_id"] != f"curriculum-evaluate-{worker}"
        or attempt is None
        or attempt.get("gpus") != [protocol["launch"]["devices"][worker]]
        or attempt.get("status") not in {"reserved", "running"}
    ):
        raise ValueError("curriculum evaluation environment is not a live recorded attempt")
    return identity


def _latest_attempt(ledger, job_id):
    rows = [row for row in ledger["attempts"] if row["job_id"] == job_id]
    if not rows:
        raise ValueError(f"missing curriculum evaluation attempt: {job_id}")
    return rows[-1]


def _expected_paths(protocol, loaded, modalities):
    return [
        str(
            (
                ROOT
                / protocol["output_root"]
                / "evaluation"
                / panel
                / modality
                / task["row"]["task_id"].replace("/", "__")
                / f"{arm}.json.gz"
            ).relative_to(ROOT)
        )
        for modality in modalities
        for panel, tasks in loaded.items()
        for task in tasks
        for arm in matched_arms(protocol, modality)
    ]


def prepare(protocol):
    loaded = panels(ROOT, protocol)
    comparator = validate_comparator_sources(ROOT, protocol)
    try:
        _bound, training = require_training_gate(ROOT, protocol)
    except RuntimeError as error:
        gate, detail = "PENDING", str(error)
    else:
        gate, detail = training["status"], "nine final checkpoints, fingerprints, and fresh init verified"
    report = {
        "schema_version": "expanded_curriculum_evaluation_preparation_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "panels": {key: len(value) for key, value in loaded.items()},
        "modalities": protocol["modalities"],
        "matched_arms_per_modality": 3,
        "comparators": list(COMPARATORS),
        "model_episodes": 243,
        "training_gate": gate,
        "training_gate_detail": detail,
        "comparator_audit": comparator,
        "model_loads": 0,
        "model_calls": 0,
        "writes": 0,
    }
    print(json.dumps(report, indent=2))
    return report


def run(protocol, worker):
    expected_gpu, port = _require_worker_environment(protocol, worker)
    protocol, _training = require_training_gate(ROOT, protocol)
    protocol, recorded_attempts = _recorded_attempts(protocol)
    producing_attempt = _producing_attempt_from_environment(protocol, worker, recorded_attempts)
    protocol["_producing_attempt"] = producing_attempt
    protocol["_runtime_head"] = _head()
    protocol["_comparator_audit"] = validate_comparator_sources(ROOT, protocol)
    loaded = panels(ROOT, protocol)
    modalities = assigned(protocol, worker)
    expected_paths = _expected_paths(protocol, loaded, modalities)
    completed_paths = []
    policy_identities = {}
    started = time.monotonic()
    cutoff = (
        datetime.strptime(protocol["budget"]["gpu_cutoff_utc"], "%Y-%m-%dT%H:%M:%SZ")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    for modality in modalities:
        arm_names = matched_arms(protocol, modality)
        if time.time() >= cutoff:
            break
        from transformers import set_seed

        from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
        from examples.planning_benchmark_slice.visual_model import VisualPolicy

        set_seed(protocol["evaluation"]["seed"])
        checkpoints = {arm: ROOT / protocol["_curriculum_checkpoints"][arm] for arm in arm_names}
        policy = VisualPolicy(
            model_id=protocol["base_model"]["model_id"],
            revision=protocol["base_model"]["revision"],
            adapter_paths=checkpoints,
            device="cuda:0",
            max_context_tokens=protocol["training"]["context_tokens"],
            max_new_tokens=protocol["training"]["output_tokens"],
            max_batch_size=2,
            max_batch_input_tokens=24000,
            inference_dtype="float32",
        )
        configure_visual_attention(policy.model, "visual_sdpa")
        for arm in arm_names:
            policy_identities[arm] = {
                **copy.deepcopy(policy.identity),
                "adapter_id": arm,
                **protocol["_curriculum_fingerprints"][arm],
            }
        protocol["_curriculum_policy_identity"] = policy_identities
        for panel_name, tasks in loaded.items():
            for arm in arm_names:
                if time.time() >= cutoff:
                    break

                def generate(examples, arm=arm, policy=policy):
                    values = policy.generate(examples, arm)
                    return values, [policy.last_generation_usage["generated_sequence_tokens"]] * len(values)

                def progress(
                    completed: int,
                    total: int,
                    task_id: str,
                    retained: bool,
                    arm=arm,
                    modality=modality,
                ):
                    write(
                        progress_path,
                        {
                            "completed": len(completed_paths) + completed,
                            "total": len(expected_paths),
                            "modality": modality,
                            "arm": arm,
                            "task_id": task_id,
                            "retained": retained,
                        },
                    )

                reports = run_cell(
                    ROOT,
                    protocol,
                    panel=panel_name,
                    modality=modality,
                    arm=arm,
                    tasks=tasks,
                    endpoint=protocol["launch"]["backend_endpoints"][worker],
                    generate=generate,
                    progress=progress,
                )
                completed_paths.extend(row["output"] for row in reports)
        del policy
        gc.collect()
        import torch

        torch.cuda.empty_cache()
    missing = sorted(set(expected_paths) - set(completed_paths))
    outcome = "PASS" if not missing else "VALID_STOP"
    result = {
        "schema_version": "expanded_curriculum_evaluation_worker_v1",
        "outcome": outcome,
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "modalities": modalities,
        "episodes": len(completed_paths),
        "paths": completed_paths,
        "missing_bindings": missing,
        "producing_attempt": producing_attempt,
        "policy_identities": policy_identities,
        "cuda_visible_devices": expected_gpu,
        "master_port": port,
        "runtime_head": protocol["_runtime_head"],
        "elapsed_seconds": time.monotonic() - started,
    }
    write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json", result)
    write(progress_path, {"completed": len(completed_paths), "total": len(expected_paths), "terminal": True})


def _bound_worker_protocol(protocol, worker, attempt):
    bound, _ = require_training_gate(ROOT, protocol)
    bound, _rows = _recorded_attempts(bound)
    worker_result = read(Path(attempt["directory"]) / "worker-result.json")
    bound["_producing_attempt"] = worker_result["producing_attempt"]
    bound["_runtime_head"] = worker_result["runtime_head"]
    bound["_curriculum_policy_identity"] = worker_result["policy_identities"]
    bound["_comparator_audit"] = validate_comparator_sources(ROOT, bound)
    return bound, worker_result


def _verify_worker_paths(protocol, worker, attempt):
    bound, worker_result = _bound_worker_protocol(protocol, worker, attempt)
    loaded = panels(ROOT, bound)
    expected = _expected_paths(bound, loaded, assigned(bound, worker))
    reports, missing = [], []
    for path in expected:
        absolute = ROOT / path
        if not absolute.is_file():
            missing.append(path)
            continue
        parts = absolute.relative_to(ROOT / bound["output_root"] / "evaluation").parts
        panel, modality, task_name, filename = parts
        arm = filename.removesuffix(".json.gz")
        task = next(row for row in loaded[panel] if row["row"]["task_id"].replace("/", "__") == task_name)
        reports.append(
            {
                **verify_episode(
                    ROOT,
                    bound,
                    panel,
                    modality,
                    task,
                    arm,
                    bound["launch"]["backend_endpoints"][worker],
                ),
                "comparison_arm": arm,
            }
        )
    if sorted(missing) != sorted(worker_result.get("missing_bindings", [])):
        raise ValueError("curriculum worker missing bindings differ from retained result")
    return reports, sorted(missing), worker_result


def audit_worker(protocol, worker):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if terminal.get("status") != "succeeded":
        raise RuntimeError("curriculum evaluation worker did not terminate cleanly")
    attempt = {
        "directory": terminal["directory"],
        "gpus": terminal["gpus"],
        "master_port": terminal["master_port"],
    }
    reports, missing, result = _verify_worker_paths(protocol, worker, attempt)
    if (
        result.get("worker") != worker
        or result.get("modalities") != assigned(protocol, worker)
        or result.get("master_port") != terminal["master_port"]
        or terminal["gpus"] != [protocol["launch"]["devices"][worker]]
        or result.get("cuda_visible_devices") != str(protocol["launch"]["devices"][worker])
    ):
        raise ValueError("curriculum evaluation worker provenance differs")
    outcome = "PASS" if not missing else "VALID_STOP"
    audit = {
        "outcome": outcome,
        "worker": worker,
        "episodes_replayed": len(reports),
        "missing_bindings": missing,
        "producing_attempt": result["producing_attempt"],
    }
    write(Path(terminal["directory"]) / "independent-replay.json", audit)
    print(json.dumps(audit, indent=2))


def _evaluation_attempts(protocol):
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    attempts = [_latest_attempt(ledger, f"curriculum-evaluate-{worker}") for worker in range(2)]
    for worker, attempt in enumerate(attempts):
        terminal = read(Path(attempt["directory"]) / "terminal.json")
        hook = read(Path(attempt["directory"]) / "hook-result.json")
        audit = read(Path(attempt["directory"]) / "independent-replay.json")
        if (
            attempt.get("status") != "succeeded"
            or not isinstance(attempt.get("attempt"), int)
            or attempt["attempt"] < 1
            or attempt.get("gpus") != [protocol["launch"]["devices"][worker]]
            or attempt.get("master_port") not in protocol["launch"]["master_port_pool"]
            or terminal.get("status") != "succeeded"
            or terminal.get("gpus") != attempt.get("gpus")
            or terminal.get("master_port") != attempt.get("master_port")
            or hook.get("returncode") != 0
            or audit.get("outcome") not in {"PASS", "VALID_STOP"}
            or audit.get("worker") != worker
        ):
            raise ValueError("curriculum evaluation scheduler/terminal/hook provenance differs")
    if len({row["master_port"] for row in attempts}) != 2:
        raise ValueError("curriculum evaluation workers reused a rendezvous port")
    return attempts


def _evidence(protocol, attempts):
    loaded = panels(ROOT, protocol)
    fresh, missing = [], []
    for worker, attempt in enumerate(attempts):
        reports, worker_missing, _result = _verify_worker_paths(protocol, worker, attempt)
        fresh.extend(reports)
        missing.extend(worker_missing)
    bound, _ = require_training_gate(ROOT, protocol)
    bound["_comparator_audit"] = validate_comparator_sources(ROOT, bound)
    comparators, comparator_missing = [], []
    for modality in bound["modalities"]:
        worker = 0 if modality in assigned(bound, 0) else 1
        endpoint = bound["launch"]["backend_endpoints"][worker]
        for panel_name, tasks in loaded.items():
            for condition in COMPARATORS:
                for task in tasks:
                    try:
                        report = verify_comparator(ROOT, bound, panel_name, modality, task, condition, endpoint)
                    except FileNotFoundError:
                        comparator_missing.append(f"{panel_name}:{modality}:{task['row']['task_id']}:{condition}")
                    else:
                        comparators.append({**report, "panel": panel_name})
    missing = sorted(missing)
    comparator_missing = sorted(comparator_missing)
    complete = not missing and not comparator_missing and len(fresh) == 243
    reports = [*fresh, *comparators]
    return {
        "schema_version": "expanded_curriculum_evaluation_evidence_v1",
        "status": "PASS" if complete else "VALID_STOP",
        "outcome": "PASS" if complete else "VALID_STOP",
        "protocol_id": bound["protocol_id"],
        "coverage": {
            "model_episodes": len(fresh),
            "expected_model_episodes": 243,
            "comparator_bindings": len(comparators),
            "expected_comparator_bindings": 324,
            "missing_bindings": missing,
            "missing_comparator_bindings": comparator_missing,
        },
        "cells": summarize(reports),
        "paired_rows": paired_rows(reports, bound) if complete else [],
        "compute": {
            "model_calls": sum(
                sum(1 for measurement in row.get("call_measurements", []) if measurement.get("model_call"))
                for row in fresh
            ),
            "active_wall_seconds": sum(
                row.get("active_wall_seconds", row.get("episode_wall_seconds", 0)) for row in fresh
            ),
        },
        "comparator_provenance": {
            "audit": bound["_comparator_audit"],
            "sources": sorted({row["comparator_source"] for row in comparators}),
        },
        "producing_attempts": [
            {"job_id": job_id, "attempt": attempt, "directory": directory}
            for job_id, attempt, directory in sorted(
                {tuple(row["producing_attempt"][key] for key in ("job_id", "attempt", "directory")) for row in fresh}
            )
        ],
        "jobs": [
            {key: row[key] for key in ("job_id", "attempt", "gpus", "master_port", "gpu_hours")} for row in attempts
        ],
    }


def finalize(protocol):
    attempts = _evaluation_attempts(protocol)
    evidence = _evidence(protocol, attempts)
    output = ROOT / protocol["output_root"] / "evaluation"
    write(output / "evidence.json", evidence)
    analysis = (
        analyze(protocol, evidence)
        if evidence["status"] == "PASS"
        else {
            "schema_version": "expanded_curriculum_analysis_v1",
            "outcome": "VALID_STOP",
            "protocol_id": protocol["protocol_id"],
            "reason": "evaluation coverage incomplete",
            "missing_bindings": evidence["coverage"]["missing_bindings"],
            "missing_comparator_bindings": evidence["coverage"]["missing_comparator_bindings"],
        }
    )
    write(output / "analysis.json", analysis)
    write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": evidence["coverage"]["model_episodes"], "total": 243})
    print(json.dumps(evidence, indent=2))


def audit_final(protocol):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    attempts = _evaluation_attempts(protocol)
    actual = _evidence(protocol, attempts)
    output = ROOT / protocol["output_root"] / "evaluation"
    expected_analysis = (
        analyze(protocol, actual)
        if actual["status"] == "PASS"
        else {
            "schema_version": "expanded_curriculum_analysis_v1",
            "outcome": "VALID_STOP",
            "protocol_id": protocol["protocol_id"],
            "reason": "evaluation coverage incomplete",
            "missing_bindings": actual["coverage"]["missing_bindings"],
            "missing_comparator_bindings": actual["coverage"]["missing_comparator_bindings"],
        }
    )
    if (
        terminal.get("status") != "succeeded"
        or read(output / "evidence.json") != actual
        or read(output / "analysis.json") != expected_analysis
    ):
        raise ValueError("curriculum evaluation evidence differs from scheduler-bound replay")
    print(f"{actual['status']}: {actual['coverage']['model_episodes']}/243 curriculum episodes replayed")


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("stage", choices=("prepare", "run", "audit-worker", "finalize", "audit-final"))
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--worker", type=int, choices=(0, 1))
    args = parser.parse_args(argv)
    protocol = read(args.protocol)
    validate_protocol(ROOT, protocol)
    if args.stage in {"run", "audit-worker"} and args.worker is None:
        parser.error(f"{args.stage} requires --worker")
    {
        "prepare": lambda: prepare(protocol),
        "run": lambda: run(protocol, args.worker),
        "audit-worker": lambda: audit_worker(protocol, args.worker),
        "finalize": lambda: finalize(protocol),
        "audit-final": lambda: audit_final(protocol),
    }[args.stage]()


if __name__ == "__main__":
    main()
