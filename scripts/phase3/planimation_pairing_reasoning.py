from __future__ import annotations
import json
from collections import Counter
from .pddl import canonical_atom
from .traversal_state_types import JSONValue
SCHEMA_VERSION = "phase3_planimation_vlm_v1"

__all__ = ("_language_context", "_planner_approximation", "_state_summary")

def compact_reasoning(trace: dict[str, JSONValue], planner: str, transition: dict[str, JSONValue], budget_chars: int) -> dict[str, JSONValue]:
    """Extract factual, small algorithm-specific context for one replay transition."""
    action = str(transition["action"])
    state = tuple(sorted(str(atom) for atom in transition["state_before"]))
    payload: dict[str, JSONValue] = {"algorithm": trace.get("algorithm", planner), "selected_action": action, "context_status": "plan_level"}
    if planner == "gbfs":
        for event in trace.get("frontier_events", []):
            if tuple(sorted(event.get("selected_state_atoms", []))) == state:
                successor = _find_action(event.get("successor_heuristics", []), action)
                if successor:
                    payload.update({"context_status": "step_bound", "heuristic_source": trace.get("heuristic_source"), "current_heuristic": event.get("current_heuristic"), "selected_successor": successor, "frontier_size_after": event.get("frontier_size_after"), "visited_count_after": event.get("visited_count_after")})
                    break
    elif planner == "ff":
        for event in trace.get("steps", []):
            if str(event.get("selected_action")) == action and tuple(sorted(event.get("state_atoms", []))) == state:
                current = event.get("current_heuristic", {})
                payload.update({"context_status": "step_bound", "heuristic_source": current.get("heuristic_source"), "heuristic_value": current.get("heuristic_value"), "selected_successor": event.get("selected_successor"), "relaxed_plan": current.get("relaxed_plan"), "relaxation_metadata": event.get("relaxation_metadata")})
                break
    elif planner == "iw":
        payload["width"] = trace.get("width")
        for event in trace.get("events", []):
            if tuple(sorted(event.get("state_atoms", []))) == state:
                successor = _find_action(event.get("successors", []), action)
                if successor:
                    payload.update({"context_status": "step_bound", "decision": event.get("decision"), "novel_item": event.get("novel_item"), "selected_successor": successor, "frontier_size_after": event.get("frontier_size_after")})
                    break
    elif planner == "graphplan":
        layers = trace.get("action_layers", [])
        for layer in layers:
            actions = layer.get("actions", [])
            if action in actions:
                partners = [pair for pair in layer.get("mutex_pairs", []) if action in pair][:16]
                payload.update({"context_status": "layer_bound", "action_layer": layer.get("layer_index"), "mutex_partners": partners, "extraction": trace.get("extraction")})
                break
    return _trim_payload(payload, budget_chars)

def _language_context(state_atoms: list[str], goal: JSONValue, planner: str) -> dict[str, JSONValue]:
    return {"instruction": f"Given the rendered current state and PDDL facts, execute the next {planner} planning action.", "current_state_pddl": " ".join(sorted(str(atom) for atom in state_atoms)), "goal_pddl": " ".join(sorted(canonical_atom(atom) for atom in goal))}

def _find_action(items: JSONValue, action: str) -> dict[str, JSONValue] | None:
    for item in items if isinstance(items, list) else []:
        if str(item.get("action")) == action:
            return item
    return None

def _trim_payload(payload: dict[str, JSONValue], budget: int) -> dict[str, JSONValue]:
    encoded = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    if len(encoded(payload)) <= budget:
        return payload
    trimmed = {key: value for key, value in payload.items() if key in {"algorithm", "selected_action", "context_status", "heuristic_source", "heuristic_value", "width", "decision", "novel_item", "action_layer"}}
    trimmed["truncated_fields"] = sorted(set(payload) - set(trimmed))
    if len(encoded(trimmed)) > budget:
        raise ValueError("mandatory compact reasoning fields exceed budget")
    return trimmed

def _planner_approximation(planner: str, _trace: dict[str, JSONValue]) -> str:
    if planner == "ff":
        return "ff_style_delete_relaxed"
    if planner == "graphplan":
        return "action_mutex_graphplan"
    return "configured_method"

def _state_summary(records: list[dict[str, JSONValue]]) -> dict[str, JSONValue]:
    return {"schema_version": SCHEMA_VERSION, "state_render_records": len(records), "status": dict(sorted(Counter(row["status"] for row in records).items())), "cache_hits": sum(bool(row.get("cache_hit")) for row in records)}
