"""Strict persisted Phase 3 pairing and state-render record contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, TypeAlias

from .traversal_state_types import JSONValue

JSONRecord: TypeAlias = Mapping[str, JSONValue]

SCHEMA_VERSION: Final = "phase3_planimation_vlm_v1"
ACTIVE_PLANNERS: Final = frozenset({"ff", "gbfs", "iw", "graphplan"})

PAIR_FIELDS: Final = frozenset(
    {
        "schema_version",
        "pair_id",
        "source_root",
        "source_root_id",
        "source_root_sha256",
        "source_jsonl",
        "source_split_sha256",
        "source_line_index",
        "source_record_sha256",
        "example_id",
        "domain",
        "instance_id",
        "split",
        "planner",
        "active_planner_id",
        "bucket",
        "plan_hash",
        "trace_hash",
        "trace_fidelity",
        "planner_approximation",
        "domain_path",
        "problem_path",
        "render_trace_path",
        "render_action_hash",
        "frame_paths",
        "frame_count",
        "plan_length",
        "trace_size_chars",
        "vfg_action_count",
        "frame_alignment_status",
        "vfg_error",
        "training_eligible",
        "exclusion_reasons",
    }
)

STATE_BASE_FIELDS: Final = frozenset(
    {
        "schema_version",
        "pair_id",
        "domain",
        "instance_id",
        "split",
        "planner",
        "step_index",
        "state_hash",
        "transition",
        "cache_dir",
        "cache_key",
        "domain_path",
        "domain_sha256",
        "problem_sha256",
        "profile_path",
        "profile_sha256",
        "renderer_id",
        "renderer_config_sha256",
        "state_sha256",
        "status",
    }
)

STATE_SUCCESS_FIELDS: Final = frozenset(
    {
        "frame_path",
        "derived_problem_path",
        "input_hash",
        "trace_path",
        "vfg_sha256",
        "png_sha256",
        "png_dimensions",
        "semantic_image_qa",
        "semantic_image_metrics",
    }
)

STATE_FAILED_FIELDS: Final = frozenset({"message"})
STATE_OPTIONAL_FIELDS: Final = frozenset({"attempts", "cache_hit", "derived_problem_path", "used_pddl_url"})
STATE_CARDINALITY_FAILURE_FIELDS: Final = frozenset(
    {"schema_version", "pair_id", "domain", "instance_id", "split", "planner", "step_index", "status", "cache_hit", "message", "failure_kind"}
)


def validate_pair_record(record: JSONRecord) -> list[str]:
    """Return controlled errors for a persisted pairing-manifest record."""
    errors = _shape_errors(record, PAIR_FIELDS, PAIR_FIELDS, "pair")
    errors.extend(_text_errors(record, PAIR_FIELDS - {"source_line_index", "frame_paths", "frame_count", "plan_length", "trace_size_chars", "vfg_action_count", "vfg_error", "training_eligible", "exclusion_reasons"}, "pair"))
    errors.extend(_integer_errors(record, {"source_line_index", "frame_count", "plan_length", "trace_size_chars", "vfg_action_count"}, "pair"))
    errors.extend(_string_list_errors(record, {"frame_paths", "exclusion_reasons"}, "pair"))
    errors.extend(_nullable_text_errors(record, {"vfg_error"}, "pair"))
    errors.extend(_boolean_errors(record, {"training_eligible"}, "pair"))
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("pair schema version")
    errors.extend(_nonnegative_errors(record, {"source_line_index", "frame_count", "plan_length", "trace_size_chars", "vfg_action_count"}, "pair"))
    errors.extend(_planner_errors(record, {"planner", "active_planner_id"}, "pair"))
    return errors


def validate_state_render_record(record: JSONRecord, pair_ids: frozenset[str]) -> list[str]:
    """Return controlled errors for a persisted state-render manifest record."""
    status = record.get("status")
    if status == "failed" and record.get("failure_kind") == "render_cardinality_invalid":
        errors = _shape_errors(record, STATE_CARDINALITY_FAILURE_FIELDS, STATE_CARDINALITY_FAILURE_FIELDS, "state render")
        errors.extend(_text_errors(record, STATE_CARDINALITY_FAILURE_FIELDS - {"step_index", "cache_hit"}, "state render"))
        errors.extend(_integer_errors(record, {"step_index"}, "state render"))
        errors.extend(_boolean_errors(record, {"cache_hit"}, "state render"))
        if record.get("schema_version") != SCHEMA_VERSION:
            errors.append("state render schema version")
        if record.get("failure_kind") != "render_cardinality_invalid":
            errors.append("state render failure kind")
        errors.extend(_planner_errors(record, {"planner"}, "state render"))
        pair_id = record.get("pair_id")
        if isinstance(pair_id, str) and pair_id not in pair_ids:
            errors.append("state render unknown pair")
        return errors
    variant_fields = (
        STATE_SUCCESS_FIELDS | {"cache_hit"} | STATE_OPTIONAL_FIELDS
        if status == "success"
        else STATE_FAILED_FIELDS | STATE_OPTIONAL_FIELDS
    )
    errors = _shape_errors(record, STATE_BASE_FIELDS, STATE_BASE_FIELDS | variant_fields, "state render")
    errors.extend(_text_errors(record, STATE_BASE_FIELDS - {"schema_version", "planner", "step_index", "transition", "status"}, "state render"))
    errors.extend(_integer_errors(record, {"step_index"}, "state render"))
    errors.extend(_mapping_errors(record, {"transition"}, "state render"))
    errors.extend(_planner_errors(record, {"planner"}, "state render"))
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("state render schema version")
    pair_id = record.get("pair_id")
    if isinstance(pair_id, str) and pair_id not in pair_ids:
        errors.append("state render unknown pair")
    match status:
        case "success":
            errors.extend(_text_errors(record, STATE_SUCCESS_FIELDS - {"png_dimensions", "semantic_image_metrics"}, "state render"))
            errors.extend(_integer_list_errors(record, {"png_dimensions"}, "state render"))
            errors.extend(_mapping_errors(record, {"semantic_image_metrics"}, "state render"))
            errors.extend(_boolean_errors(record, {"cache_hit"}, "state render"))
        case "failed":
            errors.extend(_text_errors(record, STATE_FAILED_FIELDS, "state render"))
        case status:
            errors.append(f"state render status must be success or failed: {status}")
    errors.extend(_optional_integer_errors(record, frozenset({"attempts"}), "state render"))
    errors.extend(_optional_boolean_errors(record, frozenset({"cache_hit"}), "state render"))
    errors.extend(_optional_text_errors(record, frozenset({"derived_problem_path", "used_pddl_url"}), "state render"))
    return errors


def _shape_errors(record: JSONRecord, required: frozenset[str], allowed: frozenset[str], label: str) -> list[str]:
    missing = sorted(required - set(record))
    unexpected = sorted(set(record) - allowed)
    return [*(f"{label} missing {field}" for field in missing), *(f"{label} unexpected {field}" for field in unexpected)]


def _text_errors(record: JSONRecord, fields: frozenset[str], label: str) -> list[str]:
    return [f"{label} {field} must be a nonempty string" for field in sorted(fields) if not isinstance(record.get(field), str) or not record[field]]


def _nullable_text_errors(record: JSONRecord, fields: frozenset[str], label: str) -> list[str]:
    return [f"{label} {field} must be a string or null" for field in sorted(fields) if record.get(field) is not None and not isinstance(record.get(field), str)]


def _integer_errors(record: JSONRecord, fields: frozenset[str], label: str) -> list[str]:
    return [f"{label} {field} must be an integer" for field in sorted(fields) if type(record.get(field)) is not int]


def _optional_integer_errors(record: JSONRecord, fields: frozenset[str], label: str) -> list[str]:
    return [f"{label} {field} must be an integer" for field in sorted(fields) if field in record and type(record[field]) is not int]


def _optional_boolean_errors(record: JSONRecord, fields: frozenset[str], label: str) -> list[str]:
    return [f"{label} {field} must be a boolean" for field in sorted(fields) if field in record and not isinstance(record[field], bool)]


def _optional_text_errors(record: JSONRecord, fields: frozenset[str], label: str) -> list[str]:
    return [f"{label} {field} must be a nonempty string" for field in sorted(fields) if field in record and (not isinstance(record[field], str) or not record[field])]


def _nonnegative_errors(record: JSONRecord, fields: frozenset[str], label: str) -> list[str]:
    return [f"{label} {field} must be nonnegative" for field in sorted(fields) if type(record.get(field)) is int and record[field] < 0]


def _boolean_errors(record: JSONRecord, fields: frozenset[str], label: str) -> list[str]:
    return [f"{label} {field} must be a boolean" for field in sorted(fields) if not isinstance(record.get(field), bool)]


def _string_list_errors(record: JSONRecord, fields: frozenset[str], label: str) -> list[str]:
    return [f"{label} {field} must be a string array" for field in sorted(fields) if not isinstance(record.get(field), list) or not all(isinstance(item, str) for item in record[field])]


def _integer_list_errors(record: JSONRecord, fields: frozenset[str], label: str) -> list[str]:
    return [f"{label} {field} must be an integer array" for field in sorted(fields) if not isinstance(record.get(field), list) or not all(type(item) is int for item in record[field])]


def _mapping_errors(record: JSONRecord, fields: frozenset[str], label: str) -> list[str]:
    return [f"{label} {field} must be an object" for field in sorted(fields) if not isinstance(record.get(field), dict)]


def _planner_errors(record: JSONRecord, fields: frozenset[str], label: str) -> list[str]:
    return [f"{label} {field} is unsupported" for field in sorted(fields) if isinstance(record.get(field), str) and record[field] not in ACTIVE_PLANNERS]
