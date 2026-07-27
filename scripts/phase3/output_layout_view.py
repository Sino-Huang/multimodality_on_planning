from __future__ import annotations

import os
from pathlib import Path

from . import output_layout_view_fs
from . import output_layout_view_stage
from .output_layout_contracts import VIEW_ROOT
from .output_layout_view_plan import OUTPUT_LAYOUT_VIEW_LINKS, PreflightPlan, preflight
from .output_layout_view_content import protected_content_token
from .output_layout_view_types import OutputLayoutViewError, OutputLayoutViewLink, OutputLayoutViewViolation, PinnedPath


_preflight = preflight
_PinnedPath = PinnedPath
_PreflightPlan = PreflightPlan
__all__ = ("OUTPUT_LAYOUT_VIEW_LINKS", "OutputLayoutViewError", "OutputLayoutViewLink", "OutputLayoutViewViolation", "PinnedPath", "create_output_layout_view")


def create_output_layout_view(repo_root: Path) -> None:
    """Create or verify the immutable Phase 3 navigation symlink view."""
    repository = _repository_root(repo_root)
    plan = _preflight(repository)
    outputs_root = repository / "outputs"
    try:
        outputs_descriptor = output_layout_view_fs.open_repository(outputs_root)
    except OSError as error:
        raise OutputLayoutViewError((OutputLayoutViewViolation("outputs root changed after preflight", outputs_root),)) from error
    try:
        _revalidate_plan(outputs_descriptor, outputs_root, plan)
        if len(plan.existing_destinations) == len(plan.links):
            existing = output_layout_view_stage.open_existing(
                outputs_descriptor,
                Path(VIEW_ROOT).relative_to("outputs"),
            )
            try:
                output_layout_view_stage.validate_tree(existing, plan.links)
                _verify_all_links(outputs_descriptor, outputs_root, plan, [])
                output_layout_view_stage.validate_tree(existing, plan.links)
                output_layout_view_stage.validate_published_pathname(existing)
                output_layout_view_stage.validate_tree(existing, plan.links)
            finally:
                os.close(existing.descriptor)
                os.close(existing.parent_descriptor)
            return
        if plan.existing_destinations:
            raise OutputLayoutViewError((OutputLayoutViewViolation("canonical view is incomplete", outputs_root / VIEW_ROOT),))
        root = Path(VIEW_ROOT).relative_to("outputs")
        parent_descriptor, suffix = output_layout_view_stage.locate_missing_ancestor(outputs_descriptor, root)
        stage: output_layout_view_stage.PrivateStage | None = None
        published: output_layout_view_stage.PublishedStage | None = None
        interrupted = False
        failed = True
        try:
            stage = output_layout_view_stage.create_private_stage(parent_descriptor, suffix)
            _revalidate_plan(outputs_descriptor, outputs_root, plan)
            stage = output_layout_view_stage.create_tree(
                stage, plan.links, lambda: _revalidate_plan(outputs_descriptor, outputs_root, plan)
            )
            _revalidate_plan(outputs_descriptor, outputs_root, plan)
            output_layout_view_stage.validate_tree(stage, plan.links)
            _revalidate_plan(outputs_descriptor, outputs_root, plan)
            output_layout_view_stage.fsync_tree(stage)
            _revalidate_plan(outputs_descriptor, outputs_root, plan)
            output_layout_view_stage.validate_tree(stage, plan.links)
            _revalidate_plan(outputs_descriptor, outputs_root, plan)
            published = output_layout_view_stage.publish(stage, suffix.parts[0])
            output_layout_view_stage.validate_tree(published, plan.links)
            _verify_all_links(outputs_descriptor, outputs_root, plan, [])
            output_layout_view_stage.fsync_published_parent(published)
            output_layout_view_stage.validate_tree(published, plan.links)
            _verify_all_links(outputs_descriptor, outputs_root, plan, [])
            output_layout_view_stage.validate_published_pathname(published)
            output_layout_view_stage.validate_tree(published, plan.links)
            failed = False
        except output_layout_view_stage.StageConstructionError as error:
            stage = error.stage
            raise
        except KeyboardInterrupt:
            interrupted = True
            raise
        finally:
            if published is not None:
                os.close(published.descriptor)
            if stage is not None:
                try:
                    if failed:
                        output_layout_view_stage.cleanup(stage)
                except OSError:
                    if not interrupted and not failed:
                        raise
                finally:
                    os.close(stage.descriptor)
            os.close(parent_descriptor)
    except (OSError, OutputLayoutViewError) as error:
        violations = _failure_violations(error, repository)
        raise OutputLayoutViewError(violations) from error
    finally:
        os.close(outputs_descriptor)


