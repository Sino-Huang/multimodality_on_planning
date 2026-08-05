from __future__ import annotations

import fcntl
import os
import re
import stat
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .cgas_candidate_characterization_checkpoint import validate_checkpoint
from .cgas_candidate_characterization_contracts import (
    CandidateCharacterizationError,
    model_bytes,
    parse_canonical_model,
    sha256,
)
from .cgas_candidate_characterization_models import CheckpointModel, CurrentIndexModel, JsonObject

_CHECKPOINT_NAME: Final = re.compile(r"reservoir_checkpoint_(\d{6})\.json")


@dataclass(frozen=True, slots=True)
class CheckpointEntry:
    path: Path
    checkpoint: CheckpointModel
    digest: str
    contents: bytes


@contextmanager
def output_lock(output: Path) -> Generator[None, None, None]:
    _ensure_directory(output)
    descriptor = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def checkpoint_path(output: Path, round_number: int) -> Path:
    return output / "checkpoints" / f"reservoir_checkpoint_{round_number:06d}.json"


def scan_chain(output: Path, repository_root: Path) -> tuple[CheckpointEntry, ...]:
    root = output / "checkpoints"
    if not root.exists():
        return ()
    _require_directory(root)
    entries: list[CheckpointEntry] = []
    for path in sorted(root.iterdir()):
        match = _CHECKPOINT_NAME.fullmatch(path.name)
        if match is None or path.is_symlink() or not path.is_file():
            raise CandidateCharacterizationError("checkpoint_name_invalid", path)
        checkpoint, contents = parse_canonical_model(path, CheckpointModel, "checkpoint_invalid")
        if checkpoint.round != int(match.group(1)):
            raise CandidateCharacterizationError("checkpoint_round_invalid", path)
        validate_checkpoint(checkpoint, path, repository_root)
        entries.append(CheckpointEntry(path, checkpoint, sha256(contents), contents))
    for index, entry in enumerate(entries):
        expected_round = index + 1
        predecessor = None if index == 0 else entries[index - 1].digest
        if entry.checkpoint.round != expected_round or entry.checkpoint.predecessor_checkpoint_sha256 != predecessor:
            raise CandidateCharacterizationError("checkpoint_chain_invalid", entry.path)
        if index and not _bindings_equal(entries[index - 1].checkpoint, entry.checkpoint):
            raise CandidateCharacterizationError("checkpoint_policy_drift", entry.path)
    return tuple(entries)


def recover_current_index(output: Path, repository_root: Path, chain: tuple[CheckpointEntry, ...]) -> None:
    current = output / "current.json"
    if not chain:
        if current.exists():
            raise CandidateCharacterizationError("current_index_without_checkpoint", current)
        return
    expected = _index(chain[-1], repository_root)
    expected_bytes = model_bytes(expected) + b"\n"
    try:
        parsed, contents = parse_canonical_model(current, CurrentIndexModel, "current_index_invalid")
    except CandidateCharacterizationError:
        _replace_index(current, expected_bytes)
        return
    if parsed == expected and contents == expected_bytes:
        return
    _replace_index(current, expected_bytes)


def publish_checkpoint(output: Path, checkpoint: CheckpointModel) -> CheckpointEntry:
    root = output / "checkpoints"
    _ensure_directory(root)
    destination = checkpoint_path(output, checkpoint.round)
    contents = model_bytes(checkpoint) + b"\n"
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != contents:
            raise CandidateCharacterizationError("checkpoint_collision", destination)
        return CheckpointEntry(destination, checkpoint, sha256(contents), contents)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".checkpoint-", dir=root)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination, follow_symlinks=False)
        _sync_directory(root)
    except (FileExistsError, OSError) as error:
        if destination.exists() and not destination.is_symlink() and destination.read_bytes() == contents:
            return CheckpointEntry(destination, checkpoint, sha256(contents), contents)
        raise CandidateCharacterizationError("checkpoint_publication_failed", destination) from error
    finally:
        temporary.unlink(missing_ok=True)
    return CheckpointEntry(destination, checkpoint, sha256(contents), contents)


def publish_current_index(entry: CheckpointEntry, output: Path, repository_root: Path) -> None:
    _replace_index(output / "current.json", model_bytes(_index(entry, repository_root)) + b"\n")


def publish_receipt(path: Path, record: JsonObject) -> None:
    _ensure_directory(path.parent)
    import json

    contents = (
        json.dumps(record, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode() + b"\n"
    )
    if path.exists():
        if path.is_symlink() or path.read_bytes() != contents:
            raise CandidateCharacterizationError("receipt_collision", path)
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(contents)
        handle.flush()
        os.fsync(handle.fileno())
    _sync_directory(path.parent)


def _replace_index(path: Path, contents: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".current-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _index(entry: CheckpointEntry, repository_root: Path) -> CurrentIndexModel:
    try:
        relative = entry.path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError as error:
        raise CandidateCharacterizationError("path_outside_repository", entry.path) from error
    return CurrentIndexModel(checkpoint_path=relative, checkpoint_sha256=entry.digest, round=entry.checkpoint.round)


def _bindings_equal(left: CheckpointModel, right: CheckpointModel) -> bool:
    return (
        left.approved_trace_sha256 == right.approved_trace_sha256
        and left.approved_trace_contract_sha256 == right.approved_trace_contract_sha256
        and left.candidate_config_sha256 == right.candidate_config_sha256
        and left.selector == right.selector
    )


def _ensure_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    _require_directory(path)


def _require_directory(path: Path) -> None:
    status = path.lstat()
    if not stat.S_ISDIR(status.st_mode) or path.is_symlink():
        raise CandidateCharacterizationError("directory_invalid", path)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
