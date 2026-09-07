import re
from typing import Any

import pytest

from examples.planning_benchmark_slice.modality_phase import ROOT
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.scene_assets import load_scene_task, read_json
from examples.planning_benchmark_slice.scene_profiles import grid_profile, require_grid_shape_icons, storage_profile


def context_for(domain) -> dict[str, Any]:
    rows = read_json(ROOT / "configs/experiments/issue71/v2/panel.json")["selected"]
    row = next(row for row in rows if row["domain"] == domain)
    domain_text, problem, _traces = load_scene_task(ROOT, row)
    return PDDLStateAuthority.from_pddl(domain_text, problem).task_context()


def objects(profile, visual):
    match = re.search(r"\(:visual\s+" + visual + r"\b.*?:objects\s*\(([^)]*)\)", profile, re.S)
    assert match is not None
    return match[1].split()


def test_storage_binds_the_actual_depot48_and_its_area():
    context = context_for("storage")
    profile = storage_profile(context, (ROOT / "data/pddl_instances/storage/ap.pddl").read_text())
    assert objects(profile, "depot") == ["depot48"]
    assert objects(profile, "depots") == ["depot48-1-1"]
    assert objects(profile, "containers") == ["container-0-0"]
    assert objects(profile, "hoist") == ["hoist0"]
    assert objects(profile, "loadarea") == ["loadarea"]


def test_storage_rejects_missing_containment_instead_of_inventing_positions():
    context = context_for("storage")
    context["initial_dynamic_atoms"] = [
        fact for fact in context["initial_dynamic_atoms"] if fact != "in(depot48-1-1,depot48)"
    ]
    with pytest.raises(RuntimeError, match="containing place"):
        storage_profile(context, (ROOT / "data/pddl_instances/storage/ap.pddl").read_text())


def test_grid_shape_categories_use_distinct_non_spatial_icon_templates():
    profile = grid_profile(context_for("grid"), (ROOT / "data/pddl_instances/grid/grid_AP.pddl").read_text())
    assert objects(profile, "circle") == ["shape0"]
    assert objects(profile, "square") == ["shape1"]
    assert objects(profile, "mapped-key-shape-1") == ["key1"]
    assert re.search(r"mapped-key-shape-1.*?prefabImage img-square", profile, re.S)
    assert objects(profile, "mapped-lock-shape-1") == ["pos1-2"]
    # The retained category declarations supply icons, not default node coordinates.
    for name in ("circle", "square"):
        block = re.search(r"\(:visual " + name + r"\b(.*?)(?=\(:visual)", profile, re.S)
        assert block is not None and "prefabImage" in block[1]
        assert "(x Null)" not in block[1] and "(y Null)" not in block[1]


def test_grid_does_not_silently_merge_excess_shape_categories():
    context = context_for("grid")
    context["static_initial_facts"].extend(["shape(shape2)", "shape(shape3)", "shape(shape4)"])
    with pytest.raises(RuntimeError, match="four distinct"):
        grid_profile(context, (ROOT / "data/pddl_instances/grid/grid_AP.pddl").read_text())


def test_grid_validation_rejects_resolved_but_wrong_icons():
    context = context_for("grid")
    sprites = [
        {"name": name, "prefabimage": icon}
        for name, icon in (
            ("key0", "img-circle"),
            ("key1", "img-square"),
            ("pos0-3", "img-circle"),
            ("pos1-2", "img-square"),
        )
    ]
    require_grid_shape_icons(context, [{"visualSprites": sprites}])
    sprites[1]["prefabimage"] = "img-circle"
    with pytest.raises(RuntimeError, match="declared shape for key1"):
        require_grid_shape_icons(context, [{"visualSprites": sprites}])
