from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_snapshot, output_layout_view_content, output_layout_view_stage
from scripts.phase3.output_layout_inventory import OutputLayoutInventoryError, snapshot_tree


def test_shared_production_budget_covers_frozen_selection_root() -> None:
    # The snapshot scans each directory entry before and after hashing.
    assert output_layout_snapshot._MAX_TOTAL_ENTRIES >= 2 * 322_983
    assert output_layout_snapshot._MAX_TOTAL_BYTES >= 6_633_150_947
    assert output_layout_view_content._MAX_TOTAL_ENTRIES == output_layout_snapshot._MAX_TOTAL_ENTRIES
    assert output_layout_view_content._MAX_TOTAL_BYTES == output_layout_snapshot._MAX_TOTAL_BYTES


def test_snapshot_rejects_cumulative_shallow_work_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "inventory"
    (root / "first").mkdir(parents=True)
    (root / "second").mkdir()
    (root / "first" / "one").write_bytes(b"1")
    (root / "second" / "two").write_bytes(b"2")
    monkeypatch.setattr(output_layout_snapshot, "_MAX_TOTAL_ENTRIES", 2)
    with pytest.raises(OutputLayoutInventoryError) as error_info:
        snapshot_tree(root)
    assert "work budget" in str(error_info.value.__cause__)


def test_snapshot_rejects_cumulative_actual_byte_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    (root / "payload").write_bytes(b"12345")
    monkeypatch.setattr(output_layout_snapshot, "_MAX_TOTAL_BYTES", 4)
    with pytest.raises(OutputLayoutInventoryError) as error_info:
        snapshot_tree(root)
    assert "byte budget" in str(error_info.value.__cause__)


def test_protected_token_rejects_cumulative_shallow_work_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "protected"
    (root / "first").mkdir(parents=True)
    (root / "second").mkdir()
    (root / "first" / "one").write_bytes(b"1")
    (root / "second" / "two").write_bytes(b"2")
    monkeypatch.setattr(output_layout_view_content, "_MAX_TOTAL_ENTRIES", 2)
    with pytest.raises(OSError, match="work budget"):
        output_layout_view_content.protected_content_token(root)


def test_protected_token_rejects_cumulative_actual_byte_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "protected"
    target.write_bytes(b"12345")
    monkeypatch.setattr(output_layout_view_content, "_MAX_TOTAL_BYTES", 4)
    with pytest.raises(OSError, match="byte budget"):
        output_layout_view_content.protected_content_token(target)


def test_snapshot_bounds_each_incremental_read_to_remaining_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    first = root / "first"
    target = root / "target"
    first.write_bytes(b"12")
    target.write_bytes(b"123456")
    monkeypatch.setattr(output_layout_snapshot, "_CHUNK_BYTES", 3)
    monkeypatch.setattr(output_layout_snapshot, "_MAX_TOTAL_BYTES", 6)
    requests: list[tuple[int, int]] = []

    def read_descriptor(descriptor: int, size: int) -> bytes:
        requests.append((os.fstat(descriptor).st_ino, size))
        return os.read(descriptor, size)

    monkeypatch.setattr(output_layout_snapshot, "_read_descriptor", read_descriptor)
    with pytest.raises(OutputLayoutInventoryError) as error_info:
        snapshot_tree(root)
    assert "byte budget" in str(error_info.value.__cause__)
    target_inode = target.stat().st_ino
    assert [size for inode, size in requests if inode == target_inode] == [3, 1]


def test_protected_token_bounds_each_incremental_read_to_remaining_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "protected"
    root.mkdir()
    first = root / "first"
    target = root / "target"
    first.write_bytes(b"12")
    target.write_bytes(b"123456")
    monkeypatch.setattr(output_layout_view_content, "_READ_CHUNK_BYTES", 3)
    monkeypatch.setattr(output_layout_view_content, "_MAX_TOTAL_BYTES", 6)
    requests: list[tuple[int, int]] = []
    original_read = os.read

    def read(descriptor: int, size: int) -> bytes:
        requests.append((os.fstat(descriptor).st_ino, size))
        return original_read(descriptor, size)

    monkeypatch.setattr(output_layout_view_content.os, "read", read)
    with pytest.raises(OSError, match="byte budget"):
        output_layout_view_content.protected_content_token(root)
    target_inode = target.stat().st_ino
    assert [size for inode, size in requests if inode == target_inode] == [3, 1]


