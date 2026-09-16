import copy
import hashlib
import json
from types import SimpleNamespace
from typing import ClassVar

import pytest

from examples.planning_benchmark_slice import expanded_successor_evaluation as evaluation
from examples.planning_benchmark_slice.expanded_successor import (
    prediction_target,
    static_context_id,
    verify_prediction,
)
from examples.planning_benchmark_slice.modality_corpus_replay import canonical
from examples.planning_benchmark_slice.modality_view_preparation import write_json
from examples.planning_benchmark_slice.pddl_state import GroundedAction, PDDLStateAuthority
from examples.planning_benchmark_slice.scene_assets import read_json
from scripts import run_expanded_successor_evaluation as runner

DOMAIN = """
(define (domain line)
  (:requirements :strips :typing)
  (:types place)
  (:predicates (at ?p - place))
  (:action move
    :parameters (?from - place ?to - place)
    :precondition (at ?from)
    :effect (and (not (at ?from)) (at ?to)))
  (:action wait
    :parameters (?p - place)
    :precondition (at ?p)
    :effect (at ?p)))
"""
PROBLEM = """
(define (problem line-problem)
  (:domain line)
  (:objects a b c - place)
  (:init (at a))
  (:goal (at c)))
"""


def protocol():
    modalities = ["text-state", "visual-state", "multimodal-state"]
    producing = {
        "job_id": "successor-evaluate-0",
        "attempt": 1,
        "directory": "/scheduler/jobs/successor-evaluate-0/1",
    }
    policy_identity = {
        "attention_implementation": "visual_sdpa",
        "decoding": "greedy",
        "dtype": "float32",
        "max_batch_input_tokens": 24000,
        "max_batch_size": 2,
        "max_context_tokens": 32768,
        "max_new_tokens": 512,
        "memoize_identical_inputs": False,
        "model_id": "model",
        "revision": "revision",
    }
    return {
        "protocol_id": "expanded-successor-v1",
        "output_root": "out",
        "modalities": modalities,
        "evaluation": {"seed": 17},
        "model": {"id": "model", "revision": "revision", "decoding": "greedy"},
        "training": {
            "arm": "successor_sft",
            "records_per_modality": 512,
            "optimizer_updates": 16,
        },
        "launch": {
            "devices": [0, 1],
            "master_port_pool": [18800, 18801, 18802, 18803, 18804, 18805],
        },
        "_successor_checkpoints": {
            modality: f"out/training/{modality}/successor_sft/final" for modality in modalities
        },
        "_successor_checkpoint_sha256": {
            modality: f"sha256:{modality}-model"
            for modality in modalities
        },
        "_successor_adapter_config_sha256": {
            modality: f"sha256:{modality}-config"
            for modality in modalities
        },
        "_successor_policy_identity": {
            modality: copy.deepcopy(policy_identity) for modality in modalities
        },
        "_runtime_head": "0123456789abcdef0123456789abcdef01234567",
        "_producing_attempt": producing,
        "_valid_producing_attempts": {
            (producing["job_id"], producing["attempt"], producing["directory"]): "cutoff"
        },
    }


def task(task_id="task/a", decisions=2):
    return {
        "row": {
            "task_id": task_id,
            "domain": "line",
            "difficulty": "test",
            "split": "test",
            "reference_costs": {"bfs": {"decisions": decisions, "expansions": 2}},
        }
    }


class FakeViews:
    read_only = False

    def __init__(self, *_args, read_only=False, **_kwargs):
        self.read_only = read_only

    def observe(self, raw, algorithm, *, modality, pixels=True):
        assert algorithm == "bfs"
        return {
            "messages": [
                {"role": "system", "content": "source"},
                {"role": "user", "content": [{"type": "text", "text": canonical(raw)}]},
            ],
            "images": [],
            "binding": {"state": raw["observation"]["state_id"], "input_pages": []},
        }

    def save(self):
        pass


