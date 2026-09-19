from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, NoReturn

from .pddl_state import CanonicalState, GroundedAction, PDDLStateAuthority, PDDLTransition
from .search_memory import (
    AcceptedRetirement,
    AcceptedTransition,
    FrontierIntent,
    HeuristicValue,
    RejectedTransition,
    SearchMemory,
    SearchOperation,
    SearchRetireRequest,
    SearchTransitionRequest,
    SearchTransitionResult,
    StateEvaluation,
    apply_search_retirement,
    apply_search_transition,
)

SCHEMA_VERSION = 1
_ENVELOPE_FIELDS = {
    "schema_version",
    "authority_id",
    "record_count",
    "records",
}
_RECORD_FIELDS = {
    "index",
    "observation",
    "rationale",
    "operation",
    "result",
}
_OPERATION_FIELDS = {
    "source_state_id",
    "action",
    "frontier_intent",
    "visit_target",
    "evaluate_target",
}
_RETIRE_OPERATION_FIELDS = {"operation_type", "state_id"}


class SearchTraceError(ValueError):
    """Raised when a search trace is invalid, inconsistent, or too large."""


# Convenient aliases for callers that use a shorter or validation-specific name.
TraceError = SearchTraceError
SearchTraceValidationError = SearchTraceError


@dataclass(frozen=True, slots=True)
class TraceSegmentLimits:
    max_records: int
    max_bytes: int

    def __post_init__(self) -> None:
        if isinstance(self.max_records, bool) or not isinstance(self.max_records, int) or self.max_records <= 0:
            raise ValueError("max_records must be a positive integer")
        if isinstance(self.max_bytes, bool) or not isinstance(self.max_bytes, int) or self.max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")


@dataclass(frozen=True, slots=True)
class SearchTraceSegment:
    schema_version: int
    authority_id: str
    _record_payloads: tuple[bytes, ...]
    _tail_memory: bytes

    @property
    def record_count(self) -> int:
        return len(self._record_payloads)

    def to_bytes(self) -> bytes:
        records = [_load_canonical_json(item) for item in self._record_payloads]
        return _canonical_bytes(
            {
                "schema_version": self.schema_version,
                "authority_id": self.authority_id,
                "record_count": len(records),
                "records": records,
            }
        )


def start_search_trace(memory: SearchMemory, *, limits: TraceSegmentLimits) -> SearchTraceSegment:
    segment = SearchTraceSegment(
        schema_version=SCHEMA_VERSION,
        authority_id=memory.authority.authority_id,
        _record_payloads=(),
        _tail_memory=memory.to_bytes(),
    )
    _validated_envelope(segment.to_bytes(), limits=limits)
    return segment


def _append_search_trace_record(
    segment: SearchTraceSegment,
    *,
    memory_before: SearchMemory,
    observation: Mapping[str, Any],
    rationale: str,
    operation: SearchOperation,
    result: SearchTransitionResult,
    limits: TraceSegmentLimits,
    validate_existing: bool,
    enforce_size: bool,
) -> SearchTraceSegment:
    if not isinstance(segment, SearchTraceSegment):
        raise SearchTraceError("segment must be a SearchTraceSegment")
    if validate_existing:
        _validated_envelope(segment.to_bytes(), limits=None)
    if len(segment._record_payloads) >= limits.max_records:
        raise SearchTraceError("trace exceeds max_records")
    if memory_before.authority.authority_id != segment.authority_id:
        raise SearchTraceError("memory authority does not match trace authority")
    if memory_before.to_bytes() != segment._tail_memory:
        raise SearchTraceError("memory_before does not match the trace tail")
    if not isinstance(observation, Mapping):
        raise SearchTraceError("observation must be a mapping")
    if not isinstance(rationale, str):
        raise SearchTraceError("rationale must be a string")
    normalized_observation = _normalize_json(observation, path="observation")
    operation_payload = _serialize_operation(operation)
    result_payload = _serialize_result(result)
    _validate_operation_result(operation_payload, result_payload)

    # Make the operation and supplied result one atomic, reproducible fact.
    actual = _apply_operation(
        memory_before,
        operation,
        evaluator=_persisted_evaluator(result_payload),
    )
    if _serialize_result(actual) != result_payload:
        raise SearchTraceError("result does not match operation applied to memory_before")

    record = {
        "index": len(segment._record_payloads),
        "observation": normalized_observation,
        "rationale": rationale,
        "operation": operation_payload,
        "result": result_payload,
    }
    candidate = SearchTraceSegment(
        schema_version=segment.schema_version,
        authority_id=segment.authority_id,
        _record_payloads=(*segment._record_payloads, _canonical_bytes(record)),
        _tail_memory=result.memory.to_bytes(),
    )
    if enforce_size and len(candidate.to_bytes()) > limits.max_bytes:
        raise SearchTraceError("trace exceeds max_bytes")
    return candidate


