"""Run the governed issue-59 BFWS process-SFT development gate."""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping, Sequence

from examples.planning_benchmark_slice.bfws_issue59 import (
    BFWSBatchedPolicy,
    BFWSDevelopmentTask,
    BFWSModelRequest,
    BFWSModelSession,
    adjudicate_bfws_structural_gate,
    bfws_episode_payload,
    build_bfws_sft_command,
    load_bfws_issue59,
    materialize_random_valid_bfws_reference,
    replay_bfws_episode,
    run_bfws_sessions,
    select_bfws_coverage,
)
from examples.planning_benchmark_slice.bfws_model_input import bfws_text_policy_training_messages
from examples.planning_benchmark_slice.episode_evidence import replay_episode_evidence
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    StopOutcome,
    evaluate_execution_permission,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT_ROOT = _REPO_ROOT / "outputs" / "bfws_phase" / "issue59-v1"
_SEEDS = (17, 29, 43, 71, 101)
_STAGES = ("preflight", "references", "train", "qualify", "evaluate", "adjudicate", "all", "evaluate-shard")
_REFERENCE_MODEL: tuple[str, str] | None = None
_REFERENCE_TOKEN_COUNTER: Callable[[Mapping[str, Any]], int] | None = None


@dataclass(frozen=True, slots=True)
class _ReferenceJob:
    ordinal: int
    arm: str
    task: BFWSDevelopmentTask
    evidence_path: Path
    relative_path: str
    seed: int | None
    exact_result: Mapping[str, Any] | None = None


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=_STAGES)
    parser.add_argument("--output-root", type=Path, default=_OUTPUT_ROOT)
    parser.add_argument("--devices", nargs="+", default=("cuda:0", "cuda:1"))
    parser.add_argument("--device")
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--attempt-id", default="issue-59-bfws-structural-gate-v1")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--progress-interval-seconds", type=float, default=60.0)
    parser.add_argument("--reference-workers", type=int, default=min(8, _available_cpus()))
    args = parser.parse_args(arguments)
    if args.progress_interval_seconds <= 0:
        raise ValueError("progress interval must be positive")
    if args.reference_workers <= 0:
        raise ValueError("reference workers must be positive")
    if args.reference_workers > _available_cpus():
        raise ValueError("reference workers cannot exceed the available CPU affinity")
    experiment = load_bfws_issue59(_REPO_ROOT)
    output_root = args.output_root.resolve()

    if args.stage == "preflight":
        print(_canonical_text({**experiment.preflight(), "dry_run": args.dry_run}))
        return 0
    if args.stage == "references":
        return _references(
            experiment,
            output_root,
            dry_run=args.dry_run,
            resume=args.resume,
            workers=args.reference_workers,
        )
    if args.stage == "train":
        return _train(
            experiment,
            output_root,
            devices=tuple(args.devices),
            dry_run=args.dry_run,
            smoke=args.smoke,
            progress_interval=args.progress_interval_seconds,
        )
    if args.stage == "qualify":
        return _qualify(experiment, output_root, devices=tuple(args.devices), dry_run=args.dry_run)
    if args.stage == "evaluate":
        return _evaluate(
            output_root,
            devices=tuple(args.devices),
            attempt_id=args.attempt_id,
            resume=args.resume,
            dry_run=args.dry_run,
        )
    if args.stage == "evaluate-shard":
        if args.device is None or args.shard_index is None:
            raise ValueError("evaluate-shard requires --device and --shard-index")
        return _evaluate_shard(
            experiment,
            output_root,
            device=args.device,
            shard_index=args.shard_index,
            attempt_id=args.attempt_id,
            resume=args.resume,
            dry_run=args.dry_run,
        )
    if args.stage == "adjudicate":
        return _adjudicate(experiment, output_root, attempt_id=args.attempt_id, dry_run=args.dry_run)
    if args.dry_run:
        plans = {
            "preflight": experiment.preflight(),
            "references": _references_plan(
                experiment,
                output_root,
                workers=args.reference_workers,
                resume=args.resume,
            ),
            "train": _training_plans(experiment, output_root, tuple(args.devices), smoke=args.smoke),
            "qualify": _qualification_plan(experiment, output_root, tuple(args.devices)),
            "evaluate": _evaluation_commands(output_root, tuple(args.devices), args.attempt_id, resume=args.resume),
            "adjudicate": _adjudication_plan(output_root, args.attempt_id),
        }
        print(_canonical_text({"dry_run": True, "stages": plans}))
        return 0
    for stage in ("references", "train", "qualify"):
        forwarded = [stage, "--output-root", str(output_root), "--attempt-id", args.attempt_id]
        forwarded.extend(("--devices", *args.devices))
        forwarded.extend(("--reference-workers", str(args.reference_workers)))
        if args.resume:
            forwarded.append("--resume")
        returncode = main(forwarded)
        if returncode != 0:
            return returncode
    qualification = _json_object(output_root / "qualification.json")
    if qualification.get("coverage", {}).get("outcome") == StopOutcome.PASS.value:
        forwarded = [
            "evaluate",
            "--output-root",
            str(output_root),
            "--attempt-id",
            args.attempt_id,
            "--devices",
            *args.devices,
        ]
        if args.resume:
            forwarded.append("--resume")
        returncode = main(forwarded)
        if returncode != 0:
            return returncode
    return main(["adjudicate", "--output-root", str(output_root), "--attempt-id", args.attempt_id])


