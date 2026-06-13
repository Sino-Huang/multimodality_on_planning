from __future__ import annotations

import json
from pathlib import Path

from src.data_collect.adapters import NormalizedCandidate
from src.data_collect.config import load_curriculum_config
from src.data_collect.metadata import AcceptedInstanceMetadata, RejectedCandidateMetadata
from src.data_collect.rendering import (
    DEFAULT_RENDER_SUBDIR,
    FRAMES_DIRNAME,
    RESULT_FILENAME,
    TRACE_FILENAME,
    FakeRenderer,
    PlanimationRenderer,
    RENDER_FAILED_REASON,
    RENDER_SUCCESS_STATUS,
    gate_rendered_candidate,
    inspect_rendering_preflight,
    render_candidate,
)


def _build_candidate(tmp_path: Path, *, domain_id: str = "grid", candidate_id: str = "grid-train-easy-attempt-000000") -> NormalizedCandidate:
    output_dir = tmp_path / domain_id / "candidate-000000"
    output_dir.mkdir(parents=True, exist_ok=True)
    domain_path = output_dir / "domain.pddl"
    problem_path = output_dir / "problem.pddl"
    stdout_path = output_dir / "generator.stdout"
    stderr_path = output_dir / "generator.stderr"
    domain_path.write_text("(define (domain grid))\n", encoding="utf-8")
    problem_path.write_text("(define (problem p1) (:domain grid))\n", encoding="utf-8")
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    return NormalizedCandidate(
        candidate_id=candidate_id,
        adapter_id=domain_id,
        output_dir=output_dir,
        domain_path=domain_path,
        problem_path=problem_path,
        generator_command=("python", "generate.py"),
        generator_cwd=tmp_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        seed=123,
    )


def _write_render_profile(tmp_path: Path, *, domain_id: str = "grid") -> Path:
    render_profile_path = tmp_path / domain_id / "render_profile.pddl"
    render_profile_path.parent.mkdir(parents=True, exist_ok=True)
    render_profile_path.write_text("(define (animation-profile grid))\n", encoding="utf-8")
    return render_profile_path


def test_fake_renderer_success_required_for_acceptance(tmp_path: Path) -> None:
    candidate = _build_candidate(tmp_path)
    render_profile_path = _write_render_profile(tmp_path)

    metadata = gate_rendered_candidate(
        candidate=candidate,
        split="train",
        bucket="easy",
        index=0,
        attempt_index=0,
        renderer=FakeRenderer(frame_count=2),
        render_profile_path=render_profile_path,
        timeout_seconds=30,
    )

    assert isinstance(metadata, AcceptedInstanceMetadata)
    assert metadata.render_status == RENDER_SUCCESS_STATUS
    assert Path(metadata.render_result_path).exists()
    assert Path(metadata.render_result_path).name == RESULT_FILENAME
    assert any(path.endswith(TRACE_FILENAME) for path in metadata.render_artifact_paths)
    assert any(f"{FRAMES_DIRNAME}/frame_000.png" in path for path in metadata.render_artifact_paths)
    payload = json.loads(Path(metadata.render_result_path).read_text(encoding="utf-8"))
    assert payload["render_status"] == RENDER_SUCCESS_STATUS
    assert payload["frame_count"] == 2


def test_render_failure_rejects_candidate(tmp_path: Path) -> None:
    candidate = _build_candidate(tmp_path)
    render_profile_path = _write_render_profile(tmp_path)

    metadata = gate_rendered_candidate(
        candidate=candidate,
        split="train",
        bucket="easy",
        index=0,
        attempt_index=0,
        renderer=FakeRenderer(render_status="failed", message="network down"),
        render_profile_path=render_profile_path,
        timeout_seconds=30,
    )

    assert isinstance(metadata, RejectedCandidateMetadata)
    assert metadata.rejection_reason == RENDER_FAILED_REASON
    assert metadata.rejection_stage == "render"
    assert "render_status must be 'success'" in metadata.message
    render_result_path = Path(str(metadata.details["render"]["result_path"]))
    assert render_result_path.exists()


def test_render_preflight_reports_all_curriculum_domains_configured() -> None:
    curriculum_config = load_curriculum_config()

    report = inspect_rendering_preflight(curriculum_config, renderer=FakeRenderer())

    assert report.ready is True
    assert report.render_profile_ready is True
    assert len(report.selected_domain_ids) == 15
    assert len(report.domains) == 15
    assert all(domain.render_profile_configured for domain in report.domains)


