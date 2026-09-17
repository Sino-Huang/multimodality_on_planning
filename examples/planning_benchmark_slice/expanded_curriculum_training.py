"""Frozen-order fresh-base LoRA training for the expanded curriculum study."""

from __future__ import annotations

import hashlib
import math
import os
import random
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from torch.utils.data import Dataset, SequentialSampler

from .expanded_successor_training import _adapter_tensor_changes, _sha256
from .modality_corpus import ModalityCorpus
from .modality_corpus_replay import canonical
from .modality_view_preparation import write_json
from .scene_assets import read_json

CELL_SCHEMA = "expanded_curriculum_training_cell_v1"
REPORT_SCHEMA = "expanded_curriculum_training_report_v1"
RECEIPT_SCHEMA = "expanded_curriculum_training_completion_receipt_v1"
RECEIPT_FILE = "completion-receipt.json"
RECOVERY_SCHEMA = "expanded_curriculum_training_recovery_v1"
RECOVERY_FILE = ".training-recovery.json"
FRESH_INIT_FILE = "fresh-lora-init.safetensors"
ORDERINGS = ("staged", "shuffled", "mixed_order")
DIFFICULTIES = ("easy", "medium", "hard")


def _json_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def _pair_id(record_id: str) -> str:
    return record_id.split(":", 1)[0]


def build_orderings(canonical_ids: Sequence[str], difficulty_map: Mapping[str, str]) -> dict[str, list[str]]:
    ids = list(canonical_ids)
    if len(ids) != len(set(ids)) or any(_pair_id(row) not in difficulty_map for row in ids):
        raise ValueError("curriculum canonical membership or difficulty coverage is invalid")
    if set(difficulty_map.values()) - set(DIFFICULTIES):
        raise ValueError("curriculum difficulty map contains an unsupported value")
    rank = {name: index for index, name in enumerate(DIFFICULTIES)}
    canonical_index = {record_id: index for index, record_id in enumerate(ids)}
    staged = sorted(ids, key=lambda row: (rank[difficulty_map[_pair_id(row)]], canonical_index[row]))
    shuffled = list(ids)
    random.Random(64).shuffle(shuffled)
    buckets = {
        difficulty: [row for row in ids if difficulty_map[_pair_id(row)] == difficulty] for difficulty in DIFFICULTIES
    }
    positions = {difficulty: 0 for difficulty in DIFFICULTIES}
    mixed = []
    while len(mixed) < len(ids):
        for difficulty in DIFFICULTIES:
            if positions[difficulty] < len(buckets[difficulty]):
                mixed.append(buckets[difficulty][positions[difficulty]])
                positions[difficulty] += 1
    return {"staged": staged, "shuffled": shuffled, "mixed_order": mixed}


def verify_frozen_orderings(protocol: Mapping[str, Any]) -> dict[str, list[str]]:
    rebuilt = build_orderings(protocol["source_record_ids"], protocol["difficulty_map"])
    canonical_set = set(protocol["source_record_ids"])
    for ordering in ORDERINGS:
        frozen = protocol["orderings"][ordering]
        ordered = frozen.get("ordered_ids")
        if (
            ordered != rebuilt[ordering]
            or len(ordered) != 512
            or set(ordered) != canonical_set
            or frozen.get("sha256") != _json_sha256(ordered)
        ):
            raise ValueError(f"curriculum frozen ordering differs: {ordering}")
    return rebuilt


def _difficulty_from_manifest(root: Path, protocol: Mapping[str, Any]) -> dict[str, str]:
    manifest = read_json(root / protocol["difficulty_manifest"])
    result = {}
    for artifact in manifest["artifacts"]:
        parts = artifact["path"].split("/")
        if (
            len(parts) >= 7
            and parts[:3] == ["training", "process", "train"]
            and parts[-1] == f"{protocol['algorithm']}.jsonl.gz"
        ):
            result[parts[-2]] = parts[-3]
    pairs = {_pair_id(record_id) for record_id in protocol["source_record_ids"]}
    return {pair: result[pair] for pair in sorted(pairs)}


