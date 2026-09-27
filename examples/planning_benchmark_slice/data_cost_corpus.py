"""#147 data-cost study: nested training sets, scene-only views and decision sufficiency.

Three resumable preparation stages (driven by scripts/data_cost_prepare.py):

- `build_sets`: deterministic round-robin pool per algorithm, scene-only complete-input measurement
  (all three modalities) and nested record-prefix sets; writes training-sets.json and membership.json.
- `prepare_views`: materializes the 128px unlabelled scene-only views for every task touched by the
  16,384-record prefixes (Sokoban VFGs re-anchored by `compact_grid_vfg`) and writes the
  `SceneOnlyViews.load` report.
- `check_sufficiency`: per domain, groups the rendered states of each task by exact RGB pixels and flags
  two distinct dynamic PDDL states with identical pixels as a collision.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict, deque
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations
from pathlib import Path

from PIL import Image

from .modality_corpus import MODALITIES, ModalityCorpus, canonical, iter_shard, project_record
from .modality_pages import fact_blocks, paginate
from .modality_view_preparation import frozen_processor, write_json
from .scene_assets import read_json
from .scene_only_preparation import check_task
from .scene_only_views import RECIPE_ID, REPRESENTATION, SCENE_SIZE, SceneOnlyViews, materialize_task, static_blocks
from .scene_profiles import compact_grid_vfg

STUDY_ID = "data-cost-v1"
ALGORITHMS = ("bfs", "best_first_width")
SIZES = (512, 1024, 2048, 4096, 8192, 16384)
CONTEXT_TOKENS = 32768
OUTPUT_TOKENS = 384
CORPUS_REPORT = "outputs/modality_corpus/issue74-matched-32k-v1/release-001/report.json"
TRAINING_SETS = "configs/experiments/data-cost/training-sets.json"
MEMBERSHIP = "configs/experiments/data-cost/membership.json"
PANEL = "configs/experiments/data-cost/panel.json"
PANEL_VIEWS = "outputs/data-cost/v1/panel/reference-views.json"
PREPARATION = "outputs/data-cost/v1/preparation"
SCENE_VIEWS = f"{PREPARATION}/scene-views.json"
SUFFICIENCY = f"{PREPARATION}/sufficiency.json"
# Renderer-only layout repairs; never applied to any other domain.
VFG_TRANSFORMS = {"sokoban": compact_grid_vfg}
OVER_BOUND = f"scene-only complete input + {OUTPUT_TOKENS} output tokens exceeds {CONTEXT_TOKENS} in >=1 modality"


# ---------------------------------------------------------------- pure selection logic


def task_order(tasks_by_domain: dict[str, list[str]], algorithm: str) -> tuple[list[str], list[str]]:
    """Seeded domain order, seeded task order per domain, interleaved round-robin."""
    domains = sorted(tasks_by_domain)
    random.Random(f"{STUDY_ID}:domains:{algorithm}").shuffle(domains)
    queues = {}
    for domain in domains:
        tasks = sorted(tasks_by_domain[domain])
        random.Random(f"{STUDY_ID}:tasks:{algorithm}:{domain}").shuffle(tasks)
        queues[domain] = deque(tasks)
    order = []
    while any(queues.values()):
        for domain in domains:
            if queues[domain]:
                order.append(queues[domain].popleft())
    return domains, order


def over_bound(counts: dict[str, int]) -> bool:
    """A record is admissible only if every modality's complete input leaves room for the output."""
    return any(counts[m] + OUTPUT_TOKENS > CONTEXT_TOKENS for m in MODALITIES)


