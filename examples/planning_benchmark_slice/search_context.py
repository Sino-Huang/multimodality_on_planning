from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .pddl_state import PDDLStateAuthority
from .search_memory import AcceptedTransition, SearchMemory, SearchTransitionResult, apply_search_transition
from .search_trace import (
    SearchTraceError,
    TraceSegmentLimits,
    _canonical_bytes,
    _decode_operation,
    _load_canonical_json,
    _persisted_evaluator,
    _require_hash,
    _serialize_result,
    _sha256,
    _validate_operation,
    _validate_operation_result,
    _validate_result,
    _validated_envelope,
    append_search_trace_record,
    start_search_trace,
)

_CHECKPOINT_FIELD = "checkpoint"
_CHECKPOINT_FIELDS = {"authority_id", "memory_sha256", "accepted_transitions"}
_CHECKPOINT_TRANSITION_FIELDS = {"operation", "result"}
_STANDARD_ENVELOPE_FIELDS = {
    "schema_version",
    "authority_id",
    "initial_memory_sha256",
    "record_count",
    "records",
    "tail_hash",
}


class TraceMaterializationError(SearchTraceError):
    """Raised when a persisted trace cannot be materialized safely."""


@dataclass(frozen=True, slots=True)
class SearchMemoryCheckpoint:
    """An immutable, authority-bound, replayable search-memory snapshot."""

    authority_id: str
    memory_sha256: str
    _accepted_transition_payloads: tuple[bytes, ...]

    def restore(self, authority: PDDLStateAuthority) -> SearchMemory:
        if not isinstance(authority, PDDLStateAuthority):
            raise TraceMaterializationError("checkpoint authority must be a PDDLStateAuthority")
        if authority.authority_id != self.authority_id:
            raise TraceMaterializationError("checkpoint belongs to a different authority")

        try:
            memory = SearchMemory.initial(authority)
            for payload in self._accepted_transition_payloads:
                transition = _load_canonical_json(payload)
                operation_payload = transition["operation"]
                result_payload = transition["result"]
                _validate_checkpoint_transition(operation_payload, result_payload)
                actual = _apply_persisted_transition(memory, operation_payload, result_payload)
                if not isinstance(actual, AcceptedTransition):
                    raise SearchTraceError("checkpoint transition did not replay as accepted")
                memory = actual.memory
            if _sha256(memory.to_bytes()) != self.memory_sha256:
                raise SearchTraceError("restored checkpoint memory does not match its digest")
            return memory
        except TraceMaterializationError:
            raise
        except (KeyError, TypeError, SearchTraceError, ValueError) as error:
            raise TraceMaterializationError("checkpoint could not be restored") from error

    def _to_payload(self) -> dict[str, Any]:
        return {
            "authority_id": self.authority_id,
            "memory_sha256": self.memory_sha256,
            "accepted_transitions": [
                _load_canonical_json(payload) for payload in self._accepted_transition_payloads
            ],
        }


@dataclass(frozen=True, slots=True)
class AcceptedSearchDelta:
    record_index: int
    _record_payload: bytes


@dataclass(frozen=True, slots=True)
class AtomicSearchTraceSegment:
    record_index: int
    checkpoint: SearchMemoryCheckpoint
    _payload: bytes

    def to_bytes(self) -> bytes:
        return self._payload


@dataclass(frozen=True, slots=True)
class RollingSearchContext:
    checkpoint: SearchMemoryCheckpoint
    accepted_deltas: tuple[AcceptedSearchDelta, ...]
    _payload: bytes

    def to_bytes(self) -> bytes:
        return self._payload


@dataclass(frozen=True, slots=True)
class _MaterializedRecord:
    record_index: int
    payload: bytes
    accepted: bool


@dataclass(frozen=True, slots=True)
class MaterializedSearchTrace:
    checkpoints: tuple[SearchMemoryCheckpoint, ...]
    atomic_segments: tuple[AtomicSearchTraceSegment, ...]
    _records: tuple[_MaterializedRecord, ...]
    _authority: PDDLStateAuthority
    _limits: TraceSegmentLimits

    def rolling_context_before(
        self,
        record_index: int,
        *,
        accepted_delta_limit: int,
    ) -> RollingSearchContext:
        if isinstance(record_index, bool) or not isinstance(record_index, int):
            raise TraceMaterializationError("record_index must be an integer")
        if record_index < 0 or record_index > len(self._records):
            raise TraceMaterializationError("record_index is outside the trace")
        if isinstance(accepted_delta_limit, bool) or not isinstance(accepted_delta_limit, int):
            raise TraceMaterializationError("accepted_delta_limit must be an integer")
        if accepted_delta_limit <= 0:
            raise TraceMaterializationError("accepted_delta_limit must be positive")

        prior_accepted = [record for record in self._records[:record_index] if record.accepted]
        selected = prior_accepted[-accepted_delta_limit:]
        if selected:
            checkpoint = self.checkpoints[selected[0].record_index]
        else:
            checkpoint = self.checkpoints[record_index]

        payload = _build_context_payload(
            checkpoint,
            selected,
            authority=self._authority,
            limits=self._limits,
        )
        deltas = tuple(
            AcceptedSearchDelta(record_index=record.record_index, _record_payload=record.payload)
            for record in selected
        )
        return RollingSearchContext(checkpoint=checkpoint, accepted_deltas=deltas, _payload=payload)