def validate_protocol(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    study = read_json(root / protocol["source_study"])
    membership = read_json(root / protocol["source_membership"])
    schedule = read_json(root / "docs/experiments/expanded-study/schedule.json")
    binding = read_json(
        root / "outputs/matched_modalities/v5/training/visual-state/best_first_add_greedy/training-binding.json"
    )
    training = protocol["training"]
    base = protocol["base_model"]
    evaluation = protocol["evaluation"]
    launch = protocol["launch"]
    budget = protocol["budget"]
    expected_training = {
        "records_per_cell": 512,
        "epochs": 1,
        "optimizer_updates": 16,
        "seed": 17,
        "data_seed": 17,
        "microbatch_size": 1,
        "global_batch_size": 32,
        "gradient_accumulation_steps": 32,
        "sampler": "protocol_frozen_order",
        "trainer_reshuffling": False,
        "learning_rate": 0.0001,
        "optimizer": "adamw_torch",
        "adam_beta1": 0.9,
        "adam_beta2": 0.999,
        "adam_epsilon": 1e-8,
        "warmup_ratio": 0.03,
        "warmup_steps": 1,
        "lr_scheduler": "cosine",
        "weight_decay": 0,
        "max_grad_norm": 1,
        "lora_rank": 64,
        "lora_alpha": 128,
        "lora_dropout": 0.05,
        "lora_target_modules": "all-linear",
        "lora_exclude_modules": ".*visual.*",
        "lora_bias": "none",
        "lora_task_type": "CAUSAL_LM",
        "freeze_vision": True,
        "dtype": "bfloat16",
        "attention": "sdpa",
        "gradient_checkpointing": True,
        "gradient_checkpointing_use_reentrant": False,
        "context_tokens": 32768,
        "maximum_input_tokens": 32384,
        "output_tokens": 384,
        "loss": "shared_collator_assistant_target_only",
        "checkpoint_selection": "final_update_16_only",
        "save_strategy": "no",
        "single_training_run_per_cell": True,
        "fresh_base_per_cell": True,
    }
    study_training = study["training"]
    expected_arms = [
        {"arm": arm_name(modality, ordering), "training_modality": modality, "ordering": ordering}
        for modality in protocol["modalities"]
        for ordering in ORDERINGS
    ]
    if (
        protocol.get("schema_version") != "expanded_curriculum_protocol_v1"
        or protocol.get("protocol_id") != "expanded-curriculum-v1"
        or protocol.get("status") != "frozen_before_training"
        or protocol.get("issues") != [119]
        or protocol.get("parent_issue") != 38
        or protocol.get("algorithm") != "best_first_add_greedy"
        or protocol.get("modalities") != ["text-state", "visual-state", "multimodal-state"]
        or protocol.get("source_study") != "configs/experiments/matched-modalities/study-v5.json"
        or protocol.get("source_membership") != "configs/experiments/matched-modalities/membership.json"
        or protocol.get("source_corpus") != "outputs/modality_corpus/issue74-matched-32k-v1/release-001/report.json"
        or protocol.get("difficulty_manifest")
        != "data/best_first_paired_phase_v3/corpus-release-v3/training/manifest.json"
        or protocol.get("views")
        != {
            "contract": "configs/experiments/issue72/views-contract-v2.json",
            "scene_views": "outputs/matched_modalities/v5/preparation/scene-views.json",
            "rendering": "matched_v5_ModalityCorpus.training_example",
        }
        or protocol.get("output_root") != "outputs/expanded-study/v1/curriculum"
        or "starting_checkpoints" in protocol
        or base.get("historical_checkpoint_reuse") is not False
        or base.get("model_id") != study["model_id"]
        or base.get("revision") != study["model_revision"]
        or base.get("processor_class") != study["processor_class"]
        or base.get("processor_revision") != study["processor_revision"]
        or protocol["source_record_ids"] != membership["training_record_ids"][protocol["algorithm"]]
        or protocol.get("source_record_ids_sha256") != _json_sha256(protocol["source_record_ids"])
        or len(protocol["source_record_ids"]) != 512
        or len(set(protocol["source_record_ids"])) != 512
        or training != expected_training
        or study.get("historical_checkpoint_reuse") is not False
        or study.get("training_seed") != training["seed"]
        or study.get("context_tokens") != training["context_tokens"]
        or study.get("maximum_input_tokens") != training["maximum_input_tokens"]
        or study.get("output_tokens") != training["output_tokens"]
        or any(
            study_training[study_key] != training[protocol_key]
            for study_key, protocol_key in (
                ("epochs", "epochs"),
                ("records_per_algorithm", "records_per_cell"),
                ("optimizer_updates", "optimizer_updates"),
                ("microbatch_size", "microbatch_size"),
                ("global_batch_size", "global_batch_size"),
                ("gradient_accumulation_steps", "gradient_accumulation_steps"),
                ("learning_rate", "learning_rate"),
                ("optimizer", "optimizer"),
                ("adam_beta1", "adam_beta1"),
                ("adam_beta2", "adam_beta2"),
                ("adam_epsilon", "adam_epsilon"),
                ("warmup_ratio", "warmup_ratio"),
                ("warmup_steps", "warmup_steps"),
                ("lr_scheduler", "lr_scheduler"),
                ("weight_decay", "weight_decay"),
                ("max_grad_norm", "max_grad_norm"),
                ("lora_rank", "lora_rank"),
                ("lora_alpha", "lora_alpha"),
                ("lora_dropout", "lora_dropout"),
                ("lora_target_modules", "lora_target_modules"),
                ("lora_exclude_modules", "lora_exclude_modules"),
                ("lora_bias", "lora_bias"),
                ("lora_task_type", "lora_task_type"),
                ("freeze_vision", "freeze_vision"),
                ("dtype", "dtype"),
                ("attention", "attention"),
                ("gradient_checkpointing_use_reentrant", "gradient_checkpointing_use_reentrant"),
                ("checkpoint_selection", "checkpoint_selection"),
                ("loss", "loss"),
            )
        )
        or binding.get("study") != study
        or binding.get("algorithm") != protocol["algorithm"]
        or binding.get("training_record_ids") != protocol["source_record_ids"]
        or evaluation.get("development_panel") != "outputs/matched_modalities/v5/preparation/final-panel.json"
        or evaluation.get("unseen_panel") != "configs/experiments/expanded-study/final-panel.json"
        or evaluation.get("panels") != {"development_tasks": 3, "unseen_tasks": 24}
        or evaluation.get("seed") != 17
        or evaluation.get("final_checkpoints_only") is not True
        or evaluation.get("arms") != expected_arms
        or evaluation.get("model_episodes") != 243
        or evaluation.get("paired_analysis_units") != 27
        or evaluation.get("matching_rule") != "evaluate each arm only when training_modality equals evaluation modality"
        or {name: row.get("condition") for name, row in evaluation.get("comparators", {}).items()}
        != {
            "base": "pretrained_base",
            "sft_sequential_order_control": "process_sft",
            "random_valid": "random_valid",
            "exact_reference": "exact_reference",
        }
        or evaluation.get("comparator_reuse_requires_independent_replay") is not True
        or evaluation.get("comparator_audit", {}).get("development_contract_id") != "matched-modalities-v5"
        or evaluation.get("comparator_audit", {}).get("unseen_protocol_id") != "expanded-matched-baseline-v1"
        or launch.get("devices") != [0, 1]
        or launch.get("master_port_pool") != schedule["master_port_pool"]
        or launch.get("backend_endpoints") != ["http://127.0.0.1:18092", "http://127.0.0.1:18093"]
        or launch.get("training_worker_cells")
        != {
            "0": [
                {"modality": modality, "ordering": ordering}
                for modality in ("text-state", "multimodal-state")
                for ordering in ORDERINGS
            ],
            "1": [{"modality": "visual-state", "ordering": ordering} for ordering in ORDERINGS],
        }
        or launch.get("evaluation_worker_modalities") != {"0": ["text-state", "multimodal-state"], "1": ["visual-state"]}
        or budget.get("branch") != "curriculum_modality"
        or budget.get("gpu_hours") != 48
        or schedule["allocations_gpu_hours"]["curriculum_modality"] != 48
        or budget.get("gpu_cutoff_utc") != "2026-09-21T11:55:19Z"
        or budget.get("evaluation_model_episodes") != 243
        or budget.get("training_measured_gpu_hours_per_cell") != 0.2313
        or budget.get("training_cells") != 9
        or budget.get("training_raw_gpu_hours") != 2.0817
        or budget.get("training_qualified_gpu_hours") != 2.602125
        or budget.get("qualification_safety_factor") != 1.25
        or budget.get("evaluation_raw_gpu_hours") != 3.5870795803
        or budget.get("evaluation_qualified_gpu_hours") != 4.4838494754
        or budget.get("total_raw_gpu_hours") != 5.6687795803
        or budget.get("total_qualified_gpu_hours") != 7.0859744754
        or budget.get("fits_branch_budget") is not True
    ):
        raise ValueError("expanded curriculum protocol differs from the frozen study")
    comparator_audit = evaluation["comparator_audit"]
    audit_paths = {
        "goal3_evidence": "docs/experiments/expanded-study/baseline-evaluation.json",
        "goal3_independent_replay": "docs/experiments/expanded-study/baseline-independent-replay.json",
        "checkpoint_readiness": "docs/experiments/expanded-study/readiness.json",
    }
    if any(
        comparator_audit.get(key) != relative or comparator_audit.get(f"{key}_sha256") != _sha256(root / relative)
        for key, relative in audit_paths.items()
    ) or set(comparator_audit.get("process_sft", {})) != set(protocol["modalities"]):
        raise ValueError("expanded curriculum comparator audit contract differs")
    for modality, row in comparator_audit["process_sft"].items():
        checkpoint = root / row["checkpoint"]
        if row.get("adapter_model_sha256") != _sha256(checkpoint / "adapter_model.safetensors") or row.get(
            "adapter_config_sha256"
        ) != _sha256(checkpoint / "adapter_config.json"):
            raise ValueError(f"expanded curriculum comparator checkpoint differs: {modality}")
    if _difficulty_from_manifest(root, protocol) != protocol["difficulty_map"]:
        raise ValueError("curriculum difficulty map differs from the source manifest")
    verify_frozen_orderings(protocol)
    corpus = ModalityCorpus(root, root / protocol["source_corpus"], scene_views=protocol["views"]["scene_views"])
    records = list(corpus.records(algorithm=protocol["algorithm"], split="train"))
    indexed = {row["record_id"]: row for row in records}
    if not set(protocol["source_record_ids"]).issubset(indexed):
        raise ValueError("curriculum source corpus omits frozen membership records")
    selected = [indexed[record_id] for record_id in protocol["source_record_ids"]]
    source_files = _source_files(root, protocol, corpus, selected)
    return {
        "study": study,
        "membership": membership,
        "corpus": corpus,
        "records": selected,
        "source_files": source_files,
    }


def _source_files(
    root: Path, protocol: Mapping[str, Any], corpus: ModalityCorpus, records: Sequence[Mapping[str, Any]]
) -> list[Path]:
    paths = {
        root / protocol["source_membership"],
        root / protocol["source_corpus"],
        root / protocol["difficulty_manifest"],
        root / protocol["source_study"],
        root / protocol["views"]["scene_views"],
    }
    task_ids = {row["task_id"] for row in records}
    scene_report = read_json(root / protocol["views"]["scene_views"])
    raw_scene_tasks = scene_report.get("tasks", {})
    scene_tasks = (
        raw_scene_tasks if isinstance(raw_scene_tasks, dict) else {row["task_id"]: row for row in raw_scene_tasks}
    )
    states_by_task: dict[str, set[str]] = {}
    for record in records:
        states_by_task.setdefault(record["task_id"], set()).add(str(record["state"]))
    for task_id in task_ids:
        result = corpus.results[task_id]
        for key in ("path", "view_manifest"):
            if result.get(key):
                paths.add(root / result[key])
        scene = scene_tasks.get(task_id, {})
        if scene.get("source_manifest"):
            source_manifest = root / scene["source_manifest"]
            paths.add(source_manifest)
            manifest = read_json(source_manifest)
            paths.add(root / manifest["scene_catalog"])
        for path in (*scene.get("static_pages", []), *scene.get("goal_pages", [])):
            paths.add(root / path)
        scenes = scene.get("scenes", {})
        for state in {"0", *states_by_task.get(task_id, set())}:
            if state in scenes:
                paths.add(root / scenes[state])
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise ValueError(f"curriculum source artifacts are missing: {missing[0]}")
    return sorted(paths)


def _source_manifest(root: Path, paths: Sequence[Path]) -> dict[str, dict[str, Any]]:
    result = {}
    for path in sorted(paths):
        stat = path.stat()
        result[str(path.relative_to(root))] = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": _sha256(path),
        }
    return result


