"""Opt-in localhost regression: real multi-home paths, not first-edge smoke.

Run with PLANIMATION_SCENE_LIVE=1 and four existing backend processes.
"""

import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from examples.planning_benchmark_slice.modality_phase import ROOT
from examples.planning_benchmark_slice.planimation_render import PlanimationRenderRequest, produce_planimation_render
from examples.planning_benchmark_slice.scene_assets import (
    build_scene_catalog,
    catalog_paths,
    collect_task_scenes,
    load_scene_task,
    read_json,
    require_resolved_scene_coordinates,
)
from examples.planning_benchmark_slice.scene_profiles import freecell_renderer_domain, task_bound_profile

pytestmark = pytest.mark.skipif(os.environ.get("PLANIMATION_SCENE_LIVE") != "1", reason="opt-in localhost render")


def test_complete_formerly_failed_freecell_task():
    row = read_json(ROOT / "configs/experiments/issue71/v2/panel.json")["selected"][99]
    with tempfile.TemporaryDirectory(prefix="freecell-regression-", dir=ROOT / ".cache") as temporary:
        result = collect_task_scenes(
            root=ROOT,
            row=row,
            profile=ROOT / "data/pddl_instances/freecell/freecell_AP.pddl",
            endpoint="http://127.0.0.1:18092",
            output=Path(temporary) / "task",
            timeout=30,
            preflight=False,
            progress=lambda event: None,
        )
        assert result["outcome"] == "PASS" and result["complete_state_coverage"]
        assert result["scene_frames"] == result["catalog_states"] == 363


@pytest.mark.parametrize("panel_index", [99, 100, 101, 102, 103, 187, 188, 189, 190, 191, 192])
def test_freecell_multiple_home_transitions(panel_index, tmp_path):
    row = read_json(ROOT / "configs/experiments/issue71/v2/panel.json")["selected"][panel_index]
    assert row["domain"] == "freecell"
    domain, problem, traces = load_scene_task(ROOT, row)
    catalog = build_scene_catalog(domain, problem, traces)
    paths = catalog_paths(catalog)
    # Include the exact formerly failing path as well as each task's path with
    # most foundation moves; this exercises covered cards across all 11 tasks.
    chosen = [max(paths, key=lambda item: (sum("home" in a for a in item[1]), len(item[1])))]
    if panel_index == 99:
        chosen.append(paths[108])
    (tmp_path / "domain.pddl").write_text(freecell_renderer_domain(domain))
    (tmp_path / "problem.pddl").write_text(problem)
    profile = task_bound_profile(
        "freecell", catalog["task_context"], (ROOT / "data/pddl_instances/freecell/freecell_AP.pddl").read_text()
    )
    (tmp_path / "profile.pddl").write_text(profile)
    for path_index, (indices, actions) in enumerate(chosen):
        result = produce_planimation_render(
            PlanimationRenderRequest(
                f"http://127.0.0.1:{18092 + panel_index % 4}",
                tmp_path / "domain.pddl",
                tmp_path / "problem.pddl",
                tmp_path / "profile.pddl",
                actions,
                tmp_path / f"path-{path_index}",
                30,
                canvas_size=128,
            )
        )
        stages = read_json(result.trace_path)["visualStages"]
        require_resolved_scene_coordinates(stages)
        assert len(stages) == len(indices)
        covered = set()
        previous_home = set()
        for index, stage in zip(indices, stages, strict=True):
            home = {atom[5:-1] for atom in catalog["states"][index]["atoms"] if atom.startswith("home(")}
            covered.update(previous_home - home)
            previous_home = home
            sprites = {sprite["name"]: sprite for sprite in stage["visualSprites"]}
            for card in covered:
                sprite = sprites[card]
                assert sprite["x"] == sprite["origx"] and sprite["y"] == sprite["origy"]
                assert sprite["depth"] == 0
                assert not sprite.get("showName", sprite.get("showname"))
        for frame in result.frame_paths:
            with Image.open(frame) as image:
                assert image.size == (128, 128)
