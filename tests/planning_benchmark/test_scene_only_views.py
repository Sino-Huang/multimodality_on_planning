"""Scene-only input isolation, actual processor sizes and closed page bindings."""

import json

import pytest
from PIL import Image

from examples.planning_benchmark_slice.modality_pages import PAGE_SIZE, fact_blocks, project_messages
from examples.planning_benchmark_slice.modality_view_preparation import frozen_processor
from examples.planning_benchmark_slice.scene_only_views import (
    RECIPE_ID,
    REPRESENTATION,
    SCENE_SIZE,
    SceneOnlyViews,
    static_blocks,
)


def fixture_views(tmp_path):
    paths = {}
    for name, size, colour in (
        ("context", PAGE_SIZE, "white"),
        ("goal", PAGE_SIZE, "white"),
        ("initial", (SCENE_SIZE, SCENE_SIZE), "red"),
        ("current", (SCENE_SIZE, SCENE_SIZE), "blue"),
    ):
        path = tmp_path / f"{name}.png"
        with Image.new("RGB", size, colour) as image:
            image.save(path)
        paths[name] = path.name
    tasks = {
        "task": {
            "view_id": "native/task",
            "static_pages": [paths["context"]],
            "goal_pages": [paths["goal"]],
            "scenes": {"0": paths["initial"], "1": paths["current"]},
        }
    }
    return SceneOnlyViews(tmp_path, tasks)


def semantic():
    return fact_blocks(
        {
            "static_initial_facts": ["connected(a,b)"],
            "initial_dynamic_atoms": ["at(a)"],
            "initial_dynamic_fluents": ["fuel=9"],
        },
        {"atoms": ["at(b)"], "fluents": ["fuel=8"]},
        {"objects_by_type": {"object": ["a", "b"]}, "type_parents": {}, "source_goal": ["atom", "at", ["b"]]},
    )


def test_static_pages_never_print_initial_facts_or_fluents():
    blocks = static_blocks(semantic())
    assert "connected(a,b)" in json.dumps(blocks)
    assert "at(a)" not in json.dumps(blocks)
    assert "fuel=9" not in json.dumps(blocks)
    assert {b["id"].split(":")[0] for b in blocks} == {"objects", "static"}


def test_native_roles_bind_initial_and_current_without_successor(tmp_path):
    views = fixture_views(tmp_path)
    pages, bindings = views.pages("task", 1)
    assert [role for role, _ in pages] == ["task-context", "initial-state", "current-state", "goal"]
    assert bindings[1:3] == [["initial-state", 0, 0], ["current-state", 1, 0]]
    assert pages[1][1].getpixel((0, 0)) == (255, 0, 0)
    assert pages[2][1].getpixel((0, 0)) == (0, 0, 255)
    for _, image in pages:
        image.close()
    with pytest.raises(KeyError):
        views.pages("task", 2)
    assert views.cache.bytes <= 64 * 1024 * 1024


def test_actual_mixed_size_processor_and_unchanged_text(tmp_path):
    views = fixture_views(tmp_path)
    raw = {
        "observation": {"state_atoms": ["at(b)"], "state_id": "s1"},
        "task_context": {},
        "goal_atoms": ["at(b)"],
        "search_memory": {"successor_candidates": [{"grounded_action": {"name": "move", "args": ["a"]}}]},
    }
    blocks = semantic()
    text = views.observe("task", 1, raw, "bfs", blocks, "text-state")
    assert text["messages"] == project_messages(raw, "bfs", "text-state", blocks, [])
    visual = views.observe("task", 1, raw, "bfs", blocks, "visual-state")
    user_text = visual["messages"][-1]["content"][0]["text"]
    assert "at(a)" not in user_text and "at(b)" not in user_text and "fuel=8" not in user_text
    assert "successor_candidates" in user_text
    processor = frozen_processor()
    assert visual["binding"]["input_tokens"] > processor.count(visual["messages"])
    processor.verify_complete(visual["messages"], visual["images"])
    with pytest.raises(ValueError, match="marker"):
        processor.count(visual["messages"], image_sizes=[])
    for image in visual["images"]:
        image.close()


def test_ready_flags_cannot_hide_partial_record_coverage(tmp_path):
    (tmp_path / "membership.json").write_text(
        json.dumps({"training_record_ids": {"bfs": ["r0", "r1"]}, "diagnostic_record_ids": {"bfs": []}})
    )
    report = {
        "study": {"membership": "membership.json", "state_representation": REPRESENTATION},
        "outcome": "PASS",
        "model_input_ready": True,
        "complete_selected_coverage": True,
        "tasks": {"task": {"recipe_id": RECIPE_ID, "scenes": {"0": "missing.png"}}},
        "measurements": {"r0": {}},
        "decision_bindings": {"r0": {}},
        "counts": {"records": 2, "tasks": 1, "states": 1},
    }
    (tmp_path / "report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="coverage"):
        SceneOnlyViews.load(tmp_path, "report.json")


def test_saved_successor_binding_is_rejected_before_loading_images(tmp_path):
    views = fixture_views(tmp_path)
    views.tasks["task"]["source_manifest"] = "source.json"
    record = {
        "record_id": "r0",
        "task_id": "task",
        "view_manifest": "source.json",
        "state": 1,
        "algorithm": "bfs",
        "decision_index": 0,
        "split": "train",
    }
    views.decision_bindings["r0"] = {**record, "state": 2}
    with pytest.raises(ValueError, match="decision binding"):
        views.training_example(None, record, "visual-state")


def test_native_training_masks_every_image_token_and_matches_text_targets(tmp_path):
    from examples.planning_benchmark_slice.visual_model import VisualCollator

    views = fixture_views(tmp_path)
    raw = {
        "observation": {"state_atoms": ["at(b)"], "state_id": "s1"},
        "task_context": {},
        "goal_atoms": ["at(b)"],
        "search_memory": {},
    }
    target = {"role": "assistant", "content": '{"operation":"select","state_id":"s1"}'}
    supervised = []
    for modality in ("text-state", "visual-state", "multimodal-state"):
        example = views.observe("task", 1, raw, "bfs", semantic(), modality)
        example["messages"].append(target)
        batch = VisualCollator(frozen_processor().processor)([example])
        supervised.append(batch["labels"][batch["labels"] != -100].tolist())
        for image in example["images"]:
            image.close()
    assert supervised[0] == supervised[1] == supervised[2]
    assert 0 < len(supervised[0]) < 100
