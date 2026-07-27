from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .output_layout_writer_registry import WriterDetectionError, WriterTarget, writer_targets


@dataclass(frozen=True, slots=True)
class WriterOverlap:
    pid: int
    command: str
    target: Path


def find_overlapping_writer(source: Path, *, proc_root: Path = Path("/proc"), own_pid: int | None = None) -> WriterOverlap | None:
    canonical_source = source.resolve(strict=False)
    current_pid = os.getpid() if own_pid is None else own_pid
    try:
        process_entries = tuple(proc_root.iterdir())
    except OSError as error:
        raise WriterDetectionError("cannot enumerate proc metadata") from error
    for process in process_entries:
        if not process.name.isdecimal():
            continue
        pid = int(process.name)
        if pid == current_pid:
            continue
        arguments = _read_cmdline(process, pid)
        if arguments is None:
            continue
        try:
            targets = writer_targets(arguments)
        except WriterDetectionError as error:
            raise WriterDetectionError(error.rule, pid) from error
        if not targets:
            continue
        for target in targets:
            if Path(target.value).is_absolute():
                canonical_target = Path(target.value).resolve(strict=False)
                if _overlaps(canonical_source, canonical_target):
                    return WriterOverlap(pid=pid, command=target.command, target=canonical_target)
        relative_targets = tuple(target for target in targets if not Path(target.value).is_absolute())
        if not relative_targets:
            continue
        cwd = _read_cwd(process, pid)
        if cwd is None:
            continue
        for target in relative_targets:
            canonical_target = _canonical_target(target, cwd)
            if _overlaps(canonical_source, canonical_target):
                return WriterOverlap(pid=pid, command=target.command, target=canonical_target)
    return None


def _read_cmdline(process: Path, pid: int) -> tuple[str, ...] | None:
    try:
        payload = (process / "cmdline").read_bytes()
    except FileNotFoundError:
        if _process_disappeared(process, pid):
            return None
        raise WriterDetectionError("cannot read cmdline", pid) from None
    except ProcessLookupError:
        return None
    except OSError as error:
        raise WriterDetectionError("cannot read cmdline", pid) from error
    if payload and not payload.endswith(b"\0"):
        raise WriterDetectionError("malformed cmdline framing", pid)
    return tuple(part.decode("utf-8", errors="surrogateescape") for part in payload.split(b"\0") if part)


def _read_cwd(process: Path, pid: int) -> Path | None:
    try:
        return (process / "cwd").resolve(strict=True)
    except FileNotFoundError:
        if _process_disappeared(process, pid):
            return None
        raise WriterDetectionError("cannot resolve cwd", pid) from None
    except ProcessLookupError:
        return None
    except OSError as error:
        raise WriterDetectionError("cannot resolve cwd", pid) from error


def _canonical_target(target: WriterTarget, cwd: Path) -> Path:
    candidate = Path(target.value)
    if not candidate.is_absolute():
        candidate = cwd / candidate
    return candidate.resolve(strict=False)


def _overlaps(source: Path, target: Path) -> bool:
    return source.is_relative_to(target) or target.is_relative_to(source)


def _process_disappeared(process: Path, pid: int) -> bool:
    try:
        _ = process.stat()
    except (FileNotFoundError, ProcessLookupError):
        return True
    except OSError as error:
        raise WriterDetectionError("cannot inspect process metadata", pid) from error
    return False
