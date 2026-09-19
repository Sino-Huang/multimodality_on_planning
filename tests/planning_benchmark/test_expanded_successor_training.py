"""CPU-only contract tests for expanded successor SFT training."""

import gzip
import hashlib
import json
from pathlib import Path

import pytest
import torch
from safetensors.torch import save_file
from torch.utils.data import SequentialSampler

from examples.planning_benchmark_slice import expanded_successor_training as training
from examples.planning_benchmark_slice.modality_corpus_replay import canonical
from scripts import run_expanded_successor_training as runner


def protocol(record_ids=None):
    ids = record_ids or ["record-0", "record-1"]
    return {
        "protocol_id": "test-successor",
        "modalities": ["text-state", "visual-state", "multimodal-state"],
        "source_record_ids": ids,
        "starting_checkpoints": {
            "text-state": "start/text",
            "visual-state": "start/visual",
            "multimodal-state": "start/multimodal",
        },
        "output_root": "successor",
        "training": {
            "arm": "successor_sft",
            "records_per_modality": len(ids),
            "epochs": 1,
            "optimizer_updates": 1,
            "seed": 17,
            "microbatch_size": 1,
            "global_batch_size": 32,
            "gradient_accumulation_steps": 32,
            "sampler": "sequential_frozen_membership_order",
            "trainer_reshuffling": False,
            "learning_rate": 1e-4,
            "optimizer": "adamw_torch",
            "warmup_ratio": 0.03,
            "lr_scheduler": "cosine",
            "weight_decay": 0,
            "max_grad_norm": 1,
            "lora_rank": 64,
            "lora_alpha": 128,
            "lora_dropout": 0.05,
            "freeze_vision": True,
        },
        "launch": {
            "devices": [0, 1],
            "master_port_pool": [18800, 18801, 18802],
            "qualification_worker_modalities": {
                "0": ["text-state", "multimodal-state"],
                "1": ["visual-state"],
            },
        },
        "budget": {"gpu_cutoff_utc": "2999-01-01T00:00:00Z"},
    }


def context(ids):
    records = [{"record_id": value, "task_id": f"task-{index}"} for index, value in enumerate(ids)]
    contracts = [
        {
            "record_id": value,
            "model_input": {"input": index},
            "query": {"query": index},
            "source_state": {"state": index},
            "source_path": [{"step": index}],
            "target": {"target": index},
        }
        for index, value in enumerate(ids)
    ]
    return {
        "membership_id": "membership",
        "records": records,
        "contracts": contracts,
        "study": {
            "training_seed": 17,
            "training": {
                "lora_rank": 64,
                "lora_alpha": 128,
                "lora_dropout": 0.05,
                "freeze_vision": True,
            },
        },
    }


def adapter_config():
    return {
        "r": 64,
        "lora_alpha": 128,
        "lora_dropout": 0.05,
        "exclude_modules": ".*visual.*",
        "peft_type": "LORA",
    }


def write_release(tmp_path: Path, p, ctx, modality="text-state"):
    base = tmp_path / p["output_root"] / "dataset" / "release-001"
    labels = []
    for index, (source, contract) in enumerate(zip(ctx["records"], ctx["contracts"], strict=True)):
        labels.append(
            {
                "schema_version": "expanded_successor_training_label_v1",
                "record_id": source["record_id"],
                "task_id": source["task_id"],
                "split": "train",
                "modality": modality,
                "collection_index": index,
                "model_input": contract["model_input"],
                "view": {"binding": {"index": index}},
                "query": contract["query"],
                "source_state": contract["source_state"],
                "source_path": contract["source_path"],
                "target": contract["target"],
            }
        )
    payload = {
        "schema_version": "expanded_successor_training_set_v1",
        "protocol_id": p["protocol_id"],
        "release_id": "release-001",
        "modality": modality,
        "membership_id": ctx["membership_id"],
        "records": labels,
    }
    path = base / modality / "labels.json.gz"
    path.parent.mkdir(parents=True)
    with gzip.open(path, "wt") as stream:
        json.dump(payload, stream)
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    report = {
        "schema_version": "expanded_successor_release_v1",
        "outcome": "PASS",
        "protocol_id": p["protocol_id"],
        "release_id": "release-001",
        "membership_id": ctx["membership_id"],
        "total_interactions": len(p["modalities"]) * p["training"]["records_per_modality"],
        "byte_identical_regeneration_verified": True,
        "artifacts": {
            modality: {
                "labels": {
                    "path": str(path.relative_to(tmp_path)),
                    "records": len(labels),
                    "sha256": digest,
                }
            }
        },
    }
    (base / "report.json").write_text(json.dumps(report))
    return labels