def _references_plan(experiment, output_root: Path, *, workers: int, resume: bool) -> dict[str, Any]:
    episode_root = output_root / "references" / "episodes" / "random_valid"
    return {
        "conditions": {"exact_bfws": len(experiment.tasks), "random_valid": len(experiment.tasks) * len(_SEEDS)},
        "existing_random_valid_episodes": sum(1 for _path in episode_root.glob("seed-*/*.json.gz")),
        "output": str(output_root / "references" / "manifest.json"),
        "progress": "one terminal record per completed episode with elapsed time and ETA",
        "resume": resume,
        "workers": workers,
    }


def _references(experiment, output_root: Path, *, dry_run: bool, resume: bool, workers: int) -> int:
    plan = _references_plan(experiment, output_root, workers=workers, resume=resume)
    if dry_run:
        print(_canonical_text({**plan, "dry_run": True}))
        return 0
    root = output_root / "references"
    manifest_path = root / "manifest.json"
    if manifest_path.is_file():
        print(_canonical_text({"output": str(manifest_path), "status": "already_complete"}))
        return 0
    if root.exists() and not resume:
        raise FileExistsError(f"BFWS references output exists; pass --resume: {root}")
    root.mkdir(parents=True, exist_ok=True)
    gate_receipt, authorization_receipt = _execution_receipts(
        experiment.phase_gate.phase_id,
        "issue-59-bfws-references-v1",
        root,
    )
    jobs = _reference_jobs(experiment, root)
    records: list[dict[str, Any] | None] = [None] * len(jobs)
    completed = 0
    started = time.monotonic()
    model = experiment.phase_gate.components["training"]["model"]
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers,
        initializer=_initialize_reference_worker,
        initargs=(str(model["model_id"]), str(model["revision"])),
    ) as executor:
        futures = {executor.submit(_run_reference_job, job): job for job in jobs}
        for future in concurrent.futures.as_completed(futures):
            ordinal, item, status, record = future.result()
            records[ordinal] = record
            completed += 1
            _terminal_progress("references", completed, len(jobs), started, f"{item}:{status}")
    if any(record is None for record in records):
        raise RuntimeError("parallel BFWS references did not return every deterministic record")
    manifest = {
        "counts": {"exact_bfws": len(experiment.tasks), "random_valid": len(experiment.tasks) * len(_SEEDS)},
        "authorization_receipt": authorization_receipt.to_dict(),
        "gate_receipt": gate_receipt.to_dict(),
        "phase_receipt": experiment.phase_gate.receipt(stage="development_references"),
        "records": records,
        "schema_version": "bfws_issue59_references_v1",
    }
    _atomic_write_json(manifest_path, manifest)
    print(_canonical_text({"output": str(manifest_path), "status": "completed"}))
    return 0


def _reference_jobs(experiment, root: Path) -> tuple[_ReferenceJob, ...]:
    trace_rows = {row["instance_id"]: row for row in experiment.trace_manifest["traces"] if row["split"] == "dev"}
    jobs = []
    for task in experiment.tasks:
        exact = trace_rows[task.instance_id]
        exact_path = _REPO_ROOT / "data" / "bfws_phase_v1" / "exact-traces" / exact["evidence"]["path"]
        jobs.append(
            _ReferenceJob(
                ordinal=len(jobs),
                arm="exact_bfws",
                task=task,
                evidence_path=exact_path,
                relative_path=str(exact_path),
                seed=None,
                exact_result=exact["result"],
            )
        )
        for seed in _SEEDS:
            relative = Path("episodes") / "random_valid" / f"seed-{seed}" / f"{task.instance_id}.json.gz"
            jobs.append(
                _ReferenceJob(
                    ordinal=len(jobs),
                    arm="random_valid",
                    task=task,
                    evidence_path=root / relative,
                    relative_path=relative.as_posix(),
                    seed=seed,
                )
            )
    return tuple(jobs)


def _initialize_reference_worker(model_id: str, revision: str) -> None:
    global _REFERENCE_MODEL, _REFERENCE_TOKEN_COUNTER
    _REFERENCE_MODEL = (model_id, revision)
    _REFERENCE_TOKEN_COUNTER = None


def _run_reference_job(job: _ReferenceJob) -> tuple[int, str, str, dict[str, Any]]:
    if job.arm == "exact_bfws":
        replayed = replay_episode_evidence(job.evidence_path)
        if replayed["result"]["goal_reached"] is not True or job.exact_result is None:
            raise ValueError(f"exact BFWS reference replay failed: {job.task.instance_id}")
        record = {
            "arm": "exact_bfws",
            "evidence": {"path": job.relative_path, "size_bytes": job.evidence_path.stat().st_size},
            "instance_id": job.task.instance_id,
            "result": {"invariant_valid_success": True, **job.exact_result},
            "seed": None,
        }
        return job.ordinal, job.task.instance_id, "replayed", record
    if job.seed is None:
        raise ValueError("random-valid BFWS reference job requires a seed")
    payload, status = materialize_random_valid_bfws_reference(
        task=job.task,
        seed=job.seed,
        evidence_path=job.evidence_path,
        input_token_counter=_reference_token_counter(),
    )
    record = {
        "arm": "random_valid",
        "evidence": {"path": job.relative_path, "size_bytes": job.evidence_path.stat().st_size},
        "instance_id": job.task.instance_id,
        "result": payload["result"],
        "seed": job.seed,
    }
    return job.ordinal, f"{job.task.instance_id}:seed-{job.seed}", status, record


