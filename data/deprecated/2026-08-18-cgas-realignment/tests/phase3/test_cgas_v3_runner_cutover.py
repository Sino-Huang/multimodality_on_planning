from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.phase3 import cgas_trace_contract_v2, cgas_trace_contract_v3
from scripts.phase3.cgas_candidate_characterization_characterizer import CharacterizationRequest, _attach_trace
from scripts.phase3.cgas_candidate_characterization_contracts import (
    CandidateCharacterizationError,
    validate_approval,
)
from scripts.phase3.cgas_candidate_characterization_models import (
    ApprovedTraceModel,
    CheckpointModel,
    JsonObject,
    PlannerInputModel,
)
from scripts.phase3.cgas_candidate_characterization_traces import (
    TracePersistenceRequest,
    TraceValidationRequest,
    persist_trace,
    trace_binding,
    validate_trace_binding,
)
from scripts.phase3.cgas_trace_stream_v2 import TraceWriteRequest, verify_trace_stream, write_trace_stream

ROOT = Path(__file__).resolve().parents[2]
V2_EVIDENCE = ROOT / ".claude/evidence/cgas-production-p0"
V3_EVIDENCE = ROOT / ".claude/evidence/cgas-trace-contract-v3"
CHECKPOINT_1 = ROOT / "tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json"

V2_ARTIFACT_SHA256 = {
    "approved-trace-v2.json": "bd6909f99ce32484f3a33863cde936c0a3128935dabaf85da783870ae7ee26a8",
    "trace-v2-migration-packet.json": "f7b93250c8302e30e8c9e15b163f2f1d3b69a57d2e7de4c58fe02e4ec67e289b",
    "trace-v2-owner-approval.json": "566d9f2cc814972245f7353b37ceb1c138aef5aee37271767699dc1e9da59c05",
}


def _planner_input() -> PlannerInputModel:
    return PlannerInputModel(
        candidate_id="a" * 64,
        canonical_composition_signature="fixture-signature",
        first_raw_rank=0,
        goal_atoms=[["on", "b01", "b00"]],
        init_atoms=[["arm-empty"]],
        object_count=4,
        problem_pddl="(define (problem fixture) (:domain blocksworld-4ops))\n",
        raw_rank=0,
        schema_version="cgas_production_planner_input_v1",
        status="emitted",
    )


def test_approved_trace_model_pins_the_signed_v3_literals() -> None:
    # Given: the owner-published v3 approval record.
    contents = (V3_EVIDENCE / "approved-trace-v3.json").read_bytes()

    # When: the candidate runner's approval model parses it.
    approval = ApprovedTraceModel.model_validate_json(contents)

    # Then: the model exposes only the signed v3 contract surface.
    assert approval.contract_id == cgas_trace_contract_v3.CONTRACT_ID
    assert approval.contract_sha256 == cgas_trace_contract_v3.NEW_CONTRACT_SHA256
    assert approval.policy_sha256 == cgas_trace_contract_v3.POLICY_SHA256
    with pytest.raises(ValidationError):
        ApprovedTraceModel.model_validate_json((V2_EVIDENCE / "approved-trace-v2.json").read_bytes())


def test_candidate_approval_validates_the_signed_v3_neighbors(tmp_path: Path) -> None:
    # Given: the three independently signed v3 artifacts under their v3 names.
    approval = tmp_path / "approved-trace-v3.json"
    approval.write_bytes((V3_EVIDENCE / approval.name).read_bytes())
    for name in ("trace-v3-migration-packet.json", "trace-v3-owner-approval.json"):
        (tmp_path / name).write_bytes((V3_EVIDENCE / name).read_bytes())

    # When: the runner validates its approval boundary.
    verified, digest = validate_approval(approval)

    # Then: the exact signed v3 contract and approval bytes are returned.
    assert verified.contract_id == cgas_trace_contract_v3.CONTRACT_ID
    assert verified.contract_sha256 == cgas_trace_contract_v3.NEW_CONTRACT_SHA256
    assert digest == hashlib.sha256(approval.read_bytes()).hexdigest()


def test_candidate_approval_rejects_cross_contract_neighbors(tmp_path: Path) -> None:
    # Given: a valid v3 approval beside renamed, internally v2 packet and owner bytes.
    approval = tmp_path / "approved-trace-v3.json"
    approval.write_bytes((V3_EVIDENCE / approval.name).read_bytes())
    (tmp_path / "trace-v3-migration-packet.json").write_bytes(
        (V2_EVIDENCE / "trace-v2-migration-packet.json").read_bytes()
    )
    (tmp_path / "trace-v3-owner-approval.json").write_bytes(
        (V2_EVIDENCE / "trace-v2-owner-approval.json").read_bytes()
    )

    # When/Then: explicit contract binding rejects the mixed lineage.
    with pytest.raises(CandidateCharacterizationError, match="approved_trace_contract_invalid"):
        validate_approval(approval)


