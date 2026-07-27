from __future__ import annotations

import os
import stat
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_snapshot
from scripts.phase3.output_layout_inventory import OutputLayoutInventoryError, read_receipt, seal_receipt, snapshot_tree, write_receipt
from scripts.phase3.output_layout_walk_budget import TraversalBudget


def _write_known_vector_tree(root: Path) -> None:
    (root / "empty").mkdir(parents=True)
    (root / "nested").mkdir()
    (root / "file.txt").write_bytes(b"alpha")
    (root / "nested" / "data.bin").write_bytes(b"\x00\xff")
    (root / "pointer").symlink_to("nested/data.bin")


def test_tree_snapshot_is_deterministic_known_vector(tmp_path: Path) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    _write_known_vector_tree(root)
    first = snapshot_tree(root)
    assert first == snapshot_tree(root)
    assert (first.file_count, first.directory_count, first.symlink_count, first.total_bytes) == (2, 3, 1, 7)
    assert first.tree_sha256 == "4e6f90aa54d75ad4a79bfe43fa7c6987e336ce1ed25e7d35ccca558bc5609bd0"


def test_tree_snapshot_changes_on_one_byte_mutation(tmp_path: Path) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    target = root / "payload.bin"
    target.write_bytes(b"abc")
    before = snapshot_tree(root)
    target.write_bytes(b"abd")
    after = snapshot_tree(root)
    assert after.tree_sha256 != before.tree_sha256
    assert after.total_bytes == before.total_bytes == 3


def test_tree_snapshot_changes_when_relative_name_changes(tmp_path: Path) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    original = root / "before.txt"
    original.write_bytes(b"unchanged")
    before = snapshot_tree(root)
    original.rename(root / "after.txt")
    after = snapshot_tree(root)
    assert after.tree_sha256 != before.tree_sha256
    assert after.total_bytes == before.total_bytes


def test_tree_snapshot_distinguishes_an_empty_directory(tmp_path: Path) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    before = snapshot_tree(root)
    (root / "empty").mkdir()
    after = snapshot_tree(root)
    assert after.tree_sha256 != before.tree_sha256
    assert after.directory_count == before.directory_count + 1


def test_tree_snapshot_changes_when_symlink_text_changes_without_following(tmp_path: Path) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    (root / "one.txt").write_text("same", encoding="utf-8")
    (root / "two.txt").write_text("same", encoding="utf-8")
    link = root / "current"
    link.symlink_to("one.txt")
    before = snapshot_tree(root)
    link.unlink()
    link.symlink_to("two.txt")
    after = snapshot_tree(root)
    assert after.tree_sha256 != before.tree_sha256
    assert after.symlink_count == 1


def test_atomic_receipt_is_mode_0600_and_round_trips(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt = seal_receipt({"operation": "synthetic-test", "state": "prepared"})
    write_receipt(receipt_path, receipt)
    assert read_receipt(receipt_path) == receipt
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600


def _single_file_tree(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "inventory"
    root.mkdir()
    target = root / "payload.txt"
    target.write_bytes(b"original")
    return root, target


def test_snapshot_rejects_root_replaced_after_walk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, target = _single_file_tree(tmp_path)
    original_walk = output_layout_snapshot._snapshot_directory

    def walk_then_replace(descriptor: int, display_path: Path, relative: str, digest: output_layout_snapshot._Digest, counts: list[int]) -> None:
        original_walk(descriptor, display_path, relative, digest, counts)
        if display_path == root:
            root.rename(tmp_path / "replaced-root")
            root.mkdir()
            (root / target.name).write_bytes(b"replacement")

    monkeypatch.setattr(output_layout_snapshot, "_snapshot_directory", walk_then_replace)
    with pytest.raises(OutputLayoutInventoryError, match="root changed"):
        snapshot_tree(root)


def _add_entry(root: Path, _target: Path) -> None:
    (root / "added.txt").write_bytes(b"added")


def _remove_entry(_root: Path, target: Path) -> None:
    target.unlink()


def _rename_entry(root: Path, target: Path) -> None:
    target.rename(root / "renamed.txt")


@pytest.mark.parametrize("mutation", (_add_entry, _remove_entry, _rename_entry), ids=("add", "remove", "rename"))
def test_snapshot_rejects_entry_set_mutation_after_file_processing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: Callable[[Path, Path], None]) -> None:
    root, target = _single_file_tree(tmp_path)
    original_add = output_layout_snapshot._add_regular_file

    def hash_then_mutate(
        parent_descriptor: int,
        name: str,
        path: Path,
        relative: str,
        expected_stat: os.stat_result,
        digest: output_layout_snapshot._Digest,
        counts: list[int],
        budget: TraversalBudget,
    ) -> None:
        original_add(parent_descriptor, name, path, relative, expected_stat, digest, counts, budget)
        mutation(root, target)

    monkeypatch.setattr(output_layout_snapshot, "_add_regular_file", hash_then_mutate)
    with pytest.raises(OutputLayoutInventoryError, match="directory changed"):
        snapshot_tree(root)


@pytest.mark.parametrize(("replacement", "match"), ((True, "regular file changed"), (False, "regular file changed")))
def test_snapshot_rejects_regular_file_path_or_content_mutation_during_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replacement: bool, match: str) -> None:
    root, target = _single_file_tree(tmp_path)
    original_read = output_layout_snapshot._read_descriptor
    mutated = False

    def read_then_mutate(descriptor: int, length: int) -> bytes:
        nonlocal mutated
        chunk = original_read(descriptor, length)
        if not mutated:
            mutated = True
            if replacement:
                target.rename(root / "original-payload.txt")
                target.write_bytes(b"replacement")
            else:
                target.write_bytes(b"changed-content")
        return chunk

    monkeypatch.setattr(output_layout_snapshot, "_read_descriptor", read_then_mutate)
    with pytest.raises(OutputLayoutInventoryError, match=match):
        snapshot_tree(root)