def _reference_token_counter() -> Callable[[Mapping[str, Any]], int]:
    global _REFERENCE_TOKEN_COUNTER
    if _REFERENCE_TOKEN_COUNTER is None:
        if _REFERENCE_MODEL is None:
            raise RuntimeError("BFWS reference worker was not initialized")
        _REFERENCE_TOKEN_COUNTER = _token_counter_for_model(*_REFERENCE_MODEL)
    return _REFERENCE_TOKEN_COUNTER


def _training_plans(experiment, output_root: Path, devices: tuple[str, ...], *, smoke: bool) -> list[dict[str, Any]]:
    if not devices:
        raise ValueError("BFWS training requires at least one device")
    plans = []
    for index, seed in enumerate(_SEEDS):
        attempt_root, attempt_id = _next_training_attempt(output_root, seed)
        if attempt_root is None:
            continue
        device = devices[index % len(devices)]
        command = build_bfws_sft_command(
            experiment,
            seed=seed,
            output_root=attempt_root / "checkpoints",
            world_size=1,
            smoke=smoke,
        )
        plans.append(
            {
                "attempt_id": attempt_id,
                "command": command,
                "device": device,
                "expected_optimizer_steps": 1 if smoke else _expected_steps(experiment),
                "output_root": str(attempt_root),
                "phase_id": experiment.phase_gate.phase_id,
                "phase_receipt": experiment.phase_gate.receipt(stage="process_sft_training"),
                "seed": seed,
                "smoke": smoke,
            }
        )
    return plans


def _train(
    experiment,
    output_root: Path,
    *,
    devices: tuple[str, ...],
    dry_run: bool,
    smoke: bool,
    progress_interval: float,
) -> int:
    plans = _training_plans(experiment, output_root, devices, smoke=smoke)
    if dry_run:
        print(_canonical_text({"dry_run": True, "launches": plans}))
        return 0
    _require_reference_gate(experiment, output_root)
    if not plans:
        print(_canonical_text({"status": "all_training_seeds_complete"}))
        return 0
    by_device: dict[str, list[dict[str, Any]]] = {device: [] for device in devices}
    for plan in plans:
        by_device[str(plan["device"])].append(plan)

    def run_queue(queue: list[dict[str, Any]]) -> int:
        for plan in queue:
            returncode = _run_training_plan(plan, progress_interval=progress_interval)
            if returncode != 0:
                return returncode
        return 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(devices)) as executor:
        results = list(executor.map(run_queue, (queue for queue in by_device.values() if queue)))
    return max(results, default=0)


def _run_training_plan(plan: Mapping[str, Any], *, progress_interval: float) -> int:
    root = Path(str(plan["output_root"]))
    root.mkdir(parents=True)
    gate_receipt, authorization_receipt = _execution_receipts(
        str(plan["phase_id"]),
        str(plan["attempt_id"]),
        root,
    )
    environment = os.environ.copy()
    environment.update(
        {
            "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
            "CUDA_VISIBLE_DEVICES": str(plan["device"]).removeprefix("cuda:"),
            "NPROC_PER_NODE": "1",
            "PYTHONHASHSEED": str(plan["seed"]),
        }
    )
    environment_keys = (
        "CUBLAS_WORKSPACE_CONFIG",
        "CUDA_VISIBLE_DEVICES",
        "NPROC_PER_NODE",
        "PYTHONHASHSEED",
    )
    launch = {
        **dict(plan),
        "authorization_receipt": authorization_receipt.to_dict(),
        "environment": {key: environment[key] for key in environment_keys},
        "gate_receipt": gate_receipt.to_dict(),
    }
    _atomic_write_json(root / "launch.json", launch)
    started = time.monotonic()
    log_path = root / "training.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            plan["command"],
            cwd=_REPO_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        assert process.stdout is not None
        thread = threading.Thread(target=_tee_output, args=(process.stdout, log, sys.stdout.buffer), daemon=True)
        thread.start()
        while True:
            try:
                returncode = process.wait(timeout=progress_interval)
                break
            except subprocess.TimeoutExpired:
                completed = _latest_step(log_path, int(plan["expected_optimizer_steps"]))
                _terminal_progress(
                    f"train-seed-{plan['seed']}",
                    completed,
                    int(plan["expected_optimizer_steps"]),
                    started,
                    str(plan["attempt_id"]),
                )
        thread.join()
    checkpoints = sorted((root / "checkpoints").glob("checkpoint-*"), key=_checkpoint_step)
    report = {
        "checkpoint_paths": [str(path.resolve()) for path in checkpoints if path.is_dir()],
        "elapsed_seconds": time.monotonic() - started,
        "outcome": StopOutcome.PASS.value if returncode == 0 else StopOutcome.INVALID.value,
        "returncode": returncode,
        "schema_version": "bfws_issue59_training_report_v1",
        "seed": plan["seed"],
        "smoke": plan["smoke"],
        "status": "training_completed" if returncode == 0 else "training_failed",
    }
    _atomic_write_json(root / "training-report.json", report)
    print(_canonical_text({"output": str(root / "training-report.json"), **report}), flush=True)
    return returncode