class FakeSession:
    instances: ClassVar[list] = []

    def __init__(self, root, row, algorithm, arm, seed, output, contract_id, *, views=None):
        assert algorithm == "bfs"
        assert arm == "exact_reference"
        self.authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
        self.state = self.authority.initial_state
        self.actions = []
        self.terminated = False
        self.views = views
        self.__class__.instances.append(self)

    def next_request(self):
        if self.authority.is_goal(self.state):
            self.terminated = True
            return None
        destination = "b" if "at(a)" in self.state.atoms else "c"
        action = {"name": "move", "args": ["a" if destination == "b" else "b", destination]}
        raw = {
            "task_context": self.authority.task_context(),
            "observation": {
                "state_id": self.state.state_id,
                "state_atoms": list(self.state.atoms),
                "frontier": [self.state.state_id],
                "modality": "text-state",
            },
            "search_memory": {
                "frontier": [self.state.state_id],
                "successor_candidates": [
                    {
                        "grounded_action": action,
                        "visited": False,
                        "target_state_id": "forbidden",
                        "target_state": {"forbidden": True},
                        "evaluation": {"forbidden": True},
                    }
                ],
            },
        }
        return SimpleNamespace(model_input=raw)

    def reference_output(self):
        request = self.next_request()
        assert request is not None
        action = request.model_input["search_memory"]["successor_candidates"][0]["grounded_action"]
        return canonical(
            {
                "canonical_rationale": "reference",
                "runtime_result": None,
                "typed_operation": {
                    "source_state_id": self.state.state_id,
                    "action": action,
                    "frontier_intent": {"retire_source": True, "target_position": 0},
                    "visit_target": True,
                    "evaluate_target": False,
                },
            }
        )

    def submit(self, output, binding=None):
        operation = json.loads(output)["typed_operation"]
        action = operation["action"]
        self.state = self.authority.apply(
            self.state, GroundedAction(action["name"], tuple(action["args"]))
        ).target_state
        self.actions.append(copy.deepcopy(action))

    def result(self):
        goal = self.terminated and self.authority.is_goal(self.state)
        return {
            "invariant_valid_success": goal,
            "goal_reached": goal,
            "algorithm_invariants_hold": True,
            "decision_count": len(self.actions),
            "expansion_count": len(self.actions) if self.terminated else max(0, len(self.actions) - 1),
            "invalid_operation_count": 0,
            "invalid_operation_rate": 0,
            "model_call_limit": 4,
            "termination_reason": "goal_reached" if goal else None,
        }


class QueueExhaustionSession(FakeSession):
    def next_request(self):
        if "at(b)" in self.state.atoms:
            self.terminated = True
            return None
        return super().next_request()

    def result(self):
        exhausted = self.terminated and "at(b)" in self.state.atoms
        return {
            "invariant_valid_success": False,
            "goal_reached": False,
            "algorithm_invariants_hold": True,
            "decision_count": len(self.actions),
            "expansion_count": len(self.actions) if self.terminated else 0,
            "invalid_operation_count": 0,
            "invalid_operation_rate": 0,
            "model_call_limit": 4,
            "termination_reason": "frontier_exhausted" if exhausted else None,
        }


def views_factory(*args, **kwargs):
    return FakeViews(*args, **kwargs)


def token_counter(messages, images):
    return len(canonical(messages))


def prediction_from_example(example):
    semantic = json.loads(example["messages"][1]["content"][0]["text"])
    query = semantic["successor_prediction_query"]
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    source = authority.initial_state
    if query["source_state_id"] != source.state_id:
        source = authority.apply(source, GroundedAction("move", ("a", "b"))).target_state
    transition = authority.preview_apply(
        source, GroundedAction(query["action"]["name"], tuple(query["action"]["args"]))
    )
    return canonical(prediction_target(authority.task_context(), transition))


def good_generate(examples):
    return [prediction_from_example(example) for example in examples], {
        "input_tokens": [example["binding"]["input_tokens"] for example in examples],
        "generated_sequence_tokens": [1] * len(examples),
    }


def run_cell(tmp_path, arm, generate, *, decisions=2, session_factory=FakeSession):
    return evaluation.run_cell(
        tmp_path,
        protocol(),
        panel="development",
        modality="text-state",
        arm=arm,
        tasks=[task(decisions=decisions)],
        endpoint="unused",
        generate=generate,
        progress=lambda **kwargs: None,
        session_factory=session_factory,
        views_factory=views_factory,
        token_counter=token_counter,
    )


def verify_report(tmp_path, report, *, session_factory=FakeSession):
    return evaluation.verify_episode(
        tmp_path,
        protocol(),
        "development",
        "text-state",
        task(decisions=report["reference_decisions"]),
        report["arm"],
        "unused",
        session_factory=session_factory,
        views_factory=views_factory,
        token_counter=token_counter,
    )


