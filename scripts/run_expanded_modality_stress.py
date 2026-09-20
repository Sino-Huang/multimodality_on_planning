#!/usr/bin/env python
"""Validate, admit, evaluate, replay and analyze the frozen modality-stress suite (#126)."""

from __future__ import annotations

import argparse
import gc
import json
import os
import random
import time
from pathlib import Path

from examples.planning_benchmark_slice import expanded_modality_stress as stress
from examples.planning_benchmark_slice.modality_view_preparation import write_json
from examples.planning_benchmark_slice.scene_assets import read_json

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_SEED = 90717
BOOTSTRAP_RESAMPLES = 10000
TINY_STRATUM_LIMIT = 8


def read(path: Path) -> dict:
    return read_json(path)


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, value)


def output_root(root: Path, protocol: dict) -> Path:
    return root / protocol["output_root"]


def validate_stage(root: Path) -> dict:
    """Fail closed on every frozen modality-stress design dependency."""

    protocol = stress.load_protocol(root)
    admission = stress.load_admission(root, protocol)
    tasks = stress.load_panel_tasks(root, protocol)
    rows = stress.bindings(tasks, protocol)
    audit = protocol["comparator_audit"]
    for key in ("baseline_protocol", "baseline_evaluation", "baseline_independent_replay"):
        if not (root / audit[key]).is_file():
            raise ValueError(f"missing comparator audit artifact: {audit[key]}")
    import hashlib

    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    if (
        sha256(root / audit["baseline_protocol"]) != audit["baseline_protocol_sha256"]
        or sha256(root / audit["baseline_evaluation"]) != audit["baseline_evaluation_sha256"]
        or sha256(root / audit["baseline_independent_replay"]) != audit["baseline_independent_replay_sha256"]
    ):
        raise ValueError("comparator audit evidence sha256 differs from the frozen pins")
    replay = read(root / audit["baseline_independent_replay"])
    evaluation = read(root / audit["baseline_evaluation"])
    if (
        evaluation.get("outcome") != "PASS"
        or evaluation.get("complete_coverage") is not True
        or replay.get("outcome") != "PASS"
        or replay.get("episodes_replayed") != replay.get("expected_episodes")
    ):
        raise ValueError("reused baseline comparator evidence is not complete and replay-verified")
    for adapter in protocol["fixed_adapters"]:
        if not (root / adapter["checkpoint"] / "adapter_model.safetensors").is_file():
            raise ValueError(f"missing verified adapter: {adapter['checkpoint']}")
    comparators = stress.comparator_bindings(protocol, tasks)
    expected_comparators = len(tasks) * (3 * 2 * 2 + 2 * 2)
    if len(comparators) != expected_comparators:
        raise ValueError("comparator binding enumeration is incomplete")
    return {
        "schema_version": "expanded_modality_stress_validation_v1",
        "protocol_id": protocol["protocol_id"],
        "outcome": "PASS",
        "source_tasks": len(tasks),
        "bindings": len(rows),
        "comparator_episodes": len(comparators),
        "membership_sha256": admission["membership_sha256"],
    }


