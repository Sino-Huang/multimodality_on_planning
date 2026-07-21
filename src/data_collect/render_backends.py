"""Concrete fake and Planimation renderer backends."""

from __future__ import annotations

import shutil
import time
import zipfile
from importlib import util as importlib_util
from urllib.parse import urlparse

from PIL import UnidentifiedImageError

from .render_archive import _extract_png_archive
from .render_types import (
    ArchiveExtractor,
    FRAMES_DIRNAME,
    HostPreflight,
    LocalFrameRenderer,
    PddlPoster,
    PlanimationDefaults,
    RENDER_FAILED_STATUS,
    RENDER_SUCCESS_STATUS,
    RenderOutcome,
    RenderRequest,
    Renderer,
    RendererPreflightStatus,
    TRACE_FILENAME,
    VfgPoster,
)

DEFAULT_BASE_URL = "https://planimation.planning.domains"


def _resolve_planimation_defaults() -> PlanimationDefaults:
    """Load optional Planimation integration functions only when needed."""
    try:
        from scripts.planimation_phase1 import (
            post_pddl_for_vfg,
            post_vfg_for_visualisation,
            preflight_host,
            render_vfg_to_local_png_frames,
        )
    except ModuleNotFoundError as error:  # pragma: no cover - runtime dependency
        missing_module = error.name or "unknown"
        raise RuntimeError(
            "Planimation renderer dependencies unavailable: "
            f"missing Python package '{missing_module}' required by scripts.planimation_phase1"
        ) from error
    return {
        "post_pddl_for_vfg_fn": post_pddl_for_vfg,
        "post_vfg_for_visualisation_fn": post_vfg_for_visualisation,
        "preflight_host_fn": preflight_host,
        "render_vfg_to_local_png_frames_fn": render_vfg_to_local_png_frames,
    }


def _derive_endpoint_candidates(
    base_url: str | None, pddl_url: str | None, vfg_url: str | None
) -> tuple[list[str], list[str], str]:
    """Derive legacy endpoint fallback candidates and their host root."""
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
        vfg_candidates = [f"{trimmed}/downloadVisualisation", f"{trimmed}/downloadVisualisation/"]
    root_source = base_url or pddl_candidates[0]
    parsed = urlparse(root_source)
    root_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else root_source
    return pddl_candidates, vfg_candidates, root_url


class PlanimationRenderer(Renderer):
    """Render Planimation VFG traces using hosted export with a local fallback."""

    def __init__(
        self,
        *,
        base_url: str | None = DEFAULT_BASE_URL,
        pddl_url: str | None = None,
        vfg_url: str | None = None,
        start_step: int = 0,
        stop_step: int = 3,
        quality: int = 1,
        post_pddl_for_vfg_fn: PddlPoster | None = None,
        post_vfg_for_visualisation_fn: VfgPoster | None = None,
        render_vfg_to_local_png_frames_fn: LocalFrameRenderer | None = None,
        extract_png_archive_fn: ArchiveExtractor | None = None,
        preflight_host_fn: HostPreflight | None = None,
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
        ) else None
        self.renderer_id = "planimation"
        self.start_step = start_step
        self.stop_step = stop_step
        self.quality = quality
        self.max_render_attempts = max_render_attempts
        self._post_pddl_for_vfg = post_pddl_for_vfg_fn or defaults["post_pddl_for_vfg_fn"]
        self._post_vfg_for_visualisation = (
            post_vfg_for_visualisation_fn or defaults["post_vfg_for_visualisation_fn"]
        )
        self._render_vfg_to_local_png_frames = (
            render_vfg_to_local_png_frames_fn or defaults["render_vfg_to_local_png_frames_fn"]
        )
        self._extract_png_archive = extract_png_archive_fn or _extract_png_archive
        self._preflight_host = preflight_host_fn or defaults["preflight_host_fn"]
        self._pddl_candidates, self._vfg_candidates, self._root_url = _derive_endpoint_candidates(
            base_url, pddl_url, vfg_url
        )

    def preflight(self, *, timeout_seconds: int) -> RendererPreflightStatus:
        host_status = self._preflight_host(self._root_url, timeout=timeout_seconds)
        pillow_available = importlib_util.find_spec("PIL") is not None
        issues: list[str] = []
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
                    used_local_renderer = False
                except RuntimeError:
                    self._render_vfg_to_local_png_frames(
                        vfg_bytes=vfg_bytes,
                        output_dir=frames_dir,
                        start_step=self.start_step,
                        stop_step=self.stop_step,
                    )
                    used_vfg_url = None
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
            except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, UnidentifiedImageError) as error:
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
            elapsed_seconds=time.monotonic() - started_at,
            message=" | ".join(errors),
        )
