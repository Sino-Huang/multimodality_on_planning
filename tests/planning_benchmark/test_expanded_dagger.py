"""Goal 4 DAgger correction and protocol tests use trusted CPU runtime only."""

import copy
import json
from pathlib import Path

import pytest

from examples.planning_benchmark_slice import expanded_dagger_collection as collection
from examples.planning_benchmark_slice.expanded_dagger import (
    DaggerBFSSession,
    aggregate_update,
    certify_corrections,
    replay_dagger_episode,
    validate_protocol,
)
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read
from examples.planning_benchmark_slice.modality_corpus_replay import canonical
from examples.planning_benchmark_slice.visual_episode import VisualSession

DOMAIN = """(define (domain rooms) (:requirements :strips) (:predicates (at ?x) (link ?x ?y))
(:action move :parameters (?x ?y) :precondition (and (at ?x) (link ?x ?y))
:effect (and (not (at ?x)) (at ?y))))"""
PROBLEM = """(define (problem rooms-p) (:domain rooms) (:objects a b c d)
(:init (at a) (link a b) (link a c) (link b d) (link c d)) (:goal (at d)))"""


def protocol(task_id="tiny/train-task", source_ids=None):
    return {
        "protocol_id": "test-dagger",
        "modalities": ["text-state", "visual-state", "multimodal-state"],
        "iterations": [1, 2],
        "starting_checkpoints": {"text-state": "start"},
        "checkpoint_lineage": {"dagger_iteration_1": "iteration-1/{modality}"},
        "collection": {
            "task_order": [task_id],
            "max_corrections_per_modality_iteration": 128,
        },
        "views": {"serializer": "scene-only-128-unlabelled-v1"},
        "model": {"output_tokens": 384},
        "source_record_ids": source_ids or [],
        "training": {"records_per_update": 512, "optimizer_updates": 16, "seed": 17},
    }


def session(tmp_path: Path):
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"domain_pddl": DOMAIN, "problem_pddl": PROBLEM}))
    row = {
        "task_id": "tiny/train-task",
        "domain": "rooms",
        "difficulty": "easy",
        "task_path": "task.json",
        "trace_paths": {},
        "reference_costs": {"bfs": {"decisions": 10, "expansions": 10}},
    }
    return VisualSession(tmp_path, row, "bfs", "process_sft", 17, tmp_path / "episode", "test")


def test_invalid_student_is_not_applied_and_expert_uses_exact_last_valid_input(tmp_path):
    p = protocol()
    wrapper = DaggerBFSSession(
        session(tmp_path),
        p,
        task_id="tiny/train-task",
        split="train",
        modality="text-state",
        iteration=1,
        starting_checkpoint="start",
    )
    request = wrapper.next_request()
    before = wrapper.session.session.context.memory.to_bytes()
    decision = wrapper.submit_student("not json")
    correction = decision["correction"]
    assert correction["student_raw_output"] == "not json"
    assert correction["strict_parse_result"]["status"] == "rejected"
    assert correction["trusted_runtime_result"]["status"] == "not_run"
    assert correction["expert_query"]["model_input"] == request.model_input
    assert correction["expert_query"]["view"] == request.example["binding"]
    assert correction["expert_query"]["trusted_runtime_result"]["status"] == "accepted"
    assert correction["invalid_operation_charge"] == correction["expert_query_charge"] == 1
    assert canonical(json.loads(before)) == canonical(correction["last_valid_search_memory"])
    assert decision["applied_operation_source"] == "expert_correction"
    assert wrapper.session.session.invalid_operation_count == 0
    report = wrapper.finish("collection_decision_quota")

    replayed = replay_dagger_episode(report, p, session(tmp_path))
    assert replayed == report
    hidden_teacher = copy.deepcopy(report)
    hidden_teacher["decisions"][0]["student_input"]["teacher_operation"] = {"hidden": True}
    hidden_teacher["decisions"][0]["correction"]["student_input"] = hidden_teacher["decisions"][0][
        "student_input"
    ]
    hidden_teacher["decisions"][0]["correction"]["expert_query"]["model_input"] = hidden_teacher["decisions"][
        0
    ]["student_input"]
    with pytest.raises(ValueError, match="input differs"):
        replay_dagger_episode(hidden_teacher, p, session(tmp_path))


