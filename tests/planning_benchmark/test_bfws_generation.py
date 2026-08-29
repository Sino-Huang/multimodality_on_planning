from __future__ import annotations

import gzip
import json
from copy import deepcopy
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.bfws_generation import (
    generate_frozen_bfws_trace,
    preflight_frozen_bfws_trace_generation,
    run_frozen_bfws_trace_generation,
)
from examples.planning_benchmark_slice.bfws_phase import load_bfws_phase_gate
from examples.planning_benchmark_slice.bfws_trace_audit import (
    _validate_audit_result,
    audit_frozen_bfws_trace,
)
from examples.planning_benchmark_slice.episode_evidence import replay_episode_evidence
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

REPO_ROOT = Path(__file__).resolve().parents[2]
FREEZE = REPO_ROOT / "configs" / "experiments" / "bfws_phase_freeze_v1.json"
AUTHORIZATION = REPO_ROOT / "configs" / "experiments" / "bfws_phase_authorization_v1.json"


def _request(tmp_path: Path) -> GenerationRequest:
    binding = ReceiptBinding(
        contract_id="issue-56-bfws-development-v1",
        attempt_id="issue-57-trace-test",
        output_root=(tmp_path / "exact-traces").resolve(),
    )
    gate = GateReceipt(binding, StopOutcome.PASS)
    return GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(binding, gate.receipt_id),
        receipt_root=(tmp_path / "receipts").resolve(),
    )


def test_bfws_trace_preflight_covers_only_the_frozen_development_panel() -> None:
    gate = load_bfws_phase_gate(FREEZE, AUTHORIZATION)

    rows = preflight_frozen_bfws_trace_generation(gate)

    assert len(rows) == 105
    assert sum(row["exact_reference_decision_count"] for row in rows) == 69_019
    assert {(row["domain_id"], row["difficulty"]) for row in rows} == {
        (row["domain_id"], row["difficulty"]) for row in rows if row["split"] == "dev"
    }
    assert {row["source_split"] for row in rows} == {"train"}
    assert gate.authorization["efficacy_test_access_authorized"] is False


def test_single_frozen_bfws_trace_replays_and_is_reused_on_resume(tmp_path: Path) -> None:
    gate = load_bfws_phase_gate(FREEZE, AUTHORIZATION)
    row = next(
        row for row in preflight_frozen_bfws_trace_generation(gate) if row["instance_id"] == "storage-train-easy-0004"
    )
    request = _request(tmp_path)

    generated = generate_frozen_bfws_trace(
        row=row,
        request=request,
        phase_gate=gate,
        resume=False,
    )

    output_root = Path(request.binding.output_root)
    evidence_path = output_root / generated["evidence"]["path"]
    trace_path = output_root / generated["search_trace"]["path"]
    assert generated["result"]["decision_count"] == row["exact_reference_decision_count"] == 3
    assert generated["result"]["expansion_count"] == row["exact_reference_expansion_count"] == 3
    assert generated["result"]["goal_reached"] is True
    replayed = replay_episode_evidence(evidence_path)
    assert replayed["result"]["decision_count"] == generated["result"]["decision_count"]
    assert trace_path.name == "search-trace.json.gz"
    assert json.loads(gzip.decompress(trace_path.read_bytes()))["record_count"] == 3

    evidence_bytes = evidence_path.read_bytes()
    trace_bytes = trace_path.read_bytes()
    resumed = generate_frozen_bfws_trace(
        row=row,
        request=request,
        phase_gate=gate,
        resume=True,
    )

    assert resumed == generated
    assert evidence_path.read_bytes() == evidence_bytes
    assert trace_path.read_bytes() == trace_bytes

    audit = audit_frozen_bfws_trace(
        row=row,
        evidence_path=evidence_path,
        search_trace_path=trace_path,
        phase_gate=gate,
        input_token_counter=lambda _model_input: 1,
        target_token_counter=lambda _target: 1,
    )
    assert audit["decision_count"] == 3
    assert audit["live_replay_input_mismatch_count"] == 0
    assert audit["teacher_decision_rejection_count"] == 0
    assert audit["target_parse_rejection_count"] == 0
    assert audit["input_over_budget_count"] == 0
    assert audit["target_over_budget_count"] == 0
    assert len(audit["teacher_records"]) == 3
    _validate_audit_result(audit, row=row, phase_gate=gate)

    stale = deepcopy(audit)
    stale["teacher_records"][1]["record_index"] = 0
    with pytest.raises(ValueError, match="audit part"):
        _validate_audit_result(stale, row=row, phase_gate=gate)


def test_bfws_trace_generation_retains_a_gated_not_run_receipt(tmp_path: Path) -> None:
    gate = load_bfws_phase_gate(FREEZE, AUTHORIZATION)
    binding = ReceiptBinding(
        contract_id=gate.phase_id,
        attempt_id="issue-57-valid-stop-test",
        output_root=(tmp_path / "exact-traces").resolve(),
    )
    request = GenerationRequest(
        binding=binding,
        gate_receipt=GateReceipt(binding, StopOutcome.VALID_STOP),
        authorization_receipt=None,
        receipt_root=(tmp_path / "receipts").resolve(),
    )

    receipt = run_frozen_bfws_trace_generation(
        request=request,
        phase_gate=gate,
        resume=False,
    )

    assert receipt.outcome is StopOutcome.VALID_STOP
    assert receipt.status == "gated_not_run"
    assert receipt.scientific_completion is False
    assert receipt.execution_result is None
    assert not Path(binding.output_root).exists()
