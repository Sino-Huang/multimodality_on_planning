from __future__ import annotations

import hashlib
import json
import math
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


def _production_smoke_attempt(tmp_path: Path) -> dict[str, Any]:
    report = _valid_attempt(tmp_path)
    report["inputs"] = {"fixture_selector": "8-object"}
    report["backend"]["startup_timeout_seconds"] = 180
    report["provenance"] = {
        "render_config": {
            "timeout_seconds": 90,
            "request_delay_seconds": 0,
            "max_attempts": 1,
        }
    }
    fixture = report["fixture"]
    assert isinstance(fixture, dict)
    fixture.update(
        {
            "fixture_id": "8-object",
            "object_count": 8,
            "schema_version": "cgas_phase3_planimation_smoke_fixture_v1",
            "expected_actions": ["(pickup b1)"],
            "semantic_expectations": {
                "minimum_covered_object_count": 8,
                "expected_action_count": 1,
                "expected_visual_stage_count": 2,
            },
            "resource_expectations": {
                "adapter_request_timeout_seconds": 90,
                "backend_startup_timeout_seconds": 180,
                "max_attempts": 1,
                "request_delay_seconds": 0,
            },
        }
    )
    return report


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


def test_build_certification_preserves_legacy_four_object_selector(tmp_path: Path) -> None:
    report = _valid_attempt(tmp_path)
    report["inputs"] = {"fixture_selector": "4-object"}

    assert build_certification(report, tmp_path)["certified"] is True


@pytest.mark.parametrize("selector", ("8-object", "12-object"))
def test_build_certification_passes_checked_in_production_smoke_fixtures(tmp_path: Path, selector: str) -> None:
    fixture_path = Path(__file__).resolve().parents[2] / f"configs/cgas/planimation_smoke/{selector}.json"
    checked_fixture: dict[str, Any] = json.loads(fixture_path.read_text(encoding="utf-8"))
    object_count = checked_fixture["problem_identity"]["object_count"]
    supplied_plan = checked_fixture["supplied_plan"]
    expected_actions = checked_fixture["expected_actions"]
    resource_expectations = checked_fixture["resource_expectations"]
    semantic_expectations = checked_fixture["semantic_expectations"]
    assert object_count in (8, 12)
    assert expected_actions
    report = _valid_attempt(tmp_path)

    sprites: list[dict[str, object]] = []
    image = Image.new("RGBA", (400, 300), (255, 255, 255, 255))
    for index in range(object_count):
        column, row = index % 4, index // 4
        min_x = 0.05 + column * 0.24
        max_x = min_x + 0.14
        min_y = 0.05 + row * 0.28
        max_y = min_y + 0.16
        sprites.append(
            {"name": f"b{index + 1}", "minX": min_x, "maxX": max_x, "minY": min_y, "maxY": max_y}
        )
        for x in range(math.floor(min_x * image.width), math.ceil(max_x * image.width)):
            for y in range(
                math.floor((1.0 - max_y) * image.height),
                math.ceil((1.0 - min_y) * image.height),
            ):
                image.putpixel((x, y), (32, 96, 160, 255))

    trace_path = tmp_path / "trace.vfg.json"
    trace_path.write_text(
        json.dumps(
            {
                "visualStages": [
                    {"stageName": "Initial Stage", "visualSprites": sprites},
                    *({"stageName": action, "visualSprites": []} for action in expected_actions),
                ]
            }
        ),
        encoding="utf-8",
    )
    frame_path = tmp_path / "frame.png"
    image.save(frame_path, format="PNG")

    report["fixture"] = {
        "fixture_id": checked_fixture["fixture_id"],
        "object_count": object_count,
        "schema_version": checked_fixture["schema_version"],
        "supplied_plan_text": supplied_plan,
        "expected_actions": expected_actions,
        "semantic_expectations": semantic_expectations,
        "resource_expectations": resource_expectations,
    }
    report["inputs"] = {"fixture_selector": selector}
    report["backend"]["startup_timeout_seconds"] = resource_expectations["backend_startup_timeout_seconds"]
    report["provenance"] = {
        "render_config": {
            "timeout_seconds": resource_expectations["adapter_request_timeout_seconds"],
            "request_delay_seconds": resource_expectations["request_delay_seconds"],
            "max_attempts": resource_expectations["max_attempts"],
        }
    }
    report["plan_submission"] = {
        "expected_plan_text": supplied_plan,
        "submitted_plan_text": supplied_plan,
    }
    report["network"]["calls"][0]["plan_text"] = supplied_plan
    report["render"] = {
        "status": "success",
        "frame_path": frame_path.name,
        "frame_sha256": _sha256(frame_path),
        "vfg_path": trace_path.name,
        "vfg_sha256": _sha256(trace_path),
        "visualStages_count": len(expected_actions) + 1,
        "semantic_receipt": {
            "status": "success",
            "reason": "validated_expected_object_coverage",
            "png_dimensions": [400, 300],
            "sprite_count": object_count,
            "covered_sprite_count": object_count,
            "minimum_object_coverage": 0.01,
        },
    }

    result = build_certification(report, tmp_path)

    assert result["action_sequences"] == {
        "expected": expected_actions,
        "submitted": expected_actions,
        "vfg": expected_actions,
    }
    assert result["claims"] == dict.fromkeys(CLAIM_NAMES, "pass")
    assert result["certified"] is True


