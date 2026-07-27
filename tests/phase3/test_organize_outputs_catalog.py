from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

import pytest

from scripts.phase3 import organize_outputs_catalog
from scripts.phase3.organize_outputs_catalog import CatalogPublicationError, publish_catalog


def test_publish_catalog_writes_exact_utf8_content_with_private_mode(tmp_path: Path) -> None:
    # Given: an existing real nested parent and an absent catalog leaf.
    destination = tmp_path / "published" / "catalog.json"
    destination.parent.mkdir()
    contents = '{"name":"catalog cafe"}\n'

    # When: the rendered catalog is published.
    publish_catalog(destination, contents)

    # Then: the exact UTF-8 bytes are published as a mode-0600 regular file.
    assert destination.read_bytes() == contents.encode("utf-8")
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


@pytest.mark.parametrize("kind", ("regular", "directory", "fifo"))
def test_publish_catalog_rejects_existing_leaf_of_every_non_symlink_type(tmp_path: Path, kind: str) -> None:
    # Given: a catalog leaf that another writer already owns.
    destination = tmp_path / "catalog.json"
    if kind == "regular":
        destination.write_bytes(b"existing\n")
    elif kind == "directory":
        destination.mkdir()
    else:
        os.mkfifo(destination)

    # When: publication targets the occupied leaf.
    with pytest.raises(CatalogPublicationError, match="catalog destination already exists"):
        publish_catalog(destination, "new\n")

    # Then: the prior filesystem entry remains untouched.
    assert destination.exists()
    assert stat.S_IFMT(destination.lstat().st_mode) == {
        "regular": stat.S_IFREG,
        "directory": stat.S_IFDIR,
        "fifo": stat.S_IFIFO,
    }[kind]


@pytest.mark.parametrize("target_exists", (True, False))
def test_publish_catalog_rejects_normal_and_dangling_leaf_symlinks(tmp_path: Path, target_exists: bool) -> None:
    # Given: a leaf symlink, either resolved or dangling.
    destination = tmp_path / "catalog.json"
    target = tmp_path / "target.json"
    if target_exists:
        target.write_bytes(b"owned\n")
    destination.symlink_to(target)

    # When: publication targets the symlink name.
    with pytest.raises(CatalogPublicationError, match="catalog destination already exists"):
        publish_catalog(destination, "new\n")

    # Then: the symlink and any existing referent remain unchanged.
    assert destination.is_symlink()
    if target_exists:
        assert target.read_bytes() == b"owned\n"


@pytest.mark.parametrize("destination_suffix", ("parent-link/catalog.json", "ancestor-link/real/catalog.json"))
def test_publish_catalog_rejects_symlink_parent_or_ancestor(tmp_path: Path, destination_suffix: str) -> None:
    # Given: traversal to the real parent would cross a symlink.
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    (tmp_path / "ancestor-target" / "real").mkdir(parents=True)
    (tmp_path / "parent-link").symlink_to(real_parent, target_is_directory=True)
    (tmp_path / "ancestor-link").symlink_to(tmp_path / "ancestor-target", target_is_directory=True)
    destination = tmp_path / destination_suffix

    # When: publication resolves the requested parent.
    with pytest.raises(CatalogPublicationError, match="catalog parent must be a real directory"):
        publish_catalog(destination, "new\n")

    # Then: no path beneath the symlink is created.
    assert not (real_parent / "catalog.json").exists()
    assert not (tmp_path / "ancestor-target" / "real" / "catalog.json").exists()


def test_publish_catalog_never_creates_missing_parent(tmp_path: Path) -> None:
    # Given: an absent parent tree.
    destination = tmp_path / "missing" / "nested" / "catalog.json"

    # When: publication is requested.
    with pytest.raises(CatalogPublicationError, match="catalog parent must be a real directory"):
        publish_catalog(destination, "new\n")

    # Then: the missing tree remains absent.
    assert not destination.parent.exists()


def test_publish_catalog_rejects_parent_replaced_by_symlink_before_temp_creation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the opened parent is swapped for a symlink after leaf inspection.
    destination = tmp_path / "parent" / "catalog.json"
    destination.parent.mkdir()
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    original_absent_check = organize_outputs_catalog._require_absent_leaf

    def replace_parent_after_check(parent_descriptor: int, destination_name: str, path: Path) -> None:
        original_absent_check(parent_descriptor, destination_name, path)
        destination.parent.rename(tmp_path / "displaced-parent")
        destination.parent.symlink_to(replacement, target_is_directory=True)

    monkeypatch.setattr(organize_outputs_catalog, "_require_absent_leaf", replace_parent_after_check)

    # When: publication reaches its parent-identity check.
    with pytest.raises(CatalogPublicationError, match="catalog parent changed during publication"):
        publish_catalog(destination, "new\n")

    # Then: neither the racer-selected path nor the detached parent receives a leaf.
    assert not (replacement / "catalog.json").exists()
    assert not (tmp_path / "displaced-parent" / "catalog.json").exists()