def evaluate_inputs_stage(root: Path) -> dict:
    """Materialize the frozen stress evaluation bindings from the admission membership."""

    protocol = stress.load_protocol(root)
    admission = stress.load_admission(root, protocol)
    tasks = stress.load_panel_tasks(root, protocol)
    rows = stress.bindings(tasks, protocol)
    models = [row for row in rows if row["kind"] == stress.MODEL_KIND]
    controls = [row for row in rows if row["kind"] == stress.CONTROL_KIND]
    manifest = {
        "schema_version": stress.EVALUATION_INPUTS_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "membership_sha256": admission["membership_sha256"],
        "tasks": [
            {
                "task_id": task["row"]["task_id"],
                "domain": task["row"]["domain"],
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
        "schema_version": stress.EVALUATION_INPUTS_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "membership_sha256": admission["membership_sha256"],
        "counts": manifest["counts"],
    }


def _evaluation_context(root: Path) -> tuple[dict, dict, list, list]:
    protocol = stress.load_protocol(root)
    admission = stress.load_admission(root, protocol)
    manifest = read(output_root(root, protocol) / "evaluation-bindings.json")
    if manifest.get("schema_version") != stress.EVALUATION_INPUTS_SCHEMA:
        raise ValueError("modality-stress evaluation bindings are missing; run evaluate-inputs first")
    tasks = stress.load_panel_tasks(root, protocol)
    rows = stress.bindings(tasks, protocol)
    if rows != manifest["bindings"]:
        raise ValueError("materialized evaluation bindings differ from the frozen admission membership")
    return protocol, admission, tasks, manifest["bindings"]


def evaluate_worker(root: Path, worker: int, kind: str, endpoint: str) -> dict:
    """Run one partition of the stress evaluation (models on GPU, controls on CPU)."""

    protocol, _, tasks, rows = _evaluation_context(root)
    protocol["root"] = str(root)
    selected = stress.assigned_bindings(rows, worker, kind)
    expected = sum(1 for row in rows if row["kind"] == kind) // stress.WORKERS
    if len(selected) != expected:
        raise ValueError("modality-stress worker partition differs from frozen equal coverage")
    if kind == stress.MODEL_KIND:
        if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
            raise ValueError("modality-stress model worker requires CUDA_VISIBLE_DEVICES isolation")
        if not os.environ.get("MASTER_PORT"):
            raise ValueError("modality-stress model worker requires an explicit scheduler MASTER_PORT")
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    completed = 0
    retained = 0
    model_calls = 0
    reports = []
    started = time.monotonic()
    if kind == stress.MODEL_KIND:
        # GPU bindings are grouped by modality so each backbone load serves its two adapters.
        modality_order = ["text-state", "visual-state", "multimodal-state"]
        groups = [
            (modality, [row for row in selected if row["modality"] == modality]) for modality in modality_order
        ]
    else:
        groups = [(None, list(selected))]
    for modality, group in groups:
        pending = [row for row in group if not stress.binding_paths(root, protocol, row)[0].exists()]
        policy = None
        adapters = stress.adapter_bank(protocol, modality) if modality else {}
        if kind == stress.MODEL_KIND and pending:
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
        for binding in group:
            condition = binding["condition"]
            checkpoint = str(adapters[binding["algorithm"]]) if condition == "learned_adapter" else None

            def generate(example, condition=condition, algorithm=binding["algorithm"], policy=policy):
                nonlocal model_calls
                if kind == stress.CONTROL_KIND:
                    raise AssertionError("control generation is supplied by the authoritative session")
                assert policy is not None
                adapter = algorithm if condition == "learned_adapter" else None
                output = policy.generate([example], adapter)[0]
                model_calls += 1
                return output, policy.last_generation_usage["generated_sequence_tokens"]

            generate_fn = None if kind == stress.CONTROL_KIND else generate
            report, was_retained = stress.run_binding(
                root,
                protocol,
                task_by_id[binding["task_id"]],
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
                    "stage": "modality_stress_episode",
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
        "schema_version": stress.WORKER_SCHEMA,
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


def _paired_analysis(protocol: dict, tasks: list[dict], reports: list[dict], comparators: list[dict]) -> dict:
    """Frozen paired whole-problem contrasts over replay-verified episodes."""

    new_by_key = {}
    for report in reports:
        if report["arm"] in stress.GPU_CONDITIONS:
            key = (report["task_id"], report["modality"], report["algorithm"], report["family"], report["arm"])
            new_by_key[key] = bool(report["result"]["invariant_valid_success"])
    clean_by_key = {}
    random_valid_by_task_algo: dict[tuple[str, str], list[bool]] = {}
    exact_by_key = {}
    for report in comparators:
        key = (report["task_id"], report["modality"], report["algorithm"])
        success = bool(report["result"]["invariant_valid_success"])
        if report["arm"] == "process_sft":
            clean_by_key[(*key, "learned_adapter")] = success
        elif report["arm"] == "pretrained_base":
            clean_by_key[(*key, "pretrained_base")] = success
        elif report["arm"] == "random_valid":
            random_valid_by_task_algo.setdefault((report["task_id"], report["algorithm"]), []).append(success)
        elif report["arm"] == "exact_reference":
            exact_by_key[key] = success
    for report in reports:
        if report["arm"] == "random_valid":
            random_valid_by_task_algo.setdefault((report["task_id"], report["algorithm"]), []).append(
                bool(report["result"]["invariant_valid_success"])
            )

    cells = []
    for task in tasks:
        task_id = task["row"]["task_id"]
        domain = task["row"]["domain"]
        stratum = "compact" if "-compact-" in task_id else "expanded"
        for algorithm in protocol["learned_algorithms"]:
            rv = random_valid_by_task_algo.get((task_id, algorithm), [])
            rv_frequency = sum(rv) / len(rv) if rv else None
            for family in stress.FAMILY_ORDER:
                for modality in stress.family_arms(protocol, family):
                    learned_key = (task_id, modality, algorithm, family, "learned_adapter")
                    base_key = (task_id, modality, algorithm, family, "pretrained_base")
                    if learned_key not in new_by_key or base_key not in new_by_key:
                        continue
                    cells.append(
                        {
                            "task_id": task_id,
                            "domain": domain,
                            "stratum_origin": stratum,
                            "algorithm": algorithm,
                            "modality": modality,
                            "family": family,
                            "learned_corrupted": new_by_key[learned_key],
                            "learned_clean": clean_by_key.get((task_id, modality, algorithm, "learned_adapter")),
                            "base_corrupted": new_by_key[base_key],
                            "base_clean": clean_by_key.get((task_id, modality, algorithm, "pretrained_base")),
                            "random_valid_frequency": rv_frequency,
                            "exact_reference": exact_by_key.get((task_id, algorithm)),
                        }
                    )

    def bootstrap_interval(deltas: list[float]) -> dict | None:
        if len(deltas) < TINY_STRATUM_LIMIT:
            return None
        rng = random.Random(BOOTSTRAP_SEED)
        means = []
        for _ in range(BOOTSTRAP_RESAMPLES):
            sample = [deltas[rng.randrange(len(deltas))] for _ in deltas]
            means.append(sum(sample) / len(sample))
        means.sort()
        low = means[int(0.025 * BOOTSTRAP_RESAMPLES)]
        high = means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1]
        return {"low": low, "high": high, "material": (low > 0) or (high < 0)}

    def group_contrast(key_fn) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for cell in cells:
            groups.setdefault(key_fn(cell), []).append(cell)
        rows = []
        for name, members in sorted(groups.items()):
            deltas = [
                float(member["learned_corrupted"]) - float(member["learned_clean"])
                for member in members
                if member["learned_clean"] is not None
            ]
            best_control = [
                max(float(member["base_corrupted"]), float(member["random_valid_frequency"]))
                for member in members
            ]
            learned = [float(member["learned_corrupted"]) for member in members]
            row = {
                "group": name,
                "tasks": len({member["task_id"] for member in members}),
                "cells": len(members),
                "learned_corrupted_success": sum(learned) / len(learned),
                "learned_clean_success": sum(float(m["learned_clean"]) for m in members) / len(members),
                "mean_degradation": sum(deltas) / len(deltas),
                "best_control_success": sum(best_control) / len(best_control),
                "control_at_ceiling_cells": sum(bc == 1.0 for bc in best_control),
                "descriptive_only": len(deltas) < TINY_STRATUM_LIMIT,
            }
            interval = bootstrap_interval(deltas)
            if interval is not None:
                row["degradation_interval_95"] = interval
            rows.append(row)
        return rows

    multimodal = [cell for cell in cells if cell["modality"] == "multimodal-state"]
    channel_deltas: dict[str, list[float]] = {"text": [], "visual": []}
    channel_by_task: dict[tuple[str, str], dict[str, list[float]]] = {}
    for cell in multimodal:
        if cell["learned_clean"] is None:
            continue
        channel = "text" if cell["family"].startswith("text-") else "visual"
        delta = float(cell["learned_corrupted"]) - float(cell["learned_clean"])
        channel_deltas[channel].append(delta)
        channel_by_task.setdefault((cell["task_id"], cell["algorithm"]), {}).setdefault(channel, []).append(delta)
    paired_channel_deltas = []
    for channels in channel_by_task.values():
        if "text" in channels and "visual" in channels:
            paired_channel_deltas.append(
                sum(channels["text"]) / len(channels["text"]) - sum(channels["visual"]) / len(channels["visual"])
            )
    channel_isolation = {
        "paired_tasks": len(paired_channel_deltas),
        "text_channel_mean_degradation": sum(channel_deltas["text"]) / len(channel_deltas["text"])
        if channel_deltas["text"]
        else None,
        "visual_channel_mean_degradation": sum(channel_deltas["visual"]) / len(channel_deltas["visual"])
        if channel_deltas["visual"]
        else None,
        "mean_text_minus_visual_degradation": sum(paired_channel_deltas) / len(paired_channel_deltas)
        if paired_channel_deltas
        else None,
        "descriptive_only": len(paired_channel_deltas) < TINY_STRATUM_LIMIT,
    }
    interval = bootstrap_interval(paired_channel_deltas)
    if interval is not None:
        channel_isolation["text_minus_visual_interval_95"] = interval

    return {
        "schema_version": stress.ANALYSIS_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "paired_unit": "whole source task instance x algorithm x modality x corruption family",
        "cells": cells,
        "contrasts": {
            "degradation_by_family": group_contrast(lambda cell: cell["family"]),
            "degradation_by_family_modality": group_contrast(
                lambda cell: f"{cell['family']}__{cell['modality']}"
            ),
            "degradation_by_domain": group_contrast(lambda cell: cell["domain"]),
            "degradation_by_stratum_origin": group_contrast(lambda cell: cell["stratum_origin"]),
            "multimodal_channel_isolation": channel_isolation,
        },
        "tiny_subgroup_rule": f"strata with fewer than {TINY_STRATUM_LIMIT} paired instances are descriptive-only",
        "saturation_rule": "no structural-advantage claim where the best control is at ceiling",
        "bootstrap": {
            "unit": "whole source task instance within group",
            "seed": BOOTSTRAP_SEED,
            "resamples": BOOTSTRAP_RESAMPLES,
            "confidence": 0.95,
            "interval": "percentile",
        },
    }


def evaluate_finalize_stage(root: Path, endpoint: str) -> dict:
    """Replay every completed stress episode and reused comparator; publish the evaluation."""

    protocol, admission, tasks, rows = _evaluation_context(root)
    protocol["root"] = str(root)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    reports = []
    missing = []
    replayed = 0
    for binding in rows:
        episode, _, _ = stress.binding_paths(root, protocol, binding)
        if not episode.exists():
            missing.append(binding["index"])
            continue
        report = read(episode)
        stress.independently_replay(root, protocol, task_by_id[binding["task_id"]], report, endpoint)
        replayed += 1
        reports.append(report)
    comparators = []
    for binding in stress.comparator_bindings(protocol, tasks):
        comparators.append(
            stress.verify_comparator(
                root,
                protocol,
                task_by_id[binding["task_id"]],
                binding["modality"],
                binding["algorithm"],
                binding["condition"],
                endpoint,
            )
        )
    result = {
        "schema_version": stress.EVALUATION_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "membership_sha256": admission["membership_sha256"],
        "outcome": "PASS" if not missing else "INCOMPLETE",
        "bindings": len(rows),
        "episodes_replayed": replayed,
        "comparator_episodes_replayed": len(comparators),
        "missing_bindings": sorted(missing),
        **stress.summarize_reports(reports),
    }
    write(output_root(root, protocol) / "evaluation.json", result)
    analysis = _paired_analysis(protocol, tasks, reports, comparators)
    write(output_root(root, protocol) / "analysis.json", analysis)
    return {
        "schema_version": stress.EVALUATION_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "outcome": result["outcome"],
        "episodes_replayed": replayed,
        "comparator_episodes_replayed": len(comparators),
        "missing_bindings": result["missing_bindings"],
    }


def audit_evaluate_worker(root: Path, worker: int, kind: str) -> dict:
    """Scheduler hook: verify one stress evaluation worker attempt before accepting it."""

    terminal = read(Path(os.environ["EXPANDED_TERMINAL_PATH"]))
    if terminal.get("status") != "succeeded":
        raise RuntimeError("modality-stress evaluate worker did not terminate cleanly")
    attempt_dir = Path(os.environ["EXPANDED_TERMINAL_PATH"]).parent
    result = read(attempt_dir / "worker-result.json")
    protocol, _, _, rows = _evaluation_context(root)
    selected = stress.assigned_bindings(rows, worker, kind)
    if (
        result.get("schema_version") != stress.WORKER_SCHEMA
        or result.get("protocol_id") != protocol["protocol_id"]
        or result.get("worker") != worker
        or result.get("kind") != kind
    ):
        raise ValueError("modality-stress worker result provenance differs from the CLI audit arguments")
    if result.get("outcome") != "PASS":
        raise ValueError("modality-stress worker outcome does not indicate completion")
    if result.get("completed") != len(selected):
        raise ValueError("modality-stress worker completed count differs from the frozen partition")
    missing_episodes = [
        binding["index"]
        for binding in selected
        if not stress.binding_paths(root, protocol, binding)[0].is_file()
    ]
    if missing_episodes:
        raise ValueError(f"modality-stress worker is missing episode files: {missing_episodes}")
    summary = {
        "outcome": "PASS",
        "worker": worker,
        "kind": kind,
        "completed": result["completed"],
        "partition": len(selected),
    }
    print(f"PASS: modality-stress {kind} worker {worker} completed {summary['completed']}/{len(selected)} episodes")
    return summary


def audit_evaluate_final(root: Path) -> dict:
    """Scheduler hook: verify the aggregated stress evaluation before accepting the chain."""

    protocol, admission, _, rows = _evaluation_context(root)
    evaluation = read(output_root(root, protocol) / "evaluation.json")
    if (
        evaluation.get("schema_version") != stress.EVALUATION_SCHEMA
        or evaluation.get("protocol_id") != protocol["protocol_id"]
        or evaluation.get("membership_sha256") != admission["membership_sha256"]
    ):
        raise ValueError("modality-stress evaluation provenance differs from the frozen admission")
    if evaluation.get("bindings") != len(rows) or evaluation.get("episodes_replayed") != len(rows):
        raise ValueError("modality-stress evaluation coverage differs from the frozen bindings")
    if evaluation.get("outcome") != "PASS" or evaluation.get("missing_bindings"):
        raise ValueError("modality-stress evaluation is incomplete: missing bindings remain")
    if evaluation.get("comparator_episodes_replayed") != 144:
        raise ValueError("modality-stress reused comparator replay coverage differs from the frozen join")
    by_condition = evaluation.get("by_condition", {})
    models = sum(by_condition[name]["episodes"] for name in stress.GPU_CONDITIONS)
    controls = sum(by_condition[name]["episodes"] for name in stress.CPU_CONDITIONS)
    summary = {
        "outcome": "PASS",
        "model_episodes": models,
        "control_episodes": controls,
        "episodes_replayed": evaluation["episodes_replayed"],
        "comparator_episodes_replayed": evaluation["comparator_episodes_replayed"],
        "bindings": len(rows),
    }
    print(
        f"PASS: modality-stress evaluation complete: {models} model + {controls} control episodes replayed "
        f"({evaluation['episodes_replayed']}/{len(rows)} bindings) with 144 reused comparators"
    )
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "validate",
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
    args = parser.parse_args(argv)
    if args.stage in ("evaluate-worker", "audit-evaluate-worker"):
        if args.worker is None:
            parser.error(f"{args.stage} requires --worker")
        if args.kind is None:
            parser.error(f"{args.stage} requires --kind")
    actions = {
        "validate": lambda: validate_stage(ROOT),
        "evaluate-inputs": lambda: evaluate_inputs_stage(ROOT),
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
