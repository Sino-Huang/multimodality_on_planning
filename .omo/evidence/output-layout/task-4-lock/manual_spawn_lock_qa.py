from __future__ import annotations

import multiprocessing as mp
from collections.abc import Callable
from contextlib import AbstractContextManager
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.phase3.output_layout_lock import exclusive_output_layout_lock, shared_output_layout_lock


_TIMEOUT_SECONDS = 5.0
_BLOCKED_POLL_SECONDS = 0.2
_ATTEMPTING = b"attempting"
_ACQUIRED = b"acquired"
_RELEASE = b"release"
_LEGACY_LOCK_FILENAME = ".phase3-output-layout.lock"

LockFactory = Callable[[Path], AbstractContextManager[None]]


class ManualSpawnLockError(Exception):
    def __init__(self, *, message: str) -> None:
        self.message: str = message
        super().__init__(message)


def _acquire_shared_lock(
    repository: Path,
    event_sender: Connection,
    release_receiver: Connection,
) -> None:
    try:
        event_sender.send_bytes(_ATTEMPTING)
        with shared_output_layout_lock(repository):
            event_sender.send_bytes(_ACQUIRED)
            if not release_receiver.poll(_TIMEOUT_SECONDS):
                raise ManualSpawnLockError(message="parent did not release manual QA lock")
            if release_receiver.recv_bytes() != _RELEASE:
                raise ManualSpawnLockError(message="parent sent an unexpected manual QA release event")
    finally:
        event_sender.close()
        release_receiver.close()


def _verify_fresh_repository_creates_no_legacy_lock_path(temporary_root: Path) -> None:
    failures: list[str] = []
    lock_factories: tuple[tuple[str, LockFactory], ...] = (
        ("shared", shared_output_layout_lock),
        ("exclusive", exclusive_output_layout_lock),
    )
    for mode, lock_factory in lock_factories:
        repository = temporary_root / f"fresh-{mode}-repository"
        repository.mkdir()
        legacy_lock_path = repository / _LEGACY_LOCK_FILENAME
        if legacy_lock_path.exists():
            failures.append(f"{mode} legacy lock path existed before acquisition")
        with lock_factory(repository):
            if legacy_lock_path.exists():
                failures.append(f"{mode} lock acquisition created the legacy lock path")
        if legacy_lock_path.exists():
            failures.append(f"{mode} legacy lock path existed after release")
    if failures:
        raise ManualSpawnLockError(message="; ".join(failures))


def _verify_legacy_path_replacement_does_not_admit_shared_holder(temporary_root: Path) -> None:
    context = mp.get_context("spawn")
    repository = temporary_root / "replacement-repository"
    repository.mkdir()
    legacy_lock_path = repository / _LEGACY_LOCK_FILENAME
    _ = legacy_lock_path.write_text("legacy", encoding="utf-8")
    replacement_path = repository / "replacement-lock-path"
    _ = replacement_path.write_text("replacement", encoding="utf-8")
    event_receiver, event_sender = context.Pipe(duplex=False)
    release_receiver, release_sender = context.Pipe(duplex=False)
    process: BaseProcess = context.Process(
        target=_acquire_shared_lock,
        args=(repository, event_sender, release_receiver),
    )
    try:
        with exclusive_output_layout_lock(repository):
            _ = replacement_path.replace(legacy_lock_path)
            process.start()
            event_sender.close()
            release_receiver.close()
            if not event_receiver.poll(_TIMEOUT_SECONDS) or event_receiver.recv_bytes() != _ATTEMPTING:
                raise ManualSpawnLockError(message="spawned shared contender did not attempt acquisition")
            if event_receiver.poll(_BLOCKED_POLL_SECONDS):
                raise ManualSpawnLockError(
                    message="legacy pathname replacement admitted a shared contender while exclusive lock was held"
                )
        if not event_receiver.poll(_TIMEOUT_SECONDS) or event_receiver.recv_bytes() != _ACQUIRED:
            raise ManualSpawnLockError(message="spawned shared contender did not acquire after exclusive release")
        release_sender.send_bytes(_RELEASE)
        process.join(_TIMEOUT_SECONDS)
        if process.exitcode != 0:
            raise ManualSpawnLockError(message=f"spawned shared contender exited with {process.exitcode}")
    finally:
        if process.is_alive():
            process.terminate()
        process.join(_TIMEOUT_SECONDS)
        event_receiver.close()
        release_sender.close()


def main() -> None:
    with TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory).resolve()
        failures: list[str] = []
        try:
            _verify_fresh_repository_creates_no_legacy_lock_path(temporary_root)
        except ManualSpawnLockError as error:
            failures.append(error.message)
        else:
            print("manual-spawn-lock-no-legacy-file-creation: PASS")
        try:
            _verify_legacy_path_replacement_does_not_admit_shared_holder(temporary_root)
        except ManualSpawnLockError as error:
            failures.append(error.message)
        else:
            print("manual-spawn-lock-replacement-resistance: PASS")
        if failures:
            raise ManualSpawnLockError(message=" | ".join(failures))


if __name__ == "__main__":
    main()
