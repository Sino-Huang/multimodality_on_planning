"""Prepare and independently check the selected scene-only model inputs."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed

from PIL import Image

from .matched_preparation import audit_training
from .modality_corpus import MODALITIES, ModalityCorpus, canonical, project_record
from .modality_pages import PAGE_SIZE, fact_blocks, paginate
from .modality_view_preparation import frozen_processor, write_json
from .scene_assets import read_json
from .scene_only_views import RECIPE_ID, REPRESENTATION, SCENE_SIZE, SceneOnlyViews, materialize_task, static_blocks


def selected_records(root, study):
    corpus = ModalityCorpus(root, root / study["corpus_report"])
    membership = read_json(root / study["membership"])
    records = []
    for algorithm in study["algorithms"]:
        for split, key in (("train", "training_record_ids"), ("dev", "diagnostic_record_ids")):
            wanted = membership[key][algorithm]
            selected = {
                r["record_id"]: r
                for r in corpus.records(algorithm=algorithm, split=split)
                if r["record_id"] in set(wanted)
            }
            if set(selected) != set(wanted):
                raise ValueError("scene-only source membership is incomplete")
            records.extend(selected[i] for i in wanted)
    if len(records) != 2156 or len({r["record_id"] for r in records}) != 2156:
        raise ValueError("scene-only source record coverage differs")
    return corpus, records


def _materialize(args):
    root, task_id, source, states, output = args
    return materialize_task(root, task_id, source, states, output, lambda *a, **k: None)


def check_task(root, task, wanted):
    manifest = read_json(root / task["source_manifest"])
    catalog = read_json(root / manifest["scene_catalog"])
    semantic = fact_blocks(catalog["task_context"], catalog["states"][0], manifest["source"])
    expected = static_blocks(semantic)
    if (
        task.get("recipe_id") != RECIPE_ID
        or manifest["task_id"] != task["task_id"]
        or task["static_blocks"] != expected
        or canonical(task["static_recipes"]) != canonical([r.to_dict() for r in paginate("task-context", expected)])
        or task["goal_pages"] != manifest["reusable_pages"]["goal"]
        or {int(i) for i in task["scenes"]} != set(wanted) | {0}
    ):
        raise ValueError("scene-only static/goal/state coverage differs")
    for path in task["static_pages"] + task["goal_pages"]:
        with Image.open(root / path) as image:
            if image.size != PAGE_SIZE:
                raise ValueError("scene-only context/goal size differs")
    for state, path in task["scenes"].items():
        bound = task["scene_bindings"][state]
        binding = next(b for b in catalog["path_bindings"] if b["vfg"] == bound["vfg"])
        if binding["state_indices"][bound["stage"]] != int(state):
            raise ValueError("scene-only state/vector binding differs")
        with Image.open(root / path) as image:
            if image.size != (SCENE_SIZE, SCENE_SIZE):
                raise ValueError("scene-only raster size differs")


def prepare(root, study, progress, workers=4, *, check=False):
    if study["state_representation"] != REPRESENTATION:
        raise ValueError("scene-only representation differs from implemented drawing/input contract")
    previous = read_json(root / study["preparation_predecessor"])
    predecessor = root / previous["output_root"] / "preparation"
    source_report = read_json(predecessor / "report.json")
    panel = read_json(predecessor / "final-panel.json")
    if source_report["outcome"] != "PASS" or panel["study"] != previous or previous["final"] != study["final"]:
        raise ValueError("scene-only preparation requires the same qualified final tasks")
    # The trusted source audit remains independent of the new pixels.
    source_audit = audit_training(root, study, progress)
    corpus, records = selected_records(root, study)
    required = {}
    for record in records:
        task = required.setdefault(record["task_id"], {"source": record["view_manifest"], "states": set()})
        task["states"].add(record["state"])
    for task in panel["tasks"]:
        required[task["row"]["task_id"]] = {"source": task["view_manifest"], "states": set(range(task["states"]))}
    output = root / study["output_root"] / "preparation"
    if check:
        report = read_json(root / study["scene_views"])
        if report["study"] != study or not report["complete_selected_coverage"] or report["outcome"] != "PASS":
            raise ValueError("scene-only preparation report is incomplete or mismatched")
        tasks = report["tasks"]
    else:
        tasks = {}
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    _materialize,
                    (root, task_id, r["source"], r["states"], output / RECIPE_ID / task_id.replace("/", "__")),
                )
                for task_id, r in required.items()
            ]
            for future in as_completed(futures):
                task = future.result()
                tasks[task["task_id"]] = task
                progress("scene_views:materialize", completed=len(tasks), total=len(required))
    if set(tasks) != set(required):
        raise ValueError("scene-only task coverage differs")
    for task_id, task in tasks.items():
        check_task(root, task, required[task_id]["states"])
    views = SceneOnlyViews(root, tasks)
    measurements = {}
    decision_bindings = {}
    processor = frozen_processor()
    current_task = None
    cross_checked = set()
    previews = {}
    for record in records:
        task_id = record["task_id"]
        if task_id != current_task:
            manifest = read_json(root / tasks[task_id]["source_manifest"])
            catalog = read_json(root / manifest["scene_catalog"])
            current_task = task_id
        semantic = fact_blocks(catalog["task_context"], catalog["states"][record["state"]], manifest["source"])
        counts = {}
        for modality in MODALITIES:
            example = views.observe(
                task_id,
                record["state"],
                record["authoritative_input"],
                record["algorithm"],
                semantic,
                modality,
                pixels=False,
            )
            legacy = project_record(record, manifest, catalog, modality)
            if modality == "text-state" and example["messages"] != legacy:
                raise ValueError("scene-only revision changed the already-trained text input")
            counts[modality] = example["binding"]["input_tokens"]
            # Include the target and chat template in the supervised-input check.
            full = [*example["messages"], {"role": "assistant", "content": canonical(record["target"])}]
            if processor.count(full, image_sizes=example["image_sizes"]) > 32768:
                raise RuntimeError("VALID_STOP: scene-only supervised input exceeds 32K")
            if (record["algorithm"], modality) not in cross_checked:
                actual = views.observe(
                    task_id, record["state"], record["authoritative_input"], record["algorithm"], semantic, modality
                )
                processor.verify_complete(actual["messages"], actual["images"])
                for image in actual["images"]:
                    image.close()
                cross_checked.add((record["algorithm"], modality))
        measurements[record["record_id"]] = {"input": counts, "target": record["tokens"]["target"]}
        decision_bindings[record["record_id"]] = {
            k: record[k] for k in ("task_id", "state", "algorithm", "decision_index", "split")
        }
        decision_bindings[record["record_id"]]["input_pages"] = example["binding"]["input_pages"]
        domain = corpus.results[task_id]["domain"]
        if domain not in previews or counts["visual-state"] > previews[domain]["input_tokens"]:
            previews[domain] = {"task_id": task_id, "state": record["state"], "input_tokens": counts["visual-state"]}
        progress("scene_views:measure", completed=len(measurements), total=len(records))
    final_measurements = {}
    for task in panel["tasks"]:
        task_id = task["row"]["task_id"]
        manifest = read_json(root / tasks[task_id]["source_manifest"])
        catalog = read_json(root / manifest["scene_catalog"])
        rows = []
        for previous_row in task["measurements"]:
            algorithm, index, state = (previous_row[k] for k in ("algorithm", "index", "state"))
            event = read_json(root / task["row"]["reference_paths"][algorithm])["events"][index]
            semantic = fact_blocks(catalog["task_context"], catalog["states"][state], manifest["source"])
            counts = {
                m: views.observe(task_id, state, event["input"], algorithm, semantic, m, pixels=False)["binding"][
                    "input_tokens"
                ]
                for m in MODALITIES
            }
            rows.append({**previous_row, "input_tokens": counts})
        final_measurements[task_id] = rows
        previews[task_id] = {
            "task_id": task_id,
            "state": max(catalog["states"], key=lambda s: len(s["atoms"]))["index"],
            "input_tokens": max(r["input_tokens"]["visual-state"] for r in rows),
        }
    result = {
        "study": study,
        "outcome": "PASS",
        "complete_selected_coverage": True,
        "model_input_ready": True,
        "source_audit": source_audit,
        "tasks": tasks,
        "measurements": measurements,
        "decision_bindings": decision_bindings,
        "final_measurements": final_measurements,
        "text_inputs_unchanged": True,
        "processor_cross_checks": [list(x) for x in sorted(cross_checked)],
        "counts": {
            "records": len(records),
            "tasks": len(tasks),
            "states": sum(len(t["scenes"]) for t in tasks.values()),
            "final_states": sum(t["states"] for t in panel["tasks"]),
        },
        "preview_selection": previews,
    }
    if check:
        if result != report:
            raise ValueError("scene-only read-only verification differs from preparation")
    else:
        for name, preview in previews.items():
            pages, _ = views.pages(preview["task_id"], preview["state"])
            folder = output / "previews" / name.replace("/", "__")
            folder.mkdir(parents=True, exist_ok=True)
            for i, (role, image) in enumerate(pages):
                processed = processor.preview(image)
                processed.save(folder / f"{i:02d}-{role}.png")
                image.close()
                processed.close()
        write_json(root / study["scene_views"], result)
    progress("scene_views:complete", completed=len(records), total=len(records), outcome="PASS", counts=result["counts"])
    return result
