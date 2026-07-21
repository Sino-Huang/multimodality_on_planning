from __future__ import annotations
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable
from .io_utils import read_jsonl, relpath, resolve_repo_path, stable_hash, write_json, write_jsonl
from .pddl import PDDLError, normalize_action_string
from .trace_contracts import FrozenSourceIdentity, TraceContractError, project_traversal_events
from .traversal_state_types import JSONValue
from .planimation_pairing_contracts import PairingConfig
SCHEMA_VERSION = "phase3_planimation_vlm_v1"

from .planimation_pairing_reasoning import _planner_approximation
from .planimation_pairing_rendering import _assert_repo_output_root, _assert_source_output_disjoint
from .planimation_pairing_source import _assert_active_planner, _source_jsonl_rows, _source_root_snapshot
from .planimation_pairing_schema import _write_pairing_schema
def build_pairing_manifest(dataset_roots: Iterable[Path], output_root: Path, *, config: PairingConfig = PairingConfig()) -> dict[str, JSONValue]:
    """Inventory source examples and report existing frame/VFG alignment without mutation."""
    roots = tuple(Path(root) for root in dataset_roots)
    _assert_repo_output_root(output_root)
    _assert_source_output_disjoint(roots, output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, JSONValue]] = []
    seen_ids: set[str] = set()
    vfg_cache: dict[str, tuple[list[str], str | None]] = {}
    for dataset_root in sorted(roots, key=lambda path: path.as_posix()):
        accounting = {str(row["instance_id"]): row for row in read_jsonl(dataset_root / "diagnostics" / "instance_accounting.jsonl")}
        source_snapshot = _source_root_snapshot(dataset_root)
        for split in ("train", "dev", "test"):
            source_jsonl = dataset_root / f"{split}.jsonl"
            for line_index, source_bytes, example in _source_jsonl_rows(source_jsonl):
                record = _pair_record(dataset_root, source_jsonl, line_index, source_bytes, example, accounting.get(str(example["instance_id"])), source_snapshot, config, vfg_cache)
                if record["pair_id"] in seen_ids:
                    raise ValueError(f"duplicate pairing record: {record['pair_id']}")
                seen_ids.add(record["pair_id"])
                records.append(record)
    if config.selected_pair_ids is not None:
        selected_records = [record for record in records if str(record["pair_id"]) in config.selected_pair_ids]
        found_pair_ids = {str(record["pair_id"]) for record in selected_records}
        missing_pair_ids = config.selected_pair_ids - found_pair_ids
        if missing_pair_ids:
            raise ValueError(f"selected pairing records are absent: {sorted(missing_pair_ids)}")
        records = selected_records
    records.sort(key=lambda row: (row["split"], row["domain"], row["instance_id"], row["planner"], row["pair_id"]))
    diagnostics = output_root / "diagnostics"
    write_jsonl(diagnostics / "pairing_manifest.jsonl", records)
    _write_pairing_schema(output_root / "schema" / "pairing_manifest.schema.json")
    summary = _pairing_summary(records)
    write_json(output_root / "reports" / "pairing_summary.json", summary)
    return {"records": records, "summary": summary}

