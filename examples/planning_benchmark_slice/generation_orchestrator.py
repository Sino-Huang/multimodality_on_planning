"""Persist one governed BFS Search Episode Harness run as a corpus fragment."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, cast

from src.data_collect.generate import GenerationRequest, GenerationRunReceipt, run_authorized_generation
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, StopOutcome

from .episode_evidence import (
    EpisodeEvidenceError,
    materialize_episode_artifacts,
    replay_episode_evidence,
    write_episode_evidence,
)
from .pddl_state import PDDLStateAuthority
from .search_context import materialize_search_trace
from .search_episode import SearchEpisodeError, replay_search_episode, run_search_episode
from .search_trace import TraceSegmentLimits

_FORMAL_TASK_PATH = Path("formal-tasks/task.json")
_EXPERT_TRACE_PATH = Path("expert-traces/search-trace.json")
_ATOMIC_SEGMENTS_DIRECTORY = Path("atomic-segments")
_CORPUS_FRAGMENT_PATH = Path("corpus/corpus-fragment.jsonl")
_CORPUS_MANIFEST_PATH = Path("manifests/corpus-manifest.json")
_ARTIFACT_MANIFEST_PATH = Path("manifests/artifact-manifest.json")
_EPISODE_EVIDENCE_PATH = Path("evidence/search-episode.jsonl.gz")
_CORPUS_MANIFEST_SCHEMA_VERSION = "planning_benchmark_corpus_v1"
_ARTIFACT_MANIFEST_SCHEMA_VERSION = "planning_benchmark_artifact_manifest_v1"


def run_bfs_generation_smoke(
    *,
    task_path: str | Path,
    request: GenerationRequest,
    max_expansions: int,
) -> GenerationRunReceipt:
    """Authorize, execute, and persist one exact text-state BFS episode."""

    def execute() -> dict[str, object]:
        output_root = Path(request.binding.output_root).resolve()
        if output_root.exists():
            raise FileExistsError(f"generation output root already exists: {output_root}")
        output_root.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
        try:
            episode = run_search_episode(
                task_path=task_path,
                algorithm="bfs",
                modality="text-state",
                policy="exact",
                max_expansions=max_expansions,
                gate_receipt=cast(GateReceipt, request.gate_receipt),
                authorization_receipt=cast(AuthorizationReceipt | None, request.authorization_receipt),
                signing_key=request.signing_key,
                ancestor_receipt_digest=request.ancestor_receipt_digest,
            )
            result = episode["result"]
            if (
                not isinstance(result, dict)
                or result.get("completion") != "completed"
                or result.get("outcome") != StopOutcome.PASS.value
                or result.get("goal_reached") is not True
                or result.get("scientific_completion") is not True
            ):
                raise ValueError("BFS episode did not complete a goal-reaching PASS")
            evidence = episode["evidence"]
            if not isinstance(evidence, dict):
                raise ValueError("authorized search episode did not produce episode evidence")
            replayed_episode = replay_search_episode(evidence, signing_key=request.signing_key)
            if replayed_episode != episode:
                raise ValueError("replayed BFS episode differs from its Evidence Bundle")
            formal_task, expert_trace = _bundle_artifacts(replayed_episode, signing_key=request.signing_key)

            formal_task_path = staging_root / _FORMAL_TASK_PATH
            expert_trace_path = staging_root / _EXPERT_TRACE_PATH
            episode_evidence_path = staging_root / _EPISODE_EVIDENCE_PATH
            _write_bytes(formal_task_path, formal_task)
            _write_bytes(expert_trace_path, expert_trace)
            write_episode_evidence(episode_evidence_path, episode)

            atomic_segments, corpus_fragment = _build_corpus_fragment(formal_task, expert_trace)
            atomic_segment_paths: list[Path] = []
            for index, segment in atomic_segments:
                path = staging_root / _ATOMIC_SEGMENTS_DIRECTORY / f"{index:06d}.json"
                _write_bytes(path, segment)
                atomic_segment_paths.append(path)

            corpus_fragment_path = staging_root / _CORPUS_FRAGMENT_PATH
            _write_bytes(corpus_fragment_path, corpus_fragment)

            corpus_manifest_path = staging_root / _CORPUS_MANIFEST_PATH
            corpus_manifest = {
                "atomic_segments": [_path_digest(path, staging_root) for path in atomic_segment_paths],
                "binding": {
                    "attempt_id": request.binding.attempt_id,
                    "contract_id": request.binding.contract_id,
                },
                "corpus_fragment": _path_digest(corpus_fragment_path, staging_root),
                "episode_evidence": _path_digest(episode_evidence_path, staging_root),
                "expert_trace": _path_digest(expert_trace_path, staging_root),
                "formal_task": _path_digest(formal_task_path, staging_root),
                "schema_version": _CORPUS_MANIFEST_SCHEMA_VERSION,
                "segment_count": len(atomic_segment_paths),
            }
            _write_bytes(corpus_manifest_path, _canonical_json_bytes(corpus_manifest))

            artifact_manifest_path = staging_root / _ARTIFACT_MANIFEST_PATH
            artifact_paths = [
                formal_task_path,
                expert_trace_path,
                episode_evidence_path,
                *atomic_segment_paths,
                corpus_fragment_path,
                corpus_manifest_path,
            ]
            artifact_manifest = {
                "artifacts": [_path_digest(path, staging_root, include_size=True) for path in artifact_paths],
                "schema_version": _ARTIFACT_MANIFEST_SCHEMA_VERSION,
            }
            artifact_manifest_bytes = _canonical_json_bytes(artifact_manifest)
            _write_bytes(artifact_manifest_path, artifact_manifest_bytes)
            staging_root.replace(output_root)
        except Exception:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise

        return {
            "artifact_manifest_path": str((output_root / _ARTIFACT_MANIFEST_PATH).resolve()),
            "artifact_manifest_sha256": hashlib.sha256(artifact_manifest_bytes).hexdigest(),
            "atomic_segment_paths": [
                str((output_root / path.relative_to(staging_root)).resolve()) for path in atomic_segment_paths
            ],
            "corpus_fragment_path": str((output_root / _CORPUS_FRAGMENT_PATH).resolve()),
            "corpus_manifest_path": str((output_root / _CORPUS_MANIFEST_PATH).resolve()),
            "episode_evidence_path": str((output_root / _EPISODE_EVIDENCE_PATH).resolve()),
            "expert_trace_paths": [str((output_root / _EXPERT_TRACE_PATH).resolve())],
            "formal_task_paths": [str((output_root / _FORMAL_TASK_PATH).resolve())],
        }

    return run_authorized_generation(request, execute)


def regenerate_corpus_fragment(output_root: str | Path, *, signing_key: bytes | str) -> bytes:
    """Replay persisted episode evidence and rebuild its corpus fragment."""

    root = Path(output_root)
    try:
        replayed_episode = replay_episode_evidence(root / _EPISODE_EVIDENCE_PATH, signing_key=signing_key)
        formal_task, expert_trace = _bundle_artifacts(replayed_episode, signing_key=signing_key)
    except EpisodeEvidenceError as error:
        raise SearchEpisodeError(str(error)) from error
    _, corpus_fragment = _build_corpus_fragment(formal_task, expert_trace)
    return corpus_fragment


def _bundle_artifacts(episode: dict[str, Any], *, signing_key: bytes | str) -> tuple[bytes, bytes]:
    evidence = episode["evidence"]
    if not isinstance(evidence, dict):
        raise ValueError("replayed search episode did not produce episode evidence")
    return materialize_episode_artifacts(evidence, signing_key=signing_key)


def _build_corpus_fragment(
    formal_task: bytes,
    expert_trace: bytes,
) -> tuple[tuple[tuple[int, bytes], ...], bytes]:
    atomic_segments = _materialize_atomic_segments(formal_task, expert_trace)
    return atomic_segments, b"".join(
        segment if segment.endswith(b"\n") else segment + b"\n" for _, segment in atomic_segments
    )


def _materialize_atomic_segments(formal_task: bytes, expert_trace: bytes) -> tuple[tuple[int, bytes], ...]:
    task_payload: Any = json.loads(formal_task.decode("utf-8"))
    trace_payload: Any = json.loads(expert_trace.decode("utf-8"))
    record_count = trace_payload["record_count"]
    if isinstance(record_count, bool) or not isinstance(record_count, int) or record_count < 0:
        raise ValueError("expert trace record_count must be a non-negative integer")

    authority = PDDLStateAuthority.from_pddl(task_payload["domain_pddl"], task_payload["problem_pddl"])
    limits = TraceSegmentLimits(
        max_records=max(1, record_count),
        max_bytes=max(1_000_000, max(1, len(expert_trace)) * max(1, record_count)),
    )
    materialized = materialize_search_trace(expert_trace, authority=authority, limits=limits)
    return tuple(
        (segment.record_index, segment.to_bytes())
        for segment in sorted(materialized.atomic_segments, key=lambda segment: segment.record_index)
    )


def _path_digest(path: Path, output_root: Path, *, include_size: bool = False) -> dict[str, object]:
    payload = path.read_bytes()
    result: dict[str, object] = {
        "path": path.relative_to(output_root).as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    if include_size:
        result["size_bytes"] = len(payload)
    return result


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


__all__ = ["regenerate_corpus_fragment", "run_bfs_generation_smoke"]
