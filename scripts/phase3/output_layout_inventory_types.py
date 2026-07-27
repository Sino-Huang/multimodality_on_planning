from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias


ReceiptScalar: TypeAlias = str | int | float | bool | None
ReceiptInputValue: TypeAlias = ReceiptScalar | list["ReceiptInputValue"] | Mapping[str, "ReceiptInputValue"]
ReceiptValue: TypeAlias = ReceiptInputValue
ReceiptRecord: TypeAlias = dict[str, ReceiptValue]


class OutputLayoutInventoryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TreeSnapshot:
    file_count: int
    directory_count: int
    symlink_count: int
    total_bytes: int
    tree_sha256: str

    def to_record(self) -> ReceiptRecord:
        return {
            "directory_count": self.directory_count,
            "file_count": self.file_count,
            "symlink_count": self.symlink_count,
            "total_bytes": self.total_bytes,
            "tree_sha256": self.tree_sha256,
        }
