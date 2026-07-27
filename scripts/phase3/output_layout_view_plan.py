from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .output_layout_contracts import DEFAULT_OUTPUT_LAYOUT, VIEW_ROOT, ViewTargetKind, validate_output_layout
from .output_layout_view_content import protected_content_token
from .output_layout_view_types import (
    OutputLayoutViewError,
    OutputLayoutViewLink,
    OutputLayoutViewViolation,
    PinnedPath,
)


OUTPUT_LAYOUT_VIEW_LINKS: Final = tuple(
    OutputLayoutViewLink(
        location=Path(link.link.value).relative_to(VIEW_ROOT),
        protected_target=Path(link.target.value),
        readlink_target=link.readlink_target,
        target_kind=link.target_kind,
    )
    for link in DEFAULT_OUTPUT_LAYOUT.view_links
)


@dataclass(frozen=True, slots=True)
class PreflightPlan:
    directories: tuple[Path, ...]
    links: tuple[OutputLayoutViewLink, ...]
    pinned_paths: tuple[PinnedPath, ...]
    existing_destinations: frozenset[Path]


def preflight(repository: Path) -> PreflightPlan:
    try:
        validate_output_layout(DEFAULT_OUTPUT_LAYOUT)
    except ValueError as error:
        raise OutputLayoutViewError((OutputLayoutViewViolation(str(error), repository),)) from error
    violations: list[OutputLayoutViewViolation] = []
    directories: list[Path] = []
    pinned_paths: list[PinnedPath] = []
    existing_destinations: set[Path] = set()
    _pin_valid_path(repository / "outputs", pinned_paths)
    for entry in OUTPUT_LAYOUT_VIEW_LINKS:
        target = repository / entry.protected_target
        destination = repository / VIEW_ROOT / entry.location
        _collect_target(repository, target, entry, pinned_paths, violations)
        _collect_destination_ancestors(repository, destination.parent, directories, pinned_paths, violations)
        if _lexists(destination):
            violation = _matching_link(destination, target, entry)
            if violation is not None:
                violations.append(violation)
            else:
                _pin_valid_path(destination, pinned_paths)
                existing_destinations.add(destination)
    _raise_if_invalid(tuple(violations))
    return PreflightPlan(tuple(directories), OUTPUT_LAYOUT_VIEW_LINKS, tuple(pinned_paths), frozenset(existing_destinations))


def _collect_target(
    repository: Path,
    target: Path,
    entry: OutputLayoutViewLink,
    pinned_paths: list[PinnedPath],
    violations: list[OutputLayoutViewViolation],
) -> None:
    violation = _protected_target_violation(repository, target, entry)
    if violation is not None:
        violations.append(violation)
        return
    for ancestor in _ancestors(repository, target.parent):
        _pin_valid_path(ancestor, pinned_paths)
    try:
        _pin_valid_path(target, pinned_paths, protected_content_token(target))
    except OSError:
        violations.append(OutputLayoutViewViolation("protected target changed during tokenization", target))


def _collect_destination_ancestors(
    repository: Path,
    endpoint: Path,
    directories: list[Path],
    pinned_paths: list[PinnedPath],
    violations: list[OutputLayoutViewViolation],
) -> None:
    for ancestor in _ancestors(repository, endpoint):
        if not _lexists(ancestor):
            if ancestor not in directories:
                directories.append(ancestor)
            continue
        status = ancestor.lstat()
        if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
            violations.append(OutputLayoutViewViolation("destination ancestor is not a real directory", ancestor))
            continue
        _pin_valid_path(ancestor, pinned_paths)


def _protected_target_violation(
    repository: Path,
    target: Path,
    entry: OutputLayoutViewLink,
) -> OutputLayoutViewViolation | None:
    if not target.is_relative_to(repository):
        return OutputLayoutViewViolation("protected target escapes repository", target)
    for ancestor in _ancestors(repository, target.parent):
        if not _lexists(ancestor):
            return OutputLayoutViewViolation("protected target ancestor is missing", ancestor)
        status = ancestor.lstat()
        if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
            return OutputLayoutViewViolation("protected target ancestor is not a real directory", ancestor)
    if not _lexists(target):
        return OutputLayoutViewViolation("protected target is missing", target)
    status = target.lstat()
    if stat.S_ISLNK(status.st_mode):
        return OutputLayoutViewViolation("protected target must not be a symlink", target)
    if _has_expected_kind(status, entry.target_kind):
        return None
    return OutputLayoutViewViolation("protected target has wrong kind", target)


def _has_expected_kind(status: os.stat_result, target_kind: ViewTargetKind) -> bool:
    return stat.S_ISDIR(status.st_mode) if target_kind == "directory" else stat.S_ISREG(status.st_mode)


def _matching_link(destination: Path, target: Path, entry: OutputLayoutViewLink) -> OutputLayoutViewViolation | None:
    status = destination.lstat()
    if not stat.S_ISLNK(status.st_mode):
        return OutputLayoutViewViolation("destination collision is not a symlink", destination)
    stored_target = os.readlink(destination)
    if Path(stored_target).is_absolute():
        return OutputLayoutViewViolation("destination symlink is absolute", destination)
    if stored_target != entry.readlink_target:
        return OutputLayoutViewViolation("destination symlink text differs", destination)
    try:
        resolved = destination.resolve(strict=True)
        expected = target.resolve(strict=True)
    except (FileNotFoundError, RuntimeError) as error:
        return OutputLayoutViewViolation("destination symlink cannot resolve", Path(str(error)))
    if resolved != expected:
        return OutputLayoutViewViolation("destination symlink resolves unexpectedly", destination)
    return None


def _ancestors(repository: Path, endpoint: Path) -> tuple[Path, ...]:
    current = repository
    ancestors: list[Path] = []
    for part in endpoint.relative_to(repository).parts:
        current /= part
        ancestors.append(current)
    return tuple(ancestors)


def _lexists(path: Path) -> bool:
    try:
        _ = path.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return False
    return True


def _pin_valid_path(path: Path, pinned_paths: list[PinnedPath], content_token: bytes | None = None) -> None:
    if path not in {pinned.path for pinned in pinned_paths}:
        pinned_paths.append(PinnedPath.from_status(path, path.lstat(), content_token))


def _raise_if_invalid(violations: tuple[OutputLayoutViewViolation, ...]) -> None:
    if violations:
        raise OutputLayoutViewError(violations)