def fake_example(ctx, index):
    return {
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "input"},
            {"role": "assistant", "content": canonical(ctx["contracts"][index]["target"])},
        ],
        "images": [],
        "binding": {"index": index},
    }


def test_membership_order_and_dataset_match_verified_labels(tmp_path, monkeypatch):
    p = protocol()
    ctx = context(p["source_record_ids"])
    labels = write_release(tmp_path, p, ctx)
    path, membership = training.prepare_membership(tmp_path, p, ctx, modality="text-state")
    assert path.name == "labels.json.gz"
    assert [row["record_id"] for row in membership["records"]] == p["source_record_ids"]
    monkeypatch.setattr(
        training,
        "training_example",
        lambda root, protocol, context, views, index, modality, pixels=True: fake_example(ctx, index),
    )
    dataset = training.SuccessorTrainingDataset(tmp_path, p, ctx, object(), membership)
    assert [dataset[index]["messages"][-1]["content"] for index in range(len(dataset))] == [
        canonical(row["target"]) for row in labels
    ]
    membership["records"][0]["target"] = {"changed": True}
    with pytest.raises(ValueError, match="teacher label"):
        dataset[0]


def test_training_arguments_sampler_and_update_guard(tmp_path):
    p = protocol([f"record-{index}" for index in range(512)])
    p["training"]["optimizer_updates"] = 16
    kwargs = training.training_arguments_kwargs(p, tmp_path)
    assert kwargs["num_train_epochs"] == 1
    assert kwargs["per_device_train_batch_size"] == 1
    assert kwargs["gradient_accumulation_steps"] == 32
    assert kwargs["learning_rate"] == 1e-4
    assert kwargs["optim"] == "adamw_torch"
    assert kwargs["warmup_ratio"] == 0.03 and kwargs["lr_scheduler_type"] == "cosine"
    assert kwargs["weight_decay"] == 0 and kwargs["max_grad_norm"] == 1
    assert kwargs["seed"] == kwargs["data_seed"] == 17
    assert kwargs["save_strategy"] == "no"
    dataset = list(range(512))
    sampler = training.sequential_sampler(dataset)
    assert isinstance(sampler, SequentialSampler)
    assert list(sampler) == list(range(512))
    assert training.optimizer_updates(512, p["training"]) == 16
    assert training.optimizer_updates(513, p["training"]) == 17


