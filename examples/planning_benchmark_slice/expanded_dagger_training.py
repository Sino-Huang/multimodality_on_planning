"""Frozen-membership training for the expanded DAgger comparison."""

from __future__ import annotations

import math
import os
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from torch.utils.data import Dataset

from .expanded_dagger import aggregate_update
from .expanded_dagger_collection import _episode_paths, cell_root
from .modality_corpus_replay import canonical
from .modality_view_preparation import write_json
from .scene_assets import read_json
from .visual_episode import VisualTaskViews


def training_root(root: Path, protocol: Mapping[str, Any], modality: str, arm: str, iteration: int) -> Path:
    return root / protocol["output_root"] / "training" / modality / arm.replace("_", "-") / f"iteration-{iteration}"


def training_checkpoint(protocol: Mapping[str, Any], modality: str, arm: str, iteration: int) -> str:
    if arm not in protocol["training"]["arms"] or iteration not in protocol["iterations"]:
        raise ValueError("DAgger training cell is outside the frozen protocol")
    if iteration == 1:
        return protocol["starting_checkpoints"][modality]
    key = f"{arm}_iteration_{iteration - 1}"
    return protocol["checkpoint_lineage"][key].format(modality=modality)


def membership_path(root: Path, protocol: Mapping[str, Any], modality: str, arm: str, iteration: int) -> Path:
    if arm == "dagger":
        return cell_root(root, protocol, modality, iteration) / "aggregation.json.gz"
    return (
        root
        / protocol["output_root"]
        / "training"
        / "membership"
        / modality
        / "continued-sft"
        / f"iteration-{iteration}.json.gz"
    )


def prepare_membership(
    root: Path,
    protocol: Mapping[str, Any],
    source_records: list[dict[str, Any]],
    *,
    modality: str,
    arm: str,
    iteration: int,
    target_token_counter: Callable[[Mapping[str, Any]], int],
) -> tuple[Path, dict[str, Any]]:
    path = membership_path(root, protocol, modality, arm, iteration)
    if arm == "dagger":
        if not path.is_file():
            raise ValueError("verified DAgger aggregation is missing")
        membership = read_json(path)
    else:
        membership = aggregate_update(
            source_records,
            [],
            protocol,
            modality=modality,
            through_iteration=iteration,
            arm="continued_sft",
            target_token_counter=target_token_counter,
        )
        if path.exists() and read_json(path) != membership:
            raise ValueError("retained continued-SFT membership differs")
        write_json(path, membership)
    if (
        membership.get("protocol_id") != protocol["protocol_id"]
        or membership.get("arm") != arm
        or membership.get("modality") != modality
        or membership.get("through_iteration") != iteration
        or membership.get("record_count") != protocol["training"]["records_per_update"]
        or membership.get("optimizer_updates") != protocol["training"]["optimizer_updates"]
        or membership.get("training_seed") != protocol["training"]["seed"]
        or any(row.get("split") != "train" for row in membership.get("records", []))
    ):
        raise ValueError("DAgger training membership differs from the frozen cell")
    return path, membership


class DaggerTrainingDataset(Dataset):
    """Render the persisted aggregate membership through the live serializer."""

    def __init__(
        self,
        root: Path,
        protocol: Mapping[str, Any],
        context: Mapping[str, Any],
        membership: Mapping[str, Any],
        *,
        endpoint: str,
    ) -> None:
        self.root = root
        self.protocol = protocol
        self.corpus = context["corpus"]
        self.records = list(membership["records"])
        self.modality = membership["modality"]
        self.endpoint = endpoint
        self.source = {row["record_id"]: row for row in context["source_records"]}
        self.tasks: dict[str, dict[str, Any]] = {}
        for row in context["source_records"]:
            self.tasks.setdefault(row["task_id"], row)
        self.views: dict[tuple[int, str], VisualTaskViews] = {}

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        record = self.records[index]
        if record["source_kind"] == "original_sft":
            example = self.corpus.training_example(self.source[record["record_id"]], self.modality)
        else:
            parts = record["record_id"].split(":")
            if len(parts) != 4 or not parts[2].startswith("iteration-"):
                raise ValueError("DAgger correction record identity is malformed")
            iteration = int(parts[2].removeprefix("iteration-"))
            task_id = record["task_id"]
            key = (iteration, task_id)
            if key not in self.views:
                _, _, view_output = _episode_paths(
                    cell_root(self.root, self.protocol, self.modality, iteration), task_id
                )
                row = self.tasks[task_id]
                self.views[key] = VisualTaskViews(
                    self.root,
                    row,
                    row["view_manifest"],
                    view_output,
                    self.endpoint,
                    read_only=True,
                    scene_views=self.protocol["views"]["source"],
                )
            example = self.views[key].observe(record["input"], "bfs", modality=self.modality)
            if example["binding"] != record["view"]:
                raise ValueError("DAgger correction training view differs from collection")
            example["messages"].append({"role": "assistant", "content": canonical(record["target"])})
        return example


