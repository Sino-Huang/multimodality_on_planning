from __future__ import annotations

import hashlib
import os
import posixpath
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from .output_layout_inventory_types import OutputLayoutInventoryError, TreeSnapshot
from .output_layout_receipt_io import open_parent_directory
from .output_layout_walk_budget import MAX_TREE_BYTES, MAX_TREE_ENTRIES, TraversalBudget


_CHUNK_BYTES: Final = 1024 * 1024
_MAX_DIRECTORY_ENTRIES: Final = 100_000
_MAX_DIRECTORY_DEPTH: Final = 128
_MAX_TOTAL_ENTRIES: Final = MAX_TREE_ENTRIES
_MAX_TOTAL_BYTES: Final = MAX_TREE_BYTES
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
_open_descriptor = os.open
_close_descriptor = os.close
_read_descriptor = os.read
_fstat_descriptor = os.fstat


@dataclass(frozen=True, slots=True)
class _EntryIdentity:
    device: int
    inode: int
    mode: int


class _Digest(Protocol):
    def update(self, data: bytes, /) -> None: ...


def snapshot_tree(root: Path) -> TreeSnapshot:
    try:
        return _snapshot_tree(root)
    except (OSError, ValueError) as error:
        raise OutputLayoutInventoryError(f"unable to snapshot inventory tree: {root}") from error


def _snapshot_tree(root: Path) -> TreeSnapshot:
    descriptor = _open_root_directory(root)
    try:
        root_stat = _fstat(descriptor, root, "unable to stat inventory root")
        _require_readable(root_stat, root, "inventory root")
        digest = hashlib.sha256()
        counts = [0, 0, 0, 0]
        _snapshot_directory(descriptor, root, ".", digest, counts)
        _require_root_unchanged(root, root_stat)
        return TreeSnapshot(counts[0], counts[1], counts[2], counts[3], digest.hexdigest())
    finally:
        _close_descriptor(descriptor)


def _open_root_directory(root: Path) -> int:
    parent_descriptor: int | None = None
    try:
        if root.parent == Path("."):
            parent_descriptor = _open_descriptor(Path("."), _DIRECTORY_FLAGS)
        else:
            parent_descriptor = open_parent_directory(root.parent)
        return _open_descriptor(root.name, _DIRECTORY_FLAGS, dir_fd=parent_descriptor)
    except OSError as error:
        raise OutputLayoutInventoryError(f"inventory root must be a real readable directory: {root}") from error
    finally:
        if parent_descriptor is not None:
            _close_descriptor(parent_descriptor)


def _snapshot_directory(
    descriptor: int,
    display_path: Path,
    relative: str,
    digest: _Digest,
    counts: list[int],
) -> None:
    budget = TraversalBudget(_MAX_TOTAL_ENTRIES, _MAX_TOTAL_BYTES)
    _snapshot_directory_at_depth(descriptor, display_path, relative, digest, counts, budget, 0)


def _snapshot_directory_at_depth(
    descriptor: int,
    display_path: Path,
    relative: str,
    digest: _Digest,
    counts: list[int],
    budget: TraversalBudget,
    depth: int,
) -> None:
    initial_stat = _fstat(descriptor, display_path, "unable to stat directory")
    _require_readable(initial_stat, display_path, "directory")
    _add_record(digest, b"D", relative)
    counts[1] += 1
    entries = _sorted_entries(descriptor, display_path, budget)
    if not entries:
        _add_record(digest, b"E", relative)
    for name in entries:
        child_path = display_path / name
        child_relative = name if relative == "." else f"{relative}/{name}"
        child_stat = _stat_entry(descriptor, name, child_path)
        _require_readable(child_stat, child_path, "tree entry")
        mode = child_stat.st_mode
        if stat.S_ISREG(mode):
            _add_regular_file(descriptor, name, child_path, child_relative, child_stat, digest, counts, budget)
        elif stat.S_ISDIR(mode):
            if depth >= _MAX_DIRECTORY_DEPTH:
                raise OutputLayoutInventoryError(f"directory too deep: {child_path}")
            child_descriptor = _open_child_directory(descriptor, name, child_path, child_stat)
            try:
                _snapshot_directory_at_depth(child_descriptor, child_path, child_relative, digest, counts, budget, depth + 1)
            finally:
                _close_descriptor(child_descriptor)
        elif stat.S_ISLNK(mode):
            _add_symlink(descriptor, name, child_path, child_relative, relative, child_stat, digest, counts)
        else:
            raise OutputLayoutInventoryError(f"special entry is not allowed: {child_path}")
    final_stat = _fstat(descriptor, display_path, "unable to stat directory")
    if _content_identity(final_stat) != _content_identity(initial_stat) or _sorted_entries(descriptor, display_path, budget) != entries:
        raise OutputLayoutInventoryError(f"directory changed during snapshot: {display_path}")


