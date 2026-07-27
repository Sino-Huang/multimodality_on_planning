from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Final

from . import output_layout_receipt_fs as _receipt_fs
from .output_layout_inventory_types import OutputLayoutInventoryError
from .output_layout_receipt_fs import ExchangeOperation, RENAME_NOREPLACE
from .output_layout_receipt_transaction_values import Digest, Entry, Transaction, digest_bytes, new_transaction, parse_transaction, sidecar_names

_NOFOLLOW: Final = getattr(os, "O_NOFOLLOW", 0)
_CREATE_FLAGS: Final = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW
_READ_FLAGS: Final = os.O_RDONLY | _NOFOLLOW | getattr(os, "O_NONBLOCK", 0)


def persist_receipt(parent_descriptor: int, parent: Path, receipt_path: Path, contents: bytes, fsync_operation: Callable[[int], None], exchange_operation: ExchangeOperation) -> None:
    parent_identity = _parent_identity(parent_descriptor, parent)
    _recover(parent_descriptor, parent, receipt_path, fsync_operation, exchange_operation)
    current = _read_entry(parent_descriptor, receipt_path.name, receipt_path)
    new = digest_bytes(contents)
    if current is not None and current.permissions != 0o600:
        raise OutputLayoutInventoryError(f"receipt path must have mode 0600: {receipt_path}")
    if current is not None and current.digest == new:
        _require_same_parent_path(parent, parent_identity)
        return
    swap_name, transaction_name = sidecar_names(receipt_path.name)
    if _read_entry(parent_descriptor, swap_name, receipt_path) is not None:
        raise OutputLayoutInventoryError(f"receipt recovery requires a transaction record: {receipt_path}")
    transaction = new_transaction(new, current.digest if current is not None else None, swap_name)
    _create_file(parent_descriptor, transaction_name, transaction.contents, fsync_operation, receipt_path)
    _fsync_parent(parent_descriptor, parent, fsync_operation)
    _create_file(parent_descriptor, swap_name, contents, fsync_operation, receipt_path)
    _fsync_parent(parent_descriptor, parent, fsync_operation)
    if current is None:
        _publish_initial(parent_descriptor, swap_name, receipt_path.name, receipt_path)
        _fsync_parent(parent_descriptor, parent, fsync_operation)
        _cleanup(parent_descriptor, parent, receipt_path, transaction, fsync_operation)
    else:
        _exchange_and_cleanup(parent_descriptor, parent, receipt_path, transaction, fsync_operation, exchange_operation)
    _require_same_parent_path(parent, parent_identity)


def _recover(parent_descriptor: int, parent: Path, receipt_path: Path, fsync_operation: Callable[[int], None], exchange_operation: ExchangeOperation) -> None:
    swap_name, transaction_name = sidecar_names(receipt_path.name)
    _restore_quarantined_entry(parent_descriptor, swap_name, receipt_path)
    _restore_quarantined_entry(parent_descriptor, transaction_name, receipt_path)
    transaction_entry = _read_entry(parent_descriptor, transaction_name, receipt_path)
    swap = _read_entry(parent_descriptor, swap_name, receipt_path)
    if transaction_entry is None:
        if swap is not None:
            raise OutputLayoutInventoryError(f"receipt recovery requires a transaction record: {receipt_path}")
        return
    transaction = parse_transaction(transaction_entry.contents, swap_name, receipt_path)
    receipt = _read_entry(parent_descriptor, receipt_path.name, receipt_path)
    if swap is None and ((receipt is None and transaction.old is None) or (receipt is not None and transaction.old is not None and receipt.digest == transaction.old)):
        _remove_entry(parent_descriptor, transaction_name, transaction_entry.digest, receipt_path)
        _fsync_parent(parent_descriptor, parent, fsync_operation)
        return
    if receipt is None and swap is not None and swap.digest == transaction.new and transaction.operation == "create":
        _publish_initial(parent_descriptor, swap_name, receipt_path.name, receipt_path)
        _fsync_parent(parent_descriptor, parent, fsync_operation)
        _cleanup(parent_descriptor, parent, receipt_path, transaction, fsync_operation)
        return
    if transaction.old is not None and receipt is not None and swap is not None:
        if receipt.digest == transaction.old and swap.digest == transaction.new:
            _exchange_and_cleanup(parent_descriptor, parent, receipt_path, transaction, fsync_operation, exchange_operation)
            return
        if receipt.digest == transaction.new and swap.digest == transaction.old:
            _fsync_parent(parent_descriptor, parent, fsync_operation)
            _cleanup(parent_descriptor, parent, receipt_path, transaction, fsync_operation)
            return
    if receipt is not None and receipt.digest == transaction.new and swap is None:
        _fsync_parent(parent_descriptor, parent, fsync_operation)
        _cleanup(parent_descriptor, parent, receipt_path, transaction, fsync_operation)
        return
    raise OutputLayoutInventoryError(f"receipt recovery state does not match transaction: {receipt_path}")