def _pair_record(dataset_root: Path, source_jsonl: Path, line_index: int, source_bytes: bytes, example: dict[str, JSONValue], accounting: dict[str, JSONValue] | None, source_snapshot: dict[str, str], config: PairingConfig, vfg_cache: dict[str, tuple[list[str], str | None]]) -> dict[str, JSONValue]:
    vision = example.get("model_facing", {}).get("vision", {})
    trace = example.get("supervised_target", {}).get("planner_trace", {})
    plan = [normalize_action_string(str(action)) for action in example.get("supervised_target", {}).get("plan", [])]
    vfg_path = resolve_repo_path(vision.get("trace_path"))
    frames = [resolve_repo_path(path) for path in vision.get("frame_paths", [])]
    frames = [path for path in frames if path is not None]
    cache_key = str(vfg_path) if vfg_path else ""
    if cache_key not in vfg_cache:
        vfg_cache[cache_key] = _vfg_actions(vfg_path)
    vfg_actions, vfg_error = vfg_cache[cache_key]
    alignment = _alignment_status(plan, vfg_actions, len(frames), vfg_error)
    planner = str(example["planner"])
    _assert_active_planner(planner)
    source_relative_path = source_jsonl.relative_to(dataset_root).as_posix()
    trace_text = json.dumps(trace, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    bucket = str((accounting or {}).get("bucket", ""))
    identity = FrozenSourceIdentity(dataset_root.name, source_relative_path, line_index, hashlib.sha256(source_bytes).hexdigest(), str(example["example_id"]), planner)
    try:
        project_traversal_events(identity, example)
    except TraceContractError as error:
        trace_contract_exclusion = error.reason
    else:
        trace_contract_exclusion = None
    exclusions = _exclusion_reasons(example, trace, len(plan), len(trace_text), bucket, config)
    if trace_contract_exclusion is not None:
        exclusions.append(f"trace_contract_exclusion:{trace_contract_exclusion}")
    pair_id = stable_hash([dataset_root.name, example["example_id"]])[:32]
    return {
        "schema_version": SCHEMA_VERSION,
        "pair_id": pair_id,
        "source_root": relpath(dataset_root),
        "source_root_id": dataset_root.name,
        "source_root_sha256": stable_hash(source_snapshot),
        "source_jsonl": source_relative_path,
        "source_split_sha256": source_snapshot[source_relative_path.removesuffix(".jsonl")],
        "source_line_index": line_index,
        "source_record_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "example_id": example["example_id"],
        "domain": example["domain"],
        "instance_id": example["instance_id"],
        "split": example["split"],
        "planner": planner,
        "active_planner_id": planner,
        "bucket": bucket,
        "plan_hash": example["plan_hash"],
        "trace_hash": stable_hash(trace),
        "trace_fidelity": example["trace_fidelity"],
        "planner_approximation": _planner_approximation(planner, trace),
        "domain_path": example["model_facing"]["domain_source"],
        "problem_path": example["model_facing"]["problem_source"],
        "render_trace_path": relpath(vfg_path) if vfg_path else "",
        "render_action_hash": stable_hash(vfg_actions),
        "frame_paths": [relpath(path) for path in frames],
        "frame_count": len(frames),
        "plan_length": len(plan),
        "trace_size_chars": len(trace_text),
        "vfg_action_count": len(vfg_actions),
        "frame_alignment_status": alignment,
        "vfg_error": vfg_error,
        "training_eligible": not exclusions,
        "exclusion_reasons": exclusions,
    }

def _exclusion_reasons(example: dict[str, JSONValue], trace: dict[str, JSONValue], plan_length: int, trace_chars: int, bucket: str, config: PairingConfig) -> list[str]:
    reasons: list[str] = []
    if str(example.get("trace_fidelity")) != "success_full_trace":
        reasons.append("trace_not_full_internal")
    if _has_recovery(trace):
        reasons.append("recovery_trace")
    if str(example.get("domain")) not in config.domains:
        reasons.append("domain_not_in_core")
    if bucket not in config.buckets:
        reasons.append("bucket_not_in_core")
    if plan_length > config.max_plan_length:
        reasons.append("plan_length_exceeds_limit")
    if trace_chars > config.max_trace_chars:
        reasons.append("trace_size_exceeds_limit")
    return reasons

def _has_recovery(value: JSONValue) -> bool:
    if isinstance(value, dict):
        if "plan_recovery" in value:
            return True
        return any(_has_recovery(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_recovery(item) for item in value)
    return False

def _vfg_actions(path: Path | None) -> tuple[list[str], str | None]:
    if path is None or not path.exists():
        return [], "missing_vfg"
    try:
        # VFG files embed large base64 sprite tables. Extracting stage names without
        # deserializing those tables keeps corpus-scale manifest generation bounded.
        text = path.read_text(encoding="utf-8")
        names = [json.loads(f'"{match.group(1)}"') for match in re.finditer(r'"stageName"\s*:\s*"((?:\\.|[^"\\])*)"', text)]
        actions = [normalize_action_string(name) for name in names[1:] if name.strip().startswith("(")]
        return actions, None
    except (OSError, json.JSONDecodeError, PDDLError) as exc:
        return [], type(exc).__name__

def _alignment_status(plan: list[str], vfg_actions: list[str], frame_count: int, error: str | None) -> str:
    if error:
        return error
    if plan != vfg_actions:
        return "action_mismatch"
    if frame_count in {len(plan), len(plan) + 1}:
        return "existing_exact_complete"
    return "existing_exact_preview_partial"

def _pairing_summary(records: list[dict[str, JSONValue]]) -> dict[str, JSONValue]:
    return {"schema_version": SCHEMA_VERSION, "pair_records": len(records), "training_eligible": sum(bool(row["training_eligible"]) for row in records), "by_split": dict(sorted(Counter(row["split"] for row in records).items())), "by_alignment": dict(sorted(Counter(row["frame_alignment_status"] for row in records).items())), "exclusions": dict(sorted(Counter(reason for row in records for reason in row["exclusion_reasons"]).items()))}
