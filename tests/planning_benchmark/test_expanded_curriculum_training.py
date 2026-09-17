"""CPU-only tests for expanded curriculum protocol and training evidence."""

import copy
import json
from pathlib import Path

import pytest
import torch
from safetensors.torch import save_file
from torch.utils.data import SequentialSampler

from examples.planning_benchmark_slice import expanded_curriculum_training as training
from scripts import run_expanded_curriculum_training as runner

ROOT = Path(__file__).resolve().parents[2]


def fake_protocol(ids=None):
    ids = ids or [f"pair-{i % 3}:best_first_add_greedy:{i}" for i in range(512)]
    difficulty = {"pair-0": "easy", "pair-1": "medium", "pair-2": "hard"}
    orders = training.build_orderings(ids, difficulty)
    return {
        "protocol_id": "test-curriculum",
        "algorithm": "best_first_add_greedy",
        "modalities": ["text-state", "visual-state", "multimodal-state"],
        "source_record_ids": ids,
        "difficulty_map": difficulty,
        "orderings": {
            name: {"ordered_ids": rows, "sha256": training._json_sha256(rows)} for name, rows in orders.items()
        },
        "base_model": {
            "model_id": "model",
            "revision": "rev",
            "processor_class": "Processor",
            "processor_revision": "rev",
            "historical_checkpoint_reuse": False,
        },
        "training": {
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
            "learning_rate": 1e-4,
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
        },
        "output_root": "curriculum",
        "launch": {"devices": [0, 1], "master_port_pool": [18800, 18801], "training_worker_cells": {"0": [], "1": []}},
    }


def adapter_config():
    return {
        "r": 64,
        "lora_alpha": 128,
        "lora_dropout": 0.05,
        "exclude_modules": ".*visual.*",
        "bias": "none",
        "task_type": "CAUSAL_LM",
    }


def test_repository_protocol_orderings_reproduce_and_hash_match():
    protocol = json.loads((ROOT / "configs/experiments/expanded-study/curriculum-protocol.json").read_text())
    rebuilt = training.verify_frozen_orderings(protocol)
    assert all(rebuilt[name] == protocol["orderings"][name]["ordered_ids"] for name in training.ORDERINGS)
    assert all(set(rows) == set(protocol["source_record_ids"]) for rows in rebuilt.values())
    assert protocol["difficulty_distribution"] == {
        "pairs": {"easy": 13, "medium": 11, "hard": 2},
        "records": {"easy": 180, "medium": 270, "hard": 62},
    }


def test_repository_protocol_full_contract_accepts_and_rejects_material_drift():
    protocol = json.loads((ROOT / "configs/experiments/expanded-study/curriculum-protocol.json").read_text())
    context = training.validate_protocol(ROOT, protocol)
    assert len(context["records"]) == 512
    mutations = [
        ("training", "learning_rate", 0.001),
        ("training", "lora_rank", 32),
        ("evaluation", "model_episodes", 729),
        ("budget", "total_qualified_gpu_hours", 16.0),
    ]
    for section, key, value in mutations:
        changed = copy.deepcopy(protocol)
        changed[section][key] = value
        with pytest.raises(ValueError, match="frozen study"):
            training.validate_protocol(ROOT, changed)


def test_ordering_construction_small_fixture():
    ids = ["a:x:0", "b:x:0", "c:x:0", "a:x:1", "b:x:1"]
    result = training.build_orderings(ids, {"a": "easy", "b": "medium", "c": "hard"})
    assert result["staged"] == ["a:x:0", "a:x:1", "b:x:0", "b:x:1", "c:x:0"]
    assert result["mixed_order"] == ["a:x:0", "b:x:0", "c:x:0", "a:x:1", "b:x:1"]
    assert result["shuffled"] != ids and set(result["shuffled"]) == set(ids)


