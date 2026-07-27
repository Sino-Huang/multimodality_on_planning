from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_view, output_layout_view_stage
from scripts.phase3.output_layout_view import (
    OUTPUT_LAYOUT_VIEW_LINKS,
    OutputLayoutViewError,
    create_output_layout_view,
)


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


def _protected_snapshot(repo_root: Path) -> tuple[tuple[str, int, int], ...]:
    entries: list[tuple[str, int, int]] = []
    protected_roots = (
        "outputs/phase3_planimation_frames_stratified_pilot_20260725",
        "outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800",
        "outputs/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round",
    )
    for root in protected_roots:
        for path in sorted((repo_root / root).rglob("*")):
            status = path.lstat()
            entries.append((path.relative_to(repo_root).as_posix(), stat.S_IFMT(status.st_mode), status.st_mtime_ns))
    return tuple(entries)


def _view_link(repo_root: Path, relative_path: str) -> Path:
    return repo_root / VIEW_ROOT / relative_path


def test_catalog_has_exact_fifteen_literal_links() -> None:
    # Given: the independent plan-derived catalog.
    expected = tuple((Path(link), Path(target), readlink_target, is_directory) for link, target, readlink_target, is_directory in EXPECTED_LINKS)

    # When: the worker exposes its immutable catalog.
    actual = tuple((entry.location, entry.protected_target, entry.readlink_target, entry.is_directory) for entry in OUTPUT_LAYOUT_VIEW_LINKS)

    # Then: every location, target, target text, and kind is exact.
    assert actual == expected


def test_real_repository_has_all_fifteen_protected_view_targets() -> None:
    repository = Path(__file__).resolve().parents[2]

    for entry in OUTPUT_LAYOUT_VIEW_LINKS:
        target = repository / entry.protected_target
        status = target.lstat()
        assert not stat.S_ISLNK(status.st_mode), target
        if entry.is_directory:
            assert stat.S_ISDIR(status.st_mode), target
        else:
            assert stat.S_ISREG(status.st_mode), target


def test_create_view_resolves_all_fifteen_relative_links(tmp_path: Path) -> None:
    # Given: a complete synthetic protected output tree and its recursive metadata snapshot.
    _seed_protected_targets(tmp_path)
    before = _protected_snapshot(tmp_path)

    # When: the structured view is created.
    create_output_layout_view(tmp_path)

    # Then: all literal links resolve to their protected targets without mutation.
    for link, target, readlink_target, _is_directory in EXPECTED_LINKS:
        destination = _view_link(tmp_path, link)
        assert os.readlink(destination) == readlink_target
        assert destination.resolve(strict=True) == (tmp_path / target).resolve(strict=True)
    assert _protected_snapshot(tmp_path) == before


@pytest.mark.parametrize("target_index,make_directory", ((0, True), (9, False)))
def test_missing_or_wrong_kind_protected_target_fails_without_view_mutation(
    tmp_path: Path, target_index: int, make_directory: bool
) -> None:
    # Given: a synthetic protected tree with one missing or wrongly typed target.
    _seed_protected_targets(tmp_path)
    _link, target, _readlink_target, _is_directory = EXPECTED_LINKS[target_index]
    target_path = tmp_path / target
    if target_path.is_dir():
        target_path.rmdir()
    else:
        target_path.unlink()
    if make_directory:
        target_path.mkdir()
    else:
        target_path.write_text("wrong kind\n", encoding="utf-8")

    # When: validation attempts to create the view.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: no destination root has been created.
    assert not (tmp_path / VIEW_ROOT).exists()


def test_symlinked_protected_target_component_fails_without_view_mutation(tmp_path: Path) -> None:
    # Given: an otherwise complete tree whose protected component is a symlink.
    _seed_protected_targets(tmp_path)
    pilot = tmp_path / "outputs/phase3_planimation_frames_stratified_pilot_20260725"
    alternate = tmp_path / "outputs/alternate_pilot"
    pilot.rename(alternate)
    pilot.symlink_to(alternate, target_is_directory=True)

    # When: validation attempts to create the view.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: no destination root has been created.
    assert not (tmp_path / VIEW_ROOT).exists()


@pytest.mark.parametrize(
    ("stored_target", "make_target"),
    (("../../../../../../wrong", False), ("/tmp/absolute", False), ("../../../../../../missing", False), ("../../../../../../../../escape", False), ("loop", True)),
)
def test_invalid_existing_link_fails_without_partial_creation(tmp_path: Path, stored_target: str, make_target: bool) -> None:
    # Given: a complete protected tree and a first destination with an invalid real symlink.
    _seed_protected_targets(tmp_path)
    destination = _view_link(tmp_path, EXPECTED_LINKS[0][0])
    destination.parent.mkdir(parents=True)
    destination.symlink_to(stored_target)
    if make_target:
        loop = destination.parent / stored_target
        loop.symlink_to(loop.name)

    # When: validation attempts to create the view.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: only the supplied invalid link remains; no later link was created.
    assert destination.is_symlink()
    assert not _view_link(tmp_path, EXPECTED_LINKS[1][0]).exists()