def test_canonical_action_order_is_shared_and_accepted_predictions_enter_search(tmp_path):
    trusted = run_cell(tmp_path, "trusted_successor", None)[0]
    generated = run_cell(tmp_path, "model_generated_successor", good_generate)[0]
    assert trusted["canonical_action_sequence"] == generated["canonical_action_sequence"]
    assert generated["result"]["invariant_valid_success"] is True
    assert generated["result"]["model_calls"] == 2
    assert generated["final_checkpoint_sha256"] == protocol()["_successor_checkpoint_sha256"]["text-state"]
    assert all(event["accepted"] for event in generated["events"])
    assert all(event["verification"]["prediction_applied"] for event in generated["events"])
    assert generated["trusted_state_substitutions"] == 0


def test_trusted_goal_episode_replays_identical_terminal_result(tmp_path):
    report = run_cell(tmp_path, "trusted_successor", None)[0]
    replayed = verify_report(tmp_path, report)
    assert replayed["result"] == report["result"]
    assert report["result"]["goal_reached"] is True


def test_model_goal_episode_replays_identical_terminal_result(tmp_path):
    report = run_cell(tmp_path, "model_generated_successor", good_generate)[0]
    replayed = verify_report(tmp_path, report)
    assert replayed["result"] == report["result"]
    assert report["result"]["invariant_valid_success"] is True


def test_natural_queue_exhaustion_replays_identical_terminal_result(tmp_path):
    report = run_cell(
        tmp_path,
        "trusted_successor",
        None,
        session_factory=QueueExhaustionSession,
    )[0]
    replayed = verify_report(tmp_path, report, session_factory=QueueExhaustionSession)
    assert replayed["result"] == report["result"]
    assert report["result"]["termination_reason"] == "frontier_exhausted"


def test_rejected_prediction_is_invalid_successor_without_trusted_substitution(tmp_path):
    before = len(FakeSession.instances)

    def reject(examples):
        return ["{}" for _ in examples], {
            "input_tokens": [1] * len(examples),
            "generated_sequence_tokens": [1] * len(examples),
        }

    report = run_cell(tmp_path, "model_generated_successor", reject)[0]
    session = FakeSession.instances[before]
    assert session.actions == []
    assert report["result"]["termination_reason"] == "invalid_successor"
    assert report["events"][0]["verification"]["failure_kind"] == "schema"
    assert report["events"][0]["verification"]["trusted_state_substituted"] is False
    assert report["events"][0]["raw_prediction"] == "{}"
    assert verify_report(tmp_path, report)["result"] == report["result"]


def test_call_limit_exhaustion_is_a_valid_unsuccessful_episode(tmp_path):
    report = run_cell(
        tmp_path,
        "model_generated_successor",
        lambda examples: (_ for _ in ()).throw(AssertionError("call limit should prevent generation")),
        decisions=0,
    )[0]
    assert report["result"]["termination_reason"] == "model_call_limit_exhausted"
    assert report["result"]["invariant_valid_success"] is False
    assert report["result"]["model_calls"] == 0
    assert report["events"] == []
    assert verify_report(tmp_path, report)["result"] == report["result"]


def test_strict_failure_kinds_are_classified_separately():
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    source = authority.initial_state
    action = GroundedAction("move", ("a", "b"))
    transition = authority.preview_apply(source, action)
    query = {
        "source_state_id": source.state_id,
        "action": {"name": action.name, "args": list(action.args)},
        "static_context_id": static_context_id(authority.task_context()),
    }
    valid = prediction_target(authority.task_context(), transition)

    def kind(value, current_query=query):
        return verify_prediction(authority, source, current_query, canonical(value))["failure_kind"]

    assert verify_prediction(authority, source, query, "not-json")["failure_kind"] == "schema"
    changed = copy.deepcopy(valid)
    changed["static_context_id"] = "wrong"
    assert kind(changed) == "static_context"
    changed = copy.deepcopy(valid)
    changed["source_state_id"] = "wrong"
    assert kind(changed) == "source_identity"
    changed = copy.deepcopy(valid)
    changed["action"] = {"name": "wait", "args": ["a"]}
    assert kind(changed) == "action_identity"
    bad_query = copy.deepcopy(query)
    bad_query["action"] = {"name": "move", "args": ["b", "c"]}
    changed = copy.deepcopy(valid)
    changed["action"] = copy.deepcopy(bad_query["action"])
    assert kind(changed, bad_query) == "applicability"
    changed = copy.deepcopy(valid)
    changed["predicted_state"]["state_id"] = "wrong"
    assert kind(changed) == "state_identity"
    changed = copy.deepcopy(valid)
    changed["predicted_state"] = {
        "atoms": list(source.atoms),
        "fluents": list(source.fluents),
        "state_id": source.state_id,
    }
    assert kind(changed) == "effect"


