from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import pytest

from scripts.phase3 import cgas_certificate_publication, cgas_certificates
from scripts.phase3.cgas_alignment import build_alignment
from test_cgas_alignment import _build_cgas_source, _write_render_manifest


Replace = Callable[[Path | str, Path | str], None]


@pytest.mark.parametrize("failure_index", range(1, 4))
def test_first_publication_rolls_back_every_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_index: int
) -> None:
    # Given: accepted inputs and a destination with non-certificate companion trees.
    source_root, alignment_root = _accepted_inputs(tmp_path)
    output_root = tmp_path / "steps"
    _write_companions(output_root)
    before = _tree_bytes(output_root)

    _fail_replace_at(monkeypatch, failure_index)

    # When: a first publication fails at one of its three replacement boundaries.
    with pytest.raises(OSError, match="injected replace failure"):
        cgas_certificates.build_steps(source_root, alignment_root, output_root)

    # Then: the original tree and its companion directories are exact, with no staging residue.
    assert _tree_bytes(output_root) == before
    _assert_no_publication_residue(tmp_path, output_root)


@pytest.mark.parametrize("failure_index", range(1, 7))
def test_update_publication_rolls_back_every_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_index: int
) -> None:
    # Given: a prior approved artifact set and colocated source and alignment directories.
    source_root, alignment_root = _accepted_inputs(tmp_path)
    output_root = tmp_path / "steps"
    assert not cgas_certificates.build_steps(source_root, alignment_root, output_root)["rejections"]
    _write_companions(output_root)
    before = _tree_bytes(output_root)

    _fail_replace_at(monkeypatch, failure_index)

    # When: an update fails at any backup or candidate replacement boundary.
    with pytest.raises(OSError, match="injected replace failure"):
        cgas_certificates.build_steps(source_root, alignment_root, output_root)

    # Then: the previously approved bytes remain exactly intact and no transaction paths survive.
    assert _tree_bytes(output_root) == before
    _assert_no_publication_residue(tmp_path, output_root)


def test_successful_update_replaces_all_certificate_artifacts_and_preserves_companions(tmp_path: Path) -> None:
    # Given: a completed first publication and colocated source and alignment trees.
    source_root, alignment_root = _accepted_inputs(tmp_path)
    output_root = tmp_path / "steps"
    assert not cgas_certificates.build_steps(source_root, alignment_root, output_root)["rejections"]
    _write_companions(output_root)
    previous_steps = (output_root / "steps" / "train.jsonl").read_bytes()
    replacements: list[Path] = []
    real_replace = os.replace

    def record_replace(source: Path | str, destination: Path | str) -> None:
        replacements.append(Path(destination))
        real_replace(source, destination)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cgas_certificate_publication.os, "replace", record_replace)

    try:
        # When: the builder replaces a complete previously approved artifact set.
        report = cgas_certificates.build_steps(source_root, alignment_root, output_root)
    finally:
        monkeypatch.undo()

    # Then: every certificate artifact is replaced while non-owned directories remain untouched.
    assert not report["rejections"]
    assert (output_root / "steps" / "train.jsonl").read_bytes() == previous_steps
    assert {output_root / "steps", output_root / "schema", output_root / "steps_manifest.json"} <= set(replacements)
    assert (output_root / "schema" / "planning_cgas_v1.schema.json").is_file()
    assert (output_root / "steps_manifest.json").is_file()
    assert (output_root / "source" / "retained.txt").read_bytes() == b"source companion\n"
    assert (output_root / "alignment" / "retained.txt").read_bytes() == b"alignment companion\n"
    _assert_no_publication_residue(tmp_path, output_root)


def _accepted_inputs(root: Path) -> tuple[Path, Path]:
    source_root = _build_cgas_source(root)
    render_manifest = _write_render_manifest(source_root, root / "renders")
    alignment_root = root / "alignment-output"
    assert not build_alignment(source_root, render_manifest, alignment_root)["rejections"]
    return source_root, alignment_root


def _write_companions(output_root: Path) -> None:
    for name in ("source", "alignment"):
        companion = output_root / name
        companion.mkdir(parents=True, exist_ok=True)
        (companion / "retained.txt").write_bytes(f"{name} companion\n".encode())


def _fail_replace_at(monkeypatch: pytest.MonkeyPatch, failure_index: int) -> None:
    real_replace = os.replace
    calls = 0

    def fail_at_index(source: Path | str, destination: Path | str) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_index:
            raise OSError("injected replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(cgas_certificate_publication.os, "replace", fail_at_index)


def _tree_bytes(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def _assert_no_publication_residue(parent: Path, output_root: Path) -> None:
    assert not [
        path
        for path in parent.iterdir()
        if path.name.startswith(f".{output_root.name}.steps-") or path.name.startswith(f".{output_root.name}.publication-")
    ]
