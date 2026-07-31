from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Sequence

from .cgas_provenance import SPLITS, verify_corpus
from .cgas_serialization import canonical, digest, digest_text, read_jsonl, write_json, write_jsonl
from .pddl import canonical_atom, parse_task
from .planimation_pairing_manifest import _vfg_actions
from .planimation_pairing_rendering import _valid_png
from .render_semantics import validate_render_artifacts


ALIGNMENT_SCHEMA_VERSION = "planning_cgas_alignment_v1"
ALIGNMENT_FIELDS = {
    "schema_version",
    "source_transition_id",
    "split",
    "state_before_hash",
    "action",
    "png_path",
    "png_sha256",
    "vfg_action_index",
    "source_trace_sha256",
    "render_trace_sha256",
    "mapping_rationale",
    "vision_status",
}
MANIFEST_FIELDS = {
    "schema_version",
    "source_digest",
    "render_manifest_digest",
    "alignment_digest",
    "counts",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or verify replay-proven CGAS pre-action image alignment.")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--render-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/planning_cgas_v1"))
    parser.add_argument("--verify", action="store_true")
    return parser


def build_alignment(source_root: Path, render_manifest: Path, output_root: Path) -> dict[str, object]:
    report, records = _evaluate(source_root, render_manifest)
    if report["rejections"]:
        return report
    candidate = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.alignment-", dir=output_root.parent))
    try:
        for split in SPLITS:
            write_jsonl(candidate / f"{split}.jsonl", [record for record in records if record["split"] == split])
        write_json(candidate / "manifest.json", _manifest(source_root, render_manifest, records))
        _publish(candidate, output_root / "alignment")
    except OSError:
        shutil.rmtree(candidate, ignore_errors=True)
        raise
    return report


def verify_alignment(source_root: Path, render_manifest: Path, output_root: Path) -> dict[str, object]:
    report, records = _evaluate(source_root, render_manifest)
    if report["rejections"]:
        return report
    expected_manifest = _manifest(source_root, render_manifest, records)
    try:
        actual_manifest = json.loads((output_root / "alignment" / "manifest.json").read_text(encoding="utf-8"))
        actual_records = [row for split in SPLITS for row in read_jsonl(output_root / "alignment" / f"{split}.jsonl")]
    except (OSError, json.JSONDecodeError):
        return _failed_report(records, [("alignment", "missing_alignment_output")])
    if canonical(actual_manifest) != canonical(expected_manifest) or canonical(actual_records) != canonical(records):
        return _failed_report(records, [("alignment", "alignment_output_mismatch")])
    return report


def verify_persisted_alignment(source_root: Path, alignment_root: Path) -> tuple[list[dict[str, object]], list[tuple[str, str]]]:
    try:
        source_rows = [row for split in SPLITS for row in read_jsonl(source_root / "source" / f"{split}.jsonl")]
        records = [row for split in SPLITS for row in read_jsonl(alignment_root / "alignment" / f"{split}.jsonl")]
    except (OSError, json.JSONDecodeError):
        return [], [("input", "missing_accepted_manifests")]
    failures = _persisted_manifest_failures(source_root, alignment_root, source_rows, records)
    source_by_id = {str(row.get("record_id")): row for row in source_rows}
    source_counts = Counter(str(row.get("split")) for row in source_rows)
    seen: set[str] = set()
    for record in records:
        record_id = record.get("source_transition_id")
        if not isinstance(record_id, str):
            failures.append(("alignment", "invalid_alignment_source_transition"))
            continue
        if record_id in seen:
            failures.append((record_id, "duplicate_alignment_source_transition"))
        seen.add(record_id)
        source = source_by_id.get(record_id)
        if source is None:
            failures.append((record_id, "unknown_alignment_source_transition"))
            continue
        failures.extend((record_id, reason) for reason in _persisted_row_failures(record, source))
    for source_id in source_by_id:
        if source_id not in seen:
            failures.append((source_id, "missing_accepted_alignment"))
    actual_counts = Counter(str(record.get("split")) for record in records)
    if actual_counts != source_counts:
        failures.append(("alignment", "alignment_split_count_mismatch"))
    return records, failures


