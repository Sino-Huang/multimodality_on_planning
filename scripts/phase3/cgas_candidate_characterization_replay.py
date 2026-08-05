from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .cgas_candidate_characterization_contracts import (
    CandidateCharacterizationError,
    confined,
    parse_canonical_model,
    sha256,
    validate_feedback,
)
from .cgas_candidate_characterization_models import CheckpointModel, SelectorBindingModel
from .cgas_candidate_characterization_publication import CheckpointEntry, checkpoint_path


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    repository_root: Path
    round: int
    checkpoint: Path | None
    feedback: Path | None
    output: Path


def load_predecessor(
    request: ReplayRequest,
    chain: tuple[CheckpointEntry, ...],
) -> tuple[CheckpointEntry | None, str | None, str | None]:
    if request.round == 1:
        if request.checkpoint is not None or request.feedback is not None:
            raise CandidateCharacterizationError("round_one_feedback_forbidden", request.output)
        return (chain[0], None, None) if chain else (None, None, None)
    if request.checkpoint is None or request.feedback is None:
        raise CandidateCharacterizationError("feedback_required", request.output)
    checkpoint_relative = confined(request.checkpoint, request.repository_root)
    expected = checkpoint_path(request.output, request.round - 1)
    expected_relative = expected.resolve().relative_to(request.repository_root.resolve()).as_posix()
    if request.checkpoint.resolve() != expected.resolve() or checkpoint_relative.as_posix() != expected_relative:
        raise CandidateCharacterizationError("checkpoint_path_invalid", request.checkpoint)
    checkpoint, contents = parse_canonical_model(request.checkpoint, CheckpointModel, "checkpoint_invalid")
    digest = sha256(contents)
    entry = CheckpointEntry(request.checkpoint, checkpoint, digest, contents)
    feedback, feedback_digest = validate_feedback(request.feedback, request.checkpoint, checkpoint, digest)
    if feedback.status == "selector_feasible":
        return entry, feedback_digest, feedback.status
    if chain and request.round <= len(chain):
        target = chain[request.round - 1]
        binding_matches = (
            target.checkpoint.predecessor_checkpoint_sha256 == digest
            and target.checkpoint.feedback_sha256 == feedback_digest
        )
        if not binding_matches:
            raise CandidateCharacterizationError("historical_checkpoint_binding_invalid", target.path)
        return target, feedback_digest, feedback.status
    return entry, feedback_digest, feedback.status


def validate_external_bindings(
    entry: CheckpointEntry | None,
    approval_digest: str,
    trace_contract_digest: str,
    config_digest: str,
    selector: SelectorBindingModel,
) -> None:
    if entry is None:
        return
    checkpoint = entry.checkpoint
    if (
        checkpoint.approved_trace_sha256 != approval_digest
        or checkpoint.approved_trace_contract_sha256 != trace_contract_digest
    ):
        raise CandidateCharacterizationError("approved_trace_binding_invalid", entry.path)
    if checkpoint.candidate_config_sha256 != config_digest:
        raise CandidateCharacterizationError("candidate_config_binding_invalid", entry.path)
    if checkpoint.selector != selector:
        raise CandidateCharacterizationError("selector_binding_invalid", entry.path)
