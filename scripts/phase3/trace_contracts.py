from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Mapping, NoReturn, Sequence, TypeAlias

from .local_planner_types import JSONValue


TRACE_CONTRACT_VERSION: Final = "phase3_traversal_trace_v1"
ACTIVE_PLANNERS: Final = frozenset({"ff", "gbfs", "iw", "graphplan"})
CONCRETE_EVENT_KINDS: Final = frozenset({"expansion", "generation", "revisit", "backtrack"})
PlannerName: TypeAlias = Literal["ff", "gbfs", "iw", "graphplan"]
JSONMapping: TypeAlias = Mapping[str, JSONValue]


class TraceContractError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

    def __str__(self) -> str:
        return f"trace_contract_exclusion: {self.reason}"


@dataclass(frozen=True, slots=True)
class FrozenSourceIdentity:
    source_root_id: str
    source_jsonl: str
    source_line_index: int
    source_record_sha256: str
    example_id: str
    planner: PlannerName

    def to_record(self) -> dict[str, JSONValue]:
        return {
            "source_root_id": self.source_root_id,
            "source_jsonl": self.source_jsonl,
            "source_line_index": self.source_line_index,
            "source_record_sha256": self.source_record_sha256,
            "example_id": self.example_id,
            "planner": self.planner,
        }


@dataclass(frozen=True, slots=True)
class TraversalEvent:
    source_identity: FrozenSourceIdentity
    supervision_mode: Literal["concrete_state", "planner_semantics"]
    planner: PlannerName
    event_kind: str
    event_index: int
    node_id: str
    parent_node_id: str | None
    action: str | None
    concrete_state_source: Literal["trace_recorded"] | None
    concrete_state_hash: str | None
    planner_metadata: dict[str, JSONValue]

    def to_record(self) -> dict[str, JSONValue]:
        return {
            "source_identity": self.source_identity.to_record(),
            "supervision_mode": self.supervision_mode,
            "planner": self.planner,
            "event_kind": self.event_kind,
            "event_index": self.event_index,
            "node_id": self.node_id,
            "parent_node_id": self.parent_node_id,
            "action": self.action,
            "concrete_state_source": self.concrete_state_source,
            "concrete_state_hash": self.concrete_state_hash,
            "planner_metadata": self.planner_metadata,
        }


def project_traversal_events(identity: FrozenSourceIdentity, source_row: JSONMapping) -> tuple[TraversalEvent, ...]:
    _equal(_text(source_row, "example_id"), identity.example_id, "source_identity_mismatch: example_id")
    planner_text = _text(source_row, "planner")
    planner = _planner(planner_text)
    _equal(planner, identity.planner, "source_identity_mismatch: planner")
    trace = _mapping(_mapping(source_row, "supervised_target"), "planner_trace")
    _equal(_text(trace, "trace_contract_version"), TRACE_CONTRACT_VERSION, "unsupported_trace_contract_version")
    match planner_text:
        case "ff":
            return _ff_events(identity, trace)
        case "gbfs":
            return _gbfs_events(identity, trace)
        case "iw":
            return _iw_events(identity, trace)
        case "graphplan":
            return _graphplan_events(identity, trace)
        case unsupported:
            assert_never(unsupported, "unsupported_active_planner")


def _ff_events(identity: FrozenSourceIdentity, trace: JSONMapping) -> tuple[TraversalEvent, ...]:
    _equal(_text(trace, "algorithm"), "fast_forward", "planner_algorithm_mismatch")
    _list(trace, "goal_atoms")
    _text(trace, "planner_source")
    return tuple(
        _concrete_event(identity, "ff", index, _item_mapping(value, f"steps[{index}]"), "selected_action")
        for index, value in enumerate(_list(trace, "steps"))
    )


