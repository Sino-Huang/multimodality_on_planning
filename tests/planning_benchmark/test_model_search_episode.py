from __future__ import annotations

import base64
import json
from pathlib import Path

from examples.planning_benchmark_slice.model_search_episode import (
    replay_model_search_episode,
    run_model_search_episode,
)
from examples.planning_benchmark_slice.search_episode import run_search_episode
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome
from src.data_collect.replay import parse_canonical_bundle

REPO_ROOT = Path(__file__).resolve().parents[2]
NONTRIVIAL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_nontrivial.json"
SIGNING_KEY = b"issue-52-model-search-episode-test-key"


def _receipts(tmp_path: Path) -> tuple[GateReceipt, AuthorizationReceipt]:
    binding = ReceiptBinding(
        contract_id="issue-49-bfs-development-v1",
        attempt_id="issue-52-model-episode",
        output_root=(tmp_path / "episode-evidence").resolve(),
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS).signed(SIGNING_KEY)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_digest=gate.digest).signed(SIGNING_KEY)
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
        signing_key=SIGNING_KEY,
    )
    bundle = base64.b64decode(exact["evidence"]["bundle"], validate=True)
    records = json.loads(parse_canonical_bundle(bundle)["search-trace.json"])["records"]
    outputs = iter(
        json.dumps(
            {
                "canonical_rationale": record["rationale"],
                "runtime_result": record["result"],
                "typed_operation": record["operation"],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        for record in records
    )

    episode = run_model_search_episode(
        NONTRIVIAL_FIXTURE,
        algorithm="bfs",
        modality="text-state",
        arm="base",
        model_identity={"model_id": "fixture-exact-policy", "revision": "test"},
        policy=lambda _model_input: next(outputs),
        max_expansions=64,
        max_output_tokens=256,
        accepted_delta_limit=16,
        seed=17,
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=SIGNING_KEY,
    )

    assert episode["result"]["goal_reached"] is True
    assert episode["result"]["invalid_operation_count"] == 0
    assert episode["result"]["algorithm_invariants_hold"] is True
    assert replay_model_search_episode(episode["evidence"], signing_key=SIGNING_KEY) == episode


def test_invalid_model_output_is_charged_without_repair(tmp_path: Path) -> None:
    gate, authorization = _receipts(tmp_path)

    episode = run_model_search_episode(
        NONTRIVIAL_FIXTURE,
        algorithm="bfs",
        modality="text-state",
        arm="base",
        model_identity={"model_id": "fixture-invalid-policy", "revision": "test"},
        policy=lambda _model_input: "not-json",
        max_expansions=2,
        max_output_tokens=256,
        accepted_delta_limit=16,
        seed=17,
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=SIGNING_KEY,
    )

    assert episode["result"]["goal_reached"] is False
    assert episode["result"]["budget_used"] == 2
    assert episode["result"]["invalid_operation_count"] == 2
    assert episode["result"]["invalid_operation_rate"] == 1.0
    assert all(event["status"] == "rejected" for event in episode["evidence"]["policy_events"])
    assert replay_model_search_episode(episode["evidence"], signing_key=SIGNING_KEY) == episode


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
        ancestor_receipt_digest=ancestor_digest,
    ).signed(SIGNING_KEY)

    episode = run_model_search_episode(
        tmp_path / "must-not-be-read.json",
        algorithm="not-validated-after-stop",
        modality="not-validated-after-stop",
        arm="base",
        model_identity={},
        policy=lambda _model_input: (_ for _ in ()).throw(AssertionError("must not be called")),
        max_expansions=0,
        max_output_tokens=0,
        accepted_delta_limit=0,
        seed=17,
        gate_receipt=gate,
        authorization_receipt=None,
        signing_key=SIGNING_KEY,
        ancestor_receipt_digest=ancestor_digest,
    )

    assert episode["result"]["outcome"] == StopOutcome.ANCESTOR_STOP.value
    assert episode["result"]["completion"] == "gated-not-run"
    assert episode["evidence"] is None
