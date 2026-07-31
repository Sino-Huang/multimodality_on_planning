from __future__ import annotations

import json
import os
import resource
import stat
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .cgas_characterization_contract import MAX_RUN_CONTRACT_BYTES, CharacterizationRunContract
from .cgas_characterization_work import RunContractSnapshot, WorkRootError
from .cgas_serialization import CanonicalSerializationError, canonical_json_object

_NAME: Final = "run-contract.json"
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_READ_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_CHUNK_BYTES: Final = 64 * 1024
_FD_RESERVE: Final = 4


@dataclass(frozen=True, slots=True)
class PinnedRunContract:
    work_root: Path
    directory: int
    descriptor: int
    snapshot: RunContractSnapshot

    def require_contract(self, contract: CharacterizationRunContract) -> None:
        current = self.require_current()
        if current.canonical_bytes != contract.canonical_bytes:
            raise WorkRootError("incomplete_initialization", self.work_root)

    def require_current(self) -> RunContractSnapshot:
        status = _status(self.descriptor, self.work_root)
        entry = os.stat(_NAME, dir_fd=self.directory, follow_symlinks=False)
        if (entry.st_dev, entry.st_ino, entry.st_size) != (status.st_dev, status.st_ino, status.st_size):
            raise WorkRootError("incomplete_initialization", self.work_root)
        current = _snapshot(self.descriptor, self.work_root)
        if current != self.snapshot:
            raise WorkRootError("incomplete_initialization", self.work_root)
        return current


@contextmanager
def pin_run_contract(work_root: Path) -> Generator[PinnedRunContract, None, None]:
    _require_capacity(work_root)
    directory: int | None = None
    try:
        directory = os.open(work_root, _DIRECTORY_FLAGS)
        descriptor = os.open(_NAME, _READ_FLAGS, dir_fd=directory)
    except OSError as error:
        if directory is not None:
            os.close(directory)
        raise WorkRootError("incomplete_initialization", work_root) from error
    try:
        yield PinnedRunContract(work_root, directory, descriptor, _snapshot(descriptor, work_root))
    finally:
        _close(descriptor, directory, work_root)


def _require_capacity(work_root: Path) -> None:
    soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft_limit == resource.RLIM_INFINITY:
        return
    try:
        open_count = len(os.listdir("/proc/self/fd"))
    except OSError as error:
        raise WorkRootError("incomplete_initialization", work_root) from error
    if open_count + 2 + _FD_RESERVE > soft_limit:
        raise WorkRootError("incomplete_initialization", work_root)


def _snapshot(descriptor: int, work_root: Path) -> RunContractSnapshot:
    before = _status(descriptor, work_root)
    contents = bytearray()
    offset = 0
    while offset < before.st_size:
        try:
            chunk = os.pread(descriptor, min(_CHUNK_BYTES, before.st_size - offset), offset)
        except OSError as error:
            raise WorkRootError("incomplete_initialization", work_root) from error
        if not chunk:
            raise WorkRootError("incomplete_initialization", work_root)
        contents.extend(chunk)
        offset += len(chunk)
    after = _status(descriptor, work_root)
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


def _status(descriptor: int, work_root: Path) -> os.stat_result:
    try:
        status = os.fstat(descriptor)
    except OSError as error:
        raise WorkRootError("incomplete_initialization", work_root) from error
    if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600 or status.st_uid != os.geteuid() or status.st_nlink != 1 or status.st_size > MAX_RUN_CONTRACT_BYTES:
        raise WorkRootError("incomplete_initialization", work_root)
    return status


def _close(descriptor: int, directory: int, work_root: Path) -> None:
    failure: OSError | None = None
    for value in (descriptor, directory):
        try:
            os.close(value)
        except OSError as error:
            failure = failure or error
    if failure is not None:
        raise WorkRootError("incomplete_initialization", work_root) from failure
