from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .traversal_state_types import JSONValue


MIN_OBJECT_COVERAGE = 0.01


@dataclass(frozen=True, slots=True)
class RenderSemanticReceipt:
    status: str
    reason: str
    png_dimensions: tuple[int, int] = ()
    sprite_count: int = 0
    covered_sprite_count: int = 0

    def to_record(self) -> dict[str, int | str | list[int]]:
        return {
            "status": self.status,
            "reason": self.reason,
            "png_dimensions": list(self.png_dimensions),
            "sprite_count": self.sprite_count,
            "covered_sprite_count": self.covered_sprite_count,
            "minimum_object_coverage": MIN_OBJECT_COVERAGE,
        }


@dataclass(frozen=True, slots=True)
class SpriteBounds:
    name: str
    min_x: float
    max_x: float
    min_y: float
    max_y: float


def validate_render_artifacts(trace_path: Path, frame_path: Path) -> RenderSemanticReceipt:
    sprites = _parse_stage_zero_sprites(trace_path)
    if isinstance(sprites, RenderSemanticReceipt):
        return sprites
    decoded = _decode_png(frame_path)
    if isinstance(decoded, RenderSemanticReceipt):
        return decoded
    image, dimensions = decoded
    covered = sum(_sprite_has_coverage(image, bounds, sprites) for bounds in sprites)
    if covered != len(sprites):
        return RenderSemanticReceipt(
            "semantic_image_invalid",
            "expected_object_coverage_failed",
            dimensions,
            len(sprites),
            covered,
        )
    return RenderSemanticReceipt("success", "validated_expected_object_coverage", dimensions, len(sprites), covered)


def _parse_stage_zero_sprites(trace_path: Path) -> tuple[SpriteBounds, ...] | RenderSemanticReceipt:
    try:
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return RenderSemanticReceipt("semantic_image_invalid", "vfg_decode_failed")
    if not isinstance(payload, Mapping):
        return RenderSemanticReceipt("semantic_image_invalid", "vfg_not_mapping")
    stages = payload.get("visualStages")
    if not isinstance(stages, list) or not stages:
        return RenderSemanticReceipt("semantic_image_invalid", "visual_stages_missing")
    stage = stages[0]
    if not isinstance(stage, Mapping):
        return RenderSemanticReceipt("semantic_image_invalid", "visual_stage_not_mapping")
    raw_sprites = stage.get("visualSprites")
    if not isinstance(raw_sprites, list):
        return RenderSemanticReceipt("semantic_image_invalid", "visual_sprites_not_list")
    if not raw_sprites:
        return RenderSemanticReceipt("semantic_image_invalid", "required_sprites_missing")
    parsed: list[SpriteBounds] = []
    seen_bounds: set[tuple[float, float, float, float]] = set()
    for index, raw_sprite in enumerate(raw_sprites):
        if not isinstance(raw_sprite, Mapping):
            return RenderSemanticReceipt("semantic_image_invalid", "sprite_not_mapping")
        bounds = _parse_sprite(raw_sprite, index)
        if isinstance(bounds, RenderSemanticReceipt):
            return bounds
        key = (bounds.min_x, bounds.max_x, bounds.min_y, bounds.max_y)
        if key in seen_bounds:
            return RenderSemanticReceipt("semantic_image_invalid", "coincident_sprite_bounds")
        seen_bounds.add(key)
        parsed.append(bounds)
    return tuple(parsed)


def _parse_sprite(raw_sprite: Mapping[str, JSONValue], index: int) -> SpriteBounds | RenderSemanticReceipt:
    coordinates = tuple(raw_sprite.get(field) for field in ("minX", "maxX", "minY", "maxY"))
    if not all(_is_coordinate(value) for value in coordinates):
        return RenderSemanticReceipt("semantic_image_invalid", "sprite_coordinate_not_numeric")
    min_x, max_x, min_y, max_y = (float(value) for value in coordinates)
    if min_x < 0.0 or max_x > 1.0 or min_y < 0.0 or max_y > 1.0:
        return RenderSemanticReceipt("semantic_image_invalid", "sprite_out_of_canvas")
    if min_x >= max_x or min_y >= max_y:
        return RenderSemanticReceipt("semantic_image_invalid", "sprite_degenerate_bounds")
    name = raw_sprite.get("name")
    return SpriteBounds(name if isinstance(name, str) and name else f"sprite-{index}", min_x, max_x, min_y, max_y)


def _is_coordinate(value: JSONValue) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _decode_png(frame_path: Path) -> tuple[Image.Image, tuple[int, int]] | RenderSemanticReceipt:
    try:
        with Image.open(frame_path) as source:
            source.verify()
        with Image.open(frame_path) as source:
            image = source.convert("RGBA")
    except (OSError, UnidentifiedImageError):
        return RenderSemanticReceipt("semantic_image_invalid", "png_decode_failed")
    if image.width <= 0 or image.height <= 0:
        return RenderSemanticReceipt("semantic_image_invalid", "png_invalid_dimensions")
    return image, (image.width, image.height)


def _sprite_has_coverage(image: Image.Image, bounds: SpriteBounds, sprites: tuple[SpriteBounds, ...]) -> bool:
    left = math.floor(bounds.min_x * image.width)
    right = math.ceil(bounds.max_x * image.width)
    top = math.floor((1.0 - bounds.max_y) * image.height)
    bottom = math.ceil((1.0 - bounds.min_y) * image.height)
    crop = image.crop((left, top, right, bottom))
    pixels = tuple(crop.get_flattened_data())
    background = _local_background(image, left, right, top, bottom, bounds, sprites)
    background_reference, texture_variation = _background_reference(background)
    covered = sum(pixel[3] > 0 and max(abs(pixel[channel] - background_reference[channel]) for channel in range(3)) > 12 + texture_variation for pixel in pixels)
    return covered >= max(1, math.ceil(len(pixels) * MIN_OBJECT_COVERAGE))


def _local_background(
    image: Image.Image,
    left: int,
    right: int,
    top: int,
    bottom: int,
    bounds: SpriteBounds,
    sprites: tuple[SpriteBounds, ...],
) -> tuple[tuple[int, int, int, int], ...]:
    points = [(x, y) for x in range(max(0, left - 1), min(image.width, right + 1)) for y in (top - 1, bottom)]
    points.extend((x, y) for y in range(top, bottom) for x in (left - 1, right))
    pixels = tuple(
        image.getpixel((x, y))
        for x, y in points
        if 0 <= x < image.width
        and 0 <= y < image.height
        and not _inside_other_sprite(x, y, image, bounds, sprites)
    )
    return pixels or (image.getpixel((0, 0)),)


def _inside_other_sprite(
    x: int,
    y: int,
    image: Image.Image,
    bounds: SpriteBounds,
    sprites: tuple[SpriteBounds, ...],
) -> bool:
    normalized_x = (x + 0.5) / image.width
    normalized_y = 1.0 - (y + 0.5) / image.height
    return any(
        sprite != bounds
        and sprite.min_x <= normalized_x <= sprite.max_x
        and sprite.min_y <= normalized_y <= sprite.max_y
        for sprite in sprites
    )


def _background_reference(
    background: tuple[tuple[int, int, int, int], ...],
) -> tuple[tuple[int, int, int, int], int]:
    reference = Counter(background).most_common(1)[0][0]
    variations = sorted(max(abs(pixel[channel] - reference[channel]) for channel in range(3)) for pixel in background)
    return reference, variations[math.ceil(len(variations) * 0.98) - 1]
