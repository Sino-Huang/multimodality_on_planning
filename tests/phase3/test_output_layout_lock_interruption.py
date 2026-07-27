from __future__ import annotations

import fcntl
import os
from pathlib import Path

import pytest

from output_layout_lock_test_support import (
    LOCK_FACTORIES,
    LOCK_OPERATIONS,
    LockMode,
    repository,
)


@pytest.mark.parametrize("mode", ["shared", "exclusive"])
def test_keyboard_interrupt_during_flock_closes_descriptor_without_unlock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: LockMode,
) -> None:
    # Given: flock raises KeyboardInterrupt while acquiring the descriptor lock.
    repository_root = repository(tmp_path)
    events: list[str] = []
    original_close = os.close
    interrupted_descriptors: list[int] = []
    body_entered = False

    def interrupt_acquisition(descriptor: int, operation: int) -> None:
        interrupted_descriptors.append(descriptor)
        events.append(f"flock:{descriptor}:{operation}")
        raise KeyboardInterrupt()

    def record_close(descriptor: int) -> None:
        events.append(f"close:{descriptor}")
        original_close(descriptor)

    monkeypatch.setattr("scripts.phase3.output_layout_lock.fcntl.flock", interrupt_acquisition)
    monkeypatch.setattr("scripts.phase3.output_layout_lock.os.close", record_close)

    # When: either public lock mode is interrupted during acquisition.
    try:
        with pytest.raises(KeyboardInterrupt):
            with LOCK_FACTORIES[mode](repository_root):
                body_entered = True
    finally:
        if interrupted_descriptors and f"close:{interrupted_descriptors[0]}" not in events:
            original_close(interrupted_descriptors[0])

    # Then: interruption closes its descriptor and never attempts an unlock.
    assert interrupted_descriptors
    interrupted_descriptor = interrupted_descriptors[0]
    assert not body_entered
    assert events == [
        f"flock:{interrupted_descriptor}:{LOCK_OPERATIONS[mode]}",
        f"close:{interrupted_descriptor}",
    ]
    assert all(not event.endswith(f":{fcntl.LOCK_UN}") for event in events)


@pytest.mark.parametrize("mode", ["shared", "exclusive"])
def test_keyboard_interrupt_after_flock_unlocks_then_closes_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: LockMode,
) -> None:
    # Given: flock succeeds, then the post-acquisition descriptor check is interrupted.
    repository_root = repository(tmp_path)
    events: list[str] = []
    verification_calls = 0
    acquired_descriptors: list[int] = []
    original_flock = fcntl.flock
    original_close = os.close
    operation = LOCK_OPERATIONS[mode]
    body_entered = False

    def interrupt_after_acquisition(repository_path: Path, descriptor: int) -> None:
        nonlocal verification_calls
        _ = repository_path
        _ = descriptor
        verification_calls += 1
        if verification_calls == 2:
            raise KeyboardInterrupt()

    def record_flock(descriptor: int, flock_operation: int) -> None:
        events.append(f"flock:{descriptor}:{flock_operation}")
        if flock_operation == operation:
            acquired_descriptors.append(descriptor)
        original_flock(descriptor, flock_operation)

    def record_close(descriptor: int) -> None:
        events.append(f"close:{descriptor}")
        original_close(descriptor)

    monkeypatch.setattr(
        "scripts.phase3.output_layout_lock._verify_repository_descriptor",
        interrupt_after_acquisition,
    )
    monkeypatch.setattr("scripts.phase3.output_layout_lock.fcntl.flock", record_flock)
    monkeypatch.setattr("scripts.phase3.output_layout_lock.os.close", record_close)

    # When: either public lock mode is interrupted after acquiring flock.
    try:
        with pytest.raises(KeyboardInterrupt):
            with LOCK_FACTORIES[mode](repository_root):
                body_entered = True
    finally:
        if acquired_descriptors and f"close:{acquired_descriptors[0]}" not in events:
            original_flock(acquired_descriptors[0], fcntl.LOCK_UN)
            original_close(acquired_descriptors[0])

    # Then: interruption unlocks and closes the acquired descriptor in order.
    assert acquired_descriptors
    acquired_descriptor = acquired_descriptors[0]
    assert verification_calls == 2
    assert not body_entered
    assert events == [
        f"flock:{acquired_descriptor}:{operation}",
        f"flock:{acquired_descriptor}:{fcntl.LOCK_UN}",
        f"close:{acquired_descriptor}",
    ]