def test_sampler_arguments_updates_and_fresh_base_contract(tmp_path):
    protocol = fake_protocol()
    args = training.training_arguments_kwargs(protocol, tmp_path)
    assert args["seed"] == args["data_seed"] == 17 and args["save_strategy"] == "no"
    assert args["gradient_accumulation_steps"] == 32 and args["warmup_steps"] == 1
    sampler = training.sequential_sampler(list(range(512)))
    assert isinstance(sampler, SequentialSampler) and list(sampler) == list(range(512))
    assert training.optimizer_updates(512, protocol["training"]) == 16
    assert "starting_checkpoints" not in protocol
    config = training._model_config(protocol)
    assert config["model_id"] == "model" and config["training_seed"] == 17


def build_cell(tmp_path, *, tamper_receipt=False):
    protocol = fake_protocol()
    ordering = "staged"
    modality = "text-state"
    source = tmp_path / "membership.json"
    source.write_text("{}")
    context = {"source_files": [source]}
    source_manifest = training._source_manifest(tmp_path, [source])
    output = training.training_root(tmp_path, protocol, modality, ordering)
    final = output / "final"
    final.mkdir(parents=True)
    init = {"a": torch.zeros(2), "b": torch.ones(2)}
    changed = {"a": torch.ones(2), "b": torch.zeros(2)}
    save_file(init, output / training.FRESH_INIT_FILE)
    save_file(changed, final / "adapter_model.safetensors")
    (final / "adapter_config.json").write_text(json.dumps(adapter_config()))
    state = {"global_step": 16, "log_history": [{"loss": 1.0, "step": 16}]}
    (output / "training_state.json").write_text(json.dumps(state))
    receipt = training._receipt(
        tmp_path,
        protocol,
        modality=modality,
        ordering=ordering,
        source_manifest=source_manifest,
        final=final,
        init_tensor=output / training.FRESH_INIT_FILE,
        state=state,
        wall_seconds=1.0,
        cpu_seconds=0.5,
    )
    if tamper_receipt:
        receipt["ordered_training_record_ids_sha256"] = "sha256:wrong"
    receipt_path = output / training.RECEIPT_FILE
    receipt_path.write_text(json.dumps(receipt))
    report = training._build_report(
        tmp_path,
        protocol,
        modality=modality,
        ordering=ordering,
        source_before=source_manifest,
        source_after=source_manifest,
        output=output,
        state=state,
        runtime={"runtime_head": "head", "cuda_visible_devices": "0", "master_port": 18800, "elapsed_seconds": 1.0},
        recovered=False,
    )
    (output / "report.json").write_text(json.dumps(report))
    return protocol, context, output


