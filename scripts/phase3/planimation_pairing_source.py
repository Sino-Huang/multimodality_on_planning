from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Iterable
from .io_utils import file_sha256, repo_root, stable_hash
from .trace_contracts import FrozenSourceIdentity
from .traversal_state_types import JSONValue
from .planimation_pairing_contracts import ACTIVE_PLANNERS, SourceSnapshotMismatch, UnsupportedActivePlanner
SCHEMA_VERSION = "phase3_planimation_vlm_v1"

__all__ = ("_load_source_example", "_trace_identity")

def _load_source_example(pair: dict[str, JSONValue], *, source_snapshots: dict[str, dict[str, str]] | None = None, source_rows: dict[str, dict[int, tuple[bytes, dict[str, JSONValue]]]] | None = None) -> dict[str, JSONValue]:
    source_root = _provenance_text(pair, "source_root")
    source_jsonl = _provenance_text(pair, "source_jsonl")
    source_root_id = _provenance_text(pair, "source_root_id")
    source_root_sha256 = _provenance_text(pair, "source_root_sha256")
    source_split_sha256 = _provenance_text(pair, "source_split_sha256")
    source_record_sha256 = _provenance_text(pair, "source_record_sha256")
    example_id = _provenance_text(pair, "example_id")
    planner = _provenance_text(pair, "planner")
    active_planner_id = _provenance_text(pair, "active_planner_id")
    split = _provenance_text(pair, "split")
    domain = _provenance_text(pair, "domain")
    instance_id = _provenance_text(pair, "instance_id")
    plan_hash = _provenance_text(pair, "plan_hash")
    target_line = _provenance_line_index(pair)
    _assert_active_planner(planner)
    _assert_active_planner(active_planner_id)
    root = _repo_path(source_root)
    source_path = root / source_jsonl
    if not source_path.resolve().is_relative_to(root.resolve()):
        raise SourceSnapshotMismatch("source_jsonl_not_within_source_root")
    if root.name != source_root_id:
        raise SourceSnapshotMismatch("source_root_id")
    snapshot_key = source_root
    current_snapshot = source_snapshots.get(snapshot_key) if source_snapshots is not None else None
    if current_snapshot is None:
        try:
            current_snapshot = _source_root_snapshot(root)
        except FileNotFoundError as exc:
            raise SourceSnapshotMismatch("source_root_missing") from exc
        if source_snapshots is not None:
            source_snapshots[snapshot_key] = current_snapshot
    if stable_hash(current_snapshot) != source_root_sha256:
        raise SourceSnapshotMismatch("source_root_sha256")
    source_split = source_path.stem
    if current_snapshot.get(source_split) != source_split_sha256:
        raise SourceSnapshotMismatch("source_split_sha256")
    if source_split != split:
        raise SourceSnapshotMismatch("split")
    row_key = f"{source_root}:{source_jsonl}"
    indexed_rows = source_rows.get(row_key) if source_rows is not None else None
    if indexed_rows is None:
        try:
            indexed_rows = {line_index: (source_bytes, example) for line_index, source_bytes, example in _source_jsonl_rows(source_path)}
        except FileNotFoundError as exc:
            raise SourceSnapshotMismatch("source_jsonl_missing") from exc
        if source_rows is not None:
            source_rows[row_key] = indexed_rows
    source_row = indexed_rows.get(target_line)
    if source_row is None:
        raise SourceSnapshotMismatch("source_line_index")
    source_bytes, example = source_row
    if hashlib.sha256(source_bytes).hexdigest() != source_record_sha256:
        raise SourceSnapshotMismatch("source_record_sha256")
    _assert_source_identity(example, "example_id", example_id)
    source_planner = _source_text(example, "planner")
    _assert_active_planner(source_planner)
    if source_planner != planner:
        raise SourceSnapshotMismatch("planner")
    if source_planner != active_planner_id:
        raise SourceSnapshotMismatch("active_planner_id")
    _assert_source_identity(example, "split", split)
    _assert_source_identity(example, "domain", domain)
    _assert_source_identity(example, "instance_id", instance_id)
    _assert_source_identity(example, "plan_hash", plan_hash)
    return example

def _provenance_text(pair: dict[str, JSONValue], field: str) -> str:
    value = pair.get(field)
    if not isinstance(value, str) or not value:
        raise SourceSnapshotMismatch(f"malformed_provenance: {field}")
    return value

def _provenance_line_index(pair: dict[str, JSONValue]) -> int:
    value = pair.get("source_line_index")
    if type(value) is not int or value < 0:
        raise SourceSnapshotMismatch("malformed_provenance: source_line_index")
    return value

def _source_text(example: dict[str, JSONValue], field: str) -> str:
    value = example.get(field)
    if not isinstance(value, str) or not value:
        raise SourceSnapshotMismatch(f"source_record_identity: {field}")
    return value

def _assert_source_identity(example: dict[str, JSONValue], field: str, expected: str) -> None:
    if _source_text(example, field) != expected:
        raise SourceSnapshotMismatch(field)

def _source_root_snapshot(dataset_root: Path) -> dict[str, str]:
    return {split: file_sha256(dataset_root / f"{split}.jsonl") for split in ("train", "dev", "test")}

def _source_jsonl_rows(path: Path) -> Iterable[tuple[int, bytes, dict[str, JSONValue]]]:
    with path.open("rb") as handle:
        for line_index, source_bytes in enumerate(handle):
            if source_bytes.strip():
                source_row = json.loads(source_bytes)
                if not isinstance(source_row, dict):
                    raise SourceSnapshotMismatch("source_record_not_object")
                yield line_index, source_bytes, source_row

def _assert_active_planner(planner: str) -> None:
    if planner not in ACTIVE_PLANNERS:
        raise UnsupportedActivePlanner(planner)

def _trace_identity(pair: dict[str, JSONValue]) -> FrozenSourceIdentity:
    return FrozenSourceIdentity(
        _provenance_text(pair, "source_root_id"),
        _provenance_text(pair, "source_jsonl"),
        _provenance_line_index(pair),
        _provenance_text(pair, "source_record_sha256"),
        _provenance_text(pair, "example_id"),
        _provenance_text(pair, "planner"),
    )

def _repo_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else repo_root() / candidate