def build_verified_cell(tmp_path, monkeypatch, *, unchanged_key=None):
    p = protocol()
    ctx = context(p["source_record_ids"])
    write_release(tmp_path, p, ctx)
    monkeypatch.setattr(
        training,
        "training_example",
        lambda root, protocol, context, views, index, modality, pixels=True: fake_example(ctx, index),
    )
    source = tmp_path / p["starting_checkpoints"]["text-state"]
    source.mkdir(parents=True)
    source_tensors = {"a": torch.zeros(2), "b": torch.ones(2)}
    final_tensors = {"a": torch.ones(2), "b": torch.zeros(2)}
    if unchanged_key:
        final_tensors[unchanged_key] = source_tensors[unchanged_key]
    save_file(source_tensors, source / "adapter_model.safetensors")
    (source / "adapter_config.json").write_text(json.dumps(adapter_config()))
    (source / "README.md").write_text("frozen source checkpoint\n")
    source_manifest = training._checkpoint_manifest(source)
    output = training.training_root(tmp_path, p, "text-state")
    final = output / "final"
    final.mkdir(parents=True)
    save_file(final_tensors, final / "adapter_model.safetensors")
    (final / "adapter_config.json").write_text(json.dumps(adapter_config()))
    final_fingerprints = training._final_checkpoint_fingerprints(final)
    state = {"global_step": 1, "log_history": [{"loss": 0.25, "step": 1}]}
    (output / "training_state.json").write_text(json.dumps(state))
    label_path, membership = training.prepare_membership(tmp_path, p, ctx, modality="text-state")
    receipt = training._build_completion_receipt(
        tmp_path,
        p,
        membership,
        modality="text-state",
        source=source,
        source_manifest=source_manifest,
        final=final,
        state=state,
        wall_seconds=12.5,
        cpu_seconds=4.5,
    )
    receipt_path = output / training.COMPLETION_RECEIPT_FILE
    receipt_path.write_text(json.dumps(receipt))
    report = {
        "schema_version": "expanded_successor_training_cell_v1",
        "outcome": "PASS",
        "protocol_id": p["protocol_id"],
        "modality": "text-state",
        "arm": "successor_sft",
        "source_checkpoint": p["starting_checkpoints"]["text-state"],
        "source_checkpoint_manifest_before": source_manifest,
        "source_checkpoint_manifest_after": source_manifest,
        "source_checkpoint_unchanged": True,
        "teacher_labels": str(label_path.relative_to(tmp_path)),
        "teacher_labels_sha256": membership["labels_sha256"],
        "membership_id": ctx["membership_id"],
        "training_record_ids": p["source_record_ids"],
        "records": len(p["source_record_ids"]),
        "epochs": 1,
        "optimizer_updates": 1,
        "seed": 17,
        "data_seed": 17,
        "sampler": "sequential_frozen_membership_order",
        "trainer_reshuffling": False,
        "freeze_vision": True,
        "lora": {"rank": 64, "alpha": 128, "dropout": 0.05},
        "final_checkpoint": str(final.relative_to(tmp_path)),
        **final_fingerprints,
        "final_checkpoint_only": True,
        "tensor_change_requirement": training.CHANGE_REQUIREMENT,
        "completion_receipt": str(receipt_path.relative_to(tmp_path)),
        "completion_receipt_sha256": training._sha256(receipt_path),
        "recovered_without_retrain": False,
    }
    (output / "report.json").write_text(json.dumps(report))
    return p, ctx


def test_verify_training_cell_accepts_complete_changed_adapter(tmp_path, monkeypatch):
    p, ctx = build_verified_cell(tmp_path, monkeypatch)
    result = training.verify_training_cell(tmp_path, p, ctx, object(), modality="text-state")
    assert result["changed_parameter_tensors"] == result["parameter_tensors"] == 2
    assert result["optimizer_updates"] == 1
    receipt_path = training.training_root(tmp_path, p, "text-state") / training.COMPLETION_RECEIPT_FILE
    receipt = json.loads(receipt_path.read_text())
    assert set(receipt) == {
        "schema_version",
        "status",
        "protocol_id",
        "modality",
        "arm",
        "membership_id",
        "teacher_labels_sha256",
        "effective_training_arguments",
        "source_checkpoint",
        "source_checkpoint_manifest_sha256",
        "final_checkpoint",
        "final_checkpoint_sha256",
        "final_adapter_config_sha256",
        "trainer_state_digest",
        "wall_seconds",
        "cpu_seconds",
        "completed_at",
    }
    assert receipt["effective_training_arguments"]["seed"] == 17
    assert receipt["trainer_state_digest"]["global_step"] == 1


