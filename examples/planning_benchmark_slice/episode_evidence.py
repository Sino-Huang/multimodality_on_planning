"""Versioned, deterministic persistence and replay for governed BFS episodes."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import tempfile
import zlib
from collections.abc import Iterator, Mapping
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
from src.data_collect.replay import parse_canonical_bundle

from .pddl_state import CanonicalState, GroundedAction, PDDLStateAuthority
from .search_memory import (
    AcceptedRetirement,
    AcceptedTransition,
    FrontierIntent,
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

EVIDENCE_SCHEMA_VERSION = "search_episode_evidence_v2"
CODEC_VERSION = "canonical_jsonl_gzip_v2"
TASK_SCHEMA_VERSION = "search_episode_task_v1"
REQUEST_SCHEMA_VERSION = "search_episode_request_v1"

_EVIDENCE_FIELDS = {"events", "header", "result", "schema_version", "states"}
_HEADER_FIELDS = {
    "authorization_receipt",
    "authority_id",
    "gate_receipt",
    "initial_memory_sha256",
    "request",
    "task",
}
_EVENT_FIELDS = {
    "expanded_state_id",
    "expansion_index",
    "index",
    "memory_sha256",
    "newly_enqueued_state_ids",
    "operation",
    "rationale",
}
_STATE_FIELDS = {"atoms", "authority_id", "fluents"}


class EpisodeEvidenceError(ValueError):
    """Raised when persisted episode evidence is malformed or inconsistent."""


def serialize_state(state: CanonicalState) -> dict[str, Any]:
    """Return the state-table value for one canonical state."""

    return {
        "atoms": list(state.atoms),
        "authority_id": state.authority_id,
        "fluents": list(state.fluents),
    }


def serialize_operation(operation: SearchTransitionRequest | SearchRetireRequest) -> dict[str, Any]:
    """Return the canonical logical payload for one typed search operation."""

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


def memory_sha256(memory: SearchMemory) -> str:
    return hashlib.sha256(memory.to_bytes()).hexdigest()


def write_episode_evidence(path: str | Path, episode: Mapping[str, Any]) -> dict[str, Any]:
    """Atomically write one v2 episode as deterministic canonical JSONL gzip."""

    target = Path(path)
    if target.exists():
        raise FileExistsError(f"episode evidence already exists: {target}")
    evidence = _episode_evidence(episode)
    _validate_evidence(evidence)
    logical_digest = hashlib.sha256()
    for line in _logical_lines(evidence):
        logical_digest.update(line)
    logical_sha256 = logical_digest.hexdigest()
    digest_line = _canonical_line({"logical_sha256": logical_sha256, "record_type": "digest"})

    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=raw, mtime=0) as compressed:
                for line in _logical_lines(evidence):
                    compressed.write(line)
                compressed.write(digest_line)
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "codec_version": CODEC_VERSION,
        "logical_sha256": logical_sha256,
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "stored_size_bytes": target.stat().st_size,
    }


def read_episode_evidence(path: str | Path) -> dict[str, Any]:
    """Read and authenticate a v2 artifact without depending on its physical layout."""

    source = Path(path)
    digest = hashlib.sha256()
    header: dict[str, Any] | None = None
    states: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    result: dict[str, Any] | None = None
    expected_digest: str | None = None
    phase = "header"
    try:
        with gzip.open(source, "rb") as compressed:
            for index, line in enumerate(compressed):
                record = _load_canonical_line(line, index=index)
                record_type = record.get("record_type") if isinstance(record, dict) else None
                if record_type == "digest":
                    if phase != "result" or set(record) != {"logical_sha256", "record_type"}:
                        raise EpisodeEvidenceError("digest record is misplaced or malformed")
                    _require_digest(record["logical_sha256"], "logical_sha256")
                    expected_digest = record["logical_sha256"]
                    phase = "digest"
                    continue
                if phase == "digest":
                    raise EpisodeEvidenceError("artifact contains records after its logical digest")
                digest.update(line)
                if record_type == "header":
                    if (
                        phase != "header"
                        or header is not None
                        or set(record) != {"header", "record_type", "schema_version"}
                    ):
                        raise EpisodeEvidenceError("header record is misplaced or malformed")
                    if record["schema_version"] != EVIDENCE_SCHEMA_VERSION or not isinstance(record["header"], dict):
                        raise EpisodeEvidenceError("unsupported evidence schema")
                    header = record["header"]
                    phase = "states"
                elif record_type == "state":
                    if phase not in {"states"} or set(record) != {"record_type", "state", "state_id"}:
                        raise EpisodeEvidenceError("state record is misplaced or malformed")
                    state_id = record["state_id"]
                    if state_id in states:
                        raise EpisodeEvidenceError(f"duplicate state table entry: {state_id}")
                    states[state_id] = record["state"]
                elif record_type == "event":
                    if phase not in {"states", "events"} or set(record) != {"event", "record_type"}:
                        raise EpisodeEvidenceError("event record is misplaced or malformed")
                    if not isinstance(record["event"], dict):
                        raise EpisodeEvidenceError("event payload must be an object")
                    events.append(record["event"])
                    phase = "events"
                elif record_type == "result":
                    if (
                        phase not in {"states", "events"}
                        or result is not None
                        or set(record) != {"record_type", "result"}
                    ):
                        raise EpisodeEvidenceError("result record is misplaced or malformed")
                    if not isinstance(record["result"], dict):
                        raise EpisodeEvidenceError("result payload must be an object")
                    result = record["result"]
                    phase = "result"
                else:
                    raise EpisodeEvidenceError(f"unknown record type at line {index + 1}")
    except EpisodeEvidenceError:
        raise
    except (EOFError, gzip.BadGzipFile, OSError, zlib.error) as error:
        raise EpisodeEvidenceError("episode evidence is not a complete valid gzip stream") from error

    if header is None or result is None or expected_digest is None:
        raise EpisodeEvidenceError("episode evidence is incomplete")
    actual_digest = digest.hexdigest()
    if actual_digest != expected_digest:
        raise EpisodeEvidenceError("logical evidence digest does not match its records")
    evidence = {
        "events": events,
        "header": header,
        "result": result,
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "states": states,
    }
    _validate_evidence(evidence)
    return {"evidence": evidence, "result": result}


def episode_evidence_manifest(
    path: str | Path,
    *,
    episode: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the compact manifest fields for one verified v2 artifact."""

    source = Path(path)
    episode = read_episode_evidence(source) if episode is None else dict(episode)
    evidence = _episode_evidence(episode)
    logical_digest = hashlib.sha256()
    for line in _logical_lines(evidence):
        logical_digest.update(line)
    return {
        "codec_version": CODEC_VERSION,
        "logical_sha256": logical_digest.hexdigest(),
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "stored_size_bytes": source.stat().st_size,
    }


