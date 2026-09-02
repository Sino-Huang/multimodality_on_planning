from __future__ import annotations

import json
from pathlib import Path

import pytest

from examples.planning_benchmark_slice import model_search_episode
from examples.planning_benchmark_slice.model_search_episode import (
    replay_model_search_episode,
    run_model_search_episode,
)
from examples.planning_benchmark_slice.search_episode import run_search_episode
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

REPO_ROOT = Path(__file__).resolve().parents[2]
NONTRIVIAL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_nontrivial.json"


def _receipts(tmp_path: Path) -> tuple[GateReceipt, AuthorizationReceipt]:
    binding = ReceiptBinding(
        contract_id="issue-49-bfs-development-v1",
        attempt_id="issue-52-model-episode",
        output_root=(tmp_path / "episode-evidence").resolve(),
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_id=gate.receipt_id)
    return gate, authorization


def test_model_owned_exact_operations_complete_and_replay_without_rerunning_policy(tmp_path: Path) -> None:
    gate, authorization = _receipts(tmp_path)
    exact = run_search_episode(
        task_path=NONTRIVIAL_FIXTURE,
        algorithm="bfs",
        modality="text-state",
        policy="exact",
        max_expansions=64,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )
    events = exact["evidence"]["events"]
    outputs = iter(
        json.dumps(
            {
                "canonical_rationale": event["rationale"],
                "runtime_result": None,
                "typed_operation": event["operation"],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        for event in events
    )

    model_inputs: list[dict[str, object]] = []

    def policy(model_input: dict[str, object]) -> str:
        model_inputs.append(model_input)
        return next(outputs)

    episode = run_model_search_episode(
        NONTRIVIAL_FIXTURE,
        algorithm="bfs",
        modality="text-state",
        arm="base",
        model_identity={"model_id": "fixture-exact-policy", "revision": "test"},
        policy=policy,
        max_expansions=64,
        max_input_bytes=3_840,
        max_output_tokens=256,
        accepted_delta_limit=16,
        model_input_projection="bounded_bfs_search_memory_v3",
        seed=17,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )

    assert episode["result"]["goal_reached"] is True
    assert episode["result"]["invalid_operation_count"] == 0
    assert episode["result"]["algorithm_invariants_hold"] is True
    assert model_inputs
    assert model_inputs[0]["observation"] == {
        "frontier_head": model_inputs[0]["observation"]["state_id"],
        "frontier_size": 1,
        "modality": "text-state",
        "state_atoms": model_inputs[0]["observation"]["state_atoms"],
        "state_id": model_inputs[0]["observation"]["state_id"],
    }
    assert model_inputs[0]["search_memory"]["context_type"] == "bounded_bfs_search_memory"
    assert model_inputs[0]["search_memory"]["schema_version"] == 3
    assert replay_model_search_episode(episode["evidence"]) == episode


def test_deterministic_invalid_model_output_is_charged_once_without_replay(tmp_path: Path) -> None:
    gate, authorization = _receipts(tmp_path)
    call_count = 0

    def invalid_policy(_model_input: dict[str, object]) -> str:
        nonlocal call_count
        call_count += 1
        return "not-json"

    episode = run_model_search_episode(
        NONTRIVIAL_FIXTURE,
        algorithm="bfs",
        modality="text-state",
        arm="base",
        model_identity={
            "decoding": "greedy",
            "memoize_identical_inputs": True,
            "model_id": "fixture-invalid-policy",
            "revision": "test",
        },
        policy=invalid_policy,
        max_expansions=2,
        max_input_bytes=3_840,
        max_output_tokens=256,
        accepted_delta_limit=16,
        model_input_projection="rolling_search_context_v1",
        seed=17,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )

    assert episode["result"]["goal_reached"] is False
    assert episode["result"]["budget_used"] == 1
    assert episode["result"]["invalid_operation_count"] == 1
    assert episode["result"]["invalid_operation_rate"] == 1.0
    assert episode["result"]["termination_reason"] == "deterministic_invalid_operation"
    assert call_count == 1
    assert all(event["status"] == "rejected" for event in episode["evidence"]["policy_events"])
    assert replay_model_search_episode(episode["evidence"]) == episode


def test_model_episode_stops_before_loading_task_or_calling_policy(tmp_path: Path) -> None:
    binding = ReceiptBinding(
        contract_id="issue-49-bfs-development-v1",
        attempt_id="issue-52-ancestor-stop",
        output_root=(tmp_path / "episode-evidence").resolve(),
    )
    ancestor_digest = "a" * 64
    gate = GateReceipt(
        binding=binding,
        outcome=StopOutcome.ANCESTOR_STOP,
        ancestor_receipt_id=ancestor_digest,
    )

    episode = run_model_search_episode(
        tmp_path / "must-not-be-read.json",
        algorithm="not-validated-after-stop",
        modality="not-validated-after-stop",
        arm="base",
        model_identity={},
        policy=lambda _model_input: (_ for _ in ()).throw(AssertionError("must not be called")),
        max_expansions=0,
        max_input_bytes=0,
        max_output_tokens=0,
        accepted_delta_limit=0,
        model_input_projection="not-validated-after-stop",
        seed=17,
        gate_receipt=gate,
        authorization_receipt=None,
        ancestor_receipt_id=ancestor_digest,
    )

    assert episode["result"]["outcome"] == StopOutcome.ANCESTOR_STOP.value
    assert episode["result"]["completion"] == "gated-not-run"
    assert episode["evidence"] is None


def test_incremental_loop_materializes_only_after_completion_and_honors_decision_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate, authorization = _receipts(tmp_path)
    exact = run_search_episode(
        task_path=NONTRIVIAL_FIXTURE,
        algorithm="bfs",
        modality="text-state",
        policy="exact",
        max_expansions=64,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )
    first = exact["evidence"]["events"][0]
    output = json.dumps(
        {
            "canonical_rationale": first["rationale"],
            "runtime_result": None,
            "typed_operation": first["operation"],
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    materialization_count = 0
    original = model_search_episode.materialize_search_trace

    def counted_materialization(*args: object, **kwargs: object) -> object:
        nonlocal materialization_count
        materialization_count += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(model_search_episode, "materialize_search_trace", counted_materialization)

    def policy(_model_input: dict[str, object]) -> str:
        assert materialization_count == 0
        return output

    episode = run_model_search_episode(
        NONTRIVIAL_FIXTURE,
        algorithm="bfs",
        modality="text-state",
        arm="base",
        model_identity={"model_id": "fixture", "revision": "test"},
        policy=policy,
        max_expansions=64,
        max_model_calls=1,
        max_input_bytes=3_840,
        max_output_tokens=384,
        accepted_delta_limit=16,
        model_input_projection="bounded_bfs_search_memory_v3",
        seed=17,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )

    assert materialization_count == 1
    assert episode["result"]["decision_count"] == 1
    assert episode["result"]["termination_reason"] == "decision_budget_exhausted"
    assert episode["result"]["goal_reached"] is False
    assert replay_model_search_episode(episode["evidence"]) == episode
