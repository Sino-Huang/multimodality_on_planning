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


SIGNING_KEY = b"issue-42-public-seam-test-key"


def _binding(**changes: str) -> ReceiptBinding:
    values = {
        "contract_id": "generation-contract-v1",
        "attempt_id": "attempt-001",
        "output_root": "/tmp/generated/attempt-001",
    }
    values.update(changes)
    return ReceiptBinding(**values)


def _pass_receipts(binding: ReceiptBinding) -> tuple[GateReceipt, AuthorizationReceipt]:
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS).signed(SIGNING_KEY)
    authorization = AuthorizationReceipt(
        binding=binding,
        gate_receipt_digest=gate.digest,
    ).signed(SIGNING_KEY)
    return gate, authorization


def test_stop_outcome_vocabulary_is_exact() -> None:
    assert [(outcome.name, outcome.value) for outcome in StopOutcome] == [
        ("PASS", "PASS"),
        ("VALID_STOP", "VALID_STOP"),
        ("INVALID", "INVALID"),
        ("ANCESTOR_STOP", "ANCESTOR_STOP"),
    ]


def test_receipts_are_signed_and_have_canonical_json() -> None:
    binding = _binding()
    gate, authorization = _pass_receipts(binding)
    run = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=SIGNING_KEY,
    )

    for receipt in (gate, authorization, run):
        assert receipt.verify_signature(SIGNING_KEY)
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
    assert binding.to_dict()["output_root"] == str(actual_root.resolve())
    with pytest.raises(ValueError, match="output_root must be absolute"):
        _binding(output_root="relative/output")


def test_only_matching_pass_and_authorization_permit_a_start() -> None:
    binding = _binding()
    gate, authorization = _pass_receipts(binding)

    receipt = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=SIGNING_KEY,
    )

    assert receipt.outcome is StopOutcome.PASS
    assert receipt.run_state == "authorized-to-start"
    assert receipt.start_permitted is True
    assert receipt.scientific_completion is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract_id", "other-contract"),
        ("attempt_id", "other-attempt"),
        ("output_root", "/tmp/generated/other-output"),
    ],
)
def test_contract_attempt_and_output_binding_mismatches_fail_closed(field: str, value: str) -> None:
    binding = _binding()
    gate, authorization = _pass_receipts(binding)
    requested_binding = replace(binding, **{field: value})

    receipt = evaluate_execution_permission(
        binding=requested_binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=SIGNING_KEY,
    )

    assert receipt.outcome is StopOutcome.INVALID
    assert receipt.run_state == "invalid-not-run"
    assert receipt.start_permitted is False
    assert receipt.scientific_completion is False


def test_missing_or_forged_authorization_fails_closed() -> None:
    binding = _binding()
    gate, authorization = _pass_receipts(binding)

    missing = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=None,
        signing_key=SIGNING_KEY,
    )
    forged = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=replace(authorization, gate_receipt_digest="0" * 64),
        signing_key=SIGNING_KEY,
    )

    assert missing.outcome is StopOutcome.INVALID
    assert forged.outcome is StopOutcome.INVALID
    assert missing.start_permitted is forged.start_permitted is False


@pytest.mark.parametrize("outcome", [StopOutcome.VALID_STOP, StopOutcome.ANCESTOR_STOP])
def test_governed_stops_create_gated_not_run_receipts(outcome: StopOutcome) -> None:
    binding = _binding()
    ancestor_digest = "a" * 64 if outcome is StopOutcome.ANCESTOR_STOP else None
    gate = GateReceipt(
        binding=binding,
        outcome=outcome,
        ancestor_receipt_digest=ancestor_digest,
    ).signed(SIGNING_KEY)

    receipt = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=None,
        ancestor_receipt_digest=ancestor_digest,
        signing_key=SIGNING_KEY,
    )

    assert receipt.outcome is outcome
    assert receipt.run_state == "gated-not-run"
    assert receipt.start_permitted is False
    assert receipt.scientific_completion is False
    assert receipt.ancestor_receipt_digest == ancestor_digest


def test_ancestor_stop_binds_the_supplied_ancestor_receipt_digest() -> None:
    binding = _binding()
    gate = GateReceipt(
        binding=binding,
        outcome=StopOutcome.ANCESTOR_STOP,
        ancestor_receipt_digest="a" * 64,
    ).signed(SIGNING_KEY)

    receipt = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=None,
        ancestor_receipt_digest="b" * 64,
        signing_key=SIGNING_KEY,
    )

    assert receipt.outcome is StopOutcome.INVALID
    assert receipt.run_state == "invalid-not-run"
    assert receipt.start_permitted is False