def _qualification_plan(experiment, output_root: Path, devices: tuple[str, ...]) -> dict[str, Any]:
    return {
        "adapter_paths": {str(seed): str(_expected_final_checkpoint(output_root, seed)) for seed in _SEEDS},
        "coverage_order": ["full_development", "preregistered_exact_cost_panel"],
        "devices": devices,
        "development_tasks": len(experiment.tasks),
        "inference_dtype": "float32",
        "output": str(output_root / "qualification.json"),
        "probes": 6,
        "uses_model_outcomes": False,
    }


def _qualify(experiment, output_root: Path, *, devices: tuple[str, ...], dry_run: bool) -> int:
    plan = _qualification_plan(experiment, output_root, devices)
    if dry_run:
        print(_canonical_text({**plan, "dry_run": True}))
        return 0
    _require_reference_gate(experiment, output_root)
    if len(devices) != 2 or len(set(devices)) != 2:
        raise ValueError("BFWS qualification is frozen to two distinct GPU devices")
    adapters = {f"seed-{seed}": _final_checkpoint(output_root, seed) for seed in _SEEDS}
    gate_receipt, authorization_receipt = _execution_receipts(
        experiment.phase_gate.phase_id,
        "issue-59-bfws-hardware-qualification-v1",
        output_root / "qualification",
    )
    snapshots = _jsonl_objects(
        _REPO_ROOT / "data" / "bfws_phase_v1" / "exact-traces" / "manifests" / "bfws-teacher-snapshots.jsonl"
    )
    model = experiment.phase_gate.components["training"]["model"]
    load_samples: list[float] = []
    throughput_samples: list[float] = []
    runtime_samples: list[float] = []
    for device in devices:
        before = time.perf_counter()
        policy = BFWSBatchedPolicy(
            model_id=model["model_id"],
            revision=model["revision"],
            adapter_paths=adapters,
            device=device,
        )
        load_samples.append(time.perf_counter() - before)
        base_probes = tuple(_probe_request(row, None) for row in snapshots)
        if not policy.verify_scalar_batch_parity(base_probes) or not policy.verify_repeated_batch(base_probes):
            raise ValueError(f"BFWS scalar/batch or repeated-batch probe failed on {device}")
        for adapter_id in (None, *adapters):
            probes = tuple(_probe_request(row, adapter_id) for row in snapshots)
            before = time.perf_counter()
            policy._generate_uncached(adapter_id, probes)
            throughput_samples.append(len(probes) / (time.perf_counter() - before))
        before = time.perf_counter()
        for _ in range(100):
            from examples.planning_benchmark_slice.bfws_issue59 import _deterministic_batches

            _deterministic_batches(base_probes, policy)
        runtime_samples.append((time.perf_counter() - before) / (100 * len(base_probes)))
        del policy
        import torch

        torch.cuda.empty_cache()
    qualification = select_bfws_coverage(
        experiment.tasks,
        model_load_seconds=max(load_samples),
        throughput_samples=throughput_samples,
        runtime_seconds_per_call=max(runtime_samples),
    )
    payload = {
        **qualification.to_dict(),
        "authorization_receipt": authorization_receipt.to_dict(),
        "gate_started_at_unix": time.time(),
        "gate_receipt": gate_receipt.to_dict(),
        "phase_id": experiment.phase_gate.phase_id,
        "plan": plan,
    }
    _atomic_write_json(output_root / "qualification.json", payload)
    print(_canonical_text({"output": str(output_root / "qualification.json"), **payload["coverage"]}))
    return 0


def _probe_request(row: Mapping[str, Any], adapter_id: str | None) -> BFWSModelRequest:
    return BFWSModelRequest(
        session_id=f"probe:{adapter_id or 'base'}:{row['instance_id']}:{row['record_index']}",
        adapter_id=adapter_id,
        seed=17,
        instance_id=str(row["instance_id"]),
        decision_index=int(row["record_index"]),
        model_input=row["input"],
        observation={},
    )


def _evaluation_commands(output_root: Path, devices: tuple[str, ...], attempt_id: str, *, resume: bool):
    if len(devices) != 2:
        raise ValueError("BFWS evaluation is frozen to two devices")
    commands = []
    for index, device in enumerate(devices):
        command = [
            sys.executable,
            "scripts/run_bfws_issue59.py",
            "evaluate-shard",
            "--output-root",
            str(output_root),
            "--device",
            device,
            "--shard-index",
            str(index),
            "--attempt-id",
            f"{attempt_id}-shard-{index}",
        ]
        if resume:
            command.append("--resume")
        commands.append(tuple(command))
    return commands


def _evaluate(output_root: Path, *, devices: tuple[str, ...], attempt_id: str, resume: bool, dry_run: bool) -> int:
    commands = _evaluation_commands(output_root, devices, attempt_id, resume=resume)
    if dry_run:
        print(
            _canonical_text(
                {
                    "commands": commands,
                    "dry_run": True,
                    "progress": "per-round calls, completed episodes, elapsed time, and ETA",
                }
            )
        )
        return 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(_run_console_command, commands))
    return max(results)


