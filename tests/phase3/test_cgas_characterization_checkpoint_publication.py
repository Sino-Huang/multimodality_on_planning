from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

import scripts.phase3.cgas_characterization_checkpoint as checkpoints
import scripts.phase3.cgas_characterization_checkpoint_publication as publication
from scripts.phase3.cgas_characterization_types import CanonicalRowIndex, CharacterizationArtifactDigest, SourceManifestDigest


def test_publish_checkpoint_uses_anonymous_inode_and_syncs_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, private, checkpoint = _publication(tmp_path)
    original_write = checkpoints.os.write
    original_fsync = checkpoints.os.fsync
    writes: list[int] = []
    synced: list[str] = []

    def short_write(descriptor: int, contents: bytes) -> int:
        writes.append(len(contents))
        return original_write(descriptor, contents[:1])

    def record_fsync(descriptor: int) -> None:
        synced.append(Path(os.readlink(f"/proc/self/fd/{descriptor}")).name)
        original_fsync(descriptor)

    monkeypatch.setattr(checkpoints.os, "write", short_write)
    monkeypatch.setattr(checkpoints.os, "fsync", record_fsync)

    checkpoints.publish_checkpoint(root, private, checkpoint)

    leaf = root / "0007.json"
    assert leaf.read_bytes() == checkpoint.canonical_bytes
    assert leaf.stat().st_nlink == 1
    assert writes[-1] == 1
    assert synced[-1] == root.name
    assert not tuple(private.iterdir())


def test_publish_checkpoint_never_replaces_existing_destination(tmp_path: Path) -> None:
    root, private, checkpoint = _publication(tmp_path)
    destination = root / "0007.json"
    destination.write_bytes(b"existing")
    destination.chmod(0o600)

    with pytest.raises(checkpoints.CheckpointError, match="collision"):
        checkpoints.publish_checkpoint(root, private, checkpoint)

    assert destination.read_bytes() == b"existing"
    assert not tuple(private.iterdir())


def test_checkpoint_link_durability_failure_leaves_a_valid_resumable_leaf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, private, checkpoint = _publication(tmp_path)
    original_fsync = publication.os.fsync
    calls = 0

    def fail_destination_directory(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        original_fsync(descriptor)
        if calls == 2:
            raise OSError("destination fsync interrupted")

    monkeypatch.setattr(publication.os, "fsync", fail_destination_directory)

    with pytest.raises(checkpoints.CheckpointError, match="fsync checkpoint directory"):
        checkpoints.publish_checkpoint(root, private, checkpoint)

    assert checkpoints.load_checkpoint(root, checkpoint.expectation) == checkpoint
    assert (root / "0007.json").stat().st_nlink == 1


def test_checkpoint_publication_only_uses_otmpfile_procfd_linkat(tmp_path: Path) -> None:
    root, private, checkpoint = _publication(tmp_path)
    tree = ast.parse(Path(publication.__file__).read_text(encoding="utf-8"))
    attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    imports = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "cgas_characterization_checkpoint_fs"
        for alias in node.names
    }

    checkpoints.publish_checkpoint(root, private, checkpoint)

    assert {"rename", "replace", "unlink"}.isdisjoint(attributes)
    assert imports == {"linkat_proc_fd"}
    assert publication._ANONYMOUS_FLAGS & os.O_TMPFILE
    assert not tuple(private.iterdir())


def _publication(tmp_path: Path) -> tuple[Path, Path, checkpoints.Checkpoint]:
    root = tmp_path / "checkpoints"
    private = tmp_path / "private"
    root.mkdir(mode=0o700)
    private.mkdir(mode=0o700)
    expectation = checkpoints.CheckpointExpectation(
        SourceManifestDigest("a" * 64),
        CanonicalRowIndex(7),
        "synthetic-0007",
        CharacterizationArtifactDigest("b" * 64),
    )
    return root, private, checkpoints.build_checkpoint(expectation)
