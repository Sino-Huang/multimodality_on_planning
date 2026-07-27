from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final, Literal, TypeAlias

from .output_layout_contracts import DEFAULT_OUTPUT_LAYOUT, serialize_catalog
from .output_layout_inventory import ReceiptRecord, ReceiptValue, snapshot_tree


ReceiptState: TypeAlias = Literal["prepared", "complete"]
_SCHEMA: Final = "phase3_output_organization_receipt_v1"
_SNAPSHOT_KEYS: Final = frozenset(("directory_count", "file_count", "symlink_count", "total_bytes", "tree_sha256"))


class ReceiptSemanticError(RuntimeError):
    def __init__(self, rule: str) -> None:
        self.rule = rule
        super().__init__(rule)


def prepared_receipt(repository: Path) -> ReceiptRecord:
    return {
        "catalog_sha256": _catalog_hash(),
        "protected_roots": [
            {"path": root.path.value, "snapshot": snapshot_tree(repository / root.path.value).to_record()}
            for root in DEFAULT_OUTPUT_LAYOUT.protected_roots
        ],
        "relocations": [
            {
                "classification": item.classification,
                "category": item.category,
                "destination": item.destination.value,
                "destination_snapshot": None,
                "source": item.source.value,
                "source_snapshot": snapshot_tree(repository / item.source.value).to_record(),
                "status": "prepared",
            }
            for item in DEFAULT_OUTPUT_LAYOUT.relocations
        ],
        "schema_version": _SCHEMA,
        "state": "prepared",
        "view_links": [
            {
                "category": item.category,
                "link": item.link.value,
                "readlink_target": item.readlink_target,
                "target": item.target.value,
                "target_kind": item.target_kind,
            }
            for item in DEFAULT_OUTPUT_LAYOUT.view_links
        ],
    }


def validate_receipt(receipt: ReceiptRecord) -> ReceiptState:
    if set(receipt) != {"catalog_sha256", "protected_roots", "receipt_sha256", "relocations", "schema_version", "state", "view_links"}:
        raise ReceiptSemanticError("receipt has unknown or missing fields")
    if receipt["schema_version"] != _SCHEMA or receipt["catalog_sha256"] != _catalog_hash():
        raise ReceiptSemanticError("receipt does not match fixed catalog")
    state = _state(receipt["state"])
    _protected(receipt["protected_roots"])
    _relocations(receipt["relocations"], state)
    _links(receipt["view_links"])
    return state


def mark_moved(receipt: ReceiptRecord, index: int) -> None:
    relocations = receipt["relocations"]
    if not isinstance(relocations, list) or not isinstance(relocations[index], dict):
        raise ReceiptSemanticError("receipt relocation has invalid shape")
    relocation = relocations[index]
    relocation["destination_snapshot"] = relocation["source_snapshot"]
    relocation["status"] = "moved_verified"
    _ = validate_receipt(receipt)


def complete(receipt: ReceiptRecord) -> None:
    receipt["state"] = "complete"
    _ = validate_receipt(receipt)


def relocation_snapshot(receipt: ReceiptRecord, index: int) -> ReceiptRecord:
    relocations = receipt["relocations"]
    if not isinstance(relocations, list) or not isinstance(relocations[index], dict):
        raise ReceiptSemanticError("receipt relocation has invalid shape")
    snapshot = relocations[index].get("source_snapshot")
    if not isinstance(snapshot, dict):
        raise ReceiptSemanticError("receipt source snapshot has invalid shape")
    return snapshot


def relocation_status(receipt: ReceiptRecord, index: int) -> str:
    relocations = receipt["relocations"]
    if not isinstance(relocations, list) or not isinstance(relocations[index], dict):
        raise ReceiptSemanticError("receipt relocation has invalid shape")
    status = relocations[index].get("status")
    if not isinstance(status, str):
        raise ReceiptSemanticError("receipt relocation status has invalid shape")
    return status


def _catalog_hash() -> str:
    return hashlib.sha256(serialize_catalog(DEFAULT_OUTPUT_LAYOUT).encode()).hexdigest()


def _state(value: ReceiptValue) -> ReceiptState:
    if value == "prepared" or value == "complete":
        return value
    raise ReceiptSemanticError("receipt has invalid semantic state")


def _protected(value: ReceiptValue) -> None:
    expected = DEFAULT_OUTPUT_LAYOUT.protected_roots
    if not isinstance(value, list) or len(value) != len(expected):
        raise ReceiptSemanticError("receipt protected roots have invalid count")
    for entry, root in zip(value, expected, strict=True):
        if not isinstance(entry, dict) or set(entry) != {"path", "snapshot"} or entry.get("path") != root.path.value:
            raise ReceiptSemanticError("receipt protected root mapping differs")
        _snapshot(entry.get("snapshot"))


def _relocations(value: ReceiptValue, state: ReceiptState) -> None:
    expected = DEFAULT_OUTPUT_LAYOUT.relocations
    if not isinstance(value, list) or len(value) != len(expected):
        raise ReceiptSemanticError("receipt relocations have invalid count")
    for entry, item in zip(value, expected, strict=True):
        if not isinstance(entry, dict) or set(entry) != {"category", "classification", "destination", "destination_snapshot", "source", "source_snapshot", "status"}:
            raise ReceiptSemanticError("receipt relocation fields differ")
        if (entry.get("source"), entry.get("classification"), entry.get("category"), entry.get("destination")) != (item.source.value, item.classification, item.category, item.destination.value):
            raise ReceiptSemanticError("receipt relocation mapping differs")
        source_snapshot = entry.get("source_snapshot")
        _snapshot(source_snapshot)
        status = entry.get("status")
        destination_snapshot = entry.get("destination_snapshot")
        if status == "prepared" and destination_snapshot is None and state == "prepared":
            continue
        if status != "moved_verified" or destination_snapshot != source_snapshot:
            raise ReceiptSemanticError("receipt relocation transition is invalid")
    if state == "complete" and any(entry.get("status") != "moved_verified" for entry in value if isinstance(entry, dict)):
        raise ReceiptSemanticError("complete receipt has unverified relocations")


def _links(value: ReceiptValue) -> None:
    expected = DEFAULT_OUTPUT_LAYOUT.view_links
    if not isinstance(value, list) or len(value) != len(expected):
        raise ReceiptSemanticError("receipt view links have invalid count")
    for entry, item in zip(value, expected, strict=True):
        actual = (entry.get("link"), entry.get("target"), entry.get("readlink_target"), entry.get("category"), entry.get("target_kind")) if isinstance(entry, dict) else ()
        if actual != (item.link.value, item.target.value, item.readlink_target, item.category, item.target_kind):
            raise ReceiptSemanticError("receipt view link mapping differs")


def _snapshot(value: ReceiptValue) -> None:
    if not isinstance(value, dict) or set(value) != _SNAPSHOT_KEYS:
        raise ReceiptSemanticError("receipt snapshot fields differ")
    if not all(isinstance(value[key], int) and not isinstance(value[key], bool) and value[key] >= 0 for key in ("directory_count", "file_count", "symlink_count", "total_bytes")):
        raise ReceiptSemanticError("receipt snapshot counts are invalid")
    digest = value["tree_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or digest.lower() != digest or any(letter not in "0123456789abcdef" for letter in digest):
        raise ReceiptSemanticError("receipt snapshot digest is invalid")
