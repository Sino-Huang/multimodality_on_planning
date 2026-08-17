from __future__ import annotations

import json
import os
import stat
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .cgas_characterization_checkpoint_contracts import (
    Checkpoint,
    CheckpointError,
    CheckpointExpectation,
    checkpoint_name,
    envelope as _envelope,
    normalize_expectation as _normalize_expectation,
)
from .cgas_characterization_checkpoint_publication import publish_checkpoint as _publish_checkpoint
from .cgas_characterization_types import (
    CharacterizationTypeError,
    parse_canonical_row_index,
    parse_characterization_artifact_digest,
    parse_source_manifest_digest,
)
from .cgas_serialization import CanonicalSerializationError, canonical_json_object
from .cgas_serialization import canonical
from .output_layout_inventory_types import OutputLayoutInventoryError
from .output_layout_receipt_io import open_parent_directory


_MAX_CHECKPOINT_BYTES: Final = 64 * 1024
_READ_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


@dataclass(frozen=True, slots=True)
class CheckpointEntry:
    name: str
    device: int
    inode: int
    size: int


@dataclass(frozen=True, slots=True)
class VerifiedCheckpoint:
    entry: CheckpointEntry
    canonical_bytes: bytes
    row: dict[str, object] | None
    expectation: CheckpointExpectation


def build_checkpoint(expectation: CheckpointExpectation, row: dict[str, object] | None = None) -> Checkpoint:
    """Create the only canonical byte representation for one row checkpoint."""
    normalized = _normalize_expectation(expectation)
    if row is not None and normalized.row_digest != parse_characterization_artifact_digest(hashlib.sha256(canonical(row).encode()).hexdigest()):
        raise CheckpointError("checkpoint row digest differs", Path(normalized.instance_id))
    return Checkpoint(normalized, canonical_json_object(_envelope(normalized, row)), row)


def load_checkpoint(root: Path, expected: CheckpointExpectation) -> Checkpoint | None:
    """Load one exact canonical checkpoint, returning None only when its leaf is absent."""
    normalized = _normalize_expectation(expected)
    root_descriptor = _open_directory(root, "checkpoint root must be a real directory")
    try:
        name = checkpoint_name(normalized.row_index)
        try:
            descriptor = os.open(name, _READ_FLAGS, dir_fd=root_descriptor)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise CheckpointError("checkpoint must be a regular file", root / name) from error
        try:
            status = _checkpoint_status(descriptor, root / name)
            if status.st_size > _MAX_CHECKPOINT_BYTES:
                raise CheckpointError("checkpoint exceeds byte limit", root / name)
            contents = _read_bytes(descriptor, status.st_size, root / name)
            after_read = _checkpoint_status(descriptor, root / name)
            if (after_read.st_dev, after_read.st_ino, after_read.st_size) != (status.st_dev, status.st_ino, status.st_size):
                raise CheckpointError("checkpoint metadata changed while read", root / name)
        finally:
            _close(descriptor, "unable to close checkpoint", root / name)
    finally:
        _close(root_descriptor, "unable to close checkpoint root", root)
    return _parse_checkpoint(contents, normalized, root / name)


def publish_checkpoint(root: Path, private_root: Path, checkpoint: Checkpoint) -> None:
    """Publish a private, durable checkpoint without replacing an existing leaf."""
    expected = _normalize_expectation(checkpoint.expectation)
    canonical = build_checkpoint(expected, checkpoint.row).canonical_bytes
    if checkpoint.canonical_bytes != canonical:
        raise CheckpointError("checkpoint bytes are not canonical", root / checkpoint_name(expected.row_index))
    _publish_checkpoint(root, private_root, checkpoint)


def checkpoint_entries(root: Path, allowed_names: frozenset[str]) -> tuple[CheckpointEntry, ...]:
    root_descriptor = _open_directory(root, "checkpoint root must be a real directory")
    try:
        _checkpoint_root_status(root_descriptor, root)
        entries: list[CheckpointEntry] = []
        for name in sorted(os.listdir(root_descriptor)):
            path = root / name
            if name not in allowed_names:
                raise CheckpointError("checkpoint name is not canonical", path)
            try:
                status = os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
            except OSError as error:
                raise CheckpointError("unable to inspect checkpoint", path) from error
            if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600 or status.st_uid != os.geteuid() or status.st_nlink != 1:
                raise CheckpointError("checkpoint must be owner regular mode 0600 single-link", path)
            if status.st_size > _MAX_CHECKPOINT_BYTES:
                raise CheckpointError("checkpoint exceeds byte limit", path)
            entries.append(CheckpointEntry(name, status.st_dev, status.st_ino, status.st_size))
        return tuple(entries)
    finally:
        _close(root_descriptor, "unable to close checkpoint root", root)


