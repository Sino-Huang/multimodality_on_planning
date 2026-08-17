from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Final, Sequence

from .cgas_partition_selection import SelectionFeasibilityError
from .cgas_serialization import write_json

OWNER_APPROVAL_SCHEMA_VERSION: Final = "cgas_partition_owner_approval_v1"


def approve_draft(draft_path: Path, approval_path: Path, output_path: Path) -> dict[str, object]:
    draft_bytes = draft_path.read_bytes()
    approval_bytes = approval_path.read_bytes()
    draft = _mapping(json.loads(draft_bytes), "partition_draft")
    approval = _mapping(json.loads(approval_bytes), "owner_approval")
    draft_digest = hashlib.sha256(draft_bytes).hexdigest()
    approval_digest = hashlib.sha256(approval_bytes).hexdigest()
    _digest(draft_digest, "draft_sha256")
    _digest(approval_digest, "owner_approval_digest")
    if draft.get("status") != "draft_for_owner_review":
        raise SelectionFeasibilityError("invalid_partition_draft_status")
    if draft.get("owner_approved") is not False:
        raise SelectionFeasibilityError("partition_draft_already_approved")
    records = _records(draft.get("records"))
    if not records:
        raise SelectionFeasibilityError("partition_records_empty")
    if draft.get("failure") is not None:
        raise SelectionFeasibilityError("partition_draft_failed")
    if approval.get("schema_version") != OWNER_APPROVAL_SCHEMA_VERSION:
        raise SelectionFeasibilityError("invalid_owner_approval_schema")
    if approval.get("owner_approved") is not True:
        raise SelectionFeasibilityError("owner_approval_required")
    if approval.get("draft_sha256") != draft_digest:
        raise SelectionFeasibilityError("owner_approval_draft_mismatch")
    if approval.get("policy_sha256") != draft.get("policy_sha256"):
        raise SelectionFeasibilityError("owner_approval_policy_mismatch")
    if _integer(approval.get("record_count"), "owner_approval_record_count") != len(records):
        raise SelectionFeasibilityError("owner_approval_record_count_mismatch")
    approved = dict(draft)
    approved["owner_approved"] = True
    approved["owner_approval_digest"] = approval_digest
    approved["owner_approval_schema_version"] = OWNER_APPROVAL_SCHEMA_VERSION
    approved["status"] = "approved_p0_partition"
    write_json(output_path, approved)
    return approved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Approve a non-empty CGAS P0 partition draft.")
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--owner-approval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        approved = approve_draft(args.draft, args.owner_approval, args.output)
    except (OSError, json.JSONDecodeError, SelectionFeasibilityError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps({"records": len(_records(approved["records"])), "status": approved["status"]}, sort_keys=True, separators=(",", ":")))
    return 0


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SelectionFeasibilityError(f"invalid_{label}")
    return value


def _records(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise SelectionFeasibilityError("invalid_records")
    return tuple(value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SelectionFeasibilityError(f"invalid_{label}")
    return value


def _digest(value: str, label: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise SelectionFeasibilityError(f"invalid_{label}")


if __name__ == "__main__":
    raise SystemExit(main())
