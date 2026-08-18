from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from .cgas_candidate_characterization_characterizer import CharacterizationRequest, characterize_candidate
from .cgas_candidate_characterization_checkpoint import CheckpointBuildRequest, build_checkpoint
from .cgas_candidate_characterization_contracts import (
    CandidateCharacterizationError,
    selector_binding,
    validate_approval,
)
from .cgas_candidate_characterization_models import CheckpointModel, JsonObject, SelectorBindingModel, StreamCursorModel
from .cgas_candidate_characterization_publication import (
    CheckpointEntry,
    output_lock,
    publish_checkpoint,
    publish_current_index,
    publish_receipt,
    recover_current_index,
    scan_chain,
)
from .cgas_candidate_characterization_ranges import CandidateBatch, RangeLoadRequest, load_candidate_batch
from .cgas_candidate_characterization_replay import ReplayRequest, load_predecessor, validate_external_bindings
from .cgas_candidate_characterization_runner_support import (
    characterization_ids,
    range_binding,
    text,
    validate_batch,
    validate_characterization,
    validate_paths,
)
from .cgas_candidate_contracts import load_config
from .cgas_candidate_space import stream_capacity


class FaultPoint(str, Enum):
    AFTER_RANGE = "after_range"
    AFTER_ACCOUNTING = "after_accounting"
    AFTER_CHARACTERIZATION = "after_characterization"
    BEFORE_CHECKPOINT = "before_checkpoint"
    AFTER_CHECKPOINT = "after_checkpoint"
    BEFORE_INDEX = "before_index"


@dataclass(frozen=True, slots=True)
class NextRoundRequest:
    repository_root: Path
    round: int
    approved_trace_contract: Path
    candidate_config: Path
    candidate_root: Path
    output: Path
    checkpoint: Path | None = None
    feedback: Path | None = None


@dataclass(frozen=True, slots=True)
class RoundReport:
    status: str
    checkpoint_path: Path
    receipt_path: Path | None = None
    read_only: bool = False


class RangeLoader(Protocol):
    def __call__(self, request: RangeLoadRequest, /) -> CandidateBatch: ...


class CandidateCharacterizer(Protocol):
    def __call__(self, request: CharacterizationRequest, /) -> JsonObject: ...


class CapacityProvider(Protocol):
    def __call__(self, object_count: int, /) -> int: ...


class FaultInjector(Protocol):
    def __call__(self, point: FaultPoint, /) -> None: ...


@dataclass(frozen=True, slots=True)
class RunnerExecution:
    range_loader: RangeLoader
    characterizer: CandidateCharacterizer
    capacity: CapacityProvider
    fault: FaultInjector


def default_execution() -> RunnerExecution:
    return RunnerExecution(load_candidate_batch, characterize_candidate, stream_capacity, _no_fault)


def run_next_round(request: NextRoundRequest, execution: RunnerExecution | None = None) -> RoundReport:
    approval, approval_digest = validate_approval(request.approved_trace_contract)
    validate_paths(
        request.repository_root,
        request.approved_trace_contract,
        request.candidate_config,
        request.candidate_root,
        request.output,
        request.checkpoint,
        request.feedback,
        request.round,
    )
    config = load_config(request.candidate_config)
    dependencies = execution or default_execution()
    selector = selector_binding()
    with output_lock(request.output):
        chain = scan_chain(request.output, request.repository_root)
        recover_current_index(request.output, request.repository_root, chain)
        predecessor, feedback_digest, feedback_status = load_predecessor(
            ReplayRequest(
                request.repository_root,
                request.round,
                request.checkpoint,
                request.feedback,
                request.output,
            ),
            chain,
        )
        validate_external_bindings(predecessor, approval_digest, approval.contract_sha256, config.sha256, selector)
        if feedback_status == "selector_feasible":
            target = chain[request.round - 1] if len(chain) >= request.round else predecessor
            if target is None:
                raise CandidateCharacterizationError("feedback_predecessor_missing", request.output)
            return RoundReport("selector_feasible", target.path, read_only=True)
        if predecessor is not None and predecessor.checkpoint.round == request.round:
            return RoundReport("ok", predecessor.path, read_only=True)
        if request.round > 1 and predecessor is not None and _all_exhausted(predecessor.checkpoint):
            return _finish_exhaustion(request, predecessor, feedback_digest)
        if request.round == 1 and chain:
            return RoundReport("ok", chain[0].path, read_only=True)
        expected_round = 1 if predecessor is None else predecessor.checkpoint.round + 1
        if request.round != expected_round:
            raise CandidateCharacterizationError("round_noncontiguous", request.output)
        checkpoint = _consume_round(
            request,
            config.sha256,
            selector,
            approval_digest,
            approval.contract_sha256,
            predecessor,
            feedback_digest,
            dependencies,
        )
        dependencies.fault(FaultPoint.BEFORE_CHECKPOINT)
        entry = publish_checkpoint(request.output, checkpoint)
        dependencies.fault(FaultPoint.AFTER_CHECKPOINT)
        dependencies.fault(FaultPoint.BEFORE_INDEX)
        publish_current_index(entry, request.output, request.repository_root)
    return RoundReport("ok", entry.path)