def test_verify_cell_accepts_and_rejects_order_set_and_receipt(tmp_path):
    protocol, context, output = build_cell(tmp_path)
    result = training.verify_training_cell(tmp_path, protocol, context, modality="text-state", ordering="staged")
    assert result["changed_parameter_tensors"] == result["parameter_tensors"] == 2
    assert result["fresh_lora_init_tensors"] == 2
    report = json.loads((output / "report.json").read_text())
    report["training_record_ids"] = list(reversed(report["training_record_ids"]))
    (output / "report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="exposure"):
        training.verify_training_cell(tmp_path, protocol, context, modality="text-state", ordering="staged")
    report["training_record_ids"] = ["wrong"] * 512
    (output / "report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError):
        training.verify_training_cell(tmp_path, protocol, context, modality="text-state", ordering="staged")


def write_recovery(protocol, context, output, tmp_path):
    marker = {
        "schema_version": training.RECOVERY_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "modality": "text-state",
        "ordering": "staged",
        "source_manifest_before": training._source_manifest(tmp_path, context["source_files"]),
        "runtime_head": "head",
        "cuda_visible_devices": "0",
        "master_port": 18800,
    }
    (output / training.RECOVERY_FILE).write_text(json.dumps(marker))


def test_crash_recovery_requires_valid_receipt(tmp_path, monkeypatch):
    protocol, context, output = build_cell(tmp_path)
    (output / "report.json").unlink()
    write_recovery(protocol, context, output, tmp_path)
    monkeypatch.setattr(training, "CurriculumDataset", lambda *args, **kwargs: list(range(512)))
    report = training.train_cell(
        tmp_path,
        protocol,
        context,
        modality="text-state",
        ordering="staged",
        progress=lambda **kwargs: pytest.fail("retrained"),
    )
    assert report["recovered_without_retrain"] is True
    (output / "report.json").unlink()
    write_recovery(protocol, context, output, tmp_path)
    (output / training.RECEIPT_FILE).unlink()
    with pytest.raises(ValueError, match="completion receipt"):
        training.train_cell(
            tmp_path, protocol, context, modality="text-state", ordering="staged", progress=lambda **kwargs: None
        )


def test_crash_recovery_rejects_tampered_receipt(tmp_path, monkeypatch):
    protocol, context, output = build_cell(tmp_path, tamper_receipt=True)
    (output / "report.json").unlink()
    write_recovery(protocol, context, output, tmp_path)
    monkeypatch.setattr(training, "CurriculumDataset", lambda *args, **kwargs: list(range(512)))
    with pytest.raises(ValueError, match="completion receipt"):
        training.train_cell(
            tmp_path, protocol, context, modality="text-state", ordering="staged", progress=lambda **kwargs: None
        )
    assert not (output / "report.json").exists()


def test_worker_mapping_and_repository_jobs(monkeypatch):
    protocol = fake_protocol()
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setenv("MASTER_PORT", "18800")
    assert runner.require_worker_environment(protocol, 0) == 18800
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1")
    with pytest.raises(ValueError, match="GPU"):
        runner.require_worker_environment(protocol, 0)
    for kind in ("train", "evaluate"):
        for suffix, gpus in (("0", [0]), ("1", [1]), ("final", [])):
            job = json.loads(
                (ROOT / f"configs/experiments/expanded-study/curriculum-{kind}-{suffix}-job.json").read_text()
            )
            assert job["branch"] == "curriculum_modality" and job["gpus"] == gpus
            assert f"run_expanded_curriculum_{'training' if kind == 'train' else 'evaluation'}.py" in job["command"][1]
    train_one = json.loads((ROOT / "configs/experiments/expanded-study/curriculum-train-1-job.json").read_text())
    assert train_one["max_seconds"] == 3600
    evaluate = {
        name: json.loads((ROOT / f"configs/experiments/expanded-study/curriculum-evaluate-{name}-job.json").read_text())
        for name in ("0", "1", "final")
    }
    assert (evaluate["0"]["total"], evaluate["1"]["total"], evaluate["final"]["total"]) == (
        162,
        81,
        243,
    )
    assert (evaluate["0"]["max_seconds"], evaluate["1"]["max_seconds"]) == (10800, 5400)
    expected_resume = (
        "attempt 1 crashed on BestFirstModelSession arm-name validation (curriculum arm names rejected by the "
        "issue-75 guard); fixed by mapping curriculum arms to process_sft behavior arm with adapter_id identity; "
        "zero episodes were produced by attempt 1, attempt 2 reruns the full fixed panel"
    )
    assert evaluate["0"]["resume_reason"] == evaluate["1"]["resume_reason"] == expected_resume


def test_aggregate_requires_identical_fresh_lora_initialization():
    cells = [{"fresh_lora_init_sha256": "sha256:init", "fresh_lora_init_tensors": 504} for _ in range(9)]
    assert runner._fresh_init_evidence(cells) == {"sha256": "sha256:init", "parameter_tensors": 504}
    cells[-1]["fresh_lora_init_sha256"] = "sha256:different"
    with pytest.raises(ValueError, match="initialization differs"):
        runner._fresh_init_evidence(cells)