def _evaluate_shard(
    experiment,
    output_root: Path,
    *,
    device: str,
    shard_index: int,
    attempt_id: str,
    resume: bool,
    dry_run: bool,
) -> int:
    if shard_index not in (0, 1):
        raise ValueError("BFWS rollout shard index must be 0 or 1")
    qualification_path = output_root / "qualification.json"
    if dry_run:
        print(
            _canonical_text(
                {
                    "device": device,
                    "dry_run": True,
                    "qualification": str(qualification_path),
                    "shard_index": shard_index,
                }
            )
        )
        return 0
    qualification = _json_object(qualification_path)
    coverage = qualification.get("coverage")
    if not isinstance(coverage, dict) or coverage.get("outcome") != StopOutcome.PASS.value:
        raise ValueError("BFWS rollout lacks a PASS hardware qualification")
    selected_ids = set(coverage["task_ids"])
    selected = tuple(task for task in experiment.tasks if task.instance_id in selected_ids)
    shards = _cost_shards(selected)
    assigned = shards[shard_index]
    adapters = {f"seed-{seed}": _final_checkpoint(output_root, seed) for seed in _SEEDS}
    root = output_root / "rollout" / f"shard-{shard_index}"
    gate_receipt, authorization_receipt = _execution_receipts(
        experiment.phase_gate.phase_id,
        attempt_id,
        root,
    )
    launch = {
        "authorization_receipt": authorization_receipt.to_dict(),
        "attempt_id": attempt_id,
        "coverage_mode": coverage["mode"],
        "device": device,
        "gate_receipt": gate_receipt.to_dict(),
        "phase_id": experiment.phase_gate.phase_id,
        "shard_index": shard_index,
        "task_ids": [task.instance_id for task in assigned],
    }
    if root.exists():
        if not resume or _json_object(root / "launch.json") != launch:
            raise ValueError("existing BFWS rollout requires --resume and an identical launch")
    else:
        root.mkdir(parents=True)
    if not (root / "launch.json").exists():
        _atomic_write_json(root / "launch.json", launch)
    model = experiment.phase_gate.components["training"]["model"]
    policy = BFWSBatchedPolicy(
        model_id=model["model_id"],
        revision=model["revision"],
        adapter_paths=adapters,
        device=device,
    )
    sessions: list[BFWSModelSession] = []
    completed_records = []
    for task in assigned:
        authority = _authority(task)
        for arm, seed, adapter_id in _model_variants():
            relative = _episode_relative(arm, seed, task.instance_id)
            path = root / relative
            if path.is_file():
                payload = _read_gzip_json(path)
                replay_bfws_episode(payload, authority=authority, input_token_counter=policy.input_token_count)
                completed_records.append(_model_record(task, arm, seed, relative, path, payload))
                continue
            sessions.append(
                BFWSModelSession(
                    authority=authority,
                    instance_id=task.instance_id,
                    arm=arm,
                    seed=seed,
                    max_model_calls=task.model_call_limit,
                    max_expansions=task.exact_expansions,
                    accepted_delta_limit=16,
                    max_input_bytes=10_000_000,
                    max_input_tokens=7_808,
                    input_token_counter=policy.input_token_count,
                    adapter_id=adapter_id,
                )
            )
    task_by_id = {task.instance_id: task for task in assigned}
    assigned_count = len(assigned) * 10
    started = time.monotonic()
    last_progress = [0.0]

    def on_complete(session: BFWSModelSession) -> None:
        task = task_by_id[session.instance_id]
        relative = _episode_relative(session.arm, session.seed, session.instance_id)
        path = root / relative
        payload = bfws_episode_payload(session)
        _write_gzip_json(path, payload)
        completed_records.append(_model_record(task, session.arm, session.seed, relative, path, payload))

    def on_progress(completed: int, total: int, calls: int) -> None:
        now = time.monotonic()
        if now - last_progress[0] >= 30 or completed == total:
            last_progress[0] = now
            _terminal_progress(
                f"rollout-shard-{shard_index}",
                len(completed_records),
                assigned_count,
                started,
                f"model_calls={calls}",
            )

    cutoff = float(qualification["gate_started_at_unix"]) + 18 * 60 * 60
    run_bfws_sessions(
        sessions,
        policy,
        should_stop=lambda: time.time() >= cutoff,
        on_complete=on_complete,
        on_progress=on_progress,
    )
    manifest = {
        "assigned_episode_count": assigned_count,
        "authorization_receipt": authorization_receipt.to_dict(),
        "completed_episode_count": len(completed_records),
        "coverage_mode": coverage["mode"],
        "outcome": (StopOutcome.PASS if len(completed_records) == assigned_count else StopOutcome.VALID_STOP).value,
        "gate_receipt": gate_receipt.to_dict(),
        "phase_receipt": experiment.phase_gate.receipt(stage="development_structural_gate"),
        "records": sorted(completed_records, key=lambda row: (row["arm"], row["seed"], row["instance_id"])),
        "schema_version": "bfws_issue59_rollout_shard_v1",
        "shard_index": shard_index,
    }
    _atomic_write_json(root / "manifest.json", manifest)
    summary = {key: manifest[key] for key in ("assigned_episode_count", "completed_episode_count", "outcome")}
    print(_canonical_text({"output": str(root / "manifest.json"), **summary}))
    return 0


def _model_variants():
    for seed in _SEEDS:
        yield "pretrained_base", seed, None
    for seed in _SEEDS:
        yield "process_sft", seed, f"seed-{seed}"


