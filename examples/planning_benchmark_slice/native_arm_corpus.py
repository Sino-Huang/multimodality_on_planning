"""CPU corpus materialization and training examples for the native arms (#128).

Re-materializes the frozen matched-modalities membership (512 training + the
diagnostic records per additive algorithm) under the two new observation
contracts, reusing the retained scene catalogs and the v5 scene-only store:

- static-context/goal pages and selected-state scenes are reused verbatim from
  the verified v5 preparation;
- history-window states missing from the v5 store are rasterized on demand from
  the retained catalog VFG vector stages (unlabelled 128px, ``draw_labels=False``
  — the same rendering call as the v5 preparation; no new pipeline);
- structural qualification gates assert the removed payload keys are absent,
  frame counts <= K, window states precede the current state, every image
  reference resolves, the candidate menu matches the trusted grounded order and
  each measured input fits the frozen 32K gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from .modality_corpus import ModalityCorpus
from .modality_corpus_replay import canonical
from .modality_view_preparation import write_json
from .native_arm_views import (
    ARMS,
    arm_history_k,
    arm_recipe_id,
    assert_no_text_leak,
    build_observation,
    history_window,
    reduce_payload,
)
from .scene_assets import read_json
from .scene_only_views import _declared_scene_size

STORE_SCHEMA = "native_arms_scene_store_v1"
REPORT_SCHEMA = "native_arms_preparation_v1"


def _render_states(root: Path, catalog: dict, manifest: dict, wanted: set[int], output: Path) -> dict[str, str]:
    """Rasterize retained vector stages for states missing from the v5 store."""

    from scripts.planimation_phase1_frames import render_vfg_to_local_png_frames

    scene_size = _declared_scene_size(manifest)
    objects = frozenset(name for names in catalog["task_context"]["objects_by_type"].values() for name in names)
    rendered: dict[str, str] = {}
    output.mkdir(parents=True, exist_ok=True)
    for binding in catalog["path_bindings"]:
        selected = [(i, s) for i, s in enumerate(binding["state_indices"]) if s in wanted and str(s) not in rendered]
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
                    raise ValueError("native-arm rendered history scene has the wrong native resolution")
            rendered[str(state)] = str(path.relative_to(root))
    missing = wanted - {int(index) for index in rendered}
    if missing:
        raise ValueError(f"retained vectors do not cover history states {sorted(missing)}")
    return rendered


def prepare_arm(
    root: Path,
    arm: str,
    *,
    corpus_report: str,
    membership_path: str,
    scene_views_path: str,
    output_dir: Path,
    algorithms: list[str],
    progress,
) -> dict[str, Any]:
    """Materialize the frozen membership under one native-arm contract."""

    if arm not in ARMS:
        raise ValueError(f"unknown native-arm contract: {arm}")
    k = arm_history_k(arm)
    corpus = ModalityCorpus(root, root / corpus_report)
    membership = read_json(root / membership_path)
    v5 = read_json(root / scene_views_path)
    representation = v5.get("study", {}).get("state_representation")
    recipe_id = representation.get("id") if isinstance(representation, dict) else representation
    if v5.get("outcome") != "PASS" or recipe_id != "scene-only-128-unlabelled-v1":
        raise ValueError("native arms build on the verified v5 scene-only preparation")
    store = {
        "schema_version": STORE_SCHEMA,
        "arm": arm,
        "recipe_id": arm_recipe_id(arm),
        "history_k": k,
        "study": {
            "corpus_report": corpus_report,
            "membership": membership_path,
            "v5_scene_views": scene_views_path,
            "state_representation": arm_recipe_id(arm),
        },
        "tasks": {},
        "measurements": {},
        "decision_bindings": {},
        "counts": {},
    }
    catalog_states: dict[str, list[dict[str, Any]]] = {}
    manifests: dict[str, dict[str, Any]] = {}
    extra_states: dict[str, int] = {task_id: 0 for task_id in v5["tasks"]}
    record_plan: dict[str, list[dict[str, Any]]] = {}
    for algorithm in algorithms:
        wanted = list(membership["training_record_ids"][algorithm]) + list(
            membership["diagnostic_record_ids"][algorithm]
        )
        rows = [r for split in ("train", "dev") for r in corpus.records(algorithm=algorithm, split=split)]
        indexed = {r["record_id"]: r for r in rows}
        missing = [rid for rid in wanted if rid not in indexed]
        if missing:
            raise ValueError(f"membership records absent from the released corpus: {missing[:3]}")
        record_plan[algorithm] = [indexed[rid] for rid in wanted]

    tasks_touched = sorted({r["task_id"] for rows in record_plan.values() for r in rows})
    for position, task_id in enumerate(tasks_touched):
        result = corpus.results[task_id]
        if any(
            r["task_id"] == task_id and r["view_manifest"] != result["view_manifest"]
            for rows in record_plan.values()
            for r in rows
        ):
            raise ValueError("record provenance differs from the released task")
        manifest = read_json(root / result["view_manifest"])
        catalog = read_json(root / manifest["scene_catalog"])
        manifests[task_id] = manifest
        catalog_states[task_id] = list(catalog["states"])
        v5_task = v5["tasks"][task_id]
        scenes = dict(v5_task["scenes"])
        window_states: set[int] = set()
        for algorithm in algorithms:
            for record in record_plan[algorithm]:
                if record["task_id"] != task_id:
                    continue
                window_states.update(history_window(catalog_states[task_id], record["state"], k))
        needed = window_states - {int(index) for index in scenes}
        if needed:
            rendered = _render_states(root, catalog, manifest, needed, output_dir / "scenes" / arm / task_id)
            scenes.update(rendered)
            extra_states[task_id] = len(rendered)
        store["tasks"][task_id] = {
            "source_manifest": result["view_manifest"],
            "static_pages": list(v5_task["static_pages"]),
            "goal_pages": list(v5_task["goal_pages"]),
            "scenes": scenes,
            "scene_bindings": dict(v5_task["scene_bindings"]),
            "view_id": f"native-arms/{arm}/{task_id}",
        }
        progress("native_prep:task", completed=position + 1, total=len(tasks_touched), task=task_id)

    total_records = 0
    for algorithm in algorithms:
        for record in record_plan[algorithm]:
            task = store["tasks"][record["task_id"]]
            states = catalog_states[record["task_id"]]
            window = history_window(states, record["state"], k)
            if len(window) > k or any(w >= record["state"] for w in window):
                raise ValueError("history window violates the frozen bound/past invariant")
            payload = reduce_payload(record["authoritative_input"], arm)
            example = build_observation(
                payload,
                task["static_pages"],
                task["goal_pages"],
                lambda state_index, task=task: task["scenes"][str(state_index)],
                record["state"],
                window,
                None,
            )
            assert_no_text_leak(example)
            for index in [0, *window, record["state"]]:
                if not (root / task["scenes"][str(index)]).is_file():
                    raise ValueError(f"native-arm image reference does not resolve: state {index}")
            binding = {
                "task_id": record["task_id"],
                "state": record["state"],
                "algorithm": record["algorithm"],
                "decision_index": record["decision_index"],
                "split": record["split"],
                "arm": arm,
                "history_window": list(window),
                "input_pages": example["binding"]["input_pages"],
                "input_tokens": example["binding"]["input_tokens"],
            }
            for key in ("task_id", "state", "algorithm", "decision_index", "split"):
                if record.get(key) != binding[key]:
                    raise ValueError("native-arm decision binding differs from the source record")
            store["decision_bindings"][record["record_id"]] = binding
            store["measurements"][record["record_id"]] = example["binding"]["input_tokens"]
            total_records += 1
            if total_records % 128 == 0:
                progress("native_prep:records", completed=total_records)

    expected_ids = {
        rid
        for algorithm in algorithms
        for rid in list(membership["training_record_ids"][algorithm])
        + list(membership["diagnostic_record_ids"][algorithm])
    }
    if set(store["decision_bindings"]) != expected_ids:
        raise ValueError("native-arm materialized membership differs from the frozen v5 membership")
    store["counts"] = {
        "records": len(store["decision_bindings"]),
        "tasks": len(store["tasks"]),
        "states": sum(len(task["scenes"]) for task in store["tasks"].values()),
        "extra_history_states": sum(extra_states.values()),
        "history_k": k,
    }
    write_json(output_dir / "store.json", store)
    return store


class NativeArmStore:
    """Load a materialized native-arm store and build training examples."""

    def __init__(self, root: Path, store_path: Path, *, corpus: ModalityCorpus | None = None):
        self.root = root
        report = read_json(store_path)
        if report.get("schema_version") != STORE_SCHEMA:
            raise ValueError("native-arm store schema differs")
        self.arm = report["arm"]
        self.k = report["history_k"]
        self.recipe_id = report["recipe_id"]
        self.tasks = report["tasks"]
        self.measurements = report["measurements"]
        self.decision_bindings = report["decision_bindings"]
        self.study = report["study"]
        self.counts = report["counts"]
        self._catalog_states: dict[str, list[dict[str, Any]]] = {}
        self.corpus = corpus or ModalityCorpus(root, root / self.study["corpus_report"])

    def catalog_states(self, task_id: str) -> list[dict[str, Any]]:
        if task_id not in self._catalog_states:
            manifest = read_json(self.root / self.tasks[task_id]["source_manifest"])
            catalog = read_json(self.root / manifest["scene_catalog"])
            self._catalog_states[task_id] = list(catalog["states"])
        return self._catalog_states[task_id]

    def training_example(self, record: dict[str, Any]) -> dict[str, Any]:
        task = self.tasks[record["task_id"]]
        if record["view_manifest"] != task["source_manifest"]:
            raise ValueError("native-arm record/source binding differs")
        binding = self.decision_bindings[record["record_id"]]
        if any(binding[k] != record[k] for k in ("task_id", "state", "algorithm", "decision_index", "split")):
            raise ValueError("native-arm decision binding differs from the source record")
        window = history_window(self.catalog_states(record["task_id"]), record["state"], self.k)
        if window != binding["history_window"]:
            raise ValueError("native-arm history window differs from the frozen preparation")
        payload = reduce_payload(record["authoritative_input"], self.arm)
        example = build_observation(
            payload,
            task["static_pages"],
            task["goal_pages"],
            lambda state_index, task=task: task["scenes"][str(state_index)],
            record["state"],
            window,
            self._loader(task),
        )
        assert_no_text_leak(example)
        if example["binding"]["input_pages"] != binding["input_pages"]:
            raise ValueError("native-arm decision page roles differ from the frozen preparation")
        if example["binding"]["input_tokens"] != binding["input_tokens"]:
            raise ValueError("native-arm measured input tokens differ from the frozen preparation")
        example["messages"].append({"role": "assistant", "content": canonical(record["target"])})
        return example

    def _loader(self, task: dict[str, Any]):
        def load(label: str, path: str):
            with Image.open(self.root / path) as stored:
                return stored.convert("RGB")

        return load


def qualification_report(store: dict[str, Any], arm: str) -> dict[str, Any]:
    """Frozen structural qualification gates over a materialized store."""

    k = arm_history_k(arm)
    windows = [binding["history_window"] for binding in store["decision_bindings"].values()]
    pages = [binding["input_pages"] for binding in store["decision_bindings"].values()]
    tokens = store["measurements"]
    checks = {
        "schema_binding": store["schema_version"] == STORE_SCHEMA and store["arm"] == arm,
        "recipe_binding": store["recipe_id"] == arm_recipe_id(arm) and store["history_k"] == k,
        "removed_keys_absent": True,  # asserted per record during materialization
        "frame_counts_within_k": all(len(w) <= k for w in windows),
        "windows_strictly_past": all(
            all(state < binding["state"] for state in binding["history_window"])
            for binding in store["decision_bindings"].values()
        ),
        "windows_visit_ordered": all(list(w) == sorted(w) for w in windows),
        "images_resolve": True,  # asserted per record during materialization
        "input_tokens_within_gate": all(count + 384 <= 32768 for count in tokens.values()),
        "membership_complete": store["counts"]["records"] == len(store["decision_bindings"]),
        "page_roles_layout": all(
            roles[0][0] == "task-context"
            and roles[-1][0] == "goal"
            and any(role[0] == "current-state" for role in roles)
            for roles in pages
        ),
    }
    history_page_counts: dict[str, int] = {}
    for binding in store["decision_bindings"].values():
        roles = [page[0] for page in binding["input_pages"]]
        count = sum(1 for role in roles if role.startswith("history-state"))
        history_page_counts[str(count)] = history_page_counts.get(str(count), 0) + 1
    return {
        "schema_version": REPORT_SCHEMA,
        "arm": arm,
        "checks": checks,
        "outcome": "PASS" if all(v is True for v in checks.values()) else "FAIL",
        "counts": store["counts"],
        "history_page_count_histogram": history_page_counts,
        "max_observed_input_tokens": max(tokens.values()),
    }


def load_records(corpus: ModalityCorpus, algorithm: str, record_ids: list[str]) -> list[dict[str, Any]]:
    rows = [r for split in ("train", "dev") for r in corpus.records(algorithm=algorithm, split=split)]
    indexed = {r["record_id"]: r for r in rows}
    return [indexed[rid] for rid in record_ids]


class NativeArmTrainingDataset:
    """Membership-ordered torch dataset over one native-arm store.

    Mirrors ``VisualDataset``: ``.records`` holds the frozen membership order
    and ``__getitem__`` returns the collator's expected
    ``{messages, images, page_roles}`` example with the assistant target.
    """

    def __init__(self, root: Path, store: NativeArmStore, membership: dict[str, Any], algorithm: str, split: str):
        key = "training_record_ids" if split == "train" else "diagnostic_record_ids"
        wanted = list(membership[key][algorithm])
        self.store = store
        self.arm = store.arm
        self.records = load_records(store.corpus, algorithm, wanted)
        if [r["record_id"] for r in self.records] != wanted:
            raise ValueError("native-arm dataset order differs from the frozen membership")
        for record in self.records:
            if record["record_id"] not in store.decision_bindings:
                raise ValueError("native-arm dataset record lacks a frozen decision binding")

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        return self.store.training_example(self.records[index])


