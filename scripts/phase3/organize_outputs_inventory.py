from __future__ import annotations

import os
import stat
from pathlib import Path, PurePosixPath
from typing import Final

from .output_layout_contracts import DEFAULT_OUTPUT_LAYOUT, OUTPUTS_DIRECTORY, validate_output_layout

__all__ = ["CurrentOutputInventoryError", "validate_current_output_inventory"]

_ALLOWED_TOP_LEVEL: Final = frozenset(("datasets", "deprecated"))


class CurrentOutputInventoryError(RuntimeError):
    """Raised when the current outputs root violates the inventory contract."""

    def __init__(self, *, rule: str, path: Path) -> None:
        self.rule: str = rule
        self.path: Path = path
        super().__init__(f"{rule}: {path}")


def validate_current_output_inventory(repository: Path) -> None:
    """Validate the immediate children of the repository's existing outputs root."""
    validate_output_layout(DEFAULT_OUTPUT_LAYOUT)
    outputs = repository / OUTPUTS_DIRECTORY
    _validate_real_directory(outputs)
    expected = {
        PurePosixPath(root.path.value).parts[1]
        for root in DEFAULT_OUTPUT_LAYOUT.protected_roots
    }
    expected.update(
        PurePosixPath(relocation.source.value).parts[1]
        for relocation in DEFAULT_OUTPUT_LAYOUT.relocations
    )
    try:
        with os.scandir(outputs) as entries:
            names = frozenset(entry.name for entry in entries)
    except OSError as error:
        raise CurrentOutputInventoryError(rule="outputs root cannot be listed", path=outputs) from error
    unknown = names - expected - _ALLOWED_TOP_LEVEL
    if unknown:
        raise CurrentOutputInventoryError(rule="unknown output root", path=outputs / sorted(unknown)[0])


def _validate_real_directory(path: Path) -> None:
    try:
        status = path.lstat()
    except OSError as error:
        raise CurrentOutputInventoryError(rule="outputs root must be a real directory", path=path) from error
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        raise CurrentOutputInventoryError(rule="outputs root must be a real directory", path=path)
