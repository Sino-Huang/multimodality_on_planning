from __future__ import annotations

import errno
import importlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_rename
from scripts.phase3.output_layout_rename import rename_noreplace


def test_rename_noreplace_moves_same_device_directory(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "payload.txt").write_text("payload\n", encoding="utf-8")

    rename_noreplace(source, destination)

    assert not source.exists()
    assert (destination / "payload.txt").read_text(encoding="utf-8") == "payload\n"


def test_rename_noreplace_uses_ordinary_rename_when_renameat2_rejects_gpfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "payload.txt").write_text("payload\n", encoding="utf-8")

    def reject_renameat2(*_arguments: int | str | Path) -> None:
        raise output_layout_rename.OutputLayoutRenameError(
            rule=os.strerror(errno.EINVAL), source=source, destination=destination
        )

    monkeypatch.setattr(output_layout_rename, "_renameat2", reject_renameat2, raising=False)

    rename_noreplace(source, destination)

    assert not source.exists()
    assert (destination / "payload.txt").read_text(encoding="utf-8") == "payload\n"


def test_rename_noreplace_rejects_destination_claimed_before_final_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "payload.txt").write_text("source\n", encoding="utf-8")
    checks = 0
    original_check = output_layout_rename._assert_destination_absent

    def claim_destination_before_final_check(*arguments: int | str | Path) -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            destination.mkdir()
            (destination / "racer.txt").write_text("racer\n", encoding="utf-8")
        original_check(*arguments)

    monkeypatch.setattr(output_layout_rename, "_assert_destination_absent", claim_destination_before_final_check)

    with pytest.raises(output_layout_rename.OutputLayoutRenameError, match="destination collision"):
        rename_noreplace(source, destination)

    assert (source / "payload.txt").read_text(encoding="utf-8") == "source\n"
    assert (destination / "racer.txt").read_text(encoding="utf-8") == "racer\n"


def test_rename_noreplace_rejects_cross_device_parents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_parent = tmp_path / "source-parent"
    destination_parent = tmp_path / "destination-parent"
    source_parent.mkdir()
    destination_parent.mkdir()
    source = source_parent / "source"
    destination = destination_parent / "destination"
    source.mkdir()
    original_fstat = output_layout_rename.os.fstat
    parent_stats = 0

    @dataclass(frozen=True, slots=True)
    class ParentStatus:
        st_dev: int
        st_mode: int

    def report_cross_device_for_destination_parent(descriptor: int) -> os.stat_result | ParentStatus:
        nonlocal parent_stats
        result = original_fstat(descriptor)
        parent_stats += 1
        if parent_stats != 4:
            return result
        return ParentStatus(st_dev=result.st_dev + 1, st_mode=result.st_mode)

    monkeypatch.setattr(output_layout_rename.os, "fstat", report_cross_device_for_destination_parent)

    with pytest.raises(output_layout_rename.OutputLayoutRenameError, match="cross-filesystem"):
        rename_noreplace(source, destination)

    assert source.is_dir()
    assert not destination.exists()


def test_rename_noreplace_rejects_non_directory_source(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination"
    source.write_text("source\n", encoding="utf-8")

    with pytest.raises(output_layout_rename.OutputLayoutRenameError, match="source must be a real directory"):
        rename_noreplace(source, destination)

    assert source.read_text(encoding="utf-8") == "source\n"
    assert not destination.exists()


def test_rename_noreplace_reports_destination_after_rename_before_parent_fsync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "payload.txt").write_text("payload\n", encoding="utf-8")

    def interrupt_parent_fsync(_descriptor: int) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr(output_layout_rename.os, "fsync", interrupt_parent_fsync)

    with pytest.raises(output_layout_rename.OutputLayoutRenameError, match="ordinary rename failed"):
        rename_noreplace(source, destination)

    assert not source.exists()
    assert (destination / "payload.txt").read_text(encoding="utf-8") == "payload\n"


def test_write_record_rejects_existing_journal_name_without_clobbering(tmp_path: Path) -> None:
    output_layout_journal = importlib.import_module("scripts.phase3.output_layout_journal")
    journal_directory = tmp_path / "journal"
    journal_directory.mkdir()
    first_payload = {"event": "prepared", "sequence": 1}
    replacement_payload = {"event": "complete", "sequence": 2}

    record_path = output_layout_journal.write_record(journal_directory, "0001-prepared.json", first_payload)

    with pytest.raises(output_layout_journal.OutputLayoutJournalError, match="journal record already exists"):
        output_layout_journal.write_record(journal_directory, "0001-prepared.json", replacement_payload)

    assert record_path.read_bytes() == b'{"event":"prepared","sequence":1}\n'


def test_write_record_creates_private_immutable_json(tmp_path: Path) -> None:
    output_layout_journal = importlib.import_module("scripts.phase3.output_layout_journal")
    journal_directory = tmp_path / "journal"
    journal_directory.mkdir()

    record_path = output_layout_journal.write_record(journal_directory, "0001-prepared.json", {"event": "prepared"})

    assert stat.S_IMODE(record_path.stat().st_mode) == 0o600
    assert record_path.read_bytes() == b'{"event":"prepared"}\n'


def test_write_record_fsyncs_content_before_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_layout_journal = importlib.import_module("scripts.phase3.output_layout_journal")
    journal_directory = tmp_path / "journal"
    journal_directory.mkdir()
    original_fsync = output_layout_journal.os.fsync
    observed_inodes: list[int] = []

    def observe_fsync(descriptor: int) -> None:
        observed_inodes.append(os.fstat(descriptor).st_ino)
        original_fsync(descriptor)

    monkeypatch.setattr(output_layout_journal.os, "fsync", observe_fsync)

    record_path = output_layout_journal.write_record(journal_directory, "0001-prepared.json", {"event": "prepared"})

    assert observed_inodes == [record_path.stat().st_ino, journal_directory.stat().st_ino]


def test_write_record_rejects_malformed_record_name(tmp_path: Path) -> None:
    output_layout_journal = importlib.import_module("scripts.phase3.output_layout_journal")
    journal_directory = tmp_path / "journal"
    journal_directory.mkdir()

    with pytest.raises(output_layout_journal.OutputLayoutJournalError, match="journal record name"):
        output_layout_journal.write_record(journal_directory, "../escape.json", {"event": "prepared"})

    assert not tuple(journal_directory.iterdir())
