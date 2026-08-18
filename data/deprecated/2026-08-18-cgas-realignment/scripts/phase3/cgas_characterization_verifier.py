from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Sequence

from .cgas_characterization_checkpoint import CheckpointEntry, VerifiedCheckpoint, checkpoint_entries, load_checkpoint
from .cgas_characterization_checkpoint_contracts import CheckpointError, CheckpointExpectation
from .cgas_characterization_contract import MAX_RUN_CONTRACT_BYTES, CharacterizationRunContractError, build_characterization_run_contract
from .cgas_characterization_bundle import BundleError, parse_bundle
from .cgas_characterization_final_members import verify_final_members
from .cgas_characterization_types import (
    CanonicalRowIndex,
    CharacterizationArtifactDigest,
    SourceManifestDigest,
)
from .cgas_characterization_final_validation import expected_characterization_rows
from .cgas_partition_contracts import CHARACTERIZATION_FILE, MANIFEST_FILE
from .cgas_serialization import CanonicalSerializationError, canonical, canonical_json_object
from .cgas_characterization_work import WorkRootError, read_initialized_contract

_READ_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
_DIRECTORY_FLAGS: Final = _READ_FLAGS | os.O_DIRECTORY
_CHECKPOINT_NAMES: Final = re.compile(r"0[0-4][0-9][0-9]\.json|0480\.json")
_CHECKPOINT_PROFILE: Final = frozenset({"run-contract.json", "checkpoints"})
_FINAL_PROFILE: Final = frozenset({"run-contract.json", CHARACTERIZATION_FILE, MANIFEST_FILE})
_MAX_CHECKPOINT_BYTES: Final = 64 * 1024
_MAX_MANIFEST_BYTES: Final = 256 * 1024
_MAX_JSONL_BYTES: Final = 128 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class VerificationRequest:
    repository_root: Path
    source_manifest: Path
    checkpoint_root: Path
    final_root: Path | None
    module_roots: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CharacterizationVerificationReport:
    valid: bool
    complete: bool
    publishable: bool
    errors: tuple[str, ...]
    checkpoint_count: int
    checkpoint_entries: tuple[CheckpointEntry, ...] | None = None
    verified_checkpoints: tuple[VerifiedCheckpoint, ...] | None = None
    contract_bytes: bytes | None = None
    contract_fingerprint: str | None = None


def verify_characterization(request: VerificationRequest) -> CharacterizationVerificationReport:
    """Verify persisted characterization roots without creating or changing filesystem entries."""
    try:
        contract_bytes, checkpoint_names = _checkpoint_root(request.checkpoint_root)
        contract = _current_contract(request, contract_bytes)
        verified = _verify_pinned_checkpoints(request.checkpoint_root / "checkpoints", checkpoint_names, contract.fingerprint, contract.payload)
        entries = tuple(checkpoint.entry for checkpoint in verified)
        if request.final_root is None:
            ready = len(checkpoint_names) == _record_count(contract.payload)
            return CharacterizationVerificationReport(True, ready, False, (), len(checkpoint_names), entries, verified, contract_bytes, contract.fingerprint)
        expected_rows = expected_characterization_rows(contract.payload, request.repository_root)
        _verify_final(request.final_root, contract_bytes, contract.fingerprint, contract.payload, request.repository_root, expected_rows)
    except (BundleError, CharacterizationRunContractError, CheckpointError, WorkRootError, OSError, ValueError, json.JSONDecodeError, CanonicalSerializationError) as error:
        return CharacterizationVerificationReport(False, False, False, (str(error),), 0)
    return CharacterizationVerificationReport(True, True, True, (), len(checkpoint_names), entries, verified, contract_bytes, contract.fingerprint)


