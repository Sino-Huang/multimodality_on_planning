from __future__ import annotations
from pathlib import Path
from .io_utils import is_relative_artifact_path, stable_hash, write_json
from .traversal_state_types import JSONValue
SCHEMA_VERSION = "phase3_planimation_vlm_v1"

__all__ = (
    "_full_record",
    "_step_record",
    "_search_traversal_record",
    "_write_pairing_schema",
    "_write_vlm_schema",
)

from .planimation_pairing_reasoning import _language_context
def _full_record(pair: dict[str, JSONValue], source: dict[str, JSONValue], initial: dict[str, JSONValue], goal: JSONValue) -> dict[str, JSONValue]:
    trace = source["supervised_target"]["planner_trace"]
    return _hybrid_record(
        pair,
        initial,
        _language_context(initial["transition"]["state_before"], goal, pair["planner"]),
        {"kind": "planner_trace", "planner_trace": trace},
        "full_reasoning_record",
        "hybrid_full",
        trace,
    )

def _step_record(pair: dict[str, JSONValue], source: dict[str, JSONValue], state: dict[str, JSONValue], goal: JSONValue, reasoning: dict[str, JSONValue]) -> dict[str, JSONValue]:
    transition = state["transition"]
    trace = source["supervised_target"]["planner_trace"]
    return _hybrid_record(
        pair,
        state,
        _language_context(transition["state_before"], goal, pair["planner"]),
        {"kind": "next_action", "next_action": transition["action"], "reasoning_context": reasoning},
        "step_vlm_record",
        "hybrid_step",
        trace,
    )

def _search_traversal_record(pair: dict[str, JSONValue], source: dict[str, JSONValue], state: dict[str, JSONValue], goal: JSONValue) -> dict[str, JSONValue]:
    transition = state["transition"]
    trace = source["supervised_target"]["planner_trace"]
    return _hybrid_record(
        pair,
        state,
        _language_context(transition["state_before"], goal, pair["planner"]),
        {
            "kind": "search_event",
            "event_kind": transition["event_kind"],
            "event_id": transition["event_id"],
            "parent_event_id": transition["parent_event_id"],
            "normalized_action": transition["normalized_action"],
        },
        "search_traversal_record",
        "search_traversal",
        trace,
    )

def _hybrid_record(pair: dict[str, JSONValue], state: dict[str, JSONValue], language_context: dict[str, JSONValue], target: dict[str, JSONValue], record_type: str, supervision_mode: str, trace: dict[str, JSONValue]) -> dict[str, JSONValue]:
    transition = state["transition"]
    step_index = int(transition["step_index"])
    event_id = str(transition["event_id"])
    artifact_paths = {
        "image_path": state["frame_path"],
        "render_trace_path": state["trace_path"],
        "derived_problem_path": state["derived_problem_path"],
    }
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": record_type,
        "record_id": stable_hash([pair["pair_id"], record_type, event_id])[:32],
        "split": pair["split"],
        "domain": pair["domain"],
        "instance_id": pair["instance_id"],
        "planner": pair["planner"],
        "planner_approximation": pair["planner_approximation"],
        "supervision_mode": supervision_mode,
        "artifact_paths": artifact_paths,
        "language_context": language_context,
        "target": target,
        "provenance": {
            "pair": {key: pair[key] for key in ("pair_id", "example_id", "source_root_id", "source_jsonl", "source_line_index", "source_record_sha256", "source_split_sha256", "source_root_sha256", "plan_hash")},
            "event": {"event_id": event_id, "parent_event_id": transition.get("parent_event_id"), "step_index": step_index, "action": transition["action"], "normalized_action": transition.get("normalized_action"), "frame_role": transition["frame_role"], "event_kind": transition.get("event_kind", "plan_replay"), "state_role": transition.get("state_role", "plan_replay")},
            "state": {"state_hash": state["state_hash"], "state_asset_hash": transition.get("state_asset_hash", state["state_hash"]), "state_source": transition["state_source"], "state_before_hash": stable_hash(transition["state_before"]), "state_after_hash": stable_hash(transition["state_after"])},
            "trace": {"trace_contract_version": trace["trace_contract_version"], "full_trace_hash": stable_hash(trace), "trace_size_chars": pair["trace_size_chars"], "trace_fidelity": pair["trace_fidelity"]},
            "render": {key: state[key] for key in ("cache_key", "cache_dir", "derived_problem_path", "input_hash", "trace_path", "vfg_sha256", "png_sha256", "png_dimensions", "semantic_image_qa", "semantic_image_metrics")},
        },
    }
    if record_type == "step_vlm_record":
        record["step_index"] = step_index
    errors = validate_vlm_record(record)
    if errors:
        raise ValueError(f"invalid hybrid record: {'; '.join(errors)}")
    return record