def test_resume_accepts_and_skips_episode_from_terminal_cutoff_attempt(tmp_path):
    original = run_cell(tmp_path, "model_generated_successor", good_generate)
    retained = run_cell(
        tmp_path,
        "model_generated_successor",
        lambda examples: (_ for _ in ()).throw(AssertionError("completed episode generated")),
    )
    assert retained == original


@pytest.mark.parametrize("producing", [None, {"job_id": "unknown", "attempt": 9, "directory": "/tmp/x"}])
def test_resume_rejects_ad_hoc_or_unknown_producing_attempt(tmp_path, producing):
    report = run_cell(tmp_path, "model_generated_successor", good_generate)[0]
    path = tmp_path / report["output"]
    tampered = read_json(path)
    if producing is None:
        tampered.pop("producing_attempt")
    else:
        tampered["producing_attempt"] = producing
    write_json(path, tampered)
    with pytest.raises(ValueError, match="producing attempt"):
        run_cell(
            tmp_path,
            "model_generated_successor",
            lambda examples: (_ for _ in ()).throw(AssertionError("invalid episode was skipped")),
        )


def test_resume_rejects_tampered_loaded_policy_identity(tmp_path):
    report = run_cell(tmp_path, "model_generated_successor", good_generate)[0]
    path = tmp_path / report["output"]
    tampered = read_json(path)
    tampered["policy_identity"]["model_id"] = "other-model"
    write_json(path, tampered)
    with pytest.raises(ValueError, match="loaded-policy"):
        run_cell(
            tmp_path,
            "model_generated_successor",
            lambda examples: (_ for _ in ()).throw(AssertionError("tampered episode was skipped")),
        )


def test_independent_replay_catches_tampered_raw_prediction(tmp_path):
    report = run_cell(tmp_path, "model_generated_successor", good_generate)[0]
    path = tmp_path / report["output"]
    tampered = read_json(path)
    tampered["events"][0]["raw_prediction"] = "{}"
    write_json(path, tampered)
    with pytest.raises(ValueError, match="verification/classification"):
        evaluation.verify_episode(
            tmp_path,
            protocol(),
            "development",
            "text-state",
            task(),
            "model_generated_successor",
            "unused",
            session_factory=FakeSession,
            views_factory=views_factory,
            token_counter=token_counter,
        )


def test_truncated_natural_episode_fails_as_incomplete_events(tmp_path):
    report = run_cell(tmp_path, "trusted_successor", None)[0]
    path = tmp_path / report["output"]
    truncated = read_json(path)
    truncated["events"] = truncated["events"][:-1]
    write_json(path, truncated)
    with pytest.raises(ValueError, match="recorded events are incomplete"):
        verify_report(tmp_path, truncated)


def test_runtime_head_is_bound_to_producing_worker_not_replay_head(tmp_path):
    producing_directory = (tmp_path / "jobs/successor-evaluate-0/3").resolve()
    producing_directory.mkdir(parents=True)
    producing = {
        "job_id": "successor-evaluate-0",
        "attempt": 3,
        "directory": str(producing_directory),
    }
    runtime_head = "dd4818a000000000000000000000000000000000"
    bound = protocol()
    bound["_producing_attempt"] = producing
    bound["_valid_producing_attempts"] = {
        (producing["job_id"], producing["attempt"], producing["directory"]): "succeeded"
    }
    bound["_runtime_head"] = runtime_head
    report = evaluation.run_cell(
        tmp_path,
        bound,
        panel="development",
        modality="text-state",
        arm="trusted_successor",
        tasks=[task()],
        endpoint="unused",
        generate=None,
        progress=lambda **kwargs: None,
        session_factory=FakeSession,
        views_factory=views_factory,
        token_counter=token_counter,
    )[0]
    assert report["runtime_head"] == runtime_head
    (producing_directory / "worker-result.json").write_text(
        json.dumps(
            {
                "producing_attempt": producing,
                "runtime_head": runtime_head,
                "policy_identities": bound["_successor_policy_identity"],
            }
        )
    )
    replay_protocol = copy.deepcopy(bound)
    replay_protocol["_runtime_head"] = "ffffffffffffffffffffffffffffffffffffffff"
    replayed = evaluation.verify_episode(
        tmp_path,
        replay_protocol,
        "development",
        "text-state",
        task(),
        "trusted_successor",
        "unused",
        session_factory=FakeSession,
        views_factory=views_factory,
        token_counter=token_counter,
    )
    assert replayed["runtime_head"] == runtime_head


