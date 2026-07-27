from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WalkLimits:
    depth: int
    entries: int


def scan(
    descriptor: int,
    relative: Path,
    directories: set[Path],
    links: dict[Path, str],
    limits: WalkLimits,
) -> None:
    _scan_directory(descriptor, relative, directories, links, limits, [0], 0)


def fsync_tree(descriptor: int, limits: WalkLimits) -> None:
    _fsync_directory(descriptor, limits, [0], 0)


def _scan_directory(
    descriptor: int,
    relative: Path,
    directories: set[Path],
    links: dict[Path, str],
    limits: WalkLimits,
    budget: list[int],
    depth: int,
) -> None:
    for name in _names(descriptor, limits, budget):
        path = relative / name
        status = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISDIR(status.st_mode):
            if depth >= limits.depth:
                raise OSError("private stage directory is too deep")
            directories.add(path)
            child = os.open(name, _DIRECTORY_FLAGS, dir_fd=descriptor)
            try:
                if not _same_identity(status, os.fstat(child)):
                    raise OSError("private stage directory changed while scanning")
                _scan_directory(child, path, directories, links, limits, budget, depth + 1)
            finally:
                os.close(child)
        elif stat.S_ISLNK(status.st_mode):
            links[path] = os.readlink(name, dir_fd=descriptor)
        else:
            raise OSError("private stage contains an unsupported entry")


def _fsync_directory(descriptor: int, limits: WalkLimits, budget: list[int], depth: int) -> None:
    for name in _names(descriptor, limits, budget):
        status = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISDIR(status.st_mode):
            if depth >= limits.depth:
                raise OSError("private stage directory is too deep")
            child = os.open(name, _DIRECTORY_FLAGS, dir_fd=descriptor)
            try:
                if not _same_identity(status, os.fstat(child)):
                    raise OSError("private stage directory changed while syncing")
                _fsync_directory(child, limits, budget, depth + 1)
            finally:
                os.close(child)
    os.fsync(descriptor)


def _names(descriptor: int, limits: WalkLimits, budget: list[int]):
    with os.scandir(descriptor) as iterator:
        for entry in iterator:
            budget[0] += 1
            if budget[0] > limits.entries:
                raise OSError("private stage has too many entries")
            yield entry.name


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino, stat.S_IFMT(left.st_mode)) == (
        right.st_dev,
        right.st_ino,
        stat.S_IFMT(right.st_mode),
    )


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
