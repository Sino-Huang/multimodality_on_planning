from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from scripts.phase3.output_layout_contracts import (
    DEFAULT_OUTPUT_LAYOUT,
    OutputLayoutContractError,
    RepositoryRelativePath,
    Relocation,
    serialize_catalog,
    validate_inventory_roots,
    validate_output_layout,
)


def test_catalog_has_exact_three_category_relocation_and_copy_topology() -> None:
    # Given: the approved immutable output-layout contract.
    contract = DEFAULT_OUTPUT_LAYOUT

    # When: its migration contract is serialized.
    catalog = serialize_catalog(contract)

    # Then: it contains precisely the approved categories, moves, and physical copies.
    assert tuple((root.category, root.path.value) for root in contract.category_roots) == (
        ("reasoning_traces", "outputs/reasoning_traces"),
        ("image_frames", "outputs/image_frames"),
        ("deprecated", "outputs/deprecated"),
    )
    assert len(contract.protected_roots) == 3
    assert len(contract.relocations) == 15
    assert len(contract.physical_record_copies) == 9
    assert tuple((root.path.value, root.rationale) for root in contract.protected_roots) == (
        ("outputs/reasoning_traces/curriculum/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round", "approved strict source traces for the pilot"),
        ("outputs/image_frames/phase3_planimation_frames_stratified_pilot_20260725", "approved 52-pair stratified pilot records and assets"),
        ("outputs/image_frames/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800", "frozen selection provenance for the approved pilot"),
    )
    assert tuple((move.category, move.source.value, move.destination.value) for move in contract.relocations) == _expected_relocations()
    assert tuple((copy.family, copy.split, copy.source.value, copy.destination.value, copy.policy) for copy in contract.physical_record_copies) == _expected_record_copies()
    assert sum(move.category == "reasoning_traces" for move in contract.relocations) == 1
    assert sum(move.category == "image_frames" for move in contract.relocations) == 2
    assert sum(move.category == "deprecated" for move in contract.relocations) == 12
    assert '"authoritativeness": "migration_contract"' in catalog
    assert "outputs/datasets" not in catalog
    assert "view_links" not in catalog
    assert "symlink" not in catalog


def test_catalog_rejects_unknown_inventory_root_without_mutating_a_dirty_worktree(tmp_path: Path) -> None:
    # Given: a test-only dirty worktree and a pre-validation digest.
    dirty_worktree = tmp_path / "dirty-worktree"
    unknown_root = dirty_worktree / "outputs" / "unapproved_run"
    unknown_root.mkdir(parents=True)
    (unknown_root / "fixture.txt").write_text("test-only fixture\n", encoding="utf-8")
    before_digest = _test_only_tree_digest(tmp_path)
    approved_sources = tuple(move.source for move in DEFAULT_OUTPUT_LAYOUT.relocations)

    # When: inventory validation receives an unknown flat source root.
    with pytest.raises(OutputLayoutContractError, match="unknown inventory root"):
        validate_inventory_roots(DEFAULT_OUTPUT_LAYOUT, (*approved_sources, RepositoryRelativePath("outputs/unapproved_run")))

    # Then: validation leaves the test-only tree unchanged.
    assert _test_only_tree_digest(tmp_path) == before_digest


def test_contract_rejects_relocation_overlapping_a_protected_destination() -> None:
    # Given: a move source that overlaps an approved live destination.
    protected_path = DEFAULT_OUTPUT_LAYOUT.protected_roots[0].path
    invalid_move = replace(DEFAULT_OUTPUT_LAYOUT.relocations[0], source=protected_path)
    invalid_contract = replace(DEFAULT_OUTPUT_LAYOUT, relocations=(invalid_move, *DEFAULT_OUTPUT_LAYOUT.relocations[1:]))

    # When: the move map is validated.
    with pytest.raises(OutputLayoutContractError, match="overlaps protected root"):
        validate_output_layout(invalid_contract)

    # Then: a move cannot consume a protected destination.


def test_contract_rejects_duplicate_relocation_destination() -> None:
    # Given: two moves with the same destination.
    first_move = DEFAULT_OUTPUT_LAYOUT.relocations[0]
    duplicate_move = replace(DEFAULT_OUTPUT_LAYOUT.relocations[1], destination=first_move.destination)
    invalid_contract = replace(DEFAULT_OUTPUT_LAYOUT, relocations=(first_move, duplicate_move, *DEFAULT_OUTPUT_LAYOUT.relocations[2:]))

    # When: the move map is validated.
    with pytest.raises(OutputLayoutContractError, match="duplicate relocation destination"):
        validate_output_layout(invalid_contract)

    # Then: a destination collision is rejected before any move can run.


def test_contract_rejects_record_copy_collision() -> None:
    # Given: two physical copy specifications targeting the same record path.
    first_copy = DEFAULT_OUTPUT_LAYOUT.physical_record_copies[0]
    duplicate_copy = replace(DEFAULT_OUTPUT_LAYOUT.physical_record_copies[1], destination=first_copy.destination)
    invalid_contract = replace(DEFAULT_OUTPUT_LAYOUT, physical_record_copies=(first_copy, duplicate_copy, *DEFAULT_OUTPUT_LAYOUT.physical_record_copies[2:]))

    # When: the copy contract is validated.
    with pytest.raises(OutputLayoutContractError, match="duplicate physical record destination"):
        validate_output_layout(invalid_contract)

    # Then: one copy cannot silently overwrite another.


