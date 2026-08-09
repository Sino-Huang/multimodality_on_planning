from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypeAlias

from . import cgas_trace_contract_v3
from .cgas_trace_stream_v2 import TraceStreamError, verify_trace_stream

Planner: TypeAlias = Literal["bfs", "iw"]
JsonObject: TypeAlias = dict[str, object]


@dataclass(frozen=True, slots=True)
class PilotExpansionIndexError(RuntimeError):
    rule: str
    path: Path | None = None

    def __str__(self) -> str:
        return self.rule if self.path is None else f"{self.rule}: {self.path}"


@dataclass(slots=True)
class BfsCertificateFold:
    frontier: list[str] = field(default_factory=list)
    visited: set[str] = field(default_factory=set)
    expansion_count: int = 0

    def project(self, event: Mapping[str, object]) -> JsonObject:
        state_id = _text(event, "state_id")
        successors = _mappings(event, "successors")
        enqueued = [
            _text(successor, "state_id")
            for successor in successors
            if successor.get("enqueued") is True
        ]
        if self.expansion_count == 0:
            self.frontier = [state_id]
            self.visited.add(state_id)
        if (
            not self.frontier
            or self.frontier[0] != state_id
            or len(enqueued) != len(set(enqueued))
            or any(item in self.visited for item in enqueued)
        ):
            raise PilotExpansionIndexError("pilot_expansion_bfs_frontier_mismatch")
        self.frontier = [*self.frontier[1:], *enqueued]
        self.visited.update(enqueued)
        visited_delta = sorted([*enqueued, *([state_id] if self.expansion_count == 0 else [])])
        self.expansion_count += 1
        return {
            "kind": "bfs",
            "frontier_head": state_id,
            "frontier_order_summary": list(self.frontier),
            "visited_delta": visited_delta,
            "expanded_state": state_id,
        }