def test_invalid_never_claims_scientific_completion() -> None:
    binding = _binding()
    gate = GateReceipt(binding=binding, outcome=StopOutcome.INVALID).signed(SIGNING_KEY)

    receipt = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=None,
        signing_key=SIGNING_KEY,
    )

    assert receipt.outcome is StopOutcome.INVALID
    assert receipt.start_permitted is False
    assert receipt.scientific_completion is False
    with pytest.raises(ValueError, match="INVALID.*scientific completion"):
        RunReceipt(
            binding=binding,
            outcome=StopOutcome.INVALID,
            run_state="completed",
            start_permitted=False,
            scientific_completion=True,
            gate_receipt_digest=gate.digest,
        )


@pytest.mark.parametrize(
    ("outcome", "run_state", "start_permitted", "scientific_completion", "ancestor_digest"),
    [
        (StopOutcome.PASS, "gated-not-run", False, False, None),
        (StopOutcome.PASS, "authorized-to-start", True, True, None),
        (StopOutcome.PASS, "completed", False, False, None),
        (StopOutcome.VALID_STOP, "authorized-to-start", True, False, None),
        (StopOutcome.VALID_STOP, "gated-not-run", False, True, None),
        (StopOutcome.ANCESTOR_STOP, "gated-not-run", False, False, None),
        (StopOutcome.ANCESTOR_STOP, "gated-not-run", False, False, "not-a-digest"),
        (StopOutcome.INVALID, "authorized-to-start", True, False, None),
        (StopOutcome.INVALID, "completed", False, True, None),
    ],
)
def test_direct_run_receipt_construction_rejects_contradictory_states(
    outcome: StopOutcome,
    run_state: str,
    start_permitted: bool,
    scientific_completion: bool,
    ancestor_digest: str | None,
) -> None:
    with pytest.raises(ValueError, match="RunReceipt semantics"):
        RunReceipt(
            binding=_binding(),
            outcome=outcome,
            run_state=run_state,
            start_permitted=start_permitted,
            scientific_completion=scientific_completion,
            gate_receipt_digest="a" * 64,
            authorization_receipt_digest="b" * 64 if outcome is StopOutcome.PASS else None,
            ancestor_receipt_digest=ancestor_digest,
        )


def test_valid_completed_pass_receipt_can_claim_scientific_completion() -> None:
    receipt = RunReceipt(
        binding=_binding(),
        outcome=StopOutcome.PASS,
        run_state="completed",
        start_permitted=False,
        scientific_completion=True,
        gate_receipt_digest="a" * 64,
        authorization_receipt_digest="b" * 64,
    ).signed(SIGNING_KEY)

    assert receipt.verify_signature(SIGNING_KEY)


@pytest.mark.parametrize(
    ("outcome", "ancestor_digest"),
    [
        (StopOutcome.ANCESTOR_STOP, None),
        (StopOutcome.ANCESTOR_STOP, "not-a-digest"),
        (StopOutcome.PASS, "a" * 64),
        (StopOutcome.VALID_STOP, "a" * 64),
        (StopOutcome.INVALID, "a" * 64),
    ],
)
def test_direct_gate_receipt_construction_rejects_invalid_ancestor_binding(
    outcome: StopOutcome,
    ancestor_digest: str | None,
) -> None:
    with pytest.raises(ValueError, match="GateReceipt semantics"):
        GateReceipt(
            binding=_binding(),
            outcome=outcome,
            ancestor_receipt_digest=ancestor_digest,
        )


def test_signing_revalidates_receipt_semantics() -> None:
    run = RunReceipt(
        binding=_binding(),
        outcome=StopOutcome.PASS,
        run_state="authorized-to-start",
        start_permitted=True,
        scientific_completion=False,
        gate_receipt_digest="a" * 64,
        authorization_receipt_digest="b" * 64,
    )
    object.__setattr__(run, "scientific_completion", True)

    gate = GateReceipt(
        binding=_binding(),
        outcome=StopOutcome.ANCESTOR_STOP,
        ancestor_receipt_digest="c" * 64,
    )
    object.__setattr__(gate, "ancestor_receipt_digest", None)

    with pytest.raises(ValueError, match="RunReceipt semantics"):
        run.signed(SIGNING_KEY)
    with pytest.raises(ValueError, match="GateReceipt semantics"):
        gate.signed(SIGNING_KEY)
