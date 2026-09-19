"""Run the issue-67 best-first curriculum and replacement comparison."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

from examples.planning_benchmark_slice.best_first_curriculum import (
    CURRICULA,
    curriculum_metadata,
    load_best_first_issue67,
    paired_bootstrap_interval,
    replacement_setting_summary,
    select_issue67_coverage,
)
from examples.planning_benchmark_slice.best_first_development import (
    BestFirstDevelopmentTask,
    BestFirstModelSession,
    cost_balanced_task_shards,
    lower_95_bound,
    replay_best_first_model_episode,
)
from examples.planning_benchmark_slice.best_first_model_input import (
    best_first_policy_messages,
    serialize_best_first_message_prefix,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.qwen_text_policy import BatchedPolicyAdapter
from scripts.run_best_first_issue65 import (
    _atomic_write_json,
    _canonical_text,
    _episode_record,
    _json_object,
    _qualification_device,
    _read_gzip_json,
    _ReferenceJob,
    _run_children,
    _run_model_sessions,
    _run_reference_job,
    _run_with_heartbeat,
    _terminal_progress,
    _train,
    _training_plan,
    _write_gzip_json,
)
from src.data_collect.governance import StopOutcome

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUTPUT = _ROOT / "outputs" / "best_first_phase" / "issue67-v1"
_DEFAULT_DATASET = _ROOT / "data" / "best_first_paired_phase_v3" / "issue67-curriculum-sft"
_HEURISTIC_STOP = _ROOT / ("configs/experiments/best-first-issue67-heuristic-gated-not-run-v1.json")


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "all",
            "preflight",
            "qualify",
            "qualification-device",
            "prepare",
            "train",
            "train-cell",
            "references",
            "evaluate",
            "evaluation-shard",
            "adjudicate",
        ),
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--devices", nargs="+", default=("cuda:0", "cuda:1"))
    parser.add_argument("--device")
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-count", type=int, default=2)
    parser.add_argument("--reference-workers", type=int, default=8)
    parser.add_argument("--training-devices", nargs="+", default=("0", "1"))
    parser.add_argument("--training-device")
    parser.add_argument("--master-ports", nargs="+", type=int, default=(29670, 29671, 29672))
    parser.add_argument("--master-port", type=int)
    parser.add_argument("--curriculum", choices=CURRICULA)
    parser.add_argument("--progress-interval-seconds", type=float, default=30.0)
    parser.add_argument("--rollout-started-at", type=float)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)
    if args.progress_interval_seconds <= 0:
        raise ValueError("progress interval must be positive")
    if any(port < 1024 or port > 65535 for port in args.master_ports):
        raise ValueError("MASTER_PORT values must be between 1024 and 65535")
    if args.master_port is not None and not 1024 <= args.master_port <= 65535:
        raise ValueError("MASTER_PORT must be between 1024 and 65535")
    if len(set(args.master_ports)) != len(args.master_ports):
        raise ValueError("issue #67 concurrent training cells require distinct MASTER_PORT values")

    experiment = load_best_first_issue67(_ROOT)
    output_root = (args.output_root or _DEFAULT_OUTPUT).resolve()
    dataset_root = (args.dataset_root or _DEFAULT_DATASET).resolve()
    if args.stage == "preflight":
        print(_canonical_text(_preflight(experiment)), flush=True)
        return 0
    if args.stage == "qualify":
        return _qualify(experiment, output_root, tuple(args.devices), dry_run=args.dry_run)
    if args.stage == "qualification-device":
        if args.device is None or args.shard_index is None:
            raise ValueError("qualification-device requires --device and --shard-index")
        return _qualification_device(experiment, output_root, args.device, args.shard_index)
    if args.stage == "prepare":
        return _prepare(experiment, dataset_root, dry_run=args.dry_run)
    if args.stage == "train":
        return _train_all(
            experiment,
            output_root,
            dataset_root,
            devices=tuple(args.training_devices),
            ports=tuple(args.master_ports),
            progress_interval=args.progress_interval_seconds,
            resume=args.resume,
            dry_run=args.dry_run,
        )
    if args.stage == "train-cell":
        if args.curriculum is None or args.training_device is None or args.master_port is None:
            raise ValueError("train-cell requires curriculum, training device, and master port")
        return _train_cell(
            experiment,
            output_root,
            dataset_root,
            curriculum=args.curriculum,
            training_device=args.training_device,
            master_port=args.master_port,
            progress_interval=args.progress_interval_seconds,
            resume=args.resume,
            dry_run=args.dry_run,
        )
    if args.stage == "references":
        return _references(
            experiment,
            output_root,
            workers=args.reference_workers,
            resume=args.resume,
            dry_run=args.dry_run,
        )
    if args.stage == "evaluate":
        return _evaluate(
            experiment,
            output_root,
            devices=tuple(args.devices),
            resume=args.resume,
            dry_run=args.dry_run,
            progress_interval=args.progress_interval_seconds,
        )
    if args.stage == "evaluation-shard":
        if args.device is None or args.shard_index is None or args.rollout_started_at is None:
            raise ValueError("evaluation-shard requires device, shard index, and rollout start")
        return _evaluation_shard(
            experiment,
            output_root,
            device=args.device,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            rollout_started_at=args.rollout_started_at,
            resume=args.resume,
            progress_interval=args.progress_interval_seconds,
        )
    if args.stage == "adjudicate":
        return _adjudicate(experiment, output_root, dry_run=args.dry_run)
    return _all(experiment, args, output_root, dataset_root)


def _preflight(experiment) -> dict[str, Any]:
    experiment.require_stage("preflight")
    return {
        **experiment.preflight(),
        "curricula": list(CURRICULA),
        "original_heuristic_representation": _json_object(_HEURISTIC_STOP),
        "representative_algorithm": experiment.algorithm,
        "status": StopOutcome.PASS.value,
        "training_runs": len(CURRICULA),
        "writes": 0,
    }


def _all(experiment, args, output_root: Path, dataset_root: Path) -> int:
    if args.dry_run:
        plans = {
            "preflight": _preflight(experiment),
            "qualification": _qualification_plan(experiment, output_root, tuple(args.devices)),
            "prepare": _prepare_plan(experiment, dataset_root),
            "references": _candidate_coverage_plan(experiment, args.reference_workers),
            "training": _training_plan_all(
                experiment,
                output_root,
                dataset_root,
                tuple(args.training_devices),
                tuple(args.master_ports),
            ),
            "evaluation": _candidate_evaluation_plan(experiment, tuple(args.devices)),
            "adjudication": _adjudication_plan(output_root),
        }
        print(_canonical_text({"dry_run": True, "plans": plans, "writes": 0}))
        return 0
    print(_canonical_text({**_preflight(experiment), "stage": "preflight"}), flush=True)
    if _qualify(experiment, output_root, tuple(args.devices), dry_run=False):
        return 1
    qualification = _json_object(output_root / "qualification" / "qualification.json")
    if qualification["coverage"]["outcome"] != StopOutcome.PASS.value:
        return _adjudicate(experiment, output_root, dry_run=False)
    if _prepare(experiment, dataset_root, dry_run=False):
        return 1
    if _references(
        experiment,
        output_root,
        workers=args.reference_workers,
        resume=args.resume,
        dry_run=False,
    ):
        return 1
    if _train_all(
        experiment,
        output_root,
        dataset_root,
        devices=tuple(args.training_devices),
        ports=tuple(args.master_ports),
        progress_interval=args.progress_interval_seconds,
        resume=args.resume,
        dry_run=False,
    ):
        return 1
    if _evaluate(
        experiment,
        output_root,
        devices=tuple(args.devices),
        resume=args.resume,
        dry_run=False,
        progress_interval=args.progress_interval_seconds,
    ):
        return 1
    return _adjudicate(experiment, output_root, dry_run=False)


def _qualification_plan(experiment, output_root: Path, devices: tuple[str, ...]) -> dict[str, Any]:
    if len(devices) != 2 or len(set(devices)) != 2:
        raise ValueError("issue #67 qualification requires two distinct A100 devices")
    fallback = _fallback_tasks(experiment.tasks)
    return {
        "candidate_panels": [
            {"mode": "complete_issue64_v3_development_panel", "tasks": len(experiment.tasks)},
            {"mode": "cheapest_complete_task_per_domain", "tasks": len(fallback)},
        ],
        "devices": list(devices),
        "outcomes_observed": False,
        "output": str(output_root / "qualification" / "qualification.json"),
        "physical_model_conditions": 4,
        "probe_count_per_device": len(experiment.tasks),
    }


def _qualify(experiment, output_root: Path, devices: tuple[str, ...], *, dry_run: bool) -> int:
    experiment.require_stage("performance_qualification")
    plan = _qualification_plan(experiment, output_root, devices)
    if dry_run:
        print(_canonical_text({**plan, "dry_run": True, "writes": 0}))
        return 0
    root = output_root / "qualification"
    final_path = root / "qualification.json"
    if final_path.is_file():
        print(_canonical_text({"output": str(final_path), "status": "already_complete"}))
        return 0
    root.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    commands = [
        (
            sys.executable,
            str(Path(__file__).resolve()),
            "qualification-device",
            "--output-root",
            str(output_root),
            "--device",
            device,
            "--shard-index",
            str(index),
        )
        for index, device in enumerate(devices)
    ]
    if _run_children(commands, prefixes=tuple(f"qualification:{device}" for device in devices)):
        return 1
    measurements = [_json_object(root / f"device-{index}.json") for index in range(len(devices))]
    device_bounds = [lower_95_bound(row["throughput_samples"]) for row in measurements]
    qualification = select_issue67_coverage(
        experiment.tasks,
        model_load_seconds=max(float(row["model_load_seconds"]) for row in measurements),
        throughput_samples=(min(device_bounds),),
        runtime_seconds_per_call=max(float(row["runtime_seconds_per_call"]) for row in measurements),
        rollout_shard_count=len(devices),
        certification_seconds=float(experiment.design["evaluation"]["rollout_certification_seconds"]),
        safety_margin=float(experiment.design["evaluation"]["safety_margin"]),
    )
    if time.time() - started_at > experiment.design["evaluation"]["qualification_seconds"]:
        qualification["coverage"].update({"mode": None, "outcome": StopOutcome.VALID_STOP.value, "task_ids": []})
        qualification["reason"] = "qualification_hour_exhausted"
    qualification.update(
        {
            "authorization_id": experiment.authorization["authorization_id"],
            "contract_id": experiment.contract_id,
            "device_measurements": [f"device-{index}.json" for index in range(len(devices))],
            "qualification_elapsed_seconds": time.time() - started_at,
            "source_gate_receipt_id": experiment.authorization["gate_receipt"]["receipt_id"],
        }
    )
    _atomic_write_json(final_path, qualification)
    receipt = {
        "contract_id": experiment.contract_id,
        "outcome": qualification["coverage"]["outcome"],
        "receipt_id": f"gate:{experiment.contract_id}:qualification-attempt-001",
        "scientific_completion": False,
        "start_permitted": qualification["coverage"]["outcome"] == StopOutcome.PASS.value,
    }
    _atomic_write_json(root / "gate-receipt.json", receipt)
    if receipt["outcome"] != StopOutcome.PASS.value:
        _write_gated_not_run(root, experiment.contract_id, receipt["outcome"], "qualification did not fit")
    print(_canonical_text({"output": str(final_path), **qualification["coverage"]}))
    return 0


def _prepare_plan(experiment, dataset_root: Path) -> dict[str, Any]:
    return {
        "controls": list(CURRICULA),
        "dataset_root": str(dataset_root),
        "expected_rows_per_control": experiment.training_counts,
        "source_content": "identical issue-66 greedy process-SFT rows",
    }


def _prepare(experiment, dataset_root: Path, *, dry_run: bool) -> int:
    experiment.require_stage("dataset_preparation")
    plan = _prepare_plan(experiment, dataset_root)
    if dry_run:
        print(_canonical_text({**plan, "dry_run": True, "writes": 0}))
        return 0
    source_rows = _source_training_rows(experiment)
    source_keys = set(source_rows)
    for control in CURRICULA:
        root = dataset_root / control
        manifest_path = root / "manifest.json"
        if manifest_path.is_file():
            manifest = _json_object(manifest_path)
            if manifest.get("counts") != experiment.training_counts or manifest.get("curriculum") != control:
                raise ValueError(f"existing issue #67 {control} dataset has incomplete coverage")
            print(_canonical_text({"curriculum": control, "status": "already_prepared"}))
            continue
        if root.exists():
            raise FileExistsError(f"incomplete issue #67 dataset root exists: {root}")
        root.mkdir(parents=True)
        metadata = curriculum_metadata(experiment, control)
        ordered_keys = {
            split: [(split, str(row["pair_id"]), int(row["record_index"])) for row in rows]
            for split, rows in metadata.items()
        }
        if set(key for keys in ordered_keys.values() for key in keys) != source_keys:
            raise ValueError(f"issue #67 {control} does not contain the matched training content")
        started = time.monotonic()
        for split, keys in ordered_keys.items():
            destination = root / "data" / f"{split}.jsonl"
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(".jsonl.tmp")
            with temporary.open("w", encoding="utf-8") as stream:
                for index, key in enumerate(keys, start=1):
                    stream.write(_canonical_text(source_rows[key]) + "\n")
                    if index % 1000 == 0 or index == len(keys):
                        _terminal_progress(f"prepare-{control}-{split}", index, len(keys), started, "rows")
            temporary.replace(destination)
        manifest = {
            "algorithm": experiment.algorithm,
            "authorization_id": experiment.authorization["authorization_id"],
            "contract_id": experiment.contract_id,
            "counts": experiment.training_counts,
            "curriculum": control,
            "data": {split: f"data/{split}.jsonl" for split in ("train", "dev")},
            "framework": {"name": "ms-swift", "version": "4.2.2"},
            "gate_receipt_id": experiment.authorization["gate_receipt"]["receipt_id"],
            "schema_version": "best_first_issue67_training_dataset_v1",
        }
        _atomic_write_json(manifest_path, manifest)
        print(_canonical_text({"curriculum": control, "manifest": str(manifest_path), "status": "PASS"}))
    return 0


def _source_training_rows(experiment) -> dict[tuple[str, str, int], dict[str, Any]]:
    rows: dict[tuple[str, str, int], dict[str, Any]] = {}
    paths_by_split = {"train": experiment.train_datasets, "dev": experiment.dev_datasets}
    total = sum(len(paths) for paths in paths_by_split.values())
    completed = 0
    started = time.monotonic()
    for split, paths in paths_by_split.items():
        for path in paths:
            pair_id = path.parent.name
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                for record_index, line in enumerate(stream):
                    key = (split, pair_id, record_index)
                    if key in rows:
                        raise ValueError(f"duplicate issue #67 training row: {key}")
                    rows[key] = json.loads(line)
            completed += 1
            _terminal_progress("load-training-rows", completed, total, started, pair_id)
    if len(rows) != sum(experiment.training_counts.values()):
        raise ValueError("issue #67 source training rows are incomplete")
    return rows


def _training_plan_all(
    experiment,
    output_root: Path,
    dataset_root: Path,
    devices: tuple[str, ...],
    ports: tuple[int, ...],
) -> dict[str, Any]:
    assignments = _training_assignments(devices, ports)
    return {
        "cells": [
            {
                "curriculum": control,
                "device": device,
                "master_port": port,
                "plan": _training_plan(
                    experiment,
                    output_root / "cells" / control,
                    dataset_root / control,
                    device,
                    port,
                ),
            }
            for control, device, port in assignments
        ],
        "parallel_devices": list(devices),
    }


def _training_assignments(devices: tuple[str, ...], ports: tuple[int, ...]) -> tuple[tuple[str, str, int], ...]:
    if not devices or len(set(devices)) != len(devices):
        raise ValueError("training devices must be a nonempty distinct list")
    if len(ports) != len(CURRICULA):
        raise ValueError("issue #67 requires one explicit MASTER_PORT per curriculum")
    return tuple((control, devices[index % len(devices)], ports[index]) for index, control in enumerate(CURRICULA))


def _train_all(
    experiment,
    output_root: Path,
    dataset_root: Path,
    *,
    devices: tuple[str, ...],
    ports: tuple[int, ...],
    progress_interval: float,
    resume: bool,
    dry_run: bool,
) -> int:
    experiment.require_stage("process_sft_training")
    plan = _training_plan_all(experiment, output_root, dataset_root, devices, ports)
    if dry_run:
        print(_canonical_text({**plan, "dry_run": True, "writes": 0}))
        return 0
    _require_qualification_pass(output_root)
    assignments = _training_assignments(devices, ports)
    queues = {
        device: [(control, port) for control, assigned, port in assignments if assigned == device] for device in devices
    }
    for wave in range(max(len(queue) for queue in queues.values())):
        commands = []
        prefixes = []
        for device, queue in queues.items():
            if wave >= len(queue):
                continue
            control, port = queue[wave]
            commands.append(
                (
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "train-cell",
                    "--output-root",
                    str(output_root),
                    "--dataset-root",
                    str(dataset_root),
                    "--curriculum",
                    control,
                    "--training-device",
                    device,
                    "--master-port",
                    str(port),
                    "--progress-interval-seconds",
                    str(progress_interval),
                    *(("--resume",) if resume else ()),
                )
            )
            prefixes.append(f"training:{control}:cuda:{device}")
        if _run_children(commands, prefixes=prefixes):
            return 1
    return 0


def _train_cell(
    experiment,
    output_root: Path,
    dataset_root: Path,
    *,
    curriculum: str,
    training_device: str,
    master_port: int,
    progress_interval: float,
    resume: bool,
    dry_run: bool,
) -> int:
    return _train(
        experiment,
        output_root / "cells" / curriculum,
        dataset_root / curriculum,
        training_device=training_device,
        master_port=master_port,
        progress_interval=progress_interval,
        resume=resume,
        dry_run=dry_run,
        qualification_output_root=output_root,
    )


def _candidate_coverage_plan(experiment, workers: int) -> dict[str, Any]:
    return {
        "candidate_task_counts": [len(experiment.tasks), len(_fallback_tasks(experiment.tasks))],
        "exact_reference_episodes": "selected_task_count",
        "random_valid_episodes": f"selected_task_count * {len(experiment.evaluation_seeds)}",
        "workers": workers,
    }


def _references(experiment, output_root: Path, *, workers: int, resume: bool, dry_run: bool) -> int:
    experiment.require_stage("development_references")
    available = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count() or 1
    if workers <= 0 or workers > available:
        raise ValueError("reference worker count must fit the available CPU allocation")
    if dry_run:
        print(_canonical_text({**_candidate_coverage_plan(experiment, workers), "dry_run": True, "writes": 0}))
        return 0
    tasks = _selected_tasks(experiment, output_root)
    root = output_root / "references"
    manifest_path = root / "manifest.json"
    if manifest_path.is_file():
        print(_canonical_text({"output": str(manifest_path), "status": "already_complete"}))
        return 0
    if root.exists() and not resume:
        raise FileExistsError(f"issue #67 reference root exists; pass --resume: {root}")
    root.mkdir(parents=True, exist_ok=True)
    jobs = []
    for task in tasks:
        jobs.append(
            _ReferenceJob(len(jobs), task, "exact_reference", 17, root / "exact" / f"{task.pair_id}.json.gz", resume)
        )
        for seed in experiment.evaluation_seeds:
            jobs.append(
                _ReferenceJob(
                    len(jobs),
                    task,
                    "random_valid",
                    seed,
                    root / "random-valid" / f"seed-{seed}" / f"{task.pair_id}.json.gz",
                    resume,
                )
            )
    rows: list[dict[str, Any] | None] = [None] * len(jobs)
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_run_reference_job, job): job for job in jobs}
        for completed, future in enumerate(as_completed(futures), start=1):
            index, status, row = future.result()
            rows[index] = row
            _terminal_progress("references", completed, len(jobs), started, status)
    records = [row for row in rows if row is not None]
    manifest = {
        "authorization_id": experiment.authorization["authorization_id"],
        "contract_id": experiment.contract_id,
        "counts": {
            "exact_reference": len(tasks),
            "random_valid": len(tasks) * len(experiment.evaluation_seeds),
        },
        "outcome": StopOutcome.PASS.value,
        "records": records,
        "schema_version": "best_first_issue67_references_v1",
        "source_gate_receipt_id": experiment.authorization["gate_receipt"]["receipt_id"],
    }
    _atomic_write_json(manifest_path, manifest)
    print(_canonical_text({"output": str(manifest_path), "records": len(records), "status": "PASS"}))
    return 0


def _candidate_evaluation_plan(experiment, devices: tuple[str, ...]) -> dict[str, Any]:
    if len(devices) != 2 or len(set(devices)) != 2:
        raise ValueError("issue #67 evaluation requires two distinct A100 devices")
    return {
        "candidate_task_counts": [len(experiment.tasks), len(_fallback_tasks(experiment.tasks))],
        "conditions": ["pretrained_base", *[f"process_sft:{name}" for name in CURRICULA]],
        "devices": list(devices),
        "episodes": f"selected_task_count * {len(experiment.evaluation_seeds)} * 4",
    }


def _evaluate(
    experiment,
    output_root: Path,
    *,
    devices: tuple[str, ...],
    resume: bool,
    dry_run: bool,
    progress_interval: float,
) -> int:
    experiment.require_stage("batched_evaluation")
    plan = _candidate_evaluation_plan(experiment, devices)
    if dry_run:
        print(_canonical_text({**plan, "dry_run": True, "writes": 0}))
        return 0
    tasks = _selected_tasks(experiment, output_root)
    for control in CURRICULA:
        report = _json_object(output_root / "cells" / control / "training" / "training-report.json")
        if report.get("outcome") != StopOutcome.PASS.value or not Path(report["final_checkpoint"]).is_dir():
            raise ValueError(f"issue #67 final {control} checkpoint is unavailable")
    references = _json_object(output_root / "references" / "manifest.json")
    if references.get("outcome") != StopOutcome.PASS.value:
        raise ValueError("issue #67 references are incomplete")
    rollout_root = output_root / "rollout"
    launch_path = rollout_root / "launch.json"
    if launch_path.is_file():
        if not resume:
            raise FileExistsError(f"issue #67 rollout exists; pass --resume: {rollout_root}")
        rollout_started_at = float(_json_object(launch_path)["rollout_started_at"])
    else:
        rollout_started_at = time.time()
        rollout_root.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(
            launch_path,
            {
                **plan,
                "rollout_started_at": rollout_started_at,
                "selected_tasks": [task.instance_id for task in tasks],
            },
        )
    commands = [
        (
            sys.executable,
            str(Path(__file__).resolve()),
            "evaluation-shard",
            "--output-root",
            str(output_root),
            "--device",
            device,
            "--shard-index",
            str(index),
            "--shard-count",
            str(len(devices)),
            "--rollout-started-at",
            str(rollout_started_at),
            "--progress-interval-seconds",
            str(progress_interval),
            *(("--resume",) if resume else ()),
        )
        for index, device in enumerate(devices)
    ]
    result = _run_children(commands, prefixes=tuple(f"rollout:{device}" for device in devices))
    print(_canonical_text({"output_root": str(rollout_root), "returncode": result, "status": "complete"}))
    return result


def _evaluation_shard(
    experiment,
    output_root: Path,
    *,
    device: str,
    shard_index: int,
    shard_count: int,
    rollout_started_at: float,
    resume: bool,
    progress_interval: float,
) -> int:
    experiment.require_stage("batched_evaluation")
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError("issue #67 rollout shard index is invalid")
    selected = _selected_tasks(experiment, output_root)
    tasks = cost_balanced_task_shards(selected, shard_count=shard_count)[shard_index]
    adapter_paths = {
        control: Path(
            _json_object(output_root / "cells" / control / "training" / "training-report.json")["final_checkpoint"]
        )
        for control in CURRICULA
    }
    root = output_root / "rollout" / f"shard-{shard_index}"
    if root.exists() and not resume:
        raise FileExistsError(f"issue #67 rollout shard exists; pass --resume: {root}")
    root.mkdir(parents=True, exist_ok=True)
    records = []
    sessions = []
    task_by_id = {task.instance_id: task for task in tasks}
    conditions = (("pretrained_base", None), *[("process_sft", name) for name in CURRICULA])
    for task in tasks:
        payload = _json_object(task.task_path)
        for arm, control in conditions:
            directory = "pretrained-base" if control is None else f"process-sft/{control}"
            for seed in experiment.evaluation_seeds:
                path = root / "episodes" / directory / f"seed-{seed}" / f"{task.pair_id}.json.gz"
                if path.is_file():
                    episode = _read_gzip_json(path)
                    replay_best_first_model_episode(episode, task=task)
                    records.append(_rollout_record(task, episode, path, seed, control))
                    continue
                authority = PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])
                sessions.append(
                    BestFirstModelSession(
                        authority=authority,
                        task=task,
                        arm=arm,
                        seed=seed,
                        adapter_id=control,
                    )
                )
    model = experiment.design["model"]
    evaluation = experiment.design["evaluation"]
    policy = _run_with_heartbeat(
        lambda: BatchedPolicyAdapter(
            model_id=model["model_id"],
            revision=model["revision"],
            adapter_paths=adapter_paths,
            device=device,
            max_new_tokens=evaluation["output_tokens"],
            max_context_tokens=model["context_tokens"],
            max_batch_size=evaluation["batch_size"],
            max_batch_input_tokens=evaluation["batch_input_tokens"],
            training_message_builder=serialize_best_first_message_prefix,
            policy_message_builder=best_first_policy_messages,
        ),
        stage=f"rollout-{device}",
        item="loading one base model and three curriculum adapters",
        interval=progress_interval,
    )
    total = len(tasks) * len(experiment.evaluation_seeds) * 4
    started = time.monotonic()
    last_progress = 0.0

    def on_complete(session: BestFirstModelSession) -> None:
        episode = session.episode()
        task = task_by_id[session.task.instance_id]
        control = session.adapter_id
        directory = "pretrained-base" if control is None else f"process-sft/{control}"
        path = root / "episodes" / directory / f"seed-{session.seed}" / f"{task.pair_id}.json.gz"
        _write_gzip_json(path, episode)
        records.append(_rollout_record(task, episode, path, session.seed, control))

    def on_progress(_completed: int, batches: int, logical_calls: int) -> None:
        nonlocal last_progress
        now = time.monotonic()
        if now - last_progress >= progress_interval or len(records) == total:
            _terminal_progress(
                f"rollout-{device}",
                len(records),
                total,
                started,
                f"batches={batches} logical_calls={logical_calls}",
            )
            last_progress = now

    _, launched_batches, logical_calls, stopped = _run_model_sessions(
        sessions,
        policy,
        should_stop=lambda: time.time() - rollout_started_at >= evaluation["rollout_cutoff_seconds"],
        on_complete=on_complete,
        on_progress=on_progress,
    )
    complete = len(records) == total
    manifest = {
        "authorization_id": experiment.authorization["authorization_id"],
        "completed_episodes": len(records),
        "contract_id": experiment.contract_id,
        "device": device,
        "launched_batches": launched_batches,
        "logical_model_calls": logical_calls,
        "outcome": StopOutcome.PASS.value if complete else StopOutcome.VALID_STOP.value,
        "records": sorted(
            records,
            key=lambda row: (str(row["curriculum"]), row["arm"], row["seed"], row["instance_id"]),
        ),
        "schema_version": "best_first_issue67_rollout_shard_v1",
        "shard_count": shard_count,
        "shard_index": shard_index,
        "stop_reason": "wall_clock_cutoff" if stopped else None,
        "total_episodes": total,
    }
    _atomic_write_json(root / "manifest.json", manifest)
    print(_canonical_text({"output": str(root / "manifest.json"), **manifest}))
    return 0


def _rollout_record(
    task: BestFirstDevelopmentTask,
    episode: Mapping[str, Any],
    path: Path,
    seed: int,
    curriculum: str | None,
) -> dict[str, Any]:
    return {**_episode_record(task, episode, path=path, seed=seed), "curriculum": curriculum}


def _adjudication_plan(output_root: Path) -> dict[str, Any]:
    return {
        "qualification": str(output_root / "qualification" / "qualification.json"),
        "references": str(output_root / "references" / "manifest.json"),
        "rollout_shards": [str(output_root / "rollout" / f"shard-{index}" / "manifest.json") for index in range(2)],
    }


def _adjudicate(experiment, output_root: Path, *, dry_run: bool) -> int:
    experiment.require_stage("replay_and_adjudication")
    plan = _adjudication_plan(output_root)
    if dry_run:
        print(_canonical_text({**plan, "dry_run": True, "writes": 0}))
        return 0
    qualification = _json_object(Path(plan["qualification"]))
    if qualification["coverage"]["outcome"] != StopOutcome.PASS.value:
        report = _stop_report(experiment, "hardware qualification did not authorize a panel")
        _write_adjudication(output_root, report, gated=True)
        return 0
    tasks = _selected_tasks(experiment, output_root)
    task_by_id = {task.instance_id: task for task in tasks}
    reference_manifest = _optional_object(Path(plan["references"]))
    shard_manifests = [_optional_object(Path(path)) for path in plan["rollout_shards"]]
    reference_rows = list(reference_manifest.get("records", []))
    rollout_rows = [row for shard in shard_manifests for row in shard.get("records", [])]
    all_rows = [*reference_rows, *rollout_rows]
    started = time.monotonic()
    try:
        for index, row in enumerate(all_rows, start=1):
            episode = _read_gzip_json(_ROOT / row["path"])
            replay_best_first_model_episode(episode, task=task_by_id[row["instance_id"]])
            _terminal_progress("adjudication-replay", index, len(all_rows), started, row["instance_id"])
    except (KeyError, ValueError) as error:
        report = {
            "contract_id": experiment.contract_id,
            "outcome": StopOutcome.INVALID.value,
            "reason": str(error),
            "schema_version": "best_first_issue67_adjudication_v1",
            "scientific_completion": False,
        }
        _write_adjudication(output_root, report, gated=False)
        return 0
    if reference_manifest.get("outcome") != StopOutcome.PASS.value or any(
        shard.get("outcome") != StopOutcome.PASS.value for shard in shard_manifests
    ):
        report = _stop_report(
            experiment,
            "complete selected rollout coverage was not retained before the cutoff",
            replayed=len(all_rows),
        )
        _write_adjudication(output_root, report, gated=True)
        return 0
    try:
        metrics = _adjudication_metrics(experiment, tasks, reference_rows, rollout_rows)
        report = {
            "contract_id": experiment.contract_id,
            "metrics": metrics,
            "original_heuristic_representation": _json_object(_HEURISTIC_STOP),
            "outcome": StopOutcome.PASS.value,
            "replacement_setting_comparison": replacement_setting_summary(experiment),
            "replayed_episodes": len(all_rows),
            "schema_version": "best_first_issue67_adjudication_v1",
            "scientific_completion": True,
        }
    except ValueError as error:
        report = {
            "contract_id": experiment.contract_id,
            "outcome": StopOutcome.INVALID.value,
            "reason": str(error),
            "replayed_episodes": len(all_rows),
            "schema_version": "best_first_issue67_adjudication_v1",
            "scientific_completion": False,
        }
    _write_adjudication(output_root, report, gated=False)
    return 0


def _adjudication_metrics(experiment, tasks, reference_rows, rollout_rows) -> dict[str, Any]:
    ids = {task.instance_id for task in tasks}
    seeds = experiment.evaluation_seeds
    exact = [row for row in reference_rows if row["arm"] == "exact_reference"]
    random_rows = [row for row in reference_rows if row["arm"] == "random_valid"]
    base = [row for row in rollout_rows if row["arm"] == "pretrained_base"]
    learned = {
        control: [row for row in rollout_rows if row["arm"] == "process_sft" and row.get("curriculum") == control]
        for control in CURRICULA
    }
    _require_product(exact, ids, (None,), "exact reference")
    _require_product(random_rows, ids, seeds, "random valid")
    _require_product(base, ids, seeds, "pretrained base")
    for control, rows in learned.items():
        _require_product(rows, ids, seeds, control)
    exact_metrics = _condition_metrics(exact)
    if exact_metrics["invariant_valid_success"] != 1.0:
        raise ValueError("issue #67 exact reference failed an algorithm invariant")
    task_success = {control: _task_success(rows, ids) for control, rows in learned.items()}
    analysis = experiment.design["analysis"]
    comparisons = {}
    conclusions = []
    for left, right in combinations(CURRICULA, 2):
        interval = paired_bootstrap_interval(
            task_success[left],
            task_success[right],
            resamples=int(analysis["bootstrap_resamples"]),
            seed=int(analysis["bootstrap_seed"]),
            confidence=float(analysis["bootstrap_confidence"]),
        )
        conclusion = _interval_conclusion(
            interval,
            left,
            right,
            float(analysis["curriculum_equivalence_margin"]),
        )
        comparisons[f"{left}_minus_{right}"] = {**interval, "conclusion": conclusion}
        conclusions.append(conclusion)
    return {
        "base": _condition_metrics(base),
        "curriculum_comparisons": comparisons,
        "curriculum_conclusion": (
            "no_material_order_effect"
            if all(value == "practical_equivalence" for value in conclusions)
            else (
                "order_effect_detected"
                if any(value.endswith("_advantage") for value in conclusions)
                else "inconclusive_order_effect"
            )
        ),
        "curriculum_equivalence_margin": analysis["curriculum_equivalence_margin"],
        "exact_reference": exact_metrics,
        "process_sft": {control: _condition_metrics(rows) for control, rows in learned.items()},
        "random_valid": _condition_metrics(random_rows),
        "selected_tasks": len(tasks),
    }


def _condition_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, float | int]:
    decisions = sum(int(row["result"]["decision_count"]) for row in rows)
    allowed = sum(int(row["result"]["model_call_limit"]) for row in rows)
    invalid = sum(int(row["result"]["invalid_operation_count"]) for row in rows)
    successes = sum(bool(row["result"]["invariant_valid_success"]) for row in rows)
    return {
        "budget_usage": decisions / allowed if allowed else 0.0,
        "episodes": len(rows),
        "invalid_operation_rate": invalid / decisions if decisions else 0.0,
        "invariant_valid_success": successes / len(rows) if rows else 0.0,
    }


def _task_success(rows: Sequence[Mapping[str, Any]], ids: set[str]) -> dict[str, float]:
    return {
        instance_id: (
            sum(bool(row["result"]["invariant_valid_success"]) for row in rows if row["instance_id"] == instance_id)
            / sum(row["instance_id"] == instance_id for row in rows)
        )
        for instance_id in ids
    }


def _require_product(rows, ids: set[str], seeds: Sequence[int | None], label: str) -> None:
    observed = {(str(row["instance_id"]), row.get("seed")) for row in rows}
    expected = {(instance_id, seed) for instance_id in ids for seed in seeds}
    if observed != expected or len(rows) != len(expected):
        raise ValueError(f"issue #67 {label} coverage is incomplete")


def _interval_conclusion(interval: Mapping[str, float], left: str, right: str, margin: float) -> str:
    if interval["lower"] > 0 and interval["point"] >= margin:
        return f"{left}_advantage"
    if interval["upper"] < 0 and interval["point"] <= -margin:
        return f"{right}_advantage"
    if interval["lower"] >= -margin and interval["upper"] <= margin:
        return "practical_equivalence"
    return "inconclusive"


def _write_adjudication(output_root: Path, report: Mapping[str, Any], *, gated: bool) -> None:
    root = output_root / "adjudication"
    _atomic_write_json(root / "report.json", report)
    _atomic_write_json(
        root / "gate-receipt.json",
        {
            "contract_id": report["contract_id"],
            "outcome": report["outcome"],
            "receipt_id": f"gate:{report['contract_id']}:attempt-001",
            "scientific_completion": report["scientific_completion"],
            "start_permitted": False,
        },
    )
    if gated:
        _write_gated_not_run(root, str(report["contract_id"]), str(report["outcome"]), str(report["reason"]))
    print(_canonical_text({"output": str(root / "report.json"), **report}))


def _write_gated_not_run(root: Path, contract_id: str, outcome: str, reason: str) -> None:
    _atomic_write_json(
        root / "gated-not-run-receipt.json",
        {
            "contract_id": contract_id,
            "outcome": outcome,
            "reason": reason,
            "receipt_id": f"gated-not-run:{contract_id}:attempt-001",
            "receipt_type": "gated_not_run",
            "scientific_completion": False,
            "start_permitted": False,
        },
    )


def _stop_report(experiment, reason: str, *, replayed: int = 0) -> dict[str, Any]:
    return {
        "contract_id": experiment.contract_id,
        "outcome": StopOutcome.VALID_STOP.value,
        "reason": reason,
        "replayed_episodes": replayed,
        "schema_version": "best_first_issue67_adjudication_v1",
        "scientific_completion": False,
    }


def _selected_tasks(experiment, output_root: Path) -> tuple[BestFirstDevelopmentTask, ...]:
    qualification = _require_qualification_pass(output_root)
    selected = set(qualification["coverage"]["task_ids"])
    tasks = tuple(task for task in experiment.tasks if task.instance_id in selected)
    if len(tasks) != len(selected):
        raise ValueError("issue #67 qualification selected unknown tasks")
    return tasks


def _require_qualification_pass(output_root: Path) -> dict[str, Any]:
    qualification = _json_object(output_root / "qualification" / "qualification.json")
    if qualification.get("coverage", {}).get("outcome") != StopOutcome.PASS.value:
        raise ValueError("issue #67 qualification did not authorize training or rollout")
    return qualification


def _fallback_tasks(tasks) -> tuple[BestFirstDevelopmentTask, ...]:
    by_domain: dict[str, list[BestFirstDevelopmentTask]] = {}
    for task in tasks:
        by_domain.setdefault(task.domain_id, []).append(task)
    return tuple(
        min(rows, key=lambda task: (task.model_call_limit, task.difficulty, task.pair_id))
        for _, rows in sorted(by_domain.items())
    )


def _optional_object(path: Path) -> dict[str, Any]:
    return _json_object(path) if path.is_file() else {}


if __name__ == "__main__":
    raise SystemExit(main())
