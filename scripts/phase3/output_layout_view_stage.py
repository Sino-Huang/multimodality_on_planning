from __future__ import annotations

import os
import secrets
import stat
from dataclasses import dataclass, replace
from pathlib import Path
from collections.abc import Callable
from typing import Final

from . import output_layout_view_fs
from . import output_layout_view_walk
from .output_layout_view_types import OutputLayoutViewError, OutputLayoutViewLink


_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
_PRIVATE_MODE: Final = 0o700
_MAX_DIRECTORY_ENTRIES: Final = 100_000
_MAX_DIRECTORY_DEPTH: Final = 128


@dataclass(frozen=True, slots=True)
class StageIdentity:
    device: int
    inode: int
    file_type: int

    def matches(self, status: os.stat_result) -> bool:
        return (self.device, self.inode, self.file_type) == (
            status.st_dev,
            status.st_ino,
            stat.S_IFMT(status.st_mode),
        )


@dataclass(frozen=True, slots=True)
class OwnedStageEntry:
    relative: Path
    identity: StageIdentity


@dataclass(frozen=True, slots=True)
class PrivateStage:
    parent_descriptor: int
    name: str
    descriptor: int
    identity: StageIdentity
    suffix: Path
    entries: tuple[OwnedStageEntry, ...]


@dataclass(frozen=True, slots=True)
class PublishedStage:
    parent_descriptor: int
    name: str
    descriptor: int
    identity: StageIdentity
    suffix: Path


class StageConstructionError(OSError):
    def __init__(self, stage: PrivateStage, error: OSError | OutputLayoutViewError) -> None:
        self.stage: PrivateStage = stage
        super().__init__(str(error))


def locate_missing_ancestor(outputs_descriptor: int, root: Path) -> tuple[int, Path]:
    """Return a pinned parent descriptor and the suffix rooted at its first missing child."""
    descriptor = os.dup(outputs_descriptor)
    parts = root.parts
    for index, part in enumerate(parts):
        try:
            status = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return descriptor, Path(*parts[index:])
        if not stat.S_ISDIR(status.st_mode):
            os.close(descriptor)
            raise OSError("canonical view ancestor is not a real directory")
        try:
            next_descriptor = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
        except OSError:
            os.close(descriptor)
            raise
        os.close(descriptor)
        descriptor = next_descriptor
    os.close(descriptor)
    raise FileExistsError("canonical view root already exists")


def create_private_stage(parent_descriptor: int, suffix: Path) -> PrivateStage:
    """Create a private sibling whose directory descriptor remains pinned."""
    for _attempt in range(32):
        name = f".phase3-view-stage-{secrets.token_hex(16)}"
        try:
            os.mkdir(name, _PRIVATE_MODE, dir_fd=parent_descriptor)
        except FileExistsError:
            continue
        identity = _identity(os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False))
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_descriptor)
        if not identity.matches(os.fstat(descriptor)):
            os.close(descriptor)
            raise OSError("private stage changed during creation")
        return PrivateStage(parent_descriptor, name, descriptor, identity, suffix, ())
    raise OSError("unable to allocate a private view stage")


def create_tree(stage: PrivateStage, links: tuple[OutputLayoutViewLink, ...], guard: Callable[[], None]) -> PrivateStage:
    """Construct the exact contract tree under the private sibling."""
    root = _stage_root(stage.suffix)
    try:
        for directory in _directories(root, links):
            guard()
            _mkdir(stage.descriptor, directory)
            stage = replace(stage, entries=(*stage.entries, _owned_entry(stage.descriptor, directory)))
            guard()
        for link in links:
            guard()
            relative = root / link.location
            _symlink(stage.descriptor, relative, link.readlink_target)
            stage = replace(stage, entries=(*stage.entries, _owned_entry(stage.descriptor, relative)))
            guard()
    except (OSError, OutputLayoutViewError) as error:
        raise StageConstructionError(stage, error) from error
    return stage


def validate_tree(stage: PrivateStage | PublishedStage, links: tuple[OutputLayoutViewLink, ...]) -> None:
    """Reject extras, wrong types, or wrong target text before publication."""
    if not stage.identity.matches(os.fstat(stage.descriptor)):
        raise OSError("held stage descriptor identity differs from the stage")
    root = _stage_root(stage.suffix)
    expected_directories = set(_directories(root, links))
    expected_links = {root / link.location: link.readlink_target for link in links}
    actual_directories: set[Path] = set()
    actual_links: dict[Path, str] = {}
    _scan(stage.descriptor, Path(), actual_directories, actual_links)
    if actual_directories != expected_directories or actual_links != expected_links:
        raise OSError("private stage differs from the exact view contract")