def test_exhausted_correction_quota_retains_rejection_without_applying_it(tmp_path):
    p = protocol()
    wrapper = DaggerBFSSession(
        session(tmp_path),
        p,
        task_id="tiny/train-task",
        split="train",
        modality="text-state",
        iteration=1,
        starting_checkpoint="start",
    )
    wrapper.next_request()
    before = wrapper.session.session.context.memory.to_bytes()
    decision = wrapper.submit_student("not json", allow_expert=False)
    assert decision["correction"] is None and decision["applied_operation_source"] is None
    assert wrapper.session.session.context.memory.to_bytes() == before
    report = wrapper.finish("correction_quota")
    assert report["result"]["trusted_rollout_events"] == 0
    assert replay_dagger_episode(report, p, session(tmp_path)) == report


def test_certification_rejects_split_drift_and_conflicting_identical_inputs(tmp_path):
    p = protocol()
    wrapper = DaggerBFSSession(
        session(tmp_path),
        p,
        task_id="tiny/train-task",
        split="train",
        modality="text-state",
        iteration=1,
        starting_checkpoint="start",
    )
    wrapper.next_request()
    correction = wrapper.submit_student("not json")["correction"]
    assert certify_corrections([correction], p, modality="text-state", iteration=1, target_token_counter=lambda _: 1)

    drift = copy.deepcopy(correction)
    drift["split"] = "dev"
    with pytest.raises(ValueError, match="provenance"):
        certify_corrections([drift], p, modality="text-state", iteration=1, target_token_counter=lambda _: 1)

    serializer = copy.deepcopy(correction)
    serializer["view_serializer"] = "different"
    with pytest.raises(ValueError, match="provenance"):
        certify_corrections([serializer], p, modality="text-state", iteration=1, target_token_counter=lambda _: 1)

    with pytest.raises(ValueError, match="output allowance"):
        certify_corrections([correction], p, modality="text-state", iteration=1, target_token_counter=lambda _: 385)

    conflict = copy.deepcopy(correction)
    conflict["correction_id"] += ":conflict"
    conflict["expert_query"]["target"]["canonical_rationale"] = "different"
    conflict["expert_query"]["raw_output"] = canonical(conflict["expert_query"]["target"])
    with pytest.raises(ValueError, match="conflicting"):
        certify_corrections(
            [correction, conflict], p, modality="text-state", iteration=1, target_token_counter=lambda _: 1
        )


def test_aggregation_matches_512_record_continued_sft_exposure_and_never_duplicates_corrections(tmp_path):
    source = [
        {
            "record_id": f"source-{i}",
            "task_id": "tiny/train-task",
            "split": "train",
            "authoritative_input": {"i": i},
            "view_manifest": "view.json",
            "state": i,
            "input_pages": [],
            "target": {"target": i},
        }
        for i in range(512)
    ]
    p = protocol(source_ids=[row["record_id"] for row in source])
    wrapper = DaggerBFSSession(
        session(tmp_path),
        p,
        task_id="tiny/train-task",
        split="train",
        modality="text-state",
        iteration=1,
        starting_checkpoint="start",
    )
    wrapper.next_request()
    correction = wrapper.submit_student("not json")["correction"]
    repeated = copy.deepcopy(correction)
    repeated["correction_id"] += ":repeat"
    repeated["collection_decision_index"] += 1
    continued = aggregate_update(
        source,
        [],
        p,
        modality="text-state",
        through_iteration=1,
        arm="continued_sft",
        target_token_counter=lambda _: 1,
    )
    dagger = aggregate_update(
        source,
        [correction, repeated],
        p,
        modality="text-state",
        through_iteration=1,
        arm="dagger",
        target_token_counter=lambda _: 1,
    )
    assert continued["record_count"] == dagger["record_count"] == 512
    assert continued["original_sft_records"] == 512 and continued["unique_corrections"] == 0
    assert dagger["original_sft_records"] == 511 and dagger["unique_corrections"] == 1
    assert dagger["records"][-1]["record_id"] == correction["correction_id"]
    assert continued["optimizer_updates"] == dagger["optimizer_updates"] == 16


def test_repository_protocol_binds_real_bfs_membership_and_checkpoints():
    p = read(ROOT / "configs/experiments/expanded-study/dagger-protocol.json")
    context = validate_protocol(ROOT, p)
    assert len(context["source_records"]) == 512
    assert all(row["trace_paths"]["bfs"] == row["source_trace_path"] for row in context["source_records"])
    assert len(p["collection"]["task_order"]) == 25
    assert p["collection"]["allowed_split"] == "train"
    assert p["training"]["arms"] == ["dagger", "continued_sft"]
    assert p["training"]["iterations"] == 2
    assert p["launch"]["master_port_pool"] == [18800, 18801, 18802, 18803, 18804, 18805]
    assert p["goal4_runner_commit"] == "4ba554e535202dc1589a9c679128d4f116adeff8"
    assert p["goal5_runner_commit"] == "f338b17589ce4454d255b68a4ef75b7eacedf772"
    assert not p["collection"]["per_modality_trajectories_identical"]
    assert not p["budget"]["full_allowance_completion_guaranteed"]


