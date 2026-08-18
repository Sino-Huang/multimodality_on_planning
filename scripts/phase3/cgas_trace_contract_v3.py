from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Sequence

from .cgas_trace_contract_v2 import (
    BFS_MAX_RECORDS as V2_BFS_MAX_RECORDS,
)
from .cgas_trace_contract_v2 import (
    CONTRACT_ID as V2_CONTRACT_ID,
)
from .cgas_trace_contract_v2 import (
    FIXTURE_CORPUS_ROOT,
    PRODUCTION_CORPUS_ROOT,
    PRODUCTION_STAGING_ROOT,
    TRACE_STREAMS_RELATIVE_ROOT,
    TRACE_V1_RELEASE_SHA256,
    TraceContractPacketError,
    _canonical_bytes,
    _parse_canonical_document,
    _publish_immutable,
)
from .cgas_trace_contract_v2 import (
    NEW_CONTRACT_SHA256 as V2_CONTRACT_SHA256,
)
from .local_planner_types import JSONValue

CONTRACT_ID: Final = "cgas_trace_contract_v3"
PREDECESSOR_CONTRACT_ID: Final = V2_CONTRACT_ID
PREDECESSOR_CONTRACT_SHA256: Final = V2_CONTRACT_SHA256
TRACE_V2_APPROVAL_SHA256: Final = "bd6909f99ce32484f3a33863cde936c0a3128935dabaf85da783870ae7ee26a8"
APPROVAL_SCOPE: Final = "trace_v3_persistence_and_policy"
# Legacy packet publication labels/defaults in the ignored outputs namespace.
# No archived evidence is read: the retired agent-state tree now lives only
# under the cold archive data/deprecated/2026-08-18-cgas-realignment/, which no
# active code may read.
EVIDENCE_ROOT: Final = Path("outputs/deprecated/phase3/cgas-trace-contract-v3/owner-decision-packet")
PACKET_PATH: Final = Path("outputs/deprecated/phase3/cgas-trace-contract-v3/trace-v3-migration-packet.json")
OWNER_TEMPLATE_PATH: Final = Path("outputs/deprecated/phase3/cgas-trace-contract-v3/trace-v3-owner-approval.template.json")

# Generated packets default to an ignored outputs location; pass explicit CLI
# paths to publish elsewhere.
DEFAULT_OUTPUT_ROOT: Final = Path("outputs/deprecated/phase3/cgas-trace-contract-v3")
DEFAULT_PACKET_OUTPUT: Final = DEFAULT_OUTPUT_ROOT / PACKET_PATH.name
DEFAULT_OWNER_TEMPLATE_OUTPUT: Final = DEFAULT_OUTPUT_ROOT / OWNER_TEMPLATE_PATH.name

# verify_trace_stream refuses any line above this. write_trace_stream has no counterpart
# in v2, so a writer can emit a stream its own verifier rejects; MAX_EVENT_BYTES is the
# write-side bound that closes that asymmetry.
READER_LINE_CEILING: Final = 16 * 1024 * 1024
MAX_EVENT_BYTES: Final = 65_536

POLICY_LIMITS: Final = {
    "local_iw_escalate": 1,
    "local_iw_max_width": 2,
    "local_iw_novelty_max_expansions": 50_000,
    "local_iw_recovery": "disabled",
    "local_iw_width": 1,
    "local_max_applicable_actions": 2_000,
    "max_expansions": 10_000,
    "max_grounded_actions": 100_000,
    "max_grounded_atoms": 100_000,
    "max_plan_length": 128,
}

# Escalation runs every width from local_iw_width to local_iw_max_width into one stream,
# each pass resetting its own expansion counter. The v2 formula prices a single pass.
IW_WIDTHS: Final = POLICY_LIMITS["local_iw_max_width"] - POLICY_LIMITS["local_iw_width"] + 1
BFS_MAX_RECORDS: Final = V2_BFS_MAX_RECORDS
IW_MAX_RECORDS: Final = (
    1
    + 2
    * IW_WIDTHS
    * POLICY_LIMITS["local_iw_novelty_max_expansions"]
    * POLICY_LIMITS["local_max_applicable_actions"]
    + 2
)

BFS_EVENT_FIELDS_REMOVED: Final = ("frontier_after", "frontier_before", "visited_after")
IW_EVENT_FIELDS_REMOVED: Final = ("novelty_table_after", "novelty_table_before")
IW_EVENT_FIELDS_ADDED: Final = ("seen_feature_delta",)
RETAINED_FOR_OFF_PLAN_CERTIFICATES: Final = ("actions_considered", "enqueued", "state_atoms", "successors")

