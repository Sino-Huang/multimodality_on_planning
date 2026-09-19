#!/usr/bin/env python
"""Run, audit, and publish the expanded second-backbone (#101-#103) branch."""

from __future__ import annotations

import argparse
import copy
import gc
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.planning_benchmark_slice import expanded_second_backbone as branch
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, timestamp, write

PROTOCOL = ROOT / "configs/experiments/expanded-study/second-backbone-protocol.json"


def _head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def require_worker_environment(protocol, worker):
    if worker not in (0, 1):
        raise ValueError("second-backbone worker is outside the frozen mapping")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != str(protocol["launch"]["devices"][worker]):
        raise ValueError("second-backbone worker GPU differs from frozen mapping")
    try:
        port = int(os.environ["MASTER_PORT"])
    except (KeyError, ValueError) as error:
        raise ValueError("second-backbone worker MASTER_PORT is missing or invalid") from error
    if port not in protocol["launch"]["master_port_pool"]:
        raise ValueError("second-backbone worker MASTER_PORT is outside the frozen pool")
    return port


def _write_progress(path, values):
    write(Path(path), values)
    print(json.dumps({"stage": "second_backbone", **values}), flush=True)


def validate(protocol):
    context = branch.validate_protocol(ROOT, protocol)
    report = {
        "schema_version": "expanded_second_backbone_validate_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "records": len(context["records"]),
        "panel_tasks": len(context["panel_tasks"]),
        "source_files": len(context["source_files"]),
    }
    print(json.dumps(report, indent=2))


def qualify_inputs(protocol, context, args):
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])

    def progress(**values):
        _write_progress(progress_path, values)

    result = branch.qualify_inputs(
        ROOT,
        protocol,
        context,
        record_limit=args.limit_records,
        task_limit=args.limit_tasks,
        progress=progress,
    )
    write(
        progress_path, {"completed": result["records_measured"], "total": result["records_measured"], "terminal": True}
    )
    print(json.dumps(result, indent=2))


def audit_qualify(protocol):
    result = read(branch.qualification_json_path(ROOT, protocol))
    if result.get("outcome") != "PASS" or result.get("complete") is not True:
        raise RuntimeError("second-backbone qualification did not pass completely")
    print("PASS: second-backbone qualification complete")


def probe(protocol, context):
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])

    def progress(**values):
        _write_progress(progress_path, values)

    result = branch.probe_stage(ROOT, protocol, context, attempt_dir=attempt_dir, progress=progress)
    write(progress_path, {"completed": 1, "total": 1, "terminal": True})
    print(json.dumps(result, indent=2))


def audit_probe(protocol):
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    probe = read(attempt_dir / "probe.json")
    if (
        probe.get("schema_version") != branch.PROBE_SCHEMA
        or probe.get("outcome") != "PASS"
        or not probe.get("scalar_batch_parity", {}).get("byte_identical")
        or not probe.get("repeated_batch_determinism", {}).get("byte_identical")
        or not probe.get("token_limit_guards", {}).get("oversize_batch_raises_valid_stop")
    ):
        raise RuntimeError("second-backbone probe evidence is incomplete")
    print("PASS: second-backbone probe evidence complete")


def admit(protocol, context):
    result = branch.admit_stage(ROOT, protocol, context)
    print(json.dumps(result, indent=2))


