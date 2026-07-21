from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.phase3.trace_contracts import FrozenSourceIdentity, project_traversal_events
from scripts.phase3.traversal_states import TraversalProjectionInput, project_traversal_state_candidates


FIXTURES = Path("tests/phase3/fixtures/traversal_state_projection_cases.json")
DOMAIN = Path("tests/phase3/fixtures/traversal_state_domain.pddl")
PROBLEM = Path("tests/phase3/fixtures/traversal_state_problem.pddl")
UNSUPPORTED_DOMAIN = Path("tests/phase3/fixtures/traversal_unsupported_domain.pddl")
UNSUPPORTED_PROBLEM = Path("tests/phase3/fixtures/traversal_unsupported_problem.pddl")


def test_projects_direct_and_reconstructed_states_for_each_concrete_planner() -> None:
    # Given: nonzero-plan FF, GBFS, and IW strict trace fixtures.
    projections = {case["source_row"]["planner"]: _project(case["source_row"]) for case in _cases()}

    # When: the concrete states are extracted.
    candidates = {planner: projection.candidates for planner, projection in projections.items()}

    # Then: FF preserves its recorded successor and GBFS/IW reconstruct successors.
    assert candidates["ff"][1].state_source == "trace_recorded"
    assert candidates["gbfs"][1].state_source == "pddl_action_reconstruction"
    assert candidates["iw"][1].state_source == "pddl_action_reconstruction"
    assert all(candidate.state_atoms[0] == "(at b)" for rows in candidates.values() for candidate in rows[1:])


def test_repeated_state_assets_do_not_merge_graph_events() -> None:
    # Given: GBFS and IW visits to equal selected and successor states.
    projections = [_project(case["source_row"]) for case in _cases() if case["source_row"]["planner"] in {"gbfs", "iw"}]

    # When: candidates share a canonical state asset hash.
    repeated = [candidate for projection in projections for candidate in projection.candidates if candidate.state_atoms[0] == "(at b)"]

    # Then: each graph event remains separately addressable.
    assert len({candidate.state_asset_hash for candidate in repeated}) == 1
    assert len({candidate.event_id for candidate in repeated}) == len(repeated)


def test_repeated_expansions_in_one_trace_keep_distinct_event_ids() -> None:
    # Given: two GBFS expansion records that select the same concrete state.
    source_row = _case("gbfs_nonzero_plan")["source_row"]
    events = source_row["supervised_target"]["planner_trace"]["frontier_events"]
    events.append(json.loads(json.dumps(events[0])))

    # When: both records are projected from one frozen source row.
    projection = _project(source_row)
    selected = [candidate for candidate in projection.candidates if candidate.state_role == "selected_state"]

    # Then: one shared state asset never aliases the separate expansion events.
    assert len(selected) == 2
    assert len({candidate.state_asset_hash for candidate in selected}) == 1
    assert len({candidate.event_id for candidate in selected}) == 2


def test_preserves_explicit_successor_semantics_when_assets_repeat() -> None:
    # Given: one GBFS expansion with recorded generation, revisit, and backtrack successors.
    source_row = _case("gbfs_nonzero_plan")["source_row"]
    event = source_row["supervised_target"]["planner_trace"]["frontier_events"][0]
    event["event_kind"] = "expansion"
    successor = event["successor_heuristics"][0]
    successor["event_kind"] = "generation"
    revisit = json.loads(json.dumps(successor))
    revisit["event_kind"] = "revisit"
    backtrack = json.loads(json.dumps(successor))
    backtrack["event_kind"] = "backtrack"
    event["successor_heuristics"] = [successor, revisit, backtrack]
    event["selected_goal_successor"]["event_kind"] = "generation"

    # When: the strict trace is projected into concrete candidates.
    projection = _project(source_row)
    successors = [candidate for candidate in projection.candidates if candidate.state_role == "successor"]

    # Then: equal state assets retain their recorded and distinct graph semantics.
    assert [candidate.event_kind for candidate in successors] == ["generation", "revisit", "backtrack"]
    assert len({candidate.state_asset_hash for candidate in successors}) == 1
    assert len({candidate.event_id for candidate in successors}) == 3


def test_excludes_missing_successor_semantics_without_guessing() -> None:
    # Given: a GBFS trace whose recorded successor has no semantic label.
    source_row = _case("gbfs_nonzero_plan")["source_row"]
    event = source_row["supervised_target"]["planner_trace"]["frontier_events"][0]
    del event["successor_heuristics"][0]["event_kind"]
    del event["selected_goal_successor"]["event_kind"]

    # When: strict projection receives the incomplete event contract.
    projection = _project(source_row)

    # Then: it excludes the trace rather than assigning parent semantics.
    assert not projection.candidates
    assert [item.reason for item in projection.exclusions] == ["missing_required_field: event_kind"]


def test_excludes_inapplicable_and_atom_mismatched_successors_without_candidates() -> None:
    # Given: one inapplicable GBFS edge and one FF successor whose atoms disagree with PDDL effects.
    gbfs = _case("gbfs_nonzero_plan")
    gbfs["source_row"]["supervised_target"]["planner_trace"]["frontier_events"][0]["selected_state_atoms"][0] = "(at b)"
    ff = _case("ff_nonzero_plan")
    successor = ff["source_row"]["supervised_target"]["planner_trace"]["steps"][0]["selected_successor"]
    successor["state_atoms"][0] = "(at a)"
    ff["source_row"]["supervised_target"]["planner_trace"]["steps"][0]["successor_heuristics"][0]["state_atoms"][0] = "(at a)"

    # When: successor reconstruction validates each recorded action against its parent state.
    excluded = [_project(gbfs["source_row"]), _project(ff["source_row"])]

    # Then: no frame candidate is created for either invalid successor edge.
    assert [item.reason for item in excluded[0].exclusions] == ["inapplicable_action"]
    assert [item.reason for item in excluded[1].exclusions] == ["successor_atom_mismatch"]
    assert all(len(projection.candidates) == 1 for projection in excluded)


