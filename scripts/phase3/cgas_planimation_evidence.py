from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .pddl import normalize_action_string
from .render_semantics import validate_render_artifacts

APPROVED_BACKEND_COMMIT = "94d82afb5ee122ce579dd11ca1953b7c85ca5824"
SCHEMA_VERSION = "cgas_phase3_planimation_integration_certification_v1"
SMOKE_FIXTURE_SCHEMA_VERSION = "cgas_phase3_planimation_smoke_fixture_v1"
SMOKE_FIXTURE_OBJECT_COUNTS = {
    "8-object": 8,
    "12-object": 12,
}
CLAIM_NAMES = (
    "expected_action_sequence_match",
    "loopback_plan_submission",
    "backend_commit_match",
    "vfg_action_sequence_match",
    "render_artifacts_valid",
    "semantic_validation_pass",
    "render_counts_exact",
    "no_hosted_client_request",
)
CLAIM_STATUSES = frozenset({"pass", "fail", "not_observed"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
EXPECTED_RENDER_COUNTS = {
    "requested": 1,
    "processed": 1,
    "succeeded": 1,
    "failed": 0,
    "duplicate": 0,
    "collision": 0,
    "remaining": 0,
}

_ACTION = re.compile(r"\([^()]+\)", re.DOTALL)


class EvidenceMalformedError(ValueError):
    pass


def parse_action_sequence(plan_text: str) -> tuple[str, ...]:
    if not isinstance(plan_text, str):
        raise EvidenceMalformedError("action_sequence_malformed")
    actions: list[str] = []
    position = 0
    try:
        for match in _ACTION.finditer(plan_text):
            separator = plan_text[position : match.start()]
            if separator.strip():
                raise EvidenceMalformedError("action_sequence_malformed")
            actions.append(normalize_action_string(match.group()))
            position = match.end()
    except ValueError as exc:
        raise EvidenceMalformedError("action_sequence_malformed") from exc
    if not actions or plan_text[position:].strip():
        raise EvidenceMalformedError("action_sequence_malformed")
    return tuple(actions)


def extract_vfg_action_sequence(vfg: Mapping[str, Any]) -> tuple[str, ...]:
    stages = vfg.get("visualStages")
    if not isinstance(stages, list) or not stages:
        raise EvidenceMalformedError("vfg_visual_stages_malformed")
    if not isinstance(stages[0], Mapping) or stages[0].get("stageName") != "Initial Stage":
        raise EvidenceMalformedError("vfg_initial_stage_malformed")
    actions: list[str] = []
    for stage in stages[1:]:
        if not isinstance(stage, Mapping) or not isinstance(stage.get("stageName"), str):
            raise EvidenceMalformedError("vfg_action_stage_malformed")
        if stage["stageName"] == "Initial Stage":
            raise EvidenceMalformedError("vfg_initial_stage_malformed")
        try:
            action = parse_action_sequence(stage["stageName"])
        except EvidenceMalformedError as exc:
            raise EvidenceMalformedError("vfg_action_stage_malformed") from exc
        if len(action) != 1 or any(part.startswith("?") for part in action[0][1:-1].split()):
            raise EvidenceMalformedError("vfg_action_stage_malformed")
        actions.extend(action)
    return tuple(actions)


def build_certification(report: Mapping[str, Any], attempt_root: Path) -> dict[str, Any]:
    if report.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceMalformedError("report_schema_version_invalid")
    attempt_root = attempt_root.resolve()
    completed = report.get("status") == "success"
    claims = dict.fromkeys(CLAIM_NAMES, "not_observed")
    diagnostics = dict.fromkeys(CLAIM_NAMES, "evidence not observed before hard stop")
    action_sequences: dict[str, list[str]] = {"expected": [], "submitted": [], "vfg": []}

    fixture_selector = _fixture_selector(report)
    production_smoke = fixture_selector in SMOKE_FIXTURE_OBJECT_COUNTS
    fixture = _optional_mapping(report.get("fixture"), "fixture", completed)
    expected: tuple[str, ...] = ()
    submitted: tuple[str, ...] = ()
    semantic_expectations: Mapping[str, Any] | None = None
    resource_expectations: Mapping[str, Any] | None = None
    if fixture is not None:
        fixture_id = fixture.get("fixture_id")
        object_count = fixture.get("object_count")
        if production_smoke:
            assert fixture_selector is not None
            if (
                fixture_id != fixture_selector
                or object_count != SMOKE_FIXTURE_OBJECT_COUNTS[fixture_selector]
            ):
                raise EvidenceMalformedError("smoke_fixture_selector_count_mismatch")
            if fixture.get("schema_version") != SMOKE_FIXTURE_SCHEMA_VERSION:
                raise EvidenceMalformedError("smoke_fixture_schema_version_invalid")
        expected_text = fixture.get("supplied_plan_text")
        if not isinstance(expected_text, str):
            raise EvidenceMalformedError("expected_plan_text_missing")
        expected = parse_action_sequence(expected_text)
        action_sequences["expected"] = list(expected)
        raw_expected_actions = fixture.get("expected_actions")
        if raw_expected_actions is None:
            if production_smoke:
                raise EvidenceMalformedError("fixture_expected_actions_invalid")
        else:
            if not isinstance(raw_expected_actions, list) or not raw_expected_actions:
                raise EvidenceMalformedError("fixture_expected_actions_invalid")
            try:
                parsed_actions = tuple(parse_action_sequence(action) for action in raw_expected_actions)
            except (TypeError, ValueError) as exc:
                raise EvidenceMalformedError("fixture_expected_actions_invalid") from exc
            if any(
                len(action) != 1 or action[0] != raw
                for action, raw in zip(parsed_actions, raw_expected_actions, strict=True)
            ):
                raise EvidenceMalformedError("fixture_expected_actions_invalid")
            if tuple(action[0] for action in parsed_actions) != expected:
                raise EvidenceMalformedError("fixture_expected_actions_mismatch")
        raw_expectations = fixture.get("semantic_expectations")
        raw_resources = fixture.get("resource_expectations")
        if production_smoke:
            semantic_expectations, resource_expectations = validate_smoke_fixture_contract(
                semantic_expectations=raw_expectations,
                resource_expectations=raw_resources,
                object_count=object_count,
                expected_action_count=len(expected),
            )
        elif raw_expectations is not None:
            semantic_expectations = _semantic_expectations(raw_expectations)
        if not production_smoke and raw_resources is not None:
            _resource_expectations(raw_resources)
    if production_smoke and completed:
        if resource_expectations is None:
            raise EvidenceMalformedError("fixture_resource_expectations_invalid")
        _validate_smoke_resource_execution(resource_expectations, report)

    submission = _optional_mapping(report.get("plan_submission"), "plan_submission", completed)
    if submission is not None:
        recorded_expected = submission.get("expected_plan_text")
        submitted_text = submission.get("submitted_plan_text")
        if not isinstance(recorded_expected, str) or not isinstance(submitted_text, str):
            raise EvidenceMalformedError("submitted_plan_text_missing")
        recorded = parse_action_sequence(recorded_expected)
        submitted = parse_action_sequence(submitted_text)
        action_sequences["submitted"] = list(submitted)
        passed = bool(expected) and expected == recorded == submitted
        claims["expected_action_sequence_match"] = "pass" if passed else "fail"
        diagnostics["expected_action_sequence_match"] = (
            "fixture, recorded expected, and submitted Action Sequences match"
            if passed
            else "fixture, recorded expected, and submitted Action Sequences differ"
        )

    network = _optional_mapping(report.get("network"), "network", completed)
    if network is not None:
        calls = network.get("calls")
        if not isinstance(calls, list):
            raise EvidenceMalformedError("network_calls_invalid")
        backend_evidence = report.get("backend")
        approved_endpoint = backend_evidence.get("endpoint") if isinstance(backend_evidence, Mapping) else None
        loopback_submission = len(calls) == 1 and _valid_plan_call(calls[0], approved_endpoint)
        if loopback_submission:
            call_plan = parse_action_sequence(calls[0]["plan_text"])
            if not submitted or call_plan != submitted:
                raise EvidenceMalformedError("submitted_plan_text_mismatch")
        claims["loopback_plan_submission"] = "pass" if loopback_submission else "fail"
        diagnostics["loopback_plan_submission"] = (
            "exactly one POST to the approved HTTP loopback /upload/pddl endpoint carried a non-empty multipart plan"
            if loopback_submission
            else "render POST count, approved endpoint, or multipart plan evidence did not match"
        )
        all_client_loopback = all(isinstance(call, Mapping) and _is_loopback_url(call.get("url")) for call in calls)
        no_hosted = all_client_loopback and network.get("hosted_requests") == 0 and report.get("hosted_requests") == 0
        claims["no_hosted_client_request"] = "pass" if no_hosted else "fail"
        diagnostics["no_hosted_client_request"] = (
            "all recorded project-client POSTs were loopback and hosted_requests was zero"
            if no_hosted
            else "project-client request evidence included or did not exclude a hosted POST"
        )

    backend = _optional_mapping(report.get("backend"), "backend", completed)
    if backend is not None:
        commit = backend.get("commit")
        if not isinstance(commit, str) or not commit:
            raise EvidenceMalformedError("backend_commit_invalid")
        matched = commit == APPROVED_BACKEND_COMMIT
        claims["backend_commit_match"] = "pass" if matched else "fail"
        diagnostics["backend_commit_match"] = (
            "recorded backend commit matches the approved pin"
            if matched
            else f"recorded backend commit {commit} does not match the approved pin"
        )

    adapter = _optional_mapping(report.get("adapter"), "adapter", completed)
    if adapter is not None:
        counts = adapter.get("counts")
        if not isinstance(counts, Mapping):
            raise EvidenceMalformedError("render_counts_invalid")
        exact = dict(counts) == EXPECTED_RENDER_COUNTS
        claims["render_counts_exact"] = "pass" if exact else "fail"
        diagnostics["render_counts_exact"] = (
            "exactly one state was requested, processed, and rendered successfully"
            if exact
            else "adapter render counts differ from the required exact counts"
        )

    render = _optional_mapping(report.get("render"), "render", completed)
    if render is not None:
        trace_path = _artifact_path(attempt_root, render.get("vfg_path"), "vfg_path")
        frame_path = _artifact_path(attempt_root, render.get("frame_path"), "frame_path")
        try:
            vfg = json.loads(trace_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceMalformedError("vfg_malformed") from exc
        if not isinstance(vfg, Mapping):
            raise EvidenceMalformedError("vfg_malformed")
        vfg_actions = extract_vfg_action_sequence(vfg)
        action_sequences["vfg"] = list(vfg_actions)
        submitted_actions = tuple(action_sequences["submitted"])
        vfg_match = bool(submitted_actions) and submitted_actions == vfg_actions
        claims["vfg_action_sequence_match"] = "pass" if vfg_match else "fail"
        diagnostics["vfg_action_sequence_match"] = (
            "submitted and VFG Action Sequences match in count and order"
            if vfg_match
            else "submitted and VFG Action Sequences differ in count or order"
        )

        stages = vfg.get("visualStages")
        artifact_checks = (
            render.get("status") == "success",
            render.get("vfg_sha256") == _sha256(trace_path),
            render.get("frame_sha256") == _sha256(frame_path),
            isinstance(stages, list),
            isinstance(stages, list) and render.get("visualStages_count") == len(stages),
        )
        artifacts_valid = all(artifact_checks)
        claims["render_artifacts_valid"] = "pass" if artifacts_valid else "fail"
        diagnostics["render_artifacts_valid"] = (
            "required VFG and PNG artifacts exist with matching digests and structure"
            if artifacts_valid
            else "required artifact status, digest, or VFG stage count did not match"
        )

        saved_receipt = render.get("semantic_receipt")
        if not isinstance(saved_receipt, Mapping):
            raise EvidenceMalformedError("semantic_receipt_invalid")
        rerun_receipt = validate_render_artifacts(trace_path, frame_path).to_record()
        fixture_semantics_pass = True
        if semantic_expectations is not None:
            fixture_semantics_pass = (
                rerun_receipt["covered_sprite_count"]
                >= semantic_expectations["minimum_covered_object_count"]
                and len(expected) == semantic_expectations["expected_action_count"]
                and len(vfg_actions) == semantic_expectations["expected_action_count"]
                and isinstance(stages, list)
                and len(stages) == semantic_expectations["expected_visual_stage_count"]
            )
        semantic_pass = (
            saved_receipt.get("status") == "success"
            and dict(saved_receipt) == rerun_receipt
            and fixture_semantics_pass
        )
        claims["semantic_validation_pass"] = "pass" if semantic_pass else "fail"
        diagnostics["semantic_validation_pass"] = (
            "independent Render Validation matched the saved receipt and fixture expectations"
            if semantic_pass
            else "Render Validation, saved receipt, or fixture expectations differed"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "action_sequences": action_sequences,
        "claims": claims,
        "diagnostics": diagnostics,
        "certified": all(status == "pass" for status in claims.values()),
    }


def validate_smoke_fixture_contract(
    *,
    semantic_expectations: Any,
    resource_expectations: Any,
    object_count: Any,
    expected_action_count: int,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    semantics = _semantic_expectations(semantic_expectations)
    if (
        not isinstance(object_count, int)
        or isinstance(object_count, bool)
        or semantics["minimum_covered_object_count"] != object_count
        or semantics["expected_action_count"] != expected_action_count
        or semantics["expected_visual_stage_count"] != expected_action_count + 1
    ):
        raise EvidenceMalformedError("fixture_semantic_expectations_invalid")
    return semantics, _resource_expectations(resource_expectations)


def _semantic_expectations(value: Any) -> Mapping[str, Any]:
    keys = {"minimum_covered_object_count", "expected_action_count", "expected_visual_stage_count"}
    if not isinstance(value, Mapping) or set(value) != keys:
        raise EvidenceMalformedError("fixture_semantic_expectations_invalid")
    if any(not isinstance(value[key], int) or isinstance(value[key], bool) or value[key] <= 0 for key in keys):
        raise EvidenceMalformedError("fixture_semantic_expectations_invalid")
    if value["expected_visual_stage_count"] != value["expected_action_count"] + 1:
        raise EvidenceMalformedError("fixture_semantic_expectations_invalid")
    return value


def _fixture_selector(report: Mapping[str, Any]) -> str | None:
    inputs = report.get("inputs")
    if inputs is None:
        return None
    if not isinstance(inputs, Mapping):
        raise EvidenceMalformedError("inputs_invalid")
    selector = inputs.get("fixture_selector")
    if selector is None:
        return None
    if selector not in {"4-object", *SMOKE_FIXTURE_OBJECT_COUNTS}:
        raise EvidenceMalformedError("smoke_fixture_selector_invalid")
    return selector


def _validate_smoke_resource_execution(resources: Mapping[str, Any], report: Mapping[str, Any]) -> None:
    backend = report.get("backend")
    provenance = report.get("provenance")
    render_config = provenance.get("render_config") if isinstance(provenance, Mapping) else None
    observed = (
        backend.get("startup_timeout_seconds") if isinstance(backend, Mapping) else None,
        render_config.get("timeout_seconds") if isinstance(render_config, Mapping) else None,
        render_config.get("request_delay_seconds") if isinstance(render_config, Mapping) else None,
        render_config.get("max_attempts") if isinstance(render_config, Mapping) else None,
    )
    expected = (
        resources["backend_startup_timeout_seconds"],
        resources["adapter_request_timeout_seconds"],
        resources["request_delay_seconds"],
        resources["max_attempts"],
    )
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value != expected_value
        for value, expected_value in zip(observed, expected, strict=True)
    ):
        raise EvidenceMalformedError("fixture_resource_execution_mismatch")


def _resource_expectations(value: Any) -> Mapping[str, Any]:
    keys = {
        "adapter_request_timeout_seconds",
        "backend_startup_timeout_seconds",
        "max_attempts",
        "request_delay_seconds",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        raise EvidenceMalformedError("fixture_resource_expectations_invalid")
    timeout_values = (
        value["adapter_request_timeout_seconds"],
        value["backend_startup_timeout_seconds"],
    )
    if (
        any(not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 300 for timeout in timeout_values)
        or value["max_attempts"] != 1
        or not isinstance(value["max_attempts"], int)
        or isinstance(value["max_attempts"], bool)
        or value["request_delay_seconds"] != 0
        or not isinstance(value["request_delay_seconds"], int)
        or isinstance(value["request_delay_seconds"], bool)
    ):
        raise EvidenceMalformedError("fixture_resource_expectations_invalid")
    return value


def _optional_mapping(value: Any, name: str, required: bool) -> Mapping[str, Any] | None:
    if value is None and not required:
        return None
    if not isinstance(value, Mapping):
        raise EvidenceMalformedError(f"{name}_invalid")
    return value


def _artifact_path(attempt_root: Path, value: Any, name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise EvidenceMalformedError(f"{name}_invalid")
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (attempt_root / path).resolve()
    if not resolved.is_relative_to(attempt_root) or not resolved.is_file():
        raise EvidenceMalformedError(f"{name}_invalid")
    return resolved


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_loopback_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parts = urlsplit(value)
    return parts.scheme == "http" and parts.hostname in LOOPBACK_HOSTS


def _valid_plan_call(value: Any, approved_endpoint: Any) -> bool:
    if (
        not isinstance(value, Mapping)
        or not isinstance(approved_endpoint, str)
        or not _is_loopback_url(approved_endpoint)
        or value.get("url") != approved_endpoint
    ):
        return False
    plan_text = value.get("plan_text")
    parts = urlsplit(approved_endpoint)
    return (
        parts.path == "/upload/pddl"
        and not parts.query
        and not parts.fragment
        and value.get("plan_present") is True
        and value.get("plan_nonempty") is True
        and isinstance(plan_text, str)
        and bool(plan_text.strip())
    )


def verify_attempt(attempt_root: Path) -> dict[str, Any]:
    attempt_root = attempt_root.expanduser().resolve()
    if not attempt_root.is_dir():
        raise EvidenceMalformedError("attempt_root_invalid")
    report_path = attempt_root / "proof-report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceMalformedError("proof_report_malformed") from exc
    if not isinstance(report, Mapping) or report.get("status") not in {"success", "hard_stop"}:
        raise EvidenceMalformedError("proof_report_malformed")
    derived_fields = ("action_sequences", "claims", "diagnostics", "certified")
    for field in derived_fields:
        if field not in report:
            raise EvidenceMalformedError(f"saved_{field}_missing")
    result = build_certification(report, attempt_root)
    for field in derived_fields:
        if report[field] != result[field]:
            raise EvidenceMalformedError(f"saved_{field}_mismatch")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a saved CGAS Planimation integration attempt offline.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--attempt-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_attempt(args.attempt_root)
    except EvidenceMalformedError as exc:
        print(json.dumps({"error": str(exc), "malformed": True}, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["certified"] else 1


if __name__ == "__main__":
    sys.exit(main())