def test_publish_catalog_completes_short_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a write syscall that only accepts one byte at a time.
    destination = tmp_path / "catalog.json"
    original_write = organize_outputs_catalog.os.write
    writes: list[int] = []

    def short_write(descriptor: int, data: bytes) -> int:
        writes.append(len(data))
        return original_write(descriptor, data[:1])

    monkeypatch.setattr(organize_outputs_catalog.os, "write", short_write)

    # When: a multi-byte catalog is published.
    publish_catalog(destination, "abcdef\n")

    # Then: all bytes arrive despite the short writes.
    assert destination.read_bytes() == b"abcdef\n"
    assert writes == [7, 6, 5, 4, 3, 2, 1]


def test_publish_catalog_syncs_temp_before_parent_after_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: fsync observation at the file-descriptor boundary.
    destination = tmp_path / "catalog.json"
    original_fsync = organize_outputs_catalog.os.fsync
    synced: list[str] = []

    def record_fsync(descriptor: int) -> None:
        synced.append(Path(os.readlink(f"/proc/self/fd/{descriptor}")).name)
        original_fsync(descriptor)

    monkeypatch.setattr(organize_outputs_catalog.os, "fsync", record_fsync)

    # When: publication completes.
    publish_catalog(destination, "new\n")

    # Then: the private temp file is durable before the final parent sync.
    assert synced[0].startswith(".catalog.json.tmp-")
    assert synced[1] == tmp_path.name


def test_publish_catalog_preserves_racer_at_no_replace_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: another writer claims the leaf between validation and rename.
    destination = tmp_path / "catalog.json"
    original_rename = organize_outputs_catalog._atomic_rename

    def race_before_rename(parent_descriptor: int, source_name: str, destination_name: str, flags: int) -> None:
        destination.write_bytes(b"racer\n")
        original_rename(parent_descriptor, source_name, destination_name, flags)

    monkeypatch.setattr(organize_outputs_catalog, "_atomic_rename", race_before_rename)

    # When: publication reaches the no-replace rename.
    with pytest.raises(CatalogPublicationError, match="catalog destination collision"):
        publish_catalog(destination, "new\n")

    # Then: the racing artifact wins and no owned temp file remains.
    assert destination.read_bytes() == b"racer\n"
    assert not tuple(tmp_path.glob(".catalog.json.tmp-*"))


def test_publish_catalog_fails_closed_when_renameat2_is_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the Linux no-replace syscall is unavailable.
    destination = tmp_path / "catalog.json"

    def unavailable_rename(_parent_descriptor: int, _source_name: str, _destination_name: str, _flags: int) -> None:
        raise OSError(errno.ENOSYS, "Function not implemented")

    monkeypatch.setattr(organize_outputs_catalog, "_atomic_rename", unavailable_rename)

    # When: publication needs to make the final atomic transition.
    with pytest.raises(CatalogPublicationError, match="renameat2 is unavailable"):
        publish_catalog(destination, "new\n")

    # Then: no final or temporary artifact is retained.
    assert not destination.exists()
    assert not tuple(tmp_path.glob(".catalog.json.tmp-*"))


def test_publish_catalog_cleanup_never_removes_replaced_temp_inode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a write error after an attacker replaces the owned temporary inode.
    destination = tmp_path / "catalog.json"
    original_write = organize_outputs_catalog.os.write

    def replace_temp_then_fail(descriptor: int, data: bytes) -> int:
        _ = original_write(descriptor, data)
        temporary = next(tmp_path.glob(".catalog.json.tmp-*"))
        temporary.unlink()
        temporary.write_bytes(b"racer-owned\n")
        raise OSError("simulated write failure")

    monkeypatch.setattr(organize_outputs_catalog.os, "write", replace_temp_then_fail)

    # When: pre-publication cleanup handles the write failure.
    with pytest.raises(CatalogPublicationError, match="unable to write catalog temporary"):
        publish_catalog(destination, "new\n")

    # Then: cleanup does not unlink the replacement inode.
    temporary = next(tmp_path.glob(".catalog.json.tmp-*"))
    assert temporary.read_bytes() == b"racer-owned\n"


def test_publish_catalog_retains_published_artifact_when_parent_fsync_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: temp-file fsync works but the post-publication parent fsync fails.
    destination = tmp_path / "catalog.json"
    original_fsync = organize_outputs_catalog.os.fsync
    calls = 0

    def fail_parent_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated parent fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(organize_outputs_catalog.os, "fsync", fail_parent_fsync)

    # When: publication reaches its final durability boundary.
    with pytest.raises(CatalogPublicationError, match="unable to fsync catalog parent"):
        publish_catalog(destination, "new\n")

    # Then: the already-published file is retained for recovery or inspection.
    assert destination.read_bytes() == b"new\n"