def _model_record(task, arm: str, seed: int, relative: Path, path: Path, payload: Mapping[str, Any]):
    return {
        "arm": arm,
        "difficulty": task.difficulty,
        "domain_id": task.domain_id,
        "evidence": {"path": relative.as_posix(), "size_bytes": path.stat().st_size},
        "instance_id": task.instance_id,
        "result": payload["result"],
        "seed": seed,
    }


def _adjudication_plan(output_root: Path, attempt_id: str) -> dict[str, Any]:
    return {
        "attempt_id": attempt_id,
        "inputs": [
            str(output_root / "references" / "manifest.json"),
            str(output_root / "qualification.json"),
            str(output_root / "rollout" / "shard-0" / "manifest.json"),
            str(output_root / "rollout" / "shard-1" / "manifest.json"),
        ],
        "output": str(output_root / "adjudication" / "report.json"),
        "replay_required": True,
    }


def _adjudicate(experiment, output_root: Path, *, attempt_id: str, dry_run: bool) -> int:
    plan = _adjudication_plan(output_root, attempt_id)
    if dry_run:
        print(_canonical_text({**plan, "dry_run": True}))
        return 0
    binding = ReceiptBinding(experiment.phase_gate.phase_id, attempt_id, output_root / "adjudication")
    execution_gate, execution_authorization = _execution_receipts(
        experiment.phase_gate.phase_id,
        f"{attempt_id}-execution",
        output_root / "adjudication-execution",
    )
    coverage: Mapping[str, Any] = {}
    try:
        qualification = _json_object(output_root / "qualification.json")
        raw_coverage = qualification.get("coverage")
        if not isinstance(raw_coverage, dict):
            raise ValueError("BFWS qualification coverage is malformed")
        coverage = raw_coverage
        report = _adjudication_metrics(experiment, output_root, qualification, coverage)
    except (KeyError, OSError, TypeError, ValueError) as error:
        report = {
            "error": str(error),
            "outcome": StopOutcome.INVALID.value,
            "scientific_completion": False,
        }
    outcome = StopOutcome(report["outcome"])
    ancestor_gate = None
    if outcome is StopOutcome.ANCESTOR_STOP:
        ancestor_gate = GateReceipt(
            ReceiptBinding(
                experiment.phase_gate.phase_id,
                f"{attempt_id}-exact-reference",
                output_root / "adjudication" / "exact-reference",
            ),
            StopOutcome.VALID_STOP,
        )
    gate = GateReceipt(
        binding,
        outcome,
        ancestor_receipt_id=ancestor_gate.receipt_id if ancestor_gate is not None else None,
    )
    report.update(
        {
            "attempt_id": attempt_id,
            "coverage": coverage,
            "execution_authorization_receipt": execution_authorization.to_dict(),
            "execution_gate_receipt": execution_gate.to_dict(),
            "gate_receipt": gate.to_dict(),
            "phase_receipt": experiment.phase_gate.receipt(stage="development_structural_gate"),
            "schema_version": "bfws_issue59_structural_gate_v1",
        }
    )
    if ancestor_gate is not None:
        report["ancestor_gate_receipt"] = ancestor_gate.to_dict()
    if outcome is not StopOutcome.PASS:
        report["downstream_run_receipt"] = evaluate_execution_permission(
            binding=binding,
            gate_receipt=gate,
            authorization_receipt=None,
            ancestor_receipt_id=gate.ancestor_receipt_id,
        ).to_dict()
    adjudication_root = output_root / "adjudication"
    if adjudication_root.exists():
        raise FileExistsError(f"BFWS adjudication output already exists: {adjudication_root}")
    adjudication_root.mkdir(parents=True)
    _atomic_write_json(adjudication_root / "report.json", report)
    _atomic_write_json(adjudication_root / "gate-receipt.json", gate.to_dict())
    print(_canonical_text({"outcome": outcome.value, "output": str(adjudication_root / "report.json")}))
    return 1 if outcome is StopOutcome.INVALID else 0