def _repository_root(repo_root: Path) -> Path:
    try:
        repository = repo_root.resolve(strict=True)
    except (FileNotFoundError, RuntimeError) as error:
        raise OutputLayoutViewError((OutputLayoutViewViolation("repository root is unavailable", repo_root),)) from error
    if not repository.is_dir():
        raise OutputLayoutViewError((OutputLayoutViewViolation("repository root is not a directory", repo_root),))
    return repository


def _revalidate_plan(outputs_descriptor: int, outputs_root: Path, plan: PreflightPlan) -> None:
    outputs_status = os.fstat(outputs_descriptor)
    outputs_pin = plan.pinned_paths[0]
    if not outputs_pin.matches(outputs_status) or not outputs_pin.matches(outputs_root.lstat()):
        raise OutputLayoutViewError((OutputLayoutViewViolation("outputs root changed after preflight", outputs_pin.path),))
    violations: list[OutputLayoutViewViolation] = []
    for pinned in plan.pinned_paths[1:]:
        try:
            status = output_layout_view_fs.stat_path(outputs_descriptor, outputs_root, pinned.path)
        except OSError:
            violations.append(OutputLayoutViewViolation(_pin_change_rule(outputs_root, pinned), pinned.path))
            continue
        content_token = protected_content_token(pinned.path) if pinned.content_token is not None else None
        if not pinned.matches(status, content_token):
            violations.append(OutputLayoutViewViolation(_pin_change_rule(outputs_root, pinned), pinned.path))
    if violations:
        raise OutputLayoutViewError(tuple(violations))


def _verify_all_links(
    outputs_descriptor: int,
    outputs_root: Path,
    plan: PreflightPlan,
    created_directories: list[output_layout_view_fs.OwnedViewPath],
) -> None:
    _revalidate_plan(outputs_descriptor, outputs_root, plan)
    _verify_created_directories(outputs_descriptor, outputs_root, created_directories)
    target_pins = {pinned.path: pinned for pinned in plan.pinned_paths}
    for entry in plan.links:
        target = outputs_root.parent / entry.protected_target
        output_layout_view_fs.verify_symlink(outputs_descriptor, outputs_root, entry, target_pins[target])
    _verify_created_directories(outputs_descriptor, outputs_root, created_directories)
    _revalidate_plan(outputs_descriptor, outputs_root, plan)


def _verify_created_directories(
    outputs_descriptor: int,
    outputs_root: Path,
    created_directories: list[output_layout_view_fs.OwnedViewPath],
) -> None:
    for directory in created_directories:
        output_layout_view_fs.verify_owned_directory(outputs_descriptor, outputs_root, directory)


def _failure_violations(
    error: OSError | OutputLayoutViewError,
    repository: Path,
) -> tuple[OutputLayoutViewViolation, ...]:
    primary = error.violations if isinstance(error, OutputLayoutViewError) else (
        OutputLayoutViewViolation("filesystem mutation failed", repository),
    )
    return primary


def _pin_change_rule(outputs_root: Path, pinned: PinnedPath) -> str:
    target_paths = {outputs_root.parent / entry.protected_target for entry in OUTPUT_LAYOUT_VIEW_LINKS}
    if pinned.path in target_paths:
        return "protected target changed during creation"
    return "preflight path changed during creation"
