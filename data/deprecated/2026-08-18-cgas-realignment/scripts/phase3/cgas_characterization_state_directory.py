from __future__ import annotations

import os
import stat
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final


_STATE_NAME: Final = ".cgas-characterization"
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


@dataclass(frozen=True, slots=True)
class StateDirectoryError(RuntimeError):
    reason: str
    path: Path

    def __str__(self) -> str:
        return f"trusted state {self.reason}: {self.path}"


@dataclass(frozen=True, slots=True)
class TrustedStateDirectory:
    path: Path
    descriptor: int

    def final_path(self, bundle_name: str) -> Path:
        _require_component(bundle_name, self.path)
        return self.path / bundle_name

    def work_path(self, bundle_name: str) -> Path:
        return self.final_path(bundle_name).with_name(f"{bundle_name}.work")

    def private_path(self, path: Path, *, create: bool) -> Path:
        if path.parent != self.path:
            raise StateDirectoryError("private_root_outside_state", path)
        _require_component(path.name, path)
        status = _entry_status(self.descriptor, path.name, path)
        if status is None:
            if not create:
                raise StateDirectoryError("private_root_not_directory", path)
            descriptor: int | None = None
            try:
                os.mkdir(path.name, 0o700, dir_fd=self.descriptor)
                descriptor = os.open(path.name, _DIRECTORY_FLAGS, dir_fd=self.descriptor)
                os.fchmod(descriptor, 0o700)
                os.fsync(descriptor)
                os.fsync(self.descriptor)
                return path
            except OSError as error:
                raise StateDirectoryError("private_root_create_failed", path) from error
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        if not stat.S_ISDIR(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o700 or status.st_uid != os.geteuid():
            raise StateDirectoryError("private_root_not_owned_mode0700", path)
        return path


@contextmanager
def open_trusted_state_directory(repository_root: Path, *, create: bool) -> Generator[TrustedStateDirectory, None, None]:
    repository = _open_repository(repository_root)
    tmp: int | None = None
    state: int | None = None
    state_path = repository_root / "tmp" / _STATE_NAME
    try:
        tmp = _open_tmp(repository, state_path)
        state = _open_state(tmp, state_path, create)
        yield TrustedStateDirectory(state_path, state)
    finally:
        if state is not None:
            os.close(state)
        if tmp is not None:
            os.close(tmp)
        os.close(repository)


def _open_repository(repository_root: Path) -> int:
    try:
        descriptor = os.open(repository_root, _DIRECTORY_FLAGS)
    except OSError as error:
        raise StateDirectoryError("repository_root_not_owner_safe", repository_root) from error
    try:
        _require_safe_parent(descriptor, repository_root, "repository_root_not_owner_safe")
        return descriptor
    except StateDirectoryError:
        os.close(descriptor)
        raise


def _open_tmp(repository: int, state_path: Path) -> int:
    try:
        descriptor = os.open("tmp", _DIRECTORY_FLAGS, dir_fd=repository)
    except OSError as error:
        raise StateDirectoryError("tmp_parent_not_owner_safe", state_path.parent) from error
    try:
        _require_safe_parent(descriptor, state_path.parent, "tmp_parent_not_owner_safe")
        return descriptor
    except StateDirectoryError:
        os.close(descriptor)
        raise


def _open_state(tmp: int, state_path: Path, create: bool) -> int:
    status = _entry_status(tmp, _STATE_NAME, state_path)
    if status is None:
        if not create:
            raise StateDirectoryError("state_child_missing", state_path)
        try:
            os.mkdir(_STATE_NAME, 0o700, dir_fd=tmp)
            descriptor = os.open(_STATE_NAME, _DIRECTORY_FLAGS, dir_fd=tmp)
            os.fchmod(descriptor, 0o700)
            identity = _require_owner_state(descriptor, state_path)
            os.fsync(descriptor)
            os.fsync(tmp)
            _require_named_identity(tmp, state_path, identity)
            return descriptor
        except OSError as error:
            raise StateDirectoryError("state_child_create_failed", state_path) from error
    if not stat.S_ISDIR(status.st_mode):
        raise StateDirectoryError("state_child_not_owner_mode0700", state_path)
    try:
        descriptor = os.open(_STATE_NAME, _DIRECTORY_FLAGS, dir_fd=tmp)
    except OSError as error:
        raise StateDirectoryError("state_child_not_owner_mode0700", state_path) from error
    try:
        identity = _require_owner_state(descriptor, state_path)
        _require_named_identity(tmp, state_path, identity)
        return descriptor
    except StateDirectoryError:
        os.close(descriptor)
        raise


def _require_safe_parent(descriptor: int, path: Path, reason: str) -> None:
    status = os.fstat(descriptor)
    if not stat.S_ISDIR(status.st_mode) or status.st_uid != os.geteuid() or stat.S_IMODE(status.st_mode) & 0o022:
        raise StateDirectoryError(reason, path)


def _require_owner_state(descriptor: int, path: Path) -> tuple[int, int, int, int]:
    status = os.fstat(descriptor)
    identity = status.st_dev, status.st_ino, status.st_uid, stat.S_IMODE(status.st_mode)
    if not stat.S_ISDIR(status.st_mode) or identity[2:] != (os.geteuid(), 0o700):
        raise StateDirectoryError("state_child_not_owner_mode0700", path)
    return identity


def _require_named_identity(tmp: int, path: Path, expected: tuple[int, int, int, int]) -> None:
    try:
        status = os.stat(_STATE_NAME, dir_fd=tmp, follow_symlinks=False)
    except OSError as error:
        raise StateDirectoryError("state_child_identity_changed", path) from error
    identity = status.st_dev, status.st_ino, status.st_uid, stat.S_IMODE(status.st_mode)
    if not stat.S_ISDIR(status.st_mode) or identity != expected:
        raise StateDirectoryError("state_child_identity_changed", path)


def _entry_status(parent: int, name: str, path: Path) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise StateDirectoryError("state_child_inspection_failed", path) from error


def _require_component(name: str, path: Path) -> None:
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise StateDirectoryError("unsafe_bundle_component", path / name)
