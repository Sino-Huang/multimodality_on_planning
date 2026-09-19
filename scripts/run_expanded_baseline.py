#!/usr/bin/env python
"""Execute one fixed partition of the expanded baseline with safe episode resume."""

import argparse
import gc
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_baseline import (  # noqa: E402
    assigned_bindings,
    binding_paths,
    checkpoint_bank,
    run_binding,
    validate_protocol,
)
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("stage", choices=("prepare", "run"))
    parser.add_argument("--config", type=Path, default=ROOT / "configs/experiments/expanded-study/baseline-protocol.json")
    parser.add_argument("--worker", type=int, required=True)
    parser.add_argument("--kind", choices=("controls", "models"), required=True)
    args = parser.parse_args(argv)
    protocol = read(args.config)
    protocol["root"] = str(ROOT)
    panel, study, readiness = validate_protocol(ROOT, protocol)
    selected = assigned_bindings(panel, protocol, args.worker, args.kind)
    expected = protocol["logical_bindings"] // protocol["workers"] // 2
    if len(selected) != expected:
        raise ValueError("worker partition differs from frozen equal coverage")
    endpoint = protocol["endpoints"][args.worker]
    task_by_id = {task["row"]["task_id"]: task for task in read(ROOT / panel["view_report"])["tasks"]}
    if set(task_by_id) != {task["row"]["task_id"] for task in panel["tasks"]}:
        raise ValueError("expanded view tasks differ from frozen panel")
    if args.stage == "prepare":
        existing = sum(binding_paths(ROOT, protocol, binding)[0].exists() for binding in selected)
        print(
            {
                "outcome": "PASS",
                "worker": args.worker,
                "kind": args.kind,
                "bindings": len(selected),
                "existing": existing,
                "model_loads": 0,
                "model_calls": 0,
            }
        )
        return 0
    if args.kind == "models":
        if os.environ.get("CUDA_VISIBLE_DEVICES") != str(protocol["physical_gpus"][args.worker]):
            raise ValueError("scheduler GPU isolation differs from frozen worker mapping")
        if not os.environ.get("MASTER_PORT"):
            raise ValueError("expanded model worker requires an explicit scheduler MASTER_PORT")
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    completed = 0
    retained = 0
    model_calls = 0
    reports = []
    started = time.monotonic()
    for modality in protocol["modalities"]:
        modality_bindings = [binding for binding in selected if binding["modality"] == modality]
        pending = [binding for binding in modality_bindings if not binding_paths(ROOT, protocol, binding)[0].exists()]
        policy = None
        adapters = checkpoint_bank(ROOT, protocol, readiness, modality)
        if args.kind == "models" and pending:
            from transformers import set_seed
            from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
            from examples.planning_benchmark_slice.visual_model import VisualPolicy

            set_seed(protocol["evaluation_seed"])
            policy = VisualPolicy(
                model_id=protocol["model_id"],
                revision=protocol["model_revision"],
                adapter_paths=adapters,
                device="cuda:0",
                max_context_tokens=protocol["context_tokens"],
                max_new_tokens=protocol["output_tokens"],
                max_batch_size=protocol["inference"]["max_batch_size"],
                max_batch_input_tokens=protocol["inference"]["max_padded_batch_input_tokens"],
            )
            configure_visual_attention(policy.model, protocol["inference"]["attention"])
            policy.identity.update(memoize_identical_inputs=False)
        for binding in modality_bindings:
            condition = binding["condition"]
            checkpoint = (
                str(Path(adapters[binding["algorithm"]]).relative_to(ROOT))
                if condition == "process_sft"
                else None
            )

            def generate(example, condition=condition, algorithm=binding["algorithm"]):
                nonlocal model_calls
                if condition in {"random_valid", "exact_reference"}:
                    raise AssertionError("control generation is supplied by the authoritative session")
                assert policy is not None
                output = policy.generate([example], algorithm if condition == "process_sft" else None)[0]
                model_calls += 1
                return output, policy.last_generation_usage["generated_sequence_tokens"]

            task = task_by_id[binding["task_id"]]
            generate_fn = None if condition in {"random_valid", "exact_reference"} else generate
            report, was_retained = run_binding(
                ROOT, protocol, task, binding, checkpoint, endpoint, generate_fn
            )
            retained += int(was_retained)
            reports.append(report["output"])
            completed += 1
            elapsed = time.monotonic() - started
            write(
                progress_path,
                {
                    "completed": completed,
                    "total": len(selected),
                    "retained": retained,
                    "model_calls": model_calls,
                    "modality": modality,
                    "eta_seconds": elapsed * (len(selected) - completed) / completed,
                },
            )
            print(
                {
                    "stage": "baseline_episode",
                    "worker": args.worker,
                    "kind": args.kind,
                    "completed": completed,
                    "total": len(selected),
                    "binding_index": binding["index"],
                    "retained": was_retained,
                    "result": report["result"]["termination_reason"],
                },
                flush=True,
            )
        if policy is not None:
            del policy
            gc.collect()
            import torch

            torch.cuda.empty_cache()
    result = {
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "worker": args.worker,
        "kind": args.kind,
        "episodes": reports,
        "completed": completed,
        "retained": retained,
        "model_calls": model_calls,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": os.environ.get("MASTER_PORT"),
        "elapsed_seconds": time.monotonic() - started,
    }
    write(ROOT / protocol["output_root"] / "workers" / f"{args.kind}-{args.worker}.json", result)
    write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