def append_search_trace_record(
    segment: SearchTraceSegment,
    *,
    memory_before: SearchMemory,
    observation: Mapping[str, Any],
    rationale: str,
    operation: SearchOperation,
    result: SearchTransitionResult,
    limits: TraceSegmentLimits,
) -> SearchTraceSegment:
    return _append_search_trace_record(
        segment,
        memory_before=memory_before,
        observation=observation,
        rationale=rationale,
        operation=operation,
        result=result,
        limits=limits,
        validate_existing=True,
        enforce_size=True,
    )


def append_trusted_search_trace_record(
    segment: SearchTraceSegment,
    *,
    memory_before: SearchMemory,
    observation: Mapping[str, Any],
    rationale: str,
    operation: SearchOperation,
    result: SearchTransitionResult,
    limits: TraceSegmentLimits,
) -> SearchTraceSegment:
    """Append runtime-produced operations; validate the complete trace once at the end."""
    if not isinstance(segment, SearchTraceSegment):
        raise SearchTraceError("segment must be a SearchTraceSegment")
    if len(segment._record_payloads) >= limits.max_records:
        raise SearchTraceError("trace exceeds max_records")
    if memory_before.authority.authority_id != segment.authority_id:
        raise SearchTraceError("memory authority does not match trace authority")
    if not isinstance(observation, Mapping) or not isinstance(rationale, str):
        raise SearchTraceError("runtime trace observation and rationale are malformed")
    operation_payload = _serialize_operation(operation)
    result_payload = _serialize_result(result)
    _validate_operation_result(operation_payload, result_payload)
    record = {
        "index": segment.record_count,
        "observation": _normalize_json(observation, path="observation"),
        "rationale": rationale,
        "operation": operation_payload,
        "result": result_payload,
    }
    return SearchTraceSegment(
        schema_version=segment.schema_version,
        authority_id=segment.authority_id,
        _record_payloads=(*segment._record_payloads, _canonical_bytes(record)),
        _tail_memory=b"runtime-trace-requires-final-replay",
    )


def verify_search_trace_segment(payload: bytes, *, limits: TraceSegmentLimits) -> bool:
    _validated_envelope(payload, limits=limits)
    return True


def replay_search_trace_segment(
    payload: bytes,
    *,
    authority: PDDLStateAuthority,
    limits: TraceSegmentLimits,
) -> SearchMemory:
    envelope = _validated_envelope(payload, limits=limits)
    if authority.authority_id != envelope["authority_id"]:
        raise SearchTraceError("trace authority does not match replay authority")

    memory = SearchMemory.initial(authority)
    for record in envelope["records"]:
        operation = _decode_operation(record["operation"])
        actual = _apply_operation(
            memory,
            operation,
            evaluator=_persisted_evaluator(record["result"]),
        )
        actual_payload = _serialize_result(actual)
        if actual_payload != record["result"]:
            raise SearchTraceError(f"replayed result differs at record {record['index']}")
        memory = actual.memory
    return memory


