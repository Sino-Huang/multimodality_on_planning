from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .io_utils import file_sha256, read_jsonl, relpath
from .schema import validate_instance_accounting, validate_planner_attempt, validate_supervised_example


class VerificationError(RuntimeError):
    pass


def verify_manifest_coverage(accepted_manifest: Path, diagnostics: Path) -> dict[str, Any]:
    manifest_ids = _ids(read_jsonl(accepted_manifest))
    diagnostic_ids = _ids(read_jsonl(diagnostics))
    missing = sorted(manifest_ids - diagnostic_ids)
    extra = sorted(diagnostic_ids - manifest_ids)
    payload = {"missing_from_diagnostics": len(missing), "unexpected_extra_instances": len(extra), "accepted_instances": len(manifest_ids), "diagnostic_instances": len(diagnostic_ids)}
    _assert_clean(payload, ("missing_from_diagnostics", "unexpected_extra_instances"))
    return payload


def verify_planner_attempts(accepted_manifest: Path, planner_attempts: Path, planners: list[str]) -> dict[str, Any]:
    manifest = read_jsonl(accepted_manifest)
    attempts = read_jsonl(planner_attempts)
    expected = {(row["domain_id"], row["instance_id"], planner) for row in manifest for planner in planners}
    actual = {(row["domain"], row["instance_id"], row["planner"]) for row in attempts}
    missing = expected - actual
    counts = {planner: dict(Counter(row["status"] for row in attempts if row["planner"] == planner)) for planner in planners}
    payload = {"missing_attempt_records": len(missing), "attempt_records": len(attempts), "counts_by_planner_status": counts}
    _assert_clean(payload, ("missing_attempt_records",))
    return payload


def validate_jsonl_schema(schema: Path, jsonl_paths: list[Path]) -> dict[str, Any]:
    schema_payload = json.loads(schema.read_text(encoding="utf-8"))
    invalid: list[dict[str, Any]] = []
    rows = 0
    for path in jsonl_paths:
        for index, row in enumerate(read_jsonl(path), start=1):
            rows += 1
            errors = _validate_by_schema_title(row, schema_payload)
            errors.extend(_validate_against_schema_doc(row, schema_payload))
            if errors:
                invalid.append({"path": str(path), "line": index, "errors": errors})
    payload = {"rows_checked": rows, "invalid_rows": len(invalid), "errors": invalid[:20]}
    _assert_clean(payload, ("invalid_rows",))
    return payload


def verify_replay_validated_examples(dataset_root: Path) -> dict[str, Any]:
    examples = _examples(dataset_root)
    replay = {row["replay_validation_id"]: row for row in read_jsonl(dataset_root / "diagnostics" / "replay_validation.jsonl")}
    missing = 0
    failed = 0
    for example in examples:
        replay_id = example.get("evaluation_metadata", {}).get("replay_validation_id")
        row = replay.get(replay_id)
        if row is None:
            missing += 1
        elif not row.get("replay_ok") or not row.get("goal_satisfied"):
            failed += 1
    payload = {"examples_checked": len(examples), "examples_without_replay_validation": missing, "examples_with_failed_replay": failed}
    _assert_clean(payload, ("examples_without_replay_validation", "examples_with_failed_replay"))
    return payload


def verify_fidelity_labels(dataset_root: Path) -> dict[str, Any]:
    bad = [row["example_id"] for row in _examples(dataset_root) if _has_invalid_full_trace_label(row)]
    payload = {"invalid_external_full_trace_labels": len(bad), "invalid_example_ids": bad[:20]}
    _assert_clean(payload, ("invalid_external_full_trace_labels",))
    return payload


def verify_splits(accepted_manifest: Path, dataset_root: Path) -> dict[str, Any]:
    manifest_counts = Counter(row["split"] for row in read_jsonl(accepted_manifest))
    seen: dict[str, set[str]] = {}
    for split in ("train", "dev", "test"):
        seen[split] = {row["instance_id"] for row in read_jsonl(dataset_root / f"{split}.jsonl")}
    overlaps = sum(len(seen[a] & seen[b]) for a, b in (("train", "dev"), ("train", "test"), ("dev", "test")))
    diagnostic_counts = Counter(row["split"] for row in read_jsonl(dataset_root / "diagnostics" / "instance_accounting.jsonl"))
    mismatches = {split: {"manifest": manifest_counts[split], "diagnostics": diagnostic_counts[split]} for split in manifest_counts if manifest_counts[split] != diagnostic_counts[split]}
    payload = {"split_overlaps": overlaps, "split_count_mismatches": mismatches, "manifest_split_counts": dict(manifest_counts)}
    if overlaps or mismatches:
        raise VerificationError(json.dumps(payload, sort_keys=True))
    return payload