def test_training_loader_continues_existing_adapter_weights(monkeypatch):
    from types import SimpleNamespace

    import peft
    import torch
    from transformers import Qwen3VLForConditionalGeneration

    from examples.planning_benchmark_slice.visual_model import load_training_model

    model = torch.nn.Linear(2, 2).eval()
    monkeypatch.setattr(model, "config", SimpleNamespace(use_cache=True), raising=False)
    monkeypatch.setattr(model, "to", lambda *args, **kwargs: model)
    monkeypatch.setattr(model, "gradient_checkpointing_enable", lambda **kwargs: None, raising=False)
    monkeypatch.setattr(model, "enable_input_require_grads", lambda: None, raising=False)
    monkeypatch.setattr(Qwen3VLForConditionalGeneration, "from_pretrained", lambda *args, **kwargs: model)
    loaded = {}

    def continue_adapter(base, path, *, is_trainable):
        loaded.update(base=base, path=path, is_trainable=is_trainable)
        return base

    monkeypatch.setattr(peft.PeftModel, "from_pretrained", continue_adapter)
    config = read(ROOT / "configs/experiments/matched-modalities/study-v5.json")
    assert load_training_model(config, "checkpoint/final") is model
    assert loaded == {"base": model, "path": "checkpoint/final", "is_trainable": True}
    assert model.training and not model.config.use_cache


def test_collection_journal_resumes_and_preserves_correction_quota_stop(tmp_path, monkeypatch):
    p = protocol()
    p["algorithm"] = "bfs"
    p["output_root"] = "dagger-output"
    p["collection"].update(
        allowed_split="train",
        seed=17,
        max_decisions_per_modality_iteration=10,
        max_corrections_per_modality_iteration=2,
    )
    p["views"]["source"] = "unused-scene-views.json"
    p["model"] = {"id": "model", "revision": "revision", "output_tokens": 384}
    row = {
        "task_id": "tiny/train-task",
        "domain": "rooms",
        "difficulty": "easy",
        "view_manifest": "unused-view-manifest.json",
    }

    class Views:
        def __init__(self, *args, read_only=False, **kwargs):
            self.read_only = read_only

        def observe(self, raw, algorithm, *, modality, pixels=True):
            return {
                "messages": [],
                "images": [],
                "binding": {"state": raw["observation"]["state_id"], "input_pages": [], "input_tokens": 1},
            }

        def save(self):
            pass

    monkeypatch.setattr(collection, "VisualTaskViews", Views)
    monkeypatch.setattr(collection, "VisualSession", lambda *args, **kwargs: session(tmp_path))
    calls = 0

    def interrupted(_example):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated collector interruption")
        return "not json", 2

    with pytest.raises(RuntimeError, match="simulated"):
        collection._collect_episode(
            tmp_path,
            p,
            row,
            modality="text-state",
            iteration=1,
            checkpoint="start",
            endpoint="unused",
            collection_offset=0,
            corrections_before=0,
            generate=interrupted,
            progress=lambda **values: None,
        )
    base = collection.cell_root(tmp_path, p, "text-state", 1)
    episode_path, journal_path, _ = collection._episode_paths(base, row["task_id"])
    assert journal_path.exists() and not episode_path.exists()
    assert len(collection.read_json(journal_path)["decisions"]) == 1

    report, retained = collection._collect_episode(
        tmp_path,
        p,
        row,
        modality="text-state",
        iteration=1,
        checkpoint="start",
        endpoint="unused",
        collection_offset=0,
        corrections_before=0,
        generate=lambda _example: ("not json", 2),
        progress=lambda **values: None,
    )
    assert not retained and not journal_path.exists()
    assert report["result"]["stop_reason"] == "correction_quota"
    assert [decision["collection_decision_index"] for decision in report["decisions"]] == [0, 1, 2]
    assert sum(decision["correction"] is not None for decision in report["decisions"]) == 2
    assert report["decisions"][-1]["correction"] is None

    replayed, retained = collection._collect_episode(
        tmp_path,
        p,
        row,
        modality="text-state",
        iteration=1,
        checkpoint="start",
        endpoint="unused",
        collection_offset=0,
        corrections_before=0,
        generate=lambda _example: pytest.fail("retained episode made a new model call"),
        progress=lambda **values: None,
    )
    assert retained and replayed == report