@pytest.mark.parametrize(
    "failure", ["unchanged", "state", "report", "source_file", "final_fingerprint"]
)
def test_verify_training_cell_rejects_negative_cases(tmp_path, monkeypatch, failure):
    p, ctx = build_verified_cell(
        tmp_path, monkeypatch, unchanged_key="a" if failure == "unchanged" else None
    )
    output = training.training_root(tmp_path, p, "text-state")
    if failure == "state":
        (output / "training_state.json").write_text(json.dumps({"global_step": 0}))
    elif failure == "report":
        report = json.loads((output / "report.json").read_text())
        report["seed"] = 18
        (output / "report.json").write_text(json.dumps(report))
    elif failure == "source_file":
        source = tmp_path / p["starting_checkpoints"]["text-state"]
        (source / "README.md").write_text("mutated after training\n")
    elif failure == "final_fingerprint":
        report = json.loads((output / "report.json").read_text())
        report["final_checkpoint_sha256"] = "sha256:wrong"
        (output / "report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError):
        training.verify_training_cell(tmp_path, p, ctx, object(), modality="text-state")


def test_worker_environment_mapping_validation(monkeypatch):
    p = protocol()
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setenv("MASTER_PORT", "18800")
    assert runner.require_worker_environment(p, 0) == 18800
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1")
    with pytest.raises(ValueError, match="GPU"):
        runner.require_worker_environment(p, 0)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setenv("MASTER_PORT", "19999")
    with pytest.raises(ValueError, match="MASTER_PORT"):
        runner.require_worker_environment(p, 0)
    with pytest.raises(ValueError, match="outside"):
        runner.require_worker_environment(p, 2)


def test_completed_cells_are_audited_and_skipped_on_resume(tmp_path, monkeypatch):
    p = protocol()
    p["launch"]["qualification_worker_modalities"]["0"] = ["text-state"]
    report_path = training.training_root(tmp_path, p, "text-state") / "report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps({"records": 2, "optimizer_updates": 1}))
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "require_before_cutoff", lambda protocol: None)
    monkeypatch.setattr(runner, "verify_training_cell", lambda *args, **kwargs: {"outcome": "PASS"})
    monkeypatch.setattr(runner, "train_cell", lambda *args, **kwargs: pytest.fail("completed cell retrained"))
    monkeypatch.setattr(runner, "head", lambda: "head")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setenv("MASTER_PORT", "18800")
    monkeypatch.setenv("EXPANDED_ATTEMPT_DIR", str(attempt))
    monkeypatch.setenv("EXPANDED_PROGRESS_PATH", str(attempt / "progress.json"))
    runner.run_training(p, {}, object(), 0)
    result = json.loads((attempt / "worker-result.json").read_text())
    progress = json.loads((attempt / "progress.json").read_text())
    assert result["records"] == 2 and result["optimizer_updates"] == 1
    assert progress == {"completed": 2, "total": 2, "terminal": True}


def write_recovery_marker(tmp_path, p, output):
    source = tmp_path / p["starting_checkpoints"]["text-state"]
    recovery = {
        "schema_version": training.RECOVERY_SCHEMA,
        "protocol_id": p["protocol_id"],
        "modality": "text-state",
        "source_checkpoint": p["starting_checkpoints"]["text-state"],
        "source_checkpoint_manifest_before": training._checkpoint_manifest(source),
        "runtime_head": "retained-head",
        "cuda_visible_devices": "0",
        "master_port": 18800,
        "started_at": 1,
    }
    (output / training.RECOVERY_FILE).write_text(json.dumps(recovery))


def test_crash_window_with_valid_receipt_recovers_without_retraining(tmp_path, monkeypatch):
    p, ctx = build_verified_cell(tmp_path, monkeypatch)
    output = training.training_root(tmp_path, p, "text-state")
    (output / "report.json").unlink()
    write_recovery_marker(tmp_path, p, output)
    report = training.train_cell(
        tmp_path,
        p,
        ctx,
        object(),
        modality="text-state",
        progress=lambda **kwargs: pytest.fail("recovered cell entered training"),
    )
    assert report["recovered_without_retrain"] is True
    assert report["final_checkpoint_sha256"].startswith("sha256:")
    assert report["final_adapter_config_sha256"].startswith("sha256:")
    assert (output / "report.json").is_file()
    assert not (output / training.RECOVERY_FILE).exists()


def test_crash_window_without_receipt_refuses_to_publish_pass(tmp_path, monkeypatch):
    p, ctx = build_verified_cell(tmp_path, monkeypatch)
    output = training.training_root(tmp_path, p, "text-state")
    (output / "report.json").unlink()
    (output / training.COMPLETION_RECEIPT_FILE).unlink()
    write_recovery_marker(tmp_path, p, output)
    with pytest.raises(ValueError, match="completion receipt"):
        training.train_cell(
            tmp_path,
            p,
            ctx,
            object(),
            modality="text-state",
            progress=lambda **kwargs: pytest.fail("incomplete cell entered training"),
        )
    assert not (output / "report.json").exists()


