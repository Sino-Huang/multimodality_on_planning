"""Compatibility facade for curriculum rendering contracts and backends."""

from .render_backends import PlanimationRenderer
from .render_fake import FakeRenderer
from .render_gates import (
    gate_rendered_candidate,
    persist_render_outcome,
    render_candidate,
    validate_render_contract,
)
from .render_preflight import inspect_rendering_preflight, require_rendering_preflight
from .render_types import (
    DEFAULT_RENDER_SUBDIR,
    FRAMES_DIRNAME,
    RESULT_FILENAME,
    TRACE_FILENAME,
    RENDER_FAILED_REASON,
    RENDER_FAILED_STATUS,
    RENDER_REJECTION_STAGE,
    RENDER_SUCCESS_STATUS,
    RenderDomainPreflight,
    RenderGateDecision,
    RenderOutcome,
    RenderRequest,
    Renderer,
    RendererPreflightStatus,
    RenderingPreflightReport,
)
from .render_archive import _extract_png_archive

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
    "_extract_png_archive",
    "gate_rendered_candidate",
    "inspect_rendering_preflight",
    "persist_render_outcome",
    "render_candidate",
    "require_rendering_preflight",
    "validate_render_contract",
]
