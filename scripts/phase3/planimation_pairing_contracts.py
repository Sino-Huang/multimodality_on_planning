"""Shared typed contracts for Phase 3 Planimation pairing workflows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from typing_extensions import NotRequired

from .traversal_state_types import JSONValue

SCHEMA_VERSION = "phase3_planimation_vlm_v1"
CORE_DOMAINS = frozenset({"blocksworld", "elevators", "ferry", "gripper", "logistics", "towers_of_hanoi", "visitall"})
CORE_BUCKETS = frozenset({"easy", "medium"})
ACTIVE_PLANNERS = frozenset({"gbfs", "ff", "iw", "graphplan"})
CURRENT_TRACE_ROOTS = (
    Path("outputs/reasoning_traces/curriculum/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round"),
)
CURRENT_IMAGE_FRAME_ROOT = Path("outputs/image_frames/phase3_planimation_frames_stratified_pilot_20260725")
CURRENT_SELECTION_CACHE_ROOT = Path("outputs/image_frames/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800")
CURRENT_TEXT_RECORD_ROOT = Path("outputs/reasoning_traces/vlm_records/stratified_pilot_20260725")
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
