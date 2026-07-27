from __future__ import annotations

import fcntl
import os
import stat
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Final


__all__ = ["OutputLayoutLockError", "exclusive_output_layout_lock", "shared_output_layout_lock"]

_REPOSITORY_OPEN_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW


class OutputLayoutLockError(ValueError):
    def __init__(self, *, rule: str, path: Path) -> None:
        self.rule: str = rule
        self.path: Path = path
        super().__init__(f"{rule}: {path}")


def shared_output_layout_lock(repository: Path) -> AbstractContextManager[None]:
    return _output_layout_lock(repository, fcntl.LOCK_SH)


def exclusive_output_layout_lock(repository: Path) -> AbstractContextManager[None]:
    return _output_layout_lock(repository, fcntl.LOCK_EX)


@contextmanager
def _output_layout_lock(repository: Path, operation: int) -> Iterator[None]:
    descriptor = _open_repository_directory(repository)
    acquired = False
    try:
        _verify_repository_descriptor(repository, descriptor)
        fcntl.flock(descriptor, operation)
        acquired = True
        _verify_repository_descriptor(repository, descriptor)
        yield
    finally:
        try:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _validate_real_directory(path: Path, rule: str) -> os.stat_result:
    if not path.is_absolute():
        raise OutputLayoutLockError(rule=rule, path=path)
    try:
        status = path.lstat()
        canonical = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise OutputLayoutLockError(rule=rule, path=path) from error
    if canonical != path or stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        raise OutputLayoutLockError(rule=rule, path=path)
    return status


def _open_repository_directory(repository: Path) -> int:
    _ = _validate_real_directory(repository, "repository must be an absolute canonical real directory")
    try:
        return os.open(repository, _REPOSITORY_OPEN_FLAGS)
    except OSError as error:
        raise OutputLayoutLockError(rule="repository directory cannot be opened safely", path=repository) from error


def _verify_repository_descriptor(repository: Path, descriptor: int) -> None:
    try:
        opened_status = os.fstat(descriptor)
    except OSError as error:
        raise OutputLayoutLockError(rule="repository directory descriptor cannot be verified safely", path=repository) from error
    named_status = _validate_real_directory(repository, "repository must be an absolute canonical real directory")
    if (
        not stat.S_ISDIR(opened_status.st_mode)
        or (opened_status.st_dev, opened_status.st_ino) != (named_status.st_dev, named_status.st_ino)
    ):
        raise OutputLayoutLockError(rule="repository directory must match the opened descriptor", path=repository)