def test_crash_window_with_tampered_receipt_refuses_to_publish_pass(tmp_path, monkeypatch):
    p, ctx = build_verified_cell(tmp_path, monkeypatch)
    output = training.training_root(tmp_path, p, "text-state")
    (output / "report.json").unlink()
    receipt_path = output / training.COMPLETION_RECEIPT_FILE
    receipt = json.loads(receipt_path.read_text())
    receipt["teacher_labels_sha256"] = "sha256:wrong"
    receipt_path.write_text(json.dumps(receipt))
    write_recovery_marker(tmp_path, p, output)
    with pytest.raises(ValueError, match="completion receipt"):
        training.train_cell(
            tmp_path,
            p,
            ctx,
            object(),
            modality="text-state",
            progress=lambda **kwargs: pytest.fail("tampered cell entered training"),
        )
    assert not (output / "report.json").exists()


def test_aggregate_report_pairs_status_and_outcome_with_checkpoint_fingerprints(
    tmp_path, monkeypatch
):
    p = protocol()
    attempts = [
        {
            "job_id": f"successor-train-{worker}",
            "attempt": 1,
            "status": "succeeded",
            "directory": str(tmp_path / f"attempt-{worker}"),
            "gpus": [worker],
            "master_port": 18800 + worker,
            "gpu_hours": 1.0,
        }
        for worker in range(2)
    ]
    cells = {
        modality: {
            "outcome": "PASS",
            "modality": modality,
            "records": 2,
            "optimizer_updates": 1,
            "final_checkpoint": f"successor/training/{modality}/successor_sft/final",
            "final_checkpoint_sha256": f"sha256:model-{modality}",
            "final_adapter_config_sha256": f"sha256:config-{modality}",
        }
        for modality in p["modalities"]
    }

    def fake_read(path):
        if str(path).endswith("budget.json"):
            return {"attempts": attempts}
        return {"returncode": 0}

    written = {}
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "read", fake_read)
    monkeypatch.setattr(
        runner,
        "verify_training_cell",
        lambda root, protocol, context, views, *, modality: cells[modality],
    )
    monkeypatch.setattr(runner, "write", lambda path, value: written.__setitem__(str(path), value))
    monkeypatch.setenv("EXPANDED_PROGRESS_PATH", str(tmp_path / "progress.json"))
    runner.finalize_training(p, {}, object())
    report_path = str(tmp_path / p["output_root"] / "training" / "training-report.json")
    report = written[report_path]
    assert set(report) == {
        "schema_version",
        "status",
        "outcome",
        "protocol_id",
        "arm",
        "cells",
        "records",
        "optimizer_updates",
        "jobs",
    }
    assert report["status"] == report["outcome"] == "PASS"
    assert [row["modality"] for row in report["cells"]] == p["modalities"]
    assert all(row["final_checkpoint_sha256"].startswith("sha256:") for row in report["cells"])
    assert all(row["final_adapter_config_sha256"].startswith("sha256:") for row in report["cells"])


def test_repository_training_job_configs_are_frozen():
    root = Path(__file__).resolve().parents[2]
    jobs = {
        name: json.loads(
            (root / f"configs/experiments/expanded-study/successor-train-{name}-job.json").read_text()
        )
        for name in ("0", "1", "final")
    }
    assert jobs["0"]["branch"] == jobs["1"]["branch"] == jobs["final"]["branch"] == "successor_prediction"
    assert jobs["0"]["gpus"] == [0] and jobs["1"]["gpus"] == [1] and jobs["final"]["gpus"] == []
    assert jobs["0"]["total"] == 1024 and jobs["1"]["total"] == 512
    assert jobs["0"]["max_seconds"] == 21600 and jobs["1"]["max_seconds"] == 10800
    assert all(
        "scripts/run_expanded_successor_training.py" in job["command"] for job in jobs.values()
    )
