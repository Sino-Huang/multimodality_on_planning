"""Versioned, deterministic persistence and replay for governed BFS episodes."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import tempfile
import zlib
from collections.abc import Iterable, Iterator, Mapping
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

V2_EVIDENCE_SCHEMA_VERSION = "search_episode_evidence_v2"
V2_CODEC_VERSION = "canonical_jsonl_gzip_v2"
EVIDENCE_SCHEMA_VERSION = "search_episode_evidence_v3"
CODEC_VERSION = "canonical_jsonl_gzip_v3"
TASK_SCHEMA_VERSION = "search_episode_task_v1"
REQUEST_SCHEMA_VERSION = "search_episode_request_v1"
_GZIP_SCHEMAS = {V2_EVIDENCE_SCHEMA_VERSION, EVIDENCE_SCHEMA_VERSION}

_EVIDENCE_FIELDS = {"events", "header", "result", "schema_version", "states"}
_V3_HEADER_FIELDS = {
    "authorization_receipt",
    "authority_id",
    "frozen_binding",
    "gate_receipt",
    "request",
    "task",
}
_V2_HEADER_FIELDS = {*_V3_HEADER_FIELDS, "initial_memory_sha256"}
_V3_EVENT_FIELDS = {
    "expanded_state_id",
    "expansion_index",
    "index",
    "newly_enqueued_state_ids",
    "operation",
    "rationale",
}
_V2_EVENT_FIELDS = {*_V3_EVENT_FIELDS, "memory_sha256"}
_STATE_FIELDS = {"atoms", "authority_id", "fluents"}


def _codec_version(schema_version: str) -> str:
    return V2_CODEC_VERSION if schema_version == V2_EVIDENCE_SCHEMA_VERSION else CODEC_VERSION


class EpisodeEvidenceError(ValueError):
    """Raised when persisted episode evidence is malformed or inconsistent."""


def episode_result_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return the compact scientific result retained in episode manifests."""

    return {
        field: result[field]
        for field in ("completion", "expansion_count", "goal_reached", "outcome", "scientific_completion")
    }


def verify_manifested_episode(
    path: str | Path,
    manifest: Mapping[str, Any],
    expected_result: Mapping[str, Any],
    *,
    signing_key: bytes | str,
) -> dict[str, Any]:
    """Verify a manifested search episode without exposing format dispatch."""

    source = Path(path)
    with source.open("rb") as handle:
        is_gzip = handle.read(2) == b"\x1f\x8b"
    if is_gzip:
        verified = verify_episode_evidence(source, signing_key=signing_key)
        actual_manifest = {"path": manifest.get("path"), **verified["manifest"]}
        actual_result = episode_result_summary(verified["result"])
        result = verified
    else:
        episode = read_versioned_episode_evidence(source, signing_key=signing_key)
        payload = source.read_bytes()
        actual_manifest = {
            "path": manifest.get("path"),
            "sha256": _sha256(payload),
            "size_bytes": len(payload),
        }
        actual_result = episode["result"]
        result = episode
    if dict(manifest) != actual_manifest or dict(expected_result) != actual_result:
        raise EpisodeEvidenceError(f"episode artifact differs from its manifest: {source}")
    return result


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
    """Atomically write one supported episode as deterministic canonical JSONL gzip."""

    target = Path(path)
    if target.exists():
        raise FileExistsError(f"episode evidence already exists: {target}")
    evidence = _episode_evidence(episode)
    schema_version = evidence["schema_version"]
    _validate_evidence(evidence)
    logical_digest = hashlib.sha256()

    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=raw, mtime=0) as compressed:
                for line in _logical_lines(evidence):
                    logical_digest.update(line)
                    compressed.write(line)
                logical_sha256 = logical_digest.hexdigest()
                compressed.write(_canonical_line({"logical_sha256": logical_sha256, "record_type": "digest"}))
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "codec_version": _codec_version(schema_version),
        "logical_sha256": logical_sha256,
        "schema_version": schema_version,
        "stored_size_bytes": target.stat().st_size,
    }


def read_episode_evidence(path: str | Path) -> dict[str, Any]:
    """Read and authenticate a gzip artifact without exposing its physical layout."""

    source = Path(path)
    digest = hashlib.sha256()
    header: dict[str, Any] | None = None
    states: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    result: dict[str, Any] | None = None
    expected_digest: str | None = None
    schema_version: str | None = None
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
                    schema_version = record["schema_version"]
                    if schema_version not in _GZIP_SCHEMAS or not isinstance(record["header"], dict):
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

    if header is None or result is None or expected_digest is None or schema_version is None:
        raise EpisodeEvidenceError("episode evidence is incomplete")
    actual_digest = digest.hexdigest()
    if actual_digest != expected_digest:
        raise EpisodeEvidenceError("logical evidence digest does not match its records")
    evidence = {
        "events": events,
        "header": header,
        "result": result,
        "schema_version": schema_version,
        "states": states,
    }
    _validate_evidence(evidence)
    return {"evidence": evidence, "result": result}


