from __future__ import annotations

import os
import stat
from collections.abc import Callable
from pathlib import Path

from .output_layout_inventory_types import OutputLayoutInventoryError


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
_open_descriptor = os.open
_stat_entry = os.stat
_close_operation = os.close


def open_parent_directory(parent: Path) -> int:
    start = Path(parent.anchor) if parent.is_absolute() else Path(".")
    parts = validated_directory_components(parent.parts[1:] if parent.is_absolute() else parent.parts)
    try:
        descriptor = _open_descriptor(start, _DIRECTORY_FLAGS)
    except OSError as error:
        raise OutputLayoutInventoryError(f"receipt parent must be a real directory: {parent}") from error
    for index, part in enumerate(parts):
        try:
            component_stat = _stat_entry(part, dir_fd=descriptor, follow_symlinks=False)
        except OSError as error:
            close_descriptor(descriptor, f"receipt parent traversal failed: {parent}")
            raise OutputLayoutInventoryError(f"receipt parent must be a real directory: {parent}") from error
        if stat.S_ISLNK(component_stat.st_mode):
            close_descriptor(descriptor, f"receipt parent traversal failed: {parent}")
            rule = "receipt parent must not be a symlink" if index == len(parts) - 1 else "receipt parent must not contain symlinks"
            raise OutputLayoutInventoryError(f"{rule}: {parent}")
        try:
            next_descriptor = _open_descriptor(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
        except OSError as error:
            close_descriptor(descriptor, f"receipt parent traversal failed: {parent}")
            raise OutputLayoutInventoryError(f"receipt parent must be a real directory: {parent}") from error
        old_descriptor = descriptor
        descriptor = next_descriptor
        try:
            close_descriptor(old_descriptor, f"receipt parent traversal failed: {parent}")
        except OutputLayoutInventoryError:
            close_descriptor(next_descriptor, f"receipt parent traversal failed: {parent}")
            raise
    return descriptor


def validated_directory_components(parts: tuple[str, ...]) -> tuple[str, ...]:
    if any(part in (".", "..") for part in parts):
        raise OutputLayoutInventoryError("receipt parent components must not contain '.' or '..'")
    return parts


def open_receipt(
    parent_descriptor: int,
    receipt_name: str,
    receipt_path: Path,
    *,
    fstat_operation: Callable[[int], os.stat_result] = os.fstat,
) -> int:
    try:
        descriptor = _open_descriptor(
            receipt_name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_descriptor,
        )
    except OSError as error:
        raise OutputLayoutInventoryError(f"receipt path must be a regular file: {receipt_path}") from error
    is_valid = False
    try:
        opened_stat = fstat_operation(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise OutputLayoutInventoryError(f"receipt path must be a regular file: {receipt_path}")
        if stat.S_IMODE(opened_stat.st_mode) != 0o600:
            raise OutputLayoutInventoryError(f"receipt path must have mode 0600: {receipt_path}")
        is_valid = True
        return descriptor
    except OSError as error:
        raise OutputLayoutInventoryError(f"receipt path must be a regular file: {receipt_path}") from error
    finally:
        if not is_valid:
            close_descriptor(descriptor, f"unable to close rejected receipt: {receipt_path}")


def close_descriptor(descriptor: int, context: str) -> None:
    try:
        _close_operation(descriptor)
    except OSError as error:
        raise OutputLayoutInventoryError(context) from error
