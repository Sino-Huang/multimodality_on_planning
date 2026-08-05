from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .cgas_trace_contract_v2 import (
    CONTRACT_ID,
    NEW_CONTRACT_SHA256,
    POLICY_SHA256,
    TraceContractPacketError,
    _canonical_bytes,
    _publish_immutable,
    validate_packet_bytes,
)
from .local_planner_types import JSONValue


@dataclass(frozen=True, slots=True)
class TraceApprovalError(RuntimeError):
    rule: str
    path: Path

    def __str__(self) -> str:
        return f"{self.rule}: {self.path}"


@dataclass(frozen=True, slots=True)
class ApprovedTraceContract:
    packet_sha256: str
    owner_approval_sha256: str
    policy_sha256: str
    contract_sha256: str
    status: str

    def to_record(self) -> dict[str, str | bool]:
        return {
            "contract_id": CONTRACT_ID,
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

    def approved_record(self) -> dict[str, str | bool]:
        return {
            "approved_at": self.approved_at,
            "approval_scope": "trace_v2_persistence_only",
            "contract_id": CONTRACT_ID,
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
    approval = _parse_approval(approval_bytes, approval_path)
    packet_sha256 = hashlib.sha256(packet_bytes).hexdigest()
    if approval.get("packet_sha256") != packet_sha256:
        raise TraceApprovalError("trace_v2_approval_packet_mismatch", approval_path)
    try:
        packet = validate_packet_bytes(packet_bytes, packet_path)
    except TraceContractPacketError as error:
        raise TraceApprovalError(error.rule, error.path) from error
    expected_bindings = {
        "approval_scope": "trace_v2_persistence_only",
        "contract_id": CONTRACT_ID,
        "contract_sha256": packet["new_contract_sha256"],
        "owner_approved": True,
        "policy_sha256": packet["policy_sha256"],
        "schema_version": "cgas_trace_contract_owner_approval_v1",
    }
    if any(approval.get(key) != value for key, value in expected_bindings.items()):
        raise TraceApprovalError("trace_v2_approval_contract_mismatch", approval_path)
    owner_id = approval.get("owner_id")
    approved_at = approval.get("approved_at")
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise TraceApprovalError("trace_v2_approval_owner_identity_missing", approval_path)
    if not isinstance(approved_at, str) or not approved_at.strip():
        raise TraceApprovalError("trace_v2_approval_owner_identity_missing", approval_path)
    owner_approval_sha256 = hashlib.sha256(approval_bytes).hexdigest()
    contract = ApprovedTraceContract(
        packet_sha256, owner_approval_sha256, POLICY_SHA256, NEW_CONTRACT_SHA256, "approved_trace_v2"
    )
    return VerifiedOwnerApproval(contract, approved_at, owner_id)


def validate_owner_approval(packet_path: Path, approval_path: Path, output_path: Path) -> ApprovedTraceContract:
    verified = verify_owner_approval(packet_path, approval_path)
    _publish_immutable(output_path, _canonical_bytes(verified.approved_record()) + b"\n")
    return verified.contract


def _parse_approval(contents: bytes, path: Path) -> dict[str, JSONValue]:
    if not contents.endswith(b"\n") or contents.endswith(b"\n\n"):
        raise TraceApprovalError("trace_v2_approval_noncanonical", path)
    try:
        value = json.loads(contents)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TraceApprovalError("trace_v2_approval_malformed", path) from error
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
        raise TraceApprovalError("trace_v2_approval_noncanonical", path)
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