def test_snapshot_exact_byte_limit_does_not_probe_eof(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    target = root / "target"
    target.write_bytes(b"123456")
    monkeypatch.setattr(output_layout_snapshot, "_CHUNK_BYTES", 3)
    monkeypatch.setattr(output_layout_snapshot, "_MAX_TOTAL_BYTES", 6)
    requests: list[tuple[int, int]] = []

    def read_descriptor(descriptor: int, size: int) -> bytes:
        requests.append((os.fstat(descriptor).st_ino, size))
        return os.read(descriptor, size)

    monkeypatch.setattr(output_layout_snapshot, "_read_descriptor", read_descriptor)
    snapshot_tree(root)
    target_inode = target.stat().st_ino
    assert [size for inode, size in requests if inode == target_inode] == [3, 3]


def test_protected_token_exact_byte_limit_does_not_probe_eof(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "protected"
    target.write_bytes(b"123456")
    monkeypatch.setattr(output_layout_view_content, "_READ_CHUNK_BYTES", 3)
    monkeypatch.setattr(output_layout_view_content, "_MAX_TOTAL_BYTES", 6)
    requests: list[tuple[int, int]] = []
    original_read = os.read

    def read(descriptor: int, size: int) -> bytes:
        requests.append((os.fstat(descriptor).st_ino, size))
        return original_read(descriptor, size)

    monkeypatch.setattr(output_layout_view_content.os, "read", read)
    output_layout_view_content.protected_content_token(target)
    target_inode = target.stat().st_ino
    assert [size for inode, size in requests if inode == target_inode] == [3, 3]


def test_snapshot_exhausted_budget_allows_empty_file_without_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    first = root / "first"
    empty = root / "zero"
    first.write_bytes(b"123456")
    empty.write_bytes(b"")
    monkeypatch.setattr(output_layout_snapshot, "_CHUNK_BYTES", 3)
    monkeypatch.setattr(output_layout_snapshot, "_MAX_TOTAL_BYTES", 6)
    requests: list[tuple[int, int]] = []

    def read_descriptor(descriptor: int, size: int) -> bytes:
        requests.append((os.fstat(descriptor).st_ino, size))
        return os.read(descriptor, size)

    monkeypatch.setattr(output_layout_snapshot, "_read_descriptor", read_descriptor)
    snapshot_tree(root)
    empty_inode = empty.stat().st_ino
    assert [size for inode, size in requests if inode == empty_inode] == []


def test_protected_token_exhausted_budget_allows_empty_file_without_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "protected"
    root.mkdir()
    first = root / "first"
    empty = root / "zero"
    first.write_bytes(b"123456")
    empty.write_bytes(b"")
    monkeypatch.setattr(output_layout_view_content, "_READ_CHUNK_BYTES", 3)
    monkeypatch.setattr(output_layout_view_content, "_MAX_TOTAL_BYTES", 6)
    requests: list[tuple[int, int]] = []
    original_read = os.read

    def read(descriptor: int, size: int) -> bytes:
        requests.append((os.fstat(descriptor).st_ino, size))
        return original_read(descriptor, size)

    monkeypatch.setattr(output_layout_view_content.os, "read", read)
    output_layout_view_content.protected_content_token(root)
    empty_inode = empty.stat().st_ino
    assert [size for inode, size in requests if inode == empty_inode] == []


def test_stage_walker_rejects_cumulative_shallow_work_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    stage = output_layout_view_stage.create_private_stage(parent, Path("datasets/view"))
    try:
        (tmp_path / stage.name / "first").mkdir()
        (tmp_path / stage.name / "second").mkdir()
        (tmp_path / stage.name / "first" / "one").mkdir()
        monkeypatch.setattr(output_layout_view_stage, "_MAX_DIRECTORY_ENTRIES", 2)
        with pytest.raises(OSError, match="too many entries"):
            output_layout_view_stage._scan(stage.descriptor, Path(), set(), {})
    finally:
        os.close(stage.descriptor)
        os.close(parent)
