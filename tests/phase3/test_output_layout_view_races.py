from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_view, output_layout_view_fs, output_layout_view_stage
from scripts.phase3.output_layout_view import OutputLayoutViewError, create_output_layout_view


VIEW_ROOT = Path("outputs/datasets/phase3/planimation/stratified_pilot_20260725")
EXPECTED_LINKS = (
    ("records/full_reasoning/train.jsonl", "outputs/phase3_planimation_frames_stratified_pilot_20260725/full_reasoning_train.jsonl", "../../../../../../phase3_planimation_frames_stratified_pilot_20260725/full_reasoning_train.jsonl", False),
    ("records/full_reasoning/dev.jsonl", "outputs/phase3_planimation_frames_stratified_pilot_20260725/full_reasoning_dev.jsonl", "../../../../../../phase3_planimation_frames_stratified_pilot_20260725/full_reasoning_dev.jsonl", False),
    ("records/full_reasoning/test.jsonl", "outputs/phase3_planimation_frames_stratified_pilot_20260725/full_reasoning_test.jsonl", "../../../../../../phase3_planimation_frames_stratified_pilot_20260725/full_reasoning_test.jsonl", False),
    ("records/step_vlm/train.jsonl", "outputs/phase3_planimation_frames_stratified_pilot_20260725/step_vlm_train.jsonl", "../../../../../../phase3_planimation_frames_stratified_pilot_20260725/step_vlm_train.jsonl", False),
    ("records/step_vlm/dev.jsonl", "outputs/phase3_planimation_frames_stratified_pilot_20260725/step_vlm_dev.jsonl", "../../../../../../phase3_planimation_frames_stratified_pilot_20260725/step_vlm_dev.jsonl", False),
    ("records/step_vlm/test.jsonl", "outputs/phase3_planimation_frames_stratified_pilot_20260725/step_vlm_test.jsonl", "../../../../../../phase3_planimation_frames_stratified_pilot_20260725/step_vlm_test.jsonl", False),
    ("records/search_traversal/train.jsonl", "outputs/phase3_planimation_frames_stratified_pilot_20260725/search_traversal_train.jsonl", "../../../../../../phase3_planimation_frames_stratified_pilot_20260725/search_traversal_train.jsonl", False),
    ("records/search_traversal/dev.jsonl", "outputs/phase3_planimation_frames_stratified_pilot_20260725/search_traversal_dev.jsonl", "../../../../../../phase3_planimation_frames_stratified_pilot_20260725/search_traversal_dev.jsonl", False),
    ("records/search_traversal/test.jsonl", "outputs/phase3_planimation_frames_stratified_pilot_20260725/search_traversal_test.jsonl", "../../../../../../phase3_planimation_frames_stratified_pilot_20260725/search_traversal_test.jsonl", False),
    ("images/state_cache", "outputs/phase3_planimation_frames_stratified_pilot_20260725/state_cache", "../../../../../phase3_planimation_frames_stratified_pilot_20260725/state_cache", True),
    ("metadata/reports", "outputs/phase3_planimation_frames_stratified_pilot_20260725/reports", "../../../../../phase3_planimation_frames_stratified_pilot_20260725/reports", True),
    ("metadata/diagnostics", "outputs/phase3_planimation_frames_stratified_pilot_20260725/diagnostics", "../../../../../phase3_planimation_frames_stratified_pilot_20260725/diagnostics", True),
    ("metadata/schema", "outputs/phase3_planimation_frames_stratified_pilot_20260725/schema", "../../../../../phase3_planimation_frames_stratified_pilot_20260725/schema", True),
    ("provenance/source_traces", "outputs/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round", "../../../../../phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round", True),
    ("provenance/frozen_selection.json", "outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800/diagnostics/rollout_selection.json", "../../../../../phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800/diagnostics/rollout_selection.json", False),
)