def test_snapshot_rejects_symlink_replaced_after_target_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    link = root / "current"
    link.symlink_to("first.txt")
    original_record = output_layout_snapshot._add_record

    def record_then_replace(digest: output_layout_snapshot._Digest, marker: bytes, relative: str, payload: bytes = b"") -> None:
        original_record(digest, marker, relative, payload)
        if marker == b"L":
            link.unlink()
            link.symlink_to("second.txt")

    monkeypatch.setattr(output_layout_snapshot, "_add_record", record_then_replace)
    with pytest.raises(OutputLayoutInventoryError, match="symlink changed"):
        snapshot_tree(root)


def test_snapshot_closes_all_descriptors_when_child_fstat_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "inventory"
    (root / "child").mkdir(parents=True)
    original_open = output_layout_snapshot._open_descriptor
    original_close = output_layout_snapshot._close_descriptor
    original_fstat = output_layout_snapshot._fstat_descriptor
    children: list[int] = []
    opened: list[int] = []
    closed: list[int] = []

    def record_open(path: str | bytes | os.PathLike[str] | os.PathLike[bytes], flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
        descriptor = original_open(path, flags, mode, dir_fd=dir_fd)
        opened.append(descriptor)
        if dir_fd is not None and os.fsdecode(path) == "child":
            children.append(descriptor)
        return descriptor

    def fail_child_fstat(descriptor: int) -> os.stat_result:
        if descriptor in children:
            raise OSError("synthetic child fstat failure")
        return original_fstat(descriptor)

    def record_close(descriptor: int) -> None:
        closed.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(output_layout_snapshot, "_open_descriptor", record_open)
    monkeypatch.setattr(output_layout_snapshot, "_fstat_descriptor", fail_child_fstat)
    monkeypatch.setattr(output_layout_snapshot, "_close_descriptor", record_close)
    with pytest.raises(OutputLayoutInventoryError, match="directory changed"):
        snapshot_tree(root)
    assert set(opened) <= set(closed)


def test_snapshot_translates_invalid_root_path_to_inventory_error() -> None:
    with pytest.raises(OutputLayoutInventoryError, match="unable to snapshot inventory tree"):
        snapshot_tree(Path("invalid\x00root"))


def test_snapshot_translates_descriptor_close_failure_to_inventory_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    original_close = output_layout_snapshot._close_descriptor

    def close_then_fail(descriptor: int) -> None:
        original_close(descriptor)
        raise OSError("synthetic close failure")

    monkeypatch.setattr(output_layout_snapshot, "_close_descriptor", close_then_fail)
    with pytest.raises(OutputLayoutInventoryError, match="unable to snapshot inventory tree"):
        snapshot_tree(root)


def test_snapshot_fifo_substitution_before_regular_file_open_is_nonblocking_and_normalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, target = _single_file_tree(tmp_path)
    original_open = output_layout_snapshot._open_descriptor
    replaced = False

    def replace_regular_file_with_fifo(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if os.fsdecode(path) == target.name and not replaced:
            replaced = True
            target.unlink()
            os.mkfifo(target)
            assert flags & os.O_NONBLOCK
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(output_layout_snapshot, "_open_descriptor", replace_regular_file_with_fifo)

    with pytest.raises(OutputLayoutInventoryError, match="tree entry changed type during snapshot"):
        snapshot_tree(root)
