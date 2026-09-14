#!/usr/bin/env python
"""Prepare new-task reference scenes and complete projected reference inputs."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write
from examples.planning_benchmark_slice.expanded_views import reference_catalog
from examples.planning_benchmark_slice.modality_pages import compose_page, fact_blocks, paginate
from examples.planning_benchmark_slice.modality_view_preparation import _state_goal_checks, frozen_processor, write_json
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.scene_assets import collect_task_scenes, read_json
from examples.planning_benchmark_slice.scene_only_views import materialize_task, SceneOnlyViews
from examples.planning_benchmark_slice.source_goal import source_task


def prepare_task(protocol, group, index):
    import torch

    torch.set_num_threads(2)
    candidate = group["selected"]
    row = dict(candidate["row"])
    name = f"{group['domain']}-{group['stratum']}-{candidate['seed']}"
    output = ROOT / protocol["output_root"] / "views" / name
    saved = output / "result.json"
    if saved.exists():
        result = read(saved)
        if result["protocol"] != protocol or result["row"] != row:
            raise ValueError("retained view preparation binding differs")
        return result
    refs = {
        a: str((ROOT / protocol["output_root"] / "candidates" / name / f"reference-{a}.json.gz").relative_to(ROOT))
        for a in protocol["reference"]["algorithms"]
    }

    def progress(stage, **fields):
        print(dict(stage=stage, **{"task": row["task_id"], **fields}), flush=True)

    catalog = reference_catalog(ROOT, row, refs, protocol["study_id"])
    task = read(ROOT / row["task_path"])
    source = source_task(task["domain_pddl"], task["problem_pddl"])
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    _state_goal_checks(authority, catalog, source)
    scene_output = output / "scenes"
    if not (scene_output / "catalog.json.gz").exists():
        if scene_output.exists():
            number = 1
            while scene_output.with_name(f"scenes-interrupted-{number}").exists():
                number += 1
            scene_output.rename(scene_output.with_name(f"scenes-interrupted-{number}"))
        profiles = read(ROOT / "configs/experiments/issue71/v2/render.json")["domain_profiles"]
        collect_task_scenes(
            root=ROOT,
            row=row,
            profile=ROOT / profiles[row["domain"]],
            endpoint=f"http://127.0.0.1:{18092+index%4}",
            output=scene_output,
            timeout=30,
            preflight=False,
            progress=lambda detail: progress("render", detail=detail),
            catalog=catalog,
        )
    catalog = read_json(scene_output / "catalog.json.gz")
    goal_recipes = paginate("goal", fact_blocks(catalog["task_context"], catalog["states"][0], source)["goal"])
    goal_paths = []
    for recipe in goal_recipes:
        path = output / f"goal-{recipe.index}.png"
        image = compose_page(recipe, ROOT)
        image.save(path)
        image.close()
        goal_paths.append(str(path.relative_to(ROOT)))
    manifest_path = output / "manifest.json"
    write(
        manifest_path,
        dict(
            task_id=row["task_id"],
            split="test",
            scene_catalog=str((scene_output / "catalog.json.gz").relative_to(ROOT)),
            source=source,
            task_context=catalog["task_context"],
            reusable_pages={"goal": goal_paths},
            reusable_recipes={"goal": [r.to_dict() for r in goal_recipes]},
            reference_costs=row["reference_costs"],
            complete_reference_coverage=True,
            full_reachable_closure=False,
        ),
    )
    native = materialize_task(
        ROOT,
        row["task_id"],
        str(manifest_path.relative_to(ROOT)),
        range(len(catalog["states"])),
        output / "unlabelled",
        progress,
    )
    views = SceneOnlyViews(ROOT, {row["task_id"]: native})
    processor = frozen_processor()
    measurements = []
    modalities = ["text-state", "visual-state", "multimodal-state"]
    for algorithm, path in refs.items():
        reference = read_json(ROOT / path)
        positions = [d["state"] for d in catalog["decisions"] if d["algorithm"] == algorithm]
        for position, event in enumerate(reference["events"]):
            state = positions[position]
            semantic = fact_blocks(catalog["task_context"], catalog["states"][state], source)
            counts = {}
            for modality in modalities:
                example = views.observe(
                    row["task_id"], state, event["input"], algorithm, semantic, modality, pixels=position == 0
                )
                counts[modality] = example["binding"]["input_tokens"]
                if position == 0:
                    processor.verify_complete(example["messages"], example["images"])
                    for image in example["images"]:
                        image.close()
            measurements.append(dict(algorithm=algorithm, index=position, state=state, input_tokens=counts))
        progress(
            "reference_inputs", algorithm=algorithm, completed=len(reference["events"]), total=len(reference["events"])
        )
    result = dict(
        protocol=protocol,
        row=row,
        reference_paths=refs,
        native_views=native,
        measurements=measurements,
        states=len(catalog["states"]),
        reference_input_maxima={m: max(r["input_tokens"][m] for r in measurements) for m in modalities},
        outcome="REFERENCE_VIEWS_PASS",
        complete_live_input_bounds=False,
        hardware_qualified=False,
    )
    write(saved, result)
    return result


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("stage", choices=("prepare", "audit"))
    args = parser.parse_args()
    protocol = read(ROOT / "configs/experiments/expanded-study/panel-protocol-v2.json")
    path = ROOT / protocol["output_root"] / "reference-views.json"
    if args.stage == "audit":
        terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
        if terminal["status"] != "succeeded":
            raise RuntimeError(f"reference views failed: {terminal['directory']}/worker.log")
        report = read(path)
        assert len(report["tasks"]) == 24
        assert all(t["outcome"] == "REFERENCE_VIEWS_PASS" for t in report["tasks"])
        print("PASS: reference scenes and input projections; complete live bounds and GPU qualification pending")
        return
    selection = read(ROOT / protocol["output_root"] / "structural-selection.json")
    if selection["selected_count"] != 24 or selection["missing_strata"]:
        raise ValueError("all 24 structural strata required before view preparation")
    tasks = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(prepare_task, protocol, g, i) for i, g in enumerate(selection["strata"])]
        for future in as_completed(futures):
            tasks.append(future.result())
            write(os.environ["EXPANDED_PROGRESS_PATH"], dict(completed=len(tasks)))
    tasks.sort(key=lambda t: t["row"]["task_id"])
    write(path, dict(protocol=protocol, tasks=tasks, complete_live_input_bounds=False, hardware_qualified=False))


if __name__ == "__main__":
    main()
