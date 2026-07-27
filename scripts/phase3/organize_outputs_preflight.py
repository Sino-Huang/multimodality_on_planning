from __future__ import annotations

from pathlib import Path

from .organize_outputs_inventory import CurrentOutputInventoryError, validate_current_output_inventory
from .output_layout_contracts import DEFAULT_OUTPUT_LAYOUT, validate_inventory_roots, validate_output_layout
from .output_layout_inventory import OutputLayoutInventoryError, snapshot_tree
from .output_layout_rename import OutputLayoutRenameError, validate_real_path
from .output_layout_writer_detection import find_overlapping_writer
from .output_layout_writer_registry import WriterDetectionError


class OrganizerPreflightError(RuntimeError):
    def __init__(self, rule: str, path: Path) -> None:
        self.rule = rule
        self.path = path
        super().__init__(f"{rule}: {path}")


def preflight(repository: Path, receipt_path: Path) -> None:
    validate_output_layout(DEFAULT_OUTPUT_LAYOUT)
    roots = tuple((*[root.path for root in DEFAULT_OUTPUT_LAYOUT.protected_roots], *[item.source for item in DEFAULT_OUTPUT_LAYOUT.relocations]))
    validate_inventory_roots(DEFAULT_OUTPUT_LAYOUT, roots)
    try:
        validate_current_output_inventory(repository)
    except CurrentOutputInventoryError as error:
        raise OrganizerPreflightError(error.rule, error.path) from error
    for root in DEFAULT_OUTPUT_LAYOUT.protected_roots:
        _snapshot(repository / root.path.value)
    for item in DEFAULT_OUTPUT_LAYOUT.relocations:
        source = repository / item.source.value
        destination = repository / item.destination.value
        _snapshot(source)
        if _lexists(destination):
            raise OrganizerPreflightError("destination collision before prepared receipt", destination)
        try:
            validate_real_path(destination.parent, allow_missing=True)
        except OutputLayoutRenameError as error:
            raise OrganizerPreflightError(error.rule, destination.parent) from error
    try:
        validate_real_path(receipt_path.parent, allow_missing=True)
    except OutputLayoutRenameError as error:
        raise OrganizerPreflightError(error.rule, receipt_path.parent) from error


def reject_uncooperative_writers(source: Path, proc_root: Path = Path("/proc")) -> None:
    try:
        overlap = find_overlapping_writer(source, proc_root=proc_root)
    except WriterDetectionError as error:
        raise OrganizerPreflightError(error.rule, source) from error
    if overlap is not None:
        raise OrganizerPreflightError("uncooperative generator writes relocation source", source)


def _snapshot(path: Path) -> None:
    try:
        _ = snapshot_tree(path)
    except OutputLayoutInventoryError as error:
        raise OrganizerPreflightError("required root is not a real readable tree", path) from error


def _lexists(path: Path) -> bool:
    try:
        _ = path.lstat()
    except FileNotFoundError:
        return False
    return True
