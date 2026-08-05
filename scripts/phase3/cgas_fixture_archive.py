from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Sequence

DEFAULT_RELEASE_SHA256: Final = "3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3"
_COPY_CHUNK_BYTES: Final = 1024 * 1024


@dataclass(frozen=True, slots=True)
class FixtureArchiveError(RuntimeError):
    rule: str
    path: Path

    def __str__(self) -> str:
        return f"{self.rule}: {self.path}"


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    status: str
    release_sha256: str
    tree_sha256: str
    file_count: int

    def to_record(self) -> dict[str, str | int]:
        return {
            "file_count": self.file_count,
            "release_sha256": self.release_sha256,
            "status": self.status,
            "tree_sha256": self.tree_sha256,
        }


@dataclass(frozen=True, slots=True)
class _TreeEntry:
    relative_path: str
    kind: str
    size: int
    sha256: str | None


def archive_fixture(source: Path, archive: Path, expected_release_sha256: str) -> ArchiveResult:
    source_absolute = source.absolute()
    archive_absolute = archive.absolute()
    if source_absolute == archive_absolute or source_absolute in archive_absolute.parents:
        raise FixtureArchiveError("fixture_archive_path_overlap", archive)
    source_entries = _inventory(source)
    release_sha256 = _release_digest(source)
    if release_sha256 != expected_release_sha256:
        raise FixtureArchiveError("trace_v1_immutable", source / "release_manifest.json")
    tree_sha256 = _tree_digest(source_entries)
    file_count = sum(entry.kind == "file" for entry in source_entries)
    if archive.exists() or archive.is_symlink():
        archive_entries = _inventory(archive)
        if archive_entries != source_entries:
            raise FixtureArchiveError("fixture_archive_mismatch", archive)
        return ArchiveResult("already_archived", release_sha256, tree_sha256, file_count)
    archive.parent.mkdir(parents=True, exist_ok=True)
    candidate = Path(tempfile.mkdtemp(prefix=f".{archive.name}-", dir=archive.parent))
    try:
        _copy_tree(source, candidate, source_entries)
        if _inventory(candidate) != source_entries:
            raise FixtureArchiveError("fixture_archive_copy_mismatch", candidate)
        os.rename(candidate, archive)
        _fsync_directory(archive.parent)
    except FixtureArchiveError:
        raise
    except OSError as error:
        raise FixtureArchiveError("fixture_archive_publication_failed", archive) from error
    finally:
        if candidate.exists():
            shutil.rmtree(candidate)
    return ArchiveResult("archived", release_sha256, tree_sha256, file_count)


def _inventory(root: Path) -> tuple[_TreeEntry, ...]:
    if root.is_symlink():
        raise FixtureArchiveError("fixture_archive_symlink", root)
    if not root.is_dir():
        raise FixtureArchiveError("fixture_archive_root_not_directory", root)
    entries: list[_TreeEntry] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        status = path.lstat()
        if stat.S_ISLNK(status.st_mode):
            raise FixtureArchiveError("fixture_archive_symlink", path)
        if stat.S_ISDIR(status.st_mode):
            entries.append(_TreeEntry(relative, "directory", 0, None))
        elif stat.S_ISREG(status.st_mode):
            entries.append(_TreeEntry(relative, "file", status.st_size, _file_digest(path)))
        else:
            raise FixtureArchiveError("fixture_archive_non_regular_leaf", path)
    return tuple(entries)


def _copy_tree(source: Path, candidate: Path, entries: tuple[_TreeEntry, ...]) -> None:
    for entry in entries:
        destination = candidate / entry.relative_path
        if entry.kind == "directory":
            destination.mkdir()
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_descriptor = os.open(source / entry.relative_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        destination_descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
            0o644,
        )
        try:
            while chunk := os.read(source_descriptor, _COPY_CHUNK_BYTES):
                _write_all(destination_descriptor, chunk, destination)
            os.fsync(destination_descriptor)
        finally:
            os.close(destination_descriptor)
            os.close(source_descriptor)
    directories = sorted((path for path in candidate.rglob("*") if path.is_dir()), reverse=True)
    for directory in (*directories, candidate):
        _fsync_directory(directory)


def _write_all(descriptor: int, contents: bytes, path: Path) -> None:
    offset = 0
    while offset < len(contents):
        written = os.write(descriptor, contents[offset:])
        if written <= 0:
            raise FixtureArchiveError("fixture_archive_write_stalled", path)
        offset += written


def _release_digest(root: Path) -> str:
    release = root / "release_manifest.json"
    if not release.is_file() or release.is_symlink():
        raise FixtureArchiveError("trace_v1_release_manifest_missing", release)
    return _file_digest(release)


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        while chunk := os.read(descriptor, _COPY_CHUNK_BYTES):
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _tree_digest(entries: tuple[_TreeEntry, ...]) -> str:
    records = [
        {
            "kind": entry.kind,
            "path": entry.relative_path,
            "sha256": entry.sha256,
            "size": entry.size,
        }
        for entry in entries
    ]
    payload = json.dumps(records, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Archive the verified CGAS fixture release without changing its source."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--expected-release-sha256", default=DEFAULT_RELEASE_SHA256)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    try:
        result = archive_fixture(parsed.source, parsed.archive, parsed.expected_release_sha256)
    except (FixtureArchiveError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result.to_record(), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
