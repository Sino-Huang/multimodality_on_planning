"""Local VFG-to-PNG fallback renderer."""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path

from src.data_collect.render_archive import _extract_png_archive


def extract_png_archive(archive_bytes: bytes, output_dir: Path) -> int:
    """Delegate PNG archive extraction to the shared safety boundary."""
    return _extract_png_archive(archive_bytes, output_dir)


def _import_pillow():
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as error:  # pragma: no cover - runtime dependency
        raise RuntimeError("Pillow is required for local PNG rendering fallback") from error
    return Image, ImageDraw, ImageOps


def _sprite_bounds(sprite: dict[str, object], canvas_size: int) -> tuple[int, int, int, int]:
    min_x = float(sprite.get("minX", 0.0))
    max_x = float(sprite.get("maxX", 1.0))
    min_y = float(sprite.get("minY", 0.0))
    max_y = float(sprite.get("maxY", 1.0))
    left = max(int(min_x * canvas_size), 0)
    right = min(max(int(max_x * canvas_size), left + 1), canvas_size)
    top = max(int((1.0 - max_y) * canvas_size), 0)
    bottom = min(max(int((1.0 - min_y) * canvas_size), top + 1), canvas_size)
    return left, top, right, bottom


def _sprite_rgba(sprite: dict[str, object]) -> tuple[int, int, int, int]:
    color = sprite.get("color")
    if not isinstance(color, dict):
        color = {}
    return (
        int(float(color.get("r", 0.65)) * 255),
        int(float(color.get("g", 0.65)) * 255),
        int(float(color.get("b", 0.65)) * 255),
        int(float(color.get("a", 1.0)) * 255),
    )


def layout_scene_labels(draw, labels, font, canvas_size):
    """Keep complete object names separate and visibly attached to their sprites."""
    placed = []
    for preferred_x, preferred_y, text, anchor in labels:
        bounds = draw.textbbox((0, 0), text, font=font)
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        if width + 8 > canvas_size or height + 8 > canvas_size:
            raise ValueError("complete scene object label exceeds canvas")
        offsets = [(0, 0)]
        for radius in range(1, 9):
            x, y = radius * (width + 8), radius * (height + 8)
            offsets.extend([(0, -y), (0, y), (x, 0), (-x, 0), (x, -y), (-x, -y), (x, y), (-x, y)])
        for dx, dy in offsets:
            x = min(max(preferred_x + dx, 4 - bounds[0]), canvas_size - 4 - bounds[2])
            y = min(max(preferred_y + dy, 4 - bounds[1]), canvas_size - 4 - bounds[3])
            box = draw.textbbox((x, y), text, font=font)
            if any(
                box[0] < p["box"][2] + 4
                and box[2] + 4 > p["box"][0]
                and box[1] < p["box"][3] + 4
                and box[3] + 4 > p["box"][1]
                for p in placed
            ):
                continue
            placed.append(
                {"text": text, "xy": (x, y), "box": box, "anchor": anchor, "moved": (x, y) != (preferred_x, preferred_y)}
            )
            break
        else:
            raise ValueError("scene object labels cannot be placed without overlap")
    return placed


def render_vfg_to_local_png_frames(
    vfg_bytes: bytes,
    output_dir: Path,
    start_step: int,
    stop_step: int,
    canvas_size: int = 1024,
    label_font_size: int | None = None,
    object_names: frozenset[str] = frozenset(),
) -> int:
    """Render selected VFG visual stages to readable local PNG frames."""
    Image, ImageDraw, ImageOps = _import_pillow()
    label_font = None
    if label_font_size is not None:
        from PIL import ImageFont

        label_font = ImageFont.truetype("DejaVuSans.ttf", label_font_size)
    payload = json.loads(vfg_bytes.decode("utf-8"))
    stages = payload.get("visualStages") or []
    if not stages:
        raise RuntimeError("VFG payload does not contain any visualStages")
    image_table = payload.get("imageTable") or {}
    prefab_images = {
        key: Image.open(BytesIO(base64.b64decode(encoded))).convert("RGBA")
        for key, encoded in zip(image_table.get("m_keys") or [], image_table.get("m_values") or [], strict=False)
    }
    selected_stages = stages[start_step : min(stop_step + 1, len(stages))]
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, stage in enumerate(selected_stages):
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        labels = []
        for sprite in sorted(stage.get("visualSprites") or [], key=lambda item: item.get("depth", 0)):
            left, top, right, bottom = _sprite_bounds(sprite, canvas_size)
            width, height = max(right - left, 1), max(bottom - top, 1)
            rgba = _sprite_rgba(sprite)
            if object_names and sprite.get("name") == "robot":
                # Some profiles tint the robot exactly like the visited cell.
                rgba = (0, 0, 0, 255)
            prefab_image = prefab_images.get(sprite.get("prefabImage") or sprite.get("prefabimage"))
            if prefab_image is None:
                draw.rectangle([left, top, right, bottom], fill=rgba, outline=(0, 0, 0, 255))
            else:
                resized = prefab_image.resize((width, height))
                tinted = Image.new("RGBA", (width, height), rgba)
                tinted.putalpha(ImageOps.autocontrast(resized.split()[-1]))
                canvas.alpha_composite(tinted, (left, top))
            if (
                sprite.get("name") in object_names
                or sprite.get("showName")
                or sprite.get("showname")
                or sprite.get("showlabel")
            ):
                label = (
                    sprite.get("name")
                    if sprite.get("name") in object_names
                    else sprite.get("label") or sprite.get("name") or ""
                )
                if label:
                    if object_names:
                        labels.append((left + 4, top + 4, str(label), ((left + right) // 2, (top + bottom) // 2)))
                    else:
                        draw.text((left + 4, top + 4), str(label), fill=(0, 0, 0, 255), font=label_font)
        placed = layout_scene_labels(draw, labels, label_font, canvas_size)
        for label in placed:
            if label["moved"]:
                box = label["box"]
                draw.line([((box[0] + box[2]) // 2, (box[1] + box[3]) // 2), label["anchor"]], fill="black", width=1)
        for label in placed:
            draw.rectangle(label["box"], fill="white")
            draw.text(label["xy"], label["text"], fill="black", font=label_font)
        canvas.save(output_dir / f"frame_{index:03d}.png")
    if not selected_stages:
        raise RuntimeError("Local VFG rendering produced zero PNG frames")
    return len(selected_stages)