def read_versioned_episode_evidence(
    path: str | Path,
    *,
    signing_key: bytes | str,
) -> dict[str, Any]:
    """Read and replay either retained v1 JSON or current v2 gzip evidence."""

    source = Path(path)
    with source.open("rb") as handle:
        is_gzip = handle.read(2) == b"\x1f\x8b"
    if is_gzip:
        return replay_episode_evidence(source, signing_key=signing_key)

    legacy_episode = _load_canonical_episode(source.read_bytes())
    if not isinstance(legacy_episode, dict) or set(legacy_episode) != {"evidence", "result"}:
        raise EpisodeEvidenceError("v1 episode artifact is malformed")
    legacy_evidence = legacy_episode["evidence"]
    if not isinstance(legacy_evidence, dict) or legacy_evidence.get("schema_version") != "search_episode_evidence_v1":
        raise EpisodeEvidenceError("episode artifact has an unsupported schema")
    from . import search_episode as search_harness

    if search_harness.replay_search_episode(legacy_evidence, signing_key=signing_key) != legacy_episode:
        raise EpisodeEvidenceError("v1 episode did not replay identically")
    return legacy_episode


def read_episode_artifacts(
    path: str | Path,
    *,
    signing_key: bytes | str,
) -> tuple[dict[str, Any], bytes, bytes]:
    """Read either evidence version and return its canonical task and training trace."""

    episode = read_versioned_episode_evidence(path, signing_key=signing_key)
    evidence = episode["evidence"]
    if evidence["schema_version"] == EVIDENCE_SCHEMA_VERSION:
        task, trace = materialize_episode_artifacts(evidence, signing_key=signing_key)
        return episode, task, trace
    bundle = base64.b64decode(evidence["bundle"].encode("ascii"), validate=True)
    artifacts = parse_canonical_bundle(bundle)
    return episode, artifacts["task.json"], artifacts["search-trace.json"]