def _exchange_and_cleanup(parent_descriptor: int, parent: Path, receipt_path: Path, transaction: Transaction, fsync_operation: Callable[[int], None], exchange_operation: ExchangeOperation) -> None:
    old = transaction.old
    if old is None:
        raise OutputLayoutInventoryError(f"invalid replacement transaction: {receipt_path}")
    try:
        receipt = _read_entry(parent_descriptor, receipt_path.name, receipt_path)
        swap = _read_entry(parent_descriptor, transaction.swap_name, receipt_path)
    except OutputLayoutInventoryError as error:
        raise OutputLayoutInventoryError(f"receipt changed during persistence: {receipt_path}") from error
    if receipt is None or swap is None or receipt.digest != old or swap.digest != transaction.new:
        raise OutputLayoutInventoryError(f"receipt changed during persistence: {receipt_path}")
    try:
        exchange_operation(parent_descriptor, transaction.swap_name, receipt_path.name)
    except OSError as error:
        raise OutputLayoutInventoryError(f"atomic receipt exchange failed: {receipt_path}") from error
    try:
        receipt = _read_entry(parent_descriptor, receipt_path.name, receipt_path)
        swap = _read_entry(parent_descriptor, transaction.swap_name, receipt_path)
    except OutputLayoutInventoryError as error:
        try:
            exchange_operation(parent_descriptor, transaction.swap_name, receipt_path.name)
        except OSError as restore_error:
            raise OutputLayoutInventoryError(f"receipt race restoration failed: {receipt_path}") from restore_error
        raise OutputLayoutInventoryError(f"receipt changed during persistence: {receipt_path}") from error
    if receipt is None or swap is None or receipt.digest != transaction.new or swap.digest != old:
        _restore_racer(parent_descriptor, receipt_path, transaction, exchange_operation, receipt, swap)
        raise OutputLayoutInventoryError(f"receipt changed during persistence: {receipt_path}")
    _fsync_parent(parent_descriptor, parent, fsync_operation)
    _cleanup(parent_descriptor, parent, receipt_path, transaction, fsync_operation)


def _restore_racer(parent_descriptor: int, receipt_path: Path, transaction: Transaction, exchange_operation: ExchangeOperation, receipt: Entry | None, swap: Entry | None) -> None:
    if receipt is None or swap is None or receipt.digest != transaction.new:
        return
    try:
        exchange_operation(parent_descriptor, transaction.swap_name, receipt_path.name)
    except OSError as error:
        raise OutputLayoutInventoryError(f"receipt race restoration failed: {receipt_path}") from error


def _cleanup(parent_descriptor: int, parent: Path, receipt_path: Path, transaction: Transaction, fsync_operation: Callable[[int], None]) -> None:
    _require_entry(parent_descriptor, receipt_path.name, transaction.new, receipt_path)
    swap = _read_entry(parent_descriptor, transaction.swap_name, receipt_path)
    if swap is not None:
        old = transaction.old
        if old is None or swap.digest != old:
            raise OutputLayoutInventoryError(f"receipt recovery state does not match transaction: {receipt_path}")
        _require_entry(parent_descriptor, receipt_path.name, transaction.new, receipt_path)
        _remove_entry(parent_descriptor, transaction.swap_name, old, receipt_path)
        _fsync_parent(parent_descriptor, parent, fsync_operation)
    _require_entry(parent_descriptor, receipt_path.name, transaction.new, receipt_path)
    if _read_entry(parent_descriptor, transaction.swap_name, receipt_path) is not None:
        raise OutputLayoutInventoryError(f"receipt recovery state does not match transaction: {receipt_path}")
    _remove_entry(parent_descriptor, sidecar_names(receipt_path.name)[1], digest_bytes(transaction.contents), receipt_path)
    _fsync_parent(parent_descriptor, parent, fsync_operation)


def _create_file(parent_descriptor: int, name: str, contents: bytes, fsync_operation: Callable[[int], None], receipt_path: Path) -> None:
    try:
        descriptor = os.open(name, _CREATE_FLAGS, 0o600, dir_fd=parent_descriptor)
    except OSError as error:
        raise OutputLayoutInventoryError(f"unable to create receipt recovery entry: {receipt_path}") from error
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, contents)
        fsync_operation(descriptor)
    except OSError as error:
        _close(descriptor, f"unable to close receipt recovery entry: {receipt_path}")
        raise OutputLayoutInventoryError(f"unable to write receipt recovery entry: {receipt_path}") from error
    _close(descriptor, f"unable to close receipt recovery entry: {receipt_path}")


def _write_all(descriptor: int, contents: bytes) -> None:
    offset = 0
    while offset < len(contents):
        written = os.write(descriptor, contents[offset:])
        if written == 0:
            raise OSError("unable to write receipt recovery entry")
        offset += written


