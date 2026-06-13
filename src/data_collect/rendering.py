"""Rendering contract helpers for curriculum data collection."""

from __future__ import annotations

import json
import shutil
import time
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from importlib import util as importlib_util
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from .adapters import NormalizedCandidate
from .config import CurriculumConfig
from .metadata import AcceptedInstanceMetadata, RejectedCandidateMetadata, build_candidate_id, build_instance_id

DEFAULT_BASE_URL = "https://planimation.planning.domains"


def _resolve_planimation_defaults() -> dict[str, Any]:
    try:
        from scripts.planimation_phase1 import (
            extract_png_archive,
            post_pddl_for_vfg,
            post_vfg_for_visualisation,
            preflight_host,
            render_vfg_to_local_png_frames,
        )
    except ModuleNotFoundError as error:  # pragma: no cover - depends on runtime environment
        missing_module = getattr(error, "name", None) or "unknown"
        raise RuntimeError(
            "Planimation renderer dependencies unavailable: "
            f"missing Python package '{missing_module}' required by scripts.planimation_phase1"
        ) from error

    return {
        "extract_png_archive_fn": extract_png_archive,
        "post_pddl_for_vfg_fn": post_pddl_for_vfg,
        "post_vfg_for_visualisation_fn": post_vfg_for_visualisation,
        "preflight_host_fn": preflight_host,
        "render_vfg_to_local_png_frames_fn": render_vfg_to_local_png_frames,
    }


def _derive_endpoint_candidates(
    base_url: str | None,
    pddl_url: str | None,
    vfg_url: str | None,
) -> tuple[list[str], list[str], str]:
    if pddl_url:
        pddl_candidates = [pddl_url]
    else:
        if not base_url:
            raise ValueError("Either base_url or pddl_url must be provided")
        trimmed = base_url.rstrip("/")
        pddl_candidates = [
            f"{trimmed}/upload/pddl",
            f"{trimmed}/upload/(?P<filename>[^/]+)$",
            f"{trimmed}/upload/",
        ]

    if vfg_url:
        vfg_candidates = [vfg_url]
    else:
        if not base_url:
            raise ValueError("Either base_url or vfg_url must be provided")
        trimmed = base_url.rstrip("/")
        vfg_candidates = [
            f"{trimmed}/downloadVisualisation",
            f"{trimmed}/downloadVisualisation/",
        ]

    root_source = base_url or pddl_candidates[0]
    parsed = urlparse(root_source)
    root_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else root_source
    return pddl_candidates, vfg_candidates, root_url


def _extract_png_archive(archive_bytes: bytes, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BytesIO(archive_bytes), "r") as archive:
        archive.extractall(output_dir)
    return len(list(output_dir.rglob("*.png")))

RENDER_SUCCESS_STATUS = "success"
RENDER_FAILED_STATUS = "failed"
RENDER_FAILED_REASON = "render_failed"
RENDER_REJECTION_STAGE = "render"
TRACE_FILENAME = "trace.vfg.json"
FRAMES_DIRNAME = "frames"
RESULT_FILENAME = "result.json"
DEFAULT_RENDER_SUBDIR = "render"

_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc```\xf8\x0f"
    b"\x00\x01\x01\x01\x00\x18\xdd\x8d\xb1\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


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
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, render_profile_path: Path, result_path: Path | None = None) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "frame_count": len(self.frame_paths),
            "frame_paths": [str(path) for path in self.frame_paths],
            "frames_dir": str(self.frames_dir) if self.frames_dir is not None else "",
            "message": self.message,
            "render_profile_path": str(render_profile_path),
            "render_status": self.render_status,
            "renderer_id": self.renderer_id,
            "result_path": str(result_path) if result_path is not None else "",
            "status": self.render_status,
            "trace_path": str(self.trace_path) if self.trace_path is not None else "",
            "used_local_renderer": self.used_local_renderer,
            "used_pddl_url": self.used_pddl_url,
            "used_vfg_url": self.used_vfg_url,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class RendererPreflightStatus:
    renderer_id: str
    ready: bool
    details: dict[str, Any] = field(default_factory=dict)
    issues: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "renderer_id": self.renderer_id,
            "ready": self.ready,
            "details": dict(self.details),
            "issues": list(self.issues),
        }


@dataclass(frozen=True)
class RenderDomainPreflight:
    domain_id: str
    render_profile_path: str
    render_profile_configured: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "render_profile_path": self.render_profile_path,
            "render_profile_configured": self.render_profile_configured,
        }


@dataclass(frozen=True)
class RenderingPreflightReport:
    require_rendering: bool
    ready: bool
    render_profile_ready: bool
    selected_domain_ids: tuple[str, ...]
    domains: tuple[RenderDomainPreflight, ...]
    renderer: RendererPreflightStatus | None = None
    issues: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "domains": [domain.to_dict() for domain in self.domains],
            "issues": list(self.issues),
            "ready": self.ready,
            "render_profile_ready": self.render_profile_ready,
            "renderer": self.renderer.to_dict() if self.renderer is not None else None,
            "require_rendering": self.require_rendering,
            "selected_domain_ids": list(self.selected_domain_ids),
        }


@dataclass(frozen=True)
class RenderGateDecision:
    accepted: bool
    message: str = ""
    issues: tuple[str, ...] = ()


class Renderer(ABC):
    renderer_id: str

    @abstractmethod
    def preflight(self, *, timeout_seconds: int) -> RendererPreflightStatus:
        """Report whether the renderer is ready to be used."""

    @abstractmethod
    def render(self, request: RenderRequest) -> RenderOutcome:
        """Render one normalized candidate into trace/frame artifacts."""


class FakeRenderer(Renderer):
    def __init__(
        self,
        *,
        render_status: str = RENDER_SUCCESS_STATUS,
        frame_count: int = 1,
        message: str = "",
        preflight_ready: bool = True,
        preflight_issues: tuple[str, ...] = (),
        trace_bytes: bytes | None = None,
    ) -> None:
        self.renderer_id = "fake"
        self.render_status = render_status
        self.frame_count = frame_count
        self.message = message
        self.preflight_ready = preflight_ready
        self.preflight_issues = preflight_issues
        self.trace_bytes = trace_bytes or json.dumps(
            {"imageTable": {"m_keys": [], "m_values": []}, "visualStages": [{"visualSprites": []}]}
        ).encode("utf-8")

    def preflight(self, *, timeout_seconds: int) -> RendererPreflightStatus:
        return RendererPreflightStatus(
            renderer_id=self.renderer_id,
            ready=self.preflight_ready,
            details={"timeout_seconds": timeout_seconds},
            issues=self.preflight_issues,
        )

    def render(self, request: RenderRequest) -> RenderOutcome:
        started_at = time.monotonic()
        request.output_dir.mkdir(parents=True, exist_ok=True)
        trace_path = request.output_dir / TRACE_FILENAME
        frames_dir = request.output_dir / FRAMES_DIRNAME

        if self.render_status != RENDER_SUCCESS_STATUS:
            return RenderOutcome(
                candidate_id=request.candidate.candidate_id,
                renderer_id=self.renderer_id,
                output_dir=request.output_dir,
                render_status=self.render_status,
                trace_path=None,
                frames_dir=frames_dir,
                frame_paths=(),
                elapsed_seconds=time.monotonic() - started_at,
                message=self.message or "Fake renderer configured to fail.",
            )

        trace_path.write_bytes(self.trace_bytes)
        frames_dir.mkdir(parents=True, exist_ok=True)
        frame_paths: list[Path] = []
        for index in range(self.frame_count):
            frame_path = frames_dir / f"frame_{index:03d}.png"
            frame_path.write_bytes(_MINIMAL_PNG)
            frame_paths.append(frame_path)

        return RenderOutcome(
            candidate_id=request.candidate.candidate_id,
            renderer_id=self.renderer_id,
            output_dir=request.output_dir,
            render_status=RENDER_SUCCESS_STATUS,
            trace_path=trace_path,
            frames_dir=frames_dir,
            frame_paths=tuple(frame_paths),
            elapsed_seconds=time.monotonic() - started_at,
            message=self.message,
            details={"mode": "fake"},
        )


class PlanimationRenderer(Renderer):
    def __init__(
        self,
        *,
        base_url: str | None = DEFAULT_BASE_URL,
        pddl_url: str | None = None,
        vfg_url: str | None = None,
        start_step: int = 0,
        stop_step: int = 3,
        quality: int = 1,
        post_pddl_for_vfg_fn: Any | None = None,
        post_vfg_for_visualisation_fn: Any | None = None,
        render_vfg_to_local_png_frames_fn: Any | None = None,
        extract_png_archive_fn: Any | None = None,
        preflight_host_fn: Any | None = None,
        max_render_attempts: int = 3,
    ) -> None:
        if stop_step <= start_step:
            raise ValueError("stop_step must be greater than start_step")
        if max_render_attempts <= 0:
            raise ValueError("max_render_attempts must be positive")
        defaults = _resolve_planimation_defaults() if any(
            value is None
            for value in (
                post_pddl_for_vfg_fn,
                post_vfg_for_visualisation_fn,
                render_vfg_to_local_png_frames_fn,
                preflight_host_fn,
            )
        ) else {}
        self.renderer_id = "planimation"
        self.start_step = start_step
        self.stop_step = stop_step
        self.quality = quality
        self._post_pddl_for_vfg = post_pddl_for_vfg_fn or defaults["post_pddl_for_vfg_fn"]
        self._post_vfg_for_visualisation = post_vfg_for_visualisation_fn or defaults["post_vfg_for_visualisation_fn"]
        self._render_vfg_to_local_png_frames = (
            render_vfg_to_local_png_frames_fn or defaults["render_vfg_to_local_png_frames_fn"]
        )
        self._extract_png_archive = extract_png_archive_fn or _extract_png_archive
        self._preflight_host = preflight_host_fn or defaults["preflight_host_fn"]
        self._pddl_candidates, self._vfg_candidates, self._root_url = _derive_endpoint_candidates(base_url, pddl_url, vfg_url)
        self.max_render_attempts = max_render_attempts

    def preflight(self, *, timeout_seconds: int) -> RendererPreflightStatus:
        host_status = self._preflight_host(self._root_url, timeout=timeout_seconds)
        issues: list[str] = []
        pillow_available = importlib_util.find_spec("PIL") is not None
        if not pillow_available:
            issues.append("Pillow unavailable for local PNG fallback")

        if not bool(host_status.get("reachable", False)):
            issues.append(f"Planimation host preflight failed for {self._root_url}")

        return RendererPreflightStatus(
            renderer_id=self.renderer_id,
            ready=bool(host_status.get("reachable", False)) and pillow_available,
            details={
                "host": dict(host_status),
                "pddl_candidates": list(self._pddl_candidates),
                "pillow_available": pillow_available,
                "root_url": self._root_url,
                "vfg_candidates": list(self._vfg_candidates),
            },
            issues=tuple(issues),
        )

    def render(self, request: RenderRequest) -> RenderOutcome:
        started_at = time.monotonic()
        request.output_dir.mkdir(parents=True, exist_ok=True)
        trace_path = request.output_dir / TRACE_FILENAME
        frames_dir = request.output_dir / FRAMES_DIRNAME
        errors: list[str] = []

        for _attempt in range(1, self.max_render_attempts + 1):
            used_pddl_url: str | None = None
            used_vfg_url: str | None = None
            used_local_renderer = False
            try:
                if trace_path.exists():
                    trace_path.unlink()
                if frames_dir.exists():
                    shutil.rmtree(frames_dir)

                vfg_bytes, used_pddl_url = self._post_pddl_for_vfg(
                    domain_path=request.candidate.domain_path,
                    problem_path=request.candidate.problem_path,
                    animation_profile_path=request.render_profile_path,
                    pddl_candidates=self._pddl_candidates,
                    timeout=request.timeout_seconds,
                )
                trace_path.write_bytes(vfg_bytes)

                try:
                    render_bytes, used_vfg_url = self._post_vfg_for_visualisation(
                        vfg_bytes=vfg_bytes,
                        output_format="png",
                        vfg_candidates=self._vfg_candidates,
                        start_step=self.start_step,
                        stop_step=self.stop_step,
                        quality=self.quality,
                        timeout=request.timeout_seconds,
                    )
                    self._extract_png_archive(render_bytes, frames_dir)
                except RuntimeError:
                    self._render_vfg_to_local_png_frames(
                        vfg_bytes=vfg_bytes,
                        output_dir=frames_dir,
                        start_step=self.start_step,
                        stop_step=self.stop_step,
                    )
                    used_local_renderer = True

                frame_paths = tuple(sorted(frames_dir.rglob("*.png")))
                if not frame_paths:
                    raise RuntimeError("Rendered output directory does not contain any PNG frames")

                return RenderOutcome(
                    candidate_id=request.candidate.candidate_id,
                    renderer_id=self.renderer_id,
                    output_dir=request.output_dir,
                    render_status=RENDER_SUCCESS_STATUS,
                    trace_path=trace_path,
                    frames_dir=frames_dir,
                    frame_paths=frame_paths,
                    used_pddl_url=used_pddl_url,
                    used_vfg_url=used_vfg_url,
                    used_local_renderer=used_local_renderer,
                    elapsed_seconds=time.monotonic() - started_at,
                )
            except Exception as error:  # noqa: BLE001
                errors.append(str(error))

        frame_paths = tuple(sorted(frames_dir.rglob("*.png"))) if frames_dir.exists() else ()
        return RenderOutcome(
            candidate_id=request.candidate.candidate_id,
            renderer_id=self.renderer_id,
            output_dir=request.output_dir,
            render_status=RENDER_FAILED_STATUS,
            trace_path=trace_path if trace_path.exists() else None,
            frames_dir=frames_dir,
            frame_paths=frame_paths,
            used_pddl_url=None,
            used_vfg_url=None,
            used_local_renderer=False,
            elapsed_seconds=time.monotonic() - started_at,
            message=" | ".join(errors),
        )


def persist_render_outcome(outcome: RenderOutcome, *, render_profile_path: Path) -> Path:
    result_path = outcome.output_dir / RESULT_FILENAME
    _write_json(result_path, outcome.to_dict(render_profile_path=render_profile_path, result_path=result_path))
    return result_path


def validate_render_contract(
    outcome: RenderOutcome,
    *,
    render_profile_path: Path,
    result_path: Path,
) -> RenderGateDecision:
    issues: list[str] = []
    if outcome.render_status != RENDER_SUCCESS_STATUS:
        issues.append(f"render_status must be {RENDER_SUCCESS_STATUS!r}, got {outcome.render_status!r}")
    if not render_profile_path.exists():
        issues.append(f"render profile is missing: {render_profile_path}")
    if outcome.trace_path is None or not outcome.trace_path.exists():
        issues.append("trace.vfg.json is missing")
    elif outcome.trace_path.stat().st_size <= 0:
        issues.append("trace.vfg.json must be non-empty")
    frame_paths = tuple(path for path in outcome.frame_paths if path.exists())
    if not frame_paths:
        issues.append("frames directory must contain at least one PNG")
    if not result_path.exists():
        issues.append(f"render result metadata missing: {result_path}")
    return RenderGateDecision(accepted=not issues, message="; ".join(issues), issues=tuple(issues))


def render_candidate(
    *,
    candidate: NormalizedCandidate,
    renderer: Renderer,
    render_profile_path: Path,
    timeout_seconds: int,
    output_dir: Path | None = None,
) -> tuple[RenderOutcome, Path]:
    render_output_dir = (output_dir or (candidate.output_dir / DEFAULT_RENDER_SUBDIR)).resolve()
    request = RenderRequest(
        candidate=candidate,
        render_profile_path=render_profile_path.resolve(),
        output_dir=render_output_dir,
        timeout_seconds=timeout_seconds,
    )
    outcome = renderer.render(request)
    result_path = persist_render_outcome(outcome, render_profile_path=request.render_profile_path)
    return outcome, result_path


def gate_rendered_candidate(
    *,
    candidate: NormalizedCandidate,
    split: str,
    bucket: str,
    index: int,
    attempt_index: int,
    renderer: Renderer,
    render_profile_path: Path,
    timeout_seconds: int,
    output_dir: Path | None = None,
    notes: str = "",
    extra: Mapping[str, Any] | None = None,
) -> AcceptedInstanceMetadata | RejectedCandidateMetadata:
    outcome, result_path = render_candidate(
        candidate=candidate,
        renderer=renderer,
        render_profile_path=render_profile_path,
        timeout_seconds=timeout_seconds,
        output_dir=output_dir,
    )
    decision = validate_render_contract(outcome, render_profile_path=render_profile_path, result_path=result_path)
    canonical_candidate_id = build_candidate_id(candidate.adapter_id, split, bucket, attempt_index)

    render_payload = outcome.to_dict(render_profile_path=render_profile_path, result_path=result_path)
    if not decision.accepted:
        return RejectedCandidateMetadata(
            candidate_id=canonical_candidate_id,
            domain_id=candidate.adapter_id,
            split=split,
            bucket=bucket,
            attempt_index=attempt_index,
            seed=candidate.seed,
            rejection_reason=RENDER_FAILED_REASON,
            rejection_stage=RENDER_REJECTION_STAGE,
            message=decision.message or outcome.message or "Rendering gate failed.",
            generator_command=candidate.generator_command,
            generator_cwd=str(candidate.generator_cwd),
            stdout_path=str(candidate.stdout_path),
            stderr_path=str(candidate.stderr_path),
            details={
                "issues": list(decision.issues),
                "render": render_payload,
            },
        )

    accepted_extra = dict(extra or {})
    accepted_extra["render"] = render_payload
    return AcceptedInstanceMetadata(
        instance_id=build_instance_id(candidate.adapter_id, split, bucket, index),
        candidate_id=canonical_candidate_id,
        domain_id=candidate.adapter_id,
        split=split,
        bucket=bucket,
        index=index,
        attempt_index=attempt_index,
        seed=candidate.seed,
        domain_path=str(candidate.domain_path),
        problem_path=str(candidate.problem_path),
        generator_command=candidate.generator_command,
        generator_cwd=str(candidate.generator_cwd),
        stdout_path=str(candidate.stdout_path),
        stderr_path=str(candidate.stderr_path),
        render_status=outcome.render_status,
        render_artifact_paths=tuple(
            str(path)
            for path in (
                [outcome.trace_path] if outcome.trace_path is not None else []
            )
            + list(outcome.frame_paths)
        ),
        render_result_path=str(result_path),
        difficulty_target=bucket,
        notes=notes,
        extra=accepted_extra,
    )


def inspect_rendering_preflight(
    curriculum_config: CurriculumConfig,
    *,
    renderer: Renderer | None = None,
    timeout_seconds: int | None = None,
) -> RenderingPreflightReport:
    domains = tuple(
        RenderDomainPreflight(
            domain_id=domain.domain_id,
            render_profile_path=str(domain.render_profile_path),
            render_profile_configured=domain.render_profile_path.exists(),
        )
        for domain in curriculum_config.domains
    )
    issues = [
        f"render profile missing for domain: {domain.domain_id}"
        for domain in domains
        if not domain.render_profile_configured
    ]
    render_profile_ready = not issues

    renderer_report: RendererPreflightStatus | None = None
    if renderer is not None:
        renderer_report = renderer.preflight(
            timeout_seconds=timeout_seconds or curriculum_config.timeouts.render_seconds
        )
        issues.extend(renderer_report.issues)

    renderer_ready = renderer_report.ready if renderer_report is not None else True
    ready = (not curriculum_config.require_rendering) or (render_profile_ready and renderer_ready)
    return RenderingPreflightReport(
        require_rendering=curriculum_config.require_rendering,
        ready=ready,
        render_profile_ready=render_profile_ready,
        selected_domain_ids=curriculum_config.selected_domain_ids,
        domains=domains,
        renderer=renderer_report,
        issues=tuple(issues),
    )


def require_rendering_preflight(
    curriculum_config: CurriculumConfig,
    *,
    renderer: Renderer | None = None,
    timeout_seconds: int | None = None,
) -> RenderingPreflightReport:
    report = inspect_rendering_preflight(
        curriculum_config,
        renderer=renderer,
        timeout_seconds=timeout_seconds,
    )
    if not report.ready:
        raise RuntimeError("Rendering preflight failed: " + "; ".join(report.issues or ("renderer not ready",)))
    return report


__all__ = [
    "DEFAULT_RENDER_SUBDIR",
    "FRAMES_DIRNAME",
    "FakeRenderer",
    "PlanimationRenderer",
    "RENDER_FAILED_REASON",
    "RENDER_FAILED_STATUS",
    "RENDER_REJECTION_STAGE",
    "RENDER_SUCCESS_STATUS",
    "RESULT_FILENAME",
    "RenderDomainPreflight",
    "RenderGateDecision",
    "RenderOutcome",
    "RenderRequest",
    "Renderer",
    "RendererPreflightStatus",
    "RenderingPreflightReport",
    "TRACE_FILENAME",
    "gate_rendered_candidate",
    "inspect_rendering_preflight",
    "persist_render_outcome",
    "render_candidate",
    "require_rendering_preflight",
    "validate_render_contract",
]
