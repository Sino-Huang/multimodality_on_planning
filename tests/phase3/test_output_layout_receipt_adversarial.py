from __future__ import annotations

import os
import hashlib
from pathlib import Path
from typing import TextIO

import pytest

from scripts.phase3 import output_layout_receipt, output_layout_receipt_fs, output_layout_receipt_io
from scripts.phase3.output_layout_inventory import OutputLayoutInventoryError, ReceiptRecord, read_receipt, seal_receipt, write_receipt


def _receipt(state: str = "prepared") -> ReceiptRecord:
    return seal_receipt({"operation": "adversarial-test", "state": state})


def _receipt_bytes(state: str) -> bytes:
    return output_layout_receipt._canonical_json(_receipt(state)) + b"\n"


def _transaction_bytes(new_state: str, expected_old_state: str | None, operation: str) -> bytes:
    new_bytes = _receipt_bytes(new_state)
    old_bytes = _receipt_bytes(expected_old_state) if expected_old_state is not None else b""
    transaction = {
        "canonical_sha256": hashlib.sha256(new_bytes).hexdigest(),
        "canonical_size": len(new_bytes),
        "expected_old_sha256": hashlib.sha256(old_bytes).hexdigest() if expected_old_state is not None else None,
        "expected_old_size": len(old_bytes) if expected_old_state is not None else None,
        "operation": operation,
        "swap_name": ".receipt.json.swap",
        "txid": "0123456789abcdef0123456789abcdef",
    }
    return output_layout_receipt._canonical_json(transaction) + b"\n"


@pytest.mark.parametrize("contents", ('{"receipt_sha256":"first","receipt_sha256":"second"}', '{"nested":{"key":"first","key":"second"}}', '{"nested":[{"key":"first","key":"second"}]}'))
def test_read_receipt_rejects_duplicate_json_keys_at_every_nesting_level(tmp_path: Path, contents: str) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(contents, encoding="utf-8")
    receipt_path.chmod(0o600)
    with pytest.raises(OutputLayoutInventoryError, match="duplicate receipt JSON key"):
        read_receipt(receipt_path)


def test_descriptor_component_guard_rejects_dot_components() -> None:
    with pytest.raises(OutputLayoutInventoryError, match="must not contain '.' or '..'"):
        output_layout_receipt_io.validated_directory_components(("receipts", ".", "current", ".."))


