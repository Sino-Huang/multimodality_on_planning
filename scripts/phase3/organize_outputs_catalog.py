from __future__ import annotations

import errno
import os
import secrets
import stat
from pathlib import Path
from typing import Final

from .output_layout_inventory_types import OutputLayoutInventoryError
from .output_layout_receipt_fs import RENAME_NOREPLACE, atomic_rename as _atomic_rename
from .output_layout_receipt_io import open_parent_directory


_TEMPORARY_PREFIX: Final = ".{name}.tmp-"
_TEMPORARY_ATTEMPTS: Final = 32
_CREATE_FLAGS: Final = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


class CatalogPublicationError(RuntimeError):
    def __init__(self, *, rule: str, path: Path) -> None:
        self.rule = rule
        self.path = path
        super().__init__(f"{rule}: {path}")


def publish_catalog(destination: Path, rendered_catalog: str) -> None:
    """Durably publish catalog text without replacing an existing leaf."""
    destination_name = _destination_name(destination)
    contents = rendered_catalog.encode("utf-8")
    parent_descriptor = _open_parent(destination)
    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    temporary_descriptor: int | None = None
    published = False
    primary_error: CatalogPublicationError | None = None
    try:
        _require_absent_leaf(parent_descriptor, destination_name, destination)
        _require_current_parent(parent_descriptor, destination.parent, destination)
        temporary_name, temporary_descriptor = _create_temporary(parent_descriptor, destination)
        temporary_identity = _identity(temporary_descriptor, destination)
        _write_and_sync_temporary(temporary_descriptor, contents, destination)
        _close_descriptor(temporary_descriptor, "unable to close catalog temporary", destination)
        temporary_descriptor = None
        _require_current_parent(parent_descriptor, destination.parent, destination)
        _publish(parent_descriptor, temporary_name, destination_name, destination, temporary_identity)
        published = True
        _sync_parent(parent_descriptor, destination.parent)
        _require_current_parent(parent_descriptor, destination.parent, destination)
    except CatalogPublicationError as error:
        primary_error = error
        raise
    finally:
        close_error: CatalogPublicationError | None = None
        if temporary_descriptor is not None:
            close_error = _close_after_failure(temporary_descriptor, "unable to close catalog temporary", destination)
        if temporary_name is not None and temporary_identity is not None and not published:
            _cleanup_owned_temporary(parent_descriptor, temporary_name, temporary_identity)
        parent_close_error = _close_after_failure(parent_descriptor, "unable to close catalog parent", destination.parent)
        if close_error is None:
            close_error = parent_close_error
        if primary_error is None and close_error is not None:
            raise close_error


def _destination_name(destination: Path) -> str:
    if destination.name:
        return destination.name
    raise CatalogPublicationError(rule="catalog destination must name a leaf", path=destination)


def _open_parent(destination: Path) -> int:
    try:
        return open_parent_directory(destination.parent)
    except OutputLayoutInventoryError as error:
        raise CatalogPublicationError(rule="catalog parent must be a real directory", path=destination.parent) from error