# The rules the field removal rests on. R1-R3 were verified in the trace-v2 decision
# packet; R4 was added by the v3 packet and is why only frontier_order_summary needs a
# running fold in the reader.
RECONSTRUCTION_RULES: Final = {
    "R1": "frontier_before[i] == [state_id[i]]",
    "R2": "frontier_after[i] == frontier_after[i-1][1:] + enqueued(i)",
    "R3": "visited_after[i] == sorted(visited_after[i-1] | enqueued(i))",
    "R4": "visited_delta[i] == enqueued(i); at i == 0, {state_id[0]} | enqueued(0)",
}

_OLD_CONTRACT: Final = {
    "contract_id": PREDECESSOR_CONTRACT_ID,
    "contract_sha256": PREDECESSOR_CONTRACT_SHA256,
    "owner_approval_sha256": TRACE_V2_APPROVAL_SHA256,
}
# Unlike v2's, this dict covers the EVENT BODY as well as the framing. v2 described
# framing only, so dropping event fields left its digest unchanged and an event-shape
# change could pass unsigned.
_NEW_CONTRACT: Final = {
    "bfs_event_fields_removed": list(BFS_EVENT_FIELDS_REMOVED),
    "compression": "none",
    "contract_id": CONTRACT_ID,
    "encoding": "utf-8",
    "event_hash": "sha256(canonical_event_preimage)",
    "event_order": "zero_based_contiguous_sequence",
    "format": "canonical_jsonl",
    "hash_chain": "previous_event_sha256_to_current_event_sha256",
    "iw_event_fields_added": list(IW_EVENT_FIELDS_ADDED),
    "iw_event_fields_removed": list(IW_EVENT_FIELDS_REMOVED),
    "max_event_bytes": MAX_EVENT_BYTES,
    "newline": "LF",
    "predecessor_contract_id": PREDECESSOR_CONTRACT_ID,
    "retained_for_off_plan_certificates": list(RETAINED_FOR_OFF_PLAN_CERTIFICATES),
    "stream_hash": "sha256(canonical_event_lines)",
    "trailer": [
        "record_count",
        "final_event_sha256",
        "stream_sha256",
        "contract_sha256",
        "planner",
        "completion_status",
        "success_plan_sha256",
    ],
}

