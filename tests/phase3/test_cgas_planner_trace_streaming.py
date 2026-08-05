from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from scripts.phase3.cgas_bfs import run_fifo_bfs
from scripts.phase3.cgas_candidate_characterization_characterizer import _limits
from scripts.phase3.cgas_candidate_characterization_contracts import CandidateCharacterizationError
from scripts.phase3.cgas_candidate_characterization_planners import PlannerRunRequest, _validate_reuse, run_planners
from scripts.phase3.cgas_trace_stream_v2 import TraceVerification
from scripts.phase3.local_iw import run_iterated_width
from scripts.phase3.local_planner_types import JSONValue, LocalPlannerRequest
from scripts.phase3.pddl import ground_actions, parse_task

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data/curriculum_pddl/blocksworld/dev/easy/blocksworld-dev-easy-0001"


class RecordingSink:
    __slots__ = ("events",)

    def __init__(self) -> None:
        self.events: list[Mapping[str, JSONValue]] = []

    def append(self, event: Mapping[str, JSONValue], /) -> None:
        self.events.append(event)


def test_bfs_streaming_preserves_search_without_retaining_events() -> None:
    # Given: one real grounded task and the complete-trace production limits.
    task = parse_task(FIXTURE / "domain.pddl", FIXTURE / "problem.pddl")
    grounded, status = ground_actions(task, max_grounded_actions=100_000, max_grounded_atoms=100_000)
    assert status is None
    limits = _limits()
    sink = RecordingSink()

    # When: BFS runs once with retained events and once through the streaming sink.
    retained = run_fifo_bfs(task, tuple(grounded), limits)
    streamed = run_fifo_bfs(task, tuple(grounded), limits, sink)

    # Then: search semantics and complete event count match without an in-memory streamed event list.
    assert (streamed.plan, streamed.status) == (retained.plan, retained.status)
    assert streamed.trace["expansions"] == []
    assert streamed.trace["trace_complete"] is True
    retained_events = retained.trace["expansions"]
    assert isinstance(retained_events, list)
    assert len(sink.events) == len(retained_events)
    trace_bytes = json.dumps(
        retained.trace, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode()
    assert hashlib.sha256(trace_bytes).hexdigest() == "9f6fb29a80e4363ab3055f5ef7c4984aab3eb60a161da4a254cd21bc0852c70f"


def test_iw_streaming_preserves_search_without_retaining_events() -> None:
    # Given: the same real grounded task and separate retained/streaming requests.
    task = parse_task(FIXTURE / "domain.pddl", FIXTURE / "problem.pddl")
    grounded, status = ground_actions(task, max_grounded_actions=100_000, max_grounded_atoms=100_000)
    assert status is None
    limits = _limits()
    sink = RecordingSink()

    # When: IW(1) runs through both trace retention modes.
    retained = run_iterated_width(LocalPlannerRequest("iw", task, tuple(grounded), limits))
    streamed = run_iterated_width(LocalPlannerRequest("iw", task, tuple(grounded), limits, sink))

    # Then: plan/status and complete event count match while streamed events live only in the sink.
    assert (streamed.plan, streamed.status) == (retained.plan, retained.status)
    assert streamed.trace["events"] == []
    assert streamed.trace["trace_complete"] is True
    retained_events = retained.trace["events"]
    assert isinstance(retained_events, list)
    assert len(sink.events) == len(retained_events)


def test_verified_trace_rerun_replays_non_degenerate_success_without_replacing_streams(tmp_path: Path) -> None:
    # Given: one real planner request with no existing trace files.
    task = parse_task(FIXTURE / "domain.pddl", FIXTURE / "problem.pddl")
    grounded, status = ground_actions(task, max_grounded_actions=100_000, max_grounded_atoms=100_000)
    assert status is None
    request = PlannerRunRequest(tmp_path, tmp_path / "output", "a" * 64, task, tuple(grounded), _limits())

    # When: the request is characterized and replayed through its verified streams.
    first = run_planners(request)
    bfs_path = tmp_path / first.bfs_binding.path
    iw_path = tmp_path / first.iw_binding.path
    before = ((bfs_path.stat().st_ino, bfs_path.read_bytes()), (iw_path.stat().st_ino, iw_path.read_bytes()))
    second = run_planners(request)

    # Then: replay preserves planner outcomes, reports complete logical traces, and preserves streams exactly.
    assert (second.bfs.plan, second.bfs.status) == (first.bfs.plan, first.bfs.status)
    assert (second.iw.plan, second.iw.status) == (first.iw.plan, first.iw.status)
    assert second.bfs.trace["trace_complete"] is True
    assert second.iw.trace["trace_complete"] is True
    assert (bfs_path.stat().st_ino, bfs_path.read_bytes()) == before[0]
    assert (iw_path.stat().st_ino, iw_path.read_bytes()) == before[1]


def test_validate_reuse_rejects_successful_truncated_status(tmp_path: Path) -> None:
    # Given: a verified complete stream and a replay with a matching successful plan digest.
    plan = ("(move)",)
    plan_digest = hashlib.sha256(json.dumps(plan, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
    verification = TraceVerification("bfs", "success_full_trace", 0, None, "1" * 64, plan_digest, "2" * 64)
    path = tmp_path / "bfs.trace-v2.jsonl"

    # When: reuse validation receives a successful truncated replay status.
    with pytest.raises(CandidateCharacterizationError) as captured:
        _validate_reuse(verification, "bfs", "success_truncated_trace", {"trace_complete": True}, plan, path)

    # Then: the persisted stream is rejected instead of normalizing the truncated status.
    assert captured.value == CandidateCharacterizationError("existing_trace_replay_invalid", path)


def test_validate_reuse_rejects_truncated_verification_and_replay(tmp_path: Path) -> None:
    # Given: a crafted verification and replay that both claim truncated success.
    verification = TraceVerification("bfs", "success_full_trace", 0, None, "1" * 64, "2" * 64, "3" * 64)
    object.__setattr__(verification, "completion_status", "success_truncated_trace")
    object.__setattr__(verification, "success_plan_sha256", None)
    path = tmp_path / "bfs.trace-v2.jsonl"

    # When: reuse validation receives matching truncated statuses and a complete flag.
    with pytest.raises(CandidateCharacterizationError) as captured:
        _validate_reuse(
            verification,
            "bfs",
            "success_truncated_trace",
            {"trace_complete": True},
            ("(move)",),
            path,
        )

    # Then: truncated success still fails closed before digest matching.
    assert captured.value == CandidateCharacterizationError("existing_trace_replay_invalid", path)
