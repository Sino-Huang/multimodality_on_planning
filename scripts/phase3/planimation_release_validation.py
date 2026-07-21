"""Typed file, schema, artifact, and coverage helpers for release verification."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Callable, Literal

from scripts.phase3.io_utils import file_sha256, is_relative_artifact_path, repo_root
from scripts.phase3.planimation_pairing import _load_source_example, _trace_identity, validate_vlm_schema_instance
from scripts.phase3.render_semantics import validate_render_artifacts
from scripts.phase3.traversal_state_types import JSONValue, TraversalProjectionInput, TraversalStateCandidate
from scripts.phase3.traversal_states import project_traversal_state_candidates

JSONRecord = dict[str, JSONValue]
Split = Literal["train", "dev", "test"]
FailureFactory = Callable[[tuple[str, ...]], RuntimeError]

__all__ = (
    "_artifact_errors",
    "_coverage_errors",
    "_hybrid_schema_errors",
    "_persisted_schema_errors",
    "_read_required_jsonl",
    "_record_type_errors",
    "_release_manifest_errors",
    "_require_json",
    "_search_candidates",
    "_split_errors",
)


def _read_required_jsonl(path: Path, *, require_rows: bool, failure_type: FailureFactory) -> list[JSONRecord]:
    if not path.is_file():
        raise failure_type((f"missing_required_file: {path.relative_to(path.parents[1]).as_posix()}",))
    rows: list[JSONRecord] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value: JSONValue = json.loads(line)
        except JSONDecodeError as exc:
            raise failure_type((f"malformed_jsonl: {path.name}",)) from exc
        if not isinstance(value, dict):
            raise failure_type((f"invalid_jsonl_record: {path.name}:{line_number}",))
        rows.append(value)
    if require_rows and not rows:
        raise failure_type((f"empty_required_jsonl: {path.name}",))
    return rows


def _require_json(path: Path, *, failure_type: FailureFactory) -> JSONRecord:
    if not path.is_file():
        raise failure_type((f"missing_required_file: {path.relative_to(path.parents[1]).as_posix()}",))
    try:
        value: JSONValue = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise failure_type((f"malformed_json: {path.name}",)) from exc
    if not isinstance(value, dict):
        raise failure_type((f"invalid_json_object: {path.name}",))
    return value


def _release_manifest_errors(manifest: JSONRecord, schema_version: str) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != schema_version or manifest.get("artifact_kind") != "hybrid_output_manifest":
        errors.append("invalid hybrid output manifest")
    if manifest.get("output_mode") != "production" or manifest.get("partial") is not False or manifest.get("production_complete") is not True:
        errors.append("release_requires_production_complete")
    selection = manifest.get("selection")
    if not isinstance(selection, dict) or selection.get("render_limit") is not None:
        errors.append("release manifest selection")
    if not isinstance(manifest.get("counts"), dict):
        errors.append("release manifest counts")
    return errors


def _hybrid_schema_errors(schema: JSONRecord, record_type: str) -> list[str]:
    properties = schema.get("properties")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False or not isinstance(properties, dict):
        return ["invalid hybrid record schema"]
    record_type_schema = properties.get("record_type")
    if not isinstance(record_type_schema, dict) or record_type_schema.get("const") != record_type:
        return ["invalid hybrid record schema"]
    return []


def _split_errors(rows: list[JSONRecord], split: Split, file_name: str) -> list[str]:
    return [f"split leakage in {file_name}" for row in rows if row.get("split") != split]


def _record_type_errors(rows: list[JSONRecord], record_type: str, file_name: str) -> list[str]:
    return [f"record type mismatch in {file_name}" for row in rows if row.get("record_type") != record_type]


def _persisted_schema_errors(records: list[JSONRecord], schema: JSONRecord) -> list[str]:
    return [error for record in records for error in validate_vlm_schema_instance(record, schema)]


def _artifact_errors(record: JSONRecord) -> list[str]:
    artifacts = record.get("artifact_paths")
    provenance = record.get("provenance")
    if not isinstance(artifacts, dict) or not isinstance(provenance, dict):
        return []
    render = provenance.get("render")
    if not isinstance(render, dict):
        return []
    paths = tuple(_relative_repo_path(artifacts.get(field)) for field in ("image_path", "render_trace_path", "derived_problem_path"))
    image_path, trace_path, derived_problem_path = paths
    if any(path is None or not path.is_file() for path in paths):
        return ["missing_render_artifact"]
    assert image_path is not None and trace_path is not None and derived_problem_path is not None
    receipt = validate_render_artifacts(trace_path, image_path)
    if receipt.status != "success":
        return ["invalid_render_image"]
    if render.get("png_sha256") != file_sha256(image_path) or render.get("vfg_sha256") != file_sha256(trace_path) or render.get("semantic_image_metrics") != receipt.to_record():
        return ["render_receipt_mismatch"]
    return []


def _coverage_errors(pairs: list[JSONRecord], records: list[JSONRecord]) -> list[str]:
    pairs_by_id = {str(pair["pair_id"]): pair for pair in pairs}
    full_by_pair: dict[str, int] = {}
    step_by_pair: dict[str, int] = {}
    traversal_events_by_pair: dict[str, set[str]] = {}
    errors: list[str] = []
    for record in records:
        provenance = record.get("provenance")
        if not isinstance(provenance, dict) or not isinstance(provenance.get("pair"), dict):
            continue
        pair_id = str(provenance["pair"].get("pair_id", ""))
        pair = pairs_by_id.get(pair_id)
        if pair is None:
            errors.append("VLM record unknown pair")
            continue
        if record.get("split") != pair["split"]:
            errors.append("VLM record pair split mismatch")
        match record.get("record_type"):
            case "full_reasoning_record": full_by_pair[pair_id] = full_by_pair.get(pair_id, 0) + 1
            case "step_vlm_record": step_by_pair[pair_id] = step_by_pair.get(pair_id, 0) + 1
            case "search_traversal_record":
                event = provenance.get("event")
                if isinstance(event, dict) and isinstance(event.get("event_id"), str):
                    traversal_events_by_pair.setdefault(pair_id, set()).add(event["event_id"])
    for pair in pairs:
        if not pair.get("training_eligible"):
            continue
        pair_id = str(pair["pair_id"])
        plan = _load_source_example(pair)["supervised_target"]["plan"]
        if full_by_pair.get(pair_id, 0) != 1 or step_by_pair.get(pair_id, 0) != len(plan):
            errors.append("VLM coverage reconciliation")
        expected_events = {candidate.event_id for candidate in _search_candidates(pair, _load_source_example(pair))}
        if traversal_events_by_pair.get(pair_id, set()) != expected_events:
            errors.append("search traversal coverage reconciliation")
    return errors


def _search_candidates(pair: JSONRecord, source: JSONRecord) -> tuple[TraversalStateCandidate, ...]:
    if pair.get("planner") == "graphplan":
        return ()
    projection = project_traversal_state_candidates(TraversalProjectionInput(_trace_identity(pair), source, repo_root() / str(pair["domain_path"]), repo_root() / str(pair["problem_path"])))
    return projection.candidates


def _relative_repo_path(value: JSONValue) -> Path | None:
    if not isinstance(value, str) or not is_relative_artifact_path(value):
        return None
    return repo_root() / value
