"""Deterministic Goal 11 suite derivation and pre-outcome semantic audits."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import random
import re
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Mapping

from PIL import Image, UnidentifiedImageError

from .expanded_candidates import typed_grounding_count, walk_initial
from .expanded_views import apply_render_overrides
from .matched_tasks import task_semantics
from .pddl_state import PDDLStateAuthority
from .scene_assets import read_json
from .task_isomorphism import same_instance

PROTOCOL = Path("configs/experiments/expanded-study/generalization-robustness-protocol.json")
SEMANTICS_PRESERVING = "semantics-preserving"
LOSSY = "lossy"
_RENDER_RELATION_EPSILON = 1e-9
_FROZEN_SECTION_SHA256 = {
    "fixed_adapters": "fab9b9df125541e5e347454f94e38917c28bbad1a7ef0689fe4e214dbf9c074a",
    "structural_variant_families": "44f92d2e853da7329ed56d4d82ea11fb7cce3be20b2cf9ae6f6f016527618824",
    "perturbation_families": "b707b767d3c0f35ed56a89b4952884983ecaa81047b4b1e87a3e026adfefef77",
    "source_problems": "3d1266010e15c3279072711bf0e71eec3fbc1b34a6265168a76a2d94756e57f9",
    "eligibility": "aa260fe96981743598101d596b8fc674a4f9c60f777486d3f3e5ee5ca95bbc1c",
    "evaluation": "ffd2fcb1ea7f45e448031b300c9f4223e67ec490907b25256d37b7693ca4bd15",
    "inference": "d786b4aead63df44448c4a04f8a42f21a90961e9025c6646512648c9bcf6de54",
    "execution_contract": "47d7c5e55d79cf10de9d1cc08e990048f2418220c9f7216d6a71f89ab21c1a79",
    "throughput_probe": "ea11757fa87b63bb16b4e1f2786db5d7c56c87a12dec0592f05eff60044fa35b",
    "admission": "21783aeaf3ddfcc8cf405820e1bf718a5b52c6eefbae4a0422187d56f06603cd",
    "analysis": "132d07b5f365da33427d0fabd2a4ed36b022e4b295856cd8de69e3b293cddc56",
}


def load_protocol(root: Path) -> dict[str, Any]:
    protocol = json.loads((root / PROTOCOL).read_text())
    validate_protocol(root, protocol)
    return protocol


def _numeric_delta(compact: str, expanded: str) -> str:
    try:
        compact_value = Decimal(compact)
        expanded_value = Decimal(expanded)
    except InvalidOperation:
        return expanded
    scaled = 2 * expanded_value - compact_value
    if compact_value == compact_value.to_integral() and expanded_value == expanded_value.to_integral():
        width = max(len(compact), len(expanded)) if compact.startswith("0") or expanded.startswith("0") else 0
        return f"{int(scaled):0{width}d}" if width else str(int(scaled))
    return format(scaled.normalize(), "f")


def scale_up_arguments(compact: Iterable[str], expanded: Iterable[str]) -> list[str]:
    compact_values = list(compact)
    expanded_values = list(expanded)
    if len(compact_values) != len(expanded_values):
        raise ValueError("compact and expanded generator arguments differ in shape")
    return [_numeric_delta(left, right) for left, right in zip(compact_values, expanded_values, strict=True)]


def snapshot_arguments(snapshot: Mapping[str, Any], domain: str) -> list[str]:
    """Recover the frozen profile arguments from one retained task snapshot."""

    arguments = list(snapshot["generator_command"])[1:]
    if domain == "grid":
        arguments = arguments[1:]
    if domain == "driverlog":
        return arguments[1:]
    if domain == "blocksworld":
        return arguments[:-1]
    seed_flags = {
        "15puzzle": "-s",
        "depot": "-s",
        "elevators": "-r",
        "ferry": "-s",
        "grid": "--seed",
        "logistics": "-r",
        "storage": "-e",
        "visitall": "-s",
    }
    flag = seed_flags.get(domain)
    if flag is not None:
        index = arguments.index(flag)
        arguments = arguments[:index] + arguments[index + 2 :]
    if domain == "storage":
        arguments = arguments[:-1]
    return arguments


def materialize_variant_profiles(protocol: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    structural: list[dict[str, Any]] = []
    perturbations: list[dict[str, Any]] = []
    for source in protocol["source_problems"]:
        for family in ("scale-up", "shifted-init"):
            profile = copy.deepcopy(source["structural_variants"][family])
            structural.append(
                {
                    "source_task_id": source["task_id"],
                    "source_task_path": source["task_path"],
                    "domain": source["domain"],
                    "stratum_origin": source["stratum_origin"],
                    "family": family,
                    **profile,
                }
            )
        for family in ("object-renaming", "render-restyle", "name-compression"):
            perturbations.append(
                {
                    "source_task_id": source["task_id"],
                    "source_task_path": source["task_path"],
                    "domain": source["domain"],
                    "stratum_origin": source["stratum_origin"],
                    "family": family,
                    "seed": source["perturbation_seeds"][family],
                }
            )
    return {"structural": structural, "perturbations": perturbations}


def seeded_object_map(task: Mapping[str, Any], seed: int, *, compressed: bool = False) -> dict[str, str]:
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    objects = list(authority.objects)
    targets = [f"o{index + 1:04d}" if compressed else f"g11_{seed}_{index + 1:04d}" for index in range(len(objects))]
    random.Random(seed).shuffle(targets)
    return dict(zip(objects, targets, strict=True))


def _replace_object_tokens(text: str, mapping: Mapping[str, str]) -> str:
    if not mapping:
        return text
    names = sorted(mapping, key=lambda value: (-len(value), value))
    pattern = re.compile(r"(?<![A-Za-z0-9_-])(?:" + "|".join(re.escape(name) for name in names) + r")(?![A-Za-z0-9_-])")
    return pattern.sub(lambda match: mapping[match.group(0)], text)


def _rewrite_payload(value: Any, mapping: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return _replace_object_tokens(value, mapping)
    if isinstance(value, list):
        return [_rewrite_payload(item, mapping) for item in value]
    if isinstance(value, tuple):
        return tuple(_rewrite_payload(item, mapping) for item in value)
    if isinstance(value, dict):
        return {
            _replace_object_tokens(key, mapping) if isinstance(key, str) else key: _rewrite_payload(item, mapping)
            for key, item in value.items()
        }
    return copy.deepcopy(value)


def rename_task_asset(task: Mapping[str, Any], mapping: Mapping[str, str]) -> dict[str, Any]:
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    source_objects = set(authority.objects)
    if set(mapping) != source_objects or len(set(mapping.values())) != len(mapping):
        raise ValueError("object renaming must be a complete bijection over source objects")
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", target) for target in mapping.values()):
        raise ValueError("renamed objects must be valid PDDL identifiers")
    result = {}
    for key, value in task.items():
        if key in {"domain_pddl", "generator_command", "authority_transformations"}:
            result[key] = copy.deepcopy(value)
        else:
            result[key] = _rewrite_payload(value, mapping)
    result["problem_pddl"] = _replace_object_tokens(task["problem_pddl"], mapping)
    return result


def _render_delta(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    return {
        "canvas_size": 160,
        "layout_offset": [rng.choice((-0.04, 0.04)), rng.choice((-0.04, 0.04))],
    }


def materialize_view_manifest(derived_task: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact per-task manifest consumed by ExpandedTaskViews."""

    manifest = derived_task.get("view_manifest")
    if not isinstance(manifest, Mapping):
        raise ValueError("derived task lacks a materialized view_manifest")
    result = copy.deepcopy(dict(manifest))
    overrides = result.get("render_overrides")
    if overrides is not None and (
        not isinstance(overrides, Mapping) or set(overrides) != {"canvas_size", "layout_offset"}
    ):
        raise ValueError("derived task render_overrides differ from the frozen surface")
    return result


