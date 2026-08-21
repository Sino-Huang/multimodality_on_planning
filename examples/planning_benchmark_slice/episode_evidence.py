from __future__ import annotations

import gzip
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn

from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    RunReceipt,
    StopOutcome,
    evaluate_execution_permission,
)

from .pddl_state import CanonicalState, GroundedAction, PDDLStateAuthority
from .search_memory import (
    AcceptedRetirement,
    AcceptedTransition,
    FrontierIntent,
    MutableBFSMemory,
    SearchMemory,
    SearchRetireRequest,
    SearchTransitionRequest,
    StateEvaluation,
    apply_search_retirement,
    apply_search_transition,
)
from .search_trace import (
    TraceSegmentLimits,
    append_trusted_search_trace_record,
    start_search_trace,
    verify_search_trace_segment,
)

EVIDENCE_SCHEMA_VERSION = "search_episode_evidence_v4"
CODEC_VERSION = "canonical_json_gzip_v4"
TASK_SCHEMA_VERSION = "search_episode_task_v1"
REQUEST_SCHEMA_VERSION = "search_episode_request_v1"

_EVIDENCE_FIELDS = {"events", "header", "result", "schema_version", "states"}
_HEADER_FIELDS = {
    "authorization_receipt",
    "authority_id",
    "frozen_binding",
    "gate_receipt",
    "request",
    "task",
}
_STATE_FIELDS = {"atoms", "authority_id", "fluents"}
_EVENT_FIELDS = {
    "expanded_state_id",
    "expansion_index",
    "index",
    "newly_enqueued_state_ids",
    "operation",
    "rationale",
}


class EpisodeEvidenceError(ValueError):
    """Raised when persisted episode evidence is malformed or inconsistent."""


def episode_result_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: result[field]
        for field in ("completion", "expansion_count", "goal_reached", "outcome", "scientific_completion")
    }


def serialize_state(state: CanonicalState) -> dict[str, Any]:
    return {
        "atoms": list(state.atoms),
        "authority_id": state.authority_id,
        "fluents": list(state.fluents),
    }


def serialize_operation(operation: SearchTransitionRequest | SearchRetireRequest) -> dict[str, Any]:
    if isinstance(operation, SearchRetireRequest):
        return {"operation_type": "retire_frontier", "state_id": operation.state_id}
    if not isinstance(operation, SearchTransitionRequest):
        raise EpisodeEvidenceError("operation must be a typed search operation")
    return {
        "action": {"args": list(operation.action.args), "name": operation.action.name},
        "evaluate_target": operation.evaluate_target,
        "frontier_intent": {
            "retire_source": operation.frontier_intent.retire_source,
            "target_position": operation.frontier_intent.target_position,
        },
        "source_state_id": operation.source_state_id,
        "visit_target": operation.visit_target,
    }


def write_episode_evidence(path: str | Path, episode: Mapping[str, Any]) -> dict[str, Any]:
    """Atomically write one canonical, deterministic gzip episode."""

    target = Path(path)
    evidence = _episode_evidence(episode)
    _validate_evidence(evidence)
    payload = _canonical_bytes({"evidence": evidence, "result": evidence["result"]}) + b"\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=9, mtime=0) as compressed:
                compressed.write(payload)
            raw.flush()
            os.fsync(raw.fileno())
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return episode_evidence_manifest(target, episode={"evidence": evidence, "result": evidence["result"]})


