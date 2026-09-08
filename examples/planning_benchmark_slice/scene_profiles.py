"""Renderer-only task bindings for retained animation profiles."""

from __future__ import annotations

import re
from typing import Any


def freecell_renderer_domain(domain: str) -> str:
    """Track covered foundation cards in a rendering-only copy of the domain.

    Freecell's home predicate identifies only the top card. Once covered, a
    card has no location predicate but still exists as a backend sprite. The
    extra fact is display bookkeeping only; original planning replay is unchanged.
    """
    domain = re.sub(r"\(:predicates\b", "(:predicates (coveredhome ?c - card)", domain, count=1, flags=re.I)
    return re.sub(
        r"\(not\s+\(home\s+(\?[\w-]+)\)\s*\)", lambda match: match[0] + f" (coveredhome {match[1]})", domain, flags=re.I
    )


def renderer_domain(domain: str) -> str:
    """Alpha-rename variables to avoid the legacy backend's prefix substitution.

    Equal-length names preserve variable identity and scope, action names and
    argument order. The planning authority continues to use the original PDDL.
    """
    pattern = r"\?[a-zA-Z0-9_-]+"
    names = sorted(set(re.findall(pattern, domain.lower())))
    width = len(str(len(names)))
    mapping = {name: f"?render{index:0{width}d}" for index, name in enumerate(names)}
    return re.sub(pattern, lambda match: mapping[match[0].lower()], domain)


def _block(profile: str, kind: str, name: str) -> tuple[int, int]:
    start = re.search(r"\(:" + kind + r"\s+" + re.escape(name) + r"\b", profile, re.IGNORECASE)
    if start is None:
        raise RuntimeError(f"missing animation {kind} {name}")
    depth = 0
    for end in range(start.start(), len(profile)):
        depth += (profile[end] == "(") - (profile[end] == ")")
        if depth == 0:
            return start.start(), end + 1
    raise RuntimeError(f"unclosed animation {kind} {name}")


def task_bound_profile(domain: str, context: dict[str, Any], profile: str) -> str:
    """Bind static layout roots; dynamic at/on/in rules remain authoritative.

    Typed place declarations are not unary facts in the legacy backend. Logical
    Freecell counters/suits are deliberately non-spatial, not failed sprites.
    """
    bindings: list[str] = []

    def bind(template: str, obj: str, x: int, y: int) -> None:
        start, end = _block(profile, "visual", template)
        block = profile[start:end]
        block = re.sub(r"(:visual\s+)\S+", r"\1mapped-" + obj, block, count=1)
        block = re.sub(r":objects\s+(?:\([^)]*\)|[^\s()]+)", f":objects ({obj})", block, count=1)
        for key, value in (("x", x), ("y", y)):
            block = re.sub(r"\(" + key + r"\s+[^)]+\)", f"({key} {value})", block, count=1, flags=re.I)
        bindings.append(block)

    if domain == "logistics":
        cities = sorted(args[0] for args in _facts(context, "city"))
        for row, city in enumerate(cities):
            bind("city", city, 0, row * 300 + 100)
            locations = sorted(loc for loc, parent in _facts(context, "in-city") if parent == city)
            for column, location in enumerate(locations):
                bind("hub", location, column * 750, row * 300 + 100)
        for predicate in ("city", "in-city"):
            start, end = _block(profile, "predicate", predicate)
            profile = profile[:start] + profile[end:]
    elif domain == "depot":
        for row, (place,) in enumerate(sorted(_facts(context, "@type-place@"))):
            is_depot = (place,) in _facts(context, "@type-depot@")
            bind("depot" if is_depot else "distributor", place, 10 if is_depot else 300, row * 300 + 100)
    elif domain == "driverlog":
        locations = sorted(args[0] for args in _facts(context, "@type-location@"))
        sites = {obj for edge in _facts(context, "link") for obj in edge}
        for objects, template, y in (
            ([obj for obj in locations if obj in sites], "s", 0),
            ([obj for obj in locations if obj not in sites], "p", 500),
        ):
            for column, obj in enumerate(objects):
                bind(template, obj, column * 440, y)
    elif domain == "freecell":
        bindings.append(
            "(:predicate coveredhome :parameters (?c) :effect ("
            "(equal (?c x) (?c origx)) (equal (?c y) (?c origy)) "
            "(equal (?c depth) 0) (equal (?c showName) FALSE)))"
        )
        symbols = sorted(
            args[0] for kind in ("cellnum", "colnum", "num", "suit") for args in _facts(context, f"@type-{kind}@")
        )
        bindings.append(
            "(:visual logical-symbols :type predefine :objects ("
            + " ".join(symbols)
            + ") :properties ((showName FALSE)))"
        )
    else:
        raise ValueError(f"unsupported task-bound profile: {domain}")
    end = profile.rfind(")")
    return profile[:end] + "\n" + "\n".join(bindings) + "\n" + profile[end:]


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
