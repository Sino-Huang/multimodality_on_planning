"""CPU-only design and semantic-audit tests for Goal 11 Phase 1."""

import base64
import copy
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from examples.planning_benchmark_slice.expanded_generalization import (
    LOSSY,
    SEMANTICS_PRESERVING,
    audit_perturbation,
    classify_information_availability,
    derive_perturbed_task,
    derive_shifted_initial,
    load_protocol,
    materialize_variant_profiles,
    materialize_view_manifest,
    rename_task_asset,
    scale_up_arguments,
    semantically_disjoint,
    snapshot_arguments,
    validate_protocol,
    view_information,
)
from examples.planning_benchmark_slice.expanded_views import ExpandedTaskViews, render_unlabelled_vfg
from examples.planning_benchmark_slice.matched_tasks import task_semantics
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.task_isomorphism import same_instance
from examples.planning_benchmark_slice.visual_episode import VisualTaskViews

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "configs/experiments/expanded-study/generalization-robustness-protocol.json"

DOMAIN = """(define (domain tiny)
(:requirements :strips :typing)
(:types place item)
(:predicates (at ?x - item ?p - place) (linked ?a ?b - place))
(:action move :parameters (?x - item ?a ?b - place)
 :precondition (and (at ?x ?a) (linked ?a ?b))
 :effect (and (at ?x ?b) (not (at ?x ?a)))))"""
PROBLEM = """(define (problem tiny-p) (:domain tiny)
(:objects box - item home away - place)
(:init (at box home) (linked home away) (linked away home))
(:goal (at box away)))"""


def task():
    return {
        "domain_pddl": DOMAIN,
        "problem_pddl": PROBLEM,
        "authority_transformations": [],
        "generator_command": ["synthetic"],
        "text_pages": {
            "state": {
                "object_identities": ["box", "home", "away"],
                "object_types": {"box": "item", "home": "place", "away": "place"},
                "type_inventory": ["item", "place"],
                "atoms": ["at(box,home)", "linked(home,away)", "linked(away,home)"],
                "fluents": [],
                "description": "Types: box - item; home - place; away - place",
            }
        },
        "scene_bindings": {"box": {"location": "home"}},
    }


def visual_payload(names=("box", "home", "away"), *, injective_types=True, identical_prefab_bytes=False):
    def icon(color):
        image = Image.new("RGBA", (2, 2), color)
        stream = BytesIO()
        image.save(stream, format="PNG")
        return base64.b64encode(stream.getvalue()).decode()

    colors = {
        name: (
            {"r": 0.65, "g": 0.65, "b": 0.65, "a": 1.0}
            if identical_prefab_bytes
            else {"r": 0.9, "g": 0.1, "b": 0.1, "a": 1.0}
            if injective_types and (name == "box" or name.startswith("o0002"))
            else {"r": 0.1, "g": 0.3, "b": 0.9, "a": 1.0}
            if injective_types
            else {"r": 0.65, "g": 0.65, "b": 0.65, "a": 1.0}
        )
        for name in names
    }
    icon_ids = {
        name: "item-icon" if name == "box" or name.startswith("o0002") else "place-icon"
        for name in names
    }
    return {
        "visualStages": [
            {
                "visualSprites": [
                    {
                        "name": name,
                        "minX": 0.1 + index * 0.3,
                        "maxX": 0.3 + index * 0.3,
                        "minY": 0.3,
                        "maxY": 0.5,
                        "color": colors[name],
                        **({"prefabImage": icon_ids[name]} if injective_types else {}),
                    }
                    for index, name in enumerate(names)
                ]
            }
        ],
        "imageTable": (
            {
                "m_keys": ["item-icon", "place-icon"],
                "m_values": (
                    [icon((255, 0, 0, 255))] * 2
                    if identical_prefab_bytes
                    else [icon((255, 0, 0, 255)), icon((0, 0, 255, 255))]
                ),
            }
            if injective_types
            else {"m_keys": [], "m_values": []}
        ),
    }


