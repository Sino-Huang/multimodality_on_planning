from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypeAlias

from . import cgas_trace_contract_v2, cgas_trace_contract_v3
from .cgas_trace_v2_json import TraceJsonError, canonical_json_bytes, parse_canonical_json_line
from .local_planner_types import JSONValue

Planner: TypeAlias = Literal["bfs", "iw"]
ContractId: TypeAlias = Literal["cgas_trace_contract_v2", "cgas_trace_contract_v3"]
CompletionStatus: TypeAlias = Literal["success_full_trace", "skipped_resource_limit", "failed_no_plan_extracted"]


@dataclass(frozen=True, slots=True)
class _TraceContractBinding:
    contract_id: ContractId
    contract_sha256: str
    bfs_max_records: int
    iw_max_records: int
    max_event_bytes: int | None


_V2_BINDING: Final = _TraceContractBinding(
    cgas_trace_contract_v2.CONTRACT_ID,
    cgas_trace_contract_v2.NEW_CONTRACT_SHA256,
    cgas_trace_contract_v2.BFS_MAX_RECORDS,
    cgas_trace_contract_v2.IW_MAX_RECORDS,
    None,
)
_V3_BINDING: Final = _TraceContractBinding(
    cgas_trace_contract_v3.CONTRACT_ID,
    cgas_trace_contract_v3.NEW_CONTRACT_SHA256,
    cgas_trace_contract_v3.BFS_MAX_RECORDS,
    cgas_trace_contract_v3.IW_MAX_RECORDS,
    cgas_trace_contract_v3.MAX_EVENT_BYTES,
)
_CONTRACT_BINDINGS: Final = {
    _V2_BINDING.contract_id: _V2_BINDING,
    _V3_BINDING.contract_id: _V3_BINDING,
}


@dataclass(frozen=True, slots=True)
class TraceStreamError(RuntimeError):
    rule: str
    path: Path

    def __str__(self) -> str:
        return f"{self.rule}: {self.path}"


@dataclass(frozen=True, slots=True)
class TraceWriteRequest:
    output: Path
    planner: Planner
    completion_status: CompletionStatus
    success_plan: tuple[str, ...]
    expected_record_count: int
    contract_id: ContractId = cgas_trace_contract_v2.CONTRACT_ID


@dataclass(frozen=True, slots=True)
class TraceVerification:
    planner: Planner
    completion_status: CompletionStatus
    record_count: int
    final_event_sha256: str | None
    stream_sha256: str
    success_plan_sha256: str | None
    contract_sha256: str
    contract_id: ContractId = cgas_trace_contract_v2.CONTRACT_ID


def write_trace_stream(request: TraceWriteRequest, events: Iterable[Mapping[str, JSONValue]]) -> TraceVerification:
    binding = _binding(request.contract_id, request.output)
    _validate_request(request, binding)
    request.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{request.output.name}-", dir=request.output.parent)
    temporary = Path(temporary_name)
    stream_digest = hashlib.sha256()
    previous_sha256: str | None = None
    record_count = 0
    try:
        with os.fdopen(descriptor, "wb") as handle:
            for sequence, event in enumerate(events):
                preimage = {
                    "event": dict(event),
                    "previous_event_sha256": previous_sha256,
                    "record_type": "event",
                    "sequence": sequence,
                }
                current_sha256 = hashlib.sha256(_canonical_bytes(preimage, request.output)).hexdigest()
                line = _canonical_bytes({"current_event_sha256": current_sha256, **preimage}, request.output) + b"\n"
                if binding.max_event_bytes is not None and len(line) > binding.max_event_bytes:
                    raise TraceStreamError("trace_v3_record_size_exceeded", request.output)
                handle.write(line)
                stream_digest.update(line)
                previous_sha256 = current_sha256
                record_count += 1
                if record_count + 1 > _record_bound(request.planner, binding):
                    raise TraceStreamError("trace_v2_record_bound_exceeded", request.output)
            if record_count != request.expected_record_count:
                raise TraceStreamError("trace_v2_record_count_mismatch", request.output)
            success_plan_sha256 = _success_plan_digest(request)
            trailer = {
                "completion_status": request.completion_status,
                "contract_id": binding.contract_id,
                "contract_sha256": binding.contract_sha256,
                "final_event_sha256": previous_sha256,
                "planner": request.planner,
                "record_count": record_count,
                "record_type": "trailer",
                "stream_sha256": stream_digest.hexdigest(),
                "success_plan_sha256": success_plan_sha256,
            }
            handle.write(_canonical_bytes(trailer, request.output) + b"\n")
            handle.flush()
            try:
                _fsync_descriptor(handle.fileno())
            except OSError as error:
                raise TraceStreamError("trace_v2_fsync_failed", request.output) from error
        verification = verify_trace_stream(temporary)
        _install_stream(temporary, request.output, verification)
        return verification
    except TraceStreamError:
        raise
    except OSError as error:
        raise TraceStreamError("trace_v2_write_failed", request.output) from error
    finally:
        temporary.unlink(missing_ok=True)


