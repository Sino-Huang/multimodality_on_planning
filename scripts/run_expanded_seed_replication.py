#!/usr/bin/env python
"""Run the frozen prospective training-seed replication (#127).

Protocol `expanded-seed-replication-v1`
(configs/experiments/expanded-study/seed-replication-protocol.json): retrain
the frozen headline cells with the two additional prospective training seeds
29 and 71, evaluate every seed under the original cells' frozen evaluation
contracts, independently replay every new episode, and publish the
seed-variance addendum. GPU stages run inside the shared scheduler
environment; audit stages are CPU-only.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.planning_benchmark_slice.expanded_baseline import (
    binding_paths,
    independently_replay,
    run_binding,
)
from examples.planning_benchmark_slice.expanded_dagger import validate_protocol
from examples.planning_benchmark_slice.expanded_dagger_evaluation import (
    COMPARATORS,
    panels,
    run_cell,
    verify_comparator,
    verify_episode,
)
from examples.planning_benchmark_slice.expanded_dagger_training import (
    DaggerTrainingDataset,
    _git_head,
)
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write
from examples.planning_benchmark_slice.modality_view_preparation import write_json
from examples.planning_benchmark_slice.scene_assets import read_json

PROTOCOL_PATH = ROOT / "configs/experiments/expanded-study/seed-replication-protocol.json"
DAGGER_PROTOCOL_PATH = ROOT / "configs/experiments/expanded-study/dagger-protocol.json"
BASELINE_PROTOCOL_PATH = ROOT / "configs/experiments/expanded-study/baseline-protocol.json"
BASELINE_STUDY_PATH = ROOT / "configs/experiments/matched-modalities/study-v5.json"
MEMBERSHIP_PATH = ROOT / "configs/experiments/matched-modalities/membership.json"
LEDGER_PATH = ROOT / "outputs/expanded-study/v1/budget.json"
ORIGINAL_DAGGER_ROOT = "outputs/expanded-study/v1/dagger"
ORIGINAL_BASELINE_EPISODES = ROOT / "outputs/expanded-study/v1/baseline/episodes"
ADDENDUM_DIR = ROOT / "docs/experiments/expanded-study/synthesis-v1"

OUT = ROOT / "outputs/expanded-study/v1/seed-replication"
SEEDS_NEW = (29, 71)
SEEDS_ALL = (17, 29, 71)
A_MODALITY = "multimodal-state"
A_ALGORITHM = "best_first_add_greedy"
A_TRAIN_SEED = {0: 29, 1: 71}
B_MODALITIES = ("text-state", "visual-state", "multimodal-state")
B_WORKER_MODALITIES = {0: ("text-state", "multimodal-state"), 1: ("visual-state",)}
B_ARMS = ("dagger", "continued_sft")
B_ARMSEEDS = tuple(f"{arm}_iteration_1_seed{seed}" for seed in SEEDS_ALL for arm in B_ARMS)
ENDPOINTS = {0: "http://127.0.0.1:18092", 1: "http://127.0.0.1:18093"}
MASTER_PORT_POOL = (18800, 18801, 18802, 18803, 18804, 18805)
BOOTSTRAP_SEED = 1729
BOOTSTRAP_RESAMPLES = 10000


def protocol():
    return read_json(PROTOCOL_PATH)


def dagger_protocol():
    return read_json(DAGGER_PROTOCOL_PATH)


def require_worker_environment(worker: int) -> int:
    if os.environ.get("CUDA_VISIBLE_DEVICES") != str(worker):
        raise ValueError("seed-replication worker GPU differs from the frozen mapping")
    port = int(os.environ["MASTER_PORT"])
    if port not in MASTER_PORT_POOL:
        raise ValueError("seed-replication worker MASTER_PORT is outside the frozen pool")
    return port


def progress_write(completed: int, total: int, **fields) -> None:
    path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    started = progress_write.started
    elapsed = time.monotonic() - started
    write(
        path,
        {
            "completed": completed,
            "total": total,
            "eta_seconds": elapsed * (total - completed) / completed if completed else None,
            **fields,
        },
    )


progress_write.started = time.monotonic()


# ---------------------------------------------------------------------------
# Frozen contract validation (prepare)
# ---------------------------------------------------------------------------


def a_cell_output(seed: int) -> Path:
    return OUT / "baseline" / f"seed-{seed}" / "training" / A_MODALITY / A_ALGORITHM


def b_cell_dir(seed: int, modality: str, arm: str) -> Path:
    return OUT / "dagger" / f"seed-{seed}" / "training" / modality / arm.replace("_", "-") / "iteration-1"


def b_verified_membership(modality: str, arm: str) -> tuple[str, dict]:
    key = "dagger_memberships" if arm == "dagger" else "continued_sft_memberships"
    relative = protocol()["cells"]["dagger_iteration_1"]["training"][key][modality]
    membership = read_json(ROOT / relative)
    original_report = read_json(
        ROOT / ORIGINAL_DAGGER_ROOT / "training" / modality / arm.replace("_", "-") / "iteration-1" / "report.json"
    )
    ids = [row["record_id"] for row in membership["records"]]
    if (
        ids != original_report["training_record_ids"]
        or len(ids) != 512
        or membership.get("modality") != modality
        or membership.get("arm") != arm
        or membership.get("through_iteration") != 1
        or any(row.get("split") != "train" for row in membership["records"])
    ):
        raise ValueError("verified seed-17 membership differs from the original cell")
    return relative, membership


def b_eval_protocol() -> dict:
    base = dagger_protocol()
    lineage = {}
    for arm in B_ARMS:
        for seed in SEEDS_ALL:
            key = f"{arm}_iteration_1_seed{seed}"
            if seed == 17:
                lineage[key] = f"{ORIGINAL_DAGGER_ROOT}/training/{{modality}}/{arm.replace('_', '-')}/iteration-1/final"
            else:
                lineage[key] = (
                    f"outputs/expanded-study/v1/seed-replication/dagger/seed-{seed}"
                    f"/training/{{modality}}/{arm.replace('_', '-')}/iteration-1/final"
                )
    evaluation = dict(base["evaluation"])
    evaluation["new_arms"] = list(B_ARMSEEDS)
    return {
        **base,
        "protocol_id": "expanded-seed-replication-v1",
        "output_root": "outputs/expanded-study/v1/seed-replication/dagger",
        "checkpoint_lineage": lineage,
        "evaluation": evaluation,
    }


def a_eval_protocol(seed: int) -> dict:
    base = read_json(BASELINE_PROTOCOL_PATH)
    return {
        **base,
        "protocol_id": "expanded-seed-replication-v1",
        "output_root": f"outputs/expanded-study/v1/seed-replication/baseline/seed-{seed}",
        "algorithms": [A_ALGORITHM],
        "modalities": [A_MODALITY],
        "conditions": ["process_sft"],
        "execution_groups": {"models": ["process_sft"]},
        "logical_bindings": 24,
        "model_episodes": 24,
        "root": str(ROOT),
    }


def a_panel_tasks() -> tuple[dict, list[dict]]:
    panel = read_json(ROOT / "configs/experiments/expanded-study/final-panel.json")
    view_tasks = read_json(ROOT / panel["view_report"])["tasks"]
    if (
        panel["panel_id"] != "expanded-panel-v2-qualified"
        or len(panel["tasks"]) != 24
        or {task["row"]["task_id"] for task in view_tasks} != {task["row"]["task_id"] for task in panel["tasks"]}
    ):
        raise ValueError("seed-replication panel differs from the frozen contract")
    return panel, view_tasks


def a_bindings(panel: dict) -> list[dict]:
    result = []
    for task_index, task in enumerate(panel["tasks"]):
        result.append(
            {
                "index": task_index,
                "worker": task_index % 2,
                "task_index": task_index,
                "task_id": task["row"]["task_id"],
                "modality": A_MODALITY,
                "algorithm": A_ALGORITHM,
                "condition": "process_sft",
            }
        )
    return result


def prepare() -> int:
    proto = protocol()
    if proto["protocol_id"] != "expanded-seed-replication-v1" or proto["training_seeds"]["additional_prospective"] != [
        29,
        71,
    ]:
        raise ValueError("seed-replication protocol identity or frozen seeds differ")
    study = read_json(BASELINE_STUDY_PATH)
    membership = read_json(MEMBERSHIP_PATH)
    greedy_ids = membership["training_record_ids"][A_ALGORITHM]
    v5_report = read_json(ROOT / "outputs/matched_modalities/v5/training" / A_MODALITY / A_ALGORITHM / "report.json")
    if len(greedy_ids) != 512 or v5_report["training_record_ids"] != greedy_ids:
        raise ValueError("cell-A training membership differs from the verified v5 cell")
    if study["training_seed"] != 17 or study["training"]["records_per_algorithm"] != 512:
        raise ValueError("cell-A source study differs from the frozen contract")
    validate_protocol(ROOT, dagger_protocol())
    for modality in B_MODALITIES:
        for arm in B_ARMS:
            b_verified_membership(modality, arm)
    eval_protocol = b_eval_protocol()
    loaded = panels(ROOT, eval_protocol)
    if sum(len(tasks) for tasks in loaded.values()) != 27:
        raise ValueError("cell-B evaluation panels differ from the frozen contract")
    for modality in B_MODALITIES:
        for arm in B_ARMS:
            checkpoint = (
                ROOT / ORIGINAL_DAGGER_ROOT / "training" / modality / arm.replace("_", "-") / "iteration-1" / "final"
            )
            if not (checkpoint / "adapter_model.safetensors").is_file():
                raise ValueError(f"missing verified seed-17 checkpoint: {checkpoint}")
    panel, _ = a_panel_tasks()
    if len(a_bindings(panel)) != 24:
        raise ValueError("cell-A binding enumeration differs from the frozen contract")
    for seed in SEEDS_ALL:
        if seed == 17:
            continue
        if a_cell_output(seed).exists() or any(
            b_cell_dir(seed, modality, arm).exists() for modality in B_MODALITIES for arm in B_ARMS
        ):
            raise ValueError("seed-replication outputs already exist for a prospective seed")
    ledger = read(LEDGER_PATH)
    spent = {"expanded_baseline": 0.0, "dagger": 0.0}
    for attempt in ledger["attempts"]:
        if attempt["branch"] in spent:
            spent[attempt["branch"]] += attempt["gpu_hours"]
    remainders = {branch: ledger["allocations_gpu_hours"][branch] - spent[branch] for branch in spent}
    report = {
        "schema_version": "expanded_seed_replication_preparation_v1",
        "outcome": "PASS",
        "protocol_id": proto["protocol_id"],
        "seeds": {"original": 17, "additional_prospective": [29, 71]},
        "cells": {
            "baseline_process_sft": {"algorithm": A_ALGORITHM, "modality": A_MODALITY, "new_training_runs": 2},
            "dagger_iteration_1": {
                "algorithm": "bfs",
                "modalities": list(B_MODALITIES),
                "arms": list(B_ARMS),
                "new_training_runs": 12,
            },
        },
        "branch_remainders_gpu_hours": remainders,
        "head": _git_head(ROOT),
    }
    (OUT).mkdir(parents=True, exist_ok=True)
    write(OUT / "preparation.json", report)
    print(json.dumps(report, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Cell A training (fresh adapter per seed)
# ---------------------------------------------------------------------------


def a_study(seed: int) -> dict:
    study = read_json(BASELINE_STUDY_PATH)
    return {
        **study,
        "study_id": "matched-modalities-v5-seed-replication",
        "status": "frozen_seed_replication_execution",
        "output_root": f"outputs/expanded-study/v1/seed-replication/baseline/seed-{seed}",
        "training_seed": seed,
    }


def train_baseline(worker: int) -> int:
    require_worker_environment(worker)
    seed = A_TRAIN_SEED[worker]
    from examples.planning_benchmark_slice.matched_workers import train_worker

    study = a_study(seed)
    status_path = a_cell_output(seed) / "status.json"
    if status_path.is_file():
        print(json.dumps(read_json(status_path), indent=2))
        return 0
    deadline = time.monotonic() + 5700

    def progress(stage: str, **fields):
        if stage == "training":
            progress_write(fields.get("completed", 0), 16, stage=stage, seed=seed)
        else:
            fields.pop("completed", None)
            fields.pop("total", None)
            progress_write(0, 16, stage=stage, seed=seed, **fields)

    result = train_worker(
        ROOT,
        study,
        {"modality": A_MODALITY, "algorithm": A_ALGORITHM},
        deadline,
        progress,
        True,
    )
    write_json(status_path, {**result, "training_seed": seed, "worker": worker})
    progress_write(16, 16, terminal=True, seed=seed)
    return 0


def audit_training_baseline(worker: int) -> int:
    seed = A_TRAIN_SEED[worker]
    from safetensors import safe_open

    membership = read_json(MEMBERSHIP_PATH)
    output = a_cell_output(seed)
    status = read_json(output / "status.json")
    expected_ids = membership["training_record_ids"][A_ALGORITHM]
    checks = {
        "algorithm": A_ALGORITHM,
        "seed": seed,
        "steps": 16,
        "train_records": 512,
        "outcome": "PASS",
        "modality": A_MODALITY,
        "adapter_isolation_passed": True,
        "training_seed": seed,
        "worker": worker,
    }
    if any(status.get(key) != value for key, value in checks.items()):
        raise ValueError("cell-A training report differs from the frozen cell")
    if status["training_record_ids"] != expected_ids:
        raise ValueError("cell-A training record membership differs from the frozen 512 records")
    state = read_json(output / "training_state.json")
    if state.get("global_step") != 16:
        raise ValueError("cell-A trainer state does not contain exactly 16 updates")
    final = output / "final"
    if not (final / "adapter_model.safetensors").is_file() or not (final / "adapter_config.json").is_file():
        raise ValueError("cell-A final adapter checkpoint is incomplete")
    config = read_json(final / "adapter_config.json")
    if config.get("r") != 64 or config.get("lora_alpha") != 128 or config.get("lora_dropout") != 0.05:
        raise ValueError("cell-A adapter config differs from the frozen LoRA settings")
    source_final = ROOT / "outputs/matched_modalities/v5/training" / A_MODALITY / A_ALGORITHM / "final"
    import torch

    with (
        safe_open(source_final / "adapter_model.safetensors", framework="pt", device="cpu") as reference,
        safe_open(final / "adapter_model.safetensors", framework="pt", device="cpu") as replicated,
    ):
        if set(reference.keys()) != set(replicated.keys()):
            raise ValueError("cell-A adapter parameter membership differs from the seed-17 cell")
        keys = list(reference.keys())
        changed = 0
        for key in keys:
            tensor = replicated.get_tensor(key)
            if not torch.isfinite(tensor).all():
                raise ValueError("cell-A adapter contains non-finite parameters")
            changed += int(not reference.get_tensor(key).equal(tensor))
    if changed != len(keys):
        raise ValueError("cell-A seed replication must change every adapter tensor from the seed-17 init")
    result = {
        "outcome": "PASS",
        "cell": f"{A_ALGORITHM}/{A_MODALITY}",
        "training_seed": seed,
        "optimizer_updates": 16,
        "records": 512,
        "parameter_tensors": len(keys),
        "changed_parameter_tensors_vs_seed17": changed,
        "final_checkpoint": str(final.relative_to(ROOT)),
    }
    write(Path(os.environ["EXPANDED_TERMINAL_PATH"]).parent / "audit-result.json", result)
    print(json.dumps(result, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Cell set B training (continuation from verified seed-17 starting adapters)
# ---------------------------------------------------------------------------


def train_dagger(seed: int, worker: int) -> int:
    require_worker_environment(worker)
    if seed not in SEEDS_NEW:
        raise ValueError("cell-B trains only the prospective seeds; seed 17 checkpoints are verified already")
    context = validate_protocol(ROOT, dagger_protocol())
    modalities = B_WORKER_MODALITIES[worker]
    cells = [(modality, arm) for modality in modalities for arm in B_ARMS]
    completed = 0
    reports = []
    for modality, arm in cells:
        report = train_dagger_cell(context, seed, modality, arm, worker, completed, len(cells) * 16)
        reports.append(report)
        completed += 16
    progress_write(len(cells) * 16, len(cells) * 16, terminal=True, seed=seed)
    result = {
        "outcome": "PASS",
        "training_seed": seed,
        "worker": worker,
        "cells": [
            {"modality": report["modality"], "arm": report["arm"], "final_checkpoint": report["final_checkpoint"]}
            for report in reports
        ],
    }
    attempt_dir = os.environ.get("EXPANDED_ATTEMPT_DIR")
    if attempt_dir:
        write(Path(attempt_dir) / "worker-result.json", result)
    return 0


def train_dagger_cell(context, seed, modality, arm, worker, completed_base, completed_total):
    from torch.utils.data import SequentialSampler
    from transformers import Trainer, TrainerCallback, TrainingArguments

    from examples.planning_benchmark_slice.modality_view_preparation import frozen_processor
    from examples.planning_benchmark_slice.visual_model import VisualCollator, load_training_model

    output = b_cell_dir(seed, modality, arm)
    report_path = output / "report.json"
    if report_path.is_file():
        return read_json(report_path)
    membership_relative, membership = b_verified_membership(modality, arm)
    dataset = DaggerTrainingDataset(ROOT, dagger_protocol(), context, membership, endpoint=ENDPOINTS[worker])
    training = dagger_protocol()["training"]
    total = math.ceil(len(dataset) / training["global_batch_size"]) * training["epochs"]
    if total != training["optimizer_updates"]:
        raise ValueError("cell-B training membership does not yield exactly 16 updates")
    source = ROOT / dagger_protocol()["starting_checkpoints"][modality]
    source_tensor = source / "adapter_model.safetensors"
    source_before = {"size": source_tensor.stat().st_size, "mtime_ns": source_tensor.stat().st_mtime_ns}
    started = time.monotonic()

    class FrozenTrainer(Trainer):
        def _get_train_sampler(self, train_dataset=None):
            return SequentialSampler(dataset)

    class Progress(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            progress_write(
                completed_base + state.global_step,
                completed_total,
                seed=seed,
                modality=modality,
                arm=arm,
            )
            return control

    output.mkdir(parents=True, exist_ok=True)
    checkpoints = sorted(output.glob("checkpoint-*"), key=lambda item: int(item.name.split("-")[-1]))
    model = load_training_model(context["study"], str(source))
    arguments = TrainingArguments(
        output_dir=str(output),
        num_train_epochs=training["epochs"],
        per_device_train_batch_size=training["microbatch_size"],
        gradient_accumulation_steps=training["gradient_accumulation_steps"],
        learning_rate=training["learning_rate"],
        weight_decay=training["weight_decay"],
        warmup_ratio=training["warmup_ratio"],
        lr_scheduler_type=training["lr_scheduler"],
        optim=training["optimizer"],
        max_grad_norm=training["max_grad_norm"],
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        seed=seed,
        data_seed=seed,
        logging_steps=1,
        save_steps=max(1, total // 2),
        save_total_limit=2,
        report_to=[],
        remove_unused_columns=False,
        dataloader_num_workers=0,
    )
    trainer = FrozenTrainer(
        model=model,
        args=arguments,
        train_dataset=dataset,
        data_collator=VisualCollator(frozen_processor().processor),
        callbacks=[Progress()],
    )
    trainer.train(resume_from_checkpoint=str(checkpoints[-1]) if checkpoints else None)
    if trainer.state.global_step != total:
        raise RuntimeError("VALID_STOP: cell-B training ended before its final update")
    final = output / "final"
    trainer.save_model(str(final))
    trainer.state.save_to_json(str(output / "training_state.json"))
    source_after = {"size": source_tensor.stat().st_size, "mtime_ns": source_tensor.stat().st_mtime_ns}
    report = {
        "schema_version": "expanded_seed_replication_training_cell_v1",
        "outcome": "PASS",
        "protocol_id": "expanded-seed-replication-v1",
        "modality": modality,
        "arm": arm,
        "iteration": 1,
        "training_seed": seed,
        "data_membership_seed": 17,
        "source_checkpoint": str(source.relative_to(ROOT)),
        "source_checkpoint_unchanged": source_before == source_after,
        "membership": membership_relative,
        "training_record_ids": [row["record_id"] for row in membership["records"]],
        "records": len(dataset),
        "epochs": training["epochs"],
        "optimizer_updates": trainer.state.global_step,
        "seed": seed,
        "final_checkpoint": str(final.relative_to(ROOT)),
        "runtime_head": _git_head(ROOT),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": int(os.environ["MASTER_PORT"]),
        "elapsed_seconds": time.monotonic() - started,
        "loss_history": [row for row in trainer.state.log_history if "loss" in row],
    }
    write_json(report_path, report)
    del trainer, model
    gc.collect()
    import torch

    torch.cuda.empty_cache()
    return report


def audit_training_dagger(seed: int, worker: int) -> int:
    import torch
    from safetensors import safe_open

    results = []
    for modality in B_WORKER_MODALITIES[worker]:
        for arm in B_ARMS:
            output = b_cell_dir(seed, modality, arm)
            report = read_json(output / "report.json")
            membership_relative, membership = b_verified_membership(modality, arm)
            source = dagger_protocol()["starting_checkpoints"][modality]
            expected = {
                "schema_version": "expanded_seed_replication_training_cell_v1",
                "outcome": "PASS",
                "protocol_id": "expanded-seed-replication-v1",
                "modality": modality,
                "arm": arm,
                "iteration": 1,
                "training_seed": seed,
                "data_membership_seed": 17,
                "source_checkpoint": source,
                "source_checkpoint_unchanged": True,
                "membership": membership_relative,
                "training_record_ids": [row["record_id"] for row in membership["records"]],
                "records": 512,
                "epochs": 1,
                "optimizer_updates": 16,
                "seed": seed,
                "final_checkpoint": str(output.relative_to(ROOT) / "final"),
            }
            if any(report.get(key) != value for key, value in expected.items()):
                raise ValueError(f"cell-B training report differs from the frozen cell: {modality}/{arm}")
            state = read_json(output / "training_state.json")
            if state.get("global_step") != 16:
                raise ValueError("cell-B trainer state does not contain exactly 16 updates")
            final = ROOT / report["final_checkpoint"]
            source_tensor = ROOT / source / "adapter_model.safetensors"
            final_tensor = final / "adapter_model.safetensors"
            if not final_tensor.is_file() or not (final / "adapter_config.json").is_file():
                raise ValueError("cell-B final adapter checkpoint is incomplete")
            seed17_tensor = (
                ROOT
                / ORIGINAL_DAGGER_ROOT
                / "training"
                / modality
                / arm.replace("_", "-")
                / "iteration-1"
                / "final"
                / "adapter_model.safetensors"
            )
            with (
                safe_open(source_tensor, framework="pt", device="cpu") as before,
                safe_open(final_tensor, framework="pt", device="cpu") as after,
                safe_open(seed17_tensor, framework="pt", device="cpu") as original,
            ):
                if set(before.keys()) != set(after.keys()):
                    raise ValueError("cell-B adapter parameter membership changed")
                keys = list(before.keys())
                changed = 0
                differs_from_seed17 = 0
                for key in keys:
                    tensor = after.get_tensor(key)
                    if not torch.isfinite(tensor).all():
                        raise ValueError("cell-B adapter contains non-finite parameters")
                    changed += int(not before.get_tensor(key).equal(tensor))
                    differs_from_seed17 += int(not original.get_tensor(key).equal(tensor))
            if not changed:
                raise ValueError("cell-B adapter weights did not change")
            if not differs_from_seed17:
                raise ValueError("cell-B seed replication must not reproduce the seed-17 adapter")
            results.append(
                {
                    "modality": modality,
                    "arm": arm,
                    "changed_parameter_tensors": changed,
                    "parameter_tensors": len(keys),
                    "tensors_differing_from_seed17": differs_from_seed17,
                }
            )
    result = {"outcome": "PASS", "training_seed": seed, "worker": worker, "cells": results}
    write(Path(os.environ["EXPANDED_TERMINAL_PATH"]).parent / "audit-result.json", result)
    print(json.dumps(result, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Evaluation under the original cells' frozen contracts
# ---------------------------------------------------------------------------


def evaluate_baseline(worker: int) -> int:
    require_worker_environment(worker)
    from transformers import set_seed

    from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
    from examples.planning_benchmark_slice.visual_model import VisualPolicy

    panel, view_tasks = a_panel_tasks()
    task_by_id = {task["row"]["task_id"]: task for task in view_tasks}
    bindings = [binding for binding in a_bindings(panel) if binding["worker"] == worker]
    completed = 0
    for seed in SEEDS_NEW:
        eval_protocol = a_eval_protocol(seed)
        policy = None
        pending = [b for b in bindings if not binding_paths(ROOT, eval_protocol, b)[0].exists()]
        if pending:
            set_seed(17)
            policy = VisualPolicy(
                model_id=eval_protocol["model_id"],
                revision=eval_protocol["model_revision"],
                adapter_paths={A_ALGORITHM: str(a_cell_output(seed) / "final")},
                device="cuda:0",
                max_context_tokens=eval_protocol["context_tokens"],
                max_new_tokens=eval_protocol["output_tokens"],
                max_batch_size=eval_protocol["inference"]["max_batch_size"],
                max_batch_input_tokens=eval_protocol["inference"]["max_padded_batch_input_tokens"],
            )
            configure_visual_attention(policy.model, eval_protocol["inference"]["attention"])
            policy.identity.update(memoize_identical_inputs=False)
        for binding in bindings:
            checkpoint = str((a_cell_output(seed) / "final").relative_to(ROOT))

            def generate(example, policy=policy):
                output = policy.generate([example], A_ALGORITHM)[0]
                return output, policy.last_generation_usage["generated_sequence_tokens"]

            run_binding(
                ROOT,
                eval_protocol,
                task_by_id[binding["task_id"]],
                binding,
                checkpoint,
                ENDPOINTS[worker],
                generate,
            )
            completed += 1
            progress_write(completed, len(bindings) * len(SEEDS_NEW), seed=seed)
        if pending:
            del policy
            gc.collect()
            import torch

            torch.cuda.empty_cache()
    progress_write(len(bindings) * len(SEEDS_NEW), len(bindings) * len(SEEDS_NEW), terminal=True)
    return 0


def audit_evaluation_baseline(worker: int) -> int:
    panel, view_tasks = a_panel_tasks()
    task_by_id = {task["row"]["task_id"]: task for task in view_tasks}
    bindings = [binding for binding in a_bindings(panel) if binding["worker"] == worker]
    replayed = []
    for seed in SEEDS_NEW:
        eval_protocol = a_eval_protocol(seed)
        for binding in bindings:
            episode, partial, _ = binding_paths(ROOT, eval_protocol, binding)
            if partial.exists() or not episode.exists():
                raise ValueError(f"cell-A episode missing or incomplete: {episode}")
            report = read_json(episode)
            replay = independently_replay(ROOT, task_by_id[binding["task_id"]], report, ENDPOINTS[0])
            if replay != report["result"]:
                raise ValueError(f"cell-A independent replay differs: {episode}")
            replayed.append(str(episode.relative_to(ROOT)))
    result = {"outcome": "PASS", "worker": worker, "episodes_replayed": len(replayed), "episodes": replayed}
    write(Path(os.environ["EXPANDED_TERMINAL_PATH"]).parent / "audit-result.json", result)
    print(json.dumps({**result, "episodes": f"{len(replayed)} paths"}, indent=2))
    return 0


def b_armseeds_for(seed: int) -> tuple[str, str]:
    return (f"dagger_iteration_1_seed{seed}", f"continued_sft_iteration_1_seed{seed}")


COMPARATOR_FILE_CONDITIONS = {
    "original_process_sft": "process_sft",
    "random_valid": "random_valid",
    "exact_reference": "exact_reference",
}


def evaluate_dagger(seed: int, worker: int) -> int:
    require_worker_environment(worker)
    from transformers import set_seed

    from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
    from examples.planning_benchmark_slice.visual_model import VisualPolicy

    eval_protocol = b_eval_protocol()
    loaded = panels(ROOT, eval_protocol)
    armseeds = b_armseeds_for(seed)
    selected = {
        panel_name: [task for index, task in enumerate(tasks) if index % 2 == worker]
        for panel_name, tasks in loaded.items()
    }
    worker_total = sum(len(tasks) for tasks in selected.values()) * len(armseeds) * len(B_MODALITIES)
    completed_before = 0
    rows = []
    set_seed(eval_protocol["evaluation"]["seed"])
    policy = VisualPolicy(
        model_id=eval_protocol["model"]["id"],
        revision=eval_protocol["model"]["revision"],
        adapter_paths={
            f"{armseed}@{modality}": ROOT
            / eval_protocol["checkpoint_lineage"][armseed].format(modality=modality)
            for modality in B_MODALITIES
            for armseed in armseeds
        },
        device="cuda:0",
        max_context_tokens=eval_protocol["model"]["context_tokens"],
        max_new_tokens=eval_protocol["model"]["output_tokens"],
        max_batch_size=2,
        max_batch_input_tokens=24000,
        inference_dtype=eval_protocol["model"]["inference_dtype"],
    )
    configure_visual_attention(policy.model, eval_protocol["model"]["attention"])
    policy.identity.update(memoize_identical_inputs=False)
    for modality in B_MODALITIES:
        for panel_name, tasks in selected.items():
            for armseed in armseeds:

                def generate(examples, armseed=armseed, modality=modality, policy=policy):
                    outputs = policy.generate(examples, f"{armseed}@{modality}")
                    tokens = policy.last_generation_usage["generated_sequence_tokens"]
                    return outputs, [tokens] * len(outputs)

                def progress(
                    *,
                    completed,
                    total,
                    task_id,
                    retained,
                    base=completed_before,
                    armseed=armseed,
                    panel_name=panel_name,
                    modality=modality,
                ):
                    progress_write(
                        base + completed,
                        worker_total,
                        panel=panel_name,
                        modality=modality,
                        arm=armseed,
                        task_id=task_id,
                        retained=retained,
                    )

                reports = run_cell(
                    ROOT,
                    eval_protocol,
                    panel=panel_name,
                    modality=modality,
                    arm=armseed,
                    tasks=tasks,
                    endpoint=ENDPOINTS[worker],
                    generate=generate,
                    progress=progress,
                )
                rows.append(
                    {
                        "panel": panel_name,
                        "modality": modality,
                        "arm": armseed,
                        "episodes": len(reports),
                        "decisions": sum(report["result"]["decision_count"] for report in reports),
                    }
                )
                completed_before += len(tasks)
    del policy
    gc.collect()
    import torch

    torch.cuda.empty_cache()
    progress_write(worker_total, worker_total, terminal=True)
    attempt_dir = os.environ.get("EXPANDED_ATTEMPT_DIR")
    if attempt_dir:
        write(Path(attempt_dir) / "worker-result.json", {"outcome": "PASS", "worker": worker, "cells": rows})
    return 0


def audit_evaluation_dagger(seed: int, worker: int) -> int:
    eval_protocol = b_eval_protocol()
    loaded = panels(ROOT, eval_protocol)
    replayed = 0
    comparators = 0
    selected = {
        panel_name: [task for index, task in enumerate(tasks) if index % 2 == worker]
        for panel_name, tasks in loaded.items()
    }
    for modality in B_MODALITIES:
        for panel_name, tasks in selected.items():
            for armseed in b_armseeds_for(seed):
                for task in tasks:
                    verify_episode(ROOT, eval_protocol, panel_name, modality, task, armseed, ENDPOINTS[0])
                    replayed += 1
            for task in tasks:
                for condition in COMPARATORS:
                    verify_comparator(
                        ROOT,
                        eval_protocol,
                        panel_name,
                        modality,
                        task,
                        COMPARATOR_FILE_CONDITIONS[condition],
                        ENDPOINTS[0],
                    )
                    comparators += 1
    result = {
        "outcome": "PASS",
        "training_seed": seed,
        "worker": worker,
        "episodes_replayed": replayed,
        "comparator_episodes_replayed": comparators,
    }
    write(Path(os.environ["EXPANDED_TERMINAL_PATH"]).parent / "audit-result.json", result)
    print(json.dumps(result, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Finalize: full independent replay, evidence, analysis, publication
# ---------------------------------------------------------------------------


def episode_metrics(report: dict) -> dict:
    result = report["result"]
    return {
        "invariant_valid_success": bool(result["invariant_valid_success"]),
        "goal_reached": bool(result["goal_reached"]),
        "algorithm_invariants_hold": bool(result["algorithm_invariants_hold"]),
        "decision_count": result["decision_count"],
        "expansion_count": result["expansion_count"],
        "invalid_operation_count": result["invalid_operation_count"],
        "termination_reason": result["termination_reason"],
    }


def collect_baseline_seed(seed: int, *, replay: bool) -> dict:
    panel, view_tasks = a_panel_tasks()
    task_by_id = {task["row"]["task_id"]: task for task in view_tasks}
    rows = []
    if seed == 17:
        for binding in a_bindings(panel):
            episode = (
                ORIGINAL_BASELINE_EPISODES
                / A_MODALITY
                / binding["task_id"].replace("/", "__")
                / f"{A_ALGORITHM}-process_sft.json.gz"
            )
            report = read_json(episode)
            if report["checkpoint"] != f"outputs/matched_modalities/v5/training/{A_MODALITY}/{A_ALGORITHM}/final":
                raise ValueError("cell-A seed-17 episode checkpoint differs from the verified adapter")
            if replay:
                replay_result = independently_replay(ROOT, task_by_id[binding["task_id"]], report, ENDPOINTS[0])
                if replay_result != report["result"]:
                    raise ValueError(f"cell-A seed-17 independent replay differs: {episode}")
            rows.append({"task_id": binding["task_id"], **episode_metrics(report)})
    else:
        eval_protocol = a_eval_protocol(seed)
        for binding in a_bindings(panel):
            episode, _, _ = binding_paths(ROOT, eval_protocol, binding)
            report = read_json(episode)
            expected_checkpoint = str((a_cell_output(seed) / "final").relative_to(ROOT))
            if report["checkpoint"] != expected_checkpoint or report["seed"] != 17:
                raise ValueError(f"cell-A seed-{seed} episode identity differs")
            if replay:
                replay_result = independently_replay(ROOT, task_by_id[binding["task_id"]], report, ENDPOINTS[0])
                if replay_result != report["result"]:
                    raise ValueError(f"cell-A seed-{seed} independent replay differs: {episode}")
            rows.append({"task_id": binding["task_id"], **episode_metrics(report)})
    return {"seed": seed, "episodes": len(rows), "rows": rows}


def collect_baseline_comparator(condition: str, *, replay: bool) -> dict:
    panel, view_tasks = a_panel_tasks()
    task_by_id = {task["row"]["task_id"]: task for task in view_tasks}
    rows = []
    for binding in a_bindings(panel):
        episode = (
            ORIGINAL_BASELINE_EPISODES
            / A_MODALITY
            / binding["task_id"].replace("/", "__")
            / f"{A_ALGORITHM}-{condition}.json.gz"
        )
        report = read_json(episode)
        if replay:
            replay_result = independently_replay(ROOT, task_by_id[binding["task_id"]], report, ENDPOINTS[0])
            if replay_result != report["result"]:
                raise ValueError(f"cell-A comparator independent replay differs: {episode}")
        rows.append({"task_id": binding["task_id"], **episode_metrics(report)})
    return {"condition": condition, "episodes": len(rows), "rows": rows}


def collect_dagger_seed(seed: int, *, replay: bool) -> dict:
    eval_protocol = b_eval_protocol()
    loaded = panels(ROOT, eval_protocol)
    from examples.planning_benchmark_slice.expanded_dagger_evaluation import episode_path

    cells = []
    for modality in B_MODALITIES:
        for arm in B_ARMS:
            armseed = f"{arm}_iteration_1_seed{seed}"
            for panel_name, tasks in loaded.items():
                rows = []
                for task in tasks:
                    task_id = task["row"]["task_id"]
                    path = episode_path(ROOT, eval_protocol, panel_name, modality, task_id, armseed)
                    if replay:
                        report = verify_episode(ROOT, eval_protocol, panel_name, modality, task, armseed, ENDPOINTS[0])
                    else:
                        report = read_json(path)
                    rows.append({"task_id": task_id, **episode_metrics(report)})
                cells.append(
                    {
                        "modality": modality,
                        "arm": arm,
                        "panel": panel_name,
                        "episodes": len(rows),
                        "rows": rows,
                    }
                )
    return {"seed": seed, "cells": cells}


def collect_dagger_comparators(*, replay: bool) -> list[dict]:
    eval_protocol = b_eval_protocol()
    loaded = panels(ROOT, eval_protocol)
    rows = []
    for modality in B_MODALITIES:
        for panel_name, tasks in loaded.items():
            for task in tasks:
                for condition in COMPARATORS:
                    report = verify_comparator(
                        ROOT,
                        eval_protocol,
                        panel_name,
                        modality,
                        task,
                        COMPARATOR_FILE_CONDITIONS[condition],
                        ENDPOINTS[0],
                    )
                    rows.append(
                        {
                            "modality": modality,
                            "panel": panel_name,
                            "task_id": task["row"]["task_id"],
                            "condition": condition,
                            **episode_metrics(report),
                        }
                    )
    return rows


def paired_bootstrap(differences):
    import numpy as np

    values = np.array(differences, dtype=float)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    resample = rng.integers(0, len(values), size=(BOOTSTRAP_RESAMPLES, len(values)))
    boot = values[resample].mean(axis=1)
    lower, upper = (float(x) for x in np.percentile(boot, [2.5, 97.5]))
    return {
        "difference": float(values.mean()),
        "lower": lower,
        "upper": upper,
        "wins": int((values > 0).sum()),
        "losses": int((values < 0).sum()),
        "ties": int((values == 0).sum()),
        "units": len(values),
    }


def analysis(evidence: dict) -> dict:
    per_seed_baseline = {}
    for seed_data in evidence["baseline"]["seeds"]:
        seed = seed_data["seed"]
        rows = seed_data["rows"]
        comparators = {row["condition"]: row for row in evidence["baseline"]["comparators"]}
        by_task = {row["task_id"]: row for row in rows}
        contrasts = {}
        for condition in ("pretrained_base", "random_valid", "exact_reference"):
            comp = comparators[condition]
            comp_by_task = {row["task_id"]: row for row in comp["rows"]}
            differences = [
                float(by_task[task_id]["invariant_valid_success"])
                - float(comp_by_task[task_id]["invariant_valid_success"])
                for task_id in sorted(by_task)
            ]
            contrasts[f"process_sft_minus_{condition}"] = paired_bootstrap(differences)
        per_seed_baseline[str(seed)] = {
            "successes": sum(row["invariant_valid_success"] for row in rows),
            "episodes": len(rows),
            "invalid_operations": sum(row["invalid_operation_count"] for row in rows),
            "decisions": sum(row["decision_count"] for row in rows),
            "expansions": sum(row["expansion_count"] for row in rows),
            "contrasts": contrasts,
        }
    seeds_sorted = [str(seed) for seed in SEEDS_ALL]
    success_rates = [per_seed_baseline[seed]["successes"] / per_seed_baseline[seed]["episodes"] for seed in seeds_sorted]
    baseline_aggregated = {
        "successes_per_seed": {seed: per_seed_baseline[seed]["successes"] for seed in seeds_sorted},
        "episodes_per_seed": {seed: per_seed_baseline[seed]["episodes"] for seed in seeds_sorted},
        "success_rate_mean": sum(success_rates) / len(success_rates),
        "success_rate_min": min(success_rates),
        "success_rate_max": max(success_rates),
        "contrast_point_estimates_per_seed": {
            contrast: {seed: per_seed_baseline[seed]["contrasts"][contrast]["difference"] for seed in seeds_sorted}
            for contrast in per_seed_baseline["17"]["contrasts"]
        },
    }

    per_seed_dagger = {}
    for seed_data in evidence["dagger"]["seeds"]:
        seed = seed_data["seed"]
        arm_rows = {"dagger": {"development": [], "unseen": []}, "continued_sft": {"development": [], "unseen": []}}
        for cell in seed_data["cells"]:
            arm_rows[cell["arm"]][cell["panel"]].extend({"modality": cell["modality"], **row} for row in cell["rows"])
        comparators = {}
        for row in evidence["dagger"]["comparators"]:
            comparators.setdefault((row["panel"], row["condition"]), []).append(row)
        seed_summary = {"arms": {}, "contrasts": {}}
        for arm in B_ARMS:
            arm_summary = {}
            for panel_name in ("development", "unseen"):
                rows = arm_rows[arm][panel_name]
                decisions = sum(row["decision_count"] for row in rows)
                arm_summary[panel_name] = {
                    "successes": sum(row["invariant_valid_success"] for row in rows),
                    "episodes": len(rows),
                    "invalid_operations": sum(row["invalid_operation_count"] for row in rows),
                    "decisions": decisions,
                    "invalid_operation_rate": (
                        (sum(row["invalid_operation_count"] for row in rows) / decisions) if decisions else 0.0
                    ),
                    "per_modality": {
                        modality: {
                            "successes": sum(
                                row["invariant_valid_success"] for row in rows if row["modality"] == modality
                            ),
                            "episodes": sum(1 for row in rows if row["modality"] == modality),
                        }
                        for modality in B_MODALITIES
                    },
                }
            seed_summary["arms"][arm] = arm_summary
        for panel_name in ("development", "unseen"):
            dagger_rows = {(row["modality"], row["task_id"]): row for row in arm_rows["dagger"][panel_name]}
            continued_rows = {(row["modality"], row["task_id"]): row for row in arm_rows["continued_sft"][panel_name]}
            differences = [
                float(dagger_rows[key]["invariant_valid_success"])
                - float(continued_rows[key]["invariant_valid_success"])
                for key in sorted(dagger_rows)
            ]
            seed_summary["contrasts"][f"dagger_minus_continued_sft_{panel_name}"] = paired_bootstrap(differences)
            for condition in ("original_process_sft", "random_valid", "exact_reference"):
                comp_rows = {(row["modality"], row["task_id"]): row for row in comparators[(panel_name, condition)]}
                differences = [
                    float(dagger_rows[key]["invariant_valid_success"]) - float(comp_rows[key]["invariant_valid_success"])
                    for key in sorted(dagger_rows)
                ]
                seed_summary["contrasts"][f"dagger_minus_{condition}_{panel_name}"] = paired_bootstrap(differences)
        per_seed_dagger[str(seed)] = seed_summary
    dagger_rates = [per_seed_dagger[seed]["arms"]["dagger"]["unseen"]["successes"] / 72 for seed in seeds_sorted]
    continued_rates = [
        per_seed_dagger[seed]["arms"]["continued_sft"]["unseen"]["successes"] / 72 for seed in seeds_sorted
    ]
    dagger_aggregated = {
        "dagger_unseen_successes_per_seed": {
            seed: per_seed_dagger[seed]["arms"]["dagger"]["unseen"]["successes"] for seed in seeds_sorted
        },
        "continued_sft_unseen_successes_per_seed": {
            seed: per_seed_dagger[seed]["arms"]["continued_sft"]["unseen"]["successes"] for seed in seeds_sorted
        },
        "dagger_unseen_rate_mean": sum(dagger_rates) / len(dagger_rates),
        "dagger_unseen_rate_min": min(dagger_rates),
        "dagger_unseen_rate_max": max(dagger_rates),
        "continued_sft_unseen_rate_mean": sum(continued_rates) / len(continued_rates),
        "continued_sft_unseen_rate_min": min(continued_rates),
        "continued_sft_unseen_rate_max": max(continued_rates),
        "contrast_point_estimates_per_seed": {
            "dagger_minus_continued_sft_unseen": {
                seed: per_seed_dagger[seed]["contrasts"]["dagger_minus_continued_sft_unseen"]["difference"]
                for seed in seeds_sorted
            }
        },
    }
    return {
        "schema_version": "expanded_seed_replication_analysis_v1",
        "protocol_id": "expanded-seed-replication-v1",
        "seeds": {"original": 17, "additional_prospective": [29, 71]},
        "bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES, "confidence": 0.95},
        "cross_seed_aggregation": "descriptive only (n = 3 seeds); every seed reported individually; no seed dropped",
        "baseline_process_sft": {"per_seed": per_seed_baseline, "aggregated": baseline_aggregated},
        "dagger_iteration_1": {"per_seed": per_seed_dagger, "aggregated": dagger_aggregated},
    }


def finalize() -> int:
    import hashlib

    from safetensors import safe_open  # noqa: F401

    training = {"baseline": {}, "dagger": {}}
    for seed in SEEDS_NEW:
        status = read_json(a_cell_output(seed) / "status.json")
        final = a_cell_output(seed) / "final" / "adapter_model.safetensors"
        training["baseline"][str(seed)] = {
            "final_checkpoint": str((a_cell_output(seed) / "final").relative_to(ROOT)),
            "adapter_sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
            "optimizer_updates": status["steps"],
            "records": status["train_records"],
        }
        for modality in B_MODALITIES:
            for arm in B_ARMS:
                report = read_json(b_cell_dir(seed, modality, arm) / "report.json")
                final = ROOT / report["final_checkpoint"] / "adapter_model.safetensors"
                training["dagger"][f"{seed}/{modality}/{arm}"] = {
                    "final_checkpoint": report["final_checkpoint"],
                    "adapter_sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
                    "optimizer_updates": report["optimizer_updates"],
                    "records": report["records"],
                    "source_checkpoint": report["source_checkpoint"],
                }
    baseline_seeds = [collect_baseline_seed(seed, replay=True) for seed in SEEDS_ALL]
    baseline_comparators = [
        collect_baseline_comparator(condition, replay=True)
        for condition in ("pretrained_base", "random_valid", "exact_reference")
    ]
    dagger_seeds = [collect_dagger_seed(seed, replay=True) for seed in SEEDS_ALL]
    dagger_comparators = collect_dagger_comparators(replay=True)
    expected = {"baseline": 3 * 24 + 3 * 24, "dagger": 3 * 6 * 27 + 243}
    actual = {
        "baseline": (
            sum(item["episodes"] for item in baseline_seeds) + sum(item["episodes"] for item in baseline_comparators)
        ),
        "dagger": (
            sum(sum(cell["episodes"] for cell in item["cells"]) for item in dagger_seeds) + len(dagger_comparators)
        ),
    }
    if actual != expected:
        raise ValueError(f"seed-replication coverage differs: {actual} != {expected}")
    ledger = read(LEDGER_PATH)
    replication_attempts = [
        {
            "job_id": attempt["job_id"],
            "attempt": attempt["attempt"],
            "branch": attempt["branch"],
            "status": attempt["status"],
            "gpu_hours": attempt["gpu_hours"],
        }
        for attempt in ledger["attempts"]
        if attempt["job_id"].startswith("seed-rep-")
    ]
    evidence = {
        "schema_version": "expanded_seed_replication_evidence_v1",
        "protocol_id": "expanded-seed-replication-v1",
        "outcome": "PASS",
        "seeds": {"original": 17, "additional_prospective": [29, 71]},
        "independent_replay": {
            "every_new_episode_replayed": True,
            "new_episodes_replayed": 534,
            "seed17_baseline_cell_episodes_replayed": 24,
            "comparator_episodes_replayed": 3 * 24 + 243,
            "machinery": "replay_visual_episode over read-only persisted views; CPU-only, no model calls",
        },
        "training": training,
        "baseline": {"seeds": baseline_seeds, "comparators": baseline_comparators},
        "dagger": {"seeds": dagger_seeds, "comparators": dagger_comparators},
        "scheduler_attempts": replication_attempts,
        "compute_gpu_hours": {
            "baseline": sum(a["gpu_hours"] for a in replication_attempts if a["branch"] == "expanded_baseline"),
            "dagger": sum(a["gpu_hours"] for a in replication_attempts if a["branch"] == "dagger"),
        },
        "head": _git_head(ROOT),
    }
    write(OUT / "evidence.json", evidence)
    result = analysis(evidence)
    write(OUT / "analysis.json", result)
    publish(evidence, result)
    print(
        json.dumps(
            {"outcome": "PASS", "evidence": "outputs/expanded-study/v1/seed-replication/evidence.json"},
            indent=2,
        )
    )
    return 0


def publish(evidence: dict, result: dict) -> None:
    import csv
    import hashlib

    evidence_sha = hashlib.sha256((OUT / "evidence.json").read_bytes()).hexdigest()
    analysis_payload = {
        **result,
        "source_evidence": {
            "path": "outputs/expanded-study/v1/seed-replication/evidence.json",
            "sha256": evidence_sha,
        },
    }
    write(ADDENDUM_DIR / "seed-variance.json", analysis_payload)
    with (ADDENDUM_DIR / "seed-variance.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["cell", "seed", "arm", "panel", "successes", "episodes", "invalid_operations", "decisions"])
        for seed, per in result["baseline_process_sft"]["per_seed"].items():
            writer.writerow(
                [
                    "best_first_add_greedy/multimodal-state",
                    seed,
                    "process_sft",
                    "unseen",
                    per["successes"],
                    per["episodes"],
                    per["invalid_operations"],
                    per["decisions"],
                ]
            )
        for seed, per in result["dagger_iteration_1"]["per_seed"].items():
            for arm in B_ARMS:
                for panel_name in ("development", "unseen"):
                    summary = per["arms"][arm][panel_name]
                    writer.writerow(
                        [
                            "bfs/dagger-iteration-1",
                            seed,
                            arm,
                            panel_name,
                            summary["successes"],
                            summary["episodes"],
                            summary["invalid_operations"],
                            summary["decisions"],
                        ]
                    )
    (ADDENDUM_DIR / "seed-variance-addendum.md").write_text(render_addendum(result, evidence_sha), encoding="utf-8")


def render_addendum(result: dict, evidence_sha: str) -> str:
    base = result["baseline_process_sft"]
    dag = result["dagger_iteration_1"]
    seeds = ["17", "29", "71"]

    def fmt(value: float) -> str:
        return f"{value:+.3f}"

    lines = []
    lines.append("# Seed-variance addendum — prospective training-seed replication (#127)")
    lines.append("")
    lines.append(
        "Protocol `expanded-seed-replication-v1` (frozen 2026-09-20 before any seed-29/71 artifact; "
        "amendment `docs/experiments/expanded-study/seed-replication-amendment.md`, machine-readable "
        "`configs/experiments/expanded-study/seed-replication-protocol.json`). This addendum appends "
        "training-seed-variance evidence to synthesis-v1; it does not modify any published verdict, and "
        "`synthesis-v1/README.md` remains the frozen #120 snapshot (its single-training-seed claim "
        "boundary is superseded only for the two cells below, which now report seed robustness). "
        "Seeds: original 17 plus prospective 29 and 71, frozen before launch; every seed is reported "
        "individually and aggregated; no seed was dropped after outcomes. Every new episode (534: 48 "
        "baseline + 486 DAgger) was independently replayed CPU-only; the 24 seed-17 baseline-cell "
        "episodes and all referenced comparator episodes were re-replayed at finalize. Machine-readable "
        "analysis: `seed-variance.json` (+ `seed-variance.csv`); canonical evidence: "
        f"`outputs/expanded-study/v1/seed-replication/evidence.json` (sha256 "
        f"`{evidence_sha}`)."
    )
    lines.append("")
    lines.append("## Cell A — expanded-baseline headline process-SFT cell")
    lines.append("")
    lines.append(
        "Cell: `best_first_add_greedy x multimodal-state` process-SFT on the 24-problem "
        "unseen panel `expanded-panel-v2-qualified` (the headline cell of the primary positive "
        "contrast). Fresh LoRA adapter per seed (new init + dropout RNG; identical frozen 512-record "
        "membership, one epoch, 16 updates). Evaluation seed 17, greedy decoding, 2x reference "
        "decision call limit "
        "— the original cell's frozen contract; comparators reused from the replay-verified baseline "
        "episodes."
    )
    lines.append("")
    lines.append("| Seed | Successes/24 | Invalid ops | Decisions | Expansions |")
    lines.append("| ---: | ---: | ---: | ---: | ---: |")
    for seed in seeds:
        per = base["per_seed"][seed]
        lines.append(
            f"| {seed} | {per['successes']}/24 | {per['invalid_operations']} | {per['decisions']} | "
            f"{per['expansions']} |"
        )
    agg = base["aggregated"]
    lines.append("")
    lines.append(
        f"Aggregated (descriptive, n = 3): success rate mean {agg['success_rate_mean']:.3f}, "
        f"min {agg['success_rate_min']:.3f}, max {agg['success_rate_max']:.3f}; "
        f"successes per seed {agg['successes_per_seed']['17']}/{agg['successes_per_seed']['29']}/"
        f"{agg['successes_per_seed']['71']} of 24."
    )
    lines.append("")
    lines.append(
        "Per-seed paired whole-problem contrasts over the 24 tasks (bootstrap seed 1729, 10,000 resamples, "
        "95% percentile intervals):"
    )
    lines.append("")
    lines.append("| Contrast | Seed 17 | Seed 29 | Seed 71 |")
    lines.append("| --- | ---: | ---: | ---: |")
    for contrast in (
        "process_sft_minus_pretrained_base",
        "process_sft_minus_random_valid",
        "process_sft_minus_exact_reference",
    ):
        row = []
        for seed in seeds:
            c = base["per_seed"][seed]["contrasts"][contrast]
            row.append(
                f"{fmt(c['difference'])} [{fmt(c['lower'])}, {fmt(c['upper'])}] "
                f"(wins {c['wins']}, losses {c['losses']}, ties {c['ties']})"
            )
        lines.append(f"| {contrast} | {row[0]} | {row[1]} | {row[2]} |")
    lines.append("")
    lines.append("## Cell set B — DAgger iteration-1 vs exposure-matched continued-SFT")
    lines.append("")
    lines.append(
        "Cells: `bfs x {text-state, visual-state, multimodal-state} x {dagger, continued_sft}` "
        "at iteration 1, continued from the verified seed-17 starting adapters on the verified "
        "seed-17 memberships (new seed perturbs only the dropout RNG). Evaluated on the original "
        "frozen panels "
        "(3 development + 24 unseen per modality) with evaluation seed 17 and the original call limits. "
        "The seed-17 iteration-1 checkpoints were never panel-evaluated in the original program (it "
        "evaluated iteration-2 finals only); they are evaluated here inference-only under the same "
        "contract so the comparison's seed-17 point exists. Comparators (original process SFT, "
        "random-valid, exact reference) are reused from the replay-verified original DAgger evaluation."
    )
    lines.append("")
    lines.append("| Arm | Seed | Dev successes/9 | Unseen successes/72 | Unseen invalid rate |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for arm in B_ARMS:
        for seed in seeds:
            summary = dag["per_seed"][seed]["arms"][arm]
            dev = summary["development"]
            unseen = summary["unseen"]
            lines.append(
                f"| {arm}_iteration_1 | {seed} | {dev['successes']}/9 | {unseen['successes']}/72 | "
                f"{unseen['invalid_operation_rate']:.3f} |"
            )
    lines.append("")
    agg = dag["aggregated"]
    lines.append(
        f"Aggregated (descriptive, n = 3): DAgger unseen rate mean {agg['dagger_unseen_rate_mean']:.3f} "
        f"[min {agg['dagger_unseen_rate_min']:.3f}, max {agg['dagger_unseen_rate_max']:.3f}]; "
        f"continued-SFT mean {agg['continued_sft_unseen_rate_mean']:.3f} "
        f"[min {agg['continued_sft_unseen_rate_min']:.3f}, max {agg['continued_sft_unseen_rate_max']:.3f}]."
    )
    lines.append("")
    lines.append(
        "Per-seed paired contrast dagger_iteration_1 - continued_sft_iteration_1 on the 72 unseen "
        "modality-task rows (bootstrap seed 1729, 10,000 resamples, 95% percentile intervals):"
    )
    lines.append("")
    lines.append("| Seed | Point | 95% interval | Wins | Losses | Ties |")
    lines.append("| ---: | ---: | --- | ---: | ---: | ---: |")
    for seed in seeds:
        c = dag["per_seed"][seed]["contrasts"]["dagger_minus_continued_sft_unseen"]
        lines.append(
            f"| {seed} | {fmt(c['difference'])} | [{fmt(c['lower'])}, {fmt(c['upper'])}] | {c['wins']} "
            f"| {c['losses']} | {c['ties']} |"
        )
    lines.append("")
    lines.append("## Boundaries")
    lines.append("")
    lines.append(
        "- Cross-seed aggregation is descriptive only (n = 3 seeds); per-seed bootstrap intervals remain "
        "tiny-subgroup descriptive bounds over 24 (cell A) or 72/9 (cell B) units.\n"
        "- Cell A covers one modality of the three in the pooled headline contrast; the other two "
        "modalities remain single-seed evidence as published.\n"
        "- Cell set B is the iteration-1 comparison named by the ticket; the published iteration-2 "
        "comparison (single seed 17) is unchanged and remains the program's DAgger verdict.\n"
        "- Random-valid is an oracle-assisted programmatic control; exact-reference bounds perfect "
        "decision-making. Neither measures learned ability.\n"
        "- Training-seed variance is now reported for exactly these two cells; all other cells of the "
        "program remain single-seed (17) as published."
    )
    lines.append("")
    return "\n".join(lines)


def audit_final() -> int:
    import hashlib

    evidence = read(OUT / "evidence.json")
    recomputed = analysis(evidence)
    published = read(ADDENDUM_DIR / "seed-variance.json")
    evidence_sha = hashlib.sha256((OUT / "evidence.json").read_bytes()).hexdigest()
    if published.get("source_evidence", {}).get("sha256") != evidence_sha:
        raise ValueError("published seed-variance evidence digest differs")
    stripped = {key: value for key, value in published.items() if key != "source_evidence"}
    if stripped != recomputed:
        raise ValueError("published seed-variance analysis differs from an independent recompute")
    coverage = {"baseline": 0, "dagger": 0}
    for seed in SEEDS_NEW:
        eval_protocol = a_eval_protocol(seed)
        panel, _ = a_panel_tasks()
        for binding in a_bindings(panel):
            episode, _, _ = binding_paths(ROOT, eval_protocol, binding)
            if not episode.exists():
                raise ValueError(f"missing cell-A episode: {episode}")
            coverage["baseline"] += 1
    eval_protocol = b_eval_protocol()
    from examples.planning_benchmark_slice.expanded_dagger_evaluation import episode_path

    loaded = panels(ROOT, eval_protocol)
    for modality in B_MODALITIES:
        for armseed in B_ARMSEEDS:
            for panel_name, tasks in loaded.items():
                for task in tasks:
                    path = episode_path(ROOT, eval_protocol, panel_name, modality, task["row"]["task_id"], armseed)
                    if not path.exists():
                        raise ValueError(f"missing cell-B episode: {path}")
                    coverage["dagger"] += 1
    if coverage != {"baseline": 48, "dagger": 486}:
        raise ValueError(f"seed-replication new-episode coverage differs: {coverage}")
    result = {"outcome": "PASS", "coverage": coverage, "evidence_sha256": evidence_sha}
    terminal = os.environ.get("EXPANDED_TERMINAL_PATH")
    if terminal:
        write(Path(terminal).parent / "audit-result.json", result)
    print(json.dumps(result, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "prepare",
            "train-baseline",
            "audit-training-baseline",
            "train-dagger",
            "audit-training-dagger",
            "evaluate-baseline",
            "audit-evaluation-baseline",
            "evaluate-dagger",
            "audit-evaluation-dagger",
            "finalize",
            "audit-final",
        ),
    )
    parser.add_argument("--worker", type=int, choices=(0, 1))
    parser.add_argument("--seed", type=int, choices=SEEDS_ALL)
    args = parser.parse_args()
    if args.stage == "prepare":
        raise SystemExit(prepare())
    if args.stage == "train-baseline":
        raise SystemExit(train_baseline(args.worker))
    if args.stage == "audit-training-baseline":
        raise SystemExit(audit_training_baseline(args.worker))
    if args.stage == "train-dagger":
        raise SystemExit(train_dagger(args.seed, args.worker))
    if args.stage == "audit-training-dagger":
        raise SystemExit(audit_training_dagger(args.seed, args.worker))
    if args.stage == "evaluate-baseline":
        raise SystemExit(evaluate_baseline(args.worker))
    if args.stage == "audit-evaluation-baseline":
        raise SystemExit(audit_evaluation_baseline(args.worker))
    if args.stage == "evaluate-dagger":
        raise SystemExit(evaluate_dagger(args.seed, args.worker))
    if args.stage == "audit-evaluation-dagger":
        raise SystemExit(audit_evaluation_dagger(args.seed, args.worker))
    if args.stage == "finalize":
        raise SystemExit(finalize())
    if args.stage == "audit-final":
        raise SystemExit(audit_final())


if __name__ == "__main__":
    main()
