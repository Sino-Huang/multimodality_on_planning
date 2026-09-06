from __future__ import annotations

import json
import types

import pytest
from PIL import Image

from examples.planning_benchmark_slice.modality_phase import ROOT
from examples.planning_benchmark_slice.pddl_state import GroundedAction, PDDLStateAuthority
from examples.planning_benchmark_slice.scene_assets import (
    build_scene_catalog,
    catalog_paths,
    collect_task_scenes,
    require_resolved_scene_coordinates,
    typed_puzzle_profile,
)
from scripts.collect_modality_scene_assets import main

DOMAIN = """(define (domain branches) (:requirements :strips)
(:predicates (at ?x) (link ?x ?y))
(:action move :parameters (?x ?y) :precondition (and (at ?x) (link ?x ?y))
 :effect (and (not (at ?x)) (at ?y))))"""
PROBLEM = """(define (problem branching) (:domain branches) (:objects x y z)
(:init (at x) (link x y) (link x z)) (:goal (at y)))"""


def trace():
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    initial = authority.initial_state
    records = []
    for destination in ("y", "z"):
        action = GroundedAction("move", ("x", destination))
        successor = authority.apply(initial, action).target_state
        records.append(
            {
                "observation": {"state_atoms": list(initial.atoms)},
                "operation": {"action": {"name": action.name, "args": list(action.args)}},
                "result": {
                    "transition": {
                        "source_state": {"atoms": list(initial.atoms)},
                        "target_state": {"atoms": list(successor.atoms)},
                    }
                },
            }
        )
    return {"bfs": {"records": records}}


def test_catalog_covers_non_solution_branch_without_future_image_leakage():
    catalog = build_scene_catalog(DOMAIN, PROBLEM, trace())
    assert len(catalog["states"]) == 3
    assert {state["atoms"][0] for state in catalog["states"]} == {"at(x)", "at(y)", "at(z)"}
    assert [decision["state"] for decision in catalog["decisions"]] == [0, 0]
    assert [decision["successor"] for decision in catalog["decisions"]] == [1, 2]
    assert catalog_paths(catalog) == [([0, 1], ("(move x y)",)), ([0, 2], ("(move x z)",))]


def test_bad_recorded_successor_is_rejected_by_physical_replay():
    traces = trace()
    traces["bfs"]["records"][0]["result"]["transition"]["target_state"]["atoms"] = ["at(z)"]
    with pytest.raises(ValueError, match="successor differs"):
        build_scene_catalog(DOMAIN, PROBLEM, traces)


def test_negative_goal_formula_is_preserved_without_claiming_a_goal_image():
    problem = PROBLEM.replace("(:goal (at y))", "(:goal (not (at x)))")
    catalog = build_scene_catalog(DOMAIN, problem, trace())
    assert '"not"' in json.dumps(catalog["task_context"]["canonical_goal"])


def test_128px_collection_reuses_root_image_and_retains_semantic_bindings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "examples.planning_benchmark_slice.scene_assets.load_scene_task", lambda root, row: (DOMAIN, PROBLEM, trace())
    )
    profile = tmp_path / "profile.pddl"
    profile.write_text("(define (animation branches))")
    submitted = []

    def post(url, **kwargs):
        actions = kwargs["files"]["plan"][1].splitlines()
        submitted.append(actions)
        payload = {
            "visualStages": [
                {
                    "stageName": name,
                    "visualSprites": [
                        {"x": 0, "y": 0, "name": "node", "minX": 0.1, "maxX": 0.4, "minY": 0.2, "maxY": 0.6}
                    ],
                }
                for name in ["initial stage", *actions]
            ]
        }
        return types.SimpleNamespace(status_code=200, text=json.dumps(payload), json=lambda: payload)

    monkeypatch.setattr("scripts.planimation_phase1_client.requests.post", post)
    result = collect_task_scenes(
        root=tmp_path,
        row={
            "task_id": "task",
            "domain": "branches",
            "split": "train",
            "reference_costs": {"bfs": {"decisions": 2}},
            "trace_paths": {"bfs": "source.json"},
        },
        profile=profile,
        endpoint="http://127.0.0.1:18092",
        output=tmp_path / "result",
        timeout=30,
        preflight=False,
        progress=lambda event: None,
    )
    images = list((tmp_path / "result/frames").glob("*.png"))
    assert len(images) == 3
    for path in images:
        with Image.open(path) as image:
            assert image.size == (128, 128)
    assert submitted == [["(move x y)"], ["(move x z)"]]
    assert result["complete_state_coverage"] is True
    assert result["partial_goal_images_complete"] is False
    assert not list((tmp_path / "result").glob("render-path-*"))


def test_unresolved_backend_coordinates_are_not_a_valid_scene():
    with pytest.raises(RuntimeError, match="unresolved"):
        require_resolved_scene_coordinates([{"visualSprites": [{"x": False, "y": False, "name": "tile"}]}])
    require_resolved_scene_coordinates([{"visualSprites": [{"x": 0, "y": 0, "name": "tile"}]}])


def test_typed_puzzle_profile_requires_real_neighbor_geometry():
    root = ROOT / "data/bfs_pilot_v6/tasks/15puzzle/dev/easy"
    authority = PDDLStateAuthority.from_pddl((root / "domain.pddl").read_text(), (root / "problem.pddl").read_text())
    context = authority.task_context()
    profile = typed_puzzle_profile(context)
    assert ":objects (p_1_1)" in profile
    assert "(:predicate at" in profile
    context["static_initial_facts"] = [
        fact for fact in authority.static_initial_facts if not fact.startswith("neighbor(")
    ]
    with pytest.raises(RuntimeError, match="neighbor graph"):
        typed_puzzle_profile(context)


@pytest.mark.parametrize("defect", ["gate", "authorization"])
def test_cli_rejects_stopped_or_unmatched_permission_before_task_reads(tmp_path, monkeypatch, defect):
    config = json.loads((ROOT / "configs/experiments/issue72/scenes128.json").read_text())
    if defect == "gate":
        config["attempts"]["preflight"]["gate_outcome"] = "INVALID"
    else:
        config["attempts"]["preflight"]["authorization_gate_id"] = "wrong-gate"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    monkeypatch.setattr(
        "scripts.collect_modality_scene_assets.load_modality_phase",
        lambda: pytest.fail("source phase read without permission"),
    )
    assert main(["--dry-run", "--config", str(path)]) == 1