def verify_domain_coverage(accepted_manifest: Path, dataset_root: Path, domains: list[str]) -> dict[str, Any]:
    del accepted_manifest
    present = {row["domain"] for row in read_jsonl(dataset_root / "diagnostics" / "instance_accounting.jsonl")}
    missing = sorted(set(domains) - present)
    payload = {"domain_count": len(present), "missing_domains": missing, "domains_present": sorted(present)}
    if missing:
        raise VerificationError(json.dumps(payload, sort_keys=True))
    return payload


def verify_vision_assets(dataset_root: Path) -> dict[str, Any]:
    missing = 0
    unreadable = 0
    for example in _examples(dataset_root):
        vision = example.get("model_facing", {}).get("vision", {})
        if not vision.get("available"):
            continue
        frames = vision.get("frame_paths", [])
        if not frames:
            missing += 1
        for path in frames:
            try:
                if (Path.cwd() / path).read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                    unreadable += 1
            except OSError:
                unreadable += 1
    payload = {"missing_frames": missing, "unreadable_frames": unreadable}
    _assert_clean(payload, ("missing_frames", "unreadable_frames"))
    return payload


def verify_no_smoke_sources(dataset_root: Path, forbidden_paths: list[str]) -> dict[str, Any]:
    forbidden = [item.replace("\\", "/") for item in forbidden_paths]
    references: list[str] = []
    for path in dataset_root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(token in text for token in forbidden):
            references.append(relpath(path))
    payload = {"forbidden_references": len(references), "files": references}
    _assert_clean(payload, ("forbidden_references",))
    return payload


def verify_determinism(dataset_root: Path, manifest: Path) -> dict[str, Any]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    expected = data.get("generated_file_digests", {})
    changed = []
    for relative, digest in expected.items():
        current = file_sha256(dataset_root / relative)
        if current != digest:
            changed.append(relative)
    example_ids = [row["example_id"] for row in _examples(dataset_root)]
    duplicate_ids = len(example_ids) - len(set(example_ids))
    payload = {"digest_mismatches": len(changed), "changed_files": changed, "duplicate_example_ids": duplicate_ids}
    _assert_clean(payload, ("digest_mismatches", "duplicate_example_ids"))
    return payload


def _ids(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {(str(row.get("domain_id", row.get("domain"))), str(row.get("instance_id"))) for row in rows}


def _examples(dataset_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split in ("train", "dev", "test"):
        rows.extend(read_jsonl(dataset_root / f"{split}.jsonl"))
    return rows


def _has_invalid_full_trace_label(row: dict[str, Any]) -> bool:
    if row["planner"] not in {"ff", "iw", "graphplan"} or row["trace_fidelity"] != "success_full_trace":
        return False
    trace = row.get("supervised_target", {}).get("planner_trace", {})
    return bool(trace.get("external_plan_only"))


def _assert_clean(payload: dict[str, Any], keys: tuple[str, ...]) -> None:
    if any(payload.get(key) for key in keys):
        raise VerificationError(json.dumps(payload, sort_keys=True))


def _validate_by_schema_title(row: dict[str, Any], schema_payload: dict[str, Any]) -> list[str]:
    title = schema_payload.get("title")
    if title == "supervised_planning_example":
        return validate_supervised_example(row)
    if title == "planner_attempt":
        return validate_planner_attempt(row)
    if title == "instance_accounting":
        return validate_instance_accounting(row)
    return []


def _validate_against_schema_doc(row: dict[str, Any], schema_payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = schema_payload.get("required", [])
    if isinstance(required, list):
        for field in required:
            if field not in row:
                errors.append(f"schema missing required field: {field}")
    properties = schema_payload.get("properties", {})
    if schema_payload.get("additionalProperties") is False and isinstance(properties, dict):
        extra_fields = sorted(set(row) - set(properties))
        if extra_fields:
            errors.append("schema additional properties forbidden: " + ", ".join(extra_fields))
    if not isinstance(properties, dict):
        return errors
    for field, rule in properties.items():
        if field not in row or not isinstance(rule, dict):
            continue
        if "const" in rule and row[field] != rule["const"]:
            errors.append(f"schema const mismatch for {field}")
        if "enum" in rule and row[field] not in rule["enum"]:
            errors.append(f"schema enum mismatch for {field}")
        expected_type = rule.get("type")
        if expected_type == "object" and not isinstance(row[field], dict):
            errors.append(f"schema type mismatch for {field}: expected object")
        if expected_type == "string" and not isinstance(row[field], str):
            errors.append(f"schema type mismatch for {field}: expected string")
        if expected_type == "boolean" and not isinstance(row[field], bool):
            errors.append(f"schema type mismatch for {field}: expected boolean")
    return errors


def run_cli(func: Callable[..., dict[str, Any]], parser: argparse.ArgumentParser, kwargs_builder: Callable[[argparse.Namespace], dict[str, Any]]) -> None:
    args = parser.parse_args()
    payload = func(**kwargs_builder(args))
    print(json.dumps(payload, indent=2, sort_keys=True))