def read_episode_evidence(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        with gzip.open(source, "rb") as compressed:
            payload = compressed.read()
    except (EOFError, gzip.BadGzipFile, OSError) as error:
        raise EpisodeEvidenceError("episode evidence is not a complete valid gzip stream") from error
    if not payload.endswith(b"\n"):
        raise EpisodeEvidenceError("episode evidence is not newline terminated")
    episode = _load_canonical_json(payload[:-1], "episode evidence")
    if not isinstance(episode, dict) or set(episode) != {"evidence", "result"}:
        raise EpisodeEvidenceError("episode evidence has invalid fields")
    evidence = _episode_evidence(episode)
    _validate_evidence(evidence)
    return {"evidence": evidence, "result": evidence["result"]}


def episode_evidence_manifest(
    path: str | Path,
    *,
    episode: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source = Path(path)
    loaded = read_episode_evidence(source) if episode is None else dict(episode)
    evidence = _episode_evidence(loaded)
    return {
        "codec_version": CODEC_VERSION,
        "schema_version": evidence["schema_version"],
        "stored_size_bytes": source.stat().st_size,
    }


def verify_episode_evidence(path: str | Path) -> dict[str, Any]:
    episode = read_episode_evidence(path)
    replay_episode(episode["evidence"])
    return {
        "header": episode["evidence"]["header"],
        "manifest": episode_evidence_manifest(path, episode=episode),
        "result": episode["result"],
    }


def verify_manifested_episode(
    path: str | Path,
    manifest: Mapping[str, Any],
    expected_result: Mapping[str, Any],
) -> dict[str, Any]:
    verified = verify_episode_evidence(path)
    actual_manifest = {"path": manifest.get("path"), **verified["manifest"]}
    if dict(manifest) != actual_manifest or dict(expected_result) != episode_result_summary(verified["result"]):
        raise EpisodeEvidenceError(f"episode artifact differs from its manifest: {path}")
    return verified


def replay_episode_evidence(path: str | Path) -> dict[str, Any]:
    episode = read_episode_evidence(path)
    replay_episode(episode["evidence"])
    return episode


def read_episode_artifacts(path: str | Path) -> tuple[dict[str, Any], bytes, bytes]:
    episode = replay_episode_evidence(path)
    task, trace = materialize_episode_artifacts(episode["evidence"])
    return episode, task, trace


def materialize_episode_artifacts(evidence: Mapping[str, Any]) -> tuple[bytes, bytes]:
    """Materialize canonical task and training-trace views from episode evidence."""

    normalized = dict(evidence)
    replay_episode(normalized)
    header = normalized["header"]
    request = _parse_request(header["request"])
    authority = _authority_from_task(header["task"])
    memory = SearchMemory.initial(authority)
    limits = _trace_limits(authority, request["max_expansions"])
    trace = start_search_trace(memory, limits=limits)
    for event in normalized["events"]:
        state = memory.state(event["expanded_state_id"])
        operation = _decode_operation(event["operation"])
        if isinstance(operation, SearchRetireRequest):
            applied = apply_search_retirement(memory, operation)
            if not isinstance(applied, AcceptedRetirement):
                raise EpisodeEvidenceError(f"persisted retirement was rejected at event {event['index']}")
        else:
            applied = apply_search_transition(memory, operation, evaluator=_unexpected_evaluator)
            if not isinstance(applied, AcceptedTransition):
                raise EpisodeEvidenceError(f"persisted transition was rejected at event {event['index']}")
        trace = append_trusted_search_trace_record(
            trace,
            memory_before=memory,
            observation=_text_observation(state, memory),
            rationale=event["rationale"],
            operation=operation,
            result=applied,
            limits=limits,
        )
        memory = applied.memory
    trace_bytes = trace.to_bytes()
    verify_search_trace_segment(trace_bytes, limits=limits)
    return _canonical_bytes(header["task"]), trace_bytes


def replay_episode(evidence: Mapping[str, Any]) -> SearchMemory:
    normalized = dict(evidence)
    _validate_evidence(normalized)
    header = normalized["header"]
    gate = _gate_from_payload(header["gate_receipt"])
    authorization = _authorization_from_payload(header["authorization_receipt"])
    permission = evaluate_execution_permission(
        binding=gate.binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )
    if not permission.start_permitted:
        raise EpisodeEvidenceError("evidence receipts do not authorize replay")

    request = _parse_request(header["request"])
    authority = _authority_from_task(header["task"])
    if header["authority_id"] != authority.authority_id:
        raise EpisodeEvidenceError("evidence authority differs from its task")
    memory = _replay_events(
        normalized["states"],
        normalized["events"],
        authority=authority,
    )
    _validate_replayed_result(
        normalized["result"],
        memory=memory,
        expansion_count=_expansion_count(normalized["events"]),
        authority=authority,
        gate=gate,
        request=request,
        states=normalized["states"],
    )
    return memory


def _replay_events(
    states: Mapping[str, Any],
    events: list[Mapping[str, Any]],
    *,
    authority: PDDLStateAuthority,
) -> SearchMemory:
    memory = MutableBFSMemory(authority)
    if states.get(authority.initial_state.state_id) != serialize_state(authority.initial_state):
        raise EpisodeEvidenceError("state table does not contain the canonical initial state")

    current_expansion = -1
    expanded_state_id = ""
    frontier_tail: tuple[str, ...] = ()
    enqueued_state_ids: list[str] = []
    operation_in_expansion = 0

    def finish_expansion() -> None:
        if current_expansion < 0:
            return
        if tuple(memory.frontier) != (*frontier_tail, *enqueued_state_ids):
            raise EpisodeEvidenceError(f"BFS FIFO invariant failed after expansion {current_expansion}")

    for index, event in enumerate(events):
        if event["index"] != index:
            raise EpisodeEvidenceError(f"event index differs at event {index}")
        event_expansion = event["expansion_index"]
        if event_expansion != current_expansion:
            finish_expansion()
            if event_expansion != current_expansion + 1:
                raise EpisodeEvidenceError(f"expansion index differs at event {index}")
            if not memory.frontier or event["expanded_state_id"] != memory.frontier[0]:
                raise EpisodeEvidenceError(f"expanded state is not the BFS frontier head at event {index}")
            current_expansion = event_expansion
            expanded_state_id = event["expanded_state_id"]
            frontier_tail = tuple(memory.frontier)[1:]
            enqueued_state_ids = []
            operation_in_expansion = 0
        elif event["expanded_state_id"] != expanded_state_id:
            raise EpisodeEvidenceError(f"expanded state changes within expansion {current_expansion}")

        operation = _decode_operation(event["operation"])
        newly_enqueued = event["newly_enqueued_state_ids"]
        if isinstance(operation, SearchRetireRequest):
            if operation_in_expansion != 0 or operation.state_id != expanded_state_id or newly_enqueued:
                raise EpisodeEvidenceError(f"retirement is not a complete empty expansion at event {index}")
            if memory.retire_frontier_head(expanded_state_id) != operation:
                raise EpisodeEvidenceError(f"persisted retirement differs at event {index}")
        else:
            first = operation_in_expansion == 0
            expected_position = len(memory.frontier) - (1 if first else 0)
            if (
                operation.source_state_id != expanded_state_id
                or operation.frontier_intent.retire_source is not first
                or operation.frontier_intent.target_position != expected_position
                or not operation.visit_target
                or operation.evaluate_target
            ):
                raise EpisodeEvidenceError(f"BFS operation invariant failed at event {index}")
            applied = memory.apply_generated_action(expanded_state_id, operation.action, retire_source=first)
            if applied is None:
                raise EpisodeEvidenceError(f"persisted transition revisits a state at event {index}")
            generated, transition = applied
            target = transition.target_state
            if generated != operation or newly_enqueued != [target.state_id]:
                raise EpisodeEvidenceError(f"event target delta differs at event {index}")
            if states.get(target.state_id) != serialize_state(target):
                raise EpisodeEvidenceError(f"state table differs from replayed target at event {index}")
            enqueued_state_ids.append(target.state_id)
        operation_in_expansion += 1
    finish_expansion()
    return memory.freeze()


def _expansion_count(events: list[Mapping[str, Any]]) -> int:
    return 0 if not events else events[-1]["expansion_index"] + 1


def _validate_replayed_result(
    result: Mapping[str, Any],
    *,
    memory: SearchMemory,
    expansion_count: int,
    authority: PDDLStateAuthority,
    gate: GateReceipt,
    request: Mapping[str, Any],
    states: Mapping[str, Any],
) -> None:
    completed = _run_receipt_from_payload(result.get("run_receipt"))
    if (
        completed.binding != gate.binding
        or completed.outcome is not StopOutcome.PASS
        or completed.run_state != "completed"
        or not completed.scientific_completion
    ):
        raise EpisodeEvidenceError("completed run receipt is invalid")
    goal_reached = bool(memory.frontier and authority.is_goal(memory.state(memory.frontier[0])))
    if (
        result.get("completion") != "completed"
        or result.get("expansion_count") != expansion_count
        or result.get("goal_reached") is not goal_reached
        or result.get("outcome") != StopOutcome.PASS.value
        or result.get("scientific_completion") is not True
    ):
        raise EpisodeEvidenceError("result summary differs from replay")
    if set(states) != memory.visited:
        raise EpisodeEvidenceError("state table does not equal the replayed visited set")
    if expansion_count > request["max_expansions"]:
        raise EpisodeEvidenceError("replayed episode exceeds its expansion budget")


def _episode_evidence(episode: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(episode, Mapping) or set(episode) != {"evidence", "result"}:
        raise EpisodeEvidenceError("episode must contain evidence and result")
    evidence = episode["evidence"]
    if not isinstance(evidence, Mapping) or episode["result"] != evidence.get("result"):
        raise EpisodeEvidenceError("episode result differs from evidence")
    return dict(evidence)


def _validate_evidence(evidence: Mapping[str, Any]) -> None:
    _require_object(evidence, _EVIDENCE_FIELDS, "evidence")
    if evidence["schema_version"] != EVIDENCE_SCHEMA_VERSION:
        raise EpisodeEvidenceError("unsupported evidence schema")
    _require_object(evidence["header"], _HEADER_FIELDS, "header")
    _require_text(evidence["header"]["authority_id"], "header.authority_id")
    frozen_binding = evidence["header"]["frozen_binding"]
    if frozen_binding is not None and not isinstance(frozen_binding, dict):
        raise EpisodeEvidenceError("header.frozen_binding must be an object or null")
    _validate_states(evidence["states"])
    if not isinstance(evidence["events"], list):
        raise EpisodeEvidenceError("events must be an array")
    for index, event in enumerate(evidence["events"]):
        _validate_event(event, index=index)
    if not isinstance(evidence["result"], dict):
        raise EpisodeEvidenceError("result must be an object")


def _validate_states(states: Any) -> None:
    if not isinstance(states, dict) or not states:
        raise EpisodeEvidenceError("states must be a non-empty state table")
    for state_id, state in states.items():
        _require_text(state_id, "state_id")
        _require_object(state, _STATE_FIELDS, f"state {state_id}")
        _require_text(state["authority_id"], f"state {state_id}.authority_id")
        for field in ("atoms", "fluents"):
            if not isinstance(state[field], list) or any(not isinstance(item, str) for item in state[field]):
                raise EpisodeEvidenceError(f"state {state_id}.{field} must be an array of strings")
        canonical = CanonicalState(tuple(state["atoms"]), state["authority_id"], tuple(state["fluents"]))
        if canonical.state_id != state_id or serialize_state(canonical) != state:
            raise EpisodeEvidenceError(f"state table entry is not canonical: {state_id}")


def _validate_event(event: Any, *, index: int) -> None:
    _require_object(event, _EVENT_FIELDS, f"event {index}")
    for field in ("index", "expansion_index"):
        if isinstance(event[field], bool) or not isinstance(event[field], int) or event[field] < 0:
            raise EpisodeEvidenceError(f"event {index}.{field} must be a non-negative integer")
    _require_text(event["expanded_state_id"], f"event {index}.expanded_state_id")
    if not isinstance(event["newly_enqueued_state_ids"], list):
        raise EpisodeEvidenceError(f"event {index}.newly_enqueued_state_ids must be an array")
    for state_id in event["newly_enqueued_state_ids"]:
        _require_text(state_id, f"event {index}.newly_enqueued_state_ids")
    if not isinstance(event["rationale"], str):
        raise EpisodeEvidenceError(f"event {index}.rationale must be text")
    _decode_operation(event["operation"])


def _decode_operation(payload: Any) -> SearchTransitionRequest | SearchRetireRequest:
    if not isinstance(payload, dict):
        raise EpisodeEvidenceError("operation must be an object")
    if "operation_type" in payload:
        _require_object(payload, {"operation_type", "state_id"}, "retirement operation")
        if payload["operation_type"] != "retire_frontier":
            raise EpisodeEvidenceError("retirement operation type is invalid")
        _require_text(payload["state_id"], "retirement state_id")
        return SearchRetireRequest(payload["state_id"])
    _require_object(
        payload,
        {"action", "evaluate_target", "frontier_intent", "source_state_id", "visit_target"},
        "transition operation",
    )
    action = payload["action"]
    _require_object(action, {"args", "name"}, "operation action")
    _require_text(action["name"], "operation action name")
    if not isinstance(action["args"], list) or any(not isinstance(item, str) for item in action["args"]):
        raise EpisodeEvidenceError("operation action args must be an array of strings")
    intent = payload["frontier_intent"]
    _require_object(intent, {"retire_source", "target_position"}, "operation frontier_intent")
    position = intent["target_position"]
    if not isinstance(intent["retire_source"], bool):
        raise EpisodeEvidenceError("operation retire_source must be boolean")
    if isinstance(position, bool) or not isinstance(position, int) or position < 0:
        raise EpisodeEvidenceError("operation target_position must be non-negative")
    _require_text(payload["source_state_id"], "operation source_state_id")
    if not isinstance(payload["visit_target"], bool) or not isinstance(payload["evaluate_target"], bool):
        raise EpisodeEvidenceError("operation visit/evaluate fields must be boolean")
    return SearchTransitionRequest(
        source_state_id=payload["source_state_id"],
        action=GroundedAction(action["name"], tuple(action["args"])),
        frontier_intent=FrontierIntent(intent["retire_source"], position),
        visit_target=payload["visit_target"],
        evaluate_target=payload["evaluate_target"],
    )


def _parse_request(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise EpisodeEvidenceError("request must be an object")
    fields = {"algorithm", "max_expansions", "modality", "policy", "schema_version"}
    if payload.get("policy") == "random":
        fields.add("random_seed")
    _require_object(payload, fields, "request")
    if payload["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise EpisodeEvidenceError("request schema is invalid")
    if payload["algorithm"] != "bfs" or payload["modality"] != "text-state":
        raise EpisodeEvidenceError("request algorithm or modality is unsupported")
    if payload["policy"] not in {"exact", "random"}:
        raise EpisodeEvidenceError("request policy is unsupported")
    budget = payload["max_expansions"]
    if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
        raise EpisodeEvidenceError("request expansion budget is invalid")
    if payload["policy"] == "random" and (
        isinstance(payload["random_seed"], bool) or not isinstance(payload["random_seed"], int)
    ):
        raise EpisodeEvidenceError("request random seed is invalid")
    return dict(payload)


def _authority_from_task(task: Any) -> PDDLStateAuthority:
    _require_object(task, {"domain_pddl", "instance_id", "problem_pddl", "schema_version"}, "task")
    if task["schema_version"] != TASK_SCHEMA_VERSION:
        raise EpisodeEvidenceError("task schema is invalid")
    if any(not isinstance(task[field], str) for field in ("domain_pddl", "instance_id", "problem_pddl")):
        raise EpisodeEvidenceError("task fields must be text")
    return PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])


def _binding_from_payload(payload: Any) -> ReceiptBinding:
    _require_object(payload, {"attempt_id", "contract_id", "output_root"}, "receipt binding")
    try:
        return ReceiptBinding(payload["contract_id"], payload["attempt_id"], payload["output_root"])
    except (TypeError, ValueError) as error:
        raise EpisodeEvidenceError("receipt binding is malformed") from error


def _gate_from_payload(payload: Any) -> GateReceipt:
    try:
        receipt = GateReceipt(
            binding=_binding_from_payload(payload["binding"]),
            outcome=payload["outcome"],
            ancestor_receipt_id=payload["ancestor_receipt_id"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise EpisodeEvidenceError("gate receipt is malformed") from error
    if receipt.to_dict() != payload:
        raise EpisodeEvidenceError("gate receipt has noncanonical fields")
    return receipt


def _authorization_from_payload(payload: Any) -> AuthorizationReceipt:
    try:
        receipt = AuthorizationReceipt(
            binding=_binding_from_payload(payload["binding"]),
            gate_receipt_id=payload["gate_receipt_id"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise EpisodeEvidenceError("authorization receipt is malformed") from error
    if receipt.to_dict() != payload:
        raise EpisodeEvidenceError("authorization receipt has noncanonical fields")
    return receipt


def _run_receipt_from_payload(payload: Any) -> RunReceipt:
    try:
        receipt = RunReceipt(
            binding=_binding_from_payload(payload["binding"]),
            outcome=payload["outcome"],
            run_state=payload["run_state"],
            start_permitted=payload["start_permitted"],
            scientific_completion=payload["scientific_completion"],
            gate_receipt_id=payload["gate_receipt_id"],
            authorization_receipt_id=payload["authorization_receipt_id"],
            ancestor_receipt_id=payload["ancestor_receipt_id"],
            reason=payload["reason"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise EpisodeEvidenceError("run receipt is malformed") from error
    if receipt.to_dict() != payload:
        raise EpisodeEvidenceError("run receipt has noncanonical fields")
    return receipt


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise EpisodeEvidenceError("value is not canonical JSON-compatible") from error


def _load_canonical_json(payload: bytes, label: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise EpisodeEvidenceError(f"duplicate field in {label}: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise EpisodeEvidenceError(f"invalid number in {label}: {value}")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except EpisodeEvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EpisodeEvidenceError(f"{label} is not valid UTF-8 JSON") from error
    if _canonical_bytes(value) != payload:
        raise EpisodeEvidenceError(f"{label} is not canonical JSON")
    return value


def _require_object(value: Any, fields: set[str], path: str) -> None:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise EpisodeEvidenceError(f"{path} has invalid fields")


def _require_text(value: Any, path: str) -> None:
    if not isinstance(value, str) or not value:
        raise EpisodeEvidenceError(f"{path} must be non-empty text")


def _trace_limits(authority: PDDLStateAuthority, max_expansions: int) -> TraceSegmentLimits:
    arity_bound = max(1, len(authority.objects) ** 2)
    max_records = max_expansions * max(1, len(authority.action_vocabulary) * arity_bound)
    return TraceSegmentLimits(max_records=max_records, max_bytes=max(1_000_000, max_records * 16_384))


def _text_observation(state: CanonicalState, memory: SearchMemory) -> dict[str, Any]:
    return {
        "frontier": list(memory.frontier),
        "goal_atoms": list(memory.authority.goal_atoms or ()),
        "modality": "text-state",
        "state_atoms": list(state.atoms),
        "state_id": state.state_id,
    }


def _unexpected_evaluator(_state: CanonicalState) -> StateEvaluation:
    raise AssertionError("BFS transitions do not request state evaluation")


__all__ = [
    "CODEC_VERSION",
    "EVIDENCE_SCHEMA_VERSION",
    "EpisodeEvidenceError",
    "episode_evidence_manifest",
    "episode_result_summary",
    "materialize_episode_artifacts",
    "read_episode_artifacts",
    "read_episode_evidence",
    "replay_episode",
    "replay_episode_evidence",
    "serialize_operation",
    "serialize_state",
    "verify_episode_evidence",
    "verify_manifested_episode",
    "write_episode_evidence",
]
