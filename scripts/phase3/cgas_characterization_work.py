from __future__ import annotations

import os
import stat
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .cgas_characterization_contract import MAX_RUN_CONTRACT_BYTES
from .cgas_serialization import CanonicalSerializationError, canonical_json_object

_INITIALIZING = ".initializing"
_PROFILE = frozenset({"checkpoints", "run-contract.json"})
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_CONTRACT_READ_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class WorkRootError(RuntimeError):
    reason: str
    path: Path

    def __str__(self) -> str:
        return f"work_root {self.reason}: {self.path}"


@dataclass(frozen=True, slots=True)
class RunContractSnapshot:
    canonical_bytes: bytes
    device: int
    inode: int
    size: int


@dataclass(frozen=True, slots=True)
class WorkInitializationHooks:
    mkdir_root: Callable[[Path, int], None]
    write_contents: Callable[[int, str, bytes], None]
    fsync_file: Callable[[int], None]
    fsync_directory: Callable[[int], None]
    mkdir_checkpoints: Callable[[int, str, int], None]


def work_root_for(final_root: Path) -> Path:
    """Return the only permitted sibling work root for a final candidate root."""
    name = final_root.name
    if not name or name in {".", ".."} or "/" in name:
        raise WorkRootError("unsafe_final_component", final_root)
    return final_root.with_name(f"{name}.work")


def initialize_work_root(
    final_root: Path, contract_bytes: bytes, hooks: WorkInitializationHooks | None = None
) -> Path:
    work_root = work_root_for(final_root)
    _require_fresh_entries(final_root, work_root)
    operations = hooks or WorkInitializationHooks(os.mkdir, _write_contents_at, _fsync_descriptor, _fsync_descriptor, _mkdir_at)
    parent = os.open(final_root.parent, _DIRECTORY_FLAGS)
    root_descriptor: int | None = None
    try:
        if hooks is None:
            _mkdir_new_work_root(parent, final_root, work_root)
        else:
            operations.mkdir_root(work_root, 0o700)
        root_descriptor = os.open(work_root.name, _DIRECTORY_FLAGS, dir_fd=parent)
        root_identity = _normalize_directory(root_descriptor)
        operations.write_contents(root_descriptor, _INITIALIZING, b"")
        operations.fsync_directory(root_descriptor)
        operations.fsync_directory(parent)
        operations.mkdir_checkpoints(root_descriptor, "checkpoints", 0o700)
        checkpoints = os.open("checkpoints", _DIRECTORY_FLAGS, dir_fd=root_descriptor)
        try:
            _normalize_directory(checkpoints)
            operations.fsync_directory(checkpoints)
        finally:
            os.close(checkpoints)
        operations.fsync_directory(root_descriptor)
        operations.write_contents(root_descriptor, "run-contract.json", contract_bytes)
        contract = os.open("run-contract.json", _READ_FLAGS, dir_fd=root_descriptor)
        try:
            operations.fsync_file(contract)
        finally:
            os.close(contract)
        operations.fsync_directory(root_descriptor)
        operations.fsync_directory(parent)
        os.unlink(_INITIALIZING, dir_fd=root_descriptor)
        operations.fsync_directory(root_descriptor)
        operations.fsync_directory(parent)
        _require_pinned_directory(root_descriptor, root_identity, work_root)
        _require_root_entry(parent, work_root.name, root_identity)
    except OSError as error:
        raise WorkRootError("initialize_failed", work_root) from error
    except WorkRootError:
        raise
    finally:
        if root_descriptor is not None:
            os.close(root_descriptor)
        os.close(parent)
    return work_root


def require_work_root(final_root: Path, expected_contract: bytes) -> Path:
    work_root = work_root_for(final_root)
    final_status, work_status = _root_entry_statuses(final_root, work_root)
    if final_status is not None or work_status is None:
        raise WorkRootError("resume_root_missing_or_final_present", work_root)
    if not stat.S_ISDIR(work_status.st_mode):
        raise WorkRootError("unsafe_work_root_entry", work_root)
    _read_initialized_contract(work_root, expected_contract)
    return work_root


def read_initialized_contract(work_root: Path) -> bytes:
    return read_initialized_contract_snapshot(work_root).canonical_bytes


def read_initialized_contract_snapshot(work_root: Path) -> RunContractSnapshot:
    return _read_initialized_contract(work_root, None)


