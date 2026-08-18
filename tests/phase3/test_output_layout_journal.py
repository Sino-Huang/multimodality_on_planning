from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_receipt_fs, output_layout_receipt_io
from scripts.phase3.output_layout_journal import OutputLayoutJournalError, read_record


def _write_record(path: Path, contents: bytes = b'{"state":"original"}\n') -> None:
    path.write_bytes(contents)
    path.chmod(0o600)


def test_read_record_rejects_mode_0644(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    _write_record(path)
    path.chmod(0o644)

    with pytest.raises(OutputLayoutJournalError, match="mode-0600 regular file"):
        read_record(path)


def test_read_record_rejects_static_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    _write_record(target)
    path = tmp_path / "record.json"
    path.symlink_to(target)

    with pytest.raises(OutputLayoutJournalError, match="mode-0600 regular file"):
        read_record(path)


def test_read_record_rejects_fifo_promptly(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    os.mkfifo(path, mode=0o600)

    with pytest.raises(OutputLayoutJournalError, match="mode-0600 regular file"):
        read_record(path)


def test_read_record_rejects_fifo_replacement_before_nonblocking_leaf_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "record.json"
    _write_record(path)
    original_open = output_layout_receipt_io._open_descriptor
    replaced = False

    def replace_leaf_with_fifo(
        name: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if os.fsdecode(name) == path.name and not replaced:
            replaced = True
            path.unlink()
            os.mkfifo(path, mode=0o600)
            assert flags & os.O_NOFOLLOW
            assert flags & os.O_NONBLOCK
        return original_open(name, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(output_layout_receipt_io, "_open_descriptor", replace_leaf_with_fifo)

    with pytest.raises(OutputLayoutJournalError, match="mode-0600 regular file"):
        read_record(path)

    assert replaced


def test_read_record_rejects_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    _write_record(path, b'{"state":"\xff"}\n')

    with pytest.raises(OutputLayoutJournalError, match="invalid journal record"):
        read_record(path)


def test_read_record_rejects_truncated_json(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    _write_record(path, b'{"state":')

    with pytest.raises(OutputLayoutJournalError, match="invalid journal record"):
        read_record(path)


def test_read_record_rejects_nested_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    _write_record(path, b'{"nested":{"state":"first","state":"second"}}\n')

    with pytest.raises(OutputLayoutJournalError, match="duplicate journal JSON key"):
        read_record(path)


@pytest.mark.parametrize("contents", (b"[]\n", b'"value"\n', b"null\n"))
def test_read_record_rejects_non_object_root(tmp_path: Path, contents: bytes) -> None:
    path = tmp_path / "record.json"
    _write_record(path, contents)

    with pytest.raises(OutputLayoutJournalError, match="journal record must be an object"):
        read_record(path)


def test_read_record_uses_descriptor_after_leaf_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "record.json"
    _write_record(path)
    replacement = b'{"state":"replacement"}\n'
    original_open = output_layout_receipt_io._open_descriptor
    replaced = False

    def replace_leaf_after_open(
        name: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        descriptor = original_open(name, flags, mode, dir_fd=dir_fd)
        if os.fsdecode(name) == path.name and not replaced:
            replaced = True
            path.unlink()
            _write_record(path, replacement)
        return descriptor

    monkeypatch.setattr(output_layout_receipt_io, "_open_descriptor", replace_leaf_after_open)

    assert read_record(path) == {"state": "original"}
    assert replaced
    assert path.read_bytes() == replacement


def test_read_record_rejects_content_mutation_during_descriptor_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "record.json"
    _write_record(path)
    original_read = output_layout_receipt_fs._read_descriptor_bytes
    mutated = False

    def read_then_mutate(descriptor: int) -> bytes:
        nonlocal mutated
        contents = original_read(descriptor)
        if not mutated:
            mutated = True
            path.write_bytes(b'{"state":"mutated-with-a-different-size"}\n')
        return contents

    monkeypatch.setattr(output_layout_receipt_fs, "_read_descriptor_bytes", read_then_mutate)

    with pytest.raises(OutputLayoutJournalError, match="invalid journal record"):
        read_record(path)

    assert mutated