def training_root(root: Path, protocol: Mapping[str, Any], modality: str, ordering: str) -> Path:
    return root / protocol["output_root"] / "training" / modality / ordering


def arm_name(modality: str, ordering: str) -> str:
    return f"{modality}__{ordering}"


class CurriculumDataset(Dataset):
    """Render original matched-v5 examples in one protocol-frozen order."""

    def __init__(self, context: Mapping[str, Any], protocol: Mapping[str, Any], modality: str, ordering: str):
        if modality not in protocol["modalities"] or ordering not in ORDERINGS:
            raise ValueError("curriculum dataset cell is outside the frozen protocol")
        indexed = {row["record_id"]: row for row in context["records"]}
        self.record_ids = list(protocol["orderings"][ordering]["ordered_ids"])
        if set(self.record_ids) != set(protocol["source_record_ids"]):
            raise ValueError("curriculum dataset record set differs")
        self.records = [indexed[record_id] for record_id in self.record_ids]
        self.corpus = context["corpus"]
        self.modality = modality

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.corpus.training_example(self.records[index], self.modality)


def sequential_sampler(dataset: Any) -> SequentialSampler:
    return SequentialSampler(dataset)


def optimizer_updates(records: int, training: Mapping[str, Any]) -> int:
    return math.ceil(records / training["global_batch_size"]) * training["epochs"]