def _consume_round(
    request: NextRoundRequest,
    config_digest: str,
    selector: SelectorBindingModel,
    approval_digest: str,
    trace_contract_digest: str,
    predecessor: CheckpointEntry | None,
    feedback_digest: str | None,
    execution: RunnerExecution,
) -> CheckpointModel:
    cursors = (
        {stream.object_count: stream for stream in predecessor.checkpoint.streams}
        if predecessor is not None
        else {index: StreamCursorModel(object_count=index, next_raw_rank=0, exhausted=False) for index in (4, 8, 12)}
    )
    accounting = []
    characterizations: list[JsonObject] = []
    ranges = []
    known_candidates = characterization_ids(predecessor.checkpoint) if predecessor is not None else set()
    for object_count in (4, 8, 12):
        stream = cursors[object_count]
        if stream.exhausted:
            continue
        quota = {4: 190, 8: 198, 12: 93}[object_count]
        count = min(quota, execution.capacity(object_count) - stream.next_raw_rank)
        if count <= 0:
            cursors[object_count] = StreamCursorModel(
                object_count=object_count, next_raw_rank=stream.next_raw_rank, exhausted=True
            )
            continue
        batch = execution.range_loader(
            RangeLoadRequest(request.candidate_config, request.candidate_root, object_count, stream.next_raw_rank, count)
        )
        execution.fault(FaultPoint.AFTER_RANGE)
        validate_batch(batch, object_count, stream.next_raw_rank, count, request.output)
        accounting.extend(batch.accounting)
        ranges.append(range_binding(batch, object_count, stream.next_raw_rank, count))
        execution.fault(FaultPoint.AFTER_ACCOUNTING)
        new_characterizations: list[JsonObject] = []
        for planner in batch.planner_inputs:
            if planner.candidate_id in known_candidates:
                raise CandidateCharacterizationError("duplicate_candidate_characterization", request.output)
            row = execution.characterizer(
                CharacterizationRequest(
                    planner,
                    request.repository_root,
                    request.output,
                    approval_digest,
                    trace_contract_digest,
                )
            )
            validate_characterization(row, planner, approval_digest, trace_contract_digest, request.output)
            characterizations.append(row)
            new_characterizations.append(row)
            known_candidates.add(planner.candidate_id)
        if {planner.candidate_id for planner in batch.planner_inputs} != {
            text(row, "candidate_id") for row in new_characterizations
        }:
            raise CandidateCharacterizationError("emitted_characterization_incomplete", request.output)
        execution.fault(FaultPoint.AFTER_CHARACTERIZATION)
        cursors[object_count] = StreamCursorModel(
            object_count=object_count,
            next_raw_rank=stream.next_raw_rank + count,
            exhausted=stream.next_raw_rank + count >= execution.capacity(object_count),
        )
    return build_checkpoint(
        CheckpointBuildRequest(
            request.repository_root,
            request.round,
            predecessor.digest if predecessor is not None else None,
            feedback_digest,
            approval_digest,
            trace_contract_digest,
            config_digest,
            selector,
            predecessor.checkpoint if predecessor is not None else None,
            tuple(cursors[index] for index in (4, 8, 12)),
            tuple(accounting),
            tuple(characterizations),
            tuple(ranges),
        )
    )


def _all_exhausted(checkpoint: CheckpointModel) -> bool:
    return all(stream.exhausted for stream in checkpoint.streams)


def _finish_exhaustion(
    request: NextRoundRequest, predecessor: CheckpointEntry, feedback_digest: str | None
) -> RoundReport:
    path = request.output / "receipts/finite_candidate_exhaustion.json"
    record: JsonObject = {
        "checkpoint_sha256": predecessor.digest,
        "feedback_sha256": feedback_digest,
        "reason": "finite_candidate_exhaustion",
        "round": predecessor.checkpoint.round,
        "schema_version": "cgas_finite_candidate_exhaustion_v1",
        "status": "finite_candidate_exhaustion",
    }
    publish_receipt(path, record)
    return RoundReport("finite_candidate_exhaustion", predecessor.path, path, read_only=True)


def _no_fault(_point: FaultPoint) -> None:
    return None