def materialize_episode_artifacts(
    evidence: Mapping[str, Any],
    *,
    signing_key: bytes | str,
) -> tuple[bytes, bytes]:
    """Materialize canonical task and v1 training-trace views from compact v2 evidence."""

    normalized = dict(evidence)
    replay_episode(normalized, signing_key=signing_key)
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
            result = apply_search_retirement(memory, operation)
            if not isinstance(result, AcceptedRetirement):
                raise EpisodeEvidenceError(f"persisted retirement was rejected at event {event['index']}")
        else:
            result = apply_search_transition(memory, operation, evaluator=_unexpected_evaluator)
            if not isinstance(result, AcceptedTransition):
                raise EpisodeEvidenceError(f"persisted transition was rejected at event {event['index']}")
        trace = append_trusted_search_trace_record(
            trace,
            memory_before=memory,
            observation=_text_observation(state, memory),
            rationale=event["rationale"],
            operation=operation,
            result=result,
            limits=limits,
        )
        memory = result.memory
    trace_bytes = trace.to_bytes()
    verify_search_trace_segment(trace_bytes, limits=limits)
    return _canonical_bytes(header["task"]), trace_bytes


def migrate_v1_episode(
    source_path: str | Path,
    target_path: str | Path,
    *,
    signing_key: bytes | str,
) -> dict[str, Any]:
    """Verify one immutable v1 JSON episode and write its equivalent v2 artifact."""

    source = Path(source_path)
    target = Path(target_path)
    if source.resolve() == target.resolve():
        raise EpisodeEvidenceError("v1 migration target must differ from its source")
    source_bytes = source.read_bytes()
    source_sha256 = _sha256(source_bytes)
    legacy_episode = _load_canonical_episode(source_bytes)
    if not isinstance(legacy_episode, dict) or set(legacy_episode) != {"evidence", "result"}:
        raise EpisodeEvidenceError("v1 episode artifact is malformed")
    legacy_evidence = legacy_episode["evidence"]
    if not isinstance(legacy_evidence, dict) or legacy_evidence.get("schema_version") != "search_episode_evidence_v1":
        raise EpisodeEvidenceError("migration source is not v1 episode evidence")

    from . import search_episode as search_harness

    if search_harness.replay_search_episode(legacy_evidence, signing_key=signing_key) != legacy_episode:
        raise EpisodeEvidenceError("v1 episode did not replay identically")
    bundle = base64.b64decode(legacy_evidence["bundle"].encode("ascii"), validate=True)
    artifacts = parse_canonical_bundle(bundle)
    task = _load_canonical_payload(artifacts["task.json"], "v1 task")
    request = _parse_request(_load_canonical_payload(artifacts["request.json"], "v1 request"))
    gate = _gate_from_payload(_load_canonical_payload(artifacts["gate-receipt.json"], "v1 gate receipt"))
    authorization = _authorization_from_payload(
        _load_canonical_payload(artifacts["authorization-receipt.json"], "v1 authorization receipt")
    )
    migrated = search_harness._execute_authorized_episode(
        task=task,
        algorithm=request["algorithm"],
        modality=request["modality"],
        policy=request["policy"],
        random_seed=request.get("random_seed"),
        max_expansions=request["max_expansions"],
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=signing_key,
    )
    if migrated["result"] != legacy_episode["result"]:
        raise EpisodeEvidenceError("v1 and v2 scientific results differ")
    manifest = write_episode_evidence(target, migrated)
    if source.read_bytes() != source_bytes:
        raise EpisodeEvidenceError("v1 migration mutated its source artifact")
    return {"source_sha256": source_sha256, **manifest}


