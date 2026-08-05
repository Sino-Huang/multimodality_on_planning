from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from .cgas_candidate_characterization_contracts import CandidateCharacterizationError
from .cgas_candidate_characterization_models import JsonObject, PlannerInputModel, TraceBindingModel
from .cgas_candidate_characterization_planners import PlannerRunRequest, run_planners
from .cgas_partition_characterization import _failure_row, _success_row
from .cgas_partition_contracts import DEFAULT_LIMITS, CharacterizationInput
from .cgas_trace_contract_v2 import NEW_CONTRACT_SHA256, POLICY_LIMITS
from .cgas_trace_contract_v2 import POLICY_SHA256 as TRACE_POLICY_SHA256
from .local_planner_types import RecoveryPolicy
from .pddl import PDDLError, ground_actions, parse_task


@dataclass(frozen=True, slots=True)
class CharacterizationRequest:
    planner_input: PlannerInputModel
    repository_root: Path
    output_root: Path
    approved_trace_sha256: str
    trace_contract_sha256: str = NEW_CONTRACT_SHA256
    trace_policy_sha256: str = TRACE_POLICY_SHA256


def characterize_candidate(request: CharacterizationRequest) -> JsonObject:
    planner = request.planner_input
    domain_path = request.repository_root / "modules/pddl-generators/blocksworld/4ops/domain.pddl"
    source_digest = hashlib.sha256(_canonical_planner_bytes(planner)).hexdigest()
    instance = CharacterizationInput(
        planner.candidate_id,
        "candidate",
        domain_path,
        Path(),
        source_digest,
    )
    try:
        with tempfile.TemporaryDirectory(prefix="cgas-candidate-") as temporary:
            problem_path = Path(temporary) / "problem.pddl"
            problem_path.write_text(planner.problem_pddl, encoding="utf-8")
            task = parse_task(domain_path, problem_path)
            if task.unsupported_features:
                row = TypeAdapter(JsonObject).validate_python(_failure_row(instance, "unsupported_pddl", task=task))
            else:
                grounded, grounding_status = ground_actions(
                    task,
                    max_grounded_actions=DEFAULT_LIMITS["max_grounded_actions"],
                    max_grounded_atoms=DEFAULT_LIMITS["max_grounded_atoms"],
                )
                if grounding_status is not None:
                    row = TypeAdapter(JsonObject).validate_python(_failure_row(instance, grounding_status, task=task))
                else:
                    limits = _limits()
                    planners = run_planners(
                        PlannerRunRequest(
                            request.repository_root,
                            request.output_root,
                            planner.candidate_id,
                            task,
                            tuple(grounded),
                            limits,
                        )
                    )
                    bfs = planners.bfs
                    iw = planners.iw
                    row = TypeAdapter(JsonObject).validate_python(
                        _success_row(
                            instance,
                            task,
                            grounded,
                            bfs.plan,
                            bfs.trace,
                            bfs.status,
                            iw.plan,
                            iw.trace,
                            iw.status,
                        )
                    )
                    _attach_trace(
                        row,
                        "bfs",
                        planners.bfs_binding,
                    )
                    _attach_trace(
                        row,
                        "iw_width_1",
                        planners.iw_binding,
                    )
    except (OSError, PDDLError, json.JSONDecodeError) as error:
        row = TypeAdapter(JsonObject).validate_python(_failure_row(instance, f"pddl_error:{type(error).__name__}"))
    result = row
    result.update(
        {
            "approved_trace_sha256": request.approved_trace_sha256,
            "candidate_id": planner.candidate_id,
            "object_count": planner.object_count,
            "raw_rank": planner.raw_rank,
            "trace_contract_sha256": request.trace_contract_sha256,
            "trace_policy_sha256": request.trace_policy_sha256,
        }
    )
    return result


def _attach_trace(row: JsonObject, planner_name: str, binding: TraceBindingModel) -> None:
    planner = row.get(planner_name)
    if not isinstance(planner, dict):
        raise CandidateCharacterizationError("characterization_planner_invalid", Path(planner_name))
    planner["trace_v2"] = binding.model_dump(mode="json")


def _canonical_planner_bytes(planner: PlannerInputModel) -> bytes:
    return (
        json.dumps(
            planner.model_dump(mode="json"),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        + b"\n"
    )


def _limits() -> dict[str, int]:
    limits = {key: value for key, value in DEFAULT_LIMITS.items()}
    limits.update({key: value for key, value in POLICY_LIMITS.items() if isinstance(value, int)})
    limits["max_trace_steps"] = 10_000
    limits["local_iw_recovery"] = RecoveryPolicy.DISABLED
    return limits
