#!/usr/bin/env python
"""Generate, qualify, probe, admit, and evaluate the frozen Goal 11 suites."""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.planning_benchmark_slice import expanded_generalization_eval as gen_eval
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


def evaluate_inputs_stage(root: Path, only: list[str] | None = None) -> dict:
    """Materialize the frozen v2 evaluation bindings from the admission membership."""

    protocol = gen_eval.load_protocol_v2(root)
    admission = gen_eval.load_admission(root, protocol)
    tasks = gen_eval.load_tasks(root, protocol, admission, only=only)
    rows = gen_eval.bindings(tasks, protocol)
    models = [row for row in rows if row["condition"] in gen_eval.GPU_CONDITIONS]
    controls = [row for row in rows if row["condition"] in gen_eval.CPU_CONDITIONS]
    manifest = {
        "schema_version": gen_eval.EVALUATION_INPUTS_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "membership_sha256": admission["membership_sha256"],
        "tasks": [
            {
                "variant_id": task["variant_id"],
                "family": task["family"],
                "task_index": task["task_index"],
                "reference_costs": {
                    algorithm: task["row"]["reference_costs"][algorithm]
                    for algorithm in protocol["learned_algorithms"]
                },
            }
            for task in tasks
        ],
        "bindings": rows,
        "counts": {
            "tasks": len(tasks),
            "bindings": len(rows),
            "model_bindings": len(models),
            "control_bindings": len(controls),
            "episodes_per_task": len(rows) // len(tasks),
        },
    }
    write(output_root(root, protocol) / "evaluation-bindings.json", manifest)
    return {
        "schema_version": gen_eval.EVALUATION_INPUTS_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "membership_sha256": admission["membership_sha256"],
        "counts": manifest["counts"],
    }


def _evaluation_context(root: Path) -> tuple[dict, dict, list, list]:
    protocol = gen_eval.load_protocol_v2(root)
    admission = gen_eval.load_admission(root, protocol)
    manifest = read(output_root(root, protocol) / "evaluation-bindings.json")
    if manifest.get("schema_version") != gen_eval.EVALUATION_INPUTS_SCHEMA:
        raise ValueError("generalization v2 evaluation bindings are missing; run evaluate-inputs first")
    tasks = gen_eval.load_tasks(root, protocol, admission)
    rows = gen_eval.bindings(tasks, protocol)
    if rows != manifest["bindings"]:
        raise ValueError("materialized evaluation bindings differ from the frozen admission membership")
    return protocol, admission, tasks, manifest["bindings"]


