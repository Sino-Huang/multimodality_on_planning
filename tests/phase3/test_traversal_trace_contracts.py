from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from scripts.phase3.trace_contracts import (
    FrozenSourceIdentity,
    TraceContractError,
    project_traversal_events,
)


FIXTURES = Path("tests/phase3/fixtures/traversal_trace_contract_cases.json")


def test_projects_only_documented_events_for_each_valid_active_planner() -> None:
    cases = _cases()

    for case in (item for item in cases if item["valid"]):
        source_row = case["source_row"]
        events = project_traversal_events(_identity(source_row), source_row)

        assert events
        assert {event.planner for event in events} == {source_row["planner"]}
        assert all(event.event_index >= 0 for event in events)
        assert all(event.source_identity.example_id == source_row["example_id"] for event in events)
        assert all(set(event.to_record()) == _DOCUMENTED_EVENT_FIELDS for event in events)


def test_rejects_one_malformed_trace_for_each_active_planner() -> None:
    cases = _cases()

    for case in (item for item in cases if not item["valid"]):
        source_row = case["source_row"]

        with pytest.raises(TraceContractError, match=case["reason"]):
            project_traversal_events(_identity(source_row), source_row)


def test_rejects_absent_unsupported_and_legacy_trace_versions() -> None:
    source_row = _cases()[0]["source_row"]
    trace = source_row["supervised_target"]["planner_trace"]

    for version, reason in ((None, "missing_required_field: trace_contract_version"), ("v0", "unsupported_trace_contract_version: v0")):
        candidate = json.loads(json.dumps(source_row))
        if version is None:
            del candidate["supervised_target"]["planner_trace"]["trace_contract_version"]
        else:
            candidate["supervised_target"]["planner_trace"]["trace_contract_version"] = version

        with pytest.raises(TraceContractError, match=reason):
            project_traversal_events(_identity(candidate), candidate)

    assert trace["trace_contract_version"] == "phase3_traversal_trace_v1"


def test_graphplan_layers_never_claim_concrete_state_or_frame() -> None:
    source_row = _case("graphplan_valid")["source_row"]

    events = project_traversal_events(_identity(source_row), source_row)

    assert {event.event_kind for event in events} == {"proposition_layer", "action_layer", "extraction"}
    assert all(event.concrete_state_source is None for event in events)
    assert all(event.concrete_state_hash is None for event in events)


def test_rejects_graphplan_layer_supplied_as_concrete_state_atoms() -> None:
    # Given: a planning-graph proposition layer mislabeled as a concrete state.
    source_row = _case("graphplan_valid")["source_row"]
    layer = source_row["supervised_target"]["planner_trace"]["proposition_layers"][0]
    layer["state_atoms"] = layer.pop("propositions")

    # When: strict Graphplan semantics are projected.
    # Then: the layer is rejected rather than treated as a renderable PDDL state.
    with pytest.raises(TraceContractError, match="missing_required_field: propositions"):
        project_traversal_events(_identity(source_row), source_row)


def test_rejects_visual_fields_added_to_graphplan_semantic_payload() -> None:
    # Given: a valid Graphplan layer with a second, fabricated state representation.
    source_row = _case("graphplan_valid")["source_row"]
    layer = source_row["supervised_target"]["planner_trace"]["proposition_layers"][0]
    layer["state_atoms"] = ["(start)"]

    # When: the semantic layer is projected.
    # Then: visual state fields are rejected instead of being carried in semantic metadata.
    with pytest.raises(TraceContractError, match="forbidden_visual_field: proposition_layer.state_atoms"):
        project_traversal_events(_identity(source_row), source_row)


def test_rejects_graphplan_extraction_with_forged_replay_parent_linkage() -> None:
    # Given: a Graphplan extraction record that tries to supply its own replay parent.
    source_row = _case("graphplan_valid")["source_row"]
    source_row["supervised_target"]["planner_trace"]["extraction"]["replay_parent_event_id"] = "forged-parent"

    # When: semantic extraction is parsed.
    # Then: raw Graphplan metadata cannot forge concrete replay lineage.
    with pytest.raises(TraceContractError, match="invalid_graphplan_extraction_parent_linkage"):
        project_traversal_events(_identity(source_row), source_row)


def test_rejects_legacy_bfs_planner_without_aliasing_to_gbfs() -> None:
    source_row = _cases()[2]["source_row"]
    source_row["planner"] = "bfs"

    with pytest.raises(TraceContractError, match="unsupported_active_planner: bfs"):
        project_traversal_events(_identity(source_row), source_row)


@pytest.mark.parametrize(
    ("case_name", "field_path", "value", "reason"),
    [
        ("ff_valid", ("steps", 0, "step_index"), True, "invalid_field_type: step_index: integer"),
        ("ff_valid", ("steps", 0, "state_atoms", 0), 7, "invalid_field_type: state_atoms: string_array"),
        ("ff_valid", ("steps", 0, "selected_successor", "action"), 7, "invalid_field_type: action: string"),
        ("gbfs_valid", ("expansion_count",), True, "invalid_field_type: expansion_count: integer"),
        ("iw_valid", ("events", 0, "successors", 0, "is_goal"), "true", "invalid_field_type: iw_successors[0].is_goal: boolean"),
        ("graphplan_valid", ("proposition_layers", 0, "goal_present"), "false", "invalid_field_type: proposition_layer.goal_present: boolean"),
    ],
)
def test_rejects_wrong_scalar_types_in_planner_specific_trace_fields(
    case_name: str, field_path: tuple[str | int, ...], value: Any, reason: str
) -> None:
    # Given: a valid trace for each active planner with one typed field corrupted.
    source_row = _case(case_name)["source_row"]
    target: Any = source_row["supervised_target"]["planner_trace"]
    for field in field_path[:-1]:
        target = target[field]
    target[field_path[-1]] = value

    # When: the strict traversal boundary parses the trace.
    # Then: scalar coercion and malformed successor fields are excluded.
    with pytest.raises(TraceContractError, match=re.escape(reason)):
        project_traversal_events(_identity(source_row), source_row)


def test_rejects_malformed_nested_successor_object() -> None:
    # Given: an otherwise valid GBFS trace whose selected successor is not an object.
    source_row = _case("gbfs_valid")["source_row"]
    source_row["supervised_target"]["planner_trace"]["frontier_events"][0]["selected_goal_successor"] = []

    # When: the concrete event is projected.
    # Then: the malformed nested contract cannot bypass event validation.
    with pytest.raises(TraceContractError, match="invalid_field_type: selected_goal_successor: object"):
        project_traversal_events(_identity(source_row), source_row)


def _cases() -> list[dict[str, Any]]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def _case(name: str) -> dict[str, Any]:
    return next(item for item in _cases() if item["name"] == name)


def _identity(source_row: dict[str, Any]) -> FrozenSourceIdentity:
    return FrozenSourceIdentity(
        source_root_id="fixture-root",
        source_jsonl="train.jsonl",
        source_line_index=0,
        source_record_sha256=f"hash-{source_row['example_id']}",
        example_id=source_row["example_id"],
        planner=source_row["planner"],
    )


_DOCUMENTED_EVENT_FIELDS = {
    "source_identity",
    "supervision_mode",
    "planner",
    "event_kind",
    "event_index",
    "node_id",
    "parent_node_id",
    "action",
    "concrete_state_source",
    "concrete_state_hash",
    "planner_metadata",
}
