from __future__ import annotations

import os
from pathlib import Path

from .output_layout_contracts import VIEW_ROOT
from .output_layout_view_plan import preflight
from .output_layout_view_types import OutputLayoutViewError


class OrganizerViewError(RuntimeError):
    pass


def verify_exact_view(repository: Path) -> None:
    try:
        plan = preflight(repository)
    except OutputLayoutViewError as error:
        raise OrganizerViewError("view links are invalid") from error
    if len(plan.existing_destinations) != len(plan.links):
        raise OrganizerViewError("view is incomplete")
    root = repository / VIEW_ROOT
    expected = {entry.location for entry in plan.links}
    expected.update(parent for entry in plan.links for parent in entry.location.parents if parent != Path("."))
    actual = {path.relative_to(root) for path in root.rglob("*")}
    if actual != expected:
        raise OrganizerViewError("view tree has extra or missing entries")
    for entry in plan.links:
        location = root / entry.location
        if not location.is_symlink() or os.readlink(location) != entry.readlink_target:
            raise OrganizerViewError("view link text differs")
        if location.resolve(strict=True) != (repository / entry.protected_target).resolve(strict=True):
            raise OrganizerViewError("view link resolves unexpectedly")