def test_preserves_source_identity_and_active_contract_on_each_candidate() -> None:
    # Given: a frozen-source FF row.
    source_row = _case("ff_nonzero_plan")["source_row"]

    # When: candidates are projected.
    projection = _project(source_row)

    # Then: all candidates retain frozen provenance and the active contract version.
    assert all(candidate.source_identity == _identity(source_row) for candidate in projection.candidates)
    assert {candidate.trace_contract_version for candidate in projection.candidates} == {"phase3_traversal_trace_v1"}


def test_excludes_unknown_actions_and_missing_parent_atoms_without_frame_candidates() -> None:
    # Given: an unknown GBFS successor and an IW event missing its recorded parent state.
    unknown = _case("gbfs_nonzero_plan")
    event = unknown["source_row"]["supervised_target"]["planner_trace"]["frontier_events"][0]
    event["successor_heuristics"][0]["action"] = "(fly a b)"
    event["selected_goal_successor"]["action"] = "(fly a b)"
    missing_parent = _case("iw_nonzero_plan")
    del missing_parent["source_row"]["supervised_target"]["planner_trace"]["events"][0]["state_atoms"]

    # When: the traversal projection validates graph edges against recorded parents.
    unknown_projection = _project(unknown["source_row"])
    missing_parent_projection = _project(missing_parent["source_row"])

    # Then: both sources produce controlled exclusions and no invalid frame candidate.
    assert [item.reason for item in unknown_projection.exclusions] == ["unknown_action"]
    assert len(unknown_projection.candidates) == 1
    assert [item.reason for item in missing_parent_projection.exclusions] == ["missing_required_field: state_atoms"]
    assert not missing_parent_projection.candidates


def test_excludes_unsupported_pddl_before_successor_reconstruction() -> None:
    # Given: a strict GBFS trace and a PDDL task outside the supported STRIPS subset.
    source_row = _case("gbfs_nonzero_plan")["source_row"]

    # When: concrete candidate extraction evaluates the task semantics.
    projection = project_traversal_state_candidates(
        TraversalProjectionInput(_identity(source_row), source_row, UNSUPPORTED_DOMAIN, UNSUPPORTED_PROBLEM)
    )

    # Then: no frame candidate can be scheduled from unsupported semantics.
    assert not projection.candidates
    assert [item.reason for item in projection.exclusions] == ["unsupported_pddl_features:negative_preconditions_requirement"]


def test_projects_only_validated_graphplan_extracted_plan_replay_states() -> None:
    # Given: a Graphplan planning graph and its selected extracted plan.
    source_row = _case("graphplan_extracted_plan")["source_row"]

    # When: Graphplan semantics and concrete replay candidates are projected.
    events = project_traversal_events(_identity(source_row), source_row)
    projection = _project(source_row)

    # Then: layers remain nonvisual and only PDDL-validated replay states become candidates.
    assert all(event.supervision_mode == "planner_semantics" for event in events)
    assert all("state_atoms" not in event.to_record() for event in events)
    assert all("state_asset_hash" not in event.to_record() for event in events)
    assert [candidate.state_source for candidate in projection.candidates] == [
        "extracted_plan_replay",
        "extracted_plan_replay",
    ]
    extraction_event = next(event for event in events if event.event_kind == "extraction")
    assert all(candidate.extraction_event_id == extraction_event.node_id for candidate in projection.candidates)
    assert projection.candidates[1].parent_event_id == projection.candidates[0].event_id
    assert projection.candidates[1].normalized_action == "(move a b)"
    assert projection.candidates[1].state_atoms[0] == "(at b)"


def test_excludes_invalid_graphplan_extraction_actions_without_frame_candidates() -> None:
    # Given: Graphplan extractions with unknown and inapplicable selected actions.
    unknown = _case("graphplan_extracted_plan")["source_row"]
    unknown["supervised_target"]["planner_trace"]["extraction"]["selected_plan"] = ["(fly a b)"]
    inapplicable = _case("graphplan_extracted_plan")["source_row"]
    inapplicable["supervised_target"]["planner_trace"]["extraction"]["selected_plan"] = ["(move b a)"]

    # When: the complete extracted plans are replayed against PDDL semantics.
    unknown_projection = _project(unknown)
    inapplicable_projection = _project(inapplicable)

    # Then: neither invalid extraction creates a concrete render candidate.
    assert not unknown_projection.candidates
    assert not inapplicable_projection.candidates
    assert "unknown_extraction_action" in [item.reason for item in unknown_projection.exclusions]
    assert "inapplicable_extraction_action" in [item.reason for item in inapplicable_projection.exclusions]


def test_excludes_malformed_graphplan_extraction_without_frame_candidates() -> None:
    # Given: a Graphplan extraction whose selected plan is not an action array.
    source_row = _case("graphplan_extracted_plan")["source_row"]
    source_row["supervised_target"]["planner_trace"]["extraction"]["selected_plan"] = "(move a b)"

    # When: the traversal boundary parses the malformed extraction.
    projection = _project(source_row)

    # Then: it emits an inspectable exclusion and no frame candidate.
    assert not projection.candidates
    assert [item.reason for item in projection.exclusions] == ["invalid_field_type: selected_plan: array"]


def _project(source_row: dict[str, Any]):
    return project_traversal_state_candidates(
        TraversalProjectionInput(
            source_identity=_identity(source_row),
            source_row=source_row,
            domain_path=DOMAIN,
            problem_path=PROBLEM,
        )
    )


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
