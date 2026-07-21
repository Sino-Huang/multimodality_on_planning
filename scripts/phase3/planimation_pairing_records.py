from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from .io_utils import read_jsonl, stable_hash, write_json, write_jsonl
from .pddl import parse_task
from .trace_contracts import TraceContractError, project_traversal_events
from .traversal_state_types import JSONValue
SCHEMA_VERSION = "phase3_planimation_vlm_v1"

__all__ = ("_write_hybrid_output_manifest",)

from .planimation_pairing_reasoning import compact_reasoning
from .planimation_pairing_replay import _search_traversal_transitions
from .planimation_pairing_rendering import _assert_repo_output_root
from .planimation_pairing_schema import _full_record, _search_traversal_record, _step_record, _write_vlm_schema
from .planimation_pairing_source import _load_source_example, _repo_path, _trace_identity
from .planimation_pairing_validation import _render_receipt_is_valid
def build_vlm_records(output_root: Path, *, reasoning_budget_chars: int = 8192) -> dict[str, JSONValue]:
    """Emit full-trace and per-transition model-neutral JSONL records from cached states."""
    _assert_repo_output_root(output_root)
    if reasoning_budget_chars < 256:
        raise ValueError("reasoning_budget_chars must be at least 256")
    pairs = {str(row["pair_id"]): row for row in read_jsonl(output_root / "diagnostics" / "pairing_manifest.jsonl")}
    renders = read_jsonl(output_root / "diagnostics" / "state_render_manifest.jsonl")
    renders_by_pair: dict[str, list[dict[str, JSONValue]]] = {}
    source_snapshots: dict[str, dict[str, str]] = {}
    source_rows: dict[str, dict[int, tuple[bytes, dict[str, JSONValue]]]] = {}
    for row in renders:
        if row["status"] == "success":
            renders_by_pair.setdefault(str(row["pair_id"]), []).append(row)
    full_by_split: dict[str, list[dict[str, JSONValue]]] = {split: [] for split in ("train", "dev", "test")}
    step_by_split: dict[str, list[dict[str, JSONValue]]] = {split: [] for split in ("train", "dev", "test")}
    traversal_by_split: dict[str, list[dict[str, JSONValue]]] = {split: [] for split in ("train", "dev", "test")}
    skipped: Counter[str] = Counter()
    for pair_id, pair in sorted(pairs.items()):
        rows = renders_by_pair.get(pair_id, [])
        replay_rows = sorted((row for row in rows if row["transition"].get("record_family", "plan_replay") == "plan_replay"), key=lambda row: int(row["step_index"]))
        traversal_rows = sorted((row for row in rows if row["transition"].get("record_family") == "search_traversal"), key=lambda row: str(row["transition"]["event_id"]))
        source = _load_source_example(pair, source_snapshots=source_snapshots, source_rows=source_rows)
        project_traversal_events(_trace_identity(pair), source)
        expected_traversal_event_ids = {
            str(transition["event_id"])
            for transition in _search_traversal_transitions(pair, source)
        }
        actual_traversal_event_ids = {
            str(row["transition"]["event_id"])
            for row in traversal_rows
            if _render_receipt_is_valid(row)
        }
        if actual_traversal_event_ids != expected_traversal_event_ids:
            skipped["search_traversal_coverage_mismatch"] += 1
            traversal_rows = []
        recordable, cardinality_error = _recordable_render_rows(source, replay_rows)
        if cardinality_error is not None:
            skipped[cardinality_error] += 1
            continue
        task = parse_task(_repo_path(pair["domain_path"]), _repo_path(pair["problem_path"]))
        split = str(pair["split"])
        full_by_split[split].append(_full_record(pair, source, recordable[0], task.goal))
        trace = source["supervised_target"]["planner_trace"]
        for state_row in recordable[1]:
            transition = state_row["transition"]
            reasoning = compact_reasoning(trace, str(pair["planner"]), transition, reasoning_budget_chars)
            if reasoning["context_status"] == "plan_level":
                raise TraceContractError("trace_event_not_bound_to_replay_transition")
            step_by_split[split].append(_step_record(pair, source, state_row, task.goal, reasoning))
        for state_row in traversal_rows:
            traversal_by_split[split].append(_search_traversal_record(pair, source, state_row, task.goal))
    for split in ("train", "dev", "test"):
        full_by_split[split].sort(key=lambda row: row["record_id"])
        step_by_split[split].sort(key=lambda row: row["record_id"])
        write_jsonl(output_root / f"full_reasoning_{split}.jsonl", full_by_split[split])
        write_jsonl(output_root / f"step_vlm_{split}.jsonl", step_by_split[split])
        write_jsonl(output_root / f"search_traversal_{split}.jsonl", traversal_by_split[split])
    _write_vlm_schema(output_root / "schema" / "full_reasoning.schema.json", "full_reasoning_record")
    _write_vlm_schema(output_root / "schema" / "step_vlm.schema.json", "step_vlm_record")
    _write_vlm_schema(output_root / "schema" / "search_traversal.schema.json", "search_traversal_record")
    summary = {
        "schema_version": SCHEMA_VERSION,
        "reasoning_budget_chars": reasoning_budget_chars,
        "full_records": {split: len(rows) for split, rows in full_by_split.items()},
        "step_records": {split: len(rows) for split, rows in step_by_split.items()},
        "search_traversal_records": {split: len(rows) for split, rows in traversal_by_split.items()},
        "skipped": dict(sorted(skipped.items())),
    }
    write_json(output_root / "reports" / "vlm_record_summary.json", summary)
    _reconcile_hybrid_output_manifest(output_root, summary)
    return summary

