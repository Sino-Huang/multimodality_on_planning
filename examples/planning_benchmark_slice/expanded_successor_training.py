"""Frozen release-001 SFT training for expanded successor prediction."""

from __future__ import annotations

import hashlib
import math
import os
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from torch.utils.data import Dataset, SequentialSampler

from .expanded_successor_collection import LABEL_SCHEMA, RELEASE_ID
from .expanded_successor_protocol import training_example
from .modality_corpus_replay import canonical
from .modality_view_preparation import write_json
from .scene_assets import read_json

CELL_SCHEMA = "expanded_successor_training_cell_v1"
MEMBERSHIP_SCHEMA = "expanded_successor_training_membership_v1"
CHANGE_REQUIREMENT = "all_adapter_parameter_tensors_changed_with_identical_key_set"
RECOVERY_SCHEMA = "expanded_successor_training_recovery_v1"
RECOVERY_FILE = ".training-recovery.json"
COMPLETION_RECEIPT_SCHEMA = "expanded_successor_training_completion_receipt_v1"
COMPLETION_RECEIPT_FILE = "completion-receipt.json"


def training_root(root: Path, protocol: Mapping[str, Any], modality: str) -> Path:
    return root / protocol["output_root"] / "training" / modality / protocol["training"]["arm"]


def labels_path(root: Path, protocol: Mapping[str, Any], modality: str) -> Path:
    return root / protocol["output_root"] / "dataset" / RELEASE_ID / modality / "labels.json.gz"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _file_fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"size": stat.st_size, "sha256": _sha256(path)}


def _checkpoint_manifest(checkpoint: Path) -> dict[str, dict[str, Any]]:
    if not checkpoint.is_dir():
        raise ValueError(f"checkpoint directory is missing: {checkpoint}")
    files = sorted(path for path in checkpoint.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"checkpoint directory contains no files: {checkpoint}")
    return {str(path.relative_to(checkpoint)): _file_fingerprint(path) for path in files}


def _final_checkpoint_fingerprints(final: Path) -> dict[str, str]:
    tensor = final / "adapter_model.safetensors"
    config = final / "adapter_config.json"
    if not (tensor.is_file() and config.is_file()):
        raise ValueError("successor final adapter checkpoint is incomplete")
    return {
        "final_checkpoint_sha256": _sha256(tensor),
        "final_adapter_config_sha256": _sha256(config),
    }


def _json_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def _effective_training_arguments(protocol: Mapping[str, Any]) -> dict[str, Any]:
    training = protocol["training"]
    return {
        "arm": training["arm"],
        "records_per_modality": training["records_per_modality"],
        "epochs": training["epochs"],
        "optimizer_updates": training["optimizer_updates"],
        "seed": training["seed"],
        "data_seed": training["seed"],
        "microbatch_size": training["microbatch_size"],
        "global_batch_size": training["global_batch_size"],
        "gradient_accumulation_steps": training["gradient_accumulation_steps"],
        "sampler": training["sampler"],
        "trainer_reshuffling": training["trainer_reshuffling"],
        "learning_rate": training["learning_rate"],
        "optimizer": training["optimizer"],
        "warmup_ratio": training["warmup_ratio"],
        "lr_scheduler": training["lr_scheduler"],
        "weight_decay": training["weight_decay"],
        "max_grad_norm": training["max_grad_norm"],
        "bf16": True,
        "gradient_checkpointing": True,
        "gradient_checkpointing_use_reentrant": False,
        "save_strategy": "no",
        "dataloader_num_workers": 0,
        "freeze_vision": training["freeze_vision"],
        "lora": {
            "rank": training["lora_rank"],
            "alpha": training["lora_alpha"],
            "dropout": training["lora_dropout"],
        },
        "final_checkpoint_only": True,
    }


def _trainer_state_digest(state: Mapping[str, Any]) -> dict[str, Any]:
    bound = {
        "global_step": state.get("global_step"),
        "log_history": state.get("log_history", []),
    }
    return {**bound, "sha256": _json_sha256(bound)}


def optimizer_updates(record_count: int, training: Mapping[str, Any]) -> int:
    return math.ceil(record_count / training["global_batch_size"]) * training["epochs"]


