from __future__ import annotations
from pathlib import Path
from .io_utils import read_jsonl, stable_hash, write_json, write_jsonl
from .graphplan_render_transitions import graphplan_render_transitions
from .pddl import canonical_atom, parse_task
from .trace_contracts import FrozenSourceIdentity
from .traversal_state_types import JSONValue, TraversalProjectionInput
from .traversal_states import project_traversal_state_candidates
from .planimation_pairing_contracts import ProgressCallback, RenderConfig, StateRenderer
SCHEMA_VERSION = "phase3_planimation_vlm_v1"

from .planimation_pairing_reasoning import _state_summary
from .planimation_pairing_rendering import _assert_repo_output_root, _render_one_state, render_state_with_planimation
from .planimation_pairing_source import _load_source_example, _repo_path, _trace_identity
def render_replay_states(
    output_root: Path,
    *,
    renderer: StateRenderer | None = None,
    config: RenderConfig = RenderConfig(),
    max_states: int | None = None,
    output_mode: str = "production",
    progress_callback: ProgressCallback | None = None,
    progress_every: int = 100,
) -> dict[str, JSONValue]:
    """Render every eligible replay state as a cached Planimation stage-zero PNG."""
    _assert_repo_output_root(output_root)
    if output_mode not in {"production", "bounded-smoke"}:
        raise ValueError(f"unsupported output mode: {output_mode}")
    if output_mode == "production" and max_states is not None:
        raise ValueError("production output does not permit a render limit")
    if progress_every < 1:
        raise ValueError("progress_every must be at least one")
    pairs = read_jsonl(output_root / "diagnostics" / "pairing_manifest.jsonl")
    state_rows: list[dict[str, JSONValue]] = []
    source_snapshots: dict[str, dict[str, str]] = {}
    source_rows: dict[str, dict[int, tuple[bytes, dict[str, JSONValue]]]] = {}
    renderer = renderer or render_state_with_planimation
    _emit_progress(progress_callback, "state_render_started", output_root, output_mode, max_states, state_rows)
    for pair in pairs:
        if not pair["training_eligible"]:
            continue
        source = _load_source_example(pair, source_snapshots=source_snapshots, source_rows=source_rows)
        try:
            transitions = [*_render_transitions(pair, source), *_search_traversal_transitions(pair, source)]
        except ValueError as exc:
            state_rows.append({"schema_version": SCHEMA_VERSION, "pair_id": pair["pair_id"], "domain": pair["domain"], "instance_id": pair["instance_id"], "split": pair["split"], "planner": pair["planner"], "step_index": -1, "status": "failed", "cache_hit": False, "message": str(exc), "failure_kind": "render_cardinality_invalid"})
            if len(state_rows) % progress_every == 0:
                _emit_progress(progress_callback, "state_render_progress", output_root, output_mode, max_states, state_rows)
            continue
        for transition in transitions:
            if max_states is not None and len(state_rows) >= max_states:
                break
            state_rows.append(_render_one_state(pair, transition, output_root, renderer, config))
            if len(state_rows) % progress_every == 0:
                _emit_progress(progress_callback, "state_render_progress", output_root, output_mode, max_states, state_rows)
        if max_states is not None and len(state_rows) >= max_states:
            break
    state_rows.sort(key=lambda row: (row["split"], row["domain"], row["instance_id"], row["planner"], row.get("transition", {}).get("record_family", "plan_replay"), row.get("transition", {}).get("event_id", ""), row["step_index"]))
    write_jsonl(output_root / "diagnostics" / "state_render_manifest.jsonl", state_rows)
    summary = _state_summary(state_rows)
    write_json(output_root / "reports" / "state_render_summary.json", summary)
    from .planimation_pairing_records import _write_hybrid_output_manifest

    _write_hybrid_output_manifest(output_root, output_mode, max_states, state_rows)
    _emit_progress(progress_callback, "state_render_finished", output_root, output_mode, max_states, state_rows)
    return {"records": state_rows, "summary": summary}


