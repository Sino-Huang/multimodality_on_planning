from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from scripts.phase3.cgas_planimation_evidence import (
    APPROVED_BACKEND_COMMIT,
    CLAIM_NAMES,
    SCHEMA_VERSION,
    build_certification,
    extract_vfg_action_sequence,
    main,
    parse_action_sequence,
    verify_attempt,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_attempt(tmp_path: Path) -> dict[str, Any]:
    vfg = {
        "visualStages": [
            {
                "stageName": "Initial Stage",
                "visualSprites": [{"name": "token", "minX": 0.2, "maxX": 0.6, "minY": 0.2, "maxY": 0.6}],
            },
            {"stageName": "(pickup b1)", "visualSprites": []},
        ]
    }
    trace_path = tmp_path / "trace.vfg.json"
    trace_path.write_text(json.dumps(vfg), encoding="utf-8")
    frame_path = tmp_path / "frame.png"
    image = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    for x in range(20, 60):
        for y in range(40, 80):
            image.putpixel((x, y), (32, 96, 160, 255))
    image.save(frame_path, format="PNG")
    receipt = {
        "status": "success",
        "reason": "validated_expected_object_coverage",
        "png_dimensions": [100, 100],
        "sprite_count": 1,
        "covered_sprite_count": 1,
        "minimum_object_coverage": 0.01,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "success",
        "backend": {
            "commit": APPROVED_BACKEND_COMMIT,
            "endpoint": "http://127.0.0.1:18321/upload/pddl",
        },
        "fixture": {"supplied_plan_text": "(pickup b1)"},
        "plan_submission": {
            "expected_plan_text": "(pickup b1)",
            "submitted_plan_text": "(pickup b1)",
        },
        "network": {
            "calls": [
                {
                    "url": "http://127.0.0.1:18321/upload/pddl",
                    "plan_present": True,
                    "plan_nonempty": True,
                    "plan_text": "(pickup b1)",
                }
            ],
            "hosted_requests": 0,
        },
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
            "frame_sha256": _sha256(frame_path),
            "vfg_path": trace_path.name,
            "vfg_sha256": _sha256(trace_path),
            "visualStages_count": 2,
            "semantic_receipt": receipt,
        },
        "hosted_requests": 0,
    }


def test_parse_action_sequence_normalizes_one_grounded_action() -> None:
    assert parse_action_sequence("  (PickUp   B1)  ") == ("(pickup b1)",)


@pytest.mark.parametrize(
    "plan_text",
    (
        "(MOVE A B C)\n\t(stack  B1 B2)",
        "(MOVE A B C)(stack B1 B2)",
    ),
)
def test_parse_action_sequence_preserves_multiple_action_order(plan_text: str) -> None:
    assert parse_action_sequence(plan_text) == (
        "(move a b c)",
        "(stack b1 b2)",
    )


@pytest.mark.parametrize(
    "plan_text",
    (
        "",
        "   ",
        "pickup b1",
        "(pickup b1) trailing",
        "prefix (pickup b1)",
        "(pickup (nested b1))",
        "()",
        "(pickup b1",
        "pickup b1)",
    ),
)
def test_parse_action_sequence_rejects_malformed_plans(plan_text: str) -> None:
    with pytest.raises(ValueError, match="action_sequence_malformed"):
        parse_action_sequence(plan_text)


def test_extract_vfg_action_sequence_excludes_initial_stage_and_preserves_order() -> None:
    vfg = {
        "visualStages": [
            {"stageName": "Initial Stage"},
            {"stageName": "(MOVE A B C)"},
            {"stageName": "(pickup B1)"},
        ]
    }
    assert extract_vfg_action_sequence(vfg) == ("(move a b c)", "(pickup b1)")


def test_build_certification_passes_all_required_claims(tmp_path: Path) -> None:
    result = build_certification(_valid_attempt(tmp_path), tmp_path)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["action_sequences"] == {
        "expected": ["(pickup b1)"],
        "submitted": ["(pickup b1)"],
        "vfg": ["(pickup b1)"],
    }
    assert result["claims"] == dict.fromkeys(CLAIM_NAMES, "pass")
    assert set(result["diagnostics"]) == set(CLAIM_NAMES)
    assert result["certified"] is True


