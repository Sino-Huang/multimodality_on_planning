from __future__ import annotations

from pathlib import Path

import pytest

from scripts.phase3.organize_outputs import OrganizerError, apply, verify
from scripts.phase3.output_layout_contracts import DEFAULT_OUTPUT_LAYOUT
from scripts.phase3.output_layout_inventory import read_receipt, seal_receipt, write_receipt
from organize_outputs_support import receipt_path, repository


def test_complete_receipt_requires_verified_status_and_destination_snapshot(tmp_path: Path) -> None:
    # Given: all physical moves completed but a resealed semantically partial complete receipt.
    repository_root = repository(tmp_path)
    path = receipt_path(repository_root)
    apply(repository_root, path)
    receipt = read_receipt(path)
    receipt.pop("receipt_sha256")
    for relocation in receipt["relocations"]:
        relocation["status"] = "prepared"
        relocation["destination_snapshot"] = None
    write_receipt(path, seal_receipt(receipt))

    # When: read-only verification sees valid destinations and absent sources.
    with pytest.raises(OrganizerError):
        verify(repository_root, path)

    # Then: receipt semantics, not only live files, control completion.
    assert not (repository_root / DEFAULT_OUTPUT_LAYOUT.relocations[0].source.value).exists()


def test_preflight_rejects_unknown_root_and_destination_collision_before_receipt(tmp_path: Path) -> None:
    # Given: synthetic layouts with an extra root or a pre-existing destination collision.
    unknown_root = repository(tmp_path / "unknown")
    (unknown_root / "outputs/unapproved-root").mkdir()
    collision_root = repository(tmp_path / "collision")
    collision = collision_root / DEFAULT_OUTPUT_LAYOUT.relocations[0].destination.value
    collision.mkdir(parents=True)

    # When: apply preflights each layout.
    for repository_root in (unknown_root, collision_root):
        with pytest.raises(OrganizerError):
            apply(repository_root, receipt_path(repository_root))

    # Then: neither failure creates a receipt or starts a relocation.
    assert not receipt_path(unknown_root).exists()
    assert not receipt_path(collision_root).exists()
    assert (collision_root / DEFAULT_OUTPUT_LAYOUT.relocations[0].source.value).is_dir()


def test_verify_rejects_extra_view_entry_without_mutation(tmp_path: Path) -> None:
    # Given: an otherwise exact synthetic complete layout with an extra view entry.
    repository_root = repository(tmp_path)
    path = receipt_path(repository_root)
    apply(repository_root, path)
    extra = repository_root / "outputs/datasets/phase3/planimation/stratified_pilot_20260725/extra.txt"
    extra.write_text("extra\n", encoding="utf-8")

    # When: verify runs through its read-only view path.
    with pytest.raises(OrganizerError):
        verify(repository_root, path)

    # Then: the extra entry is not removed or rewritten.
    assert extra.read_text(encoding="utf-8") == "extra\n"


def test_later_source_and_protected_mutations_fail_before_completion(tmp_path: Path) -> None:
    repository_root = repository(tmp_path)
    path = receipt_path(repository_root)
    calls = 0

    def mutate_before_next_rename(checkpoint: str) -> None:
        nonlocal calls
        if checkpoint == "move_verified":
            calls += 1
            if calls == 1:
                source = repository_root / DEFAULT_OUTPUT_LAYOUT.relocations[1].source.value / "payload-1.txt"
                source.write_text("changed\n", encoding="utf-8")

    with pytest.raises(OrganizerError):
        apply(repository_root, path, checkpoint=mutate_before_next_rename)
    assert (repository_root / DEFAULT_OUTPUT_LAYOUT.relocations[1].source.value).is_dir()
    protected = repository_root / DEFAULT_OUTPUT_LAYOUT.protected_roots[0].path.value / "protected-0.txt"
    protected.write_text("changed\n", encoding="utf-8")
    with pytest.raises(OrganizerError):
        apply(repository_root, path)


def test_protected_mutation_does_not_rewrite_complete_receipt(tmp_path: Path) -> None:
    repository_root = repository(tmp_path)
    path = receipt_path(repository_root)
    apply(repository_root, path)
    before = path.read_bytes()
    protected = repository_root / DEFAULT_OUTPUT_LAYOUT.protected_roots[0].path.value / "protected-0.txt"
    protected.write_text("changed\n", encoding="utf-8")
    with pytest.raises(OrganizerError):
        apply(repository_root, path)
    assert path.read_bytes() == before


def test_preflight_rejects_destination_and_receipt_parent_symlinks_without_artifacts(tmp_path: Path) -> None:
    repository_root = repository(tmp_path)
    destination_parent = repository_root / "outputs/deprecated"
    destination_parent.symlink_to(repository_root / "outside", target_is_directory=True)
    with pytest.raises(OrganizerError):
        apply(repository_root, receipt_path(repository_root))
    assert not receipt_path(repository_root).exists()
    second = repository(tmp_path / "receipt-parent")
    external = tmp_path / "external-receipt"
    external.mkdir()
    (second / "outputs/deprecated").symlink_to(external, target_is_directory=True)
    with pytest.raises(OrganizerError):
        apply(second, receipt_path(second))
    assert not (external / "phase3/output_reorganization_20260726.json").exists()