def replay_episode_evidence(path: str | Path, *, signing_key: bytes | str) -> dict[str, Any]:
    """Read, verify receipts, and mechanically replay one persisted v2 episode."""

    episode = read_episode_evidence(path)
    replay_episode(episode["evidence"], signing_key=signing_key)
    return episode


def replay_episode(evidence: Mapping[str, Any], *, signing_key: bytes | str) -> SearchMemory:
    """Verify and replay an in-memory v2 logical episode."""

    normalized = dict(evidence)
    _validate_evidence(normalized)
    header = normalized["header"]
    gate = _gate_from_payload(header["gate_receipt"])
    authorization = _authorization_from_payload(header["authorization_receipt"])
    permission = evaluate_execution_permission(
        binding=gate.binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=signing_key,
    )
    if not permission.start_permitted:
        raise EpisodeEvidenceError("evidence receipts do not authorize replay")

    request = _parse_request(header["request"])
    task = header["task"]
    authority = _authority_from_task(task)
    if header["authority_id"] != authority.authority_id:
        raise EpisodeEvidenceError("evidence authority differs from its task")
    memory = SearchMemory.initial(authority)
    if header["initial_memory_sha256"] != memory_sha256(memory):
        raise EpisodeEvidenceError("initial replay memory differs from evidence")

    states = normalized["states"]
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
        expected = (*frontier_tail, *enqueued_state_ids)
        if memory.frontier != expected:
            raise EpisodeEvidenceError(f"BFS FIFO invariant failed after expansion {current_expansion}")

    for index, event in enumerate(normalized["events"]):
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
            frontier_tail = memory.frontier[1:]
            enqueued_state_ids = []
            operation_in_expansion = 0
        elif event["expanded_state_id"] != expanded_state_id:
            raise EpisodeEvidenceError(f"expanded state changes within expansion {current_expansion}")

        operation = _decode_operation(event["operation"])
        newly_enqueued = event["newly_enqueued_state_ids"]
        if isinstance(operation, SearchRetireRequest):
            if operation_in_expansion != 0 or operation.state_id != expanded_state_id or newly_enqueued:
                raise EpisodeEvidenceError(f"retirement is not a complete empty expansion at event {index}")
            result = apply_search_retirement(memory, operation)
            if not isinstance(result, AcceptedRetirement):
                raise EpisodeEvidenceError(f"persisted retirement was rejected at event {index}")
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
            result = apply_search_transition(memory, operation, evaluator=_unexpected_evaluator)
            if not isinstance(result, AcceptedTransition):
                raise EpisodeEvidenceError(f"persisted transition was rejected at event {index}")
            target = result.transition.target_state
            if newly_enqueued != [target.state_id]:
                raise EpisodeEvidenceError(f"event target delta differs at event {index}")
            if states.get(target.state_id) != serialize_state(target):
                raise EpisodeEvidenceError(f"state table differs from replayed target at event {index}")
            enqueued_state_ids.append(target.state_id)
        memory = result.memory
        if event["memory_sha256"] != memory_sha256(memory):
            raise EpisodeEvidenceError(f"memory digest differs at event {index}")
        operation_in_expansion += 1
    finish_expansion()

    result_payload = normalized["result"]
    completed = _run_receipt_from_payload(result_payload.get("run_receipt"))
    if (
        completed.binding != gate.binding
        or completed.outcome is not StopOutcome.PASS
        or completed.run_state != "completed"
        or not completed.scientific_completion
        or not completed.verify_signature(signing_key)
    ):
        raise EpisodeEvidenceError("completed run receipt is invalid")
    goal_reached = bool(memory.frontier and authority.is_goal(memory.state(memory.frontier[0])))
    if (
        result_payload.get("completion") != "completed"
        or result_payload.get("expansion_count") != current_expansion + 1
        or result_payload.get("goal_reached") is not goal_reached
        or result_payload.get("outcome") != StopOutcome.PASS.value
        or result_payload.get("scientific_completion") is not True
    ):
        raise EpisodeEvidenceError("result summary differs from replay")
    if set(states) != memory.visited:
        raise EpisodeEvidenceError("state table does not equal the replayed visited set")
    if current_expansion + 1 > request["max_expansions"]:
        raise EpisodeEvidenceError("replayed episode exceeds its expansion budget")
    return memory