def _git_head(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def train_cell(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    modality: str,
    arm: str,
    iteration: int,
    endpoint: str,
    progress: Callable[..., None],
) -> dict[str, Any]:
    """Run one frozen 512-record, one-epoch, 16-update adapter continuation."""
    from torch.utils.data import SequentialSampler
    from transformers import Trainer, TrainerCallback, TrainingArguments

    from .expanded_dagger_collection import _target_token_count
    from .modality_view_preparation import frozen_processor
    from .visual_model import VisualCollator, load_training_model

    output = training_root(root, protocol, modality, arm, iteration)
    report_path = output / "report.json"
    if report_path.is_file():
        return read_json(report_path)
    path, membership = prepare_membership(
        root,
        protocol,
        context["source_records"],
        modality=modality,
        arm=arm,
        iteration=iteration,
        target_token_counter=_target_token_count,
    )
    dataset = DaggerTrainingDataset(root, protocol, context, membership, endpoint=endpoint)
    training = protocol["training"]
    total = math.ceil(len(dataset) / training["global_batch_size"]) * training["epochs"]
    if total != training["optimizer_updates"]:
        raise ValueError("DAgger training membership does not yield exactly 16 updates")
    source = root / training_checkpoint(protocol, modality, arm, iteration)
    source_tensor = source / "adapter_model.safetensors"
    source_before = {"size": source_tensor.stat().st_size, "mtime_ns": source_tensor.stat().st_mtime_ns}
    started = time.monotonic()

    class FrozenTrainer(Trainer):
        def _get_train_sampler(self, train_dataset=None):
            return SequentialSampler(dataset)

    class Progress(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            progress(
                completed=state.global_step,
                total=total,
                eta_seconds=(time.monotonic() - started) / state.global_step * (total - state.global_step),
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
        seed=training["seed"],
        data_seed=training["seed"],
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
        raise RuntimeError("VALID_STOP: DAgger training ended before its final update")
    final = output / "final"
    trainer.save_model(str(final))
    trainer.state.save_to_json(str(output / "training_state.json"))
    source_after = {"size": source_tensor.stat().st_size, "mtime_ns": source_tensor.stat().st_mtime_ns}
    report = {
        "schema_version": "expanded_dagger_training_cell_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "arm": arm,
        "iteration": iteration,
        "source_checkpoint": str(source.relative_to(root)),
        "source_checkpoint_unchanged": source_before == source_after,
        "membership": str(path.relative_to(root)),
        "training_record_ids": [row["record_id"] for row in membership["records"]],
        "records": len(dataset),
        "epochs": training["epochs"],
        "optimizer_updates": trainer.state.global_step,
        "seed": training["seed"],
        "final_checkpoint": str(final.relative_to(root)),
        "runtime_head": _git_head(root),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": int(os.environ["MASTER_PORT"]),
        "elapsed_seconds": time.monotonic() - started,
        "loss_history": [row for row in trainer.state.log_history if "loss" in row],
    }
    write_json(report_path, report)
    return report


def verify_training_cell(
    root: Path,
    protocol: Mapping[str, Any],
    source_records: list[dict[str, Any]],
    *,
    modality: str,
    arm: str,
    iteration: int,
) -> dict[str, Any]:
    """Verify lineage, exposure and a real adapter-weight update without a GPU."""
    from safetensors import safe_open

    from .expanded_dagger_collection import _target_token_count

    output = training_root(root, protocol, modality, arm, iteration)
    report = read_json(output / "report.json")
    path, membership = prepare_membership(
        root,
        protocol,
        source_records,
        modality=modality,
        arm=arm,
        iteration=iteration,
        target_token_counter=_target_token_count,
    )
    expected_source = training_checkpoint(protocol, modality, arm, iteration)
    final = root / report["final_checkpoint"]
    expected = {
        "schema_version": "expanded_dagger_training_cell_v1",
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "arm": arm,
        "iteration": iteration,
        "source_checkpoint": expected_source,
        "source_checkpoint_unchanged": True,
        "membership": str(path.relative_to(root)),
        "training_record_ids": [row["record_id"] for row in membership["records"]],
        "records": protocol["training"]["records_per_update"],
        "epochs": protocol["training"]["epochs"],
        "optimizer_updates": protocol["training"]["optimizer_updates"],
        "seed": protocol["training"]["seed"],
        "final_checkpoint": str(output.relative_to(root) / "final"),
    }
    if any(report.get(key) != value for key, value in expected.items()):
        raise ValueError("DAgger training report differs from frozen lineage or exposure")
    state = read_json(output / "training_state.json")
    if state.get("global_step") != protocol["training"]["optimizer_updates"]:
        raise ValueError("DAgger Trainer state does not contain exactly 16 updates")
    source_tensor = root / expected_source / "adapter_model.safetensors"
    final_tensor = final / "adapter_model.safetensors"
    if not (final_tensor.is_file() and (final / "adapter_config.json").is_file()):
        raise ValueError("DAgger final adapter checkpoint is incomplete")
    changed = 0
    with safe_open(source_tensor, framework="pt", device="cpu") as before, safe_open(
        final_tensor, framework="pt", device="cpu"
    ) as after:
        if set(before.keys()) != set(after.keys()):
            raise ValueError("DAgger adapter parameter membership changed")
        keys = list(before.keys())
        for key in keys:
            changed += int(not before.get_tensor(key).equal(after.get_tensor(key)))
    if not changed:
        raise ValueError("DAgger adapter weights did not change")
    return {
        "outcome": "PASS",
        "modality": modality,
        "arm": arm,
        "iteration": iteration,
        "records": report["records"],
        "optimizer_updates": report["optimizer_updates"],
        "source_checkpoint": expected_source,
        "final_checkpoint": report["final_checkpoint"],
        "changed_parameter_tensors": changed,
        "parameter_tensors": len(keys),
    }
