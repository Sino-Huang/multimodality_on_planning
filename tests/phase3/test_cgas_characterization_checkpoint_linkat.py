from __future__ import annotations

import os
from pathlib import Path

import pytest

import scripts.phase3.cgas_characterization_checkpoint as checkpoints
import scripts.phase3.cgas_characterization_checkpoint_publication as publication
from scripts.phase3.cgas_characterization_types import CanonicalRowIndex, CharacterizationArtifactDigest, SourceManifestDigest


def test_checkpoint_procfd_link_preserves_mode_and_single_link(tmp_path: Path) -> None:
    root, private, checkpoint = _publication(tmp_path)

    checkpoints.publish_checkpoint(root, private, checkpoint)

    status = os.stat(root / "0007.json")
    assert (status.st_nlink, status.st_uid, status.st_mode & 0o777) == (1, os.geteuid(), 0o600)
    assert not tuple(private.iterdir())


def test_checkpoint_procfd_link_failure_leaves_no_public_or_private_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, private, checkpoint = _publication(tmp_path)

    def fail_link(_source: int, _destination: int, _name: bytes) -> None:
        raise OSError("procfd unavailable")

    monkeypatch.setattr(publication, "linkat_proc_fd", fail_link)

    with pytest.raises(checkpoints.CheckpointError, match="procfd linkat"):
        checkpoints.publish_checkpoint(root, private, checkpoint)

    assert not tuple(root.iterdir())
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