def test_build_certification_rejects_inconsistent_recorded_submitted_plan(tmp_path: Path) -> None:
    report = _valid_attempt(tmp_path)
    report["network"]["calls"][0]["plan_text"] = "(stack b1 b2)"

    with pytest.raises(ValueError, match="submitted_plan_text_mismatch"):
        build_certification(report, tmp_path)


def test_build_certification_fails_plan_post_to_unapproved_loopback_endpoint(tmp_path: Path) -> None:
    report = _valid_attempt(tmp_path)
    report["network"]["calls"][0]["url"] = "http://127.0.0.1:18322/upload/pddl"

    result = build_certification(report, tmp_path)

    assert result["claims"]["loopback_plan_submission"] == "fail"
    assert result["claims"]["no_hosted_client_request"] == "pass"
    assert result["certified"] is False


@pytest.mark.parametrize(
    "vfg",
    (
        {},
        {"visualStages": []},
        {"visualStages": [{"stageName": "(pickup b1)"}]},
        {"visualStages": [{"stageName": "Initial Stage"}, {"stageName": "Initial Stage"}]},
        {"visualStages": [{"stageName": "Initial Stage"}, {}]},
        {"visualStages": [{"stageName": "Initial Stage"}, {"stageName": "(move (nested b1))"}]},
        {"visualStages": [{"stageName": "Initial Stage"}, {"stageName": "(move ?from b1)"}]},
    ),
)
def test_extract_vfg_action_sequence_rejects_malformed_stage_structure(vfg: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="vfg_"):
        extract_vfg_action_sequence(vfg)


def test_build_certification_fails_wrong_vfg_action_order(tmp_path: Path) -> None:
    report = _valid_attempt(tmp_path)
    report["fixture"]["supplied_plan_text"] = "(pickup b1)\n(stack b1 b2)"
    report["plan_submission"] = {
        "expected_plan_text": "(pickup b1)\n(stack b1 b2)",
        "submitted_plan_text": "(pickup b1)\n(stack b1 b2)",
    }
    report["network"]["calls"][0]["plan_text"] = "(pickup b1)\n(stack b1 b2)"
    trace_path = tmp_path / "trace.vfg.json"
    vfg = json.loads(trace_path.read_text(encoding="utf-8"))
    vfg["visualStages"][1]["stageName"] = "(stack b1 b2)"
    vfg["visualStages"].append({"stageName": "(pickup b1)", "visualSprites": []})
    trace_path.write_text(json.dumps(vfg), encoding="utf-8")
    report["render"]["vfg_sha256"] = _sha256(trace_path)
    report["render"]["visualStages_count"] = 3

    result = build_certification(report, tmp_path)

    assert result["claims"]["expected_action_sequence_match"] == "pass"
    assert result["claims"]["vfg_action_sequence_match"] == "fail"
    assert result["certified"] is False


@pytest.mark.parametrize("action_stages", ([], ["(pickup b1)", "(stack b1 b2)"]))
def test_build_certification_fails_missing_or_extra_vfg_action_stages(tmp_path: Path, action_stages: list[str]) -> None:
    report = _valid_attempt(tmp_path)
    trace_path = tmp_path / "trace.vfg.json"
    vfg = json.loads(trace_path.read_text(encoding="utf-8"))
    vfg["visualStages"] = [vfg["visualStages"][0], *({"stageName": action} for action in action_stages)]
    trace_path.write_text(json.dumps(vfg), encoding="utf-8")
    report["render"]["vfg_sha256"] = _sha256(trace_path)
    report["render"]["visualStages_count"] = len(vfg["visualStages"])

    result = build_certification(report, tmp_path)

    assert result["claims"]["vfg_action_sequence_match"] == "fail"
    assert result["certified"] is False


