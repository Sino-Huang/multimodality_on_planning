"""CPU-only evaluation and analysis tests for expanded curriculum."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
from safetensors.torch import save_file

from examples.planning_benchmark_slice import expanded_curriculum_evaluation as evaluation
from examples.planning_benchmark_slice.expanded_curriculum_analysis import analyze
from examples.planning_benchmark_slice.expanded_successor_training import _sha256
from scripts import run_expanded_curriculum_evaluation as runner

ROOT = Path(__file__).resolve().parents[2]


def protocol(tmp_path=None):
    modalities = ["text-state", "visual-state", "multimodal-state"]
    orderings = ("staged", "shuffled", "mixed_order")
    return {
        "protocol_id": "test-curriculum",
        "algorithm": "best_first_add_greedy",
        "modalities": modalities,
        "orderings": {name: {} for name in orderings},
        "output_root": "curriculum",
        "base_model": {"model_id": "model", "revision": "rev"},
        "training": {
            "records_per_cell": 512,
            "optimizer_updates": 16,
            "context_tokens": 32768,
            "maximum_input_tokens": 32384,
            "output_tokens": 384,
        },
        "evaluation": {
            "seed": 17,
            "arms": [{"arm": f"{m}__{o}", "training_modality": m, "ordering": o} for m in modalities for o in orderings],
        },
        "views": {"scene_views": "scene.json"},
        "analysis": {
            "bootstrap_seed": 1729,
            "bootstrap_resamples": 200,
            "confidence": 0.95,
            "materiality_margin": 0.05,
            "historical_issue67": {"result": "old.json", "documentation": "old.md", "pooled": False},
        },
        "launch": {
            "devices": [0, 1],
            "master_port_pool": [18800, 18801],
            "evaluation_worker_modalities": {"0": ["text-state", "multimodal-state"], "1": ["visual-state"]},
            "backend_endpoints": ["a", "b"],
        },
    }


def write_training_gate(tmp_path, p):
    cells = []
    for row in p["evaluation"]["arms"]:
        final = tmp_path / p["output_root"] / "training" / row["training_modality"] / row["ordering"] / "final"
        final.mkdir(parents=True)
        save_file({"a": torch.ones(1)}, final / "adapter_model.safetensors")
        (final / "adapter_config.json").write_text("{}")
        cells.append(
            {
                "outcome": "PASS",
                "modality": row["training_modality"],
                "ordering": row["ordering"],
                "arm": row["arm"],
                "records": 512,
                "optimizer_updates": 16,
                "final_checkpoint": str(final.relative_to(tmp_path)),
                "final_checkpoint_sha256": _sha256(final / "adapter_model.safetensors"),
                "final_adapter_config_sha256": _sha256(final / "adapter_config.json"),
                "fresh_lora_init_sha256": "sha256:init",
                "fresh_lora_init_tensors": 1,
            }
        )
    report = {
        "schema_version": "expanded_curriculum_training_report_v1",
        "status": "PASS",
        "outcome": "PASS",
        "protocol_id": p["protocol_id"],
        "same_record_set_all_cells": True,
        "exact_protocol_orders_all_cells": True,
        "fresh_lora_init_identical_all_cells": True,
        "fresh_lora_init": {"sha256": "sha256:init", "parameter_tensors": 1},
        "cells": cells,
    }
    path = tmp_path / p["output_root"] / "training" / "training-report.json"
    path.write_text(json.dumps(report))
    return report


def test_training_gate_binds_all_nine_fingerprints(tmp_path):
    p = protocol()
    write_training_gate(tmp_path, p)
    bound, report = runner.require_training_gate(tmp_path, p)
    assert report["status"] == "PASS" and len(bound["_curriculum_checkpoints"]) == 9
    first = next(iter(bound["_curriculum_fingerprints"].values()))
    assert first["final_checkpoint_sha256"].startswith("sha256:")
    report["cells"][0]["final_checkpoint_sha256"] = "sha256:wrong"
    (tmp_path / p["output_root"] / "training" / "training-report.json").write_text(json.dumps(report))
    with pytest.raises(RuntimeError, match="fingerprint"):
        runner.require_training_gate(tmp_path, p)


def test_repository_comparator_sources_bind_goal3_audits_and_checkpoint_hashes():
    p = json.loads((ROOT / "configs/experiments/expanded-study/curriculum-protocol.json").read_text())
    result = evaluation.validate_comparator_sources(ROOT, p)
    assert result["goal3_evidence_sha256"] == p["evaluation"]["comparator_audit"]["goal3_evidence_sha256"]
    assert set(result["process_sft"]) == set(p["modalities"])


class Views:
    def observe(self, raw, algorithm, *, modality, pixels=True):
        return {"messages": [], "images": [], "binding": {"state": raw["step"], "input_tokens": 1}}

    def save(self):
        pass


class Session:
    def __init__(self, root, row, algorithm, arm, seed, output, contract, *, views):
        self.row = row
        self.algorithm = algorithm
        self.step = 0
        self.events = []
        self.views = views

    def next_request(self):
        return None if self.step == 2 else SimpleNamespace(model_input={"step": self.step})

    def submit(self, output, binding):
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


def test_run_cell_uses_deterministic_task_rounds(tmp_path, monkeypatch):
    p = protocol()
    arm = p["evaluation"]["arms"][0]["arm"]
    p["_curriculum_checkpoints"] = {arm: "checkpoint"}
    p["_curriculum_fingerprints"] = {
        arm: {"final_checkpoint_sha256": "sha256:a", "final_adapter_config_sha256": "sha256:b"}
    }
    producing = {"job_id": "curriculum-evaluate-0", "attempt": 1, "directory": str(tmp_path / "attempt")}
    p["_producing_attempt"] = producing
    p["_runtime_head"] = "head"
    p["_curriculum_policy_identity"] = {arm: {"model_id": "model", "adapter_id": arm}}
    p["_valid_producing_attempts"] = {(producing["job_id"], producing["attempt"], producing["directory"]): "succeeded"}
    tasks = [{"row": {"task_id": name}} for name in ("task/a", "task/b", "task/c")]
    monkeypatch.setattr(evaluation, "_views", lambda *args, **kwargs: Views())
    monkeypatch.setattr(evaluation, "VisualSession", Session)
    monkeypatch.setattr(evaluation, "replay_visual_episode", lambda root, row, report, views: report["result"])
    batches = []

    def generate(examples):
        batches.append(len(examples))
        return ["output"] * len(examples), [1] * len(examples)

    reports = evaluation.run_cell(
        tmp_path,
        p,
        panel="development",
        modality="text-state",
        arm=arm,
        tasks=tasks,
        endpoint="unused",
        generate=generate,
        progress=lambda **kwargs: None,
    )
    assert len(reports) == 3 and batches == [2, 1, 2, 1]
    verified = evaluation.verify_episode(tmp_path, p, "development", "text-state", tasks[0], arm, "unused")
    assert verified["result"]["invariant_valid_success"] is True
    retained_path = evaluation.episode_path(tmp_path, p, "development", "text-state", "task/a", arm)
    retained = evaluation.read_json(retained_path)
    retained["call_measurements"][0]["input_tokens"] = p["training"]["maximum_input_tokens"] + 1
    evaluation.write_json(retained_path, retained)
    with pytest.raises(ValueError, match="accounting"):
        evaluation.verify_episode(tmp_path, p, "development", "text-state", tasks[0], arm, "unused")


def test_real_best_first_session_maps_curriculum_arm_for_run_and_replay(tmp_path):
    """Previous run-cell tests mocked VisualSession and missed the historical arm whitelist."""
    p = protocol()
    arm = "text-state__staged"
    task_file = tmp_path / "task.json"
    task_file.write_text(
        json.dumps(
            {
                "domain_pddl": """(define (domain tiny) (:requirements :strips)
                (:predicates (at ?x)) (:action stay :parameters (?x)
                :precondition (at ?x) :effect (at ?x)))""",
                "problem_pddl": """(define (problem tiny-p) (:domain tiny)
                (:objects a) (:init (at a)) (:goal (at a)))""",
            }
        )
    )
    task = {
        "row": {
            "task_id": "tiny/task",
            "domain": "tiny",
            "difficulty": "easy",
            "task_path": "task.json",
            "trace_paths": {},
            "reference_costs": {"best_first_add_greedy": {"decisions": 1, "expansions": 1}},
        }
    }
    output = tmp_path / "episode.json"
    session = evaluation._curriculum_session(tmp_path, p, task, arm, output)
    assert session.arm == session.session.arm == "process_sft"
    assert session.session.adapter_id == arm
    assert session.session.session_id.startswith(f"process_sft:{arm}:17:")
    assert session.next_request() is None
    report = {
        "output": "episode.json",
        "algorithm": p["algorithm"],
        "arm": arm,
        "comparison_arm": arm,
        "behavior_arm": "process_sft",
        "adapter_id": arm,
        "modality": "text-state",
        "seed": 17,
        "events": [],
        "result": session.result(),
    }
    assert evaluation._replay_curriculum_episode(tmp_path, p, task, arm, report, None) == report["result"]
    p["_curriculum_checkpoints"] = {arm: "checkpoint"}
    p["_curriculum_fingerprints"] = {
        arm: {"final_checkpoint_sha256": "sha256:a", "final_adapter_config_sha256": "sha256:b"}
    }
    p["_producing_attempt"] = {"job_id": "job", "attempt": 2, "directory": "attempt"}
    p["_runtime_head"] = "head"
    p["_curriculum_policy_identity"] = {arm: {"adapter_id": arm}}
    identity = evaluation._identity(
        tmp_path,
        p,
        "development",
        "text-state",
        task,
        arm,
        output,
        tmp_path / "views",
    )
    assert identity["arm"] == identity["comparison_arm"] == identity["adapter_id"] == arm
    assert identity["behavior_arm"] == "process_sft"


def paired_rows(saturated=False):
    arms = [
        f"{m}__{o}"
        for m in ("text-state", "visual-state", "multimodal-state")
        for o in ("staged", "shuffled", "mixed_order")
    ]
    rows = []
    for index in range(6):
        values = {}
        for arm in arms:
            success = True if saturated else (arm.endswith("__staged") and index < 5)
            values[arm] = {
                "invariant_valid_success": success,
                "goal_reached": success,
                "invalid_operations": 0,
                "decisions": 1,
            }
        for modality in ("text-state", "visual-state", "multimodal-state"):
            for control in ("base", "sft_sequential_order_control", "random_valid", "exact_reference"):
                arm = f"{modality}__{control}"
                values[arm] = {
                    "invariant_valid_success": control == "exact_reference",
                    "goal_reached": control == "exact_reference",
                    "invalid_operations": 0,
                    "decisions": 1,
                }
        rows.append({"panel": "unseen", "task_id": f"task-{index}", "arms": values})
    return rows


def test_analysis_known_effect_and_saturated_conclusion():
    p = protocol()
    result = analyze(p, {"paired_rows": paired_rows()})
    staged = next(
        row
        for row in result["ordering_main_effect_by_modality"]
        if row["modality"] == "text-state" and row["contrast"] == "staged_minus_shuffled"
    )
    assert (
        staged["interval"]["point"] == pytest.approx(5 / 6)
        and not result["control_saturation"]["all_curriculum_arms_saturated"]
    )
    saturated = analyze(p, {"paired_rows": paired_rows(saturated=True)})
    assert saturated["control_saturation"]["all_curriculum_arms_saturated"]
    assert saturated["control_saturation"]["all_comparator_controls_saturated"] is False
    assert "comparator controls did not all saturate" in saturated["control_saturation"]["conclusion"]
    assert set(saturated["control_saturation"]["controls_by_modality"]["text-state"]) == {
        "base",
        "sft_sequential_order_control",
        "random_valid",
        "exact_reference",
    }


def test_paired_rows_collapse_matched_modalities_to_27_units():
    p = protocol()
    reports = []
    tasks = [("development", f"dev-{index}") for index in range(3)] + [
        ("unseen", f"unseen-{index}") for index in range(24)
    ]
    for panel, task_id in tasks:
        for arm_row in p["evaluation"]["arms"]:
            reports.append(
                {
                    "panel": panel,
                    "modality": arm_row["training_modality"],
                    "task_id": task_id,
                    "comparison_arm": arm_row["arm"],
                    "result": {
                        "invariant_valid_success": True,
                        "goal_reached": True,
                        "invalid_operation_count": 0,
                        "decision_count": 1,
                    },
                }
            )
        for modality in p["modalities"]:
            for control in evaluation.COMPARATORS:
                reports.append(
                    {
                        "panel": panel,
                        "modality": modality,
                        "task_id": task_id,
                        "comparison_arm": f"{modality}__{control}",
                        "result": {
                            "invariant_valid_success": True,
                            "goal_reached": True,
                            "invalid_operation_count": 0,
                            "decision_count": 1,
                        },
                    }
                )
    rows = evaluation.paired_rows(reports, p)
    assert len(rows) == 27
    assert all(len(row["arms"]) == 21 for row in rows)


def test_comparator_reuse_binds_contract_model_checkpoint_and_fingerprint(tmp_path, monkeypatch):
    p = protocol()
    checkpoint = tmp_path / "control-final"
    checkpoint.mkdir()
    save_file({"a": torch.ones(1)}, checkpoint / "adapter_model.safetensors")
    (checkpoint / "adapter_config.json").write_text("{}")
    p["source_study"] = "study.json"
    (tmp_path / "study.json").write_text(json.dumps({"output_root": "matched"}))
    p["evaluation"]["comparator_audit"] = {
        "development_contract_id": "matched-modalities-v5",
        "unseen_protocol_id": "expanded-matched-baseline-v1",
        "process_sft": {
            "text-state": {
                "checkpoint": str(checkpoint.relative_to(tmp_path)),
                "adapter_model_sha256": _sha256(checkpoint / "adapter_model.safetensors"),
                "adapter_config_sha256": _sha256(checkpoint / "adapter_config.json"),
            }
        },
    }
    task = {"row": {"task_id": "task/a"}}
    monkeypatch.setattr(evaluation, "_views", lambda *args, **kwargs: Views())
    monkeypatch.setattr(evaluation, "replay_visual_episode", lambda *args, **kwargs: {})
    for label, retained, retained_checkpoint in (
        ("base", "pretrained_base", None),
        ("sft_sequential_order_control", "process_sft", str(checkpoint.relative_to(tmp_path))),
        ("random_valid", "random_valid", None),
        ("exact_reference", "exact_reference", None),
    ):
        path = evaluation.comparator_path(tmp_path, "development", "text-state", "task/a", retained)
        report = {
            "contract_id": "matched-modalities-v5",
            "task_id": "task/a",
            "modality": "text-state",
            "algorithm": "best_first_add_greedy",
            "arm": retained,
            "seed": 17,
            "model_id": "model",
            "model_revision": "rev",
            "checkpoint": retained_checkpoint,
            "result": {},
        }
        evaluation.write_json(path, report)
        verified = evaluation.verify_comparator(tmp_path, p, "development", "text-state", task, label, "unused")
        assert verified["comparison_arm"] == f"text-state__{label}"
    report["contract_id"] = "wrong"
    evaluation.write_json(path, report)
    with pytest.raises(ValueError, match="panel binding"):
        evaluation.verify_comparator(tmp_path, p, "development", "text-state", task, "exact_reference", "unused")


def test_partial_evidence_is_valid_stop_with_explicit_missing_bindings(monkeypatch):
    p = protocol()
    attempts = [
        {
            "job_id": f"curriculum-evaluate-{worker}",
            "attempt": 1,
            "directory": name,
            "gpus": [worker],
            "master_port": 18800 + worker,
            "gpu_hours": 0.1,
        }
        for worker, name in enumerate(("a", "b"))
    ]
    monkeypatch.setattr(runner, "panels", lambda root, protocol: {"development": [], "unseen": []})
    monkeypatch.setattr(
        runner,
        "_verify_worker_paths",
        lambda protocol, worker, attempt: ([], [f"missing-{worker}"], {}),
    )
    monkeypatch.setattr(runner, "require_training_gate", lambda root, protocol: (dict(protocol), {}))
    monkeypatch.setattr(runner, "validate_comparator_sources", lambda root, protocol: {"outcome": "PASS"})
    evidence = runner._evidence(p, attempts)
    assert evidence["status"] == evidence["outcome"] == "VALID_STOP"
    assert evidence["coverage"]["missing_bindings"] == ["missing-0", "missing-1"]
    assert evidence["paired_rows"] == []


def test_scheduler_attempt_terminal_hook_gpu_and_port_provenance(tmp_path, monkeypatch):
    p = protocol()
    attempts = []
    for worker in range(2):
        directory = tmp_path / "jobs" / f"curriculum-evaluate-{worker}" / "1"
        directory.mkdir(parents=True)
        attempt = {
            "job_id": f"curriculum-evaluate-{worker}",
            "attempt": 1,
            "branch": "curriculum_modality",
            "status": "succeeded",
            "directory": str(directory),
            "gpus": [worker],
            "master_port": 18800 + worker,
            "gpu_hours": 0.1,
            "command": [
                "python",
                "scripts/run_expanded_curriculum_evaluation.py",
                "run",
                "--worker",
                str(worker),
            ],
        }
        attempts.append(attempt)
        (directory / "terminal.json").write_text(
            json.dumps(
                {
                    "status": "succeeded",
                    "gpus": [worker],
                    "master_port": 18800 + worker,
                }
            )
        )
        (directory / "hook-result.json").write_text(json.dumps({"returncode": 0}))
        (directory / "independent-replay.json").write_text(json.dumps({"outcome": "PASS", "worker": worker}))
    ledger = tmp_path / "outputs/expanded-study/v1/budget.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({"attempts": attempts}))
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    bound, rows = runner._recorded_attempts(p)
    assert len(bound["_valid_producing_attempts"]) == len(rows) == 2
    assert runner._evaluation_attempts(p) == attempts


def test_audit_final_requires_byte_equal_evidence(tmp_path, monkeypatch):
    p = protocol()
    evidence = {
        "schema_version": "expanded_curriculum_evaluation_evidence_v1",
        "status": "PASS",
        "coverage": {"model_episodes": 243},
    }
    path = tmp_path / p["output_root"] / "evaluation" / "evidence.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(evidence))
    analysis = {"schema_version": "expanded_curriculum_analysis_v1", "outcome": "PASS"}
    (path.parent / "analysis.json").write_text(json.dumps(analysis))
    terminal = tmp_path / "terminal.json"
    terminal.write_text(json.dumps({"status": "succeeded"}))
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    attempts = [{"job_id": "a"}, {"job_id": "b"}]
    monkeypatch.setattr(runner, "_evaluation_attempts", lambda protocol: attempts)
    monkeypatch.setattr(runner, "_evidence", lambda protocol, actual_attempts: evidence)
    monkeypatch.setattr(runner, "analyze", lambda protocol, actual: analysis)
    monkeypatch.setenv("EXPANDED_TERMINAL_PATH", str(terminal))
    runner.audit_final(p)
    path.write_text(json.dumps({"status": "FAIL"}))
    with pytest.raises(ValueError, match="scheduler-bound replay"):
        runner.audit_final(p)
