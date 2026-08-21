"""Release-verifier orchestration for persisted Planimation artifacts."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from scripts.phase3.planimation_release_validation import (
    _artifact_errors,
    _coverage_errors,
    _hybrid_schema_errors,
    _persisted_schema_errors,
    _read_required_jsonl,
    _record_type_errors,
    _release_manifest_errors,
    _require_json,
    _search_candidates,
    _split_errors,
)
from scripts.phase3.planimation_pairing import (
    SCHEMA_VERSION,
    _load_source_example,
    _render_receipt_is_valid,
    validate_pair_record,
    validate_state_render_record,
    validate_vlm_record,
)
from scripts.phase3.rollout_gate_selection import has_valid_selection_pair_contract
from scripts.phase3.traversal_state_types import JSONValue

Split = Literal["train", "dev", "test"]
Mode = Literal["manifest", "render", "release"]
SPLITS: tuple[Split, ...] = ("train", "dev", "test")
JSONRecord = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class SelectionPair:
    pair_id: str
    split: str
    source_root: str
    source_jsonl: str
    source_line_index: int
    source_record_id: str
    planner: str
    domain: str
    bucket: str
    source_root_id: str | None
    example_id: str | None
    active_planner_id: str | None
    instance_id: str | None


@dataclass(frozen=True, slots=True)
class SelectionContract:
    selected_pair_ids: frozenset[str]
    selected_pairs: tuple[SelectionPair, ...]
    input_pairing_manifest_path: str


@dataclass(frozen=True, slots=True)
class VerificationFailure(RuntimeError):
    reasons: tuple[str, ...]

    def __str__(self) -> str:
        return "\n".join(self.reasons)


def verify_output(output_root: Path, mode: Mode, selection_file: Path | None = None) -> JSONRecord:
    """Verify the requested Planimation artifact boundary without mutation."""
    selection = _load_selection(selection_file) if selection_file is not None else None
    manifest = _validate_manifest(output_root)
    if selection is not None:
        _validate_selection(manifest, selection)
    match mode:
        case "manifest":
            return {"mode": mode, "counts": {"pair_records": len(manifest)}}
        case "render":
            renders = _validate_render(output_root, manifest)
            return {"mode": mode, "counts": {"pair_records": len(manifest), "state_render_records": len(renders)}}
        case "release":
            renders = _validate_render(output_root, manifest)
            full_counts, step_counts, traversal_counts = _validate_release(output_root, manifest, renders)
            return {
                "mode": mode,
                "counts": {
                    "pair_records": len(manifest),
                    "state_render_records": len(renders),
                    "full_records": full_counts,
                    "step_records": step_counts,
                    "search_traversal_records": traversal_counts,
                },
            }


def _validate_manifest(output_root: Path) -> list[JSONRecord]:
    pairs = _read_required_jsonl(output_root / "diagnostics" / "pairing_manifest.jsonl", require_rows=True, failure_type=VerificationFailure)
    _require_json(output_root / "schema" / "pairing_manifest.schema.json", failure_type=VerificationFailure)
    errors: list[str] = []
    pair_ids: set[str] = set()
    source_snapshots: dict[str, dict[str, str]] = {}
    source_rows: dict[str, dict[int, tuple[bytes, JSONRecord]]] = {}
    for pair in pairs:
        errors.extend(validate_pair_record(pair))
        pair_id = str(pair.get("pair_id", ""))
        if pair_id in pair_ids:
            errors.append("duplicate pair_id")
        pair_ids.add(pair_id)
        try:
            _load_source_example(pair, source_snapshots=source_snapshots, source_rows=source_rows)
        except RuntimeError as exc:
            errors.append(str(exc))
    _raise_if_errors(errors)
    return pairs


def _validate_render(output_root: Path, pairs: list[JSONRecord]) -> list[JSONRecord]:
    _require_json(output_root / "reports" / "state_render_summary.json", failure_type=VerificationFailure)
    _require_json(output_root / "diagnostics" / "hybrid_output_manifest.json", failure_type=VerificationFailure)
    renders = _read_required_jsonl(output_root / "diagnostics" / "state_render_manifest.jsonl", require_rows=True, failure_type=VerificationFailure)
    pair_ids = frozenset(str(pair["pair_id"]) for pair in pairs)
    errors: list[str] = []
    successful_by_pair: Counter[str] = Counter()
    for row in renders:
        errors.extend(validate_state_render_record(row, pair_ids))
        if row.get("status") == "success":
            successful_by_pair[str(row.get("pair_id"))] += 1
            if not _render_receipt_is_valid(row):
                errors.append("invalid_render_image")
    for pair in pairs:
        if not pair.get("training_eligible"):
            continue
        source = _load_source_example(pair)
        plan = source["supervised_target"]["plan"]
        expected = len(plan) + 1 + len(_search_candidates(pair, source))
        if successful_by_pair[str(pair["pair_id"])] != expected:
            errors.append("render coverage reconciliation")
    _raise_if_errors(errors)
    return renders


def _validate_release(output_root: Path, pairs: list[JSONRecord], renders: list[JSONRecord]) -> tuple[JSONRecord, JSONRecord, JSONRecord]:
    manifest = _require_json(output_root / "diagnostics" / "hybrid_output_manifest.json", failure_type=VerificationFailure)
    _require_json(output_root / "reports" / "vlm_record_summary.json", failure_type=VerificationFailure)
    schemas = {
        "full_records": _require_json(output_root / "schema" / "full_reasoning.schema.json", failure_type=VerificationFailure),
        "step_records": _require_json(output_root / "schema" / "step_vlm.schema.json", failure_type=VerificationFailure),
        "search_traversal_records": _require_json(output_root / "schema" / "search_traversal.schema.json", failure_type=VerificationFailure),
    }
    record_specs = (
        ("full_reasoning", "full_records", "full_reasoning_record"),
        ("step_vlm", "step_records", "step_vlm_record"),
        ("search_traversal", "search_traversal_records", "search_traversal_record"),
    )
    flat_errors = _release_manifest_errors(manifest, SCHEMA_VERSION)
    for _, count_key, record_type in record_specs:
        flat_errors.extend(_hybrid_schema_errors(schemas[count_key], record_type))
    counts: dict[str, JSONRecord] = {"full_records": {}, "step_records": {}, "search_traversal_records": {}}
    records: list[JSONRecord] = []
    for split in SPLITS:
        for prefix, count_key, record_type in record_specs:
            rows = _read_required_jsonl(output_root / f"{prefix}_{split}.jsonl", require_rows=False, failure_type=VerificationFailure)
            counts[count_key][split] = len(rows)
            records.extend(rows)
            flat_errors.extend(_split_errors(rows, split, f"{prefix}_{split}.jsonl"))
            flat_errors.extend(_record_type_errors(rows, record_type, f"{prefix}_{split}.jsonl"))
            flat_errors.extend(_persisted_schema_errors(rows, schemas[count_key]))
    flat_errors.extend(_record_errors(records))
    flat_errors.extend(_coverage_errors(pairs, records))
    expected_counts = manifest.get("counts", {})
    for count_key, message in (("full_records", "full record count reconciliation"), ("step_records", "step record count reconciliation"), ("search_traversal_records", "search traversal record count reconciliation")):
        if isinstance(expected_counts, dict) and expected_counts.get(count_key) != counts[count_key]:
            flat_errors.append(message)
    if isinstance(expected_counts, dict) and expected_counts.get("state_render_records") != len(renders):
        flat_errors.append("state render count reconciliation")
    _raise_if_errors(flat_errors)
    return counts["full_records"], counts["step_records"], counts["search_traversal_records"]


def _record_errors(records: list[JSONRecord]) -> list[str]:
    errors: list[str] = []
    record_ids: set[str] = set()
    for record in records:
        errors.extend(validate_vlm_record(record))
        record_id = str(record.get("record_id", ""))
        if record_id in record_ids:
            errors.append("duplicate VLM record_id")
        record_ids.add(record_id)
        errors.extend(_artifact_errors(record))
    return errors


def _raise_if_errors(errors: list[str]) -> None:
    if errors:
        raise VerificationFailure(tuple(sorted(set(errors))))


def _load_selection(path: Path) -> SelectionContract:
    selection = _require_json(path, failure_type=VerificationFailure)
    errors: list[str] = []
    if selection.get("artifact_kind") != "planimation_rollout_selection_v1":
        errors.append("invalid selection artifact kind")
    manifest_path = selection.get("input_pairing_manifest_path")
    if manifest_path != "diagnostics/pairing_manifest.jsonl":
        errors.append("selection input_pairing_manifest_path")
    raw_ids = selection.get("selected_pair_ids")
    selected_ids: tuple[str, ...] = ()
    if not isinstance(raw_ids, list) or not raw_ids:
        errors.append("selection selected_pair_ids")
    else:
        selected_ids = tuple(value for value in raw_ids if isinstance(value, str) and value)
        if len(selected_ids) != len(raw_ids):
            errors.append("selection selected_pair_ids")
        if len(selected_ids) != len(set(selected_ids)):
            errors.append("duplicate selected pair_id")
    raw_pairs = selection.get("selected_pairs")
    frozen_pairs: list[SelectionPair] = []
    if not isinstance(raw_pairs, list) or not raw_pairs or not all(isinstance(pair, dict) for pair in raw_pairs):
        errors.append("selection selected_pairs")
    else:
        for raw_pair in raw_pairs:
            parsed_pair = _parse_selection_pair(raw_pair, errors)
            if parsed_pair is not None:
                frozen_pairs.append(parsed_pair)
    if len(frozen_pairs) != len({pair.pair_id for pair in frozen_pairs}):
        errors.append("duplicate selected pair")
    if not has_valid_selection_pair_contract(raw_ids, raw_pairs):
        errors.append("selection pair IDs mismatch")
    _raise_if_errors(errors)
    assert isinstance(manifest_path, str) and manifest_path
    return SelectionContract(frozenset(selected_ids), tuple(frozen_pairs), manifest_path)


def _parse_selection_pair(pair: JSONRecord, errors: list[str]) -> SelectionPair | None:
    pair_id = _selection_string(pair, "pair_id", errors)
    split = _selection_string(pair, "split", errors)
    source_root = _selection_string(pair, "source_root", errors)
    source_jsonl = _selection_string(pair, "source_jsonl", errors)
    source_line_index = _selection_line_index(pair, errors)
    source_record_id = _selection_string(pair, "source_record_id", errors)
    planner = _selection_string(pair, "planner", errors)
    domain = _selection_string(pair, "domain", errors)
    bucket = _selection_string(pair, "bucket", errors)
    source_root_id = _optional_selection_string(pair, "source_root_id", errors)
    example_id = _optional_selection_string(pair, "example_id", errors)
    active_planner_id = _optional_selection_string(pair, "active_planner_id", errors)
    instance_id = _optional_selection_string(pair, "instance_id", errors)
    if (
        pair_id is None
        or split is None
        or source_root is None
        or source_jsonl is None
        or source_line_index is None
        or source_record_id is None
        or planner is None
        or domain is None
        or bucket is None
    ):
        return None
    return SelectionPair(
        pair_id,
        split,
        source_root,
        source_jsonl,
        source_line_index,
        source_record_id,
        planner,
        domain,
        bucket,
        source_root_id,
        example_id,
        active_planner_id,
        instance_id,
    )


def _selection_string(pair: JSONRecord, field: str, errors: list[str]) -> str | None:
    if field not in pair:
        errors.append(f"selection pair missing {field}")
        return None
    value = pair[field]
    if not isinstance(value, str) or not value:
        errors.append(f"selection {field}")
        return None
    return value


def _optional_selection_string(pair: JSONRecord, field: str, errors: list[str]) -> str | None:
    if field not in pair:
        return None
    return _selection_string(pair, field, errors)


def _selection_line_index(pair: JSONRecord, errors: list[str]) -> int | None:
    field = "source_line_index"
    if field not in pair:
        errors.append(f"selection pair missing {field}")
        return None
    value = pair[field]
    if type(value) is not int:
        errors.append("selection source_line_index")
        return None
    return value


def _validate_selection(manifest: list[JSONRecord], selection: SelectionContract) -> None:
    errors: list[str] = []
    manifest_by_id = {str(pair.get("pair_id")): pair for pair in manifest}
    manifest_ids = frozenset(manifest_by_id)
    if manifest_ids != selection.selected_pair_ids:
        errors.append("selection pair set mismatch")
    for selected in selection.selected_pairs:
        actual = manifest_by_id.get(selected.pair_id)
        if actual is None:
            continue
        for field, expected in (
            ("pair_id", selected.pair_id),
            ("split", selected.split),
            ("source_root", selected.source_root),
            ("source_jsonl", selected.source_jsonl),
            ("source_line_index", selected.source_line_index),
            ("source_record_id", selected.source_record_id),
            ("planner", selected.planner),
            ("domain", selected.domain),
            ("bucket", selected.bucket),
            ("source_root_id", selected.source_root_id),
            ("example_id", selected.example_id),
            ("active_planner_id", selected.active_planner_id),
            ("instance_id", selected.instance_id),
        ):
            if expected is not None and actual.get(field) != expected:
                errors.append(f"selection provenance mismatch: {selected.pair_id}:{field}")
    _raise_if_errors(errors)