def _sorted_entries(descriptor: int, display_path: Path, budget: TraversalBudget) -> list[str]:
    try:
        with os.scandir(descriptor) as iterator:
            entries: list[str] = []
            for entry in iterator:
                budget.account_entry()
                if len(entries) == _MAX_DIRECTORY_ENTRIES:
                    raise OutputLayoutInventoryError(f"directory has too many entries: {display_path}")
                entries.append(entry.name)
            return sorted(entries)
    except OSError as error:
        raise OutputLayoutInventoryError(f"unable to list directory: {display_path}") from error


def _stat_entry(parent_descriptor: int, name: str, path: Path) -> os.stat_result:
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except OSError as error:
        raise OutputLayoutInventoryError(f"unable to stat tree entry: {path}") from error


def _fstat(descriptor: int, path: Path, reason: str) -> os.stat_result:
    try:
        return _fstat_descriptor(descriptor)
    except OSError as error:
        raise OutputLayoutInventoryError(f"{reason}: {path}") from error


def _open_child_directory(
    parent_descriptor: int,
    name: str,
    path: Path,
    expected_stat: os.stat_result,
) -> int:
    try:
        descriptor = _open_descriptor(name, _DIRECTORY_FLAGS, dir_fd=parent_descriptor)
    except OSError as error:
        raise OutputLayoutInventoryError(f"directory changed during snapshot: {path}") from error
    try:
        opened_stat = _fstat(descriptor, path, "directory changed during snapshot")
    except OutputLayoutInventoryError as error:
        _close_descriptor(descriptor)
        raise OutputLayoutInventoryError(f"directory changed during snapshot: {path}") from error
    if not stat.S_ISDIR(opened_stat.st_mode) or _identity(opened_stat) != _identity(expected_stat):
        _close_descriptor(descriptor)
        raise OutputLayoutInventoryError(f"directory changed during snapshot: {path}")
    return descriptor


def _add_regular_file(
    parent_descriptor: int,
    name: str,
    path: Path,
    relative: str,
    expected_stat: os.stat_result,
    digest: _Digest,
    counts: list[int],
    budget: TraversalBudget,
) -> None:
    try:
        descriptor = _open_descriptor(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_descriptor,
        )
    except OSError as error:
        raise OutputLayoutInventoryError(f"unable to open regular file: {path}") from error
    try:
        opened_stat = _fstat(descriptor, path, "unable to stat tree entry")
        _require_readable(opened_stat, path, "tree entry")
        if not stat.S_ISREG(opened_stat.st_mode) or _identity(opened_stat) != _identity(expected_stat):
            raise OutputLayoutInventoryError(f"tree entry changed type during snapshot: {path}")
        _add_record_header(digest, b"F", relative, opened_stat.st_size)
        bytes_read = 0
        while bytes_read < opened_stat.st_size:
            read_size = budget.next_read_size(_CHUNK_BYTES, opened_stat.st_size - bytes_read)
            chunk = _read_descriptor(descriptor, read_size)
            if not chunk:
                break
            budget.account_bytes(len(chunk))
            digest.update(chunk)
            bytes_read += len(chunk)
        final_stat = _fstat(descriptor, path, "unable to stat tree entry")
        if bytes_read != opened_stat.st_size or _content_identity(final_stat) != _content_identity(opened_stat):
            raise OutputLayoutInventoryError(f"regular file changed during snapshot: {path}")
        final_name_stat = _stat_entry(parent_descriptor, name, path)
        if not stat.S_ISREG(final_name_stat.st_mode) or _identity(final_name_stat) != _identity(opened_stat) or _content_identity(final_name_stat) != _content_identity(opened_stat):
            raise OutputLayoutInventoryError(f"regular file changed during snapshot: {path}")
    finally:
        _close_descriptor(descriptor)
    counts[0] += 1
    counts[3] += bytes_read