def evaluate_worker(root: Path, worker: int, kind: str, endpoint: str) -> dict:
    """Run one partition of the v2 evaluation (models on GPU, controls on CPU)."""

    protocol, _, tasks, rows = _evaluation_context(root)
    protocol["root"] = str(root)
    selected = gen_eval.assigned_bindings(rows, worker, kind)
    kind_conditions = set(gen_eval.GPU_CONDITIONS if kind == gen_eval.MODEL_KIND else gen_eval.CPU_CONDITIONS)
    expected = sum(1 for row in rows if row["condition"] in kind_conditions) // gen_eval.WORKERS
    if len(selected) != expected:
        raise ValueError("generalization v2 worker partition differs from frozen equal coverage")
    if kind == gen_eval.MODEL_KIND:
        if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
            raise ValueError("generalization v2 model worker requires CUDA_VISIBLE_DEVICES isolation")
        if not os.environ.get("MASTER_PORT"):
            raise ValueError("generalization v2 model worker requires an explicit scheduler MASTER_PORT")
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    task_by_id = {task["variant_id"]: task for task in tasks}
    completed = 0
    retained = 0
    model_calls = 0
    reports = []
    started = time.monotonic()
    for modality in protocol["modalities"]:
        modality_bindings = [row for row in selected if row["modality"] == modality]
        pending = [
            row
            for row in modality_bindings
            if not gen_eval.binding_paths(root, protocol, row)[0].exists()
        ]
        policy = None
        adapters = gen_eval.adapter_bank(protocol, modality)
        if kind == gen_eval.MODEL_KIND and pending:
            from transformers import set_seed

            from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
            from examples.planning_benchmark_slice.visual_model import VisualPolicy

            set_seed(int(protocol["training_seed"]))
            policy = VisualPolicy(
                model_id=protocol["model_id"],
                revision=protocol["model_revision"],
                adapter_paths={algorithm: root / path for algorithm, path in adapters.items()},
                device="cuda:0",
                max_context_tokens=32768,
                max_new_tokens=384,
                max_batch_size=protocol["inference"]["max_batch_size"],
                max_batch_input_tokens=protocol["inference"]["max_padded_batch_input_tokens"],
                inference_dtype=protocol["inference"]["dtype"],
            )
            configure_visual_attention(policy.model, protocol["inference"]["attention"])
            policy.identity.update(memoize_identical_inputs=False)
        for binding in modality_bindings:
            condition = binding["condition"]
            checkpoint = str(adapters[binding["algorithm"]]) if condition == "learned_adapter" else None

            def generate(example, condition=condition, algorithm=binding["algorithm"], policy=policy):
                nonlocal model_calls
                if condition in gen_eval.CPU_CONDITIONS:
                    raise AssertionError("control generation is supplied by the authoritative session")
                assert policy is not None
                adapter = algorithm if condition == "learned_adapter" else None
                output = policy.generate([example], adapter)[0]
                model_calls += 1
                return output, policy.last_generation_usage["generated_sequence_tokens"]

            generate_fn = None if kind == gen_eval.CONTROL_KIND else generate
            report, was_retained = gen_eval.run_binding(
                root,
                protocol,
                task_by_id[binding["variant_id"]],
                binding,
                checkpoint,
                endpoint,
                generate_fn,
            )
            retained += int(was_retained)
            reports.append(report["output"])
            completed += 1
            write(
                progress_path,
                {
                    "completed": completed,
                    "total": len(selected),
                    "retained": retained,
                    "model_calls": model_calls,
                    "modality": modality,
                    "condition": condition,
                },
            )
            print(
                {
                    "stage": "generalization_v2_episode",
                    "worker": worker,
                    "kind": kind,
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
        "schema_version": gen_eval.WORKER_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "kind": kind,
        "episodes": reports,
        "completed": completed,
        "retained": retained,
        "model_calls": model_calls,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": os.environ.get("MASTER_PORT"),
        "elapsed_seconds": time.monotonic() - started,
    }
    write(attempt_dir / "worker-result.json", result)
    write(progress_path, {"completed": completed, "total": len(selected), "terminal": True})
    return result


def evaluate_finalize_stage(root: Path, endpoint: str) -> dict:
    """Replay every completed v2 episode and publish the aggregate evaluation."""

    protocol, admission, tasks, rows = _evaluation_context(root)
    task_by_id = {task["variant_id"]: task for task in tasks}
    reports = []
    missing = []
    replayed = 0
    for binding in rows:
        episode, _, _ = gen_eval.binding_paths(root, protocol, binding)
        if not episode.exists():
            missing.append(binding["index"])
            continue
        report = read(episode)
        gen_eval.independently_replay(root, task_by_id[binding["variant_id"]], report, endpoint)
        replayed += 1
        reports.append(report)
    result = {
        "schema_version": gen_eval.EVALUATION_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "membership_sha256": admission["membership_sha256"],
        "outcome": "PASS" if not missing else "INCOMPLETE",
        "bindings": len(rows),
        "episodes_replayed": replayed,
        "missing_bindings": sorted(missing),
        **gen_eval.summarize_reports(reports),
    }
    write(output_root(root, protocol) / "evaluation.json", result)
    return result


def audit_evaluate_worker(root: Path, worker: int, kind: str) -> dict:
    """Scheduler hook: verify one v2 evaluation worker attempt before accepting it."""

    terminal = read(Path(os.environ["EXPANDED_TERMINAL_PATH"]))
    if terminal.get("status") != "succeeded":
        raise RuntimeError("generalization v2 evaluate worker did not terminate cleanly")
    attempt_dir = Path(os.environ["EXPANDED_TERMINAL_PATH"]).parent
    result = read(attempt_dir / "worker-result.json")
    protocol, _, _, rows = _evaluation_context(root)
    selected = gen_eval.assigned_bindings(rows, worker, kind)
    if (
        result.get("schema_version") != gen_eval.WORKER_SCHEMA
        or result.get("protocol_id") != protocol["protocol_id"]
        or result.get("worker") != worker
        or result.get("kind") != kind
    ):
        raise ValueError("generalization v2 worker result provenance differs from the CLI audit arguments")
    if result.get("outcome") != "PASS":
        raise ValueError("generalization v2 worker outcome does not indicate completion")
    if result.get("completed") != len(selected):
        raise ValueError("generalization v2 worker completed count differs from the frozen partition")
    missing_episodes = [
        binding["index"]
        for binding in selected
        if not gen_eval.binding_paths(root, protocol, binding)[0].is_file()
    ]
    if missing_episodes:
        raise ValueError(f"generalization v2 worker is missing episode files: {missing_episodes}")
    summary = {
        "outcome": "PASS",
        "worker": worker,
        "kind": kind,
        "completed": result["completed"],
        "partition": len(selected),
    }
    print(f"PASS: generalization v2 {kind} worker {worker} completed {summary['completed']}/{len(selected)} episodes")
    return summary


def audit_evaluate_final(root: Path) -> dict:
    """Scheduler hook: verify the aggregated v2 evaluation before accepting the chain."""

    protocol, admission, _, rows = _evaluation_context(root)
    evaluation = read(output_root(root, protocol) / "evaluation.json")
    if (
        evaluation.get("schema_version") != gen_eval.EVALUATION_SCHEMA
        or evaluation.get("protocol_id") != protocol["protocol_id"]
        or evaluation.get("membership_sha256") != admission["membership_sha256"]
    ):
        raise ValueError("generalization v2 evaluation provenance differs from the frozen admission")
    if evaluation.get("bindings") != len(rows) or evaluation.get("episodes_replayed") != len(rows):
        raise ValueError("generalization v2 evaluation coverage differs from the frozen bindings")
    if evaluation.get("outcome") != "PASS" or evaluation.get("missing_bindings"):
        raise ValueError("generalization v2 evaluation is incomplete: missing bindings remain")
    by_condition = evaluation.get("by_condition", {})
    models = sum(by_condition[name]["episodes"] for name in gen_eval.GPU_CONDITIONS)
    controls = sum(by_condition[name]["episodes"] for name in gen_eval.CPU_CONDITIONS)
    summary = {
        "outcome": "PASS",
        "model_episodes": models,
        "control_episodes": controls,
        "episodes_replayed": evaluation["episodes_replayed"],
        "bindings": len(rows),
    }
    print(
        f"PASS: generalization v2 evaluation complete: {models} model + {controls} control "
        f"episodes replayed ({evaluation['episodes_replayed']}/{len(rows)} bindings)"
    )
    return summary


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
            "evaluate-inputs",
            "evaluate-worker",
            "evaluate-finalize",
            "audit-evaluate-worker",
            "audit-evaluate-final",
        ),
    )
    parser.add_argument("--worker", type=int, choices=(0, 1))
    parser.add_argument("--kind", choices=("models", "controls"))
    parser.add_argument("--endpoint", default="http://127.0.0.1:18092")
    parser.add_argument("--only", nargs="+", default=None, metavar="VARIANT_ID")
    args = parser.parse_args(argv)
    if args.stage == "probe-worker" and args.worker is None:
        parser.error("probe-worker requires --worker")
    if args.stage == "probe-worker" and args.worker != 0:
        parser.error("probe-worker only supports the frozen probe GPU mapping (worker 0)")
    if args.stage == "evaluate-worker":
        if args.worker is None:
            parser.error("evaluate-worker requires --worker")
        if args.kind is None:
            parser.error("evaluate-worker requires --kind")
    if args.stage == "audit-evaluate-worker":
        if args.worker is None:
            parser.error("audit-evaluate-worker requires --worker")
        if args.kind is None:
            parser.error("audit-evaluate-worker requires --kind")
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
        "evaluate-inputs": lambda: evaluate_inputs_stage(ROOT, only=args.only),
        "evaluate-worker": lambda: evaluate_worker(ROOT, args.worker, args.kind, args.endpoint),
        "evaluate-finalize": lambda: evaluate_finalize_stage(ROOT, args.endpoint),
        "audit-evaluate-worker": lambda: audit_evaluate_worker(ROOT, args.worker, args.kind),
        "audit-evaluate-final": lambda: audit_evaluate_final(ROOT),
    }
    result = actions[args.stage]()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