def _strip_text_type_information(value: Any) -> Any:
    type_keys = {
        "object_types",
        "objects_by_type",
        "textual_type_annotations",
        "type_annotations",
        "type_inventory",
        "types",
    }
    if isinstance(value, dict):
        return {key: _strip_text_type_information(item) for key, item in value.items() if key not in type_keys}
    if isinstance(value, list):
        return [_strip_text_type_information(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_strip_text_type_information(item) for item in value)
    if isinstance(value, str):
        lines = []
        for line in value.splitlines():
            if re.match(r"\s*(?:types?|type inventory|object types?)\s*:", line, flags=re.I):
                continue
            line = re.sub(r"\b([A-Za-z][A-Za-z0-9_-]*)\s+-\s+[A-Za-z][A-Za-z0-9_-]*\b", r"\1", line)
            lines.append(line)
        return "\n".join(lines)
    return copy.deepcopy(value)


def derive_perturbed_task(task: Mapping[str, Any], family: str, seed: int) -> tuple[dict[str, Any], dict[str, Any]]:
    if family not in {"object-renaming", "render-restyle", "name-compression"}:
        raise ValueError(f"unknown perturbation family: {family}")
    if family == "render-restyle":
        authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
        mapping = {name: name for name in authority.objects}
        derived = copy.deepcopy(dict(task))
        render_delta = _render_delta(seed)
        source_manifest = task.get("view_manifest")
        if not isinstance(source_manifest, Mapping):
            raise ValueError("render-restyle requires the source task view_manifest")
        derived["view_manifest"] = copy.deepcopy(dict(source_manifest))
        derived["view_manifest"]["render_overrides"] = copy.deepcopy(render_delta)
        view_delta = {"removed_information": []}
    else:
        mapping = seeded_object_map(task, seed, compressed=family == "name-compression")
        derived = rename_task_asset(task, mapping)
        render_delta = {}
        if family == "name-compression" and "text_pages" in derived:
            derived["text_pages"] = _strip_text_type_information(derived["text_pages"])
        view_delta = {
            "strip_textual_type_annotations_and_type_inventory": family == "name-compression",
        }
        derived["view_perturbation"] = copy.deepcopy(view_delta)
    semantic_map = {
        "schema_version": "expanded_generalization_semantic_map_v1",
        "family": family,
        "seed": seed,
        "source_to_perturbed": dict(sorted(mapping.items())),
        "perturbed_to_source": {target: source for source, target in sorted(mapping.items())},
        "render_delta": render_delta,
        "view_delta": view_delta,
    }
    return derived, semantic_map


def _asset_root(task: Mapping[str, Any]) -> Path:
    return Path(task.get("asset_root", "."))


def _asset(value: Any, root: Path) -> Any:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    if isinstance(value, str):
        return read_json(root / value)
    raise ValueError("view artifact must be an inline object or a path")


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for item in value.values() for text in _flatten_strings(item)]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [text for item in value for text in _flatten_strings(item)]
    return []


