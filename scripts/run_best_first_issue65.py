"""Run a governed additive best-first development experiment."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Sequence

from examples.planning_benchmark_slice.batched_search_evaluation import form_deterministic_batches
from examples.planning_benchmark_slice.best_first_development import (
    BestFirstDevelopmentTask,
    BestFirstModelSession,
    adjudicate_best_first,
    build_best_first_sft_command,
    cost_balanced_task_shards,
    expected_training_steps,
    load_best_first_issue65,
    load_best_first_issue66,
    lower_95_bound,
    replay_best_first_model_episode,
    run_reference_episode,
    select_best_first_coverage,
)
from examples.planning_benchmark_slice.best_first_model_input import (
    best_first_policy_messages,
    serialize_best_first_message_prefix,
)
from examples.planning_benchmark_slice.model_search_episode import SearchPolicyRequest
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.qwen_text_policy import BatchedPolicyAdapter
from src.data_collect.governance import StopOutcome

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUTPUTS = {
    65: _ROOT / "outputs" / "best_first_phase" / "issue65-v1",
    66: _ROOT / "outputs" / "best_first_phase" / "issue66-v1",
}
_DEFAULT_DATASETS = {
    65: _ROOT / "data" / "best_first_paired_phase_v3" / "issue65-w3-sft",
    66: _ROOT / "data" / "best_first_paired_phase_v3" / "issue66-greedy-sft",
}


@dataclass(frozen=True, slots=True)
class _ReferenceJob:
    index: int
    task: BestFirstDevelopmentTask
    arm: str
    seed: int
    path: Path
    resume: bool


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-issue", type=int, choices=(65, 66), default=65, help=argparse.SUPPRESS)
    parser.add_argument(
        "stage",
        choices=(
            "all",
            "preflight",
            "prepare",
            "qualify",
            "qualification-device",
            "train",
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
    parser.add_argument("--training-device", default="1")
    parser.add_argument("--master-port", type=int, default=29650)
    parser.add_argument("--progress-interval-seconds", type=float, default=30.0)
    parser.add_argument("--rollout-started-at", type=float)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)
    if args.progress_interval_seconds <= 0:
        raise ValueError("progress interval must be positive")
    if not 1024 <= args.master_port <= 65535:
        raise ValueError("MASTER_PORT must be between 1024 and 65535")

    loader = load_best_first_issue65 if args.source_issue == 65 else load_best_first_issue66
    experiment = loader(_ROOT)
    output_root = (args.output_root or _DEFAULT_OUTPUTS[args.source_issue]).resolve()
    dataset_root = (args.dataset_root or _DEFAULT_DATASETS[args.source_issue]).resolve()
    if args.stage == "preflight":
        experiment.require_stage("preflight")
        print(_canonical_text({**experiment.preflight(), "status": "PASS", "writes": 0}))
        return 0
    if args.stage == "prepare":
        return _prepare(experiment, dataset_root, dry_run=args.dry_run)
    if args.stage == "qualify":
        return _qualify(experiment, output_root, tuple(args.devices), dry_run=args.dry_run)
    if args.stage == "qualification-device":
        if args.device is None or args.shard_index is None:
            raise ValueError("qualification-device requires --device and --shard-index")
        return _qualification_device(experiment, output_root, args.device, args.shard_index)
    if args.stage == "train":
        return _train(
            experiment,
            output_root,
            dataset_root,
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
            tuple(args.devices),
            resume=args.resume,
            dry_run=args.dry_run,
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


def _all(experiment, args, output_root: Path, dataset_root: Path) -> int:
    if args.dry_run:
        plans = {
            "preflight": experiment.preflight(),
            "prepare": _prepare_plan(experiment, dataset_root),
            "qualify": _qualification_plan(experiment, output_root, tuple(args.devices)),
            "train": _training_plan(experiment, output_root, dataset_root, args.training_device, args.master_port),
            "references": _references_plan(experiment, output_root, args.reference_workers),
            "evaluate": _evaluation_plan(experiment, output_root, tuple(args.devices)),
            "adjudicate": _adjudication_plan(output_root),
        }
        print(_canonical_text({"dry_run": True, "plans": plans, "writes": 0}))
        return 0
    print(_canonical_text({**experiment.preflight(), "stage": "preflight", "status": "PASS"}), flush=True)
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
    if _train(
        experiment,
        output_root,
        dataset_root,
        training_device=args.training_device,
        master_port=args.master_port,
        progress_interval=args.progress_interval_seconds,
        resume=args.resume,
        dry_run=False,
    ):
        return 1
    if _evaluate(experiment, output_root, tuple(args.devices), resume=args.resume, dry_run=False):
        return 1
    return _adjudicate(experiment, output_root, dry_run=False)


def _prepare_plan(experiment, dataset_root: Path) -> dict[str, Any]:
    return {
        "dataset_root": str(dataset_root),
        "dev_shards": len(experiment.dev_datasets),
        "expected_dev_rows": experiment.training_counts["dev"],
        "expected_train_rows": experiment.training_counts["train"],
        "train_shards": len(experiment.train_datasets),
    }


def _prepare(experiment, dataset_root: Path, *, dry_run: bool) -> int:
    experiment.require_stage("dataset_preparation")
    plan = _prepare_plan(experiment, dataset_root)
    if dry_run:
        print(_canonical_text({**plan, "dry_run": True, "writes": 0}))
        return 0
    manifest_path = dataset_root / "manifest.json"
    if manifest_path.is_file():
        manifest = _json_object(manifest_path)
        if manifest.get("counts") != experiment.training_counts:
            raise ValueError(
                f"existing issue #{experiment.source_issue} training dataset has incomplete scientific coverage"
            )
        print(_canonical_text({"manifest": str(manifest_path), "status": "already_prepared"}))
        return 0
    if dataset_root.exists():
        raise FileExistsError(f"incomplete issue #{experiment.source_issue} dataset root exists: {dataset_root}")
    dataset_root.mkdir(parents=True)
    counts = {}
    for split, paths in (("train", experiment.train_datasets), ("dev", experiment.dev_datasets)):
        destination = dataset_root / "data" / f"{split}.jsonl"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".jsonl.tmp")
        count = 0
        started = time.monotonic()
        with temporary.open("w", encoding="utf-8") as output:
            for shard_index, path in enumerate(paths, start=1):
                with gzip.open(path, "rt", encoding="utf-8") as source:
                    for line in source:
                        row = json.loads(line)
                        messages = row.get("messages")
                        if not isinstance(messages, list) or len(messages) != 3:
                            raise ValueError(f"malformed issue #64 training row: {path}")
                        model_input = json.loads(messages[1]["content"])
                        if model_input.get("algorithm") != experiment.algorithm:
                            raise ValueError(f"issue #{experiment.source_issue} dataset included a different algorithm")
                        output.write(_canonical_text(row) + "\n")
                        count += 1
                _terminal_progress(f"prepare-{split}", shard_index, len(paths), started, f"rows={count}")
        temporary.replace(destination)
        counts[split] = count
    expected = experiment.training_counts
    if counts != expected:
        raise ValueError(f"prepared issue #{experiment.source_issue} dataset does not cover all selected records")
    manifest = {
        "algorithm": experiment.algorithm,
        "authorization_id": experiment.authorization["authorization_id"],
        "contract_id": experiment.contract_id,
        "counts": counts,
        "data": {split: f"data/{split}.jsonl" for split in ("train", "dev")},
        "framework": {"name": "ms-swift", "version": "4.2.2"},
        "gate_receipt_id": experiment.authorization["gate_receipt"]["receipt_id"],
        "schema_version": experiment.schema("training_dataset"),
    }
    _atomic_write_json(manifest_path, manifest)
    print(_canonical_text({"manifest": str(manifest_path), "status": "PASS", **counts}))
    return 0


def _qualification_plan(experiment, output_root: Path, devices: tuple[str, ...]) -> dict[str, Any]:
    if len(devices) != 2 or len(set(devices)) != 2:
        raise ValueError(f"issue #{experiment.source_issue} qualification requires two distinct A100 devices")
    return {
        "devices": list(devices),
        "development_tasks": len(experiment.tasks),
        "logical_episode_call_allowance": (
            len(experiment.evaluation_seeds) * 2 * sum(task.model_call_limit for task in experiment.tasks)
        ),
        "maximum_scheduled_calls": 2 * sum(task.model_call_limit for task in experiment.tasks),
        "outcomes_observed": False,
        "output": str(output_root / "qualification" / "qualification.json"),
        "probe_count_per_device": len(experiment.tasks),
        "rollout_shards": len(devices),
    }


def _qualify(experiment, output_root: Path, devices: tuple[str, ...], *, dry_run: bool) -> int:
    experiment.require_stage("performance_qualification")
    plan = _qualification_plan(experiment, output_root, devices)
    if dry_run:
        print(_canonical_text({**plan, "dry_run": True, "writes": 0}))
        return 0
    qualification_root = output_root / "qualification"
    final_path = qualification_root / "qualification.json"
    if final_path.is_file():
        print(_canonical_text({"output": str(final_path), "status": "already_complete"}))
        return 0
    qualification_root.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    commands = [
        (
            sys.executable,
            str(Path(__file__).resolve()),
            "--source-issue",
            str(experiment.source_issue),
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
    measurements = [_json_object(qualification_root / f"device-{index}.json") for index in range(len(devices))]
    device_bounds = [lower_95_bound(row["throughput_samples"]) for row in measurements]
    qualification = select_best_first_coverage(
        experiment.tasks,
        model_load_seconds=max(float(row["model_load_seconds"]) for row in measurements),
        throughput_samples=(min(device_bounds),),
        runtime_seconds_per_call=max(float(row["runtime_seconds_per_call"]) for row in measurements),
        rollout_shard_count=len(devices),
        source_issue=experiment.source_issue,
    ).to_dict()
    if time.time() - started_at > experiment.design["evaluation"]["qualification_seconds"]:
        qualification["coverage"].update({"mode": None, "outcome": "VALID_STOP", "task_ids": []})
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
    _atomic_write_json(
        qualification_root / "gate-receipt.json",
        {
            "contract_id": experiment.contract_id,
            "outcome": qualification["coverage"]["outcome"],
            "receipt_id": f"gate:{experiment.contract_id}:qualification-attempt-001",
            "scientific_completion": False,
            "start_permitted": qualification["coverage"]["outcome"] == StopOutcome.PASS.value,
        },
    )
    print(_canonical_text({"output": str(final_path), **qualification["coverage"]}))
    return 0


def _qualification_device(experiment, output_root: Path, device: str, index: int) -> int:
    experiment.require_stage("performance_qualification")
    if index not in (0, 1):
        raise ValueError("qualification device index must be 0 or 1")
    model = experiment.design["model"]
    evaluation = experiment.design["evaluation"]
    started = time.perf_counter()
    policy = _run_with_heartbeat(
        lambda: BatchedPolicyAdapter(
            model_id=model["model_id"],
            revision=model["revision"],
            adapter_paths={},
            device=device,
            max_new_tokens=evaluation["output_tokens"],
            max_context_tokens=model["context_tokens"],
            max_batch_size=evaluation["batch_size"],
            max_batch_input_tokens=evaluation["batch_input_tokens"],
            training_message_builder=serialize_best_first_message_prefix,
            policy_message_builder=best_first_policy_messages,
        ),
        stage=f"qualification-{device}",
        item="loading model",
        interval=30.0,
    )
    model_load_seconds = time.perf_counter() - started
    requests = _run_with_heartbeat(
        lambda: _qualification_requests(experiment, token_length=policy.input_token_length),
        stage=f"qualification-{device}",
        item="selecting the longest-token probe for each development task",
        interval=30.0,
    )
    batches = form_deterministic_batches(
        requests,
        token_length=policy.input_token_length,
        max_batch_size=evaluation["batch_size"],
        max_batch_input_tokens=evaluation["batch_input_tokens"],
    )
    samples = []
    qualification_started = time.monotonic()
    for batch_index, batch in enumerate(batches, start=1):
        before = time.perf_counter()
        _run_with_heartbeat(
            lambda requests=batch.requests: policy.generate_many(requests),
            stage=f"qualification-{device}",
            item=f"generating batch {batch_index}/{len(batches)}",
            interval=30.0,
        )
        elapsed = time.perf_counter() - before
        samples.append(len(batch.requests) / elapsed)
        _terminal_progress(
            f"qualification-{device}",
            batch_index,
            len(batches),
            qualification_started,
            f"batch_calls={len(batch.requests)} throughput={samples[-1]:.6f}",
        )
    overhead_started = time.perf_counter()
    for _ in range(100):
        form_deterministic_batches(
            requests,
            token_length=policy.input_token_length,
            max_batch_size=evaluation["batch_size"],
            max_batch_input_tokens=evaluation["batch_input_tokens"],
        )
    runtime_seconds_per_call = (time.perf_counter() - overhead_started) / (100 * len(requests))
    payload = {
        "device": device,
        "model_load_seconds": model_load_seconds,
        "outcomes_observed": False,
        "probe_ids": [request.instance_id for request in requests],
        "runtime_seconds_per_call": runtime_seconds_per_call,
        "schema_version": experiment.schema("device_qualification"),
        "throughput_samples": samples,
    }
    path = output_root / "qualification" / f"device-{index}.json"
    _atomic_write_json(path, payload)
    print(_canonical_text({"output": str(path), "status": "PASS"}))
    return 0


def _qualification_requests(experiment, *, token_length) -> tuple[SearchPolicyRequest, ...]:
    by_pair = {task.pair_id: task for task in experiment.tasks}
    requests = []
    for path in experiment.dev_datasets:
        pair_id = path.parent.name
        task = by_pair[pair_id]
        longest: SearchPolicyRequest | None = None
        longest_tokens = -1
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for row_index, line in enumerate(stream):
                row = json.loads(line)
                request = SearchPolicyRequest(
                    session_id=f"qualification:{task.instance_id}:{row_index}",
                    adapter_id=None,
                    seed=17,
                    instance_id=task.instance_id,
                    decision_index=row_index,
                    model_input=json.loads(row["messages"][1]["content"]),
                )
                tokens = token_length(request)
                if tokens > longest_tokens:
                    longest = request
                    longest_tokens = tokens
        if longest is None:
            raise ValueError(f"empty qualification shard: {path}")
        requests.append(longest)
    return tuple(sorted(requests, key=lambda request: request.instance_id))


def _training_plan(
    experiment,
    output_root: Path,
    dataset_root: Path,
    training_device: str,
    master_port: int,
) -> dict[str, Any]:
    checkpoint_root = output_root / "training" / "attempt-001" / "checkpoints"
    return {
        "command": build_best_first_sft_command(
            experiment,
            dataset_root=dataset_root,
            output_root=checkpoint_root,
        ),
        "environment": {
            "CUDA_VISIBLE_DEVICES": training_device,
            "MASTER_PORT": str(master_port),
            "NPROC_PER_NODE": "1",
        },
        "estimated_optimizer_steps": expected_training_steps(experiment),
        "output_root": str(output_root / "training" / "attempt-001"),
        "training_runs": 1,
        "training_seed": 17,
    }


def _train(
    experiment,
    output_root: Path,
    dataset_root: Path,
    *,
    training_device: str,
    master_port: int,
    progress_interval: float,
    resume: bool,
    dry_run: bool,
    qualification_output_root: Path | None = None,
) -> int:
    experiment.require_stage("process_sft_training")
    plan = _training_plan(experiment, output_root, dataset_root, training_device, master_port)
    if dry_run:
        print(_canonical_text({**plan, "dry_run": True, "writes": 0}))
        return 0
    _require_qualification_pass(qualification_output_root or output_root)
    dataset_manifest = _json_object(dataset_root / "manifest.json")
    if dataset_manifest.get("counts") != experiment.training_counts:
        raise ValueError(f"issue #{experiment.source_issue} training dataset coverage is incomplete")
    training_root = output_root / "training"
    report_path = training_root / "training-report.json"
    if report_path.is_file() and _json_object(report_path).get("outcome") == StopOutcome.PASS.value:
        print(_canonical_text({"output": str(report_path), "status": "already_complete"}))
        return 0
    if training_root.exists() and not resume:
        raise FileExistsError(f"issue #{experiment.source_issue} training root exists; pass --resume: {training_root}")
    training_root.mkdir(parents=True, exist_ok=True)
    attempt_number = _next_training_attempt(training_root)
    attempt_root = training_root / f"attempt-{attempt_number:03d}"
    checkpoint_root = attempt_root / "checkpoints"
    resume_checkpoint = _latest_checkpoint(training_root) if resume else None
    attempt_root.mkdir(parents=True)
    command = build_best_first_sft_command(
        experiment,
        dataset_root=dataset_root,
        output_root=checkpoint_root,
        resume_from_checkpoint=resume_checkpoint,
    )
    environment = os.environ.copy()
    environment.update(plan["environment"])
    launch = {
        **plan,
        "attempt": attempt_number,
        "command": command,
        "output_root": str(attempt_root),
        "resume_from_checkpoint": str(resume_checkpoint) if resume_checkpoint is not None else None,
    }
    _atomic_write_json(attempt_root / "launch.json", launch)
    expected = expected_training_steps(experiment)
    started = time.monotonic()
    with (attempt_root / "training.log").open("ab") as log:
        process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert process.stdout is not None
        thread = threading.Thread(target=_tee_output, args=(process.stdout, log, sys.stdout.buffer))
        thread.start()
        while True:
            try:
                returncode = process.wait(timeout=progress_interval)
                break
            except subprocess.TimeoutExpired:
                completed = _latest_logged_step(attempt_root / "training.log", expected)
                _training_progress(completed, expected, started)
        thread.join()
    completed = expected if returncode == 0 else _latest_logged_step(attempt_root / "training.log", expected)
    _training_progress(completed, expected, started)
    final_checkpoint = checkpoint_root / f"checkpoint-{expected}"
    report = {
        "authorization_id": experiment.authorization["authorization_id"],
        "attempt": attempt_number,
        "completed_steps": completed,
        "contract_id": experiment.contract_id,
        "elapsed_seconds": time.monotonic() - started,
        "final_checkpoint": str(final_checkpoint),
        "outcome": (
            StopOutcome.PASS.value if returncode == 0 and final_checkpoint.is_dir() else StopOutcome.INVALID.value
        ),
        "returncode": returncode,
        "schema_version": experiment.schema("training_report"),
        "scientific_completion": False,
        "seed": 17,
        "source_gate_receipt_id": experiment.authorization["gate_receipt"]["receipt_id"],
    }
    _atomic_write_json(attempt_root / "training-report.json", report)
    _atomic_write_json(report_path, report)
    print(_canonical_text({"output": str(report_path), **report}))
    return returncode or (0 if report["outcome"] == StopOutcome.PASS.value else 1)


def _references_plan(experiment, output_root: Path, workers: int) -> dict[str, Any]:
    available_cpus = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count() or 1
    if workers <= 0 or workers > available_cpus:
        raise ValueError("reference worker count must fit the available CPU allocation")
    return {
        "exact_episodes": len(experiment.tasks),
        "output": str(output_root / "references" / "manifest.json"),
        "random_valid_episodes": len(experiment.tasks) * len(experiment.evaluation_seeds),
        "workers": workers,
    }


def _references(experiment, output_root: Path, *, workers: int, resume: bool, dry_run: bool) -> int:
    experiment.require_stage("development_references")
    plan = _references_plan(experiment, output_root, workers)
    if dry_run:
        print(_canonical_text({**plan, "dry_run": True, "writes": 0}))
        return 0
    reference_root = output_root / "references"
    manifest_path = reference_root / "manifest.json"
    if manifest_path.is_file():
        print(_canonical_text({"output": str(manifest_path), "status": "already_complete"}))
        return 0
    if reference_root.exists() and not resume:
        raise FileExistsError(f"issue #{experiment.source_issue} reference root exists; pass --resume: {reference_root}")
    reference_root.mkdir(parents=True, exist_ok=True)
    jobs = _reference_jobs(experiment, reference_root, resume)
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
            "exact_reference": len(experiment.tasks),
            "random_valid": len(experiment.tasks) * len(experiment.evaluation_seeds),
        },
        "outcome": StopOutcome.PASS.value,
        "records": records,
        "schema_version": experiment.schema("references"),
        "source_gate_receipt_id": experiment.authorization["gate_receipt"]["receipt_id"],
    }
    _atomic_write_json(manifest_path, manifest)
    print(_canonical_text({"output": str(manifest_path), "status": "PASS", "records": len(records)}))
    return 0


def _reference_jobs(experiment, root: Path, resume: bool) -> tuple[_ReferenceJob, ...]:
    jobs = []
    for task in experiment.tasks:
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
    return tuple(jobs)


def _run_reference_job(job: _ReferenceJob) -> tuple[int, str, dict[str, Any]]:
    if job.path.is_file():
        if not job.resume:
            raise FileExistsError(f"existing reference requires --resume: {job.path}")
        episode = _read_gzip_json(job.path)
        replay_best_first_model_episode(episode, task=job.task)
        status = f"reused {job.arm} {job.task.instance_id} seed={job.seed}"
    else:
        episode = run_reference_episode(job.task, arm=job.arm, seed=job.seed)
        replay_best_first_model_episode(episode, task=job.task)
        _write_gzip_json(job.path, episode)
        status = f"generated {job.arm} {job.task.instance_id} seed={job.seed}"
    return (
        job.index,
        status,
        _episode_record(
            job.task,
            episode,
            path=job.path,
            seed=None if job.arm == "exact_reference" else job.seed,
        ),
    )


def _evaluation_plan(experiment, output_root: Path, devices: tuple[str, ...]) -> dict[str, Any]:
    if len(devices) != 2 or len(set(devices)) != 2:
        raise ValueError(f"issue #{experiment.source_issue} evaluation requires two distinct A100 devices")
    shards = cost_balanced_task_shards(experiment.tasks, shard_count=len(devices))
    return {
        "devices": list(devices),
        "episodes": len(experiment.tasks) * len(experiment.evaluation_seeds) * 2,
        "output_root": str(output_root / "rollout"),
        "shards": [
            {
                "device": device,
                "index": index,
                "maximum_physical_calls": 2 * sum(task.model_call_limit for task in shard),
                "tasks": [task.instance_id for task in shard],
            }
            for index, (device, shard) in enumerate(zip(devices, shards, strict=True))
        ],
    }


def _evaluate(experiment, output_root: Path, devices: tuple[str, ...], *, resume: bool, dry_run: bool) -> int:
    experiment.require_stage("batched_evaluation")
    plan = _evaluation_plan(experiment, output_root, devices)
    if dry_run:
        print(_canonical_text({**plan, "dry_run": True, "writes": 0}))
        return 0
    _require_qualification_pass(output_root)
    training = _json_object(output_root / "training" / "training-report.json")
    if training.get("outcome") != StopOutcome.PASS.value or not Path(training["final_checkpoint"]).is_dir():
        raise ValueError(f"issue #{experiment.source_issue} final process-SFT checkpoint is unavailable")
    references = _json_object(output_root / "references" / "manifest.json")
    if references.get("outcome") != StopOutcome.PASS.value:
        raise ValueError(f"issue #{experiment.source_issue} references are incomplete")
    rollout_root = output_root / "rollout"
    launch_path = rollout_root / "launch.json"
    if launch_path.is_file():
        if not resume:
            raise FileExistsError(f"issue #{experiment.source_issue} rollout exists; pass --resume: {rollout_root}")
        rollout_started_at = float(_json_object(launch_path)["rollout_started_at"])
    else:
        rollout_started_at = time.time()
        rollout_root.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(launch_path, {**plan, "rollout_started_at": rollout_started_at})
    commands = [
        (
            sys.executable,
            str(Path(__file__).resolve()),
            "--source-issue",
            str(experiment.source_issue),
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
        raise ValueError(f"issue #{experiment.source_issue} rollout shard index is invalid")
    qualification = _require_qualification_pass(output_root)
    selected = set(qualification["coverage"]["task_ids"])
    if selected != {task.instance_id for task in experiment.tasks}:
        raise ValueError("qualification did not authorize the complete issue #64 v3 development panel")
    tasks = cost_balanced_task_shards(experiment.tasks, shard_count=shard_count)[shard_index]
    training = _json_object(output_root / "training" / "training-report.json")
    adapter_path = Path(training["final_checkpoint"])
    shard_root = output_root / "rollout" / f"shard-{shard_index}"
    if shard_root.exists() and not resume:
        raise FileExistsError(f"issue #{experiment.source_issue} rollout shard exists; pass --resume: {shard_root}")
    shard_root.mkdir(parents=True, exist_ok=True)
    task_by_id = {task.instance_id: task for task in tasks}
    records = []
    sessions = []
    for task in tasks:
        task_payload = _json_object(task.task_path)
        for arm, adapter_id in (("pretrained_base", None), ("process_sft", "seed-17")):
            for seed in experiment.evaluation_seeds:
                path = shard_root / "episodes" / arm / f"seed-{seed}" / f"{task.pair_id}.json.gz"
                if path.is_file():
                    episode = _read_gzip_json(path)
                    replay_best_first_model_episode(episode, task=task)
                    records.append(_episode_record(task, episode, path=path, seed=seed))
                    continue
                authority = PDDLStateAuthority.from_pddl(task_payload["domain_pddl"], task_payload["problem_pddl"])
                sessions.append(
                    BestFirstModelSession(
                        authority=authority,
                        task=task,
                        arm=arm,
                        seed=seed,
                        adapter_id=adapter_id,
                    )
                )
    model = experiment.design["model"]
    evaluation = experiment.design["evaluation"]
    policy = _run_with_heartbeat(
        lambda: BatchedPolicyAdapter(
            model_id=model["model_id"],
            revision=model["revision"],
            adapter_paths={"seed-17": adapter_path},
            device=device,
            max_new_tokens=evaluation["output_tokens"],
            max_context_tokens=model["context_tokens"],
            max_batch_size=evaluation["batch_size"],
            max_batch_input_tokens=evaluation["batch_input_tokens"],
            training_message_builder=serialize_best_first_message_prefix,
            policy_message_builder=best_first_policy_messages,
        ),
        stage=f"rollout-{device}",
        item="loading base model and adapter",
        interval=progress_interval,
    )
    total = len(tasks) * len(experiment.evaluation_seeds) * 2
    started = time.monotonic()
    last_progress = 0.0

    def on_complete(session: BestFirstModelSession) -> None:
        episode = session.episode()
        task = task_by_id[session.task.instance_id]
        path = shard_root / "episodes" / session.arm / f"seed-{session.seed}" / f"{task.pair_id}.json.gz"
        _write_gzip_json(path, episode)
        records.append(_episode_record(task, episode, path=path, seed=session.seed))

    def on_progress(completed: int, batches: int, logical_calls: int) -> None:
        nonlocal last_progress
        now = time.monotonic()
        if now - last_progress >= progress_interval or completed == total:
            _terminal_progress(
                f"rollout-{device}",
                completed,
                total,
                started,
                f"batches={batches} logical_calls={logical_calls}",
            )
            last_progress = now

    completed_sessions, launched_batches, logical_calls, stopped = _run_model_sessions(
        sessions,
        policy,
        should_stop=lambda: time.time() - rollout_started_at >= evaluation["rollout_cutoff_seconds"],
        on_complete=on_complete,
        on_progress=on_progress,
    )
    del completed_sessions
    complete = len(records) == total
    manifest = {
        "authorization_id": experiment.authorization["authorization_id"],
        "completed_episodes": len(records),
        "contract_id": experiment.contract_id,
        "device": device,
        "launched_batches": launched_batches,
        "logical_model_calls": logical_calls,
        "outcome": StopOutcome.PASS.value if complete else StopOutcome.VALID_STOP.value,
        "records": sorted(records, key=lambda row: (row["arm"], row["seed"], row["instance_id"])),
        "schema_version": experiment.schema("rollout_shard"),
        "shard_count": shard_count,
        "shard_index": shard_index,
        "stop_reason": "wall_clock_cutoff" if stopped else None,
        "source_gate_receipt_id": experiment.authorization["gate_receipt"]["receipt_id"],
        "total_episodes": total,
    }
    _atomic_write_json(shard_root / "manifest.json", manifest)
    print(_canonical_text({"output": str(shard_root / "manifest.json"), **manifest}))
    return 0


def _run_model_sessions(sessions, policy, *, should_stop, on_complete, on_progress):
    active = {session.session_id: session for session in sessions}
    completed = []
    batches = 0
    logical_calls = 0
    stopped = False
    while active:
        if should_stop():
            stopped = True
            break
        requests = []
        newly_complete = []
        for session_id in sorted(active):
            session = active[session_id]
            request = session.next_request()
            if request is None:
                newly_complete.append(session)
            else:
                requests.append(request)
        for session in newly_complete:
            completed.append(session)
            on_complete(session)
            active.pop(session.session_id)
        if not requests:
            on_progress(len(completed), batches, logical_calls)
            continue
        deterministic_batches = form_deterministic_batches(
            requests,
            token_length=policy.input_token_length,
            max_batch_size=policy.max_batch_size,
            max_batch_input_tokens=policy.max_batch_input_tokens,
        )
        for batch in deterministic_batches:
            if should_stop():
                stopped = True
                break
            outputs = _run_with_heartbeat(
                lambda requests=batch.requests: policy.generate_many(requests),
                stage="rollout-generation",
                item=f"batch={batches + 1} requests={len(batch.requests)}",
                interval=30.0,
            )
            batches += 1
            logical_calls += len(batch.requests)
            for request, output in zip(batch.requests, outputs, strict=True):
                session = active[request.session_id]
                session.submit_output(output)
                if session.complete:
                    completed.append(session)
                    on_complete(session)
                    active.pop(session.session_id)
            on_progress(len(completed), batches, logical_calls)
        if stopped:
            break
    return tuple(completed), batches, logical_calls, stopped


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
    adjudication_root = output_root / "adjudication"
    if qualification["coverage"]["outcome"] != StopOutcome.PASS.value:
        report = {
            "contract_id": experiment.contract_id,
            "outcome": StopOutcome.VALID_STOP.value,
            "reason": "outcome-blind hardware qualification did not certify complete coverage",
            "schema_version": experiment.schema("adjudication"),
            "scientific_completion": False,
        }
        _write_adjudication(adjudication_root, report)
        return 0
    references = _json_object(Path(plan["references"]))
    shards = [_json_object(Path(path)) for path in plan["rollout_shards"]]
    if references.get("outcome") != StopOutcome.PASS.value or any(
        shard.get("outcome") != StopOutcome.PASS.value for shard in shards
    ):
        report = {
            "contract_id": experiment.contract_id,
            "outcome": StopOutcome.VALID_STOP.value,
            "reason": "complete selected rollout coverage was not retained before the cutoff",
            "schema_version": experiment.schema("adjudication"),
            "scientific_completion": False,
        }
        _write_adjudication(adjudication_root, report)
        return 0
    task_by_id = {task.instance_id: task for task in experiment.tasks}
    reference_rows = list(references["records"])
    rollout_rows = [row for shard in shards for row in shard["records"]]
    all_rows = [*reference_rows, *rollout_rows]
    started = time.monotonic()
    try:
        for index, row in enumerate(all_rows, start=1):
            episode = _read_gzip_json(_ROOT / row["path"])
            replay_best_first_model_episode(episode, task=task_by_id[row["instance_id"]])
            _terminal_progress("adjudication-replay", index, len(all_rows), started, row["instance_id"])
        metrics = adjudicate_best_first(
            expected_tasks=experiment.tasks,
            seeds=experiment.evaluation_seeds,
            exact_rows=[row for row in reference_rows if row["arm"] == "exact_reference"],
            random_rows=[row for row in reference_rows if row["arm"] == "random_valid"],
            base_rows=[row for row in rollout_rows if row["arm"] == "pretrained_base"],
            process_rows=[row for row in rollout_rows if row["arm"] == "process_sft"],
            bootstrap_resamples=experiment.design["evaluation"]["bootstrap_resamples"],
            bootstrap_seed=experiment.design["evaluation"]["bootstrap_seed"],
        )
        report = {
            "contract_id": experiment.contract_id,
            "metrics": metrics,
            "outcome": metrics["outcome"],
            "replayed_episodes": len(all_rows),
            "schema_version": experiment.schema("adjudication"),
            "scientific_completion": metrics["scientific_completion"],
        }
    except ValueError as error:
        report = {
            "contract_id": experiment.contract_id,
            "outcome": StopOutcome.INVALID.value,
            "reason": str(error),
            "schema_version": experiment.schema("adjudication"),
            "scientific_completion": False,
        }
    _write_adjudication(adjudication_root, report)
    return 0


def _write_adjudication(root: Path, report: Mapping[str, Any]) -> None:
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
    print(_canonical_text({"output": str(root / "report.json"), **report}))


def _require_qualification_pass(output_root: Path) -> dict[str, Any]:
    qualification = _json_object(output_root / "qualification" / "qualification.json")
    if qualification.get("coverage", {}).get("outcome") != StopOutcome.PASS.value:
        raise ValueError("best-first qualification did not authorize model training or rollout")
    return qualification


def _episode_record(
    task: BestFirstDevelopmentTask,
    episode: Mapping[str, Any],
    *,
    path: Path,
    seed: int | None,
) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        retained_path = resolved.relative_to(_ROOT).as_posix()
    except ValueError:
        retained_path = str(resolved)
    return {
        "arm": episode["arm"],
        "difficulty": task.difficulty,
        "domain_id": task.domain_id,
        "instance_id": task.instance_id,
        "pair_id": task.pair_id,
        "path": retained_path,
        "result": episode["result"],
        "seed": seed,
    }


def _next_training_attempt(root: Path) -> int:
    attempts = []
    for path in root.glob("attempt-*"):
        try:
            attempts.append(int(path.name.removeprefix("attempt-")))
        except ValueError:
            continue
    return max(attempts, default=0) + 1


def _latest_checkpoint(root: Path) -> Path | None:
    checkpoints = []
    for path in root.glob("attempt-*/checkpoints/checkpoint-*"):
        try:
            step = int(path.name.removeprefix("checkpoint-"))
        except ValueError:
            continue
        if path.is_dir() and (path / "trainer_state.json").is_file():
            checkpoints.append((step, path))
    return max(checkpoints, default=(0, None))[1]


def _latest_logged_step(path: Path, expected: int) -> int:
    if not path.is_file():
        return 0
    with path.open("rb") as stream:
        stream.seek(max(0, stream.seek(0, os.SEEK_END) - 1_000_000))
        text = stream.read().decode("utf-8", errors="replace")
    matches = re.findall(r"(?<![\d.])(\d+)\s*/\s*(\d+)(?![\d.])", text)
    return max((int(current) for current, total in matches if int(total) == expected), default=0)


def _training_progress(completed: int, total: int, started: float) -> None:
    elapsed = time.monotonic() - started
    eta = elapsed / completed * (total - completed) if completed else None
    print(
        _canonical_text(
            {
                "completed_steps": completed,
                "elapsed_seconds": elapsed,
                "estimated_remaining_seconds": eta,
                "stage": "training",
                "total_steps": total,
            }
        ),
        flush=True,
    )


def _terminal_progress(stage: str, completed: int, total: int, started: float, item: str) -> None:
    elapsed = time.monotonic() - started
    eta = elapsed / completed * (total - completed) if completed else None
    print(
        _canonical_text(
            {
                "completed": completed,
                "elapsed_seconds": elapsed,
                "estimated_remaining_seconds": eta,
                "item": item,
                "stage": stage,
                "total": total,
            }
        ),
        flush=True,
    )


def _run_children(commands: Sequence[Sequence[str]], *, prefixes: Sequence[str]) -> int:
    lock = threading.Lock()

    def run(command: Sequence[str], prefix: str) -> int:
        process = subprocess.Popen(
            command,
            cwd=_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            with lock:
                print(f"[{prefix}] {line}", end="", flush=True)
        return process.wait()

    with ThreadPoolExecutor(max_workers=len(commands)) as executor:
        futures = [executor.submit(run, command, prefix) for command, prefix in zip(commands, prefixes, strict=True)]
        return 1 if any(future.result() != 0 for future in futures) else 0


def _tee_output(source: BinaryIO, log: BinaryIO, terminal: BinaryIO) -> None:
    while chunk := source.read(8192):
        log.write(chunk)
        log.flush()
        terminal.write(chunk)
        terminal.flush()


def _run_with_heartbeat(function, *, stage: str, item: str, interval: float):
    finished = threading.Event()
    started = time.monotonic()

    def heartbeat() -> None:
        while not finished.wait(interval):
            print(
                _canonical_text(
                    {
                        "elapsed_seconds": time.monotonic() - started,
                        "item": item,
                        "stage": stage,
                        "status": "running",
                    }
                ),
                flush=True,
            )

    thread = threading.Thread(target=heartbeat)
    thread.start()
    try:
        return function()
    finally:
        finished.set()
        thread.join()


def _read_gzip_json(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"expected gzip JSON object: {path}")
    return value


def _write_gzip_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=6) as stream:
        stream.write(_canonical_text(value) + "\n")
    temporary.replace(path)


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(_canonical_text(value) + "\n", encoding="utf-8")
    temporary.replace(path)


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
