from __future__ import annotations

from typing import Final


# The protected frozen-selection tree has 322,983 entries and 6,633,150,947
# bytes. Snapshots rescan directory entries after hashing to detect races.
MAX_TREE_ENTRIES: Final = 1_000_000
MAX_TREE_BYTES: Final = 16 * 1024 * 1024 * 1024


class TraversalBudget:
    def __init__(self, entry_limit: int, byte_limit: int) -> None:
        self._entry_limit: int = entry_limit
        self._byte_limit: int = byte_limit
        self._entries: int = 0
        self._bytes: int = 0

    def account_entry(self) -> None:
        self._entries += 1
        if self._entries > self._entry_limit:
            raise OSError("tree traversal work budget exceeded")

    def account_bytes(self, count: int) -> None:
        self._bytes += count
        if self._bytes > self._byte_limit:
            raise OSError("tree traversal byte budget exceeded")

    def next_read_size(self, requested: int, remaining_file_bytes: int) -> int:
        allowance = self._byte_limit - self._bytes
        if remaining_file_bytes > 0 and allowance <= 0:
            raise OSError("tree traversal byte budget exceeded")
        return min(requested, remaining_file_bytes, allowance)
