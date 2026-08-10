from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .cgas_pilot_expansion_index import PilotExpansionIndexError, state_sha256
from .io_utils import resolve_repo_path
from .render_semantics import validate_render_artifacts

SCHEMA_VERSION = "cgas_phase3_pilot_replay_alignment_v1"
EXPECTED_AUTHORITATIVE_COUNT = 790
EXPECTED_INDEX_SHA256 = "46d1e7c1c0a6a133372782e691888840a74f3d3732dd625b5e2d8611fdf5d390"


@dataclass(frozen=True, slots=True)
class ReplayAlignmentError(RuntimeError):
    """Raised when frozen replay rows cannot be bound to one render."""

    rule: str
    path: Path | None = None

    def __str__(self) -> str:
        return self.rule if self.path is None else f"{self.rule}: {self.path}"


@dataclass(frozen=True, slots=True)
class ReplayAlignmentResult:
    output_path: Path
    report_path: Path
    counts: dict[str, int]


def build_replay_alignment(
    expansion_index_path: Path,
    render_manifest_path: Path,
    output_root: Path,
    *,
    expected_authoritative_count: int = EXPECTED_AUTHORITATIVE_COUNT,
    expected_index_sha256: str = EXPECTED_INDEX_SHA256,
) -> ReplayAlignmentResult:
    """Bind every authoritative replay row to exactly one successful render.

    The expansion index is the sole source of replay membership and row
    cardinality. Render records are keyed only by their state digest, so a
    shared rendered state intentionally produces one output row per index row.
    """
    authoritative = list(_authoritative_rows(expansion_index_path))
    if len(authoritative) != expected_authoritative_count:
        raise ReplayAlignmentError("authoritative_count_mismatch", expansion_index_path)
    if _file_sha256(expansion_index_path) != expected_index_sha256:
        raise ReplayAlignmentError("expansion_index_binding_mismatch", expansion_index_path)
    render_output_root = render_manifest_path.resolve().parent.parent
    mappings, duplicate_count, collision_count = _render_mappings(render_manifest_path, render_output_root)
    counts: Counter[str] = Counter(
        authoritative=len(authoritative),
        accepted=0,
        missing=0,
        duplicate=duplicate_count,
        collision=collision_count,
    )
    if duplicate_count:
        raise ReplayAlignmentError("duplicate_replay_render", render_manifest_path)
    if collision_count:
        raise ReplayAlignmentError("conflicting_replay_render", render_manifest_path)

    records: list[dict[str, object]] = []
    for row in authoritative:
        digest = _digest(row, "state_sha256", "index_state_hash_invalid", expansion_index_path)
        render = mappings.get(digest)
        if render is None:
            counts["missing"] += 1
            raise ReplayAlignmentError("missing_replay_render", expansion_index_path)
        records.append(_record(row, render, expansion_index_path))
        counts["accepted"] += 1

    output_path = output_root / "replay-alignment.jsonl"
    report_path = output_root / "replay-alignment-report.json"
    _publish(output_path, b"".join(_canonical_bytes(record) + b"\n" for record in records))
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "expansion_index_path": str(expansion_index_path),
        "expansion_index_sha256": _file_sha256(expansion_index_path),
        "render_manifest_path": str(render_manifest_path),
        "render_manifest_sha256": _file_sha256(render_manifest_path),
        "replay_alignment_sha256": _sha256_rows(records),
        "counts": dict(counts),
    }
    _publish(report_path, _canonical_bytes(report) + b"\n")
    return ReplayAlignmentResult(output_path, report_path, dict(counts))


def _authoritative_rows(path: Path) -> Iterator[dict[str, object]]:
    for row in _jsonl(path, "expansion_index"):
        if row.get("replay_plan_member") is not True:
            continue
        atoms = _strings(row, "state_atoms", "index_state_atoms_invalid", path)
        if atoms != sorted(atoms):
            raise ReplayAlignmentError("index_state_atoms_noncanonical", path)
        digest = _digest(row, "state_sha256", "index_state_hash_invalid", path)
        try:
            computed = state_sha256(atoms)
        except PilotExpansionIndexError as error:
            raise ReplayAlignmentError("index_state_atoms_noncanonical", path) from error
        if computed != digest:
            raise ReplayAlignmentError("index_state_hash_mismatch", path)
        _text(row, "row_id", "index_row_id_invalid", path)
        _integer(row, "replay_step_index", "index_replay_step_index_invalid", path)
        yield dict(row)


def _render_mappings(path: Path, render_output_root: Path) -> tuple[dict[str, dict[str, object]], int, int]:
    mappings: dict[str, dict[str, object]] = {}
    duplicate_count = 0
    collision_count = 0
    for row in _jsonl(path, "render_manifest"):
        if row.get("status") != "success":
            continue
        digest = _digest(row, "state_sha256", "render_state_hash_invalid", path)
        mapping: dict[str, object] = {
            "frame_path": _text(row, "frame_path", "render_frame_path_invalid", path),
            "png_sha256": _digest(row, "png_sha256", "render_png_hash_invalid", path),
            "trace_path": _text(row, "trace_path", "render_trace_path_invalid", path),
            "vfg_sha256": _digest(row, "vfg_sha256", "render_vfg_hash_invalid", path),
        }
        _validate_artifacts(mapping, path, render_output_root)
        prior = mappings.get(digest)
        if prior is None:
            mappings[digest] = mapping
        elif prior == mapping:
            duplicate_count += 1
        else:
            collision_count += 1
    return mappings, duplicate_count, collision_count