def _evaluate(source_root: Path, render_manifest: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    provenance = verify_corpus(source_root, withdraw=False)
    if provenance["errors"]:
        return _failed_report([], [("source", "missing_authoritative_provenance")]), []
    try:
        source_rows = [row for split in SPLITS for row in read_jsonl(source_root / "source" / f"{split}.jsonl")]
        renders = read_jsonl(render_manifest)
        sources = {str(row["instance_id"]): row for row in read_jsonl(source_root / "source_manifest.jsonl")}
    except (OSError, KeyError, json.JSONDecodeError):
        return _failed_report([], [("source", "invalid_alignment_input")]), []
    renders_by_id: dict[str, list[dict[str, object]]] = defaultdict(list)
    for render in renders:
        identifier = render.get("source_transition_id")
        if isinstance(identifier, str):
            renders_by_id[identifier].append(render)
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in source_rows:
        planner = row.get("planner")
        if isinstance(planner, dict) and isinstance(planner.get("algorithm"), str):
            grouped[(str(row["split"]), str(row["instance_id"]), str(planner["algorithm"]))].append(row)
    records: list[dict[str, object]] = []
    rejections: list[tuple[str, str]] = []
    for group in grouped.values():
        ordered = sorted(group, key=_step_index)
        actions = [str(row["selected_action"]) for row in ordered]
        for row in ordered:
            record_id = str(row["record_id"])
            candidates = renders_by_id.get(record_id, [])
            if len(candidates) != 1:
                rejections.append((record_id, "missing_render_mapping" if not candidates else "duplicate_render_mapping"))
                continue
            reason, record = _align_one(row, candidates[0], source_root, sources, actions)
            if reason is not None:
                rejections.append((record_id, reason))
            elif record is not None:
                records.append(record)
    source_ids = {str(row["record_id"]) for row in source_rows}
    for record_id in renders_by_id:
        if record_id not in source_ids:
            rejections.append((record_id, "unknown_source_transition"))
    split_order = {split: index for index, split in enumerate(SPLITS)}
    records.sort(key=lambda row: (split_order[str(row["split"])], str(row["source_transition_id"])))
    if rejections:
        return _failed_report(records, rejections), records
    return _report(records, []), records


def _persisted_manifest_failures(source_root: Path, alignment_root: Path, source_rows: list[dict[str, object]], records: list[dict[str, object]]) -> list[tuple[str, str]]:
    manifest_path = alignment_root / "alignment" / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [("alignment_manifest", "missing_alignment_manifest")]
    except (OSError, json.JSONDecodeError):
        return [("alignment_manifest", "malformed_alignment_manifest")]
    if not isinstance(manifest, dict):
        return [("alignment_manifest", "malformed_alignment_manifest")]
    expected = {
        "schema_version": ALIGNMENT_SCHEMA_VERSION,
        "source_digest": digest_text("|".join(digest(source_root / "source" / f"{split}.jsonl") for split in SPLITS)),
        "alignment_digest": digest_text(canonical(records)),
        "counts": dict(sorted(Counter(str(row.get("split")) for row in source_rows).items())),
    }
    if set(manifest) != MANIFEST_FIELDS or not _digest_text(manifest.get("render_manifest_digest")):
        return [("alignment_manifest", "alignment_manifest_mismatch")]
    return [("alignment_manifest", "alignment_manifest_mismatch")] if any(manifest[field] != value for field, value in expected.items()) else []


def _persisted_row_failures(record: dict[str, object], source: dict[str, object]) -> list[str]:
    failures: list[str] = []
    if set(record) != ALIGNMENT_FIELDS or record.get("schema_version") != ALIGNMENT_SCHEMA_VERSION:
        failures.append("alignment_row_schema_mismatch")
    expected = {
        "split": source.get("split"),
        "state_before_hash": source.get("state_before_id"),
        "action": source.get("selected_action"),
        "vision_status": "vision_available_step_aligned",
        "vfg_action_index": source.get("step_index"),
    }
    for field, value in expected.items():
        if record.get(field) != value:
            failures.append(f"alignment_{field}_mismatch")
    png_path = record.get("png_path")
    if not isinstance(png_path, str) or not png_path or not _valid_png(Path(png_path)):
        failures.append("alignment_png_unreadable")
    elif record.get("png_sha256") != digest(Path(png_path)):
        failures.append("alignment_png_hash_mismatch")
    for field in ("png_sha256", "source_trace_sha256", "render_trace_sha256"):
        if not _digest_text(record.get(field)):
            failures.append(f"invalid_alignment_{field}")
    if record.get("mapping_rationale") != "replay_state_before_equals_derived_pddl_init;vfg_prefix_equals_replay_action_prefix;rendered_stage_zero_png_is_decodable":
        failures.append("alignment_mapping_rationale_mismatch")
    return failures


def _digest_text(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _align_one(source: dict[str, object], render: dict[str, object], source_root: Path, sources: dict[str, dict[str, object]], actions: list[str]) -> tuple[str | None, dict[str, object] | None]:
    record_id = str(source["record_id"])
    try:
        step_index = _step_index(source)
    except ValueError:
        return "state_linkage_mismatch", None
    if step_index < 0 or step_index >= len(actions):
        return "state_linkage_mismatch", None
    state_hash = source.get("state_before_id")
    if render.get("state_before_hash") != state_hash:
        return "state_linkage_mismatch", None
    frame_path = _path(render, "frame_path")
    render_trace = _path(render, "trace_path")
    source_trace = _path(render, "source_trace_path")
    derived_problem = _path(render, "derived_problem_path")
    if frame_path is None or render_trace is None or source_trace is None or derived_problem is None:
        return "missing_render_mapping", None
    if not _valid_png(frame_path):
        return "unreadable_png", None
    if step_index == 0:
        initial = _path(render, "initial_frame_path")
        if initial is None or not _valid_png(initial):
            return "missing_initial_frame", None
    if render.get("png_sha256") != digest(frame_path) or render.get("vfg_sha256") != digest(render_trace):
        return "state_linkage_mismatch", None
    vfg_actions, vfg_error = _vfg_actions(source_trace)
    if vfg_error is not None or vfg_actions[:step_index] != actions[:step_index] or step_index >= len(vfg_actions) or vfg_actions[step_index] != source.get("selected_action"):
        return "frame_action_order_mismatch", None
    source_descriptor = sources.get(str(source["instance_id"]))
    if source_descriptor is None:
        return "state_linkage_mismatch", None
    domain_path = _source_path(source_descriptor, "domain_path", source_root)
    expected_state = source.get("state_before")
    if domain_path is None or not isinstance(expected_state, list) or not all(isinstance(atom, str) for atom in expected_state):
        return "state_linkage_mismatch", None
    try:
        actual_state = sorted(canonical_atom(atom) for atom in parse_task(domain_path, derived_problem).init)
        receipt = validate_render_artifacts(render_trace, frame_path)
    except (OSError, ValueError):
        return "state_linkage_mismatch", None
    if actual_state != sorted(expected_state) or receipt.status != "success":
        return "state_linkage_mismatch", None
    return None, {
        "schema_version": ALIGNMENT_SCHEMA_VERSION,
        "source_transition_id": record_id,
        "split": source["split"],
        "state_before_hash": state_hash,
        "action": source["selected_action"],
        "png_path": str(frame_path),
        "png_sha256": digest(frame_path),
        "vfg_action_index": step_index,
        "source_trace_sha256": digest(source_trace),
        "render_trace_sha256": digest(render_trace),
        "mapping_rationale": "replay_state_before_equals_derived_pddl_init;vfg_prefix_equals_replay_action_prefix;rendered_stage_zero_png_is_decodable",
        "vision_status": "vision_available_step_aligned",
    }


def _source_path(descriptor: dict[str, object], field: str, source_root: Path | None) -> Path | None:
    value = descriptor.get(field)
    if not isinstance(value, str):
        return None
    path = Path(value)
    return path if path.is_absolute() else (source_root / path if source_root is not None else path)


def _path(record: dict[str, object], field: str) -> Path | None:
    value = record.get(field)
    return Path(value) if isinstance(value, str) and value else None


def _step_index(source: dict[str, object]) -> int:
    value = source.get("step_index")
    if type(value) is not int:
        raise ValueError("transition step_index must be an integer")
    return value


def _manifest(source_root: Path, render_manifest: Path, records: list[dict[str, object]]) -> dict[str, object]:
    return {"schema_version": ALIGNMENT_SCHEMA_VERSION, "source_digest": digest_text("|".join(digest(source_root / "source" / f"{split}.jsonl") for split in SPLITS)), "render_manifest_digest": digest(render_manifest), "alignment_digest": digest_text(canonical(records)), "counts": dict(sorted(Counter(str(record["split"]) for record in records).items()))}


def _report(records: list[dict[str, object]], rejections: list[tuple[str, str]]) -> dict[str, object]:
    return {"accepted_rows": 0 if rejections else len(records), "rejections": [{"record_id": record_id, "reason": reason} for record_id, reason in sorted(rejections)], "failures": {"action_order": sum(reason == "frame_action_order_mismatch" for _, reason in rejections), "duplicate": sum(reason == "duplicate_render_mapping" for _, reason in rejections), "missing": sum(reason in {"missing_initial_frame", "missing_render_mapping"} for _, reason in rejections), "state_linkage": sum(reason == "state_linkage_mismatch" for _, reason in rejections), "unreadable": sum(reason == "unreadable_png" for _, reason in rejections)}}


def _failed_report(records: list[dict[str, object]], rejections: list[tuple[str, str]]) -> dict[str, object]:
    return _report(records, rejections)


def _publish(candidate: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    previous = destination.with_name(f".{destination.name}.previous")
    if previous.exists():
        shutil.rmtree(previous)
    if destination.exists():
        os.replace(destination, previous)
    try:
        os.replace(candidate, destination)
    except OSError:
        if previous.exists():
            os.replace(previous, destination)
        raise
    if previous.exists():
        shutil.rmtree(previous)


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        report = verify_alignment(args.source_root, args.render_manifest, args.output_root) if args.verify else build_alignment(args.source_root, args.render_manifest, args.output_root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(canonical(report))
    return 1 if report["rejections"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