def training_arguments_kwargs(protocol: Mapping[str, Any], output: Path) -> dict[str, Any]:
    t = protocol["training"]
    return {
        "output_dir": str(output),
        "num_train_epochs": t["epochs"],
        "per_device_train_batch_size": t["microbatch_size"],
        "gradient_accumulation_steps": t["gradient_accumulation_steps"],
        "learning_rate": t["learning_rate"],
        "weight_decay": t["weight_decay"],
        "warmup_ratio": t["warmup_ratio"],
        "warmup_steps": t["warmup_steps"],
        "lr_scheduler_type": t["lr_scheduler"],
        "optim": t["optimizer"],
        "adam_beta1": t["adam_beta1"],
        "adam_beta2": t["adam_beta2"],
        "adam_epsilon": t["adam_epsilon"],
        "max_grad_norm": t["max_grad_norm"],
        "bf16": True,
        "gradient_checkpointing": True,
        "gradient_checkpointing_kwargs": {"use_reentrant": False},
        "seed": t["seed"],
        "data_seed": t["data_seed"],
        "logging_steps": 1,
        "save_strategy": "no",
        "report_to": [],
        "remove_unused_columns": False,
        "dataloader_num_workers": 0,
    }


def _model_config(protocol: Mapping[str, Any]) -> dict[str, Any]:
    base, training = protocol["base_model"], protocol["training"]
    return {
        "model_id": base["model_id"],
        "model_revision": base["revision"],
        "training_seed": training["seed"],
        "training": {
            "lora_rank": training["lora_rank"],
            "lora_alpha": training["lora_alpha"],
            "lora_dropout": training["lora_dropout"],
            "freeze_vision": training["freeze_vision"],
            "attention": training["attention"],
        },
    }


