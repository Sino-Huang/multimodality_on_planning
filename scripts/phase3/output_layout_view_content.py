from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Final, Protocol

from .output_layout_inventory_types import OutputLayoutInventoryError
from .output_layout_receipt_io import open_parent_directory
from .output_layout_walk_budget import MAX_TREE_BYTES, MAX_TREE_ENTRIES, TraversalBudget


_READ_CHUNK_BYTES: Final = 1024 * 1024
_MAX_DIRECTORY_ENTRIES: Final = 100_000
_MAX_DIRECTORY_DEPTH: Final = 128
_MAX_TOTAL_ENTRIES: Final = MAX_TREE_ENTRIES
_MAX_TOTAL_BYTES: Final = MAX_TREE_BYTES
_NOFOLLOW: Final = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK: Final = getattr(os, "O_NONBLOCK", 0)


class _Digest(Protocol):
    def update(self, data: bytes, /) -> None: ...


def protected_content_token(path: Path) -> bytes:
    """Return a deterministic no-follow token for a protected file or tree."""
    digest = hashlib.sha256()
    budget = TraversalBudget(_MAX_TOTAL_ENTRIES, _MAX_TOTAL_BYTES)
    try:
        parent_descriptor = open_parent_directory(path.parent)
    except OutputLayoutInventoryError as error:
        raise OSError(f"protected content parent is unavailable: {path}") from error
    try:
        status = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if stat.S_ISREG(status.st_mode):
            digest.update(b"file\0")
            _digest_file(parent_descriptor, path.name, status, digest, budget)
        elif stat.S_ISDIR(status.st_mode):
            digest.update(b"directory\0")
            descriptor = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW, dir_fd=parent_descriptor)
            try:
                _digest_directory(descriptor, Path(), digest, budget, 0)
            finally:
                os.close(descriptor)
        else:
            raise OSError(f"protected content has unsupported entry type: {path}")
    finally:
        os.close(parent_descriptor)
    return digest.digest()


def _digest_directory(descriptor: int, relative: Path, digest: _Digest, budget: TraversalBudget, depth: int) -> None:
    before = os.fstat(descriptor)
    if not stat.S_ISDIR(before.st_mode):
        raise OSError("protected directory changed during tokenization")
    digest.update(b"directory\0")
    digest.update(relative.as_posix().encode("utf-8"))
    digest.update(b"\0")
    for name in _sorted_entries(descriptor, budget):
        child_relative = relative / name
        status = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        digest.update(b"entry\0")
        digest.update(child_relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        if stat.S_ISREG(status.st_mode):
            digest.update(b"file\0")
            _digest_file(descriptor, name, status, digest, budget)
        elif stat.S_ISDIR(status.st_mode):
            if depth >= _MAX_DIRECTORY_DEPTH:
                raise OSError("protected directory is too deep")
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW, dir_fd=descriptor)
            try:
                if not _same_status(status, os.fstat(child)):
                    raise OSError("protected directory changed during tokenization")
                _digest_directory(child, child_relative, digest, budget, depth + 1)
            finally:
                os.close(child)
        elif stat.S_ISLNK(status.st_mode):
            digest.update(b"symlink\0")
            target = os.readlink(name, dir_fd=descriptor)
            digest.update(target.encode("utf-8", "surrogateescape"))
            digest.update(b"\0")
            if not _same_status(status, os.stat(name, dir_fd=descriptor, follow_symlinks=False)):
                raise OSError("protected symlink changed during tokenization")
        else:
            raise OSError("protected content has unsupported entry type")
    if not _same_status(before, os.fstat(descriptor)):
        raise OSError("protected directory changed during tokenization")


def _sorted_entries(descriptor: int, budget: TraversalBudget) -> tuple[str, ...]:
    entries: list[str] = []
    with os.scandir(descriptor) as iterator:
        for entry in iterator:
            budget.account_entry()
            if len(entries) == _MAX_DIRECTORY_ENTRIES:
                raise OSError("protected directory has too many entries")
            entries.append(entry.name)
    return tuple(sorted(entries))


def _digest_file(parent_descriptor: int, name: str, expected: os.stat_result, digest: _Digest, budget: TraversalBudget) -> None:
    descriptor = os.open(name, os.O_RDONLY | _NOFOLLOW | _NONBLOCK, dir_fd=parent_descriptor)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not _same_status(expected, before):
            raise OSError("protected file changed during tokenization")
        bytes_read = 0
        while bytes_read < before.st_size:
            read_size = budget.next_read_size(_READ_CHUNK_BYTES, before.st_size - bytes_read)
            chunk = os.read(descriptor, read_size)
            if not chunk:
                break
            budget.account_bytes(len(chunk))
            digest.update(chunk)
            bytes_read += len(chunk)
        if bytes_read != before.st_size or not _same_status(before, os.fstat(descriptor)) or not _same_status(expected, os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)):
            raise OSError("protected file changed during tokenization")
    finally:
        os.close(descriptor)


def _same_status(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        stat.S_IFMT(left.st_mode),
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        stat.S_IFMT(right.st_mode),
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )
