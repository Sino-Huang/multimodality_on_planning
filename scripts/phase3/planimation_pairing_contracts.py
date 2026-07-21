"""Shared typed contracts for Phase 3 Planimation pairing workflows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NotRequired, TypedDict

from .traversal_state_types import JSONValue

SCHEMA_VERSION = "phase3_planimation_vlm_v1"
CORE_DOMAINS = frozenset({"blocksworld", "elevators", "ferry", "gripper", "logistics", "towers_of_hanoi", "visitall"})
CORE_BUCKETS = frozenset({"easy", "medium"})
ACTIVE_PLANNERS = frozenset({"gbfs", "ff", "iw", "graphplan"})
CURRENT_TRACE_ROOTS = (
    Path("outputs/phase3_curriculum_traces_15puzzle_easy_20260709_002417"),
    Path("outputs/phase3_curriculum_traces_safe_no_visitall_20260708_122431"),
    Path("outputs/phase3_curriculum_traces_visitall_20260708_191916"),
    Path("outputs/phase3_curriculum_traces_visitall_train_test_long_timeout_20260710_000503"),
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class PairingConfig:
    max_plan_length: int = 64
    max_trace_chars: int = 1_000_000
    domains: frozenset[str] = CORE_DOMAINS
    buckets: frozenset[str] = CORE_BUCKETS
    selected_pair_ids: frozenset[str] | None = None


@dataclass(frozen=True)
class RenderConfig:
    base_url: str = "https://planimation.planning.domains"
    timeout_seconds: int = 90
    request_delay_seconds: float = 1.0
    max_attempts: int = 3


class RendererResult(TypedDict):
    status: str
    attempts: int
    frame_path: NotRequired[str]
    trace_path: NotRequired[str]
    used_pddl_url: NotRequired[str]
    message: NotRequired[str]


StateRenderer = Callable[[Path, Path, Path, Path, RenderConfig], RendererResult]


class SourceSnapshotMismatch(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"source_snapshot_mismatch: {reason}")


class UnsupportedActivePlanner(SourceSnapshotMismatch):
    def __init__(self, planner: str) -> None:
        RuntimeError.__init__(self, f"unsupported_active_planner: {planner}")


JSONRecord = dict[str, JSONValue]
ProgressCallback = Callable[[JSONRecord], None]