def add_inline_visual_assets(value, *, injective_types=True, identical_prefab_bytes=False):
    value = copy.deepcopy(value)
    authority = PDDLStateAuthority.from_pddl(value["domain_pddl"], value["problem_pddl"])
    names = tuple(authority.objects)
    kinds = {"item": ["box"], "place": ["home", "away"]}
    value["view_manifest"] = {
        "scene_catalog": {
            "path_bindings": [
                {
                    "vfg": visual_payload(
                        names,
                        injective_types=injective_types,
                        identical_prefab_bytes=identical_prefab_bytes,
                    )
                }
            ],
            "states": [{"index": 0, "atoms": [], "fluents": [], "parent": None}],
        },
        "source": {"objects_by_type": kinds},
    }
    return value


def test_object_renaming_round_trip_preserves_isomorphism_and_reference_semantics():
    source = task()
    renamed, semantic_map = derive_perturbed_task(source, "object-renaming", 950123)
    source_authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    renamed_authority = PDDLStateAuthority.from_pddl(renamed["domain_pddl"], renamed["problem_pddl"])
    assert same_instance(source_authority.task_context(), renamed_authority.task_context())
    costs = {"bfs": {"decisions": 1, "expansions": 1}}
    audit = audit_perturbation(
        source,
        renamed,
        "object-renaming",
        semantic_map,
        "text-state",
        source_reference_costs=costs,
        perturbed_reference_costs=costs,
    )
    assert audit["same_instance"] is True
    assert audit["reference_costs_match"] is True
    round_trip = rename_task_asset(renamed, semantic_map["perturbed_to_source"])
    assert task_semantics(round_trip["domain_pddl"], round_trip["problem_pddl"]) == task_semantics(DOMAIN, PROBLEM)


def test_semantic_map_is_complete_for_every_source_object():
    source = task()
    renamed, semantic_map = derive_perturbed_task(source, "object-renaming", 950321)
    objects = set(PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM).objects)
    assert set(semantic_map["source_to_perturbed"]) == objects
    assert set(semantic_map["perturbed_to_source"].values()) == objects
    assert len(set(semantic_map["source_to_perturbed"].values())) == len(objects)
    assert "box" not in renamed["problem_pddl"]
    assert "box" not in renamed["scene_bindings"]


def test_shifted_initial_materializes_replayable_distinct_walk_evidence():
    source = task()
    shifted, audit = derive_shifted_initial(
        source,
        source,
        {"domain": "tiny", "seed": 940999, "walk_origin": "initial", "walk_steps": 1},
    )
    assert shifted["initial_walk"]["actions"] == audit["walk"]["actions"]
    assert audit["replayable_walk_retained"] is True
    assert audit["goal_static_identity_unchanged"] is True
    assert audit["walked_initial_distinct_from_generated_origin"] is True
    assert audit["walked_initial_distinct_from_source"] is True


def test_name_compression_materializes_strip_and_classifies_per_modality(tmp_path):
    source = add_inline_visual_assets(task())
    compressed, semantic_map = derive_perturbed_task(source, "name-compression", 950777)
    page = compressed["text_pages"]["state"]
    assert "object_types" not in page
    assert "type_inventory" not in page
    assert " - item" not in page["description"]
    source_info = view_information(source, "text-state")
    text_info = view_information(compressed, "text-state")
    text = classify_information_availability(
        "name-compression", source_info, text_info, semantic_map, "text-state"
    )
    source_vfg = source["view_manifest"]["scene_catalog"]["path_bindings"][0]["vfg"]
    compressed_vfg = compressed["view_manifest"]["scene_catalog"]["path_bindings"][0]["vfg"]
    render_unlabelled_vfg(
        json.dumps(source_vfg).encode(),
        tmp_path / "source-visual",
        0,
        source_info["object_identities"],
    )
    render_unlabelled_vfg(
        json.dumps(compressed_vfg).encode(),
        tmp_path / "compressed-visual",
        0,
        view_information(compressed, "visual-state")["object_identities"],
    )
    assert (tmp_path / "source-visual/frame_000.png").is_file()
    assert (tmp_path / "compressed-visual/frame_000.png").is_file()
    visual = audit_perturbation(source, compressed, "name-compression", semantic_map, "visual-state")[
        "information_availability"
    ]
    multimodal = audit_perturbation(source, compressed, "name-compression", semantic_map, "multimodal-state")[
        "information_availability"
    ]
    assert text["classification"] == LOSSY
    assert any(item.startswith("object_types:") for item in text["missing_information"])
    assert visual["classification"] == multimodal["classification"] == SEMANTICS_PRESERVING
    assert multimodal["visual_type_contribution_classification"] == SEMANTICS_PRESERVING


