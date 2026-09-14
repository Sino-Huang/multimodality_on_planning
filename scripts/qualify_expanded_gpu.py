#!/usr/bin/env python
"""Bounded capacity/timing probes; generated text is retained but never scored."""

import argparse
import copy
import gc
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write
from examples.planning_benchmark_slice.modality_pages import fact_blocks
from examples.planning_benchmark_slice.modality_view_preparation import frozen_processor
from examples.planning_benchmark_slice.scene_assets import read_json
from examples.planning_benchmark_slice.scene_only_views import SceneOnlyViews


def capacity_example(tasks, modality):
    task = max(
        tasks,
        key=lambda t: (
            len(t["native_views"]["static_pages"]) + len(t["native_views"]["goal_pages"]),
            t["reference_input_maxima"][modality],
        ),
    )
    measurement = max(task["measurements"], key=lambda m: m["input_tokens"][modality])
    event = read_json(ROOT / task["reference_paths"][measurement["algorithm"]])["events"][measurement["index"]]
    views = SceneOnlyViews(ROOT, {task["row"]["task_id"]: task["native_views"]})
    manifest = read_json(ROOT / task["native_views"]["source_manifest"])
    catalog = read_json(ROOT / manifest["scene_catalog"])
    semantic = fact_blocks(catalog["task_context"], catalog["states"][measurement["state"]], manifest["source"])
    example = views.observe(
        task["row"]["task_id"], measurement["state"], event["input"], measurement["algorithm"], semantic, modality
    )
    return task["row"]["task_id"], example


def pad_capacity(example, target):
    result = dict(example, messages=copy.deepcopy(example["messages"]))
    result["messages"][-1]["content"].append({"type": "text", "text": ""})
    text = result["messages"][-1]["content"][-1]
    processor = frozen_processor()
    lo, hi = 0, target
    while lo <= hi:
        mid = (lo + hi) // 2
        text["text"] = "\nUnscored capacity probe; repeat x." + " x" * mid
        count = processor.count(result["messages"], image_sizes=result["image_sizes"])
        if count == target:
            return result
        if count < target:
            lo = mid + 1
        else:
            hi = mid - 1
    raise ValueError(f"could not construct exact {target}-token capacity input")


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("stage", choices=("run", "audit", "prepare"))
    args = parser.parse_args()
    folder = Path(os.environ.get("EXPANDED_ATTEMPT_DIR", "/tmp/expanded-capacity-inputs"))
    if args.stage == "audit":
        terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
        folder = Path(terminal["directory"])
        if terminal["status"] != "succeeded":
            raise RuntimeError(f"GPU capacity probe failed: {folder}/worker.log")
        report = read(folder / "qualification.json")
        assert len(report["modalities"]) == 3
        for m in report["modalities"]:
            assert len(m["cases"]) == 4
            assert all(c["generated_tokens"] == 384 for c in m["cases"])
            assert m["cases"][0]["input_tokens"] == [32384]
            assert m["cases"][1]["input_tokens"] == [12000, 12000]
        print("PASS: complete single/batch input caps, image geometry, all modality adapter banks, fixed full output")
        return
    tasks = read(ROOT / "outputs/expanded-study/v1/panel-v2/reference-views.json")["tasks"]
    study = read(ROOT / "configs/experiments/matched-modalities/study-v5.json")
    checkpoints = read(ROOT / "docs/experiments/expanded-study/readiness.json")["checkpoints"]
    processor = frozen_processor()
    results = []
    completed = 0
    for modality in study["modalities"]:
        task_id, example = capacity_example(tasks, modality)
        maximum = max(t["reference_input_maxima"][modality] for t in tasks)
        # Padding is synthetic capacity stress; none of these are evaluated episodes.
        single = pad_capacity(example, 32384)
        batch = pad_capacity(example, 12000)
        reference = pad_capacity(example, maximum + 32)
        if args.stage == "prepare":
            for e in (single, batch, reference):
                processor.verify_complete(e["messages"], e["images"])
            print(
                dict(
                    modality=modality,
                    single=processor.count(single["messages"], image_sizes=single["image_sizes"]),
                    image_sizes=single["image_sizes"],
                    reference_envelope=maximum + 32,
                ),
                flush=True,
            )
            for image in example["images"]:
                image.close()
            continue
        import torch
        from examples.planning_benchmark_slice.visual_model import VisualPolicy
        from examples.planning_benchmark_slice.visual_attention import configure_visual_attention

        adapters = {c["algorithm"]: str(ROOT / c["checkpoint"]) for c in checkpoints if c["modality"] == modality}
        then = time.monotonic()
        policy = VisualPolicy(
            model_id=study["model_id"],
            revision=study["model_revision"],
            adapter_paths=adapters,
            device="cuda:0",
            max_context_tokens=32768,
            max_new_tokens=384,
            max_batch_size=2,
            max_batch_input_tokens=32384,
        )
        configure_visual_attention(policy.model, "visual_sdpa")
        for adapter in adapters:
            with policy._adapter_context(adapter):
                pass
        load_seconds = time.monotonic() - then
        cases = []
        for name, examples, adapter in [
            ("single_limit", [single], None),
            ("batch_limit", [batch, batch], "bfs"),
            ("reference_envelope_base", [reference, reference], None),
            ("reference_envelope_sft", [reference, reference], "bfs"),
        ]:
            policy.max_batch_input_tokens = 32384 if name == "single_limit" else 24000
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            started = time.monotonic()
            outputs = policy.generate(examples, adapter_id=adapter, force_full_output=True)
            torch.cuda.synchronize()
            usage = policy.last_generation_usage
            case = dict(
                name=name,
                seconds=time.monotonic() - started,
                input_tokens=usage["input_tokens"],
                generated_tokens=usage["generated_sequence_tokens"],
                batch_size=len(examples),
                peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                raw_capacity_outputs=outputs,
                scored=False,
            )
            cases.append(case)
            write(folder / f"{modality}-{name}.json", case)
            completed += 1
            write(os.environ["EXPANDED_PROGRESS_PATH"], dict(completed=completed))
            print({k: v for k, v in case.items() if k != "raw_capacity_outputs"}, flush=True)
        results.append(
            dict(
                modality=modality,
                source_task=task_id,
                image_sizes=example["image_sizes"],
                reference_envelope_tokens=maximum + 32,
                adapters=adapters,
                load_seconds=load_seconds,
                cases=cases,
            )
        )
        del policy
        gc.collect()
        torch.cuda.empty_cache()
        for image in example["images"]:
            image.close()
    if args.stage == "run":
        write(
            folder / "qualification.json",
            dict(
                modalities=results,
                outcome="PASS",
                scored_model_episodes=0,
                cuda_visible_devices=os.environ["CUDA_VISIBLE_DEVICES"],
                master_port=os.environ["MASTER_PORT"],
            ),
        )


if __name__ == "__main__":
    main()