def episode_evidence_manifest(
    path: str | Path,
    *,
    episode: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the compact manifest fields for one verified gzip artifact."""

    source = Path(path)
    episode = read_episode_evidence(source) if episode is None else dict(episode)
    evidence = _episode_evidence(episode)
    logical_digest = hashlib.sha256()
    for line in _logical_lines(evidence):
        logical_digest.update(line)
    schema_version = evidence["schema_version"]
    return {
        "codec_version": _codec_version(schema_version),
        "logical_sha256": logical_digest.hexdigest(),
        "schema_version": schema_version,
        "stored_size_bytes": source.stat().st_size,
    }


def verify_episode_evidence(path: str | Path, *, signing_key: bytes | str) -> dict[str, Any]:
    """Stream, authenticate, and replay gzip evidence without retaining its events."""

    source = Path(path)
    digest = hashlib.sha256()
    states: dict[str, Any] = {}
    result_holder: dict[str, Any] = {}
    digest_holder: dict[str, str] = {}
    try:
        with gzip.open(source, "rb") as compressed:
            numbered = enumerate(compressed)
            try:
                line_index, line = next(numbered)
            except StopIteration as error:
                raise EpisodeEvidenceError("episode evidence is incomplete") from error
            header_record = _load_canonical_line(line, index=line_index)
            schema_version = header_record.get("schema_version") if isinstance(header_record, dict) else None
            if (
                not isinstance(header_record, dict)
                or set(header_record) != {"header", "record_type", "schema_version"}
                or header_record["record_type"] != "header"
                or schema_version not in _GZIP_SCHEMAS
            ):
                raise EpisodeEvidenceError("header record is misplaced or malformed")
            header = header_record["header"]
            _validate_header(header, schema_version=schema_version)
            digest.update(line)

            first_non_state: tuple[int, bytes, Any] | None = None
            for line_index, line in numbered:
                record = _load_canonical_line(line, index=line_index)
                if isinstance(record, dict) and record.get("record_type") == "state":
                    if set(record) != {"record_type", "state", "state_id"}:
                        raise EpisodeEvidenceError("state record is malformed")
                    state_id = record["state_id"]
                    if state_id in states:
                        raise EpisodeEvidenceError(f"duplicate state table entry: {state_id}")
                    states[state_id] = record["state"]
                    digest.update(line)
                    continue
                first_non_state = (line_index, line, record)
                break
            if first_non_state is None:
                raise EpisodeEvidenceError("episode evidence is incomplete")
            _validate_states(states)

            def streamed_events() -> Iterator[Mapping[str, Any]]:
                pending = first_non_state
                result_seen = False
                items = iter(numbered)
                while pending is not None:
                    current_index, current_line, record = pending
                    pending = None
                    record_type = record.get("record_type") if isinstance(record, dict) else None
                    if record_type == "event":
                        if result_seen or set(record) != {"event", "record_type"}:
                            raise EpisodeEvidenceError("event record is misplaced or malformed")
                        event = record["event"]
                        _validate_event(
                            event, index=event["index"] if isinstance(event, dict) else -1, schema_version=schema_version
                        )
                        digest.update(current_line)
                        yield event
                    elif record_type == "result":
                        if (
                            result_seen
                            or set(record) != {"record_type", "result"}
                            or not isinstance(record["result"], dict)
                        ):
                            raise EpisodeEvidenceError("result record is misplaced or malformed")
                        result_holder.update(record["result"])
                        result_seen = True
                        digest.update(current_line)
                    elif record_type == "digest":
                        if (
                            not result_seen
                            or set(record) != {"logical_sha256", "record_type"}
                            or record["logical_sha256"] != digest.hexdigest()
                        ):
                            raise EpisodeEvidenceError("logical evidence digest does not match its records")
                        digest_holder["logical_sha256"] = record["logical_sha256"]
                        try:
                            next(items)
                        except StopIteration:
                            return
                        raise EpisodeEvidenceError("artifact contains records after its logical digest")
                    else:
                        raise EpisodeEvidenceError(f"unknown record type at line {current_index + 1}")
                    try:
                        next_index, next_line = next(items)
                    except StopIteration:
                        break
                    pending = (next_index, next_line, _load_canonical_line(next_line, index=next_index))
                raise EpisodeEvidenceError("episode evidence is incomplete")

            memory, expansion_count, authority, gate, request = _replay_event_sequence(
                header,
                states,
                streamed_events(),
                signing_key=signing_key,
                schema_version=schema_version,
            )
    except EpisodeEvidenceError:
        raise
    except (EOFError, gzip.BadGzipFile, OSError, zlib.error) as error:
        raise EpisodeEvidenceError("episode evidence is not a complete valid gzip stream") from error

    if not result_holder or "logical_sha256" not in digest_holder:
        raise EpisodeEvidenceError("episode evidence is incomplete")
    _validate_replayed_result(
        result_holder,
        memory=memory,
        expansion_count=expansion_count,
        authority=authority,
        gate=gate,
        request=request,
        states=states,
        signing_key=signing_key,
    )
    return {
        "header": header,
        "manifest": {
            "codec_version": _codec_version(schema_version),
            "logical_sha256": digest_holder["logical_sha256"],
            "schema_version": schema_version,
            "stored_size_bytes": source.stat().st_size,
        },
        "result": result_holder,
    }


def read_versioned_episode_evidence(
    path: str | Path,
    *,
    signing_key: bytes | str,
) -> dict[str, Any]:
    """Read and replay retained v1 JSON or supported gzip evidence."""

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
    if evidence["schema_version"] in _GZIP_SCHEMAS:
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
    """Materialize canonical task and v1 training-trace views from compact evidence."""

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
    """Verify one immutable v1 JSON episode and write its current-schema equivalent."""

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
        frozen_binding=None,
    )
    if migrated["result"] != legacy_episode["result"]:
        raise EpisodeEvidenceError("v1 and migrated scientific results differ")
    manifest = write_episode_evidence(target, migrated)
    if source.read_bytes() != source_bytes:
        raise EpisodeEvidenceError("v1 migration mutated its source artifact")
    return {"source_sha256": source_sha256, **manifest}


def replay_episode_evidence(path: str | Path, *, signing_key: bytes | str) -> dict[str, Any]:
    """Read, verify receipts, and mechanically replay one persisted gzip episode."""

    episode = read_episode_evidence(path)
    replay_episode(episode["evidence"], signing_key=signing_key)
    return episode


def replay_episode(evidence: Mapping[str, Any], *, signing_key: bytes | str) -> SearchMemory:
    """Verify and replay an in-memory logical episode."""

    normalized = dict(evidence)
    _validate_evidence(normalized)
    memory, expansion_count, authority, gate, request = _replay_event_sequence(
        normalized["header"],
        normalized["states"],
        iter(normalized["events"]),
        signing_key=signing_key,
        schema_version=normalized["schema_version"],
    )
    _validate_replayed_result(
        normalized["result"],
        memory=memory,
        expansion_count=expansion_count,
        authority=authority,
        gate=gate,
        request=request,
        states=normalized["states"],
        signing_key=signing_key,
    )
    return memory


def _replay_event_sequence(
    header: Mapping[str, Any],
    states: Mapping[str, Any],
    events: Iterable[Mapping[str, Any]],
    *,
    signing_key: bytes | str,
    schema_version: str = EVIDENCE_SCHEMA_VERSION,
) -> tuple[SearchMemory, int, PDDLStateAuthority, GateReceipt, dict[str, Any]]:
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
    authority = _authority_from_task(header["task"])
    if header["authority_id"] != authority.authority_id:
        raise EpisodeEvidenceError("evidence authority differs from its task")
    if schema_version == EVIDENCE_SCHEMA_VERSION:
        return _replay_v3_event_sequence(
            states,
            events,
            authority=authority,
            gate=gate,
            request=request,
        )
    memory = SearchMemory.initial(authority)
    if schema_version == V2_EVIDENCE_SCHEMA_VERSION and header["initial_memory_sha256"] != memory_sha256(memory):
        raise EpisodeEvidenceError("initial replay memory differs from evidence")
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
        if schema_version == V2_EVIDENCE_SCHEMA_VERSION and event["memory_sha256"] != memory_sha256(memory):
            raise EpisodeEvidenceError(f"memory digest differs at event {index}")
        operation_in_expansion += 1
    finish_expansion()
    return memory, current_expansion + 1, authority, gate, request


def _replay_v3_event_sequence(
    states: Mapping[str, Any],
    events: Iterable[Mapping[str, Any]],
    *,
    authority: PDDLStateAuthority,
    gate: GateReceipt,
    request: dict[str, Any],
) -> tuple[SearchMemory, int, PDDLStateAuthority, GateReceipt, dict[str, Any]]:
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
        expected = (*frontier_tail, *enqueued_state_ids)
        if tuple(memory.frontier) != expected:
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
            generated = memory.retire_frontier_head(expanded_state_id)
            if generated != operation:
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
            applied = memory.apply_generated_action(
                expanded_state_id,
                operation.action,
                retire_source=first,
            )
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
    return memory.freeze(), current_expansion + 1, authority, gate, request


def _validate_replayed_result(
    result_payload: Mapping[str, Any],
    *,
    memory: SearchMemory,
    expansion_count: int,
    authority: PDDLStateAuthority,
    gate: GateReceipt,
    request: Mapping[str, Any],
    states: Mapping[str, Any],
    signing_key: bytes | str,
) -> None:
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
        or result_payload.get("expansion_count") != expansion_count
        or result_payload.get("goal_reached") is not goal_reached
        or result_payload.get("outcome") != StopOutcome.PASS.value
        or result_payload.get("scientific_completion") is not True
    ):
        raise EpisodeEvidenceError("result summary differs from replay")
    if set(states) != memory.visited:
        raise EpisodeEvidenceError("state table does not equal the replayed visited set")
    if expansion_count > request["max_expansions"]:
        raise EpisodeEvidenceError("replayed episode exceeds its expansion budget")


def _logical_lines(evidence: Mapping[str, Any]) -> Iterator[bytes]:
    yield _canonical_line(
        {
            "header": evidence["header"],
            "record_type": "header",
            "schema_version": evidence["schema_version"],
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
    schema_version = evidence["schema_version"]
    if schema_version not in _GZIP_SCHEMAS:
        raise EpisodeEvidenceError("unsupported evidence schema")
    _validate_header(evidence["header"], schema_version=schema_version)
    _validate_states(evidence["states"])
    if not isinstance(evidence["events"], list):
        raise EpisodeEvidenceError("events must be an array")
    for index, event in enumerate(evidence["events"]):
        _validate_event(event, index=index, schema_version=schema_version)
    if not isinstance(evidence["result"], dict):
        raise EpisodeEvidenceError("result must be an object")


def _validate_header(header: Any, *, schema_version: str) -> None:
    fields = _V2_HEADER_FIELDS if schema_version == V2_EVIDENCE_SCHEMA_VERSION else _V3_HEADER_FIELDS
    _require_object(header, fields, "header")
    _require_digest(header["authority_id"], "header.authority_id")
    if schema_version == V2_EVIDENCE_SCHEMA_VERSION:
        _require_digest(header["initial_memory_sha256"], "header.initial_memory_sha256")
    frozen_binding = header["frozen_binding"]
    if frozen_binding is not None and not isinstance(frozen_binding, dict):
        raise EpisodeEvidenceError("header.frozen_binding must be an object or null")


def _validate_states(states: Any) -> None:
    if not isinstance(states, dict) or not states:
        raise EpisodeEvidenceError("states must be a non-empty state table")
    for state_id, state in states.items():
        _require_digest(state_id, "state_id")
        _require_object(state, _STATE_FIELDS, f"state {state_id}")
        _require_digest(state["authority_id"], f"state {state_id}.authority_id")
        for field in ("atoms", "fluents"):
            if not isinstance(state[field], list) or any(not isinstance(item, str) for item in state[field]):
                raise EpisodeEvidenceError(f"state {state_id}.{field} must be an array of strings")
        canonical = CanonicalState(tuple(state["atoms"]), state["authority_id"], tuple(state["fluents"]))
        if canonical.state_id != state_id or serialize_state(canonical) != state:
            raise EpisodeEvidenceError(f"state table entry is not canonical: {state_id}")


def _validate_event(event: Any, *, index: int, schema_version: str) -> None:
    fields = _V2_EVENT_FIELDS if schema_version == V2_EVIDENCE_SCHEMA_VERSION else _V3_EVENT_FIELDS
    _require_object(event, fields, f"event {index}")
    for field in ("index", "expansion_index"):
        if isinstance(event[field], bool) or not isinstance(event[field], int) or event[field] < 0:
            raise EpisodeEvidenceError(f"event {index}.{field} must be a non-negative integer")
    _require_digest(event["expanded_state_id"], f"event {index}.expanded_state_id")
    if schema_version == V2_EVIDENCE_SCHEMA_VERSION:
        _require_digest(event["memory_sha256"], f"event {index}.memory_sha256")
    if not isinstance(event["newly_enqueued_state_ids"], list):
        raise EpisodeEvidenceError(f"event {index}.newly_enqueued_state_ids must be an array")
    for state_id in event["newly_enqueued_state_ids"]:
        _require_digest(state_id, f"event {index}.newly_enqueued_state_ids")
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
    "V2_CODEC_VERSION",
    "V2_EVIDENCE_SCHEMA_VERSION",
    "EpisodeEvidenceError",
    "episode_evidence_manifest",
    "episode_result_summary",
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
    "verify_episode_evidence",
    "verify_manifested_episode",
    "write_episode_evidence",
]
