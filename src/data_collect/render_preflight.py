"""Rendering configuration and backend readiness checks."""

from __future__ import annotations

from .config import CurriculumConfig
from .render_types import (
    RenderDomainPreflight,
    Renderer,
    RendererPreflightStatus,
    RenderingPreflightReport,
)


def inspect_rendering_preflight(
    curriculum_config: CurriculumConfig,
    *,
    renderer: Renderer | None = None,
    timeout_seconds: int | None = None,
) -> RenderingPreflightReport:
    """Report profile configuration and optional renderer readiness."""
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
    renderer_report: RendererPreflightStatus | None = None
    if renderer is not None:
        renderer_report = renderer.preflight(
            timeout_seconds=timeout_seconds or curriculum_config.timeouts.render_seconds
        )
        issues.extend(renderer_report.issues)
    render_profile_ready = not any(not domain.render_profile_configured for domain in domains)
    renderer_ready = renderer_report.ready if renderer_report is not None else True
    return RenderingPreflightReport(
        require_rendering=curriculum_config.require_rendering,
        ready=not curriculum_config.require_rendering or (render_profile_ready and renderer_ready),
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
    """Return the readiness report or stop a rendering-required workflow."""
    report = inspect_rendering_preflight(
        curriculum_config,
        renderer=renderer,
        timeout_seconds=timeout_seconds,
    )
    if not report.ready:
        raise RuntimeError("Rendering preflight failed: " + "; ".join(report.issues or ("renderer not ready",)))
    return report
