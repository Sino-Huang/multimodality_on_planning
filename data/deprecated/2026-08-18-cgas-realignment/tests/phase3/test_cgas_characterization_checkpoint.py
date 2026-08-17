from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

import scripts.phase3.cgas_characterization_checkpoint as checkpoints
from scripts.phase3.cgas_characterization_types import (
    CanonicalRowIndex,
    CharacterizationArtifactDigest,
    SourceManifestDigest,
)


def test_load_checkpoint_accepts_only_exact_canonical_bound_envelope(tmp_path: Path) -> None:
    # Given: a synthetic checkpoint bound to one canonical row identity.
    root, scratch, expected = _paths(tmp_path)
    checkpoint = checkpoints.build_checkpoint(expected)

    # When: its exact canonical bytes are published and loaded.
    checkpoints.publish_checkpoint(root, scratch, checkpoint)
    loaded = checkpoints.load_checkpoint(root, expected)

    # Then: the durable leaf is canonical, private, and bound to that identity.
    assert loaded == checkpoint
    destination = root / "0007.json"
    assert destination.read_bytes() == checkpoint.canonical_bytes
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


@pytest.mark.parametrize("row_index", (CanonicalRowIndex(481), CanonicalRowIndex(-1)))
def test_checkpoint_name_rejects_indexes_outside_the_canonical_range(row_index: CanonicalRowIndex) -> None:
    # Given: an index that cannot name one of the 0000.json through 0480.json leaves.

    # When: it is formatted for a checkpoint leaf.
    with pytest.raises(checkpoints.CheckpointError, match="checkpoint"):
        checkpoints.checkpoint_name(row_index)

    # Then: no noncanonical name is emitted.


def test_load_checkpoint_rejects_noncanonical_bytes_and_wrong_index(tmp_path: Path) -> None:
    # Given: a target leaf whose envelope uses noncanonical bytes and another row index.
    root, _scratch, expected = _paths(tmp_path)
    payload = json.loads(checkpoints.build_checkpoint(expected).canonical_bytes)
    payload["row_index"] = 8
    path = root / "0007.json"
    path.write_bytes(checkpoints.canonical_json_object(payload) + b"\n")
    path.chmod(0o600)

    # When: the checkpoint crosses the single parsing boundary.
    with pytest.raises(checkpoints.CheckpointError, match="checkpoint"):
        checkpoints.load_checkpoint(root, expected)

    # Then: no untyped JSON value reaches the caller.
    assert path.exists()


def test_load_checkpoint_rejects_sparse_terabyte_before_pread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: an owner-mode checkpoint leaf with a one-terabyte sparse logical size.
    root, _scratch, expected = _paths(tmp_path)
    path = root / "0007.json"
    path.touch(mode=0o600)
    os.truncate(path, 1 << 40)

    def prohibit_read(_descriptor: int, _size: int, _offset: int) -> bytes:
        raise AssertionError("oversized checkpoint reached pread")

    monkeypatch.setattr(checkpoints.os, "pread", prohibit_read)

    # When: the hardened checkpoint loader examines the sparse leaf.
    with pytest.raises(checkpoints.CheckpointError, match="byte limit"):
        checkpoints.load_checkpoint(root, expected)

    # Then: the cap rejects metadata before a giant allocation request is possible.


def test_load_checkpoint_rejects_wrong_digest_and_symlink(tmp_path: Path) -> None:
    # Given: a wrong-digest envelope and a replacement leaf symlink.
    root, _scratch, expected = _paths(tmp_path)
    payload = json.loads(checkpoints.build_checkpoint(expected).canonical_bytes)
    payload["row_digest"] = "c" * 64
    destination = root / "0007.json"
    destination.write_bytes(checkpoints.canonical_json_object(payload))
    destination.chmod(0o600)

    # When: the row digest disagrees with the expected row.
    with pytest.raises(checkpoints.CheckpointError, match="row digest"):
        checkpoints.load_checkpoint(root, expected)
    destination.unlink()
    target = tmp_path / "target.json"
    target.write_bytes(b"owned")
    destination.symlink_to(target)

    # Then: a symlink cannot be substituted for an owned checkpoint.
    with pytest.raises(checkpoints.CheckpointError, match="regular file"):
        checkpoints.load_checkpoint(root, expected)


def test_load_checkpoint_rejects_hardlinked_leaf_before_and_after_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a canonical leaf that is hard-linked before loading and then linked during a read.
    root, scratch, expected = _paths(tmp_path)
    checkpoint = checkpoints.build_checkpoint(expected)
    checkpoints.publish_checkpoint(root, scratch, checkpoint)
    destination = root / "0007.json"
    alias = tmp_path / "before-read-alias.json"
    os.link(destination, alias)

    # When: direct loading observes either link-count violation.
    with pytest.raises(checkpoints.CheckpointError, match="owner regular mode 0600 single-link"):
        checkpoints.load_checkpoint(root, expected)
    alias.unlink()
    original_read = checkpoints._read_bytes

    def link_after_read(descriptor: int, expected_size: int, path: Path) -> bytes:
        contents = original_read(descriptor, expected_size, path)
        os.link(path, tmp_path / "after-read-alias.json")
        return contents

    monkeypatch.setattr(checkpoints, "_read_bytes", link_after_read)
    with pytest.raises(checkpoints.CheckpointError, match="owner regular mode 0600 single-link"):
        checkpoints.load_checkpoint(root, expected)

    # Then: one descriptor snapshot cannot authorize a multi-link leaf.


def test_load_checkpoint_rejects_noncurrent_owner_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a canonical single-link leaf and a filesystem report with another effective owner.
    root, scratch, expected = _paths(tmp_path)
    checkpoints.publish_checkpoint(root, scratch, checkpoints.build_checkpoint(expected))
    original_fstat = checkpoints.os.fstat

    def wrong_owner(descriptor: int) -> os.stat_result:
        status = original_fstat(descriptor)
        if stat.S_ISREG(status.st_mode):
            return os.stat_result(
                (status.st_mode, status.st_ino, status.st_dev, status.st_nlink, status.st_uid + 1, status.st_gid, status.st_size, status.st_atime, status.st_mtime, status.st_ctime)
            )
        return status

    monkeypatch.setattr(checkpoints.os, "fstat", wrong_owner)

    # When: direct loading checks its pinned descriptor metadata.
    with pytest.raises(checkpoints.CheckpointError, match="owner regular mode 0600 single-link"):
        checkpoints.load_checkpoint(root, expected)

    # Then: metadata for another owner cannot cross the load boundary.


def _paths(tmp_path: Path) -> tuple[Path, Path, checkpoints.CheckpointExpectation]:
    root = tmp_path / "checkpoints"
    scratch = tmp_path / "private-scratch"
    root.mkdir()
    scratch.mkdir(mode=0o700)
    expected = checkpoints.CheckpointExpectation(
        run_fingerprint=SourceManifestDigest("a" * 64),
        row_index=CanonicalRowIndex(7),
        instance_id="synthetic-0007",
        row_digest=CharacterizationArtifactDigest("b" * 64),
    )
    return root, scratch, expected