def _require_absent_leaf(parent_descriptor: int, destination_name: str, destination: Path) -> None:
    try:
        _ = os.stat(destination_name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as error:
        raise CatalogPublicationError(rule="catalog destination cannot be inspected", path=destination) from error
    raise CatalogPublicationError(rule="catalog destination already exists", path=destination)


def _require_current_parent(parent_descriptor: int, parent: Path, destination: Path) -> None:
    try:
        expected = os.fstat(parent_descriptor)
        current = parent.lstat()
    except OSError as error:
        raise CatalogPublicationError(rule="catalog parent changed during publication", path=destination) from error
    if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
        raise CatalogPublicationError(rule="catalog parent changed during publication", path=destination)


def _create_temporary(parent_descriptor: int, destination: Path) -> tuple[str, int]:
    prefix = _TEMPORARY_PREFIX.format(name=destination.name)
    for _attempt in range(_TEMPORARY_ATTEMPTS):
        temporary_name = f"{prefix}{secrets.token_hex(16)}"
        try:
            descriptor = os.open(temporary_name, _CREATE_FLAGS, 0o600, dir_fd=parent_descriptor)
        except FileExistsError:
            continue
        except OSError as error:
            raise CatalogPublicationError(rule="unable to create catalog temporary", path=destination) from error
        try:
            temporary_status = os.fstat(descriptor)
        except OSError as error:
            _ = _close_after_failure(descriptor, "unable to close catalog temporary", destination)
            raise CatalogPublicationError(rule="unable to inspect catalog temporary", path=destination) from error
        temporary_identity = temporary_status.st_dev, temporary_status.st_ino
        try:
            os.fchmod(descriptor, 0o600)
        except OSError as error:
            _ = _close_after_failure(descriptor, "unable to close catalog temporary", destination)
            _cleanup_owned_temporary(parent_descriptor, temporary_name, temporary_identity)
            raise CatalogPublicationError(rule="unable to create catalog temporary", path=destination) from error
        return temporary_name, descriptor
    raise CatalogPublicationError(rule="unable to allocate catalog temporary", path=destination)


def _identity(descriptor: int, destination: Path) -> tuple[int, int]:
    try:
        status = os.fstat(descriptor)
    except OSError as error:
        raise CatalogPublicationError(rule="unable to inspect catalog temporary", path=destination) from error
    if not stat.S_ISREG(status.st_mode):
        raise CatalogPublicationError(rule="catalog temporary must be a regular file", path=destination)
    return status.st_dev, status.st_ino


def _write_and_sync_temporary(descriptor: int, contents: bytes, destination: Path) -> None:
    offset = 0
    try:
        while offset < len(contents):
            written = os.write(descriptor, contents[offset:])
            if written == 0:
                raise OSError("catalog temporary write made no progress")
            offset += written
        os.fsync(descriptor)
    except OSError as error:
        raise CatalogPublicationError(rule="unable to write catalog temporary", path=destination) from error


def _publish(
    parent_descriptor: int,
    temporary_name: str,
    destination_name: str,
    destination: Path,
    temporary_identity: tuple[int, int],
) -> None:
    _require_current_temporary(parent_descriptor, temporary_name, temporary_identity, destination)
    try:
        _atomic_rename(parent_descriptor, temporary_name, destination_name, RENAME_NOREPLACE)
    except FileExistsError as error:
        raise CatalogPublicationError(rule="catalog destination collision", path=destination) from error
    except OSError as error:
        if error.errno in (errno.ENOSYS, errno.EINVAL):
            raise CatalogPublicationError(rule="renameat2 is unavailable", path=destination) from error
        raise CatalogPublicationError(rule="catalog no-replace rename failed", path=destination) from error


def _require_current_temporary(
    parent_descriptor: int,
    temporary_name: str,
    expected_identity: tuple[int, int],
    destination: Path,
) -> None:
    try:
        status = os.stat(temporary_name, dir_fd=parent_descriptor, follow_symlinks=False)
    except OSError as error:
        raise CatalogPublicationError(rule="catalog temporary changed before publication", path=destination) from error
    if not stat.S_ISREG(status.st_mode) or (status.st_dev, status.st_ino) != expected_identity:
        raise CatalogPublicationError(rule="catalog temporary changed before publication", path=destination)


def _sync_parent(parent_descriptor: int, parent: Path) -> None:
    try:
        os.fsync(parent_descriptor)
    except OSError as error:
        raise CatalogPublicationError(rule="unable to fsync catalog parent", path=parent) from error


def _close_descriptor(descriptor: int, rule: str, path: Path) -> None:
    try:
        os.close(descriptor)
    except OSError as error:
        raise CatalogPublicationError(rule=rule, path=path) from error


def _close_after_failure(descriptor: int, rule: str, path: Path) -> CatalogPublicationError | None:
    try:
        _close_descriptor(descriptor, rule, path)
    except CatalogPublicationError as error:
        return error
    return None


def _cleanup_owned_temporary(
    parent_descriptor: int,
    temporary_name: str,
    expected_identity: tuple[int, int] | None,
) -> None:
    try:
        status = os.stat(temporary_name, dir_fd=parent_descriptor, follow_symlinks=False)
    except OSError:
        return
    if expected_identity is not None and stat.S_ISREG(status.st_mode) and (status.st_dev, status.st_ino) == expected_identity:
        try:
            os.unlink(temporary_name, dir_fd=parent_descriptor)
        except OSError:
            return