def _validate_artifacts(mapping: Mapping[str, object], manifest_path: Path, render_output_root: Path) -> None:
    frame_text = _text(mapping, "frame_path", "render_frame_path_invalid", manifest_path)
    trace_text = _text(mapping, "trace_path", "render_trace_path_invalid", manifest_path)
    frame_path = resolve_repo_path(frame_text)
    trace_path = resolve_repo_path(trace_text)
    if frame_path is None or trace_path is None:
        raise ReplayAlignmentError("render_artifact_path_invalid", manifest_path)
    for artifact_path, rule in (
        (frame_path, "render_frame_unavailable"),
        (trace_path, "render_trace_unavailable"),
    ):
        try:
            resolved = artifact_path.resolve(strict=True)
            if artifact_path.is_symlink() or not artifact_path.is_file():
                raise ReplayAlignmentError(rule, artifact_path)
            if not resolved.is_relative_to(render_output_root.resolve()):
                raise ReplayAlignmentError("render_artifact_path_invalid", artifact_path)
        except OSError as error:
            raise ReplayAlignmentError(rule, artifact_path) from error
    try:
        png_digest = _file_sha256(frame_path)
        vfg_digest = _file_sha256(trace_path)
    except ReplayAlignmentError:
        raise
    expected_png = _text(mapping, "png_sha256", "render_png_hash_invalid", manifest_path)
    expected_vfg = _text(mapping, "vfg_sha256", "render_vfg_hash_invalid", manifest_path)
    if png_digest != expected_png:
        raise ReplayAlignmentError("render_png_hash_mismatch", frame_path)
    if vfg_digest != expected_vfg:
        raise ReplayAlignmentError("render_vfg_hash_mismatch", trace_path)
    receipt = validate_render_artifacts(trace_path, frame_path)
    if receipt.status != "success":
        raise ReplayAlignmentError("render_semantics_invalid", trace_path)


def _record(row: Mapping[str, object], render: Mapping[str, object], path: Path) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source_row_id": _text(row, "row_id", "index_row_id_invalid", path),
        "source_record_sha256": _digest(row, "source_record_sha256", "index_source_hash_invalid", path),
        "candidate_id": _text(row, "candidate_id", "index_candidate_id_invalid", path),
        "instance_id": _text(row, "instance_id", "index_instance_id_invalid", path),
        "planner": _text(row, "planner", "index_planner_invalid", path),
        "role": _text(row, "role", "index_role_invalid", path),
        "object_count": _integer(row, "object_count", "index_object_count_invalid", path),
        "replay_step_index": _integer(row, "replay_step_index", "index_replay_step_index_invalid", path),
        "state_atoms": _strings(row, "state_atoms", "index_state_atoms_invalid", path),
        "state_sha256": _digest(row, "state_sha256", "index_state_hash_invalid", path),
        "frame_path": render["frame_path"],
        "png_sha256": render["png_sha256"],
        "trace_path": render["trace_path"],
        "vfg_sha256": render["vfg_sha256"],
    }


def _jsonl(path: Path, source: str) -> Iterator[dict[str, object]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ReplayAlignmentError(f"{source}_record_invalid", path)
                yield value
    except ReplayAlignmentError:
        raise
    except (OSError, json.JSONDecodeError) as error:
        raise ReplayAlignmentError(f"{source}_read_failed", path) from error


def _text(row: Mapping[str, object], field: str, rule: str, path: Path) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ReplayAlignmentError(rule, path)
    return value


def _digest(row: Mapping[str, object], field: str, rule: str, path: Path) -> str:
    value = _text(row, field, rule, path)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ReplayAlignmentError(rule, path)
    return value


def _integer(row: Mapping[str, object], field: str, rule: str, path: Path) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReplayAlignmentError(rule, path)
    return value


def _strings(row: Mapping[str, object], field: str, rule: str, path: Path) -> list[str]:
    value = row.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ReplayAlignmentError(rule, path)
    return list(value)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha256_rows(rows: Sequence[Mapping[str, object]]) -> str:
    return hashlib.sha256(b"".join(_canonical_bytes(row) + b"\n" for row in rows)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ReplayAlignmentError("input_digest_unavailable", path) from error
    return digest.hexdigest()


def _publish(path: Path, contents: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        if path.exists():
            if not path.is_file() or path.is_symlink() or path.read_bytes() != contents:
                raise ReplayAlignmentError("replay_alignment_publication_collision", path)
            return
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except ReplayAlignmentError:
        raise
    except OSError as error:
        raise ReplayAlignmentError("replay_alignment_publication_failed", path) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