def nested_sets(pool: list[dict], inputs: dict[str, dict[str, int]], sizes=SIZES) -> dict:
    """Set N = first N retained pool records; over-bound records are skipped for every modality.

    `pool` rows carry record_id/task_id/domain in pool order; `inputs` maps record ids to per-modality
    input tokens and must cover the pool up to the largest set.
    """
    largest = max(sizes)
    retained, skipped = [], []
    for row in pool:
        if len(retained) == largest:
            break
        counts = inputs[row["record_id"]]
        if over_bound(counts):
            skipped.append({"record_id": row["record_id"], "reason": OVER_BOUND, "input_tokens": counts})
        else:
            retained.append(row)
    if len(retained) < largest:
        raise ValueError(f"pool retains only {len(retained)} records; {largest} required")
    # A task is whole in a set when every retainable (measured, within-bound) record of it is included.
    task_totals = Counter(r["task_id"] for r in pool if r["record_id"] in inputs and not over_bound(inputs[r["record_id"]]))
    sets = {}
    for size in sizes:
        chosen = retained[:size]
        per_task = Counter(r["task_id"] for r in chosen)
        partial = [t for t, n in per_task.items() if n < task_totals[t]]
        domains = Counter(r["domain"] for r in chosen)
        sets[str(size)] = {
            "records": size,
            "record_id_prefix": size,
            "last_record_id": chosen[-1]["record_id"],
            "tasks": {
                "total": len(per_task),
                "whole": len(per_task) - len(partial),
                "partial": len(partial),
                "partial_tasks": [
                    {"task_id": t, "records": per_task[t], "task_retained_records": task_totals[t]} for t in partial
                ],
            },
            "task_ids": list(per_task),
            "domains_covered": len(domains),
            "domain_records": dict(sorted(domains.items())),
        }
    return {"retained": [r["record_id"] for r in retained], "skipped": skipped, "sets": sets}


def pixel_collisions(states: list[dict]) -> dict:
    """Group one task's rendered states by exact pixels.

    Each state row: {state, pixels (bytes key), dynamic (hashable dynamic PDDL state)}. A collision is
    two distinct dynamic states rendered to identical pixels; repeated identical dynamic states are not.
    """
    groups = defaultdict(dict)
    for row in states:
        groups[row["pixels"]].setdefault(row["dynamic"], []).append(row["state"])
    colliding = [sorted(sorted(v) for v in g.values()) for g in groups.values() if len(g) > 1]
    return {
        "states": len(states),
        "distinct_dynamic_states": len({row["dynamic"] for row in states}),
        "distinct_pixel_images": len(groups),
        "colliding_groups": colliding,
        "colliding_pairs": sum(len(list(combinations(g, 2))) for g in colliding),
        "colliding_states": sum(len(v) for g in colliding for v in g),
    }


# ---------------------------------------------------------------- shared helpers


def _progress(stage, **fields):
    print(json.dumps({"stage": stage, **fields}), flush=True)


def _task_dir(task_id: str) -> str:
    return task_id.replace("/", "__")


def _dynamic_key(state: dict):
    return (tuple(sorted(state["atoms"])), canonical(state["fluents"]))


_PROCESSOR = None


def _processor():
    global _PROCESSOR
    if _PROCESSOR is None:
        _PROCESSOR = frozen_processor()
    return _PROCESSOR


class _CountRecorder:
    """Retain the complete-input count `SceneOnlyViews.observe` computes before its 32K guard."""

    def __init__(self, processor):
        self.processor, self.last = processor, None

    def count(self, messages, *, image_sizes=None):
        self.last = self.processor.count(messages, image_sizes=image_sizes)
        return self.last


def _observe_count(views, recorder, task_id, record, semantic, modality):
    recorder.last = None
    try:
        example = views.observe(
            task_id, record["state"], record["authoritative_input"], record["algorithm"], semantic, modality, pixels=False
        )
    except RuntimeError as error:
        if "VALID_STOP" not in str(error) or recorder.last is None:
            raise
        return recorder.last, None
    return example["binding"]["input_tokens"], example


def _layout_task(root: Path, task_id: str, source_manifest: str, manifest: dict, catalog: dict) -> dict:
    """Page layout of the scene-only task without pixels (token counts depend only on page shapes)."""
    semantic = fact_blocks(catalog["task_context"], catalog["states"][0], manifest["source"])
    recipes = paginate("task-context", static_blocks(semantic))
    return {
        "recipe_id": RECIPE_ID,
        "task_id": task_id,
        "view_id": f"layout/{_task_dir(task_id)}",
        "source_manifest": source_manifest,
        "static_pages": [f"layout/static-context-{r.index}.png" for r in recipes],
        "goal_pages": manifest["reusable_pages"]["goal"],
        "scenes": {str(s["index"]): f"layout/state-{s['index']:06d}.png" for s in catalog["states"]},
    }


