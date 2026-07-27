from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from . import output_layout_receipt_fs
from .output_layout_view_types import OutputLayoutViewLink, PinnedPath


_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
_RENAME_EXCHANGE: Final = output_layout_receipt_fs.RENAME_EXCHANGE
_RENAME_NOREPLACE: Final = output_layout_receipt_fs.RENAME_NOREPLACE
_renameat2 = output_layout_receipt_fs.atomic_rename
RENAME_NOREPLACE: Final = _RENAME_NOREPLACE
__all__ = ("RENAME_NOREPLACE", "rename_noreplace")


def rename_noreplace(parent_descriptor: int, source_name: str, destination_name: str) -> None:
    _renameat2(parent_descriptor, source_name, destination_name, RENAME_NOREPLACE)


@dataclass(frozen=True, slots=True)
class OwnedViewPath:
    path: Path
    device: int
    inode: int
    mode: int


@dataclass(frozen=True, slots=True)
class CleanupFailure:
    path: Path
    operation: str
    error: OSError


@dataclass(frozen=True, slots=True)
class CleanupReport:
    failures: tuple[CleanupFailure, ...]


class ViewCleanupError(OSError):
    def __init__(self, failures: tuple[CleanupFailure, ...]) -> None:
        self.failures: tuple[CleanupFailure, ...] = failures
        super().__init__("; ".join(f"{failure.operation}: {failure.path}: {failure.error}" for failure in failures))


def open_repository(repository: Path) -> int:
    return os.open(repository, _DIRECTORY_FLAGS)


def stat_path(root_descriptor: int, root: Path, path: Path) -> os.stat_result:
    parent_descriptor, name = _open_parent(root_descriptor, root, path)
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    finally:
        os.close(parent_descriptor)


def create_directory(repository_descriptor: int, repository: Path, path: Path) -> OwnedViewPath:
    return _create_entry(repository_descriptor, repository, path, None)


def create_symlink(
    repository_descriptor: int,
    repository: Path,
    destination: Path,
    target_text: str,
) -> OwnedViewPath:
    return _create_entry(repository_descriptor, repository, destination, target_text)


def _create_entry(
    repository_descriptor: int,
    repository: Path,
    path: Path,
    target_text: str | None,
) -> OwnedViewPath:
    parent_descriptor, name = _open_parent(repository_descriptor, repository, path)
    published = False
    try:
        if target_text is None:
            os.mkdir(name, dir_fd=parent_descriptor)
        else:
            os.symlink(target_text, name, dir_fd=parent_descriptor)
        published = True
        status = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        _verify_created_entry(parent_descriptor, name, status, target_text)
        return _owned(path, status)
    except OSError as error:
        if published:
            failure = CleanupFailure(path, "retain published view entry", error)
            raise ViewCleanupError((failure,)) from error
        raise
    finally:
        os.close(parent_descriptor)


def verify_owned_symlink(
    repository_descriptor: int,
    repository: Path,
    owned: OwnedViewPath,
    target_text: str,
) -> None:
    parent_descriptor, name = _open_parent(repository_descriptor, repository, owned.path)
    try:
        status = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if not _matches_owned(status, owned):
            raise OSError("published view symlink changed ownership")
        _verify_created_entry(parent_descriptor, name, status, target_text)
    finally:
        os.close(parent_descriptor)


def verify_owned_directory(repository_descriptor: int, repository: Path, owned: OwnedViewPath) -> None:
    parent_descriptor, name = _open_parent(repository_descriptor, repository, owned.path)
    try:
        status = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if not _matches_owned(status, owned) or not stat.S_ISDIR(status.st_mode):
            raise OSError("created view directory changed ownership")
    finally:
        os.close(parent_descriptor)


def verify_symlink(
    repository_descriptor: int,
    repository: Path,
    entry: OutputLayoutViewLink,
    target_pin: PinnedPath,
) -> None:
    destination = entry.destination(repository)
    parent_descriptor, name = _open_parent(repository_descriptor, repository, destination)
    try:
        status = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if not stat.S_ISLNK(status.st_mode):
            raise OSError("view entry is not a symlink")
        if os.readlink(name, dir_fd=parent_descriptor) != entry.readlink_target:
            raise OSError("view entry target text differs")
        resolved_status = os.stat(name, dir_fd=parent_descriptor)
    finally:
        os.close(parent_descriptor)
    target = repository.parent / entry.protected_target
    target_status = stat_path(repository_descriptor, repository, target)
    if not target_pin.matches(target_status, target_pin.content_token):
        raise OSError("protected target changed during final verification")
    if not target_pin.matches(resolved_status, target_pin.content_token):
        raise OSError("view entry resolves to an unexpected target")
    if entry.is_directory and not stat.S_ISDIR(target_status.st_mode):
        raise OSError("protected target has wrong directory kind")
    if not entry.is_directory and not stat.S_ISREG(target_status.st_mode):
        raise OSError("protected target has wrong file kind")


def rollback(
    repository_descriptor: int,
    repository: Path,
    links: list[OwnedViewPath],
    directories: list[OwnedViewPath],
) -> CleanupReport:
    failures: list[CleanupFailure] = []
    for owned in [*reversed(links), *reversed(directories)]:
        failure = _remove_if_owned(repository_descriptor, repository, owned, is_directory=False)
        if failure is not None:
            failures.append(failure)
    return CleanupReport(tuple(failures))


def _open_parent(repository_descriptor: int, repository: Path, path: Path) -> tuple[int, str]:
    relative = path.relative_to(repository)
    if not relative.parts:
        raise OSError("repository root cannot be a view entry")
    if any(part in {".", ".."} for part in relative.parts):
        raise OSError("view entry cannot traverse current or parent components")
    descriptor = os.dup(repository_descriptor)
    try:
        for part in relative.parts[:-1]:
            next_descriptor = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, relative.parts[-1]
    except OSError:
        os.close(descriptor)
        raise


def _owned(path: Path, status: os.stat_result) -> OwnedViewPath:
    return OwnedViewPath(path, status.st_dev, status.st_ino, stat.S_IFMT(status.st_mode))


def _verify_created_entry(parent_descriptor: int, name: str, status: os.stat_result, target_text: str | None) -> None:
    if target_text is None and not stat.S_ISDIR(status.st_mode):
        raise OSError("published view entry is not a directory")
    if target_text is not None and (
        not stat.S_ISLNK(status.st_mode) or os.readlink(name, dir_fd=parent_descriptor) != target_text
    ):
        raise OSError("published view entry is not the requested symlink")


def _remove_if_owned(
    repository_descriptor: int,
    repository: Path,
    owned: OwnedViewPath,
    *,
    is_directory: bool,
) -> CleanupFailure | None:
    del is_directory
    try:
        _ = stat_path(repository_descriptor, repository, owned.path)
    except FileNotFoundError:
        return None
    except OSError as error:
        return CleanupFailure(owned.path, "retain published view entry", error)
    return CleanupFailure(
        owned.path,
        "retain published view entry",
        OSError("directly published view entries are never destructively cleaned up"),
    )


def _matches_owned(status: os.stat_result, owned: OwnedViewPath) -> bool:
    return (status.st_dev, status.st_ino, stat.S_IFMT(status.st_mode)) == (
        owned.device,
        owned.inode,
        owned.mode,
    )