def test_planimation_renderer_writes_trace_frames_and_result_with_local_fallback(tmp_path: Path) -> None:
    candidate = _build_candidate(tmp_path)
    render_profile_path = _write_render_profile(tmp_path)
    trace_bytes = json.dumps(
        {"imageTable": {"m_keys": [], "m_values": []}, "visualStages": [{"visualSprites": []}]}
    ).encode("utf-8")

    def fake_post_pddl_for_vfg(**_: object) -> tuple[bytes, str]:
        return trace_bytes, "https://planimation.planning.domains/upload/pddl"

    def fake_post_vfg_for_visualisation(**_: object) -> tuple[bytes, str]:
        raise RuntimeError("hosted raster export unavailable")

    def fake_local_render(*, vfg_bytes: bytes, output_dir: Path, start_step: int, stop_step: int) -> int:
        assert vfg_bytes == trace_bytes
        assert start_step == 0
        assert stop_step == 3
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "frame_000.png").write_bytes(b"png")
        return 1

    renderer = PlanimationRenderer(
        post_pddl_for_vfg_fn=fake_post_pddl_for_vfg,
        post_vfg_for_visualisation_fn=fake_post_vfg_for_visualisation,
        render_vfg_to_local_png_frames_fn=fake_local_render,
        preflight_host_fn=lambda root_url, timeout: {"root_url": root_url, "reachable": True, "timeout": timeout},
    )

    outcome, result_path = render_candidate(
        candidate=candidate,
        renderer=renderer,
        render_profile_path=render_profile_path,
        timeout_seconds=30,
    )

    assert outcome.render_status == RENDER_SUCCESS_STATUS
    assert outcome.trace_path == candidate.output_dir / DEFAULT_RENDER_SUBDIR / TRACE_FILENAME
    assert outcome.trace_path.read_bytes() == trace_bytes
    assert outcome.used_local_renderer is True
    assert outcome.frame_paths == (candidate.output_dir / DEFAULT_RENDER_SUBDIR / FRAMES_DIRNAME / "frame_000.png",)
    assert result_path == candidate.output_dir / DEFAULT_RENDER_SUBDIR / RESULT_FILENAME
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["used_local_renderer"] is True
    assert payload["used_pddl_url"] == "https://planimation.planning.domains/upload/pddl"


def test_planimation_renderer_retries_transient_pddl_upload_failure(tmp_path: Path) -> None:
    candidate = _build_candidate(tmp_path)
    render_profile_path = _write_render_profile(tmp_path)
    trace_bytes = json.dumps(
        {"imageTable": {"m_keys": [], "m_values": []}, "visualStages": [{"visualSprites": []}]}
    ).encode("utf-8")
    attempts = {"count": 0}

    def flaky_post_pddl_for_vfg(**_: object) -> tuple[bytes, str]:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("Unexpected status from the server")
        return trace_bytes, "https://planimation.planning.domains/upload/pddl"

    def fake_post_vfg_for_visualisation(**_: object) -> tuple[bytes, str]:
        raise RuntimeError("hosted raster export unavailable")

    def fake_local_render(*, vfg_bytes: bytes, output_dir: Path, start_step: int, stop_step: int) -> int:
        assert vfg_bytes == trace_bytes
        assert start_step == 0
        assert stop_step == 3
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "frame_000.png").write_bytes(b"png")
        return 1

    renderer = PlanimationRenderer(
        post_pddl_for_vfg_fn=flaky_post_pddl_for_vfg,
        post_vfg_for_visualisation_fn=fake_post_vfg_for_visualisation,
        render_vfg_to_local_png_frames_fn=fake_local_render,
        preflight_host_fn=lambda root_url, timeout: {"root_url": root_url, "reachable": True, "timeout": timeout},
    )

    outcome, result_path = render_candidate(
        candidate=candidate,
        renderer=renderer,
        render_profile_path=render_profile_path,
        timeout_seconds=30,
    )

    assert attempts["count"] == 2
    assert outcome.render_status == RENDER_SUCCESS_STATUS
    assert outcome.trace_path == candidate.output_dir / DEFAULT_RENDER_SUBDIR / TRACE_FILENAME
    assert outcome.trace_path.read_bytes() == trace_bytes
    assert result_path.exists()
