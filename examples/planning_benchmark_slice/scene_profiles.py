"""Task-aware bindings for the retained Storage and Grid animation profiles."""

from __future__ import annotations

import re
from typing import Any


def _facts(context: dict[str, Any], predicate: str) -> list[tuple[str, ...]]:
    prefix = predicate + "("
    return [
        tuple(fact[len(prefix) : -1].split(","))
        for fact in (*context["static_initial_facts"], *context["initial_dynamic_atoms"])
        if fact.startswith(prefix)
    ]


def _visual(profile: str, name: str, objects: list[str], *, width: int | None = None) -> str:
    start = re.search(r"\(:visual\s+" + re.escape(name) + r"\b", profile, re.IGNORECASE)
    if start is None or not objects:
        raise RuntimeError(f"cannot bind animation visual {name}")
    depth = 0
    end = start.start()
    for end in range(start.start(), len(profile)):
        depth += (profile[end] == "(") - (profile[end] == ")")
        if depth == 0:
            break
    block = profile[start.start() : end + 1]
    block, count = re.subn(
        r"(:objects\s+)(?:\([^)]*\)|[^\s()]+)",
        lambda match: match[1] + "(" + " ".join(objects) + ")",
        block,
        count=1,
        flags=re.IGNORECASE,
    )
    if count != 1:
        raise RuntimeError(f"animation visual {name} has no object binding")
    if width is not None:
        block = re.sub(r"\(width\s+[^)]+\)", f"(width {width})", block, count=1, flags=re.IGNORECASE)
    return profile[: start.start()] + block + profile[end + 1 :]


def storage_profile(context: dict[str, Any], profile: str) -> str:
    """Bind compartments from type and containment facts, not hard-coded depot0 names."""
    members = {
        kind: sorted(args[0] for args in _facts(context, f"@type-{kind}@"))
        for kind in ("depot", "container", "storearea", "transitarea", "hoist")
    }
    # The retained illustration has one depot row and one container row.
    if len(members["depot"]) != 1 or len(members["container"]) != 1:
        raise RuntimeError("storage profile requires one depot and one container row")
    containment = {area: place for area, place in _facts(context, "in") if area in members["storearea"]}
    if set(containment) != set(members["storearea"]):
        raise RuntimeError("storage area lacks an authoritative containing place")
    depot_areas = sorted(area for area, place in containment.items() if place in members["depot"])
    container_areas = sorted(area for area, place in containment.items() if place in members["container"])
    if set(depot_areas + container_areas) != set(members["storearea"]):
        raise RuntimeError("storage area has an unsupported containing place")
    width = 300 * (max(len(depot_areas), len(container_areas)) + 1)
    for visual, objects in (
        ("depots", depot_areas),
        ("containers", container_areas),
        ("depot", members["depot"]),
        ("container", members["container"]),
        ("loadarea", members["transitarea"]),
        ("hoist", members["hoist"]),
    ):
        profile = _visual(profile, visual, objects, width=width if visual in {"depot", "container"} else None)
    return profile


def grid_profile(context: dict[str, Any], profile: str) -> str:
    """Keep shape categories non-spatial and bind their distinct existing icon templates."""
    shapes = sorted(args[0] for args in _facts(context, "shape"))
    templates = ("circle", "square", "triangle", "diamond")
    if not 1 <= len(shapes) <= len(templates):
        raise RuntimeError("grid shape count exceeds the four distinct retained icon templates")
    used = {shape for predicate in ("key-shape", "lock-shape") for _object, shape in _facts(context, predicate)}
    if not used.issubset(shapes):
        raise RuntimeError("grid key/lock refers to an undeclared shape category")
    for template, shape in zip(templates, shapes, strict=False):
        profile = _visual(profile, template, [shape])
    # Shape facts are static. Bind the key/lock sprites explicitly as well: the
    # legacy backend's stage rules do not reliably propagate their prefab image.
    icons = dict(zip(shapes, templates, strict=False))
    bindings = []
    for predicate, width, color, depth in (("key-shape", 20, "#14A5DB", 3), ("lock-shape", 80, "GREEN", 1)):
        for index, (obj, shape) in enumerate(sorted(_facts(context, predicate))):
            bindings.append(
                f"(:visual mapped-{predicate}-{index} :type predefine :objects ({obj}) :properties "
                f"((prefabImage img-{icons[shape]}) (showName FALSE) (x Null) (y Null) "
                f"(width {width}) (height {width}) (color {color}) (depth {depth})))"
            )
    end = profile.rfind(")")
    profile = profile[:end] + "\n" + "\n".join(bindings) + "\n" + profile[end:]
    return profile


def require_grid_shape_icons(context: dict[str, Any], stages: list[dict[str, Any]]) -> None:
    """A resolved scene must still distinguish the task's key/lock categories."""
    shapes = sorted(args[0] for args in _facts(context, "shape"))
    icons = dict(zip(shapes, ("img-circle", "img-square", "img-triangle", "img-diamond"), strict=False))
    expected = {
        obj: icons[shape] for predicate in ("key-shape", "lock-shape") for obj, shape in _facts(context, predicate)
    }
    for stage in stages:
        sprites = {sprite["name"]: sprite for sprite in stage.get("visualSprites", [])}
        for obj, icon in expected.items():
            sprite = sprites.get(obj, {})
            if sprite.get("prefabImage", sprite.get("prefabimage")) != icon:
                raise RuntimeError(f"grid scene does not preserve the declared shape for {obj}")
