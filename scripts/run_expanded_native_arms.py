#!/usr/bin/env python
"""Frozen native-arm (#128) preparation, admission, training and evaluation.

Stages (CPU unless noted):
  validate              fail closed on every frozen design dependency
  prepare --arm ARM     materialize the membership under one native arm
  probe --arm ARM       GPU: pretrained-base admission-gate probe
  admit                 CPU: recompute the frozen admission equation
  train --arm ARM       GPU: train both additive adapters of one arm
  evaluate-inputs       materialize the frozen evaluation bindings
  evaluate-worker       GPU (models) / CPU (controls): run episodes
  finalize              CPU: independent replay of every episode + analysis
  audit-*               scheduler completion hooks
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.expanded_modality_stress import (  # noqa: E402
    load_panel_tasks as stress_panel_tasks,
)
from examples.planning_benchmark_slice.expanded_views import ExpandedTaskViews  # noqa: E402
from examples.planning_benchmark_slice.native_arm_corpus import (  # noqa: E402
    NativeArmStore,
    NativeArmTrainingDataset,
    prepare_arm,
    qualification_report,
)
from examples.planning_benchmark_slice.native_arm_views import (  # noqa: E402
    ARMS,
    HISTORY_K,
    NOMEM_ARM,
    SEQ_ARM,
)
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402
from examples.planning_benchmark_slice.visual_episode import replay_visual_episode  # noqa: E402
from examples.planning_benchmark_slice.visual_model import train_visual  # noqa: E402

PROTOCOL_PATH = Path("configs/experiments/native-arms/native-arms-protocol.json")
SCHEDULE_PATH = Path("docs/experiments/native-arms/schedule.json")
LEDGER_PATH = ROOT / "outputs/native-arms/v1/budget.json"
BOOTSTRAP_SEED = 61813
BOOTSTRAP_RESAMPLES = 10000
TINY_STRATUM_LIMIT = 8
V5_TRAINING_SECONDS_PER_CELL_BASIS = 5232.08 * 2 / 8 / 3600  # 0.36334 GPU-h, v5 8-cell chain
ENGINE_ARM = {
    "learned_adapter": "process_sft",
    "pretrained_base": "pretrained_base",
    "random_valid": "random_valid",
    "exact_reference": "exact_reference",
}
BASE_MODEL_CALL_CAP = 1
PHASES = ("clean", "corruption")


def write(path: Path, value) -> None:
    import gzip

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    payload = json.dumps(value, indent=1, sort_keys=False)
    if path.suffix == ".gz":
        with gzip.open(temporary, "wt") as stream:
            stream.write(payload)
    else:
        temporary.write_text(payload)
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def progress_writer():
    path = Path(os.environ.get("EXPANDED_PROGRESS_PATH", "/tmp/native-arms-progress.json"))

    def emit(stage, **fields):
        write(path, {"stage": stage, **fields})

    return emit


V2_PROTOCOL_PATH = Path("configs/experiments/native-arms/native-arms-v2-protocol.json")
V3_PROTOCOL_PATH = Path("configs/experiments/native-arms/native-arms-v3-protocol.json")


def load_protocol() -> dict:
    for path in (V3_PROTOCOL_PATH, V2_PROTOCOL_PATH):
        if path.is_file():
            protocol = read_json(ROOT / path)
            protocol["root"] = str(ROOT)
            return protocol
    protocol = read_json(ROOT / PROTOCOL_PATH)
    protocol["root"] = str(ROOT)
    return protocol



def output_root(protocol: dict) -> Path:
    return ROOT / protocol["output_root"]


def load_tasks(protocol: dict) -> list[dict]:
    shim = {
        "panel": protocol["panel"],
        "panel_view_report": protocol["panel_view_report"],
        "panel_id": protocol["panel_id"],
        "membership_rule": {"membership": protocol["evaluation"]["membership"]},
    }
    tasks = stress_panel_tasks(ROOT, shim)
    if len(tasks) != len(protocol["evaluation"]["membership"]):
        raise ValueError("native-arm task loading differs from the frozen membership")
    return tasks


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #


def validate_stage() -> dict:
    from examples.planning_benchmark_slice import native_arm_views as views

    protocol = load_protocol()
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    check(sha256_file(ROOT / protocol["panel"]) == protocol["panel_sha256"], "panel sha differs")
    check(
        sha256_file(ROOT / protocol["panel_view_report"]) == protocol["panel_view_report_sha256"],
        "panel view report sha differs",
    )
    training = protocol["training"]
    check(sha256_file(ROOT / training["study"]) == training["study_sha256"], "study-v5 sha differs")
    check(sha256_file(ROOT / training["membership"]) == training["membership_sha256"], "membership sha differs")
    stress_protocol = read_json(ROOT / protocol["reference_protocols"]["modality_stress"])
    check(
        sha256_file(ROOT / protocol["reference_protocols"]["modality_stress"])
        == protocol["reference_protocols"]["modality_stress_sha256"],
        "modality-stress protocol sha differs",
    )
    membership = stress_protocol["membership_rule"]["membership"]
    recomputed = hashlib.sha256(canonical(sorted(membership)).encode()).hexdigest()
    check(
        recomputed == protocol["evaluation"]["membership_sha256"]
        and protocol["evaluation"]["membership"] == membership,
        "frozen 9-task membership differs from #126",
    )
    # Code/protocol byte-match of the frozen contract constants.
    check(views.NOMEM_LEGEND == protocol["arms"][NOMEM_ARM]["legend"], "nomem legend differs")
    check(views.SEQ_LEGEND == protocol["arms"][SEQ_ARM]["legend"], "seq legend differs")
    check(views.HISTORY_K == protocol["history_window"]["k"] == HISTORY_K, "history K differs")
    check(views.NOMEM_RECIPE_ID == protocol["arms"][NOMEM_ARM]["recipe_id"], "nomem recipe id differs")
    check(views.SEQ_RECIPE_ID == protocol["arms"][SEQ_ARM]["recipe_id"], "seq recipe id differs")
    check(
        sorted(protocol["arms"]) == sorted(ARMS)
        and protocol["payload_reduction"]["retained_keys"] == sorted(views.REDUCED_PAYLOAD_KEYS),
        "arm/payload contract differs",
    )
    # Frozen dependencies exist.
    for key in ("corpus_report", "membership", "scene_views"):
        check((ROOT / training[key]).is_file(), f"training dependency missing: {key}")
    check((ROOT / training["scene_views"]).is_file(), "v5 scene views store missing")
    baseline_root = ROOT / protocol["comparators"]["baseline_episodes_root"]
    tasks = load_tasks(protocol)
    for task in tasks:
        for algorithm in protocol["learned_algorithms"]:
            for arm in ("visual-state",):
                for condition in ("process_sft", "pretrained_base"):
                    path = (
                        baseline_root
                        / arm
                        / task["row"]["task_id"].replace("/", "__")
                        / f"{algorithm}-{condition}.json.gz"
                    )
                    check(path.is_file(), f"comparator episode missing: {path.name}")
            for condition in ("random_valid", "exact_reference"):
                path = (
                    baseline_root
                    / "text-state"
                    / task["row"]["task_id"].replace("/", "__")
                    / f"{algorithm}-{condition}.json.gz"
                )
                check(path.is_file(), f"control comparator missing: {path.name}")
    result = {
        "schema_version": "native_arms_validation_v1",
        "protocol_id": protocol["protocol_id"],
        "failures": failures,
        "outcome": "PASS" if not failures else "FAIL",
        "checked_at": time.time(),
    }
    write(output_root(protocol) / "validation.json", result)
    return result


# --------------------------------------------------------------------------- #
# prepare
# --------------------------------------------------------------------------- #


def prepare_stage(arm: str) -> dict:
    protocol = load_protocol()
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")
    progress = progress_writer()
    out = output_root(protocol) / "preparation" / arm
    store = prepare_arm(
        ROOT,
        arm,
        corpus_report=protocol["training"]["corpus_report"],
        membership_path=protocol["training"]["membership"],
        scene_views_path=protocol["training"]["scene_views"],
        output_dir=out,
        algorithms=list(protocol["learned_algorithms"]),
        progress=progress,
    )
    report = qualification_report(store, arm)
    write(out / "report.json", report)
    return report


# --------------------------------------------------------------------------- #
# probe (GPU)
# --------------------------------------------------------------------------- #


def probe_stage(arm: str, endpoint: str) -> dict:
    import torch

    from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
    from examples.planning_benchmark_slice.visual_model import VisualPolicy

    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError("native-arm probe requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("native-arm probe requires an explicit scheduler MASTER_PORT")
    protocol = load_protocol()
    tasks = load_tasks(protocol)
    progress = progress_writer()
    out = output_root(protocol) / "probe" / arm
    gate = protocol["admission_gate"]
    calls = []
    from examples.planning_benchmark_slice.expanded_generalization_eval import V2VisualSession
    from examples.planning_benchmark_slice.native_arm_views import NativeArmTaskViews

    policy = VisualPolicy(
        model_id=protocol["model_id"],
        revision=protocol["model_revision"],
        adapter_paths={},
        device="cuda:0",
        max_context_tokens=32768,
        max_new_tokens=384,
        max_batch_size=protocol["inference"]["max_batch_size"],
        max_batch_input_tokens=protocol["inference"]["max_padded_batch_input_tokens"],
        inference_dtype=protocol["inference"]["dtype"],
    )
    configure_visual_attention(policy.model, protocol["inference"]["attention"])
    from transformers import set_seed

    set_seed(int(protocol["training_seed"]))
    completed = 0
    total = len(tasks) * len(protocol["learned_algorithms"])
    for task in tasks:
        for algorithm in protocol["learned_algorithms"]:
            view_output = out / "views" / task["row"]["task_id"].replace("/", "__") / algorithm
            episode = out / "episodes" / task["row"]["task_id"].replace("/", "__") / f"{algorithm}-probe.json.gz"
            if episode.exists():
                record = read_json(episode)
            else:
                views = NativeArmTaskViews(ROOT, task, view_output, endpoint, arm=arm)
                session = V2VisualSession(
                    ROOT,
                    task["row"],
                    algorithm,
                    "pretrained_base",
                    int(protocol["training_seed"]),
                    episode,
                    protocol["protocol_id"],
                    views=views,
                    model_call_cap=BASE_MODEL_CALL_CAP,
                )
                request = session.next_request()
                if request is None:
                    raise ValueError("probe session produced no first decision")
                example = views.observe(dict(request.model_input), algorithm, modality=arm)
                started = time.monotonic()
                generated = policy.generate([example], None)[0]
                wall = time.monotonic() - started
                session.submit(generated, example["binding"])
                record = {
                    "schema_version": "native_arms_probe_call_v1",
                    "arm": arm,
                    "task_id": task["row"]["task_id"],
                    "algorithm": algorithm,
                    "input_tokens": example["binding"]["input_tokens"],
                    "call_wall_seconds": wall,
                    "generated": generated,
                    "accepted": session.events[-1]["accepted"],
                    "termination": session.result()["termination_reason"],
                }
                write(episode, record)
                views.save()
                del session, views
            calls.append(record)
            completed += 1
            progress("probe", completed=completed, total=total, arm=arm)
    del policy
    gc.collect()
    torch.cuda.empty_cache()
    accepted = sum(1 for call in calls if call["accepted"])
    walls = [call["call_wall_seconds"] for call in calls]
    result = {
        "schema_version": "native_arms_probe_v1",
        "protocol_id": protocol["protocol_id"],
        "arm": arm,
        "calls": calls,
        "call_count": len(calls),
        "accepted_count": accepted,
        "accepted_rate": accepted / max(1, len(calls)),
        "threshold": gate["minimum_schema_valid_grounded_rate"],
        "max_observed_call_seconds": max(walls),
        "mean_observed_call_seconds": statistics.fmean(walls),
        "max_observed_input_tokens": max(call["input_tokens"] for call in calls),
        "mean_observed_input_tokens": statistics.fmean(call["input_tokens"] for call in calls),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": os.environ.get("MASTER_PORT"),
    }
    result["gate"] = "PASS" if result["accepted_rate"] >= gate["minimum_schema_valid_grounded_rate"] else "FAIL"
    write(out / "probe.json", result)
    progress("probe", completed=completed, total=total, terminal=True, arm=arm)
    return result


def audit_probe_stage(arm: str) -> dict:
    protocol = load_protocol()
    probe = read_json(output_root(protocol) / "probe" / arm / "probe.json")
    episodes = list((output_root(protocol) / "probe" / arm / "episodes").rglob("*-probe.json.gz"))
    ok = (
        probe["call_count"] == len(episodes) == 18
        and probe["gate"] in ("PASS", "FAIL")
        and abs(probe["accepted_rate"] - probe["accepted_count"] / probe["call_count"]) < 1e-12
    )
    return {"schema_version": "native_arms_probe_audit_v1", "arm": arm, "ok": ok, "gate": probe["gate"]}


# --------------------------------------------------------------------------- #
# admission
# --------------------------------------------------------------------------- #


def admission_stage() -> dict:
    protocol = load_protocol()
    tasks = load_tasks(protocol)
    estimates = protocol["estimand"]
    probes = {arm: read_json(output_root(protocol) / "probe" / arm / "probe.json") for arm in ARMS}
    prep = {
        arm: read_json(output_root(protocol) / "preparation" / arm / "report.json") for arm in ARMS
    }
    for arm in ARMS:
        if prep[arm]["outcome"] != "PASS":
            raise ValueError(f"preparation for {arm} did not pass its structural gates")
    ref_decisions = {
        (task["row"]["task_id"], algorithm): task["row"]["reference_costs"][algorithm]["decisions"]
        for task in tasks
        for algorithm in protocol["learned_algorithms"]
    }
    cap_multiplier = int(estimates["parameters"]["decision_cap_multiplier"])
    safety = float(estimates["parameters"]["safety_factor"])
    overhead_jobs = int(estimates["parameters"]["planned_worker_jobs"])
    overhead_seconds = float(estimates["parameters"]["planned_worker_overhead_seconds"])
    cell_basis = V5_TRAINING_SECONDS_PER_CELL_BASIS

    def episode_seconds(arm: str, corrupted: bool) -> float:
        price = probes[arm]["max_observed_call_seconds"]
        if corrupted and arm == SEQ_ARM:
            price = max(price, probes[SEQ_ARM]["max_observed_call_seconds"])
        return sum(
            (cap_multiplier * ref_decisions[(task["row"]["task_id"], algorithm)] + 1) * price
            for task in tasks
            for algorithm in protocol["learned_algorithms"]
        )

    def train_hours(arms: list[str]) -> float:
        total = 0.0
        for arm in arms:
            ratio = 1.0
            if arm == SEQ_ARM:
                histogram = prep[arm]["history_page_count_histogram"]
                frames = sum(int(count) * int(size) for size, count in histogram.items())
                records = prep[arm]["counts"]["records"]
                ratio = 1.0 + (frames / max(1, records)) / 4.0
            total += cell_basis * ratio * len(protocol["learned_algorithms"])
        return total

    clean_eval_hours = sum(episode_seconds(arm, False) for arm in ARMS) / 3600 * safety
    corruption_eval_hours = episode_seconds(SEQ_ARM, True) / 3600 * safety
    training_hours = train_hours(list(ARMS)) * safety
    overhead_hours = overhead_jobs * overhead_seconds / 3600
    required = training_hours + clean_eval_hours + corruption_eval_hours + overhead_hours
    min_scope_train = train_hours([NOMEM_ARM]) * safety
    min_scope_eval = episode_seconds(NOMEM_ARM, False) / 3600 * safety
    min_scope = min_scope_train + min_scope_eval + overhead_hours

    gates = {arm: probes[arm]["gate"] for arm in ARMS}
    passing_arms = [arm for arm in ARMS if gates[arm] == "PASS"]
    window_cap = float(protocol["budget"]["window_gpu_hours_cap"])
    budget_ok = required <= window_cap
    min_scope_ok = min_scope <= window_cap
    admission = {
        "schema_version": protocol["admission"]["schema_version"],
        "protocol_id": protocol["protocol_id"],
        "decision": "PASS" if (passing_arms and budget_ok and min_scope_ok) else "VALID_STOP",
        "arm_gates": gates,
        "minimum_meaningful_scope": {
            "arms": [NOMEM_ARM],
            "gpu_hours": min_scope,
            "fits_window": min_scope_ok,
        },
        "budget": {
            "window_gpu_hours_cap": window_cap,
            "training_gpu_hours": training_hours,
            "clean_evaluation_gpu_hours": clean_eval_hours,
            "corruption_evaluation_gpu_hours": corruption_eval_hours,
            "worker_overhead_gpu_hours": overhead_hours,
            "required_gpu_hours": required,
            "fits_window": budget_ok,
        },
        "price_basis": {
            "per_arm_max_observed_call_seconds": {
                arm: probes[arm]["max_observed_call_seconds"] for arm in ARMS
            },
            "training_cell_basis_gpu_hours": cell_basis,
            "reference_decision_multiplier": cap_multiplier,
            "safety_factor": safety,
        },
        "no_test_driven_retraining": True,
        "no_outcome_selected_reruns": True,
        "no_favourable_replacement_tasks": True,
    }
    write(output_root(protocol) / "admission.json", admission)
    return admission


# --------------------------------------------------------------------------- #
# training
# --------------------------------------------------------------------------- #


def train_stage(arm: str) -> dict:
    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError("native-arm training requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("native-arm training requires an explicit scheduler MASTER_PORT")
    protocol = load_protocol()
    training = protocol["training"]
    membership = read_json(ROOT / training["membership"])
    progress = progress_writer()
    results = []
    for algorithm in protocol["learned_algorithms"]:
        output = output_root(protocol) / "training" / arm / algorithm
        store = NativeArmStore(ROOT, output_root(protocol) / "preparation" / arm / "store.json")

        def factory(root, config, algo, split, store=store, membership=membership):
            return NativeArmTrainingDataset(root, store, membership, algo, split)

        config = {
            **read_json(ROOT / training["study"]),
            "modality": arm,
            "training_seed": int(protocol["training_seed"]),
        }
        deadline = time.monotonic() + float(protocol["training"]["max_seconds_per_cell"])
        result = train_visual(
            config,
            ROOT,
            algorithm,
            output,
            deadline=deadline,
            progress=progress,
            dataset_factory=factory,
        )
        result["arm"] = arm
        results.append(result)
        progress("train", completed=len(results), total=len(protocol["learned_algorithms"]), arm=arm)
    summary = {
        "schema_version": "native_arms_training_v1",
        "protocol_id": protocol["protocol_id"],
        "arm": arm,
        "cells": results,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": os.environ.get("MASTER_PORT"),
        "outcome": "PASS",
    }
    write(output_root(protocol) / "training" / arm / "report.json", summary)
    return summary


def audit_train_stage(arm: str) -> dict:
    protocol = load_protocol()
    summary = read_json(output_root(protocol) / "training" / arm / "report.json")
    ok = len(summary["cells"]) == len(protocol["learned_algorithms"])
    for cell in summary["cells"]:
        checkpoint = output_root(protocol) / "training" / arm / cell["algorithm"] / "final"
        adapter = checkpoint / "adapter_model.safetensors"
        config_file = checkpoint / "adapter_config.json"
        ok = ok and adapter.is_file() and config_file.is_file()
        adapter_config = read_json(config_file)
        ok = ok and adapter_config.get("r") == 64 and adapter_config.get("lora_alpha") == 128
        ok = ok and cell["steps"] == 16 and cell["seed"] == 17 and cell["train_records"] == 512
    return {"schema_version": "native_arms_train_audit_v1", "arm": arm, "ok": ok}

def arm_smoke_gate(protocol: dict, arm: str) -> str | None:
    """PASS/FAIL from the arm's frozen smoke report; None when absent."""

    path = output_root(protocol) / "smoke" / arm / "smoke.json"
    if not path.is_file():
        return None
    return read_json(path)["gate"]


