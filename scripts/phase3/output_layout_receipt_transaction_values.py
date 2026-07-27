from __future__ import annotations

import hashlib
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from .output_layout_inventory_types import OutputLayoutInventoryError, ReceiptRecord, ReceiptValue
from .output_layout_receipt_values import load_receipt_record

_HEX: Final = frozenset("0123456789abcdef")
_TRANSACTION_FIELDS: Final = frozenset(
    {
        "canonical_sha256",
        "canonical_size",
        "expected_old_sha256",
        "expected_old_size",
        "operation",
        "swap_name",
        "txid",
    }
)


@dataclass(frozen=True, slots=True)
class Digest:
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class Entry:
    digest: Digest
    contents: bytes
    permissions: int
    identity: tuple[int, int]


@dataclass(frozen=True, slots=True)
class Transaction:
    new: Digest
    old: Digest | None
    operation: Literal["create", "replace"]
    swap_name: str
    contents: bytes


def digest_bytes(contents: bytes) -> Digest:
    return Digest(hashlib.sha256(contents).hexdigest(), len(contents))


def sidecar_names(receipt_name: str) -> tuple[str, str]:
    return f".{receipt_name}.swap", f".{receipt_name}.txn"


def new_transaction(new: Digest, old: Digest | None, swap_name: str) -> Transaction:
    operation: Literal["create", "replace"] = "create" if old is None else "replace"
    record: ReceiptRecord = {
        "canonical_sha256": new.sha256,
        "canonical_size": new.size,
        "expected_old_sha256": old.sha256 if old is not None else None,
        "expected_old_size": old.size if old is not None else None,
        "operation": operation,
        "swap_name": swap_name,
        "txid": os.urandom(16).hex(),
    }
    contents = _canonical_json(record) + b"\n"
    return Transaction(new, old, operation, swap_name, contents)


def parse_transaction(contents: bytes, expected_swap_name: str, receipt_path: Path) -> Transaction:
    try:
        with io.TextIOWrapper(io.BytesIO(contents), encoding="utf-8") as handle:
            record = load_receipt_record(handle)
    except (UnicodeDecodeError, json.JSONDecodeError, OutputLayoutInventoryError, RecursionError) as error:
        raise OutputLayoutInventoryError(f"invalid receipt transaction record: {receipt_path}") from error
    if _canonical_json(record) + b"\n" != contents or frozenset(record) != _TRANSACTION_FIELDS:
        raise OutputLayoutInventoryError(f"noncanonical receipt transaction record: {receipt_path}")
    new = _record_digest(record["canonical_sha256"], record["canonical_size"], receipt_path)
    old_sha256 = record["expected_old_sha256"]
    old_size = record["expected_old_size"]
    swap_name = record["swap_name"]
    txid = record["txid"]
    if not isinstance(swap_name, str) or swap_name != expected_swap_name:
        raise OutputLayoutInventoryError(f"invalid receipt transaction record: {receipt_path}")
    if not isinstance(txid, str) or not _is_hex(txid, 32):
        raise OutputLayoutInventoryError(f"invalid receipt transaction record: {receipt_path}")
    operation = _transaction_operation(record["operation"], receipt_path)
    if operation == "create":
        if old_sha256 is not None or old_size is not None:
            raise OutputLayoutInventoryError(f"invalid receipt transaction record: {receipt_path}")
        return Transaction(new, None, operation, swap_name, contents)
    return Transaction(new, _record_digest(old_sha256, old_size, receipt_path), operation, swap_name, contents)


def _transaction_operation(value: ReceiptValue, receipt_path: Path) -> Literal["create", "replace"]:
    if value == "create":
        return "create"
    if value == "replace":
        return "replace"
    raise OutputLayoutInventoryError(f"invalid receipt transaction record: {receipt_path}")


def _record_digest(sha256: ReceiptValue, size: ReceiptValue, receipt_path: Path) -> Digest:
    if not isinstance(sha256, str) or not _is_hex(sha256, 64):
        raise OutputLayoutInventoryError(f"invalid receipt transaction record: {receipt_path}")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise OutputLayoutInventoryError(f"invalid receipt transaction record: {receipt_path}")
    return Digest(sha256, size)


def _canonical_json(record: ReceiptRecord) -> bytes:
    return json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(character in _HEX for character in value)
