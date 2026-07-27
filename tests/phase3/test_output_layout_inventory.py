from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import get_args

import pytest

from scripts.phase3 import output_layout_inventory, output_layout_receipt, output_layout_receipt_io, output_layout_snapshot
from scripts.phase3.output_layout_inventory import OutputLayoutInventoryError, ReceiptInputValue, ReceiptRecord, read_receipt, seal_receipt, snapshot_tree, write_receipt


def _receipt() -> ReceiptRecord:
    return seal_receipt({"operation": "synthetic-test", "state": "prepared"})


class _ReprCapableValue:
    def __repr__(self) -> str:
        return "repr-capable"


@pytest.mark.parametrize("target", ("../outside", "/tmp/outside"))
def test_tree_snapshot_rejects_out_of_root_symlink(tmp_path: Path, target: str) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    (root / "escape").symlink_to(target)
    with pytest.raises(OutputLayoutInventoryError, match="out-of-root symlink"):
        snapshot_tree(root)


def test_tree_snapshot_rejects_special_file(tmp_path: Path) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    os.mkfifo(root / "events.fifo")
    with pytest.raises(OutputLayoutInventoryError, match="special entry"):
        snapshot_tree(root)


def test_tree_snapshot_rejects_unreadable_entry(tmp_path: Path) -> None:
    root = tmp_path / "inventory"
    root.mkdir()
    blocked = root / "blocked.txt"
    blocked.write_text("secret", encoding="utf-8")
    blocked.chmod(0)
    try:
        with pytest.raises(OutputLayoutInventoryError, match="unreadable entry"):
            snapshot_tree(root)
    finally:
        blocked.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_tree_snapshot_rejects_directory_replaced_by_symlink_during_walk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "inventory"
    child = root / "child"
    outside = tmp_path / "outside"
    child.mkdir(parents=True)
    outside.mkdir()
    (child / "inside.txt").write_text("inside\n", encoding="utf-8")
    original_open = output_layout_snapshot._open_child_directory

    def raced_open(parent_descriptor: int, name: str, path: Path, expected_stat: os.stat_result) -> int:
        if path == child:
            child.rename(root / "original-child")
            child.symlink_to(outside, target_is_directory=True)
        return original_open(parent_descriptor, name, path, expected_stat)

    monkeypatch.setattr(output_layout_snapshot, "_open_child_directory", raced_open)
    with pytest.raises(OutputLayoutInventoryError):
        snapshot_tree(root)


