from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_view_fs


def test_rollback_reports_every_owned_directory_cleanup_failure(tmp_path: Path) -> None:
    # Given: two locally-owned directories that cannot be removed because each has a child.
    root = tmp_path / "outputs"
    root.mkdir()
    first = root / "first"
    second = root / "second"
    descriptor = output_layout_view_fs.open_repository(root)
    try:
        first_owned = output_layout_view_fs.create_directory(descriptor, root, first)
        second_owned = output_layout_view_fs.create_directory(descriptor, root, second)
        (first / "child").write_text("racer content\n", encoding="utf-8")
        (second / "child").write_text("racer content\n", encoding="utf-8")

        # When: rollback attempts every owned directory.
        report = output_layout_view_fs.rollback(descriptor, root, [], [first_owned, second_owned])

        # Then: both failures are visible rather than silently suppressed.
        assert tuple(failure.path for failure in report.failures) == (second, first)
    finally:
        os.close(descriptor)


def test_rollback_treats_missing_owned_path_as_idempotent_success(tmp_path: Path) -> None:
    # Given: a locally-owned directory that has already been removed.
    root = tmp_path / "outputs"
    root.mkdir()
    destination = root / "created"
    descriptor = output_layout_view_fs.open_repository(root)
    try:
        owned = output_layout_view_fs.create_directory(descriptor, root, destination)
        destination.rmdir()

        # When: rollback revisits the missing path.
        report = output_layout_view_fs.rollback(descriptor, root, [], [owned])

        # Then: the missing path is a clean idempotent result.
        assert report.failures == ()
    finally:
        os.close(descriptor)


def test_rollback_preserves_replaced_symlink_owned_by_a_racer(tmp_path: Path) -> None:
    # Given: a locally-created link that a racer has replaced.
    root = tmp_path / "outputs"
    root.mkdir()
    destination = root / "record"
    descriptor = output_layout_view_fs.open_repository(root)
    try:
        owned = output_layout_view_fs.create_symlink(descriptor, root, destination, "approved")
        destination.unlink()
        destination.symlink_to("racer-owned")

        # When: rollback reaches a directly published final name.
        report = output_layout_view_fs.rollback(descriptor, root, [owned], [])

        # Then: it leaves the racer object intact and reports retained cleanup evidence.
        assert tuple(failure.operation for failure in report.failures) == ("retain published view entry",)
        assert destination.is_symlink()
        assert os.readlink(destination) == "racer-owned"
    finally:
        os.close(descriptor)


def test_creation_failure_after_publish_does_not_orphan_untracked_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a post-create verification stat that fails after namespace publication.
    root = tmp_path / "outputs"
    root.mkdir()
    destination = root / "record"
    descriptor = output_layout_view_fs.open_repository(root)

    def fail_ownership_capture(
        _path: Path,
        _status: os.stat_result,
    ) -> output_layout_view_fs.OwnedViewPath:
        raise OSError("synthetic verification failure")

    try:
        monkeypatch.setattr(output_layout_view_fs, "_owned", fail_ownership_capture)

        # When: post-create verification cannot collect ownership.
        # Then: publication is retained with an explicit fail-closed receipt.
        with pytest.raises(output_layout_view_fs.ViewCleanupError, match="synthetic verification failure") as error_info:
            output_layout_view_fs.create_symlink(descriptor, root, destination, "approved")
        assert not destination.exists()
        assert destination.is_symlink()
        assert tuple(failure.operation for failure in error_info.value.failures) == ("retain published view entry",)
    finally:
        os.close(descriptor)