def test_visual_type_recovery_is_lossy_when_item_and_place_share_one_rectangle_style():
    source = add_inline_visual_assets(task(), injective_types=False)
    renamed, semantic_map = derive_perturbed_task(source, "object-renaming", 950778)
    source_visual = view_information(source, "visual-state")
    assert source_visual["type_style_injective"] is False
    assert source_visual["object_types"] == {}
    audit = audit_perturbation(source, renamed, "object-renaming", semantic_map, "visual-state")
    assert audit["expected_classification_prior"] == SEMANTICS_PRESERVING
    assert audit["measured_classification"] == LOSSY
    assert all(
        style[0] == "shape:rectangle"
        for styles in source_visual["rendered_type_styles"].values()
        for style in styles
    )
    assert any(item.startswith("object_types:") for item in audit["information_availability"]["missing_information"])


def test_visual_type_recovery_is_preserving_for_injective_rendered_styles():
    source = add_inline_visual_assets(task(), injective_types=True)
    renamed, semantic_map = derive_perturbed_task(source, "object-renaming", 950779)
    source_visual = view_information(source, "visual-state")
    assert source_visual["type_style_injective"] is True
    assert source_visual["object_types"] == {"away": "place", "box": "item", "home": "place"}
    image_styles = {style[0] for styles in source_visual["rendered_type_styles"].values() for style in styles}
    assert len(image_styles) == 2
    assert all(style.startswith("prefab-sha256:") for style in image_styles)
    audit = audit_perturbation(source, renamed, "object-renaming", semantic_map, "visual-state")
    assert audit["measured_classification"] == SEMANTICS_PRESERVING


def test_distinct_prefab_ids_with_identical_rendered_content_are_not_injective():
    source = add_inline_visual_assets(task(), injective_types=True, identical_prefab_bytes=True)
    renamed, semantic_map = derive_perturbed_task(source, "object-renaming", 950780)
    source_visual = view_information(source, "visual-state")
    assert source_visual["type_style_injective"] is False
    assert source_visual["object_types"] == {}
    styles = {style[0] for rows in source_visual["rendered_type_styles"].values() for style in rows}
    assert len(styles) == 1
    assert next(iter(styles)).startswith("prefab-sha256:")
    visual = audit_perturbation(source, renamed, "object-renaming", semantic_map, "visual-state")
    multimodal = audit_perturbation(source, renamed, "object-renaming", semantic_map, "multimodal-state")
    assert visual["measured_classification"] == LOSSY
    assert visual["information_availability"]["classification"] == LOSSY
    assert multimodal["information_availability"]["visual_type_contribution_classification"] == LOSSY


def test_invalid_prefab_payloads_fail_closed_to_shared_rectangle_style():
    source = add_inline_visual_assets(task(), injective_types=True, identical_prefab_bytes=True)
    payload = source["view_manifest"]["scene_catalog"]["path_bindings"][0]["vfg"]
    payload["imageTable"]["m_values"] = ["not-base64", "also-not-base64"]
    source_visual = view_information(source, "visual-state")
    assert source_visual["type_style_injective"] is False
    assert source_visual["object_types"] == {}
    assert {
        style[0] for rows in source_visual["rendered_type_styles"].values() for style in rows
    } == {"shape:rectangle"}


