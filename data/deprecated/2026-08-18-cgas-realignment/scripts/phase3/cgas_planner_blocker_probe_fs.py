from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal


RUN_DIRECTORY: Final = re.compile(r"cgas-planner-blocker-investigation-[a-z0-9][a-z0-9-]{7,}")
ALTERNATIVE_RUN_DIRECTORY: Final = re.compile(r"cgas-planner-alternative-profile-[a-z0-9][a-z0-9-]{7,}")
OutputNamespace = Literal["alternative", "blocker"]


@dataclass(frozen=True, slots=True)
class ProbeOutput:
    output: Path
    directory_descriptor: int

    def close(self) -> None:
        os.close(self.directory_descriptor)


class ProbeFilesystemError(RuntimeError):
    pass


def repository_file(root: Path, raw_path: str | Path) -> Path:
    root = root.resolve(strict=True)
    path = Path(raw_path)
    relative = _relative_to_root(root, path) if path.is_absolute() else path
    _reject_traversal(relative)
    candidate = root.joinpath(*relative.parts)
    _reject_symlink_components(root, relative)
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ProbeFilesystemError("source_path_outside_repository") from error
    if not resolved.is_file():
        raise ProbeFilesystemError("source_path_unavailable")
    return resolved


def open_probe_output(root: Path, raw_output: Path, namespace: OutputNamespace = "blocker") -> ProbeOutput:
    root = root.resolve(strict=True)
    tmp = root / "tmp"
    if not tmp.is_dir():
        raise ProbeFilesystemError("unsafe_output_path")
    relative = _relative_to_root(tmp, raw_output if raw_output.is_absolute() else root / raw_output)
    _reject_traversal(relative)
    if len(relative.parts) != 2 or relative.parts[1] != "probe.json" or not _directory_pattern(namespace).fullmatch(relative.parts[0]):
        raise ProbeFilesystemError("unsafe_output_path")
    _reject_symlink_components(root, Path("tmp"))
    checked_tmp = os.stat(tmp, follow_symlinks=False)
    tmp_descriptor = os.open(tmp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        opened_tmp = os.fstat(tmp_descriptor)
        if opened_tmp.st_dev != checked_tmp.st_dev or opened_tmp.st_ino != checked_tmp.st_ino:
            raise ProbeFilesystemError("unsafe_output_path")
        return _create_output(tmp, relative.parts[0], tmp_descriptor)
    finally:
        os.close(tmp_descriptor)


def write_new(directory_descriptor: int, name: str, contents: bytes) -> None:
    descriptor = os.open(name, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600, dir_fd=directory_descriptor)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(contents)


def _directory_pattern(namespace: OutputNamespace) -> re.Pattern[str]:
    match namespace:
        case "alternative":
            return ALTERNATIVE_RUN_DIRECTORY
        case "blocker":
            return RUN_DIRECTORY


def _create_output(tmp: Path, name: str, tmp_descriptor: int) -> ProbeOutput:
    try:
        os.mkdir(name, mode=0o700, dir_fd=tmp_descriptor)
    except FileExistsError as error:
        raise ProbeFilesystemError("output_target_exists") from error
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=tmp_descriptor)
    except OSError as error:
        raise ProbeFilesystemError("unsafe_output_path") from error
    created = os.stat(name, dir_fd=tmp_descriptor, follow_symlinks=False)
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode) or opened.st_dev != created.st_dev or opened.st_ino != created.st_ino or opened.st_uid != os.geteuid() or stat.S_IMODE(opened.st_mode) & 0o077:
        os.close(descriptor)
        raise ProbeFilesystemError("unsafe_output_path")
    return ProbeOutput(tmp / name / "probe.json", descriptor)


def _relative_to_root(root: Path, candidate: Path) -> Path:
    try:
        return candidate.relative_to(root)
    except ValueError as error:
        raise ProbeFilesystemError("source_path_outside_repository") from error


def _reject_traversal(path: Path) -> None:
    if any(part == ".." for part in path.parts):
        raise ProbeFilesystemError("source_path_outside_repository")


def _reject_symlink_components(root: Path, relative: Path) -> None:
    current = root
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise ProbeFilesystemError("source_path_unavailable")
