from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_view_stage
from scripts.phase3.output_layout_view import OutputLayoutViewError, create_output_layout_view
from tests.phase3.test_output_layout_view import _seed_protected_targets


def test_post_fsync_extra_stage_entry_fails_closed_and_is_retained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an attacker can add an entry after the durable stage fsync pass.
    _seed_protected_targets(tmp_path)
    original_fsync_tree = output_layout_view_stage.fsync_tree
    stage_names: list[str] = []

    def fsync_then_add_extra(stage: output_layout_view_stage.PrivateStage) -> None:
        original_fsync_tree(stage)
        stage_names.append(stage.name)
        descriptor = os.open("racer-owned", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=stage.descriptor)
        os.close(descriptor)

    monkeypatch.setattr(output_layout_view_stage, "fsync_tree", fsync_then_add_extra)

    # When: publication follows the previously final fsync pass.
    with pytest.raises(OutputLayoutViewError, match="filesystem mutation failed"):
        create_output_layout_view(tmp_path)

    # Then: the added entry is never accepted into the public view.
    assert len(stage_names) == 1
    assert (tmp_path / "outputs" / stage_names[0] / "racer-owned").is_file()


def test_publish_returns_final_descriptor_opened_with_directory_no_follow_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a private stage ready for a final canonical publication name.
    parent_descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    stage = output_layout_view_stage.create_private_stage(parent_descriptor, Path("datasets/view"))
    original_open = output_layout_view_stage.os.open
    original_publish: Callable[[output_layout_view_stage.PrivateStage, str], output_layout_view_stage.PublishedStage] = output_layout_view_stage.publish
    final_name = "datasets"
    final_open_flags: list[int] = []
    published: output_layout_view_stage.PublishedStage | None = None

    def publish_final_stage(
        private_stage: output_layout_view_stage.PrivateStage,
        canonical_name: str,
    ) -> output_layout_view_stage.PublishedStage:
        published_stage = original_publish(private_stage, canonical_name)
        assert isinstance(published_stage, output_layout_view_stage.PublishedStage)
        return published_stage

    def record_final_open(
        name: str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if name == final_name and dir_fd == parent_descriptor:
            final_open_flags.append(flags)
        return original_open(name, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(output_layout_view_stage.os, "open", record_final_open)
    try:
        # When: the private stage is published under its canonical name.
        published = publish_final_stage(stage, final_name)

        # Then: publication pins and returns the final directory after identity validation.
        assert final_open_flags == [output_layout_view_stage._DIRECTORY_FLAGS]
        assert isinstance(published, output_layout_view_stage.PublishedStage)
        assert published.identity.matches(os.fstat(published.descriptor))
    finally:
        descriptors = {stage.descriptor}
        if isinstance(published, output_layout_view_stage.PublishedStage):
            descriptors.add(published.descriptor)
        for descriptor in descriptors:
            os.close(descriptor)
        os.close(parent_descriptor)


def test_post_publication_canonical_substitution_after_final_descriptor_acquisition_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a canonical-name substitution immediately after the final descriptor is acquired.
    _seed_protected_targets(tmp_path)
    original_open = output_layout_view_stage.os.open
    original_publish: Callable[[output_layout_view_stage.PrivateStage, str], output_layout_view_stage.PublishedStage] = output_layout_view_stage.publish
    publishing = False
    raced = False

    def publish_with_acquisition_window(
        stage: output_layout_view_stage.PrivateStage,
        final_name: str,
    ) -> output_layout_view_stage.PublishedStage:
        nonlocal publishing
        publishing = True
        try:
            published = original_publish(stage, final_name)
            assert isinstance(published, output_layout_view_stage.PublishedStage)
            return published
        finally:
            publishing = False

    def substitute_canonical_name_after_open(
        name: str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal raced
        descriptor = original_open(name, flags, mode, dir_fd=dir_fd)
        if publishing and name == "datasets" and dir_fd is not None and not raced:
            raced = True
            os.rename(name, "displaced-view", src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            os.mkdir(name, dir_fd=dir_fd)
        return descriptor

    monkeypatch.setattr(output_layout_view_stage, "publish", publish_with_acquisition_window)
    monkeypatch.setattr(output_layout_view_stage.os, "open", substitute_canonical_name_after_open)

    # When: publication continues after the final canonical name is substituted.
    with pytest.raises(OutputLayoutViewError, match="filesystem mutation failed"):
        create_output_layout_view(tmp_path)

    # Then: failure preserves both the attacker's name and the displaced published directory.
    assert raced
    assert (tmp_path / "outputs" / "datasets").is_dir()
    assert (tmp_path / "outputs" / "displaced-view").is_dir()


def test_post_publication_exact_tree_validation_uses_the_held_final_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a recorded descriptor returned from canonical publication.
    _seed_protected_targets(tmp_path)
    original_publish: Callable[[output_layout_view_stage.PrivateStage, str], output_layout_view_stage.PublishedStage] = output_layout_view_stage.publish
    original_validate_tree = output_layout_view_stage.validate_tree
    published_descriptors: set[int] = set()
    held_descriptor_validations: list[bool] = []

    def record_published_stage(
        stage: output_layout_view_stage.PrivateStage,
        final_name: str,
    ) -> output_layout_view_stage.PublishedStage:
        published = original_publish(stage, final_name)
        assert isinstance(published, output_layout_view_stage.PublishedStage)
        published_descriptors.add(published.descriptor)
        return published

    def record_held_descriptor_validation(
        stage: output_layout_view_stage.PrivateStage | output_layout_view_stage.PublishedStage,
        links: tuple[output_layout_view_stage.OutputLayoutViewLink, ...],
    ) -> None:
        original_validate_tree(stage, links)
        if stage.descriptor in published_descriptors:
            held_descriptor_validations.append(stage.identity.matches(os.fstat(stage.descriptor)))

    monkeypatch.setattr(output_layout_view_stage, "publish", record_published_stage)
    monkeypatch.setattr(output_layout_view_stage, "validate_tree", record_held_descriptor_validation)

    # When: the canonical view is published.
    create_output_layout_view(tmp_path)

    # Then: post-publication validation uses the descriptor returned by publication.
    assert held_descriptor_validations == [True, True, True]