def test_wrong_existing_link_fails_without_partial_creation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a creator that replaces its first published link before validation.
    _seed_protected_targets(tmp_path)
    destination = _view_link(tmp_path, EXPECTED_LINKS[0][0])
    wrong_target = "../../../../../../racer-owned"
    original = output_layout_view_stage._symlink

    def replace_after_real_creation(
        repository_descriptor: int,
        destination: Path,
        target_text: str,
    ) -> None:
        original(repository_descriptor, destination, wrong_target)

    monkeypatch.setattr(output_layout_view_stage, "_symlink", replace_after_real_creation)

    # When: the replacement makes the first destination invalid.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: the invalid private link never becomes a public partial view.
    assert not destination.exists()
    assert not _view_link(tmp_path, EXPECTED_LINKS[1][0]).exists()


def test_staged_symlink_replacement_cannot_publish_regular_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a hard-link staging primitive that must not be used for publication.
    _seed_protected_targets(tmp_path)

    def reject_hard_link(
        _source: os.PathLike[str] | str,
        _destination: os.PathLike[str] | str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        del src_dir_fd, dst_dir_fd, follow_symlinks
        raise AssertionError("view publication must create the final symlink directly")

    monkeypatch.setattr(output_layout_view.os, "link", reject_hard_link)

    # When: the view is created.
    create_output_layout_view(tmp_path)

    # Then: the destination is the intended symlink without a replaceable staging name.
    destination = _view_link(tmp_path, EXPECTED_LINKS[0][0])
    assert destination.is_symlink()
    assert os.readlink(destination) == EXPECTED_LINKS[0][2]


@pytest.mark.parametrize("collision", ("file", "directory", "parent_file"))
def test_destination_collisions_fail_without_view_mutation(tmp_path: Path, collision: str) -> None:
    # Given: a complete tree with a destination or ancestor collision.
    _seed_protected_targets(tmp_path)
    destination = _view_link(tmp_path, EXPECTED_LINKS[0][0])
    if collision == "parent_file":
        destination.parent.parent.mkdir(parents=True)
        destination.parent.write_text("collision\n", encoding="utf-8")
    else:
        destination.parent.mkdir(parents=True)
        if collision == "file":
            destination.write_text("collision\n", encoding="utf-8")
        else:
            destination.mkdir()

    # When: validation attempts to create the view.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: no later destination has been created.
    assert not _view_link(tmp_path, EXPECTED_LINKS[1][0]).exists()


def test_late_collision_preflight_creates_no_partial_view(tmp_path: Path) -> None:
    # Given: a complete tree and a collision in the final destination.
    _seed_protected_targets(tmp_path)
    collision = _view_link(tmp_path, EXPECTED_LINKS[-1][0])
    collision.parent.mkdir(parents=True)
    collision.write_text("collision\n", encoding="utf-8")

    # When: validation attempts to create the view.
    with pytest.raises(OutputLayoutViewError):
        create_output_layout_view(tmp_path)

    # Then: no earlier link was created before the late rejection.
    assert not _view_link(tmp_path, EXPECTED_LINKS[0][0]).exists()


def test_matching_links_are_idempotent_and_retain_link_stat(tmp_path: Path) -> None:
    # Given: a complete protected tree and a successfully created view.
    _seed_protected_targets(tmp_path)
    create_output_layout_view(tmp_path)
    before = tuple(_view_link(tmp_path, link).lstat() for link, _target, _readlink, _kind in EXPECTED_LINKS)

    # When: the same view is requested again.
    create_output_layout_view(tmp_path)

    # Then: every pre-existing symlink identity is retained.
    after = tuple(_view_link(tmp_path, link).lstat() for link, _target, _readlink, _kind in EXPECTED_LINKS)
    assert tuple((entry.st_dev, entry.st_ino) for entry in after) == tuple((entry.st_dev, entry.st_ino) for entry in before)


def test_creation_failure_rolls_back_owned_links_and_keeps_matching_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: protected targets and one pre-existing matching entry.
    _seed_protected_targets(tmp_path)
    first_link, _first_target, first_text, _first_kind = EXPECTED_LINKS[0]
    first_destination = _view_link(tmp_path, first_link)
    first_destination.parent.mkdir(parents=True)
    first_destination.symlink_to(first_text)
    first_identity = first_destination.lstat()
    original = output_layout_view_stage._symlink
    calls = 0

    def fail_after_real_creation(
        repository_descriptor: int,
        destination: Path,
        target_text: str,
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected creation failure")
        original(repository_descriptor, destination, target_text)

    monkeypatch.setattr(output_layout_view_stage, "_symlink", fail_after_real_creation)

    # When: creation hits an injected failure after a real symlink operation.
    with pytest.raises(OutputLayoutViewError) as error_info:
        create_output_layout_view(tmp_path)

    # Then: private staging preserves the pre-existing public entry without exposing later links.
    assert first_destination.is_symlink()
    assert (first_destination.lstat().st_dev, first_destination.lstat().st_ino) == (first_identity.st_dev, first_identity.st_ino)
    assert not _view_link(tmp_path, EXPECTED_LINKS[1][0]).exists()
    assert not _view_link(tmp_path, EXPECTED_LINKS[2][0]).exists()
    assert "canonical view is incomplete" in tuple(violation.rule for violation in error_info.value.violations)