def test_summary_preserves_coverage_missingness(tmp_path):
    report = run_cell(tmp_path, "trusted_successor", None)[0]
    expected = [
        {"panel": "development", "modality": "text-state", "task_id": "task/a", "arm": arm}
        for arm in evaluation.ARMS
    ]
    cells = evaluation.summarize([report], expected)
    indexed = {row["arm"]: row for row in cells}
    assert indexed["trusted_successor"]["episodes"] == 1
    assert indexed["model_generated_successor"]["episodes"] == 0
    assert indexed["model_generated_successor"]["missing_episodes"] == 1
    paired = evaluation.paired_rows([report], expected)[0]
    assert paired["arms"]["model_generated_successor"] is None


def test_training_gate_refuses_missing_and_nonpassing_report(tmp_path):
    frozen = protocol()
    with pytest.raises(RuntimeError, match="training-report"):
        runner.require_training_gate(tmp_path, frozen)
    report = tmp_path / "out/training/training-report.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "schema_version": "expanded_successor_training_report_v1",
                "status": "FAIL",
                "outcome": "FAIL",
                "protocol_id": frozen["protocol_id"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="not PASS"):
        runner.require_training_gate(tmp_path, frozen)
    cells = []
    for modality in frozen["modalities"]:
        final = tmp_path / "out/training" / modality / "successor_sft/final"
        final.mkdir(parents=True)
        (final / "adapter_model.safetensors").write_bytes(f"model:{modality}".encode())
        (final / "adapter_config.json").write_text(json.dumps({"modality": modality}))
        tensor_fingerprint = "sha256:" + hashlib.sha256(
            (final / "adapter_model.safetensors").read_bytes()
        ).hexdigest()
        config_fingerprint = "sha256:" + hashlib.sha256(
            (final / "adapter_config.json").read_bytes()
        ).hexdigest()
        cells.append(
            {
                "outcome": "PASS",
                "modality": modality,
                "arm": "successor_sft",
                "records": 512,
                "optimizer_updates": 16,
                "final_checkpoint": f"out/training/{modality}/successor_sft/final",
                "final_checkpoint_sha256": tensor_fingerprint,
                "final_adapter_config_sha256": config_fingerprint,
            }
        )
    aggregate = {
        "schema_version": "expanded_successor_training_report_v1",
        "status": "PASS",
        "outcome": "PASS",
        "protocol_id": frozen["protocol_id"],
        "arm": "successor_sft",
        "cells": cells,
        "records": 1536,
        "optimizer_updates": 48,
        "jobs": [
            {
                "job_id": "successor-train-0",
                "attempt": 1,
                "gpus": [0],
                "master_port": 18804,
                "gpu_hours": 1,
            },
            {
                "job_id": "successor-train-1",
                "attempt": 1,
                "gpus": [1],
                "master_port": 18805,
                "gpu_hours": 1,
            },
        ],
    }
    report.write_text(json.dumps(aggregate), encoding="utf-8")
    retained, checkpoints, fingerprints, config_fingerprints = runner.require_training_gate(
        tmp_path, frozen
    )
    assert retained["status"] == "PASS"
    assert set(checkpoints) == set(frozen["modalities"])
    assert set(fingerprints) == set(frozen["modalities"])
    assert set(config_fingerprints) == set(frozen["modalities"])
    (checkpoints["text-state"] / "adapter_config.json").write_text("tampered")
    with pytest.raises(RuntimeError, match="fingerprint differs"):
        runner.require_training_gate(tmp_path, frozen)


def test_worker_environment_accepts_any_frozen_pool_port(monkeypatch):
    frozen = protocol()
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1")
    monkeypatch.setenv("MASTER_PORT", "18805")
    assert runner._require_worker_environment(frozen, 1) == ("1", 18805)
    monkeypatch.setenv("MASTER_PORT", "19999")
    with pytest.raises(ValueError, match="outside the frozen pool"):
        runner._require_worker_environment(frozen, 1)