def test_open_receipt_closes_descriptor_when_fstat_fails(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text("{}", encoding="utf-8")
    parent_descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    opened: list[int] = []

    def failing_fstat(descriptor: int) -> os.stat_result:
        opened.append(descriptor)
        raise OSError("simulated fstat failure")

    try:
        with pytest.raises(OutputLayoutInventoryError, match="receipt path must be a regular file"):
            output_layout_receipt._open_receipt(parent_descriptor, receipt_path.name, receipt_path, fstat_operation=failing_fstat)
        with pytest.raises(OSError):
            os.fstat(opened[0])
    finally:
        os.close(parent_descriptor)


def test_read_receipt_rejects_in_place_content_mutation_after_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_bytes(_receipt_bytes("prepared"))
    receipt_path.chmod(0o600)
    original_load = output_layout_receipt.load_receipt_record

    def load_then_mutate(handle: TextIO) -> ReceiptRecord:
        decoded = original_load(handle)
        receipt_path.write_bytes(_receipt_bytes("complete"))
        return decoded

    monkeypatch.setattr(output_layout_receipt, "load_receipt_record", load_then_mutate)
    with pytest.raises(OutputLayoutInventoryError, match="receipt changed during read"):
        read_receipt(receipt_path)


def test_replacement_race_is_restored_without_clobbering_racer(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    write_receipt(receipt_path, _receipt())
    raced = False

    def exchange_with_racer(parent_descriptor: int, temporary_name: str, receipt_name: str) -> None:
        nonlocal raced
        if not raced:
            raced = True
            receipt_path.unlink()
            receipt_path.write_bytes(b"racer-owned\n")
        output_layout_receipt._atomic_exchange(parent_descriptor, temporary_name, receipt_name)

    with pytest.raises(OutputLayoutInventoryError, match="receipt changed during persistence"):
        write_receipt(receipt_path, _receipt("complete"), exchange_operation=exchange_with_racer)
    assert receipt_path.read_bytes() == b"racer-owned\n"


def test_existing_receipt_fails_closed_when_atomic_exchange_is_unavailable(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    original = _receipt()
    write_receipt(receipt_path, original)

    def unavailable_exchange(_parent_descriptor: int, _temporary_name: str, _receipt_name: str) -> None:
        raise OutputLayoutInventoryError("atomic receipt exchange is unavailable")

    with pytest.raises(OutputLayoutInventoryError, match="atomic receipt exchange is unavailable"):
        write_receipt(receipt_path, _receipt("complete"), exchange_operation=unavailable_exchange)
    assert read_receipt(receipt_path) == original


@pytest.mark.parametrize(("boundary", "expected_names", "has_receipt"), (("txn", (".receipt.json.txn",), False), ("directory-after-txn", (".receipt.json.txn",), False), ("swap", (".receipt.json.swap", ".receipt.json.txn"), False), ("directory-after-swap", (".receipt.json.swap", ".receipt.json.txn"), False), ("directory-after-publish", (".receipt.json.txn",), True), ("directory-after-cleanup", (), True)))
def test_initial_crashes_leave_only_fixed_sidecar_protocol_state(tmp_path: Path, boundary: str, expected_names: tuple[str, ...], has_receipt: bool) -> None:
    receipt_path = tmp_path / "receipt.json"
    directory_states: list[tuple[str, ...]] = []

    def crash_after_named_boundary(descriptor: int) -> None:
        os.fsync(descriptor)
        names = tuple(sorted(path.name for path in tmp_path.iterdir()))
        descriptor_name = Path(os.readlink(f"/proc/self/fd/{descriptor}")).name
        is_directory = os.path.isdir(f"/proc/self/fd/{descriptor}")
        if is_directory:
            directory_states.append(names)
        matches = (boundary == "txn" and descriptor_name == ".receipt.json.txn") or (boundary == "swap" and descriptor_name == ".receipt.json.swap") or (boundary == "directory-after-txn" and directory_states == [(".receipt.json.txn",)]) or (boundary == "directory-after-swap" and directory_states == [(".receipt.json.txn",), (".receipt.json.swap", ".receipt.json.txn")]) or (boundary == "directory-after-publish" and directory_states == [(".receipt.json.txn",), (".receipt.json.swap", ".receipt.json.txn"), (".receipt.json.txn", "receipt.json")]) or (boundary == "directory-after-cleanup" and directory_states == [(".receipt.json.txn",), (".receipt.json.swap", ".receipt.json.txn"), (".receipt.json.txn", "receipt.json"), ("receipt.json",)])
        if matches:
            raise OSError("simulated crash after durable boundary")

    if boundary == "directory-after-cleanup":
        write_receipt(receipt_path, _receipt(), fsync_operation=crash_after_named_boundary)
        assert len(tuple(tmp_path.glob(".receipt.json.txn.retained-*"))) == 1
    else:
        with pytest.raises(OutputLayoutInventoryError):
            write_receipt(receipt_path, _receipt(), fsync_operation=crash_after_named_boundary)
        assert tuple(sorted(path.name for path in tmp_path.iterdir())) == expected_names + (("receipt.json",) if has_receipt else ())
    assert not tuple(tmp_path.glob(".receipt.json.tmp-*"))
    assert not tuple(tmp_path.glob(".receipt.json.retired-*"))


def test_retry_recovers_create_interrupted_after_transaction_fsync(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"

    def crash_after_transaction_fsync(descriptor: int) -> None:
        os.fsync(descriptor)
        if Path(os.readlink(f"/proc/self/fd/{descriptor}")).name == ".receipt.json.txn":
            raise OSError("simulated crash after transaction fsync")

    with pytest.raises(OutputLayoutInventoryError):
        write_receipt(receipt_path, _receipt(), fsync_operation=crash_after_transaction_fsync)
    assert tuple(sorted(path.name for path in tmp_path.iterdir())) == (".receipt.json.txn",)
    write_receipt(receipt_path, _receipt())
    assert read_receipt(receipt_path) == _receipt()
    assert not tuple(tmp_path.glob(".receipt.json.txn"))
    assert not tuple(tmp_path.glob(".receipt.json.swap"))


def test_retry_recovers_replace_interrupted_after_transaction_fsync(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    old_receipt = _receipt()
    replacement = _receipt("complete")
    write_receipt(receipt_path, old_receipt)

    def crash_after_transaction_fsync(descriptor: int) -> None:
        os.fsync(descriptor)
        if Path(os.readlink(f"/proc/self/fd/{descriptor}")).name == ".receipt.json.txn":
            raise OSError("simulated crash after transaction fsync")

    with pytest.raises(OutputLayoutInventoryError):
        write_receipt(receipt_path, replacement, fsync_operation=crash_after_transaction_fsync)
    assert (tmp_path / "receipt.json").is_file()
    assert tuple(tmp_path.glob(".receipt.json.txn.retained-*"))
    assert read_receipt(receipt_path) == old_receipt
    write_receipt(receipt_path, replacement)
    assert read_receipt(receipt_path) == replacement
    assert not tuple(tmp_path.glob(".receipt.json.txn"))
    assert not tuple(tmp_path.glob(".receipt.json.swap"))


def test_initial_crash_after_no_replace_rename_leaves_fixed_recovery_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    receipt_path = tmp_path / "receipt.json"
    original_rename = output_layout_receipt_fs.atomic_rename

    def rename_then_crash(parent_descriptor: int, source_name: str, destination_name: str, flags: int) -> None:
        original_rename(parent_descriptor, source_name, destination_name, flags)
        if flags == output_layout_receipt_fs.RENAME_NOREPLACE:
            raise OSError("simulated crash after no-replace rename")

    monkeypatch.setattr(output_layout_receipt_fs, "atomic_rename", rename_then_crash)
    with pytest.raises(OutputLayoutInventoryError, match="initial receipt publication failed"):
        write_receipt(receipt_path, _receipt())
    assert tuple(sorted(path.name for path in tmp_path.iterdir())) == (".receipt.json.txn", "receipt.json")


def test_replacement_crash_after_exchange_leaves_fixed_recovery_state(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    write_receipt(receipt_path, _receipt())

    def exchange_then_crash(parent_descriptor: int, source_name: str, destination_name: str) -> None:
        output_layout_receipt._atomic_exchange(parent_descriptor, source_name, destination_name)
        raise OSError("simulated crash after exchange")

    with pytest.raises(OutputLayoutInventoryError, match="exchange"):
        write_receipt(receipt_path, _receipt("complete"), exchange_operation=exchange_then_crash)
    assert (tmp_path / "receipt.json").is_file()
    assert (tmp_path / ".receipt.json.swap").is_file()
    assert len(tuple(tmp_path.glob(".receipt.json.txn.retained-*"))) == 1
    assert read_receipt(receipt_path) == _receipt("complete")


@pytest.mark.parametrize(("receipt_state", "swap_state", "operation", "expected_old_state", "expected_exchanges"), ((None, "complete", "create", None, 0), ("prepared", "complete", "replace", "prepared", 1), ("complete", "prepared", "replace", "prepared", 0), ("complete", None, "replace", "prepared", 0)))
def test_retry_reconciles_fixed_transaction_states_without_unnecessary_exchange(tmp_path: Path, receipt_state: str | None, swap_state: str | None, operation: str, expected_old_state: str | None, expected_exchanges: int) -> None:
    receipt_path = tmp_path / "receipt.json"
    transaction_path = tmp_path / ".receipt.json.txn"
    transaction_path.write_bytes(_transaction_bytes("complete", expected_old_state, operation))
    transaction_path.chmod(0o600)
    if receipt_state is not None:
        receipt_path.write_bytes(_receipt_bytes(receipt_state))
        receipt_path.chmod(0o600)
    if swap_state is not None:
        swap_path = tmp_path / ".receipt.json.swap"
        swap_path.write_bytes(_receipt_bytes(swap_state))
        swap_path.chmod(0o600)
    exchanges = 0

    def count_exchange(parent_descriptor: int, source_name: str, destination_name: str) -> None:
        nonlocal exchanges
        exchanges += 1
        output_layout_receipt._atomic_exchange(parent_descriptor, source_name, destination_name)

    write_receipt(receipt_path, _receipt("complete"), exchange_operation=count_exchange)
    assert read_receipt(receipt_path) == _receipt("complete")
    assert exchanges == expected_exchanges
    assert not (tmp_path / ".receipt.json.txn").exists()
    assert not (tmp_path / ".receipt.json.swap").exists()


def test_malformed_fixed_transaction_preserves_evidence(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_bytes(_receipt_bytes("prepared"))
    receipt_path.chmod(0o600)
    transaction = tmp_path / ".receipt.json.txn"
    swap = tmp_path / ".receipt.json.swap"
    transaction.write_bytes(b"not-json")
    transaction.chmod(0o600)
    swap.write_bytes(_receipt_bytes("complete"))
    swap.chmod(0o600)
    with pytest.raises(OutputLayoutInventoryError):
        write_receipt(receipt_path, _receipt("complete"))
    assert transaction.read_bytes() == b"not-json"
    assert swap.read_bytes() == _receipt_bytes("complete")


def test_mismatched_fixed_transaction_preserves_evidence(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_bytes(_receipt_bytes("prepared"))
    receipt_path.chmod(0o600)
    transaction = tmp_path / ".receipt.json.txn"
    swap = tmp_path / ".receipt.json.swap"
    transaction.write_bytes(_transaction_bytes("complete", "final", "replace"))
    transaction.chmod(0o600)
    swap.write_bytes(_receipt_bytes("complete"))
    swap.chmod(0o600)
    with pytest.raises(OutputLayoutInventoryError):
        write_receipt(receipt_path, _receipt("complete"))
    assert transaction.read_bytes() == _transaction_bytes("complete", "final", "replace")
    assert swap.read_bytes() == _receipt_bytes("complete")


def test_repeated_replacements_remove_fixed_sidecars_and_displaced_receipt_bytes(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    old_bytes = _receipt_bytes("prepared")
    write_receipt(receipt_path, _receipt())
    write_receipt(receipt_path, _receipt("complete"))
    write_receipt(receipt_path, _receipt("final"))
    assert receipt_path.read_bytes() == _receipt_bytes("final")
    assert old_bytes != receipt_path.read_bytes()
    assert not tuple(tmp_path.glob(".receipt.json.txn"))
    assert not tuple(tmp_path.glob(".receipt.json.swap"))
    assert not tuple(tmp_path.glob(".receipt.json.retired-*"))
