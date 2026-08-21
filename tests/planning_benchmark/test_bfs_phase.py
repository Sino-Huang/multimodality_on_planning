from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.bfs_generation import run_frozen_bfs_generation_smoke
from examples.planning_benchmark_slice.bfs_phase import BFSPhaseGate, BFSPhaseGateError, load_bfs_phase_gate
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

REPO_ROOT = Path(__file__).resolve().parents[2]
FREEZE_MANIFEST = REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json"
AUTHORIZATION_MANIFEST = REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json"
V3_FREEZE_MANIFEST = REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v3.json"
V3_AUTHORIZATION_MANIFEST = REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v3.json"
TASK_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_nontrivial.json"
SIGNING_KEY = b"issue-49-bfs-phase-test-key"


def _phase_gate() -> BFSPhaseGate:
    return load_bfs_phase_gate(FREEZE_MANIFEST, AUTHORIZATION_MANIFEST)


def _request(tmp_path: Path, *, contract_id: str) -> GenerationRequest:
    binding = ReceiptBinding(
        contract_id=contract_id,
        attempt_id="issue-49-bfs-smoke-001",
        output_root=(tmp_path / "corpus-output").resolve(),
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS).signed(SIGNING_KEY)
    return GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(
            binding=binding,
            gate_receipt_digest=gate.digest,
        ).signed(SIGNING_KEY),
        signing_key=SIGNING_KEY,
        receipt_root=(tmp_path / "receipts").resolve(),
    )


def test_committed_bfs_phase_freezes_every_authorized_input_family() -> None:
    gate = _phase_gate()

    assert gate.phase_id == "issue-49-bfs-development-v1"
    assert gate.freeze["models"]["primary"]["revision"] == "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
    assert gate.freeze["data"]["allowed_splits"] == ["train", "dev"]
    assert gate.freeze["data"]["held_out_split"] == "test"
    assert gate.freeze["seeds"] == [17, 29, 43, 71, 101]
    assert set(gate.freeze["training"]["arms"]) == {
        "base",
        "exact_classical",
        "operational_sft",
        "process_sft",
        "random_valid",
    }
    assert set(gate.freeze["thresholds"]) == {
        "exact_reference_invariant_valid_success",
        "expert_trace_minimum_per_domain_difficulty",
        "expert_trace_replay_rate",
        "maximum_invalid_operation_rate",
        "operational_process_record_contamination",
        "process_sft_absolute_gain_over_best_control",
        "process_sft_gain_bootstrap_lower_bound",
        "process_sft_invariant_valid_success",
    }
    assert set(gate.freeze["stop_rules"]) == {
        "ancestor_stop",
        "invalid",
        "no_retuning",
        "pass",
        "valid_stop",
    }
    assert gate.authorization["downstream_issues"] == [50, 51, 52, 53, 54]


def test_phase_gate_supplies_the_frozen_budget_to_a_complete_bfs_run(tmp_path: Path) -> None:
    phase_gate = _phase_gate()
    request = _request(tmp_path, contract_id=phase_gate.phase_id)

    receipt = run_frozen_bfs_generation_smoke(
        task_path=TASK_FIXTURE,
        request=request,
        phase_gate=phase_gate,
        difficulty="easy",
    )

    assert receipt.outcome is StopOutcome.PASS
    assert receipt.status == "completed"
    assert receipt.scientific_completion is True
    assert receipt.binding.contract_id == phase_gate.phase_id
    assert receipt.execution_result is not None
    phase_receipt = phase_gate.receipt(stage="trace_generation", difficulty="easy")
    assert phase_receipt["outcome"] == StopOutcome.PASS.value
    assert phase_receipt["max_expansions"] == 64


def test_phase_authorization_is_required_before_a_bfs_output_is_created(tmp_path: Path) -> None:
    phase_gate = _phase_gate()
    request = _request(tmp_path, contract_id="unfrozen-bfs-contract")

    with pytest.raises(BFSPhaseGateError, match="contract_id"):
        run_frozen_bfs_generation_smoke(
            task_path=TASK_FIXTURE,
            request=request,
            phase_gate=phase_gate,
            difficulty="easy",
        )

    assert not Path(request.binding.output_root).exists()
    assert not Path(request.receipt_root).exists()


def test_phase_gate_rejects_an_authorization_for_different_freeze_bytes(tmp_path: Path) -> None:
    authorization = json.loads(AUTHORIZATION_MANIFEST.read_text(encoding="utf-8"))
    authorization["freeze_manifest_sha256"] = "0" * 64
    mismatched_authorization = tmp_path / "authorization.json"
    mismatched_authorization.write_text(json.dumps(authorization), encoding="utf-8")

    with pytest.raises(BFSPhaseGateError, match="does not match its authorization"):
        load_bfs_phase_gate(FREEZE_MANIFEST, mismatched_authorization)


def test_v1_manifests_remain_byte_identical_and_cannot_authorize_v3() -> None:
    assert hashlib.sha256(FREEZE_MANIFEST.read_bytes()).hexdigest() == (
        "5d00eb28c348c1d8a85472e834b52762683b0ddbbf9904c912bfaafdce6f23fd"
    )
    assert hashlib.sha256(AUTHORIZATION_MANIFEST.read_bytes()).hexdigest() == (
        "6ddd28ca0586faadf13971b14af002ea6eefb1aacafb0a671a4eb70f06b7c8b7"
    )
    with pytest.raises(BFSPhaseGateError, match="v3 authorization"):
        load_bfs_phase_gate(V3_FREEZE_MANIFEST, AUTHORIZATION_MANIFEST)


def test_committed_v3_gate_binds_the_qualification_pass_and_process_only_contract() -> None:
    gate = load_bfs_phase_gate(V3_FREEZE_MANIFEST, V3_AUTHORIZATION_MANIFEST)

    assert gate.phase_id == "issue-111-bfs-expansion-qualified-pilot-v3"
    assert gate.freeze["source_issue"] == 111
    assert gate.freeze["data"]["qualification"]["outcome"] == "PASS"
    assert gate.freeze["data"]["qualification"]["selected_task_count"] == 90
    assert gate.freeze["implementation"]["corpus_materialization_revision"] == (
        "82422c2269c22ddbb8da76889a222cc7500ea74c"
    )
    assert gate.freeze["implementation"]["process_memory_projection"] == "bounded_bfs_search_memory_v3"
    assert gate.freeze["data"]["development_counts_by_split_and_difficulty"] == {
        split: {difficulty: 15 for difficulty in ("easy", "medium", "hard")} for split in ("train", "dev")
    }
    assert set(gate.freeze["training"]["arms"]) == {
        "base",
        "exact_classical",
        "process_sft",
        "random_valid",
    }
    assert "operational_sft" not in gate.authorization["authorized_stages"]
    assert gate.authorization["downstream_issues"] == [54]