def _effective_arguments(protocol: Mapping[str, Any]) -> dict[str, Any]:
    return {**protocol["training"], "base_model": dict(protocol["base_model"])}


def _trainer_digest(state: Mapping[str, Any]) -> dict[str, Any]:
    value = {"global_step": state.get("global_step"), "log_history": state.get("log_history", [])}
    return {**value, "sha256": _json_sha256(value)}


def _final_fingerprints(final: Path) -> dict[str, str]:
    tensor, config = final / "adapter_model.safetensors", final / "adapter_config.json"
    if not tensor.is_file() or not config.is_file():
        raise ValueError("curriculum final checkpoint is incomplete")
    return {"final_checkpoint_sha256": _sha256(tensor), "final_adapter_config_sha256": _sha256(config)}


def _safetensor_count(path: Path) -> int:
    from safetensors import safe_open

    with safe_open(path, framework="pt", device="cpu") as handle:
        return len(list(handle.keys()))


def _validate_adapter_config(protocol: Mapping[str, Any], path: Path) -> None:
    config, t = read_json(path), protocol["training"]
    if (
        config.get("r") != t["lora_rank"]
        or config.get("lora_alpha") != t["lora_alpha"]
        or config.get("lora_dropout") != t["lora_dropout"]
        or config.get("exclude_modules") != t["lora_exclude_modules"]
        or config.get("bias") != t["lora_bias"]
        or config.get("task_type") != t["lora_task_type"]
    ):
        raise ValueError("curriculum adapter config differs from frozen LoRA settings")


