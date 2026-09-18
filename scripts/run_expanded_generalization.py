#!/usr/bin/env python
"""Generate, qualify, probe, and admit the frozen Goal 11 suites."""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.planning_benchmark_slice.expanded_generalization import load_protocol
from examples.planning_benchmark_slice.expanded_generalization_run import (
    PROBE_PERSIST_FIELDS,
    admit_stage,
    audit_stage,
    freeze_stage,
    generate_stage,
    output_root,
    probe_finalize_stage,
    probe_inputs_stage,
    read,
    screen_stage,
    validate_stage,
    write,
)
from examples.planning_benchmark_slice.expanded_scheduler import ROOT
from examples.planning_benchmark_slice.expanded_views import ExpandedTaskViews
from examples.planning_benchmark_slice.visual_episode import VisualSession


def _probe_example(root, protocol, probe, endpoint, output):
    task = probe["task"]
    views = ExpandedTaskViews(root, task, output, endpoint, read_only=True)
    session = VisualSession(
        root,
        task["row"],
        probe["algorithm"],
        "process_sft",
        17,
        output,
        protocol["protocol_id"],
        views=views,
    )
    request = session.next_request()
    if request is None:
        raise ValueError("probe task produced no model request")
    return views.observe(dict(request.model_input), probe["algorithm"], modality=probe["modality"])


def probe_worker(root: Path, worker: int) -> dict:
    """Time frozen first calls through the existing VisualPolicy loading path."""

    protocol = load_protocol(root)
    if worker != 0 or os.environ.get("CUDA_VISIBLE_DEVICES") != "0":
        raise ValueError("generalization probe worker differs from the frozen GPU mapping")
    inputs = read(output_root(root, protocol) / "probe-inputs.json")["inputs"]
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    endpoint = "http://127.0.0.1:18092"
    measurements = []
    load_seconds = 0.0
    save_seconds = 0.0
    for modality in protocol["modalities"]:
        from transformers import set_seed

        from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
        from examples.planning_benchmark_slice.visual_model import VisualPolicy

        adapters = {
            row["algorithm"]: root / row["checkpoint"]
            for row in protocol["fixed_adapters"]
            if row["modality"] == modality
        }
        started = time.monotonic()
        set_seed(17)
        policy = VisualPolicy(
            model_id=protocol["model_id"],
            revision=protocol["model_revision"],
            adapter_paths=adapters,
            device="cuda:0",
            max_context_tokens=32768,
            max_new_tokens=384,
            max_batch_size=protocol["inference"]["max_batch_size"],
            max_batch_input_tokens=protocol["inference"]["max_padded_batch_input_tokens"],
            inference_dtype=protocol["inference"]["dtype"],
        )
        configure_visual_attention(policy.model, protocol["inference"]["attention"])
        load_seconds += time.monotonic() - started
        modality_inputs = [row for row in inputs if row["modality"] == modality]
        for algorithm in protocol["algorithms"]:
            algorithm_inputs = [row for row in modality_inputs if row["algorithm"] == algorithm]
            examples = [
                _probe_example(
                    root,
                    protocol,
                    row,
                    endpoint,
                    attempt_dir / "views" / row["probe_id"].replace(":", "__"),
                )
                for row in algorithm_inputs
            ]
            try:
                for _sample in range(protocol["throughput_probe"]["timing_samples_per_probe_input"]):
                    for offset in range(0, len(examples), protocol["inference"]["max_batch_size"]):
                        batch, bound = examples[offset : offset + 2], algorithm_inputs[offset : offset + 2]
                        started = time.monotonic()
                        outputs = policy.generate(batch, algorithm)
                        elapsed = time.monotonic() - started
                        usage = policy.last_generation_usage
                        del outputs
                        for row, _example, input_tokens in zip(bound, batch, usage["input_tokens"], strict=True):
                            measurement = {
                                "call_wall_seconds": elapsed,
                                "input_tokens": input_tokens,
                                "output_tokens": usage["generated_sequence_tokens"],
                                "algorithm": algorithm,
                                "modality": modality,
                                "family": row["family"],
                                "batch_size": len(batch),
                            }
                            if set(measurement) != PROBE_PERSIST_FIELDS - {
                                "worker",
                                "model_load_wall_seconds",
                                "model_save_wall_seconds",
                            }:
                                raise ValueError("probe worker metadata differs from the frozen whitelist")
                            measurements.append(measurement)
            finally:
                for example in examples:
                    for image in example["images"]:
                        image.close()
        started = time.monotonic()
        del policy
        gc.collect()
        import torch

        torch.cuda.empty_cache()
        save_seconds += time.monotonic() - started
    if len(measurements) != protocol["throughput_probe"]["timing_calls"]:
        raise ValueError("probe worker timing-call coverage differs")
    result = {
        "schema_version": "expanded_generalization_probe_worker_v1",
        "outcome": "PASS",
        "worker": worker,
        "measurements": measurements,
        "worker_overheads": [
            {
                "worker": worker,
                "model_load_wall_seconds": load_seconds,
                "model_save_wall_seconds": save_seconds,
            }
        ],
    }
    write(attempt_dir / "probe-worker.json", result)
    if os.environ.get("EXPANDED_PROGRESS_PATH"):
        write(Path(os.environ["EXPANDED_PROGRESS_PATH"]), {"completed": len(measurements), "total": len(measurements)})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "validate",
            "generate",
            "screen",
            "audit",
            "freeze",
            "probe-inputs",
            "probe-worker",
            "probe-finalize",
            "admit",
        ),
    )
    parser.add_argument("--worker", type=int, choices=(0,))
    parser.add_argument("--endpoint", default="http://127.0.0.1:18092")
    parser.add_argument("--only", nargs="+", default=None, metavar="VARIANT_ID")
    args = parser.parse_args(argv)
    if args.stage == "probe-worker" and args.worker is None:
        parser.error("probe-worker requires --worker")
    actions = {
        "validate": lambda: validate_stage(ROOT),
        "generate": lambda: generate_stage(ROOT),
        "screen": lambda: screen_stage(ROOT),
        "audit": lambda: audit_stage(ROOT, endpoint=args.endpoint, only=args.only),
        "freeze": lambda: freeze_stage(ROOT),
        "probe-inputs": lambda: probe_inputs_stage(ROOT),
        "probe-worker": lambda: probe_worker(ROOT, args.worker),
        "probe-finalize": lambda: probe_finalize_stage(ROOT),
        "admit": lambda: admit_stage(ROOT),
    }
    result = actions[args.stage]()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
