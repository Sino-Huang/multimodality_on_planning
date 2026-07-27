from __future__ import annotations

import os
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_view, output_layout_view_fs, output_layout_view_plan, output_layout_view_stage
from scripts.phase3.output_layout_contracts import DEFAULT_OUTPUT_LAYOUT
from scripts.phase3.output_layout_view import OUTPUT_LAYOUT_VIEW_LINKS, OutputLayoutViewError, create_output_layout_view


def _seed_targets(repository: Path) -> None:
    for link in DEFAULT_OUTPUT_LAYOUT.view_links:
        target = repository / link.target.value
        if link.target_kind == "directory":
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("approved\n", encoding="utf-8")


def _destination(repository: Path, index: int) -> Path:
    return repository / DEFAULT_OUTPUT_LAYOUT.view_links[index].link.value


def _create_all_links(repository: Path) -> None:
    for link in DEFAULT_OUTPUT_LAYOUT.view_links:
        destination = repository / link.link.value
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(link.readlink_target)


def test_catalog_mutation_is_rejected_before_view_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a complete synthetic protected tree and an altered approved contract.
    _seed_targets(tmp_path)
    altered_link = replace(DEFAULT_OUTPUT_LAYOUT.view_links[0], target_kind="directory")
    altered_layout = replace(DEFAULT_OUTPUT_LAYOUT, view_links=(altered_link, *DEFAULT_OUTPUT_LAYOUT.view_links[1:]))
    monkeypatch.setattr(output_layout_view_plan, "DEFAULT_OUTPUT_LAYOUT", altered_layout)

    # When: publication reads the mutable catalog binding.
    with pytest.raises(OutputLayoutViewError, match="approved immutable default"):
        create_output_layout_view(tmp_path)

    # Then: catalog rejection precedes every destination mutation.
    assert not (tmp_path / "outputs/datasets").exists()


def test_preexisting_link_and_parent_replacement_after_preflight_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a complete pre-existing view with a matching link and parent.
    _seed_targets(tmp_path)
    _create_all_links(tmp_path)
    destination = _destination(tmp_path, 0)
    parent = destination.parent
    replacement_parent = tmp_path / "replacement-parent"
    replacement_parent.mkdir()
    original_preflight = output_layout_view._preflight

    def replace_entries_after_preflight(repository: Path):
        plan = original_preflight(repository)
        destination.unlink()
        destination.symlink_to("racer-link")
        parent.rename(replacement_parent / "moved-parent")
        parent.mkdir()
        return plan

    monkeypatch.setattr(output_layout_view, "_preflight", replace_entries_after_preflight)

    # When: verification continues after both pre-existing objects are replaced.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: neither replacement is accepted or deleted.
    assert (replacement_parent / "moved-parent" / destination.name).is_symlink()
    assert os.readlink(replacement_parent / "moved-parent" / destination.name) == "racer-link"


def test_preexisting_parent_symlink_replacement_after_preflight_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a complete pre-existing view whose link parent is later made a symlink.
    _seed_targets(tmp_path)
    _create_all_links(tmp_path)
    parent = _destination(tmp_path, 0).parent
    outside = tmp_path / "outside"
    outside.mkdir()
    original_preflight = output_layout_view._preflight

    def replace_parent_after_preflight(repository: Path):
        plan = original_preflight(repository)
        parent.rename(tmp_path / "moved-parent")
        parent.symlink_to(outside, target_is_directory=True)
        return plan

    monkeypatch.setattr(output_layout_view, "_preflight", replace_parent_after_preflight)

    # When: creation revalidates the preflight plan.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: descriptor traversal never writes through the replacement symlink.
    assert not (outside / "train.jsonl").exists()


def test_final_verification_checks_every_preexisting_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: every matching view link already exists.
    _seed_targets(tmp_path)
    _create_all_links(tmp_path)
    observed: list[Path] = []
    original_verify = output_layout_view_fs.verify_symlink

    def record_verified_link(
        descriptor: int,
        root: Path,
        entry: output_layout_view.OutputLayoutViewLink,
        target_pin: output_layout_view.PinnedPath,
    ) -> None:
        observed.append(entry.destination(root))
        original_verify(descriptor, root, entry, target_pin)

    monkeypatch.setattr(output_layout_view_fs, "verify_symlink", record_verified_link)

    # When: all-existing view creation completes.
    create_output_layout_view(tmp_path)

    # Then: descriptor-rooted final verification includes all fifteen exact links.
    assert tuple(observed) == tuple(tmp_path / entry.link.value for entry in DEFAULT_OUTPUT_LAYOUT.view_links)


