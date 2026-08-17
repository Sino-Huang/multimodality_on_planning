from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cgas_candidate_characterization_support import (
    execution_fixture as _execution,
)
from cgas_candidate_characterization_support import (
    load_checkpoint as _checkpoint,
)
from cgas_candidate_characterization_support import (
    request_fixture as _request,
)
from cgas_candidate_characterization_support import (
    write_feedback as _feedback,
)

from scripts.phase3.cgas_candidate_characterization import (
    CandidateCharacterizationError,
    run_next_round,
)
from scripts.phase3.cgas_candidate_characterization_ranges import (
    CandidateBatch,
    RangeLoadRequest,
)
from scripts.phase3.cgas_candidate_characterization_runner import (
    FaultPoint,
    RunnerExecution,
)


def test_checkpoint_feedback_cursor_ownership_and_emitted_only(tmp_path: Path) -> None:
    # Given: exact quota batches with one emitted row and only accounting-only duplicates per stream.
    execution = _execution()
    request = _request(tmp_path)

    # When: Todo 3 creates the initial reservoir checkpoint.
    report = run_next_round(request, execution.dependencies())

    # Then: Todo 3 alone advances exact cursors and invokes planners only for emitted candidate IDs.
    assert [(call.object_count, call.start_rank, call.count) for call in execution.calls] == [
        (4, 0, 190),
        (8, 0, 198),
        (12, 0, 93),
    ]
    assert execution.characterized == [
        hashlib.sha256(f"{object_count}:0".encode()).hexdigest() for object_count in (4, 8, 12)
    ]
    checkpoint = _checkpoint(report.checkpoint_path)
    assert [(stream.object_count, stream.next_raw_rank) for stream in checkpoint.streams] == [
        (4, 190),
        (8, 198),
        (12, 93),
    ]
    assert checkpoint.accounting.row_count == 481
    assert checkpoint.characterization.row_count == 3
    assert checkpoint.reservoir.row_count == 3
    assert not (request.candidate_root / "current.json").exists()