def smoke_stage(arm: str, endpoint: str) -> dict:
    """Post-training held-out smoke gate: learned adapter, clean contract."""

    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError("native-arm smoke requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("native-arm smoke requires an explicit scheduler MASTER_PORT")
    protocol = load_protocol()
    gate_spec = protocol["smoke_gate"]
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")
    all_tasks = {task["row"]["task_id"]: task for task in load_tasks(protocol)}
    tasks = [all_tasks[task_id] for task_id in gate_spec["subset"]]
    if len(tasks) != len(gate_spec["subset"]):
        raise ValueError("smoke subset differs from the frozen panel membership")
    adapters = {
        algorithm: str(output_root(protocol) / "training" / arm / algorithm / "final")
        for algorithm in protocol["learned_algorithms"]
    }
    for path in adapters.values():
        if not (ROOT / path / "adapter_model.safetensors").is_file():
            raise ValueError(f"native-arm adapter checkpoint missing: {path}")
    from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
    from examples.planning_benchmark_slice.visual_model import VisualPolicy

    progress = progress_writer()
    policy = VisualPolicy(
        model_id=protocol["model_id"],
        revision=protocol["model_revision"],
        adapter_paths={key: ROOT / value for key, value in adapters.items()},
        device="cuda:0",
        max_context_tokens=32768,
        max_new_tokens=384,
        max_batch_size=protocol["inference"]["max_batch_size"],
        max_batch_input_tokens=protocol["inference"]["max_padded_batch_input_tokens"],
        inference_dtype=protocol["inference"]["dtype"],
    )
    configure_visual_attention(policy.model, protocol["inference"]["attention"])
    policy.identity.update(memoize_identical_inputs=False)
    from transformers import set_seed

    set_seed(int(protocol["training_seed"]))
    reports = []
    index = 0
    total_calls = 0
    valid_calls = 0
    for task in tasks:
        for algorithm in protocol["learned_algorithms"]:
            binding = {
                "index": index,
                "worker": 0,
                "kind": "models",
                "phase": "smoke",
                "arm": arm,
                "family": None,
                "task_id": task["row"]["task_id"],
                "algorithm": algorithm,
                "condition": "learned_adapter",
                "seed": int(protocol["training_seed"]),
            }
            index += 1

            def generate(example, algorithm=algorithm, policy=policy):
                output = policy.generate([example], algorithm)[0]
                return output, policy.last_generation_usage["generated_sequence_tokens"]

            report, _ = run_binding(ROOT, protocol, task, binding, adapters[binding["algorithm"]], endpoint, generate)
            reports.append(report)
            total_calls += len(report["events"])
            valid_calls += sum(1 for event in report["events"] if event["accepted"])
            progress("smoke", completed=len(reports), total=len(tasks) * len(protocol["learned_algorithms"]), arm=arm)
    del policy
    gc.collect()
    import torch

    torch.cuda.empty_cache()
    rate = valid_calls / max(1, total_calls)
    result = {
        "schema_version": "native_arms_smoke_v1",
        "protocol_id": protocol["protocol_id"],
        "arm": arm,
        "subset": gate_spec["subset"],
        "episodes": [report["output"] for report in reports],
        "model_calls": total_calls,
        "schema_valid_grounded_calls": valid_calls,
        "schema_valid_grounded_rate": rate,
        "threshold": gate_spec["minimum_schema_valid_grounded_rate"],
        "gate": "PASS" if rate >= gate_spec["minimum_schema_valid_grounded_rate"] else "FAIL",
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": os.environ.get("MASTER_PORT"),
    }
    write(output_root(protocol) / "smoke" / arm / "smoke.json", result)
    progress("smoke", completed=len(reports), total=len(reports), terminal=True, arm=arm)
    return result


def audit_smoke_stage(arm: str) -> dict:
    protocol = load_protocol()
    smoke = read_json(output_root(protocol) / "smoke" / arm / "smoke.json")
    episodes = list((output_root(protocol) / "evaluation" / "episodes" / "smoke" / arm).rglob("*.json.gz"))
    ok = (
        len(episodes) == 6
        and smoke["model_calls"] > 0
        and abs(
            smoke["schema_valid_grounded_rate"] - smoke["schema_valid_grounded_calls"] / smoke["model_calls"]
        )
        < 1e-12
        and smoke["gate"] in ("PASS", "FAIL")
    )
    summary = {
        "schema_version": "native_arms_smoke_audit_v1",
        "arm": arm,
        "ok": ok,
        "gate": smoke["gate"],
        "rate": smoke["schema_valid_grounded_rate"],
    }
    write(output_root(protocol) / "smoke" / arm / "audit.json", summary)
    return summary


def admission_v2_stage() -> dict:
    """v2 admission: corpus/budget gates only; the smoke gate adjudicates after training."""

    protocol = load_protocol()
    tasks = load_tasks(protocol)
    estimates = protocol["estimand_v2"]
    prep = {arm: read_json(output_root(protocol) / "preparation" / arm / "report.json") for arm in ARMS}
    for arm in ARMS:
        if prep[arm]["outcome"] != "PASS":
            raise ValueError(f"preparation for {arm} did not pass its structural gates")
    ledger = read_json(LEDGER_PATH)
    spent = sum(attempt.get("gpu_hours", 0) for attempt in ledger["attempts"])
    cap = float(protocol["budget"]["window_gpu_hours_cap"])
    remainder = cap - spent
    ref_decisions = {
        (task["row"]["task_id"], algorithm): task["row"]["reference_costs"][algorithm]["decisions"]
        for task in tasks
        for algorithm in protocol["learned_algorithms"]
    }
    safety = float(estimates["safety_factor"])
    cell_basis = V5_TRAINING_SECONDS_PER_CELL_BASIS

    def train_hours() -> float:
        total = 0.0
        for arm in ARMS:
            ratio = 1.0
            if arm == SEQ_ARM:
                histogram = prep[arm]["history_page_count_histogram"]
                frames = sum(int(count) * int(size) for size, count in histogram.items())
                ratio = 1.0 + (frames / max(1, prep[arm]["counts"]["records"])) / 4.0
            total += cell_basis * ratio * len(protocol["learned_algorithms"])
        return total * safety

    def episode_seconds(arms: list[str], price_key: str = "probe_max_call_seconds") -> float:
        price = float(estimates[price_key])
        return sum(
            (2 * ref_decisions[(task["row"]["task_id"], algorithm)] + 1) * price * instances
            for task in tasks
            for algorithm in protocol["learned_algorithms"]
            for instances in [len(arms)]
        )

    smoke_subset = protocol["smoke_gate"]["subset"]
    smoke_seconds = sum(
        (2 * ref_decisions[(task_id, algorithm)] + 1) * float(estimates["probe_max_call_seconds"]) * 2
        for task_id in smoke_subset
        for algorithm in protocol["learned_algorithms"]
        for _ in [0]
    )
    training_hours = train_hours()
    smoke_hours = smoke_seconds / 3600 * safety
    clean_hours = episode_seconds(list(ARMS)) / 3600 * safety
    corruption_hours = episode_seconds([SEQ_ARM]) / 3600 * safety
    overhead = int(estimates["planned_worker_jobs"]) * float(estimates["planned_worker_overhead_seconds"]) / 3600
    required = training_hours + smoke_hours + clean_hours + corruption_hours + overhead
    admission = {
        "schema_version": "native_arms_admission_v2",
        "protocol_id": protocol["protocol_id"],
        "decision": "PASS" if required <= remainder else "VALID_STOP",
        "budget": {
            "window_gpu_hours_cap": cap,
            "spent_gpu_hours": spent,
            "remainder_gpu_hours": remainder,
            "training_gpu_hours": training_hours,
            "smoke_gpu_hours": smoke_hours,
            "clean_evaluation_gpu_hours": clean_hours,
            "corruption_evaluation_gpu_hours": corruption_hours,
            "worker_overhead_gpu_hours": overhead,
            "required_gpu_hours": required,
        },
        "gate_note": (
            "pretrained-base format compliance is not a v2 admission condition; each arm's rung "
            "is adjudicated post-training by the frozen smoke gate"
        ),
        "no_test_driven_retraining": True,
        "no_outcome_selected_reruns": True,
        "no_favourable_replacement_tasks": True,
    }
    write(output_root(protocol) / "admission-v2.json", admission)
    return admission


# --------------------------------------------------------------------------- #
# evaluation
# --------------------------------------------------------------------------- #


def bindings(protocol: dict, tasks: list[dict]) -> list[dict]:
    rows = []
    index = 0
    seeds = [s for s in protocol["evaluation"]["random_valid_rollout_seeds"] if s != 17]
    for task in tasks:
        for arm in ARMS:
            for algorithm in protocol["learned_algorithms"]:
                for condition in ("learned_adapter", "pretrained_base"):
                    rows.append(
                        {
                            "index": index,
                            "worker": index % 2,
                            "kind": "models",
                            "phase": "clean",
                            "arm": arm,
                            "family": None,
                            "task_id": task["row"]["task_id"],
                            "algorithm": algorithm,
                            "condition": condition,
                            "seed": int(protocol["training_seed"]),
                        }
                    )
                    index += 1
    for task in tasks:
        for family in protocol["corruption"]["families"]:
            for algorithm in protocol["learned_algorithms"]:
                for condition in ("learned_adapter", "pretrained_base"):
                    rows.append(
                        {
                            "index": index,
                            "worker": index % 2,
                            "kind": "models",
                            "phase": "corruption",
                            "arm": SEQ_ARM,
                            "family": family,
                            "task_id": task["row"]["task_id"],
                            "algorithm": algorithm,
                            "condition": condition,
                            "seed": int(protocol["training_seed"]),
                        }
                    )
                    index += 1
    for task in tasks:
        for algorithm in protocol["learned_algorithms"]:
            for seed in seeds:
                rows.append(
                    {
                        "index": index,
                        "worker": index % 2,
                        "kind": "controls",
                        "phase": "clean",
                        "arm": None,
                        "family": None,
                        "task_id": task["row"]["task_id"],
                        "algorithm": algorithm,
                        "condition": "random_valid",
                        "seed": int(seed),
                    }
                )
                index += 1
    return rows


def evaluate_inputs_stage() -> dict:
    protocol = load_protocol()
    tasks = load_tasks(protocol)
    rows = bindings(protocol, tasks)
    manifest = {
        "schema_version": "native_arms_evaluation_inputs_v1",
        "protocol_id": protocol["protocol_id"],
        "bindings": rows,
        "counts": {
            "models": sum(1 for row in rows if row["kind"] == "models"),
            "controls": sum(1 for row in rows if row["kind"] == "controls"),
            "clean": sum(1 for row in rows if row["phase"] == "clean"),
            "corruption": sum(1 for row in rows if row["phase"] == "corruption"),
        },
    }
    write(output_root(protocol) / "evaluation" / "bindings.json", manifest)
    return manifest


def episode_paths(protocol: dict, binding: dict) -> tuple[Path, Path, Path]:
    evaluation = output_root(protocol) / "evaluation"
    task_name = binding["task_id"].replace("/", "__")
    suffix = binding["family"] or "clean"
    if binding["kind"] == "controls":
        episode = (
            evaluation / "episodes" / "control" / task_name / f"{binding['algorithm']}-rv-{binding['seed']}.json.gz"
        )
        view_output = evaluation / "views" / "control" / task_name / f"{binding['algorithm']}-rv-{binding['seed']}"
    else:
        name = f"{binding['algorithm']}-{suffix}-{binding['condition']}"
        episode = evaluation / "episodes" / binding["phase"] / binding["arm"] / task_name / f"{name}.json.gz"
        view_output = evaluation / "views" / binding["phase"] / binding["arm"] / task_name / name
    partial = episode.with_name(episode.name + ".partial.json.gz")
    return episode, partial, view_output


def _identity(protocol: dict, binding: dict, episode: Path, view_output: Path, checkpoint) -> dict:
    return {
        "schema_version": "native_arms_episode_v1",
        "protocol_id": protocol["protocol_id"],
        "binding_index": binding["index"],
        "worker": binding["worker"],
        "phase": binding["phase"],
        "family": binding["family"],
        "arm": binding["arm"],
        "modality": binding["arm"] or NOMEM_ARM,
        "task_id": binding["task_id"],
        "algorithm": binding["algorithm"],
        "condition": binding["condition"],
        "seed": binding["seed"],
        "output": str(episode.relative_to(ROOT)),
        "view_output": str(view_output.relative_to(ROOT)),
        "checkpoint": checkpoint,
        "model_id": protocol["model_id"],
        "model_revision": protocol["model_revision"],
        "oracle_assisted_valid_operation_control": binding["condition"] == "random_valid",
    }


def run_binding(root, protocol, task, binding, checkpoint, endpoint, generate, *, paths=None, views=None):
    from examples.planning_benchmark_slice.expanded_baseline import _commit_pending, _restore_events
    from examples.planning_benchmark_slice.expanded_generalization_eval import V2VisualSession
    from examples.planning_benchmark_slice.native_arm_views import NativeArmTaskViews

    episode, partial_path, view_output = paths or episode_paths(protocol, binding)
    expected = _identity(protocol, binding, episode, view_output, checkpoint)
    arm = binding["arm"] or NOMEM_ARM
    corruption = binding["family"] if binding["kind"] == "models" and binding["phase"] == "corruption" else None
    if episode.exists():
        if partial_path.exists():
            raise ValueError("completed episode retains a conflicting partial journal")
        report = read_json(episode)
        if any(report.get(key) != value for key, value in expected.items()):
            raise ValueError("retained episode binding differs")
        independently_replay(root, protocol, task, report, endpoint)
        return report, True
    views = views or NativeArmTaskViews(
        ROOT,
        task,
        view_output,
        endpoint,
        arm=arm,
        corruption=corruption,
        master_seed=int(protocol["corruption"]["master_seed"]),
    )
    session = V2VisualSession(
        ROOT,
        task["row"],
        binding["algorithm"],
        ENGINE_ARM[binding["condition"]],
        binding["seed"],
        episode,
        protocol["protocol_id"],
        views=views,
        model_call_cap=BASE_MODEL_CALL_CAP if binding["condition"] == "pretrained_base" else None,
    )
    saved = (
        read_json(partial_path)
        if partial_path.exists()
        else {
            **expected,
            "events": [],
            "call_measurements": [],
            "pending": None,
            "started": time.time(),
            "active_wall_seconds": 0.0,
        }
    )
    if any(saved.get(key) != value for key, value in expected.items()):
        raise ValueError("partial episode binding differs")
    attempt_started = time.monotonic()
    _restore_events(session, views, saved)
    _commit_pending(session, views, saved)
    saved["active_wall_seconds"] += time.monotonic() - attempt_started
    write(partial_path, saved)
    checkpoint_started = time.monotonic()
    from PIL import Image

    while (request := session.next_request()) is not None:
        raw = dict(request.model_input)
        example = views.observe(raw, binding["algorithm"], modality=arm)
        call_started = time.monotonic()
        try:
            if generate is None:
                generated = session.reference_output()
                generated_tokens = None
            else:
                generated, generated_tokens = generate(example)
        finally:
            for image in example["images"]:
                if isinstance(image, Image.Image):
                    image.close()
        measurement = {
            "event_index": len(session.events),
            "model_call": binding["condition"] in {"learned_adapter", "pretrained_base"},
            "input_tokens": example["binding"]["input_tokens"],
            "generated_sequence_tokens": generated_tokens,
            "call_wall_seconds": time.monotonic() - call_started,
        }
        saved["pending"] = {
            "input": raw,
            "binding": example["binding"],
            "raw_output": generated,
            "measurement": measurement,
        }
        saved["active_wall_seconds"] += time.monotonic() - checkpoint_started
        write(partial_path, saved)
        checkpoint_started = time.monotonic()
        _commit_pending(session, views, saved)
        saved["active_wall_seconds"] += time.monotonic() - checkpoint_started
        write(partial_path, saved)
        checkpoint_started = time.monotonic()
    report = {
        **expected,
        "outcome": "RECORDED",
        "events": saved["events"],
        "result": session.result(),
        "call_measurements": saved["call_measurements"],
        "started": saved["started"],
        "finished": time.time(),
        "active_wall_seconds": saved["active_wall_seconds"] + time.monotonic() - checkpoint_started,
        "raw_invalid_outputs_preserved": sum(not event["accepted"] for event in saved["events"]),
    }
    views.save()
    write(episode, report)
    partial_path.unlink()
    return report, False


def independently_replay(root, protocol, task, report, endpoint):
    from examples.planning_benchmark_slice.expanded_generalization_eval import V2VisualSession

    views = replay_views(protocol, task, report, endpoint)
    replay_report = dict(report, arm=ENGINE_ARM[report["condition"]], contract_id=report["protocol_id"])
    return replay_visual_episode(
        ROOT,
        task["row"],
        replay_report,
        views,
        session_class=lambda *args, **kwargs: V2VisualSession(
            *args, model_call_cap=int(report["result"]["model_call_limit"]), **kwargs
        ),
    )


def replay_views(protocol, task, report, endpoint):
    """Rebuild the exact frozen views class for an episode's phase."""

    phase = report.get("phase")
    if phase == "menu":
        from examples.planning_benchmark_slice.native_arm_stress import MenuStressTaskViews

        return MenuStressTaskViews(
            ROOT,
            task,
            ROOT / report["view_output"],
            endpoint,
            read_only=True,
            arm=report["arm"],
            menu_family=report["family"],
        )
    if phase == "textmask":
        from examples.planning_benchmark_slice.expanded_modality_stress import StressTaskViews

        return StressTaskViews(
            ROOT,
            task,
            ROOT / report["view_output"],
            endpoint,
            read_only=True,
            corruption="text-masked",
            master_seed=int(protocol["corruption"]["master_seed"]),
        )
    from examples.planning_benchmark_slice.native_arm_views import NativeArmTaskViews

    corruption = report.get("family") if phase == "corruption" else None
    return NativeArmTaskViews(
        ROOT,
        task,
        ROOT / report["view_output"],
        endpoint,
        read_only=True,
        arm=report["arm"] or NOMEM_ARM,
        corruption=corruption,
        master_seed=int(protocol["corruption"]["master_seed"]),
    )


def verify_comparator(root, protocol, task, arm, algorithm, condition, seed, expected_protocol):
    episode = (
        ROOT
        / protocol["comparators"]["baseline_episodes_root"]
        / arm
        / task["row"]["task_id"].replace("/", "__")
        / f"{algorithm}-{condition}.json.gz"
    )
    report = read_json(episode)
    if (
        report["task_id"] != task["row"]["task_id"]
        or report["algorithm"] != algorithm
        or report["arm"] != condition
        or report["seed"] != seed
        or report["model_id"] != protocol["model_id"]
        or report["model_revision"] != protocol["model_revision"]
        or report["protocol_id"] != expected_protocol
    ):
        raise ValueError("reused comparator episode identity differs")
    views = ExpandedTaskViews(ROOT, task, ROOT / report["view_output"], "http://127.0.0.1:18092", read_only=True)
    replay_report = dict(report, arm=report["arm"], contract_id=report["protocol_id"])
    replay_visual_episode(ROOT, task["row"], replay_report, views)
    return report


def evaluate_worker(worker: int, kind: str, endpoint: str) -> dict:
    protocol = load_protocol()
    tasks = load_tasks(protocol)
    manifest = read_json(output_root(protocol) / "evaluation" / "bindings.json")
    rows = [row for row in manifest["bindings"] if row["worker"] == worker and row["kind"] == kind]
    expected = sum(1 for row in manifest["bindings"] if row["kind"] == kind) // 2
    if len(rows) != expected:
        raise ValueError("native-arm worker partition differs from frozen equal coverage")
    if kind == "models":
        if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
            raise ValueError("native-arm model worker requires CUDA_VISIBLE_DEVICES isolation")
        if not os.environ.get("MASTER_PORT"):
            raise ValueError("native-arm model worker requires an explicit scheduler MASTER_PORT")
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    completed = 0
    retained = 0
    model_calls = 0
    reports = []
    started = time.monotonic()
    groups = []
    if kind == "models":
        for arm in ARMS:
            gate = arm_smoke_gate(protocol, arm)
            if gate is None:
                raise ValueError(f"native-arm evaluation requires the frozen smoke gate for {arm}")
            if gate == "FAIL":
                continue
            for phase in PHASES:
                if phase == "corruption" and arm != SEQ_ARM:
                    continue
                group = [row for row in rows if row["arm"] == arm and row["phase"] == phase]
                if group:
                    groups.append(((arm, phase), group))
    else:
        groups = [(("control", "clean"), list(rows))]
    for (arm, phase), group in groups:
        pending = [row for row in group if not episode_paths(protocol, row)[0].exists()]
        policy = None
        adapters = {
            algorithm: str(output_root(protocol) / "training" / arm / algorithm / "final")
            for algorithm in protocol["learned_algorithms"]
        }
        if kind == "models":
            for path in adapters.values():
                if not (ROOT / path / "adapter_model.safetensors").is_file():
                    raise ValueError(f"native-arm adapter checkpoint missing: {path}")
        else:
            adapters = {}
        if kind == "models" and pending:
            from transformers import set_seed

            from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
            from examples.planning_benchmark_slice.visual_model import VisualPolicy

            set_seed(int(protocol["training_seed"]))
            policy = VisualPolicy(
                model_id=protocol["model_id"],
                revision=protocol["model_revision"],
                adapter_paths={key: ROOT / value for key, value in adapters.items()},
                device="cuda:0",
                max_context_tokens=32768,
                max_new_tokens=384,
                max_batch_size=protocol["inference"]["max_batch_size"],
                max_batch_input_tokens=protocol["inference"]["max_padded_batch_input_tokens"],
                inference_dtype=protocol["inference"]["dtype"],
            )
            configure_visual_attention(policy.model, protocol["inference"]["attention"])
            policy.identity.update(memoize_identical_inputs=False)
        for binding in group:
            condition = binding["condition"]
            checkpoint = adapters.get(binding["algorithm"]) if condition == "learned_adapter" else None

            def generate(example, condition=condition, algorithm=binding["algorithm"], policy=policy):
                nonlocal model_calls
                adapter = algorithm if condition == "learned_adapter" else None
                output = policy.generate([example], adapter)[0]
                model_calls += 1
                return output, policy.last_generation_usage["generated_sequence_tokens"]

            generate_fn = None if kind == "controls" else generate
            report, was_retained = run_binding(
                ROOT,
                protocol,
                task_by_id[binding["task_id"]],
                binding,
                checkpoint,
                endpoint,
                generate_fn,
            )
            retained += int(was_retained)
            reports.append(report["output"])
            completed += 1
            write(
                progress_path,
                {
                    "completed": completed,
                    "total": len(rows),
                    "retained": retained,
                    "model_calls": model_calls,
                    "group": f"{arm}:{phase}",
                },
            )
            print(
                {
                    "stage": "native_arms_episode",
                    "worker": worker,
                    "kind": kind,
                    "group": f"{arm}:{phase}",
                    "completed": completed,
                    "total": len(rows),
                    "binding_index": binding["index"],
                    "result": report["result"]["termination_reason"],
                },
                flush=True,
            )
        if policy is not None:
            del policy
            gc.collect()
            import torch

            torch.cuda.empty_cache()
    result = {
        "schema_version": "native_arms_evaluation_worker_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "kind": kind,
        "episodes": reports,
        "completed": completed,
        "retained": retained,
        "model_calls": model_calls,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": os.environ.get("MASTER_PORT"),
        "elapsed_seconds": time.monotonic() - started,
    }
    write(attempt_dir / "worker-result.json", result)
    write(progress_path, {"completed": completed, "total": len(rows), "terminal": True})
    return result


def audit_evaluate_worker(worker: int, kind: str) -> dict:
    protocol = load_protocol()
    terminal = Path(os.environ["EXPANDED_TERMINAL_PATH"])
    attempt = read_json(terminal)
    result_path = Path(attempt["directory"]) / "worker-result.json"
    ok = result_path.is_file()
    if ok:
        result = read_json(result_path)
        ok = result["outcome"] == "PASS" and result["worker"] == worker and result["kind"] == kind
    summary = {
        "schema_version": "native_arms_worker_audit_v1",
        "worker": worker,
        "kind": kind,
        "ok": ok,
        "job_id": attempt.get("job_id"),
        "status": attempt.get("status"),
        "gpu_hours": attempt.get("gpu_hours"),
    }
    write(output_root(protocol) / "evaluation" / f"audit-{kind}-{worker}.json", summary)
    return summary


# --------------------------------------------------------------------------- #
# finalize + analysis
# --------------------------------------------------------------------------- #


def _success(report: dict) -> int:
    return int(bool(report["result"].get("invariant_valid_success")))


def bootstrap_delta(pairs: list[int]) -> dict:
    """Frozen bootstrap over paired whole-problem differences."""

    generator = random.Random(BOOTSTRAP_SEED)
    if not pairs:
        return {"n": 0, "mean": None, "low": None, "high": None, "material": None}
    count = len(pairs)
    means = sorted(
        sum(pairs[i] for i in indices) / count
        for indices in (
            [generator.randrange(count) for _ in range(count)] for _ in range(BOOTSTRAP_RESAMPLES)
        )
    )
    low = means[int(0.025 * BOOTSTRAP_RESAMPLES)]
    high = means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1]
    return {
        "n": count,
        "mean": sum(pairs) / count,
        "low": low,
        "high": high,
        "material": bool(low > 0 or high < 0),
        "descriptive_only": count < TINY_STRATUM_LIMIT,
    }


