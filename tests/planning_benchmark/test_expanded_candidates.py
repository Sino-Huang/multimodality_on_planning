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


def test_live_view_restore_replays_reference_states_into_authority(tmp_path, monkeypatch):
    from examples.planning_benchmark_slice import expanded_candidates as candidates
    from examples.planning_benchmark_slice.expanded_scheduler import write
    from examples.planning_benchmark_slice.expanded_views import ExpandedTaskViews, reference_catalog

    task = read(ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json")
    monkeypatch.setattr(candidates, "generate", lambda *args: task)
    protocol = read(ROOT / "configs/experiments/expanded-study/panel-protocol.json")
    protocol["output_root"] = "panel"
    profile = next(p for p in protocol["strata"] if p["domain"] == "blocksworld")
    result = candidates.screen(tmp_path, protocol, profile, 1, set())
    refs = {
        a: f"panel/candidates/blocksworld-compact-1/reference-{a}.json.gz" for a in protocol["reference"]["algorithms"]
    }
    catalog = reference_catalog(tmp_path, result["row"], refs, protocol["study_id"])
    write(tmp_path / "catalog.json", catalog)
    write(tmp_path / "manifest.json", {"scene_catalog": "catalog.json"})
    prepared = {
        "row": result["row"],
        "native_views": {"view_id": "fixture", "source_manifest": "manifest.json", "scenes": {}, "scene_bindings": {}},
    }
    views = ExpandedTaskViews(tmp_path, prepared, tmp_path / "live", "http://127.0.0.1:18092")
    views.save()
    restored = ExpandedTaskViews(tmp_path, prepared, tmp_path / "live", "http://127.0.0.1:18092", read_only=True)
    assert len(restored.states) > 1
    for entry in restored.states:
        state = restored.authority.canonical_state(tuple(entry["atoms"]), tuple(entry["fluents"]))
        assert isinstance(restored.authority.is_goal(state), bool)


def test_distinct_episodes_cannot_share_a_new_state_image_cache(tmp_path, monkeypatch):
    from PIL import Image

    from examples.planning_benchmark_slice.expanded_scheduler import write
    from examples.planning_benchmark_slice.expanded_views import ExpandedTaskViews

    source = read(ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json")
    write(tmp_path / "task.json", source)
    authority = PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"])
    initial = authority.initial_state
    write(
        tmp_path / "catalog.json",
        {
            "task_context": authority.task_context(),
            "states": [
                {
                    "index": 0,
                    "atoms": list(initial.atoms),
                    "fluents": list(initial.fluents),
                    "parent": None,
                    "scene_path": "initial.png",
                }
            ],
        },
    )
    write(tmp_path / "manifest.json", {"scene_catalog": "catalog.json"})
    Image.new("RGB", (128, 128), "white").save(tmp_path / "initial.png")
    task = {
        "row": {"task_id": "same-task", "task_path": "task.json"},
        "native_views": {
            "view_id": "shared-reference",
            "source_manifest": "manifest.json",
            "static_pages": [],
            "goal_pages": [],
            "scenes": {"0": "initial.png"},
            "scene_bindings": {},
        },
    }

    def render(views, index):
        views.output.mkdir(parents=True)
        path = views.output / "new.png"
        colour = "red" if views.output.name == "episode-a" else "blue"
        Image.new("RGB", (128, 128), colour).save(path)
        views.states[index].update(scene_path=str(path.relative_to(tmp_path)), vfg="unused-test-vector.json")
        views._bind_native(index)

    monkeypatch.setattr(ExpandedTaskViews, "_render", render)
    actions = authority.applicable_actions(initial)
    assert len(actions) >= 2
    observed = []
    for number, name in enumerate(("episode-a", "episode-b")):
        views = ExpandedTaskViews(tmp_path, task, tmp_path / name, "http://127.0.0.1:18092")
        action = actions[number]
        index = views.register(views.authority.initial_state, {"name": action.name, "args": list(action.args)})
        assert index == 1
        pages, _ = views.scene_views.pages("same-task", index)
        observed.append(pages[1][1].getpixel((0, 0)))
        for _, image in pages:
            image.close()
    assert observed == [(255, 0, 0), (0, 0, 255)]
