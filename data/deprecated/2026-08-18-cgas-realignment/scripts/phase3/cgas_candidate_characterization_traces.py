from __future__ import annotations

import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from io import BufferedRandom
from pathlib import Path
from types import TracebackType

from pydantic import ValidationError

from .cgas_candidate_characterization_contracts import CandidateCharacterizationError, confined
from .cgas_candidate_characterization_models import JsonValue as PersistedJsonValue
from .cgas_candidate_characterization_models import TraceBindingModel
from .cgas_trace_contract_v3 import CONTRACT_ID
from .cgas_trace_stream_v2 import (
    CompletionStatus,
    ContractId,
    Planner,
    TraceStreamError,
    TraceVerification,
    TraceWriteRequest,
    verify_trace_stream,
    write_trace_stream,
)
from .cgas_trace_v2_json import canonical_json_bytes, parse_canonical_json_line
from .local_planner_types import JSONValue as PlannerJsonValue


@dataclass(frozen=True, slots=True)
class TracePersistenceRequest:
    repository_root: Path
    output_root: Path
    candidate_id: str
    planner: Planner
    status: str
    plan: tuple[str, ...]
    trace: Mapping[str, PlannerJsonValue]
    event_field: str


@dataclass(frozen=True, slots=True)
class TraceValidationRequest:
    repository_root: Path
    binding_value: PersistedJsonValue | None
    expected_planner: Planner
    error_path: Path
    expected_contract_id: ContractId


class TraceEventSpool:
    __slots__ = ("_candidate_id", "_handle", "_output_root", "_planner", "_repository_root", "_row_count")

    def __init__(self, repository_root: Path, output_root: Path, candidate_id: str, planner: Planner) -> None:
        self._repository_root = repository_root
        self._output_root = output_root
        self._candidate_id = candidate_id
        self._planner: Planner = planner
        self._handle: BufferedRandom = tempfile.TemporaryFile(mode="w+b")
        self._row_count = 0

    def append(self, event: Mapping[str, PlannerJsonValue], /) -> None:
        self._handle.write(canonical_json_bytes(dict(event), self._output_root, "trace_spool_invalid") + b"\n")
        self._row_count += 1

    def publish(self, status: str, plan: tuple[str, ...]) -> TraceBindingModel:
        self._handle.flush()
        self._handle.seek(0)
        output = self._output_root / "traces" / self._candidate_id / f"{self._planner}.trace-v3.jsonl"
        verification = write_trace_stream(
            TraceWriteRequest(
                output,
                self._planner,
                _completion_status(status, output),
                plan,
                self._row_count,
                CONTRACT_ID,
            ),
            (parse_canonical_json_line(line, output, "trace_spool_invalid") for line in self._handle),
        )
        return trace_binding(self._repository_root, output, verification)

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> TraceEventSpool:
        return self

    def __exit__(
        self,
        _error_type: type[BaseException] | None,
        _error: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()


def persist_trace(request: TracePersistenceRequest) -> TraceBindingModel:
    events = _events(request.trace.get(request.event_field), request.output_root)
    status = _completion_status(request.status, request.output_root)
    output = request.output_root / "traces" / request.candidate_id / f"{request.planner}.trace-v3.jsonl"
    verification = write_trace_stream(
        TraceWriteRequest(output, request.planner, status, request.plan, len(events), CONTRACT_ID),
        events,
    )
    return trace_binding(request.repository_root, output, verification)


def validate_trace_binding(request: TraceValidationRequest) -> None:
    try:
        binding = TraceBindingModel.model_validate(request.binding_value)
        relative = Path(binding.path)
        path = request.repository_root / relative
        if confined(path, request.repository_root) != relative or binding.planner != request.expected_planner:
            raise CandidateCharacterizationError("characterization_trace_invalid", request.error_path)
        verification = verify_trace_stream(path)
    except (ValidationError, TraceStreamError, OSError) as error:
        raise CandidateCharacterizationError("characterization_trace_invalid", request.error_path) from error
    if verification.contract_id != request.expected_contract_id or binding != trace_binding(
        request.repository_root, path, verification
    ):
        raise CandidateCharacterizationError("characterization_trace_invalid", request.error_path)


def _events(value: PlannerJsonValue | None, path: Path) -> tuple[Mapping[str, PlannerJsonValue], ...]:
    if not isinstance(value, list) or any(not isinstance(event, dict) for event in value):
        raise CandidateCharacterizationError("characterization_trace_events_invalid", path)
    return tuple(event for event in value if isinstance(event, dict))


def _completion_status(status: str, path: Path) -> CompletionStatus:
    if status == "success_full_trace":
        return "success_full_trace"
    if status == "skipped_resource_limit":
        return "skipped_resource_limit"
    if status == "failed_no_plan_extracted":
        return "failed_no_plan_extracted"
    raise CandidateCharacterizationError("successful_trace_must_be_complete", path)


def trace_binding(repository_root: Path, path: Path, verification: TraceVerification) -> TraceBindingModel:
    return TraceBindingModel(
        completion_status=verification.completion_status,
        contract_sha256=verification.contract_sha256,
        final_event_sha256=verification.final_event_sha256,
        path=confined(path, repository_root).as_posix(),
        planner=verification.planner,
        record_count=verification.record_count,
        stream_sha256=verification.stream_sha256,
        success_plan_sha256=verification.success_plan_sha256,
    )
