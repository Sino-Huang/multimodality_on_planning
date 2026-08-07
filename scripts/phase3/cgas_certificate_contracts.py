from __future__ import annotations

from copy import deepcopy
from typing import Final

from .cgas_serialization import canonical, digest_text


SCHEMA_VERSION: Final = "planning_cgas_v1"
INPUT_FIELDS: Final = frozenset({"domain", "image_path", "planner", "task_text"})
BFS_FIELDS: Final = ("frontier_head", "frontier_order_summary", "visited_delta", "expanded_state")
IW_FIELDS: Final = ("novelty_tuple", "seen_feature_delta", "width_decision")
ORACLE_FIELDS: Final = frozenset({"action_target", "certificate", "counterfactual_targets", "diagnostics", "evaluation_diagnostics", "final_state", "gold_queue", "gold_targets", "memory_payload", "novelty_table", "planner_trace", "queue", "replay_trace", "route_label", "scaffold_costs", "visited"})


def step_schema() -> dict[str, object]:
    string_array = {"type": "array", "items": {"type": "string"}}
    bfs_certificate = {"type": "object", "required": ["kind", "frontier_head", "frontier_order_summary", "visited_delta", "expanded_state"], "properties": {"kind": {"const": "bfs"}, "frontier_head": {"type": "string"}, "frontier_order_summary": string_array, "visited_delta": string_array, "expanded_state": {"type": "string"}}, "additionalProperties": False}
    iw_certificate = {"type": "object", "required": ["kind", "novelty_tuple", "seen_feature_delta", "width_decision"], "properties": {"kind": {"const": "iw"}, "novelty_tuple": {"type": "string"}, "seen_feature_delta": string_array, "width_decision": {"type": "string"}}, "additionalProperties": False}
    certificate = {"oneOf": [{"$ref": "#/$defs/bfs_certificate"}, {"$ref": "#/$defs/iw_certificate"}]}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": SCHEMA_VERSION, "type": "object", "required": ["schema_version", "step_id", "source_transition_id", "source_hash", "planner", "split", "structural_ood", "model_input", "action_target", "certificate", "replay_evidence", "alignment", "counterfactual_targets"], "properties": {"schema_version": {"const": SCHEMA_VERSION}, "step_id": {"type": "string"}, "source_transition_id": {"type": "string"}, "source_hash": {"type": "string"}, "planner": {"$ref": "#/$defs/planner"}, "split": {"enum": ["train", "dev", "test"]}, "structural_ood": {"type": "boolean"}, "model_input": {"$ref": "#/$defs/model_input"}, "action_target": {"type": "string"}, "certificate": certificate, "replay_evidence": {"$ref": "#/$defs/replay_evidence"}, "alignment": {"$ref": "#/$defs/alignment"}, "counterfactual_targets": {"type": "array", "items": {"$ref": "#/$defs/counterfactual"}}}, "additionalProperties": False, "$defs": {"planner": {"type": "object", "required": ["algorithm", "version"], "properties": {"algorithm": {"enum": ["breadth_first_search", "iterated_width"]}, "version": {"type": "string"}}, "additionalProperties": False}, "model_input": {"type": "object", "required": ["domain", "image_path", "planner", "task_text"], "properties": {"domain": {"type": "string"}, "image_path": {"type": "string"}, "planner": {"enum": ["breadth_first_search", "iterated_width"]}, "task_text": {"type": "string"}}, "additionalProperties": False}, "replay_evidence": {"type": "object", "required": ["replay_ok", "replay_validation_id"], "properties": {"replay_ok": {"const": True}, "replay_validation_id": {"type": "string"}}, "additionalProperties": False}, "alignment": {"type": "object", "required": ["png_sha256", "state_before_hash", "vision_status"], "properties": {"png_sha256": {"type": "string"}, "state_before_hash": {"type": "string"}, "vision_status": {"const": "vision_available_step_aligned"}}, "additionalProperties": False}, "bfs_certificate": bfs_certificate, "iw_certificate": iw_certificate, "counterfactual": {"type": "object", "required": ["counterfactual_id", "declared_invariant", "planner_algorithm", "certificate", "expected_certificate"], "properties": {"counterfactual_id": {"type": "string"}, "declared_invariant": {"enum": [*BFS_FIELDS, *IW_FIELDS]}, "planner_algorithm": {"enum": ["breadth_first_search", "iterated_width"]}, "certificate": certificate, "expected_certificate": certificate}, "additionalProperties": False}}}


def stable_step_id(source_id: str, alignment_hash: str) -> str:
    return f"cgas-step-{digest_text(f'{source_id}:{alignment_hash}')[:24]}"


def expected_certificate(source: dict[str, object]) -> dict[str, object]:
    """Project one certificate from the authoritative planner trace."""
    planner = _mapping(source, "planner")
    trace = _mapping(source, "planner_trace")
    algorithm = _text(planner, "algorithm")
    match algorithm:
        case "breadth_first_search":
            expansion = _bfs_expansion(source, trace)
            expansions = _list(trace, "expansions")
            index = expansions.index(expansion)
            frontier = [_text(_mapping_item(expansions[0], "first_expansion"), "state_id")]
            enqueued: list[str] = []
            for item in expansions[: index + 1]:
                enqueued = _bfs_enqueued(_mapping_item(item, "bfs_expansion"))
                frontier = [*frontier[1:], *enqueued]
            state_id = _text(expansion, "state_id")
            visited_delta = sorted([*enqueued, *([state_id] if index == 0 else [])])
            return {
                "kind": "bfs",
                "frontier_head": state_id,
                "frontier_order_summary": frontier,
                "visited_delta": visited_delta,
                "expanded_state": state_id,
            }
        case "iterated_width":
            event = _iw_event(source, trace)
            before = set(_strings(event, "novelty_table_before"))
            after = set(_strings(event, "novelty_table_after"))
            return {"kind": "iw", "novelty_tuple": _text(event, "novel_item"), "seen_feature_delta": sorted(after - before), "width_decision": _text(event, "width_decision")}
        case unsupported:
            raise CertificateError("unsupported_planner", _text(source, "record_id"), unsupported)


