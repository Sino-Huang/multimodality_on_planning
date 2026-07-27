from __future__ import annotations

import shutil
import stat
from pathlib import Path

import pytest

from scripts.phase3 import organize_outputs, organize_outputs_preflight
from scripts.phase3.organize_outputs import OrganizerError, apply, main, verify
from scripts.phase3.organize_outputs_preflight import OrganizerPreflightError
from scripts.phase3.output_layout_contracts import DEFAULT_OUTPUT_LAYOUT, serialize_catalog
from scripts.phase3.output_layout_writer_detection import WriterOverlap
from scripts.phase3.output_layout_writer_registry import WriterDetectionError
from organize_outputs_support import receipt_path, repository


def test_apply_rejects_unknown_inventory_before_preparing_receipt(tmp_path: Path) -> None:
    # Given: a fresh synthetic repository with an unrecognized immediate output root.
    repository_root = repository(tmp_path)
    unknown = repository_root / "outputs/unrecognized"
    unknown.mkdir()
    path = receipt_path(repository_root)

    # When: apply begins its fresh receipt preparation.
    with pytest.raises(OrganizerError) as error_info:
        apply(repository_root, path)

    # Then: it reports the inventory violation without creating a receipt or moving a source.
    assert (error_info.value.rule, error_info.value.path) == ("unknown output root", unknown)
    assert not path.exists()
    assert (repository_root / DEFAULT_OUTPUT_LAYOUT.relocations[0].source.value).is_dir()


def test_fresh_apply_revalidates_inventory_before_initial_receipt_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: an unknown root injected after receipt preparation but before its first persistence.
    repository_root = repository(tmp_path)
    path = receipt_path(repository_root)
    unknown = repository_root / "outputs/unrecognized"
    original_prepare = organize_outputs.prepare_real_directory

    def prepare_receipt_parent_then_add_unknown(receipt_parent: Path) -> None:
        original_prepare(receipt_parent)
        unknown.mkdir()

    monkeypatch.setattr(organize_outputs, "prepare_real_directory", prepare_receipt_parent_then_add_unknown)

    # When: fresh apply reaches the initial durable receipt boundary.
    with pytest.raises(OrganizerError) as error_info:
        apply(repository_root, path)

    # Then: no receipt, destination, or view mutation is published after the rejection.
    first = DEFAULT_OUTPUT_LAYOUT.relocations[0]
    assert (error_info.value.rule, error_info.value.path) == ("unknown output root", unknown)
    assert not path.exists()
    assert not (repository_root / first.destination.value).exists()
    assert not (repository_root / DEFAULT_OUTPUT_LAYOUT.view_links[0].link.value).exists()


def test_resumed_apply_stops_before_additional_mutation_when_inventory_changes(tmp_path: Path) -> None:
    # Given: a prepared apply that adds an unknown root after its first durable relocation.
    repository_root = repository(tmp_path)
    path = receipt_path(repository_root)
    receipt_before_rejection = b""

    def add_unknown_after_first_move(checkpoint: str) -> None:
        nonlocal receipt_before_rejection
        if checkpoint == "move_verified" and not receipt_before_rejection:
            receipt_before_rejection = path.read_bytes()
            (repository_root / "outputs/unrecognized").mkdir()

    # When: apply reaches the next relocation boundary.
    with pytest.raises(OrganizerError) as error_info:
        apply(repository_root, path, checkpoint=add_unknown_after_first_move)

    # Then: the prior durable move remains, but no later source, receipt, or view is mutated.
    first = DEFAULT_OUTPUT_LAYOUT.relocations[0]
    second = DEFAULT_OUTPUT_LAYOUT.relocations[1]
    assert error_info.value.rule == "unknown output root"
    assert (repository_root / first.destination.value).is_dir()
    assert (repository_root / second.source.value).is_dir()
    assert not (repository_root / second.destination.value).exists()
    assert path.read_bytes() == receipt_before_rejection
    assert not (repository_root / DEFAULT_OUTPUT_LAYOUT.view_links[0].link.value).exists()


def test_apply_rejects_noncanonical_receipt_path_before_mutation(tmp_path: Path) -> None:
    # Given: a fresh repository and a lexically different spelling of the canonical receipt.
    repository_root = repository(tmp_path)
    alternate = repository_root / "outputs/deprecated/phase3/../phase3/output_reorganization_20260726.json"

    # When: apply receives the alternate spelling.
    with pytest.raises(OrganizerError) as error_info:
        apply(repository_root, alternate)

    # Then: no receipt or relocation mutation occurs.
    assert error_info.value.rule == "apply receipt path must be canonical"
    assert not receipt_path(repository_root).exists()
    assert (repository_root / DEFAULT_OUTPUT_LAYOUT.relocations[0].source.value).is_dir()