def test_render_override_manifest_bridges_through_expanded_task_views(tmp_path, monkeypatch):
    source = task()
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    vfg = tmp_path / "scene.vfg.json"
    vfg.write_text(json.dumps(visual_payload()))
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "task_context": authority.task_context(),
                "path_bindings": [{"vfg": vfg.name}],
                "states": [
                    {
                        "index": 0,
                        "atoms": list(authority.initial_state.atoms),
                        "fluents": list(authority.initial_state.fluents),
                        "parent": None,
                    }
                ],
            }
        )
    )
    source_task_path = tmp_path / "task.json"
    source_task_path.write_text(json.dumps({"domain_pddl": DOMAIN, "problem_pddl": PROBLEM}))
    source_manifest_path = tmp_path / "source-manifest.json"
    source_manifest_path.write_text("{}")
    source["asset_root"] = str(tmp_path)
    source["view_manifest"] = {
        "scene_catalog": catalog.name,
        "source": {"objects_by_type": {"item": ["box"], "place": ["home", "away"]}},
    }
    derived, _semantic_map = derive_perturbed_task(source, "render-restyle", 950001)
    assert materialize_view_manifest(derived)["render_overrides"] == derived["view_manifest"]["render_overrides"]

    monkeypatch.setattr(VisualTaskViews, "_render", lambda self, index: None)

    def render(bound_task, name):
        output = tmp_path / name
        output.mkdir()
        evaluation_task = {
            **bound_task,
            "row": {"task_id": "tiny", "task_path": source_task_path.name},
            "native_views": {
                "view_id": "tiny-view",
                "source_manifest": source_manifest_path.name,
                "static_pages": [],
                "goal_pages": [],
                "scenes": {},
                "scene_bindings": {},
            },
        }
        views = ExpandedTaskViews(tmp_path, evaluation_task, output, "unused")
        views.states[0].update(vfg=vfg.name, scene_path=f"{name}.png")
        views._render(0)
        return (tmp_path / f"{name}.png").read_bytes()

    source_bytes = render(source, "source")
    first = render(derived, "derived-a")
    second = render(derived, "derived-b")
    assert first != source_bytes
    assert first == second
    assert view_information(source, "visual-state") == view_information(derived, "visual-state")
    with Image.open(tmp_path / "derived-a.png") as image:
        assert image.size == (160, 160)


def test_protocol_all_rows_v2_rules_deltas_seeds_and_matrix_are_consistent():
    protocol = json.loads(PROTOCOL.read_text())
    panel = json.loads((ROOT / protocol["panel"]).read_text())
    panel_by_id = {item["row"]["task_id"]: item["row"] for item in panel["tasks"]}
    profiles = materialize_variant_profiles(protocol)
    assert len(protocol["source_problems"]) == 24
    assert len(profiles["structural"]) == 48
    assert len(profiles["perturbations"]) == 72
    for row in protocol["source_problems"]:
        domain = row["domain"]
        compact = json.loads((ROOT / row["compact_snapshot"]).read_text())
        expanded = json.loads((ROOT / row["expanded_snapshot"]).read_text())
        compact_arguments = snapshot_arguments(compact, domain)
        expanded_arguments = snapshot_arguments(expanded, domain)
        assert row["compact_arguments"] == compact_arguments
        assert row["expanded_arguments"] == expanded_arguments
        assert row["structural_variants"]["scale-up"]["arguments"] == scale_up_arguments(
            compact_arguments, expanded_arguments
        )
        shifted = row["structural_variants"]["shifted-init"]
        assert shifted["walk_steps"] == panel_by_id[row["task_id"]]["reference_costs"]["bfs"]["decisions"] > 0
        assert shifted["walk_origin"] == ("goal" if domain == "15puzzle" else "initial")
        assert shifted["arguments"] == expanded_arguments
        assert set(shifted["audit_requirements"]) == {
            "replayable_walk_retained",
            "goal_static_identity_unchanged",
            "walked_initial_distinct_from_generated_origin",
            "walked_initial_distinct_from_source",
        }
    evaluation = protocol["evaluation"]
    assert evaluation["random_valid_rollout_seeds"] == [17, 1013, 2027, 3041, 4001]
    assert evaluation["gpu_model_episodes_per_task"] == 24
    assert evaluation["cpu_control_episodes_per_task"] == 72
    assert evaluation["gpu_model_episodes_full"] == 2880
    assert evaluation["cpu_control_episodes_full"] == 8640
    assert evaluation["logical_bindings_full"] == 11520
    probe = protocol["throughput_probe"]
    assert probe["probe_inputs"] == 60
    assert probe["timing_samples_per_probe_input"] == 3
    assert probe["timing_calls"] == 180
    assert probe["call_time_margin"] == 1.5


