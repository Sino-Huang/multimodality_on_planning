from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "phase3_supervised_planning_v1"

PLANNER_STATUSES = frozenset(
    {
        "success_full_trace",
        "success_plan_replayed",
        "skipped_planner_unavailable",
        "skipped_unsupported_pddl",
        "skipped_grounding_limit",
        "skipped_resource_limit",
        "failed_parse_domain",
        "failed_parse_problem",
        "failed_grounding",
        "failed_planner_timeout",
        "failed_planner_error",
        "failed_no_plan_extracted",
        "failed_action_normalization",
        "failed_replay_invalid_action",
        "failed_replay_goal_not_satisfied",
        "failed_vision_missing",
        "failed_schema_validation",
    }
)

VISION_STATUSES = frozenset(
    {
        "vision_available_step_aligned",
        "vision_available_unaligned",
        "vision_missing_result_json",
        "vision_missing_trace_vfg",
        "vision_missing_frames",
        "vision_unreadable_frames",
        "vision_action_mismatch",
        "vision_not_required_for_text_only_example",
    }
)

REQUIRED_EXAMPLE_FIELDS = (
    "schema_version",
    "example_id",
    "domain",
    "instance_id",
    "split",
    "planner",
    "plan_hash",
    "trace_fidelity",
    "vision_supervision_available",
    "model_facing",
    "supervised_target",
    "evaluation_metadata",
)

REQUIRED_ATTEMPT_FIELDS = (
    "schema_version",
    "domain",
    "instance_id",
    "split",
    "planner",
    "status",
    "trace_fidelity",
    "replay_validation_id",
)

PLANNER_ATTEMPT_FIELDS = (
    *REQUIRED_ATTEMPT_FIELDS,
    "domain_path",
    "problem_path",
    "planner_command",
    "planner_version",
    "plan_hash",
    "resource_gate",
    "expansion_count",
    "plan_length",
    "schema_errors",
)

REQUIRED_ACCOUNTING_FIELDS = (
    "schema_version",
    "domain",
    "instance_id",
    "split",
    "domain_path",
    "problem_path",
    "vision_status",
)

INSTANCE_ACCOUNTING_FIELDS = (
    *REQUIRED_ACCOUNTING_FIELDS,
    "manifest_index",
    "bucket",
    "render_result_path",
    "render_trace_path",
    "frame_paths",
    "source_manifest",
    "files",
    "schema_errors",
)


class Phase3SchemaError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def validate_supervised_example(record: dict[str, Any]) -> list[str]:
    errors = _missing(record, REQUIRED_EXAMPLE_FIELDS)
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be phase3_supervised_planning_v1")
    if record.get("trace_fidelity") not in {"success_full_trace", "success_plan_replayed"}:
        errors.append("trace_fidelity must be a successful controlled status")
    for key in ("model_facing", "supervised_target", "evaluation_metadata"):
        if not isinstance(record.get(key), dict):
            errors.append(f"{key} must be an object")
    errors.extend(_absolute_path_errors(record))
    return errors


def validate_planner_attempt(record: dict[str, Any]) -> list[str]:
    errors = _missing(record, REQUIRED_ATTEMPT_FIELDS)
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be phase3_supervised_planning_v1")
    if record.get("status") not in PLANNER_STATUSES:
        errors.append("status must be a controlled planner status")
    errors.extend(_absolute_path_errors(record))
    return errors


def validate_instance_accounting(record: dict[str, Any]) -> list[str]:
    errors = _missing(record, REQUIRED_ACCOUNTING_FIELDS)
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be phase3_supervised_planning_v1")
    if record.get("vision_status") not in VISION_STATUSES:
        errors.append("vision_status must be a controlled vision status")
    errors.extend(_absolute_path_errors(record))
    return errors


def write_schema_documents(output_root: Path) -> None:
    schema_dir = output_root / "schema"
    schema_dir.mkdir(parents=True, exist_ok=True)
    _write_json(schema_dir / "supervised_planning_example.schema.json", _schema_doc("supervised_planning_example", REQUIRED_EXAMPLE_FIELDS))
    _write_json(schema_dir / "planner_attempt.schema.json", _schema_doc("planner_attempt", PLANNER_ATTEMPT_FIELDS, required=REQUIRED_ATTEMPT_FIELDS))
    _write_json(schema_dir / "instance_accounting.schema.json", _schema_doc("instance_accounting", INSTANCE_ACCOUNTING_FIELDS, required=REQUIRED_ACCOUNTING_FIELDS))


def _schema_doc(title: str, fields: tuple[str, ...], *, required: tuple[str, ...] | None = None) -> dict[str, Any]:
    required_fields = required or fields
    properties: dict[str, Any] = {field: {} for field in fields}
    properties["schema_version"] = {"const": SCHEMA_VERSION}
    if "status" in fields:
        properties["status"] = {"enum": sorted(PLANNER_STATUSES)}
    if "vision_status" in fields:
        properties["vision_status"] = {"enum": sorted(VISION_STATUSES)}
    for field in ("model_facing", "supervised_target", "evaluation_metadata"):
        if field in fields:
            properties[field] = {"type": "object"}
    for field in ("domain", "instance_id", "split", "planner", "example_id", "plan_hash", "trace_fidelity"):
        if field in required_fields:
            properties[field] = {"type": "string"}
    if "vision_supervision_available" in fields:
        properties["vision_supervision_available"] = {"type": "boolean"}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": title,
        "type": "object",
        "required": list(required_fields),
        "properties": properties,
        "additionalProperties": False,
        "schema_version": SCHEMA_VERSION,
    }


def _missing(record: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [f"missing required field: {field}" for field in fields if field not in record]


def _absolute_path_errors(value: Any, path: str = "<root>") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            errors.extend(_absolute_path_errors(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(_absolute_path_errors(item, f"{path}[{index}]"))
    elif isinstance(value, str) and value.startswith("/"):
        errors.append(f"absolute path forbidden at {path}")
    return errors


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