def _measure_task(args):
    """Scene-only complete-input counts for one task/algorithm's records (cached, idempotent)."""
    root, task_id, algorithm, shard, source_manifest, cache = args
    cache = root / cache
    if cache.exists():
        return read_json(cache)
    manifest = read_json(root / source_manifest)
    catalog = read_json(root / manifest["scene_catalog"])
    recorder = _CountRecorder(_processor())
    views = SceneOnlyViews(
        root, {task_id: _layout_task(root, task_id, source_manifest, manifest, catalog)}, page_processor=recorder
    )
    records = {}
    for record in iter_shard(root / shard):
        if record["algorithm"] != algorithm:
            continue
        if record["view_manifest"] != source_manifest:
            raise ValueError("record/task source manifest differs")
        semantic = fact_blocks(catalog["task_context"], catalog["states"][record["state"]], manifest["source"])
        counts = {m: _observe_count(views, recorder, task_id, record, semantic, m)[0] for m in MODALITIES}
        records[record["record_id"]] = {"input": counts, "target": record["tokens"]["target"]}
    result = {
        "task_id": task_id,
        "algorithm": algorithm,
        "source_manifest": source_manifest,
        "recipe_id": RECIPE_ID,
        "records": records,
    }
    write_json(cache, result)
    return result


def _pool(corpus: ModalityCorpus, algorithm: str) -> tuple[dict, list[dict]]:
    by_task = defaultdict(list)
    for split in ("train", "dev"):
        for record in corpus.records(algorithm=algorithm, split=split):
            by_task[record["task_id"]].append(
                {
                    "record_id": record["record_id"],
                    "task_id": record["task_id"],
                    "domain": record["domain"],
                    "decision_index": record["decision_index"],
                    "target": record["tokens"]["target"],
                }
            )
    tasks_by_domain = defaultdict(list)
    for task_id, rows in by_task.items():
        tasks_by_domain[corpus.results[task_id]["domain"]].append(task_id)
        rows.sort(key=lambda r: r["decision_index"])
    domains, order = task_order(tasks_by_domain, algorithm)
    pool = [row for task_id in order for row in by_task[task_id]]
    meta = {
        "records": len(pool),
        "tasks": len(order),
        "domain_order": domains,
        "task_order": order,
        "sha256": hashlib.sha256("\n".join(r["record_id"] for r in pool).encode()).hexdigest(),
    }
    return meta, pool


# ---------------------------------------------------------------- stage 1: sets