def test_approval_precedes_every_side_effect(tmp_path: Path) -> None:
    # Given: a copied approval with one exact binding changed.
    request = _request(tmp_path)
    approval = json.loads(request.approved_trace_contract.read_bytes())
    approval["policy_sha256"] = "0" * 64
    request.approved_trace_contract.write_bytes(
        json.dumps(approval, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )

    # When: initial round validation rejects the approval.
    with pytest.raises(CandidateCharacterizationError, match="approved_trace_contract_invalid"):
        run_next_round(request, _execution().dependencies())

    # Then: no characterization output root exists.
    assert not request.output.exists()


@pytest.mark.parametrize("fault", tuple(FaultPoint))
def test_dual_commit_fault_preserves_cursor(tmp_path: Path, fault: FaultPoint) -> None:
    # Given: a committed round one and valid exact selector-failure feedback.
    baseline = _execution()
    request = _request(tmp_path)
    first = run_next_round(request, baseline.dependencies())
    current = request.output / "current.json"
    current_before = current.read_bytes()
    checkpoint_before = first.checkpoint_path.read_bytes()
    streams_before = _checkpoint(first.checkpoint_path).streams
    feedback = tmp_path / "selector_attempt_000001.json"
    _feedback(feedback, first.checkpoint_path)
    second = _request(tmp_path, 2, checkpoint=first.checkpoint_path, feedback=feedback)

    # When: each atomic accounting/characterization/checkpoint boundary fails.
    with pytest.raises(OSError, match="injected"):
        run_next_round(second, _execution(fault=fault).dependencies())

    # Then: the canonical current index and its committed checkpoint remain byte-identical.
    assert current.read_bytes() == current_before
    assert first.checkpoint_path.read_bytes() == checkpoint_before
    assert _checkpoint(first.checkpoint_path).streams == streams_before


def test_torn_index_recovers_and_historical_replay_does_not_roll_back(tmp_path: Path) -> None:
    # Given: one valid checkpoint with a torn derived index.
    request = _request(tmp_path)
    first = run_next_round(request, _execution().dependencies())
    current = request.output / "current.json"
    current.write_bytes(b"{torn")

    # When: the exact historical round is replayed.
    replay = run_next_round(request, _execution().dependencies())
    repaired = current.read_bytes()
    replay_again = run_next_round(request, _execution().dependencies())

    # Then: recovery resolves the unique chain once and replay never rewrites or rolls the index backward.
    assert replay.read_only and replay_again.read_only
    assert replay.checkpoint_path == first.checkpoint_path
    assert current.read_bytes() == repaired


def test_feedback_digest_and_filename_are_exact(tmp_path: Path) -> None:
    # Given: round one and feedback under a noncanonical Todo 4 filename.
    request = _request(tmp_path)
    first = run_next_round(request, _execution().dependencies())
    feedback = tmp_path / "wrong-name.json"
    _feedback(feedback, first.checkpoint_path)
    second = _request(tmp_path, 2, checkpoint=first.checkpoint_path, feedback=feedback)

    # When/Then: Todo 3 rejects it before loading a range or advancing a cursor.
    next_execution = _execution()
    with pytest.raises(CandidateCharacterizationError, match="feedback_filename_invalid"):
        run_next_round(second, next_execution.dependencies())
    assert next_execution.calls == []
    assert _checkpoint(first.checkpoint_path).streams[0].next_raw_rank == 190


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("checkpoint_sha256", "2" * 64),
        ("reservoir_sha256", "3" * 64),
        ("selector_config_sha256", "4" * 64),
        ("selector_implementation_sha256", "5" * 64),
    ),
)
def test_feedback_bindings_are_exact(tmp_path: Path, field: str, replacement: str) -> None:
    # Given: canonical round-one feedback with one predecessor binding changed.
    request = _request(tmp_path)
    first = run_next_round(request, _execution().dependencies())
    feedback = tmp_path / "selector_attempt_000001.json"
    _feedback(feedback, first.checkpoint_path)
    record = json.loads(feedback.read_bytes())
    record[field] = replacement
    feedback.write_bytes(json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    second = _request(tmp_path, 2, checkpoint=first.checkpoint_path, feedback=feedback)

    # When/Then: validation rejects the mismatch before requesting another range.
    execution = _execution()
    with pytest.raises(CandidateCharacterizationError, match="feedback_binding_invalid"):
        run_next_round(second, execution.dependencies())
    assert execution.calls == []


@pytest.mark.parametrize("offset", (-1, 1))
def test_skipped_or_overlapping_range_is_rejected(tmp_path: Path, offset: int) -> None:
    # Given: an adapter that shifts every accounting rank away from the requested range.
    execution = _execution()

    def shifted_load(request: RangeLoadRequest) -> CandidateBatch:
        batch = execution.load(request)
        accounting = tuple(row.model_copy(update={"raw_rank": row.raw_rank + offset}) for row in batch.accounting)
        return CandidateBatch(accounting, batch.planner_inputs, batch.receipt_sha256)

    dependencies = RunnerExecution(shifted_load, execution.characterize, execution.capacity, execution.fault)

    # When/Then: exact contiguous-range validation aborts before publication.
    request = _request(tmp_path)
    with pytest.raises(CandidateCharacterizationError, match="accounting_range_invalid"):
        run_next_round(request, dependencies)
    assert not (request.output / "current.json").exists()


def test_duplicate_emitted_characterization_is_rejected(tmp_path: Path) -> None:
    # Given: a range adapter that repeats one emitted candidate ID across object streams.
    execution = _execution()
    original_load = execution.load

    def duplicate_load(request: RangeLoadRequest) -> CandidateBatch:
        batch = original_load(request)
        repeated_id = "f" * 64
        planner = batch.planner_inputs[0].model_copy(update={"candidate_id": repeated_id})
        accounting = tuple(row.model_copy(update={"candidate_id": repeated_id}) for row in batch.accounting)
        return CandidateBatch(accounting, (planner,), batch.receipt_sha256)

    dependencies = RunnerExecution(duplicate_load, execution.characterize, execution.capacity, execution.fault)

    # When/Then: duplicate candidate-ID characterization aborts before checkpoint publication.
    request = _request(tmp_path)
    with pytest.raises(CandidateCharacterizationError, match="duplicate_candidate_characterization"):
        run_next_round(request, dependencies)
    assert not (request.output / "current.json").exists()


def test_finite_exhaustion_after_selector_feedback(tmp_path: Path) -> None:
    # Given: terminal remainders for all streams and a validated selector failure.
    execution = _execution(capacities={4: 2, 8: 3, 12: 1})
    request = _request(tmp_path)
    first = run_next_round(request, execution.dependencies())
    feedback = tmp_path / "selector_attempt_000001.json"
    _feedback(feedback, first.checkpoint_path)
    second = _request(tmp_path, 2, checkpoint=first.checkpoint_path, feedback=feedback)

    # When: Todo 3 observes failure only after every finite stream is exhausted.
    terminal = run_next_round(second, execution.dependencies())

    # Then: it emits one bound immutable exhaustion receipt without a second checkpoint.
    assert terminal.status == "finite_candidate_exhaustion"
    assert terminal.receipt_path == request.output / "receipts/finite_candidate_exhaustion.json"
    assert terminal.receipt_path is not None
    assert terminal.receipt_path.is_file()
    assert not (request.output / "checkpoints/reservoir_checkpoint_000002.json").exists()


def test_selector_feasible_freezes_without_another_batch(tmp_path: Path) -> None:
    # Given: round one and exact selector-feasible feedback.
    request = _request(tmp_path)
    first = run_next_round(request, _execution().dependencies())
    feedback = tmp_path / "selector_attempt_000001.json"
    _feedback(feedback, first.checkpoint_path, "selector_feasible")
    second = _request(tmp_path, 2, checkpoint=first.checkpoint_path, feedback=feedback)
    execution = _execution()

    # When: the feedback is validated.
    result = run_next_round(second, execution.dependencies())

    # Then: cursors freeze and no Todo 4 selector behavior or new range is owned here.
    assert result.status == "selector_feasible"
    assert result.read_only
    assert execution.calls == []


def test_path_escaping_checkpoint_is_rejected(tmp_path: Path) -> None:
    # Given: a predecessor argument outside the repository root.
    request = _request(tmp_path)
    first = run_next_round(request, _execution().dependencies())
    feedback = tmp_path / "selector_attempt_000001.json"
    _feedback(feedback, first.checkpoint_path)
    escaped = Path("/tmp/escaped-reservoir-checkpoint.json")
    escaped.write_bytes(first.checkpoint_path.read_bytes())

    # When/Then: canonical path confinement rejects the predecessor before cursor work.
    try:
        second = _request(tmp_path, 2, checkpoint=escaped, feedback=feedback)
        with pytest.raises(CandidateCharacterizationError, match="path_outside_repository"):
            run_next_round(second, _execution().dependencies())
    finally:
        escaped.unlink(missing_ok=True)