def test_publish_catalog_translates_temporary_close_failure_and_removes_owned_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: closing the completed private temporary reports an operating-system error.
    destination = tmp_path / "catalog.json"
    original_close = organize_outputs_catalog.os.close

    def close_temp_then_fail(descriptor: int) -> None:
        name = Path(os.readlink(f"/proc/self/fd/{descriptor}")).name
        original_close(descriptor)
        if name.startswith(".catalog.json.tmp-"):
            raise OSError("simulated temporary close failure")

    monkeypatch.setattr(organize_outputs_catalog.os, "close", close_temp_then_fail)

    # When: the publisher closes the fsynced temporary before publication.
    with pytest.raises(CatalogPublicationError, match="unable to close catalog temporary"):
        publish_catalog(destination, "new\n")

    # Then: no owned temporary or published destination is left behind.
    assert not destination.exists()
    assert not tuple(tmp_path.glob(".catalog.json.tmp-*"))


def test_publish_catalog_preserves_metadata_failure_when_temporary_close_also_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: inspecting a new temporary fails and its descriptor close also reports an error.
    destination = tmp_path / "catalog.json"
    original_fstat = organize_outputs_catalog.os.fstat
    original_close = organize_outputs_catalog.os.close

    def fail_temp_fstat(descriptor: int) -> os.stat_result:
        name = Path(os.readlink(f"/proc/self/fd/{descriptor}")).name
        if name.startswith(".catalog.json.tmp-"):
            raise OSError("simulated temporary metadata failure")
        return original_fstat(descriptor)

    def close_temp_then_fail(descriptor: int) -> None:
        name = Path(os.readlink(f"/proc/self/fd/{descriptor}")).name
        original_close(descriptor)
        if name.startswith(".catalog.json.tmp-"):
            raise OSError("simulated temporary close failure")

    monkeypatch.setattr(organize_outputs_catalog.os, "fstat", fail_temp_fstat)
    monkeypatch.setattr(organize_outputs_catalog.os, "close", close_temp_then_fail)

    # When: temporary creation cannot capture its identity.
    with pytest.raises(CatalogPublicationError, match="unable to inspect catalog temporary"):
        publish_catalog(destination, "new\n")

    # Then: the typed metadata failure remains the surfaced contract error.
    assert not destination.exists()


def test_publish_catalog_preserves_parent_fsync_failure_when_parent_close_also_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the post-rename parent fsync and later parent descriptor close both fail.
    destination = tmp_path / "catalog.json"
    original_close = organize_outputs_catalog.os.close
    original_fsync = organize_outputs_catalog.os.fsync
    fsync_calls = 0

    def fail_parent_fsync(descriptor: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 2:
            raise OSError("simulated parent fsync failure")
        original_fsync(descriptor)

    def close_parent_then_fail(descriptor: int) -> None:
        name = Path(os.readlink(f"/proc/self/fd/{descriptor}")).name
        original_close(descriptor)
        if name == tmp_path.name:
            raise OSError("simulated parent close failure")

    monkeypatch.setattr(organize_outputs_catalog.os, "fsync", fail_parent_fsync)
    monkeypatch.setattr(organize_outputs_catalog.os, "close", close_parent_then_fail)

    # When: publication reaches the parent durability boundary.
    with pytest.raises(CatalogPublicationError, match="unable to fsync catalog parent"):
        publish_catalog(destination, "new\n")

    # Then: the already-published artifact is retained and the fsync failure is not masked.
    assert destination.read_bytes() == b"new\n"


def test_publish_catalog_rejects_temp_substitution_before_no_replace_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a racer replaces the closed temporary pathname immediately before publication.
    destination = tmp_path / "catalog.json"
    original_publish = organize_outputs_catalog._publish

    def replace_temp_before_publish(
        parent_descriptor: int,
        temporary_name: str,
        destination_name: str,
        path: Path,
        temporary_identity: tuple[int, int] | None = None,
    ) -> None:
        temporary = tmp_path / temporary_name
        temporary.unlink()
        temporary.write_bytes(b"racer-owned\n")
        if temporary_identity is None:
            original_publish(parent_descriptor, temporary_name, destination_name, path)
            return
        original_publish(parent_descriptor, temporary_name, destination_name, path, temporary_identity)

    monkeypatch.setattr(organize_outputs_catalog, "_publish", replace_temp_before_publish)

    # When: the publisher reaches its no-replace publication boundary.
    with pytest.raises(CatalogPublicationError, match="catalog temporary changed before publication"):
        publish_catalog(destination, "approved\n")

    # Then: the destination remains absent and cleanup preserves the racer's replacement.
    assert not destination.exists()
    temporary = next(tmp_path.glob(".catalog.json.tmp-*"))
    assert temporary.read_bytes() == b"racer-owned\n"
