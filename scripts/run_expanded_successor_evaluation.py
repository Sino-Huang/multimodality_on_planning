#!/usr/bin/env python
"""Run, replay, and summarize the frozen expanded successor evaluation."""

from __future__ import annotations

import argparse
import copy
import gc
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write
from examples.planning_benchmark_slice.expanded_successor_evaluation import (
    ARMS,
    SCHEMA_VERSION,
    episode_path,
    exact_reference_counts,
    expected_bindings,
    paired_rows,
    panels,
    run_cell,
    summarize,
    verify_episode,
)

PROTOCOL = ROOT / "configs/experiments/expanded-study/successor-protocol.json"
QUALIFICATION = ROOT / "docs/experiments/expanded-study/successor-qualification.json"
TRAINING_REPORT = ROOT / "outputs/expanded-study/v1/successor/training/training-report.json"
REAUDIT_SCHEMA = "expanded_successor_evaluation_reaudit_v1"
REAUDIT_FIELDS = {
    "schema_version",
    "worker",
    "job_id",
    "attempt",
    "directory",
    "runtime_head",
    "timestamp",
    "episodes_replayed",
    "missing_bindings",
    "outcome",
    "original_hook_receipt",
}


def assigned(protocol, worker):
    return protocol["launch"]["qualification_worker_modalities"][str(worker)]


def _head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _validate_protocol(protocol):
    coverage = protocol.get("qualification", {}).get("coverage_admission", {})
    if (
        protocol.get("schema_version") != "expanded_successor_protocol_v1"
        or protocol.get("protocol_id") != "expanded-successor-v1"
        or protocol.get("algorithm") != "bfs"
        or protocol.get("modalities") != ["text-state", "visual-state", "multimodal-state"]
        or protocol.get("evaluation", {}).get("arms") != list(ARMS)
        or protocol.get("evaluation", {}).get("seed") != 17
        or coverage.get("fallback_unseen_task_count") != 12
        or coverage.get("fallback_model_call_allowance") != 4062
        or protocol.get("launch", {}).get("qualification_worker_modalities")
        != {"0": ["text-state", "multimodal-state"], "1": ["visual-state"]}
    ):
        raise ValueError("expanded successor evaluation protocol differs from the frozen contract")


def require_training_gate(root: Path, protocol):
    path = root / Path(protocol["output_root"]) / "training" / "training-report.json"
    if not path.exists():
        raise RuntimeError("successor evaluation requires training-report.json with status PASS")
    report = read(path)
    if (
        report.get("schema_version") != "expanded_successor_training_report_v1"
        or report.get("status") != "PASS"
        or report.get("outcome") != "PASS"
        or report.get("protocol_id") != protocol["protocol_id"]
        or report.get("arm") != protocol["training"]["arm"]
        or report.get("records")
        != len(protocol["modalities"]) * protocol["training"]["records_per_modality"]
        or report.get("optimizer_updates")
        != len(protocol["modalities"]) * protocol["training"]["optimizer_updates"]
    ):
        raise RuntimeError("successor evaluation training report is absent or not PASS")
    cells = report.get("cells")
    if not isinstance(cells, list) or len(cells) != len(protocol["modalities"]):
        raise RuntimeError("successor evaluation training report has incomplete modality cells")
    by_modality = {cell.get("modality"): cell for cell in cells if isinstance(cell, dict)}
    if set(by_modality) != set(protocol["modalities"]) or len(by_modality) != len(cells):
        raise RuntimeError("successor evaluation training report has incomplete modality cells")
    jobs = report.get("jobs")
    expected_jobs = {f"successor-train-{worker}": [protocol["launch"]["devices"][worker]] for worker in range(2)}
    if (
        not isinstance(jobs, list)
        or {row.get("job_id") for row in jobs if isinstance(row, dict)} != set(expected_jobs)
        or any(
            not isinstance(row, dict)
            or row.get("gpus") != expected_jobs.get(str(row.get("job_id")))
            or not isinstance(row.get("attempt"), int)
            or row["attempt"] < 1
            or row.get("master_port") not in protocol["launch"]["master_port_pool"]
            for row in jobs
        )
    ):
        raise RuntimeError("successor evaluation training report has invalid scheduler provenance")
    checkpoints = {}
    checkpoint_fingerprints = {}
    config_fingerprints = {}
    for modality in protocol["modalities"]:
        cell = by_modality[modality]
        expected_relative = (
            Path(protocol["output_root"]) / "training" / modality / protocol["training"]["arm"] / "final"
        )
        if (
            cell.get("outcome") != "PASS"
            or cell.get("arm") != protocol["training"]["arm"]
            or cell.get("records") != protocol["training"]["records_per_modality"]
            or cell.get("optimizer_updates") != protocol["training"]["optimizer_updates"]
            or cell.get("final_checkpoint") != str(expected_relative)
            or not isinstance(cell.get("final_checkpoint_sha256"), str)
            or not isinstance(cell.get("final_adapter_config_sha256"), str)
        ):
            raise RuntimeError(f"successor evaluation training cell is invalid: {modality}")
        checkpoint = root / expected_relative
        tensor = checkpoint / "adapter_model.safetensors"
        config = checkpoint / "adapter_config.json"
        if not tensor.is_file() or not config.is_file():
            raise RuntimeError(f"successor evaluation final checkpoint files are missing: {checkpoint}")
        actual_tensor = _sha256(tensor)
        actual_config = _sha256(config)
        if (
            cell["final_checkpoint_sha256"] != actual_tensor
            or cell["final_adapter_config_sha256"] != actual_config
        ):
            raise RuntimeError(f"successor evaluation final checkpoint fingerprint differs: {modality}")
        checkpoints[modality] = checkpoint
        checkpoint_fingerprints[modality] = actual_tensor
        config_fingerprints[modality] = actual_config
    return report, checkpoints, checkpoint_fingerprints, config_fingerprints