def test_existing_view_rejects_extra_entry_added_after_final_link_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a complete pre-existing view and a writer that acts after the last link check.
    _seed_targets(tmp_path)
    _create_all_links(tmp_path)
    view_root = _destination(tmp_path, 0).parents[2]
    original_verify = output_layout_view_fs.verify_symlink
    verified_links = 0

    def add_extra_after_last_link(
        descriptor: int,
        root: Path,
        entry: output_layout_view.OutputLayoutViewLink,
        target_pin: output_layout_view.PinnedPath,
    ) -> None:
        nonlocal verified_links
        original_verify(descriptor, root, entry, target_pin)
        verified_links += 1
        if verified_links == len(DEFAULT_OUTPUT_LAYOUT.view_links):
            (view_root / "racer-owned").write_text("retain\n", encoding="utf-8")

    monkeypatch.setattr(output_layout_view_fs, "verify_symlink", add_extra_after_last_link)

    # When: the idempotent existing-view path completes its per-link verification.
    with pytest.raises(OutputLayoutViewError, match="filesystem mutation failed"):
        create_output_layout_view(tmp_path)

    # Then: the unexpected entry is retained as evidence but success is rejected.
    assert (view_root / "racer-owned").read_text(encoding="utf-8") == "retain\n"


def test_existing_view_rejects_extra_entry_added_after_pathname_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a complete pre-existing view and a writer that acts after pathname validation.
    _seed_targets(tmp_path)
    _create_all_links(tmp_path)
    view_root = _destination(tmp_path, 0).parents[2]
    original_validate = output_layout_view_stage.validate_published_pathname
    pathname_validations = 0

    def add_extra_after_pathname(stage: output_layout_view_stage.PublishedStage) -> None:
        nonlocal pathname_validations
        original_validate(stage)
        pathname_validations += 1
        if pathname_validations == 2:
            (view_root / "racer-owned-after-pathname").write_text("retain\n", encoding="utf-8")

    monkeypatch.setattr(output_layout_view_stage, "validate_published_pathname", add_extra_after_pathname)

    # When: pathname validation completes before the operation returns success.
    with pytest.raises(OutputLayoutViewError, match="filesystem mutation failed"):
        create_output_layout_view(tmp_path)

    # Then: the unexpected entry is retained as evidence but success is rejected.
    assert (view_root / "racer-owned-after-pathname").read_text(encoding="utf-8") == "retain\n"


def test_new_view_rejects_extra_entry_added_after_pathname_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: protected targets and a writer that acts after publication pathname validation.
    _seed_targets(tmp_path)
    view_root = _destination(tmp_path, 0).parents[2]
    original_validate = output_layout_view_stage.validate_published_pathname

    def add_extra_after_pathname(stage: output_layout_view_stage.PublishedStage) -> None:
        original_validate(stage)
        (view_root / "racer-owned-after-new-pathname").write_text("retain\n", encoding="utf-8")

    monkeypatch.setattr(output_layout_view_stage, "validate_published_pathname", add_extra_after_pathname)

    # When: first publication completes pathname validation before reporting success.
    with pytest.raises(OutputLayoutViewError, match="filesystem mutation failed"):
        create_output_layout_view(tmp_path)

    # Then: the unexpected entry is retained as evidence but success is rejected.
    assert (view_root / "racer-owned-after-new-pathname").read_text(encoding="utf-8") == "retain\n"