def finalize_stage(endpoint: str) -> dict:
    protocol = load_protocol()
    tasks = load_tasks(protocol)
    manifest = read_json(output_root(protocol) / "evaluation" / "bindings.json")
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    new_reports = []
    missing = []
    gated_out = []
    failed_arms = {arm for arm in ARMS if arm_smoke_gate(protocol, arm) == "FAIL"}
    for binding in manifest["bindings"]:
        episode, _, _ = episode_paths(protocol, binding)
        if binding["kind"] == "models" and binding["arm"] in failed_arms:
            gated_out.append(binding["index"])
            continue
        if not episode.exists():
            missing.append(binding["index"])
            continue
        report = read_json(episode)
        independently_replay(ROOT, protocol, task_by_id[binding["task_id"]], report, endpoint)
        new_reports.append(report)
    comparators = []
    baseline_protocol = protocol["comparators"]["baseline_protocol_id"]
    for task in tasks:
        for algorithm in protocol["learned_algorithms"]:
            for condition in ("process_sft", "pretrained_base"):
                comparators.append(
                    verify_comparator(
                        ROOT,
                        protocol,
                        task,
                        "visual-state",
                        algorithm,
                        condition,
                        int(protocol["training_seed"]),
                        baseline_protocol,
                    )
                )
            for condition in ("random_valid", "exact_reference"):
                comparators.append(
                    verify_comparator(
                        ROOT,
                        protocol,
                        task,
                        "text-state",
                        algorithm,
                        condition,
                        int(protocol["training_seed"]),
                        baseline_protocol,
                    )
                )
    evaluation = {
        "schema_version": "native_arms_evaluation_v1",
        "protocol_id": protocol["protocol_id"],
        "membership_sha256": protocol["evaluation"]["membership_sha256"],
        "outcome": "PASS" if not missing else "INCOMPLETE",
        "bindings_total": len(manifest["bindings"]),
        "episodes_replayed": len(new_reports),
        "comparator_episodes_replayed": len(comparators),
        "missing_bindings": missing,
        "gated_out_by_smoke": gated_out,
        "smoke_gates": {arm: arm_smoke_gate(protocol, arm) for arm in ARMS},
    }
    write(output_root(protocol) / "evaluation" / "evaluation.json", evaluation)
    analysis = analyze(protocol, tasks, manifest, new_reports, comparators)
    write(output_root(protocol) / "evaluation" / "analysis.json", analysis)
    return {"evaluation": evaluation, "analysis_summary": analysis["summary"]}