def state_sha256(atoms: Sequence[str]) -> str:
    if any(not isinstance(atom, str) for atom in atoms) or len(set(atoms)) != len(atoms):
        raise PilotExpansionIndexError("pilot_expansion_state_atoms_noncanonical")
    payload = json.dumps(sorted(atoms), ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def project_expansion(
    planner: Planner,
    event: Mapping[str, object],
    bfs_fold: BfsCertificateFold | None,
) -> JsonObject | None:
    if planner == "iw" and (event.get("decision") != "expand" or event.get("event_kind") != "expansion"):
        return None
    state_atoms = sorted(_strings(event, "state_atoms"))
    successors = [dict(successor) for successor in _mappings(event, "successors")]
    if planner == "bfs":
        if bfs_fold is None:
            raise PilotExpansionIndexError("pilot_expansion_bfs_fold_missing")
        certificate = bfs_fold.project(event)
    elif planner == "iw":
        certificate = {
            "kind": "iw",
            "novelty_tuple": _text(event, "novel_item"),
            "seen_feature_delta": _strings(event, "seen_feature_delta"),
            "width_decision": _text(event, "width_decision"),
        }
    else:
        raise PilotExpansionIndexError("pilot_expansion_planner_unsupported")
    return {
        "state_atoms": state_atoms,
        "state_sha256": state_sha256(state_atoms),
        "successors": successors,
        "actions_considered": _strings(event, "actions_considered") if planner == "bfs" else [
            _text(successor, "action") for successor in successors
        ],
        "certificate": certificate,
    }


def iter_verified_events(path: Path) -> Iterator[JsonObject]:
    try:
        verification = verify_trace_stream(path)
    except TraceStreamError as error:
        raise PilotExpansionIndexError("pilot_expansion_stream_invalid", path) from error
    if verification.contract_id != cgas_trace_contract_v3.CONTRACT_ID:
        raise PilotExpansionIndexError("pilot_expansion_contract_unsupported", path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise PilotExpansionIndexError("pilot_expansion_stream_record_invalid", path)
                if record.get("record_type") == "trailer":
                    continue
                event = record.get("event")
                if not isinstance(event, dict):
                    raise PilotExpansionIndexError("pilot_expansion_stream_event_invalid", path)
                yield {
                    "sequence": record.get("sequence"),
                    "event_sha256": record.get("current_event_sha256"),
                    "event": event,
                }
    except (OSError, json.JSONDecodeError) as error:
        raise PilotExpansionIndexError("pilot_expansion_stream_read_failed", path) from error


def publish_once(output: Path, payload: bytes) -> bool:
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}-", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        directory = os.open(
            output.parent,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        try:
            fcntl.flock(directory, fcntl.LOCK_EX)
            if output.exists() or output.is_symlink():
                if output.is_symlink() or not output.is_file() or output.read_bytes() != payload:
                    raise PilotExpansionIndexError("pilot_expansion_publication_collision", output)
                return True
            try:
                os.link(temporary, output, follow_symlinks=False)
                os.fsync(directory)
            except OSError as error:
                raise PilotExpansionIndexError("pilot_expansion_publication_failed", output) from error
            return False
        finally:
            os.close(directory)
    except OSError as error:
        raise PilotExpansionIndexError("pilot_expansion_publication_failed", output) from error
    finally:
        temporary.unlink(missing_ok=True)


def build_render_coverage(
    index_path: Path,
    render_manifests: Iterable[Path],
    repository_root: Path,
) -> tuple[JsonObject, list[JsonObject]]:
    required: dict[str, JsonObject] = {}
    index_row_count = 0
    state_partitions: dict[str, set[str]] = defaultdict(set)
    partition_rows: dict[str, int] = defaultdict(int)
    for row in _jsonl_records(index_path):
        index_row_count += 1
        digest = _text(row, "state_sha256")
        atoms = _strings(row, "state_atoms")
        if state_sha256(atoms) != digest:
            raise PilotExpansionIndexError("pilot_expansion_state_hash_mismatch", index_path)
        prior = required.get(digest)
        candidate = {"state_atoms": sorted(atoms), "state_sha256": digest}
        if prior is not None and prior != candidate:
            raise PilotExpansionIndexError("pilot_expansion_state_hash_collision", index_path)
        required[digest] = candidate
        partition = f"{_text(row, 'role')}|{_integer(row, 'object_count')}|{_text(row, 'planner')}"
        state_partitions[digest].add(partition)
        partition_rows[partition] += 1

    render_candidates: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    manifest_bindings: list[JsonObject] = []
    for manifest in sorted(render_manifests):
        manifest_bindings.append({"path": _relative(manifest, repository_root), "sha256": _file_sha256(manifest)})
        for record in _jsonl_records(manifest):
            if record.get("status") != "success":
                continue
            digest = _digest_text(record, "state_sha256")
            png_digest = _digest_text(record, "png_sha256")
            frame_path = _text(record, "frame_path")
            transition = _mapping(record, "transition")
            if state_sha256(_strings(transition, "state_before")) != digest:
                raise PilotExpansionIndexError("pilot_expansion_render_state_hash_mismatch", manifest)
            frame = _resolve_frame_path(manifest, frame_path, repository_root)
            if _file_sha256(frame) != png_digest:
                raise PilotExpansionIndexError("pilot_expansion_render_hash_mismatch", frame)
            render_candidates[digest][png_digest].add(_relative(frame, repository_root))

    collisions = {
        digest: sorted(images)
        for digest, images in render_candidates.items()
        if len(images) > 1
    }
    accepted = {
        digest: {
            "frame_path": min(next(iter(images.values()))),
            "png_sha256": next(iter(images)),
            "state_sha256": digest,
        }
        for digest, images in render_candidates.items()
        if len(images) == 1
    }
    covered = set(required) & set(accepted)
    required_collisions = set(required) & set(collisions)
    if required_collisions:
        raise PilotExpansionIndexError("pilot_expansion_render_collision", index_path)
    covered_rows: dict[str, int] = defaultdict(int)
    if covered:
        for row in _jsonl_records(index_path):
            digest = _text(row, "state_sha256")
            if digest in covered:
                partition = f"{_text(row, 'role')}|{_integer(row, 'object_count')}|{_text(row, 'planner')}"
                covered_rows[partition] += 1
    partitions: dict[str, JsonObject] = {}
    for partition, row_count in sorted(partition_rows.items()):
        partition_states = {digest for digest, values in state_partitions.items() if partition in values}
        partitions[partition] = {
            "row_count": row_count,
            "covered_rows": covered_rows[partition],
            "unique_state_count": len(partition_states),
            "covered_unique_state_count": len(partition_states & covered),
            "missing_unique_state_count": len(partition_states - covered),
        }
    missing = [
        {**required[digest], "partitions": sorted(state_partitions[digest])}
        for digest in sorted(set(required) - covered)
    ]
    return {
        "schema_version": "cgas_phase3_pilot_render_coverage_v1",
        "expansion_index_path": _relative(index_path, repository_root),
        "expansion_index_sha256": _file_sha256(index_path),
        "render_manifests": manifest_bindings,
        "index_row_count": index_row_count,
        "required_unique_state_count": len(required),
        "covered_unique_state_count": len(covered),
        "missing_unique_state_count": len(missing),
        "render_collision_state_count": len(collisions),
        "render_collision_states": sorted(collisions),
        "covered_state_bindings": [accepted[digest] for digest in sorted(covered)],
        "partitions": partitions,
    }, missing


def _resolve_frame_path(manifest: Path, frame_path: str, repository_root: Path) -> Path:
    repository = repository_root.resolve()
    direct = (repository / frame_path).resolve()
    candidates = [direct]
    parts = Path(frame_path).parts
    if parts and parts[0] == "outputs":
        candidates.append((repository / "outputs/image_frames" / Path(*parts[1:])).resolve())
    for candidate in candidates:
        if candidate.is_relative_to(repository) and candidate.is_file() and not candidate.is_symlink():
            return candidate
    raise PilotExpansionIndexError("pilot_expansion_render_path_invalid", manifest)


def _digest_text(value: Mapping[str, object], field: str) -> str:
    digest = _text(value, field)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise PilotExpansionIndexError(f"pilot_expansion_invalid_digest:{field}")
    return digest


def _mapping(value: Mapping[str, object], field: str) -> dict[str, object]:
    item = value.get(field)
    if not isinstance(item, dict):
        raise PilotExpansionIndexError(f"pilot_expansion_invalid_mapping:{field}")
    return dict(item)


def _jsonl_records(path: Path) -> Iterator[JsonObject]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise PilotExpansionIndexError("pilot_expansion_jsonl_record_invalid", path)
                yield value
    except (OSError, json.JSONDecodeError) as error:
        raise PilotExpansionIndexError("pilot_expansion_jsonl_read_failed", path) from error


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _text(value: Mapping[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str):
        raise PilotExpansionIndexError(f"pilot_expansion_invalid_text:{field}")
    return item


def _integer(value: Mapping[str, object], field: str) -> int:
    item = value.get(field)
    if isinstance(item, bool) or not isinstance(item, int):
        raise PilotExpansionIndexError(f"pilot_expansion_invalid_integer:{field}")
    return item


def _strings(value: Mapping[str, object], field: str) -> list[str]:
    items = value.get(field)
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise PilotExpansionIndexError(f"pilot_expansion_invalid_string_array:{field}")
    return list(items)


def _mappings(value: Mapping[str, object], field: str) -> list[dict[str, object]]:
    items = value.get(field)
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise PilotExpansionIndexError(f"pilot_expansion_invalid_mapping_array:{field}")
    return [dict(item) for item in items]