def materialize_search_trace(
    payload: bytes,
    *,
    authority: PDDLStateAuthority,
    limits: TraceSegmentLimits,
) -> MaterializedSearchTrace:
    """Validate, replay, and split canonical persisted trace bytes into contexts."""

    try:
        if not isinstance(authority, PDDLStateAuthority):
            raise SearchTraceError("authority must be a PDDLStateAuthority")
        if not isinstance(limits, TraceSegmentLimits):
            raise SearchTraceError("limits must be TraceSegmentLimits")
        if not isinstance(payload, bytes):
            raise SearchTraceError("trace payload must be bytes")
        if len(payload) > limits.max_bytes:
            raise SearchTraceError("trace exceeds max_bytes")

        encoded = _load_canonical_json(payload)
        if not isinstance(encoded, dict):
            raise SearchTraceError("trace envelope must be an object")
        fields = set(encoded)
        if fields == _STANDARD_ENVELOPE_FIELDS:
            checkpoint_payload = None
            standard_payload = payload
        elif fields == _STANDARD_ENVELOPE_FIELDS | {_CHECKPOINT_FIELD}:
            checkpoint_payload = encoded[_CHECKPOINT_FIELD]
            standard_payload = _canonical_bytes(
                {field: encoded[field] for field in _STANDARD_ENVELOPE_FIELDS}
            )
        else:
            missing = sorted(_STANDARD_ENVELOPE_FIELDS - fields)
            unknown = sorted(fields - (_STANDARD_ENVELOPE_FIELDS | {_CHECKPOINT_FIELD}))
            raise SearchTraceError(
                f"invalid fields in envelope: missing={missing}, unknown={unknown}"
            )

        envelope = _validated_envelope(standard_payload, limits=limits)
        if authority.authority_id != envelope["authority_id"]:
            raise SearchTraceError("trace authority does not match materialization authority")

        if checkpoint_payload is None:
            initial_memory = SearchMemory.initial(authority)
            if _sha256(initial_memory.to_bytes()) != envelope["initial_memory_sha256"]:
                raise SearchTraceError("initial materialization memory does not match trace")
            initial_checkpoint = _checkpoint_from_memory(initial_memory, ())
        else:
            initial_checkpoint = _decode_checkpoint(
                checkpoint_payload,
                authority=authority,
                limits=limits,
            )
            if (
                len(initial_checkpoint._accepted_transition_payloads)
                + envelope["record_count"]
                > limits.max_records
            ):
                raise SearchTraceError("checkpoint and trace exceed max_records")
            if initial_checkpoint.memory_sha256 != envelope["initial_memory_sha256"]:
                raise SearchTraceError("checkpoint does not match trace initial memory")

        return _materialize_validated_envelope(
            envelope,
            initial_checkpoint=initial_checkpoint,
            authority=authority,
            limits=limits,
        )
    except TraceMaterializationError:
        raise
    except (KeyError, TypeError, SearchTraceError, ValueError) as error:
        raise TraceMaterializationError("search trace could not be materialized") from error


def _materialize_validated_envelope(
    envelope: Mapping[str, Any],
    *,
    initial_checkpoint: SearchMemoryCheckpoint,
    authority: PDDLStateAuthority,
    limits: TraceSegmentLimits,
) -> MaterializedSearchTrace:
    memory = initial_checkpoint.restore(authority)
    accepted_transition_payloads = initial_checkpoint._accepted_transition_payloads
    checkpoints = [initial_checkpoint]
    records: list[_MaterializedRecord] = []
    atomic_segments: list[AtomicSearchTraceSegment] = []

    for index, persisted_record in enumerate(envelope["records"]):
        record_payload = _canonical_bytes(persisted_record)
        status = persisted_record["result"]["status"]
        actual = _apply_persisted_transition(
            memory,
            persisted_record["operation"],
            persisted_record["result"],
        )
        is_accepted = isinstance(actual, AcceptedTransition)
        if is_accepted != (status == "accepted"):
            raise SearchTraceError(f"replayed status differs at record {index}")

        record = _MaterializedRecord(index, record_payload, is_accepted)
        atomic_payload = _build_context_payload(
            checkpoints[-1],
            [record],
            authority=authority,
            limits=limits,
        )
        atomic_segments.append(
            AtomicSearchTraceSegment(
                record_index=index,
                checkpoint=checkpoints[-1],
                _payload=atomic_payload,
            )
        )
        records.append(record)

        memory = actual.memory
        if is_accepted:
            accepted_transition_payloads = (
                *accepted_transition_payloads,
                _checkpoint_transition_bytes(
                    persisted_record["operation"], persisted_record["result"]
                ),
            )
        checkpoints.append(_checkpoint_from_memory(memory, accepted_transition_payloads))

    return MaterializedSearchTrace(
        checkpoints=tuple(checkpoints),
        atomic_segments=tuple(atomic_segments),
        _records=tuple(records),
        _authority=authority,
        _limits=limits,
    )