def _adjudication_metrics(experiment, output_root: Path, qualification, coverage) -> dict[str, Any]:
    if qualification.get("phase_id") != experiment.phase_gate.phase_id:
        raise ValueError("BFWS qualification belongs to a different governed phase")
    if coverage.get("outcome") == StopOutcome.VALID_STOP.value:
        return {
            "outcome": StopOutcome.VALID_STOP.value,
            "reason": "hardware qualification could not certify full or preregistered panel coverage",
            "scientific_completion": False,
        }
    if coverage.get("outcome") != StopOutcome.PASS.value or coverage.get("mode") not in {
        "full_development",
        "preregistered_exact_cost_panel",
    }:
        raise ValueError("BFWS qualification does not authorize a selected rollout panel")
    selected_ids = set(coverage.get("task_ids", []))
    task_by_id = {task.instance_id: task for task in experiment.tasks if task.instance_id in selected_ids}
    if set(task_by_id) != selected_ids or not selected_ids:
        raise ValueError("BFWS qualification selected unknown or empty development coverage")

    references = _json_object(output_root / "references" / "manifest.json")
    if (
        references.get("schema_version") != "bfws_issue59_references_v1"
        or references.get("phase_receipt") != experiment.phase_gate.receipt(stage="development_references")
        or not isinstance(references.get("records"), list)
    ):
        raise ValueError("BFWS references are not the authorized issue #59 product")
    reference_rows = references["records"]
    exact = [row for row in reference_rows if row["arm"] == "exact_bfws" and row["instance_id"] in selected_ids]
    random_rows = [row for row in reference_rows if row["arm"] == "random_valid" and row["instance_id"] in selected_ids]
    counter = _token_counter(experiment)
    total = len(selected_ids) * 16
    completed = 0
    started = time.monotonic()
    for row in exact:
        evidence = row["evidence"]
        path = Path(evidence["path"])
        if path.stat().st_size != evidence["size_bytes"]:
            raise ValueError(f"exact BFWS evidence size differs: {row['instance_id']}")
        replayed = replay_episode_evidence(path)
        if replayed["result"]["goal_reached"] is not True:
            raise ValueError(f"exact BFWS evidence replay failed: {row['instance_id']}")
        completed += 1
        _terminal_progress("adjudication-replay", completed, total, started, row["instance_id"])
    for row in random_rows:
        task = task_by_id[row["instance_id"]]
        path = output_root / "references" / row["evidence"]["path"]
        _replay_model_record(row, path, task, counter)
        completed += 1
        _terminal_progress("adjudication-replay", completed, total, started, row["instance_id"])

    rollout_rows = []
    for shard_index in (0, 1):
        root = output_root / "rollout" / f"shard-{shard_index}"
        manifest = _json_object(root / "manifest.json")
        if manifest.get("outcome") != StopOutcome.PASS.value:
            return {
                "outcome": StopOutcome.VALID_STOP.value,
                "reason": "rollout cutoff left incomplete selected coverage",
                "scientific_completion": False,
            }
        if (
            manifest.get("schema_version") != "bfws_issue59_rollout_shard_v1"
            or manifest.get("phase_receipt") != experiment.phase_gate.receipt(stage="development_structural_gate")
            or manifest.get("coverage_mode") != coverage["mode"]
            or not isinstance(manifest.get("records"), list)
        ):
            raise ValueError("BFWS rollout manifest differs from its authorization or qualification")
        for row in manifest["records"]:
            task = task_by_id[row["instance_id"]]
            path = root / row["evidence"]["path"]
            _replay_model_record(row, path, task, counter)
            completed += 1
            _terminal_progress("adjudication-replay", completed, total, started, row["instance_id"])
            rollout_rows.append(row)
    if completed != total:
        raise ValueError("BFWS independent replay did not cover every selected episode")
    base = [row for row in rollout_rows if row["arm"] == "pretrained_base"]
    process = [row for row in rollout_rows if row["arm"] == "process_sft"]
    threshold = experiment.phase_gate.components["threshold"]
    report = adjudicate_bfws_structural_gate(
        expected_ids=selected_ids,
        seeds=_SEEDS,
        exact_rows=exact,
        random_rows=random_rows,
        base_rows=base,
        process_rows=process,
        thresholds=threshold["metrics"],
        bootstrap_resamples=int(threshold["bootstrap"]["resamples"]),
        bootstrap_seed=int(threshold["bootstrap"]["seed"]),
    )
    report["independently_replayed_episode_count"] = completed
    if time.time() - float(qualification["gate_started_at_unix"]) > 20 * 60 * 60:
        report["outcome"] = StopOutcome.VALID_STOP.value
        report["scientific_completion"] = False
        report["reason"] = "20-hour gate deadline exceeded before adjudication"
    return report


def _replay_model_record(row, path: Path, task: BFWSDevelopmentTask, counter) -> None:
    evidence = row.get("evidence")
    if not isinstance(evidence, dict) or path.stat().st_size != evidence.get("size_bytes"):
        raise ValueError(f"BFWS model evidence size differs: {row.get('instance_id')}")
    payload = _read_gzip_json(path)
    result = replay_bfws_episode(payload, authority=_authority(task), input_token_counter=counter)
    if result != row.get("result"):
        raise ValueError(f"BFWS model evidence result differs: {row.get('instance_id')}")


def _token_counter(experiment):
    model = experiment.phase_gate.components["training"]["model"]
    return _token_counter_for_model(str(model["model_id"]), str(model["revision"]))


def _token_counter_for_model(model_id: str, revision: str) -> Callable[[Mapping[str, Any]], int]:
    from transformers import AutoProcessor

    tokenizer = AutoProcessor.from_pretrained(model_id, revision=revision).tokenizer

    def count(model_input: Mapping[str, Any]) -> int:
        return len(
            tokenizer.apply_chat_template(
                bfws_text_policy_training_messages(model_input),
                tokenize=True,
                add_generation_prompt=True,
            )
        )

    return count


def _require_reference_gate(experiment, output_root: Path) -> None:
    manifest = _json_object(output_root / "references" / "manifest.json")
    records = manifest.get("records")
    if (
        manifest.get("schema_version") != "bfws_issue59_references_v1"
        or manifest.get("phase_receipt") != experiment.phase_gate.receipt(stage="development_references")
        or manifest.get("counts") != {"exact_bfws": 35, "random_valid": 175}
        or not isinstance(records, list)
    ):
        raise ValueError("BFWS process SFT requires the complete authorized reference product")
    exact = [row for row in records if row.get("arm") == "exact_bfws"]
    if len(exact) != 35 or any(row.get("result", {}).get("goal_reached") is not True for row in exact):
        raise ValueError("BFWS process SFT requires exact-reference invariant-valid success 1.0")