def build_sets(root: Path, workers: int = 6, progress=_progress) -> dict:
    corpus = ModalityCorpus(root, root / CORPUS_REPORT)
    largest = max(SIZES)
    report = {
        "schema": "data_cost_training_sets_v1",
        "study_id": STUDY_ID,
        "corpus_report": CORPUS_REPORT,
        "splits_admitted": ["train", "dev"],
        "sizes": list(SIZES),
        "context_tokens": CONTEXT_TOKENS,
        "output_tokens": OUTPUT_TOKENS,
        "state_representation": REPRESENTATION,
        "vfg_transforms": {d: f.__name__ for d, f in VFG_TRANSFORMS.items()},
        "skip_rule": OVER_BOUND,
        "algorithms": {},
    }
    membership = {
        "schema": "data_cost_membership_v1",
        "study_id": STUDY_ID,
        "corpus_report": CORPUS_REPORT,
        "training_sets": TRAINING_SETS,
        "training_record_ids": {},
        "diagnostic_record_ids": {},
    }
    with ProcessPoolExecutor(max_workers=workers) as pool_executor:
        for algorithm in ALGORITHMS:
            meta, pool = _pool(corpus, algorithm)
            if max(r["target"] for r in pool) > OUTPUT_TOKENS:
                raise ValueError("a pool target exceeds the frozen output budget")
            rows_by_task = defaultdict(list)
            for row in pool:
                rows_by_task[row["task_id"]].append(row)
            inputs, retained, futures = {}, 0, deque()
            tasks = deque(meta["task_order"])

            def submit(task_id, algorithm=algorithm):
                result = corpus.results[task_id]
                cache = f"{PREPARATION}/measurements/{algorithm}/{_task_dir(task_id)}.json"
                args = (root, task_id, algorithm, result["path"], result["view_manifest"], cache)
                return task_id, pool_executor.submit(_measure_task, args)

            # Measure tasks in pool order with a bounded look-ahead; stop once the largest set is full.
            while retained < largest:
                while tasks and len(futures) < 2 * workers:
                    futures.append(submit(tasks.popleft()))
                if not futures:
                    break
                task_id, future = futures.popleft()
                measured = future.result()["records"]
                if set(measured) != {r["record_id"] for r in rows_by_task[task_id]}:
                    raise ValueError("measured records differ from the pool task records")
                for row in rows_by_task[task_id]:
                    inputs[row["record_id"]] = measured[row["record_id"]]["input"]
                    if retained < largest and not over_bound(inputs[row["record_id"]]):
                        retained += 1
                progress("sets:measure", algorithm=algorithm, task=task_id, retained=retained, total=largest)
            for _, future in futures:
                future.cancel()
            selection = nested_sets(pool, inputs, SIZES)
            measured_prefix = next(i for i, r in enumerate(pool) if r["record_id"] == selection["retained"][-1]) + 1
            report["algorithms"][algorithm] = {
                "pool": {**meta, "measured_prefix_records": measured_prefix},
                "retained": len(selection["retained"]),
                "skipped": selection["skipped"],
                "sets": selection["sets"],
            }
            membership["training_record_ids"][algorithm] = selection["retained"]
            membership["diagnostic_record_ids"][algorithm] = []
    write_json(root / TRAINING_SETS, report)
    write_json(root / MEMBERSHIP, membership)
    return report


# ---------------------------------------------------------------- stage 2: views


def _materialize(args):
    root, task_id, source, states, output, domain = args
    return materialize_task(
        root, task_id, source, states, root / output, lambda *a, **k: None, vfg_transform=VFG_TRANSFORMS.get(domain)
    )


def _measure_views(args):
    """Measure every membership record of one materialized task against its real pages (cached)."""
    root, task, records, cache = args
    cache = root / cache
    # JSON-normalized so tuple/list differences in the fresh task never defeat the cache.
    binding = json.loads(json.dumps({"task": task, "record_ids": [r["record_id"] for r in records]}))
    if cache.exists():
        retained = read_json(cache)
        if retained["binding"] == binding:
            return retained["measurements"], retained["decision_bindings"]
    task_id = task["task_id"]
    manifest = read_json(root / task["source_manifest"])
    catalog = read_json(root / manifest["scene_catalog"])
    processor = _processor()
    views = SceneOnlyViews(root, {task_id: task}, page_processor=processor)
    measurements, bindings = {}, {}
    for record in records:
        semantic = fact_blocks(catalog["task_context"], catalog["states"][record["state"]], manifest["source"])
        counts = {}
        for modality in MODALITIES:
            example = views.observe(
                task_id, record["state"], record["authoritative_input"], record["algorithm"], semantic, modality, pixels=False
            )
            if modality == "text-state" and example["messages"] != project_record(record, manifest, catalog, modality):
                raise ValueError("scene-only views changed the text-state input")
            full = [*example["messages"], {"role": "assistant", "content": canonical(record["target"])}]
            if processor.count(full, image_sizes=example["image_sizes"]) > CONTEXT_TOKENS:
                raise RuntimeError("VALID_STOP: scene-only supervised input exceeds 32K")
            counts[modality] = example["binding"]["input_tokens"]
        measurements[record["record_id"]] = {"input": counts, "target": record["tokens"]["target"]}
        bindings[record["record_id"]] = {
            **{k: record[k] for k in ("task_id", "state", "algorithm", "decision_index", "split")},
            "input_pages": example["binding"]["input_pages"],
        }
    write_json(cache, {"binding": binding, "measurements": measurements, "decision_bindings": bindings})
    return measurements, bindings


