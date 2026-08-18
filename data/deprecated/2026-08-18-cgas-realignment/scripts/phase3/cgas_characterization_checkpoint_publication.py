from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .cgas_characterization_checkpoint_contracts import Checkpoint, CheckpointError, checkpoint_name, external_private_root, normalize_expectation
from .cgas_characterization_checkpoint_fs import linkat_proc_fd
from .output_layout_inventory_types import OutputLayoutInventoryError
from .output_layout_receipt_io import open_parent_directory


_ANONYMOUS_FLAGS: Final = os.O_TMPFILE | os.O_RDWR | os.O_CLOEXEC
_READ_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


@dataclass(frozen=True, slots=True)
class _FileIdentity:
    device: int
    inode: int
    owner: int


def publish_checkpoint(root: Path, private_root: Path, checkpoint: Checkpoint) -> None:
    expected = normalize_expectation(checkpoint.expectation)
    destination_name = checkpoint_name(expected.row_index)
    canonical_root, canonical_private_root = external_private_root(root, private_root)
    destination = canonical_root / destination_name
    root_descriptor = _open_directory(root, "checkpoint root must be a real directory")
    private_descriptor: int | None = None
    anonymous_descriptor: int | None = None
    try:
        private_descriptor = _open_private_directory(private_root)
        _require_same_filesystem(root_descriptor, private_descriptor, destination)
        anonymous_descriptor = _open_anonymous(private_root, destination)
        identity = _regular_identity(anonymous_descriptor, destination, 0)
        _write_and_sync(anonymous_descriptor, checkpoint.canonical_bytes, destination)
        _verify_anonymous(anonymous_descriptor, identity, checkpoint.canonical_bytes, destination)
        try:
            linkat_proc_fd(anonymous_descriptor, root_descriptor, os.fsencode(destination_name))
        except FileExistsError as error:
            raise CheckpointError("checkpoint destination collision", destination) from error
        except OSError as error:
            raise CheckpointError("checkpoint procfd linkat failed", destination) from error
        _verify_published(root_descriptor, destination_name, identity, checkpoint.canonical_bytes, destination)
        _sync_directory(root_descriptor, canonical_root, destination)
    except CheckpointError:
        raise
    except OSError as error:
        raise CheckpointError("checkpoint publication failed", destination) from error
    finally:
        if anonymous_descriptor is not None:
            _close(anonymous_descriptor, "unable to close anonymous checkpoint", destination)
        if private_descriptor is not None:
            _close(private_descriptor, "unable to close checkpoint private root", canonical_private_root)
        _close(root_descriptor, "unable to close checkpoint root", canonical_root)


def _open_directory(path: Path, rule: str) -> int:
    try:
        return open_parent_directory(path)
    except OutputLayoutInventoryError as error:
        raise CheckpointError(rule, path) from error


def _open_private_directory(path: Path) -> int:
    descriptor = _open_directory(path, "checkpoint private root must be a real directory")
    status = os.fstat(descriptor)
    if stat.S_IMODE(status.st_mode) != 0o700 or status.st_uid != os.geteuid():
        _close(descriptor, "unable to close checkpoint private root", path)
        raise CheckpointError("checkpoint private root must be owned mode 0700", path)
    return descriptor


def _require_same_filesystem(root_descriptor: int, private_descriptor: int, destination: Path) -> None:
    root_status = os.fstat(root_descriptor)
    private_status = os.fstat(private_descriptor)
    if (root_status.st_dev, root_status.st_ino) == (private_status.st_dev, private_status.st_ino):
        raise CheckpointError("checkpoint private root must be external to checkpoint root", destination)
    if root_status.st_dev != private_status.st_dev:
        raise CheckpointError("checkpoint private root must share destination filesystem", destination)


def _open_anonymous(private_root: Path, destination: Path) -> int:
    try:
        descriptor = os.open(private_root, _ANONYMOUS_FLAGS, 0o600)
        os.fchmod(descriptor, 0o600)
        return descriptor
    except OSError as error:
        raise CheckpointError("checkpoint otmpfile unsupported", destination) from error


def _regular_identity(descriptor: int, path: Path, links: int) -> _FileIdentity:
    status = os.fstat(descriptor)
    if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600 or status.st_uid != os.geteuid() or status.st_nlink != links:
        raise CheckpointError("checkpoint metadata changed", path)
    return _FileIdentity(status.st_dev, status.st_ino, status.st_uid)


def _write_and_sync(descriptor: int, contents: bytes, destination: Path) -> None:
    offset = 0
    try:
        while offset < len(contents):
            written = os.write(descriptor, contents[offset:])
            if written <= 0:
                raise OSError(errno.EIO, "checkpoint write made no progress")
            offset += written
        os.fsync(descriptor)
    except OSError as error:
        raise CheckpointError("unable to write or fsync anonymous checkpoint", destination) from error


def _verify_anonymous(descriptor: int, identity: _FileIdentity, contents: bytes, destination: Path) -> None:
    if _regular_identity(descriptor, destination, 0) != identity or _read_bytes(descriptor, len(contents), destination) != contents:
        raise CheckpointError("anonymous checkpoint identity or bytes changed", destination)


def _verify_published(root: int, name: str, identity: _FileIdentity, contents: bytes, destination: Path) -> None:
    try:
        descriptor = os.open(name, _READ_FLAGS, dir_fd=root)
    except OSError as error:
        raise CheckpointError("published checkpoint cannot be verified", destination) from error
    try:
        if _regular_identity(descriptor, destination, 1) != identity or _read_bytes(descriptor, len(contents), destination) != contents:
            raise CheckpointError("published checkpoint identity or bytes changed", destination)
    finally:
        _close(descriptor, "unable to close published checkpoint", destination)


def _read_bytes(descriptor: int, expected_size: int, path: Path) -> bytes:
    try:
        contents = os.pread(descriptor, expected_size + 1, 0)
    except OSError as error:
        raise CheckpointError("unable to read checkpoint", path) from error
    if len(contents) != expected_size:
        raise CheckpointError("checkpoint changed while read", path)
    return contents


def _sync_directory(descriptor: int, directory: Path, destination: Path) -> None:
    try:
        os.fsync(descriptor)
    except OSError as error:
        raise CheckpointError(f"unable to fsync checkpoint directory {directory}", destination) from error


def _close(descriptor: int, rule: str, path: Path) -> None:
    try:
        os.close(descriptor)
    except OSError as error:
        raise CheckpointError(rule, path) from error
