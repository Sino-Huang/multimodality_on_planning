from __future__ import annotations

import hashlib
import importlib.util
import json
import types
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from scripts.phase3.cgas_planimation_evidence import CLAIM_NAMES

HARNESS_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "evidence"
    / "cgas-phase3-pilot-rendering"
    / "local_planimation_adapter_integration.py"
)


def _load_harness() -> types.ModuleType:
    """Import the loopback harness from its non-package location under .claude.

    The harness has no import-time side effects (no server, no HTTP, no git), so
    loading it is safe for exercising its pure guards and constants.
    """
    spec = importlib.util.spec_from_file_location("local_planimation_adapter_integration", HARNESS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _certifiable_report(root: Path, harness: types.ModuleType) -> dict[str, object]:
    trace_path = root / "trace.vfg.json"
    trace_path.write_text(
        json.dumps(
            {
                "visualStages": [
                    {
                        "stageName": "Initial Stage",
                        "visualSprites": [{"name": "token", "minX": 0.2, "maxX": 0.6, "minY": 0.2, "maxY": 0.6}],
                    },
                    {"stageName": "(pickup b1)", "visualSprites": []},
                ]
            }
        ),
        encoding="utf-8",
    )
    frame_path = root / "frame.png"
    image = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    for x in range(20, 60):
        for y in range(40, 80):
            image.putpixel((x, y), (32, 96, 160, 255))
    image.save(frame_path, format="PNG")

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    return {
        "schema_version": harness.SCHEMA_VERSION,
        "backend": {
            "commit": harness.BACKEND_PIN,
            "endpoint": "http://127.0.0.1:18321/upload/pddl",
        },
        "fixture": {"supplied_plan_text": harness.PLAN_TEXT},
        "adapter": {
            "counts": {
                "requested": 1,
                "processed": 1,
                "succeeded": 1,
                "failed": 0,
                "duplicate": 0,
                "collision": 0,
                "remaining": 0,
            }
        },
        "render": {
            "status": "success",
            "frame_path": frame_path.name,
            "frame_sha256": digest(frame_path),
            "vfg_path": trace_path.name,
            "vfg_sha256": digest(trace_path),
            "visualStages_count": 2,
            "semantic_receipt": {
                "status": "success",
                "reason": "validated_expected_object_coverage",
                "png_dimensions": [100, 100],
                "sprite_count": 1,
                "covered_sprite_count": 1,
                "minimum_object_coverage": 0.01,
            },
        },
        "hosted_requests": 0,
    }


def _adapter_result(
    root: Path,
    report: dict[str, object],
    *,
    counts: dict[str, int] | None = None,
    png_sha256: str | None = None,
) -> types.SimpleNamespace:
    render = report["render"]
    assert isinstance(render, dict)
    manifest_path = root / "manifest.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "status": "success",
                "frame_path": str(root / "frame.png"),
                "trace_path": str(root / "trace.vfg.json"),
                "png_sha256": png_sha256 or render["frame_sha256"],
                "vfg_sha256": render["vfg_sha256"],
                "supplied_plan_sha256": "supplied-plan-digest",
                "renderer_config_sha256": "renderer-config-digest",
                "cache_key": "cache-key",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    diagnostics = root / "diagnostics"
    diagnostics.mkdir()
    (diagnostics / "run-contract.json").write_text(
        json.dumps(
            {
                "run_contract_sha256": "run-contract-digest",
                "request_sha256": "request-digest",
                "expansion_index_sha256": "expansion-index-digest",
                "domain_sha256": "domain-digest",
                "profile_sha256": "profile-digest",
                "adapter_implementation_sha256": "adapter-digest",
                "rendering_implementation_sha256": "rendering-digest",
                "renderer_implementation_sha256": "renderer-digest",
                "planimation_client_implementation_sha256": "client-digest",
                "render_config": {"base_url": "http://127.0.0.1:18321"},
            }
        ),
        encoding="utf-8",
    )
    return types.SimpleNamespace(
        manifest_path=manifest_path,
        report_path=root / "adapter-report.json",
        counts=counts
        or {
            "requested": 1,
            "processed": 1,
            "succeeded": 1,
            "failed": 0,
            "duplicate": 0,
            "collision": 0,
            "remaining": 0,
        },
    )


def _one_plan_call(harness: types.ModuleType) -> dict[str, object]:
    return {
        "url": "http://127.0.0.1:18321/upload/pddl",
        "plan_present": True,
        "plan_nonempty": True,
        "plan_text": harness.PLAN_TEXT,
    }


def _emit_adapter_report(
    root: Path,
    harness: types.ModuleType,
    report: dict[str, object],
    result: types.SimpleNamespace,
    calls: list[dict[str, object]],
) -> tuple[int, dict[str, Any]]:
    report["adapter"] = None
    report["render"] = None
    harness._capture_request_evidence(report, {"calls": calls})
    harness._capture_adapter_evidence(report, result, root, root)
    exit_code = harness._emit_certification_result(root, report)
    saved = json.loads((root / "proof-report.json").read_text(encoding="utf-8"))
    return exit_code, saved


def test_harness_refuses_non_loopback_urls() -> None:
    harness = _load_harness()
    for invalid_url in (
        "https://example.com/upload/pddl",
        "http://192.168.1.1/upload/pddl",
        "ftp://127.0.0.1/upload/pddl",
    ):
        with pytest.raises(harness.ProofError) as excinfo:
            harness._assert_loopback_url(invalid_url)
        assert excinfo.value.reason == "refusing_non_loopback_url"
    harness._assert_loopback_url("http://127.0.0.1:8000/upload/pddl")
    harness._assert_loopback_url("http://localhost:8000/upload/pddl")


def test_harness_fixture_is_synthetic_4_object_not_production_fixture() -> None:
    harness = _load_harness()
    assert harness.FIXTURE_OBJECT_COUNT == 4
    assert harness.FIXTURE_OBJECT_COUNT not in (8, 12)  # never the mapping-bound 8-obj / representative 12-obj
    assert harness.FIXTURE_RAW_RANK == 0
    assert harness.PLAN_ACTIONS == ["(pickup b1)"]


def test_harness_profile_materialization_changes_only_randocolor_sentinel() -> None:
    harness = _load_harness()
    profile = "(define (animation blocksworld)\n  (color RANDOMCOLOR)\n  (color RED)\n)"
    materialized = harness._materialize_profile_text(profile)
    assert "(color GREY)" in materialized
    assert "RANDOMCOLOR" not in materialized
    assert "(color RED)" in materialized  # unrelated text untouched
    assert harness._materialize_profile_text("no sentinel present") == "no sentinel present"
    assert harness._materialize_profile_text(materialized) == materialized  # idempotent


def test_harness_output_root_guard_fails_closed_before_any_server(tmp_path: Path) -> None:
    harness = _load_harness()
    existing = tmp_path / "exists"
    existing.mkdir()
    assert harness.main(["--output-root", str(existing)]) == 2


def test_harness_records_present_and_nonempty_multipart_plan_text() -> None:
    harness = _load_harness()

    assert harness._multipart_plan_observation({"plan": (None, " (pickup b1) ")}) == {
        "plan_present": True,
        "plan_nonempty": True,
        "plan_text": " (pickup b1) ",
    }
    assert harness._multipart_plan_observation({}) == {
        "plan_present": False,
        "plan_nonempty": False,
        "plan_text": None,
    }


def test_harness_hard_stop_report_contains_complete_certification(tmp_path: Path) -> None:
    harness = _load_harness()
    report = {"schema_version": harness.SCHEMA_VERSION}

    assert harness._emit_hard_stop(tmp_path, report, "backend_server_startup_timeout") == 1

    saved = json.loads((tmp_path / "proof-report.json").read_text(encoding="utf-8"))
    assert saved["action_sequences"] == {"expected": [], "submitted": [], "vfg": []}
    assert set(saved["claims"]) == set(CLAIM_NAMES)
    assert set(saved["claims"].values()) == {"not_observed"}
    assert set(saved["diagnostics"]) == set(CLAIM_NAMES)
    assert saved["certified"] is False


def test_harness_hard_stop_records_absent_multipart_plan_without_crashing(tmp_path: Path) -> None:
    harness = _load_harness()
    report = {
        "schema_version": harness.SCHEMA_VERSION,
        "fixture": {"supplied_plan_text": harness.PLAN_TEXT},
        "plan_submission": None,
        "hosted_requests": 0,
    }
    recorder = {
        "calls": [
            {
                "url": "http://127.0.0.1:18321/upload/pddl",
                "plan_present": False,
                "plan_nonempty": False,
                "plan_text": None,
            }
        ]
    }
    harness._capture_request_evidence(report, recorder)

    assert harness._emit_hard_stop(tmp_path, report, "supplied_plan_field_absent") == 1

    saved = json.loads((tmp_path / "proof-report.json").read_text(encoding="utf-8"))
    assert saved["network"]["calls"] == recorder["calls"]
    assert saved["action_sequences"]["expected"] == ["(pickup b1)"]
    assert saved["action_sequences"]["submitted"] == []
    assert saved["claims"]["loopback_plan_submission"] == "fail"
    assert saved["certified"] is False


def test_harness_success_report_records_plan_and_certifies(tmp_path: Path) -> None:
    harness = _load_harness()
    report = _certifiable_report(tmp_path, harness)
    recorder = {
        "calls": [
            {
                "url": "http://127.0.0.1:18321/upload/pddl",
                "plan_present": True,
                "plan_nonempty": True,
                "plan_text": harness.PLAN_TEXT,
            }
        ]
    }
    harness._capture_request_evidence(report, recorder)

    assert harness._emit_certification_result(tmp_path, report) == 0

    saved = json.loads((tmp_path / "proof-report.json").read_text(encoding="utf-8"))
    assert saved["plan_submission"] == {
        "expected_plan_text": harness.PLAN_TEXT,
        "submitted_plan_text": harness.PLAN_TEXT,
    }
    assert saved["network"]["calls"][0]["plan_nonempty"] is True
    assert set(saved["claims"].values()) == {"pass"}
    assert saved["certified"] is True


def test_harness_continues_safe_checks_after_render_counts_fail(tmp_path: Path) -> None:
    harness = _load_harness()
    report = _certifiable_report(tmp_path, harness)
    result = _adapter_result(
        tmp_path,
        report,
        counts={
            "requested": 1,
            "processed": 1,
            "succeeded": 0,
            "failed": 1,
            "duplicate": 0,
            "collision": 0,
            "remaining": 0,
        },
    )

    exit_code, saved = _emit_adapter_report(tmp_path, harness, report, result, [_one_plan_call(harness)])

    assert exit_code == 1
    assert saved["status"] == "hard_stop"
    assert saved["reason"] == "integration_certification_failed"
    assert saved["action_sequences"] == {
        "expected": ["(pickup b1)"],
        "submitted": ["(pickup b1)"],
        "vfg": ["(pickup b1)"],
    }
    assert saved["claims"]["render_counts_exact"] == "fail"
    assert {saved["claims"][name] for name in CLAIM_NAMES if name != "render_counts_exact"} == {"pass"}
    assert set(saved["diagnostics"]) == set(CLAIM_NAMES)
    assert saved["certified"] is False


def test_harness_continues_vfg_and_semantic_checks_after_artifact_digest_fails(tmp_path: Path) -> None:
    from scripts.phase3.cgas_planimation_evidence import verify_attempt

    harness = _load_harness()
    report = _certifiable_report(tmp_path, harness)
    result = _adapter_result(tmp_path, report, png_sha256="0" * 64)

    exit_code, saved = _emit_adapter_report(tmp_path, harness, report, result, [_one_plan_call(harness)])

    assert exit_code == 1
    assert saved["claims"]["render_artifacts_valid"] == "fail"
    assert saved["claims"]["vfg_action_sequence_match"] == "pass"
    assert saved["claims"]["semantic_validation_pass"] == "pass"
    assert saved["claims"]["render_counts_exact"] == "pass"
    assert set(saved["diagnostics"]) == set(CLAIM_NAMES)
    expected = {
        field: saved[field] for field in ("schema_version", "action_sequences", "claims", "diagnostics", "certified")
    }
    assert verify_attempt(tmp_path) == expected


def test_harness_preserves_complete_report_after_multiple_loopback_requests_fail_claim(tmp_path: Path) -> None:
    harness = _load_harness()
    report = _certifiable_report(tmp_path, harness)
    result = _adapter_result(tmp_path, report)
    call = _one_plan_call(harness)

    exit_code, saved = _emit_adapter_report(tmp_path, harness, report, result, [call, dict(call)])

    assert exit_code == 1
    assert saved["claims"]["loopback_plan_submission"] == "fail"
    assert {saved["claims"][name] for name in CLAIM_NAMES if name != "loopback_plan_submission"} == {"pass"}
    assert saved["action_sequences"] == {
        "expected": ["(pickup b1)"],
        "submitted": ["(pickup b1)"],
        "vfg": ["(pickup b1)"],
    }
    assert set(saved["diagnostics"]) == set(CLAIM_NAMES)


def test_harness_report_wording_preserves_isolation_and_parser_boundaries() -> None:
    source = HARNESS_PATH.read_text(encoding="utf-8")
    assert "no claim of network-level interception" in source
    assert "integrated client path" in source
    assert "does not directly observe a parser invocation" in source
    for removed_gate in (
        "adapter_counts_mismatch",
        "render_png_hash_mismatch",
        "render_vfg_hash_mismatch",
        "render_semantic_invalid",
        "unexpected_request_count",
        "supplied_plan_field_absent",
        "supplied_plan_field_empty",
        "unexpected_endpoint",
        "backend_log_plan_parse_evidence",
        "get_plan_actions",
    ):
        assert removed_gate not in source