def _logical_lines(evidence: Mapping[str, Any]) -> Iterator[bytes]:
    yield _canonical_line(
        {
            "header": evidence["header"],
            "record_type": "header",
            "schema_version": EVIDENCE_SCHEMA_VERSION,
        }
    )
    for state_id in sorted(evidence["states"]):
        yield _canonical_line({"record_type": "state", "state": evidence["states"][state_id], "state_id": state_id})
    for event in evidence["events"]:
        yield _canonical_line({"event": event, "record_type": "event"})
    yield _canonical_line({"record_type": "result", "result": evidence["result"]})


def _episode_evidence(episode: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(episode, Mapping) or set(episode) != {"evidence", "result"}:
        raise EpisodeEvidenceError("episode must contain evidence and result")
    evidence = episode["evidence"]
    if not isinstance(evidence, Mapping) or episode["result"] != evidence.get("result"):
        raise EpisodeEvidenceError("episode result differs from logical evidence")
    return dict(evidence)


def _validate_evidence(evidence: Mapping[str, Any]) -> None:
    _require_object(evidence, _EVIDENCE_FIELDS, "evidence")
    if evidence["schema_version"] != EVIDENCE_SCHEMA_VERSION:
        raise EpisodeEvidenceError("unsupported evidence schema")
    _require_object(evidence["header"], _HEADER_FIELDS, "header")
    _require_digest(evidence["header"]["authority_id"], "header.authority_id")
    _require_digest(evidence["header"]["initial_memory_sha256"], "header.initial_memory_sha256")
    if not isinstance(evidence["states"], dict) or not evidence["states"]:
        raise EpisodeEvidenceError("states must be a non-empty state table")
    for state_id, state in evidence["states"].items():
        _require_digest(state_id, "state_id")
        _require_object(state, _STATE_FIELDS, f"state {state_id}")
        _require_digest(state["authority_id"], f"state {state_id}.authority_id")
        for field in ("atoms", "fluents"):
            if not isinstance(state[field], list) or any(not isinstance(item, str) for item in state[field]):
                raise EpisodeEvidenceError(f"state {state_id}.{field} must be an array of strings")
        canonical = CanonicalState(tuple(state["atoms"]), state["authority_id"], tuple(state["fluents"]))
        if canonical.state_id != state_id or serialize_state(canonical) != state:
            raise EpisodeEvidenceError(f"state table entry is not canonical: {state_id}")
    if not isinstance(evidence["events"], list):
        raise EpisodeEvidenceError("events must be an array")
    for index, event in enumerate(evidence["events"]):
        _require_object(event, _EVENT_FIELDS, f"event {index}")
        for field in ("index", "expansion_index"):
            if isinstance(event[field], bool) or not isinstance(event[field], int) or event[field] < 0:
                raise EpisodeEvidenceError(f"event {index}.{field} must be a non-negative integer")
        _require_digest(event["expanded_state_id"], f"event {index}.expanded_state_id")
        _require_digest(event["memory_sha256"], f"event {index}.memory_sha256")
        if not isinstance(event["newly_enqueued_state_ids"], list):
            raise EpisodeEvidenceError(f"event {index}.newly_enqueued_state_ids must be an array")
        for state_id in event["newly_enqueued_state_ids"]:
            _require_digest(state_id, f"event {index}.newly_enqueued_state_ids")
        if not isinstance(event["rationale"], str):
            raise EpisodeEvidenceError(f"event {index}.rationale must be text")
        _decode_operation(event["operation"])
    if not isinstance(evidence["result"], dict):
        raise EpisodeEvidenceError("result must be an object")
    try:
        _canonical_bytes(evidence)
    except (TypeError, ValueError) as error:
        raise EpisodeEvidenceError("evidence is not canonical JSON-compatible") from error


def _decode_operation(payload: Any) -> SearchTransitionRequest | SearchRetireRequest:
    if not isinstance(payload, dict):
        raise EpisodeEvidenceError("operation must be an object")
    if "operation_type" in payload:
        _require_object(payload, {"operation_type", "state_id"}, "retirement operation")
        if payload["operation_type"] != "retire_frontier":
            raise EpisodeEvidenceError("retirement operation type is invalid")
        _require_digest(payload["state_id"], "retirement state_id")
        return SearchRetireRequest(payload["state_id"])
    _require_object(
        payload,
        {"action", "evaluate_target", "frontier_intent", "source_state_id", "visit_target"},
        "transition operation",
    )
    action = payload["action"]
    _require_object(action, {"args", "name"}, "operation action")
    if not isinstance(action["name"], str) or not action["name"]:
        raise EpisodeEvidenceError("operation action name must be non-empty text")
    if not isinstance(action["args"], list) or any(not isinstance(item, str) for item in action["args"]):
        raise EpisodeEvidenceError("operation action args must be an array of strings")
    intent = payload["frontier_intent"]
    _require_object(intent, {"retire_source", "target_position"}, "operation frontier_intent")
    if not isinstance(intent["retire_source"], bool):
        raise EpisodeEvidenceError("operation retire_source must be boolean")
    position = intent["target_position"]
    if isinstance(position, bool) or not isinstance(position, int) or position < 0:
        raise EpisodeEvidenceError("operation target_position must be non-negative")
    _require_digest(payload["source_state_id"], "operation source_state_id")
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
    expected = {"algorithm", "max_expansions", "modality", "policy", "schema_version"}
    if payload.get("policy") == "random":
        expected.add("random_seed")
    _require_object(payload, expected, "request")
    if payload["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise EpisodeEvidenceError("request schema is invalid")
    if payload["algorithm"] != "bfs" or payload["modality"] != "text-state":
        raise EpisodeEvidenceError("request is not a BFS text-state episode")
    if payload["policy"] not in {"exact", "random"}:
        raise EpisodeEvidenceError("request policy is invalid")
    budget = payload["max_expansions"]
    if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
        raise EpisodeEvidenceError("request budget must be positive")
    if payload["policy"] == "random" and (
        isinstance(payload["random_seed"], bool) or not isinstance(payload["random_seed"], int)
    ):
        raise EpisodeEvidenceError("random request seed must be an integer")
    return payload


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
    if not isinstance(payload, dict):
        raise EpisodeEvidenceError("gate receipt is malformed")
    try:
        receipt = GateReceipt(
            binding=_binding_from_payload(payload["binding"]),
            outcome=payload["outcome"],
            ancestor_receipt_digest=payload["ancestor_receipt_digest"],
            signature=payload["signature"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise EpisodeEvidenceError("gate receipt is malformed") from error
    if receipt.to_dict() != payload:
        raise EpisodeEvidenceError("gate receipt has noncanonical fields")
    return receipt


def _authorization_from_payload(payload: Any) -> AuthorizationReceipt:
    if not isinstance(payload, dict):
        raise EpisodeEvidenceError("authorization receipt is malformed")
    try:
        receipt = AuthorizationReceipt(
            binding=_binding_from_payload(payload["binding"]),
            gate_receipt_digest=payload["gate_receipt_digest"],
            signature=payload["signature"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise EpisodeEvidenceError("authorization receipt is malformed") from error
    if receipt.to_dict() != payload:
        raise EpisodeEvidenceError("authorization receipt has noncanonical fields")
    return receipt


def _run_receipt_from_payload(payload: Any) -> RunReceipt:
    if not isinstance(payload, dict):
        raise EpisodeEvidenceError("run receipt is malformed")
    try:
        receipt = RunReceipt(
            binding=_binding_from_payload(payload["binding"]),
            outcome=payload["outcome"],
            run_state=payload["run_state"],
            start_permitted=payload["start_permitted"],
            scientific_completion=payload["scientific_completion"],
            gate_receipt_digest=payload["gate_receipt_digest"],
            authorization_receipt_digest=payload["authorization_receipt_digest"],
            ancestor_receipt_digest=payload["ancestor_receipt_digest"],
            reason=payload["reason"],
            signature=payload["signature"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise EpisodeEvidenceError("run receipt is malformed") from error
    if receipt.to_dict() != payload:
        raise EpisodeEvidenceError("run receipt has noncanonical fields")
    return receipt


def _load_canonical_episode(payload: bytes) -> Any:
    if not payload.endswith(b"\n"):
        raise EpisodeEvidenceError("v1 episode artifact is not newline terminated")
    value = _load_json(payload[:-1], "v1 episode")
    if _canonical_line(value) != payload:
        raise EpisodeEvidenceError("v1 episode artifact is not canonical JSON")
    return value


def _load_canonical_payload(payload: bytes, label: str) -> Any:
    value = _load_json(payload, label)
    if _canonical_bytes(value) != payload:
        raise EpisodeEvidenceError(f"{label} is not canonical JSON")
    return value


def _load_json(payload: bytes, label: str) -> Any:
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
        return json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicates, parse_constant=reject_constant)
    except EpisodeEvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EpisodeEvidenceError(f"{label} is not valid UTF-8 JSON") from error


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _canonical_line(value: Any) -> bytes:
    return _canonical_bytes(value) + b"\n"


def _load_canonical_line(line: bytes, *, index: int) -> Any:
    if not line.endswith(b"\n"):
        raise EpisodeEvidenceError(f"record {index} is not newline terminated")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise EpisodeEvidenceError(f"duplicate field at record {index}: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise EpisodeEvidenceError(f"invalid number at record {index}: {value}")

    try:
        value = json.loads(
            line[:-1].decode("utf-8"), object_pairs_hook=reject_duplicates, parse_constant=reject_constant
        )
    except EpisodeEvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EpisodeEvidenceError(f"record {index} is not valid UTF-8 JSON") from error
    if _canonical_line(value) != line:
        raise EpisodeEvidenceError(f"record {index} is not canonical JSON")
    return value


def _require_object(value: Any, fields: set[str], path: str) -> None:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise EpisodeEvidenceError(f"{path} has invalid fields")


def _require_digest(value: Any, path: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise EpisodeEvidenceError(f"{path} must be a lowercase SHA-256 digest")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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
    "materialize_episode_artifacts",
    "memory_sha256",
    "migrate_v1_episode",
    "read_episode_artifacts",
    "read_episode_evidence",
    "read_versioned_episode_evidence",
    "replay_episode",
    "replay_episode_evidence",
    "serialize_operation",
    "serialize_state",
    "write_episode_evidence",
]