def verify_trace_stream(path: Path) -> TraceVerification:
    stream_digest = hashlib.sha256()
    previous_sha256: str | None = None
    record_count = 0
    trailer: dict[str, JSONValue] | None = None
    largest_event_line = 0
    try:
        with path.open("rb") as handle:
            for line in handle:
                if len(line) > 16 * 1024 * 1024 or not line.endswith(b"\n"):
                    raise TraceStreamError("trace_v2_noncanonical_jsonl", path)
                record = _parse_line(line, path)
                record_type = record.get("record_type")
                if record_type == "trailer":
                    if trailer is not None:
                        raise TraceStreamError("trace_v2_trailer_not_final", path)
                    trailer = record
                    continue
                if trailer is not None:
                    raise TraceStreamError("trace_v2_trailer_not_final", path)
                if record_type != "event":
                    raise TraceStreamError("trace_v2_noncanonical_jsonl", path)
                _verify_event(record, record_count, previous_sha256, path)
                current = record["current_event_sha256"]
                if not isinstance(current, str):
                    raise TraceStreamError("trace_v2_hash_chain_mismatch", path)
                previous_sha256 = current
                record_count += 1
                largest_event_line = max(largest_event_line, len(line))
                stream_digest.update(line)
    except OSError as error:
        raise TraceStreamError("trace_v2_read_failed", path) from error
    if trailer is None:
        raise TraceStreamError("trace_v2_missing_trailer", path)
    return _verify_trailer(trailer, record_count, previous_sha256, stream_digest.hexdigest(), largest_event_line, path)


def _validate_request(request: TraceWriteRequest, binding: _TraceContractBinding) -> None:
    if request.output.suffix != ".jsonl":
        raise TraceStreamError("trace_v2_uncompressed_jsonl_required", request.output)
    if request.expected_record_count < 0 or request.expected_record_count + 1 > _record_bound(request.planner, binding):
        raise TraceStreamError("trace_v2_record_bound_exceeded", request.output)
    if request.completion_status == "success_full_trace":
        return
    if request.success_plan:
        raise TraceStreamError("trace_v2_failure_plan_present", request.output)


