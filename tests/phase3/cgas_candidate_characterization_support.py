from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.phase3.cgas_candidate_characterization import NextRoundRequest
from scripts.phase3.cgas_candidate_characterization_models import (
    AccountingRowModel,
    CheckpointModel,
    JsonObject,
    PlannerInputModel,
)
from scripts.phase3.cgas_candidate_characterization_ranges import CandidateBatch, RangeLoadRequest
from scripts.phase3.cgas_candidate_characterization_runner import (
    CharacterizationRequest,
    FaultPoint,
    RunnerExecution,
)
from scripts.phase3.cgas_candidate_characterization_runner_support import planner_input_sha256
from scripts.phase3.cgas_candidate_characterization_traces import TracePersistenceRequest, persist_trace

ROOT = Path(__file__).resolve().parents[2]
APPROVAL = ROOT / ".claude/evidence/cgas-production-p0/approved-trace-v2.json"
PACKET = ROOT / ".claude/evidence/cgas-production-p0/trace-v2-migration-packet.json"
OWNER_APPROVAL = ROOT / ".claude/evidence/cgas-production-p0/trace-v2-owner-approval.json"
CONFIG = ROOT / "configs/cgas/production_p0_candidates.json"


class RecordingExecution:
    __slots__ = ("calls", "capacity_by_object", "characterized", "fault_point")

    def __init__(
        self,
        calls: list[RangeLoadRequest],
        characterized: list[str],
        capacity_by_object: dict[int, int],
        fault_point: FaultPoint | None = None,
    ) -> None:
        self.calls = calls
        self.characterized = characterized
        self.capacity_by_object = capacity_by_object
        self.fault_point = fault_point

    def load(self, request: RangeLoadRequest) -> CandidateBatch:
        self.calls.append(request)
        candidate_id = hashlib.sha256(f"{request.object_count}:{request.start_rank}".encode()).hexdigest()
        accounting = tuple(
            AccountingRowModel(
                candidate_id=candidate_id,
                first_raw_rank=request.start_rank,
                object_count=request.object_count,
                raw_rank=rank,
                schema_version="cgas_production_raw_accounting_v1",
                status=(
                    "emitted"
                    if rank == request.start_rank
                    else "solved"
                    if rank == request.start_rank + request.count - 1
                    else "duplicate"
                ),
            )
            for rank in range(request.start_rank, request.start_rank + request.count)
        )
        planner = PlannerInputModel(
            candidate_id=candidate_id,
            canonical_composition_signature=f"signature-{request.object_count}",
            first_raw_rank=request.start_rank,
            goal_atoms=[["on", "b01", "b00"]],
            init_atoms=[["arm-empty"]],
            object_count=request.object_count,
            problem_pddl="(define (problem exact-fixture) (:domain blocksworld-4ops))\n",
            raw_rank=request.start_rank,
            schema_version="cgas_production_planner_input_v1",
            status="emitted",
        )
        receipt = hashlib.sha256(f"receipt:{request.object_count}:{request.start_rank}".encode()).hexdigest()
        return CandidateBatch(accounting, (planner,), receipt)

    def characterize(self, request: CharacterizationRequest) -> JsonObject:
        candidate_id = request.planner_input.candidate_id
        self.characterized.append(candidate_id)
        bfs_binding = persist_trace(
            TracePersistenceRequest(
                request.repository_root,
                request.output_root,
                candidate_id,
                "bfs",
                "success_full_trace",
                ("(finish)",),
                {"expansions": [{"fixture": candidate_id}]},
                "expansions",
            )
        )
        iw_binding = persist_trace(
            TracePersistenceRequest(
                request.repository_root,
                request.output_root,
                candidate_id,
                "iw",
                "success_full_trace",
                ("(finish)",),
                {"events": [{"fixture": candidate_id}]},
                "events",
            )
        )
        planner = {
            "exact_search": {"expansion_count": 1, "plan_length": 1, "status": "exact_solution_replayed"},
            "replay": {"goal_satisfied": True, "replay_ok": True},
            "source_eligibility": "eligible_complete_trace",
        }
        bfs = {**planner, "trace_v2": bfs_binding.model_dump(mode="json")}
        iw = {**planner, "trace_v2": iw_binding.model_dump(mode="json")}
        return {
            "approved_trace_sha256": request.approved_trace_sha256,
            "bfs": bfs,
            "candidate_id": candidate_id,
            "composition_signature": request.planner_input.canonical_composition_signature,
            "instance_id": candidate_id,
            "iw_width_1": iw,
            "object_count": request.planner_input.object_count,
            "raw_rank": request.planner_input.raw_rank,
            "source_identity": {"source_record_sha256": planner_input_sha256(request.planner_input)},
            "status": "characterized",
            "trace_contract_sha256": request.trace_contract_sha256,
            "trace_policy_sha256": request.trace_policy_sha256,
        }

    def capacity(self, object_count: int) -> int:
        return self.capacity_by_object[object_count]

    def fault(self, point: FaultPoint) -> None:
        if point is self.fault_point:
            raise OSError(f"injected:{point.value}")

    def dependencies(self) -> RunnerExecution:
        return RunnerExecution(self.load, self.characterize, self.capacity, self.fault)


def request_fixture(
    repository: Path,
    round_number: int = 1,
    *,
    checkpoint: Path | None = None,
    feedback: Path | None = None,
) -> NextRoundRequest:
    approval = repository / "approved-trace-v2.json"
    config = repository / "production-p0-candidates.json"
    candidate_root = repository / "candidates"
    if not approval.exists():
        approval.write_bytes(APPROVAL.read_bytes())
        (repository / "trace-v2-migration-packet.json").write_bytes(PACKET.read_bytes())
        (repository / "trace-v2-owner-approval.json").write_bytes(OWNER_APPROVAL.read_bytes())
        config.write_bytes(CONFIG.read_bytes())
        candidate_root.mkdir()
    return NextRoundRequest(
        repository,
        round_number,
        approval,
        config,
        candidate_root,
        repository / "characterized",
        checkpoint,
        feedback,
    )


def execution_fixture(
    *, capacities: dict[int, int] | None = None, fault: FaultPoint | None = None
) -> RecordingExecution:
    defaults = {4: 600, 8: 19_514_880, 12: 2_840_000_486_400}
    return RecordingExecution([], [], capacities or defaults, fault)


def load_checkpoint(path: Path) -> CheckpointModel:
    return CheckpointModel.model_validate_json(path.read_bytes())


def write_feedback(path: Path, checkpoint_path: Path, status: str = "selector_infeasible") -> None:
    checkpoint = load_checkpoint(checkpoint_path)
    record = {
        "checkpoint_sha256": hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
        "diagnostics": {"paired_exact": checkpoint.reservoir.row_count},
        "non_exhausted_streams": [stream.object_count for stream in checkpoint.streams if not stream.exhausted],
        "reservoir_sha256": checkpoint.reservoir.sha256,
        "round": checkpoint.round,
        "schema_version": "cgas_production_selector_attempt_v1",
        "selector_config_sha256": checkpoint.selector.config_sha256,
        "selector_implementation_sha256": checkpoint.selector.implementation_sha256,
        "status": status,
    }
    if status == "selector_feasible":
        record["accepted_manifest_sha256"] = "1" * 64
    else:
        record["reason"] = "exact_selector_infeasible"
    contents = json.dumps(record, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    path.write_bytes(contents.encode() + b"\n")