def _set_path(value, path, replacement):
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("status",), "draft"),
        (("program_id",), "wrong"),
        (("issues",), []),
        (("parent_issue",), 0),
        (("panel",), "wrong.json"),
        (("panel_protocol",), "wrong.json"),
        (("checkpoint_readiness",), "wrong.json"),
        (("checkpoint_protocol",), "wrong.json"),
        (("schedule",), "wrong.json"),
        (("source_problems_expected",), 23),
        (("domains_expected",), 11),
        (("output_root",), "arbitrary"),
        (("new_training",), True),
        (("training_seed",), 18),
        (("training_seed_variance_claimed",), True),
        (("phase1_execution",), False),
        (("model_revision",), "wrong"),
        (("fixed_adapters", 0, "adapter_model_sha256"), "sha256:" + "0" * 64),
        (("source_problems", 0, "structural_variants", "scale-up", "arguments"), ["wrong"]),
        (("source_problems", 0, "structural_variants", "shifted-init", "seed"), 930000),
        (("structural_variant_families", "scale-up", "id"), "wrong"),
        (("perturbation_families", "render-restyle", "id"), "wrong"),
        (("perturbation_families", "render-restyle", "transform"), "metadata only"),
        (("eligibility", "max_input_tokens_per_call"), 8192),
        (("evaluation", "rollouts", "random_valid"), 1),
        (("evaluation", "logical_bindings_full"), 1),
        (("inference", "dtype"), "bfloat16"),
        (("execution_contract", "deterministic_rounds"), False),
        (("throughput_probe", "kind"), "episode probe"),
        (("throughput_probe", "persist"), ["call_wall_seconds", "outcome"]),
        (("admission", "fallback_ladder"), ["L0 only"]),
        (("analysis", "bootstrap", "seed"), 1),
        (("analysis", "bootstrap", "resamples"), 100),
        (("analysis", "paired_unit"), "episode"),
        (("analysis", "lossy_pooling"), "pooled"),
    ],
)
def test_validate_protocol_rejects_each_load_bearing_mutation(path, replacement):
    protocol = json.loads(PROTOCOL.read_text())
    _set_path(protocol, path, replacement)
    with pytest.raises(ValueError):
        validate_protocol(ROOT, protocol)


def test_validate_protocol_passes_and_rejects_material_tampering():
    protocol = json.loads(PROTOCOL.read_text())
    validate_protocol(ROOT, protocol)
    assert load_protocol(ROOT) == protocol


def test_isomorphic_disjointness_rejects_renamed_duplicate_except_own_perturbation_source():
    source = task()
    renamed, _ = derive_perturbed_task(source, "object-renaming", 950555)
    known = [{"task_id": "source", **source}]
    assert semantically_disjoint(renamed, known, candidate_kind="structural") is False
    assert semantically_disjoint(
        renamed, known, candidate_kind="perturbation", source_task_id="source"
    ) is True
