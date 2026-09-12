"""Frozen Qwen visual batching and on-demand supervised examples."""

from __future__ import annotations

import math
import time
from typing import Any

from torch.utils.data import Dataset

from .modality_corpus import ModalityCorpus
from .modality_view_preparation import frozen_processor
from .qwen_text_policy import BatchedPolicyAdapter


class VisualPolicy(BatchedPolicyAdapter):
    """One float32 backbone per GPU; no cross-episode or cross-adapter output cache."""

    stop_at: float = float("inf")

    def generate(self, examples, adapter_id=None, *, force_full_output=False):
        if time.monotonic() >= getattr(self, "stop_at", float("inf")):
            raise RuntimeError("VALID_STOP: no new model calls after cutoff")
        lengths = [frozen_processor().count(e["messages"]) for e in examples]
        if (
            len(examples) > self.max_batch_size
            or max(lengths) * len(lengths) > self.max_batch_input_tokens
            or max(lengths) + self.max_new_tokens > self.max_context_tokens
        ):
            raise RuntimeError("VALID_STOP: visual batch exceeds frozen token limits")
        texts = [
            self.processor.apply_chat_template(e["messages"], tokenize=False, add_generation_prompt=True)
            for e in examples
        ]
        images = [image for example in examples for image in example["images"]]
        inputs = self.processor(text=texts, images=images or None, padding=True, return_tensors="pt").to(self.device)
        width = inputs["input_ids"].shape[1]
        if width != max(lengths):
            raise ValueError("actual visual processor differs from complete input measurement")
        if time.monotonic() >= self.stop_at:
            raise RuntimeError("VALID_STOP: cutoff before model generation")
        with self._adapter_context(adapter_id), self._torch.inference_mode():
            ids = self.model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=self.max_new_tokens,
                use_cache=True,
                min_new_tokens=self.max_new_tokens if force_full_output else 0,
            )
        return [
            s.strip()
            for s in self.processor.batch_decode(
                ids[:, width:], skip_special_tokens=True, clean_up_tokenization_spaces=False
            )
        ]


class VisualDataset(Dataset):
    def __init__(self, root, report, algorithm, split="train", record_ids=None, modality="visual-state"):
        self.corpus = ModalityCorpus(root, report)
        self.modality = modality
        self.records = list(self.corpus.records(algorithm=algorithm, split=split))
        if record_ids is not None:
            indexed = {r["record_id"]: r for r in self.records}
            self.records = [indexed[i] for i in record_ids]

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        return self.corpus.training_example(self.records[index], self.modality)


class VisualCollator:
    """Mask all instruction/image tokens; supervise only the assistant target."""

    def __init__(self, processor):
        self.processor = processor

    def __call__(self, examples):
        processor = self.processor
        texts = [
            processor.apply_chat_template(e["messages"], tokenize=False, add_generation_prompt=False) for e in examples
        ]
        images = [image for e in examples for image in e["images"]]
        encoded = processor(text=texts, images=images or None, padding=True, return_tensors="pt")
        labels = encoded["input_ids"].clone()
        for i, example in enumerate(examples):
            length = frozen_processor().count(example["messages"][:-1])
            if length + 384 > 32768 or encoded["input_ids"].shape[1] > 32768:
                raise RuntimeError("VALID_STOP: training example exceeds context")
            padding = (
                len(labels[i]) - int(encoded["attention_mask"][i].sum())
                if processor.tokenizer.padding_side == "left"
                else 0
            )
            labels[i, : padding + length] = -100
            labels[i, encoded["attention_mask"][i] == 0] = -100
            if not (labels[i] != -100).any():
                raise ValueError("training example has no assistant target")
        encoded["labels"] = labels
        return encoded


def load_training_model(config):
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import Qwen3VLForConditionalGeneration, set_seed

    set_seed(config["training_seed"])
    training = config["training"]
    model: Any = Qwen3VLForConditionalGeneration.from_pretrained(
        config["model_id"],
        revision=config["model_revision"],
        dtype=torch.bfloat16,
        attn_implementation=training["attention"],
        local_files_only=True,
    )
    model.to("cuda:0")
    model = get_peft_model(
        model,
        LoraConfig(
            r=training["lora_rank"],
            lora_alpha=training["lora_alpha"],
            lora_dropout=training["lora_dropout"],
            bias="none",
            target_modules="all-linear",
            exclude_modules=r".*visual.*",
            task_type="CAUSAL_LM",
        ),
    )
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model.train()
    return model


