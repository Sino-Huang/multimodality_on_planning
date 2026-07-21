from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from scripts.phase3.render_semantics import validate_render_artifacts


FIXTURES = Path(__file__).parent / "fixtures" / "render_semantic_cases.json"


def _png(*, covered: bool) -> bytes:
    image = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    if covered:
        for x in range(20, 60):
            for y in range(40, 80):
                image.putpixel((x, y), (32, 96, 160, 255))
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _textured_blank_png(kind: str) -> bytes:
    image = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    for x in range(100):
        for y in range(100):
            if kind == "gradient":
                value = 128 + x
                pixel = (value, value, value, 255)
            elif kind == "grid":
                pixel = (160, 160, 160, 255) if x % 10 == 0 or y % 10 == 0 else (255, 255, 255, 255)
            elif kind == "noise":
                value = (x * 37 + y * 17) % 256
                pixel = (value, (value * 13) % 256, (value * 29) % 256, 255)
            else:
                raise AssertionError(f"unsupported texture: {kind}")
            image.putpixel((x, y), pixel)
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _artifacts(tmp_path: Path, case: str, *, covered: bool = True) -> tuple[Path, Path]:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))[case]
    tmp_path.mkdir(parents=True, exist_ok=True)
    trace_path = tmp_path / "trace.vfg.json"
    frame_path = tmp_path / "frame_000.png"
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    frame_path.write_bytes(_png(covered=covered))
    return trace_path, frame_path


def test_accepts_decoded_png_with_expected_object_coverage(tmp_path: Path) -> None:
    # Given: a concrete VFG sprite and a raster that covers its expected bounds.
    trace_path, frame_path = _artifacts(tmp_path, "valid")

    # When: the semantic render gate validates artifacts.
    receipt = validate_render_artifacts(trace_path, frame_path)

    # Then: the receipt records sprite and coverage metrics.
    assert receipt.status == "success"
    assert receipt.sprite_count == 1
    assert receipt.covered_sprite_count == 1
    assert receipt.png_dimensions == (100, 100)


def test_accepts_sprite_coverage_adjacent_to_another_expected_sprite(tmp_path: Path) -> None:
    # Given: a block touching its expected board sprite in a valid rendered frame.
    payload = {
        "visualStages": [
            {
                "visualSprites": [
                    {"name": "block", "minX": 0.02, "maxX": 0.11, "minY": 0.02, "maxY": 0.11},
                    {"name": "board", "minX": 0.02, "maxX": 0.98, "minY": 0.01, "maxY": 0.04},
                ]
            }
        ]
    }
    trace_path = tmp_path / "trace.vfg.json"
    frame_path = tmp_path / "frame_000.png"
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    image = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    for x in range(2, 11):
        for y in range(89, 97):
            image.putpixel((x, y), (255, 255, 0, 255))
    for x in range(2, 98):
        for y in range(96, 99):
            image.putpixel((x, y), (0, 0, 0, 255))
    image.putpixel((11, 96), (255, 255, 0, 255))
    image.putpixel((50, 95), (255, 255, 0, 255))
    image.save(frame_path, format="PNG")

    # When: semantic validation samples the bounds of both expected sprites.
    receipt = validate_render_artifacts(trace_path, frame_path)

    # Then: adjacent board pixels do not invalidate visible block coverage.
    assert receipt.status == "success"
    assert receipt.covered_sprite_count == 2


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("malformed", "visual_sprites_not_list"),
        ("non_numeric", "sprite_coordinate_not_numeric"),
        ("out_of_canvas", "sprite_out_of_canvas"),
        ("coincident", "coincident_sprite_bounds"),
    ],
)
def test_rejects_invalid_vfg_sprite_semantics(tmp_path: Path, case: str, reason: str) -> None:
    # Given: a VFG fixture with invalid required sprite semantics.
    trace_path, frame_path = _artifacts(tmp_path, case)

    # When: the semantic render gate validates artifacts.
    receipt = validate_render_artifacts(trace_path, frame_path)

    # Then: it produces an inspectable controlled rejection.
    assert receipt.status == "semantic_image_invalid"
    assert receipt.reason == reason


def test_rejects_corrupt_png_and_missing_expected_object_coverage(tmp_path: Path) -> None:
    # Given: one corrupt raster and one valid raster missing the expected object pixels.
    trace_path, frame_path = _artifacts(tmp_path, "valid")
    corrupt_path = tmp_path / "corrupt.png"
    corrupt_path.write_bytes(b"not-a-png")

    # When: each raster is validated against the same concrete VFG.
    corrupt = validate_render_artifacts(trace_path, corrupt_path)
    uncovered = validate_render_artifacts(trace_path, frame_path)

    # Then: corrupt bytes and no coverage are controlled semantic failures.
    assert corrupt.status == "semantic_image_invalid"
    assert corrupt.reason == "png_decode_failed"
    assert uncovered.status == "success"
    empty_trace, empty_frame = _artifacts(tmp_path / "empty", "valid", covered=False)
    missing = validate_render_artifacts(empty_trace, empty_frame)
    assert missing.status == "semantic_image_invalid"
    assert missing.reason == "expected_object_coverage_failed"


@pytest.mark.parametrize("texture", ("gradient", "grid", "noise"))
def test_rejects_textured_blank_images_as_sprite_coverage(tmp_path: Path, texture: str) -> None:
    # Given: a valid VFG expecting one concrete sprite and a texture-only raster.
    trace_path, frame_path = _artifacts(tmp_path, "valid")
    frame_path.write_bytes(_textured_blank_png(texture))

    # When: the semantic render gate validates the texture against sprite bounds.
    receipt = validate_render_artifacts(trace_path, frame_path)

    # Then: texture cannot be promoted as object coverage.
    assert receipt.status == "semantic_image_invalid"
    assert receipt.reason == "expected_object_coverage_failed"
