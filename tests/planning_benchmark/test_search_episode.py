from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.search_episode import (
    EVIDENCE_SCHEMA_VERSION,
    SearchEpisodeError,
    SearchEpisodeVariant,
    replay_search_episode,
    run_search_episode,
    run_search_episode_batch,
)
from examples.planning_benchmark_slice.search_memory import SearchMemory
from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    StopOutcome,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
NONTRIVIAL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_nontrivial.json"
IW_PRUNING_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "iw_novelty_pruning.json"
IW_WIDTH_TWO_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "iw_width_two.json"
IW_WIDTH_FOUR_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "iw_width_four.json"


def test_exact_text_bfs_completes_with_fifo_evidence_that_replays(tmp_path: Path) -> None:
    binding = ReceiptBinding(
        contract_id="issue-47-text-bfs",
        attempt_id="slice-1-exact-policy",
        output_root=tmp_path / "episode-evidence",
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(
        binding=binding,
        gate_receipt_id=gate.receipt_id,
    )

    episode = run_search_episode(
        task_path=NONTRIVIAL_FIXTURE,
        algorithm="bfs",
        modality="text-state",
        policy="exact",
        max_expansions=64,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )

    assert episode["result"]["completion"] == "completed"
    assert episode["result"]["outcome"] == StopOutcome.PASS.value
    assert episode["result"]["scientific_completion"] is True
    assert episode["result"]["goal_reached"] is True
    assert episode["evidence"]["schema_version"] == EVIDENCE_SCHEMA_VERSION

    events = episode["evidence"]["events"]
    assert events
    assert {event["expansion_index"] for event in events} == set(range(episode["result"]["expansion_count"]))
    for event in events:
        assert event["expanded_state_id"]
        assert "frontier_before" not in event
        assert "frontier_after" not in event
        assert len(event["newly_enqueued_state_ids"]) <= 1

    assert replay_search_episode(episode["evidence"]) == episode


def test_seeded_random_text_bfs_is_reproducible_and_replayable(tmp_path: Path) -> None:
    binding = ReceiptBinding(
        contract_id="issue-47-text-bfs",
        attempt_id="slice-2-seeded-random-policy",
        output_root=tmp_path / "episode-evidence",
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(
        binding=binding,
        gate_receipt_id=gate.receipt_id,
    )
    common_request = {
        "task_path": NONTRIVIAL_FIXTURE,
        "algorithm": "bfs",
        "modality": "text-state",
        "max_expansions": 64,
        "gate_receipt": gate,
        "authorization_receipt": authorization,
    }

    first = run_search_episode(policy="random", random_seed=47, **common_request)
    second = run_search_episode(policy="random", random_seed=47, **common_request)
    exact = run_search_episode(policy="exact", **common_request)

    for episode in (first, second):
        assert episode["result"]["completion"] == "completed"
        assert episode["result"]["outcome"] == StopOutcome.PASS.value
        assert episode["result"]["scientific_completion"] is True
        assert episode["result"]["goal_reached"] is True
        assert replay_search_episode(episode["evidence"]) == episode

    assert first == second
    assert first["evidence"] != exact["evidence"]


def test_exact_text_iw1_completes_with_typed_novelty_evidence_that_replays(tmp_path: Path) -> None:
    binding = ReceiptBinding(
        contract_id="issue-55-text-iw1",
        attempt_id="slice-exact-iw1-policy",
        output_root=tmp_path / "episode-evidence",
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_id=gate.receipt_id)

    episode = run_search_episode(
        task_path=IW_PRUNING_FIXTURE,
        algorithm="iterated_width",
        modality="text-state",
        policy="exact",
        max_expansions=64,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )

    assert episode["result"]["goal_reached"] is True
    assert episode["result"]["completion"] == "completed"
    assert episode["result"]["outcome"] == StopOutcome.PASS.value
    assert episode["result"]["scientific_completion"] is True
    assert episode["result"]["expansion_count"] <= 64
    assert episode["result"]["algorithm_invariants_hold"] is True
    assert episode["result"]["decision_count"] == 7
    assert episode["result"]["invariant_valid_success"] is True
    assert episode["result"]["fallback_used"] is False
    assert episode["evidence"]["header"]["request"]["recovery_policy"] == "prohibited"
    run_receipt = episode["result"]["run_receipt"]
    assert run_receipt["gate_receipt_id"] == gate.receipt_id
    assert run_receipt["authorization_receipt_id"] == authorization.receipt_id

    events = episode["evidence"]["events"]
    novelty_transitions = [event["novelty_transition"] for event in events]
    assert novelty_transitions
    assert all(transition["width"] == 1 for transition in novelty_transitions)
    assert any(transition["decision"] == "prune" for transition in novelty_transitions)
    assert any(
        len(transition["novelty_table_after"]) > len(transition["novelty_table_before"])
        for transition in novelty_transitions
    )
    assert all(
        event["operation"].get("operation_type") == "retire_frontier"
        or event["operation"]["evaluate_target"] is True
        for event in events
    )
    first_observation = events[0]["observation"]
    assert first_observation["task_context"]["static_initial_facts"] == []
    assert first_observation["search_memory"]["visited"]
    assert first_observation["successor_candidates"]
    assert all(
        {"target_state_id", "visited", "novel_item", "pruned", "enqueue_eligible"} <= candidate.keys()
        for candidate in first_observation["successor_candidates"]
    )
    assert replay_search_episode(episode["evidence"]) == episode

    tampered = deepcopy(episode["evidence"])
    tampered["events"][0]["novelty_transition"]["novel_item"] = ["invented-feature"]
    with pytest.raises(SearchEpisodeError, match="IW novelty invariant"):
        replay_search_episode(tampered)


def test_exact_iterative_width_escalates_until_width_two_solves(tmp_path: Path) -> None:
    binding = ReceiptBinding(
        contract_id="issue-55-text-iw3",
        attempt_id="slice-exact-iterative-width",
        output_root=tmp_path / "episode-evidence",
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_id=gate.receipt_id)

    episode = run_search_episode(
        task_path=IW_WIDTH_TWO_FIXTURE,
        algorithm="iterated_width",
        modality="text-state",
        policy="exact",
        max_expansions=64,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )

    assert episode["result"]["goal_reached"] is True
    assert episode["result"]["width_sequence"] == [1, 2]
    assert episode["result"]["solving_width"] == 2
    assert len(episode["result"]["expansion_count_by_width"]) == 2
    assert len(episode["result"]["decision_count_by_width"]) == 2
    assert episode["evidence"]["header"]["request"]["max_width"] == 3
    assert episode["evidence"]["header"]["request"]["width_policy"] == "iterate_1_to_max_until_solved"
    assert {event["width_attempt"] for event in episode["evidence"]["events"]} == {0, 1}
    attempt_roots = {
        attempt: next(event for event in episode["evidence"]["events"] if event["width_attempt"] == attempt)
        for attempt in (0, 1)
    }
    assert [attempt_roots[attempt]["novelty_transition"]["width"] for attempt in (0, 1)] == [1, 2]
    assert all(attempt_roots[attempt]["novelty_transition"]["novelty_table_before"] == [] for attempt in (0, 1))
    assert replay_search_episode(episode["evidence"]) == episode


def test_exact_bfws_retains_residual_novelty_and_solves_width_four_fixture(tmp_path: Path) -> None:
    binding = ReceiptBinding(
        contract_id="issue-55-text-bfws",
        attempt_id="slice-exact-bfws",
        output_root=tmp_path / "episode-evidence",
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_id=gate.receipt_id)

    episode = run_search_episode(
        task_path=IW_WIDTH_FOUR_FIXTURE,
        algorithm="best_first_width",
        modality="text-state",
        policy="exact",
        max_expansions=64,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )

    assert episode["result"]["goal_reached"] is True
    assert episode["result"]["algorithm_invariants_hold"] is True
    assert episode["result"]["novelty_pruned_count"] == 0
    assert episode["result"]["residual_novelty_retained_count"] > 0
    assert episode["evidence"]["header"]["request"]["novelty_precision"] == 2
    assert episode["evidence"]["header"]["request"]["high_novelty_policy"] == "enqueue"
    assert any(event["bfws_transition"]["novelty_bucket"] == 3 for event in episode["evidence"]["events"])
    assert replay_search_episode(episode["evidence"]) == episode

    tampered = deepcopy(episode["evidence"])
    residual = next(event for event in tampered["events"] if event["bfws_transition"]["novelty_bucket"] == 3)
    residual["bfws_transition"]["residual_novelty_retained"] = False
    with pytest.raises(SearchEpisodeError, match="BFWS invariant"):
        replay_search_episode(tampered)


def test_bfs_variant_batch_parses_one_authority_and_preserves_variant_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    binding = ReceiptBinding(
        contract_id="issue-47-text-bfs",
        attempt_id="slice-batched-policies",
        output_root=tmp_path / "episode-evidence",
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_id=gate.receipt_id)
    original = PDDLStateAuthority.from_pddl
    parse_count = 0

    def counted(domain_pddl: str, problem_pddl: str) -> PDDLStateAuthority:
        nonlocal parse_count
        parse_count += 1
        return original(domain_pddl, problem_pddl)

    monkeypatch.setattr(PDDLStateAuthority, "from_pddl", counted)
    variants = (
        SearchEpisodeVariant("exact", None),
        *(SearchEpisodeVariant("random", seed) for seed in (17, 29, 43, 71, 101)),
    )

    episodes = run_search_episode_batch(
        task_path=NONTRIVIAL_FIXTURE,
        algorithm="bfs",
        modality="text-state",
        variants=variants,
        max_expansions=64,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )

    requests = [episode["evidence"]["header"]["request"] for episode in episodes]
    assert parse_count == 1
    assert [request["policy"] for request in requests] == ["exact", *("random" for _ in range(5))]
    assert [request.get("random_seed") for request in requests] == [None, 17, 29, 43, 71, 101]


def test_v3_execution_freezes_immutable_search_memory_once(tmp_path: Path, monkeypatch) -> None:
    binding = ReceiptBinding(
        contract_id="issue-47-text-bfs",
        attempt_id="slice-mutable-runtime",
        output_root=tmp_path / "episode-evidence",
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_id=gate.receipt_id)
    original_create = SearchMemory._create.__func__
    create_count = 0

    def counted_create(cls, **kwargs):
        nonlocal create_count
        create_count += 1
        return original_create(cls, **kwargs)

    monkeypatch.setattr(SearchMemory, "_create", classmethod(counted_create))

    episode = run_search_episode(
        task_path=NONTRIVIAL_FIXTURE,
        algorithm="bfs",
        modality="text-state",
        policy="exact",
        max_expansions=64,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )

    assert episode["result"]["goal_reached"] is True
    assert len(episode["evidence"]["events"]) > 1
    assert create_count == 1


@pytest.mark.parametrize("algorithm", ["bfs", "iterated_width", "best_first_width"])
def test_governed_stops_do_not_read_or_execute_a_missing_task(tmp_path: Path, algorithm: str) -> None:
    binding = ReceiptBinding(
        contract_id="issue-47-text-bfs",
        attempt_id="slice-3-governed-stops",
        output_root=tmp_path / "episode-evidence",
    )
    pass_gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    valid_stop_gate = GateReceipt(binding=binding, outcome=StopOutcome.VALID_STOP)
    invalid_gate = GateReceipt(binding=binding, outcome=StopOutcome.INVALID)
    ancestor_digest = "a" * 64
    ancestor_stop_gate = GateReceipt(
        binding=binding,
        outcome=StopOutcome.ANCESTOR_STOP,
        ancestor_receipt_id=ancestor_digest,
    )
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
            algorithm=algorithm,
            modality="text-state",
            policy="exact",
            max_expansions=64,
            gate_receipt=gate,
            authorization_receipt=authorization,
            ancestor_receipt_id=supplied_ancestor_digest,
        )

        run_receipt = episode["result"]["run_receipt"]
        assert run_receipt["outcome"] == expected_outcome.value
        assert run_receipt["run_state"] == expected_run_state
        assert run_receipt["scientific_completion"] is False
        assert episode["result"]["expansion_count"] == 0
        assert episode["evidence"] is None