def certificate_failures(certificate: dict[str, object], expected: dict[str, object]) -> list[str]:
    fields = BFS_FIELDS if expected["kind"] == "bfs" else IW_FIELDS
    return [field for field in fields if certificate.get(field) != expected.get(field)]


def counterfactuals_for(record: dict[str, object]) -> list[dict[str, object]]:
    certificate = _mapping(record, "certificate")
    algorithm = _text(_mapping(record, "planner"), "algorithm")
    fields = BFS_FIELDS if algorithm == "breadth_first_search" else IW_FIELDS
    variants: list[dict[str, object]] = []
    for field in fields:
        mutated = deepcopy(certificate)
        mutated[field] = _alternate(mutated[field])
        variants.append({"counterfactual_id": f"{_text(record, 'step_id')}:{field}", "declared_invariant": field, "planner_algorithm": algorithm, "certificate": mutated, "expected_certificate": deepcopy(certificate)})
    return variants


def verify_counterfactual(variant: dict[str, object]) -> dict[str, object]:
    expected = _mapping(variant, "expected_certificate")
    actual = _mapping(variant, "certificate")
    failures = certificate_failures(actual, expected)
    declared = _text(variant, "declared_invariant")
    if len(failures) == 1 and failures[0] == declared:
        return {"failure_count": 1, "reason": declared}
    if len(failures) > 1:
        return {"failure_count": len(failures), "reason": "multiple_invariants_changed"}
    return {"failure_count": len(failures), "reason": "wrong_declared_invariant"}


def validate_model_input(value: dict[str, object]) -> list[str]:
    keys = set(value)
    errors = ["oracle_field_in_input" for key in keys if key in ORACLE_FIELDS]
    errors.extend("invalid_model_input_field" for key in keys if key not in INPUT_FIELDS)
    return errors


def validate_step_schema(record: dict[str, object]) -> list[str]:
    required = {"schema_version", "step_id", "source_transition_id", "source_hash", "planner", "split", "structural_ood", "model_input", "action_target", "certificate", "replay_evidence", "alignment", "counterfactual_targets"}
    errors = [f"missing_schema_field:{field}" for field in sorted(required - set(record))]
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("invalid_schema_version")
    model_input = record.get("model_input")
    if not isinstance(model_input, dict):
        errors.append("invalid_model_input")
    else:
        errors.extend(validate_model_input(model_input))
    return errors


class CertificateError(RuntimeError):
    def __init__(self, reason: str, record_id: str, detail: str) -> None:
        self.reason = reason
        self.record_id = record_id
        self.detail = detail
        super().__init__(f"{reason}:{record_id}:{detail}")


def _bfs_expansion(source: dict[str, object], trace: dict[str, object]) -> dict[str, object]:
    state = _text(source, "state_before_id")
    expansions = _list(trace, "expansions")
    matches = [item for item in expansions if isinstance(item, dict) and item.get("state_id") == state]
    if len(matches) != 1:
        raise CertificateError("bfs_expansion_not_unique", _text(source, "record_id"), state)
    return matches[0]


def _bfs_enqueued(expansion: dict[str, object]) -> list[str]:
    successors = [_mapping_item(item, "bfs_successor") for item in _list(expansion, "successors")]
    return [_text(successor, "state_id") for successor in successors if successor.get("enqueued") is True]


def _iw_event(source: dict[str, object], trace: dict[str, object]) -> dict[str, object]:
    state = source.get("state_before")
    events = _list(trace, "events")
    matches = [item for item in events if isinstance(item, dict) and item.get("state_atoms") == state and item.get("decision") == "expand"]
    if len(matches) != 1:
        raise CertificateError("iw_event_not_unique", _text(source, "record_id"), canonical(state))
    return matches[0]


def _alternate(value: object) -> object:
    if isinstance(value, str):
        return f"counterfactual:{value}"
    if isinstance(value, list):
        return ["counterfactual"]
    raise CertificateError("unsupported_counterfactual_value", "unknown", type(value).__name__)


def _mapping(value: dict[str, object], field: str) -> dict[str, object]:
    return _mapping_item(value.get(field), field)


def _mapping_item(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise CertificateError("invalid_mapping", "unknown", field)
    return value


def _text(value: dict[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str):
        raise CertificateError("invalid_text", "unknown", field)
    return item


def _strings(value: dict[str, object], field: str) -> list[str]:
    items = _list(value, field)
    if not all(isinstance(item, str) for item in items):
        raise CertificateError("invalid_string_array", "unknown", field)
    return [item for item in items if isinstance(item, str)]


def _list(value: dict[str, object], field: str) -> list[object]:
    item = value.get(field)
    if not isinstance(item, list):
        raise CertificateError("invalid_list", "unknown", field)
    return item
