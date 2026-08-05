from __future__ import annotations

import json
from pathlib import Path

import pytest
from cgas_candidate_characterization_support import execution_fixture, request_fixture
from pydantic import TypeAdapter

from scripts.phase3 import cgas_candidate_characterization_runner
from scripts.phase3.cgas_candidate_characterization import CandidateCharacterizationError, run_next_round
from scripts.phase3.cgas_candidate_characterization_characterizer import CharacterizationRequest
from scripts.phase3.cgas_candidate_characterization_models import JsonObject, SelectorBindingModel
from scripts.phase3.cgas_candidate_characterization_runner import RunnerExecution
from scripts.phase3.cgas_trace_stream_v2 import verify_trace_stream


def _canonical(record: JsonObject) -> bytes:
    return json.dumps(record, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode() + b"\n"


def test_historical_replay_rejects_different_valid_candidate_config(tmp_path: Path) -> None:
    # Given: a committed round and a different schema-valid candidate configuration.
    request = request_fixture(tmp_path)
    run_next_round(request, execution_fixture().dependencies())
    config = json.loads(request.candidate_config.read_bytes())
    config["streams"][0]["raw_quota"] = 191
    request.candidate_config.write_bytes(_canonical(config))

    # When/Then: replay compares the current immutable input before returning read-only success.
    with pytest.raises(CandidateCharacterizationError, match="candidate_config_binding_invalid"):
        run_next_round(request, execution_fixture().dependencies())


def test_historical_replay_rejects_selector_policy_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a committed round and a current selector binding that differs from its checkpoint.
    request = request_fixture(tmp_path)
    run_next_round(request, execution_fixture().dependencies())
    changed = SelectorBindingModel(config_sha256="1" * 64, implementation_sha256="2" * 64)
    monkeypatch.setattr(cgas_candidate_characterization_runner, "selector_binding", lambda: changed)

    # When/Then: replay cannot bypass the unchanged-selector contract.
    with pytest.raises(CandidateCharacterizationError, match="selector_binding_invalid"):
        run_next_round(request, execution_fixture().dependencies())


def test_historical_replay_rejects_alternate_valid_approval(tmp_path: Path) -> None:
    # Given: a committed round and a byte-valid approval carrying plausible IDs but different owner bytes.
    request = request_fixture(tmp_path)
    run_next_round(request, execution_fixture().dependencies())
    approval = json.loads(request.approved_trace_contract.read_bytes())
    approval["approved_at"] = "2026-08-03T14:56:49Z"
    request.approved_trace_contract.write_bytes(_canonical(approval))

    # When/Then: exact canonical owner approval binding is required before replay.
    with pytest.raises(CandidateCharacterizationError, match="approved_trace_contract_invalid"):
        run_next_round(request, execution_fixture().dependencies())


@pytest.mark.parametrize(
    ("field", "replacement", "code"),
    (
        ("receipt_sha256", "not-a-digest", "checkpoint_invalid"),
        ("start_rank", 1, "checkpoint_range_invalid"),
        ("end_rank", 189, "checkpoint_range_invalid"),
    ),
)
def test_checkpoint_rejects_malformed_or_discontinuous_range(
    tmp_path: Path,
    field: str,
    replacement: str | int,
    code: str,
) -> None:
    # Given: a canonical checkpoint whose first range no longer binds its cursor/accounting slice.
    request = request_fixture(tmp_path)
    report = run_next_round(request, execution_fixture().dependencies())
    checkpoint = json.loads(report.checkpoint_path.read_bytes())
    checkpoint["ranges"][0][field] = replacement
    report.checkpoint_path.write_bytes(_canonical(checkpoint))

    # When/Then: chain scanning rejects the checkpoint before read-only acceptance.
    with pytest.raises(CandidateCharacterizationError, match=code):
        run_next_round(request, execution_fixture().dependencies())


def test_checkpoint_binds_verified_bfs_and_iw_trace_streams(tmp_path: Path) -> None:
    # Given: one complete characterization round.
    request = request_fixture(tmp_path)

    # When: the checkpoint is accepted.
    report = run_next_round(request, execution_fixture().dependencies())
    checkpoint = json.loads(report.checkpoint_path.read_bytes())
    rows = tuple(
        TypeAdapter(JsonObject).validate_json(line)
        for line in checkpoint["characterization"]["canonical_jsonl"].splitlines()
    )

    # Then: every planner row binds a repository-relative stream that verifies exactly.
    for row in rows:
        for planner_name in ("bfs", "iw_width_1"):
            planner = row[planner_name]
            assert isinstance(planner, dict)
            binding = planner["trace_v2"]
            assert isinstance(binding, dict)
            trace_path = request.repository_root / str(binding["path"])
            verified = verify_trace_stream(trace_path)
            assert verified.stream_sha256 == binding["stream_sha256"]
            assert verified.final_event_sha256 == binding["final_event_sha256"]


def test_replay_rejects_tampered_bound_trace_stream(tmp_path: Path) -> None:
    # Given: an accepted checkpoint whose first bound stream is changed afterward.
    request = request_fixture(tmp_path)
    report = run_next_round(request, execution_fixture().dependencies())
    checkpoint = json.loads(report.checkpoint_path.read_bytes())
    row = json.loads(checkpoint["characterization"]["canonical_jsonl"].splitlines()[0])
    trace_path = request.repository_root / row["bfs"]["trace_v2"]["path"]
    trace_path.write_bytes(trace_path.read_bytes().replace(b'"record_type":"trailer"', b'"record_type":"changed"'))

    # When/Then: chain validation refuses read-only success for the stale checkpoint binding.
    with pytest.raises(CandidateCharacterizationError, match="characterization_trace_invalid"):
        run_next_round(request, execution_fixture().dependencies())


def test_characterization_rejects_changed_planner_input_digest(tmp_path: Path) -> None:
    # Given: a characterizer that returns valid traces but claims a different planner-input source.
    execution = execution_fixture()

    def changed_source(request: CharacterizationRequest) -> JsonObject:
        row = execution.characterize(request)
        row["source_identity"] = {"source_record_sha256": "0" * 64}
        return row

    dependencies = RunnerExecution(execution.load, changed_source, execution.capacity, execution.fault)

    # When/Then: exact source bytes are checked before checkpoint publication.
    with pytest.raises(CandidateCharacterizationError, match="characterization_source_binding_invalid"):
        run_next_round(request_fixture(tmp_path), dependencies)