def test_build_certification_marks_unreached_hard_stop_claims_not_observed(tmp_path: Path) -> None:
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "hard_stop",
        "reason": "backend_server_startup_timeout",
        "hosted_requests": 0,
    }

    result = build_certification(report, tmp_path)

    assert result["claims"] == dict.fromkeys(CLAIM_NAMES, "not_observed")
    assert result["certified"] is False


def test_build_certification_keeps_observed_expected_sequence_after_hard_stop(tmp_path: Path) -> None:
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "hard_stop",
        "reason": "backend_server_startup_timeout",
        "fixture": {"supplied_plan_text": "(PICKUP B1)"},
        "hosted_requests": 0,
    }

    result = build_certification(report, tmp_path)

    assert result["action_sequences"]["expected"] == ["(pickup b1)"]
    assert result["claims"]["expected_action_sequence_match"] == "not_observed"


def test_verify_attempt_recomputes_and_validates_saved_certification(tmp_path: Path) -> None:
    report = _valid_attempt(tmp_path)
    report["render"]["frame_path"] = str((tmp_path / "frame.png").resolve())
    report["render"]["vfg_path"] = str((tmp_path / "trace.vfg.json").resolve())
    saved = build_certification(report, tmp_path)
    report.update(saved)
    (tmp_path / "proof-report.json").write_text(json.dumps(report), encoding="utf-8")

    assert verify_attempt(tmp_path) == saved


def test_cli_returns_zero_for_certified_attempt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _valid_attempt(tmp_path)
    saved = build_certification(report, tmp_path)
    report.update(saved)
    (tmp_path / "proof-report.json").write_text(json.dumps(report), encoding="utf-8")

    assert main(["verify", "--attempt-root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == json.dumps(saved, sort_keys=True, separators=(",", ":")) + "\n"


def test_cli_returns_one_for_failed_claim(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _valid_attempt(tmp_path)
    report["backend"]["commit"] = "0" * 40
    saved = build_certification(report, tmp_path)
    report.update(saved)
    (tmp_path / "proof-report.json").write_text(json.dumps(report), encoding="utf-8")

    assert main(["verify", "--attempt-root", str(tmp_path)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["claims"]["backend_commit_match"] == "fail"
    assert payload["certified"] is False


def test_cli_returns_one_for_not_observed_claims(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "hard_stop",
        "reason": "backend_server_startup_timeout",
        "hosted_requests": 0,
    }
    report.update(build_certification(report, tmp_path))
    (tmp_path / "proof-report.json").write_text(json.dumps(report), encoding="utf-8")

    assert main(["verify", "--attempt-root", str(tmp_path)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert set(payload["claims"].values()) == {"not_observed"}
    assert payload["certified"] is False


def test_cli_returns_two_for_malformed_or_tampered_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _valid_attempt(tmp_path)
    report.update(build_certification(report, tmp_path))
    report["certified"] = False
    (tmp_path / "proof-report.json").write_text(json.dumps(report), encoding="utf-8")

    assert main(["verify", "--attempt-root", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "error": "saved_certified_mismatch",
        "malformed": True,
    }


def test_cli_returns_two_when_required_certification_fields_are_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = _valid_attempt(tmp_path)
    (tmp_path / "proof-report.json").write_text(json.dumps(report), encoding="utf-8")

    assert main(["verify", "--attempt-root", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "error": "saved_action_sequences_missing",
        "malformed": True,
    }


def test_verify_attempt_rejects_artifact_paths_outside_attempt(tmp_path: Path) -> None:
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    report = _valid_attempt(attempt_root)
    report.update(build_certification(report, attempt_root))
    outside = tmp_path / "outside.vfg.json"
    outside.write_text((attempt_root / "trace.vfg.json").read_text(encoding="utf-8"), encoding="utf-8")
    report["render"]["vfg_path"] = str(outside)
    (attempt_root / "proof-report.json").write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="vfg_path_invalid"):
        verify_attempt(attempt_root)
