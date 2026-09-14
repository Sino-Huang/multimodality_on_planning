"""New initial states preserve source goals and replay their generating paths."""

import pytest

from examples.planning_benchmark_slice.expanded_candidates import generate
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read
from examples.planning_benchmark_slice.pddl_state import GroundedAction, PDDLStateAuthority
from examples.planning_benchmark_slice.source_goal import source_task


@pytest.mark.parametrize("domain", ["15puzzle", "gripper", "towers_of_hanoi"])
def test_seeded_walk_replays_without_goal_or_static_changes(tmp_path, domain):
    protocol = read(ROOT / "configs/experiments/expanded-study/panel-protocol.json")
    profile = next(p for p in protocol["strata"] if p["domain"] == domain)
    task = generate(ROOT, profile, profile["seeds"][0], tmp_path / "generator")
    walk = task["initial_walk"]
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], walk["origin_problem_pddl"])
    state = authority.initial_state
    for serialized in walk["actions"]:
        words = serialized.strip("()").split()
        state = authority.apply(state, GroundedAction(words[0], tuple(words[1:]))).target_state
    final = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    assert final.initial_state.atoms == state.atoms
    assert final.initial_state.fluents == state.fluents
    assert final.static_initial_facts == authority.static_initial_facts
    assert source_task(task["domain_pddl"], task["problem_pddl"]) == source_task(
        task["domain_pddl"], walk["origin_problem_pddl"]
    )
    assert len(walk["actions"]) == profile["walk_steps"]


def test_reference_screen_preserves_four_algorithms_and_cached_candidate(tmp_path, monkeypatch):
    from examples.planning_benchmark_slice import expanded_candidates as candidates

    task = read(ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json")
    monkeypatch.setattr(candidates, "generate", lambda *args: task)
    protocol = read(ROOT / "configs/experiments/expanded-study/panel-protocol.json")
    protocol["output_root"] = "panel"
    profile = next(p for p in protocol["strata"] if p["domain"] == "blocksworld")
    result = candidates.screen(tmp_path, protocol, profile, 1, set())
    assert result["reference_eligible"], result["reason"]
    assert set(result["row"]["reference_costs"]) == set(protocol["reference"]["algorithms"])
    assert not result["final_selected"]
    assert candidates.screen(tmp_path, protocol, profile, 1, set()) == result
    overlap = {candidates.task_semantics(task["domain_pddl"], task["problem_pddl"])}
    assert candidates.screen(tmp_path, protocol, profile, 2, overlap)["reason"] == "historical_task_overlap"


def test_type_pruned_count_matches_actual_additive_operator_construction():
    from examples.planning_benchmark_slice.expanded_candidates import typed_grounding_count
    from examples.planning_benchmark_slice.strips_relaxation import extract_grounded_positive_strips

    task = read(ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json")
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    actual = extract_grounded_positive_strips(authority, prune_type_impossible_groundings=True)
    assert typed_grounding_count(authority) == len(actual.operators)


def test_reference_catalog_preserves_producing_operation_paths(tmp_path, monkeypatch):
    from examples.planning_benchmark_slice import expanded_candidates as candidates
    from examples.planning_benchmark_slice.expanded_views import reference_catalog

    task = read(ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json")
    monkeypatch.setattr(candidates, "generate", lambda *args: task)
    protocol = read(ROOT / "configs/experiments/expanded-study/panel-protocol.json")
    protocol["output_root"] = "panel"
    profile = next(p for p in protocol["strata"] if p["domain"] == "blocksworld")
    result = candidates.screen(tmp_path, protocol, profile, 1, set())
    paths = {
        a: f"panel/candidates/blocksworld-compact-1/reference-{a}.json.gz" for a in protocol["reference"]["algorithms"]
    }
    catalog = reference_catalog(tmp_path, result["row"], paths, protocol["study_id"])
    assert len(catalog["decisions"]) == sum(c["decisions"] for c in result["row"]["reference_costs"].values())
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    states = [authority.canonical_state(tuple(s["atoms"]), tuple(s["fluents"])) for s in catalog["states"]]
    for index, state in enumerate(catalog["states"][1:], 1):
        parent = state["parent"]
        words = parent["action"].strip("()").split()
        assert (
            authority.apply(states[parent["state"]], GroundedAction(words[0], tuple(words[1:]))).target_state
            == states[index]
        )
