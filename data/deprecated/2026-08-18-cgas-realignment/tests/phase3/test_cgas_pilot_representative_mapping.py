from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.phase3.cgas_candidate_accounting import PlannerInput, planner_input_record
from scripts.phase3.cgas_candidate_space import build_candidate
from scripts.phase3.cgas_pilot_expansion_index import state_sha256


def _jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _source(
    object_count: int,
    raw_rank: int,
    atoms: list[str],
    *,
    row_id: str,
    role: str = "train",
    planner: str = "bfs",
    replay: bool = False,
    sequence: int = 0,
) -> dict[str, object]:
    candidate = build_candidate(object_count, raw_rank)
    planner_input = PlannerInput(
        object_count,
        raw_rank,
        "emitted",
        candidate.candidate_id,
        raw_rank,
        candidate,
    )
    source = planner_input_record(planner_input)
    source_digest = hashlib.sha256(
        (json.dumps(source, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode()
    ).hexdigest()
    digest = state_sha256(atoms)
    return {
        "schema_version": "cgas_phase3_pilot_expansion_index_v1",
        "row_id": row_id,
        "candidate_id": candidate.candidate_id,
        "instance_id": candidate.candidate_id,
        "object_count": object_count,
        "raw_rank": raw_rank,
        "role": role,
        "planner": planner,
        "source_record_sha256": source_digest,
        "state_atoms": atoms,
        "state_sha256": digest,
        "event_sequence": sequence,
        "event_sha256": hashlib.sha256(f"event-{row_id}".encode()).hexdigest(),
        "trace_path": f"traces/{row_id}.jsonl",
        "trace_stream_sha256": hashlib.sha256(f"stream-{row_id}".encode()).hexdigest(),
        "trace_contract_id": "cgas_trace_contract_v3",
        "trace_contract_sha256": hashlib.sha256(b"contract").hexdigest(),
        "replay_plan_member": replay,
        "replay_step_index": 0 if replay else None,
    }


def test_policy_prefers_replay_then_held_out_and_is_order_independent(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_representative_mapping import build_representative_mapping

    atoms = ["(arm-empty)", "(clear b00)", "(on-table b00)"]
    digest = state_sha256(atoms)
    request = tmp_path / "request.jsonl"
    _jsonl(request, [{"state_atoms": atoms, "state_sha256": digest, "partitions": ["train|1|bfs"]}])
    train = _source(1, 0, atoms, row_id="train")
    held_out = _source(2, 0, atoms, row_id="held", role="held_out_calibration")
    replay = _source(2, 1, atoms, row_id="replay", replay=True)
    first_index = tmp_path / "first-index.jsonl"
    second_index = tmp_path / "second-index.jsonl"
    _jsonl(first_index, [train, replay, held_out])
    _jsonl(second_index, [held_out, train, replay])

    first = build_representative_mapping(request, first_index, tmp_path / "first")
    second = build_representative_mapping(request, second_index, tmp_path / "second")
    first_row = json.loads(first.mapping_path.read_text())
    second_row = json.loads(second.mapping_path.read_text())
    assert first_row["representative"]["row_id"] == "replay"
    assert second_row["representative"]["row_id"] == "replay"
    assert first_row["selection"]["policy_id"] == "replay_then_held_out_then_stable_source_v1"


def test_mapping_preserves_request_order_and_binds_inputs(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_representative_mapping import build_representative_mapping

    atoms_a = ["(arm-empty)", "(clear b00)", "(on-table b00)"]
    atoms_b = ["(holding b00)"]
    requests = [
        {"state_atoms": atoms_b, "state_sha256": state_sha256(atoms_b), "partitions": ["train|1|bfs"]},
        {"state_atoms": atoms_a, "state_sha256": state_sha256(atoms_a), "partitions": ["train|1|bfs"]},
    ]
    request = tmp_path / "request.jsonl"
    index = tmp_path / "index.jsonl"
    _jsonl(request, requests)
    _jsonl(index, [_source(1, 0, atoms_a, row_id="a"), _source(1, 0, atoms_b, row_id="b")])
    result = build_representative_mapping(request, index, tmp_path / "output")
    rows = [json.loads(line) for line in result.mapping_path.read_text().splitlines()]
    assert [row["state_sha256"] for row in rows] == [row["state_sha256"] for row in requests]
    assert rows[0]["bindings"]["request_sha256"] == hashlib.sha256(request.read_bytes()).hexdigest()
    assert rows[0]["bindings"]["expansion_index_sha256"] == hashlib.sha256(index.read_bytes()).hexdigest()
    assert result.count == 2


def test_mapping_rejects_missing_state_and_source_drift(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_representative_mapping import RepresentativeMappingError, build_representative_mapping

    atoms = ["(arm-empty)", "(clear b00)", "(on-table b00)"]
    request = tmp_path / "request.jsonl"
    index = tmp_path / "index.jsonl"
    _jsonl(request, [{"state_atoms": atoms, "state_sha256": state_sha256(atoms), "partitions": []}])
    _jsonl(index, [])
    with pytest.raises(RepresentativeMappingError, match="representative_source_missing"):
        build_representative_mapping(request, index, tmp_path / "missing")
    row = _source(1, 0, atoms, row_id="drift")
    row["source_record_sha256"] = "0" * 64
    _jsonl(index, [row])
    with pytest.raises(RepresentativeMappingError, match="representative_source_record_mismatch"):
        build_representative_mapping(request, index, tmp_path / "drift")


def test_mapping_publication_is_idempotent_and_collision_safe(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_expansion_index import PilotExpansionIndexError
    from scripts.phase3.cgas_pilot_representative_mapping import build_representative_mapping

    atoms = ["(arm-empty)", "(clear b00)", "(on-table b00)"]
    request = tmp_path / "request.jsonl"
    index = tmp_path / "index.jsonl"
    _jsonl(request, [{"state_atoms": atoms, "state_sha256": state_sha256(atoms), "partitions": []}])
    _jsonl(index, [_source(1, 0, atoms, row_id="row")])
    output = tmp_path / "output"
    first = build_representative_mapping(request, index, output)
    second = build_representative_mapping(request, index, output)
    assert first.mapping_sha256 == second.mapping_sha256
    first.mapping_path.write_text("changed", encoding="utf-8")
    with pytest.raises(PilotExpansionIndexError, match="pilot_expansion_publication_collision"):
        build_representative_mapping(request, index, output)


def test_mapping_rejects_noncanonical_duplicate_atoms(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_representative_mapping import RepresentativeMappingError, build_representative_mapping

    request = tmp_path / "request.jsonl"
    index = tmp_path / "index.jsonl"
    _jsonl(request, [{"state_atoms": ["(a)", "(a)"], "state_sha256": "0" * 64, "partitions": []}])
    _jsonl(index, [])
    with pytest.raises(
        RepresentativeMappingError, match="representative_request_state_atoms_noncanonical"
    ):
        build_representative_mapping(request, index, tmp_path / "output")
