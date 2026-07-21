"""Rendering outcome persistence and metadata gate logic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .adapters import NormalizedCandidate
from .metadata import AcceptedInstanceMetadata, RejectedCandidateMetadata, build_candidate_id, build_instance_id
from .render_types import (
    DEFAULT_RENDER_SUBDIR,
    RENDER_FAILED_REASON,
    RENDER_REJECTION_STAGE,
    RENDER_SUCCESS_STATUS,
    RESULT_FILENAME,
    JsonValue,
    RenderGateDecision,
    RenderOutcome,
    RenderRequest,
    Renderer,
)


def _write_json(path: Path, payload: Mapping[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def persist_render_outcome(outcome: RenderOutcome, *, render_profile_path: Path) -> Path:
    """Persist an outcome before its acceptance decision is made."""
    result_path = outcome.output_dir / RESULT_FILENAME
    _write_json(result_path, outcome.to_dict(render_profile_path=render_profile_path, result_path=result_path))
    return result_path


def validate_render_contract(
    outcome: RenderOutcome, *, render_profile_path: Path, result_path: Path
) -> RenderGateDecision:
    """Check the artifacts required for a render to be accepted."""
    issues: list[str] = []
    if outcome.render_status != RENDER_SUCCESS_STATUS:
        issues.append(f"render_status must be {RENDER_SUCCESS_STATUS!r}, got {outcome.render_status!r}")
    if not render_profile_path.exists():
        issues.append(f"render profile is missing: {render_profile_path}")
    if outcome.trace_path is None or not outcome.trace_path.exists():
        issues.append("trace.vfg.json is missing")
    elif outcome.trace_path.stat().st_size <= 0:
        issues.append("trace.vfg.json must be non-empty")
    if not tuple(path for path in outcome.frame_paths if path.exists()):
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
    """Render one candidate and write its result metadata."""
    render_output_dir = (output_dir or candidate.output_dir / DEFAULT_RENDER_SUBDIR).resolve()
    request = RenderRequest(
        candidate=candidate,
        render_profile_path=render_profile_path.resolve(),
        output_dir=render_output_dir,
        timeout_seconds=timeout_seconds,
    )
    outcome = renderer.render(request)
    return outcome, persist_render_outcome(outcome, render_profile_path=request.render_profile_path)


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
    extra: Mapping[str, JsonValue] | None = None,
) -> AcceptedInstanceMetadata | RejectedCandidateMetadata:
    """Render a candidate and construct accepted or rejected metadata."""
    outcome, result_path = render_candidate(
        candidate=candidate,
        renderer=renderer,
        render_profile_path=render_profile_path,
        timeout_seconds=timeout_seconds,
        output_dir=output_dir,
    )
    decision = validate_render_contract(outcome, render_profile_path=render_profile_path, result_path=result_path)
    candidate_id = build_candidate_id(candidate.adapter_id, split, bucket, attempt_index)
    render_payload = outcome.to_dict(render_profile_path=render_profile_path, result_path=result_path)
    if not decision.accepted:
        return RejectedCandidateMetadata(
            candidate_id=candidate_id,
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
            details={"issues": list(decision.issues), "render": render_payload},
        )
    accepted_extra = dict(extra or {})
    accepted_extra["render"] = render_payload
    return AcceptedInstanceMetadata(
        instance_id=build_instance_id(candidate.adapter_id, split, bucket, index),
        candidate_id=candidate_id,
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
            for path in ([outcome.trace_path] if outcome.trace_path is not None else []) + list(outcome.frame_paths)
        ),
        render_result_path=str(result_path),
        difficulty_target=bucket,
        notes=notes,
        extra=accepted_extra,
    )
