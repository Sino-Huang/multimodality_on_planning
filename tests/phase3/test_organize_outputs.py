from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.phase3 import organize_outputs
from scripts.phase3.organize_outputs import OrganizerError, apply, verify
from scripts.phase3.output_layout_contracts import DEFAULT_OUTPUT_LAYOUT
from scripts.phase3.output_layout_snapshot import snapshot_tree
from organize_outputs_support import repository as synthetic_repository


def test_apply_and_verify_create_exact_three_category_layout(tmp_path: Path) -> None:
    repository = synthetic_repository(tmp_path)

    apply(repository)
    verify(repository)

    assert {path.name for path in (repository / "outputs").iterdir()} == {"reasoning_traces", "image_frames", "deprecated"}
    for relocation in DEFAULT_OUTPUT_LAYOUT.relocations:
        assert not (repository / relocation.source.value).exists()
        assert (repository / relocation.destination.value).is_dir()
    for copy in DEFAULT_OUTPUT_LAYOUT.physical_record_copies:
        source = repository / copy.source.value
        destination = repository / copy.destination.value
        assert source.read_bytes() == destination.read_bytes()
        assert not destination.is_symlink()


def test_destination_collision_preserves_source(tmp_path: Path) -> None:
    repository = synthetic_repository(tmp_path)
    relocation = DEFAULT_OUTPUT_LAYOUT.relocations[0]
    destination = repository / relocation.destination.value
    destination.mkdir(parents=True)

    with pytest.raises(OrganizerError, match="destination collision"):
        apply(repository)

    assert (repository / relocation.source.value).is_dir()


def test_quarantines_valid_failed_receipt_sidecars(tmp_path: Path) -> None:
    repository = synthetic_repository(tmp_path)
    source_directory = repository / "outputs/deprecated/phase3"
    swap = source_directory / ".output_reorganization_20260726.json.swap"
    transaction = source_directory / ".output_reorganization_20260726.json.txn"
    swap.write_text("{}\n", encoding="utf-8")
    digest = hashlib.sha256(swap.read_bytes()).hexdigest()
    transaction.write_text(json.dumps({"canonical_sha256": digest, "canonical_size": swap.stat().st_size, "swap_name": swap.name}) + "\n", encoding="utf-8")
    swap.chmod(0o600)
    transaction.chmod(0o600)

    apply(repository)

    destination = repository / "outputs/deprecated/receipts/failed-output-reorganization-20260726"
    assert (destination / swap.name).is_file()
    assert (destination / transaction.name).is_file()
    assert not swap.exists()
    assert not transaction.exists()


def test_apply_after_completion_returns_without_locking_again(tmp_path: Path) -> None:
    repository = synthetic_repository(tmp_path)
    apply(repository)
    completed_snapshot = snapshot_tree(repository / "outputs").to_record()

    result = subprocess.run(
        [sys.executable, "-m", "scripts.phase3.organize_outputs", "apply", "--repo-root", str(repository)],
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
    )

    assert result.returncode == 0
    assert result.stdout == '{"command": "apply", "ok": true}\n'
    assert snapshot_tree(repository / "outputs").to_record() == completed_snapshot