def training_arguments_kwargs(protocol: Mapping[str, Any], output: Path) -> dict[str, Any]:
    training = protocol["training"]
    return {
        "output_dir": str(output),
        "num_train_epochs": training["epochs"],
        "per_device_train_batch_size": training["microbatch_size"],
        "gradient_accumulation_steps": training["gradient_accumulation_steps"],
        "learning_rate": training["learning_rate"],
        "weight_decay": training["weight_decay"],
        "warmup_ratio": training["warmup_ratio"],
        "lr_scheduler_type": training["lr_scheduler"],
        "optim": training["optimizer"],
        "max_grad_norm": training["max_grad_norm"],
        "bf16": True,
        "gradient_checkpointing": True,
        "gradient_checkpointing_kwargs": {"use_reentrant": False},
        "seed": training["seed"],
        "data_seed": training["seed"],
        "logging_steps": 1,
        "save_strategy": "no",
        "report_to": [],
        "remove_unused_columns": False,
        "dataloader_num_workers": 0,
    }


def sequential_sampler(dataset: Any) -> SequentialSampler:
    return SequentialSampler(dataset)


def _release_report(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    path = root / protocol["output_root"] / "dataset" / RELEASE_ID / "report.json"
    report = read_json(path)
    if (
        report.get("schema_version") != "expanded_successor_release_v1"
        or report.get("outcome") != "PASS"
        or report.get("protocol_id") != protocol["protocol_id"]
        or report.get("release_id") != RELEASE_ID
        or report.get("membership_id") is None
        or report.get("total_interactions") != len(protocol["modalities"])
        * protocol["training"]["records_per_modality"]
        or report.get("byte_identical_regeneration_verified") is not True
    ):
        raise ValueError("verified successor release-001 report is incomplete")
    return report


def prepare_membership(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    modality: str,
) -> tuple[Path, dict[str, Any]]:
    """Load and bind the immutable teacher labels in frozen source-record order."""

    if modality not in protocol["modalities"]:
        raise ValueError("successor training modality is outside the frozen protocol")
    report = _release_report(root, protocol)
    path = labels_path(root, protocol, modality)
    artifact = report.get("artifacts", {}).get(modality, {}).get("labels", {})
    if (
        artifact.get("path") != str(path.relative_to(root))
        or artifact.get("records") != protocol["training"]["records_per_modality"]
        or artifact.get("sha256") != _sha256(path)
    ):
        raise ValueError("successor teacher-label artifact differs from release-001")
    payload = read_json(path)
    records = payload.get("records", [])
    expected_ids = protocol["source_record_ids"]
    if (
        payload.get("schema_version") != "expanded_successor_training_set_v1"
        or payload.get("protocol_id") != protocol["protocol_id"]
        or payload.get("release_id") != RELEASE_ID
        or payload.get("modality") != modality
        or payload.get("membership_id") != context["membership_id"]
        or context["membership_id"] != report["membership_id"]
        or len(records) != protocol["training"]["records_per_modality"]
        or [row.get("record_id") for row in records] != expected_ids
    ):
        raise ValueError("successor teacher-label membership differs from the frozen cell")
    if len(context["records"]) != len(records) or len(context["contracts"]) != len(records):
        raise ValueError("successor live context does not cover the teacher-label membership")
    for index, (label, source, contract) in enumerate(
        zip(records, context["records"], context["contracts"], strict=True)
    ):
        if (
            label.get("schema_version") != LABEL_SCHEMA
            or label.get("collection_index") != index
            or label.get("modality") != modality
            or label.get("split") != "train"
            or label.get("record_id") != source.get("record_id")
            or source.get("record_id") != contract.get("record_id")
            or label.get("task_id") != source.get("task_id")
            or label.get("model_input") != contract.get("model_input")
            or label.get("query") != contract.get("query")
            or label.get("source_state") != contract.get("source_state")
            or label.get("source_path") != contract.get("source_path")
            or label.get("target") != contract.get("target")
        ):
            raise ValueError(f"successor teacher label {index} differs from the live authoritative contract")
    membership = {
        "schema_version": MEMBERSHIP_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "release_id": RELEASE_ID,
        "membership_id": payload["membership_id"],
        "modality": modality,
        "arm": protocol["training"]["arm"],
        "record_count": len(records),
        "optimizer_updates": protocol["training"]["optimizer_updates"],
        "training_seed": protocol["training"]["seed"],
        "records": records,
        "labels_sha256": artifact["sha256"],
    }
    return path, membership


class SuccessorTrainingDataset(Dataset):
    """Render release labels through the frozen live successor serializer."""

    def __init__(
        self,
        root: Path,
        protocol: Mapping[str, Any],
        context: Mapping[str, Any],
        views: Any,
        membership: Mapping[str, Any],
        *,
        pixels: bool = True,
    ) -> None:
        self.root = root
        self.protocol = dict(protocol)
        self.context = dict(context)
        self.views = views
        self.records = list(membership["records"])
        self.modality = membership["modality"]
        self.pixels = pixels

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        label = self.records[index]
        example = training_example(
            self.root,
            self.protocol,
            self.context,
            self.views,
            index,
            self.modality,
            pixels=self.pixels,
        )
        contract = self.context["contracts"][index]
        expected_binding = label["view"]["binding"]
        if (
            label["record_id"] != self.protocol["source_record_ids"][index]
            or contract["model_input"] != label["model_input"]
            or contract["target"] != label["target"]
            or example.get("binding") != expected_binding
            or example.get("messages", [])[-1:]
            != [{"role": "assistant", "content": canonical(label["target"])}]
        ):
            raise ValueError("successor live SFT example differs from its verified teacher label")
        return example


def _validate_adapter_contract(
    protocol: Mapping[str, Any], study: Mapping[str, Any], adapter_config: Mapping[str, Any]
) -> None:
    training = protocol["training"]
    study_training = study["training"]
    if (
        study.get("training_seed") != training["seed"]
        or study_training.get("lora_rank") != training["lora_rank"]
        or study_training.get("lora_alpha") != training["lora_alpha"]
        or study_training.get("lora_dropout") != training["lora_dropout"]
        or study_training.get("freeze_vision") is not training["freeze_vision"]
        or adapter_config.get("r") != training["lora_rank"]
        or adapter_config.get("lora_alpha") != training["lora_alpha"]
        or adapter_config.get("lora_dropout") != training["lora_dropout"]
        or adapter_config.get("exclude_modules") != ".*visual.*"
        or adapter_config.get("peft_type") != "LORA"
    ):
        raise ValueError("successor LoRA/frozen-vision contract differs from the source adapter")


def _git_head(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def _adapter_tensor_changes(source_tensor: Path, final_tensor: Path) -> tuple[int, int]:
    from safetensors import safe_open

    changed = 0
    with safe_open(source_tensor, framework="pt", device="cpu") as before, safe_open(
        final_tensor, framework="pt", device="cpu"
    ) as after:
        if set(before.keys()) != set(after.keys()):
            raise ValueError("successor adapter parameter membership changed")
        keys = list(before.keys())
        for key in keys:
            changed += int(not before.get_tensor(key).equal(after.get_tensor(key)))
    if not keys or changed != len(keys):
        raise ValueError("successor training did not change every adapter parameter tensor")
    return changed, len(keys)


def _build_completion_receipt(
    root: Path,
    protocol: Mapping[str, Any],
    membership: Mapping[str, Any],
    *,
    modality: str,
    source: Path,
    source_manifest: Mapping[str, Any],
    final: Path,
    state: Mapping[str, Any],
    wall_seconds: float,
    cpu_seconds: float,
) -> dict[str, Any]:
    return {
        "schema_version": COMPLETION_RECEIPT_SCHEMA,
        "status": "PASS",
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "arm": protocol["training"]["arm"],
        "membership_id": membership["membership_id"],
        "teacher_labels_sha256": membership["labels_sha256"],
        "effective_training_arguments": _effective_training_arguments(protocol),
        "source_checkpoint": str(source.relative_to(root)),
        "source_checkpoint_manifest_sha256": _json_sha256(source_manifest),
        "final_checkpoint": str(final.relative_to(root)),
        **_final_checkpoint_fingerprints(final),
        "trainer_state_digest": _trainer_state_digest(state),
        "wall_seconds": wall_seconds,
        "cpu_seconds": cpu_seconds,
        "completed_at": time.time(),
    }


def _validate_completion_receipt(
    root: Path,
    protocol: Mapping[str, Any],
    membership: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    modality: str,
    source: Path,
    source_manifest: Mapping[str, Any],
    final: Path,
    state: Mapping[str, Any],
) -> None:
    fingerprints = _final_checkpoint_fingerprints(final)
    expected = {
        "schema_version": COMPLETION_RECEIPT_SCHEMA,
        "status": "PASS",
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "arm": protocol["training"]["arm"],
        "membership_id": membership["membership_id"],
        "teacher_labels_sha256": membership["labels_sha256"],
        "effective_training_arguments": _effective_training_arguments(protocol),
        "source_checkpoint": str(source.relative_to(root)),
        "source_checkpoint_manifest_sha256": _json_sha256(source_manifest),
        "final_checkpoint": str(final.relative_to(root)),
        **fingerprints,
        "trainer_state_digest": _trainer_state_digest(state),
    }
    timing_fields = {"wall_seconds", "cpu_seconds", "completed_at"}
    if set(receipt) != set(expected) | timing_fields or any(
        receipt.get(key) != value for key, value in expected.items()
    ):
        raise ValueError("successor completion receipt differs from retained training artifacts")
    for key in timing_fields:
        value = receipt.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError("successor completion receipt has invalid timing evidence")


def _build_cell_report(
    root: Path,
    protocol: Mapping[str, Any],
    membership: Mapping[str, Any],
    *,
    modality: str,
    labels: Path,
    source: Path,
    source_before: Mapping[str, Any],
    source_after: Mapping[str, Any],
    final: Path,
    state: Mapping[str, Any],
    runtime: Mapping[str, Any],
    completion_receipt: Path,
    recovered_without_retrain: bool,
) -> dict[str, Any]:
    training = protocol["training"]
    fingerprints = _final_checkpoint_fingerprints(final)
    return {
        "schema_version": CELL_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "arm": training["arm"],
        "source_checkpoint": str(source.relative_to(root)),
        "source_checkpoint_manifest_before": dict(source_before),
        "source_checkpoint_manifest_after": dict(source_after),
        "source_checkpoint_unchanged": source_before == source_after,
        "teacher_labels": str(labels.relative_to(root)),
        "teacher_labels_sha256": membership["labels_sha256"],
        "membership_id": membership["membership_id"],
        "training_record_ids": [row["record_id"] for row in membership["records"]],
        "records": len(membership["records"]),
        "epochs": training["epochs"],
        "optimizer_updates": state["global_step"],
        "seed": training["seed"],
        "data_seed": training["seed"],
        "sampler": training["sampler"],
        "trainer_reshuffling": training["trainer_reshuffling"],
        "freeze_vision": training["freeze_vision"],
        "lora": {
            "rank": training["lora_rank"],
            "alpha": training["lora_alpha"],
            "dropout": training["lora_dropout"],
        },
        "final_checkpoint": str(final.relative_to(root)),
        **fingerprints,
        "final_checkpoint_only": True,
        "tensor_change_requirement": CHANGE_REQUIREMENT,
        "completion_receipt": str(completion_receipt.relative_to(root)),
        "completion_receipt_sha256": _sha256(completion_receipt),
        "recovered_without_retrain": recovered_without_retrain,
        "runtime_head": runtime["runtime_head"],
        "cuda_visible_devices": runtime.get("cuda_visible_devices"),
        "master_port": runtime["master_port"],
        "elapsed_seconds": runtime["elapsed_seconds"],
        "loss_history": [row for row in state.get("log_history", []) if "loss" in row],
    }


def _recovery_metadata(
    root: Path,
    protocol: Mapping[str, Any],
    *,
    modality: str,
    source: Path,
    source_before: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": RECOVERY_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "source_checkpoint": str(source.relative_to(root)),
        "source_checkpoint_manifest_before": dict(source_before),
        "runtime_head": _git_head(root),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": int(os.environ["MASTER_PORT"]),
        "started_at": time.time(),
    }


def _recover_cell_report(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    membership: Mapping[str, Any],
    *,
    modality: str,
    labels: Path,
    source: Path,
    output: Path,
) -> dict[str, Any]:
    recovery_path = output / RECOVERY_FILE
    recovery = read_json(recovery_path)
    if (
        recovery.get("schema_version") != RECOVERY_SCHEMA
        or recovery.get("protocol_id") != protocol["protocol_id"]
        or recovery.get("modality") != modality
        or recovery.get("source_checkpoint") != str(source.relative_to(root))
    ):
        raise ValueError("successor crash-recovery metadata differs from the frozen cell")
    training = protocol["training"]
    state = read_json(output / "training_state.json")
    if state.get("global_step") != training["optimizer_updates"]:
        raise ValueError("successor retained Trainer state does not contain exactly 16 updates")
    source_before = recovery.get("source_checkpoint_manifest_before")
    source_after = _checkpoint_manifest(source)
    if not isinstance(source_before, dict) or source_before != source_after:
        raise ValueError("successor source checkpoint changed before crash recovery")
    final = output / "final"
    receipt_path = output / COMPLETION_RECEIPT_FILE
    if not receipt_path.is_file():
        raise ValueError("successor retained artifacts lack a post-training completion receipt")
    receipt = read_json(receipt_path)
    _validate_completion_receipt(
        root,
        protocol,
        membership,
        receipt,
        modality=modality,
        source=source,
        source_manifest=source_after,
        final=final,
        state=state,
    )
    _validate_adapter_contract(protocol, context["study"], read_json(final / "adapter_config.json"))
    _adapter_tensor_changes(source / "adapter_model.safetensors", final / "adapter_model.safetensors")
    if list(output.glob("checkpoint-*")):
        raise ValueError("successor crash recovery found a non-final checkpoint")
    report = _build_cell_report(
        root,
        protocol,
        membership,
        modality=modality,
        labels=labels,
        source=source,
        source_before=source_before,
        source_after=source_after,
        final=final,
        state=state,
        runtime={
            "runtime_head": recovery.get("runtime_head"),
            "cuda_visible_devices": recovery.get("cuda_visible_devices"),
            "master_port": recovery.get("master_port"),
            "elapsed_seconds": receipt["wall_seconds"],
        },
        completion_receipt=receipt_path,
        recovered_without_retrain=True,
    )
    if report["source_checkpoint_unchanged"] is not True:
        raise ValueError("successor source checkpoint changed during recovered training")
    write_json(output / "report.json", report)
    recovery_path.unlink()
    return report


def train_cell(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    views: Any,
    *,
    modality: str,
    progress: Callable[..., None],
) -> dict[str, Any]:
    """Run one frozen 512-record, one-epoch, 16-update successor continuation."""

    output = training_root(root, protocol, modality)
    report_path = output / "report.json"
    if report_path.is_file():
        verify_training_cell(root, protocol, context, views, modality=modality)
        recovery_path = output / RECOVERY_FILE
        if recovery_path.exists():
            recovery_path.unlink()
        return read_json(report_path)
    path, membership = prepare_membership(root, protocol, context, modality=modality)
    training = protocol["training"]
    total = optimizer_updates(len(membership["records"]), training)
    if total != training["optimizer_updates"]:
        raise ValueError("successor training membership does not yield exactly 16 updates")
    source = root / protocol["starting_checkpoints"][modality]
    source_tensor = source / "adapter_model.safetensors"
    source_before = _checkpoint_manifest(source)
    adapter_config = read_json(source / "adapter_config.json")
    _validate_adapter_contract(protocol, context["study"], adapter_config)
    final = output / "final"
    state_path = output / "training_state.json"
    if final.exists() or state_path.exists():
        if not (final.is_dir() and state_path.is_file()):
            raise ValueError("successor retained training artifacts are incomplete")
        report = _recover_cell_report(
            root,
            protocol,
            context,
            membership,
            modality=modality,
            labels=path,
            source=source,
            output=output,
        )
        verify_training_cell(root, protocol, context, views, modality=modality)
        return report

    from transformers import Trainer, TrainerCallback, TrainingArguments

    from .modality_view_preparation import frozen_processor
    from .visual_model import VisualCollator, load_training_model

    dataset = SuccessorTrainingDataset(root, protocol, context, views, membership)
    started = time.monotonic()
    cpu_started = time.process_time()

    class FrozenTrainer(Trainer):
        def _get_train_sampler(self, train_dataset=None):
            return sequential_sampler(dataset)

    class Progress(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            elapsed = time.monotonic() - started
            progress(
                completed=state.global_step,
                total=total,
                eta_seconds=elapsed / state.global_step * (total - state.global_step),
            )
            return control

    output.mkdir(parents=True, exist_ok=True)
    recovery_path = output / RECOVERY_FILE
    receipt_path = output / COMPLETION_RECEIPT_FILE
    if receipt_path.exists():
        raise ValueError("successor completion receipt exists without retained final training artifacts")
    if recovery_path.is_file():
        recovery = read_json(recovery_path)
        if recovery.get("source_checkpoint_manifest_before") != source_before:
            raise ValueError("successor source checkpoint changed since interrupted training")
    else:
        recovery = _recovery_metadata(
            root,
            protocol,
            modality=modality,
            source=source,
            source_before=source_before,
        )
        write_json(recovery_path, recovery)
    model = load_training_model(context["study"], str(source))
    trainable = [name for name, parameter in model.named_parameters() if parameter.requires_grad]
    if not trainable or any("visual" in name.lower() for name in trainable):
        raise ValueError("successor training did not keep the vision tower frozen")
    arguments = TrainingArguments(**training_arguments_kwargs(protocol, output))
    trainer = FrozenTrainer(
        model=model,
        args=arguments,
        train_dataset=dataset,
        data_collator=VisualCollator(frozen_processor().processor),
        callbacks=[Progress()],
    )
    trainer.train()
    if trainer.state.global_step != total:
        raise RuntimeError("VALID_STOP: successor training ended before its final update")
    trainer.save_model(str(final))
    trainer.state.save_to_json(str(state_path))
    if list(output.glob("checkpoint-*")):
        raise ValueError("successor training retained a non-final checkpoint")
    source_after = _checkpoint_manifest(source)
    if source_before != source_after:
        raise ValueError("source successor checkpoint changed during continuation")
    final_config = read_json(final / "adapter_config.json")
    _validate_adapter_contract(protocol, context["study"], final_config)
    final_fingerprints = _final_checkpoint_fingerprints(final)
    _adapter_tensor_changes(source_tensor, final / "adapter_model.safetensors")
    state = read_json(state_path)
    if state.get("global_step") != total:
        raise ValueError("successor retained Trainer state differs from the completed run")
    receipt = _build_completion_receipt(
        root,
        protocol,
        membership,
        modality=modality,
        source=source,
        source_manifest=source_after,
        final=final,
        state=state,
        wall_seconds=time.monotonic() - started,
        cpu_seconds=time.process_time() - cpu_started,
    )
    write_json(receipt_path, receipt)
    _validate_completion_receipt(
        root,
        protocol,
        membership,
        receipt,
        modality=modality,
        source=source,
        source_manifest=source_after,
        final=final,
        state=state,
    )
    report = _build_cell_report(
        root,
        protocol,
        membership,
        modality=modality,
        labels=path,
        source=source,
        source_before=source_before,
        source_after=source_after,
        final=final,
        state=state,
        runtime={
            "runtime_head": recovery["runtime_head"],
            "cuda_visible_devices": recovery.get("cuda_visible_devices"),
            "master_port": recovery["master_port"],
            "elapsed_seconds": receipt["wall_seconds"],
        },
        completion_receipt=receipt_path,
        recovered_without_retrain=False,
    )
    if any(report[key] != value for key, value in final_fingerprints.items()):
        raise ValueError("successor final checkpoint fingerprint changed before report publication")
    write_json(report_path, report)
    recovery_path.unlink()
    return report


def verify_training_cell(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    views: Any,
    *,
    modality: str,
) -> dict[str, Any]:
    """CPU-only audit of release exposure, lineage and every adapter tensor update."""

    output = training_root(root, protocol, modality)
    report = read_json(output / "report.json")
    path, membership = prepare_membership(root, protocol, context, modality=modality)
    dataset = SuccessorTrainingDataset(root, protocol, context, views, membership, pixels=False)
    for index in range(len(dataset)):
        example = dataset[index]
        for image in example.get("images", []):
            close = getattr(image, "close", None)
            if close is not None:
                close()
    training = protocol["training"]
    expected_source = protocol["starting_checkpoints"][modality]
    receipt_path = output / COMPLETION_RECEIPT_FILE
    if not receipt_path.is_file():
        raise ValueError("successor training cell lacks a post-training completion receipt")
    expected = {
        "schema_version": CELL_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "arm": training["arm"],
        "source_checkpoint": expected_source,
        "source_checkpoint_unchanged": True,
        "teacher_labels": str(path.relative_to(root)),
        "teacher_labels_sha256": membership["labels_sha256"],
        "membership_id": membership["membership_id"],
        "training_record_ids": protocol["source_record_ids"],
        "records": training["records_per_modality"],
        "epochs": training["epochs"],
        "optimizer_updates": training["optimizer_updates"],
        "seed": training["seed"],
        "data_seed": training["seed"],
        "sampler": training["sampler"],
        "trainer_reshuffling": False,
        "freeze_vision": True,
        "lora": {
            "rank": training["lora_rank"],
            "alpha": training["lora_alpha"],
            "dropout": training["lora_dropout"],
        },
        "final_checkpoint": str(output.relative_to(root) / "final"),
        "final_checkpoint_only": True,
        "tensor_change_requirement": CHANGE_REQUIREMENT,
        "completion_receipt": str(receipt_path.relative_to(root)),
        "completion_receipt_sha256": _sha256(receipt_path),
    }
    if any(report.get(key) != value for key, value in expected.items()):
        raise ValueError("successor training report differs from frozen lineage or exposure")
    if not isinstance(report.get("recovered_without_retrain"), bool):
        raise ValueError("successor training report has an invalid recovery marker")
    source = root / expected_source
    source_tensor = source / "adapter_model.safetensors"
    actual_source = _checkpoint_manifest(source)
    if (
        report.get("source_checkpoint_manifest_before")
        != report.get("source_checkpoint_manifest_after")
        or report.get("source_checkpoint_manifest_after") != actual_source
    ):
        raise ValueError("successor source checkpoint manifest changed")
    state = read_json(output / "training_state.json")
    if state.get("global_step") != training["optimizer_updates"]:
        raise ValueError("successor Trainer state does not contain exactly 16 updates")
    final = root / report["final_checkpoint"]
    final_tensor = final / "adapter_model.safetensors"
    fingerprints = _final_checkpoint_fingerprints(final)
    if any(report.get(key) != value for key, value in fingerprints.items()):
        raise ValueError("successor final checkpoint fingerprint changed")
    _validate_completion_receipt(
        root,
        protocol,
        membership,
        read_json(receipt_path),
        modality=modality,
        source=source,
        source_manifest=actual_source,
        final=final,
        state=state,
    )
    if list(output.glob("checkpoint-*")):
        raise ValueError("successor training retained a non-final checkpoint")
    _validate_adapter_contract(protocol, context["study"], read_json(final / "adapter_config.json"))
    changed, parameter_tensors = _adapter_tensor_changes(source_tensor, final_tensor)
    return {
        "outcome": "PASS",
        "modality": modality,
        "arm": training["arm"],
        "records": report["records"],
        "optimizer_updates": report["optimizer_updates"],
        "source_checkpoint": expected_source,
        "final_checkpoint": report["final_checkpoint"],
        **fingerprints,
        "changed_parameter_tensors": changed,
        "parameter_tensors": parameter_tensors,
        "tensor_change_requirement": CHANGE_REQUIREMENT,
        "completion_receipt": report["completion_receipt"],
        "completion_receipt_sha256": report["completion_receipt_sha256"],
        "recovered_without_retrain": report["recovered_without_retrain"],
    }