def _text_information(task: Mapping[str, Any]) -> dict[str, Any]:
    pages = task.get("text_pages")
    if pages is None:
        raise ValueError("text-state audit requires materialized text_pages")
    explicit = pages.get("state", pages) if isinstance(pages, Mapping) else pages
    if isinstance(explicit, Mapping) and {"object_identities", "atoms", "fluents"} <= set(explicit):
        return {
            "object_identities": copy.deepcopy(explicit["object_identities"]),
            "object_types": copy.deepcopy(explicit.get("object_types", {})),
            "atoms": copy.deepcopy(explicit["atoms"]),
            "fluents": copy.deepcopy(explicit["fluents"]),
        }
    text = "\n".join(_flatten_strings(explicit))
    atoms = sorted(set(re.findall(r"[A-Za-z][A-Za-z0-9_-]*\([^()]+\)", text)))
    typed = dict(re.findall(r"\b([A-Za-z][A-Za-z0-9_-]*)\s+-\s+([A-Za-z][A-Za-z0-9_-]*)\b", text))
    objects = sorted(set(typed) | {arg.strip() for atom in atoms for arg in atom.partition("(")[2][:-1].split(",")})
    return {"object_identities": objects, "object_types": typed, "atoms": atoms, "fluents": []}


def _scene_information(task: Mapping[str, Any]) -> dict[str, Any]:
    root = _asset_root(task)
    manifest = materialize_view_manifest(task)
    catalog = _asset(manifest["scene_catalog"], root)
    bindings = catalog.get("path_bindings") or []
    if not bindings:
        raise ValueError("visual audit requires a rendered VFG binding")
    payload = _asset(bindings[0]["vfg"], root)
    payload, _settings = apply_render_overrides(payload, manifest.get("render_overrides"))
    stages = payload.get("visualStages") or []
    if not stages:
        raise ValueError("visual audit VFG has no rendered stage")
    sprites = stages[0].get("visualSprites") or []
    source = manifest.get("audit_source", manifest.get("source", {}))
    declared_types = {
        name: kind for kind, names in source.get("objects_by_type", {}).items() for name in names
    }
    visible = [sprite for sprite in sprites if sprite.get("name") in declared_types]
    identities = sorted({sprite["name"] for sprite in visible})
    image_table = payload.get("imageTable") or {}
    image_keys = image_table.get("m_keys") or []
    image_values = image_table.get("m_values") or []
    encoded_images = dict(zip(image_keys, image_values, strict=False))

    def decoded_image_hash(prefab):
        encoded = encoded_images.get(prefab)
        if not isinstance(encoded, str):
            return None
        try:
            decoded = base64.b64decode(encoded, validate=True)
            with Image.open(BytesIO(decoded)) as source:
                source.load()
                image = source.convert("RGBA")
            canonical = image.width.to_bytes(4, "big") + image.height.to_bytes(4, "big") + image.tobytes()
            return hashlib.sha256(canonical).hexdigest()
        except (OSError, UnidentifiedImageError, ValueError):
            return None

    def rendered_style(sprite):
        prefab = sprite.get("prefabImage") or sprite.get("prefabimage")
        color = sprite.get("color") if isinstance(sprite.get("color"), Mapping) else {}
        rgba = tuple(
            float(color.get(channel, default))
            for channel, default in (("r", 0.65), ("g", 0.65), ("b", 0.65), ("a", 1.0))
        )
        image_hash = decoded_image_hash(prefab)
        return (f"prefab-sha256:{image_hash}" if image_hash is not None else "shape:rectangle", rgba)

    type_styles: dict[str, set[tuple[Any, ...]]] = {}
    for sprite in visible:
        type_styles.setdefault(declared_types[sprite["name"]], set()).add(rendered_style(sprite))
    singleton_styles = {kind: next(iter(styles)) for kind, styles in type_styles.items() if len(styles) == 1}
    visually_injective = len(singleton_styles) == len(type_styles) and len(
        set(singleton_styles.values())
    ) == len(type_styles)
    types = {sprite["name"]: declared_types[sprite["name"]] for sprite in visible} if visually_injective else {}
    relations = set()
    for left in visible:
        left_x = (float(left["minX"]) + float(left["maxX"])) / 2
        left_y = (float(left["minY"]) + float(left["maxY"])) / 2
        for right in visible:
            if left is right:
                continue
            right_x = (float(right["minX"]) + float(right["maxX"])) / 2
            right_y = (float(right["minY"]) + float(right["maxY"])) / 2
            if left_x + _RENDER_RELATION_EPSILON < right_x:
                relations.add(f"left_of({left['name']},{right['name']})")
            if left_y + _RENDER_RELATION_EPSILON < right_y:
                relations.add(f"below({left['name']},{right['name']})")
    return {
        "object_identities": identities,
        "object_types": types,
        "unrecoverable_information": (
            []
            if visually_injective
            else [f"object_types:{name}={declared_types[name]}" for name in sorted(identities)]
        ),
        "rendered_type_styles": {
            kind: [list(style) for style in sorted(styles, key=repr)] for kind, styles in sorted(type_styles.items())
        },
        "type_style_injective": visually_injective,
        "atoms": sorted(relations),
        "fluents": [],
    }