def run_training(protocol, context, worker):
    if time.time() >= timestamp(read(ROOT / branch.SCHEDULE_DOC)["gpu_cutoff_utc"]):
        raise RuntimeError("VALID_STOP: second-backbone training cutoff has passed")
    branch.require_admission_gate(ROOT, protocol)
    port = require_worker_environment(protocol, worker)
    cells = protocol["launch"]["training_worker_cells"][str(worker)]
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    started = time.monotonic()
    reports = []
    completed_before = 0
    for cell in cells:
        modality = cell["modality"]

        def progress(*, completed, total, eta_seconds, base=completed_before, modality=modality):
            values = {
                "completed": base + min(completed * 32, 512),
                "total": len(cells) * 512,
                "modality": modality,
                "cell_update": completed,
                "cell_updates": total,
                "eta_seconds": eta_seconds,
            }
            _write_progress(progress_path, values)

        reports.append(branch.train_cell(ROOT, protocol, context, modality=modality, progress=progress))
        completed_before += 512
        gc.collect()
        import torch

        torch.cuda.empty_cache()
    result = {
        "schema_version": "expanded_second_backbone_training_worker_v1",
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
    write(progress_path, {"completed": len(cells) * 512, "total": len(cells) * 512, "terminal": True})


def audit_training_worker(protocol, context, worker):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if terminal.get("status") != "succeeded":
        raise RuntimeError("second-backbone training worker did not succeed")
    result = read(Path(terminal["directory"]) / "worker-result.json")
    cells = protocol["launch"]["training_worker_cells"][str(worker)]
    if (
        result.get("outcome") != "PASS"
        or result.get("cells") != cells
        or terminal.get("gpus") != [protocol["launch"]["devices"][worker]]
        or result.get("master_port") != terminal.get("master_port")
    ):
        raise ValueError("second-backbone worker provenance differs")
    verified = [branch.verify_training_cell(ROOT, protocol, context, modality=row["modality"]) for row in cells]
    write(
        Path(terminal["directory"]) / "checkpoint-audit.json",
        {"outcome": "PASS", "worker": worker, "cells": verified},
    )
    print(json.dumps({"outcome": "PASS", "worker": worker, "cells": verified}, indent=2))


def _latest(ledger, job_id):
    rows = [row for row in ledger["attempts"] if row["job_id"] == job_id]
    if not rows:
        raise ValueError(f"missing second-backbone scheduler attempt: {job_id}")
    return rows[-1]


def _fresh_init_evidence(cells):
    fingerprints = {row.get("fresh_lora_init_sha256") for row in cells}
    tensor_counts = {row.get("fresh_lora_init_tensors") for row in cells}
    if len(fingerprints) != 1 or None in fingerprints or len(tensor_counts) != 1 or None in tensor_counts:
        raise ValueError("second-backbone fresh LoRA initialization differs across cells")
    return {"sha256": next(iter(fingerprints)), "parameter_tensors": next(iter(tensor_counts))}


def finalize_training(protocol, context):
    ledger = read(ROOT / branch.LEDGER_PATH)
    attempts = [_latest(ledger, f"second-backbone-train-{worker}") for worker in range(2)]
    if any(
        row["status"] != "succeeded" or read(Path(row["directory"]) / "hook-result.json").get("returncode") != 0
        for row in attempts
    ):
        raise ValueError("second-backbone workers or hooks are incomplete")
    cells = [
        branch.verify_training_cell(ROOT, protocol, context, modality=modality) for modality in protocol["modalities"]
    ]
    record_sets = {tuple(cell["training_record_ids"]) for cell in cells}
    if len(record_sets) != 1:
        raise ValueError("second-backbone cells do not share the exact frozen record order")
    fresh_init = _fresh_init_evidence(cells)
    report = {
        "schema_version": branch.TRAINING_REPORT_SCHEMA,
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
    write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": 3, "total": 3})
    print(json.dumps(report, indent=2))


def audit_training_final(protocol, context):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    report = read(ROOT / protocol["output_root"] / "training" / "training-report.json")
    cells = [
        branch.verify_training_cell(ROOT, protocol, context, modality=modality) for modality in protocol["modalities"]
    ]
    fresh_init = _fresh_init_evidence(cells)
    if (
        terminal.get("status") != "succeeded"
        or report.get("status") != "PASS"
        or report.get("cells") != cells
        or report.get("fresh_lora_init_identical_all_cells") is not True
        or report.get("fresh_lora_init") != fresh_init
    ):
        raise ValueError("second-backbone aggregate report differs from independent audit")
    print("PASS: all three second-backbone checkpoints and exact exposures independently verified")


def evaluate(protocol, worker):
    require_worker_environment(protocol, worker)
    branch.require_admission_gate(ROOT, protocol)
    bound, _training = branch.require_training_gate(ROOT, protocol)
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"]).resolve()
    try:
        attempt_number = int(attempt_dir.name)
    except ValueError as error:
        raise ValueError("second-backbone attempt directory is malformed") from error
    producing_attempt = {
        "job_id": attempt_dir.parent.name,
        "attempt": attempt_number,
        "directory": str(attempt_dir),
    }
    ledger = read(ROOT / branch.LEDGER_PATH)
    recorded = [
        row
        for row in ledger["attempts"]
        if row.get("job_id") == producing_attempt["job_id"] and row.get("attempt") == attempt_number
    ]
    if (
        producing_attempt["job_id"] != f"second-backbone-evaluate-{worker}"
        or not recorded
        or recorded[-1].get("status") not in {"reserved", "running"}
        or recorded[-1].get("gpus") != [protocol["launch"]["devices"][worker]]
    ):
        raise ValueError("second-backbone evaluation environment is not a live recorded attempt")
    probe = read(branch.probe_path(ROOT, protocol))
    attention_implementation = probe["attention"]["applied"] or protocol["evaluation"]["inference"]["attention"]
    bound["_producing_attempt"] = producing_attempt
    bound["_runtime_head"] = _head()
    branch.validate_protocol(ROOT, protocol)
    _, panel_tasks = branch.load_panel(ROOT, protocol)
    panel_tasks = branch.authorized_panel_tasks(ROOT, protocol, panel_tasks)
    selected = branch.assigned_bindings(protocol, panel_tasks, worker)
    modalities = branch.worker_modalities(protocol, selected)
    expected_paths = [
        str(
            branch.episode_path(
                ROOT, protocol, binding["modality"], binding["task_id"], binding["condition"]
            ).relative_to(ROOT)
        )
        for binding in selected
    ]
    completed_paths = []
    policy_identities = {}
    started = time.monotonic()
    cutoff = timestamp(read(ROOT / branch.SCHEDULE_DOC)["gpu_cutoff_utc"])
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    for modality in modalities:
        if time.time() >= cutoff:
            break
        from transformers import set_seed

        from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
        from examples.planning_benchmark_slice.visual_model import VisualPolicy

        set_seed(protocol["evaluation"]["seed"])
        policy = VisualPolicy(
            model_id=protocol["base_model"]["model_id"],
            revision=protocol["base_model"]["revision"],
            adapter_paths={"process_sft": ROOT / bound["_second_backbone_checkpoints"][modality]},
            device="cuda:0",
            max_context_tokens=protocol["evaluation"]["context_tokens"],
            max_new_tokens=protocol["evaluation"]["output_tokens"],
            max_batch_size=protocol["evaluation"]["inference"]["max_batch_size"],
            max_batch_input_tokens=protocol["evaluation"]["inference"]["max_padded_batch_input_tokens"],
            inference_dtype="float32",
            backbone=branch.backbone_spec(protocol["base_model"]["backbone_key"]),
            page_processor=branch.backbone_page_processor(protocol),
        )
        configure_visual_attention(policy.model, attention_implementation)
        for condition in branch.MODEL_CONDITIONS:
            adapter_id = condition if condition == "process_sft" else None
            policy_identities[(modality, condition)] = {
                **copy.deepcopy(policy.identity),
                "adapter_id": adapter_id,
                **(
                    bound["_second_backbone_fingerprints"][modality]
                    if condition == "process_sft"
                    else {"final_checkpoint_sha256": None, "final_adapter_config_sha256": None}
                ),
            }
        bound["_second_backbone_policy_identity"] = policy_identities
        modality_bindings = [binding for binding in selected if binding["modality"] == modality]
        task_by_id = {task["row"]["task_id"]: task for task in panel_tasks}

        def generate(examples, adapter_id, policy=policy):
            values = policy.generate(examples, adapter_id)
            return values, [policy.last_generation_usage["generated_sequence_tokens"]] * len(values)

        for condition in branch.MODEL_CONDITIONS:
            if time.time() >= cutoff:
                break
            pairs = [
                (binding, task_by_id[binding["task_id"]])
                for binding in modality_bindings
                if binding["condition"] == condition
            ]

            def progress(
                completed: int, total: int, task_id: str, retained: bool, condition=condition, modality=modality
            ):
                _write_progress(
                    progress_path,
                    {
                        "completed": len(completed_paths) + completed,
                        "total": len(expected_paths),
                        "modality": modality,
                        "condition": condition,
                        "task_id": task_id,
                        "retained": retained,
                    },
                )

            reports = branch.run_cell(
                ROOT,
                protocol,
                bound,
                modality=modality,
                task_bindings=pairs,
                endpoint=protocol["launch"]["backend_endpoints"][worker],
                generate=generate,
                progress=progress,
            )
            completed_paths.extend(report["output"] for report in reports)
        del policy
        gc.collect()
        import torch

        torch.cuda.empty_cache()
    missing = sorted(set(expected_paths) - set(completed_paths))
    outcome = "PASS" if not missing else "VALID_STOP"
    result = {
        "schema_version": "expanded_second_backbone_evaluation_worker_v1",
        "outcome": outcome,
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "modalities": modalities,
        "episodes": len(completed_paths),
        "paths": completed_paths,
        "missing_bindings": missing,
        "producing_attempt": producing_attempt,
        "policy_identities": {
            f"{modality}__{condition}": identity for (modality, condition), identity in policy_identities.items()
        },
        "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
        "master_port": int(os.environ["MASTER_PORT"]),
        "runtime_head": bound["_runtime_head"],
        "elapsed_seconds": time.monotonic() - started,
    }
    write(attempt_dir / "worker-result.json", result)
    write(progress_path, {"completed": len(completed_paths), "total": len(expected_paths), "terminal": True})


def _evaluation_attempts(protocol):
    ledger = read(ROOT / branch.LEDGER_PATH)
    attempts = [_latest(ledger, f"second-backbone-evaluate-{worker}") for worker in range(2)]
    for worker, attempt in enumerate(attempts):
        terminal = read(Path(attempt["directory"]) / "terminal.json")
        hook = read(Path(attempt["directory"]) / "hook-result.json")
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
        ):
            raise ValueError("second-backbone evaluation scheduler/terminal/hook provenance differs")
    if len({row["master_port"] for row in attempts}) != 2:
        raise ValueError("second-backbone evaluation workers reused a rendezvous port")
    return attempts


def audit_evaluation_worker(protocol, worker):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if terminal.get("status") != "succeeded":
        raise RuntimeError("second-backbone evaluation worker did not terminate cleanly")
    _, panel_tasks = branch.load_panel(ROOT, protocol)
    panel_tasks = branch.authorized_panel_tasks(ROOT, protocol, panel_tasks)
    bound, _report = branch.require_training_gate(ROOT, protocol)
    worker_result = read(Path(terminal["directory"]) / "worker-result.json")
    bound["_producing_attempt"] = worker_result["producing_attempt"]
    bound["_runtime_head"] = worker_result["runtime_head"]
    identities = {
        (modality, condition): identity
        for modality in protocol["modalities"]
        for condition in branch.MODEL_CONDITIONS
        for key, identity in worker_result.get("policy_identities", {}).items()
        if key == f"{modality}__{condition}"
    }
    bound["_second_backbone_policy_identity"] = identities
    selected = branch.assigned_bindings(protocol, panel_tasks, worker)
    tasks = {task["row"]["task_id"]: task for task in panel_tasks}
    reports, missing = [], []
    for binding in selected:
        path = branch.episode_path(ROOT, protocol, binding["modality"], binding["task_id"], binding["condition"])
        if not path.is_file():
            missing.append(str(path.relative_to(ROOT)))
            continue
        reports.append(
            branch.verify_episode(
                ROOT,
                protocol,
                bound,
                binding,
                tasks[binding["task_id"]],
                protocol["launch"]["backend_endpoints"][worker],
            )
        )
    if sorted(missing) != sorted(worker_result.get("missing_bindings", [])):
        raise ValueError("second-backbone worker missing bindings differ from retained result")
    outcome = "PASS" if not missing else "VALID_STOP"
    audit = {
        "outcome": outcome,
        "worker": worker,
        "episodes_replayed": len(reports),
        "missing_bindings": sorted(missing),
        "producing_attempt": worker_result["producing_attempt"],
    }
    write(Path(terminal["directory"]) / "independent-replay.json", audit)
    print(json.dumps(audit, indent=2))


def finalize_evaluation(protocol):
    attempts = _evaluation_attempts(protocol)
    evidence = branch.build_evidence(ROOT, protocol, attempts)
    write(branch.evaluation_root(ROOT, protocol) / "evidence.json", evidence)
    analysis = (
        branch.analyze_evidence(ROOT, protocol, evidence)
        if evidence["status"] == "PASS"
        else {
            "schema_version": branch.ANALYSIS_SCHEMA,
            "outcome": "VALID_STOP",
            "protocol_id": protocol["protocol_id"],
            "reason": "evaluation coverage incomplete",
            "missing_bindings": evidence["missing_bindings"],
            "missing_comparator_bindings": evidence["missing_comparator_bindings"],
        }
    )
    write(branch.evaluation_root(ROOT, protocol) / "analysis.json", analysis)
    write(
        os.environ["EXPANDED_PROGRESS_PATH"],
        {"completed": evidence["model_episodes"], "total": evidence["expected_model_episodes"]},
    )
    print(json.dumps(evidence, indent=2))


def audit_final(protocol):
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    attempts = _evaluation_attempts(protocol)
    actual = branch.build_evidence(ROOT, protocol, attempts)
    output = branch.evaluation_root(ROOT, protocol)
    expected_analysis = (
        branch.analyze_evidence(ROOT, protocol, actual)
        if actual["status"] == "PASS"
        else {
            "schema_version": branch.ANALYSIS_SCHEMA,
            "outcome": "VALID_STOP",
            "protocol_id": protocol["protocol_id"],
            "reason": "evaluation coverage incomplete",
            "missing_bindings": actual["missing_bindings"],
            "missing_comparator_bindings": actual["missing_comparator_bindings"],
        }
    )
    if (
        terminal.get("status") != "succeeded"
        or read(output / "evidence.json") != actual
        or read(output / "analysis.json") != expected_analysis
    ):
        raise ValueError("second-backbone evaluation evidence differs from scheduler-bound replay")
    print(f"{actual['status']}: {actual['model_episodes']}/{actual['expected_model_episodes']} second-backbone episodes replayed")


def analyze(protocol):
    output = branch.evaluation_root(ROOT, protocol)
    evidence = read(output / "evidence.json")
    result = (
        branch.analyze_evidence(ROOT, protocol, evidence)
        if evidence.get("status") == "PASS"
        else {
            "schema_version": branch.ANALYSIS_SCHEMA,
            "outcome": "VALID_STOP",
            "protocol_id": protocol["protocol_id"],
            "reason": "evaluation coverage incomplete",
        }
    )
    write(output / "analysis.json", result)
    print(json.dumps(result, indent=2))


def publish(protocol):
    result = branch.publish(ROOT, protocol)
    print(json.dumps(result, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "validate",
            "qualify-inputs",
            "audit-qualify",
            "probe",
            "audit-probe",
            "admit",
            "run",
            "audit-training-worker",
            "finalize-training",
            "audit-training-final",
            "evaluate",
            "audit-evaluate-worker",
            "finalize-evaluation",
            "audit-final",
            "analyze",
            "publish",
        ),
    )
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--worker", type=int, choices=(0, 1))
    parser.add_argument("--limit-records", type=int)
    parser.add_argument("--limit-tasks", type=int)
    args = parser.parse_args(argv)
    protocol = read(args.protocol)
    worker_stages = {"run", "audit-training-worker", "evaluate", "audit-evaluate-worker"}
    if args.stage in worker_stages and args.worker is None:
        parser.error(f"{args.stage} requires --worker")
    context = None
    if args.stage in {
        "validate",
        "qualify-inputs",
        "probe",
        "admit",
        "run",
        "audit-training-worker",
        "finalize-training",
        "audit-training-final",
    }:
        context = branch.validate_protocol(ROOT, protocol)
    {
        "validate": lambda: validate(protocol),
        "qualify-inputs": lambda: qualify_inputs(protocol, context, args),
        "audit-qualify": lambda: audit_qualify(protocol),
        "probe": lambda: probe(protocol, context),
        "audit-probe": lambda: audit_probe(protocol),
        "admit": lambda: admit(protocol, context),
        "run": lambda: run_training(protocol, context, args.worker),
        "audit-training-worker": lambda: audit_training_worker(protocol, context, args.worker),
        "finalize-training": lambda: finalize_training(protocol, context),
        "audit-training-final": lambda: audit_training_final(protocol, context),
        "evaluate": lambda: evaluate(protocol, args.worker),
        "audit-evaluate-worker": lambda: audit_evaluation_worker(protocol, args.worker),
        "finalize-evaluation": lambda: finalize_evaluation(protocol),
        "audit-final": lambda: audit_final(protocol),
        "analyze": lambda: analyze(protocol),
        "publish": lambda: publish(protocol),
    }[args.stage]()


if __name__ == "__main__":
    main()
