"""Real PDDL/controller checks for final candidate preparation, without model calls."""

import json

import pytest

from examples.planning_benchmark_slice.matched_tasks import (
    DEFAULT_STUDY,
    ROOT,
    candidate_adapter,
    enumerate_states,
    exact_reference,
    retained_tasks,
    task_semantics,
)
from examples.planning_benchmark_slice.pddl_state import GroundedAction, PDDLStateAuthority
from examples.planning_benchmark_slice.scene_assets import read_json
from examples.planning_benchmark_slice.visual_episode import replay_visual_episode
from src.data_collect.adapters.base import GenerationSpec


def fixture():
    return read_json(ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json")


@pytest.mark.parametrize("domain", ["storage", "blocksworld", "ferry"])
def test_generator_honors_frozen_arguments_and_seed(tmp_path, domain):
    profile = read_json(DEFAULT_STUDY)["final"]["candidate_profiles"][domain]
    adapter = candidate_adapter(ROOT, domain, profile["arguments"])
    seed = profile["seeds"][0]
    raw = adapter.generate_candidate(GenerationSpec(domain, tmp_path, 30, seed, {"preset_id": "matched-final"}))
    assert raw.exit_code == 0
    assert list(raw.command[1 : 1 + len(profile["arguments"])]) == profile["arguments"]
    assert str(seed) in raw.command


def test_complete_closure_includes_off_teacher_paths_and_parent_paths_replay():
    task = fixture()
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    catalog = enumerate_states(authority, 256)
    states = [authority.canonical_state(tuple(r["atoms"]), tuple(r["fluents"])) for r in catalog["states"]]
    ids = {s.state_id for s in states}
    assert len(ids) == 22
    for i, row in enumerate(catalog["states"]):
        if row["parent"]:
            parent = row["parent"]
            words = parent["action"].strip("()").split()
            action = GroundedAction(words[0], tuple(words[1:]))
            assert authority.apply(states[parent["state"]], action).target_state == states[i]
        assert all(
            authority.apply(states[i], action).target_state.state_id in ids
            for action in authority.applicable_actions(states[i])
        )
    with pytest.raises(RuntimeError, match="reachable_state_ceiling"):
        enumerate_states(authority, 2)


@pytest.mark.parametrize("algorithm", ["bfs", "best_first_width", "best_first_add_w3", "best_first_add_greedy"])
def test_new_test_task_references_replay_without_relabelling_old_corpus(tmp_path, algorithm):
    task = fixture()
    (tmp_path / "task.json").write_text(json.dumps(task))
    study = read_json(DEFAULT_STUDY)
    row = {
        "task_id": "matched-final/blocksworld-fixture",
        "domain": "blocksworld",
        "difficulty": "bounded-final",
        "split": "test",
        "task_path": "task.json",
        "trace_paths": {},
        "reference_costs": {algorithm: {"decisions": 128, "expansions": 64}},
    }
    reference = exact_reference(tmp_path, row, algorithm, study)
    assert reference["result"]["invariant_valid_success"]
    assert reference["events"] and all(e["accepted"] for e in reference["events"])
    reference.update(algorithm=algorithm, arm="exact_reference", seed=17, output="out", contract_id=study["study_id"])
    assert replay_visual_episode(tmp_path, row, reference) == reference["result"]
    assert row["split"] == "test"


def test_historical_manifest_relative_paths_and_problem_name_do_not_bypass_overlap(tmp_path):
    task = fixture()
    folder = tmp_path / "data/old/pddl"
    folder.mkdir(parents=True)
    (folder / "d.pddl").write_text(task["domain_pddl"])
    (folder / "p.pddl").write_text(task["problem_pddl"])
    (folder.parent / "source-task-manifest.jsonl").write_text(
        json.dumps({"domain_id": "blocksworld", "domain_path": "pddl/d.pddl", "problem_path": "pddl/p.pddl"}) + "\n"
    )
    identities, sources = retained_tasks(tmp_path, {"blocksworld"})
    renamed = task["problem_pddl"].replace("bw-nontrivial-3", "supposedly-new-test")
    assert task_semantics(task["domain_pddl"], renamed) in identities
    assert sources[0]["problem_path"] == "data/old/pddl/p.pddl"
