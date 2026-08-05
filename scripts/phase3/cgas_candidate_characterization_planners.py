from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .cgas_bfs import BFSResult, run_fifo_bfs
from .cgas_candidate_characterization_contracts import CandidateCharacterizationError
from .cgas_candidate_characterization_models import TraceBindingModel
from .cgas_candidate_characterization_traces import TraceEventSpool, trace_binding
from .cgas_trace_stream_v2 import Planner, TraceVerification, verify_trace_stream
from .local_iw import run_iterated_width
from .local_planner_types import JSONValue, LocalPlannerRequest, LocalPlannerResult
from .pddl import GroundAction, PDDLTask


@dataclass(frozen=True, slots=True)
class PlannerRunRequest:
    repository_root: Path
    output_root: Path
    candidate_id: str
    task: PDDLTask
    grounded: tuple[GroundAction, ...]
    limits: dict[str, int]


@dataclass(frozen=True, slots=True)
class PlannerPair:
    bfs: BFSResult
    bfs_binding: TraceBindingModel
    iw: LocalPlannerResult
    iw_binding: TraceBindingModel


class _DiscardTraceEventSink:
    __slots__ = ()

    def append(self, _event: Mapping[str, JSONValue], /) -> None:
        return None


_DISCARD_TRACE_EVENTS: Final = _DiscardTraceEventSink()


def run_planners(request: PlannerRunRequest) -> PlannerPair:
    bfs, bfs_binding = _run_bfs(request)
    iw, iw_binding = _run_iw(request)
    return PlannerPair(bfs, bfs_binding, iw, iw_binding)


def _run_bfs(request: PlannerRunRequest) -> tuple[BFSResult, TraceBindingModel]:
    path = _trace_path(request, "bfs")
    if path.exists():
        verification = verify_trace_stream(path)
        limits = {**request.limits, "max_trace_steps": 0}
        result = run_fifo_bfs(request.task, request.grounded, limits, _DISCARD_TRACE_EVENTS)
        _validate_reuse(verification, "bfs", result.status, result.trace, result.plan, path)
        return BFSResult(result.plan, result.trace, verification.completion_status), trace_binding(
            request.repository_root, path, verification
        )
    with TraceEventSpool(request.repository_root, request.output_root, request.candidate_id, "bfs") as spool:
        result = run_fifo_bfs(request.task, request.grounded, request.limits, spool)
        return result, spool.publish(result.status, result.plan)


def _run_iw(request: PlannerRunRequest) -> tuple[LocalPlannerResult, TraceBindingModel]:
    path = _trace_path(request, "iw")
    if path.exists():
        verification = verify_trace_stream(path)
        limits = {**request.limits, "max_trace_steps": 0}
        result = run_iterated_width(
            LocalPlannerRequest("iw", request.task, request.grounded, limits, _DISCARD_TRACE_EVENTS)
        )
        plan = tuple(result.plan)
        _validate_reuse(verification, "iw", result.status, result.trace, plan, path)
        normalized = LocalPlannerResult(result.plan, result.trace, verification.completion_status)
        return normalized, trace_binding(request.repository_root, path, verification)
    with TraceEventSpool(request.repository_root, request.output_root, request.candidate_id, "iw") as spool:
        result = run_iterated_width(LocalPlannerRequest("iw", request.task, request.grounded, request.limits, spool))
        return result, spool.publish(result.status, tuple(result.plan))


def _validate_reuse(
    verification: TraceVerification,
    planner: Planner,
    replay_status: str,
    replay_trace: dict[str, JSONValue],
    plan: tuple[str, ...],
    path: Path,
) -> None:
    verification_status = str(verification.completion_status)
    if "success_truncated_trace" in {verification_status, replay_status}:
        raise CandidateCharacterizationError("existing_trace_replay_invalid", path)
    if replay_status == "success_full_trace" and replay_trace.get("trace_complete") is not True:
        raise CandidateCharacterizationError("existing_trace_replay_invalid", path)
    plan_digest = None
    if replay_status == "success_full_trace":
        plan_bytes = json.dumps(plan, allow_nan=False, ensure_ascii=True, separators=(",", ":")).encode()
        plan_digest = hashlib.sha256(plan_bytes).hexdigest()
    if (
        verification.planner != planner
        or verification_status != replay_status
        or verification.success_plan_sha256 != plan_digest
    ):
        raise CandidateCharacterizationError("existing_trace_replay_invalid", path)


def _trace_path(request: PlannerRunRequest, planner: Planner) -> Path:
    return request.output_root / "traces" / request.candidate_id / f"{planner}.trace-v2.jsonl"