def _write_pairing_schema(path: Path) -> None:
    _write_schema(path, "pairing_manifest", ["schema_version", "pair_id", "source_root", "source_root_id", "source_root_sha256", "source_jsonl", "source_split_sha256", "source_line_index", "source_record_sha256", "example_id", "active_planner_id", "domain", "instance_id", "split", "planner", "plan_length", "trace_size_chars", "frame_count", "frame_alignment_status", "training_eligible", "exclusion_reasons"])

def _write_vlm_schema(path: Path, title: str) -> None:
    write_json(path, _hybrid_vlm_schema(title))

def _hybrid_vlm_schema(record_type: str) -> dict[str, JSONValue]:
    supervision_mode = "hybrid_full" if record_type == "full_reasoning_record" else "hybrid_step" if record_type == "step_vlm_record" else "search_traversal"
    required = ["schema_version", "record_type", "record_id", "split", "domain", "instance_id", "planner", "planner_approximation", "supervision_mode", "artifact_paths", "language_context", "target", "provenance"]
    if record_type == "step_vlm_record":
        required.append("step_index")
    target_properties = {"kind": {"const": "planner_trace"}, "planner_trace": {"type": "object"}}
    if record_type == "step_vlm_record":
        target_properties = {"kind": {"const": "next_action"}, "next_action": {"type": "string"}, "reasoning_context": {"type": "object"}}
    if record_type == "search_traversal_record":
        target_properties = {"kind": {"const": "search_event"}, "event_kind": {"type": "string"}, "event_id": {"type": "string"}, "parent_event_id": {"type": ["string", "null"]}, "normalized_action": {"type": ["string", "null"]}}
    root_properties = {
        "schema_version": {"const": SCHEMA_VERSION},
        "record_type": {"const": record_type},
        "record_id": {"type": "string"},
        "split": {"type": "string"},
        "domain": {"type": "string"},
        "instance_id": {"type": "string"},
        "planner": {"type": "string"},
        "planner_approximation": {"type": "string"},
        "supervision_mode": {"const": supervision_mode},
        "artifact_paths": _strict_object_schema({field: {"type": "string"} for field in ("image_path", "render_trace_path", "derived_problem_path")}),
        "language_context": _strict_object_schema({field: {"type": "string"} for field in ("instruction", "current_state_pddl", "goal_pddl")}),
        "target": {"type": "object", "required": list(target_properties), "properties": target_properties, "additionalProperties": False},
        "provenance": {"type": "object", "required": ["pair", "event", "state", "trace", "render"], "properties": {
            "pair": _strict_object_schema({field: {"type": "integer"} if field == "source_line_index" else {"type": "string"} for field in ("pair_id", "example_id", "source_root_id", "source_jsonl", "source_line_index", "source_record_sha256", "source_split_sha256", "source_root_sha256", "plan_hash")}),
            "event": _strict_object_schema({"event_id": {"type": "string"}, "parent_event_id": {"type": ["string", "null"]}, "step_index": {"type": "integer"}, "action": {"type": ["string", "null"]}, "normalized_action": {"type": ["string", "null"]}, "frame_role": {"type": "string"}, "event_kind": {"type": "string"}, "state_role": {"type": "string"}}),
            "state": _strict_object_schema({field: {"type": "string"} for field in ("state_hash", "state_asset_hash", "state_source", "state_before_hash", "state_after_hash")}),
            "trace": _strict_object_schema({"trace_contract_version": {"type": "string"}, "full_trace_hash": {"type": "string"}, "trace_size_chars": {"type": "integer"}, "trace_fidelity": {"type": "string"}}),
            "render": _strict_object_schema({**{field: {"type": "string"} for field in ("cache_key", "cache_dir", "derived_problem_path", "input_hash", "trace_path", "vfg_sha256", "png_sha256", "semantic_image_qa")}, "png_dimensions": {"type": "array", "items": {"type": "integer"}}, "semantic_image_metrics": {"type": "object"}}),
        }, "additionalProperties": False},
    }
    if record_type == "step_vlm_record":
        root_properties["step_index"] = {"type": "integer"}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": record_type,
        "type": "object",
        "required": required,
        "properties": root_properties,
        "additionalProperties": False,
    }

