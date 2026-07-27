from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.phase3.organize_outputs_inventory import (
    CurrentOutputInventoryError,
    validate_current_output_inventory,
)
from scripts.phase3.output_layout_contracts import DEFAULT_OUTPUT_LAYOUT


def test_inventory_accepts_fresh_outputs_root(tmp_path: Path) -> None:
    # Given: a repository with only its existing real outputs directory.
    repository = tmp_path
    (repository / "outputs").mkdir()

    # When: the current output inventory is validated.
    validate_current_output_inventory(repository)

    # Then: the fresh layout is accepted.


def test_inventory_accepts_partial_layout(tmp_path: Path) -> None:
    # Given: a repository with one protected root and one relocation source.
    repository = tmp_path
    outputs = repository / "outputs"
    outputs.mkdir()
    (repository / DEFAULT_OUTPUT_LAYOUT.protected_roots[0].path.value).mkdir(parents=True)
    (repository / DEFAULT_OUTPUT_LAYOUT.relocations[0].source.value).mkdir(parents=True)

    # When: the current output inventory is validated.
    validate_current_output_inventory(repository)

    # Then: a partial layout is accepted.


def test_inventory_accepts_completed_layout(tmp_path: Path) -> None:
    # Given: all contracted roots plus the two permitted inventory directories.
    repository = tmp_path
    outputs = repository / "outputs"
    outputs.mkdir()
    for root in DEFAULT_OUTPUT_LAYOUT.protected_roots:
        (repository / root.path.value).mkdir(parents=True)
    for relocation in DEFAULT_OUTPUT_LAYOUT.relocations:
        (repository / relocation.source.value).mkdir(parents=True)
    (outputs / "datasets").mkdir()
    (outputs / "deprecated").mkdir()

    # When: the current output inventory is validated.
    validate_current_output_inventory(repository)

    # Then: the completed layout is accepted.


def test_inventory_rejects_sorted_first_unknown_immediate_child(tmp_path: Path) -> None:
    # Given: two unknown immediate children whose names have a deterministic order.
    repository = tmp_path
    outputs = repository / "outputs"
    outputs.mkdir()
    (outputs / "zeta").mkdir()
    (outputs / "alpha").mkdir()

    # When: the current output inventory is validated.
    with pytest.raises(CurrentOutputInventoryError) as error_info:
        validate_current_output_inventory(repository)

    # Then: the lexicographically first unknown child is reported with its rule and path.
    assert (error_info.value.rule, error_info.value.path) == (
        "unknown output root",
        outputs / "alpha",
    )


@pytest.mark.parametrize("root_kind", ("symlink", "file"))
def test_inventory_rejects_non_directory_outputs_root(tmp_path: Path, root_kind: str) -> None:
    # Given: an outputs path that is not an existing real directory.
    repository = tmp_path
    outputs = repository / "outputs"
    if root_kind == "symlink":
        target = repository / "target"
        target.mkdir()
        outputs.symlink_to(target, target_is_directory=True)
    else:
        outputs.write_text("not a directory\n", encoding="utf-8")

    # When: the current output inventory is validated.
    with pytest.raises(CurrentOutputInventoryError) as error_info:
        validate_current_output_inventory(repository)

    # Then: the root shape violation is reported at outputs.
    assert (error_info.value.rule, error_info.value.path) == (
        "outputs root must be a real directory",
        outputs,
    )


def test_inventory_does_not_mutate_filesystem_on_rejection(tmp_path: Path) -> None:
    # Given: a rejected inventory and a digest captured before validation.
    repository = tmp_path
    outputs = repository / "outputs"
    outputs.mkdir()
    (outputs / "unknown").mkdir()
    marker = outputs / "unknown" / "marker.txt"
    marker.write_text("unchanged\n", encoding="utf-8")
    before_digest = _tree_digest(repository)

    # When: validation rejects the unknown child.
    with pytest.raises(CurrentOutputInventoryError):
        validate_current_output_inventory(repository)

    # Then: no file or directory has been created, removed, or rewritten.
    assert _tree_digest(repository) == before_digest


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()
