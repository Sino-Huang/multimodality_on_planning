from __future__ import annotations

import fcntl
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from multiprocessing.context import SpawnContext
from multiprocessing.process import BaseProcess
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Final, Literal, Protocol, TypeAlias

from scripts.phase3.output_layout_lock import exclusive_output_layout_lock, shared_output_layout_lock


LockMode: TypeAlias = Literal["shared", "exclusive"]
InvalidRepositoryKind: TypeAlias = Literal["relative", "missing", "file"]
LockEntryKind: TypeAlias = Literal["symlink", "directory"]
LockFactory: TypeAlias = Callable[[Path], AbstractContextManager[None]]
EVENT_TIMEOUT_SECONDS: Final = 3.0
BLOCKED_POLL_SECONDS: Final = 0.2


class PipeEndpoint(Protocol):
    def send(self, obj: str) -> None: ...

    def recv(self) -> str: ...

    def poll(self, timeout: float | None = None) -> bool: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class Holder:
    process: BaseProcess
    attempted: PipeEndpoint
    entered: PipeEndpoint
    release: PipeEndpoint


def shared_lock_factory(repository: Path) -> AbstractContextManager[None]:
    return shared_output_layout_lock(repository)


def exclusive_lock_factory(repository: Path) -> AbstractContextManager[None]:
    return exclusive_output_layout_lock(repository)


LOCK_FACTORIES: Mapping[LockMode, LockFactory] = MappingProxyType(
    {"shared": shared_lock_factory, "exclusive": exclusive_lock_factory},
)
LOCK_OPERATIONS: Mapping[LockMode, int] = MappingProxyType(
    {"shared": fcntl.LOCK_SH, "exclusive": fcntl.LOCK_EX},
)


def hold_lock(
    repository: Path,
    mode: LockMode,
    attempted_sender: PipeEndpoint,
    entered_sender: PipeEndpoint,
    release_receiver: PipeEndpoint,
) -> None:
    try:
        attempted_sender.send("attempting")
        with LOCK_FACTORIES[mode](repository):
            entered_sender.send("entered")
            if not release_receiver.poll(EVENT_TIMEOUT_SECONDS):
                raise TimeoutError("parent did not release held output-layout lock")
            _ = release_receiver.recv()
    finally:
        attempted_sender.close()
        entered_sender.close()
        release_receiver.close()


def start_holder(context: SpawnContext, repository: Path, mode: LockMode) -> Holder:
    attempted_receiver, attempted_sender = context.Pipe(duplex=False)
    entered_receiver, entered_sender = context.Pipe(duplex=False)
    release_receiver, release_sender = context.Pipe(duplex=False)
    process = context.Process(
        target=hold_lock,
        args=(repository, mode, attempted_sender, entered_sender, release_receiver),
    )
    try:
        process.start()
    finally:
        attempted_sender.close()
        entered_sender.close()
        release_receiver.close()
    return Holder(process, attempted_receiver, entered_receiver, release_sender)


def assert_attempted(holder: Holder) -> None:
    assert holder.attempted.poll(EVENT_TIMEOUT_SECONDS)
    assert holder.attempted.recv() == "attempting"


def assert_entered(holder: Holder) -> None:
    assert holder.entered.poll(EVENT_TIMEOUT_SECONDS)
    assert holder.entered.recv() == "entered"


def release_holder(holder: Holder) -> None:
    holder.release.send("release")
    holder.process.join(EVENT_TIMEOUT_SECONDS)
    assert holder.process.exitcode == 0


def cleanup_holder(holder: Holder) -> None:
    try:
        if holder.process.is_alive():
            holder.process.terminate()
        holder.process.join(EVENT_TIMEOUT_SECONDS)
    finally:
        holder.attempted.close()
        holder.entered.close()
        holder.release.close()


def repository(tmp_path: Path) -> Path:
    synthetic_repository = (tmp_path / "repository").resolve()
    synthetic_repository.mkdir()
    return synthetic_repository