def _validated_envelope(payload: bytes, *, limits: TraceSegmentLimits | None) -> dict[str, Any]:
    if not isinstance(payload, bytes):
        raise SearchTraceError("trace payload must be bytes")
    if limits is not None and len(payload) > limits.max_bytes:
        raise SearchTraceError("trace exceeds max_bytes")
    envelope = _load_canonical_json(payload)
    _require_object(envelope, _ENVELOPE_FIELDS, "envelope")
    if envelope["schema_version"] != SCHEMA_VERSION or isinstance(envelope["schema_version"], bool):
        raise SearchTraceError("unsupported schema_version")
    _require_nonempty_string(envelope["authority_id"], "authority_id")
    records = envelope["records"]
    if not isinstance(records, list):
        raise SearchTraceError("records must be an array")
    record_count = envelope["record_count"]
    if isinstance(record_count, bool) or not isinstance(record_count, int) or record_count < 0:
        raise SearchTraceError("record_count must be a non-negative integer")
    if record_count != len(records):
        raise SearchTraceError("record_count does not match records")
    if limits is not None and record_count > limits.max_records:
        raise SearchTraceError("trace exceeds max_records")

    for index, record in enumerate(records):
        _validate_record(record, index=index)
    return envelope


def _validate_record(record: Any, *, index: int) -> None:
    _require_object(record, _RECORD_FIELDS, f"record {index}")
    if isinstance(record["index"], bool) or not isinstance(record["index"], int) or record["index"] != index:
        raise SearchTraceError(f"invalid index at record {index}")
    if not isinstance(record["observation"], dict):
        raise SearchTraceError(f"observation must be an object at record {index}")
    if not isinstance(record["rationale"], str):
        raise SearchTraceError(f"rationale must be a string at record {index}")
    _validate_operation(record["operation"], path=f"record {index} operation")
    _validate_result(record["result"], path=f"record {index} result")
    _validate_operation_result(record["operation"], record["result"])


def _serialize_operation(operation: SearchOperation) -> dict[str, Any]:
    if isinstance(operation, SearchRetireRequest):
        return {"operation_type": "retire_frontier", "state_id": operation.state_id}
    if not isinstance(operation, SearchTransitionRequest):
        raise SearchTraceError("operation must be a typed search operation")
    return {
        "source_state_id": operation.source_state_id,
        "action": _serialize_action(operation.action),
        "frontier_intent": {
            "retire_source": operation.frontier_intent.retire_source,
            "target_position": operation.frontier_intent.target_position,
        },
        "visit_target": operation.visit_target,
        "evaluate_target": operation.evaluate_target,
    }


def _decode_operation(payload: Any) -> SearchOperation:
    _validate_operation(payload, path="operation")
    if "operation_type" in payload:
        return SearchRetireRequest(state_id=payload["state_id"])
    return SearchTransitionRequest(
        source_state_id=payload["source_state_id"],
        action=GroundedAction(payload["action"]["name"], tuple(payload["action"]["args"])),
        frontier_intent=FrontierIntent(
            retire_source=payload["frontier_intent"]["retire_source"],
            target_position=payload["frontier_intent"]["target_position"],
        ),
        visit_target=payload["visit_target"],
        evaluate_target=payload["evaluate_target"],
    )


def _validate_operation(payload: Any, *, path: str) -> None:
    if isinstance(payload, dict) and "operation_type" in payload:
        _require_object(payload, _RETIRE_OPERATION_FIELDS, path)
        if payload["operation_type"] != "retire_frontier":
            raise SearchTraceError(f"{path}.operation_type is invalid")
        _require_nonempty_string(payload["state_id"], f"{path}.state_id")
        return
    _require_object(payload, _OPERATION_FIELDS, path)
    _require_nonempty_string(payload["source_state_id"], f"{path}.source_state_id")
    _validate_action(payload["action"], path=f"{path}.action")
    intent = payload["frontier_intent"]
    _require_object(intent, {"retire_source", "target_position"}, f"{path}.frontier_intent")
    if not isinstance(intent["retire_source"], bool):
        raise SearchTraceError(f"{path}.frontier_intent.retire_source must be boolean")
    position = intent["target_position"]
    if isinstance(position, bool) or not isinstance(position, int) or position < 0:
        raise SearchTraceError(f"{path}.frontier_intent.target_position must be a non-negative integer")
    for field in ("visit_target", "evaluate_target"):
        if not isinstance(payload[field], bool):
            raise SearchTraceError(f"{path}.{field} must be boolean")


