"""CPU-only tests for the second-backbone (#101-#103) branch machinery."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
from safetensors.torch import save_file

from examples.planning_benchmark_slice import expanded_second_backbone as branch
from examples.planning_benchmark_slice import visual_episode
from scripts import run_expanded_second_backbone as runner

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = ROOT / "configs/experiments/expanded-study/second-backbone-protocol.json"


def repository_protocol():
    return json.loads(PROTOCOL_PATH.read_text())


def fake_protocol(tmp_path, ids=None):
    ids = ids or [f"bfs/pair-{i}:bfs:{i}" for i in range(512)]
    protocol = {
        "schema_version": "expanded_second_backbone_protocol_v1",
        "protocol_id": "test-second-backbone",
        "algorithm": "bfs",
        "modalities": ["text-state", "visual-state", "multimodal-state"],
        "source_record_ids": ids,
        "source_record_ids_sha256": branch._ids_sha256(ids),
        "source_corpus": "corpus-report.json",
        "views": {"scene_views": "scene-views.json"},
        "base_model": {
            "backbone_key": "internvl3_5-8b",
            "model_id": "model",
            "revision": "rev",
            "processor_class": "InternVLProcessor",
            "model_class": "transformers.InternVLForConditionalGeneration",
            "processor_overrides": {},
            "license": "apache-2.0",
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
            "sampler": "sequential_membership_order",
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
            "lora_exclude_modules": r".*(vision_tower|multi_modal_projector).*",
            "lora_bias": "none",
            "lora_task_type": "CAUSAL_LM",
            "freeze_vision": True,
            "dtype": "bfloat16",
            "attention": "sdpa",
            "gradient_checkpointing_use_reentrant": False,
            "checkpoint_selection": "final_update_16_only",
            "loss": "shared_collator_assistant_target_only",
            "single_training_seed_limitation": "exactly one training run per cell",
        },
        "evaluation": {
            "panel_id": "expanded-panel-v2-qualified",
            "seed": 17,
            "context_tokens": 32768,
            "maximum_input_tokens": 32384,
            "output_tokens": 384,
            "model_conditions": ["pretrained_base", "process_sft"],
            "comparator_conditions": ["random_valid", "exact_reference"],
            "reference_decision_multiplier": 2,
            "expansion_cap": "reference_expansions",
            "logical_bindings": 288,
            "model_episodes": 144,
            "comparator_episodes": 144,
            "random_valid_assistance": "oracle-assisted",
            "inference": {"max_batch_size": 2, "max_padded_batch_input_tokens": 24000},
        },
        "analysis": {
            "unit": "whole_problem_paired",
            "bootstrap_seed": 1729,
            "bootstrap_resamples": 200,
            "confidence": 0.95,
        },
        "budget": {"branch": "second_backbone", "gpu_hours": 40, "qualification_safety_factor": 1.25},
        "launch": {
            "devices": [0, 1],
            "master_port_pool": [18800, 18801],
            "training_worker_cells": {
                "0": [{"modality": "text-state"}, {"modality": "visual-state"}],
                "1": [{"modality": "multimodal-state"}],
            },
            "evaluation_worker_policy_load_order": {"0": ["text-state", "multimodal-state"], "1": ["visual-state"]},
            "backend_endpoints": ["a", "b"],
        },
        "output_root": "second-backbone-test",
    }
    return protocol


def test_repository_protocol_accepts_and_rejects_material_drift():
    protocol = repository_protocol()
    context = branch.validate_protocol(ROOT, protocol)
    assert len(context["records"]) == 512
    assert len(context["panel_tasks"]) == 24
    for section, key, value in (
        ("training", "learning_rate", 0.001),
        ("evaluation", "model_episodes", 145),
        ("base_model", "revision", "different"),
        ("launch", "evaluation_worker_policy_load_order", {"0": ["visual-state"], "1": ["text-state"]}),
    ):
        changed = copy.deepcopy(protocol)
        changed[section][key] = value
        with pytest.raises(ValueError, match="second-backbone"):
            branch.validate_protocol(ROOT, changed)


def test_job_id_prefix_maps_frozen_identities():
    assert branch.job_id_prefix({"protocol_id": "expanded-second-backbone-v1"}) == "second-backbone"
    assert branch.job_id_prefix({"protocol_id": "expanded-second-backbone-v2"}) == "sb-v2"
    with pytest.raises(ValueError, match="unknown second-backbone protocol identity"):
        branch.job_id_prefix({"protocol_id": "test-second-backbone"})


def test_repository_comparator_sources_bind_pinned_baseline_audits():
    protocol = repository_protocol()
    result = branch.validate_comparator_sources(ROOT, protocol)
    assert (
        result["baseline_evaluation_sha256"] == protocol["evaluation"]["comparator_audit"]["baseline_evaluation_sha256"]
    )
    assert result["reused_conditions"] == ["random_valid", "exact_reference"]


def test_binding_partition_and_episode_paths():
    protocol = repository_protocol()
    _, panel_tasks = branch.load_panel(ROOT, protocol)
    declared = branch.bindings(protocol, panel_tasks)
    assert len(declared) == 144
    assert len({(b["modality"], b["task_index"], b["condition"]) for b in declared}) == 144
    workers = {worker: branch.assigned_bindings(protocol, panel_tasks, worker) for worker in range(2)}
    assert len(workers[0]) == 72 and len(workers[1]) == 72
    assert {b["modality"] for part in workers.values() for b in part} == set(protocol["modalities"])
    assert sorted(b["index"] for part in workers.values() for b in part) == list(range(144))
    path = branch.episode_path(ROOT, protocol, "text-state", "task/a", "process_sft")
    assert path.relative_to(ROOT).as_posix() == (
        "outputs/expanded-study/v1/second-backbone/evaluation/text-state/task__a/process_sft.json.gz"
    )


def test_replay_visual_episode_threads_page_processor(monkeypatch):
    sentinel = SimpleNamespace(name="internvl")
    captured = {}

    class Session:
        def __init__(
            self, root, row, algorithm, arm, seed, output, contract_id, *, views=None, input_token_counter=None
        ):
            captured["input_token_counter"] = input_token_counter

        def next_request(self):
            return None

        def result(self):
            return {"decision_count": 0}

    class Views:
        read_only = False
        page_processor = SimpleNamespace(name="qwen")

    monkeypatch.setattr(visual_episode, "VisualSession", Session)
    report = {
        "algorithm": "bfs",
        "arm": "process_sft",
        "seed": 17,
        "output": "episode.json",
        "contract_id": "protocol",
        "events": [],
        "result": {"decision_count": 0},
    }
    views = Views()
    result = visual_episode.replay_visual_episode(ROOT, {"task_id": "t"}, report, views, page_processor=sentinel)
    assert result == {"decision_count": 0}
    assert views.page_processor is sentinel
    assert callable(captured["input_token_counter"])
    assert views.read_only is False
    other = Views()
    visual_episode.replay_visual_episode(ROOT, {"task_id": "t"}, report, other)
    assert other.page_processor.name == "qwen"


def test_policy_and_collator_prefer_passed_backbone_processor():
    from examples.planning_benchmark_slice.visual_model import VisualCollator, VisualPolicy

    oversize = SimpleNamespace(count=lambda *a, **k: 40000)
    policy = object.__new__(VisualPolicy)
    policy.page_processor = oversize
    policy.max_batch_size = 2
    policy.max_batch_input_tokens = 24000
    policy.max_context_tokens = 32768
    policy.max_new_tokens = 384
    with pytest.raises(RuntimeError, match="batch exceeds"):
        policy.generate([{"messages": [], "images": []}])

    calls = []

    class CountingProcessor:
        def count(self, messages, *, image_sizes=None):
            calls.append((len(messages), image_sizes))
            return 2

    class CallableProcessor:
        tokenizer = SimpleNamespace(padding_side="right")

        def apply_chat_template(self, messages, tokenize, add_generation_prompt):
            return "text"

        def __call__(self, **kwargs):
            return {
                "input_ids": torch.tensor([[7, 8, 9]]),
                "attention_mask": torch.tensor([[1, 1, 1]]),
            }

    collator = VisualCollator(CallableProcessor(), page_processor=CountingProcessor())
    example = {
        "messages": [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
        ],
        "images": [],
    }
    batch = collator([example])
    assert batch["labels"][0, :2].tolist() == [-100, -100]
    assert batch["labels"][0, 2].item() == 9
    assert calls == [(2, [])]


def _write_cell(tmp_path, protocol, context, modality, *, tamper_receipt=False):
    source = tmp_path / "membership.json"
    source.write_text("{}")
    source_manifest = branch._source_manifest(tmp_path, [source])
    output = branch.training_root(tmp_path, protocol, modality)
    final = output / "final"
    final.mkdir(parents=True)
    init = {f"key-{i}": torch.zeros(1) for i in range(branch.EXPECTED_ADAPTER_TENSORS)}
    changed = {f"key-{i}": torch.ones(1) for i in range(branch.EXPECTED_ADAPTER_TENSORS)}
    save_file(init, output / branch.FRESH_INIT_FILE)
    save_file(changed, final / "adapter_model.safetensors")
    (final / "adapter_config.json").write_text(
        json.dumps(
            {
                "r": 64,
                "lora_alpha": 128,
                "lora_dropout": 0.05,
                "exclude_modules": protocol["training"]["lora_exclude_modules"],
                "bias": "none",
                "task_type": "CAUSAL_LM",
            }
        )
    )
    state = {"global_step": 16, "log_history": [{"loss": 1.0, "step": 16}]}
    (output / "training_state.json").write_text(json.dumps(state))
    receipt = branch._receipt(
        tmp_path,
        protocol,
        modality=modality,
        source_manifest=source_manifest,
        final=final,
        init_tensor=output / branch.FRESH_INIT_FILE,
        state=state,
        wall_seconds=1.0,
        cpu_seconds=0.5,
    )
    if tamper_receipt:
        receipt["ordered_training_record_ids_sha256"] = "sha256:wrong"
    write_path = output / branch.RECEIPT_FILE
    write_path.write_text(json.dumps(receipt))
    report = branch._build_report(
        tmp_path,
        protocol,
        modality=modality,
        source_before=source_manifest,
        source_after=source_manifest,
        output=output,
        state=state,
        runtime={"runtime_head": "head", "cuda_visible_devices": "0", "master_port": 18800, "elapsed_seconds": 1.0},
        recovered=False,
    )
    (output / "report.json").write_text(json.dumps(report))
    return output


def test_training_cell_verify_accepts_and_rejects_tampering(tmp_path):
    protocol = fake_protocol(tmp_path)
    source = tmp_path / "membership.json"
    source.write_text("{}")
    context = {"source_files": [source]}
    output = _write_cell(tmp_path, protocol, context, "text-state")
    result = branch.verify_training_cell(tmp_path, protocol, context, modality="text-state")
    assert result["changed_parameter_tensors"] == result["parameter_tensors"] == 504
    report = json.loads((output / "report.json").read_text())
    report["training_record_ids"] = list(reversed(report["training_record_ids"]))
    (output / "report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError):
        branch.verify_training_cell(tmp_path, protocol, context, modality="text-state")

    tampered = _write_cell(tmp_path, protocol, context, "visual-state")
    receipt_path = tampered / branch.RECEIPT_FILE
    receipt = json.loads(receipt_path.read_text())
    receipt["fresh_lora_init_sha256"] = "sha256:wrong"
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="receipt"):
        branch.verify_training_cell(tmp_path, protocol, context, modality="visual-state")


def test_crash_recovery_requires_valid_receipt(tmp_path, monkeypatch):
    protocol = fake_protocol(tmp_path)
    source = tmp_path / "membership.json"
    source.write_text("{}")
    context = {"source_files": [source]}
    modality = "text-state"
    output = _write_cell(tmp_path, protocol, context, modality)
    (output / "report.json").unlink()
    marker = {
        "schema_version": "expanded_second_backbone_training_recovery_v1",
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "source_manifest_before": branch._source_manifest(tmp_path, [source]),
        "runtime_head": "head",
        "cuda_visible_devices": "0",
        "master_port": 18800,
    }
    (output / branch.RECOVERY_FILE).write_text(json.dumps(marker))

    class StubDataset:
        def __init__(self):
            self.records = [{"record_id": record_id} for record_id in protocol["source_record_ids"]]

        def __len__(self):
            return 512

    monkeypatch.setattr(
        "examples.planning_benchmark_slice.visual_model.VisualDataset", lambda *args, **kwargs: StubDataset()
    )
    report = branch.train_cell(
        tmp_path, protocol, context, modality=modality, progress=lambda **kwargs: pytest.fail("retrained")
    )
    assert report["recovered_without_retrain"] is True
    (output / "report.json").unlink()
    (output / branch.RECOVERY_FILE).write_text(json.dumps(marker))
    (output / branch.RECEIPT_FILE).unlink()
    with pytest.raises(ValueError, match="completion receipt"):
        branch.train_cell(tmp_path, protocol, context, modality=modality, progress=lambda **kwargs: None)


def test_admission_arithmetic_l0_l1_and_valid_stop():
    protocol = fake_protocol(Path("."))
    qualification = {"outcome": "PASS", "complete": True}
    costs = [{"bfs": {"decisions": 10 + index, "expansions": 5}} for index in range(24)]
    task_ids = [f"task/{index}" for index in range(24)]

    def probe(step_seconds, latency):
        return {
            "outcome": "PASS",
            "probe_gpu_hours": 0.5,
            "training_step": {modality: {"wall_seconds": step_seconds} for modality in protocol["modalities"]},
            "throughput": {modality: {"latency_seconds": {"p95": latency}} for modality in protocol["modalities"]},
        }

    result = branch.decide_admission(
        protocol, qualification, probe(1.0, 0.1), branch_spent_gpu_hours=0.5, panel_task_costs=costs,
        panel_task_ids=task_ids,
    )
    assert result["decision"] == "L0" and result["outcome"] == "PASS"
    assert result["ledger_mutated"] is False
    assert result["arithmetic"]["L0"]["fits_branch_remainder"] is True
    assert result["reduced_scope"] is None
    assert result["authorized_scope"]["decision"] == "L0"
    assert result["authorized_scope"]["task_ids"] == task_ids
    assert result["authorized_scope"]["model_episodes"] == 144
    assert result["authorized_scope"]["comparator_episodes"] == 144
    training_hours = 3 * 1.0 * 16 / 3600
    assert result["arithmetic"]["L0"]["training_gpu_hours"] == pytest.approx(training_hours)

    huge = branch.decide_admission(
        protocol, qualification, probe(100.0, 50.0), branch_spent_gpu_hours=0.5, panel_task_costs=costs,
        panel_task_ids=task_ids,
    )
    assert huge["arithmetic"]["L0"]["fits_branch_remainder"] is False
    if huge["arithmetic"]["L1"]["fits_branch_remainder"]:
        assert huge["decision"] == "L1"
        assert "reference bfs decision count" in huge["reduced_scope"]
        assert huge["authorized_scope"]["decision"] == "L1"
        assert huge["authorized_scope"]["task_ids"] == task_ids[:12]
        assert huge["authorized_scope"]["model_episodes"] == 72
    else:
        assert huge["decision"] == "L2" and huge["outcome"] == "VALID_STOP"
        assert huge["authorized_scope"] is None


def test_admission_gate_admits_full_or_reduced_pass(tmp_path):
    protocol = fake_protocol(tmp_path)
    protocol["output_root"] = "out"
    root = tmp_path / "root"
    admission_dir = root / protocol["output_root"]
    admission_dir.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="has not run"):
        branch.require_admission_gate(root, protocol)
    base = {
        "schema_version": branch.ADMISSION_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "outcome": "PASS",
        "decision": "L0",
        "ledger_mutated": False,
        "authorized_scope": {"decision": "L0", "task_ids": ["task/0"], "model_episodes": 6},
    }
    for mutation in (
        {"outcome": "VALID_STOP"},
        {"decision": "L2"},
        {"decision": "L1"},
        {"protocol_id": "other"},
        {"authorized_scope": None},
        {"authorized_scope": {"decision": "L1", "task_ids": ["task/0"], "model_episodes": 6}},
    ):
        (admission_dir / "admission.json").write_text(json.dumps({**base, **mutation}))
        with pytest.raises(RuntimeError, match="did not authorize execution"):
            branch.require_admission_gate(root, protocol)
    (admission_dir / "admission.json").write_text(json.dumps(base))
    assert branch.require_admission_gate(root, protocol)["decision"] == "L0"
    reduced = {
        **base,
        "decision": "L1",
        "authorized_scope": {"decision": "L1", "task_ids": ["task/0", "task/2"], "model_episodes": 12},
    }
    (admission_dir / "admission.json").write_text(json.dumps(reduced))
    assert branch.require_admission_gate(root, protocol)["decision"] == "L1"


def test_authorized_panel_tasks_filters_to_admission_scope(tmp_path):
    protocol = fake_protocol(tmp_path)
    protocol["output_root"] = "out"
    root = tmp_path / "root"
    admission_dir = root / protocol["output_root"]
    admission_dir.mkdir(parents=True)
    panel_tasks = [{"row": {"task_id": f"task/{index}"}} for index in range(4)]
    admission = {
        "schema_version": branch.ADMISSION_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "outcome": "PASS",
        "decision": "L1",
        "ledger_mutated": False,
        "authorized_scope": {
            "decision": "L1",
            "task_ids": ["task/3", "task/1"],
            "model_episodes": 12,
            "comparator_episodes": 12,
        },
    }
    (admission_dir / "admission.json").write_text(json.dumps(admission))
    selected = branch.authorized_panel_tasks(root, protocol, panel_tasks)
    assert [task["row"]["task_id"] for task in selected] == ["task/1", "task/3"]
    admission["authorized_scope"]["model_episodes"] = 144
    (admission_dir / "admission.json").write_text(json.dumps(admission))
    with pytest.raises(ValueError, match="episode count differs"):
        branch.authorized_panel_tasks(root, protocol, panel_tasks)


def test_repository_job_configs_and_worker_environment(monkeypatch):
    expected = {
        "second-backbone-qualify-job.json": ("second-backbone-qualify", [], "qualify-inputs", "audit-qualify", 1560),
        "second-backbone-probe-job.json": ("second-backbone-probe", [0], "probe", "audit-probe", 1),
        "second-backbone-train-0-job.json": ("second-backbone-train-0", [0], "run", "audit-training-worker", 1024),
        "second-backbone-train-1-job.json": ("second-backbone-train-1", [1], "run", "audit-training-worker", 512),
        "second-backbone-train-final-job.json": (
            "second-backbone-train-final",
            [],
            "finalize-training",
            "audit-training-final",
            3,
        ),
        "second-backbone-evaluate-0-job.json": (
            "second-backbone-evaluate-0",
            [0],
            "evaluate",
            "audit-evaluate-worker",
            72,
        ),
        "second-backbone-evaluate-1-job.json": (
            "second-backbone-evaluate-1",
            [1],
            "evaluate",
            "audit-evaluate-worker",
            72,
        ),
        "second-backbone-audit-final-job.json": (
            "second-backbone-audit-final",
            [],
            "finalize-evaluation",
            "audit-final",
            144,
        ),
    }
    for name, (job_id, gpus, command, hook, total) in expected.items():
        job = json.loads((ROOT / "configs/experiments/expanded-study" / name).read_text())
        assert job["job_id"] == job_id
        assert job["branch"] == "second_backbone"
        assert job["gpus"] == gpus
        assert job["command"][1] == "scripts/run_expanded_second_backbone.py"
        assert job["command"][2] == command
        assert job["completion_hook"][2] == hook
        assert job["total"] == total
        assert job["command"][0] == "/home/sukaih/miniconda3/envs/ada_vla/bin/python"
    protocol = repository_protocol()
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setenv("MASTER_PORT", "18800")
    assert runner.require_worker_environment(protocol, 0) == 18800
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1")
    with pytest.raises(ValueError, match="GPU"):
        runner.require_worker_environment(protocol, 0)


class _StubViews:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def observe(self, raw, algorithm, *, modality, pixels=True):
        return {
            "messages": [],
            "images": [],
            "binding": {"state": raw["step"], "input_pages": [], "input_tokens": 1},
        }

    def save(self):
        pass


class _StubSession:
    def __init__(self, root, row, algorithm, arm, seed, output, contract_id, *, views=None):
        self.arm = arm
        self.step = 0
        self.events = []
        self.views = views

    def next_request(self):
        return None if self.step == 2 else SimpleNamespace(model_input={"step": self.step})

    def submit(self, output, binding=None):
        self.events.append(
            {
                "index": len(self.events),
                "input": {"step": self.step},
                "raw_output": output,
                "accepted": True,
                "view": binding,
                "successor_state": None,
            }
        )
        self.step += 1

    def result(self):
        return {
            "invariant_valid_success": True,
            "goal_reached": True,
            "algorithm_invariants_hold": True,
            "decision_count": 2,
            "invalid_operation_count": 0,
            "model_call_limit": 4,
        }


def _bound(protocol, producing):
    bound = dict(protocol)
    bound["_second_backbone_checkpoints"] = {
        modality: f"training/{modality}/final" for modality in protocol["modalities"]
    }
    bound["_second_backbone_fingerprints"] = {
        modality: {"final_checkpoint_sha256": f"sha256:model-{modality}", "final_adapter_config_sha256": "sha256:config"}
        for modality in protocol["modalities"]
    }
    bound["_second_backbone_policy_identity"] = {
        (modality, condition): {"model_id": "model", "adapter_id": condition}
        for modality in protocol["modalities"]
        for condition in branch.MODEL_CONDITIONS
    }
    bound["_producing_attempt"] = producing
    bound["_runtime_head"] = "head"
    return bound


def test_run_cell_deterministic_rounds_grouped_by_adapter(tmp_path, monkeypatch):
    protocol = fake_protocol(tmp_path)
    producing = {"job_id": "second-backbone-evaluate-0", "attempt": 1, "directory": str(tmp_path / "attempt")}
    bound = _bound(protocol, producing)
    names = ("a", "b", "c", "d", "e", "f")
    panel_tasks = [
        {
            "row": {
                "task_id": f"task/{name}",
                "reference_costs": {"bfs": {"decisions": 2, "expansions": 2}},
            }
        }
        for name in names
    ]
    selected = [
        binding for binding in branch.assigned_bindings(protocol, panel_tasks, 0) if binding["modality"] == "text-state"
    ]
    assert len(selected) == 6
    pairs = [
        (binding, next(t for t in panel_tasks if t["row"]["task_id"] == binding["task_id"])) for binding in selected
    ]
    monkeypatch.setattr(branch, "ExpandedTaskViews", _StubViews)
    monkeypatch.setattr(branch, "VisualSession", _StubSession)
    monkeypatch.setattr(branch, "replay_visual_episode", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        branch,
        "backbone_page_processor",
        lambda protocol: SimpleNamespace(count=lambda messages, *, image_sizes=None: 1),
    )
    batches = []

    def generate(examples, adapter_id):
        batches.append((adapter_id, len(examples)))
        return ["output"] * len(examples), [1] * len(examples)

    reports = branch.run_cell(
        tmp_path,
        protocol,
        bound,
        modality="text-state",
        task_bindings=pairs,
        endpoint="unused",
        generate=generate,
        progress=lambda **kwargs: None,
    )
    assert len(reports) == 6
    assert {report["arm"] for report in reports} == {"pretrained_base", "process_sft"}
    assert all(report["producing_attempt"] == producing for report in reports)
    assert all(batch[1] <= 2 for batch in batches)
    assert all(adapter_id in (None, "process_sft") for adapter_id, _ in batches)
    identity = next(report for report in reports if report["arm"] == "process_sft")
    assert identity["schema_version"] == branch.EPISODE_SCHEMA
    assert identity["backbone_key"] == "internvl3_5-8b"
    assert identity["checkpoint"] == "training/text-state/final"
    assert identity["final_checkpoint_sha256"] == "sha256:model-text-state"
    assert identity["policy_identity"]["adapter_id"] == "process_sft"
    base_identity = next(report for report in reports if report["arm"] == "pretrained_base")
    assert base_identity["checkpoint"] is None
    assert base_identity["final_checkpoint_sha256"] is None
    bound_sft = _bound(protocol, producing)
    binding_sft = dict(selected[0], condition="process_sft")
    episode_identity = branch._identity(
        tmp_path, protocol, bound_sft, binding_sft, pairs[0][1], tmp_path / "e.json.gz", tmp_path / "views"
    )
    assert episode_identity["checkpoint"] == "training/text-state/final"
    assert episode_identity["final_checkpoint_sha256"] == "sha256:model-text-state"


def test_form_generation_batches_respects_size_and_token_caps():
    items = ["a", "b", "c", "d"]
    assert branch.form_generation_batches(items, [5, 5, 5, 5], max_batch_size=2, max_batch_input_tokens=10) == [
        ["a", "b"],
        ["c", "d"],
    ]
    assert branch.form_generation_batches(items, [7, 5, 5, 7], max_batch_size=2, max_batch_input_tokens=12) == [
        ["a"],
        ["b", "c"],
        ["d"],
    ]
    assert branch.form_generation_batches(["x"], [13000], max_batch_size=2, max_batch_input_tokens=24000) == [["x"]]
    assert branch.form_generation_batches([], [], max_batch_size=2, max_batch_input_tokens=24000) == []


def test_run_cell_narrows_batches_to_padded_token_cap(tmp_path, monkeypatch):
    protocol = fake_protocol(tmp_path)
    producing = {"job_id": "second-backbone-evaluate-0", "attempt": 1, "directory": str(tmp_path / "attempt")}
    bound = _bound(protocol, producing)
    names = ("a", "b", "c", "d")
    panel_tasks = [
        {"row": {"task_id": f"task/{name}", "reference_costs": {"bfs": {"decisions": 2, "expansions": 2}}}}
        for name in names
    ]
    selected = [
        binding for binding in branch.assigned_bindings(protocol, panel_tasks, 0) if binding["modality"] == "text-state"
    ]
    pairs = [
        (binding, next(t for t in panel_tasks if t["row"]["task_id"] == binding["task_id"])) for binding in selected
    ]
    monkeypatch.setattr(branch, "ExpandedTaskViews", _StubViews)
    monkeypatch.setattr(branch, "VisualSession", _StubSession)
    monkeypatch.setattr(branch, "replay_visual_episode", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        branch,
        "backbone_page_processor",
        lambda protocol: SimpleNamespace(count=lambda messages, *, image_sizes=None: 13000),
    )
    batches = []

    def generate(examples, adapter_id):
        batches.append(len(examples))
        return ["output"] * len(examples), [1] * len(examples)

    reports = branch.run_cell(
        tmp_path,
        protocol,
        bound,
        modality="text-state",
        task_bindings=pairs,
        endpoint="unused",
        generate=generate,
        progress=lambda **kwargs: None,
    )
    assert len(reports) == len(selected)
    assert batches and all(size == 1 for size in batches)


def test_qualify_inputs_records_valid_stop_with_stub_processor(tmp_path, monkeypatch):
    protocol = fake_protocol(tmp_path)
    records = [{"record_id": f"bfs/pair-0:bfs:{index}", "task_id": "pair-0", "state": index} for index in range(3)]

    class StubCorpus:
        def training_example(self, record, modality):
            return {
                "messages": [
                    {"role": "system", "content": "s"},
                    {"role": "user", "content": "u"},
                    {"role": "assistant", "content": "a"},
                ],
                "images": [],
            }

    class StubProcessor:
        def __init__(self):
            self.processor = SimpleNamespace(
                apply_chat_template=lambda *args, **kwargs: "text",
                tokenizer=lambda text: {"input_ids": [1, 2, 3]},
            )
            self.cross_checked = False

        def count(self, messages, *, image_sizes=None):
            return 5 if len(messages) < 3 else 40000

        def verify_complete(self, messages, images):
            self.cross_checked = True

    context = {"records": records, "corpus": StubCorpus(), "panel_tasks": []}
    monkeypatch.setattr(branch, "backbone_page_processor", lambda protocol: StubProcessor())
    monkeypatch.setattr(branch, "frozen_processor", lambda: StubProcessor())
    monkeypatch.setattr(branch, "ExpandedTaskViews", _StubViews)
    result = branch.qualify_inputs(tmp_path, protocol, context)
    assert result["outcome"] == "VALID_STOP"
    assert result["complete"] is True
    assert len(result["violations"]) == 3 * 3
    assert result["tokenizer_identity"] is True
    assert result["maxima"]["text-state"]["train_full"] == 40000
    assert result["maxima"]["text-state"]["train_prefix"] == 5
    on_disk = json.loads((tmp_path / protocol["output_root"] / "qualification" / "qualification.json").read_text())
    assert on_disk["outcome"] == "VALID_STOP"
    assert (tmp_path / protocol["output_root"] / "qualification" / "decision-token-distributions.json.gz").is_file()


def test_analyze_evidence_contrasts_and_cross_backbone(tmp_path):
    protocol = repository_protocol()
    reports = []
    for modality in protocol["modalities"]:
        for index in range(4):
            for condition, success in (
                ("pretrained_base", False),
                ("process_sft", True),
                ("random_valid", True),
                ("exact_reference", True),
            ):
                reports.append(
                    {
                        "panel": branch.PANEL_NAME,
                        "modality": modality,
                        "task_id": f"task/{index}",
                        "arm": condition,
                        "comparison_arm": {
                            "pretrained_base": f"{modality}__base",
                            "process_sft": f"{modality}__sft_sequential_order_control",
                        }.get(condition, f"{modality}__{condition}"),
                        "result": {
                            "invariant_valid_success": success,
                            "goal_reached": success,
                            "algorithm_invariants_hold": True,
                            "decision_count": 2,
                            "invalid_operation_count": 0,
                            "model_call_limit": 4,
                        },
                    }
                )
    paired = branch.paired_rows(reports, {**protocol, "evaluation": {**protocol["evaluation"], "arms": []}})
    evidence = {
        "status": "PASS",
        "paired_rows": paired,
        "by_cell": branch.summarize(reports),
    }
    result = branch.analyze_evidence(ROOT, protocol, evidence)
    assert result["outcome"] == "PASS"
    assert result["paired_units"] == 4
    contrast = next(
        row
        for row in result["contrasts"]
        if row["modality"] == "text-state" and row["contrast"] == "process_sft_minus_pretrained_base"
    )
    assert contrast["interval"]["point"] == pytest.approx(1.0)
    assert len(result["cross_backbone"]) == 3
    assert all(
        "internvl3_5-8b_process_sft_minus_qwen3-vl-8b_process_sft" in row["contrast"] for row in result["cross_backbone"]
    )
    assert result["single_training_seed_limitation"] == protocol["training"]["single_training_seed_limitation"]
    partial = branch.analyze_evidence(
        ROOT, protocol, {"status": "VALID_STOP", "missing_bindings": ["x"], "missing_comparator_bindings": []}
    )
    assert partial["outcome"] == "VALID_STOP"


def test_publish_copies_byte_identical_evidence(tmp_path):
    protocol = fake_protocol(tmp_path)
    qual = {
        "schema_version": branch.QUALIFICATION_SCHEMA,
        "outcome": "PASS",
        "backbone_key": "internvl3_5-8b",
        "complete": True,
        "context_tokens": 32768,
        "output_tokens": 384,
        "records_measured": 1536,
        "tasks_measured": 24,
        "decisions_measured": 100,
        "tokenizer_identity": True,
        "maxima": {"text-state": {"train_prefix": 1, "train_full": 2, "live": 3}},
        "violations": [],
        "cross_checks": [{"modality": "text-state"}],
        "previews": [{"page": 0, "role": "goal", "path": "p.png"}],
    }
    branch.write_json(branch.qualification_root(tmp_path, protocol) / "qualification.json", qual)
    probe = {
        "schema_version": branch.PROBE_SCHEMA,
        "outcome": "PASS",
        "attention": {"requested": "visual_sdpa", "applied": "visual_sdpa", "fallback_used": False},
        "load": {"wall_seconds": 1.0, "vram_bytes_after_load": 1},
        "scalar_batch_parity": {"byte_identical": True},
        "repeated_batch_determinism": {"byte_identical": True},
        "adapter_isolation": {
            "base_vs_adapter_a": True,
            "base_vs_adapter_b": True,
            "adapter_a_vs_adapter_b": True,
            "disable_restores_base": True,
        },
        "token_limit_guards": {
            "near_limit_input_tokens": 1,
            "near_limit_succeeded": True,
            "oversize_batch_raises_valid_stop": True,
        },
        "throughput": {
            modality: {
                "calls": 20,
                "latency_seconds": {"mean": 1.0, "p05": 1.0, "p50": 1.0, "p95": 1.0, "max": 1.0},
                "tokens_per_second": {"mean": 1.0, "lower_95": 1.0},
                "peak_vram_bytes": 1,
            }
            for modality in protocol["modalities"]
        },
        "training_step": {
            modality: {"wall_seconds": 1.0, "microbatches": 32, "peak_vram_bytes": 1}
            for modality in protocol["modalities"]
        },
    }
    branch.write_json(tmp_path / protocol["output_root"] / "probe.json", probe)
    branch.write_json(
        tmp_path / protocol["output_root"] / "admission.json",
        {
            "schema_version": branch.ADMISSION_SCHEMA,
            "decision": "L0",
            "outcome": "PASS",
            "arithmetic": {
                "L0": {
                    "episodes": 144,
                    "training_gpu_hours": 0.1,
                    "evaluation_gpu_hours": 0.1,
                    "safety_factor": 1.25,
                    "required_gpu_hours_including_spent": 0.5,
                    "fits_branch_remainder": True,
                },
                "L1": {
                    "episodes": 72,
                    "training_gpu_hours": 0.1,
                    "evaluation_gpu_hours": 0.05,
                    "safety_factor": 1.25,
                    "required_gpu_hours_including_spent": 0.4,
                    "fits_branch_remainder": True,
                },
            },
            "branch_cap_gpu_hours": 40,
            "branch_spent_gpu_hours": 0.5,
            "branch_remainder_gpu_hours": 39.5,
            "ledger_mutated": False,
        },
    )
    training = {
        "schema_version": branch.TRAINING_REPORT_SCHEMA,
        "outcome": "PASS",
        "fresh_lora_init_identical_all_cells": True,
        "fresh_lora_init": {"sha256": "sha256:init", "parameter_tensors": 504},
        "cells": [
            {
                "modality": modality,
                "records": 512,
                "optimizer_updates": 16,
                "changed_parameter_tensors": 504,
                "parameter_tensors": 504,
                "final_checkpoint_sha256": f"sha256:{modality}",
            }
            for modality in protocol["modalities"]
        ],
    }
    branch.write_json(tmp_path / protocol["output_root"] / "training" / "training-report.json", training)
    evidence = {
        "schema_version": branch.EVIDENCE_SCHEMA,
        "status": "PASS",
        "outcome": "PASS",
        "panel_id": "expanded-panel-v2-qualified",
        "model_episodes": 144,
        "expected_model_episodes": 144,
        "comparator_episodes": 144,
        "expected_comparator_episodes": 144,
        "complete_coverage": True,
        "by_cell": [
            {
                "modality": modality,
                "condition": condition,
                "episodes": 24,
                "invariant_valid_successes": 20,
                "goal_reached": 20,
                "algorithm_invariants_hold": 24,
                "decisions": 100,
                "invalid_operations": 1,
                "invalid_operation_rate": 0.01,
                "model_calls": 100,
                "decision_call_allowance": 200,
            }
            for modality in protocol["modalities"]
            for condition in ("pretrained_base", "process_sft", "random_valid", "exact_reference")
        ],
        "paired_rows": [],
    }
    branch.write_json(branch.evaluation_root(tmp_path, protocol) / "evidence.json", evidence)
    analysis = {
        "schema_version": branch.ANALYSIS_SCHEMA,
        "outcome": "PASS",
        "paired_units": 0,
        "bootstrap": {"seed": 1729, "resamples": 200, "confidence": 0.95},
        "contrasts": [
            {
                "modality": "text-state",
                "contrast": "process_sft_minus_pretrained_base",
                "interval": {"point": 0.5, "lower": 0.0, "upper": 1.0},
            }
        ],
        "cross_backbone": [],
        "by_modality": {},
        "control_saturation": {},
        "random_valid_assistance": "oracle-assisted",
        "single_training_seed_limitation": "one run",
        "architecture_note": "note",
    }
    branch.write_json(branch.evaluation_root(tmp_path, protocol) / "analysis.json", analysis)
    result = branch.publish(tmp_path, protocol)
    docs = tmp_path / branch.DOCS_DIR
    copied = json.loads((docs / "second-backbone-qualification.json").read_text())
    assert copied == qual
    assert (docs / "second-backbone-qualification.md").is_file()
    assert (docs / "second-backbone-probe.md").is_file()
    assert (docs / "second-backbone-training.md").is_file()
    assert (docs / "second-backbone-evaluation.md").is_file()
    assert (docs / "second-backbone-analysis.md").is_file()
    assert len(result["published"]) == 6


def test_publish_admission_valid_stop_terminal_receipt(tmp_path):
    protocol = fake_protocol(tmp_path)
    qual = {
        "schema_version": branch.QUALIFICATION_SCHEMA,
        "outcome": "PASS",
        "backbone_key": "internvl3_5-8b",
        "complete": True,
        "context_tokens": 32768,
        "output_tokens": 384,
        "records_measured": 1536,
        "tasks_measured": 24,
        "decisions_measured": 100,
        "tokenizer_identity": True,
        "maxima": {"text-state": {"train_prefix": 1, "train_full": 2, "live": 3}},
        "violations": [],
        "cross_checks": [{"modality": "text-state"}],
        "previews": [{"page": 0, "role": "goal", "path": "p.png"}],
    }
    branch.write_json(branch.qualification_root(tmp_path, protocol) / "qualification.json", qual)
    probe = {
        "schema_version": branch.PROBE_SCHEMA,
        "outcome": "PASS",
        "attention": {"requested": "visual_sdpa", "applied": "visual_sdpa", "fallback_used": False},
        "load": {"wall_seconds": 1.0, "vram_bytes_after_load": 1},
        "scalar_batch_parity": {"byte_identical": True},
        "repeated_batch_determinism": {"byte_identical": True},
        "adapter_isolation": {
            "base_vs_adapter_a": True,
            "base_vs_adapter_b": True,
            "adapter_a_vs_adapter_b": True,
            "disable_restores_base": True,
        },
        "token_limit_guards": {
            "near_limit_input_tokens": 1,
            "near_limit_succeeded": True,
            "oversize_batch_raises_valid_stop": True,
        },
        "throughput": {
            modality: {
                "calls": 20,
                "latency_seconds": {"mean": 1.0, "p05": 1.0, "p50": 1.0, "p95": 1.0, "max": 1.0},
                "tokens_per_second": {"mean": 1.0, "lower_95": 1.0},
                "peak_vram_bytes": 1,
            }
            for modality in protocol["modalities"]
        },
        "training_step": {
            modality: {"wall_seconds": 1.0, "microbatches": 32, "peak_vram_bytes": 1}
            for modality in protocol["modalities"]
        },
        "probe_gpu_hours": 1.0,
    }
    branch.write_json(tmp_path / protocol["output_root"] / "probe.json", probe)
    admission = {
        "schema_version": branch.ADMISSION_SCHEMA,
        "decision": "L2",
        "outcome": "VALID_STOP",
        "protocol_id": protocol["protocol_id"],
        "branch_cap_gpu_hours": 40,
        "branch_spent_gpu_hours": 4.0,
        "branch_remainder_gpu_hours": 36.0,
        "arithmetic": {
            "L0": {
                "episodes": 144,
                "training_gpu_hours": 2.7,
                "evaluation_gpu_hours": 200.9,
                "safety_factor": 1.25,
                "required_gpu_hours_including_spent": 258.4,
                "fits_branch_remainder": False,
            },
            "L1": {
                "episodes": 72,
                "training_gpu_hours": 2.7,
                "evaluation_gpu_hours": 32.6,
                "safety_factor": 1.25,
                "required_gpu_hours_including_spent": 48.1,
                "fits_branch_remainder": False,
            },
        },
        "calls_per_episode_basis": "2 x reference bfs decisions per task (the frozen decision-call allowance)",
        "reduced_scope": None,
        "authorized_scope": None,
        "ledger_mutated": False,
    }
    branch.write_json(tmp_path / protocol["output_root"] / "admission.json", admission)
    branch.write_json(
        tmp_path / branch.LEDGER_PATH,
        {
            "attempts": [
                {
                    "branch": "second_backbone",
                    "job_id": "second-backbone-probe",
                    "status": "succeeded",
                    "gpu_hours": 4.0,
                },
                {"branch": "expanded_baseline", "job_id": "baseline-models-0", "status": "succeeded", "gpu_hours": 40.0},
                {"branch": "transfer", "job_id": "transfer-probe", "status": "reserved", "gpu_hours": 0.0},
            ]
        },
    )
    branch.write_json(tmp_path / branch.SCHEDULE_DOC, {"gpu_cutoff_utc": "2026-09-21T11:55:19Z"})
    result = branch.publish(tmp_path, protocol)
    docs = tmp_path / branch.DOCS_DIR
    assert len(result["published"]) == 4
    receipt = docs / "second-backbone-valid-stop.md"
    assert receipt.is_file()
    text = receipt.read_text()
    assert "VALID_STOP" in text and "L2" in text
    assert "48.10" in text and "remainder 36.0000" in text  # values come from the fixture admission
    assert "44.0000 / 336 GPU-h" in text  # reserved attempts excluded from the cumulative
    assert not (docs / "second-backbone-training.md").exists()
    assert not (docs / "second-backbone-evaluation.md").exists()
    assert not (docs / "second-backbone-analysis.md").exists()
