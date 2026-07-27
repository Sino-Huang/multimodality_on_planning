from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .output_layout_contracts import VIEW_ROOT, ViewTargetKind


@dataclass(frozen=True, slots=True)
class OutputLayoutViewLink:
    location: Path
    protected_target: Path
    readlink_target: str
    target_kind: ViewTargetKind

    @property
    def is_directory(self) -> bool:
        return self.target_kind == "directory"

    def destination(self, outputs_root: Path) -> Path:
        return outputs_root.parent / VIEW_ROOT / self.location


@dataclass(frozen=True, slots=True)
class OutputLayoutViewViolation:
    rule: str
    path: Path


class OutputLayoutViewError(RuntimeError):
    def __init__(self, violations: tuple[OutputLayoutViewViolation, ...]) -> None:
        self.violations: tuple[OutputLayoutViewViolation, ...] = violations
        super().__init__("; ".join(f"{entry.rule}: {entry.path}" for entry in violations))


@dataclass(frozen=True, slots=True)
class PinnedPath:
    path: Path
    device: int
    inode: int
    mode: int
    content_token: bytes | None = None

    @classmethod
    def from_status(cls, path: Path, status: os.stat_result, content_token: bytes | None = None) -> PinnedPath:
        return cls(path, status.st_dev, status.st_ino, stat.S_IFMT(status.st_mode), content_token)

    def matches(self, status: os.stat_result, content_token: bytes | None = None) -> bool:
        return (status.st_dev, status.st_ino, stat.S_IFMT(status.st_mode), content_token) == (
            self.device,
            self.inode,
            self.mode,
            self.content_token,
        )