def _build_context_payload(
    checkpoint: SearchMemoryCheckpoint,
    records: list[_MaterializedRecord],
    *,
    authority: PDDLStateAuthority,
    limits: TraceSegmentLimits,
) -> bytes:
    memory = checkpoint.restore(authority)
    segment = start_search_trace(memory, limits=limits)
    for record in records:
        persisted_record = _load_canonical_json(record.payload)
        operation = _decode_operation(persisted_record["operation"])
        actual = _apply_persisted_transition(
            memory,
            persisted_record["operation"],
            persisted_record["result"],
        )
        segment = append_search_trace_record(
            segment,
            memory_before=memory,
            observation=persisted_record["observation"],
            rationale=persisted_record["rationale"],
            operation=operation,
            result=actual,
            limits=limits,
        )
        memory = actual.memory

    standard_payload = segment.to_bytes()
    initial_memory = SearchMemory.initial(authority)
    if checkpoint.memory_sha256 == _sha256(initial_memory.to_bytes()):
        return standard_payload

    encoded = _load_canonical_json(standard_payload)
    encoded[_CHECKPOINT_FIELD] = checkpoint._to_payload()
    context_payload = _canonical_bytes(encoded)
    if len(context_payload) > limits.max_bytes:
        raise SearchTraceError("materialized context exceeds max_bytes")
    return context_payload


def _decode_checkpoint(
    payload: Any,
    *,
    authority: PDDLStateAuthority,
    limits: TraceSegmentLimits,
) -> SearchMemoryCheckpoint:
    if not isinstance(payload, dict) or set(payload) != _CHECKPOINT_FIELDS:
        raise SearchTraceError("checkpoint has invalid fields")
    if payload["authority_id"] != authority.authority_id:
        raise SearchTraceError("checkpoint authority does not match materialization authority")
    _require_hash(payload["memory_sha256"], "checkpoint.memory_sha256")
    transitions = payload["accepted_transitions"]
    if not isinstance(transitions, list):
        raise SearchTraceError("checkpoint.accepted_transitions must be an array")
    if len(transitions) > limits.max_records:
        raise SearchTraceError("checkpoint exceeds max_records")

    transition_payloads: list[bytes] = []
    for transition in transitions:
        if not isinstance(transition, dict) or set(transition) != _CHECKPOINT_TRANSITION_FIELDS:
            raise SearchTraceError("checkpoint transition has invalid fields")
        _validate_checkpoint_transition(transition["operation"], transition["result"])
        transition_payloads.append(_canonical_bytes(transition))

    checkpoint = SearchMemoryCheckpoint(
        authority_id=payload["authority_id"],
        memory_sha256=payload["memory_sha256"],
        _accepted_transition_payloads=tuple(transition_payloads),
    )
    checkpoint.restore(authority)
    return checkpoint


def _checkpoint_from_memory(
    memory: SearchMemory,
    accepted_transition_payloads: tuple[bytes, ...],
) -> SearchMemoryCheckpoint:
    return SearchMemoryCheckpoint(
        authority_id=memory.authority.authority_id,
        memory_sha256=_sha256(memory.to_bytes()),
        _accepted_transition_payloads=accepted_transition_payloads,
    )


def _checkpoint_transition_bytes(
    operation_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> bytes:
    _validate_checkpoint_transition(operation_payload, result_payload)
    return _canonical_bytes({"operation": operation_payload, "result": result_payload})


def _validate_checkpoint_transition(
    operation_payload: Any,
    result_payload: Any,
) -> None:
    _validate_operation(operation_payload, path="checkpoint.operation")
    _validate_result(result_payload, path="checkpoint.result")
    _validate_operation_result(operation_payload, result_payload)
    if result_payload["status"] != "accepted":
        raise SearchTraceError("checkpoint may contain only accepted transitions")


def _apply_persisted_transition(
    memory: SearchMemory,
    operation_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> SearchTransitionResult:
    operation = _decode_operation(operation_payload)
    actual = apply_search_transition(
        memory,
        operation,
        evaluator=_persisted_evaluator(result_payload),
    )
    if _serialize_result(actual) != result_payload:
        raise SearchTraceError("persisted result does not match semantic replay")
    if _sha256(actual.memory.to_bytes()) != result_payload["memory_sha256"]:
        raise SearchTraceError("persisted memory does not match semantic replay")
    return actual


__all__ = [
    "AcceptedSearchDelta",
    "AtomicSearchTraceSegment",
    "MaterializedSearchTrace",
    "RollingSearchContext",
    "SearchMemoryCheckpoint",
    "TraceMaterializationError",
    "materialize_search_trace",
]