def _read_entry(parent_descriptor: int, name: str, receipt_path: Path) -> Entry | None:
    try:
        descriptor = os.open(name, _READ_FLAGS, dir_fd=parent_descriptor)
    except FileNotFoundError:
        return None
    except OSError as error:
        reason = "receipt path must not be a symlink" if name == receipt_path.name else "receipt recovery entry must be a regular file"
        raise OutputLayoutInventoryError(f"{reason}: {receipt_path}") from error
    try:
        entry_stat = os.fstat(descriptor)
        if not stat.S_ISREG(entry_stat.st_mode):
            raise OutputLayoutInventoryError(f"receipt recovery entry must be a regular file: {receipt_path}")
        if name != receipt_path.name and stat.S_IMODE(entry_stat.st_mode) != 0o600:
            raise OutputLayoutInventoryError(f"receipt recovery entry must have mode 0600: {receipt_path}")
        if entry_stat.st_size > _receipt_fs.max_receipt_bytes():
            raise OutputLayoutInventoryError(f"receipt recovery entry exceeds size limit: {receipt_path}")
        chunks: list[bytes] = []
        bytes_read = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            bytes_read += len(chunk)
            if bytes_read > _receipt_fs.max_receipt_bytes():
                raise OutputLayoutInventoryError(f"receipt recovery entry exceeds size limit: {receipt_path}")
            chunks.append(chunk)
        contents = b"".join(chunks)
    except OSError as error:
        raise OutputLayoutInventoryError(f"unable to read receipt recovery entry: {receipt_path}") from error
    finally:
        _close(descriptor, f"unable to close receipt recovery entry: {receipt_path}")
    return Entry(
        digest_bytes(contents),
        contents,
        stat.S_IMODE(entry_stat.st_mode),
        (entry_stat.st_dev, entry_stat.st_ino),
    )


def _require_entry(parent_descriptor: int, name: str, expected: Digest, receipt_path: Path) -> None:
    entry = _read_entry(parent_descriptor, name, receipt_path)
    if entry is None or entry.digest != expected:
        raise OutputLayoutInventoryError(f"receipt recovery entry changed before cleanup: {receipt_path}")


def _remove_entry(parent_descriptor: int, name: str, expected: Digest, receipt_path: Path) -> None:
    _require_entry(parent_descriptor, name, expected, receipt_path)
    for _attempt in range(32):
        retained_name = f"{name}.retained-{secrets.token_hex(16)}"
        try:
            _receipt_fs.atomic_rename(parent_descriptor, name, retained_name, _receipt_fs.RENAME_NOREPLACE)
        except FileExistsError:
            continue
        except OSError as error:
            raise OutputLayoutInventoryError(f"unable to retain receipt recovery entry: {receipt_path}") from error
        return
    raise OutputLayoutInventoryError(f"unable to allocate retained receipt recovery entry: {receipt_path}")


def _restore_quarantined_entry(parent_descriptor: int, name: str, receipt_path: Path) -> None:
    quarantine_name = f"{name}.remove"
    quarantined = _read_entry(parent_descriptor, quarantine_name, receipt_path)
    if quarantined is None:
        return
    if _read_entry(parent_descriptor, name, receipt_path) is not None:
        raise OutputLayoutInventoryError(f"receipt cleanup state is ambiguous: {receipt_path}")
    try:
        _receipt_fs.atomic_rename(parent_descriptor, quarantine_name, name, _receipt_fs.RENAME_NOREPLACE)
    except OSError as error:
        raise OutputLayoutInventoryError(f"unable to restore receipt cleanup evidence: {receipt_path}") from error


def _publish_initial(parent_descriptor: int, swap_name: str, receipt_name: str, receipt_path: Path) -> None:
    try:
        _receipt_fs.atomic_rename(parent_descriptor, swap_name, receipt_name, RENAME_NOREPLACE)
    except FileExistsError as error:
        raise OutputLayoutInventoryError(f"receipt path appeared during persistence: {receipt_path}") from error
    except OSError as error:
        raise OutputLayoutInventoryError(f"initial receipt publication failed: {receipt_path}") from error


def _fsync_parent(parent_descriptor: int, parent: Path, fsync_operation: Callable[[int], None]) -> None:
    try:
        fsync_operation(parent_descriptor)
    except OSError as error:
        raise OutputLayoutInventoryError(f"unable to fsync receipt parent: {parent}") from error


def _close(descriptor: int, context: str) -> None:
    try:
        os.close(descriptor)
    except OSError as error:
        raise OutputLayoutInventoryError(context) from error


def _parent_identity(parent_descriptor: int, parent: Path) -> tuple[int, int]:
    try:
        parent_stat = os.fstat(parent_descriptor)
    except OSError as error:
        raise OutputLayoutInventoryError(f"unable to stat receipt parent: {parent}") from error
    return parent_stat.st_dev, parent_stat.st_ino


def _require_same_parent_path(parent: Path, expected_identity: tuple[int, int]) -> None:
    try:
        current_stat = parent.lstat()
    except OSError as error:
        raise OutputLayoutInventoryError(f"receipt parent changed during persistence: {parent}") from error
    if not stat.S_ISDIR(current_stat.st_mode) or (current_stat.st_dev, current_stat.st_ino) != expected_identity:
        raise OutputLayoutInventoryError(f"receipt parent changed during persistence: {parent}")
