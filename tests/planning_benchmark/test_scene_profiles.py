import re
from typing import Any

import pytest

from examples.planning_benchmark_slice.modality_phase import ROOT
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.scene_assets import load_scene_task, read_json
from examples.planning_benchmark_slice.scene_profiles import grid_profile, require_grid_shape_icons, storage_profile


def test_freecell_render_domain_tracks_covered_home_without_changing_planning_state():
    from examples.planning_benchmark_slice.pddl_state import GroundedAction
    from examples.planning_benchmark_slice.scene_profiles import freecell_renderer_domain

    row = next(
        row
        for row in read_json(ROOT / "configs/experiments/issue71/v2/panel.json")["selected"]
        if row["task_id"] == "best_first_width/freecell-train-easy-0053"
    )
    domain, problem, _ = load_scene_task(ROOT, row)
    original = PDDLStateAuthority.from_pddl(domain, problem)
    rendered = PDDLStateAuthority.from_pddl(freecell_renderer_domain(domain), problem)
    a, b = original.initial_state, rendered.initial_state
    actions = [
        "sendtofree ha c2 celln4 celln3",
        "sendtofree c2 s2 celln3 celln2",
        "sendtofree s2 s3 celln2 celln1",
        "sendtofree s3 da celln1 celln0",
        "sendtohome da d2 d n1 d0 n0",
        "sendtohome-b d2 d n2 da n1 coln2 coln3",
    ]
    for text in actions:
        name, *args = text.split()
        action = GroundedAction(name, tuple(args))
        a = original.apply(a, action).target_state
        b = rendered.apply(b, action).target_state
        assert set(a.atoms) == {atom for atom in b.atoms if not atom.startswith("coveredhome(")}
    assert "coveredhome(da)" in b.atoms and "home(d2)" in b.atoms
    assert "home(da)" not in b.atoms


def test_renderer_variable_names_do_not_overlap():
    from examples.planning_benchmark_slice.scene_profiles import renderer_domain

    domain = "(at ?ply ?ply-from) (at ?blk ?blk-to) (at ?ply ?ply-to)"
    renamed = renderer_domain(domain)
    variables = set(re.findall(r"\?[\w-]+", renamed))
    assert len(variables) == 5
    assert not any(a != b and b.startswith(a) for a in variables for b in variables)
    assert renamed.split()[1] == renamed.split()[-2]


def test_sokoban_alpha_renaming_preserves_replayed_search_states():
    from examples.planning_benchmark_slice.scene_assets import build_scene_catalog
    from examples.planning_benchmark_slice.scene_profiles import renderer_domain

    rows = read_json(ROOT / "configs/experiments/issue71/v2/panel.json")["selected"]
    row = rows[217]
    assert row["domain"] == "sokoban"
    domain, problem, traces = load_scene_task(ROOT, row)
    original = build_scene_catalog(domain, problem, traces)
    renamed = build_scene_catalog(renderer_domain(domain), problem, traces)
    assert renamed["states"] == original["states"]
    assert renamed["decisions"] == original["decisions"]


def _board(row0, col0):
    sprites = [
        {"name": f"pos{row0 + r}_{col0 + c}", "x": (row0 + r) * 100, "y": (col0 + c) * 100, "width": 100, "height": 100}
        for r in range(5)
        for c in range(5)
    ]
    return {"visualStages": [{"visualSprites": sprites}], "imageTable": {}}


def test_sokoban_generator_names_are_reanchored_to_the_backend_cell_one_layout():
    from examples.planning_benchmark_slice.scene_profiles import compact_grid_vfg

    # The retained backend VFG of bfs/sokoban-train-easy-0000 (names pos1_1..pos5_5) places pos1_1 at
    # (0.188, 0.344, 0.188, 0.344); generator names pos571_61.. must land on the same cells.
    offset = compact_grid_vfg(_board(571, 61))["visualStages"][0]["visualSprites"]
    first = next(s for s in offset if s["name"] == "pos571_61")
    assert (first["minX"], first["maxX"], first["minY"], first["maxY"]) == (0.188, 0.344, 0.188, 0.344)
    last = next(s for s in offset if s["name"] == "pos575_65")
    assert (last["maxX"], last["maxY"]) == (0.969, 0.969)
    anchored = _board(1, 1)
    for sprite in anchored["visualStages"][0]["visualSprites"]:
        sprite.update(minX=0.0, maxX=0.0, minY=0.0, maxY=0.0)
    reanchored = compact_grid_vfg(anchored)["visualStages"][0]["visualSprites"]
    assert [(s["x"], s["y"]) for s in reanchored] == [(s["x"], s["y"]) for s in anchored["visualStages"][0]["visualSprites"]]


def _prefab_png(image):
    import base64
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_identity_tinted_opaque_prefab_renders_its_picture_not_a_white_box(tmp_path):
    import json

    from PIL import Image

    from scripts.planimation_phase1_frames import render_vfg_to_local_png_frames

    opaque = Image.new("RGBA", (10, 10), (200, 180, 120, 255))
    mask = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    mask.paste((255, 255, 255, 255), (2, 2, 8, 8))
    white, red = {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}, {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}
    sprite = {"minY": 0.0, "maxY": 1.0}
    payload = {
        "imageTable": {"m_keys": ["img-floor", "img-mask"], "m_values": [_prefab_png(opaque), _prefab_png(mask)]},
        "visualStages": [
            {
                "visualSprites": [
                    {**sprite, "name": "floor", "prefabimage": "img-floor", "color": white, "minX": 0.0, "maxX": 0.5},
                    {**sprite, "name": "tile", "prefabimage": "img-mask", "color": red, "minX": 0.5, "maxX": 1.0},
                ]
            }
        ],
    }
    render_vfg_to_local_png_frames(json.dumps(payload).encode(), tmp_path, 0, 0, canvas_size=20, draw_labels=False)
    frame = Image.open(tmp_path / "frame_000.png").convert("RGB")
    assert frame.getpixel((5, 10)) == (200, 180, 120)
    assert frame.getpixel((15, 10)) == (255, 0, 0)
    assert frame.getpixel((10, 0)) == (255, 255, 255)


@pytest.mark.parametrize(
    "domain,path,spatial",
    [
        ("logistics", "logistics/logistics_ap.pddl", "l0-0"),
        ("depot", "depot/depot_ap.pddl", "depot0"),
        ("driverlog", "driverlog/ap.pddl", "s0"),
        ("freecell", "freecell/freecell_AP.pddl", None),
    ],
)
def test_task_bound_profile_roots(domain, path, spatial):
    from examples.planning_benchmark_slice.scene_profiles import task_bound_profile

    profile = task_bound_profile(domain, context_for(domain), (ROOT / "data/pddl_instances" / path).read_text())
    if spatial:
        block = re.search(r"\(:visual mapped-" + spatial + r"\s.*?\)\s*\)\s*\)", profile, re.S)
        assert block is not None
        assert "(x NULL)" not in block[0] and "(y NULL)" not in block[0]
    else:
        block = re.search(r"\(:visual logical-symbols.*?\)\)\)", profile, re.S)
        assert block is not None and "celln0" in block[0]
        assert "(x " not in block[0] and "(y " not in block[0]


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