def test_signed_v2_artifacts_remain_byte_for_byte_unchanged() -> None:
    # Given/When: the immutable v2 approval lineage is read after the cutover.
    actual = {
        name: hashlib.sha256((V2_EVIDENCE / name).read_bytes()).hexdigest()
        for name in V2_ARTIFACT_SHA256
    }

    # Then: every signed byte sequence retains its historical digest.
    assert actual == V2_ARTIFACT_SHA256


def test_characterization_request_defaults_to_the_signed_v3_contract() -> None:
    # Given: a pure candidate input and its approved v3 artifact digest.
    request = CharacterizationRequest(_planner_input(), ROOT, ROOT / "tmp/smoke", "b" * 64)

    # Then: runner-facing defaults are the signed v3 contract and policy.
    assert request.trace_contract_sha256 == cgas_trace_contract_v3.NEW_CONTRACT_SHA256
    assert request.trace_policy_sha256 == cgas_trace_contract_v3.POLICY_SHA256


def test_trace_persistence_uses_a_new_explicit_v3_path_and_contract(tmp_path: Path) -> None:
    # Given: one pure BFS event persisted through the characterization trace adapter.
    binding = persist_trace(
        TracePersistenceRequest(
            tmp_path,
            tmp_path / "characterized",
            "a" * 64,
            "bfs",
            "failed_no_plan_extracted",
            (),
            {"expansions": [{"decision": "expand", "state_id": "fixture"}]},
            "expansions",
        )
    )

    # When: the bound stream is independently verified.
    path = tmp_path / binding.path
    verified = verify_trace_stream(path)

    # Then: neither the path nor trailer relies on v2 naming or event-field inference.
    assert path.name == "bfs.trace-v3.jsonl"
    assert verified.contract_id == cgas_trace_contract_v3.CONTRACT_ID
    assert verified.contract_sha256 == cgas_trace_contract_v3.NEW_CONTRACT_SHA256


def test_characterization_rows_bind_v3_streams_under_a_v3_key(tmp_path: Path) -> None:
    # Given: a verified v3-shaped trace binding.
    output = tmp_path / "trace.jsonl"
    verification = write_trace_stream(
        TraceWriteRequest(
            output,
            "bfs",
            "failed_no_plan_extracted",
            (),
            1,
            cgas_trace_contract_v3.CONTRACT_ID,
        ),
        ({"decision": "expand", "state_id": "fixture"},),
    )
    binding = trace_binding(tmp_path, output, verification)
    row: JsonObject = {"bfs": {}}

    # When: the characterizer attaches the stream.
    _attach_trace(row, "bfs", binding)

    # Then: the machine-consumed key names v3 explicitly.
    assert row == {"bfs": {"trace_v3": binding.model_dump(mode="json")}}


def test_trace_validation_rejects_a_v2_stream_at_the_v3_boundary(tmp_path: Path) -> None:
    # Given: a valid v2 stream and matching binding bytes.
    output = tmp_path / "bfs.trace-v2.jsonl"
    verification = write_trace_stream(
        TraceWriteRequest(output, "bfs", "failed_no_plan_extracted", (), 1),
        ({"decision": "expand", "state_id": "fixture"},),
    )
    binding = trace_binding(tmp_path, output, verification)

    # When/Then: a v3 checkpoint boundary rejects the valid stream from another contract.
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


def test_checkpoint_1_model_and_signed_v2_lineage_remain_compatible() -> None:
    # Given: the immutable production checkpoint created under trace v2.
    contents = CHECKPOINT_1.read_bytes()

    # When: the current checkpoint model parses the historical bytes.
    checkpoint = CheckpointModel.model_validate_json(contents)

    # Then: the exact checkpoint and approval lineage remain readable and unchanged.
    assert hashlib.sha256(contents).hexdigest() == "fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853"
    assert checkpoint.approved_trace_sha256 == cgas_trace_contract_v3.TRACE_V2_APPROVAL_SHA256
    assert checkpoint.approved_trace_contract_sha256 == cgas_trace_contract_v2.NEW_CONTRACT_SHA256