def _receipt(
    root: Path,
    protocol: Mapping[str, Any],
    *,
    modality: str,
    ordering: str,
    source_manifest: Mapping[str, Any],
    final: Path,
    init_tensor: Path,
    state: Mapping[str, Any],
    wall_seconds: float,
    cpu_seconds: float,
) -> dict[str, Any]:
    ordered = protocol["orderings"][ordering]["ordered_ids"]
    return {
        "schema_version": RECEIPT_SCHEMA,
        "status": "PASS",
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "ordering": ordering,
        "arm": arm_name(modality, ordering),
        "ordered_training_record_ids": ordered,
        "ordered_training_record_ids_sha256": _json_sha256(ordered),
        "difficulty_map_sha256": _json_sha256(protocol["difficulty_map"]),
        "effective_training_arguments": _effective_arguments(protocol),
        "base_model": dict(protocol["base_model"]),
        "source_manifest_sha256": _json_sha256(source_manifest),
        "fresh_lora_init_sha256": _sha256(init_tensor),
        "fresh_lora_init_tensors": _safetensor_count(init_tensor),
        "final_checkpoint": str(final.relative_to(root)),
        **_final_fingerprints(final),
        "trainer_state_digest": _trainer_digest(state),
        "wall_seconds": wall_seconds,
        "cpu_seconds": cpu_seconds,
        "completed_at": time.time(),
    }


def _validate_receipt(
    root: Path,
    protocol: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    modality: str,
    ordering: str,
    source_manifest: Mapping[str, Any],
    final: Path,
    init_tensor: Path,
    state: Mapping[str, Any],
) -> None:
    expected = _receipt(
        root,
        protocol,
        modality=modality,
        ordering=ordering,
        source_manifest=source_manifest,
        final=final,
        init_tensor=init_tensor,
        state=state,
        wall_seconds=receipt.get("wall_seconds", -1),
        cpu_seconds=receipt.get("cpu_seconds", -1),
    )
    expected["completed_at"] = receipt.get("completed_at")
    if dict(receipt) != expected or any(
        not isinstance(receipt.get(key), (int, float)) or receipt[key] < 0
        for key in ("wall_seconds", "cpu_seconds", "completed_at")
    ):
        raise ValueError("curriculum completion receipt differs from retained artifacts")


