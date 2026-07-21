"""Shared rendering contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, TypeAlias, TypedDict

from .adapters import NormalizedCandidate

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

RENDER_SUCCESS_STATUS = "success"
RENDER_FAILED_STATUS = "failed"
RENDER_FAILED_REASON = "render_failed"
RENDER_REJECTION_STAGE = "render"
TRACE_FILENAME = "trace.vfg.json"
FRAMES_DIRNAME = "frames"
RESULT_FILENAME = "result.json"
DEFAULT_RENDER_SUBDIR = "render"


class PddlPoster(Protocol):
    def __call__(self, *, domain_path: Path, problem_path: Path, animation_profile_path: Path, pddl_candidates: list[str], timeout: int) -> tuple[bytes, str]: ...


class VfgPoster(Protocol):
    def __call__(self, *, vfg_bytes: bytes, output_format: str, vfg_candidates: list[str], start_step: int, stop_step: int, quality: int, timeout: int) -> tuple[bytes, str]: ...


class LocalFrameRenderer(Protocol):
    def __call__(self, *, vfg_bytes: bytes, output_dir: Path, start_step: int, stop_step: int) -> int: ...


class ArchiveExtractor(Protocol):
    def __call__(self, archive_bytes: bytes, output_dir: Path) -> int: ...


class HostPreflight(Protocol):
    def __call__(self, root_url: str, timeout: int) -> Mapping[str, JsonValue]: ...


class PlanimationDefaults(TypedDict):
    post_pddl_for_vfg_fn: PddlPoster
    post_vfg_for_visualisation_fn: VfgPoster
    render_vfg_to_local_png_frames_fn: LocalFrameRenderer
    preflight_host_fn: HostPreflight


@dataclass(frozen=True)
class RenderRequest:
    candidate: NormalizedCandidate
    render_profile_path: Path
    output_dir: Path
    timeout_seconds: int


@dataclass(frozen=True)
class RenderOutcome:
    candidate_id: str
    renderer_id: str
    output_dir: Path
    render_status: str
    trace_path: Path | None = None
    frames_dir: Path | None = None
    frame_paths: tuple[Path, ...] = ()
    used_pddl_url: str | None = None
    used_vfg_url: str | None = None
    used_local_renderer: bool = False
    elapsed_seconds: float = 0.0
    message: str = ""
    details: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self, *, render_profile_path: Path, result_path: Path | None = None) -> dict[str, JsonValue]:
        return {"candidate_id": self.candidate_id, "elapsed_seconds": round(self.elapsed_seconds, 3), "frame_count": len(self.frame_paths), "frame_paths": [str(path) for path in self.frame_paths], "frames_dir": str(self.frames_dir) if self.frames_dir else "", "message": self.message, "render_profile_path": str(render_profile_path), "render_status": self.render_status, "renderer_id": self.renderer_id, "result_path": str(result_path) if result_path else "", "status": self.render_status, "trace_path": str(self.trace_path) if self.trace_path else "", "used_local_renderer": self.used_local_renderer, "used_pddl_url": self.used_pddl_url, "used_vfg_url": self.used_vfg_url, "details": dict(self.details)}


@dataclass(frozen=True)
class RendererPreflightStatus:
    renderer_id: str
    ready: bool
    details: dict[str, JsonValue] = field(default_factory=dict)
    issues: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, JsonValue]:
        return {"renderer_id": self.renderer_id, "ready": self.ready, "details": dict(self.details), "issues": list(self.issues)}


@dataclass(frozen=True)
class RenderDomainPreflight:
    domain_id: str
    render_profile_path: str
    render_profile_configured: bool

    def to_dict(self) -> dict[str, JsonValue]:
        return {"domain_id": self.domain_id, "render_profile_path": self.render_profile_path, "render_profile_configured": self.render_profile_configured}


@dataclass(frozen=True)
class RenderingPreflightReport:
    require_rendering: bool
    ready: bool
    render_profile_ready: bool
    selected_domain_ids: tuple[str, ...]
    domains: tuple[RenderDomainPreflight, ...]
    renderer: RendererPreflightStatus | None = None
    issues: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, JsonValue]:
        return {"domains": [domain.to_dict() for domain in self.domains], "issues": list(self.issues), "ready": self.ready, "render_profile_ready": self.render_profile_ready, "renderer": self.renderer.to_dict() if self.renderer else None, "require_rendering": self.require_rendering, "selected_domain_ids": list(self.selected_domain_ids)}


@dataclass(frozen=True)
class RenderGateDecision:
    accepted: bool
    message: str = ""
    issues: tuple[str, ...] = ()


class Renderer(ABC):
    renderer_id: str

    @abstractmethod
    def preflight(self, *, timeout_seconds: int) -> RendererPreflightStatus: ...

    @abstractmethod
    def render(self, request: RenderRequest) -> RenderOutcome: ...