def _validate_operation_result(operation: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    if "operation_type" in operation:
        if result["status"] != "retired" or result["state_id"] != operation["state_id"]:
            raise SearchTraceError("retirement result does not match operation")
        return
    if result["status"] != "accepted":
        return
    has_evaluation = result["evaluation"] is not None
    if has_evaluation != operation["evaluate_target"]:
        raise SearchTraceError("accepted result evaluation does not match evaluate_target")


def _serialize_result(result: SearchTransitionResult) -> dict[str, Any]:
    if isinstance(result, AcceptedTransition):
        return {
            "status": "accepted",
            "transition": _serialize_transition(result.transition),
            "evaluation": _serialize_evaluation(result.evaluation),
        }
    if isinstance(result, AcceptedRetirement):
        return {
            "status": "retired",
            "state_id": result.state_id,
        }
    if isinstance(result, RejectedTransition):
        return {
            "status": "rejected",
            "budget_charge": result.budget_charge,
            "reason": result.reason,
        }
    raise SearchTraceError("result must be a SearchTransitionResult")


def _validate_result(payload: Any, *, path: str) -> None:
    if not isinstance(payload, dict):
        raise SearchTraceError(f"{path} must be an object")
    status = payload.get("status")
    if status == "accepted":
        _require_object(payload, {"status", "transition", "evaluation"}, path)
        _validate_transition(payload["transition"], path=f"{path}.transition")
        evaluation = payload["evaluation"]
        if evaluation is not None:
            _validate_evaluation(evaluation, path=f"{path}.evaluation")
    elif status == "retired":
        _require_object(payload, {"status", "state_id"}, path)
        _require_nonempty_string(payload["state_id"], f"{path}.state_id")
    elif status == "rejected":
        _require_object(payload, {"status", "budget_charge", "reason"}, path)
        charge = payload["budget_charge"]
        if isinstance(charge, bool) or not isinstance(charge, int) or charge < 0:
            raise SearchTraceError(f"{path}.budget_charge must be a non-negative integer")
        if not isinstance(payload["reason"], str):
            raise SearchTraceError(f"{path}.reason must be a string")
    else:
        raise SearchTraceError(f"{path}.status is invalid")


def _serialize_transition(transition: PDDLTransition) -> dict[str, Any]:
    if not isinstance(transition, PDDLTransition):
        raise SearchTraceError("accepted result must carry its PDDLTransition")
    return {
        "source_state": _serialize_state(transition.source_state),
        "action": _serialize_action(transition.action),
        "target_state": _serialize_state(transition.target_state),
        "provenance": transition.provenance.to_dict(),
    }


def _validate_transition(payload: Any, *, path: str) -> None:
    _require_object(payload, {"source_state", "action", "target_state", "provenance"}, path)
    _validate_state(payload["source_state"], path=f"{path}.source_state")
    _validate_action(payload["action"], path=f"{path}.action")
    _validate_state(payload["target_state"], path=f"{path}.target_state")
    provenance = payload["provenance"]
    _require_object(
        provenance,
        {"action", "authority_id", "provenance_id", "source_state_id", "target_state_id"},
        f"{path}.provenance",
    )
    _validate_action(provenance["action"], path=f"{path}.provenance.action")
    for field in ("authority_id", "source_state_id", "target_state_id"):
        _require_nonempty_string(provenance[field], f"{path}.provenance.{field}")
    _require_nonempty_string(provenance["provenance_id"], f"{path}.provenance.provenance_id")


def _serialize_state(state: CanonicalState) -> dict[str, Any]:
    return {
        "atoms": list(state.atoms),
        "authority_id": state.authority_id,
        "fluents": list(state.fluents),
        "state_id": state.state_id,
    }


def _validate_state(payload: Any, *, path: str) -> None:
    _require_object(payload, {"atoms", "authority_id", "fluents", "state_id"}, path)
    for field in ("atoms", "fluents"):
        values = payload[field]
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            raise SearchTraceError(f"{path}.{field} must be an array of strings")
    _require_nonempty_string(payload["authority_id"], f"{path}.authority_id")
    _require_nonempty_string(payload["state_id"], f"{path}.state_id")


def _serialize_action(action: GroundedAction) -> dict[str, Any]:
    return {"name": action.name, "args": list(action.args)}


def _validate_action(payload: Any, *, path: str) -> None:
    _require_object(payload, {"name", "args"}, path)
    _require_nonempty_string(payload["name"], f"{path}.name")
    if not isinstance(payload["args"], list) or any(not isinstance(item, str) for item in payload["args"]):
        raise SearchTraceError(f"{path}.args must be an array of strings")


def _serialize_evaluation(evaluation: StateEvaluation | None) -> dict[str, Any] | None:
    if evaluation is None:
        return None
    return {
        "novelty": evaluation.novelty,
        "heuristic": {"name": evaluation.heuristic.name, "value": evaluation.heuristic.value},
    }


def _decode_evaluation(payload: Any) -> StateEvaluation:
    _validate_evaluation(payload, path="result.evaluation")
    return StateEvaluation(
        novelty=payload["novelty"],
        heuristic=HeuristicValue(
            name=payload["heuristic"]["name"],
            value=payload["heuristic"]["value"],
        ),
    )


def _persisted_evaluator(result: Mapping[str, Any]):
    def evaluator(state: CanonicalState) -> StateEvaluation:
        if result["status"] != "accepted" or result["evaluation"] is None:
            raise SearchTraceError("transition requested an evaluation not present in its result")
        target_state_id = result["transition"]["target_state"]["state_id"]
        if state.state_id != target_state_id:
            raise SearchTraceError("persisted evaluation belongs to a different target state")
        return _decode_evaluation(result["evaluation"])

    return evaluator


def _apply_operation(
    memory: SearchMemory,
    operation: SearchOperation,
    *,
    evaluator,
) -> SearchTransitionResult:
    if isinstance(operation, SearchRetireRequest):
        return apply_search_retirement(memory, operation)
    return apply_search_transition(memory, operation, evaluator=evaluator)


def _validate_evaluation(payload: Any, *, path: str) -> None:
    _require_object(payload, {"novelty", "heuristic"}, path)
    novelty = payload["novelty"]
    if isinstance(novelty, bool) or not isinstance(novelty, int) or novelty < 0:
        raise SearchTraceError(f"{path}.novelty must be a non-negative integer")
    heuristic = payload["heuristic"]
    _require_object(heuristic, {"name", "value"}, f"{path}.heuristic")
    _require_nonempty_string(heuristic["name"], f"{path}.heuristic.name")
    if isinstance(heuristic["value"], bool) or not isinstance(heuristic["value"], int):
        raise SearchTraceError(f"{path}.heuristic.value must be an integer")


def _normalize_json(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SearchTraceError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SearchTraceError(f"{path} contains a non-string object key")
            normalized[key] = _normalize_json(item, path=f"{path}.{key}")
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    raise SearchTraceError(f"{path} contains a non-JSON-compatible value")


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SearchTraceError("value is not canonical JSON-compatible") from error


def _load_canonical_json(payload: bytes) -> Any:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SearchTraceError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise SearchTraceError(f"invalid JSON number: {value}")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except SearchTraceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SearchTraceError("trace payload is not valid UTF-8 JSON") from error
    if _canonical_bytes(value) != payload:
        raise SearchTraceError("trace payload is not in canonical JSON form")
    return value


def _require_object(value: Any, fields: set[str], path: str) -> None:
    if not isinstance(value, dict):
        raise SearchTraceError(f"{path} must be an object")
    actual = set(value)
    if actual != fields:
        missing = sorted(fields - actual)
        unknown = sorted(actual - fields)
        raise SearchTraceError(f"invalid fields in {path}: missing={missing}, unknown={unknown}")


def _require_nonempty_string(value: Any, path: str) -> None:
    if not isinstance(value, str) or not value:
        raise SearchTraceError(f"{path} must be a non-empty string")