def _gbfs_events(identity: FrozenSourceIdentity, trace: JSONMapping) -> tuple[TraversalEvent, ...]:
    _equal(_text(trace, "algorithm"), "greedy_best_first", "planner_algorithm_mismatch")
    _text(trace, "heuristic_source")
    _integer(trace, "expansion_count")
    _integer(trace, "visited_count")
    return tuple(
        _concrete_event(identity, "gbfs", index, _item_mapping(value, f"frontier_events[{index}]"), None)
        for index, value in enumerate(_list(trace, "frontier_events"))
    )


def _iw_events(identity: FrozenSourceIdentity, trace: JSONMapping) -> tuple[TraversalEvent, ...]:
    _equal(_text(trace, "algorithm"), "iterated_width", "planner_algorithm_mismatch")
    _integer(trace, "width")
    return tuple(
        _concrete_event(identity, "iw", index, event, None)
        for index, value in enumerate(_list(trace, "events"))
        for event in (_item_mapping(value, f"events[{index}]"),)
    )


def _graphplan_events(identity: FrozenSourceIdentity, trace: JSONMapping) -> tuple[TraversalEvent, ...]:
    _equal(_text(trace, "algorithm"), "graphplan", "planner_algorithm_mismatch")
    proposition_layers = _list(trace, "proposition_layers")
    action_layers = _list(trace, "action_layers")
    _list(trace, "mutex_pairs")
    extraction = _mapping(trace, "extraction")
    events = [
        _graphplan_proposition_event(identity, index, _item_mapping(layer, f"proposition_layers[{index}]"))
        for index, layer in enumerate(proposition_layers)
    ]
    events.extend(
        _graphplan_action_event(identity, len(events) + index, _item_mapping(layer, f"action_layers[{index}]"))
        for index, layer in enumerate(action_layers)
    )
    events.append(_graphplan_extraction_event(identity, len(events), _graphplan_extraction(extraction)))
    return tuple(events)


def _graphplan_extraction(extraction: JSONMapping) -> JSONMapping:
    if "replay_parent_event_id" in extraction:
        raise TraceContractError("invalid_graphplan_extraction_parent_linkage")
    _strings(extraction, "selected_plan")
    return extraction


def _graphplan_proposition_event(identity: FrozenSourceIdentity, index: int, layer: JSONMapping) -> TraversalEvent:
    _integer(layer, "layer_index")
    _strings(layer, "propositions")
    _boolean(layer, "goal_present", prefix="proposition_layer")
    return _semantic_event(identity, "proposition_layer", index, layer, ("layer_index", "propositions", "goal_present"))


def _graphplan_action_event(identity: FrozenSourceIdentity, index: int, layer: JSONMapping) -> TraversalEvent:
    _integer(layer, "layer_index")
    _strings(layer, "actions")
    _list(layer, "mutex_pairs")
    _integer(layer, "next_layer_index")
    return _semantic_event(identity, "action_layer", index, layer, ("layer_index", "actions", "mutex_pairs", "next_layer_index"))


def _graphplan_extraction_event(identity: FrozenSourceIdentity, index: int, extraction: JSONMapping) -> TraversalEvent:
    for field in ("approximation", "mutex_scope", "source"):
        _text(extraction, field)
    for field in ("goal_present_without_mutex", "proposition_mutex_computed"):
        _boolean(extraction, field)
    _list(extraction, "no_goods")
    _integer(extraction, "selected_goal_layer")
    _strings(extraction, "selected_plan")
    return _semantic_event(identity, "extraction", index, extraction, ("approximation", "goal_present_without_mutex", "mutex_scope", "no_goods", "proposition_mutex_computed", "selected_goal_layer", "selected_plan", "source"))