def _parse_checkpoint(contents: bytes, expected: CheckpointExpectation, path: Path) -> Checkpoint:
    try:
        raw: object = json.loads(contents)
        canonical = canonical_json_object(raw)
    except (json.JSONDecodeError, CanonicalSerializationError) as error:
        raise CheckpointError("checkpoint bytes are not canonical JSON", path) from error
    if canonical != contents:
        raise CheckpointError("checkpoint bytes are not canonical", path)
    match raw:
        case dict() as envelope if set(envelope) in ({"run_fingerprint", "row_index", "instance_id", "row_digest"}, {"run_fingerprint", "row_index", "instance_id", "row_digest", "row"}):
            return _parse_envelope(
                envelope["run_fingerprint"],
                envelope["row_index"],
                envelope["instance_id"],
                envelope["row_digest"],
                expected,
                contents,
                path, envelope.get("row"),
            )
        case _:
            raise CheckpointError("checkpoint envelope has invalid fields", path)


def _parse_envelope(
    run: object, index: object, instance: object, digest: object, expected: CheckpointExpectation, contents: bytes, path: Path, row: object | None
) -> Checkpoint:
    try:
        parsed = CheckpointExpectation(
            parse_source_manifest_digest(run),
            parse_canonical_row_index(index),
            _parse_instance_id(instance, path),
            parse_characterization_artifact_digest(digest),
        )
    except CheckpointError:
        raise
    except CharacterizationTypeError as error:
        raise CheckpointError("checkpoint envelope has invalid fields", path) from error
    if parsed.run_fingerprint != expected.run_fingerprint:
        raise CheckpointError("checkpoint run fingerprint differs", path)
    if parsed.row_index != expected.row_index:
        raise CheckpointError("checkpoint row index differs", path)
    if parsed.instance_id != expected.instance_id:
        raise CheckpointError("checkpoint instance differs", path)
    if parsed.row_digest != expected.row_digest:
        raise CheckpointError("checkpoint row digest differs", path)
    parsed_row: dict[str, object] | None = None
    if row is not None:
        if not isinstance(row, str):
            raise CheckpointError("checkpoint row is invalid", path)
        try:
            loaded_row = json.loads(row)
        except json.JSONDecodeError as error:
            raise CheckpointError("checkpoint row is invalid", path) from error
        if not isinstance(loaded_row, dict) or canonical(loaded_row) != row:
            raise CheckpointError("checkpoint row is invalid", path)
        parsed_row = loaded_row
        if parsed.row_digest != parse_characterization_artifact_digest(hashlib.sha256(canonical(parsed_row).encode()).hexdigest()):
            raise CheckpointError("checkpoint row digest differs", path)
    return Checkpoint(parsed, contents, parsed_row)


def _parse_instance_id(raw: object, path: Path) -> str:
    if isinstance(raw, str) and raw:
        return raw
    raise CheckpointError("checkpoint instance is invalid", path)


def _open_directory(path: Path, rule: str) -> int:
    try:
        return open_parent_directory(path)
    except OutputLayoutInventoryError as error:
        raise CheckpointError(rule, path) from error


def _checkpoint_status(descriptor: int, path: Path) -> os.stat_result:
    try:
        status = os.fstat(descriptor)
    except OSError as error:
        raise CheckpointError("unable to inspect checkpoint", path) from error
    if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600 or status.st_uid != os.geteuid() or status.st_nlink != 1:
        raise CheckpointError("checkpoint must be owner regular mode 0600 single-link", path)
    return status


def _checkpoint_root_status(descriptor: int, path: Path) -> None:
    try:
        status = os.fstat(descriptor)
    except OSError as error:
        raise CheckpointError("unable to inspect checkpoint root", path) from error
    if not stat.S_ISDIR(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o700 or status.st_uid != os.geteuid():
        raise CheckpointError("checkpoint root must be owner directory mode 0700", path)


def _read_bytes(descriptor: int, expected_size: int, path: Path) -> bytes:
    try:
        contents = os.pread(descriptor, expected_size + 1, 0)
    except OSError as error:
        raise CheckpointError("unable to read checkpoint", path) from error
    if len(contents) != expected_size:
        raise CheckpointError("checkpoint changed while read", path)
    return contents


def _close(descriptor: int, rule: str, path: Path) -> None:
    try:
        os.close(descriptor)
    except OSError as error:
        raise CheckpointError(rule, path) from error
