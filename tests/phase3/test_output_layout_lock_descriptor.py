from __future__ import annotations

import fcntl
import multiprocessing as mp
import os
from pathlib import Path

import pytest

from output_layout_lock_test_support import (
    BLOCKED_POLL_SECONDS,
    LOCK_FACTORIES,
    LOCK_OPERATIONS,
    Holder,
    LockMode,
    assert_attempted,
    assert_entered,
    cleanup_holder,
    release_holder,
    repository,
    start_holder,
)


def test_replacing_legacy_path_during_exclusive_hold_does_not_admit_shared_holder(tmp_path: Path) -> None:
    # Given: an exclusive holder and a replaceable legacy pathname.
    repository_root = repository(tmp_path)
    legacy_lock_path = repository_root / ".phase3-output-layout.lock"
    _ = legacy_lock_path.write_text("legacy", encoding="utf-8")
    replacement_path = repository_root / "replacement-lock-path"
    _ = replacement_path.write_text("replacement", encoding="utf-8")
    context = mp.get_context("spawn")
    first = start_holder(context, repository_root, "exclusive")
    second: Holder | None = None

    try:
        assert_entered(first)
        _ = replacement_path.replace(legacy_lock_path)
        second = start_holder(context, repository_root, "shared")
        assert_attempted(second)

        # When: the shared contender starts after the legacy pathname changes identity.
        # Then: the directory identity still blocks it until the exclusive holder releases.
        assert not second.entered.poll(BLOCKED_POLL_SECONDS)
        release_holder(first)
        assert_entered(second)
        release_holder(second)
    finally:
        if second is not None:
            cleanup_holder(second)
        cleanup_holder(first)


@pytest.mark.parametrize("mode", ["shared", "exclusive"])
def test_descriptor_identity_is_checked_before_and_after_flock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: LockMode,
) -> None:
    # Given: instrumentation that observes descriptor identity checks and flock calls.
    repository_root = repository(tmp_path)
    events: list[str] = []
    original_fstat = os.fstat
    original_flock = fcntl.flock

    def record_fstat(descriptor: int) -> os.stat_result:
        events.append("fstat")
        return original_fstat(descriptor)

    def record_flock(descriptor: int, operation: int) -> None:
        events.append(f"flock:{operation}")
        original_flock(descriptor, operation)

    monkeypatch.setattr("scripts.phase3.output_layout_lock.os.fstat", record_fstat)
    monkeypatch.setattr("scripts.phase3.output_layout_lock.fcntl.flock", record_flock)
    operation = LOCK_OPERATIONS[mode]

    # When: the public lock enters its protected body.
    with LOCK_FACTORIES[mode](repository_root):
        events.append("body")

    # Then: the held descriptor is identity-checked on both sides of acquisition.
    acquire_index = events.index(f"flock:{operation}")
    body_index = events.index("body")
    assert "fstat" in events[:acquire_index]
    assert "fstat" in events[acquire_index + 1 : body_index]


@pytest.mark.parametrize("mode", ["shared", "exclusive"])
def test_repository_descriptor_remains_open_for_the_full_lock_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: LockMode,
) -> None:
    # Given: a repository and descriptor lifecycle instrumentation.
    repository_root = repository(tmp_path)
    repository_status = repository_root.stat()
    events: list[str] = []
    acquired_descriptors: list[tuple[int, os.stat_result]] = []
    original_flock = fcntl.flock
    original_fstat = os.fstat
    original_close = os.close
    operation = LOCK_OPERATIONS[mode]

    def record_flock(descriptor: int, flock_operation: int) -> None:
        events.append(f"flock:{descriptor}:{flock_operation}")
        if flock_operation == operation:
            acquired_descriptors.append((descriptor, original_fstat(descriptor)))
        original_flock(descriptor, flock_operation)

    def record_close(descriptor: int) -> None:
        events.append(f"close:{descriptor}")
        original_close(descriptor)

    monkeypatch.setattr("scripts.phase3.output_layout_lock.fcntl.flock", record_flock)
    monkeypatch.setattr("scripts.phase3.output_layout_lock.os.close", record_close)

    # When: the public lock holds the repository descriptor through its body.
    with LOCK_FACTORIES[mode](repository_root):
        assert acquired_descriptors
        descriptor = acquired_descriptors[0][0]
        assert f"close:{descriptor}" not in events

    # Then: flock used the repository descriptor, which unlocked before it closed.
    descriptor, descriptor_status = acquired_descriptors[0]
    assert (descriptor_status.st_dev, descriptor_status.st_ino) == (
        repository_status.st_dev,
        repository_status.st_ino,
    )
    assert events.index(f"flock:{descriptor}:{fcntl.LOCK_UN}") < events.index(f"close:{descriptor}")


@pytest.mark.parametrize("mode", ["shared", "exclusive"])
def test_flock_acquisition_failure_closes_descriptor_without_unlock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: LockMode,
) -> None:
    # Given: a descriptor lifecycle where the acquisition flock fails.
    repository_root = repository(tmp_path)
    events: list[str] = []
    original_close = os.close

    def fail_acquisition(descriptor: int, operation: int) -> None:
        events.append(f"flock:{descriptor}:{operation}")
        raise OSError("flock acquisition failed")

    def record_close(descriptor: int) -> None:
        events.append(f"close:{descriptor}")
        original_close(descriptor)

    monkeypatch.setattr("scripts.phase3.output_layout_lock.fcntl.flock", fail_acquisition)
    monkeypatch.setattr("scripts.phase3.output_layout_lock.os.close", record_close)

    # When: either public lock mode cannot acquire flock.
    with pytest.raises(OSError, match="flock acquisition failed"):
        with LOCK_FACTORIES[mode](repository_root):
            pytest.fail("the protected body must not run")

    # Then: acquisition closes its descriptor and never attempts an unlock.
    assert any(event.startswith("close:") for event in events)
    assert all(not event.endswith(f":{fcntl.LOCK_UN}") for event in events)