def test_contract_rejects_stale_flat_record_copy_source() -> None:
    # Given: a record copy that incorrectly names the pre-relocation pilot root.
    stale_source = RepositoryRelativePath.parse("outputs/phase3_planimation_frames_stratified_pilot_20260725/full_reasoning_train.jsonl")
    stale_copy = replace(DEFAULT_OUTPUT_LAYOUT.physical_record_copies[0], source=stale_source)
    invalid_contract = replace(DEFAULT_OUTPUT_LAYOUT, physical_record_copies=(stale_copy, *DEFAULT_OUTPUT_LAYOUT.physical_record_copies[1:]))

    # When: the copy contract is validated.
    with pytest.raises(OutputLayoutContractError, match="physical record source must be below the moved pilot root"):
        validate_output_layout(invalid_contract)

    # Then: a migration cannot appear valid while retaining a stale source assumption.


def test_contract_rejects_destination_outside_category_roots() -> None:
    # Given: a relocation destination outside the three category roots.
    flat_destination = RepositoryRelativePath.parse("outputs/phase3_unclassified_destination")
    invalid_move = replace(DEFAULT_OUTPUT_LAYOUT.relocations[0], destination=flat_destination)
    invalid_contract = replace(DEFAULT_OUTPUT_LAYOUT, relocations=(invalid_move, *DEFAULT_OUTPUT_LAYOUT.relocations[1:]))

    # When: the move map is validated.
    with pytest.raises(OutputLayoutContractError, match="relocation destination must be below its category root"):
        validate_output_layout(invalid_contract)

    # Then: every output destination belongs to a category.


def test_repository_relative_path_parses_a_valid_output_path() -> None:
    # Given: a normalized repository-relative path below outputs/.
    path = "outputs/reasoning_traces/vlm_records/stratified_pilot_20260725/full_reasoning/train.jsonl"

    # When: the path is parsed as a contract value.
    parsed_path = RepositoryRelativePath.parse(path)

    # Then: parsing preserves the canonical path unchanged.
    assert parsed_path.value == path


@pytest.mark.parametrize(
    ("invalid_path", "message"),
    (
        ("../outputs/escaped", "must not contain '..'"),
        ("/outputs/absolute", "must be repository-relative"),
        ("datasets/not-under-outputs", "must be confined to outputs/"),
        ("outputs/datasets/phase3/legacy.jsonl", "outputs/datasets is prohibited"),
    ),
)
def test_contract_rejects_unsafe_repository_relative_paths(invalid_path: str, message: str) -> None:
    # Given: a path string that violates the repository-relative output contract.

    # When: the path is parsed for a contract entry.
    with pytest.raises(OutputLayoutContractError, match=message):
        RepositoryRelativePath.parse(invalid_path)

    # Then: no unsafe or deprecated path value is admitted.


def _expected_relocations() -> tuple[tuple[str, str, str], ...]:
    return (
        ("reasoning_traces", "outputs/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round", "outputs/reasoning_traces/curriculum/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round"),
        ("image_frames", "outputs/phase3_planimation_frames_stratified_pilot_20260725", "outputs/image_frames/phase3_planimation_frames_stratified_pilot_20260725"),
        ("image_frames", "outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800", "outputs/image_frames/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800"),
        ("deprecated", "outputs/phase3_curriculum_traces_15puzzle_easy_20260709_002417", "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_15puzzle_easy_20260709_002417"),
        ("deprecated", "outputs/phase3_curriculum_traces_15puzzle_easy_strict_v1_1st_round", "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_15puzzle_easy_strict_v1_1st_round"),
        ("deprecated", "outputs/phase3_curriculum_traces_safe_no_visitall_20260708_122431", "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_safe_no_visitall_20260708_122431"),
        ("deprecated", "outputs/phase3_curriculum_traces_visitall_20260708_191916", "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_visitall_20260708_191916"),
        ("deprecated", "outputs/phase3_curriculum_traces_visitall_strict_v1_1st_round", "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_visitall_strict_v1_1st_round"),
        ("deprecated", "outputs/phase3_curriculum_traces_visitall_train_test_long_timeout_20260710_000503", "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_visitall_train_test_long_timeout_20260710_000503"),
        ("deprecated", "outputs/phase3_planimation_bounded_repro_20260721_2130", "outputs/deprecated/phase3/planimation_runs/phase3_planimation_bounded_repro_20260721_2130"),
        ("deprecated", "outputs/phase3_planimation_elevators_profile_probe_20260722_100300", "outputs/deprecated/phase3/planimation_runs/phase3_planimation_elevators_profile_probe_20260722_100300"),
        ("deprecated", "outputs/phase3_planimation_frames_15puzzle_easy_20260721_214258", "outputs/deprecated/phase3/planimation_runs/phase3_planimation_frames_15puzzle_easy_20260721_214258"),
        ("deprecated", "outputs/phase3_planimation_frames_safe_no_visitall_20260721_044105", "outputs/deprecated/phase3/planimation_runs/phase3_planimation_frames_safe_no_visitall_20260721_044105"),
        ("deprecated", "outputs/phase3_planimation_frames_visitall_20260721_213129", "outputs/deprecated/phase3/planimation_runs/phase3_planimation_frames_visitall_20260721_213129"),
        ("deprecated", "outputs/phase3_planimation_smoke_blocksworld_20260722_001817", "outputs/deprecated/phase3/planimation_runs/phase3_planimation_smoke_blocksworld_20260722_001817"),
    )


def _expected_record_copies() -> tuple[tuple[str, str, str, str, str], ...]:
    return tuple(
        (family, split, f"outputs/image_frames/phase3_planimation_frames_stratified_pilot_20260725/{family}_{split}.jsonl", f"outputs/reasoning_traces/vlm_records/stratified_pilot_20260725/{family}/{split}.jsonl", "physical_immutable_copy")
        for family in ("full_reasoning", "step_vlm", "search_traversal")
        for split in ("train", "dev", "test")
    )


def _test_only_tree_digest(root: Path) -> str:
    digest = sha256()
    for path in sorted(root.rglob("*")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()