def _git_head(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def _build_report(
    root: Path,
    protocol: Mapping[str, Any],
    *,
    modality: str,
    ordering: str,
    source_before: Mapping[str, Any],
    source_after: Mapping[str, Any],
    output: Path,
    state: Mapping[str, Any],
    runtime: Mapping[str, Any],
    recovered: bool,
) -> dict[str, Any]:
    final, receipt = output / "final", output / RECEIPT_FILE
    return {
        "schema_version": CELL_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "ordering": ordering,
        "arm": arm_name(modality, ordering),
        "base_model": dict(protocol["base_model"]),
        "source_manifest_before": dict(source_before),
        "source_manifest_after": dict(source_after),
        "source_unchanged": source_before == source_after,
        "source_manifest_sha256": _json_sha256(source_after),
        "training_record_ids": list(protocol["orderings"][ordering]["ordered_ids"]),
        "training_record_ids_sha256": protocol["orderings"][ordering]["sha256"],
        "records": protocol["training"]["records_per_cell"],
        "optimizer_updates": state["global_step"],
        "final_checkpoint": str(final.relative_to(root)),
        **_final_fingerprints(final),
        "fresh_lora_init": str((output / FRESH_INIT_FILE).relative_to(root)),
        "fresh_lora_init_sha256": _sha256(output / FRESH_INIT_FILE),
        "fresh_lora_init_tensors": _safetensor_count(output / FRESH_INIT_FILE),
        "completion_receipt": str(receipt.relative_to(root)),
        "completion_receipt_sha256": _sha256(receipt),
        "recovered_without_retrain": recovered,
        "runtime_head": runtime["runtime_head"],
        "cuda_visible_devices": runtime.get("cuda_visible_devices"),
        "master_port": runtime["master_port"],
        "elapsed_seconds": runtime["elapsed_seconds"],
    }


def _recover(root, protocol, context, modality, ordering, output, source_manifest):
    recovery_path, receipt_path = output / RECOVERY_FILE, output / RECEIPT_FILE
    if not receipt_path.is_file():
        raise ValueError("curriculum retained artifacts lack a completion receipt")
    recovery = read_json(recovery_path)
    if (
        recovery.get("schema_version") != RECOVERY_SCHEMA
        or recovery.get("protocol_id") != protocol["protocol_id"]
        or recovery.get("modality") != modality
        or recovery.get("ordering") != ordering
        or recovery.get("source_manifest_before") != source_manifest
    ):
        raise ValueError("curriculum recovery marker differs")
    state, final, init_tensor = read_json(output / "training_state.json"), output / "final", output / FRESH_INIT_FILE
    if state.get("global_step") != protocol["training"]["optimizer_updates"]:
        raise ValueError("curriculum retained Trainer state is incomplete")
    _validate_adapter_config(protocol, final / "adapter_config.json")
    _adapter_tensor_changes(init_tensor, final / "adapter_model.safetensors")
    receipt = read_json(receipt_path)
    _validate_receipt(
        root,
        protocol,
        receipt,
        modality=modality,
        ordering=ordering,
        source_manifest=source_manifest,
        final=final,
        init_tensor=init_tensor,
        state=state,
    )
    report = _build_report(
        root,
        protocol,
        modality=modality,
        ordering=ordering,
        source_before=source_manifest,
        source_after=source_manifest,
        output=output,
        state=state,
        runtime={
            "runtime_head": recovery["runtime_head"],
            "cuda_visible_devices": recovery.get("cuda_visible_devices"),
            "master_port": recovery["master_port"],
            "elapsed_seconds": receipt["wall_seconds"],
        },
        recovered=True,
    )
    write_json(output / "report.json", report)
    recovery_path.unlink()
    return report


def train_cell(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    modality: str,
    ordering: str,
    progress: Callable[..., None],
) -> dict[str, Any]:
    """Train one fresh adapter in exactly the protocol-frozen sequence."""
    from transformers import Trainer, TrainerCallback, TrainingArguments

    from .modality_view_preparation import frozen_processor
    from .visual_model import VisualCollator, load_training_model

    output = training_root(root, protocol, modality, ordering)
    if (output / "report.json").is_file():
        verify_training_cell(root, protocol, context, modality=modality, ordering=ordering)
        return read_json(output / "report.json")
    dataset = CurriculumDataset(context, protocol, modality, ordering)
    total = optimizer_updates(len(dataset), protocol["training"])
    if total != 16:
        raise ValueError("curriculum cell does not yield exactly 16 optimizer updates")
    source_before = _source_manifest(root, context["source_files"])
    if (output / "final").exists() or (output / "training_state.json").exists():
        return _recover(root, protocol, context, modality, ordering, output, source_before)
    output.mkdir(parents=True, exist_ok=True)
    recovery_path = output / RECOVERY_FILE
    recovery = {
        "schema_version": RECOVERY_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "ordering": ordering,
        "source_manifest_before": source_before,
        "runtime_head": _git_head(root),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": int(os.environ["MASTER_PORT"]),
    }
    write_json(recovery_path, recovery)
    model = load_training_model(_model_config(protocol))
    trainable = [name for name, parameter in model.named_parameters() if parameter.requires_grad]
    if not trainable or any("visual" in name.lower() for name in trainable):
        raise ValueError("curriculum fresh LoRA did not freeze vision")
    temporary = output / ".fresh-init"
    model.save_pretrained(str(temporary))
    shutil.copyfile(temporary / "adapter_model.safetensors", output / FRESH_INIT_FILE)
    shutil.rmtree(temporary)
    started, cpu_started = time.monotonic(), time.process_time()

    class FrozenTrainer(Trainer):
        def _get_train_sampler(self, train_dataset=None):
            return sequential_sampler(dataset)

    class Progress(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            progress(
                completed=state.global_step,
                total=total,
                eta_seconds=(time.monotonic() - started) / max(1, state.global_step) * (total - state.global_step),
            )
            return control

    trainer = FrozenTrainer(
        model=model,
        args=TrainingArguments(**training_arguments_kwargs(protocol, output)),
        train_dataset=dataset,
        data_collator=VisualCollator(frozen_processor().processor),
        callbacks=[Progress()],
    )
    trainer.train()
    if trainer.state.global_step != 16:
        raise RuntimeError("VALID_STOP: curriculum training ended before update 16")
    final = output / "final"
    trainer.save_model(str(final))
    trainer.state.save_to_json(str(output / "training_state.json"))
    if list(output.glob("checkpoint-*")):
        raise ValueError("curriculum retained a non-final checkpoint")
    source_after = _source_manifest(root, context["source_files"])
    if source_before != source_after:
        raise ValueError("curriculum source artifacts changed during training")
    _validate_adapter_config(protocol, final / "adapter_config.json")
    _final_fingerprints(final)
    _adapter_tensor_changes(output / FRESH_INIT_FILE, final / "adapter_model.safetensors")
    state = read_json(output / "training_state.json")
    receipt = _receipt(
        root,
        protocol,
        modality=modality,
        ordering=ordering,
        source_manifest=source_after,
        final=final,
        init_tensor=output / FRESH_INIT_FILE,
        state=state,
        wall_seconds=time.monotonic() - started,
        cpu_seconds=time.process_time() - cpu_started,
    )
    write_json(output / RECEIPT_FILE, receipt)
    _validate_receipt(
        root,
        protocol,
        receipt,
        modality=modality,
        ordering=ordering,
        source_manifest=source_after,
        final=final,
        init_tensor=output / FRESH_INIT_FILE,
        state=state,
    )
    report = _build_report(
        root,
        protocol,
        modality=modality,
        ordering=ordering,
        source_before=source_before,
        source_after=source_after,
        output=output,
        state=state,
        runtime={
            "runtime_head": recovery["runtime_head"],
            "cuda_visible_devices": recovery.get("cuda_visible_devices"),
            "master_port": recovery["master_port"],
            "elapsed_seconds": receipt["wall_seconds"],
        },
        recovered=False,
    )
    write_json(output / "report.json", report)
    recovery_path.unlink()
    return report


def verify_training_cell(
    root: Path, protocol: Mapping[str, Any], context: Mapping[str, Any], *, modality: str, ordering: str
) -> dict[str, Any]:
    output = training_root(root, protocol, modality, ordering)
    report = read_json(output / "report.json")
    ordered = protocol["orderings"][ordering]["ordered_ids"]
    if (
        report.get("schema_version") != CELL_SCHEMA
        or report.get("outcome") != "PASS"
        or report.get("protocol_id") != protocol["protocol_id"]
        or report.get("modality") != modality
        or report.get("ordering") != ordering
        or report.get("training_record_ids") != ordered
        or set(report.get("training_record_ids", [])) != set(protocol["source_record_ids"])
        or report.get("training_record_ids_sha256") != protocol["orderings"][ordering]["sha256"]
        or report.get("records") != 512
        or report.get("optimizer_updates") != 16
        or report.get("base_model") != protocol["base_model"]
        or report.get("source_unchanged") is not True
    ):
        raise ValueError("curriculum training report differs from frozen exposure")
    source = _source_manifest(root, context["source_files"])
    if report.get("source_manifest_before") != source or report.get("source_manifest_after") != source:
        raise ValueError("curriculum source artifact manifest changed")
    state, final, init_tensor = read_json(output / "training_state.json"), output / "final", output / FRESH_INIT_FILE
    if state.get("global_step") != 16 or list(output.glob("checkpoint-*")):
        raise ValueError("curriculum final-only Trainer state is invalid")
    _validate_adapter_config(protocol, final / "adapter_config.json")
    fingerprints = _final_fingerprints(final)
    if any(report.get(key) != value for key, value in fingerprints.items()):
        raise ValueError("curriculum final checkpoint fingerprint changed")
    changed, count = _adapter_tensor_changes(init_tensor, final / "adapter_model.safetensors")
    receipt_path = output / RECEIPT_FILE
    if report.get("completion_receipt_sha256") != _sha256(receipt_path):
        raise ValueError("curriculum completion receipt fingerprint changed")
    _validate_receipt(
        root,
        protocol,
        read_json(receipt_path),
        modality=modality,
        ordering=ordering,
        source_manifest=source,
        final=final,
        init_tensor=init_tensor,
        state=state,
    )
    return {
        "outcome": "PASS",
        "modality": modality,
        "ordering": ordering,
        "arm": arm_name(modality, ordering),
        "records": 512,
        "optimizer_updates": 16,
        "training_record_ids": ordered,
        "final_checkpoint": report["final_checkpoint"],
        **fingerprints,
        "changed_parameter_tensors": changed,
        "parameter_tensors": count,
        "fresh_lora_init_sha256": report["fresh_lora_init_sha256"],
        "fresh_lora_init_tensors": report["fresh_lora_init_tensors"],
        "recovered_without_retrain": report["recovered_without_retrain"],
    }


def verify_all_cells_same_set(protocol: Mapping[str, Any], cells: Sequence[Mapping[str, Any]]) -> None:
    expected = set(protocol["source_record_ids"])
    expected_cells = {(m, o) for m in protocol["modalities"] for o in ORDERINGS}
    if {(row.get("modality"), row.get("ordering")) for row in cells} != expected_cells or any(
        set(row.get("training_record_ids", [])) != expected
        or row.get("training_record_ids") != protocol["orderings"][row["ordering"]]["ordered_ids"]
        for row in cells
    ):
        raise ValueError("curriculum cells do not share the exact frozen record set and orders")
