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
from scripts.phase3.traversal_state_types import JSONValue

Split = Literal["train", "dev", "test"]
Mode = Literal["manifest", "render", "release"]
SPLITS: tuple[Split, ...] = ("train", "dev", "test")
JSONRecord = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class VerificationFailure(RuntimeError):
    reasons: tuple[str, ...]

    def __str__(self) -> str:
        return "\n".join(self.reasons)


def verify_output(output_root: Path, mode: Mode) -> JSONRecord:
    """Verify the requested Planimation artifact boundary without mutation."""
    manifest = _validate_manifest(output_root)
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
    for pair in pairs:
        errors.extend(validate_pair_record(pair))
        pair_id = str(pair.get("pair_id", ""))
        if pair_id in pair_ids:
            errors.append("duplicate pair_id")
        pair_ids.add(pair_id)
        try:
            _load_source_example(pair)
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
