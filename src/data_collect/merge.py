"""Merge finalized curriculum PDDL shard outputs."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

from .generate import (
    ACCEPTED_MANIFEST_FILENAME,
    REJECTIONS_FILENAME,
    SUMMARY_FILENAME,
    GenerationRunResult,
    _sorted_accepted_instances,
    _sorted_rejections,
    _write_jsonl,
)
from .hashing import AcceptedProblemHashIndex
from .metadata import (
    AcceptedInstanceMetadata,
    RejectedCandidateMetadata,
    SummaryMetadata,
    build_summary_metadata,
    write_result_metadata,
    write_summary_metadata,
)


def merge_shards(
    shards_root: Path | str,
    output_root: Path | str,
    *,
    force: bool = False,
    resume: bool = False,
) -> GenerationRunResult:
    """Merge finalized shard roots under *shards_root* into one dataset root."""

    if force and resume:
        raise ValueError("force and resume cannot both be true")

    resolved_shards_root = Path(shards_root).resolve()
    resolved_output_root = Path(output_root).resolve()
    shard_roots = discover_finalized_shards(resolved_shards_root)
    _prepare_output_root(resolved_output_root, force=force, resume=resume)

    resumed_accepted_total = _count_existing_manifest_entries(resolved_output_root) if resume else 0
    accepted_instances: list[AcceptedInstanceMetadata] = []
    rejected_candidates: list[RejectedCandidateMetadata] = []
    copy_plan: list[tuple[Path, Path, AcceptedInstanceMetadata]] = []
    hash_index = AcceptedProblemHashIndex()

    for shard_root in shard_roots:
        _load_shard_summary(shard_root)
        shard_accepted = _load_accepted_manifest(shard_root / ACCEPTED_MANIFEST_FILENAME)
        shard_rejections = _load_rejections(shard_root / REJECTIONS_FILENAME)
        rejected_candidates.extend(shard_rejections)

        for instance in shard_accepted:
            _register_unique_hash(hash_index, instance=instance, shard_root=shard_root)
            rebased = _rebase_accepted_instance(instance, source_root=shard_root, target_root=resolved_output_root)
            source_instance_dir = _source_instance_dir(shard_root, instance)
            target_instance_dir = _accepted_instance_dir(resolved_output_root, rebased)
            copy_plan.append((source_instance_dir, target_instance_dir, rebased))
            accepted_instances.append(rebased)

    sorted_accepted = _sorted_accepted_instances(accepted_instances)
    sorted_rejections = _sorted_rejections(rejected_candidates)
    summary = build_summary_metadata(
        accepted_instances=sorted_accepted,
        rejected_candidates=sorted_rejections,
        duplicate_accepted_problem_hashes=0,
        resumed_accepted_total=resumed_accepted_total,
        notes="Merged from finalized curriculum PDDL shards.",
        extra={
            "merge": {
                "shards_root": str(resolved_shards_root),
                "shard_roots": [str(path) for path in shard_roots],
                "force": force,
                "resume": resume,
            }
        },
    )

    resolved_output_root.mkdir(parents=True, exist_ok=True)
    for source_instance_dir, target_instance_dir, rebased in copy_plan:
        if not source_instance_dir.exists():
            raise RuntimeError(f"Accepted instance directory is missing: {source_instance_dir}")
        target_instance_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_instance_dir, target_instance_dir, dirs_exist_ok=True)
        write_result_metadata(target_instance_dir / "result.json", rebased, force=True)

    accepted_manifest_path = resolved_output_root / ACCEPTED_MANIFEST_FILENAME
    rejections_path = resolved_output_root / REJECTIONS_FILENAME
    summary_path = resolved_output_root / SUMMARY_FILENAME
    _write_jsonl(accepted_manifest_path, [instance.to_dict() for instance in sorted_accepted])
    _write_jsonl(rejections_path, [rejection.to_dict() for rejection in sorted_rejections])
    write_summary_metadata(summary_path, summary)

    return GenerationRunResult(
        accepted_instances=tuple(sorted_accepted),
        rejected_candidates=tuple(sorted_rejections),
        summary=summary,
        output_root=resolved_output_root,
        accepted_manifest_path=accepted_manifest_path,
        rejections_path=rejections_path,
        summary_path=summary_path,
    )


def discover_finalized_shards(shards_root: Path | str) -> tuple[Path, ...]:
    """Return direct child shard roots that contain a finalized summary."""

    resolved_shards_root = Path(shards_root).resolve()
    if not resolved_shards_root.is_dir():
        raise RuntimeError(f"Shard root does not exist or is not a directory: {resolved_shards_root}")

    shard_roots = tuple(
        path.resolve()
        for path in sorted(resolved_shards_root.iterdir(), key=lambda item: item.name)
        if path.is_dir() and (path / SUMMARY_FILENAME).exists()
    )
    if not shard_roots:
        raise RuntimeError(f"No finalized shard roots with {SUMMARY_FILENAME} found under {resolved_shards_root}")
    return shard_roots


def _prepare_output_root(output_root: Path, *, force: bool, resume: bool) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
        return

    if resume:
        return

    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError(f"Output root already exists and is not empty: {output_root}; pass --resume or --force")


def _load_shard_summary(shard_root: Path) -> SummaryMetadata:
    summary_path = shard_root / SUMMARY_FILENAME
    payload = _load_json_object(summary_path)
    return SummaryMetadata.from_dict(payload)


def _load_accepted_manifest(path: Path) -> list[AcceptedInstanceMetadata]:
    return [AcceptedInstanceMetadata.from_dict(payload) for payload in _load_jsonl(path)]


def _load_rejections(path: Path) -> list[RejectedCandidateMetadata]:
    return [RejectedCandidateMetadata.from_dict(payload) for payload in _load_jsonl(path)]


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Required metadata file is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Metadata file must contain a JSON object: {path}")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise RuntimeError(f"Required JSONL file is missing: {path}")

    payloads: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise RuntimeError(f"JSONL row {line_number} in {path} must contain a JSON object")
        payloads.append(payload)
    return payloads


def _register_unique_hash(
    hash_index: AcceptedProblemHashIndex,
    *,
    instance: AcceptedInstanceMetadata,
    shard_root: Path,
) -> None:
    if not instance.normalized_problem_hash:
        raise RuntimeError(f"Accepted instance {instance.instance_id} in {shard_root} is missing normalized_problem_hash")

    duplicate = hash_index.register(
        normalized_problem_hash=instance.normalized_problem_hash,
        instance_id=instance.instance_id,
        domain_id=instance.domain_id,
        split=instance.split,
        bucket=instance.bucket,
        duplicate_identifier=instance.candidate_id,
    )
    if duplicate is None:
        return

    raise RuntimeError(
        "Duplicate normalized_problem_hash while merging shards: "
        f"{instance.normalized_problem_hash} from {shard_root} instance {instance.instance_id} "
        f"duplicates existing instance {duplicate.existing_instance_id} "
        f"({duplicate.existing_domain_id}/{duplicate.existing_split}/{duplicate.existing_bucket})"
    )


def _rebase_accepted_instance(
    instance: AcceptedInstanceMetadata,
    *,
    source_root: Path,
    target_root: Path,
) -> AcceptedInstanceMetadata:
    return replace(
        instance,
        domain_path=_rebase_required_path(instance.domain_path, source_root=source_root, target_root=target_root),
        problem_path=_rebase_required_path(instance.problem_path, source_root=source_root, target_root=target_root),
        stdout_path=_rebase_optional_path(instance.stdout_path, source_root=source_root, target_root=target_root),
        stderr_path=_rebase_optional_path(instance.stderr_path, source_root=source_root, target_root=target_root),
        render_artifact_paths=tuple(
            _rebase_required_path(path, source_root=source_root, target_root=target_root)
            for path in instance.render_artifact_paths
        ),
        render_result_path=_rebase_optional_path(instance.render_result_path, source_root=source_root, target_root=target_root),
    )


def _rebase_required_path(path_text: str, *, source_root: Path, target_root: Path) -> str:
    if not path_text:
        raise RuntimeError(f"Cannot rebase an empty accepted metadata path from shard {source_root}")
    return _rebase_path(path_text, source_root=source_root, target_root=target_root)


def _rebase_optional_path(path_text: str, *, source_root: Path, target_root: Path) -> str:
    if not path_text:
        return ""
    return _rebase_path(path_text, source_root=source_root, target_root=target_root)


def _rebase_path(path_text: str, *, source_root: Path, target_root: Path) -> str:
    source_path = Path(path_text)
    if not source_path.is_absolute():
        source_path = source_root / source_path
    source_path = source_path.resolve()
    resolved_source_root = source_root.resolve()
    try:
        relative_path = source_path.relative_to(resolved_source_root)
    except ValueError as exc:
        raise RuntimeError(f"Cannot rebase path outside shard root {resolved_source_root}: {source_path}") from exc
    return str((target_root.resolve() / relative_path).resolve())


def _source_instance_dir(shard_root: Path, instance: AcceptedInstanceMetadata) -> Path:
    if instance.domain_path:
        domain_path = Path(instance.domain_path)
        if not domain_path.is_absolute():
            domain_path = shard_root / domain_path
        return domain_path.resolve().parent
    return shard_root / instance.domain_id / instance.split / instance.bucket / instance.instance_id


def _accepted_instance_dir(output_root: Path, instance: AcceptedInstanceMetadata) -> Path:
    return output_root / instance.domain_id / instance.split / instance.bucket / instance.instance_id


def _count_existing_manifest_entries(output_root: Path) -> int:
    manifest_path = output_root / ACCEPTED_MANIFEST_FILENAME
    if not manifest_path.exists():
        return 0
    return len(_load_jsonl(manifest_path))


__all__ = ["discover_finalized_shards", "merge_shards"]
