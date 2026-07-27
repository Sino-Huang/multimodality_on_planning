from __future__ import annotations

import errno
import os
import stat
from pathlib import Path
from typing import Final


_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW


class OutputLayoutRenameError(RuntimeError):
    def __init__(self, *, rule: str, source: Path, destination: Path) -> None:
        self.rule = rule
        self.source = source
        self.destination = destination
        super().__init__(f"{rule}: {source} -> {destination}")


def rename_noreplace(source: Path, destination: Path) -> None:
    source_parent = _open_real_parent(source.parent, source, destination)
    destination_parent = _open_real_parent(destination.parent, source, destination)
    try:
        source_parent_status = os.fstat(source_parent)
        destination_parent_status = os.fstat(destination_parent)
        source_status = _source_directory_status(source_parent, source.name, source, destination)
        if source_status.st_dev != source_parent_status.st_dev or source_parent_status.st_dev != destination_parent_status.st_dev:
            raise OutputLayoutRenameError(rule="cross-filesystem rename is forbidden", source=source, destination=destination)
        _assert_destination_absent(destination_parent, destination.name, source, destination)
        _assert_destination_absent(destination_parent, destination.name, source, destination)
        try:
            os.rename(source.name, destination.name, src_dir_fd=source_parent, dst_dir_fd=destination_parent)
        except OSError as error:
            rule = "destination collision prevents no-clobber rename" if error.errno in (errno.EEXIST, errno.ENOTEMPTY) else "ordinary rename failed"
            raise OutputLayoutRenameError(rule=rule, source=source, destination=destination) from error
        try:
            os.fsync(source_parent)
            if source_parent != destination_parent:
                os.fsync(destination_parent)
        except OSError as error:
            raise OutputLayoutRenameError(rule="ordinary rename failed during parent fsync", source=source, destination=destination) from error
    finally:
        os.close(destination_parent)
        os.close(source_parent)


def prepare_destination_parent(source: Path, destination: Path) -> None:
    if not destination.parent.is_absolute():
        raise OutputLayoutRenameError(rule="rename parent must be absolute", source=source, destination=destination)
    descriptor = os.open("/", _DIRECTORY_FLAGS)
    try:
        for part in destination.parent.parts[1:]:
            try:
                next_descriptor = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except FileNotFoundError:
                try:
                    os.mkdir(part, dir_fd=descriptor)
                except FileExistsError:
                    next_descriptor = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
                else:
                    next_descriptor = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
    except OSError as error:
        os.close(descriptor)
        raise OutputLayoutRenameError(rule="destination parent cannot be safely created", source=source, destination=destination) from error
    os.close(descriptor)


def prepare_real_directory(path: Path) -> None:
    _prepare_directory(path, path, path)


def validate_real_path(path: Path, *, allow_missing: bool) -> None:
    if not path.is_absolute():
        raise OutputLayoutRenameError(rule="path must be absolute", source=path, destination=path)
    descriptor = os.open("/", _DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            try:
                next_descriptor = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except FileNotFoundError:
                if allow_missing:
                    return
                raise OutputLayoutRenameError(rule="directory is missing", source=path, destination=path) from None
            os.close(descriptor)
            descriptor = next_descriptor
    except OSError as error:
        raise OutputLayoutRenameError(rule="directory path cannot be opened without symlink following", source=path, destination=path) from error
    finally:
        os.close(descriptor)


def _prepare_directory(path: Path, source: Path, destination: Path) -> None:
    if not path.is_absolute():
        raise OutputLayoutRenameError(rule="rename parent must be absolute", source=source, destination=destination)
    descriptor = os.open("/", _DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            try:
                next_descriptor = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except FileNotFoundError:
                try:
                    os.mkdir(part, dir_fd=descriptor)
                except FileExistsError:
                    next_descriptor = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
                else:
                    next_descriptor = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        os.fsync(descriptor)
    except OSError as error:
        raise OutputLayoutRenameError(rule="directory cannot be safely created", source=source, destination=destination) from error
    finally:
        os.close(descriptor)


def _open_real_parent(parent: Path, source: Path, destination: Path) -> int:
    if not parent.is_absolute():
        raise OutputLayoutRenameError(rule="rename parent must be absolute", source=source, destination=destination)
    descriptor = os.open("/", _DIRECTORY_FLAGS)
    try:
        for part in parent.parts[1:]:
            next_descriptor = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        status = os.fstat(descriptor)
        if not stat.S_ISDIR(status.st_mode):
            raise OutputLayoutRenameError(rule="rename parent must be a real directory", source=source, destination=destination)
        return descriptor
    except OSError as error:
        os.close(descriptor)
        raise OutputLayoutRenameError(rule="rename parent cannot be opened without symlink following", source=source, destination=destination) from error


def _source_directory_status(parent_descriptor: int, name: str, source: Path, destination: Path) -> os.stat_result:
    try:
        source_status = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except OSError as error:
        raise OutputLayoutRenameError(rule="source must be a real directory", source=source, destination=destination) from error
    if not stat.S_ISDIR(source_status.st_mode):
        raise OutputLayoutRenameError(rule="source must be a real directory", source=source, destination=destination)
    return source_status


def _assert_destination_absent(parent_descriptor: int, name: str, source: Path, destination: Path) -> None:
    try:
        os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as error:
        raise OutputLayoutRenameError(rule="destination cannot be safely inspected", source=source, destination=destination) from error
    raise OutputLayoutRenameError(rule="destination collision prevents no-clobber rename", source=source, destination=destination)
