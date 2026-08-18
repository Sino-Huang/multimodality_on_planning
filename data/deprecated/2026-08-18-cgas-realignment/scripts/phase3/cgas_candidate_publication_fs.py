from __future__ import annotations

import errno
import fcntl
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PublicationSpec:
    stage: Path
    destination: Path
    files: tuple[str, ...]
    commit_name: str


def _cleanup_partial(spec: PublicationSpec) -> None:
    destination = spec.destination
    if not destination.exists():
        return
    if destination.is_symlink() or not destination.is_dir() or (destination / spec.commit_name).exists():
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), destination)
    children = tuple(destination.iterdir())
    if any(child.name not in spec.files or child.is_symlink() or not child.is_file() for child in children):
        raise OSError(errno.EEXIST, "partial publication contains unexpected entries", destination)
    for child in children:
        child.unlink()
    destination.rmdir()


def _cleanup_created(spec: PublicationSpec) -> None:
    children = tuple(spec.destination.iterdir())
    if any(child.name not in spec.files or child.is_symlink() or not child.is_file() for child in children):
        raise OSError(errno.EEXIST, "publication contains unexpected entries", spec.destination)
    for child in children:
        child.unlink()
    spec.destination.rmdir()


def publish_files(spec: PublicationSpec) -> None:
    spec.destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    parent = os.open(spec.destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    created = False
    fcntl.flock(parent, fcntl.LOCK_EX)
    try:
        _cleanup_partial(spec)
        os.mkdir(spec.destination.name, mode=0o700, dir_fd=parent)
        created = True
        stage = os.open(spec.stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        destination = os.open(spec.destination.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            os.fsync(stage)
            for name in spec.files:
                if name != spec.commit_name:
                    os.link(name, name, src_dir_fd=stage, dst_dir_fd=destination, follow_symlinks=False)
            os.fsync(destination)
            os.link(
                spec.commit_name,
                spec.commit_name,
                src_dir_fd=stage,
                dst_dir_fd=destination,
                follow_symlinks=False,
            )
            os.fsync(destination)
            os.fsync(parent)
        finally:
            os.close(destination)
            os.close(stage)
    except OSError:
        if created:
            _cleanup_created(spec)
        raise
    finally:
        fcntl.flock(parent, fcntl.LOCK_UN)
        os.close(parent)