def _concrete_event(identity: FrozenSourceIdentity, planner: PlannerName, index: int, event: JSONMapping, action_key: str | None) -> TraversalEvent:
    atoms = tuple(sorted(_strings(event, "state_atoms") if planner != "gbfs" else _strings(event, "selected_state_atoms")))
    required = ("step_index", "current_heuristic", "selected_successor", "successor_heuristics", "relaxation_metadata", "tie_break_rule") if planner == "ff" else ("current_heuristic", "successor_heuristics", "frontier_size_after", "visited_count_after", "tie_break_rule") if planner == "gbfs" else _iw_required_fields(event)
    for field in required:
        _value(event, field)
    action = _text(event, action_key) if action_key is not None else _optional_action(event)
    _validate_concrete_event_fields(event, planner)
    kind = _concrete_event_kind(event)
    _validate_successor_kinds(event, planner)
    return TraversalEvent(identity, "concrete_state", planner, kind, index, _node_id(identity, kind, index), None, action, "trace_recorded", _state_hash(atoms), dict(event))


def _iw_required_fields(event: JSONMapping) -> tuple[str, ...]:
    match _text(event, "decision"):
        case "expand":
            return ("decision", "frontier_size_after", "novel_item", "novelty_table_before", "novelty_table_after", "successors")
        case "prune":
            return ("decision", "frontier_size_after")
        case unsupported:
            assert_never(unsupported, "unsupported_iw_decision")


def _concrete_event_kind(event: JSONMapping) -> str:
    kind = _text(event, "event_kind")
    if kind not in CONCRETE_EVENT_KINDS:
        raise TraceContractError(f"unsupported_concrete_event_kind: {kind}")
    return kind


def _validate_successor_kinds(event: JSONMapping, planner: PlannerName) -> None:
    selected_key = "selected_successor" if "selected_successor" in event else "selected_goal_successor"
    if selected_key in event:
        _validate_successor(_item_mapping(_value(event, selected_key), selected_key), planner, selected_key)
    successors_key = "successor_heuristics" if "successor_heuristics" in event else "successors"
    if successors_key not in event:
        return
    for index, successor in enumerate(_list(event, successors_key)):
        _validate_successor(_item_mapping(successor, f"{planner}_successors[{index}]"), planner, f"{planner}_successors[{index}]")


def _validate_concrete_event_fields(event: JSONMapping, planner: PlannerName) -> None:
    _concrete_event_kind(event)
    _integer(event, "frontier_size_after") if "frontier_size_after" in event else None
    if planner == "ff":
        _integer(event, "step_index")
        _heuristic(event, "current_heuristic")
        _mapping(event, "relaxation_metadata")
        _text(event, "tie_break_rule")
    elif planner == "gbfs":
        _heuristic(event, "current_heuristic")
        _integer(event, "frontier_size_after")
        _integer(event, "visited_count_after")
        _text(event, "tie_break_rule")
    else:
        _integer(event, "frontier_size_after")
        if _text(event, "decision") == "expand":
            _list(event, "novel_item")
            _list(event, "novelty_table_before")
            _list(event, "novelty_table_after")


def _validate_successor(successor: JSONMapping, planner: PlannerName, path: str) -> None:
    _text(successor, "action")
    _concrete_event_kind(successor)
    if planner in {"ff", "gbfs"}:
        _integer(successor, "heuristic_value")
    if planner == "gbfs":
        for field in ("is_goal", "enqueued"):
            if field in successor:
                _boolean(successor, field)
    if planner == "iw":
        for field in ("is_goal", "is_novel", "enqueued"):
            _boolean(successor, field, prefix=path)


def _heuristic(value: JSONMapping, field: str) -> None:
    item = _value(value, field)
    if isinstance(item, int) and not isinstance(item, bool):
        return
    if isinstance(item, dict):
        _integer(item, "heuristic_value")
        return
    raise TraceContractError(f"invalid_field_type: {field}: integer_or_heuristic_object")


def _semantic_event(identity: FrozenSourceIdentity, kind: str, index: int, payload: JSONMapping, required: Sequence[str]) -> TraversalEvent:
    for field in required:
        _value(payload, field)
    _reject_visual_fields(payload, kind)
    return TraversalEvent(identity, "planner_semantics", "graphplan", kind, index, _node_id(identity, kind, index), None, None, None, None, dict(payload))