def analyze(protocol, tasks, manifest, new_reports, comparators) -> dict:
    by_key = {}
    for report in new_reports:
        by_key[
            (
                report["task_id"],
                report["algorithm"],
                report.get("arm"),
                report.get("phase"),
                report.get("family"),
                report["condition"],
            )
        ] = report
    comparator_by_key = {}
    for report in comparators:
        comparator_by_key[(report["task_id"], report["algorithm"], report["arm"])] = report
    control_seed17 = {
        (report["task_id"], report["algorithm"]): report
        for report in comparators
        if report["arm"] == "random_valid"
    }
    exact = {
        (report["task_id"], report["algorithm"]): report
        for report in comparators
        if report["arm"] == "exact_reference"
    }
    visual_learned = {
        (report["task_id"], report["algorithm"]): report
        for report in comparators
        if report["arm"] == "process_sft"
    }
    visual_base = {
        (report["task_id"], report["algorithm"]): report
        for report in comparators
        if report["arm"] == "pretrained_base"
    }
    random_frequency = {}
    for (task_id, algorithm), report in control_seed17.items():
        seeds = [_success(report)]
        for binding in manifest["bindings"]:
            if (
                binding["kind"] == "controls"
                and binding["task_id"] == task_id
                and binding["algorithm"] == algorithm
            ):
                episode = episode_paths(protocol, binding)[0]
                if episode.exists():
                    seeds.append(_success(read_json(episode)))
        random_frequency[(task_id, algorithm)] = sum(seeds) / len(seeds)

    cells = {}
    for task in tasks:
        for algorithm in protocol["learned_algorithms"]:
            key = (task["row"]["task_id"], algorithm)
            cell = {
                "published_visual_learned": _success(visual_learned[key]),
                "published_visual_base": _success(visual_base[key]),
                "random_valid_frequency": random_frequency[key],
                "exact_reference": _success(exact[key]),
            }
            for arm in ARMS:
                clean_learned = by_key.get((key[0], key[1], arm, "clean", None, "learned_adapter"))
                clean_base = by_key.get((key[0], key[1], arm, "clean", None, "pretrained_base"))
                if clean_learned and clean_base:
                    cell[arm] = {
                        "learned": _success(clean_learned),
                        "base": _success(clean_base),
                        "learned_decisions": clean_learned["result"]["decision_count"],
                        "learned_invalid": clean_learned["result"]["invalid_operation_count"],
                    }
            for family in protocol["corruption"]["families"]:
                corrupted = by_key.get((key[0], key[1], SEQ_ARM, "corruption", family, "learned_adapter"))
                corrupted_base = by_key.get((key[0], key[1], SEQ_ARM, "corruption", family, "pretrained_base"))
                if corrupted and corrupted_base:
                    cell[f"seq:{family}"] = {
                        "learned": _success(corrupted),
                        "base": _success(corrupted_base),
                        "learned_decisions": corrupted["result"]["decision_count"],
                        "learned_invalid": corrupted["result"]["invalid_operation_count"],
                    }
            cells[f"{key[0]}|{key[1]}"] = cell

    def paired(fn, requires=()) -> list[int]:
        return [fn(cell) for cell in cells.values() if all(cell.get(key) for key in requires)]

    contrasts = {
        "nomem_vs_published_visual": bootstrap_delta(
            paired(
                lambda c: c[NOMEM_ARM]["learned"] - c["published_visual_learned"],
                requires=(NOMEM_ARM,),
            )
        ),
        "seq_vs_published_visual": bootstrap_delta(
            paired(
                lambda c: c[SEQ_ARM]["learned"] - c["published_visual_learned"],
                requires=(SEQ_ARM,),
            )
        ),
        "ladder_seq_minus_nomem": bootstrap_delta(
            paired(
                lambda c: c[SEQ_ARM]["learned"] - c[NOMEM_ARM]["learned"],
                requires=(NOMEM_ARM, SEQ_ARM),
            )
        ),
        "nomem_learned_minus_base": bootstrap_delta(
            paired(
                lambda c: c[NOMEM_ARM]["learned"] - c[NOMEM_ARM]["base"],
                requires=(NOMEM_ARM,),
            )
        ),
        "seq_learned_minus_base": bootstrap_delta(
            paired(lambda c: c[SEQ_ARM]["learned"] - c[SEQ_ARM]["base"], requires=(SEQ_ARM,))
        ),
    }
    for family in protocol["corruption"]["families"]:
        contrasts[f"corruption:{family}:seq_corrupted_minus_clean"] = bootstrap_delta(
            paired(
                lambda c, family=family: c[f"seq:{family}"]["learned"] - c[SEQ_ARM]["learned"],
                requires=(SEQ_ARM, f"seq:{family}"),
            )
        )
    present_arms = [arm for arm in ARMS if any(cell.get(arm) for cell in cells.values())]
    best_control_at_ceiling = all(
        max(cell["random_valid_frequency"], *[cell[arm]["base"] for arm in present_arms if cell.get(arm)])
        >= 1.0
        for cell in cells.values()
        if any(cell.get(arm) for arm in present_arms)
    )
    summary = {
        "clean_learned_success": {
            arm: sum(cell[arm]["learned"] for cell in cells.values() if cell.get(arm))
            / max(1, sum(1 for cell in cells.values() if cell.get(arm)))
            for arm in present_arms
        },
        "published_visual_learned_success": sum(
            cell["published_visual_learned"] for cell in cells.values()
        )
        / max(1, len(cells)),
        "contrasts": contrasts,
        "saturation_rule": {
            "best_control_at_ceiling": best_control_at_ceiling,
            "structural_advantage_claim": not best_control_at_ceiling,
        },
    }
    return {
        "schema_version": "native_arms_analysis_v1",
        "protocol_id": protocol["protocol_id"],
        "bootstrap": {
            "seed": BOOTSTRAP_SEED,
            "resamples": BOOTSTRAP_RESAMPLES,
            "confidence": 0.95,
            "interval": "percentile",
            "materiality": "interval excludes 0",
        },
        "cells": cells,
        "contrasts": contrasts,
        "summary": summary,
    }