def _recordable_render_rows(source: dict[str, JSONValue], rows: list[dict[str, JSONValue]]) -> tuple[tuple[dict[str, JSONValue], list[dict[str, JSONValue]]] | None, str | None]:
    plan = source["supervised_target"].get("plan")
    if not isinstance(plan, list):
        return None, "render_cardinality_invalid"
    expected = len(plan)
    successful = [row for row in rows if _render_receipt_is_valid(row)]
    if len(successful) != len(rows):
        return None, "semantic_image_invalid"
    pre_action = [row for row in successful if row.get("transition", {}).get("frame_role") == "pre_action"]
    terminal = [row for row in successful if row.get("transition", {}).get("frame_role") in {"terminal_traversal_diagnostic", "initial_terminal_full"}]
    if expected == 0:
        if len(pre_action) != 0 or len(terminal) != 1 or int(terminal[0]["step_index"]) != 0:
            return None, "zero_action_cardinality_mismatch"
        return (terminal[0], []), None
    if len(pre_action) != expected or len(terminal) != 1 or [int(row["step_index"]) for row in pre_action] != list(range(expected)):
        return None, "render_cardinality_mismatch"
    if int(terminal[0]["step_index"]) != expected:
        return None, "render_cardinality_mismatch"
    return (pre_action[0], pre_action), None

def _write_hybrid_output_manifest(output_root: Path, output_mode: str, render_limit: int | None, state_rows: list[dict[str, JSONValue]]) -> None:
    selected_pair_ids = sorted({str(row["pair_id"]) for row in state_rows})
    selected_state_ids = [stable_hash([row["pair_id"], row.get("transition", {}).get("event_id", row["step_index"]), row.get("state_hash", "")])[:32] for row in state_rows]
    write_json(output_root / "diagnostics" / "hybrid_output_manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "hybrid_output_manifest",
        "output_mode": output_mode,
        "partial": output_mode == "bounded-smoke",
        "selection": {"render_limit": render_limit, "selected_pair_ids": selected_pair_ids, "selected_state_ids": selected_state_ids},
        "counts": {"state_render_records": len(state_rows), "full_records": {split: 0 for split in ("train", "dev", "test")}, "step_records": {split: 0 for split in ("train", "dev", "test")}, "search_traversal_records": {split: 0 for split in ("train", "dev", "test")}},
        "production_complete": False,
    })

def _reconcile_hybrid_output_manifest(output_root: Path, summary: dict[str, JSONValue]) -> None:
    manifest_path = output_root / "diagnostics" / "hybrid_output_manifest.json"
    if not manifest_path.exists():
        raise ValueError("missing hybrid output manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"]["full_records"] = summary["full_records"]
    manifest["counts"]["step_records"] = summary["step_records"]
    manifest["counts"]["search_traversal_records"] = summary["search_traversal_records"]
    manifest["production_complete"] = manifest["output_mode"] == "production" and not summary["skipped"]
    write_json(manifest_path, manifest)
