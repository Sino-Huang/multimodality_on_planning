"""Minimal receipt contract for governed data-generation starts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final


_SCHEMA_VERSION: Final = "generation_governance_v2"


class StopOutcome(str, Enum):
    """The fixed downstream stop-outcome vocabulary."""

    PASS = "PASS"
    VALID_STOP = "VALID_STOP"
    INVALID = "INVALID"
    ANCESTOR_STOP = "ANCESTOR_STOP"


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _require_receipt_id(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty canonical text")


@dataclass(frozen=True, slots=True)
class ReceiptBinding:
    """Identity that must match across contract, attempt, and output."""

    contract_id: str
    attempt_id: str
    output_root: str | os.PathLike[str]

    def __post_init__(self) -> None:
        for name, value in (("contract_id", self.contract_id), ("attempt_id", self.attempt_id)):
            _require_receipt_id(name, value)
        output_root = os.fspath(self.output_root)
        _require_receipt_id("output_root", output_root)
        output_path = Path(output_root)
        if not output_path.is_absolute():
            raise ValueError("output_root must be absolute")
        object.__setattr__(self, "output_root", str(output_path.resolve()))

    def to_dict(self) -> dict[str, str]:
        return {
            "attempt_id": self.attempt_id,
            "contract_id": self.contract_id,
            "output_root": str(self.output_root),
        }


@dataclass(frozen=True, slots=True)
class GateReceipt:
    """A gate outcome bound directly to one generation attempt."""

    binding: ReceiptBinding
    outcome: StopOutcome
    ancestor_receipt_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ReceiptBinding):
            raise TypeError("binding must be a ReceiptBinding")
        object.__setattr__(self, "outcome", StopOutcome(self.outcome))
        if self.outcome is StopOutcome.ANCESTOR_STOP:
            _require_receipt_id("ancestor_receipt_id", self.ancestor_receipt_id)
        elif self.ancestor_receipt_id is not None:
            raise ValueError("only ANCESTOR_STOP may reference an ancestor receipt")

    @property
    def receipt_id(self) -> str:
        return f"gate:{self.binding.contract_id}:{self.binding.attempt_id}:{self.outcome.value}"

    def to_dict(self) -> dict[str, object]:
        return {
            "ancestor_receipt_id": self.ancestor_receipt_id,
            "binding": self.binding.to_dict(),
            "outcome": self.outcome.value,
            "receipt_type": "gate",
            "schema_version": _SCHEMA_VERSION,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class AuthorizationReceipt:
    """Authorization bound directly to one PASS gate receipt."""

    binding: ReceiptBinding
    gate_receipt_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ReceiptBinding):
            raise TypeError("binding must be a ReceiptBinding")
        _require_receipt_id("gate_receipt_id", self.gate_receipt_id)

    @property
    def receipt_id(self) -> str:
        return f"authorization:{self.binding.contract_id}:{self.binding.attempt_id}"

    def to_dict(self) -> dict[str, object]:
        return {
            "binding": self.binding.to_dict(),
            "gate_receipt_id": self.gate_receipt_id,
            "receipt_type": "authorization",
            "schema_version": _SCHEMA_VERSION,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class RunReceipt:
    """Deterministic result of evaluating permission to start or finish a run."""

    binding: ReceiptBinding
    outcome: StopOutcome
    run_state: str
    start_permitted: bool
    scientific_completion: bool
    gate_receipt_id: str | None
    authorization_receipt_id: str | None = None
    ancestor_receipt_id: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ReceiptBinding):
            raise TypeError("binding must be a ReceiptBinding")
        object.__setattr__(self, "outcome", StopOutcome(self.outcome))
        self._validate_semantics()

    def _validate_semantics(self) -> None:
        if self.outcome is StopOutcome.PASS:
            valid_pass_state = (
                self.run_state == "authorized-to-start"
                and self.start_permitted
                and not self.scientific_completion
            ) or (
                self.run_state == "completed"
                and not self.start_permitted
                and self.scientific_completion
            )
            if not valid_pass_state:
                raise ValueError("PASS must authorize a start or record a completed run")
            _require_receipt_id("gate_receipt_id", self.gate_receipt_id)
            _require_receipt_id("authorization_receipt_id", self.authorization_receipt_id)
            if self.ancestor_receipt_id is not None:
                raise ValueError("PASS cannot reference an ancestor receipt")
            return

        expected_state = "invalid-not-run" if self.outcome is StopOutcome.INVALID else "gated-not-run"
        if self.run_state != expected_state or self.start_permitted or self.scientific_completion:
            raise ValueError(f"{self.outcome.value} has invalid run state")
        if self.outcome in {StopOutcome.VALID_STOP, StopOutcome.ANCESTOR_STOP}:
            _require_receipt_id("gate_receipt_id", self.gate_receipt_id)
        if self.outcome is StopOutcome.ANCESTOR_STOP:
            _require_receipt_id("ancestor_receipt_id", self.ancestor_receipt_id)
        elif self.ancestor_receipt_id is not None:
            raise ValueError(f"{self.outcome.value} cannot reference an ancestor receipt")

    @property
    def receipt_id(self) -> str:
        return f"run:{self.binding.contract_id}:{self.binding.attempt_id}:{self.run_state}"

    def to_dict(self) -> dict[str, object]:
        return {
            "ancestor_receipt_id": self.ancestor_receipt_id,
            "authorization_receipt_id": self.authorization_receipt_id,
            "binding": self.binding.to_dict(),
            "gate_receipt_id": self.gate_receipt_id,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "receipt_type": "run",
            "run_state": self.run_state,
            "schema_version": _SCHEMA_VERSION,
            "scientific_completion": self.scientific_completion,
            "start_permitted": self.start_permitted,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())


def evaluate_execution_permission(
    *,
    binding: ReceiptBinding,
    gate_receipt: GateReceipt | object,
    authorization_receipt: AuthorizationReceipt | object | None,
    ancestor_receipt_id: str | None = None,
) -> RunReceipt:
    """Evaluate receipt contents and bindings without cryptographic ceremony."""

    gate_id = gate_receipt.receipt_id if isinstance(gate_receipt, GateReceipt) else None
    if not isinstance(gate_receipt, GateReceipt):
        return _invalid_receipt(binding, gate_id, None, "gate-receipt-malformed")
    if gate_receipt.binding != binding:
        return _invalid_receipt(binding, gate_id, None, "gate-binding-mismatch")

    if gate_receipt.outcome is StopOutcome.ANCESTOR_STOP:
        if gate_receipt.ancestor_receipt_id != ancestor_receipt_id:
            return _invalid_receipt(binding, gate_id, None, "ancestor-receipt-mismatch")
        return RunReceipt(
            binding=binding,
            outcome=StopOutcome.ANCESTOR_STOP,
            run_state="gated-not-run",
            start_permitted=False,
            scientific_completion=False,
            gate_receipt_id=gate_id,
            ancestor_receipt_id=ancestor_receipt_id,
            reason="ancestor-stop",
        )

    if ancestor_receipt_id is not None or gate_receipt.ancestor_receipt_id is not None:
        return _invalid_receipt(binding, gate_id, None, "unexpected-ancestor-receipt")
    if gate_receipt.outcome is StopOutcome.VALID_STOP:
        return RunReceipt(
            binding=binding,
            outcome=StopOutcome.VALID_STOP,
            run_state="gated-not-run",
            start_permitted=False,
            scientific_completion=False,
            gate_receipt_id=gate_id,
            reason="valid-stop",
        )
    if gate_receipt.outcome is StopOutcome.INVALID:
        return _invalid_receipt(binding, gate_id, None, "gate-invalid")

    authorization_id = (
        authorization_receipt.receipt_id
        if isinstance(authorization_receipt, AuthorizationReceipt)
        else None
    )
    if not isinstance(authorization_receipt, AuthorizationReceipt):
        return _invalid_receipt(
            binding,
            gate_id,
            authorization_id,
            "authorization-receipt-missing-or-malformed",
        )
    if authorization_receipt.binding != binding:
        return _invalid_receipt(binding, gate_id, authorization_id, "authorization-binding-mismatch")
    if authorization_receipt.gate_receipt_id != gate_receipt.receipt_id:
        return _invalid_receipt(binding, gate_id, authorization_id, "authorization-gate-mismatch")

    return RunReceipt(
        binding=binding,
        outcome=StopOutcome.PASS,
        run_state="authorized-to-start",
        start_permitted=True,
        scientific_completion=False,
        gate_receipt_id=gate_id,
        authorization_receipt_id=authorization_id,
    )


def _invalid_receipt(
    binding: ReceiptBinding,
    gate_receipt_id: str | None,
    authorization_receipt_id: str | None,
    reason: str,
) -> RunReceipt:
    return RunReceipt(
        binding=binding,
        outcome=StopOutcome.INVALID,
        run_state="invalid-not-run",
        start_permitted=False,
        scientific_completion=False,
        gate_receipt_id=gate_receipt_id,
        authorization_receipt_id=authorization_receipt_id,
        reason=reason,
    )


__all__ = [
    "AuthorizationReceipt",
    "GateReceipt",
    "ReceiptBinding",
    "RunReceipt",
    "StopOutcome",
    "evaluate_execution_permission",
]