def _success_plan_digest(request: TraceWriteRequest) -> str | None:
    if request.completion_status != "success_full_trace":
        return None
    plan = json.dumps(request.success_plan, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(plan).hexdigest()


def _verify_event(record: dict[str, JSONValue], sequence: int, previous: str | None, path: Path) -> None:
    if set(record) != {"current_event_sha256", "event", "previous_event_sha256", "record_type", "sequence"}:
        raise TraceStreamError("trace_v2_noncanonical_jsonl", path)
    current = record.get("current_event_sha256")
    preimage = dict(record)
    preimage.pop("current_event_sha256")
    expected = hashlib.sha256(_canonical_bytes(preimage, path)).hexdigest()
    if record.get("sequence") != sequence or record.get("previous_event_sha256") != previous or current != expected:
        raise TraceStreamError("trace_v2_hash_chain_mismatch", path)


def _verify_trailer(
    trailer: dict[str, JSONValue],
    record_count: int,
    final_event_sha256: str | None,
    stream_sha256: str,
    largest_event_line: int,
    path: Path,
) -> TraceVerification:
    expected_keys = {
        "completion_status",
        "contract_id",
        "contract_sha256",
        "final_event_sha256",
        "planner",
        "record_count",
        "record_type",
        "stream_sha256",
        "success_plan_sha256",
    }
    if set(trailer) != expected_keys:
        raise TraceStreamError("trace_v2_trailer_mismatch", path)
    contract_id = trailer.get("contract_id")
    binding = _binding(contract_id, path)
    planner = _planner(trailer.get("planner"), path)
    completion_status = _completion_status(trailer.get("completion_status"), path)
    expected_values = {
        "contract_id": binding.contract_id,
        "contract_sha256": binding.contract_sha256,
        "final_event_sha256": final_event_sha256,
        "record_count": record_count,
        "stream_sha256": stream_sha256,
    }
    if any(trailer.get(key) != value for key, value in expected_values.items()):
        raise TraceStreamError("trace_v2_trailer_mismatch", path)
    success_plan_sha256 = trailer.get("success_plan_sha256")
    if completion_status == "success_full_trace":
        if not _is_digest(success_plan_sha256):
            raise TraceStreamError("trace_v2_success_plan_digest_missing", path)
    elif success_plan_sha256 is not None:
        raise TraceStreamError("trace_v2_trailer_mismatch", path)
    if binding.max_event_bytes is not None and largest_event_line > binding.max_event_bytes:
        raise TraceStreamError("trace_v3_record_size_exceeded", path)
    if record_count + 1 > _record_bound(planner, binding):
        raise TraceStreamError("trace_v2_record_bound_exceeded", path)
    return TraceVerification(
        planner, completion_status, record_count, final_event_sha256, stream_sha256,
        success_plan_sha256 if isinstance(success_plan_sha256, str) else None,
        binding.contract_sha256,
        binding.contract_id,
    )


def _parse_line(line: bytes, path: Path) -> dict[str, JSONValue]:
    try:
        return parse_canonical_json_line(line, path, "trace_v2_noncanonical_jsonl")
    except TraceJsonError as error:
        raise TraceStreamError(error.rule, error.path) from error


def _canonical_bytes(value: JSONValue, path: Path) -> bytes:
    try:
        return canonical_json_bytes(value, path, "trace_v2_noncanonical_jsonl")
    except TraceJsonError as error:
        raise TraceStreamError(error.rule, error.path) from error


def _install_stream(temporary: Path, output: Path, verification: TraceVerification) -> None:
    installed = False
    try:
        directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            fcntl.flock(directory, fcntl.LOCK_EX)
            if output.exists() or output.is_symlink():
                if output.is_symlink() or verify_trace_stream(output) != verification:
                    raise TraceStreamError("trace_v2_output_collision", output)
                return
            os.link(temporary, output, follow_symlinks=False)
            installed = True
            _fsync_descriptor(directory)
        except OSError as error:
            if installed:
                try:
                    output.unlink()
                    _fsync_descriptor(directory)
                except OSError as rollback_error:
                    raise TraceStreamError("trace_v2_publication_failed", output) from rollback_error
            raise TraceStreamError("trace_v2_publication_failed", output) from error
        finally:
            os.close(directory)
    except OSError as error:
        raise TraceStreamError("trace_v2_publication_failed", output) from error


_fsync_descriptor: Final = os.fsync


def _binding(contract_id: object, path: Path) -> _TraceContractBinding:
    if not isinstance(contract_id, str):
        raise TraceStreamError("trace_v2_contract_unsupported", path)
    binding = _CONTRACT_BINDINGS.get(contract_id)
    if binding is None:
        raise TraceStreamError("trace_v2_contract_unsupported", path)
    return binding


def _record_bound(planner: str, binding: _TraceContractBinding) -> int:
    if planner == "bfs":
        return binding.bfs_max_records
    if planner == "iw":
        return binding.iw_max_records
    raise TraceStreamError("trace_v2_planner_unsupported", Path(planner))


def _planner(value: JSONValue, path: Path) -> Planner:
    if value == "bfs":
        return "bfs"
    if value == "iw":
        return "iw"
    raise TraceStreamError("trace_v2_planner_unsupported", path)


def _completion_status(value: JSONValue, path: Path) -> CompletionStatus:
    if value == "success_full_trace":
        return "success_full_trace"
    if value == "skipped_resource_limit":
        return "skipped_resource_limit"
    if value == "failed_no_plan_extracted":
        return "failed_no_plan_extracted"
    raise TraceStreamError("trace_v2_completion_status_unsupported", path)


def _is_digest(value: JSONValue) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)
