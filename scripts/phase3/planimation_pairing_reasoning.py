from __future__ import annotations
import json
from collections import Counter
from .pddl import PDDLError, canonical_atom, normalize_action_string
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
        payload.update(_graphplan_extraction_context(trace, transition, planner))
    return _trim_payload(payload, budget_chars)

def _language_context(state_atoms: list[str], goal: JSONValue, planner: str) -> dict[str, JSONValue]:
    return {"instruction": f"Given the rendered current state and PDDL facts, execute the next {planner} planning action.", "current_state_pddl": " ".join(sorted(str(atom) for atom in state_atoms)), "goal_pddl": " ".join(sorted(canonical_atom(atom) for atom in goal))}

def _find_action(items: JSONValue, action: str) -> dict[str, JSONValue] | None:
    for item in items if isinstance(items, list) else []:
        if str(item.get("action")) == action:
            return item
    return None


def _graphplan_extraction_context(
    trace: dict[str, JSONValue], transition: dict[str, JSONValue], planner: str
) -> dict[str, JSONValue]:
    extraction = trace.get("extraction")
    step_index = transition.get("step_index")
    event_id = transition.get("extraction_event_id")
    if (
        transition.get("state_source") != "extracted_plan_replay"
        or not isinstance(event_id, str)
        or not event_id
        or not isinstance(step_index, int)
        or isinstance(step_index, bool)
        or not isinstance(extraction, dict)
    ):
        return {}
    selected_plan = extraction.get("selected_plan")
    source = extraction.get("source")
    approximation = extraction.get("approximation")
    selected_goal_layer = extraction.get("selected_goal_layer")
    if (
        not isinstance(selected_plan, list)
        or step_index < 0
        or step_index >= len(selected_plan)
        or not isinstance(source, str)
        or not isinstance(approximation, str)
        or not isinstance(selected_goal_layer, int)
        or isinstance(selected_goal_layer, bool)
    ):
        return {}
    transition_action = _normalized_action(transition.get("action"))
    extraction_action = _normalized_action(selected_plan[step_index])
    if transition_action is None or transition_action != extraction_action:
        return {}
    context: dict[str, JSONValue] = {
        "algorithm": trace.get("algorithm", planner),
        "selected_action": transition_action,
        "context_status": "extraction_bound",
        "extraction_step_index": step_index,
        "extraction_source": source,
        "approximation": approximation,
        "selected_goal_layer": selected_goal_layer,
    }
    matching_layers = _matching_action_layers(trace.get("action_layers"), transition_action)
    if matching_layers:
        context["matching_action_layers"] = matching_layers
    return context


def _normalized_action(value: JSONValue) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return normalize_action_string(value)
    except PDDLError:
        return None


def _matching_action_layers(layers: JSONValue | None, action: str) -> list[dict[str, JSONValue]]:
    if not isinstance(layers, list):
        return []
    matches: list[tuple[int, list[JSONValue]]] = []
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        layer_index = layer.get("layer_index")
        actions = layer.get("actions")
        if (
            not isinstance(layer_index, int)
            or isinstance(layer_index, bool)
            or not isinstance(actions, list)
            or not any(_normalized_action(candidate) == action for candidate in actions)
        ):
            continue
        mutex_pairs = layer.get("mutex_pairs")
        pairs = mutex_pairs if isinstance(mutex_pairs, list) else []
        partners = [
            pair
            for pair in pairs
            if isinstance(pair, list) and any(_normalized_action(candidate) == action for candidate in pair)
        ]
        matches.append((layer_index, sorted(partners, key=lambda pair: json.dumps(pair, ensure_ascii=True, separators=(",", ":")))[:16]))
    return [
        {"layer_index": layer_index, "mutex_partners": partners}
        for layer_index, partners in sorted(matches, key=lambda match: match[0])
    ]

def _trim_payload(payload: dict[str, JSONValue], budget: int) -> dict[str, JSONValue]:
    encoded = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    if len(encoded(payload)) <= budget:
        return payload
    retained = {"algorithm", "selected_action", "context_status", "heuristic_source", "heuristic_value", "width", "decision", "novel_item", "action_layer"}
    if payload.get("context_status") == "extraction_bound":
        retained = {"algorithm", "selected_action", "context_status", "extraction_step_index", "extraction_source", "approximation", "selected_goal_layer"}
    trimmed = {key: value for key, value in payload.items() if key in retained}
    if len(encoded(trimmed)) > budget:
        if payload.get("context_status") == "extraction_bound":
            return trimmed
        raise ValueError("mandatory compact reasoning fields exceed budget")
    truncated_fields = sorted(set(payload) - set(trimmed))
    with_truncation = {**trimmed, "truncated_fields": truncated_fields}
    if len(encoded(with_truncation)) <= budget:
        return with_truncation
    return trimmed

def _planner_approximation(planner: str, _trace: dict[str, JSONValue]) -> str:
    if planner == "ff":
        return "ff_style_delete_relaxed"
    if planner == "graphplan":
        return "action_mutex_graphplan"
    return "configured_method"

def _state_summary(records: list[dict[str, JSONValue]]) -> dict[str, JSONValue]:
    return {"schema_version": SCHEMA_VERSION, "state_render_records": len(records), "status": dict(sorted(Counter(row["status"] for row in records).items())), "cache_hits": sum(bool(row.get("cache_hit")) for row in records)}