def _bind_training_gate(root: Path, protocol):
    report, checkpoints, checkpoint_fingerprints, config_fingerprints = require_training_gate(root, protocol)
    bound = dict(protocol)
    bound["_successor_checkpoints"] = {
        modality: str(path.relative_to(root)) for modality, path in checkpoints.items()
    }
    bound["_successor_checkpoint_sha256"] = checkpoint_fingerprints
    bound["_successor_adapter_config_sha256"] = config_fingerprints
    policy_identity = {
        "attention_implementation": protocol["model"]["attention"],
        "decoding": protocol["model"]["decoding"],
        "dtype": protocol["model"]["inference_dtype"],
        "max_batch_input_tokens": 24000,
        "max_batch_size": 2,
        "max_context_tokens": protocol["model"]["context_tokens"],
        "max_new_tokens": protocol["model"]["output_tokens"],
        "memoize_identical_inputs": False,
        "model_id": protocol["model"]["id"],
        "revision": protocol["model"]["revision"],
    }
    bound["_successor_policy_identity"] = {
        modality: copy.deepcopy(policy_identity) for modality in protocol["modalities"]
    }
    bound["_runtime_head"] = _head()
    return bound, report


def _recorded_attempts(protocol):
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    expected_jobs = {f"successor-evaluate-{worker}" for worker in range(2)}
    registry = {}
    rows = {}
    for attempt in ledger["attempts"]:
        job_id = attempt.get("job_id")
        if job_id not in expected_jobs:
            continue
        command = attempt.get("command", [])
        if (
            attempt.get("branch") != "successor_prediction"
            or "scripts/run_expanded_successor_evaluation.py" not in command
            or "run" not in command
        ):
            raise ValueError("successor evaluation scheduler attempt belongs to another protocol")
        identity = {
            "job_id": job_id,
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
    try:
        directory = Path(os.environ["EXPANDED_ATTEMPT_DIR"]).resolve()
        attempt_number = int(directory.name)
    except (KeyError, ValueError) as error:
        raise ValueError("successor evaluation scheduler attempt directory is missing or malformed") from error
    job_id = directory.parent.name
    if directory.parent.parent.name != "jobs" or job_id != f"successor-evaluate-{worker}":
        raise ValueError("successor evaluation attempt directory encodes the wrong worker job")
    identity = {"job_id": job_id, "attempt": attempt_number, "directory": str(directory)}
    key = (job_id, attempt_number, str(directory))
    attempt = rows.get(key)
    if (
        attempt is None
        or attempt.get("gpus") != [protocol["launch"]["devices"][worker]]
        or attempt.get("status") not in {"reserved", "running"}
    ):
        raise ValueError("successor evaluation environment is not a live recorded scheduler attempt")
    return identity


def _require_worker_environment(protocol, worker):
    expected_gpu = str(protocol["launch"]["devices"][worker])
    if os.environ.get("CUDA_VISIBLE_DEVICES") != expected_gpu:
        raise ValueError("successor evaluation worker GPU differs from the frozen mapping")
    try:
        port = int(os.environ["MASTER_PORT"])
    except (KeyError, ValueError) as error:
        raise ValueError("successor evaluation worker MASTER_PORT is missing or invalid") from error
    if port not in protocol["launch"]["master_port_pool"]:
        raise ValueError("successor evaluation worker MASTER_PORT is outside the frozen pool")
    return expected_gpu, port


def _exclusive_worker(protocol, worker):
    parent = ROOT / protocol["output_root"] / "evaluation" / "locks"
    parent.mkdir(parents=True, exist_ok=True)
    lock = parent / f"worker-{worker}.lock"
    try:
        lock.mkdir()
    except FileExistsError as error:
        owner_path = lock / "owner.json"
        try:
            owner = json.loads(owner_path.read_text(encoding="utf-8"))
            pid = int(owner["pid"])
            os.kill(pid, 0)
        except ProcessLookupError:
            shutil.rmtree(lock)
            lock.mkdir()
        except (FileNotFoundError, KeyError, TypeError, ValueError, PermissionError, OSError) as owner_error:
            raise RuntimeError(
                f"cannot prove successor evaluation worker lock is stale: {worker}"
            ) from owner_error
        else:
            raise RuntimeError(f"duplicate concurrent successor evaluation worker: {worker}") from error
    (lock / "owner.json").write_text(
        json.dumps({"pid": os.getpid(), "started": time.time()}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return lock


def prepare(protocol):
    loaded = panels(ROOT, protocol)
    counts = exact_reference_counts(loaded)
    coverage = protocol["qualification"]["coverage_admission"]
    qualification = read(QUALIFICATION)
    if (
        qualification.get("outcome") != "PASS"
        or qualification.get("selected_coverage") != "exact_cost_fallback"
        or qualification.get("selected_unseen_task_ids") != coverage["fallback_unseen_task_ids"]
        or counts["by_panel"]["development"]
        != {
            task["row"]["task_id"]: task["row"]["reference_costs"]["bfs"]["decisions"]
            for task in loaded["development"]
        }
        or sum(counts["by_panel"]["unseen"].values()) != coverage["fallback_exact_reference_decisions"]
        or counts["model_call_allowance"] != coverage["fallback_model_call_allowance"]
    ):
        raise ValueError("successor evaluation fallback coverage/call projection differs")
    try:
        _bound, training = _bind_training_gate(ROOT, protocol)
    except RuntimeError as error:
        training_gate = "PENDING" if not TRAINING_REPORT.exists() else "FAIL"
        training_detail = str(error)
    else:
        training_gate = training["status"]
        training_detail = "all modalities and final adapter fingerprints verified"
    report = {
        "schema_version": "expanded_successor_evaluation_preparation_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "coverage": {name: len(tasks) for name, tasks in loaded.items()},
        "modalities": protocol["modalities"],
        "arms": list(ARMS),
        "logical_episodes": len(expected_bindings(protocol, loaded)),
        "exact_reference": counts,
        "qualification_selected_coverage": qualification["selected_coverage"],
        "training_gate": training_gate,
        "training_gate_detail": training_detail,
        "model_loads": 0,
        "model_calls": 0,
        "writes": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


def run(protocol, worker):
    expected_gpu, port = _require_worker_environment(protocol, worker)
    protocol, _training = _bind_training_gate(ROOT, protocol)
    protocol, recorded_attempts = _recorded_attempts(protocol)
    protocol["_producing_attempt"] = _producing_attempt_from_environment(
        protocol, worker, recorded_attempts
    )
    checkpoints = {
        modality: ROOT / path for modality, path in protocol["_successor_checkpoints"].items()
    }
    loaded = panels(ROOT, protocol)
    modalities = assigned(protocol, worker)
    worker_total = sum(len(tasks) for tasks in loaded.values()) * len(ARMS) * len(modalities)
    lock = _exclusive_worker(protocol, worker)
    reports = []
    completed = 0
    started = time.monotonic()
    cutoff = datetime.strptime(
        protocol["budget"]["gpu_cutoff_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=timezone.utc).timestamp()
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    try:
        for modality in modalities:
            from transformers import set_seed

            from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
            from examples.planning_benchmark_slice.visual_model import VisualPolicy

            set_seed(protocol["evaluation"]["seed"])
            policy = None
            pending_episodes = any(
                not episode_path(
                    ROOT,
                    protocol,
                    panel_name,
                    modality,
                    task["row"]["task_id"],
                    arm,
                ).exists()
                for panel_name, tasks in loaded.items()
                for task in tasks
                for arm in ARMS
            )
            if pending_episodes and time.time() < cutoff:
                policy = VisualPolicy(
                    model_id=protocol["model"]["id"],
                    revision=protocol["model"]["revision"],
                    adapter_paths={"successor_sft": checkpoints[modality]},
                    device="cuda:0",
                    max_context_tokens=protocol["model"]["context_tokens"],
                    max_new_tokens=protocol["model"]["output_tokens"],
                    max_batch_size=2,
                    max_batch_input_tokens=24000,
                    inference_dtype=protocol["model"]["inference_dtype"],
                )
                configure_visual_attention(policy.model, protocol["model"]["attention"])
                policy.identity.update(
                    attention_implementation=protocol["model"]["attention"],
                    memoize_identical_inputs=False,
                )
                if policy.identity != protocol["_successor_policy_identity"][modality]:
                    raise ValueError("loaded successor policy identity differs from the gated contract")

            def generate(examples, policy=policy):
                if policy is None:
                    raise RuntimeError("GPU cutoff reached before successor model loading")
                outputs = policy.generate(examples, "successor_sft")
                return outputs, dict(policy.last_generation_usage)

            for panel_name, tasks in loaded.items():
                for arm in ("trusted_successor", "model_generated_successor"):

                    def progress(
                        *,
                        completed: int,
                        total: int,
                        task_id: str,
                        retained: bool,
                        panel_name=panel_name,
                        modality=modality,
                        arm=arm,
                    ):
                        overall = len(reports) + completed
                        elapsed = time.monotonic() - started
                        write(
                            progress_path,
                            {
                                "completed": overall,
                                "total": worker_total,
                                "cell_total": total,
                                "panel": panel_name,
                                "modality": modality,
                                "arm": arm,
                                "task_id": task_id,
                                "retained": retained,
                                "eta_seconds": elapsed * (total - overall) / overall if overall else None,
                            },
                        )

                    rows = run_cell(
                        ROOT,
                        protocol,
                        panel=panel_name,
                        modality=modality,
                        arm=arm,
                        tasks=tasks,
                        endpoint=protocol["launch"]["backend_endpoints"][worker],
                        generate=generate if arm == "model_generated_successor" else None,
                        progress=progress,
                        cutoff_timestamp=cutoff,
                    )
                    reports.extend(rows)
                    completed += len(rows)
            if policy is not None:
                del policy
                gc.collect()
                import torch

                torch.cuda.empty_cache()
        outcome = "PASS" if completed == worker_total else "VALID_STOP"
        result = {
            "schema_version": "expanded_successor_evaluation_worker_v1",
            "outcome": outcome,
            "protocol_id": protocol["protocol_id"],
            "worker": worker,
            "modalities": modalities,
            "episodes": completed,
            "expected_episodes": worker_total,
            "model_calls": sum(row["result"]["model_calls"] for row in reports),
            "cuda_visible_devices": expected_gpu,
            "master_port": port,
            "producing_attempt": copy.deepcopy(protocol["_producing_attempt"]),
            "policy_identities": {
                modality: copy.deepcopy(protocol["_successor_policy_identity"][modality])
                for modality in modalities
            },
            "runtime_head": protocol["_runtime_head"],
            "elapsed_seconds": time.monotonic() - started,
            "cutoff_utc": protocol["budget"]["gpu_cutoff_utc"],
        }
        stable = ROOT / protocol["output_root"] / "evaluation" / "workers" / f"worker-{worker}.json"
        write(stable, result)
        write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json", result)
        write(
            progress_path,
            {"completed": completed, "total": worker_total, "terminal": True, "outcome": outcome},
        )
        return result
    finally:
        shutil.rmtree(lock, ignore_errors=False)


def _worker_reports(protocol, worker):
    loaded = panels(ROOT, protocol)
    rows = []
    missing = []
    for panel_name, tasks in loaded.items():
        for modality in assigned(protocol, worker):
            for task in tasks:
                for arm in ARMS:
                    path = episode_path(ROOT, protocol, panel_name, modality, task["row"]["task_id"], arm)
                    if not path.exists():
                        missing.append(
                            {
                                "panel": panel_name,
                                "modality": modality,
                                "task_id": task["row"]["task_id"],
                                "arm": arm,
                            }
                        )
                        continue
                    rows.append(
                        verify_episode(
                            ROOT,
                            protocol,
                            panel_name,
                            modality,
                            task,
                            arm,
                            protocol["launch"]["backend_endpoints"][worker],
                        )
                    )
    return rows, missing


def audit_worker(protocol, worker):
    protocol, _training = _bind_training_gate(ROOT, protocol)
    protocol, _attempts = _recorded_attempts(protocol)
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if (
        terminal.get("status") not in {"succeeded", "cutoff"}
        or terminal.get("master_port") not in protocol["launch"]["master_port_pool"]
        or terminal.get("gpus") != [protocol["launch"]["devices"][worker]]
    ):
        raise ValueError("successor evaluation worker provenance differs")
    report_path = Path(terminal["directory"]) / "worker-result.json"
    report = read(report_path) if report_path.exists() else None
    expected_producing = {
        "job_id": terminal["job_id"],
        "attempt": terminal["attempt"],
        "directory": str(Path(terminal["directory"]).resolve()),
    }
    if terminal["status"] == "succeeded" and (
        report is None
        or report.get("outcome") not in {"PASS", "VALID_STOP"}
        or report.get("worker") != worker
        or report.get("modalities") != assigned(protocol, worker)
        or report.get("master_port") != terminal.get("master_port")
        or report.get("producing_attempt") != expected_producing
        or report.get("policy_identities")
        != {
            modality: protocol["_successor_policy_identity"][modality]
            for modality in assigned(protocol, worker)
        }
        or not isinstance(report.get("runtime_head"), str)
        or not report["runtime_head"]
    ):
        raise ValueError("successor evaluation worker result provenance differs")
    rows, missing = _worker_reports(protocol, worker)
    if report is not None and report["outcome"] == "PASS" and missing:
        raise ValueError("passing successor evaluation worker omitted episodes")
    if terminal["status"] == "cutoff" and not missing:
        raise ValueError("cutoff successor worker cannot claim complete coverage")
    result = {
        "outcome": "PASS" if not missing else "VALID_STOP",
        "worker": worker,
        "episodes_replayed": len(rows),
        "missing_bindings": missing,
        "independent_replay": True,
    }
    directory = Path(terminal["directory"])
    write(directory / "independent-replay.json", result)
    original_hook = read(directory / "hook-result.json")
    reaudit = {
        "schema_version": REAUDIT_SCHEMA,
        "worker": worker,
        "job_id": terminal["job_id"],
        "attempt": terminal["attempt"],
        "directory": str(directory.resolve()),
        "runtime_head": _head(),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "episodes_replayed": len(rows),
        "missing_bindings": missing,
        "outcome": result["outcome"],
        "original_hook_receipt": original_hook,
    }
    write(directory / "reaudit-result.json", reaudit)
    print(json.dumps(result, indent=2))
    return result


def _all_reports(protocol):
    rows = []
    missing = []
    for worker in range(2):
        worker_rows, worker_missing = _worker_reports(protocol, worker)
        rows.extend(worker_rows)
        missing.extend(worker_missing)
    return rows, missing


def _latest_attempt(ledger, job_id):
    attempts = [row for row in ledger["attempts"] if row["job_id"] == job_id]
    if not attempts:
        raise ValueError(f"missing scheduler attempt for {job_id}")
    return attempts[-1]


def _validated_reaudit(path, *, attempt, worker, hook, expected_episodes):
    if not path.is_file():
        return None
    reaudit = read(path)
    expected_directory = str(Path(attempt["directory"]).resolve())
    if set(reaudit) != REAUDIT_FIELDS or reaudit.get("schema_version") != REAUDIT_SCHEMA:
        raise ValueError("successor evaluation reaudit has a malformed schema")
    timestamp = reaudit.get("timestamp")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise ValueError("successor evaluation reaudit timestamp is invalid") from error
    if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("successor evaluation reaudit timestamp is not UTC")
    if (
        reaudit.get("worker") != worker
        or reaudit.get("job_id") != attempt["job_id"]
        or reaudit.get("attempt") != attempt["attempt"]
        or reaudit.get("directory") != expected_directory
    ):
        raise ValueError("successor evaluation reaudit belongs to another attempt")
    if (
        reaudit.get("outcome") != "PASS"
        or reaudit.get("missing_bindings") != []
        or reaudit.get("episodes_replayed") != expected_episodes
        or not isinstance(reaudit.get("runtime_head"), str)
        or not reaudit["runtime_head"]
    ):
        raise ValueError("successor evaluation reaudit did not prove complete worker coverage")
    if reaudit.get("original_hook_receipt") != hook:
        raise ValueError("successor evaluation reaudit does not embed the original hook receipt")
    return reaudit


def _evaluation_attempts(protocol, outcome, missing):
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    attempts = [_latest_attempt(ledger, f"successor-evaluate-{worker}") for worker in range(2)]
    evidence = []
    for worker, attempt in enumerate(attempts):
        directory = Path(attempt["directory"])
        hook = read(directory / "hook-result.json")
        status = attempt.get("status")
        if outcome == "PASS":
            if status != "succeeded":
                raise ValueError("complete successor evaluation requires succeeded worker attempts")
        elif (
            outcome != "VALID_STOP"
            or not missing
            or status not in {"succeeded", "cutoff"}
        ):
            raise ValueError("partial successor evaluation lacks a valid terminal cutoff")
        if (
            attempt.get("gpus") != [protocol["launch"]["devices"][worker]]
            or attempt.get("master_port") not in protocol["launch"]["master_port_pool"]
        ):
            raise ValueError("successor evaluation scheduler GPU/port provenance differs")
        worker_result_path = directory / "worker-result.json"
        worker_result = read(worker_result_path) if status == "succeeded" else None
        expected_episodes = (
            worker_result.get("expected_episodes")
            if worker_result is not None
            else attempt.get("total")
        )
        if not isinstance(expected_episodes, int) or expected_episodes <= 0:
            raise ValueError("successor evaluation worker expected episode count is missing")
        reaudit = _validated_reaudit(
            directory / "reaudit-result.json",
            attempt=attempt,
            worker=worker,
            hook=hook,
            expected_episodes=expected_episodes,
        )
        if hook.get("returncode") != 0 and reaudit is None:
            raise ValueError("successor evaluation worker replay hook is incomplete and has no passing reaudit")
        if status == "succeeded":
            if worker_result is None:
                raise ValueError("successor evaluation succeeded attempt lacks a worker result")
            if (
                worker_result.get("worker") != worker
                or worker_result.get("master_port") != attempt["master_port"]
                or worker_result.get("outcome") not in {"PASS", "VALID_STOP"}
                or (outcome == "PASS" and worker_result.get("outcome") != "PASS")
            ):
                raise ValueError("successor evaluation worker result differs from scheduler attempt")
        attempt_evidence = {
            key: attempt[key]
            for key in ("job_id", "attempt", "status", "directory", "gpus", "master_port", "gpu_hours")
        } | {"hook_returncode": hook.get("returncode")}
        if reaudit is not None:
            attempt_evidence["reaudit"] = {
                key: reaudit[key]
                for key in ("runtime_head", "timestamp", "outcome", "episodes_replayed")
            }
        evidence.append(attempt_evidence)
    return evidence


def _producing_attempt_evidence(reports, recorded_attempts):
    identities = {
        (
            report["producing_attempt"]["job_id"],
            report["producing_attempt"]["attempt"],
            report["producing_attempt"]["directory"],
        )
        for report in reports
    }
    evidence = []
    for key in sorted(identities):
        attempt = recorded_attempts.get(key)
        if attempt is None or attempt.get("status") not in {
            "succeeded",
            "failed",
            "cutoff",
            "interrupted",
        }:
            raise ValueError("successor episode producing attempt is not terminal scheduler evidence")
        hook_path = Path(attempt["directory"]) / "hook-result.json"
        if not hook_path.is_file():
            raise ValueError("successor episode producing attempt lacks a hook receipt")
        hook = read(hook_path)
        evidence.append(
            {
                key: attempt[key]
                for key in ("job_id", "attempt", "status", "directory", "gpus", "master_port", "gpu_hours")
            }
            | {"hook_receipt": hook}
        )
    return evidence


def _evidence(protocol):
    protocol, training = _bind_training_gate(ROOT, protocol)
    protocol, recorded_attempts = _recorded_attempts(protocol)
    loaded = panels(ROOT, protocol)
    expected = expected_bindings(protocol, loaded)
    reports, missing = _all_reports(protocol)
    outcome = "PASS" if not missing else "VALID_STOP"
    attempts = _evaluation_attempts(protocol, outcome, missing)
    producing_attempts = _producing_attempt_evidence(reports, recorded_attempts)
    return {
        "schema_version": SCHEMA_VERSION,
        "outcome": outcome,
        "protocol_id": protocol["protocol_id"],
        "training_report_schema": training["schema_version"],
        "training_status": training["status"],
        "final_checkpoint_sha256": copy.deepcopy(protocol["_successor_checkpoint_sha256"]),
        "final_adapter_config_sha256": copy.deepcopy(
            protocol["_successor_adapter_config_sha256"]
        ),
        "evaluation_seed": protocol["evaluation"]["seed"],
        "coverage": {name: len(tasks) for name, tasks in loaded.items()},
        "expected_episodes": len(expected),
        "episodes_replayed": len(reports),
        "complete_coverage": not missing,
        "missing_bindings": missing,
        "exact_reference": exact_reference_counts(loaded),
        "cells": summarize(reports, expected),
        "paired_whole_problem_rows": paired_rows(reports, expected),
        "compute": {
            "active_wall_seconds": sum(row["active_wall_seconds"] for row in reports),
            "model_call_wall_seconds": sum(
                measurement["call_wall_seconds"]
                for row in reports
                for measurement in row["call_measurements"]
            ),
            "model_calls": sum(row["result"]["model_calls"] for row in reports),
        },
        "raw_predictions_retained": sum(row["raw_predictions_retained"] for row in reports),
        "trusted_state_substitutions": sum(row["trusted_state_substitutions"] for row in reports),
        "independent_replay": True,
        "jobs": attempts,
        "producing_attempts": producing_attempts,
    }


def finalize(protocol):
    report = _evidence(protocol)
    if report["trusted_state_substitutions"] != 0:
        raise ValueError("successor evaluation attempted trusted-state substitution")
    path = ROOT / protocol["output_root"] / "evaluation" / "evidence.json"
    write(path, report)
    if os.environ.get("EXPANDED_PROGRESS_PATH"):
        write(
            os.environ["EXPANDED_PROGRESS_PATH"],
            {"completed": report["episodes_replayed"], "total": report["expected_episodes"]},
        )
    print(json.dumps(report, indent=2))
    return report


def audit_final(protocol):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    retained = read(ROOT / protocol["output_root"] / "evaluation" / "evidence.json")
    actual = _evidence(protocol)
    if terminal["status"] != "succeeded" or retained != actual:
        raise ValueError("published successor evaluation differs from independent replay")
    print(
        f"{actual['outcome']}: independently replayed {actual['episodes_replayed']} "
        f"of {actual['expected_episodes']} successor evaluation episodes"
    )
    return actual


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("stage", choices=("prepare", "run", "audit-worker", "finalize", "audit-final"))
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--worker", type=int, choices=(0, 1))
    args = parser.parse_args(argv)
    protocol = read(args.protocol)
    _validate_protocol(protocol)
    if args.stage in {"run", "audit-worker"} and args.worker is None:
        parser.error(f"{args.stage} requires --worker")
    functions = {
        "prepare": lambda: prepare(protocol),
        "run": lambda: run(protocol, args.worker),
        "audit-worker": lambda: audit_worker(protocol, args.worker),
        "finalize": lambda: finalize(protocol),
        "audit-final": lambda: audit_final(protocol),
    }
    functions[args.stage]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
