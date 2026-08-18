from __future__ import annotations

from pathlib import Path

import pytest

from scripts.phase3.organize_outputs import OrganizerError, apply, main, verify
from scripts.phase3.output_layout_contracts import DEFAULT_OUTPUT_LAYOUT, serialize_catalog
from scripts.phase3.output_layout_journal import journal_path
from organize_outputs_support import repository


def test_verify_rejects_unknown_inventory_without_mutation(tmp_path: Path) -> None:
    repository_root = repository(tmp_path)
    apply(repository_root)
    unknown = repository_root / "outputs/unrecognized"
    unknown.mkdir()
    complete_path = journal_path(repository_root) / "complete.json"
    before = complete_path.read_bytes()

    with pytest.raises(OrganizerError) as error_info:
        verify(repository_root)

    assert (error_info.value.rule, error_info.value.path) == (
        "outputs root does not match migration state",
        unknown,
    )
    assert complete_path.read_bytes() == before
    assert unknown.is_dir()


def test_catalog_cli_writes_exact_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repository_root = repository(tmp_path)

    assert main(["catalog", "--repo-root", str(repository_root)]) == 0

    captured = capsys.readouterr()
    assert captured.out == serialize_catalog(DEFAULT_OUTPUT_LAYOUT)
    assert captured.err == ""