def test_cutoff_during_active_episode_preserves_journal_and_prevents_model_call(tmp_path):
    values = iter((0.0, 0.0, 0.0, 2.0))

    def clock():
        return next(values, 2.0)

    calls = 0

    def forbidden_generate(examples):
        nonlocal calls
        calls += 1
        return good_generate(examples)

    reports = evaluation.run_cell(
        tmp_path,
        protocol(),
        panel="development",
        modality="text-state",
        arm="model_generated_successor",
        tasks=[task()],
        endpoint="unused",
        generate=forbidden_generate,
        progress=lambda **kwargs: None,
        cutoff_timestamp=1.0,
        session_factory=FakeSession,
        views_factory=views_factory,
        token_counter=token_counter,
        clock=clock,
    )
    output = evaluation.episode_path(
        tmp_path, protocol(), "development", "text-state", "task/a", "model_generated_successor"
    )
    journal = output.with_name("model_generated_successor.partial.json.gz")
    assert reports == []
    assert calls == 0
    assert not output.exists()
    assert journal.exists()
    resumed = run_cell(tmp_path, "model_generated_successor", good_generate)
    assert resumed[0]["result"]["invariant_valid_success"] is True


def test_scheduler_attempt_validation_binds_actual_ports_and_cutoff(tmp_path, monkeypatch):
    frozen = protocol()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    attempts = []
    for worker, port in enumerate((18804, 18805)):
        directory = tmp_path / "jobs" / str(worker)
        directory.mkdir(parents=True)
        (directory / "hook-result.json").write_text(json.dumps({"returncode": 0}))
        (directory / "worker-result.json").write_text(
            json.dumps({"worker": worker, "master_port": port, "outcome": "PASS"})
        )
        attempts.append(
            {
                "job_id": f"successor-evaluate-{worker}",
                "attempt": 1,
                "status": "succeeded",
                "directory": str(directory),
                "gpus": [worker],
                "master_port": port,
                "gpu_hours": 1,
            }
        )
    ledger = tmp_path / "outputs/expanded-study/v1/budget.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({"attempts": attempts}))
    evidence = runner._evaluation_attempts(frozen, "PASS", [])
    assert [row["master_port"] for row in evidence] == [18804, 18805]
    attempts[1]["status"] = "cutoff"
    ledger.write_text(json.dumps({"attempts": attempts}))
    with pytest.raises(ValueError, match="requires succeeded"):
        runner._evaluation_attempts(frozen, "PASS", [])
    evidence = runner._evaluation_attempts(frozen, "VALID_STOP", [{"task_id": "missing"}])
    assert evidence[1]["status"] == "cutoff"


def test_final_evidence_reports_union_of_all_episode_producing_attempts(tmp_path, monkeypatch):
    frozen = protocol()
    attempts = {}
    reports = []
    for number, status in ((1, "failed"), (2, "cutoff")):
        directory = (tmp_path / "jobs/successor-evaluate-0" / str(number)).resolve()
        directory.mkdir(parents=True)
        receipt = {"returncode": 0 if number == 2 else 1}
        (directory / "hook-result.json").write_text(json.dumps(receipt))
        identity = {
            "job_id": "successor-evaluate-0",
            "attempt": number,
            "directory": str(directory),
        }
        key = (identity["job_id"], identity["attempt"], identity["directory"])
        attempts[key] = {
            **identity,
            "status": status,
            "gpus": [0],
            "master_port": 18800 + number,
            "gpu_hours": 1,
        }
        reports.append(
            {
                "producing_attempt": identity,
                "active_wall_seconds": 1,
                "call_measurements": [],
                "result": {"model_calls": 0},
                "raw_predictions_retained": 0,
                "trusted_state_substitutions": 0,
            }
        )
    monkeypatch.setattr(
        runner,
        "_bind_training_gate",
        lambda root, protocol: (
            frozen,
            {"schema_version": "expanded_successor_training_report_v1", "status": "PASS"},
        ),
    )
    monkeypatch.setattr(runner, "_recorded_attempts", lambda protocol: (frozen, attempts))
    monkeypatch.setattr(runner, "panels", lambda root, protocol: {})
    monkeypatch.setattr(runner, "expected_bindings", lambda protocol, loaded: [])
    monkeypatch.setattr(runner, "_all_reports", lambda protocol: (reports, [{"task_id": "missing"}]))
    monkeypatch.setattr(runner, "_evaluation_attempts", lambda protocol, outcome, missing: [])
    monkeypatch.setattr(runner, "summarize", lambda reports, expected: [])
    monkeypatch.setattr(runner, "paired_rows", lambda reports, expected: [])
    monkeypatch.setattr(runner, "exact_reference_counts", lambda loaded: {})
    evidence = runner._evidence(frozen)
    assert [row["attempt"] for row in evidence["producing_attempts"]] == [1, 2]
    assert evidence["producing_attempts"][0]["hook_receipt"] == {"returncode": 1}
