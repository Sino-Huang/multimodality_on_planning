from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from examples.planning_benchmark_slice.matched_modality_episode import MatchedEpisodeRequest, exact_candidate_policy
from examples.planning_benchmark_slice.modality_observation import MODALITIES, ModalityInputLimits
from examples.planning_benchmark_slice.planimation_render import PlanimationRenderRequest
from examples.planning_benchmark_slice.search_episode import (
    replay_matched_modality_episode,
    run_matched_modality_episode,
)
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome


def request(tmp_path: Path) -> MatchedEpisodeRequest:
    binding = ReceiptBinding("issue70-test", "attempt-1", tmp_path / "output")
    return MatchedEpisodeRequest(
        binding=binding,
        algorithm="best_first_add_greedy",
        max_expansions=8,
        max_decisions=16,
        render=PlanimationRenderRequest(
            "http://127.0.0.1:18082",
            tmp_path / "domain.pddl",
            tmp_path / "problem.pddl",
            tmp_path / "profile.pddl",
            None,
            tmp_path / "output" / "render",
            30,
        ),
        supplied_paths=(("(move a b)", "(move b c)"),),
        limits=ModalityInputLimits("test-counter", "v1", 4096, 1024, 1536, 18, 8192, 16, (1024, 4096)),
    )


@pytest.mark.parametrize("outcome", list(StopOutcome))
def test_gate_precedes_task_reads_rendering_and_policy_calls(tmp_path: Path, outcome: StopOutcome) -> None:
    task = request(tmp_path)
    ancestor = "ancestor:stopped" if outcome is StopOutcome.ANCESTOR_STOP else None
    gate = GateReceipt(task.binding, outcome, ancestor)
    # PASS without authorization is INVALID; other stop classifications remain distinct.
    result = run_matched_modality_episode(
        task,
        gate_receipt=gate,
        authorization_receipt=None,
        policies={},
        token_counter=lambda text, images: pytest.fail("unpermitted tokenization"),
    )
    assert result["outcome"] == ("INVALID" if outcome is StopOutcome.PASS else outcome.value)
    assert result["scientific_completion"] is False
    assert result["episodes"] == []
    assert not Path(task.binding.output_root).exists()
    if outcome in (StopOutcome.VALID_STOP, StopOutcome.ANCESTOR_STOP):
        assert result["gated_not_run_receipt"]["run_state"] == "gated-not-run"


def test_authorization_must_match_requested_output_binding(tmp_path: Path) -> None:
    task = request(tmp_path)
    wrong = ReceiptBinding(task.binding.contract_id, task.binding.attempt_id, tmp_path / "wrong-output")
    gate = GateReceipt(wrong, StopOutcome.PASS)
    result = run_matched_modality_episode(
        task,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(wrong, gate.receipt_id),
        policies={},
        token_counter=lambda text, images: 0,
    )
    assert result["outcome"] == "INVALID"
    assert result["reason"] == "gate-binding-mismatch"
    assert not Path(task.binding.output_root).exists()


def prepare(task: MatchedEpisodeRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    task.render.domain_path.write_text("""(define (domain rooms) (:requirements :strips)
      (:predicates (at ?x) (link ?x ?y))
      (:action move :parameters (?x ?y) :precondition (and (at ?x) (link ?x ?y))
        :effect (and (not (at ?x)) (at ?y))))""")
    task.render.problem_path.write_text("""(define (problem rooms-p) (:domain rooms) (:objects a b c)
      (:init (at a) (link a b) (link b a) (link b c)) (:goal (at c)))""")
    task.render.animation_profile_path.write_text("(define (animation rooms))")
    payload = {
        "visualStages": [
            {"stageName": name, "visualSprites": [{"name": "agent", "minX": 0.1, "maxX": 0.2, "minY": 0.1, "maxY": 0.2}]}
            for name in ("Initial Stage", "(move a b)", "(move b c)")
        ]
    }
    monkeypatch.setattr(
        "scripts.planimation_phase1_client.requests.post",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            text=json.dumps(payload),
            content=json.dumps(payload).encode(),
            json=lambda: payload,
        ),
    )