def _read_initialized_contract(work_root: Path, expected: bytes | None) -> RunContractSnapshot:
    try:
        directory = os.open(work_root, _DIRECTORY_FLAGS)
    except OSError as error:
        raise WorkRootError("incomplete_initialization", work_root) from error
    try:
        status = os.fstat(directory)
        names = frozenset(os.listdir(directory))
        if not stat.S_ISDIR(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o700 or status.st_uid != os.geteuid() or names != _PROFILE:
            raise WorkRootError("incomplete_initialization", work_root)
        _require_directory(directory, "checkpoints", work_root)
        contents = _read_contract(directory, work_root)
    except OSError as error:
        raise WorkRootError("incomplete_initialization", work_root) from error
    finally:
        os.close(directory)
    if expected is not None and contents.canonical_bytes != expected:
        raise WorkRootError("incomplete_initialization", work_root)
    return contents


def _require_fresh_entries(final_root: Path, work_root: Path) -> None:
    final_status, work_status = _root_entry_statuses(final_root, work_root)
    if final_status is not None or work_status is not None:
        raise WorkRootError("fresh_root_exists", final_root if final_status is not None else work_root)


def _mkdir_new_work_root(parent: int, final_root: Path, work_root: Path) -> None:
    final_status = _entry_status(parent, final_root.name)
    work_status = _entry_status(parent, work_root.name)
    if final_status is not None or work_status is not None:
        raise WorkRootError("fresh_root_exists", final_root if final_status is not None else work_root)
    os.mkdir(work_root.name, 0o700, dir_fd=parent)


def _normalize_directory(descriptor: int) -> tuple[int, int, int, int]:
    os.fchmod(descriptor, 0o700)
    status = os.fstat(descriptor)
    if not stat.S_ISDIR(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o700 or status.st_uid != os.geteuid():
        raise OSError("new directory is not owner mode 0700")
    os.fsync(descriptor)
    return status.st_dev, status.st_ino, status.st_uid, stat.S_IMODE(status.st_mode)


def _require_pinned_directory(descriptor: int, identity: tuple[int, int, int, int], work_root: Path) -> None:
    status = os.fstat(descriptor)
    if not stat.S_ISDIR(status.st_mode) or (status.st_dev, status.st_ino, status.st_uid, stat.S_IMODE(status.st_mode)) != identity:
        raise WorkRootError("initialize_indeterminate", work_root)


def _require_root_entry(parent: int, name: str, identity: tuple[int, int, int, int]) -> None:
    status = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if not stat.S_ISDIR(status.st_mode) or (status.st_dev, status.st_ino, status.st_uid, stat.S_IMODE(status.st_mode)) != identity:
        raise WorkRootError("initialize_indeterminate", Path(name))


def _root_entry_statuses(final_root: Path, work_root: Path) -> tuple[os.stat_result | None, os.stat_result | None]:
    parent = os.open(final_root.parent, _DIRECTORY_FLAGS)
    try:
        return _entry_status(parent, final_root.name), _entry_status(parent, work_root.name)
    finally:
        os.close(parent)


def _entry_status(parent: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _write_contents_at(parent: int, name: str, contents: bytes) -> None:
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
    try:
        offset = 0
        while offset < len(contents):
            written = os.write(descriptor, contents[offset:])
            if written <= 0:
                raise OSError("run contract write made no progress")
            offset += written
    finally:
        os.close(descriptor)


def _mkdir_at(parent: int, name: str, mode: int) -> None:
    os.mkdir(name, mode, dir_fd=parent)


def _fsync_descriptor(descriptor: int) -> None:
    os.fsync(descriptor)


def _require_directory(parent: int, name: str, work_root: Path) -> None:
    status = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if not stat.S_ISDIR(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o700 or status.st_uid != os.geteuid():
        raise WorkRootError("incomplete_initialization", work_root)


def _read_contract(parent: int, work_root: Path) -> RunContractSnapshot:
    descriptor = os.open("run-contract.json", _READ_FLAGS, dir_fd=parent)
    try:
        before = _pinned_contract_status(descriptor, work_root)
        contents = bytearray()
        offset = 0
        while offset < before.st_size:
            chunk = os.pread(descriptor, min(_CONTRACT_READ_CHUNK_BYTES, before.st_size - offset), offset)
            if not chunk:
                raise WorkRootError("incomplete_initialization", work_root)
            contents.extend(chunk)
            offset += len(chunk)
        after = _pinned_contract_status(descriptor, work_root)
        if (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise WorkRootError("incomplete_initialization", work_root)
        canonical_bytes = bytes(contents)
        try:
            raw = json.loads(canonical_bytes)
            if not isinstance(raw, dict) or canonical_json_object(raw) != canonical_bytes:
                raise WorkRootError("incomplete_initialization", work_root)
        except (json.JSONDecodeError, CanonicalSerializationError) as error:
            raise WorkRootError("incomplete_initialization", work_root) from error
        return RunContractSnapshot(canonical_bytes, before.st_dev, before.st_ino, before.st_size)
    finally:
        os.close(descriptor)


def _pinned_contract_status(descriptor: int, work_root: Path) -> os.stat_result:
    status = os.fstat(descriptor)
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_IMODE(status.st_mode) != 0o600
        or status.st_uid != os.geteuid()
        or status.st_nlink != 1
        or status.st_size > MAX_RUN_CONTRACT_BYTES
    ):
        raise WorkRootError("incomplete_initialization", work_root)
    return status