def _strict_object_schema(properties: dict[str, dict[str, JSONValue]]) -> dict[str, JSONValue]:
    return {"type": "object", "required": list(properties), "properties": properties, "additionalProperties": False}

def validate_vlm_record(record: dict[str, JSONValue]) -> list[str]:
    """Validate one strict hybrid supervision record before it reaches JSONL."""
    record_type = record.get("record_type")
    if record_type not in {"full_reasoning_record", "step_vlm_record", "search_traversal_record"}:
        return ["record_type is not a supported hybrid record"]
    errors = _schema_instance_errors(record, _hybrid_vlm_schema(record_type), "")
    for field in ("record_id", "split", "domain", "instance_id", "planner", "planner_approximation"):
        if not isinstance(record.get(field), str) or not record[field]:
            errors.append(f"record {field}")
    if isinstance(record.get("artifact_paths"), dict):
        for field, path_text in record["artifact_paths"].items():
            if not isinstance(path_text, str) or not is_relative_artifact_path(path_text):
                errors.append(f"artifact_paths {field} must be relative")
    if isinstance(record.get("provenance"), dict):
        provenance = record["provenance"]
        render = provenance.get("render")
        if isinstance(render, dict):
            for field in ("cache_dir", "derived_problem_path", "trace_path"):
                path_text = render.get(field)
                if not isinstance(path_text, str) or not is_relative_artifact_path(path_text):
                    errors.append(f"provenance.render {field} must be relative")
    return errors

def validate_vlm_schema_instance(record: dict[str, JSONValue], schema: dict[str, JSONValue]) -> list[str]:
    return _schema_instance_errors(record, schema, "")

def _schema_instance_errors(value: JSONValue, schema: dict[str, JSONValue], path: str) -> list[str]:
    errors: list[str] = []
    node_name = path or "record"
    if "const" in schema and value != schema["const"]:
        errors.append(f"schema const mismatch for {node_name}")
    expected_type = schema.get("type")
    expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
    if expected_type is not None and not any(_matches_schema_type(value, item) for item in expected_types):
        expected = " or ".join(str(item) for item in expected_types)
        return [*errors, f"schema type mismatch for {node_name}: expected {expected}"]
    if expected_type == "object" and isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if isinstance(required, list):
            errors.extend(f"{node_name} missing {field}" for field in required if field not in value)
        if schema.get("additionalProperties") is False and isinstance(properties, dict):
            errors.extend(f"{node_name} unexpected {field}" for field in sorted(set(value) - set(properties)))
        if isinstance(properties, dict):
            for field, nested_schema in properties.items():
                if field in value and isinstance(nested_schema, dict):
                    nested_path = f"{path}.{field}" if path else field
                    errors.extend(_schema_instance_errors(value[field], nested_schema, nested_path))
    if expected_type == "array" and isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(_schema_instance_errors(item, item_schema, f"{path}[{index}]"))
    return errors

def _matches_schema_type(value: JSONValue, expected_type: JSONValue) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return False

def _write_schema(path: Path, title: str, required: list[str]) -> None:
    write_json(path, {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": title, "type": "object", "required": required, "properties": {"schema_version": {"const": SCHEMA_VERSION}}, "additionalProperties": True})
