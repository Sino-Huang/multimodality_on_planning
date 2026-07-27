from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_receipt_fs, output_layout_receipt_io, output_layout_receipt_transaction
from scripts.phase3.output_layout_inventory import OutputLayoutInventoryError, read_receipt, write_receipt
from tests.phase3.test_output_layout_receipt_adversarial import _receipt, _receipt_bytes, _transaction_bytes


def test_open_parent_directory_closes_next_descriptor_once_after_ambiguous_old_close(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    parent_stat = tmp_path.stat()
    descriptors = iter((10, 11))
    closed: list[int] = []

    def open_descriptor(_path: str | Path, _flags: int, _mode: int = 0o777, *, dir_fd: int | None = None) -> int:
        del dir_fd
        return next(descriptors)

    def directory_stat(_path: str, *, dir_fd: int, follow_symlinks: bool) -> os.stat_result:
        del dir_fd, follow_symlinks
        return parent_stat

    def ambiguous_close(descriptor: int) -> None:
        closed.append(descriptor)
        if descriptor == 10:
            raise OSError("old descriptor was already closed")

    monkeypatch.setattr(output_layout_receipt_io, "_open_descriptor", open_descriptor)
    monkeypatch.setattr(output_layout_receipt_io, "_stat_entry", directory_stat)
    monkeypatch.setattr(output_layout_receipt_io, "_close_operation", ambiguous_close)
    with pytest.raises(OutputLayoutInventoryError, match="traversal failed"):
        output_layout_receipt_io.open_parent_directory(Path("receipt-dir"))
    assert closed.count(10) == 1
    assert closed.count(11) == 1


def test_read_receipt_translates_utf8_decoding_failure(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_bytes(b"\xff")
    receipt_path.chmod(0o600)
    with pytest.raises(OutputLayoutInventoryError, match="receipt") as exception_info:
        read_receipt(receipt_path)
    assert isinstance(exception_info.value.__cause__, UnicodeDecodeError)


def test_receipt_cleanup_retains_racer_sidecar_after_quarantine_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    receipt_path = tmp_path / "receipt.json"
    transaction_path = tmp_path / ".receipt.json.txn"
    transaction_path.write_bytes(_transaction_bytes("complete", None, "create"))
    transaction_path.chmod(0o600)
    original_read_entry = output_layout_receipt_transaction._read_entry
    raced = False

    def read_then_replace(parent_descriptor: int, name: str, path: Path) -> output_layout_receipt_transaction.Entry | None:
        nonlocal raced
        entry = original_read_entry(parent_descriptor, name, path)
        if name.endswith(".remove") and entry is not None and not raced:
            raced = True
        return entry

    monkeypatch.setattr(output_layout_receipt_transaction, "_read_entry", read_then_replace)
    write_receipt(receipt_path, _receipt("complete"))
    assert not raced
    assert tuple(tmp_path.glob(".receipt.json.txn.retained-*"))


@pytest.mark.parametrize("mode", (0o644, 0o660, 0o604, 0o600))
@pytest.mark.parametrize("sidecar", ("transaction", "swap"))
def test_recovery_sidecars_require_exact_private_mode_at_read_and_cleanup(tmp_path: Path, mode: int, sidecar: str) -> None:
    receipt_path = tmp_path / "receipt.json"
    transaction_path = tmp_path / ".receipt.json.txn"
    transaction_path.write_bytes(_transaction_bytes("complete", None, "create"))
    transaction_path.chmod(0o600 if sidecar == "swap" else mode)
    if sidecar == "swap":
        swap_path = tmp_path / ".receipt.json.swap"
        swap_path.write_bytes(_receipt_bytes("complete"))
        swap_path.chmod(mode)
    if mode == 0o600:
        write_receipt(receipt_path, _receipt("complete"))
        assert read_receipt(receipt_path) == _receipt("complete")
        assert not transaction_path.exists()
        assert not (tmp_path / ".receipt.json.swap").exists()
    else:
        with pytest.raises(OutputLayoutInventoryError, match="mode 0600"):
            write_receipt(receipt_path, _receipt("complete"))


def test_oversized_sidecar_read_closes_descriptor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    receipt_path = tmp_path / "receipt.json"
    sidecar_name = ".receipt.json.txn"
    (tmp_path / sidecar_name).write_bytes(b"12345")
    (tmp_path / sidecar_name).chmod(0o600)
    parent_descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    original_close = output_layout_receipt_transaction._close
    closed: list[int] = []

    def record_close(descriptor: int, context: str) -> None:
        closed.append(descriptor)
        original_close(descriptor, context)

    monkeypatch.setattr(output_layout_receipt_fs, "_MAX_RECEIPT_BYTES", 4)
    monkeypatch.setattr(output_layout_receipt_transaction, "_close", record_close)
    try:
        with pytest.raises(OutputLayoutInventoryError, match="exceeds size limit"):
            output_layout_receipt_transaction._read_entry(parent_descriptor, sidecar_name, receipt_path)
        assert len(closed) == 1
        with pytest.raises(OSError):
            os.fstat(closed[0])
    finally:
        os.close(parent_descriptor)


def test_new_transaction_and_swap_sidecars_are_mode_0600_before_cleanup(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    observed_modes: dict[str, int] = {}

    def observe_created_sidecar(descriptor: int) -> None:
        name = Path(os.readlink(f"/proc/self/fd/{descriptor}")).name
        if name in {".receipt.json.txn", ".receipt.json.swap"}:
            observed_modes[name] = stat.S_IMODE(os.fstat(descriptor).st_mode)
        os.fsync(descriptor)

    write_receipt(receipt_path, _receipt("complete"), fsync_operation=observe_created_sidecar)
    assert observed_modes == {".receipt.json.txn": 0o600, ".receipt.json.swap": 0o600}