def _seed_protected_targets(repo_root: Path) -> None:
    for _link, target, _readlink_target, is_directory in EXPECTED_LINKS:
        target_path = repo_root / target
        if is_directory:
            target_path.mkdir(parents=True, exist_ok=True)
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text("approved\n", encoding="utf-8")


def test_protected_target_replacement_after_preflight_fails_without_view_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a protected file replaced by an outside symlink after preflight.
    _seed_protected_targets(tmp_path)
    _link, target, _readlink_target, _kind = EXPECTED_LINKS[0]
    protected_target = tmp_path / target
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    original_preflight = output_layout_view._preflight

    def replace_target_after_preflight(repository: Path):
        plan = original_preflight(repository)
        protected_target.unlink()
        protected_target.symlink_to(outside)
        return plan

    monkeypatch.setattr(output_layout_view, "_preflight", replace_target_after_preflight)

    # When: creation continues after the protected target replacement.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: no view link is accepted against the replaced target.
    assert not (tmp_path / VIEW_ROOT).exists()


def test_destination_ancestor_replacement_after_preflight_cannot_escape_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: outputs/ is replaced by a symlink after destination preflight.
    _seed_protected_targets(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    outputs = tmp_path / "outputs"
    original_outputs = tmp_path / "original-outputs"
    original_preflight = output_layout_view._preflight
    original_mkdir = Path.mkdir
    escaped_mutation = False

    def replace_outputs_after_preflight(repository: Path):
        plan = original_preflight(repository)
        outputs.rename(original_outputs)
        outputs.symlink_to(outside, target_is_directory=True)
        return plan

    def record_escaped_mkdir(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        nonlocal escaped_mutation
        if path.resolve(strict=False).is_relative_to(outside):
            escaped_mutation = True
        original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(output_layout_view, "_preflight", replace_outputs_after_preflight)
    monkeypatch.setattr(Path, "mkdir", record_escaped_mkdir)

    # When: publication starts after the ancestor replacement.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: no dataset view is created outside the repository output tree.
    assert not (outside / "datasets").exists()
    assert not escaped_mutation


def test_destination_ancestor_replacement_after_revalidation_cannot_escape_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: outputs/ is replaced inside the descriptor mutation seam.
    _seed_protected_targets(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    outputs = tmp_path / "outputs"
    original_outputs = tmp_path / "original-outputs"
    original_create_directory = output_layout_view_stage._mkdir
    raced = False

    def replace_outputs_then_create(
        repository_descriptor: int,
        path: Path,
    ) -> None:
        nonlocal raced
        if not raced:
            raced = True
            outputs.rename(original_outputs)
            outputs.symlink_to(outside, target_is_directory=True)
        original_create_directory(repository_descriptor, path)

    monkeypatch.setattr(output_layout_view_stage, "_mkdir", replace_outputs_then_create)

    # When: the first directory mutation follows the final path revalidation.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: descriptor traversal rejects the replaced ancestor without outside mutation.
    assert not (outside / "datasets").exists()


def test_real_outputs_directory_replacement_after_revalidation_is_not_mutated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: outputs/ is replaced by another real directory inside the mutation seam.
    _seed_protected_targets(tmp_path)
    outputs = tmp_path / "outputs"
    original_outputs = tmp_path / "original-outputs"
    original_create_directory = output_layout_view_stage._mkdir
    raced = False

    def replace_outputs_then_create(
        outputs_descriptor: int,
        path: Path,
    ) -> None:
        nonlocal raced
        if not raced:
            raced = True
            outputs.rename(original_outputs)
            outputs.mkdir()
        original_create_directory(outputs_descriptor, path)

    monkeypatch.setattr(output_layout_view_stage, "_mkdir", replace_outputs_then_create)

    # When: descriptor-rooted creation continues after the path replacement.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: the replacement directory remains untouched.
    assert not (outputs / "datasets").exists()


def test_protected_regular_file_replacement_after_link_verification_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a protected file replaced after link ownership verification.
    _seed_protected_targets(tmp_path)
    _link, target, _readlink_target, _kind = EXPECTED_LINKS[0]
    protected_target = tmp_path / target
    original_validate = output_layout_view_stage.validate_tree
    raced = False

    def replace_target_after_stage_validation(
        stage: output_layout_view_stage.PrivateStage,
        links: tuple[output_layout_view.OutputLayoutViewLink, ...],
    ) -> None:
        nonlocal raced
        original_validate(stage, links)
        if not raced:
            raced = True
            protected_target.unlink()
            protected_target.write_text("replacement\n", encoding="utf-8")

    monkeypatch.setattr(output_layout_view_stage, "validate_tree", replace_target_after_stage_validation)

    # When: final protected-target verification runs.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: protected drift prevents public publication.
    assert not (tmp_path / VIEW_ROOT).exists()


@pytest.mark.parametrize(
    ("walker", "limit_name", "structure"),
    (
        ("scan", "_MAX_DIRECTORY_DEPTH", "depth"),
        ("scan", "_MAX_DIRECTORY_ENTRIES", "entries"),
        ("fsync", "_MAX_DIRECTORY_DEPTH", "depth"),
        ("fsync", "_MAX_DIRECTORY_ENTRIES", "entries"),
    ),
)
def test_private_stage_walkers_reject_synthetic_depth_and_entry_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    walker: str,
    limit_name: str,
    structure: str,
) -> None:
    parent_descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    stage = output_layout_view_stage.create_private_stage(parent_descriptor, Path("datasets/view"))
    stage_path = tmp_path / stage.name
    try:
        if structure == "depth":
            (stage_path / "one" / "two").mkdir(parents=True)
        else:
            (stage_path / "one").mkdir()
            (stage_path / "two").mkdir()
        monkeypatch.setattr(output_layout_view_stage, limit_name, 1, raising=False)

        if walker == "scan":
            with pytest.raises(OSError, match="too (deep|many entries)"):
                output_layout_view_stage._scan(stage.descriptor, Path(), set(), {})
        else:
            with pytest.raises(OSError, match="too (deep|many entries)"):
                output_layout_view_stage.fsync_tree(stage)
    finally:
        os.close(stage.descriptor)
        os.close(parent_descriptor)


def test_stage_cleanup_retains_its_original_unique_name_without_quarantine_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    stage = output_layout_view_stage.create_private_stage(parent_descriptor, Path("datasets/view"))

    def reject_cleanup_mutation(*_arguments: int | str) -> None:
        raise AssertionError("cleanup must not dispatch a mutator")

    monkeypatch.setattr(output_layout_view_stage.output_layout_view_fs, "_renameat2", reject_cleanup_mutation)
    try:
        output_layout_view_stage.cleanup(stage)
        assert (tmp_path / stage.name).is_dir()
        assert not (tmp_path / f"{stage.name}.cleanup").exists()
    finally:
        os.close(stage.descriptor)
        os.close(parent_descriptor)


def test_public_final_racer_substitution_after_publish_is_not_retained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_protected_targets(tmp_path)
    original_rename = output_layout_view_fs._renameat2
    raced = False

    def publish_then_replace(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
        flags: int,
    ) -> None:
        nonlocal raced
        original_rename(parent_descriptor, source_name, destination_name, flags)
        if flags == output_layout_view_fs._RENAME_NOREPLACE and not raced:
            raced = True
            os.rename(destination_name, f"{destination_name}.owned", src_dir_fd=parent_descriptor, dst_dir_fd=parent_descriptor)
            os.mkdir(destination_name, dir_fd=parent_descriptor)

    monkeypatch.setattr(output_layout_view_fs, "_renameat2", publish_then_replace)

    with pytest.raises(OutputLayoutViewError, match="filesystem mutation failed"):
        create_output_layout_view(tmp_path)

    assert not (tmp_path / VIEW_ROOT).exists()
    assert (tmp_path / "outputs" / "datasets").is_dir()
