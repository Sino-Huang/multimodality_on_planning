"""Curriculum PDDL generation orchestration."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .adapters import GenerationSpec, GeneratorAdapter, GeneratorRejection, build_domain_registry
from .config import CurriculumConfig, DomainConfig
from .difficulty import DIFFICULTY_BUCKETS, hybrid_measured_percentile
from .hashing import AcceptedProblemFingerprint, AcceptedProblemHashIndex, build_pddl_hash_info
from .metadata import (
    DUPLICATE_HASH_REASON,
    AcceptedInstanceMetadata,
    RejectedCandidateMetadata,
    SummaryMetadata,
    build_candidate_id,
    build_instance_id,
    build_summary_metadata,
    load_metadata_payload,
    write_result_metadata,
    write_summary_metadata,
)
from .rendering import Renderer, gate_rendered_candidate, require_rendering_preflight
from .selection import select_stratified_by_measured_bucket

GENERATION_REJECTION_STAGE = "generation"
DEDUPE_REJECTION_STAGE = "dedupe"
SELECTION_REJECTION_STAGE = "selection"
SELECTION_NOT_SELECTED_REASON = "selection_not_selected"
REJECTIONS_FILENAME = "rejections.jsonl"
ACCEPTED_MANIFEST_FILENAME = "accepted_manifest.jsonl"
SUMMARY_FILENAME = "summary.json"
STAGING_DIRNAME = ".staging"


@dataclass(frozen=True)
class GenerationRunResult:
    accepted_instances: tuple[AcceptedInstanceMetadata, ...]
    rejected_candidates: tuple[RejectedCandidateMetadata, ...]
    summary: SummaryMetadata
    output_root: Path
    accepted_manifest_path: Path
    rejections_path: Path
    summary_path: Path


def orchestrate_generation(
    curriculum_config: CurriculumConfig,
    *,
    output_root: Path | str,
    renderer: Renderer | None,
    max_attempts_per_bucket: int,
    seed: int,
    force: bool = False,
    domains: Sequence[str] | None = None,
    splits: Sequence[str] | None = None,
    quotas_by_split: Mapping[str, Mapping[str, int]] | None = None,
    candidate_multiplier: int | None = None,
    registry: Mapping[str, GeneratorAdapter] | None = None,
) -> GenerationRunResult:
    if max_attempts_per_bucket <= 0:
        raise ValueError("max_attempts_per_bucket must be positive")
    if curriculum_config.require_rendering and renderer is None:
        raise ValueError("renderer is required when curriculum_config.require_rendering is true")

    resolved_output_root = Path(output_root).resolve()
    if force and resolved_output_root.exists():
        shutil.rmtree(resolved_output_root)
    resolved_output_root.mkdir(parents=True, exist_ok=True)

    selected_domains = _select_domains(curriculum_config, domains)
    selected_splits = _select_splits(curriculum_config, splits)
    resolved_quotas = _resolve_quotas(curriculum_config, selected_splits, quotas_by_split)
    resolved_candidate_multiplier = candidate_multiplier or curriculum_config.candidate_multiplier
    if resolved_candidate_multiplier <= 0:
        raise ValueError("candidate_multiplier must be positive")

    require_rendering_preflight(
        replace(curriculum_config, domains=selected_domains),
        renderer=renderer,
        timeout_seconds=curriculum_config.timeouts.render_seconds,
    )

    domain_registry = dict(registry or build_domain_registry(replace(curriculum_config, domains=selected_domains)))
    _require_adapter_readiness(domain_registry, selected_domains)
    resume_hash_splits = tuple(curriculum_config.splits)
    existing_accepted = [] if force else _load_existing_accepted(resolved_output_root, selected_domains, resume_hash_splits)
    existing_rejections = [] if force else _load_rejections(resolved_output_root / REJECTIONS_FILENAME)

    accepted_instances: list[AcceptedInstanceMetadata] = list(existing_accepted)
    rejected_candidates: list[RejectedCandidateMetadata] = list(existing_rejections)
    hash_index = AcceptedProblemHashIndex(
        AcceptedProblemFingerprint(
            normalized_problem_hash=instance.normalized_problem_hash,
            instance_id=instance.instance_id,
            domain_id=instance.domain_id,
            split=instance.split,
            bucket=instance.bucket,
        )
        for instance in existing_accepted
        if instance.normalized_problem_hash
    )

    next_attempt_index = _build_next_attempt_index(existing_accepted, existing_rejections, selected_domains, selected_splits)
    historical_attempt_counts = _build_historical_attempt_counts(existing_accepted, existing_rejections)
    selection_reports: dict[str, dict[str, dict[str, Any]]] = {}

    for domain in selected_domains:
        adapter = domain_registry.get(domain.domain_id)
        if adapter is None:
            raise KeyError(f"No adapter registered for domain '{domain.domain_id}'")
        adapter.prepare()

        for split in selected_splits:
            remaining_quotas = _remaining_quotas(accepted_instances, domain_id=domain.domain_id, split=split, quotas=resolved_quotas[split])
            if sum(remaining_quotas.values()) == 0:
                selection_reports.setdefault(domain.domain_id, {})[split] = {
                    "requested_counts": {bucket: int(count) for bucket, count in resolved_quotas[split].items()},
                    "remaining_quotas": {bucket: int(count) for bucket, count in remaining_quotas.items()},
                    "selected_counts": {bucket: 0 for bucket in DIFFICULTY_BUCKETS},
                    "available_counts": {bucket: 0 for bucket in DIFFICULTY_BUCKETS},
                    "incomplete_buckets": [],
                    "attempt_counts": {
                        bucket: historical_attempt_counts[(domain.domain_id, split, bucket)]
                        for bucket in DIFFICULTY_BUCKETS
                    },
                    "resumed_only": True,
                }
                continue

            pool_candidates: list[AcceptedInstanceMetadata] = []
            pool_by_hash: dict[str, AcceptedInstanceMetadata] = {}
            current_attempt_counts = {
                bucket: historical_attempt_counts[(domain.domain_id, split, bucket)]
                for bucket in DIFFICULTY_BUCKETS
            }

            for target_bucket in DIFFICULTY_BUCKETS:
                pool_target_size = int(resolved_quotas[split].get(target_bucket, 0)) * resolved_candidate_multiplier
                bucket_pool_count = 0
                while bucket_pool_count < pool_target_size and current_attempt_counts[target_bucket] < max_attempts_per_bucket:
                    attempt_index = next_attempt_index[(domain.domain_id, split)]
                    next_attempt_index[(domain.domain_id, split)] += 1
                    current_attempt_counts[target_bucket] += 1

                    source_candidate_id = build_candidate_id(domain.domain_id, split, target_bucket, attempt_index)
                    candidate_output_dir = _candidate_output_dir(
                        resolved_output_root,
                        domain_id=domain.domain_id,
                        split=split,
                        target_bucket=target_bucket,
                        candidate_id=source_candidate_id,
                    )
                    candidate_seed = _derive_candidate_seed(
                        seed=seed,
                        domain_id=domain.domain_id,
                        split=split,
                        target_bucket=target_bucket,
                        attempt_index=attempt_index,
                        seed_range=curriculum_config.seed_range,
                    )
                    spec = GenerationSpec(
                        candidate_id=source_candidate_id,
                        output_dir=candidate_output_dir,
                        timeout_seconds=curriculum_config.timeouts.generator_seconds,
                        seed=candidate_seed if adapter.supports_seed() else None,
                        extra={
                            "domain_id": domain.domain_id,
                            "preset_id": target_bucket,
                            "split": split,
                            "target_bucket": target_bucket,
                            "attempt_index": attempt_index,
                            "bucket_attempt_index": current_attempt_counts[target_bucket] - 1,
                        },
                    )

                    normalized_or_rejection = adapter.normalize_outputs(adapter.generate_candidate(spec))
                    if isinstance(normalized_or_rejection, GeneratorRejection):
                        rejected_candidates.append(
                            _build_generation_rejection(
                                rejection=normalized_or_rejection,
                                domain_id=domain.domain_id,
                                split=split,
                                bucket=target_bucket,
                                attempt_index=attempt_index,
                            )
                        )
                        continue

                    rendered_or_rejection = gate_rendered_candidate(
                        candidate=normalized_or_rejection,
                        split=split,
                        bucket=target_bucket,
                        index=attempt_index,
                        attempt_index=attempt_index,
                        renderer=renderer,
                        render_profile_path=domain.render_profile_path,
                        timeout_seconds=curriculum_config.timeouts.render_seconds,
                        extra={
                            "orchestrator": {
                                "source_candidate_id": source_candidate_id,
                                "source_target_bucket": target_bucket,
                                "staging_output_dir": str(candidate_output_dir),
                            }
                        },
                    )
                    if isinstance(rendered_or_rejection, RejectedCandidateMetadata):
                        rejected_candidates.append(rendered_or_rejection)
                        continue

                    hashed_candidate = _annotate_hashes(rendered_or_rejection)
                    duplicate_rejection = _check_duplicate_candidate(
                        candidate=hashed_candidate,
                        accepted_hash_index=hash_index,
                        pool_by_hash=pool_by_hash,
                    )
                    if duplicate_rejection is not None:
                        rejected_candidates.append(duplicate_rejection)
                        continue

                    pool_by_hash[hashed_candidate.normalized_problem_hash] = hashed_candidate
                    pool_candidates.append(hashed_candidate)
                    bucket_pool_count += 1

            measured_pool = hybrid_measured_percentile(pool_candidates) if pool_candidates else ()
            selection_result = select_stratified_by_measured_bucket(
                measured_pool,
                {split: remaining_quotas},
            )
            selected_candidate_ids = {instance.candidate_id for instance in selection_result.selected_instances}
            for candidate in measured_pool:
                if candidate.candidate_id in selected_candidate_ids:
                    continue
                rejected_candidates.append(_build_selection_rejection(candidate))

            for selected in selection_result.selected_instances:
                finalized = _finalize_selected_candidate(
                    candidate=selected,
                    output_root=resolved_output_root,
                    force=force,
                    existing_instances=accepted_instances,
                )
                write_result_metadata(_accepted_result_path(resolved_output_root, finalized), finalized, force=force)
                accepted_instances.append(finalized)
                if finalized.normalized_problem_hash:
                    hash_index.register(
                        normalized_problem_hash=finalized.normalized_problem_hash,
                        instance_id=finalized.instance_id,
                        domain_id=finalized.domain_id,
                        split=finalized.split,
                        bucket=finalized.bucket,
                        duplicate_identifier=finalized.candidate_id,
                    )

            selection_reports.setdefault(domain.domain_id, {})[split] = {
                "requested_counts": {bucket: int(count) for bucket, count in selection_result.requested_counts.get(domain.domain_id, {}).get(split, {}).items()},
                "remaining_quotas": {bucket: int(count) for bucket, count in remaining_quotas.items()},
                "selected_counts": {bucket: int(count) for bucket, count in selection_result.selected_counts.get(domain.domain_id, {}).get(split, {}).items()},
                "available_counts": {bucket: int(count) for bucket, count in selection_result.available_counts.get(domain.domain_id, {}).get(split, {}).items()},
                "incomplete_buckets": [
                    summary.to_dict()
                    for summary in selection_result.incomplete_buckets
                    if summary.domain_id == domain.domain_id and summary.split == split
                ],
                "attempt_counts": {bucket: int(count) for bucket, count in current_attempt_counts.items()},
                "pool_size": len(pool_candidates),
                "selected_pool_size": len(selection_result.selected_instances),
                "resumed_only": False,
            }

    duplicate_accepted_problem_hashes = _count_duplicate_problem_hashes(accepted_instances)
    domains_completed = _count_completed_domains(accepted_instances, selected_domains, selected_splits, resolved_quotas)
    summary = build_summary_metadata(
        accepted_instances=_sorted_accepted_instances(accepted_instances),
        rejected_candidates=_sorted_rejections(rejected_candidates),
        duplicate_accepted_problem_hashes=duplicate_accepted_problem_hashes,
        resumed_accepted_total=len(existing_accepted),
        domains_completed=domains_completed,
        extra={
            "selection": selection_reports,
            "selected_domains": [domain.domain_id for domain in selected_domains],
            "selected_splits": list(selected_splits),
            "max_attempts_per_bucket": max_attempts_per_bucket,
            "candidate_multiplier": resolved_candidate_multiplier,
        },
    )

    accepted_manifest_path = resolved_output_root / ACCEPTED_MANIFEST_FILENAME
    rejections_path = resolved_output_root / REJECTIONS_FILENAME
    summary_path = resolved_output_root / SUMMARY_FILENAME
    _write_jsonl(accepted_manifest_path, [instance.to_dict() for instance in _sorted_accepted_instances(accepted_instances)])
    _write_jsonl(rejections_path, [rejection.to_dict() for rejection in _sorted_rejections(rejected_candidates)])
    write_summary_metadata(summary_path, summary)

    return GenerationRunResult(
        accepted_instances=tuple(_sorted_accepted_instances(accepted_instances)),
        rejected_candidates=tuple(_sorted_rejections(rejected_candidates)),
        summary=summary,
        output_root=resolved_output_root,
        accepted_manifest_path=accepted_manifest_path,
        rejections_path=rejections_path,
        summary_path=summary_path,
    )


def _select_domains(curriculum_config: CurriculumConfig, domains: Sequence[str] | None) -> tuple[DomainConfig, ...]:
    if domains is None:
        return curriculum_config.domains
    requested = tuple(domain.strip() for domain in domains if domain.strip())
    domain_map = {domain.domain_id: domain for domain in curriculum_config.domains}
    missing = [domain_id for domain_id in requested if domain_id not in domain_map]
    if missing:
        raise KeyError(f"Unknown domain ids requested: {missing}")
    return tuple(domain_map[domain_id] for domain_id in requested)


def _require_adapter_readiness(
    domain_registry: Mapping[str, GeneratorAdapter],
    selected_domains: Sequence[DomainConfig],
) -> None:
    issues: list[str] = []
    for domain in selected_domains:
        adapter = domain_registry.get(domain.domain_id)
        if adapter is None:
            continue

        inspect_readiness = getattr(adapter, "inspect_readiness", None)
        if not callable(inspect_readiness):
            continue

        capability = inspect_readiness()
        if bool(getattr(capability, "ready", True)):
            continue

        failures = tuple(getattr(capability, "readiness_failures", ()))
        if not failures:
            issues.append(f"{domain.domain_id}: adapter readiness failed")
            continue

        for failure in failures:
            code = str(getattr(failure, "code", "unknown"))
            message = str(getattr(failure, "message", "adapter readiness failed"))
            path = getattr(failure, "path", None)
            path_suffix = f" ({path})" if path else ""
            issues.append(f"{domain.domain_id}: {code}: {message}{path_suffix}")

    if issues:
        raise RuntimeError("Generator readiness preflight failed: " + "; ".join(issues))


def _select_splits(curriculum_config: CurriculumConfig, splits: Sequence[str] | None) -> tuple[str, ...]:
    if splits is None:
        return tuple(curriculum_config.splits)
    requested = tuple(split.strip() for split in splits if split.strip())
    missing = [split for split in requested if split not in curriculum_config.splits]
    if missing:
        raise KeyError(f"Unknown splits requested: {missing}")
    return requested


def _resolve_quotas(
    curriculum_config: CurriculumConfig,
    selected_splits: Sequence[str],
    quotas_by_split: Mapping[str, Mapping[str, int]] | None,
) -> dict[str, dict[str, int]]:
    resolved: dict[str, dict[str, int]] = {}
    for split in selected_splits:
        base = dict(curriculum_config.splits[split].buckets)
        if quotas_by_split and split in quotas_by_split:
            override = quotas_by_split[split]
            base = {bucket: int(override.get(bucket, 0)) for bucket in DIFFICULTY_BUCKETS}
        resolved[split] = base
    return resolved


def _build_next_attempt_index(
    accepted_instances: Sequence[AcceptedInstanceMetadata],
    rejected_candidates: Sequence[RejectedCandidateMetadata],
    selected_domains: Sequence[DomainConfig],
    selected_splits: Sequence[str],
) -> dict[tuple[str, str], int]:
    next_attempt_index = {(domain.domain_id, split): 0 for domain in selected_domains for split in selected_splits}
    for instance in accepted_instances:
        key = (instance.domain_id, instance.split)
        next_attempt_index[key] = max(next_attempt_index.get(key, 0), instance.attempt_index + 1)
    for rejection in rejected_candidates:
        key = (rejection.domain_id, rejection.split)
        next_attempt_index[key] = max(next_attempt_index.get(key, 0), rejection.attempt_index + 1)
    return next_attempt_index


def _build_historical_attempt_counts(
    accepted_instances: Sequence[AcceptedInstanceMetadata],
    rejected_candidates: Sequence[RejectedCandidateMetadata],
) -> Counter[tuple[str, str, str]]:
    counts: Counter[tuple[str, str, str]] = Counter()
    for instance in accepted_instances:
        target_bucket = instance.difficulty_target or instance.extra.get("orchestrator", {}).get("source_target_bucket") or instance.bucket
        counts[(instance.domain_id, instance.split, str(target_bucket))] += 1
    for rejection in rejected_candidates:
        counts[(rejection.domain_id, rejection.split, rejection.bucket)] += 1
    return counts


def _remaining_quotas(
    accepted_instances: Sequence[AcceptedInstanceMetadata],
    *,
    domain_id: str,
    split: str,
    quotas: Mapping[str, int],
) -> dict[str, int]:
    accepted_counts = Counter(
        instance.bucket
        for instance in accepted_instances
        if instance.domain_id == domain_id and instance.split == split
    )
    return {
        bucket: max(0, int(quotas.get(bucket, 0)) - int(accepted_counts.get(bucket, 0)))
        for bucket in DIFFICULTY_BUCKETS
    }


def _candidate_output_dir(
    output_root: Path,
    *,
    domain_id: str,
    split: str,
    target_bucket: str,
    candidate_id: str,
) -> Path:
    return output_root / STAGING_DIRNAME / domain_id / split / target_bucket / candidate_id


def _derive_candidate_seed(
    *,
    seed: int,
    domain_id: str,
    split: str,
    target_bucket: str,
    attempt_index: int,
    seed_range: Any,
) -> int:
    span = int(seed_range.stop) - int(seed_range.start) + 1
    if span <= 0:
        raise ValueError("seed_range must span at least one integer")
    token = f"{seed}:{domain_id}:{split}:{target_bucket}:{attempt_index}"
    hashed = sum((index + 1) * ord(character) for index, character in enumerate(token))
    return int(seed_range.start) + (hashed % span)


def _build_generation_rejection(
    *,
    rejection: GeneratorRejection,
    domain_id: str,
    split: str,
    bucket: str,
    attempt_index: int,
) -> RejectedCandidateMetadata:
    return RejectedCandidateMetadata(
        candidate_id=rejection.candidate_id,
        domain_id=domain_id,
        split=split,
        bucket=bucket,
        attempt_index=attempt_index,
        seed=rejection.seed,
        rejection_reason=rejection.rejection_reason,
        rejection_stage=GENERATION_REJECTION_STAGE,
        message=rejection.message,
        generator_command=rejection.generator_command,
        generator_cwd=str(rejection.generator_cwd),
        stdout_path=str(rejection.stdout_path),
        stderr_path=str(rejection.stderr_path),
        details=dict(rejection.details),
    )


def _annotate_hashes(candidate: AcceptedInstanceMetadata) -> AcceptedInstanceMetadata:
    domain_hash_info = build_pddl_hash_info(Path(candidate.domain_path).read_text(encoding="utf-8"))
    problem_hash_info = build_pddl_hash_info(Path(candidate.problem_path).read_text(encoding="utf-8"))
    return replace(
        candidate,
        domain_hash=domain_hash_info.raw_sha256,
        normalized_domain_hash=domain_hash_info.normalized_sha256,
        problem_hash=problem_hash_info.raw_sha256,
        normalized_problem_hash=problem_hash_info.normalized_sha256,
    )


def _check_duplicate_candidate(
    *,
    candidate: AcceptedInstanceMetadata,
    accepted_hash_index: AcceptedProblemHashIndex,
    pool_by_hash: Mapping[str, AcceptedInstanceMetadata],
) -> RejectedCandidateMetadata | None:
    if candidate.normalized_problem_hash in pool_by_hash:
        existing = pool_by_hash[candidate.normalized_problem_hash]
        return RejectedCandidateMetadata(
            candidate_id=candidate.candidate_id,
            domain_id=candidate.domain_id,
            split=candidate.split,
            bucket=candidate.bucket,
            attempt_index=candidate.attempt_index,
            seed=candidate.seed,
            rejection_reason=DUPLICATE_HASH_REASON,
            rejection_stage=DEDUPE_REJECTION_STAGE,
            message="Normalized problem hash already exists in the current candidate pool.",
            problem_hash=candidate.problem_hash,
            normalized_problem_hash=candidate.normalized_problem_hash,
            duplicate_of_instance_id=existing.candidate_id,
            generator_command=candidate.generator_command,
            generator_cwd=candidate.generator_cwd,
            stdout_path=candidate.stdout_path,
            stderr_path=candidate.stderr_path,
            details={
                "existing_candidate_id": existing.candidate_id,
                "normalized_problem_hash": candidate.normalized_problem_hash,
                "source": "candidate_pool",
            },
        )

    existing = accepted_hash_index.get(candidate.normalized_problem_hash)
    if existing is None:
        return None

    return RejectedCandidateMetadata(
        candidate_id=candidate.candidate_id,
        domain_id=candidate.domain_id,
        split=candidate.split,
        bucket=candidate.bucket,
        attempt_index=candidate.attempt_index,
        seed=candidate.seed,
        rejection_reason=DUPLICATE_HASH_REASON,
        rejection_stage=DEDUPE_REJECTION_STAGE,
        message="Normalized problem hash already accepted in an existing output.",
        problem_hash=candidate.problem_hash,
        normalized_problem_hash=candidate.normalized_problem_hash,
        duplicate_of_instance_id=existing.instance_id,
        generator_command=candidate.generator_command,
        generator_cwd=candidate.generator_cwd,
        stdout_path=candidate.stdout_path,
        stderr_path=candidate.stderr_path,
        details={
            "existing_bucket": existing.bucket,
            "existing_domain_id": existing.domain_id,
            "existing_instance_id": existing.instance_id,
            "existing_split": existing.split,
            "normalized_problem_hash": existing.normalized_problem_hash,
            "source": "accepted_outputs",
        },
    )


def _build_selection_rejection(candidate: AcceptedInstanceMetadata) -> RejectedCandidateMetadata:
    return RejectedCandidateMetadata(
        candidate_id=candidate.candidate_id,
        domain_id=candidate.domain_id,
        split=candidate.split,
        bucket=candidate.bucket,
        attempt_index=candidate.attempt_index,
        seed=candidate.seed,
        rejection_reason=SELECTION_NOT_SELECTED_REASON,
        rejection_stage=SELECTION_REJECTION_STAGE,
        message="Candidate passed generation and rendering but was not selected for measured-difficulty quotas.",
        problem_hash=candidate.problem_hash,
        normalized_problem_hash=candidate.normalized_problem_hash,
        generator_command=candidate.generator_command,
        generator_cwd=candidate.generator_cwd,
        stdout_path=candidate.stdout_path,
        stderr_path=candidate.stderr_path,
        details={
            "difficulty_measured": candidate.difficulty_measured,
            "difficulty_target": candidate.difficulty_target,
            "measured_difficulty": candidate.measured_difficulty,
            "source_candidate_id": candidate.extra.get("orchestrator", {}).get("source_candidate_id", candidate.candidate_id),
        },
    )


def _finalize_selected_candidate(
    *,
    candidate: AcceptedInstanceMetadata,
    output_root: Path,
    force: bool,
    existing_instances: Sequence[AcceptedInstanceMetadata],
) -> AcceptedInstanceMetadata:
    final_bucket = candidate.difficulty_measured or candidate.measured_bucket
    if not final_bucket:
        raise ValueError(f"Selected candidate {candidate.candidate_id} is missing difficulty_measured")

    final_index = _next_available_index(
        existing_instances,
        domain_id=candidate.domain_id,
        split=candidate.split,
        bucket=final_bucket,
    )
    final_instance_id = build_instance_id(candidate.domain_id, candidate.split, final_bucket, final_index)
    final_candidate_id = build_candidate_id(candidate.domain_id, candidate.split, final_bucket, candidate.attempt_index)
    staging_dir = Path(candidate.domain_path).resolve().parent
    final_dir = output_root / candidate.domain_id / candidate.split / final_bucket / final_instance_id
    if force and final_dir.exists():
        shutil.rmtree(final_dir)
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(staging_dir, final_dir, dirs_exist_ok=True)

    final_extra = dict(candidate.extra)
    orchestrator_payload = dict(final_extra.get("orchestrator", {}))
    orchestrator_payload["source_candidate_id"] = candidate.candidate_id
    orchestrator_payload["source_target_bucket"] = candidate.difficulty_target or candidate.bucket
    orchestrator_payload["staging_output_dir"] = str(staging_dir)
    final_extra["orchestrator"] = orchestrator_payload

    return AcceptedInstanceMetadata(
        instance_id=final_instance_id,
        candidate_id=final_candidate_id,
        domain_id=candidate.domain_id,
        split=candidate.split,
        bucket=final_bucket,
        index=final_index,
        attempt_index=candidate.attempt_index,
        seed=candidate.seed,
        domain_path=str(final_dir / "domain.pddl"),
        problem_path=str(final_dir / "problem.pddl"),
        generator_command=candidate.generator_command,
        generator_cwd=candidate.generator_cwd,
        stdout_path=str(final_dir / Path(candidate.stdout_path).name),
        stderr_path=str(final_dir / Path(candidate.stderr_path).name),
        domain_hash=candidate.domain_hash,
        normalized_domain_hash=candidate.normalized_domain_hash,
        problem_hash=candidate.problem_hash,
        normalized_problem_hash=candidate.normalized_problem_hash,
        render_status=candidate.render_status,
        render_artifact_paths=tuple(_rebase_path(path, source_root=staging_dir, target_root=final_dir) for path in candidate.render_artifact_paths),
        render_result_path=_rebase_path(candidate.render_result_path, source_root=staging_dir, target_root=final_dir),
        difficulty_target=candidate.difficulty_target or candidate.bucket,
        difficulty_measured=final_bucket,
        measured_difficulty=candidate.measured_difficulty,
        measured_bucket=final_bucket,
        notes=candidate.notes,
        extra=final_extra,
    )


def _rebase_path(path_text: str, *, source_root: Path, target_root: Path) -> str:
    source_path = Path(path_text).resolve()
    relative_path = source_path.relative_to(source_root.resolve())
    return str((target_root / relative_path).resolve())


def _next_available_index(
    instances: Sequence[AcceptedInstanceMetadata],
    *,
    domain_id: str,
    split: str,
    bucket: str,
) -> int:
    used_indices = {
        instance.index
        for instance in instances
        if instance.domain_id == domain_id and instance.split == split and instance.bucket == bucket
    }
    next_index = 0
    while next_index in used_indices:
        next_index += 1
    return next_index


def _accepted_result_path(output_root: Path, instance: AcceptedInstanceMetadata) -> Path:
    return output_root / instance.domain_id / instance.split / instance.bucket / instance.instance_id / "result.json"


def _load_existing_accepted(
    output_root: Path,
    selected_domains: Sequence[DomainConfig],
    selected_splits: Sequence[str],
) -> list[AcceptedInstanceMetadata]:
    accepted_instances: list[AcceptedInstanceMetadata] = []
    domain_ids = {domain.domain_id for domain in selected_domains}
    split_ids = set(selected_splits)
    for domain_id in sorted(domain_ids):
        for split in sorted(split_ids):
            for bucket in DIFFICULTY_BUCKETS:
                bucket_root = output_root / domain_id / split / bucket
                if not bucket_root.exists():
                    continue
                for instance_dir in sorted(path for path in bucket_root.iterdir() if path.is_dir()):
                    payload = load_metadata_payload(instance_dir / "result.json")
                    if payload is None:
                        continue
                    accepted_instances.append(AcceptedInstanceMetadata.from_dict(payload))
    return _sorted_accepted_instances(accepted_instances)


def _load_rejections(path: Path) -> list[RejectedCandidateMetadata]:
    if not path.exists():
        return []
    rejections: list[RejectedCandidateMetadata] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rejections.append(RejectedCandidateMetadata.from_dict(json.loads(line)))
    return _sorted_rejections(rejections)


def _write_jsonl(path: Path, payloads: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(dict(payload), sort_keys=True) for payload in payloads]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _count_duplicate_problem_hashes(instances: Sequence[AcceptedInstanceMetadata]) -> int:
    counts = Counter(instance.normalized_problem_hash for instance in instances if instance.normalized_problem_hash)
    return sum(count - 1 for count in counts.values() if count > 1)


def _count_completed_domains(
    accepted_instances: Sequence[AcceptedInstanceMetadata],
    selected_domains: Sequence[DomainConfig],
    selected_splits: Sequence[str],
    quotas_by_split: Mapping[str, Mapping[str, int]],
) -> int:
    completed = 0
    for domain in selected_domains:
        domain_complete = True
        for split in selected_splits:
            remaining = _remaining_quotas(accepted_instances, domain_id=domain.domain_id, split=split, quotas=quotas_by_split[split])
            if any(remaining.values()):
                domain_complete = False
                break
        if domain_complete:
            completed += 1
    return completed


def _sorted_accepted_instances(instances: Sequence[AcceptedInstanceMetadata]) -> list[AcceptedInstanceMetadata]:
    return sorted(instances, key=lambda item: (item.domain_id, item.split, item.bucket, item.index, item.attempt_index))


def _sorted_rejections(rejections: Sequence[RejectedCandidateMetadata]) -> list[RejectedCandidateMetadata]:
    return sorted(rejections, key=lambda item: (item.domain_id, item.split, item.bucket, item.attempt_index, item.candidate_id))


__all__ = [
    "ACCEPTED_MANIFEST_FILENAME",
    "GENERATION_REJECTION_STAGE",
    "GenerationRunResult",
    "REJECTIONS_FILENAME",
    "SELECTION_NOT_SELECTED_REASON",
    "STAGING_DIRNAME",
    "SUMMARY_FILENAME",
    "orchestrate_generation",
]