def _authority(task: BFWSDevelopmentTask) -> PDDLStateAuthority:
    return PDDLStateAuthority.from_pddl(
        task.domain_path.read_text(encoding="utf-8"),
        task.problem_path.read_text(encoding="utf-8"),
    )


def _cost_shards(tasks: Sequence[BFWSDevelopmentTask]):
    shards: list[list[BFWSDevelopmentTask]] = [[], []]
    loads = [0, 0]
    for task in sorted(tasks, key=lambda item: (-item.model_call_limit, item.instance_id)):
        index = min((0, 1), key=lambda value: (loads[value], value))
        shards[index].append(task)
        loads[index] += task.model_call_limit
    return tuple(tuple(sorted(shard, key=lambda item: item.instance_id)) for shard in shards)


def _available_cpus() -> int:
    affinity = getattr(os, "sched_getaffinity", None)
    if affinity is not None:
        return max(1, len(affinity(0)))
    return max(1, os.cpu_count() or 1)


def _episode_relative(arm: str, seed: int, instance_id: str) -> Path:
    return Path("episodes") / arm / f"seed-{seed}" / f"{instance_id}.json.gz"


def _next_training_attempt(output_root: Path, seed: int):
    parent = output_root / "training"
    roots = sorted(parent.glob(f"seed-{seed}-attempt-*")) if parent.is_dir() else []
    for root in roots:
        report_path = root / "training-report.json"
        if report_path.is_file():
            report = _json_object(report_path)
            if report.get("status") == "training_completed" and report.get("smoke") is False:
                return None, None
    number = len(roots) + 1
    return parent / f"seed-{seed}-attempt-{number:03d}", f"issue-59-process-sft-seed-{seed}-attempt-{number:03d}"


def _final_checkpoint(output_root: Path, seed: int) -> Path:
    roots = sorted((output_root / "training").glob(f"seed-{seed}-attempt-*"))
    completed = []
    for root in roots:
        report_path = root / "training-report.json"
        if not report_path.is_file():
            continue
        report = _json_object(report_path)
        if (
            report.get("status") == "training_completed"
            and report.get("returncode") == 0
            and report.get("smoke") is False
        ):
            paths = [Path(path) for path in report.get("checkpoint_paths", [])]
            if paths:
                completed.append(max(paths, key=_checkpoint_step))
    if not completed:
        raise FileNotFoundError(f"seed {seed} has no completed BFWS final checkpoint")
    selected = completed[-1]
    if not selected.is_dir():
        raise FileNotFoundError(selected)
    return selected.resolve()


def _expected_final_checkpoint(output_root: Path, seed: int) -> Path:
    try:
        return _final_checkpoint(output_root, seed)
    except FileNotFoundError:
        return output_root / "training" / f"seed-{seed}-attempt-001" / "checkpoints" / "checkpoint-4482"


def _expected_steps(experiment) -> int:
    count = int(experiment.training_manifest["counts"]["train"])
    optimization = experiment.phase_gate.components["training"]["optimization"]
    return math.ceil(count / int(optimization["global_batch_size"])) * int(optimization["epochs"])


def _checkpoint_step(path: Path) -> int:
    match = re.fullmatch(r"checkpoint-(\d+)", path.name)
    return int(match.group(1)) if match else -1


def _latest_step(path: Path, expected: int) -> int:
    if not path.is_file():
        return 0
    with path.open("rb") as stream:
        stream.seek(max(0, stream.seek(0, os.SEEK_END) - 1_000_000))
        text = stream.read().decode("utf-8", errors="replace")
    matches = re.findall(r"(?<![\d.])(\d+)\s*/\s*(\d+)(?![\d.])", text)
    values = [int(current) for current, total in matches if int(total) == expected]
    return max(values, default=0)


def _tee_output(source: BinaryIO, log: BinaryIO, terminal: BinaryIO) -> None:
    while chunk := source.read(8192):
        log.write(chunk)
        log.flush()
        terminal.write(chunk)
        terminal.flush()


def _run_console_command(command: Sequence[str]) -> int:
    print(_canonical_text({"command": command, "status": "launching"}), flush=True)
    return subprocess.run(command, cwd=_REPO_ROOT, check=False).returncode


def _execution_receipts(contract_id: str, attempt_id: str, output_root: Path):
    binding = ReceiptBinding(contract_id, attempt_id, output_root)
    gate = GateReceipt(binding, StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding, gate.receipt_id)
    permission = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )
    if not permission.start_permitted:
        raise RuntimeError("BFWS governed execution receipts did not permit the run")
    return gate, authorization


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


def _read_gzip_json(path: Path) -> dict[str, Any]:
    value = json.loads(gzip.decompress(path.read_bytes()))
    if not isinstance(value, dict):
        raise ValueError(f"expected gzip JSON object: {path}")
    return value


def _write_gzip_json(path: Path, value: object) -> None:
    payload = gzip.compress((_canonical_text(value) + "\n").encode("utf-8"), compresslevel=6, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"expected JSON objects: {path}")
    return rows


def _atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(_canonical_text(value) + "\n", encoding="utf-8")
    temporary.replace(path)


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
