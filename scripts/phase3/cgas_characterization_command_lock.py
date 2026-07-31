from __future__ import annotations

import errno
import fcntl
import os
import stat
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final


_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_LOCK_FLAGS: Final = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC


@dataclass(frozen=True, slots=True)
class CommandLockError(RuntimeError):
    reason: str
    path: Path

    def __str__(self) -> str:
        return f"command lock {self.reason}: {self.path}"


def lock_path(final_path: Path) -> Path:
    return final_path.with_name(f".{final_path.name}.work.lock")


@contextmanager
def command_lock(final_path: Path, *, exclusive: bool, wait: bool) -> Generator[None, None, None]:
    path = lock_path(final_path)
    parent = _open_parent(path)
    descriptor: int | None = None
    try:
        descriptor = _open_lock(parent, path)
        _lock(descriptor, path, exclusive, wait)
        yield
    finally:
        if descriptor is not None:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
        os.close(parent)


def _open_parent(path: Path) -> int:
    try:
        return os.open(path.parent, _DIRECTORY_FLAGS)
    except OSError as error:
        raise CommandLockError("trusted_lock_parent_unavailable", path) from error


def _open_lock(parent: int, path: Path) -> int:
    try:
        descriptor = os.open(path.name, _LOCK_FLAGS, 0o600, dir_fd=parent)
    except OSError as error:
        raise CommandLockError("work_lock_unavailable", path) from error
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600 or status.st_uid != os.geteuid() or status.st_nlink != 1:
            raise CommandLockError("work_lock_unsafe", path)
        return descriptor
    except CommandLockError:
        os.close(descriptor)
        raise


def _lock(descriptor: int, path: Path, exclusive: bool, wait: bool) -> None:
    operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    if not wait:
        operation |= fcntl.LOCK_NB
    try:
        fcntl.flock(descriptor, operation)
    except BlockingIOError as error:
        raise CommandLockError("work_locked", path) from error
    except OSError as error:
        if error.errno in (errno.EACCES, errno.EAGAIN):
            raise CommandLockError("work_locked", path) from error
        raise CommandLockError("work_lock_unavailable", path) from error