def prepare_views(root: Path, workers: int = 6, progress=_progress) -> dict:
    membership = read_json(root / MEMBERSHIP)
    corpus = ModalityCorpus(root, root / CORPUS_REPORT)
    wanted = {r for rows in membership["training_record_ids"].values() for r in rows}
    records = {}
    for algorithm in ALGORITHMS:
        for split in ("train", "dev"):
            for record in corpus.records(algorithm=algorithm, split=split):
                if record["record_id"] in wanted:
                    records[record["record_id"]] = record
    if set(records) != wanted:
        raise ValueError("membership records are missing from the corpus")
    required = {}
    for record in records.values():
        task = required.setdefault(record["task_id"], {"source": record["view_manifest"], "states": set()})
        if task["source"] != record["view_manifest"]:
            raise ValueError("task records use different source manifests")
        task["states"].add(record["state"])
    output = f"{PREPARATION}/{RECIPE_ID}"
    tasks = {}
    by_task = defaultdict(list)
    for record_id in (r for rows in membership["training_record_ids"].values() for r in rows):
        by_task[records[record_id]["task_id"]].append(records[record_id])
    with ProcessPoolExecutor(max_workers=workers) as executor:
        jobs = [
            (root, t, r["source"], r["states"], f"{output}/{_task_dir(t)}", corpus.results[t]["domain"])
            for t, r in required.items()
        ]
        for task in executor.map(_materialize, jobs):
            tasks[task["task_id"]] = task
            progress("views:materialize", task=task["task_id"], completed=len(tasks), total=len(required))
        for task_id, task in tasks.items():
            check_task(root, task, required[task_id]["states"])
        measurements, bindings = {}, {}
        jobs = [
            (root, tasks[t], rows, f"{PREPARATION}/view-measurements/{_task_dir(t)}.json") for t, rows in by_task.items()
        ]
        for measured, bound in executor.map(_measure_views, jobs):
            measurements.update(measured)
            bindings.update(bound)
            progress("views:measure", completed=len(measurements), total=len(records))
    # Set membership was chosen from layout-only counts; the real pages must agree exactly.
    for algorithm in ALGORITHMS:
        for task_id in {records[r]["task_id"] for r in membership["training_record_ids"][algorithm]}:
            cache = read_json(root / PREPARATION / "measurements" / algorithm / f"{_task_dir(task_id)}.json")
            for record_id, measured in cache["records"].items():
                if record_id in wanted and measurements[record_id] != measured:
                    raise ValueError(f"real scene-only pages change the set measurement of {record_id}")
    # Complete-processor cross-check with real pixels, once per algorithm and modality.
    processor = _processor()
    views = SceneOnlyViews(root, tasks, page_processor=processor)
    cross_checked = []
    for algorithm in ALGORITHMS:
        record = records[membership["training_record_ids"][algorithm][0]]
        manifest = read_json(root / tasks[record["task_id"]]["source_manifest"])
        catalog = read_json(root / manifest["scene_catalog"])
        semantic = fact_blocks(catalog["task_context"], catalog["states"][record["state"]], manifest["source"])
        for modality in MODALITIES:
            actual = views.observe(
                record["task_id"], record["state"], record["authoritative_input"], algorithm, semantic, modality
            )
            processor.verify_complete(actual["messages"], actual["images"])
            cross_checked.append([algorithm, modality])
    report = {
        "study": {
            "study_id": STUDY_ID,
            "state_representation": REPRESENTATION,
            "membership": MEMBERSHIP,
            "training_sets": TRAINING_SETS,
            "corpus_report": CORPUS_REPORT,
            "algorithms": list(ALGORITHMS),
            "vfg_transforms": {d: f.__name__ for d, f in VFG_TRANSFORMS.items()},
        },
        "outcome": "PASS",
        "complete_selected_coverage": True,
        "model_input_ready": True,
        "tasks": dict(sorted(tasks.items())),
        "measurements": measurements,
        "decision_bindings": bindings,
        "text_inputs_unchanged": True,
        "set_measurements_reproduced": True,
        "processor_cross_checks": cross_checked,
        "max_input_tokens": {m: max(v["input"][m] for v in measurements.values()) for m in MODALITIES},
        "counts": {
            "records": len(measurements),
            "tasks": len(tasks),
            "states": sum(len(t["scenes"]) for t in tasks.values()),
        },
    }
    write_json(root / SCENE_VIEWS, report)
    progress("views:complete", counts=report["counts"])
    return report


