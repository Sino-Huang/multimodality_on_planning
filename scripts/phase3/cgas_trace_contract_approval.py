from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Final, Sequence

from . import cgas_trace_contract_v2, cgas_trace_contract_v3
from .cgas_trace_contract_v2 import (
    TraceContractPacketError,
    _canonical_bytes,
    _publish_immutable,
)
from .local_planner_types import JSONValue


@dataclass(frozen=True, slots=True)
class TraceApprovalError(RuntimeError):
    rule: str
    path: Path

    def __str__(self) -> str:
        return f"{self.rule}: {self.path}"


@dataclass(frozen=True, slots=True)
class ContractBinding:
    """One trace contract's approval surface.

    The validator dispatches on the `contract_id` the owner artifact declares, not on
    anything the caller asserts, so a signature can only ever approve the contract it
    names. Rule prefixes are per contract because error strings are checked by tests
    and quoted in the production plan.
    """

    contract_id: str
    approval_scope: str
    status: str
    rule_prefix: str
    contract_sha256: str
    policy_sha256: str
    validate_packet: Callable[[bytes, Path], dict[str, JSONValue]]


_V2_BINDING: Final = ContractBinding(
    cgas_trace_contract_v2.CONTRACT_ID,
    "trace_v2_persistence_only",
    "approved_trace_v2",
    "trace_v2",
    cgas_trace_contract_v2.NEW_CONTRACT_SHA256,
    cgas_trace_contract_v2.POLICY_SHA256,
    cgas_trace_contract_v2.validate_packet_bytes,
)
_V3_BINDING: Final = ContractBinding(
    cgas_trace_contract_v3.CONTRACT_ID,
    cgas_trace_contract_v3.APPROVAL_SCOPE,
    "approved_trace_v3",
    "trace_v3",
    cgas_trace_contract_v3.NEW_CONTRACT_SHA256,
    cgas_trace_contract_v3.POLICY_SHA256,
    cgas_trace_contract_v3.validate_packet_bytes,
)
BINDINGS: Final = {binding.contract_id: binding for binding in (_V2_BINDING, _V3_BINDING)}
# An unreadable or unrecognised artifact is reported under v2's rules, which is what
# every caller and the production plan already expect from malformed input.
DEFAULT_BINDING: Final = _V2_BINDING


@dataclass(frozen=True, slots=True)
class ApprovedTraceContract:
    packet_sha256: str
    owner_approval_sha256: str
    policy_sha256: str
    contract_sha256: str
    status: str
    contract_id: str = cgas_trace_contract_v2.CONTRACT_ID

    def to_record(self) -> dict[str, str | bool]:
        return {
            "contract_id": self.contract_id,
            "contract_sha256": self.contract_sha256,
            "owner_approval_sha256": self.owner_approval_sha256,
            "owner_approved": True,
            "packet_sha256": self.packet_sha256,
            "policy_sha256": self.policy_sha256,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class VerifiedOwnerApproval:
    contract: ApprovedTraceContract
    approved_at: str
    owner_id: str
    binding: ContractBinding = field(default=DEFAULT_BINDING)

    def approved_record(self) -> dict[str, str | bool]:
        return {
            "approved_at": self.approved_at,
            "approval_scope": self.binding.approval_scope,
            "contract_id": self.binding.contract_id,
            "contract_sha256": self.contract.contract_sha256,
            "owner_approval_sha256": self.contract.owner_approval_sha256,
            "owner_approved": True,
            "owner_id": self.owner_id,
            "packet_sha256": self.contract.packet_sha256,
            "policy_sha256": self.contract.policy_sha256,
            "schema_version": "cgas_trace_contract_approval_v1",
            "status": self.contract.status,
        }


def verify_owner_approval(packet_path: Path, approval_path: Path) -> VerifiedOwnerApproval:
    packet_bytes = packet_path.read_bytes()
    approval_bytes = approval_path.read_bytes()
    binding = binding_for(approval_bytes)
    approval = _parse_approval(approval_bytes, approval_path, binding)
    packet_sha256 = hashlib.sha256(packet_bytes).hexdigest()
    if approval.get("packet_sha256") != packet_sha256:
        raise TraceApprovalError(f"{binding.rule_prefix}_approval_packet_mismatch", approval_path)
    try:
        packet = binding.validate_packet(packet_bytes, packet_path)
    except TraceContractPacketError as error:
        raise TraceApprovalError(error.rule, error.path) from error
    expected_bindings = {
        "approval_scope": binding.approval_scope,
        "contract_id": binding.contract_id,
        "contract_sha256": packet["new_contract_sha256"],
        "owner_approved": True,
        "policy_sha256": packet["policy_sha256"],
        "schema_version": "cgas_trace_contract_owner_approval_v1",
    }
    if any(approval.get(key) != value for key, value in expected_bindings.items()):
        raise TraceApprovalError(f"{binding.rule_prefix}_approval_contract_mismatch", approval_path)
    owner_id = approval.get("owner_id")
    approved_at = approval.get("approved_at")
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise TraceApprovalError(f"{binding.rule_prefix}_approval_owner_identity_missing", approval_path)
    if not isinstance(approved_at, str) or not approved_at.strip():
        raise TraceApprovalError(f"{binding.rule_prefix}_approval_owner_identity_missing", approval_path)
    owner_approval_sha256 = hashlib.sha256(approval_bytes).hexdigest()
    contract = ApprovedTraceContract(
        packet_sha256,
        owner_approval_sha256,
        binding.policy_sha256,
        binding.contract_sha256,
        binding.status,
        binding.contract_id,
    )
    return VerifiedOwnerApproval(contract, approved_at, owner_id, binding)


def validate_owner_approval(packet_path: Path, approval_path: Path, output_path: Path) -> ApprovedTraceContract:
    verified = verify_owner_approval(packet_path, approval_path)
    _publish_immutable(output_path, _canonical_bytes(verified.approved_record()) + b"\n")
    return verified.contract


def binding_for(contents: bytes) -> ContractBinding:
    """Pick the contract from what the owner artifact declares about itself."""
    try:
        value = json.loads(contents)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return DEFAULT_BINDING
    if not isinstance(value, dict):
        return DEFAULT_BINDING
    contract_id = value.get("contract_id")
    if not isinstance(contract_id, str):
        return DEFAULT_BINDING
    return BINDINGS.get(contract_id, DEFAULT_BINDING)


def _parse_approval(contents: bytes, path: Path, binding: ContractBinding) -> dict[str, JSONValue]:
    if not contents.endswith(b"\n") or contents.endswith(b"\n\n"):
        raise TraceApprovalError(f"{binding.rule_prefix}_approval_noncanonical", path)
    try:
        value = json.loads(contents)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TraceApprovalError(f"{binding.rule_prefix}_approval_malformed", path) from error
    expected_keys = {
        "approved_at",
        "approval_scope",
        "contract_id",
        "contract_sha256",
        "owner_approved",
        "owner_id",
        "packet_sha256",
        "policy_sha256",
        "schema_version",
    }
    if not isinstance(value, dict) or set(value) != expected_keys or _canonical_bytes(value) + b"\n" != contents:
        raise TraceApprovalError(f"{binding.rule_prefix}_approval_noncanonical", path)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate an independently supplied trace-v2 owner approval.")
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--owner-approval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    try:
        approved = validate_owner_approval(parsed.packet, parsed.owner_approval, parsed.output)
    except (OSError, TraceApprovalError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(approved.to_record(), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