def verify_bundle_contents(request: VerificationRequest, contents: bytes) -> CharacterizationVerificationReport:
    """Verify already-read anonymous bundle bytes without filesystem extraction or writes."""
    try:
        contract_bytes, checkpoint_names = _checkpoint_root(request.checkpoint_root)
        contract = _current_contract(request, contract_bytes)
        verified = _verify_pinned_checkpoints(request.checkpoint_root / "checkpoints", checkpoint_names, contract.fingerprint, contract.payload)
        entries = tuple(checkpoint.entry for checkpoint in verified)
        bundle = parse_bundle(contents)
        if bundle.run_fingerprint != contract.fingerprint:
            raise ValueError("bundle_run_fingerprint_mismatch")
        expected_rows = expected_characterization_rows(contract.payload, request.repository_root)
        verify_final_members({member.name: member.contents for member in bundle.members}, contract_bytes, contract.payload, request.repository_root, expected_rows)
    except (BundleError, CharacterizationRunContractError, CheckpointError, WorkRootError, OSError, ValueError, json.JSONDecodeError, CanonicalSerializationError) as error:
        return CharacterizationVerificationReport(False, False, False, (str(error),), 0)
    return CharacterizationVerificationReport(True, True, True, (), len(checkpoint_names), entries, verified, contract_bytes, contract.fingerprint)


def _checkpoint_root(root: Path) -> tuple[bytes, tuple[str, ...]]:
    contract = read_initialized_contract(root)
    checkpoint_root = root / "checkpoints"
    checkpoint_names = _directory_names(checkpoint_root, None)
    for name in checkpoint_names:
        if _CHECKPOINT_NAMES.fullmatch(name) is None:
            raise ValueError("noncanonical_checkpoint_name")
        _read_regular(checkpoint_root, name)
    return contract, checkpoint_names


def _current_contract(request: VerificationRequest, stored: bytes):
    raw = _canonical_object(stored, "run_contract")
    shard_count = raw.get("shard_count")
    if isinstance(shard_count, bool) or not isinstance(shard_count, int):
        raise ValueError("invalid_contract_shard_count")
    current = build_characterization_run_contract(
        request.source_manifest, request.repository_root, shard_count=shard_count, module_roots=request.module_roots or None
    )
    if stored != current.canonical_bytes:
        raise ValueError("stale_run_contract")
    return current


def _verify_checkpoints(root: Path, names: tuple[str, ...], fingerprint: str, payload: dict[str, object]) -> tuple[tuple[str, bytes, dict[str, object], CheckpointExpectation], ...]:
    source = _mapping(payload["source"], "contract_source")
    records = _mapping(source["records"], "contract_records")
    expected_ids = tuple(sorted(records))
    seen_ids: set[str] = set()
    verified: list[tuple[str, bytes, dict[str, object], CheckpointExpectation]] = []
    for name in names:
        index = int(name[:4])
        if index >= len(expected_ids):
            raise ValueError("checkpoint_index_outside_population")
        contents = _read_regular(root, name)
        envelope = _canonical_object(contents, "checkpoint")
        instance_id = _text(envelope.get("instance_id"), "checkpoint_instance")
        if instance_id != expected_ids[index] or instance_id in seen_ids:
            raise ValueError("checkpoint_instance_binding")
        seen_ids.add(instance_id)
        digest = CharacterizationArtifactDigest(_sha(envelope.get("row_digest"), "checkpoint_row_digest"))
        expected = CheckpointExpectation(SourceManifestDigest(fingerprint), CanonicalRowIndex(index), instance_id, digest)
        checkpoint = load_checkpoint(root, expected)
        if checkpoint is None:
            raise ValueError("checkpoint_disappeared")
        if checkpoint.row is None:
            raise ValueError("checkpoint_row_missing")
        row = checkpoint.row
        verified.append((name, contents, row, checkpoint.expectation))
    return tuple(verified)


def _verify_pinned_checkpoints(root: Path, names: tuple[str, ...], fingerprint: str, payload: dict[str, object]) -> tuple[VerifiedCheckpoint, ...]:
    allowed_names = frozenset(names)
    before = checkpoint_entries(root, allowed_names)
    verified_rows = _verify_checkpoints(root, names, fingerprint, payload)
    contents = {name: (bytes_, row, expectation) for name, bytes_, row, expectation in verified_rows}
    after = checkpoint_entries(root, allowed_names)
    if after != before:
        raise ValueError("checkpoint_state_changed_during_verification")
    return tuple(VerifiedCheckpoint(entry, contents[entry.name][0], contents[entry.name][1], contents[entry.name][2]) for entry in after)


def _record_count(payload: dict[str, object]) -> int:
    return len(_mapping(_mapping(payload["source"], "contract_source")["records"], "contract_records"))


