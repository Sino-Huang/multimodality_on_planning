from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.planimation_render import (
    PlanimationRenderError,
    PlanimationRenderRequest,
    produce_planimation_render,
)


def test_scene_object_labels_survive_later_sprites(tmp_path):
    from PIL import Image

    from scripts.planimation_phase1_frames import render_vfg_to_local_png_frames

    sprite = {
        "name": "ball1",
        "minX": 0.1,
        "maxX": 0.8,
        "minY": 0.1,
        "maxY": 0.8,
        "color": {"r": 1, "g": 1, "b": 1, "a": 1},
        "showname": False,
    }
    payload = json.dumps(
        {"visualStages": [{"visualSprites": [sprite, {**sprite, "name": "cover", "depth": 1}]}]}
    ).encode()
    render_vfg_to_local_png_frames(payload, tmp_path / "legacy", 0, 0, canvas_size=128)
    render_vfg_to_local_png_frames(
        payload, tmp_path / "scene", 0, 0, canvas_size=128, label_font_size=24, object_names=frozenset({"ball1"})
    )
    with Image.open(tmp_path / "legacy/frame_000.png") as before, Image.open(tmp_path / "scene/frame_000.png") as after:
        assert before.crop((16, 30, 90, 65)).convert("L").getextrema() == (255, 255)
        assert after.crop((16, 30, 90, 65)).convert("L").getextrema()[0] == 0


def test_scene_robot_contrasts_with_same_colour_cell(tmp_path):
    from PIL import Image

    from scripts.planimation_phase1_frames import render_vfg_to_local_png_frames

    sprite = {
        "name": "robot",
        "minX": 0.2,
        "maxX": 0.5,
        "minY": 0.2,
        "maxY": 0.5,
        "color": {"r": 1, "g": 1, "b": 1, "a": 1},
    }
    payload = json.dumps({"visualStages": [{"visualSprites": [sprite]}]}).encode()
    render_vfg_to_local_png_frames(
        payload, tmp_path, 0, 0, canvas_size=128, label_font_size=24, object_names=frozenset({"cell0"})
    )
    with Image.open(tmp_path / "frame_000.png") as image:
        assert image.getpixel((45, 80)) == (0, 0, 0, 255)


def test_scene_labels_do_not_cover_other_names_or_leave_canvas():
    from PIL import Image, ImageDraw, ImageFont

    from scripts.planimation_phase1_frames import layout_scene_labels

    draw = ImageDraw.Draw(Image.new("RGB", (256, 256), "white"))
    font = ImageFont.truetype("DejaVuSans.ttf", 24)
    labels = [
        (8, 8, "home", (30, 40)),
        (8, 12, "c0", (35, 50)),
        (250, 240, "truck1", (240, 240)),
        (250, 240, "package1", (240, 240)),
    ]
    placed = layout_scene_labels(draw, labels, font, 256)
    assert [p["text"] for p in placed] == [p[2] for p in labels]
    assert any(p["moved"] for p in placed)
    for i, entry in enumerate(placed):
        box = entry["box"]
        assert 0 <= box[0] < box[2] <= 256 and 0 <= box[1] < box[3] <= 256
        for previous in placed[:i]:
            other = previous["box"]
            assert box[2] <= other[0] or other[2] <= box[0] or box[3] <= other[1] or other[3] <= box[1]


def _request(
    tmp_path: Path,
    *,
    base_url: str = "http://127.0.0.1:18082",
    supplied_plan: tuple[str, ...] | None = ("(pickup b1)", "(stack b1 b2)"),
    solver_url: str | None = None,
) -> PlanimationRenderRequest:
    domain_path = tmp_path / "domain.pddl"
    problem_path = tmp_path / "problem.pddl"
    profile_path = tmp_path / "profile.pddl"
    domain_path.write_text("(define (domain blocks))", encoding="utf-8")
    problem_path.write_text("(define (problem p1) (:domain blocks))", encoding="utf-8")
    profile_path.write_text("(define (domain blocks-animation))", encoding="utf-8")
    return PlanimationRenderRequest(
        base_url=base_url,
        domain_path=domain_path,
        problem_path=problem_path,
        animation_profile_path=profile_path,
        supplied_plan=supplied_plan,
        output_dir=tmp_path / "render",
        timeout_seconds=30,
        solver_url=solver_url,
    )


def test_production_uses_one_local_supplied_plan_request_and_writes_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    posted: list[dict[str, object]] = []
    vfg_payload = {
        "imageTable": {"m_keys": [], "m_values": []},
        "visualStages": [{"visualSprites": []} for _ in range(3)],
    }

    def post(url: str, **arguments: object) -> object:
        posted.append({"url": url, **arguments})
        return types.SimpleNamespace(
            status_code=200,
            text=json.dumps(vfg_payload),
            content=json.dumps(vfg_payload).encode("utf-8"),
            json=lambda: vfg_payload,
        )

    monkeypatch.setattr("scripts.planimation_phase1_client.requests.post", post)
    result = produce_planimation_render(request)

    assert len(posted) == 1
    assert posted[0]["url"] == "http://127.0.0.1:18082/upload/pddl"
    assert posted[0]["allow_redirects"] is False
    files = posted[0]["files"]
    assert isinstance(files, dict)
    assert list(files) == ["domain", "problem", "animation", "plan"]
    assert files["plan"] == (None, "(pickup b1)\n(stack b1 b2)")
    assert result.used_endpoint == "http://127.0.0.1:18082/upload/pddl"
    assert result.trace_path.is_file()
    assert len(result.frame_paths) == 3
    assert all(path.is_file() for path in result.frame_paths)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"base_url": "https://planimation.planning.domains"}, "Planimation endpoint must be localhost"),
        ({"supplied_plan": None}, "supplied plan is required"),
        ({"supplied_plan": ()}, "supplied plan is required"),
        ({"supplied_plan": ("pickup b1",)}, "supplied plan actions must be parenthesized"),
        ({"solver_url": "http://127.0.0.1:18082/forbidden-solver"}, "planning fallback is prohibited"),
    ],
)
def test_production_hard_fails_unsafe_requests_before_http(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    message: str,
) -> None:
    posts: list[object] = []
    request = _request(tmp_path, **overrides)  # type: ignore[arg-type]
    monkeypatch.setattr(
        "scripts.planimation_phase1_client.requests.post",
        lambda *args, **kwargs: posts.append((args, kwargs)),
    )

    with pytest.raises(PlanimationRenderError, match=message):
        produce_planimation_render(request)

    assert posts == []
    assert not request.output_dir.exists()