def open_existing(outputs_descriptor: int, root: Path) -> PublishedStage:
    """Open an existing canonical view and retain its immediate parent descriptor."""
    parent_descriptor = os.dup(outputs_descriptor)
    try:
        for part in root.parts[:-1]:
            next_descriptor = os.open(part, _DIRECTORY_FLAGS, dir_fd=parent_descriptor)
            os.close(parent_descriptor)
            parent_descriptor = next_descriptor
        name = root.parts[-1]
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_descriptor)
        try:
            stage = PublishedStage(parent_descriptor, name, descriptor, _identity(os.fstat(descriptor)), Path())
            validate_published_pathname(stage)
            return stage
        except OSError:
            os.close(descriptor)
            raise
    except OSError:
        os.close(parent_descriptor)
        raise


def fsync_tree(stage: PrivateStage) -> None:
    _fsync_directory(stage.descriptor)


def publish(stage: PrivateStage, final_name: str) -> PublishedStage:
    """Publish a pinned private stage and return a pinned final descriptor."""
    _validate_private_stage_descriptor(stage)
    if not stage.identity.matches(os.stat(stage.name, dir_fd=stage.parent_descriptor, follow_symlinks=False)):
        raise OSError("private stage was replaced before publication")
    output_layout_view_fs.rename_noreplace(stage.parent_descriptor, stage.name, final_name)
    descriptor = os.open(final_name, _DIRECTORY_FLAGS, dir_fd=stage.parent_descriptor)
    try:
        published = PublishedStage(stage.parent_descriptor, final_name, descriptor, stage.identity, stage.suffix)
        _validate_private_stage_descriptor(stage)
        _validate_published_descriptor(published)
        return published
    except OSError:
        os.close(descriptor)
        raise


def cleanup(stage: PrivateStage) -> None:
    """Durably retain a failed private stage without mutating its pathname."""
    _validate_private_stage_descriptor(stage)
    try:
        named_status = os.stat(stage.name, dir_fd=stage.parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        os.fsync(stage.parent_descriptor)
        return
    if not stage.identity.matches(named_status):
        raise OSError("private stage was replaced before cleanup")
    os.fsync(stage.parent_descriptor)


def validate_published_pathname(stage: PublishedStage) -> None:
    """Require the public pathname to remain bound to the held descriptor identity."""
    _validate_published_descriptor(stage)
    final_status = os.stat(stage.name, dir_fd=stage.parent_descriptor, follow_symlinks=False)
    if not stage.identity.matches(final_status):
        raise OSError("published view pathname identity differs from the held descriptor")


def fsync_published_parent(stage: PublishedStage) -> None:
    """Durably record the already-validated publication rename."""
    _validate_published_descriptor(stage)
    os.fsync(stage.parent_descriptor)


def _validate_private_stage_descriptor(stage: PrivateStage) -> None:
    if not stage.identity.matches(os.fstat(stage.descriptor)):
        raise OSError("private stage was replaced before cleanup")


def _validate_published_descriptor(stage: PublishedStage) -> None:
    if not stage.identity.matches(os.fstat(stage.descriptor)):
        raise OSError("published view descriptor identity differs from the private stage")


def _directories(suffix: Path, links: tuple[OutputLayoutViewLink, ...]) -> tuple[Path, ...]:
    directories: set[Path] = set()
    for link in links:
        current = suffix / link.location.parent
        while current != Path():
            directories.add(current)
            current = current.parent
    return tuple(sorted(directories, key=lambda path: (len(path.parts), path.as_posix())))


def _stage_root(suffix: Path) -> Path:
    return Path(*suffix.parts[1:])


def _mkdir(root_descriptor: int, relative: Path) -> None:
    parent_descriptor, name = _open_parent(root_descriptor, relative)
    try:
        os.mkdir(name, _PRIVATE_MODE, dir_fd=parent_descriptor)
    finally:
        os.close(parent_descriptor)


def _symlink(root_descriptor: int, relative: Path, target: str) -> None:
    parent_descriptor, name = _open_parent(root_descriptor, relative)
    try:
        os.symlink(target, name, dir_fd=parent_descriptor)
    finally:
        os.close(parent_descriptor)


def _open_parent(root_descriptor: int, relative: Path) -> tuple[int, str]:
    descriptor = os.dup(root_descriptor)
    try:
        for part in relative.parts[:-1]:
            next_descriptor = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, relative.name
    except OSError:
        os.close(descriptor)
        raise


def _owned_entry(root_descriptor: int, relative: Path) -> OwnedStageEntry:
    parent_descriptor, name = _open_parent(root_descriptor, relative)
    try:
        status = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        return OwnedStageEntry(relative, _identity(status))
    finally:
        os.close(parent_descriptor)


def _scan(descriptor: int, relative: Path, directories: set[Path], links: dict[Path, str]) -> None:
    output_layout_view_walk.scan(descriptor, relative, directories, links, _walk_limits())


def _fsync_directory(descriptor: int) -> None:
    output_layout_view_walk.fsync_tree(descriptor, _walk_limits())


def _walk_limits() -> output_layout_view_walk.WalkLimits:
    return output_layout_view_walk.WalkLimits(_MAX_DIRECTORY_DEPTH, _MAX_DIRECTORY_ENTRIES)


def _identity(status: os.stat_result) -> StageIdentity:
    return StageIdentity(status.st_dev, status.st_ino, stat.S_IFMT(status.st_mode))