def _add_symlink(
    parent_descriptor: int,
    name: str,
    path: Path,
    relative: str,
    parent_relative: str,
    expected_stat: os.stat_result,
    digest: _Digest,
    counts: list[int],
) -> None:
    try:
        target = os.readlink(name, dir_fd=parent_descriptor)
        final_stat = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except OSError as error:
        raise OutputLayoutInventoryError(f"unable to read symlink: {path}") from error
    if _identity(final_stat) != _identity(expected_stat):
        raise OutputLayoutInventoryError(f"symlink changed during snapshot: {path}")
    if not _is_in_root_symlink_target(parent_relative, target):
        raise OutputLayoutInventoryError(f"out-of-root symlink is not allowed: {path}")
    _add_record(digest, b"L", relative, os.fsencode(target))
    if _identity(_stat_entry(parent_descriptor, name, path)) != _identity(expected_stat):
        raise OutputLayoutInventoryError(f"symlink changed during snapshot: {path}")
    counts[2] += 1


def _identity(entry_stat: os.stat_result) -> _EntryIdentity:
    return _EntryIdentity(entry_stat.st_dev, entry_stat.st_ino, stat.S_IFMT(entry_stat.st_mode))


def _content_identity(entry_stat: os.stat_result) -> tuple[int, int, int, int, int]:
    return (entry_stat.st_dev, entry_stat.st_ino, entry_stat.st_size, entry_stat.st_mtime_ns, entry_stat.st_ctime_ns)


def _require_root_unchanged(root: Path, expected_stat: os.stat_result) -> None:
    try:
        descriptor = _open_root_directory(root)
    except OSError as error:
        raise OutputLayoutInventoryError(f"root changed during snapshot: {root}") from error
    try:
        final_stat = _fstat(descriptor, root, "root changed during snapshot")
    finally:
        _close_descriptor(descriptor)
    if _identity(final_stat) != _identity(expected_stat):
        raise OutputLayoutInventoryError(f"root changed during snapshot: {root}")


def _require_readable(entry_stat: os.stat_result, path: Path, description: str) -> None:
    readable_bits = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
    if not entry_stat.st_mode & readable_bits:
        raise OutputLayoutInventoryError(f"unreadable entry: {description}: {path}")


def _is_in_root_symlink_target(parent_relative: str, target: str) -> bool:
    if target.startswith("/"):
        return False
    base = "" if parent_relative == "." else parent_relative
    normalized = posixpath.normpath(posixpath.join(base, target))
    return normalized != ".." and not normalized.startswith("../")


def _add_record(digest: _Digest, marker: bytes, relative: str, payload: bytes = b"") -> None:
    _add_record_header(digest, marker, relative, len(payload))
    digest.update(payload)


def _add_record_header(digest: _Digest, marker: bytes, relative: str, payload_length: int) -> None:
    name = os.fsencode(relative)
    for field in (marker, name):
        digest.update(len(field).to_bytes(8, "big"))
        digest.update(field)
    digest.update(payload_length.to_bytes(8, "big"))
