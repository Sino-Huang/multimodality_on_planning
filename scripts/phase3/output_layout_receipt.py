from __future__ import annotations

import hashlib
import io
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path

from .output_layout_inventory_types import OutputLayoutInventoryError, ReceiptInputValue, ReceiptRecord, ReceiptValue
from .output_layout_receipt_fs import ExchangeOperation, atomic_exchange as _atomic_exchange, read_content_token as _read_content_token
from .output_layout_receipt_io import close_descriptor as _close_descriptor
from .output_layout_receipt_io import open_parent_directory as _open_parent_directory
from .output_layout_receipt_io import open_receipt as _open_receipt
from .output_layout_receipt_transaction import persist_receipt
from .output_layout_receipt_values import load_receipt_record, parse_receipt_record


def seal_receipt(payload: Mapping[str, ReceiptInputValue]) -> ReceiptRecord:
    receipt = parse_receipt_record(payload)
    if "receipt_sha256" in receipt:
        raise OutputLayoutInventoryError("receipt payload must not predefine receipt_sha256")
    receipt["receipt_sha256"] = hashlib.sha256(_canonical_json(receipt)).hexdigest()
    return receipt


def read_receipt(receipt_path: Path) -> ReceiptRecord:
    parent_descriptor = _open_parent_directory(receipt_path.parent)
    try:
        descriptor = _open_receipt(parent_descriptor, receipt_path.name, receipt_path)
        try:
            return _read_receipt_descriptor(descriptor, receipt_path)
        finally:
            _close_descriptor(descriptor, f"unable to close receipt descriptor: {receipt_path}")
    finally:
        _close_descriptor(parent_descriptor, f"unable to close receipt parent: {receipt_path.parent}")


def write_receipt(
    receipt_path: Path,
    receipt: Mapping[str, ReceiptInputValue],
    *,
    fsync_operation: Callable[[int], None] = os.fsync,
    exchange_operation: ExchangeOperation = _atomic_exchange,
) -> None:
    contents = _canonical_json(_validate_receipt(receipt)) + b"\n"
    parent = receipt_path.parent
    parent_descriptor = _open_parent_directory(parent)
    try:
        persist_receipt(parent_descriptor, parent, receipt_path, contents, fsync_operation, exchange_operation)
    finally:
        _close_descriptor(parent_descriptor, f"unable to close receipt parent: {parent}")


def _read_receipt_descriptor(descriptor: int, receipt_path: Path) -> ReceiptRecord:
    try:
        initial_token, contents = _read_content_token(descriptor)
        with io.TextIOWrapper(io.BytesIO(contents), encoding="utf-8") as handle:
            decoded = load_receipt_record(handle)
        final_token, _ = _read_content_token(descriptor)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise OutputLayoutInventoryError(f"invalid receipt JSON: {receipt_path}") from error
    except OSError as error:
        raise OutputLayoutInventoryError(f"unable to read receipt: {receipt_path}") from error
    if final_token != initial_token:
        raise OutputLayoutInventoryError(f"receipt changed during read: {receipt_path}")
    return _validate_parsed_receipt(decoded)


def _validate_receipt(receipt: Mapping[str, ReceiptInputValue]) -> ReceiptRecord:
    return _validate_parsed_receipt(parse_receipt_record(receipt))


def _validate_parsed_receipt(receipt: ReceiptRecord) -> ReceiptRecord:
    candidate = dict(receipt)
    supplied_hash = candidate.pop("receipt_sha256", None)
    if not isinstance(supplied_hash, str) or len(supplied_hash) != 64:
        raise OutputLayoutInventoryError("receipt_sha256 must be lowercase SHA-256")
    if supplied_hash.lower() != supplied_hash or any(character not in "0123456789abcdef" for character in supplied_hash):
        raise OutputLayoutInventoryError("receipt_sha256 must be lowercase SHA-256")
    if supplied_hash != hashlib.sha256(_canonical_json(candidate)).hexdigest():
        raise OutputLayoutInventoryError("receipt_sha256 does not match canonical receipt content")
    candidate["receipt_sha256"] = supplied_hash
    return candidate


def _canonical_json(receipt: Mapping[str, ReceiptValue]) -> bytes:
    return json.dumps(receipt, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
