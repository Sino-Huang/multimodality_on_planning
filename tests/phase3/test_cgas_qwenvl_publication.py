from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import pytest

from scripts.phase3 import cgas_qwenvl_publication


Replace = Callable[[Path | str, Path | str], None]


@pytest.mark.parametrize("failure_index", range(1, 2))
def test_publish_candidate_removes_first_publish_destination_on_each_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_index: int
) -> None:
    # Given: a complete candidate and no prior public corpus.
    candidate = _write_tree(tmp_path / ".planning_cgas_v1.qwenvl-candidate", b"candidate")
    output = tmp_path / "qwenvl"
    _fail_replace_at(monkeypatch, failure_index)

    # When: the only first-publication replacement fails.
    with pytest.raises(OSError, match="injected replace failure"):
        cgas_qwenvl_publication.publish_candidate(candidate, output)

    # Then: no public destination, staged candidate, or transaction residue remains.
    assert not output.exists()
    assert not candidate.exists()
    _assert_no_publication_residue(tmp_path, output)


@pytest.mark.parametrize("failure_index", range(1, 3))
def test_publish_candidate_restores_prior_tree_on_each_update_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_index: int
) -> None:
    # Given: a prior complete corpus and a distinct complete candidate tree.
    output = _write_tree(tmp_path / "qwenvl", b"previous")
    candidate = _write_tree(tmp_path / ".planning_cgas_v1.qwenvl-candidate", b"candidate")
    before = _tree_bytes(output)
    _fail_replace_at(monkeypatch, failure_index)

    # When: either the backup or candidate replacement fails.
    with pytest.raises(OSError, match="injected replace failure"):
        cgas_qwenvl_publication.publish_candidate(candidate, output)

    # Then: the prior public bytes are exact and no private transaction path survives.
    assert _tree_bytes(output) == before
    assert not candidate.exists()
    _assert_no_publication_residue(tmp_path, output)


def test_publish_candidate_replaces_the_complete_public_tree(tmp_path: Path) -> None:
    # Given: an existing public tree whose files are absent from the replacement candidate.
    output = _write_tree(tmp_path / "qwenvl", b"previous")
    candidate = _write_tree(tmp_path / ".planning_cgas_v1.qwenvl-candidate", b"candidate")

    # When: the complete candidate is published.
    cgas_qwenvl_publication.publish_candidate(candidate, output)

    # Then: only the candidate byte tree is public and neither source nor backup remains.
    assert _tree_bytes(output) == _expected_tree(b"candidate")
    assert not candidate.exists()
    _assert_no_publication_residue(tmp_path, output)


def _write_tree(root: Path, value: bytes) -> Path:
    (root / "images" / "train").mkdir(parents=True)
    (root / "train.jsonl").write_bytes(value + b" train\n")
    (root / "images" / "train" / "frame.png").write_bytes(value + b" image\n")
    (root / "manifest.json").write_bytes(value + b" manifest\n")
    return root


def _expected_tree(value: bytes) -> dict[Path, bytes]:
    return {
        Path("train.jsonl"): value + b" train\n",
        Path("images/train/frame.png"): value + b" image\n",
        Path("manifest.json"): value + b" manifest\n",
    }


def _fail_replace_at(monkeypatch: pytest.MonkeyPatch, failure_index: int) -> None:
    real_replace = os.replace
    calls = 0

    def fail_at_index(source: Path | str, destination: Path | str) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_index:
            raise OSError("injected replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(cgas_qwenvl_publication.os, "replace", fail_at_index)


def _tree_bytes(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def _assert_no_publication_residue(parent: Path, output: Path) -> None:
    assert not [
        path
        for path in parent.iterdir()
        if path.name.startswith(".planning_cgas_v1.qwenvl-")
        or path.name.startswith(f".{output.name}.publication-")
    ]