def train_visual(config, root, algorithm, output, *, deadline, progress, resume=False):
    from torch.utils.data import SequentialSampler
    from transformers import Trainer, TrainerCallback, TrainingArguments

    from .scene_assets import read_json

    pilot = read_json(root / config["pilot_manifest"]) if config.get("pilot_manifest") else None
    dataset = VisualDataset(
        root,
        root / config["corpus_report"],
        algorithm,
        record_ids=pilot["training_record_ids"][algorithm] if pilot else None,
        modality=config["modality"],
    )
    diagnostics = VisualDataset(
        root,
        root / config["corpus_report"],
        algorithm,
        split="dev",
        record_ids=pilot["diagnostic_record_ids"][algorithm] if pilot else None,
        modality=config["modality"],
    )
    training = config["training"]
    total = math.ceil(len(dataset) / training["global_batch_size"]) * training["epochs"]
    started = time.monotonic()

    class StagedTrainer(Trainer):
        def training_step(self, *args, **kwargs):
            if time.monotonic() >= deadline:
                raise RuntimeError("VALID_STOP: cutoff before training forward pass")
            return super().training_step(*args, **kwargs)

        def prediction_step(self, *args, **kwargs):
            if time.monotonic() >= deadline:
                raise RuntimeError("VALID_STOP: cutoff before teacher diagnostic forward pass")
            return super().prediction_step(*args, **kwargs)

        def _get_train_sampler(self, train_dataset=None):
            return SequentialSampler(dataset)

    class Progress(TrainerCallback):
        diagnostic_completed = 0

        def on_prediction_step(self, args, state, control, **kwargs):
            self.diagnostic_completed += 1
            if self.diagnostic_completed % 100 == 0 or self.diagnostic_completed == len(diagnostics):
                progress(
                    "teacher_diagnostic",
                    completed=self.diagnostic_completed,
                    total=len(diagnostics),
                    step=state.global_step,
                )
            return control

        def on_evaluate(self, args, state, control, **kwargs):
            self.diagnostic_completed = 0
            return control

        def on_step_end(self, args, state, control, **kwargs):
            progress(
                "training",
                completed=state.global_step,
                total=total,
                eta_seconds=(time.monotonic() - started) / max(1, state.global_step) * (total - state.global_step),
            )
            if state.global_step in {max(1, total // 3), max(1, 2 * (total // 3))}:
                control.should_evaluate = True
            if time.monotonic() >= deadline:
                control.should_save = True
                control.should_training_stop = True
            return control

    output.mkdir(parents=True, exist_ok=True)
    checkpoints = sorted(output.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[-1]))
    if checkpoints and not resume:
        raise ValueError("existing training checkpoint requires --resume")
    model = load_training_model(config)
    args = TrainingArguments(
        output_dir=str(output),
        num_train_epochs=training["epochs"],
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        prediction_loss_only=True,
        gradient_accumulation_steps=training["global_batch_size"],
        learning_rate=training["learning_rate"],
        weight_decay=training["weight_decay"],
        warmup_ratio=training["warmup_ratio"],
        lr_scheduler_type=training["lr_scheduler"],
        optim=training["optimizer"],
        max_grad_norm=training["max_grad_norm"],
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        seed=17,
        data_seed=17,
        logging_steps=1,
        save_steps=max(1, total // 3),
        save_total_limit=3,
        report_to=[],
        remove_unused_columns=False,
        dataloader_num_workers=0,
    )
    trainer = StagedTrainer(
        model=model,
        args=args,
        train_dataset=dataset,
        eval_dataset=diagnostics,
        data_collator=VisualCollator(frozen_processor().processor),
        callbacks=[Progress()],
    )
    trainer.train(resume_from_checkpoint=str(checkpoints[-1]) if resume and checkpoints else None)
    if trainer.state.global_step != total:
        raise RuntimeError("VALID_STOP: training clock expired before final checkpoint")
    trainer.save_model(str(output / "final"))
    return {
        "algorithm": algorithm,
        "seed": 17,
        "steps": total,
        "final_checkpoint": str((output / "final").relative_to(root)),
        "train_records": len(dataset),
        "outcome": "PASS",
    }
