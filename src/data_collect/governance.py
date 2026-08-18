"""Minimal signed receipt contract for governed data-generation starts."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Final


_SCHEMA_VERSION: Final = "generation_governance_v1"
_HEX_DIGITS: Final = frozenset("0123456789abcdef")


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


def _key_bytes(signing_key: bytes | str) -> bytes:
    if isinstance(signing_key, str):
        signing_key = signing_key.encode("utf-8")
    if not isinstance(signing_key, bytes) or not signing_key:
        raise ValueError("signing_key must be non-empty bytes or text")
    return signing_key


def _signature(payload: object, signing_key: bytes | str) -> str:
    return hmac.new(
        _key_bytes(signing_key),
        _canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _digest(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX_DIGITS for character in value)
    )


@dataclass(frozen=True, slots=True)
class ReceiptBinding:
    """Identity that must match across contract, attempt, and output."""

    contract_id: str
    attempt_id: str
    output_root: str | os.PathLike[str]

    def __post_init__(self) -> None:
        for name, value in (
            ("contract_id", self.contract_id),
            ("attempt_id", self.attempt_id),
        ):
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"{name} must be non-empty canonical text")
        output_root = os.fspath(self.output_root)
        if not isinstance(output_root, str) or not output_root or output_root != output_root.strip():
            raise ValueError("output_root must be non-empty canonical text")
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
    """A signed gate outcome bound to one generation attempt."""

    binding: ReceiptBinding
    outcome: StopOutcome
    ancestor_receipt_digest: str | None = None
    signature: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ReceiptBinding):
            raise TypeError("binding must be a ReceiptBinding")
        object.__setattr__(self, "outcome", StopOutcome(self.outcome))
        self._validate_semantics()

    def _validate_semantics(self) -> None:
        if self.outcome is StopOutcome.ANCESTOR_STOP:
            if not _valid_digest(self.ancestor_receipt_digest):
                raise ValueError(
                    "GateReceipt semantics: ANCESTOR_STOP requires a valid ancestor receipt digest"
                )
        elif self.ancestor_receipt_digest is not None:
            raise ValueError(
                "GateReceipt semantics: only ANCESTOR_STOP may bind an ancestor receipt digest"
            )

    def _unsigned_dict(self) -> dict[str, object]:
        return {
            "ancestor_receipt_digest": self.ancestor_receipt_digest,
            "binding": self.binding.to_dict(),
            "outcome": self.outcome.value,
            "receipt_type": "gate",
            "schema_version": _SCHEMA_VERSION,
        }

    def signed(self, signing_key: bytes | str) -> GateReceipt:
        self._validate_semantics()
        return replace(self, signature=_signature(self._unsigned_dict(), signing_key))

    def verify_signature(self, signing_key: bytes | str) -> bool:
        return _valid_digest(self.signature) and hmac.compare_digest(
            self.signature,
            _signature(self._unsigned_dict(), signing_key),
        )

    def to_dict(self) -> dict[str, object]:
        return {**self._unsigned_dict(), "signature": self.signature}

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class AuthorizationReceipt:
    """A signed authorization for one exact signed PASS gate receipt."""

    binding: ReceiptBinding
    gate_receipt_digest: str
    signature: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ReceiptBinding):
            raise TypeError("binding must be a ReceiptBinding")

    def _unsigned_dict(self) -> dict[str, object]:
        return {
            "binding": self.binding.to_dict(),
            "gate_receipt_digest": self.gate_receipt_digest,
            "receipt_type": "authorization",
            "schema_version": _SCHEMA_VERSION,
        }

    def signed(self, signing_key: bytes | str) -> AuthorizationReceipt:
        return replace(self, signature=_signature(self._unsigned_dict(), signing_key))

    def verify_signature(self, signing_key: bytes | str) -> bool:
        return _valid_digest(self.signature) and hmac.compare_digest(
            self.signature,
            _signature(self._unsigned_dict(), signing_key),
        )

    def to_dict(self) -> dict[str, object]:
        return {**self._unsigned_dict(), "signature": self.signature}

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class RunReceipt:
    """Signed, deterministic result of evaluating permission to start a run."""

    binding: ReceiptBinding
    outcome: StopOutcome
    run_state: str
    start_permitted: bool
    scientific_completion: bool
    gate_receipt_digest: str | None
    authorization_receipt_digest: str | None = None
    ancestor_receipt_digest: str | None = None
    reason: str | None = None
    signature: str = ""

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
                raise ValueError(
                    "RunReceipt semantics: PASS must be authorized-to-start or a completed scientific completion"
                )
            if not _valid_digest(self.gate_receipt_digest) or not _valid_digest(
                self.authorization_receipt_digest
            ):
                raise ValueError(
                    "RunReceipt semantics: PASS requires valid gate and authorization receipt digests"
                )
            if self.ancestor_receipt_digest is not None:
                raise ValueError(
                    "RunReceipt semantics: PASS cannot bind an ancestor receipt digest"
                )
            return

        if self.outcome is StopOutcome.VALID_STOP:
            if (
                self.run_state != "gated-not-run"
                or self.start_permitted
                or self.scientific_completion
            ):
                raise ValueError(
                    "RunReceipt semantics: VALID_STOP must be gated-not-run and never scientific completion"
                )
            if not _valid_digest(self.gate_receipt_digest):
                raise ValueError("RunReceipt semantics: VALID_STOP requires a valid gate receipt digest")
            if self.ancestor_receipt_digest is not None:
                raise ValueError(
                    "RunReceipt semantics: VALID_STOP cannot bind an ancestor receipt digest"
                )
            return

        if self.outcome is StopOutcome.ANCESTOR_STOP:
            if (
                self.run_state != "gated-not-run"
                or self.start_permitted
                or self.scientific_completion
            ):
                raise ValueError(
                    "RunReceipt semantics: ANCESTOR_STOP must be gated-not-run and never scientific completion"
                )
            if not _valid_digest(self.gate_receipt_digest) or not _valid_digest(
                self.ancestor_receipt_digest
            ):
                raise ValueError(
                    "RunReceipt semantics: ANCESTOR_STOP requires valid gate and ancestor receipt digests"
                )
            return

        if (
            self.run_state != "invalid-not-run"
            or self.start_permitted
            or self.scientific_completion
        ):
            raise ValueError(
                "RunReceipt semantics: INVALID must never start or claim scientific completion"
            )
        if self.ancestor_receipt_digest is not None:
            raise ValueError("RunReceipt semantics: INVALID cannot bind an ancestor receipt digest")

    def _unsigned_dict(self) -> dict[str, object]:
        return {
            "ancestor_receipt_digest": self.ancestor_receipt_digest,
            "authorization_receipt_digest": self.authorization_receipt_digest,
            "binding": self.binding.to_dict(),
            "gate_receipt_digest": self.gate_receipt_digest,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "receipt_type": "run",
            "run_state": self.run_state,
            "schema_version": _SCHEMA_VERSION,
            "scientific_completion": self.scientific_completion,
            "start_permitted": self.start_permitted,
        }

    def signed(self, signing_key: bytes | str) -> RunReceipt:
        self._validate_semantics()
        return replace(self, signature=_signature(self._unsigned_dict(), signing_key))

    def verify_signature(self, signing_key: bytes | str) -> bool:
        return _valid_digest(self.signature) and hmac.compare_digest(
            self.signature,
            _signature(self._unsigned_dict(), signing_key),
        )

    def to_dict(self) -> dict[str, object]:
        return {**self._unsigned_dict(), "signature": self.signature}

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def evaluate_execution_permission(
    *,
    binding: ReceiptBinding,
    gate_receipt: GateReceipt | object,
    authorization_receipt: AuthorizationReceipt | object | None,
    signing_key: bytes | str,
    ancestor_receipt_digest: str | None = None,
) -> RunReceipt:
    """Purely evaluate signed receipts and return a signed run receipt.

    The function performs no execution or persistence. Only a signed ``PASS``
    gate plus a signed authorization bound to that exact gate and the requested
    contract/attempt/output identity permits a start.
    """

    _key_bytes(signing_key)
    gate_digest = _safe_digest(gate_receipt)

    if not isinstance(gate_receipt, GateReceipt):
        return _invalid_receipt(binding, signing_key, gate_digest, None, "gate-receipt-malformed")
    if gate_receipt.binding != binding:
        return _invalid_receipt(binding, signing_key, gate_digest, None, "gate-binding-mismatch")
    if not gate_receipt.verify_signature(signing_key):
        return _invalid_receipt(binding, signing_key, gate_digest, None, "gate-signature-invalid")

    if gate_receipt.outcome is StopOutcome.ANCESTOR_STOP:
        if (
            not _valid_digest(gate_receipt.ancestor_receipt_digest)
            or gate_receipt.ancestor_receipt_digest != ancestor_receipt_digest
        ):
            return _invalid_receipt(
                binding,
                signing_key,
                gate_digest,
                None,
                "ancestor-receipt-digest-mismatch",
            )
        return RunReceipt(
            binding=binding,
            outcome=StopOutcome.ANCESTOR_STOP,
            run_state="gated-not-run",
            start_permitted=False,
            scientific_completion=False,
            gate_receipt_digest=gate_digest,
            ancestor_receipt_digest=ancestor_receipt_digest,
            reason="ancestor-stop",
        ).signed(signing_key)

    if ancestor_receipt_digest is not None or gate_receipt.ancestor_receipt_digest is not None:
        return _invalid_receipt(
            binding,
            signing_key,
            gate_digest,
            None,
            "unexpected-ancestor-receipt-digest",
        )

    if gate_receipt.outcome is StopOutcome.VALID_STOP:
        return RunReceipt(
            binding=binding,
            outcome=StopOutcome.VALID_STOP,
            run_state="gated-not-run",
            start_permitted=False,
            scientific_completion=False,
            gate_receipt_digest=gate_digest,
            reason="valid-stop",
        ).signed(signing_key)

    if gate_receipt.outcome is StopOutcome.INVALID:
        return _invalid_receipt(binding, signing_key, gate_digest, None, "gate-invalid")

    authorization_digest = _safe_digest(authorization_receipt)
    if not isinstance(authorization_receipt, AuthorizationReceipt):
        return _invalid_receipt(
            binding,
            signing_key,
            gate_digest,
            authorization_digest,
            "authorization-receipt-missing-or-malformed",
        )
    if authorization_receipt.binding != binding:
        return _invalid_receipt(
            binding,
            signing_key,
            gate_digest,
            authorization_digest,
            "authorization-binding-mismatch",
        )
    if not authorization_receipt.verify_signature(signing_key):
        return _invalid_receipt(
            binding,
            signing_key,
            gate_digest,
            authorization_digest,
            "authorization-signature-invalid",
        )
    if authorization_receipt.gate_receipt_digest != gate_receipt.digest:
        return _invalid_receipt(
            binding,
            signing_key,
            gate_digest,
            authorization_digest,
            "authorization-gate-mismatch",
        )

    return RunReceipt(
        binding=binding,
        outcome=StopOutcome.PASS,
        run_state="authorized-to-start",
        start_permitted=True,
        scientific_completion=False,
        gate_receipt_digest=gate_digest,
        authorization_receipt_digest=authorization_digest,
    ).signed(signing_key)


def _safe_digest(receipt: object) -> str | None:
    if isinstance(receipt, (GateReceipt, AuthorizationReceipt)):
        return receipt.digest
    return None


def _invalid_receipt(
    binding: ReceiptBinding,
    signing_key: bytes | str,
    gate_receipt_digest: str | None,
    authorization_receipt_digest: str | None,
    reason: str,
) -> RunReceipt:
    return RunReceipt(
        binding=binding,
        outcome=StopOutcome.INVALID,
        run_state="invalid-not-run",
        start_permitted=False,
        scientific_completion=False,
        gate_receipt_digest=gate_receipt_digest,
        authorization_receipt_digest=authorization_receipt_digest,
        reason=reason,
    ).signed(signing_key)


__all__ = [
    "AuthorizationReceipt",
    "GateReceipt",
    "ReceiptBinding",
    "RunReceipt",
    "StopOutcome",
    "evaluate_execution_permission",
]