def _emit_progress(
    progress_callback: ProgressCallback | None,
    phase: str,
    output_root: Path,
    output_mode: str,
    max_states: int | None,
    state_rows: list[dict[str, JSONValue]],
) -> None:
    if progress_callback is None:
        return
    failure_messages = sorted({str(row["message"]) for row in state_rows if row.get("status") == "failed" and isinstance(row.get("message"), str)})[:3]
    progress_callback(
        {
            "phase": phase,
            "output_root": output_root.as_posix(),
            "output_mode": output_mode,
            "max_states": max_states,
            "processed_states": len(state_rows),
            "failure_messages": failure_messages,
            "summary": _state_summary(state_rows),
        }
    )

def _render_transitions(pair: dict[str, JSONValue], source: dict[str, JSONValue]) -> list[dict[str, JSONValue]]:
    plan = source["supervised_target"].get("plan")
    if not isinstance(plan, list) or not all(isinstance(action, str) for action in plan):
        raise ValueError("render_cardinality_invalid: plan must be a string list")
    if pair["planner"] != "graphplan":
        transitions = source["supervised_target"].get("replay_transitions", [])
    else:
        identity = FrozenSourceIdentity(
            str(pair["source_root_id"]),
            str(pair["source_jsonl"]),
            int(pair["source_line_index"]),
            str(pair["source_record_sha256"]),
            str(pair["example_id"]),
            "graphplan",
        )
        request = TraversalProjectionInput(
            identity,
            source,
            _repo_path(str(pair["domain_path"])),
            _repo_path(str(pair["problem_path"])),
        )
        transitions = [transition.to_record() for transition in graphplan_render_transitions(request)]
    if not isinstance(transitions, list) or len(transitions) != len(plan):
        raise ValueError("render_cardinality_invalid: action and pre-action state counts differ")
    if not transitions:
        initial = sorted(canonical_atom(atom) for atom in parse_task(_repo_path(str(pair["domain_path"])), _repo_path(str(pair["problem_path"]))).init)
        return [{"record_family": "plan_replay", "event_id": stable_hash([pair["pair_id"], "plan_replay", 0])[:32], "step_index": 0, "action": None, "state_before": initial, "state_after": initial, "frame_role": "initial_terminal_full", "state_source": "plan_replay"}]
    normalized: list[dict[str, JSONValue]] = []
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict) or transition.get("step_index") != index or transition.get("action") != plan[index]:
            raise ValueError("render_cardinality_invalid: replay transition does not match plan")
        normalized.append({**transition, "record_family": "plan_replay", "event_id": stable_hash([pair["pair_id"], "plan_replay", index])[:32], "frame_role": "pre_action", "state_source": transition.get("state_source", "plan_replay")})
    terminal = normalized[-1]
    normalized.append({**terminal, "step_index": len(plan), "action": None, "state_before": terminal["state_after"], "state_after": terminal["state_after"], "frame_role": "terminal_traversal_diagnostic"})
    return normalized

def _search_traversal_transitions(pair: dict[str, JSONValue], source: dict[str, JSONValue]) -> list[dict[str, JSONValue]]:
    if pair["planner"] == "graphplan":
        return []
    projection = project_traversal_state_candidates(
        TraversalProjectionInput(
            _trace_identity(pair),
            source,
            _repo_path(str(pair["domain_path"])),
            _repo_path(str(pair["problem_path"])),
        )
    )
    return [
        {
            "record_family": "search_traversal",
            "event_id": candidate.event_id,
            "parent_event_id": candidate.parent_event_id,
            "event_kind": candidate.event_kind,
            "state_role": candidate.state_role,
            "state_source": candidate.state_source,
            "state_asset_hash": candidate.state_asset_hash,
            "normalized_action": candidate.normalized_action,
            "step_index": candidate.extraction_step_index if candidate.extraction_step_index is not None else -1,
            "action": candidate.normalized_action,
            "state_before": list(candidate.state_atoms),
            "state_after": list(candidate.state_atoms),
            "frame_role": "search_traversal",
        }
        for candidate in projection.candidates
    ]