def test_final_verification_rejects_created_destination_ancestor_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: private-stage construction precedes a competing final-root creation.
    _seed_targets(tmp_path)
    view_root = _destination(tmp_path, 0).parents[2]
    original_validate = output_layout_view_stage.validate_tree
    replaced = False

    def create_competing_view_root_before_publish(
        stage: output_layout_view_stage.PrivateStage,
        links: tuple[output_layout_view.OutputLayoutViewLink, ...],
    ) -> None:
        nonlocal replaced
        original_validate(stage, links)
        if not replaced:
            replaced = True
            view_root.mkdir(parents=True)
            _create_all_links(tmp_path)

    monkeypatch.setattr(
        output_layout_view_stage,
        "validate_tree",
        create_competing_view_root_before_publish,
    )

    # When: a racer claims the final root after stage construction.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: no private stage can overwrite the racer-owned final root.
    assert view_root.is_dir()


def test_final_verification_rejects_protected_target_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the first protected file is replaced during final verification.
    _seed_targets(tmp_path)
    protected_target = tmp_path / DEFAULT_OUTPUT_LAYOUT.view_links[0].target.value
    original_validate = output_layout_view_stage.validate_tree
    mutated = False

    def replace_target_during_stage_validation(
        stage: output_layout_view_stage.PrivateStage,
        links: tuple[output_layout_view.OutputLayoutViewLink, ...],
    ) -> None:
        nonlocal mutated
        original_validate(stage, links)
        if not mutated:
            mutated = True
            protected_target.unlink()
            protected_target.write_text("replacement\n", encoding="utf-8")

    monkeypatch.setattr(output_layout_view_stage, "validate_tree", replace_target_during_stage_validation)

    # When: publication reaches the final verification pass.
    with pytest.raises(OutputLayoutViewError, match="protected target changed"):
        create_output_layout_view(tmp_path)

    # Then: prepublication failure leaves no canonical view.
    assert not _destination(tmp_path, 0).exists()


def test_second_run_preserves_every_link_inode(tmp_path: Path) -> None:
    # Given: a complete synthetic view created once.
    _seed_targets(tmp_path)
    create_output_layout_view(tmp_path)
    before = tuple(_destination(tmp_path, index).lstat() for index in range(15))

    # When: the same view is requested again.
    create_output_layout_view(tmp_path)

    # Then: every pre-existing link remains the same inode.
    after = tuple(_destination(tmp_path, index).lstat() for index in range(15))
    assert tuple((entry.st_dev, entry.st_ino) for entry in after) == tuple(
        (entry.st_dev, entry.st_ino) for entry in before
    )


def test_primary_failure_aggregates_all_rollback_cleanup_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: creation fails after owned directories exist and each cleanup is blocked.
    _seed_targets(tmp_path)
    original_create = output_layout_view_stage._mkdir
    created: list[Path] = []

    def create_then_block_cleanup(descriptor: int, path: Path) -> None:
        original_create(descriptor, path)
        created.append(path)
        if len(created) == 3:
            raise OSError("primary failure")

    monkeypatch.setattr(output_layout_view_stage, "_mkdir", create_then_block_cleanup)

    # When: the primary mutation failure triggers rollback.
    with pytest.raises(OutputLayoutViewError) as error_info:
        create_output_layout_view(tmp_path)

    # Then: private cleanup removes all owned staging entries.
    rules = tuple(violation.rule for violation in error_info.value.violations)
    assert "filesystem mutation failed" in rules
    assert "filesystem mutation failed" in rules
    assert not (tmp_path / "outputs/datasets").exists()


def test_final_view_has_exact_link_text_target_identity_and_kind(tmp_path: Path) -> None:
    # Given: a complete synthetic protected output tree.
    _seed_targets(tmp_path)

    # When: the view is created.
    create_output_layout_view(tmp_path)

    # Then: every descriptor catalog entry has exact text, identity, and target kind.
    for entry in DEFAULT_OUTPUT_LAYOUT.view_links:
        destination = tmp_path / entry.link.value
        target = tmp_path / entry.target.value
        destination_status = destination.lstat()
        target_status = target.lstat()
        assert stat.S_ISLNK(destination_status.st_mode)
        assert os.readlink(destination) == entry.readlink_target
        assert destination.resolve(strict=True) == target.resolve(strict=True)
        assert stat.S_ISDIR(target_status.st_mode) == (entry.target_kind == "directory")
        assert stat.S_ISREG(target_status.st_mode) == (entry.target_kind == "file")
    assert len(OUTPUT_LAYOUT_VIEW_LINKS) == 15
