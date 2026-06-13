"""Metadata, rejection, and resumability contracts for curriculum generation."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .hashing import DuplicateProblemHash


RESULT_SCHEMA_VERSION = 1
SUMMARY_SCHEMA_VERSION = 1
ACCEPTED_STATUS = "accepted"
REJECTED_STATUS = "rejected"
SUMMARY_STATUS = "summary"
DUPLICATE_HASH_REASON = "duplicate_hash"


def _validate_identifier_fragment(name: str, value: str) -> str:
    if not value:
        raise ValueError(f"{name} must be non-empty")
    if any(character.isspace() for character in value):
        raise ValueError(f"{name} must not contain whitespace: {value!r}")
    if "/" in value:
        raise ValueError(f"{name} must not contain path separators: {value!r}")
    return value


def _validate_non_negative(name: str, value: int) -> int:
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")
    return value


def _to_json_ready(payload: dict[str, Any]) -> dict[str, Any]:
    json_ready = dict(payload)
    if isinstance(json_ready.get("generator_command"), tuple):
        json_ready["generator_command"] = list(json_ready["generator_command"])
    if isinstance(json_ready.get("render_artifact_paths"), tuple):
        json_ready["render_artifact_paths"] = list(json_ready["render_artifact_paths"])
    return json_ready


def build_instance_id(domain_id: str, split: str, bucket: str, index: int) -> str:
    """Build the stable accepted instance identifier contract."""

    _validate_identifier_fragment("domain_id", domain_id)
    _validate_identifier_fragment("split", split)
    _validate_identifier_fragment("bucket", bucket)
    _validate_non_negative("index", index)
    return f"{domain_id}-{split}-{bucket}-{index:04d}"


def build_candidate_id(domain_id: str, split: str, bucket: str, attempt_index: int) -> str:
    """Build the stable candidate identifier contract."""

    _validate_identifier_fragment("domain_id", domain_id)
    _validate_identifier_fragment("split", split)
    _validate_identifier_fragment("bucket", bucket)
    _validate_non_negative("attempt_index", attempt_index)
    return f"{domain_id}-{split}-{bucket}-attempt-{attempt_index:06d}"


@dataclass(frozen=True)
class AcceptedInstanceMetadata:
    """Structured metadata for one accepted curriculum instance."""

    instance_id: str
    candidate_id: str
    domain_id: str
    split: str
    bucket: str
    index: int
    attempt_index: int
    seed: int | None = None
    domain_path: str = ""
    problem_path: str = ""
    generator_command: tuple[str, ...] = ()
    generator_cwd: str = ""
    stdout_path: str = ""
    stderr_path: str = ""
    domain_hash: str = ""
    normalized_domain_hash: str = ""
    problem_hash: str = ""
    normalized_problem_hash: str = ""
    render_status: str = ""
    render_artifact_paths: tuple[str, ...] = ()
    render_result_path: str = ""
    difficulty_target: str = ""
    difficulty_measured: str = ""
    measured_difficulty: float | None = None
    measured_bucket: str = ""
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    schema_version: int = RESULT_SCHEMA_VERSION
    status: str = ACCEPTED_STATUS

    def __post_init__(self) -> None:
        expected_instance_id = build_instance_id(self.domain_id, self.split, self.bucket, self.index)
        expected_candidate_id = build_candidate_id(self.domain_id, self.split, self.bucket, self.attempt_index)
        if self.instance_id != expected_instance_id:
            raise ValueError(f"instance_id must equal {expected_instance_id!r}, got {self.instance_id!r}")
        if self.candidate_id != expected_candidate_id:
            raise ValueError(f"candidate_id must equal {expected_candidate_id!r}, got {self.candidate_id!r}")
        if self.status != ACCEPTED_STATUS:
            raise ValueError(f"accepted metadata status must be {ACCEPTED_STATUS!r}")
        if not self.difficulty_target:
            object.__setattr__(self, "difficulty_target", self.bucket)
        normalized_measured = self.difficulty_measured or self.measured_bucket
        if normalized_measured:
            if not self.difficulty_measured:
                object.__setattr__(self, "difficulty_measured", normalized_measured)
            if not self.measured_bucket:
                object.__setattr__(self, "measured_bucket", normalized_measured)

    def to_dict(self) -> dict[str, Any]:
        return _to_json_ready(asdict(self))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AcceptedInstanceMetadata":
        return cls(
            instance_id=str(payload["instance_id"]),
            candidate_id=str(payload["candidate_id"]),
            domain_id=str(payload["domain_id"]),
            split=str(payload["split"]),
            bucket=str(payload["bucket"]),
            index=int(payload["index"]),
            attempt_index=int(payload["attempt_index"]),
            seed=int(payload["seed"]) if payload.get("seed") is not None else None,
            domain_path=str(payload.get("domain_path", "")),
            problem_path=str(payload.get("problem_path", "")),
            generator_command=tuple(str(item) for item in payload.get("generator_command", ())),
            generator_cwd=str(payload.get("generator_cwd", "")),
            stdout_path=str(payload.get("stdout_path", "")),
            stderr_path=str(payload.get("stderr_path", "")),
            domain_hash=str(payload.get("domain_hash", "")),
            normalized_domain_hash=str(payload.get("normalized_domain_hash", "")),
            problem_hash=str(payload.get("problem_hash", "")),
            normalized_problem_hash=str(payload.get("normalized_problem_hash", "")),
            render_status=str(payload.get("render_status", "")),
            render_artifact_paths=tuple(str(item) for item in payload.get("render_artifact_paths", ())),
            render_result_path=str(payload.get("render_result_path", "")),
            difficulty_target=str(payload.get("difficulty_target", payload.get("bucket", ""))),
            difficulty_measured=str(payload.get("difficulty_measured", payload.get("measured_bucket", ""))),
            measured_difficulty=float(payload["measured_difficulty"])
            if payload.get("measured_difficulty") is not None
            else None,
            measured_bucket=str(payload.get("measured_bucket", "")),
            notes=str(payload.get("notes", "")),
            extra=dict(payload.get("extra", {})),
            schema_version=int(payload.get("schema_version", RESULT_SCHEMA_VERSION)),
            status=str(payload.get("status", ACCEPTED_STATUS)),
        )


@dataclass(frozen=True)
class RejectedCandidateMetadata:
    """Structured metadata for one rejected candidate."""

    candidate_id: str
    domain_id: str
    split: str
    bucket: str
    attempt_index: int
    seed: int | None = None
    rejection_reason: str = ""
    rejection_stage: str = ""
    message: str = ""
    problem_hash: str = ""
    normalized_problem_hash: str = ""
    duplicate_of_instance_id: str = ""
    generator_command: tuple[str, ...] = ()
    generator_cwd: str = ""
    stdout_path: str = ""
    stderr_path: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    schema_version: int = RESULT_SCHEMA_VERSION
    status: str = REJECTED_STATUS

    def __post_init__(self) -> None:
        expected_candidate_id = build_candidate_id(self.domain_id, self.split, self.bucket, self.attempt_index)
        if self.candidate_id != expected_candidate_id:
            raise ValueError(f"candidate_id must equal {expected_candidate_id!r}, got {self.candidate_id!r}")
        if self.status != REJECTED_STATUS:
            raise ValueError(f"rejected metadata status must be {REJECTED_STATUS!r}")

    def to_dict(self) -> dict[str, Any]:
        return _to_json_ready(asdict(self))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RejectedCandidateMetadata":
        return cls(
            candidate_id=str(payload["candidate_id"]),
            domain_id=str(payload["domain_id"]),
            split=str(payload["split"]),
            bucket=str(payload["bucket"]),
            attempt_index=int(payload["attempt_index"]),
            seed=int(payload["seed"]) if payload.get("seed") is not None else None,
            rejection_reason=str(payload.get("rejection_reason", "")),
            rejection_stage=str(payload.get("rejection_stage", "")),
            message=str(payload.get("message", "")),
            problem_hash=str(payload.get("problem_hash", "")),
            normalized_problem_hash=str(payload.get("normalized_problem_hash", "")),
            duplicate_of_instance_id=str(payload.get("duplicate_of_instance_id", "")),
            generator_command=tuple(str(item) for item in payload.get("generator_command", ())),
            generator_cwd=str(payload.get("generator_cwd", "")),
            stdout_path=str(payload.get("stdout_path", "")),
            stderr_path=str(payload.get("stderr_path", "")),
            details=dict(payload.get("details", {})),
            schema_version=int(payload.get("schema_version", RESULT_SCHEMA_VERSION)),
            status=str(payload.get("status", REJECTED_STATUS)),
        )


@dataclass(frozen=True)
class SummaryMetadata:
    """Top-level summary metadata for one curriculum generation run."""

    accepted_total: int
    rejected_total: int
    duplicate_accepted_problem_hashes: int
    domains_completed: int
    accepted_by_split: dict[str, int] = field(default_factory=dict)
    accepted_by_bucket: dict[str, int] = field(default_factory=dict)
    accepted_by_domain: dict[str, int] = field(default_factory=dict)
    rejected_by_reason: dict[str, int] = field(default_factory=dict)
    render_failed_accepted: int = 0
    resumed_accepted_total: int = 0
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SUMMARY_SCHEMA_VERSION
    status: str = SUMMARY_STATUS

    def __post_init__(self) -> None:
        _validate_non_negative("accepted_total", self.accepted_total)
        _validate_non_negative("rejected_total", self.rejected_total)
        _validate_non_negative("duplicate_accepted_problem_hashes", self.duplicate_accepted_problem_hashes)
        _validate_non_negative("domains_completed", self.domains_completed)
        _validate_non_negative("render_failed_accepted", self.render_failed_accepted)
        _validate_non_negative("resumed_accepted_total", self.resumed_accepted_total)
        if self.status != SUMMARY_STATUS:
            raise ValueError(f"summary metadata status must be {SUMMARY_STATUS!r}")
        if self.accepted_by_split and self.accepted_total != sum(self.accepted_by_split.values()):
            raise ValueError("accepted_total must equal the sum of accepted_by_split")
        if self.rejected_by_reason and self.rejected_total != sum(self.rejected_by_reason.values()):
            raise ValueError("rejected_total must equal the sum of rejected_by_reason")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SummaryMetadata":
        return cls(
            accepted_total=int(payload.get("accepted_total", 0)),
            rejected_total=int(payload.get("rejected_total", 0)),
            duplicate_accepted_problem_hashes=int(payload.get("duplicate_accepted_problem_hashes", 0)),
            domains_completed=int(payload.get("domains_completed", 0)),
            accepted_by_split={str(key): int(value) for key, value in dict(payload.get("accepted_by_split", {})).items()},
            accepted_by_bucket={str(key): int(value) for key, value in dict(payload.get("accepted_by_bucket", {})).items()},
            accepted_by_domain={str(key): int(value) for key, value in dict(payload.get("accepted_by_domain", {})).items()},
            rejected_by_reason={str(key): int(value) for key, value in dict(payload.get("rejected_by_reason", {})).items()},
            render_failed_accepted=int(payload.get("render_failed_accepted", 0)),
            resumed_accepted_total=int(payload.get("resumed_accepted_total", 0)),
            notes=str(payload.get("notes", "")),
            extra=dict(payload.get("extra", {})),
            schema_version=int(payload.get("schema_version", SUMMARY_SCHEMA_VERSION)),
            status=str(payload.get("status", SUMMARY_STATUS)),
        )


@dataclass(frozen=True)
class ResumeDecision:
    """Describes whether a result path may be written during resume."""

    action: str
    should_write: bool
    result_path: str
    reason: str = ""
    existing_status: str = ""
    existing_instance_id: str = ""


def build_duplicate_rejection(
    *,
    candidate_id: str,
    domain_id: str,
    split: str,
    bucket: str,
    attempt_index: int,
    normalized_problem_hash: str,
    duplicate: DuplicateProblemHash,
    seed: int | None = None,
    problem_hash: str = "",
    message: str = "Normalized problem hash already accepted in another split or bucket.",
) -> RejectedCandidateMetadata:
    """Build the canonical duplicate-hash rejection payload."""

    return RejectedCandidateMetadata(
        candidate_id=candidate_id,
        domain_id=domain_id,
        split=split,
        bucket=bucket,
        attempt_index=attempt_index,
        seed=seed,
        rejection_reason=DUPLICATE_HASH_REASON,
        rejection_stage="dedupe",
        message=message,
        problem_hash=problem_hash,
        normalized_problem_hash=normalized_problem_hash,
        duplicate_of_instance_id=duplicate.existing_instance_id,
        details={
            "existing_bucket": duplicate.existing_bucket,
            "existing_domain_id": duplicate.existing_domain_id,
            "existing_instance_id": duplicate.existing_instance_id,
            "existing_split": duplicate.existing_split,
            "normalized_problem_hash": duplicate.normalized_problem_hash,
        },
    )


def build_summary_metadata(
    *,
    accepted_instances: list[AcceptedInstanceMetadata],
    rejected_candidates: list[RejectedCandidateMetadata],
    duplicate_accepted_problem_hashes: int = 0,
    resumed_accepted_total: int = 0,
    domains_completed: int | None = None,
    notes: str = "",
    extra: Mapping[str, Any] | None = None,
) -> SummaryMetadata:
    """Aggregate accepted/rejected records into the top-level summary contract."""

    accepted_by_split = Counter(instance.split for instance in accepted_instances)
    accepted_by_bucket = Counter(instance.bucket for instance in accepted_instances)
    accepted_by_domain = Counter(instance.domain_id for instance in accepted_instances)
    rejected_by_reason = Counter(candidate.rejection_reason for candidate in rejected_candidates if candidate.rejection_reason)
    render_failed_accepted = sum(1 for instance in accepted_instances if instance.render_status != "success")
    completed_domains = domains_completed if domains_completed is not None else len(accepted_by_domain)

    return SummaryMetadata(
        accepted_total=len(accepted_instances),
        rejected_total=len(rejected_candidates),
        duplicate_accepted_problem_hashes=duplicate_accepted_problem_hashes,
        domains_completed=completed_domains,
        accepted_by_split=dict(accepted_by_split),
        accepted_by_bucket=dict(accepted_by_bucket),
        accepted_by_domain=dict(accepted_by_domain),
        rejected_by_reason=dict(rejected_by_reason),
        render_failed_accepted=render_failed_accepted,
        resumed_accepted_total=resumed_accepted_total,
        notes=notes,
        extra=dict(extra or {}),
    )


def load_metadata_payload(path: Path) -> dict[str, Any] | None:
    """Load a result or summary payload from disk, if it exists."""

    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Metadata file {path} must contain a JSON object")
    return payload


def resolve_resume_decision(result_path: Path, *, force: bool = False) -> ResumeDecision:
    """Determine whether generation may write to *result_path*."""

    existing_payload = load_metadata_payload(result_path)
    if existing_payload is None:
        return ResumeDecision(action="write_new", should_write=True, result_path=str(result_path))

    existing_status = str(existing_payload.get("status", ""))
    existing_instance_id = str(existing_payload.get("instance_id", ""))
    if force:
        return ResumeDecision(
            action="overwrite_forced",
            should_write=True,
            result_path=str(result_path),
            existing_status=existing_status,
            existing_instance_id=existing_instance_id,
            reason="force=True allows overwriting existing metadata.",
        )

    if existing_status == ACCEPTED_STATUS:
        return ResumeDecision(
            action="skip_existing_accepted",
            should_write=False,
            result_path=str(result_path),
            existing_status=existing_status,
            existing_instance_id=existing_instance_id,
            reason="Resume preserves existing accepted metadata unless force=True.",
        )

    return ResumeDecision(
        action="overwrite_existing_nonaccepted",
        should_write=True,
        result_path=str(result_path),
        existing_status=existing_status,
        existing_instance_id=existing_instance_id,
        reason="Existing metadata is not accepted and may be replaced.",
    )


def write_result_metadata(
    result_path: Path,
    metadata: AcceptedInstanceMetadata | RejectedCandidateMetadata | Mapping[str, Any],
    *,
    force: bool = False,
) -> ResumeDecision:
    """Persist result metadata while honoring resume protection semantics."""

    decision = resolve_resume_decision(result_path, force=force)
    if not decision.should_write:
        return decision

    if isinstance(metadata, (AcceptedInstanceMetadata, RejectedCandidateMetadata)):
        payload = metadata.to_dict()
    else:
        payload = dict(metadata)

    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return decision


def write_summary_metadata(summary_path: Path, summary: SummaryMetadata) -> None:
    """Persist top-level summary metadata using the project JSON style."""

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


__all__ = [
    "ACCEPTED_STATUS",
    "DUPLICATE_HASH_REASON",
    "AcceptedInstanceMetadata",
    "REJECTED_STATUS",
    "RESULT_SCHEMA_VERSION",
    "ResumeDecision",
    "SUMMARY_SCHEMA_VERSION",
    "SUMMARY_STATUS",
    "SummaryMetadata",
    "RejectedCandidateMetadata",
    "build_candidate_id",
    "build_duplicate_rejection",
    "build_instance_id",
    "build_summary_metadata",
    "load_metadata_payload",
    "resolve_resume_decision",
    "write_result_metadata",
    "write_summary_metadata",
]
