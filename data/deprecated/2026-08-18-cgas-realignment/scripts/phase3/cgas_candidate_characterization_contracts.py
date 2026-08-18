from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from .cgas_candidate_characterization_models import (
    ApprovedTraceModel,
    CheckpointModel,
    FeedbackModel,
    JsonObject,
    SelectorBindingModel,
    StrictModel,
)
from .cgas_partition_contracts import EXPECTED_OBJECT_COUNTS, EXPECTED_SPLIT_COUNTS
from .cgas_partition_selection import CALIBRATION_SIZE, MIN_EVALUATION_ROWS, MIN_OOD_SIGNATURES, POLICY
from .cgas_trace_contract_approval import TraceApprovalError, verify_owner_approval
from .cgas_trace_contract_v3 import (
    NEW_CONTRACT_SHA256,
    OWNER_APPROVAL_PATH,
    PACKET_PATH,
    POLICY_SHA256,
)

ModelT = TypeVar("ModelT", bound=StrictModel)


@dataclass(frozen=True, slots=True)
class CandidateCharacterizationError(RuntimeError):
    code: str
    path: Path

    def __str__(self) -> str:
        return f"{self.code}:{self.path}"


def canonical_bytes(record: JsonObject) -> bytes:
    return json.dumps(record, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()


def sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def model_bytes(model: StrictModel) -> bytes:
    return json.dumps(
        model.model_dump(mode="json", exclude_none=isinstance(model, FeedbackModel)),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def parse_canonical_model(path: Path, model_type: type[ModelT], code: str) -> tuple[ModelT, bytes]:
    try:
        contents = path.read_bytes()
        model = model_type.model_validate_json(contents)
    except (OSError, ValidationError) as error:
        raise CandidateCharacterizationError(code, path) from error
    if contents != model_bytes(model) + b"\n":
        raise CandidateCharacterizationError(code, path)
    return model, contents


def validate_approval(path: Path) -> tuple[ApprovedTraceModel, str]:
    approval, contents = parse_canonical_model(path, ApprovedTraceModel, "approved_trace_contract_invalid")
    packet = path.with_name(PACKET_PATH.name)
    owner = path.with_name(OWNER_APPROVAL_PATH.name)
    try:
        verified = verify_owner_approval(packet, owner)
    except (OSError, TraceApprovalError) as error:
        raise CandidateCharacterizationError("approved_trace_contract_invalid", path) from error
    try:
        expected = ApprovedTraceModel.model_validate(verified.approved_record())
    except ValidationError as error:
        raise CandidateCharacterizationError("approved_trace_contract_invalid", path) from error
    if (
        approval != expected
        or approval.contract_sha256 != NEW_CONTRACT_SHA256
        or approval.policy_sha256 != POLICY_SHA256
    ):
        raise CandidateCharacterizationError("approved_trace_contract_invalid", path)
    return approval, sha256(contents)


def selector_binding() -> SelectorBindingModel:
    implementation = Path(__file__).with_name("cgas_partition_selection.py").read_bytes()
    config: JsonObject = {
        "calibration_size": CALIBRATION_SIZE,
        "expected_object_counts": {str(key): value for key, value in sorted(EXPECTED_OBJECT_COUNTS.items())},
        "expected_split_counts": dict(sorted(EXPECTED_SPLIT_COUNTS.items())),
        "minimum_evaluation_rows": MIN_EVALUATION_ROWS,
        "minimum_ood_signatures": MIN_OOD_SIGNATURES,
        "policy": POLICY,
    }
    return SelectorBindingModel(
        config_sha256=sha256(canonical_bytes(config)),
        implementation_sha256=sha256(implementation),
    )


def validate_feedback(
    path: Path,
    checkpoint_path: Path,
    checkpoint: CheckpointModel,
    checkpoint_digest: str,
) -> tuple[FeedbackModel, str]:
    expected_name = f"selector_attempt_{checkpoint.round:06d}.json"
    if path.name != expected_name:
        raise CandidateCharacterizationError("feedback_filename_invalid", path)
    feedback, contents = parse_canonical_model(path, FeedbackModel, "feedback_invalid")
    expected_streams = [stream.object_count for stream in checkpoint.streams if not stream.exhausted]
    expected = (
        feedback.round == checkpoint.round
        and feedback.checkpoint_sha256 == checkpoint_digest
        and feedback.reservoir_sha256 == checkpoint.reservoir.sha256
        and feedback.selector_implementation_sha256 == checkpoint.selector.implementation_sha256
        and feedback.selector_config_sha256 == checkpoint.selector.config_sha256
        and feedback.non_exhausted_streams == expected_streams
    )
    if not expected:
        raise CandidateCharacterizationError("feedback_binding_invalid", checkpoint_path)
    return feedback, sha256(contents)


def confined(path: Path, repository_root: Path) -> Path:
    try:
        return path.resolve().relative_to(repository_root.resolve())
    except ValueError as error:
        raise CandidateCharacterizationError("path_outside_repository", path) from error
