from __future__ import annotations
import json
from pathlib import Path
from .io_utils import file_sha256, read_jsonl
from .planimation_persisted_contracts import validate_pair_record, validate_state_render_record
from .render_semantics import validate_render_artifacts
from .traversal_state_types import JSONValue
from .planimation_pairing_contracts import SourceSnapshotMismatch
SCHEMA_VERSION = "phase3_planimation_vlm_v1"

__all__ = ("_render_receipt_is_valid",)

from .planimation_pairing_rendering import _assert_repo_output_root
from .planimation_pairing_schema import validate_vlm_record
from .planimation_pairing_source import _load_source_example
from .planimation_pairing_source import _repo_path
def _render_receipt_is_valid(row: dict[str, JSONValue]) -> bool:
    required = ("frame_path", "trace_path", "png_sha256", "vfg_sha256", "semantic_image_metrics")
    if any(not row.get(field) for field in required):
        return False
    frame_text = str(row["frame_path"])
    trace_text = str(row["trace_path"])
    if Path(frame_text).is_absolute() or Path(trace_text).is_absolute():
        return False
    frame_path = _repo_path(frame_text)
    trace_path = _repo_path(trace_text)
    receipt = validate_render_artifacts(trace_path, frame_path)
    return receipt.status == "success" and row.get("png_sha256") == file_sha256(frame_path) and row.get("vfg_sha256") == file_sha256(trace_path) and row.get("semantic_image_metrics") == receipt.to_record()

def validate_pairing_output(output_root: Path) -> dict[str, JSONValue]:
    _assert_repo_output_root(output_root)
    pairs = read_jsonl(output_root / "diagnostics" / "pairing_manifest.jsonl")
    renders = read_jsonl(output_root / "diagnostics" / "state_render_manifest.jsonl")
    errors: list[str] = []
    source_snapshots: dict[str, dict[str, str]] = {}
    source_rows: dict[str, dict[int, tuple[bytes, dict[str, JSONValue]]]] = {}
    pair_ids = {str(row.get("pair_id")) for row in pairs}
    if len(pair_ids) != len(pairs):
        errors.append("duplicate pair_id")
    for pair in pairs:
        errors.extend(validate_pair_record(pair))
        try:
            _load_source_example(pair, source_snapshots=source_snapshots, source_rows=source_rows)
        except SourceSnapshotMismatch as exc:
            errors.append(str(exc))
    for row in renders:
        errors.extend(validate_state_render_record(row, pair_ids))
    full_count = sum(len(read_jsonl(output_root / f"full_reasoning_{split}.jsonl")) for split in ("train", "dev", "test"))
    step_count = sum(len(read_jsonl(output_root / f"step_vlm_{split}.jsonl")) for split in ("train", "dev", "test"))
    if (output_root / "diagnostics" / "hybrid_output_manifest.json").exists() and (output_root / "reports" / "vlm_record_summary.json").exists():
        errors.extend(validate_vlm_output(output_root))
    payload = {"pair_records": len(pairs), "state_render_records": len(renders), "full_records": full_count, "step_records": step_count, "errors": errors}
    if errors:
        raise ValueError(json.dumps(payload, sort_keys=True))
    return payload

def validate_vlm_output(output_root: Path) -> list[str]:
    """Reload strict hybrid records and reconcile them with their output manifest."""
    errors: list[str] = []
    manifest_path = output_root / "diagnostics" / "hybrid_output_manifest.json"
    if not manifest_path.exists():
        return ["missing hybrid output manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record_ids: set[str] = set()
    counts = {"full_records": {}, "step_records": {}, "search_traversal_records": {}}
    selected_pair_ids = set(manifest.get("selection", {}).get("selected_pair_ids", []))
    for split in ("train", "dev", "test"):
        for prefix, count_key in (("full_reasoning", "full_records"), ("step_vlm", "step_records"), ("search_traversal", "search_traversal_records")):
            path = output_root / f"{prefix}_{split}.jsonl"
            if not path.exists():
                errors.append(f"missing {path.name}")
                continue
            rows = read_jsonl(path)
            counts[count_key][split] = len(rows)
            for row in rows:
                errors.extend(validate_vlm_record(row))
                if row.get("split") != split:
                    errors.append(f"split leakage in {path.name}")
                record_id = row.get("record_id")
                if record_id in record_ids:
                    errors.append("duplicate VLM record_id")
                record_ids.add(record_id)
                pair = row.get("provenance", {}).get("pair", {}) if isinstance(row.get("provenance"), dict) else {}
                if manifest.get("partial") and pair.get("pair_id") not in selected_pair_ids:
                    errors.append("partial output includes unselected pair")
    if manifest.get("counts", {}).get("full_records") != counts["full_records"]:
        errors.append("full record count reconciliation")
    if manifest.get("counts", {}).get("step_records") != counts["step_records"]:
        errors.append("step record count reconciliation")
    if manifest.get("output_mode") == "production" and manifest.get("partial"):
        errors.append("production output cannot be partial")
    return errors
