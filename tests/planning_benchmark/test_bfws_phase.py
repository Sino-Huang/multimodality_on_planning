from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.bfws_model_input import (
    build_bounded_bfws_model_input,
    validate_bfws_teacher_operation,
)
from examples.planning_benchmark_slice.bfws_phase import (
    BFWSPhaseGateError,
    load_bfws_phase_gate,
)
from examples.planning_benchmark_slice.episode_evidence import materialize_episode_artifacts
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.search_context import materialize_search_trace
from examples.planning_benchmark_slice.search_episode import run_search_episode
from examples.planning_benchmark_slice.search_trace import TraceSegmentLimits
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

REPO_ROOT = Path(__file__).resolve().parents[2]
FREEZE = REPO_ROOT / "configs" / "experiments" / "bfws_phase_freeze_v1.json"
AUTHORIZATION = REPO_ROOT / "configs" / "experiments" / "bfws_phase_authorization_v1.json"
TASK = REPO_ROOT / "tests" / "fixtures" / "planning" / "iw_width_four.json"


def test_committed_bfws_gate_binds_six_freezes_and_replay_proven_development_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_text = Path.read_text

    def reject_fresh_test_access(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path.name == "fresh-test-manifest.jsonl":
            raise AssertionError("development phase loading accessed the fresh held-out test manifest")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", reject_fresh_test_access)
    gate = load_bfws_phase_gate(FREEZE, AUTHORIZATION)

    assert gate.phase_id == "issue-56-bfws-development-v1"
    assert set(gate.components) == {"trace", "corpus", "training", "reference", "threshold", "stop"}
    assert gate.components["trace"]["selected_instance_count"] == 105
    assert gate.components["trace"]["selected_stratum_count"] == 35
    assert gate.components["corpus"]["model_input_schema"] == "bounded_bfws_search_memory_v1"
    assert gate.components["corpus"]["accepted_delta_limit"] == 16
    assert gate.components["training"]["checkpoint_policy"]["rollout"] == "final"
    assert gate.components["reference"]["episode_model_call_limit"] == ("2 * matching exact_reference_decision_count")
    assert gate.components["reference"]["fresh_held_out_test_instance_count"] == 45
    assert gate.authorization["efficacy_test_access_authorized"] is False
    assert gate.receipt(stage="trace_generation")["outcome"] == StopOutcome.PASS.value


def test_bfws_development_authorization_rejects_test_access_and_manifest_drift(tmp_path: Path) -> None:
    gate = load_bfws_phase_gate(FREEZE, AUTHORIZATION)
    with pytest.raises(BFWSPhaseGateError, match="efficacy-test"):
        gate.require_run(stage="development_structural_gate", contract_id=gate.phase_id, split="test")

    authorization = json.loads(AUTHORIZATION.read_bytes())
    authorization["efficacy_test_access_authorized"] = True
    changed = tmp_path / "authorization.json"
    changed.write_text(json.dumps(authorization), encoding="utf-8")
    with pytest.raises(BFWSPhaseGateError, match="authorization"):
        load_bfws_phase_gate(FREEZE, changed)


def test_bfws_observation_and_corpus_input_share_bounded_exact_candidate_facts(tmp_path: Path) -> None:
    binding = ReceiptBinding(
        contract_id="issue-56-bfws-development-v1",
        attempt_id="bfws-observable-contract-test",
        output_root=tmp_path / "episode",
    )
    gate_receipt = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_id=gate_receipt.receipt_id)
    episode = run_search_episode(
        task_path=TASK,
        algorithm="best_first_width",
        modality="text-state",
        policy="exact",
        max_expansions=64,
        gate_receipt=gate_receipt,
        authorization_receipt=authorization,
    )

    task_bytes, trace_bytes = materialize_episode_artifacts(episode["evidence"])
    task = json.loads(task_bytes)
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    record_count = json.loads(trace_bytes)["record_count"]
    materialized = materialize_search_trace(
        trace_bytes,
        authority=authority,
        limits=TraceSegmentLimits(
            max_records=max(1, record_count),
            max_bytes=max(1_000_000, len(trace_bytes) * max(1, record_count)),
        ),
    )

    for index, event in enumerate(episode["evidence"]["events"]):
        observation = event["observation"]
        search_memory = observation["search_memory"]
        assert "frontier" not in search_memory
        assert "visited" not in search_memory
        assert "partition_novelty_tables" not in search_memory
        validate_bfws_teacher_operation(observation, event["operation"])

        expected = next(
            (candidate for candidate in observation["successor_candidates"] if not candidate["duplicate"]),
            None,
        )
        if expected is not None:
            assert expected["enqueued"] is True
            assert expected["evaluation"]["priority"] == event["bfws_transition"]["priority"]
            assert expected["evaluation"]["frontier_intent"] == event["operation"]["frontier_intent"]

        rolling = materialized.rolling_context_before(index, accepted_delta_limit=16)
        model_input, dropped = build_bounded_bfws_model_input(
            observation=observation,
            checkpoint=rolling.checkpoint,
            accepted_deltas=rolling.accepted_deltas,
            max_bytes=10_000_000,
        )
        repeated, repeated_dropped = build_bounded_bfws_model_input(
            observation=deepcopy(observation),
            checkpoint=rolling.checkpoint,
            accepted_deltas=rolling.accepted_deltas,
            max_bytes=10_000_000,
        )
        assert model_input == repeated
        assert dropped == repeated_dropped == 0
        for compact, source in zip(
            model_input["observation"]["candidates"],
            observation["successor_candidates"],
            strict=True,
        ):
            assert compact["action"]["name"] == source["grounded_action"]["name"]
            assert compact["target"] == "$"
            if source["evaluation"] is None:
                assert compact["eval"] is None
            assert set(compact["atoms"]) == {"added", "removed"}
            if source["evaluation"] is not None:
                assert "target_atoms" not in compact["eval"]
        assert model_input["search_memory"]["context_type"] == "bounded_bfws_search_memory"
        assert model_input["search_memory"]["schema_version"] == 1