def test_apply_rejects_noncanonical_receipt_before_lock_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: an alternate receipt spelling and a lock seam that fails if entered.
    repository_root = repository(tmp_path)
    alternate = repository_root / "outputs/deprecated/phase3/../phase3/output_reorganization_20260726.json"

    def lock_must_not_enter(_repository: Path) -> None:
        pytest.fail("noncanonical apply entered the organizer lock")

    monkeypatch.setattr(organize_outputs, "exclusive_output_layout_lock", lock_must_not_enter)

    # When: apply receives the noncanonical path.
    with pytest.raises(OrganizerError) as error_info:
        apply(repository_root, alternate)

    # Then: path validation rejects it before lock acquisition.
    assert error_info.value.rule == "apply receipt path must be canonical"


def test_verify_accepts_external_private_complete_receipt_without_rewrite(tmp_path: Path) -> None:
    # Given: a complete canonical organization copied to an external mode-0600 receipt.
    repository_root = repository(tmp_path)
    canonical = receipt_path(repository_root)
    apply(repository_root, canonical)
    external = tmp_path / "external-receipt.json"
    shutil.copyfile(canonical, external)
    external.chmod(0o600)
    before = external.read_bytes()

    # When: verify reads the external receipt.
    verify(repository_root, external)

    # Then: verification succeeds without rewriting its external input.
    assert external.read_bytes() == before
    assert stat.S_IMODE(external.stat().st_mode) == 0o600


def test_verify_rejects_unknown_inventory_without_mutation(tmp_path: Path) -> None:
    # Given: a complete organization whose current inventory gains an unknown root.
    repository_root = repository(tmp_path)
    path = receipt_path(repository_root)
    apply(repository_root, path)
    unknown = repository_root / "outputs/unrecognized"
    unknown.mkdir()
    before = path.read_bytes()

    # When: the read-only verification surface checks the repository.
    with pytest.raises(OrganizerError) as error_info:
        verify(repository_root, path)

    # Then: it reports the unknown root without rewriting the receipt or removing the root.
    assert (error_info.value.rule, error_info.value.path) == ("unknown output root", unknown)
    assert path.read_bytes() == before
    assert unknown.is_dir()


def test_catalog_cli_without_output_writes_exact_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Given: a repository with no requested catalog destination.
    repository_root = repository(tmp_path)

    # When: catalog is requested without an output destination.
    assert main(["catalog", "--repo-root", str(repository_root)]) == 0

    # Then: stdout is exactly the pure rendered catalog.
    captured = capsys.readouterr()
    assert captured.out == serialize_catalog(DEFAULT_OUTPUT_LAYOUT)
    assert captured.err == ""


def test_catalog_cli_output_publishes_silently(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Given: a repository and a real parent for the requested catalog destination.
    repository_root = repository(tmp_path)
    destination = tmp_path / "published" / "catalog.json"
    destination.parent.mkdir()

    # When: catalog is published to the requested destination.
    assert main(["catalog", "--repo-root", str(repository_root), "--output", str(destination)]) == 0

    # Then: publication is silent and writes the same rendered catalog.
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert destination.read_text(encoding="utf-8") == serialize_catalog(DEFAULT_OUTPUT_LAYOUT)


def test_catalog_cli_translates_publication_error_to_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Given: an already-owned catalog destination.
    repository_root = repository(tmp_path)
    destination = tmp_path / "catalog.json"
    destination.write_text("owned\n", encoding="utf-8")

    # When: catalog publication targets the occupied leaf.
    assert main(["catalog", "--repo-root", str(repository_root), "--output", str(destination)]) == 1

    # Then: the existing JSON error surface is used without stdout output.
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == '{"error": "catalog destination already exists", "ok": false}\n'


def test_preflight_translates_exact_writer_detection_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: exact writer detection returning an overlapping known writer.
    source = tmp_path / "outputs/phase3_planimation_vlm"

    def detected_writer(_source: Path, *, proc_root: Path) -> WriterOverlap:
        _ = proc_root
        return WriterOverlap(pid=42, command="planimation", target=source)

    monkeypatch.setattr(organize_outputs_preflight, "find_overlapping_writer", detected_writer)

    # When: preflight rejects a source with that detected overlap.
    with pytest.raises(OrganizerPreflightError) as error_info:
        organize_outputs_preflight.reject_uncooperative_writers(source)

    # Then: the organizer keeps its typed preflight failure boundary.
    assert (error_info.value.rule, error_info.value.path) == (
        "uncooperative generator writes relocation source",
        source,
    )


def test_preflight_translates_writer_discovery_metadata_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: exact writer discovery that cannot enumerate process metadata.
    source = tmp_path / "outputs/phase3_planimation_vlm"

    def unreadable_proc(_source: Path, *, proc_root: Path) -> None:
        _ = proc_root
        raise WriterDetectionError("cannot enumerate proc metadata")

    monkeypatch.setattr(organize_outputs_preflight, "find_overlapping_writer", unreadable_proc)

    # When: preflight scans for conflicting writers.
    with pytest.raises(OrganizerPreflightError) as error_info:
        organize_outputs_preflight.reject_uncooperative_writers(source)

    # Then: the typed discovery failure is surfaced at the source boundary.
    assert (error_info.value.rule, error_info.value.path) == ("cannot enumerate proc metadata", source)