def _verify_final(root: Path, contract_bytes: bytes, fingerprint: str, payload: dict[str, object], repository: Path, expected_rows: tuple[dict[str, object], ...]) -> None:
    status = os.stat(root, follow_symlinks=False)
    if stat.S_ISREG(status.st_mode):
        _verify_final_bundle(root, contract_bytes, fingerprint, payload, repository, expected_rows)
        return
    _directory_names(root, _FINAL_PROFILE)
    verify_final_members({name: _read_regular(root, name) for name in _FINAL_PROFILE}, contract_bytes, payload, repository, expected_rows)


def _verify_final_bundle(root: Path, contract_bytes: bytes, fingerprint: str, payload: dict[str, object], repository: Path, expected_rows: tuple[dict[str, object], ...]) -> None:
    descriptor = os.open(root, _READ_FLAGS)
    try:
        before = _bundle_status(descriptor)
        contents = os.pread(descriptor, before.st_size + 1, 0)
        after = _bundle_status(descriptor)
        if len(contents) != before.st_size or (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise ValueError("bundle_changed_during_read")
    finally:
        os.close(descriptor)
    bundle = parse_bundle(contents)
    if bundle.run_fingerprint != fingerprint:
        raise ValueError("bundle_run_fingerprint_mismatch")
    verify_final_members({member.name: member.contents for member in bundle.members}, contract_bytes, payload, repository, expected_rows)


def _bundle_status(descriptor: int) -> os.stat_result:
    status = os.fstat(descriptor)
    if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600 or status.st_uid != os.geteuid() or status.st_nlink != 1:
        raise ValueError("final_bundle_not_owner_regular_mode0600_single_link")
    if status.st_size > 3 * 128 * 1024 * 1024 + 16 * 1024 + 25:
        raise ValueError("final_bundle_too_large")
    return status


def _directory_names(root: Path, expected: frozenset[str] | None) -> tuple[str, ...]:
    descriptor = os.open(root, _DIRECTORY_FLAGS)
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISDIR(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o700 or status.st_uid != os.geteuid():
            raise ValueError("root_not_directory")
        names = tuple(sorted(os.listdir(descriptor)))
        if expected is not None and frozenset(names) != expected:
            raise ValueError("unexpected_root_profile")
        for name in names:
            status = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISLNK(status.st_mode) or not (stat.S_ISREG(status.st_mode) or stat.S_ISDIR(status.st_mode)):
                raise ValueError("special_or_symlink_entry")
        return names
    finally:
        os.close(descriptor)


def _read_regular(root: Path, name: str) -> bytes:
    directory = os.open(root, _DIRECTORY_FLAGS)
    try:
        descriptor = os.open(name, _READ_FLAGS, dir_fd=directory)
        try:
            status = os.fstat(descriptor)
            if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600 or status.st_uid != os.geteuid() or status.st_nlink != 1:
                raise ValueError("leaf_not_regular")
            if status.st_size > _leaf_cap(name):
                raise ValueError("leaf_exceeds_byte_limit")
            contents = os.pread(descriptor, status.st_size + 1, 0)
            if len(contents) != status.st_size:
                raise ValueError("leaf_changed_during_read")
            return contents
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)


def _leaf_cap(name: str) -> int:
    if name == "run-contract.json":
        return MAX_RUN_CONTRACT_BYTES
    if name == MANIFEST_FILE:
        return _MAX_MANIFEST_BYTES
    if name == CHARACTERIZATION_FILE:
        return _MAX_JSONL_BYTES
    return _MAX_CHECKPOINT_BYTES


def _canonical_object(contents: bytes, label: str) -> dict[str, object]:
    raw = json.loads(contents)
    if not isinstance(raw, dict) or canonical_json_object(raw) != contents:
        raise ValueError(f"noncanonical_{label}")
    return raw


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"invalid_{label}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid_{label}")
    return value


def _sha(value: object, label: str) -> str:
    value = _text(value, label)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"invalid_{label}")
    return value


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--checkpoint-root", required=True, type=Path)
    parser.add_argument("--final-root", type=Path)
    parser.add_argument("--module-root", action="append", default=[])
    args = parser.parse_args(arguments)
    report = verify_characterization(VerificationRequest(args.repository_root, args.source_manifest, args.checkpoint_root, args.final_root, tuple(args.module_root)))
    print(canonical_json_object({"checkpoint_count": report.checkpoint_count, "complete": report.complete, "errors": {str(index): error for index, error in enumerate(report.errors)}, "publishable": report.publishable, "valid": report.valid}).decode())
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
