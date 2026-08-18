from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.phase3 import (
    output_layout_receipt_fs,
    output_layout_receipt_io,
    output_layout_receipt_transaction,
    output_layout_receipt_values,
    output_layout_snapshot,
)
from scripts.phase3.output_layout_inventory import (
    OutputLayoutInventoryError,
    read_receipt,
    seal_receipt,
    snapshot_tree,
    write_receipt,
)


def test_snapshot_rejects_intermediate_symlink_component(tmp_path: Path) -> None:
    real_parent = tmp_path / "real"
    root = real_parent / "inventory"
    root.mkdir(parents=True)
    (root / "payload.txt").write_text("protected\n", encoding="utf-8")
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(OutputLayoutInventoryError):
        snapshot_tree(linked_parent / root.name)


def test_snapshot_rejects_directory_entry_count_over_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    (root / "one").write_text("1", encoding="utf-8")
    (root / "two").write_text("2", encoding="utf-8")
    monkeypatch.setattr(output_layout_snapshot, "_MAX_DIRECTORY_ENTRIES", 1, raising=False)

    with pytest.raises(OutputLayoutInventoryError, match="too many entries"):
        snapshot_tree(root)


def test_snapshot_rejects_directory_depth_over_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "inventory"
    (root / "one" / "two").mkdir(parents=True)
    monkeypatch.setattr(output_layout_snapshot, "_MAX_DIRECTORY_DEPTH", 1, raising=False)

    with pytest.raises(OutputLayoutInventoryError, match="too deep"):
        snapshot_tree(root)


def test_same_receipt_contents_require_private_mode(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt = seal_receipt({"operation": "security-test", "state": "prepared"})
    write_receipt(receipt_path, receipt)
    receipt_path.chmod(0o644)

    with pytest.raises(OutputLayoutInventoryError, match="mode 0600"):
        write_receipt(receipt_path, receipt)


def test_read_receipt_requires_private_mode(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt = seal_receipt({"operation": "security-test", "state": "prepared"})
    write_receipt(receipt_path, receipt)
    receipt_path.chmod(0o644)

    with pytest.raises(OutputLayoutInventoryError, match="mode 0600"):
        read_receipt(receipt_path)


def test_receipt_reads_use_nonblocking_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt = seal_receipt({"operation": "security-test"})
    write_receipt(receipt_path, receipt)
    original_open = output_layout_receipt_io._open_descriptor

    def require_nonblocking_open(
        path: str | Path,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if path == receipt_path.name:
            assert flags & os.O_NONBLOCK
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(output_layout_receipt_io, "_open_descriptor", require_nonblocking_open)
    assert read_receipt(receipt_path) == receipt


def test_receipt_sidecar_reads_use_nonblocking_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt_path = tmp_path / "receipt.json"
    transaction_path = tmp_path / ".receipt.json.txn"
    transaction_path.write_bytes(b"invalid")
    transaction_path.chmod(0o600)
    original_open = output_layout_receipt_transaction.os.open

    def require_nonblocking_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if path == transaction_path.name:
            assert flags & os.O_NONBLOCK
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(output_layout_receipt_transaction.os, "open", require_nonblocking_open)
    with pytest.raises(OutputLayoutInventoryError):
        write_receipt(receipt_path, seal_receipt({"operation": "security-test"}))


def test_receipt_read_rejects_content_over_byte_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_bytes(b"0123456789")
    descriptor = os.open(receipt_path, os.O_RDONLY)
    monkeypatch.setattr(output_layout_receipt_fs, "_MAX_RECEIPT_BYTES", 4, raising=False)
    try:
        with pytest.raises(OutputLayoutInventoryError, match="size limit"):
            output_layout_receipt_fs.read_content_token(descriptor)
    finally:
        os.close(descriptor)


def test_deep_receipt_json_is_translated_to_inventory_error(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text("[" * 1_500 + "0" + "]" * 1_500, encoding="utf-8")
    receipt_path.chmod(0o600)

    with pytest.raises(OutputLayoutInventoryError, match="invalid receipt JSON"):
        read_receipt(receipt_path)


def test_receipt_json_collection_cardinality_is_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        '{"payload":[0,0,0],"receipt_sha256":"' + "0" * 64 + '"}',
        encoding="utf-8",
    )
    receipt_path.chmod(0o600)
    monkeypatch.setattr(output_layout_receipt_values, "_MAX_JSON_ITEMS", 2, raising=False)

    with pytest.raises(OutputLayoutInventoryError, match="too many JSON items"):
        read_receipt(receipt_path)


def test_oversized_transaction_sidecar_is_rejected_and_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt_path = tmp_path / "receipt.json"
    transaction_path = tmp_path / ".receipt.json.txn"
    transaction_path.write_bytes(b"0123456789")
    transaction_path.chmod(0o600)
    monkeypatch.setattr(output_layout_receipt_fs, "_MAX_RECEIPT_BYTES", 4)

    with pytest.raises(OutputLayoutInventoryError, match="size limit"):
        write_receipt(receipt_path, seal_receipt({"operation": "security-test"}))

    assert transaction_path.read_bytes() == b"0123456789"


def test_receipt_sidecar_racer_is_restored_after_quarantine_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt = seal_receipt({"operation": "security-test"})
    original_rename = output_layout_receipt_fs.atomic_rename
    racer_bytes = b"racer-owned\n"
    raced = False

    def replace_before_quarantine(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
        flags: int,
    ) -> None:
        nonlocal raced
        if destination_name.endswith(".remove") and not raced:
            raced = True
            os.unlink(source_name, dir_fd=parent_descriptor)
            descriptor = os.open(source_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent_descriptor)
            try:
                os.write(descriptor, racer_bytes)
            finally:
                os.close(descriptor)
        original_rename(parent_descriptor, source_name, destination_name, flags)

    monkeypatch.setattr(output_layout_receipt_fs, "atomic_rename", replace_before_quarantine)

    write_receipt(receipt_path, receipt)

    retained = tuple(tmp_path.glob(".receipt.json.txn.retained-*"))
    assert len(retained) == 1
    assert retained[0].read_bytes() != racer_bytes