def test_read_receipt_rejects_corrupt_json(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text("{not-json", encoding="utf-8")
    receipt_path.chmod(0o600)
    with pytest.raises(OutputLayoutInventoryError, match="invalid receipt JSON"):
        read_receipt(receipt_path)


def test_public_receipt_input_alias_excludes_non_json_scalar_types() -> None:
    assert not {bytes, complex, Path} & set(get_args(ReceiptInputValue))


def test_public_inventory_does_not_export_boundary_escape_hatches() -> None:
    assert not {"ReceiptBoundaryValue", "ReceiptKey"} & set(output_layout_inventory.__all__)


@pytest.mark.parametrize("payload", ({"nested": {"unsupported": b"bytes"}}, {"nested": {"unsupported": complex(1, 2)}}, {"nested": {"unsupported": Path("receipt-path")}}, {"nested": [("tuple",)]}, {"nested": {1: "non-string-key"}}, {"nested": {"unsupported": _ReprCapableValue()}}, {"nested": {"unsupported": float("nan")}}, {"nested": {"unsupported": float("inf")}}), ids=("bytes", "complex", "path", "tuple", "non-string-key", "repr-capable", "nan", "infinity"))
def test_seal_receipt_rejects_nested_non_json_runtime_values(payload: Mapping[str, ReceiptInputValue]) -> None:
    with pytest.raises(OutputLayoutInventoryError):
        seal_receipt(payload)


def test_seal_receipt_accepts_nested_json_values_from_non_dict_mapping() -> None:
    items: list[ReceiptInputValue] = [None, True, 3, 4.5, "text", {"child": ["value", False]}]
    payload: Mapping[str, ReceiptInputValue] = MappingProxyType({"nested": MappingProxyType({"items": items})})
    sealed = seal_receipt(payload)
    assert sealed["nested"] == {"items": [None, True, 3, 4.5, "text", {"child": ["value", False]}]}
    assert isinstance(sealed["nested"], dict)


def test_read_receipt_translates_missing_file_to_inventory_error(tmp_path: Path) -> None:
    with pytest.raises(OutputLayoutInventoryError, match="receipt path must be a regular file"):
        read_receipt(tmp_path / "missing-receipt.json")


def test_write_receipt_translates_missing_parent_to_inventory_error(tmp_path: Path) -> None:
    receipt_path = tmp_path / "missing-parent" / "receipt.json"
    with pytest.raises(OutputLayoutInventoryError, match="receipt parent must be a real directory"):
        write_receipt(receipt_path, _receipt())
    assert not receipt_path.exists()


def test_atomic_receipt_rejects_symlink_path(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.symlink_to(tmp_path / "elsewhere.json")
    with pytest.raises(OutputLayoutInventoryError, match="receipt path must not be a symlink"):
        write_receipt(receipt_path, _receipt())
    assert not (tmp_path / "elsewhere.json").exists()


def test_atomic_receipt_rejects_symlink_parent_and_ancestor(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(OutputLayoutInventoryError, match="receipt parent must not be a symlink"):
        write_receipt(alias / "receipt.json", _receipt())
    real_root = tmp_path / "real-root"
    (real_root / "receipts").mkdir(parents=True)
    ancestor = tmp_path / "ancestor"
    ancestor.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(OutputLayoutInventoryError, match="must not contain symlinks"):
        write_receipt(ancestor / "receipts" / "receipt.json", _receipt())
    assert not (target / "receipt.json").exists()


def test_atomic_receipt_rejects_parent_replaced_after_location_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent = tmp_path / "receipt-dir"
    outside = tmp_path / "outside"
    parent.mkdir()
    outside.mkdir()
    original_open = output_layout_receipt._open_parent_directory

    def replace_parent(path: Path) -> int:
        descriptor = original_open(path)
        parent.rename(tmp_path / "original-receipt-dir")
        parent.symlink_to(outside, target_is_directory=True)
        return descriptor

    monkeypatch.setattr(output_layout_receipt, "_open_parent_directory", replace_parent)
    with pytest.raises(OutputLayoutInventoryError):
        write_receipt(parent / "receipt.json", _receipt())
    assert not (outside / "receipt.json").exists()


def test_atomic_receipt_does_not_clobber_replacement_after_validation(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    write_receipt(receipt_path, _receipt())

    def exchange_with_racer(parent_descriptor: int, swap_name: str, receipt_name: str) -> None:
        receipt_path.unlink()
        receipt_path.write_text("racer-owned\n", encoding="utf-8")
        output_layout_receipt._atomic_exchange(parent_descriptor, swap_name, receipt_name)

    with pytest.raises(OutputLayoutInventoryError):
        write_receipt(receipt_path, seal_receipt({"operation": "synthetic-test", "state": "complete"}), exchange_operation=exchange_with_racer)
    assert receipt_path.read_text(encoding="utf-8") == "racer-owned\n"


def test_write_receipt_preserves_transaction_after_parent_fsync_failure(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    calls = 0

    def fail_parent_fsync(_descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated parent fsync failure")

    with pytest.raises(OutputLayoutInventoryError, match="parent") as exception_info:
        write_receipt(receipt_path, _receipt(), fsync_operation=fail_parent_fsync)
    assert isinstance(exception_info.value.__cause__, OSError)
    assert tuple(sorted(path.name for path in tmp_path.iterdir())) == (".receipt.json.txn",)


def test_read_receipt_translates_receipt_descriptor_close_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    receipt_path = tmp_path / "receipt.json"
    write_receipt(receipt_path, _receipt())
    receipt_stat = receipt_path.stat()
    original_close = output_layout_receipt_io._close_operation

    def fail_receipt_close(descriptor: int) -> None:
        descriptor_stat = os.fstat(descriptor)
        if stat.S_ISREG(descriptor_stat.st_mode) and (descriptor_stat.st_dev, descriptor_stat.st_ino) == (receipt_stat.st_dev, receipt_stat.st_ino):
            raise OSError("simulated receipt descriptor close failure")
        original_close(descriptor)

    monkeypatch.setattr(output_layout_receipt_io, "_close_operation", fail_receipt_close)
    with pytest.raises(OutputLayoutInventoryError, match="receipt") as exception_info:
        read_receipt(receipt_path)
    assert isinstance(exception_info.value.__cause__, OSError)
