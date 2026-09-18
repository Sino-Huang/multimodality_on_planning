"""Scene-only initial/current views over unchanged authoritative task records."""

from __future__ import annotations

import json

from PIL import Image

from scripts.planimation_phase1_frames import render_vfg_to_local_png_frames

from .modality_pages import (
    LEGEND,
    PAGE_SIZE,
    compose_page,
    fact_blocks,
    paginate,
    project_messages,
    shared_state_page_cache,
)
from .modality_view_preparation import frozen_processor, validate_process_state, write_json
from .scene_assets import read_json

SCENE_SIZE = 128
RECIPE_ID = "scene-only-128-unlabelled-v1"
REPRESENTATION = {
    "id": RECIPE_ID,
    "scene_size": SCENE_SIZE,
    "object_label_size": 0,
    "initial_state": "scene",
    "current_state": "scene",
    "context": "static-only",
    "goal": "source-constraints",
}
SCENE_LEGEND = (
    "Static task context, initial-state scene, current-state scene and partial-goal pages are attached. "
    "Initial/current states are unlabelled 128px scenes without text annotations. "
    "Infer dynamic state from the scene; no symbolic initial/current-state fact panels are included. "
    "Black robot silhouettes identify the agent. "
    "Goal constraints do not describe a complete solved state: unspecified facts are unconstrained. "
    "Goal blocks ALL, ANY, NOT, FOR EVERY and THERE EXISTS retain their labelled variable scopes. "
    "Candidate information and Search Memory are shared across modalities."
)


def static_blocks(blocks):
    return [b for b in blocks["task-context"] if b["id"].partition(":")[0] not in {"initial", "initial_fluent"}]


def _declared_scene_size(manifest):
    value = manifest.get("render_overrides", {}).get("canvas_size", SCENE_SIZE)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("scene-only canvas override must be a positive integer")
    return value


def materialize_task(root, task_id, source_manifest, states, output, progress):
    """Rasterize selected retained vector stages, never ask a planner for scenes."""
    manifest = read_json(root / source_manifest)
    if manifest["task_id"] != task_id:
        raise ValueError("scene-only task/source binding differs")
    catalog = read_json(root / manifest["scene_catalog"])
    scene_size = _declared_scene_size(manifest)
    wanted = set(states) | {0}
    initial = catalog["states"][0]
    if (
        initial["atoms"] != catalog["task_context"]["initial_dynamic_atoms"]
        or initial["fluents"] != catalog["task_context"]["initial_dynamic_fluents"]
    ):
        raise ValueError("scene zero does not represent the authoritative initial state")
    semantic = fact_blocks(catalog["task_context"], initial, manifest["source"])
    recipes = paginate("task-context", static_blocks(semantic))
    output.mkdir(parents=True, exist_ok=True)
    recipe_path = output / "recipe.json"
    recipe_binding = {
        "version": RECIPE_ID,
        "source_manifest": source_manifest,
        "states": sorted(wanted),
        "scene_size": scene_size,
        "label_size": 0,
    }
    if recipe_path.exists():
        retained_recipe = read_json(recipe_path)
        legacy_recipe = {**recipe_binding, "scene_size": SCENE_SIZE}
        if retained_recipe == legacy_recipe and scene_size != SCENE_SIZE:
            write_json(recipe_path, recipe_binding)
        elif retained_recipe != recipe_binding:
            raise ValueError("interrupted scene materialization uses a different recipe/binding")
    write_json(recipe_path, recipe_binding)
    context_paths = []
    for recipe in recipes:
        path = output / f"static-context-{recipe.index}.png"
        if not path.exists():
            image = compose_page(recipe, root)
            temporary = path.with_suffix(".partial.png")
            image.save(temporary)
            temporary.replace(path)
            image.close()
        context_paths.append(str(path.relative_to(root)))
    objects = frozenset(n for ns in catalog["task_context"]["objects_by_type"].values() for n in ns)
    scenes = {}
    scene_bindings = {}
    for binding in catalog["path_bindings"]:
        selected = [(i, s) for i, s in enumerate(binding["state_indices"]) if s in wanted and str(s) not in scenes]
        if not selected:
            continue
        payload = read_json(root / binding["vfg"])
        for stage, state in selected:
            path = output / f"state-{state:06d}.png"
            if not path.exists():
                render_vfg_to_local_png_frames(
                    json.dumps(payload).encode(),
                    output,
                    stage,
                    stage,
                    canvas_size=scene_size,
                    draw_labels=False,
                    object_names=objects,
                )
                (output / "frame_000.png").replace(path)
            with Image.open(path) as image:
                if image.size != (scene_size, scene_size):
                    raise ValueError("scene-only native resolution differs")
            scenes[str(state)] = str(path.relative_to(root))
            scene_bindings[str(state)] = {"vfg": binding["vfg"], "stage": stage}
        progress("scene_views:task", completed=len(scenes), total=len(wanted), task=task_id)
    if {int(i) for i in scenes} != wanted:
        raise ValueError("retained vectors do not cover all requested scene-only states")
    result = {
        "recipe_id": RECIPE_ID,
        "task_id": task_id,
        "view_id": str(output.relative_to(root)),
        "source_manifest": source_manifest,
        "static_blocks": static_blocks(semantic),
        "static_recipes": [r.to_dict() for r in recipes],
        "static_pages": context_paths,
        "goal_pages": manifest["reusable_pages"]["goal"],
        "scenes": scenes,
        "scene_bindings": scene_bindings,
    }
    write_json(output / "task.json", result)
    return result