# --------------------------------------------------------------------------- #
# reviewer blockers (#130): R1 menu stress, R2 text-corruption, R4 strains
# --------------------------------------------------------------------------- #


def stress_paths(protocol: dict, binding: dict) -> tuple[Path, Path, Path]:
    evaluation = output_root(protocol) / "evaluation"
    task_name = binding["task_id"].replace("/", "__")
    name = f"{binding['algorithm']}-{binding['family']}-{binding['condition']}"
    group = binding["phase"]
    episode = evaluation / "episodes" / group / binding["arm"] / task_name / f"{name}.json.gz"
    view_output = evaluation / "views" / group / binding["arm"] / task_name / name
    partial = episode.with_name(episode.name + ".partial.json.gz")
    return episode, partial, view_output


def menu_bindings(protocol: dict, tasks: list[dict]) -> list[dict]:
    from examples.planning_benchmark_slice.native_arm_stress import MENU_FAMILIES

    rows = []
    index = 0
    for task in tasks:
        for family in MENU_FAMILIES:
            for arm in ARMS:
                for algorithm in protocol["learned_algorithms"]:
                    rows.append(
                        {
                            "index": index,
                            "worker": (index // 2) % 2,
                            "kind": "models",
                            "phase": "menu",
                            "arm": arm,
                            "family": family,
                            "task_id": task["row"]["task_id"],
                            "algorithm": algorithm,
                            "condition": "learned_adapter",
                            "seed": int(protocol["training_seed"]),
                        }
                    )
                    index += 1
    return rows


def load_suite_tasks(protocol: dict, families: list[str]) -> list[dict]:
    admission = read_json(ROOT / protocol["r4"]["admission"])
    suite = read_json(ROOT / protocol["r4"]["suite"])
    by_id = {task["variant_id"]: task for task in suite["tasks"]}
    tasks = []
    for family in families:
        for variant_id in admission["membership"][family]:
            task = dict(by_id[variant_id])
            task["family"] = family
            tasks.append(task)
    return tasks


def r4_bindings(protocol: dict, tasks: list[dict]) -> list[dict]:
    rows = []
    index = 0
    for task in tasks:
        for arm in ARMS:
            for algorithm in protocol["learned_algorithms"]:
                for condition in ("learned_adapter", "pretrained_base"):
                    rows.append(
                        {
                            "index": index,
                            "worker": (index // 2) % 2,
                            "kind": "models",
                            "phase": "variants",
                            "arm": arm,
                            "family": task["family"],
                            "task_id": task["row"]["task_id"],
                            "algorithm": algorithm,
                            "condition": condition,
                            "seed": int(protocol["training_seed"]),
                        }
                    )
                    index += 1
    return rows


def stress_worker(worker: int, group: str, endpoint: str) -> dict:
    """Shared GPU worker for the menu (R1), text-mask cross (R2) and strain (R4) cells."""

    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError("native-arm stress worker requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("native-arm stress worker requires an explicit scheduler MASTER_PORT")
    protocol = load_protocol()
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    if group == "menu":
        tasks = load_tasks(protocol)
        rows = [row for row in menu_bindings(protocol, tasks) if row["worker"] == worker]
        task_by_id = {task["row"]["task_id"]: task for task in tasks}
    elif group == "textmask":
        tasks = load_tasks(protocol)
        rows = []
        index = 0
        for task in tasks:
            for algorithm in protocol["learned_algorithms"]:
                rows.append(
                    {
                        "index": index,
                        "worker": (index // 2) % 2,
                        "kind": "models",
                        "phase": "textmask",
                        "arm": "visual-state",
                        "family": "text-masked",
                        "task_id": task["row"]["task_id"],
                        "algorithm": algorithm,
                        "condition": "learned_adapter",
                        "seed": int(protocol["training_seed"]),
                    }
                )
                index += 1
        rows = [row for row in rows if row["worker"] == worker]
        task_by_id = {task["row"]["task_id"]: task for task in tasks}
    else:
        tasks = load_suite_tasks(protocol, list(protocol["r4"]["families"]))
        rows = [row for row in r4_bindings(protocol, tasks) if row["worker"] == worker]
        task_by_id = {task["row"]["task_id"]: task for task in tasks}
    adapters = {}
    from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
    from examples.planning_benchmark_slice.visual_model import VisualPolicy

    if group == "textmask":
        stress_protocol = read_json(ROOT / protocol["r2"]["stress_protocol"])
        adapters = {
            row["algorithm"]: row["checkpoint"]
            for row in stress_protocol["fixed_adapters"]
            if row["modality"] == "visual-state"
        }
    else:
        for arm in ARMS:
            for algorithm in protocol["learned_algorithms"]:
                adapters[f"{arm}|{algorithm}"] = str(
                    output_root(protocol) / "training" / arm / algorithm / "final"
                )
    for path in adapters.values():
        if not (ROOT / path / "adapter_model.safetensors").is_file():
            raise ValueError(f"adapter checkpoint missing: {path}")
    from transformers import set_seed

    set_seed(int(protocol["training_seed"]))
    policy = VisualPolicy(
        model_id=protocol["model_id"],
        revision=protocol["model_revision"],
        adapter_paths={key: ROOT / value for key, value in adapters.items()},
        device="cuda:0",
        max_context_tokens=32768,
        max_new_tokens=384,
        max_batch_size=protocol["inference"]["max_batch_size"],
        max_batch_input_tokens=protocol["inference"]["max_padded_batch_input_tokens"],
        inference_dtype=protocol["inference"]["dtype"],
    )
    configure_visual_attention(policy.model, protocol["inference"]["attention"])
    policy.identity.update(memoize_identical_inputs=False)
    completed = 0
    retained = 0
    model_calls = 0
    reports = []
    started = time.monotonic()
    for binding in rows:
        task = task_by_id[binding["task_id"]]
        adapter_key = (
            binding["algorithm"]
            if group == "textmask"
            else f"{binding['arm']}|{binding['algorithm']}"
        )
        checkpoint = adapters[adapter_key] if binding["condition"] == "learned_adapter" else None
        episode, partial, view_output = stress_paths(protocol, binding)
        views = None
        if group == "menu":
            from examples.planning_benchmark_slice.native_arm_stress import MenuStressTaskViews

            views = MenuStressTaskViews(
                ROOT, task, view_output, endpoint, arm=binding["arm"], menu_family=binding["family"]
            )
        elif group == "textmask":
            from examples.planning_benchmark_slice.expanded_modality_stress import StressTaskViews

            views = StressTaskViews(
                ROOT,
                task,
                view_output,
                endpoint,
                corruption="text-masked",
                master_seed=int(protocol["corruption"]["master_seed"]),
            )
        else:
            from examples.planning_benchmark_slice.native_arm_views import NativeArmTaskViews

            views = NativeArmTaskViews(ROOT, task, view_output, endpoint, arm=binding["arm"])

        def generate(example, adapter_key=adapter_key, binding=binding, policy=policy):
            nonlocal model_calls
            adapter = adapter_key if binding["condition"] == "learned_adapter" else None
            output = policy.generate([example], adapter)[0]
            model_calls += 1
            return output, policy.last_generation_usage["generated_sequence_tokens"]

        report, was_retained = run_binding(
            ROOT,
            protocol,
            task,
            binding,
            checkpoint,
            endpoint,
            generate,
            paths=(episode, partial, view_output),
            views=views,
        )
        retained += int(was_retained)
        reports.append(report["output"])
        completed += 1
        write(
            progress_path,
            {"completed": completed, "total": len(rows), "retained": retained, "group": group},
        )
        print(
            {
                "stage": "native_arms_stress",
                "group": group,
                "worker": worker,
                "completed": completed,
                "total": len(rows),
                "result": report["result"]["termination_reason"],
            },
            flush=True,
        )
    del policy
    gc.collect()
    import torch

    torch.cuda.empty_cache()
    result = {
        "schema_version": "native_arms_stress_worker_v1",
        "outcome": "PASS",
        "group": group,
        "worker": worker,
        "episodes": reports,
        "completed": completed,
        "retained": retained,
        "model_calls": model_calls,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": os.environ.get("MASTER_PORT"),
        "elapsed_seconds": time.monotonic() - started,
    }
    write(attempt_dir / "worker-result.json", result)
    write(progress_path, {"completed": completed, "total": len(rows), "terminal": True})
    return result


def r2_decompose_stage() -> dict:
    """CPU termination-mode decomposition of the published #126 corrupted episodes."""

    stress_root = ROOT / "outputs/expanded-study/v1/modality-stress/episodes"
    summary: dict[str, dict] = {}
    total = 0
    for episode in sorted(stress_root.rglob("*-learned_adapter.json.gz")):
        report = read_json(episode)
        if report.get("family") not in ("text-shuffled", "text-masked"):
            continue
        total += 1
        result = report["result"]
        decisions = max(1, result["decision_count"])
        invalid = result["invalid_operation_count"]
        mode = (
            "all_invalid"
            if invalid == decisions
            else ("goal_reached" if result.get("invariant_valid_success") else "partial_valid")
        )
        key = f"{report['family']}|{report['modality']}"
        cell = summary.setdefault(
            key,
            {"episodes": 0, "all_invalid": 0, "partial_valid": 0, "goal_reached": 0, "decisions": 0, "invalid": 0},
        )
        cell["episodes"] += 1
        cell[mode] += 1
        cell["decisions"] += decisions
        cell["invalid"] += invalid
    protocol = load_protocol()
    report = {
        "schema_version": "native_arms_r2_decomposition_v1",
        "protocol_id": protocol["protocol_id"],
        "episodes_decomposed": total,
        "cells": summary,
        "note": (
            "all_invalid = every emitted operation was schema-invalid (output-contract destruction); "
            "partial_valid = the policy emitted valid operations but the search failed — the "
            "information-loss signature the #126 claim needs"
        ),
    }
    write(output_root(protocol) / "r2-decomposition.json", report)
    return report


def stress_audit_stage() -> dict:
    protocol = load_protocol()
    path = output_root(protocol) / "stress-evaluation.json"
    ok = False
    detail = "missing stress-evaluation.json"
    if path.is_file():
        analysis = read_json(path)
        expected = 170
        ok = not analysis["missing"] and analysis["episodes_replayed"] == expected
        detail = f"replayed {analysis['episodes_replayed']}/{expected}, missing {len(analysis['missing'])}"
    summary = {"schema_version": "native_arms_stress_audit_v1", "ok": ok, "detail": detail}
    write(output_root(protocol) / "stress-audit.json", summary)
    return summary




def identity_audit_stage() -> dict:
    """Cheap hygiene check: random_valid vs exact_reference enumeration identity.

    Under the additive Search-Process contract every decision submits one
    remaining candidate and finish_expansion() requires the complete set, so
    decision and expansion counts are contract-determined and the search
    outcome is invariant to the policy's submission order. This audit makes
    that property measurable on any episode store: where random_valid is
    decision- and expansion-identical to exact_reference, the evaluation
    measures operation validity, not choice quality.
    """
    import gzip

    protocol = load_protocol()
    root = ROOT / protocol["comparators"]["baseline_episodes_root"]
    pairs: dict[tuple[str, str], dict[str, tuple[int, int]]] = {}
    for modality in ("text-state", "visual-state", "multimodal-state"):
        for algdir in sorted(p for p in root.glob(f"{modality}/*") if p.is_dir()):
            for f in algdir.glob("*.json.gz"):
                algorithm, _, condition = f.name.removesuffix(".json.gz").rpartition("-")
                if not algorithm.startswith("best_first_add"):
                    continue
                report = json.loads(gzip.open(f, "rt").read())
                entry = pairs.setdefault((algdir.name, algorithm), {})
                entry[condition] = (
                    report["result"]["decision_count"],
                    report["result"]["expansion_count"],
                )
    checked = identical = 0
    mismatches = []
    for _key, entry in sorted(pairs.items()):
        if "random_valid" not in entry or "exact_reference" not in entry:
            continue
        checked += 1
        if entry["random_valid"] == entry["exact_reference"]:
            identical += 1
        else:
            mismatches.append({str(k): v for k, v in entry.items()})
    audit = {
        "schema_version": "native_arms_identity_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "store": protocol["comparators"]["baseline_episodes_root"],
        "pairs_checked": checked,
        "pairs_identical": identical,
        "mismatches": mismatches,
        "verdict": (
            "ZERO_DECISION_HEADROOM: random_valid is decision- and expansion-identical to "
            "exact_reference on every additive pair; the contract measures operation "
            "validity (enumeration), not choice quality"
            if checked and identical == checked
            else "PARTIAL_HEADROOM"
        ),
        "structural_basis": (
            "each decision submits one remaining candidate; finish_expansion() requires the "
            "complete candidate set; heap serials are assigned from the deterministic sorted "
            "candidate order at start_expansion, so frontier evolution is submission-order "
            "invariant"
        ),
    }
    write(output_root(protocol) / "identity-audit.json", audit)
    return audit
def stress_finalize_stage(endpoint: str) -> dict:
    """Independent replay of every R1/R2/R4 episode + the frozen paired analysis."""

    protocol = load_protocol()
    panel_tasks = {task["row"]["task_id"]: task for task in load_tasks(protocol)}
    suite_tasks = {
        task["row"]["task_id"]: task for task in load_suite_tasks(protocol, list(protocol["r4"]["families"]))
    }
    textmask_rows = []
    index = 0
    for task in load_tasks(protocol):
        for algorithm in protocol["learned_algorithms"]:
            textmask_rows.append(
                {
                    "index": index,
                    "worker": (index // 2) % 2,
                    "kind": "models",
                    "phase": "textmask",
                    "arm": "visual-state",
                    "family": "text-masked",
                    "task_id": task["row"]["task_id"],
                    "algorithm": algorithm,
                    "condition": "learned_adapter",
                    "seed": int(protocol["training_seed"]),
                }
            )
            index += 1
    all_rows = (
        menu_bindings(protocol, load_tasks(protocol))
        + r4_bindings(protocol, load_suite_tasks(protocol, list(protocol["r4"]["families"])))
        + textmask_rows
    )
    reports = []
    missing = []
    for binding in all_rows:
        episode, _, _ = stress_paths(protocol, binding)
        if not episode.exists():
            missing.append(binding["index"])
            continue
        report = read_json(episode)
        task = panel_tasks.get(binding["task_id"]) or suite_tasks[binding["task_id"]]
        independently_replay(ROOT, protocol, task, report, endpoint)
        reports.append(report)

    def cell_key(report):
        return (report["phase"], report.get("family"), report.get("arm"), report["algorithm"])

    cells: dict[str, dict] = {}
    for report in reports:
        key = "|".join(str(part) for part in cell_key(report))
        cell = cells.setdefault(key, {"episodes": 0, "successes": 0, "invalid": 0, "decisions": 0})
        cell["episodes"] += 1
        cell["successes"] += _success(report)
        cell["invalid"] += report["result"]["invalid_operation_count"]
        cell["decisions"] += report["result"]["decision_count"]
    distractor_picks = 0
    distractor_decisions = 0
    for report in reports:
        if report.get("phase") != "menu" or report.get("family") != "distractor-injection":
            continue
        for event in report["events"]:
            # injected sets live per-event in the view bindings
            binding = event.get("view") or {}
            injected_set = {tuple(entry) for entry in binding.get("injected_distractors", [])}
            if not injected_set:
                continue
            try:
                action = json.loads(event["raw_output"])["action"]
                entry = (action["name"], *action["args"])
            except Exception:
                entry = None
            distractor_decisions += 1
            if entry is not None and entry in injected_set:
                distractor_picks += 1
    analysis = {
        "schema_version": "native_arms_stress_analysis_v1",
        "protocol_id": protocol["protocol_id"],
        "episodes_replayed": len(reports),
        "missing": missing,
        "cells": cells,
        "distractor": {
            "decisions_with_injection": distractor_decisions,
            "distractor_picks": distractor_picks,
            "pick_rate": distractor_picks / max(1, distractor_decisions),
        },
    }
    write(output_root(protocol) / "stress-evaluation.json", analysis)
    return analysis


def audit_final_stage() -> dict:
    protocol = load_protocol()
    evaluation = read_json(output_root(protocol) / "evaluation" / "evaluation.json")
    gated = len(evaluation.get("gated_out_by_smoke", []))
    ok = (
        evaluation["outcome"] == "PASS"
        and evaluation["episodes_replayed"] + gated == evaluation["bindings_total"]
        and evaluation["comparator_episodes_replayed"] == 72
        and not evaluation["missing_bindings"]
    )
    return {"schema_version": "native_arms_final_audit_v1", "ok": ok, "evaluation": evaluation}


# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "stage",
        choices=[
            "validate",
            "prepare",
            "probe",
            "audit-probe",
            "admit",
            "admit-v2",
            "smoke",
            "audit-smoke",
            "train",
            "audit-train",
            "evaluate-inputs",
            "evaluate-worker",
            "audit-evaluate-worker",
            "finalize",
            "audit-final",
            "stress-worker",
            "r2-decompose",
            "stress-finalize",
            "stress-audit",
            "identity-audit",
        ],
    )
    parser.add_argument("--arm", choices=list(ARMS))
    parser.add_argument("--worker", type=int)
    parser.add_argument("--kind", choices=["models", "controls"])
    parser.add_argument("--group", choices=["menu", "textmask", "variants"])
    parser.add_argument("--endpoint", default="http://127.0.0.1:18092")
    args = parser.parse_args(argv)
    if args.stage == "validate":
        result = validate_stage()
    elif args.stage == "prepare":
        result = prepare_stage(args.arm)
    elif args.stage == "probe":
        result = probe_stage(args.arm, args.endpoint)
    elif args.stage == "audit-probe":
        result = audit_probe_stage(args.arm)
    elif args.stage == "admit":
        result = admission_stage()
    elif args.stage == "admit-v2":
        result = admission_v2_stage()
    elif args.stage == "smoke":
        result = smoke_stage(args.arm, args.endpoint)
    elif args.stage == "audit-smoke":
        result = audit_smoke_stage(args.arm)
    elif args.stage == "train":
        result = train_stage(args.arm)
    elif args.stage == "audit-train":
        result = audit_train_stage(args.arm)
    elif args.stage == "evaluate-inputs":
        result = evaluate_inputs_stage()
    elif args.stage == "evaluate-worker":
        result = evaluate_worker(args.worker, args.kind, args.endpoint)
    elif args.stage == "audit-evaluate-worker":
        result = audit_evaluate_worker(args.worker, args.kind)
    elif args.stage == "finalize":
        result = finalize_stage(args.endpoint)
    elif args.stage == "stress-worker":
        result = stress_worker(args.worker, args.group, args.endpoint)
    elif args.stage == "r2-decompose":
        result = r2_decompose_stage()
    elif args.stage == "stress-finalize":
        result = stress_finalize_stage(args.endpoint)
    elif args.stage == "stress-audit":
        result = stress_audit_stage()
    elif args.stage == "identity-audit":
        result = identity_audit_stage()
    else:
        result = audit_final_stage()
    print(json.dumps(result, indent=1, default=str))
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
