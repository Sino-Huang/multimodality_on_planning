from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, StrictInt, ValidationError


DEFAULT_SUMMARY_PATH: Final = Path("data/phase3_supervised_planning/summary.json")
DEFAULT_VISION_VALIDATION_PATH: Final = Path(
    "data/phase3_supervised_planning/diagnostics/vision_validation.jsonl"
)
DEFAULT_OUTPUT_PATH: Final = Path("outputs/cgas_readiness/input_contract.json")
ACTIVE_PLANNERS: Final = ("gbfs", "ff", "iw", "graphplan")
SUCCESS_STATUS: Final = "success_full_trace"
STEP_ALIGNED_STATUS: Final = "vision_available_step_aligned"


class PlannerStatusCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    skipped_planner_unavailable: StrictInt | None = None
    skipped_resource_limit: StrictInt | None = None
    skipped_unsupported_pddl: StrictInt | None = None
    success_full_trace: StrictInt | None = None


class SummaryContract(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    emitted_examples: StrictInt
    planner_status_summary: dict[str, PlannerStatusCounts]


class VisionValidationRow(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    status: str


class Phase3Observation(BaseModel):
    model_config = ConfigDict(frozen=True)

    active_planners: list[str]
    current_bfs_examples: StrictInt
    current_iw_examples: StrictInt
    current_vision_alignment_rows: StrictInt


class ObservationStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    readiness_approved: Literal[False]
    status: Literal["observed_not_ready"]


class QwenImageContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    cardinality: Literal[1]
    path_kind: Literal["relative_string"]


class QwenConversationContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    assistant_role: Literal["assistant"]
    human_role: Literal["human"]
    required_human_image_tokens: Literal[1]


class QwenObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversations: QwenConversationContract
    image: QwenImageContract


class ReadinessSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    observation: ObservationStatus
    phase3: Phase3Observation
    qwen_vl: QwenObservation


class InputContractError(Exception):
    def __init__(self, source: Path, detail: str) -> None:
        self.source = source
        self.detail = detail
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"invalid input contract at {self.source}: {self.detail}"


def observe(summary_path: Path, vision_validation_path: Path) -> ReadinessSnapshot:
    summary = _read_summary(summary_path)
    vision_rows = _read_vision_rows(vision_validation_path)
    bfs = _planner_success_count(summary, "bfs", summary_path)
    iw = _planner_success_count(summary, "iw", summary_path)
    aligned_rows = sum(row.status == STEP_ALIGNED_STATUS for row in vision_rows)
    return ReadinessSnapshot(
        observation=ObservationStatus(
            readiness_approved=False,
            status="observed_not_ready",
        ),
        phase3=Phase3Observation(
            active_planners=list(ACTIVE_PLANNERS),
            current_bfs_examples=bfs,
            current_iw_examples=iw,
            current_vision_alignment_rows=aligned_rows,
        ),
        qwen_vl=QwenObservation(
            conversations=QwenConversationContract(
                assistant_role="assistant",
                human_role="human",
                required_human_image_tokens=1,
            ),
            image=QwenImageContract(cardinality=1, path_kind="relative_string"),
        ),
    )


def _read_summary(summary_path: Path) -> SummaryContract:
    try:
        return SummaryContract.model_validate_json(summary_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise InputContractError(summary_path, str(error)) from error
    except (ValidationError, json.JSONDecodeError) as error:
        raise InputContractError(summary_path, str(error)) from error


def _read_vision_rows(vision_validation_path: Path) -> list[VisionValidationRow]:
    try:
        lines = vision_validation_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise InputContractError(vision_validation_path, str(error)) from error
    rows: list[VisionValidationRow] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            rows.append(VisionValidationRow.model_validate_json(line))
        except (ValidationError, json.JSONDecodeError) as error:
            raise InputContractError(
                vision_validation_path, f"line {line_number}: {error}"
            ) from error
    return rows


def _planner_success_count(
    summary: SummaryContract, planner: str, summary_path: Path
) -> StrictInt:
    try:
        counts = summary.planner_status_summary[planner]
    except KeyError as error:
        raise InputContractError(
            summary_path, f"planner_status_summary.{planner}: Field required"
        ) from error
    if counts.success_full_trace is None:
        if planner == "iw":
            return 0
        raise InputContractError(
            summary_path,
            f"planner_status_summary.{planner}.success_full_trace: Field required",
        )
    return counts.success_full_trace


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Observe current CGAS input contracts without approving readiness."
    )
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument(
        "--vision-validation-path",
        type=Path,
        default=DEFAULT_VISION_VALIDATION_PATH,
    )
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args(arguments)
    try:
        snapshot = observe(args.summary_path, args.vision_validation_path)
    except InputContractError as error:
        print(str(error), file=sys.stderr)
        return 1
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
