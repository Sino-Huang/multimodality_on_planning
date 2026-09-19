from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    RunReceipt,
    StopOutcome,
    evaluate_execution_permission,
)


def _binding(**changes: str) -> ReceiptBinding:
    values = {
        "contract_id": "generation-contract-v1",
        "attempt_id": "attempt-001",
        "output_root": "/tmp/generated/attempt-001",
    }
    values.update(changes)
    return ReceiptBinding(**values)


def _pass_receipts(binding: ReceiptBinding) -> tuple[GateReceipt, AuthorizationReceipt]:
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    return gate, AuthorizationReceipt(binding=binding, gate_receipt_id=gate.receipt_id)


def test_stop_outcome_vocabulary_is_exact() -> None:
    assert [outcome.value for outcome in StopOutcome] == [
        "PASS",
        "VALID_STOP",
        "INVALID",
        "ANCESTOR_STOP",
    ]


def test_receipts_are_canonical_and_use_readable_ids() -> None:
    binding = _binding()
    gate, authorization = _pass_receipts(binding)
    run = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )

    assert gate.receipt_id == "gate:generation-contract-v1:attempt-001:PASS"
    assert authorization.gate_receipt_id == gate.receipt_id
    assert run.authorization_receipt_id == authorization.receipt_id
    for receipt in (gate, authorization, run):
        assert "signature" not in receipt.to_dict()
        assert receipt.canonical_json() == json.dumps(
            receipt.to_dict(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )


def test_receipt_binding_canonicalizes_absolute_output_root_and_rejects_relative_paths(tmp_path: Path) -> None:
    actual_root = tmp_path / "actual-output"
    actual_root.mkdir()
    symlink_root = tmp_path / "output-link"
    symlink_root.symlink_to(actual_root, target_is_directory=True)

    binding = _binding(output_root=str(symlink_root))

    assert binding.output_root == str(actual_root.resolve())
    with pytest.raises(ValueError, match="output_root must be absolute"):
        _binding(output_root="relative/output")


def test_only_matching_pass_and_authorization_permit_a_start() -> None:
    binding = _binding()
    gate, authorization = _pass_receipts(binding)

    permitted = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )
    missing = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=None,
    )
    mismatched = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=replace(authorization, gate_receipt_id="another-gate"),
    )

    assert permitted.outcome is StopOutcome.PASS
    assert permitted.start_permitted is True
    assert missing.outcome is StopOutcome.INVALID
    assert mismatched.outcome is StopOutcome.INVALID


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract_id", "other-contract"),
        ("attempt_id", "other-attempt"),
        ("output_root", "/tmp/generated/other-output"),
    ],
)
def test_binding_mismatches_do_not_permit_a_start(field: str, value: str) -> None:
    binding = _binding()
    gate, authorization = _pass_receipts(binding)

    receipt = evaluate_execution_permission(
        binding=replace(binding, **{field: value}),
        gate_receipt=gate,
        authorization_receipt=authorization,
    )

    assert receipt.outcome is StopOutcome.INVALID
    assert receipt.start_permitted is False
    assert receipt.scientific_completion is False


@pytest.mark.parametrize("outcome", [StopOutcome.VALID_STOP, StopOutcome.ANCESTOR_STOP])
def test_governed_stops_create_gated_not_run_receipts(outcome: StopOutcome) -> None:
    binding = _binding()
    ancestor_id = "run:parent:attempt:completed" if outcome is StopOutcome.ANCESTOR_STOP else None
    gate = GateReceipt(binding=binding, outcome=outcome, ancestor_receipt_id=ancestor_id)

    receipt = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=None,
        ancestor_receipt_id=ancestor_id,
    )

    assert receipt.outcome is outcome
    assert receipt.run_state == "gated-not-run"
    assert receipt.start_permitted is False
    assert receipt.ancestor_receipt_id == ancestor_id


def test_completed_pass_receipt_records_direct_receipt_references() -> None:
    receipt = RunReceipt(
        binding=_binding(),
        outcome=StopOutcome.PASS,
        run_state="completed",
        start_permitted=False,
        scientific_completion=True,
        gate_receipt_id="gate:generation-contract-v1:attempt-001:PASS",
        authorization_receipt_id="authorization:generation-contract-v1:attempt-001",
    )

    assert receipt.scientific_completion is True
    assert receipt.receipt_id == "run:generation-contract-v1:attempt-001:completed"