class SceneOnlyViews:
    def __init__(self, root, tasks, measurements=None, decision_bindings=None):
        self.root, self.tasks = root, tasks
        self.measurements = measurements or {}
        self.decision_bindings = decision_bindings or {}
        self.cache = shared_state_page_cache(root)

    @classmethod
    def load(cls, root, report_path):
        report = read_json(root / report_path)
        if (
            report.get("outcome") != "PASS"
            or not report.get("model_input_ready")
            or not report.get("complete_selected_coverage")
            or report["study"]["state_representation"] != REPRESENTATION
            or any(task.get("recipe_id") != RECIPE_ID for task in report["tasks"].values())
        ):
            raise ValueError("scene-only views require complete verified preparation")
        membership = read_json(root / report["study"]["membership"])
        expected = {
            r
            for key in ("training_record_ids", "diagnostic_record_ids")
            for rows in membership[key].values()
            for r in rows
        }
        if (
            set(report["measurements"]) != expected
            or set(report["decision_bindings"]) != expected
            or report["counts"]["records"] != len(expected)
            or report["counts"]["tasks"] != len(report["tasks"])
            or report["counts"]["states"] != sum(len(t["scenes"]) for t in report["tasks"].values())
        ):
            raise ValueError("scene-only selected coverage is incomplete")
        return cls(root, report["tasks"], report["measurements"], report["decision_bindings"])

    def pages(self, task_id, state, pixels=True, *, current_scene=None):
        task = self.tasks[task_id]
        current_scene = current_scene or task["scenes"][str(state)]
        rows = [("task-context", None, i, p) for i, p in enumerate(task["static_pages"])]
        rows += [("initial-state", 0, 0, task["scenes"]["0"]), ("current-state", state, 0, current_scene)]
        rows += [("goal", None, i, p) for i, p in enumerate(task["goal_pages"])]
        images = []
        for role, bound, i, path in rows:
            image = str(self.root / path)
            if pixels:

                def compose(path=path):
                    with Image.open(self.root / path) as stored:
                        return stored.convert("RGB")

                key = (task["view_id"] + ":" + ("scene" if bound is not None else role), bound or 0, i)
                image = self.cache.get_image(key, compose)
            images.append((role, image))
        return images, [[role, bound, i] for role, bound, i, _ in rows]

    def observe(self, task_id, state, raw, algorithm, semantic, modality, *, pixels=True, current_scene=None):
        pages, bindings = self.pages(
            task_id,
            state,
            pixels=pixels and modality != "text-state",
            current_scene=current_scene,
        )
        messages = project_messages(
            raw, algorithm, modality, semantic, pages, legend=LEGEND if modality == "text-state" else SCENE_LEGEND
        )
        sizes = (
            [
                ((SCENE_SIZE, SCENE_SIZE) if role in {"initial-state", "current-state"} else PAGE_SIZE)
                for role, _ in pages
            ]
            if modality != "text-state"
            else []
        )
        count = frozen_processor().count(messages, image_sizes=sizes)
        if count + 384 > 32768:
            raise RuntimeError("VALID_STOP: scene-only complete input exceeds 32K")
        return {
            "messages": messages,
            "images": [p for _, p in pages] if modality != "text-state" else [],
            "image_sizes": sizes,
            "page_roles": [r for r, _ in pages] if modality != "text-state" else [],
            "binding": {
                "state": state,
                "input_pages": bindings,
                "input_tokens": count,
                "state_representation": RECIPE_ID,
            },
        }

    def training_example(self, corpus, record, modality):
        from .modality_corpus import canonical, project_record

        task = self.tasks[record["task_id"]]
        if record["view_manifest"] != task["source_manifest"]:
            raise ValueError("scene-only record/source binding differs")
        binding = self.decision_bindings[record["record_id"]]
        if any(binding[k] != record[k] for k in ("task_id", "state", "algorithm", "decision_index", "split")):
            raise ValueError("scene-only decision binding differs from source record")
        manifest = read_json(self.root / task["source_manifest"])
        catalog = read_json(self.root / manifest["scene_catalog"])
        project_record(record, manifest, catalog, modality)
        state = catalog["states"][record["state"]]
        validate_process_state(record["authoritative_input"], record["algorithm"], state)
        semantic = fact_blocks(catalog["task_context"], state, manifest["source"])
        example = self.observe(
            record["task_id"], record["state"], record["authoritative_input"], record["algorithm"], semantic, modality
        )
        if example["binding"]["input_pages"] != binding["input_pages"]:
            raise ValueError("scene-only decision page roles differ")
        example["messages"].append({"role": "assistant", "content": canonical(record["target"])})
        return example
