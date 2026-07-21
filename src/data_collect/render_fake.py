"""Deterministic renderer used by local collection workflows and tests."""

from __future__ import annotations

import json
import time
from base64 import b64decode

from .render_types import (
    FRAMES_DIRNAME,
    RENDER_SUCCESS_STATUS,
    TRACE_FILENAME,
    RenderOutcome,
    RenderRequest,
    Renderer,
    RendererPreflightStatus,
)

_MINIMAL_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg=="
)


class FakeRenderer(Renderer):
    """Write deterministic render artifacts for local workflow tests."""

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
                frames_dir=frames_dir,
                elapsed_seconds=time.monotonic() - started_at,
                message=self.message or "Fake renderer configured to fail.",
            )
        trace_path.write_bytes(self.trace_bytes)
        frames_dir.mkdir(parents=True, exist_ok=True)
        frame_paths = tuple(frames_dir / f"frame_{index:03d}.png" for index in range(self.frame_count))
        for frame_path in frame_paths:
            frame_path.write_bytes(_MINIMAL_PNG)
        return RenderOutcome(
            candidate_id=request.candidate.candidate_id,
            renderer_id=self.renderer_id,
            output_dir=request.output_dir,
            render_status=RENDER_SUCCESS_STATUS,
            trace_path=trace_path,
            frames_dir=frames_dir,
            frame_paths=frame_paths,
            elapsed_seconds=time.monotonic() - started_at,
            message=self.message,
            details={"mode": "fake"},
        )