def test_three_independent_episodes_run_and_replay_aligned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task = request(tmp_path)
    prepare(task, monkeypatch)
    gate = GateReceipt(task.binding, StopOutcome.PASS)
    calls: dict[str, list[list[dict]]] = {modality: [] for modality in MODALITIES}

    def policy(modality: str):
        def choose(messages: list[dict]) -> str:
            calls[modality].append(messages)
            return exact_candidate_policy(messages)

        return choose

    updates = []
    report = run_matched_modality_episode(
        task,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(task.binding, gate.receipt_id),
        policies={modality: policy(modality) for modality in MODALITIES},
        token_counter=lambda text, images: len(text.split()) + 256 * len(images),
        progress=updates.append,
    )

    assert report["outcome"] == "PASS"
    assert report["scientific_completion"] is True
    assert report["aligned_decisions"] == 3
    assert [episode["result"]["goal_reached"] for episode in report["episodes"]] == [True, True, True]
    assert [len(calls[modality]) for modality in MODALITIES] == [3, 3, 3]
    assert [len(calls[modality][0][0]["content"]) for modality in MODALITIES] == [1, 3, 3]
    assert any(update["stage"] == "decision" for update in updates)
    # Replaying the JSON-round-tripped evidence requires neither HTTP nor policy execution.
    monkeypatch.setattr(
        "scripts.planimation_phase1_client.requests.post", lambda *args, **kwargs: pytest.fail("replay HTTP")
    )
    replayed = replay_matched_modality_episode(json.loads(json.dumps(report)))
    assert replayed["replayed_episodes"] == 3
    assert replayed["aligned_decisions"] == 3


@pytest.mark.parametrize("defect", ["operation", "membership", "frame", "image_path", "tokens", "completion"])
def test_replay_detects_semantic_and_alignment_defects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    task = request(tmp_path)
    prepare(task, monkeypatch)
    gate = GateReceipt(task.binding, StopOutcome.PASS)
    report = run_matched_modality_episode(
        task,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(task.binding, gate.receipt_id),
        policies={modality: exact_candidate_policy for modality in MODALITIES},
        token_counter=lambda text, images: 100,
    )
    damaged = deepcopy(report)
    event = damaged["episodes"][1]["events"][0]
    if defect == "operation":
        event["raw_output"] = json.dumps({"source_state_id": "s0", "action": {"name": "move", "args": ["b", "a"]}})
    elif defect == "membership":
        payload = json.loads(event["observation"]["prompt"])
        payload["search_memory"]["successor_candidates"][0].pop("closed")
        event["observation"]["prompt"] = json.dumps(payload)
    elif defect == "frame":
        event["observation"]["images"][0]["source_frame"] = "render/path-000000/frames/frame_002.png"
    elif defect == "image_path":
        event["observation"]["images"][0]["path"] = "observations/visual-state/goal.png"
    elif defect == "tokens":
        event["observation"]["input_tokens"] = 5000
    else:
        damaged["scientific_completion"] = False
    with pytest.raises(ValueError, match=r"replay|aligned|frame|token"):
        replay_matched_modality_episode(damaged)


@pytest.mark.parametrize("invalid", [False, True])
def test_exhausted_and_invalid_episodes_never_claim_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid: bool,
) -> None:
    task = replace(request(tmp_path), max_decisions=1)
    prepare(task, monkeypatch)
    gate = GateReceipt(task.binding, StopOutcome.PASS)
    report = run_matched_modality_episode(
        task,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(task.binding, gate.receipt_id),
        policies={
            modality: (lambda messages: "not an operation") if invalid else exact_candidate_policy
            for modality in MODALITIES
        },
        token_counter=lambda text, images: 100,
    )
    assert report["outcome"] == ("INVALID" if invalid else "VALID_STOP")
    assert report["scientific_completion"] is False
    assert report["execution_started"] is True
    if invalid:
        assert all(episode["result"]["invalid_operations"] == 1 for episode in report["episodes"])
        assert all(episode["result"]["budget_used"] == 1 for episode in report["episodes"])
    else:
        assert report["gated_not_run_receipt"]["run_state"] == "gated-not-run"
    assert replay_matched_modality_episode(report)["outcome"] == report["outcome"]


def test_dry_run_checks_supplied_path_without_work_or_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task = request(tmp_path)
    prepare(task, monkeypatch)
    monkeypatch.setattr(
        "scripts.planimation_phase1_client.requests.post", lambda *args, **kwargs: pytest.fail("dry-run HTTP")
    )
    gate = GateReceipt(task.binding, StopOutcome.PASS)
    report = run_matched_modality_episode(
        task,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(task.binding, gate.receipt_id),
        policies={modality: lambda messages: pytest.fail("dry-run policy") for modality in MODALITIES},
        token_counter=lambda text, images: pytest.fail("dry-run tokenization"),
        dry_run=True,
    )
    assert report["status"] == "dry_run"
    assert report["scientific_completion"] is False
    assert report["execution_started"] is False
    assert not Path(task.binding.output_root).exists()
