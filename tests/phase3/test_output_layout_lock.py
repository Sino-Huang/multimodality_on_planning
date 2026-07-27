from __future__ import annotations

import multiprocessing as mp
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

import pytest

from scripts.phase3.output_layout_lock import (
    OutputLayoutLockError,
    exclusive_output_layout_lock,
)
from tests.phase3.output_layout_lock_test_support import (
    BLOCKED_POLL_SECONDS,
    LOCK_FACTORIES,
    Holder,
    InvalidRepositoryKind,
    LockEntryKind,
    LockMode,
    assert_entered,
    cleanup_holder,
    release_holder,
    repository,
    start_holder,
)


class BodyFailure(Exception):
    pass


@pytest.mark.parametrize(
    ("first_mode", "second_mode", "second_enters"),
    [
        pytest.param("shared", "shared", True, id="shared-coexists-with-shared"),
        pytest.param("shared", "exclusive", False, id="shared-blocks-exclusive"),
        pytest.param("exclusive", "shared", False, id="exclusive-blocks-shared"),
        pytest.param("exclusive", "exclusive", False, id="exclusive-blocks-exclusive"),
    ],
)
def test_repository_scoped_lock_coordinates_modes_before_outputs_directory_exists(
    tmp_path: Path,
    first_mode: LockMode,
    second_mode: LockMode,
    second_enters: bool,
) -> None:
    # Given: one absolute repository without outputs/ and a spawned holder.
    repository_root = repository(tmp_path)
    context = mp.get_context("spawn")
    first = start_holder(context, repository_root, first_mode)
    second: Holder | None = None

    try:
        assert_entered(first)
        assert not (repository_root / "outputs").exists()
        second = start_holder(context, repository_root, second_mode)

        # When: another process acquires a repository-only advisory lock.
        if second_enters:
            assert_entered(second)
        else:
            assert not second.entered.poll(BLOCKED_POLL_SECONDS)

        # Then: only compatible modes overlap, and blocked modes enter after release.
        release_holder(first)
        if not second_enters:
            assert_entered(second)
        release_holder(second)
    finally:
        if second is not None:
            cleanup_holder(second)
        cleanup_holder(first)


def test_body_exception_releases_lock_for_another_process(tmp_path: Path) -> None:
    # Given: an exclusive holder whose body raises before it completes.
    repository_root = repository(tmp_path)
    with pytest.raises(BodyFailure):
        with exclusive_output_layout_lock(repository_root):
            raise BodyFailure()
    holder = start_holder(mp.get_context("spawn"), repository_root, "exclusive")

    try:
        # When: another process attempts the repository-scoped exclusive lock.
        assert_entered(holder)

        # Then: the exception path has released the lock.
        release_holder(holder)
    finally:
        cleanup_holder(holder)


@pytest.mark.parametrize("mode", ["shared", "exclusive"])
@pytest.mark.parametrize("invalid_kind", ["relative", "missing", "file"])
def test_invalid_repository_root_fails_closed_without_entering_body(
    tmp_path: Path,
    mode: LockMode,
    invalid_kind: InvalidRepositoryKind,
) -> None:
    # Given: a malformed repository root.
    invalid_repositories: Mapping[InvalidRepositoryKind, tuple[Path, bool]] = MappingProxyType(
        {
            "relative": (Path("repository"), False),
            "missing": (tmp_path / "missing-repository", False),
            "file": (tmp_path / "repository-file", True),
        },
    )
    invalid_repository, repository_is_file = invalid_repositories[invalid_kind]
    if repository_is_file:
        _ = invalid_repository.write_text("not a repository", encoding="utf-8")
    body_entered = False

    # When: either advisory mode receives the invalid root.
    with pytest.raises(OutputLayoutLockError) as error:
        with LOCK_FACTORIES[mode](invalid_repository):
            body_entered = True

    # Then: validation rejects it before the protected body runs.
    assert error.value.path == invalid_repository
    assert error.value.rule
    assert not body_entered


@pytest.mark.parametrize("mode", ["shared", "exclusive"])
@pytest.mark.parametrize("entry_kind", ["symlink", "directory"])
def test_preexisting_legacy_lock_path_is_ignored_without_mutation(
    tmp_path: Path,
    mode: LockMode,
    entry_kind: LockEntryKind,
) -> None:
    # Given: an unused legacy lock pathname occupied by a non-file entry.
    repository_root = repository(tmp_path)
    lock_path = repository_root / ".phase3-output-layout.lock"
    lock_entry_is_symlink: Mapping[LockEntryKind, bool] = MappingProxyType(
        {"symlink": True, "directory": False},
    )
    target: Path | None = None
    if lock_entry_is_symlink[entry_kind]:
        target = repository_root / "lock-target"
        _ = target.write_text("target", encoding="utf-8")
        lock_path.symlink_to(target)
    else:
        lock_path.mkdir()
    # When: either repository-descriptor lock mode is acquired.
    with LOCK_FACTORIES[mode](repository_root):
        pass

    # Then: the unused pathname has not been followed, accepted, or replaced.
    if lock_entry_is_symlink[entry_kind]:
        assert lock_path.is_symlink()
        assert target is not None
        assert target.read_text(encoding="utf-8") == "target"
    else:
        assert lock_path.is_dir()


def _failing_flock(_descriptor: int, _operation: int) -> None:
    raise OSError("flock acquisition failed")


@pytest.mark.parametrize("mode", ["shared", "exclusive"])
def test_flock_acquisition_failure_propagates_without_entering_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: LockMode,
) -> None:
    # Given: a valid synthetic repository and a failing blocking flock operation.
    repository_root = repository(tmp_path)
    monkeypatch.setattr("scripts.phase3.output_layout_lock.fcntl.flock", _failing_flock)
    body_entered = False

    # When: either advisory mode attempts acquisition.
    with pytest.raises(OSError, match="flock acquisition failed"):
        with LOCK_FACTORIES[mode](repository_root):
            body_entered = True

    # Then: acquisition errors propagate and the protected body remains unentered.
    assert not body_entered


@pytest.mark.parametrize("mode", ["shared", "exclusive"])
def test_lock_requires_only_repository_and_no_outputs_directory(
    tmp_path: Path,
    mode: LockMode,
) -> None:
    # Given: an absolute canonical repository with no outputs/ child directory.
    repository_root = repository(tmp_path)
    body_entered = False

    # When: each public repository-only lock is entered.
    with LOCK_FACTORIES[mode](repository_root):
        body_entered = True

    # Then: neither lock requires an output root or outputs/ directory.
    assert body_entered
    assert not (repository_root / "outputs").exists()


@pytest.mark.parametrize("mode", ["shared", "exclusive"])
def test_lock_never_creates_the_legacy_lock_path(tmp_path: Path, mode: LockMode) -> None:
    # Given: a fresh repository with no legacy lock pathname.
    repository_root = repository(tmp_path)
    legacy_lock_path = repository_root / ".phase3-output-layout.lock"
    assert not legacy_lock_path.exists()

    # When: either descriptor-backed advisory lock is acquired.
    with LOCK_FACTORIES[mode](repository_root):
        # Then: acquisition does not materialize the obsolete pathname.
        assert not legacy_lock_path.exists()

    # Then: releasing the lock also leaves no obsolete pathname behind.
    assert not legacy_lock_path.exists()
