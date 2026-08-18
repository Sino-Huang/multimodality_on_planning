from __future__ import annotations

import errno
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_WRITE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


@dataclass(frozen=True, slots=True)
class CandidateFilesystemError(RuntimeError):
    rule: str
    path: Path

    def __str__(self) -> str:
        return f"candidate {self.rule}: {self.path}"


@dataclass(frozen=True, slots=True)
class CandidateFile:
    name: str
    contents: bytes


def create_candidate_root(repository_root: Path, checkpoint_root: Path, private_root: Path) -> Path:
    root = repository_root.resolve(strict=True)
    checkpoint = checkpoint_root.resolve(strict=True)
    private = _private_root(root, checkpoint, private_root)
    candidate = private / f"cgas-characterization-candidate-{secrets.token_hex(16)}"
    try:
        candidate.mkdir(mode=0o700)
        candidate.chmod(0o700)
    except OSError as error:
        raise CandidateFilesystemError("unable to create private root", candidate) from error
    _fsync_directory(private)
    return candidate


def write_candidate_files(candidate: Path, files: tuple[CandidateFile, ...]) -> None:
    descriptor = _candidate_directory(candidate)
    try:
        for file in files:
            _write_file(descriptor, candidate, file)
        _fsync_descriptor(descriptor, candidate)
    finally:
        _close(descriptor, candidate)


def _private_root(repository: Path, checkpoint: Path, supplied: Path) -> Path:
    if supplied.is_symlink():
        raise CandidateFilesystemError("private root must not be a symlink", supplied)
    try:
        private = supplied.resolve(strict=True)
        private.relative_to(repository / "tmp")
    except OSError as error:
        raise CandidateFilesystemError("private root must resolve under repository tmp", supplied) from error
    except ValueError as error:
        raise CandidateFilesystemError("private root must resolve under repository tmp", supplied) from error
    if _contains(checkpoint, private) or _contains(private, checkpoint):
        raise CandidateFilesystemError("private root must be external to checkpoint root", private)
    descriptor = _candidate_directory(private)
    try:
        status = os.fstat(descriptor)
        if stat.S_IMODE(status.st_mode) != 0o700 or status.st_uid != os.geteuid():
            raise CandidateFilesystemError("private root must be owned mode 0700", private)
    finally:
        _close(descriptor, private)
    return private


def _candidate_directory(path: Path) -> int:
    try:
        descriptor = os.open(path, _DIRECTORY_FLAGS)
    except OSError as error:
        raise CandidateFilesystemError("root must be a real directory", path) from error
    status = os.fstat(descriptor)
    if not stat.S_ISDIR(status.st_mode):
        _close(descriptor, path)
        raise CandidateFilesystemError("root must be a real directory", path)
    return descriptor


def _write_file(directory: int, candidate: Path, file: CandidateFile) -> None:
    path = candidate / file.name
    try:
        descriptor = os.open(file.name, _WRITE_FLAGS, 0o600, dir_fd=directory)
        os.fchmod(descriptor, 0o600)
    except OSError as error:
        raise CandidateFilesystemError("unable to create artifact", path) from error
    try:
        offset = 0
        while offset < len(file.contents):
            written = os.write(descriptor, file.contents[offset:])
            if written <= 0:
                raise OSError(errno.EIO, "candidate write made no progress")
            offset += written
        os.fsync(descriptor)
    except OSError as error:
        raise CandidateFilesystemError("unable to write or fsync artifact", path) from error
    finally:
        _close(descriptor, path)


def _fsync_directory(path: Path) -> None:
    descriptor = _candidate_directory(path)
    try:
        _fsync_descriptor(descriptor, path)
    finally:
        _close(descriptor, path)


def _fsync_descriptor(descriptor: int, path: Path) -> None:
    try:
        os.fsync(descriptor)
    except OSError as error:
        raise CandidateFilesystemError("unable to fsync directory", path) from error


def _close(descriptor: int, path: Path) -> None:
    try:
        os.close(descriptor)
    except OSError as error:
        raise CandidateFilesystemError("unable to close descriptor", path) from error


def _contains(ancestor: Path, descendant: Path) -> bool:
    try:
        descendant.relative_to(ancestor)
    except ValueError:
        return False
    return True
