from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from jsonschema import Draft202012Validator

from .cgas_certificate_contracts import CertificateError, SCHEMA_VERSION, counterfactuals_for, expected_certificate, stable_step_id, step_schema, validate_step_schema, verify_counterfactual
from .cgas_certificate_publication import publish_steps
from .cgas_alignment import verify_persisted_alignment
from .cgas_provenance import SPLITS, verify_corpus
from .cgas_serialization import canonical, digest, digest_text, read_jsonl, write_json, write_jsonl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or verify planning_cgas_v1 typed certificates.")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--alignment-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/planning_cgas_v1"))
    parser.add_argument("--verify", action="store_true")
    return parser


def build_steps(source_root: Path, alignment_root: Path, output_root: Path) -> dict[str, object]:
    report, records = _evaluate(source_root, alignment_root)
    if report["rejections"]:
        return report
    output_root.parent.mkdir(parents=True, exist_ok=True)
    candidate = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.steps-", dir=output_root.parent))
    try:
        (candidate / "steps").mkdir()
        (candidate / "schema").mkdir()
        for split in SPLITS:
            write_jsonl(candidate / "steps" / f"{split}.jsonl", [record for record in records if record["split"] == split])
        schema = _schema()
        write_json(candidate / "schema" / "planning_cgas_v1.schema.json", schema)
        write_json(candidate / "steps_manifest.json", _steps_manifest(source_root, alignment_root, records))
        publish_steps(candidate, output_root)
    except OSError:
        shutil.rmtree(candidate, ignore_errors=True)
        raise
    return report


