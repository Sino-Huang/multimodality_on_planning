from __future__ import annotations

from pathlib import Path

import pytest
from cgas_candidate_characterization_support import execution_fixture, request_fixture

from scripts.phase3 import cgas_trace_contract_v3
from scripts.phase3.cgas_candidate_characterization import run_next_round
from scripts.phase3.cgas_candidate_characterization_characterizer import CharacterizationRequest
from scripts.phase3.cgas_candidate_characterization_contracts import CandidateCharacterizationError
from scripts.phase3.cgas_candidate_characterization_models import JsonObject
from scripts.phase3.cgas_candidate_characterization_runner import RunnerExecution
from scripts.phase3.cgas_candidate_characterization_traces import (
    TraceValidationRequest,
    trace_binding,
    validate_trace_binding,
)
from scripts.phase3.cgas_trace_stream_v2 import TraceWriteRequest, verify_trace_stream, write_trace_stream


def test_gate0b_verifies_isolated_v3_checkpoint_and_all_streams(tmp_path: Path) -> None:
    # Given: a complete round-one characterization in an isolated v3 root.
    request = request_fixture(tmp_path)
    report = run_next_round(request, execution_fixture(capacities={4: 1, 8: 1, 12: 1}).dependencies())

    # When: the reusable Gate 0b verifier inspects the committed root.
    from scripts.phase3.cgas_gate0b_verifier import verify_gate0b_round

    verified = verify_gate0b_round(
        tmp_path,
        request.output,
        request.approved_trace_contract,
        request.candidate_config,
        report.checkpoint_path,
    )

    # Then: checkpoint, candidate, stream, record, and byte counts are explicit.
    assert verified.round == 1
    assert verified.candidate_count == 3
    assert verified.stream_count == 6
    assert verified.total_stream_bytes == sum(item.byte_count for item in verified.streams)
    assert all(item.contract_id == cgas_trace_contract_v3.CONTRACT_ID for item in verified.streams)
    assert all(item.contract_sha256 == cgas_trace_contract_v3.NEW_CONTRACT_SHA256 for item in verified.streams)


def test_gate0b_rejects_mixed_v2_v3_stream_binding(tmp_path: Path) -> None:
    # Given: a v2 stream and a binding presented at a v3 checkpoint boundary.
    output = tmp_path / "bfs.trace-v2.jsonl"
    verification = write_trace_stream(
        TraceWriteRequest(output, "bfs", "failed_no_plan_extracted", (), 1),
        ({"decision": "expand", "state_id": "fixture"},),
    )
    binding = trace_binding(tmp_path, output, verification)

    # When/Then: the explicit contract binding fails closed.
    with pytest.raises(CandidateCharacterizationError, match="characterization_trace_invalid"):
        validate_trace_binding(
            TraceValidationRequest(
                tmp_path,
                binding.model_dump(mode="json"),
                "bfs",
                tmp_path / "checkpoint.json",
                cgas_trace_contract_v3.CONTRACT_ID,
            )
        )


def test_stream_contract_comes_from_signed_trailer_not_filename_or_event_fields(tmp_path: Path) -> None:
    # Given: a v3 stream deliberately using a v2-looking filename and event payload.
    output = tmp_path / "bfs.trace-v2.jsonl"
    write_trace_stream(
        TraceWriteRequest(output, "bfs", "failed_no_plan_extracted", (), 1, cgas_trace_contract_v3.CONTRACT_ID),
        ({"contract_id": "cgas_trace_contract_v2", "state_id": "fixture"},),
    )

    # When: the stream verifier reads the signed trailer.
    verification = verify_trace_stream(output)

    # Then: explicit trailer binding wins over path and event-field heuristics.
    assert verification.contract_id == cgas_trace_contract_v3.CONTRACT_ID
    assert verification.contract_sha256 == cgas_trace_contract_v3.NEW_CONTRACT_SHA256


def test_resume_reuses_verified_v3_streams_without_byte_drift(tmp_path: Path) -> None:
    # Given: a committed isolated v3 round and immutable snapshots of its artifacts.
    request = request_fixture(tmp_path)
    execution = execution_fixture(capacities={4: 1, 8: 1, 12: 1})
    first = run_next_round(request, execution.dependencies())
    checkpoint_before = first.checkpoint_path.read_bytes()
    stream_bytes_before = {
        path: path.read_bytes()
        for path in sorted((request.output / "traces").rglob("*.jsonl"))
    }

    # When: the same round is replayed with a characterizer that would fail if called.
    def fail_characterization(_request: CharacterizationRequest) -> JsonObject:
        raise AssertionError("resume replaced a verified stream")

    replay = run_next_round(
        request,
        RunnerExecution(
            execution.load,
            fail_characterization,
            execution.capacity,
            execution.fault,
        ),
    )

    # Then: replay is read-only and every v3 byte remains identical.
    assert replay.read_only
    assert first.checkpoint_path.read_bytes() == checkpoint_before
    assert stream_bytes_before == {
        path: path.read_bytes()
        for path in sorted((request.output / "traces").rglob("*.jsonl"))
    }