@pytest.mark.parametrize(
    ("field", "replacement", "reason"),
    (
        ("schema_version", None, "smoke_fixture_schema_version_invalid"),
        ("schema_version", "wrong", "smoke_fixture_schema_version_invalid"),
        ("expected_actions", None, "fixture_expected_actions_invalid"),
        ("semantic_expectations", None, "fixture_semantic_expectations_invalid"),
    ),
)
def test_build_certification_requires_production_smoke_fixture_contract(
    tmp_path: Path,
    field: str,
    replacement: object,
    reason: str,
) -> None:
    report = _production_smoke_attempt(tmp_path)
    fixture = report["fixture"]
    assert isinstance(fixture, dict)
    if replacement is None:
        fixture.pop(field)
    else:
        fixture[field] = replacement

    with pytest.raises(ValueError, match=reason):
        build_certification(report, tmp_path)


@pytest.mark.parametrize("mutation", ("strip_discriminator", "mismatched_selector"))
def test_build_certification_rejects_smoke_fixture_selector_count_mismatch(
    tmp_path: Path,
    mutation: str,
) -> None:
    report = _production_smoke_attempt(tmp_path)
    fixture = report["fixture"]
    assert isinstance(fixture, dict)
    if mutation == "strip_discriminator":
        for field in ("fixture_id", "schema_version", "expected_actions", "semantic_expectations"):
            fixture.pop(field)
    else:
        fixture["fixture_id"] = "12-object"

    with pytest.raises(ValueError, match="smoke_fixture_selector_count_mismatch"):
        build_certification(report, tmp_path)


def test_build_certification_uses_authoritative_smoke_selector_for_fixture_metadata(tmp_path: Path) -> None:
    report = _production_smoke_attempt(tmp_path)
    fixture = report["fixture"]
    assert isinstance(fixture, dict)
    fixture.pop("fixture_id")
    fixture.pop("object_count")

    with pytest.raises(ValueError, match="smoke_fixture_selector_count_mismatch"):
        build_certification(report, tmp_path)


def test_build_certification_binds_smoke_backend_timeout_to_execution_evidence(tmp_path: Path) -> None:
    report = _production_smoke_attempt(tmp_path)
    report["backend"]["startup_timeout_seconds"] = 1

    with pytest.raises(ValueError, match="fixture_resource_execution_mismatch"):
        build_certification(report, tmp_path)


def test_build_certification_binds_smoke_adapter_resources_to_execution_evidence(tmp_path: Path) -> None:
    report = _production_smoke_attempt(tmp_path)
    report["provenance"]["render_config"]["max_attempts"] = 2

    with pytest.raises(ValueError, match="fixture_resource_execution_mismatch"):
        build_certification(report, tmp_path)


def test_build_certification_rejects_weakened_production_smoke_coverage_expectation(tmp_path: Path) -> None:
    report = _production_smoke_attempt(tmp_path)
    fixture = report["fixture"]
    assert isinstance(fixture, dict)
    fixture["semantic_expectations"]["minimum_covered_object_count"] = 1

    with pytest.raises(ValueError, match="fixture_semantic_expectations_invalid"):
        build_certification(report, tmp_path)


def test_build_certification_requires_production_smoke_resource_expectations(tmp_path: Path) -> None:
    report = _production_smoke_attempt(tmp_path)
    fixture = report["fixture"]
    assert isinstance(fixture, dict)
    fixture.pop("resource_expectations")

    with pytest.raises(ValueError, match="fixture_resource_expectations_invalid"):
        build_certification(report, tmp_path)


def test_build_certification_fails_fixture_semantic_expectations(tmp_path: Path) -> None:
    report = _valid_attempt(tmp_path)
    report["fixture"]["semantic_expectations"] = {
        "minimum_covered_object_count": 2,
        "expected_action_count": 1,
        "expected_visual_stage_count": 2,
    }

    result = build_certification(report, tmp_path)

    assert result["claims"]["semantic_validation_pass"] == "fail"
    assert result["certified"] is False


def test_build_certification_rejects_tampered_fixture_expected_actions(tmp_path: Path) -> None:
    report = _valid_attempt(tmp_path)
    report["fixture"]["expected_actions"] = ["(stack b1 b2)"]

    with pytest.raises(ValueError, match="fixture_expected_actions_mismatch"):
        build_certification(report, tmp_path)


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