def _reject_visual_fields(value: JSONValue, path: str) -> None:
    forbidden = {"state_atoms", "state_asset_hash", "state_source", "frame_path", "render_candidate", "render_eligible", "render_job_eligible"}
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in forbidden:
                raise TraceContractError(f"forbidden_visual_field: {path}.{key}")
            _reject_visual_fields(nested, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_visual_fields(nested, f"{path}[{index}]")


def _planner(value: str) -> PlannerName:
    match value:
        case "ff" | "gbfs" | "iw" | "graphplan":
            return value
        case unsupported:
            assert_never(unsupported, "unsupported_active_planner")


def _mapping(value: JSONMapping, field: str) -> JSONMapping:
    return _item_mapping(_value(value, field), field)


def _item_mapping(item: JSONValue, field: str) -> JSONMapping:
    if not isinstance(item, dict):
        raise TraceContractError(f"invalid_field_type: {field}: object")
    return item


def _list(value: JSONMapping, field: str) -> list[JSONValue]:
    item = _value(value, field)
    if not isinstance(item, list):
        raise TraceContractError(f"invalid_field_type: {field}: array")
    return item


def _strings(value: JSONMapping, field: str) -> list[str]:
    items = _list(value, field)
    if not all(isinstance(item, str) for item in items):
        raise TraceContractError(f"invalid_field_type: {field}: string_array")
    return [item for item in items if isinstance(item, str)]


def _text(value: JSONMapping, field: str | None) -> str:
    if field is None:
        raise TraceContractError("missing_required_field: action")
    item = _value(value, field)
    if not isinstance(item, str):
        raise TraceContractError(f"invalid_field_type: {field}: string")
    return item


def _integer(value: JSONMapping, field: str) -> int:
    item = _value(value, field)
    if not isinstance(item, int) or isinstance(item, bool):
        raise TraceContractError(f"invalid_field_type: {field}: integer")
    return item


def _boolean(value: JSONMapping, field: str, *, prefix: str | None = None) -> bool:
    item = _value(value, field)
    path = f"{prefix}.{field}" if prefix is not None else field
    if not isinstance(item, bool):
        raise TraceContractError(f"invalid_field_type: {path}: boolean")
    return item


def _value(value: JSONMapping, field: str) -> JSONValue:
    if field not in value:
        raise TraceContractError(f"missing_required_field: {field}")
    return value[field]


def _equal(actual: str, expected: str, reason: str) -> None:
    if actual != expected:
        suffix = f": {actual}" if reason == "unsupported_trace_contract_version" else ""
        raise TraceContractError(f"{reason}{suffix}")


def _optional_action(event: JSONMapping) -> str | None:
    successor = event.get("selected_goal_successor")
    if successor is None:
        return None
    if not isinstance(successor, dict):
        raise TraceContractError("invalid_field_type: selected_goal_successor: object")
    return _text(successor, "action")


def _node_id(identity: FrozenSourceIdentity, kind: str, index: int) -> str:
    return f"{identity.source_record_sha256}:{kind}:{index}"


def _state_hash(atoms: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(atoms, separators=(",", ":")).encode("utf-8")).hexdigest()


def assert_never(value: str, reason: str) -> NoReturn:
    raise TraceContractError(f"{reason}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Project strict Phase 3 traversal-trace fixtures.")
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    cases = json.loads(arguments.fixtures.read_text(encoding="utf-8"))
    report = []
    for case in cases:
        source_row = case["source_row"]
        identity = FrozenSourceIdentity("fixture-root", "train.jsonl", 0, f"hash-{source_row['example_id']}", source_row["example_id"], _planner(source_row["planner"]))
        try:
            report.append({"name": case["name"], "events": len(project_traversal_events(identity, source_row)), "status": "projected"})
        except TraceContractError as error:
            report.append({"name": case["name"], "reason": error.reason, "status": "excluded"})
    arguments.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