OLD_CONTRACT_SHA256: Final = hashlib.sha256(
    json.dumps(_OLD_CONTRACT, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
).hexdigest()
NEW_CONTRACT_SHA256: Final = hashlib.sha256(
    json.dumps(_NEW_CONTRACT, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
).hexdigest()
POLICY_SHA256: Final = hashlib.sha256(
    json.dumps(POLICY_LIMITS, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
).hexdigest()


@dataclass(frozen=True, slots=True)
class PacketPublication:
    packet_sha256: str
    owner_template_sha256: str
    status: str

    def to_record(self) -> dict[str, str | bool]:
        return {
            "contract_id": CONTRACT_ID,
            "owner_approved": False,
            "owner_template_sha256": self.owner_template_sha256,
            "packet_sha256": self.packet_sha256,
            "status": self.status,
        }


def build_migration_packet() -> dict[str, JSONValue]:
    event_preimage = {
        "event": {"decision": "expand", "state_id": "vector-state"},
        "previous_event_sha256": None,
        "record_type": "event",
        "sequence": 0,
    }
    event_sha256 = hashlib.sha256(_canonical_bytes(event_preimage)).hexdigest()
    event_record = {"current_event_sha256": event_sha256, **event_preimage}
    packet: dict[str, JSONValue] = {
        "bounds_proof": {
            "bfs": {
                "formula": "1 + max_expansions * (1 + max_grounded_actions) + 1",
                "max_records": BFS_MAX_RECORDS,
            },
            "iw": {
                "formula": "1 + 2 * widths * local_iw_novelty_max_expansions * local_max_applicable_actions + 2",
                "max_records": IW_MAX_RECORDS,
                "widths": IW_WIDTHS,
                "widths_formula": "local_iw_max_width - local_iw_width + 1",
            },
            "record_size": {
                "element_bound": (
                    "one record holds one expansion: at most max_grounded_actions successors, "
                    "each carrying at most max_grounded_atoms atoms"
                ),
                "enforced_at": "write_trace_stream, on len(canonical_event_line), before the write",
                "max_event_bytes": MAX_EVENT_BYTES,
                "reader_line_ceiling": READER_LINE_CEILING,
                "stated_not_derived": (
                    "the policy element ceilings exceed observation by ~3 orders of magnitude, so a byte bound "
                    "derived from them enforces nothing; MAX_EVENT_BYTES is stated against measurement and pinned here"
                ),
            },
        },
        "contract_id": CONTRACT_ID,
        "delta_scope": "persistence_and_policy",
        "evidence": EVIDENCE_ROOT.as_posix(),
        "new_contract": _NEW_CONTRACT,
        "new_contract_sha256": NEW_CONTRACT_SHA256,
        "old_contract": _OLD_CONTRACT,
        "old_contract_sha256": OLD_CONTRACT_SHA256,
        "owner_approved": False,
        "packet_schema_version": "cgas_trace_contract_migration_packet_v2",
        "persistence_delta": [
            "bfs_reconstructible_snapshot_fields_dropped",
            "iw_truncated_novelty_snapshots_replaced_by_emitted_delta",
            "per_record_size_bound_enforced_at_write_time",
            "iw_record_count_bound_corrected_for_width_escalation",
            "true_iterative_width_escalation_enabled_in_policy",
        ],
        "policy_limits": POLICY_LIMITS,
        "policy_sha256": POLICY_SHA256,
        "predecessor_approval_sha256": TRACE_V2_APPROVAL_SHA256,
        "predecessor_contract_id": PREDECESSOR_CONTRACT_ID,
        "publication_paths": {
            "fixture_corpus_root": FIXTURE_CORPUS_ROOT.as_posix(),
            "owner_template": OWNER_TEMPLATE_PATH.as_posix(),
            "packet": PACKET_PATH.as_posix(),
            "production_corpus_root": PRODUCTION_CORPUS_ROOT.as_posix(),
            "production_staging_root": PRODUCTION_STAGING_ROOT.as_posix(),
            "trace_streams_relative_root": TRACE_STREAMS_RELATIVE_ROOT.as_posix(),
        },
        "reconstruction_rules": RECONSTRUCTION_RULES,
        "trace_v1_release_sha256": TRACE_V1_RELEASE_SHA256,
        "verifier_vectors": {
            "event_line_hex": (_canonical_bytes(event_record) + b"\n").hex(),
            "event_sha256": event_sha256,
        },
    }
    packet["packet_sha256"] = hashlib.sha256(_canonical_bytes(packet)).hexdigest()
    return packet


def owner_approval_template(packet_sha256: str) -> dict[str, JSONValue]:
    return {
        "approval_scope": APPROVAL_SCOPE,
        "contract_id": CONTRACT_ID,
        "contract_sha256": NEW_CONTRACT_SHA256,
        "owner_approved": False,
        "packet_sha256": packet_sha256,
        "policy_sha256": POLICY_SHA256,
        "schema_version": "cgas_trace_contract_owner_approval_v1",
    }


def publish_migration_packet(output: Path, owner_template: Path) -> PacketPublication:
    packet_bytes = _canonical_bytes(build_migration_packet()) + b"\n"
    packet_sha256 = hashlib.sha256(packet_bytes).hexdigest()
    template_bytes = _canonical_bytes(owner_approval_template(packet_sha256)) + b"\n"
    _require_compatible_destination(output, packet_bytes)
    _require_compatible_destination(owner_template, template_bytes)
    output_written = _publish_immutable(output, packet_bytes)
    template_written = _publish_immutable(owner_template, template_bytes)
    status = "published" if output_written or template_written else "already_published"
    return PacketPublication(packet_sha256, hashlib.sha256(template_bytes).hexdigest(), status)


def validate_packet_bytes(contents: bytes, path: Path) -> dict[str, JSONValue]:
    packet = _parse_document(contents, path)
    payload = dict(packet)
    packet_payload_sha256 = payload.pop("packet_sha256", None)
    if packet_payload_sha256 != hashlib.sha256(_canonical_bytes(payload)).hexdigest():
        raise TraceContractPacketError("trace_v3_packet_digest_mismatch", path)
    if packet != build_migration_packet():
        raise TraceContractPacketError("trace_v3_packet_contract_mismatch", path)
    return packet


def _parse_document(contents: bytes, path: Path) -> dict[str, JSONValue]:
    try:
        return _parse_canonical_document(contents, path)
    except TraceContractPacketError as error:
        raise TraceContractPacketError("trace_v3_packet_noncanonical", error.path) from error


def _require_compatible_destination(path: Path, contents: bytes) -> None:
    # v3's own rule string. _publish_immutable re-checks with v2's on a FileExistsError
    # race, which this pre-check makes unreachable in the ordinary path.
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != contents:
            raise TraceContractPacketError("trace_v3_immutable_output_mismatch", path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish the unapproved CGAS trace-v3 migration packet.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    packet = subcommands.add_parser("packet")
    packet.add_argument("--output", type=Path, default=DEFAULT_PACKET_OUTPUT)
    packet.add_argument("--owner-template", type=Path, default=DEFAULT_OWNER_TEMPLATE_OUTPUT)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    try:
        publication = publish_migration_packet(parsed.output, parsed.owner_template)
    except (OSError, TraceContractPacketError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(publication.to_record(), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
