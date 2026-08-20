from __future__ import annotations

from pathlib import Path

from examples.planning_benchmark_slice.search_episode import (
    replay_search_episode,
    run_search_episode,
)
from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    StopOutcome,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
NONTRIVIAL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_nontrivial.json"
SIGNING_KEY = b"issue-47-search-episode-test-key"


def test_exact_text_bfs_completes_with_fifo_evidence_that_replays(tmp_path: Path) -> None:
    binding = ReceiptBinding(
        contract_id="issue-47-text-bfs",
        attempt_id="slice-1-exact-policy",
        output_root=tmp_path / "episode-evidence",
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS).signed(SIGNING_KEY)
    authorization = AuthorizationReceipt(
        binding=binding,
        gate_receipt_digest=gate.digest,
    ).signed(SIGNING_KEY)

    episode = run_search_episode(
        task_path=NONTRIVIAL_FIXTURE,
        algorithm="bfs",
        modality="text-state",
        policy="exact",
        max_expansions=64,
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=SIGNING_KEY,
    )

    assert episode["result"]["completion"] == "completed"
    assert episode["result"]["outcome"] == StopOutcome.PASS.value
    assert episode["result"]["scientific_completion"] is True
    assert episode["result"]["goal_reached"] is True

    events = episode["evidence"]["events"]
    assert events
    assert {event["expansion_index"] for event in events} == set(range(episode["result"]["expansion_count"]))
    for event in events:
        assert event["expanded_state_id"]
        assert "frontier_before" not in event
        assert "frontier_after" not in event
        assert len(event["newly_enqueued_state_ids"]) <= 1

    assert replay_search_episode(episode["evidence"], signing_key=SIGNING_KEY) == episode


def test_seeded_random_text_bfs_is_reproducible_and_replayable(tmp_path: Path) -> None:
    binding = ReceiptBinding(
        contract_id="issue-47-text-bfs",
        attempt_id="slice-2-seeded-random-policy",
        output_root=tmp_path / "episode-evidence",
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS).signed(SIGNING_KEY)
    authorization = AuthorizationReceipt(
        binding=binding,
        gate_receipt_digest=gate.digest,
    ).signed(SIGNING_KEY)
    common_request = {
        "task_path": NONTRIVIAL_FIXTURE,
        "algorithm": "bfs",
        "modality": "text-state",
        "max_expansions": 64,
        "gate_receipt": gate,
        "authorization_receipt": authorization,
        "signing_key": SIGNING_KEY,
    }

    first = run_search_episode(policy="random", random_seed=47, **common_request)
    second = run_search_episode(policy="random", random_seed=47, **common_request)
    exact = run_search_episode(policy="exact", **common_request)

    for episode in (first, second):
        assert episode["result"]["completion"] == "completed"
        assert episode["result"]["outcome"] == StopOutcome.PASS.value
        assert episode["result"]["scientific_completion"] is True
        assert episode["result"]["goal_reached"] is True
        assert replay_search_episode(episode["evidence"], signing_key=SIGNING_KEY) == episode

    assert first == second
    assert first["evidence"] != exact["evidence"]


def test_governed_stops_do_not_read_or_execute_a_missing_task(tmp_path: Path) -> None:
    binding = ReceiptBinding(
        contract_id="issue-47-text-bfs",
        attempt_id="slice-3-governed-stops",
        output_root=tmp_path / "episode-evidence",
    )
    pass_gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS).signed(SIGNING_KEY)
    valid_stop_gate = GateReceipt(binding=binding, outcome=StopOutcome.VALID_STOP).signed(SIGNING_KEY)
    invalid_gate = GateReceipt(binding=binding, outcome=StopOutcome.INVALID).signed(SIGNING_KEY)
    ancestor_digest = "a" * 64
    ancestor_stop_gate = GateReceipt(
        binding=binding,
        outcome=StopOutcome.ANCESTOR_STOP,
        ancestor_receipt_digest=ancestor_digest,
    ).signed(SIGNING_KEY)
    cases = (
        (pass_gate, None, None, StopOutcome.INVALID, "invalid-not-run"),
        (valid_stop_gate, None, None, StopOutcome.VALID_STOP, "gated-not-run"),
        (invalid_gate, None, None, StopOutcome.INVALID, "invalid-not-run"),
        (
            ancestor_stop_gate,
            None,
            ancestor_digest,
            StopOutcome.ANCESTOR_STOP,
            "gated-not-run",
        ),
    )

    for gate, authorization, supplied_ancestor_digest, expected_outcome, expected_run_state in cases:
        episode = run_search_episode(
            task_path=tmp_path / "intentionally-nonexistent-task.json",
            algorithm="bfs",
            modality="text-state",
            policy="exact",
            max_expansions=64,
            gate_receipt=gate,
            authorization_receipt=authorization,
            signing_key=SIGNING_KEY,
            ancestor_receipt_digest=supplied_ancestor_digest,
        )

        run_receipt = episode["result"]["run_receipt"]
        assert run_receipt["outcome"] == expected_outcome.value
        assert run_receipt["run_state"] == expected_run_state
        assert run_receipt["scientific_completion"] is False
        assert episode["result"]["expansion_count"] == 0
        assert episode["evidence"] is None
