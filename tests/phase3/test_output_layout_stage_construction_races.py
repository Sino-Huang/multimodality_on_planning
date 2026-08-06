from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_view_stage
from scripts.phase3.output_layout_view import OutputLayoutViewError, create_output_layout_view
from test_output_layout_view_races import _seed_protected_targets


def test_locate_missing_ancestor_closes_duplicated_descriptor_when_child_open_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: traversal reaches an existing child whose descriptor open fails.
    (tmp_path / "datasets").mkdir()
    outputs_descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    original_close = output_layout_view_stage.os.close
    original_dup = output_layout_view_stage.os.dup
    duplicated_descriptors: list[int] = []
    closed_descriptors: list[int] = []

    def record_duplicate(descriptor: int) -> int:
        duplicate = original_dup(descriptor)
        duplicated_descriptors.append(duplicate)
        return duplicate

    def fail_child_open(
        name: str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        assert name == "datasets"
        assert flags == output_layout_view_stage._DIRECTORY_FLAGS
        assert mode == 0o777
        assert dir_fd is not None
        raise OSError("synthetic child open failure")

    def record_close(descriptor: int) -> None:
        closed_descriptors.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(output_layout_view_stage.os, "dup", record_duplicate)
    monkeypatch.setattr(output_layout_view_stage.os, "open", fail_child_open)
    monkeypatch.setattr(output_layout_view_stage.os, "close", record_close)
    try:
        # When: the pinned child descriptor cannot be opened.
        with pytest.raises(OSError, match="synthetic child open failure"):
            output_layout_view_stage.locate_missing_ancestor(outputs_descriptor, Path("datasets/view"))

        # Then: the duplicate created for the traversal is not leaked.
        assert duplicated_descriptors == closed_descriptors
    finally:
        for descriptor in duplicated_descriptors:
            if descriptor not in closed_descriptors:
                original_close(descriptor)
        original_close(outputs_descriptor)


def test_partial_private_stage_construction_preserves_primary_failure_and_only_cleans_owned_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_protected_targets(tmp_path)
    original_create_stage = output_layout_view_stage.create_private_stage
    original_symlink = output_layout_view_stage._symlink
    created_stages: list[output_layout_view_stage.PrivateStage] = []
    racer_paths: list[Path] = []

    def capture_stage(parent_descriptor: int, suffix: Path) -> output_layout_view_stage.PrivateStage:
        stage = original_create_stage(parent_descriptor, suffix)
        created_stages.append(stage)
        return stage

    def create_racer_then_fail(descriptor: int, relative: Path, target: str) -> None:
        original_symlink(descriptor, relative, target)
        racer_path = tmp_path / "outputs" / created_stages[0].name / "racer-owned"
        racer_path.write_text("retain\n", encoding="utf-8")
        racer_paths.append(racer_path)
        raise OSError("synthetic construction failure")

    monkeypatch.setattr(output_layout_view_stage, "create_private_stage", capture_stage)
    monkeypatch.setattr(output_layout_view_stage, "_symlink", create_racer_then_fail)
    with pytest.raises(OutputLayoutViewError) as error_info:
        create_output_layout_view(tmp_path)
    assert "synthetic construction failure" in str(error_info.value.__cause__)
    assert created_stages
    assert racer_paths
    assert racer_paths[0].read_text(encoding="utf-8") == "retain\n"
