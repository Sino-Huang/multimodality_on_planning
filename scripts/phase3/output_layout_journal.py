from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Final


_CREATE_FLAGS: Final = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


class OutputLayoutJournalError(RuntimeError):
    def __init__(self, *, rule: str, path: Path) -> None:
        self.rule = rule
        self.path = path
        super().__init__(f"{rule}: {path}")


def journal_path(repository: Path) -> Path:
    return repository / "outputs/deprecated/receipts/output-reorganization-20260727"


def write_record(directory: Path, name: str, record: dict[str, object]) -> Path:
    destination = directory / name
    _require_record_name(name, destination)
    directory.mkdir(parents=True, exist_ok=True)
    contents = _canonical_bytes(record)
    try:
        descriptor = os.open(destination, _CREATE_FLAGS, 0o600)
    except FileExistsError as error:
        raise OutputLayoutJournalError(rule="journal record already exists", path=destination) from error
    except OSError as error:
        raise OutputLayoutJournalError(rule="unable to create journal record", path=destination) from error
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, contents, destination)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(directory)
    return destination


def read_record(path: Path) -> dict[str, object]:
    try:
        status = path.lstat()
        if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600:
            raise OutputLayoutJournalError(rule="journal record must be a mode-0600 regular file", path=path)
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OutputLayoutJournalError(rule="invalid journal record", path=path) from error
    if not isinstance(value, dict):
        raise OutputLayoutJournalError(rule="journal record must be an object", path=path)
    return value


def digest(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                hasher.update(chunk)
                size += len(chunk)
    except OSError as error:
        raise OutputLayoutJournalError(rule="unable to digest file", path=path) from error
    return hasher.hexdigest(), size


def _canonical_bytes(record: dict[str, object]) -> bytes:
    return (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _require_record_name(name: str, path: Path) -> None:
    if not name.endswith(".json") or name != Path(name).name:
        raise OutputLayoutJournalError(rule="journal record name is invalid", path=path)


def _write_all(descriptor: int, contents: bytes, path: Path) -> None:
    offset = 0
    try:
        while offset < len(contents):
            written = os.write(descriptor, contents[offset:])
            if written <= 0:
                raise OSError("journal write made no progress")
            offset += written
    except OSError as error:
        raise OutputLayoutJournalError(rule="unable to write journal record", path=path) from error


def _fsync_directory(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as error:
        raise OutputLayoutJournalError(rule="unable to open journal directory", path=directory) from error
    try:
        os.fsync(descriptor)
    except OSError as error:
        raise OutputLayoutJournalError(rule="unable to fsync journal directory", path=directory) from error
    finally:
        os.close(descriptor)
