from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)
from pydantic import JsonValue as PydanticJsonValue
from pydantic_core import PydanticCustomError
from typing_extensions import Self

JsonValue: TypeAlias = PydanticJsonValue
JsonObject: TypeAlias = dict[str, JsonValue]
AccountingStatus: TypeAlias = Literal["duplicate", "emitted", "solved"]
FeedbackStatus: TypeAlias = Literal["selector_feasible", "selector_infeasible"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApprovedTraceModel(StrictModel):
    approval_scope: Literal["trace_v2_persistence_only"]
    approved_at: StrictStr = Field(min_length=1)
    contract_id: Literal["cgas_trace_contract_v2"]
    contract_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    owner_approval_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    owner_approved: Literal[True]
    owner_id: StrictStr = Field(min_length=1)
    packet_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: Literal["cgas_trace_contract_approval_v1"]
    status: Literal["approved_trace_v2"]


class AccountingRowModel(StrictModel):
    candidate_id: StrictStr = Field(min_length=1)
    first_raw_rank: StrictInt = Field(ge=0)
    object_count: StrictInt = Field(gt=0)
    raw_rank: StrictInt = Field(ge=0)
    schema_version: Literal["cgas_production_raw_accounting_v1"]
    status: AccountingStatus


class PlannerInputModel(StrictModel):
    candidate_id: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_composition_signature: StrictStr = Field(min_length=1)
    first_raw_rank: StrictInt = Field(ge=0)
    goal_atoms: list[list[StrictStr]]
    init_atoms: list[list[StrictStr]]
    object_count: StrictInt = Field(gt=0)
    problem_pddl: StrictStr = Field(min_length=1)
    raw_rank: StrictInt = Field(ge=0)
    schema_version: Literal["cgas_production_planner_input_v1"]
    status: Literal["emitted"]


class StreamCursorModel(StrictModel):
    exhausted: StrictBool
    next_raw_rank: StrictInt = Field(ge=0)
    object_count: StrictInt = Field(gt=0)


class SelectorBindingModel(StrictModel):
    config_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class AccountingCountsModel(StrictModel):
    duplicate: StrictInt = Field(ge=0)
    emitted: StrictInt = Field(ge=0)
    solved: StrictInt = Field(ge=0)


class ArtifactBindingModel(StrictModel):
    canonical_jsonl: StrictStr
    row_count: StrictInt = Field(ge=0)
    sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class AccountingBindingModel(ArtifactBindingModel):
    counts: AccountingCountsModel


class ReservoirBindingModel(ArtifactBindingModel):
    signature_count: StrictInt = Field(ge=0)
    signatures: list[StrictStr]


class RangeBindingModel(StrictModel):
    count: StrictInt = Field(gt=0)
    end_rank: StrictInt = Field(gt=0)
    object_count: StrictInt = Field(gt=0)
    receipt_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    start_rank: StrictInt = Field(ge=0)


class TraceBindingModel(StrictModel):
    completion_status: Literal["success_full_trace", "skipped_resource_limit", "failed_no_plan_extracted"]
    contract_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    final_event_sha256: StrictStr | None
    path: StrictStr = Field(min_length=1)
    planner: Literal["bfs", "iw"]
    record_count: StrictInt = Field(ge=0)
    stream_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    success_plan_sha256: StrictStr | None


class CheckpointModel(StrictModel):
    accounting: AccountingBindingModel
    approved_trace_contract_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    approved_trace_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_config_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    characterization: ArtifactBindingModel
    feedback_sha256: StrictStr | None
    predecessor_checkpoint_sha256: StrictStr | None
    ranges: list[RangeBindingModel]
    reservoir: ReservoirBindingModel
    round: StrictInt = Field(gt=0)
    schema_version: Literal["cgas_candidate_characterization_checkpoint_v1"]
    selector: SelectorBindingModel
    streams: list[StreamCursorModel]


class CurrentIndexModel(StrictModel):
    checkpoint_path: StrictStr = Field(min_length=1)
    checkpoint_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    round: StrictInt = Field(gt=0)


class FeedbackModel(StrictModel):
    accepted_manifest_sha256: StrictStr | None
    checkpoint_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostics: JsonObject
    non_exhausted_streams: list[StrictInt]
    reason: StrictStr | None
    reservoir_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    round: StrictInt = Field(gt=0)
    schema_version: Literal["cgas_production_selector_attempt_v1"]
    selector_config_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    selector_implementation_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    status: FeedbackStatus

    @model_validator(mode="after")
    def require_status_shape(self) -> Self:
        if self.status == "selector_feasible":
            if self.accepted_manifest_sha256 is None or self.reason is not None:
                raise PydanticCustomError("selector_feasible_shape", "selector feasible fields are inconsistent")
        elif self.accepted_manifest_sha256 is not None or self.reason is None:
            raise PydanticCustomError("selector_infeasible_shape", "selector infeasible fields are inconsistent")
        return self
