from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Sequence

from .cgas_trace_v2_json import TraceJsonError, canonical_json_bytes, parse_canonical_json_line
from .local_planner_types import JSONValue

CONTRACT_ID: Final = "cgas_trace_contract_v2"
TRACE_V1_RELEASE_SHA256: Final = "3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3"
BFS_MAX_RECORDS: Final = 1_000_010_002
IW_MAX_RECORDS: Final = 40_000_003
FIXTURE_CORPUS_ROOT: Final = Path("data/planning_cgas_fixture_v1")
PRODUCTION_STAGING_ROOT: Final = Path("tmp/cgas-production-stage")
PRODUCTION_CORPUS_ROOT: Final = Path("data/planning_cgas_v1")
TRACE_STREAMS_RELATIVE_ROOT: Final = Path("traces")
POLICY_LIMITS: Final = {
    "local_iw_max_width": 1,
    "local_iw_novelty_max_expansions": 10_000,
    "local_iw_recovery": "disabled",
    "local_iw_width": 1,
    "local_max_applicable_actions": 2_000,
    "max_expansions": 10_000,
    "max_grounded_actions": 100_000,
    "max_grounded_atoms": 100_000,
    "max_plan_length": 128,
}

_OLD_CONTRACT: Final = {
    "bfs_contract_id": "cgas_p0_trace_v1",
    "iw_contract_id": "phase3_traversal_trace_v1",
    "release_manifest_sha256": TRACE_V1_RELEASE_SHA256,
}
_NEW_CONTRACT: Final = {
    "compression": "none",
    "contract_id": CONTRACT_ID,
    "encoding": "utf-8",
    "event_hash": "sha256(canonical_event_preimage)",
    "event_order": "zero_based_contiguous_sequence",
    "format": "canonical_jsonl",
    "hash_chain": "previous_event_sha256_to_current_event_sha256",
    "newline": "LF",
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
class TraceContractPacketError(RuntimeError):
    rule: str
    path: Path

    def __str__(self) -> str:
        return f"{self.rule}: {self.path}"


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
                "formula": "1 + 2 * local_iw_novelty_max_expansions * local_max_applicable_actions + 2",
                "max_records": IW_MAX_RECORDS,
            },
        },
        "contract_id": CONTRACT_ID,
        "delta_scope": "persistence_only",
        "new_contract": _NEW_CONTRACT,
        "new_contract_sha256": NEW_CONTRACT_SHA256,
        "old_contract": _OLD_CONTRACT,
        "old_contract_sha256": OLD_CONTRACT_SHA256,
        "owner_approved": False,
        "packet_schema_version": "cgas_trace_contract_migration_packet_v1",
        "persistence_delta": [
            "bounded_memory_event_streaming",
            "canonical_uncompressed_jsonl",
            "contiguous_sequence_and_sha256_chain",
            "fsynced_canonical_trailer",
            "complete_successful_streams",
        ],
        "policy_limits": POLICY_LIMITS,
        "policy_sha256": POLICY_SHA256,
        "publication_paths": {
            "fixture_corpus_root": FIXTURE_CORPUS_ROOT.as_posix(),
            "production_corpus_root": PRODUCTION_CORPUS_ROOT.as_posix(),
            "production_staging_root": PRODUCTION_STAGING_ROOT.as_posix(),
            "trace_streams_relative_root": TRACE_STREAMS_RELATIVE_ROOT.as_posix(),
        },
        "trace_v1_release_sha256": TRACE_V1_RELEASE_SHA256,
        "verifier_vectors": {
            "event_line_hex": (_canonical_bytes(event_record) + b"\n").hex(),
            "event_sha256": event_sha256,
        },
    }
    packet["packet_sha256"] = hashlib.sha256(_canonical_bytes(packet)).hexdigest()
    return packet


def publish_migration_packet(output: Path, owner_template: Path) -> PacketPublication:
    packet_bytes = _canonical_bytes(build_migration_packet()) + b"\n"
    packet_sha256 = hashlib.sha256(packet_bytes).hexdigest()
    template = {
        "approval_scope": "trace_v2_persistence_only",
        "contract_id": CONTRACT_ID,
        "contract_sha256": NEW_CONTRACT_SHA256,
        "owner_approved": False,
        "packet_sha256": packet_sha256,
        "policy_sha256": POLICY_SHA256,
        "schema_version": "cgas_trace_contract_owner_approval_v1",
    }
    template_bytes = _canonical_bytes(template) + b"\n"
    _require_compatible_destination(output, packet_bytes)
    _require_compatible_destination(owner_template, template_bytes)
    output_written = _publish_immutable(output, packet_bytes)
    template_written = _publish_immutable(owner_template, template_bytes)
    status = "published" if output_written or template_written else "already_published"
    return PacketPublication(packet_sha256, hashlib.sha256(template_bytes).hexdigest(), status)


def validate_packet_bytes(contents: bytes, path: Path) -> dict[str, JSONValue]:
    packet = _parse_canonical_document(contents, path)
    payload = dict(packet)
    packet_payload_sha256 = payload.pop("packet_sha256", None)
    if packet_payload_sha256 != hashlib.sha256(_canonical_bytes(payload)).hexdigest():
        raise TraceContractPacketError("trace_v2_packet_digest_mismatch", path)
    expected = build_migration_packet()
    if packet != expected:
        raise TraceContractPacketError("trace_v2_packet_contract_mismatch", path)
    return packet


def _canonical_bytes(value: JSONValue) -> bytes:
    try:
        return canonical_json_bytes(value, Path("<trace-v2-contract>"), "trace_v2_packet_noncanonical")
    except TraceJsonError as error:
        raise TraceContractPacketError(error.rule, error.path) from error


def _parse_canonical_document(contents: bytes, path: Path) -> dict[str, JSONValue]:
    try:
        return parse_canonical_json_line(contents, path, "trace_v2_packet_noncanonical")
    except TraceJsonError as error:
        raise TraceContractPacketError(error.rule, error.path) from error


def _require_compatible_destination(path: Path, contents: bytes) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != contents:
            raise TraceContractPacketError("trace_v2_immutable_output_mismatch", path)


def _publish_immutable(path: Path, contents: bytes) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            _require_compatible_destination(path, contents)
            return False
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as error:
        raise TraceContractPacketError("trace_v2_immutable_publication_failed", path) from error
    finally:
        temporary.unlink(missing_ok=True)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish the unapproved CGAS trace-v2 persistence migration packet.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    packet = subcommands.add_parser("packet")
    packet.add_argument("--output", type=Path, required=True)
    packet.add_argument("--owner-template", type=Path, required=True)
    packet.add_argument("--json", action="store_true")
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