def view_information(task: Mapping[str, Any], modality: str) -> dict[str, Any]:
    """Extract recoverable information from the actual materialized view assets."""

    if modality == "text-state":
        return _text_information(task)
    if modality == "visual-state":
        return _scene_information(task)
    if modality == "multimodal-state":
        text, scene = _text_information(task), _scene_information(task)
        return {
            "object_identities": sorted(set(text["object_identities"]) | set(scene["object_identities"])),
            "object_types": {**text["object_types"], **scene["object_types"]},
            "atoms": sorted(set(text["atoms"]) | set(scene["atoms"])),
            "fluents": sorted(set(text["fluents"]) | set(scene["fluents"])),
            "visual_type_style_injective": scene["type_style_injective"],
            "visual_unrecoverable_information": scene["unrecoverable_information"],
        }
    raise ValueError(f"unknown modality: {modality}")


def semantic_identity(task: Mapping[str, Any]) -> dict[str, Any]:
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    return {
        "task_semantics": task_semantics(task["domain_pddl"], task["problem_pddl"]),
        "semantic_task_identity": authority.semantic_task_identity(),
        "task_context": authority.task_context(),
    }


def derive_shifted_initial(
    expanded_task: Mapping[str, Any], source_task: Mapping[str, Any], profile: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply the frozen genuine-walk V2 transform and retain replay/audit evidence."""

    origin = PDDLStateAuthority.from_pddl(expanded_task["domain_pddl"], expanded_task["problem_pddl"])
    source = PDDLStateAuthority.from_pddl(source_task["domain_pddl"], source_task["problem_pddl"])
    walked_problem, walk = walk_initial(
        expanded_task["domain_pddl"],
        expanded_task["problem_pddl"],
        {
            "domain": profile["domain"],
            "walk_origin": profile["walk_origin"],
            "walk_steps": profile["walk_steps"],
        },
        profile["seed"],
    )
    walked = PDDLStateAuthority.from_pddl(expanded_task["domain_pddl"], walked_problem)
    origin_static = {
        "canonical_goal": origin.canonical_goal,
        "objects_by_type": origin.objects_by_type,
        "static_initial_facts": origin.static_initial_facts,
    }
    walked_static = {
        "canonical_goal": walked.canonical_goal,
        "objects_by_type": walked.objects_by_type,
        "static_initial_facts": walked.static_initial_facts,
    }
    audit = {
        "replayable_walk_retained": len(walk["actions"]) == profile["walk_steps"] > 0,
        "goal_static_identity_unchanged": origin_static == walked_static,
        "walked_initial_distinct_from_generated_origin": walked.initial_state != origin.initial_state,
        "walked_initial_distinct_from_source": walked.initial_state.atoms != source.initial_state.atoms
        or walked.initial_state.fluents != source.initial_state.fluents,
        "walk": walk,
    }
    if not all(value is True for key, value in audit.items() if key != "walk"):
        raise ValueError("shifted-init genuine-walk audit failed")
    result = copy.deepcopy(dict(expanded_task))
    result["problem_pddl"] = walked_problem
    result["initial_walk"] = copy.deepcopy(walk)
    return result, audit


def _known_context(known: Mapping[str, Any]) -> tuple[str | None, str, Mapping[str, Any]]:
    task_id = known.get("task_id")
    if "domain_pddl" in known and "problem_pddl" in known:
        authority = PDDLStateAuthority.from_pddl(known["domain_pddl"], known["problem_pddl"])
        return task_id, task_semantics(known["domain_pddl"], known["problem_pddl"]), authority.task_context()
    return task_id, known["task_semantics"], known["task_context"]


def semantically_disjoint(
    task: Mapping[str, Any],
    known_tasks: Iterable[Mapping[str, Any]],
    *,
    candidate_kind: str,
    source_task_id: str | None = None,
) -> bool:
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    semantics = task_semantics(task["domain_pddl"], task["problem_pddl"])
    for known in known_tasks:
        task_id, known_semantics, context = _known_context(known)
        if candidate_kind == "perturbation" and task_id == source_task_id:
            continue
        if semantics == known_semantics or same_instance(authority.task_context(), context):
            return False
    return True


def _mapped_value(value: Any, reverse_map: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return _replace_object_tokens(value, reverse_map)
    if isinstance(value, list):
        return [_mapped_value(item, reverse_map) for item in value]
    if isinstance(value, tuple):
        return tuple(_mapped_value(item, reverse_map) for item in value)
    if isinstance(value, dict):
        return {
            reverse_map.get(key, key): _mapped_value(item, reverse_map)
            for key, item in value.items()
        }
    return value


def _information_items(information: Mapping[str, Any]) -> set[str]:
    result = set()
    for category in ("object_identities", "object_types", "atoms", "fluents"):
        value = information.get(category)
        if isinstance(value, Mapping):
            result.update(f"{category}:{key}={item}" for key, item in value.items())
        elif isinstance(value, (list, tuple, set)):
            result.update(f"{category}:{item}" for item in value)
        elif value is not None:
            result.add(f"{category}:{value}")
    return result


def classify_information_availability(
    family: str,
    source_information: Mapping[str, Any],
    perturbed_information: Mapping[str, Any],
    semantic_map: Mapping[str, Any],
    modality: str,
) -> dict[str, Any]:
    reverse = semantic_map["perturbed_to_source"]
    source_items = _information_items(source_information)
    mapped_perturbed = _mapped_value(perturbed_information, reverse)
    perturbed_items = _information_items(mapped_perturbed)
    source_unavailable = set(source_information.get("unrecoverable_information", []))
    perturbed_unavailable = set(mapped_perturbed.get("unrecoverable_information", []))
    newly_unavailable = perturbed_unavailable - source_unavailable
    missing = sorted((source_items - perturbed_items) | newly_unavailable)
    source_injective = source_information.get("type_style_injective")
    perturbed_injective = perturbed_information.get("type_style_injective")
    result = {
        "family": family,
        "modality": modality,
        "classification": LOSSY if missing else SEMANTICS_PRESERVING,
        "missing_information": missing,
        "source_information_items": len(source_items),
        "recoverable_information_items": len(source_items & perturbed_items),
        "source_visual_type_style_injective": source_injective,
        "perturbed_visual_type_style_injective": perturbed_injective,
    }
    if modality == "multimodal-state":
        source_injective = source_information["visual_type_style_injective"]
        perturbed_injective = perturbed_information["visual_type_style_injective"]
        result["visual_type_contribution_classification"] = (
            LOSSY if source_injective and not perturbed_injective else SEMANTICS_PRESERVING
        )
        result["source_visual_type_style_injective"] = source_injective
        result["perturbed_visual_type_style_injective"] = perturbed_injective
    return result


def audit_perturbation(
    source: Mapping[str, Any],
    perturbed: Mapping[str, Any],
    family: str,
    semantic_map: Mapping[str, Any],
    modality: str,
    *,
    source_reference_costs: Mapping[str, Any] | None = None,
    perturbed_reference_costs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_identity = semantic_identity(source)
    perturbed_identity = semantic_identity(perturbed)
    information = classify_information_availability(
        family,
        view_information(source, modality),
        view_information(perturbed, modality),
        semantic_map,
        modality,
    )
    expected = (
        {"text-state": LOSSY, "visual-state": SEMANTICS_PRESERVING, "multimodal-state": SEMANTICS_PRESERVING}[
            modality
        ]
        if family == "name-compression"
        else SEMANTICS_PRESERVING
    )
    return {
        "family": family,
        "expected_classification_prior": expected,
        "measured_classification": information["classification"],
        "same_instance": same_instance(source_identity["task_context"], perturbed_identity["task_context"]),
        "task_context_identical": source_identity["task_context"] == perturbed_identity["task_context"],
        "semantic_task_identity_identical": source_identity["semantic_task_identity"]
        == perturbed_identity["semantic_task_identity"],
        "information_availability": information,
        "reference_costs_match": source_reference_costs == perturbed_reference_costs
        if source_reference_costs is not None and perturbed_reference_costs is not None
        else None,
    }


def eligibility_screen(
    task: Mapping[str, Any],
    reference_costs: Mapping[str, Mapping[str, int]],
    ceilings: Mapping[str, int],
    *,
    input_tokens: int,
    view_integrity: Mapping[str, bool],
) -> dict[str, Any]:
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    grounding = typed_grounding_count(authority)
    reasons = []
    if authority.is_goal(authority.initial_state):
        reasons.append("initial_goal")
    if authority.canonical_goal in (("true",), ["true"]):
        reasons.append("empty_goal")
    if not all(view_integrity.get(key) is True for key in ("initial_view", "goal_view", "view_manifest")):
        reasons.append("render_view_integrity")
    if input_tokens > ceilings["max_input_tokens_per_call"]:
        reasons.append("input_token_bound")
    if grounding > ceilings["grounding_estimate_ceiling"]:
        reasons.append("grounding_estimate_ceiling")
    if any(row["decisions"] > ceilings["max_decisions_per_algorithm"] for row in reference_costs.values()):
        reasons.append("reference_decision_ceiling")
    if any(row["expansions"] > ceilings["max_expansions_per_algorithm"] for row in reference_costs.values()):
        reasons.append("reference_expansion_ceiling")
    if sum(row["decisions"] for row in reference_costs.values()) > ceilings["max_summed_decisions"]:
        reasons.append("summed_reference_decision_ceiling")
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "grounding_estimate": grounding,
        "reference_costs": copy.deepcopy(reference_costs),
    }


@lru_cache(maxsize=None)
def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def validate_protocol(root: Path, protocol: Mapping[str, Any]) -> None:
    """Fail closed on every frozen Goal 11 design dependency."""

    if (
        protocol.get("schema_version") != "expanded_generalization_robustness_protocol_v1"
        or protocol.get("protocol_id") != "expanded-generalization-robustness-v1"
        or protocol.get("status") != "frozen_before_suite_generation_and_model_outcomes"
        or protocol.get("program_id") != "expanded-nine-day-v1"
        or protocol.get("issues") != [96, 98]
        or protocol.get("parent_issue") != 38
        or protocol.get("panel") != "configs/experiments/expanded-study/final-panel.json"
        or protocol.get("panel_protocol") != "configs/experiments/expanded-study/panel-protocol-v2.json"
        or protocol.get("checkpoint_readiness") != "docs/experiments/expanded-study/readiness.json"
        or protocol.get("checkpoint_protocol") != "configs/experiments/expanded-study/baseline-protocol.json"
        or protocol.get("schedule") != "docs/experiments/expanded-study/schedule.json"
        or protocol.get("source_problems_expected") != 24
        or protocol.get("domains_expected") != 12
        or protocol.get("output_root") != "outputs/expanded-study/v1/generalization-robustness"
        or protocol.get("new_training") is not False
        or protocol.get("training_seed") != 17
        or protocol.get("training_seed_variance_claimed") is not False
        or protocol.get("phase1_execution")
        != (
            "CPU-only protocol and derivation design; no real suite generation, screening, model loading or GPU "
            "execution."
        )
    ):
        raise ValueError("generalization protocol schema or status differs")
    for section, expected_sha256 in _FROZEN_SECTION_SHA256.items():
        if section not in protocol or _canonical_sha256(protocol[section]) != expected_sha256:
            raise ValueError(f"generalization frozen section differs: {section}")
    final_panel = json.loads((root / protocol["panel"]).read_text())
    final_by_id = {item["row"]["task_id"]: item["row"] for item in final_panel["tasks"]}
    expected_rows = [(item["row"]["task_id"], item["row"]["task_path"]) for item in final_panel["tasks"]]
    actual_rows = [(row["task_id"], row["task_path"]) for row in protocol["source_problems"]]
    if protocol["panel_id"] != final_panel["panel_id"] or actual_rows != expected_rows or len(actual_rows) != 24:
        raise ValueError("generalization protocol panel binding differs")
    panel_protocol = json.loads((root / protocol["panel_protocol"]).read_text())
    baseline = json.loads((root / protocol["checkpoint_protocol"]).read_text())
    expected_algorithms = ["bfs", "best_first_width", "best_first_add_w3", "best_first_add_greedy"]
    expected_modalities = ["text-state", "visual-state", "multimodal-state"]
    if (
        protocol.get("model_id") != baseline["model_id"]
        or protocol.get("model_revision") != baseline["model_revision"]
        or protocol.get("algorithms") != expected_algorithms
        or protocol.get("modalities") != expected_modalities
    ):
        raise ValueError("generalization model or matrix axes differ")
    expected_structural = {
        "scale-up": {
            "id": "V1",
            "description": (
                "Extend the domain structural axis one compact-to-expanded delta beyond the expanded stratum."
            ),
            "seed_block": "93xxxx",
            "semantics_audit": "reference screen plus whole-instance disjointness; no easier replacement",
        },
        "shifted-init": {
            "id": "V2",
            "description": (
                "Use expanded-stratum arguments and a genuine fresh-seeded walk whose length equals the source "
                "problem's frozen BFS reference decisions."
            ),
            "seed_block": "94xxxx",
            "generator": "examples.planning_benchmark_slice.expanded_candidates.walk_initial",
            "require_goal_unchanged": True,
            "require_static_context_unchanged": True,
            "require_replayable_walk": True,
            "require_initial_distinct_from_generated_origin": True,
            "require_initial_distinct_from_source_task": True,
            "solvability": (
                "Empirically enforced by eligibility reference screening; failures are ineligible missing coverage "
                "and are never replaced."
            ),
        },
    }
    if protocol.get("structural_variant_families") != expected_structural:
        raise ValueError("generalization structural family definitions differ")
    perturbations = protocol.get("perturbation_families", {})
    expected_family_ids = {"object-renaming": "P1", "render-restyle": "P2", "name-compression": "P3"}
    expected_p2_transform = (
        "Set canvas_size=160 and apply a seeded normalized layout_offset of +/-0.04 to VFG sprite bounds."
    )
    expected_p3_transform = (
        "Apply a seeded bijective o0001-style object rename and remove all textual type annotations plus the "
        "complete type inventory from text-state pages."
    )
    if (
        set(perturbations) != set(expected_family_ids)
        or any(perturbations[name].get("id") != family_id for name, family_id in expected_family_ids.items())
        or any(perturbations[name].get("seed_block") != "95xxxx" for name in expected_family_ids)
        or any(not perturbations[name].get("transform") for name in expected_family_ids)
        or perturbations["render-restyle"].get("transform") != expected_p2_transform
        or perturbations["render-restyle"].get("view_manifest_override")
        != {
            "canvas_size": 160,
            "layout_offset": "seeded independent x/y choices from [-0.04, 0.04]",
        }
        or perturbations["name-compression"].get("transform") != expected_p3_transform
        or perturbations["name-compression"].get("expected_classification_by_modality")
        != {
            "text-state": "lossy",
            "visual-state": "semantics-preserving",
            "multimodal-state": "semantics-preserving",
        }
    ):
        raise ValueError("generalization perturbation family definitions differ")
    panel_seeds = {seed for row in panel_protocol["strata"] for seed in row["seeds"]}
    seed_sets = {"scale-up": set(), "shifted-init": set(), "perturbations": set()}
    for row in protocol["source_problems"]:
        compact_snapshot = json.loads((root / row["compact_snapshot"]).read_text())
        expanded_snapshot = json.loads((root / row["expanded_snapshot"]).read_text())
        compact_arguments = snapshot_arguments(compact_snapshot, row["domain"])
        expanded_arguments = snapshot_arguments(expanded_snapshot, row["domain"])
        scale_up = row["structural_variants"]["scale-up"]
        if (
            row["compact_arguments"] != compact_arguments
            or row["expanded_arguments"] != expanded_arguments
            or scale_up["arguments"] != scale_up_arguments(compact_arguments, expanded_arguments)
        ):
            raise ValueError("generalization V1 snapshot delta differs")
        for family, lower, upper in (("scale-up", 930000, 940000), ("shifted-init", 940000, 950000)):
            profile = row["structural_variants"][family]
            if not lower <= profile["seed"] < upper or (
                profile["walk_steps"] <= 0 and family == "shifted-init"
            ):
                raise ValueError("generalization structural profile differs")
            seed_sets[family].add(profile["seed"])
        shifted = row["structural_variants"]["shifted-init"]
        if (
            shifted["arguments"] != row["expanded_arguments"]
            or shifted["walk_steps"] != final_by_id[row["task_id"]]["reference_costs"]["bfs"]["decisions"]
            or shifted["walk_origin"] != ("goal" if row["domain"] == "15puzzle" else "initial")
            or set(shifted.get("audit_requirements", []))
            != {
                "replayable_walk_retained",
                "goal_static_identity_unchanged",
                "walked_initial_distinct_from_generated_origin",
                "walked_initial_distinct_from_source",
            }
        ):
            raise ValueError("generalization shifted-init rule differs")
        seed_sets["perturbations"].update(row["perturbation_seeds"].values())
    if (
        tuple(map(len, seed_sets.values())) != (24, 24, 72)
        or any(
            seed_sets[left] & seed_sets[right]
            for left, right in (
                ("scale-up", "shifted-init"),
                ("scale-up", "perturbations"),
                ("shifted-init", "perturbations"),
            )
        )
        or panel_seeds & set().union(*seed_sets.values())
        or any(not 950000 <= seed < 960000 for seed in seed_sets["perturbations"])
    ):
        raise ValueError("generalization seed blocks overlap or are incomplete")
    readiness = json.loads((root / protocol["checkpoint_readiness"]).read_text())
    readiness_rows = {(row["modality"], row["algorithm"]): row for row in readiness["checkpoints"]}
    adapter_keys = {(row["modality"], row["algorithm"]) for row in protocol["fixed_adapters"]}
    expected_adapter_keys = {
        (modality, algorithm) for modality in expected_modalities for algorithm in expected_algorithms
    }
    if (
        len(protocol["fixed_adapters"]) != 12
        or len(readiness_rows) != 12
        or adapter_keys != expected_adapter_keys
    ):
        raise ValueError("generalization checkpoint matrix differs")
    for adapter in protocol["fixed_adapters"]:
        key = (adapter["modality"], adapter["algorithm"])
        checkpoint = root / adapter["checkpoint"]
        ready = readiness_rows.get(key)
        if (
            ready is None
            or ready["checkpoint"] != adapter["checkpoint"]
            or not ready["provenance_passed"]
            or any(
                adapter[field] != ready[field]
                for field in ("seed", "steps", "tensors", "parameters", "adapter_bytes")
            )
            or _sha256(checkpoint / "adapter_model.safetensors") != adapter["adapter_model_sha256"]
            or _sha256(checkpoint / "adapter_config.json") != adapter["adapter_config_sha256"]
        ):
            raise ValueError("generalization checkpoint binding differs")
    schedule = json.loads((root / protocol["schedule"]).read_text())
    if protocol["inference"] != baseline["inference"]:
        raise ValueError("generalization inference contract differs")
    if (
        protocol["execution_contract"]["gpu_cutoff_utc"] != schedule["gpu_cutoff_utc"]
        or protocol["budget_gpu_hours"] != schedule["allocations_gpu_hours"][protocol["budget_branch"]]
    ):
        raise ValueError("generalization schedule or allocation differs")
    evaluation = protocol["evaluation"]
    tasks = evaluation["derived_tasks_full"]
    if (
        tasks != 120
        or evaluation["gpu_model_episodes_per_task"] != 24
        or evaluation["cpu_control_episodes_per_task"] != 72
        or evaluation["gpu_model_episodes_full"] != tasks * 24
        or evaluation["cpu_control_episodes_full"] != tasks * 72
        or evaluation["logical_bindings_full"] != tasks * 96
        or evaluation["random_valid_rollout_seeds"] != [17, 1013, 2027, 3041, 4001]
        or evaluation["rollouts"]
        != {"learned_adapter": 1, "pretrained_base": 1, "exact_reference": 1, "random_valid": 5}
    ):
        raise ValueError("generalization evaluation matrix arithmetic differs")
    eligibility = protocol["eligibility"]
    reference = panel_protocol["reference"]
    if (
        any(
            eligibility.get(key) != reference[key]
            for key in (
                "grounding_estimate_ceiling",
                "grounding_metric",
                "max_decisions_per_algorithm",
                "max_expansions_per_algorithm",
                "max_summed_decisions",
                "algorithms",
            )
        )
        or eligibility.get("max_input_tokens_per_call") != 32384
        or eligibility.get("render_view_integrity")
        != {"initial_view_renders": True, "goal_view_renders": True, "view_manifest_validates": True}
        or eligibility.get("source_goal_checks")
        != {"initial_state_must_not_satisfy_goal": True, "goal_must_be_non_empty": True}
    ):
        raise ValueError("generalization eligibility contract differs")
    expected_execution = {
        "deterministic_rounds": True,
        "batched_generation": True,
        "shared_backbone_per_gpu": True,
        "adapter_switching": True,
        "isolated_caching": True,
        "max_requests_per_active_episode_per_round": 1,
        "resume": (
            "Persist each raw output before trusted-runtime submission; replay committed events and pending output "
            "before continuing."
        ),
        "partial_coverage_satisfies_gate": False,
        "independent_replay_every_completed_episode": True,
        "gpu_cutoff_utc": schedule["gpu_cutoff_utc"],
    }
    if protocol.get("execution_contract") != expected_execution:
        raise ValueError("generalization execution contract differs")
    probe = protocol["throughput_probe"]
    persist_whitelist = {
        "call_wall_seconds",
        "input_tokens",
        "output_tokens",
        "algorithm",
        "modality",
        "family",
        "batch_size",
        "worker",
        "model_load_wall_seconds",
        "model_save_wall_seconds",
    }
    if (
        probe.get("kind") != "outcome-free timing calls"
        or probe.get("probe_inputs") != 60
        or probe.get("unique_probe_inputs") != 60
        or probe.get("timing_samples_per_probe_input") != 3
        or probe.get("timing_calls") != 180
        or probe.get("calls_per_algorithm_modality_family") != 3
        or probe.get("call_time_margin") != 1.5
        or probe.get("per_combo_bound")
        != "max(observed call time across the 3 repeated samples) \u00d7 1.5"
        or not {"call_wall_seconds", "input_tokens", "output_tokens"} <= set(probe.get("persist", []))
        or not set(probe.get("persist", [])) <= persist_whitelist
        or len(probe.get("persist", [])) != len(set(probe.get("persist", [])))
        or "discarded" not in probe.get("generation_outputs", "").lower()
        or "load and save wall time" not in probe.get("worker_overhead_probe", "")
    ):
        raise ValueError("generalization throughput probe contract differs")
    admission = protocol["admission"]
    expected_rule = (
        "(sum of decision_cap(task) \u00d7 per-combo max-observed-call-time \u00d7 1.5 over the admitted matrix "
        "+ measured "
        "load+save overhead per planned worker job) \u00d7 1.25 safety + probe spend already in the ledger <= branch "
        "remainder at admission time"
    )
    expected_ladder = [
        "L0 full 120 tasks",
        "L1 prospective documented recovery_reserve transfer to fit L0 (min sufficient, before launch)",
        "L2 drop P3 model evaluation (generation+audit still run) => 96 tasks",
        "L3 restrict to expanded-stratum-origin problems (S: 12x2=24, R-P1+P2: 12x2=24 => 48 tasks)",
        "L4 VALID_STOP with partial-evidence report, no closure of unfulfilled requirements",
    ]
    if (
        admission.get("rule") != expected_rule
        or admission.get("fallback_ladder") != expected_ladder
        or admission.get("safety_factor") != 1.25
        or admission.get("branch_cap_gpu_hours") != 32
        or "per planned worker job" not in admission.get("worker_overhead", "")
    ):
        raise ValueError("generalization admission contract differs")
    analysis = protocol["analysis"]
    required_analysis = {
        "paired_unit",
        "primary_contrasts",
        "missingness",
        "random_valid_aggregation",
        "bootstrap",
        "tiny_subgroup_rule",
        "lossy_pooling",
        "saturation_rule",
        "training_seed_variance_claimed",
    }
    if (
        set(analysis) != required_analysis
        or analysis["paired_unit"] != "whole task instance x algorithm x modality across conditions on identical tasks"
        or set(analysis["primary_contrasts"])
        != {"source_vs_shift_degradation", "learned_vs_best_control", "validity_and_cost"}
        or analysis["bootstrap"]
        != {
            "unit": "whole task instance within frozen domain x family strata",
            "seed": 90717,
            "resamples": 10000,
            "confidence": 0.95,
            "interval": "percentile",
            "materiality": "interval excludes 0",
        }
        or "five frozen rollout seeds" not in analysis["random_valid_aggregation"]
        or "fewer than 8" not in analysis["tiny_subgroup_rule"]
        or "never pooled" not in analysis["lossy_pooling"]
        or "issue #54" not in analysis["saturation_rule"]
        or analysis["training_seed_variance_claimed"] is not False
    ):
        raise ValueError("generalization analysis contract differs")