def test_copy_publication_does_not_overwrite_competing_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.jsonl"
    destination = tmp_path / "records/destination.jsonl"
    source.write_bytes(b'{"source":true}\n')
    source_metadata = organize_outputs._record_metadata(source)
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    competing_contents = b'{"competitor":true}\n'
    original_rename = os.rename
    original_link = os.link

    def competing_rename(source_path: os.PathLike[str], destination_path: os.PathLike[str], **options: int) -> None:
        destination.write_bytes(competing_contents)
        original_rename(source_path, destination_path, **options)

    def competing_link(
        source_path: os.PathLike[str],
        destination_path: os.PathLike[str],
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        destination.write_bytes(competing_contents)
        original_link(
            source_path,
            destination_path,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(organize_outputs.os, "rename", competing_rename)
    monkeypatch.setattr(organize_outputs.os, "link", competing_link)

    with pytest.raises(OrganizerError, match="record copy destination collision"):
        organize_outputs._copy_file(source, destination, source_metadata)

    assert destination.read_bytes() == competing_contents
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha256
    assert not tuple(destination.parent.glob(f".{destination.name}.copy-*"))


def test_record_metadata_rejects_symlink_without_reading_referent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    referent = tmp_path / "referent.jsonl"
    referent.write_bytes(b'{"referent":true}\n')
    source = tmp_path / "source.jsonl"
    source.symlink_to(referent)

    def reject_path_digest(_path: Path) -> tuple[str, int]:
        pytest.fail("record metadata must not digest a symlink referent by path")

    monkeypatch.setattr(organize_outputs, "digest", reject_path_digest)

    with pytest.raises(OrganizerError, match="record must be a regular file"):
        organize_outputs._record_metadata(source)


def test_record_metadata_rejects_fifo_with_nonblocking_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.jsonl"
    os.mkfifo(source)
    original_open = os.open

    def recording_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if os.fsdecode(path) == source.name:
            assert flags & os.O_NOFOLLOW
            assert flags & os.O_NONBLOCK
            assert flags & os.O_CLOEXEC
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(organize_outputs, "_open_descriptor", recording_open)

    with pytest.raises(OrganizerError, match="record must be a regular file"):
        organize_outputs._record_metadata(source)


def test_copy_rejects_fifo_replacement_at_source_open_without_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.jsonl"
    source.write_bytes(b'{"source":true}\n')
    source_metadata = organize_outputs._record_metadata(source)
    destination = tmp_path / "records/destination.jsonl"
    original_open = os.open
    replaced = False

    def replace_source_with_fifo(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if os.fsdecode(path) == source.name and not replaced:
            replaced = True
            source.unlink()
            os.mkfifo(source)
            assert flags & os.O_NOFOLLOW
            assert flags & os.O_NONBLOCK
            assert flags & os.O_CLOEXEC
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(organize_outputs, "_open_descriptor", replace_source_with_fifo)

    with pytest.raises(OrganizerError, match="record must be a regular file"):
        organize_outputs._copy_file(source, destination, source_metadata)

    assert replaced
    assert not destination.exists()
    assert not tuple(destination.parent.glob(f".{destination.name}.copy-*"))


def test_copy_accepts_mode_0644_jsonl_source(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    contents = b'{"source":true}\n'
    source.write_bytes(contents)
    source.chmod(0o644)
    destination = tmp_path / "records/destination.jsonl"
    source_metadata = organize_outputs._record_metadata(source)

    organize_outputs._copy_file(source, destination, source_metadata)

    assert destination.read_bytes() == contents
    assert organize_outputs._record_metadata(source) == {
        "sha256": hashlib.sha256(contents).hexdigest(),
        "bytes": len(contents),
        "lines": 1,
    }


def test_copy_records_rejects_regular_source_replacement_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = synthetic_repository(tmp_path)
    copy = DEFAULT_OUTPUT_LAYOUT.physical_record_copies[0]
    relocation = next(
        item for item in DEFAULT_OUTPUT_LAYOUT.relocations if copy.source.value.startswith(f"{item.destination.value}/")
    )
    original_source = repository / relocation.source.value / Path(copy.source.value).name
    expected_metadata = organize_outputs._record_metadata(original_source)
    source = repository / copy.source.value
    destination = repository / copy.destination.value
    replacement = b'{"replacement":true}\n'
    original_open = organize_outputs._open_descriptor
    source_opens = 0

    def replace_source_before_copy_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal source_opens
        if os.fsdecode(path) == source.name:
            source_opens += 1
            if source_opens == 2:
                source.unlink()
                source.write_bytes(replacement)
                source.chmod(0o644)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(organize_outputs, "_open_descriptor", replace_source_before_copy_open)

    with pytest.raises(OrganizerError):
        apply(repository)

    assert source_opens == 2
    assert expected_metadata != organize_outputs._record_metadata(source)
    assert not destination.exists()
    assert not tuple(destination.parent.glob(f".{destination.name}.copy-*"))