def verify_steps(source_root: Path, alignment_root: Path, output_root: Path) -> dict[str, object]:
    report, expected = _evaluate(source_root, alignment_root)
    if report["rejections"]:
        return report
    try:
        actual = [row for split in SPLITS for row in read_jsonl(output_root / "steps" / f"{split}.jsonl")]
        schema = json.loads((output_root / "schema" / "planning_cgas_v1.schema.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _failed([("steps", "missing_step_output")])
    rejections: list[tuple[str, str]] = []
    try:
        manifest = json.loads((output_root / "steps_manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        rejections.append(("steps_manifest", "missing_steps_manifest"))
    except (OSError, json.JSONDecodeError):
        rejections.append(("steps_manifest", "malformed_steps_manifest"))
    else:
        if not isinstance(manifest, dict):
            rejections.append(("steps_manifest", "malformed_steps_manifest"))
        elif manifest != _steps_manifest(source_root, alignment_root, expected):
            rejections.append(("steps_manifest", "steps_manifest_mismatch"))
    expected_by_id = {str(row["step_id"]): row for row in expected}
    validator = Draft202012Validator(json.loads(canonical(schema)))
    for row in actual:
        step_id = str(row.get("step_id", "unknown"))
        schema_errors = list(validator.iter_errors(json.loads(canonical(row))))
        if schema_errors:
            location = ".".join(str(part) for part in schema_errors[0].absolute_path) or "row"
            rejections.append((step_id, f"invalid_schema:{location}"))
        for reason in validate_step_schema(row):
            rejections.append((step_id, reason))
        source_id = row.get("source_transition_id")
        expected_row = expected_by_id.get(step_id)
        if not isinstance(source_id, str) or expected_row is None:
            rejections.append((step_id, "unknown_step_id"))
            continue
        certificate = row.get("certificate")
        if not isinstance(certificate, dict):
            rejections.append((step_id, "invalid_certificate"))
            continue
        failures = _certificate_failures(certificate, expected_row["certificate"])
        rejections.extend((step_id, reason) for reason in failures)
        for field, expected_value in expected_row.items():
            if field != "certificate" and row.get(field) != expected_value:
                rejections.append((step_id, f"record_mismatch:{field}"))
    actual_step_ids = [str(row.get("step_id")) for row in actual]
    if len(actual_step_ids) != len(set(actual_step_ids)):
        rejections.append(("steps", "duplicate_step_id"))
    if set(expected_by_id) != set(actual_step_ids):
        rejections.append(("steps", "step_set_mismatch"))
    if schema != _schema():
        rejections.append(("schema", "schema_output_mismatch"))
    counterfactual_results = [verify_counterfactual(variant) for row in actual for variant in _variants(row)]
    wrong = sum(result["failure_count"] != 1 for result in counterfactual_results)
    multi = sum(result["reason"] == "multiple_invariants_changed" for result in counterfactual_results)
    return _report(len(expected) if not rejections else 0, rejections, sum(reason in {"frontier_head", "frontier_order_summary", "visited_delta", "expanded_state", "novelty_tuple", "seen_feature_delta", "width_decision"} for _, reason in rejections), wrong, multi)


def _evaluate(source_root: Path, alignment_root: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    provenance = verify_corpus(source_root, withdraw=False)
    if provenance["errors"]:
        return _failed([("source", "missing_authoritative_provenance")]), []
    try:
        source = [row for split in SPLITS for row in read_jsonl(source_root / "source" / f"{split}.jsonl")]
    except (OSError, json.JSONDecodeError):
        return _failed([("input", "missing_accepted_manifests")]), []
    alignment, alignment_failures = verify_persisted_alignment(source_root, alignment_root)
    if alignment_failures:
        return _failed(alignment_failures), []
    by_source = {str(row.get("source_transition_id")): row for row in alignment}
    records: list[dict[str, object]] = []
    failures: list[tuple[str, str]] = []
    for row in source:
        source_id = str(row.get("record_id"))
        aligned = by_source.get(source_id)
        if aligned is None or aligned.get("vision_status") != "vision_available_step_aligned":
            failures.append((source_id, "missing_accepted_alignment"))
            continue
        try:
            records.append(_record(row, aligned))
        except CertificateError as error:
            failures.append((source_id, error.reason))
    return _failed(failures) if failures else _report(len(records), [], 0, 0, 0), records


def _record(source: dict[str, object], alignment: dict[str, object]) -> dict[str, object]:
    planner = source["planner"]
    if not isinstance(planner, dict):
        raise CertificateError("invalid_planner", str(source.get("record_id")), "planner")
    certificate = expected_certificate(source)
    alignment_hash = _text(alignment, "png_sha256")
    step_id = stable_step_id(_text(source, "record_id"), alignment_hash)
    record: dict[str, object] = {"schema_version": SCHEMA_VERSION, "step_id": step_id, "source_transition_id": _text(source, "record_id"), "source_hash": _text(source, "source_digest"), "planner": {"algorithm": _text(planner, "algorithm"), "version": _text(planner, "version")}, "split": _text(source, "split"), "structural_ood": source.get("structural_ood") is True, "model_input": {"domain": "blocksworld", "image_path": _text(alignment, "png_path"), "planner": _text(planner, "algorithm"), "task_text": f"Execute the next Blocksworld action for {_text(source, 'instance_id')}."}, "action_target": _text(source, "selected_action"), "certificate": certificate, "replay_evidence": {"replay_ok": _mapping(source, "replay").get("replay_ok") is True, "replay_validation_id": _text(_mapping(source, "replay"), "replay_validation_id")}, "alignment": {"png_sha256": alignment_hash, "state_before_hash": _text(alignment, "state_before_hash"), "vision_status": _text(alignment, "vision_status")}}
    record["counterfactual_targets"] = counterfactuals_for(record)
    return record


def _variants(record: dict[str, object]) -> list[dict[str, object]]:
    value = record.get("counterfactual_targets")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _certificate_failures(actual: dict[str, object], expected: object) -> list[str]:
    if not isinstance(expected, dict):
        return ["invalid_expected_certificate"]
    from .cgas_certificate_contracts import certificate_failures

    return certificate_failures(actual, expected)


def _schema() -> dict[str, object]:
    return step_schema()


def _source_digest(root: Path) -> str:
    return digest_text("|".join(digest(root / "source" / f"{split}.jsonl") for split in SPLITS))


def _alignment_digest(root: Path) -> str:
    return digest_text("|".join(digest(root / "alignment" / f"{split}.jsonl") for split in SPLITS))


def _steps_manifest(source_root: Path, alignment_root: Path, records: list[dict[str, object]]) -> dict[str, object]:
    return {"schema_version": SCHEMA_VERSION, "source_digest": _source_digest(source_root), "alignment_digest": _alignment_digest(alignment_root), "steps_digest": digest_text(canonical(records))}


def _report(accepted: int, rejected: list[tuple[str, str]], certificate_failures: int, wrong: int, multi: int) -> dict[str, object]:
    items = [{"record_id": record_id, "reason": reason} for record_id, reason in sorted(rejected)]
    invalid_schema_rows = len({record_id for record_id, reason in rejected if reason.startswith("invalid_schema:")})
    return {"accepted_rows": accepted, "rejections": items, "invalid_schema_rows": invalid_schema_rows, "valid_certificate_failures": certificate_failures, "counterfactual_wrong_failure_count": wrong, "counterfactual_multi_invariant_count": multi}


def _failed(rejected: list[tuple[str, str]]) -> dict[str, object]:
    return _report(0, rejected, 0, 0, 0)


def _mapping(value: dict[str, object], field: str) -> dict[str, object]:
    item = value.get(field)
    if not isinstance(item, dict):
        raise CertificateError("invalid_mapping", str(value.get("record_id")), field)
    return item


def _text(value: dict[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str):
        raise CertificateError("invalid_text", str(value.get("record_id")), field)
    return item


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        report = verify_steps(args.source_root, args.alignment_root, args.output_root) if args.verify else build_steps(args.source_root, args.alignment_root, args.output_root)
    except (CertificateError, OSError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(canonical(report))
    return 1 if report["rejections"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