def test_rollback_does_not_unlink_a_racer_replacement_after_ownership_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a racer replaces an owned symlink immediately after rollback observes it.
    root = tmp_path / "outputs"
    root.mkdir()
    destination = root / "record"
    descriptor = output_layout_view_fs.open_repository(root)
    original_renameat2 = output_layout_view_fs._renameat2
    raced = False

    def replace_before_exchange(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
        flags: int,
    ) -> None:
        nonlocal raced
        if source_name == destination.name and flags == output_layout_view_fs._RENAME_EXCHANGE and not raced:
            raced = True
            destination.unlink()
            destination.symlink_to("racer-owned")
        original_renameat2(parent_descriptor, source_name, destination_name, flags)

    try:
        owned = output_layout_view_fs.create_symlink(descriptor, root, destination, "approved")
        monkeypatch.setattr(output_layout_view_fs, "_renameat2", replace_before_exchange)

        # When: rollback encounters the replacement during its ownership protocol.
        # Then: the direct publication remains intact and cleanup reports retention.
        report = output_layout_view_fs.rollback(descriptor, root, [owned], [])
        assert tuple(failure.operation for failure in report.failures) == ("retain published view entry",)
        assert destination.is_symlink()
        assert os.readlink(destination) == "approved"
    finally:
        os.close(descriptor)


def test_rollback_retains_final_name_replaced_after_exchange_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a racer installs its own link immediately before legacy cleanup unlinks the public name.
    root = tmp_path / "outputs"
    root.mkdir()
    destination = root / "record"
    descriptor = output_layout_view_fs.open_repository(root)
    original_unlink = output_layout_view_fs.os.unlink
    raced = False

    def replace_final_name(name: str, *, dir_fd: int | None = None) -> None:
        nonlocal raced
        if name == destination.name and not raced:
            raced = True
            original_unlink(name, dir_fd=dir_fd)
            os.symlink("racer-owned", name, dir_fd=dir_fd)
        original_unlink(name, dir_fd=dir_fd)

    try:
        owned = output_layout_view_fs.create_symlink(descriptor, root, destination, "approved")
        monkeypatch.setattr(output_layout_view_fs.os, "unlink", replace_final_name)

        # When: rollback reaches its legacy public-name unlink seam.
        output_layout_view_fs.rollback(descriptor, root, [owned], [])

        # Then: either the direct-publication implementation retained its link, or a raced link survived.
        assert destination.is_symlink()
        assert os.readlink(destination) == ("racer-owned" if raced else "approved")
    finally:
        os.close(descriptor)


def test_staged_name_replacement_cannot_publish_a_racer_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a racer can replace the old staged pathname before RENAME_NOREPLACE.
    root = tmp_path / "outputs"
    root.mkdir()
    destination = root / "record"
    descriptor = output_layout_view_fs.open_repository(root)
    original_renameat2 = output_layout_view_fs._renameat2

    def replace_stage_before_publish(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
        flags: int,
    ) -> None:
        if flags == output_layout_view_fs._RENAME_NOREPLACE:
            os.unlink(source_name, dir_fd=parent_descriptor)
            os.symlink("racer-owned", source_name, dir_fd=parent_descriptor)
        original_renameat2(parent_descriptor, source_name, destination_name, flags)

    try:
        monkeypatch.setattr(output_layout_view_fs, "_renameat2", replace_stage_before_publish)

        # When: a symlink is published while the stage name is adversarially replaced.
        output_layout_view_fs.create_symlink(descriptor, root, destination, "approved")

        # Then: the final link always contains the requested target rather than the racer object.
        assert os.readlink(destination) == "approved"
    finally:
        os.close(descriptor)


def test_descriptor_walker_rejects_parent_component_without_outside_mutation(tmp_path: Path) -> None:
    # Given: a descriptor rooted at a real output directory.
    root = tmp_path / "outputs"
    outside = tmp_path / "outside"
    root.mkdir()
    descriptor = output_layout_view_fs.open_repository(root)
    try:
        # When: descriptor traversal receives a parent component.
        with pytest.raises(OSError):
            output_layout_view_fs.create_directory(descriptor, root, root / ".." / outside.name)

        # Then: it does not mutate outside the descriptor root.
        assert not outside.exists()
    finally:
        os.close(descriptor)


def test_descriptor_walker_rejects_repository_root_current_component(tmp_path: Path) -> None:
    # Given: a descriptor rooted at a real output directory.
    root = tmp_path / "outputs"
    root.mkdir()
    descriptor = output_layout_view_fs.open_repository(root)
    try:
        # When: descriptor traversal receives the root itself as a current component.
        with pytest.raises(OSError):
            output_layout_view_fs._open_parent(descriptor, root, root)

        # Then: it does not return a descriptor for the repository root as an entry.
    finally:
        os.close(descriptor)