# ---------------------------------------------------------------- stage 3: sufficiency


def _hash_task(args):
    root, source, task_id, domain, scenes, source_manifest = args
    manifest = read_json(root / source_manifest)
    catalog = read_json(root / manifest["scene_catalog"])
    rows = []
    for state, path in scenes.items():
        with Image.open(root / path) as image:
            if image.size != (SCENE_SIZE, SCENE_SIZE):
                raise ValueError("sufficiency requires 128px scenes")
            pixels = hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()
        rows.append({"state": int(state), "pixels": pixels, "dynamic": _dynamic_key(catalog["states"][int(state)])})
    result = pixel_collisions(rows)
    return {"source": source, "task_id": task_id, "domain": domain, **result}


def check_sufficiency(root: Path, workers: int = 6, progress=_progress) -> dict:
    views = read_json(root / SCENE_VIEWS)
    corpus = read_json(root / CORPUS_REPORT)
    domain_of = {r["task_id"]: r["domain"] for r in corpus["results"]}
    jobs = [
        (root, "training", t, domain_of[t], task["scenes"], task["source_manifest"]) for t, task in views["tasks"].items()
    ]
    panel_included = (root / PANEL).exists() and (root / PANEL_VIEWS).exists()
    if panel_included:
        panel_tasks = {t["row"]["task_id"] for t in read_json(root / PANEL)["tasks"]}
        for task in read_json(root / PANEL_VIEWS)["tasks"]:
            native = task["native_views"]
            if task["row"]["task_id"] not in panel_tasks:
                raise ValueError("panel views cover a task outside panel.json")
            jobs.append(
                (root, "panel", task["row"]["task_id"], task["row"]["domain"], native["scenes"], native["source_manifest"])
            )
    with ProcessPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(_hash_task, jobs))
    domains = {}
    for domain in sorted({r["domain"] for r in results}):
        rows = [r for r in results if r["domain"] == domain]
        states = sum(r["states"] for r in rows)
        colliding = sum(r["colliding_states"] for r in rows)
        examples = [
            {"source": r["source"], "task_id": r["task_id"], "state_groups": g}
            for r in rows
            for g in r["colliding_groups"]
        ]
        domains[domain] = {
            "verdict": "PASS" if not examples else "FAIL",
            "tasks": {s: sum(r["source"] == s for r in rows) for s in ("training", "panel")},
            "states": states,
            "states_by_source": {s: sum(r["states"] for r in rows if r["source"] == s) for s in ("training", "panel")},
            "distinct_dynamic_states": sum(r["distinct_dynamic_states"] for r in rows),
            "colliding_groups": len(examples),
            "colliding_pairs": sum(r["colliding_pairs"] for r in rows),
            "colliding_states": colliding,
            "collision_rate": colliding / states,
            "by_source": {
                s: {
                    "states": sum(r["states"] for r in rows if r["source"] == s),
                    "colliding_pairs": sum(r["colliding_pairs"] for r in rows if r["source"] == s),
                    "colliding_states": sum(r["colliding_states"] for r in rows if r["source"] == s),
                }
                for s in ("training", "panel")
            },
            "examples": [e for s in ("training", "panel") for e in [x for x in examples if x["source"] == s][:10]],
        }
    report = {
        "schema": "data_cost_sufficiency_v1",
        "study_id": STUDY_ID,
        "scene_views": SCENE_VIEWS,
        "panel": PANEL if panel_included else None,
        "panel_views": PANEL_VIEWS if panel_included else None,
        "panel_included": panel_included,
        "definition": (
            "within each task, rendered 128px unlabelled RGB scenes grouped by exact pixel content; a collision is "
            "two distinct dynamic PDDL states (atoms+fluents) with identical pixels; collision_rate = states in a "
            "colliding group / rendered states"
        ),
        "outcome": "PASS" if all(d["verdict"] == "PASS" for d in domains.values()) else "FAIL",
        "domains": domains,
    }
    write_json(root / SUFFICIENCY, report)
    progress("sufficiency:complete", outcome=report["outcome"], panel_included=panel_included)
    return report
