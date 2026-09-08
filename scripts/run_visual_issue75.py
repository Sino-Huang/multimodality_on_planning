"""Run the governed visual matrix; dry-runs never load weights or start experiments."""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.modality_view_preparation import write_json
from examples.planning_benchmark_slice.scene_assets import read_json
from examples.planning_benchmark_slice.visual_experiment import ALGORITHMS, VisualExperiment, select_coverage
from examples.planning_benchmark_slice.visual_jobs import adjudicate, qualify_device, run_jobs
from examples.planning_benchmark_slice.visual_model import train_visual
from src.data_collect.governance import StopOutcome

RUNNER_STARTED = time.monotonic()


def log(stage, **fields):
    fields.setdefault("completed", 0)
    fields.setdefault("total", 0)
    elapsed = fields.setdefault("elapsed_seconds", round(time.monotonic() - RUNNER_STARTED, 2))
    completed, total = fields["completed"], fields["total"]
    fields.setdefault("eta_seconds", round(elapsed / completed * (total - completed), 2) if completed else None)
    print(json.dumps({"stage": stage, **fields}), flush=True)


def heartbeat(function, stage):
    stopped = threading.Event()
    started = time.monotonic()

    def beat():
        while not stopped.wait(20):
            log(f"{stage}:heartbeat", elapsed_seconds=round(time.monotonic() - started, 2))

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        return function()
    finally:
        stopped.set()
        thread.join()


def commands(experiment, stage, config_path, resume):
    c = experiment.config
    base = [sys.executable, "-u", str(ROOT / "scripts/run_visual_issue75.py")]
    jobs = []
    if stage in ("qualify", "evaluate"):
        slots = range(len(c["devices"]))
    elif stage == "references":
        slots = range(len(c["backend_endpoints"]))
    elif stage == "train":
        slots = range(len(ALGORITHMS))
    else:
        return []
    for index in slots:
        worker = index % len(c["devices"]) if stage == "train" else index
        command = [*base, "_" + stage, "--config", str(config_path), "--worker", str(worker)]
        if stage == "train":
            command.extend(["--algorithm", ALGORITHMS[index]])
        if resume:
            command.append("--resume")
        jobs.append(
            {
                "command": command,
                "worker": worker,
                "environment": {
                    "CUDA_VISIBLE_DEVICES": "" if stage == "references" else c["devices"][worker],
                    "MASTER_PORT": str(
                        c["master_ports"][worker] if worker < len(c["master_ports"]) else c["master_ports"][0] + worker
                    ),
                    "TOKENIZERS_PARALLELISM": "false",
                    "PYTHONUNBUFFERED": "1",
                },
            }
        )
    return jobs


def run_children(experiment, stage, jobs):
    root = experiment.output / "launches" / stage
    root.mkdir(parents=True, exist_ok=True)
    # One sequential queue per GPU/backend: no overlapping model copies or rendezvous ports.
    queues = {}
    for index, job in enumerate(jobs):
        queues.setdefault(job["worker"], []).append((index, job))

    cancelled = threading.Event()
    lock = threading.Lock()
    running = set()
    failures = []

    def queue(items):
        try:
            for index, job in items:
                if cancelled.is_set():
                    return
                if time.monotonic() >= experiment.deadline():
                    raise RuntimeError("VALID_STOP: cutoff before child launch")
                env = os.environ.copy()
                env.update(job["environment"])
                write_json(root / f"launch-{index}.json", job)
                with (root / f"worker-{index}.log").open("a") as output:
                    with lock:
                        if cancelled.is_set():
                            return
                        process = subprocess.Popen(
                            job["command"],
                            env=env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1,
                            cwd=ROOT,
                        )
                        running.add(process)
                    assert process.stdout is not None
                    for line in process.stdout:
                        output.write(line)
                        output.flush()
                        print(f"[{stage}:{index}] {line}", end="", flush=True)
                    code = process.wait()
                    with lock:
                        running.discard(process)
                if cancelled.is_set():
                    return
                if code:
                    stage_name = {
                        "qualify": "qualification",
                        "train": "training",
                        "evaluate": "evaluation",
                        "references": "references",
                    }[stage]
                    name = (
                        job["command"][job["command"].index("--algorithm") + 1]
                        if stage == "train"
                        else str(job["worker"])
                    )
                    report = read_json(experiment.output / stage_name / f"{name}.json")
                    raise RuntimeError(f"{report['outcome']}: {report.get('reason','worker stopped')}")
        except Exception as error:
            with lock:
                if not failures:
                    failures.append(error)
                cancelled.set()
                for process in running:
                    if process.poll() is None:
                        process.terminate()

    with ThreadPoolExecutor(max_workers=len(queues)) as pool:
        futures = [pool.submit(queue, items) for items in queues.values()]
        for future in futures:
            future.result()
    if failures:
        raise failures[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=[
            "all",
            "qualify",
            "references",
            "train",
            "evaluate",
            "adjudicate",
            "_qualify",
            "_references",
            "_train",
            "_evaluate",
        ],
    )
    parser.add_argument("--config", type=Path, default=ROOT / "configs/experiments/issue75/experiment.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--worker", type=int, default=0)
    parser.add_argument("--algorithm", choices=ALGORITHMS)
    args = parser.parse_args(argv)
    experiment = None
    owns_attempt = False
    worker_scope = False
    started = time.monotonic()
    try:
        experiment = VisualExperiment(args.config)
        plan = experiment.plan()
        stages = ["qualify", "references", "train", "evaluate", "adjudicate"] if args.stage == "all" else [args.stage]
        if args.dry_run:
            log(
                "dry-run:complete",
                **plan,
                completed=1,
                total=1,
                commands={stage: commands(experiment, stage, args.config, args.resume) for stage in stages},
                elapsed_seconds=round(time.monotonic() - started, 2),
            )
            return 0
        if args.stage.startswith("_"):
            stage = args.stage[1:]
            c = experiment.config
            worker_count = len(c["backend_endpoints"]) if stage == "references" else len(c["devices"])
            if args.worker not in range(worker_count):
                raise ValueError("worker is outside the authorized device/backend mapping")
            worker_scope = True
            experiment.require(stage)
            if stage != "references" and (
                os.environ.get("CUDA_VISIBLE_DEVICES") != c["devices"][args.worker]
                or os.environ.get("MASTER_PORT") != str(c["master_ports"][args.worker])
            ):
                raise ValueError("GPU/MASTER_PORT mapping differs from authorized launch")

            def progress(stage, **fields):
                log(stage, worker=args.worker, elapsed_seconds=round(time.monotonic() - started, 2), **fields)

            if stage == "qualify":
                result = heartbeat(lambda: qualify_device(experiment, args.worker, progress), "qualification")
                output = experiment.output / "qualification" / f"{args.worker}.json"
            elif stage == "train":
                if not args.algorithm:
                    raise ValueError("training worker requires an algorithm")
                output = experiment.output / "training" / f"{args.algorithm}.json"
                if output.exists() and read_json(output).get("outcome") == "PASS":
                    log("training:already_complete", algorithm=args.algorithm)
                    return 0
                result = heartbeat(
                    lambda: train_visual(
                        c,
                        ROOT,
                        args.algorithm,
                        experiment.output / "training" / args.algorithm,
                        deadline=experiment.deadline(),
                        progress=progress,
                        resume=args.resume,
                    ),
                    "training",
                )
            else:
                result = heartbeat(
                    lambda: run_jobs(experiment, args.worker, stage == "references", progress, args.resume), stage
                )
                output = experiment.output / ("evaluation" if stage == "evaluate" else stage) / f"{args.worker}.json"
            write_json(output, {"contract_id": c["contract_id"], **result})
            return 0
        experiment.start(args.resume)
        owns_attempt = True
        for stage in stages:
            experiment.require(stage)
            report_name = {"qualify": "qualification", "train": "training", "evaluate": "evaluation"}.get(stage, stage)
            output = experiment.output / f"{report_name}.json"
            if output.exists() and read_json(output).get("outcome") == "PASS" and stage != "adjudicate":
                if not args.resume:
                    raise ValueError("existing stage requires --resume")
                log(f"{stage}:already_complete")
                continue
            log(f"{stage}:start", elapsed_seconds=round(time.monotonic() - started, 2))
            if stage == "adjudicate":
                report = heartbeat(lambda: adjudicate(experiment, log), stage)
            else:
                launches = commands(experiment, stage, args.config, args.resume)
                heartbeat(lambda stage=stage, launches=launches: run_children(experiment, stage, launches), stage)
                if stage == "qualify":
                    report = select_coverage(
                        experiment,
                        [
                            read_json(experiment.output / "qualification" / f"{i}.json")
                            for i in range(len(experiment.config["devices"]))
                        ],
                    )
                elif stage == "train":
                    report = {
                        "contract_id": experiment.config["contract_id"],
                        "outcome": "PASS",
                        "training_runs": [read_json(experiment.output / "training" / f"{a}.json") for a in ALGORITHMS],
                    }
                else:
                    reports = [read_json(experiment.output / report_name / f"{i}.json") for i in range(len(launches))]
                    report = {
                        "contract_id": experiment.config["contract_id"],
                        "outcome": "PASS",
                        "episodes": [e for r in reports for e in r["episodes"]],
                    }
            write_json(output, report)
            log(f"{stage}:complete", outcome=report["outcome"], elapsed_seconds=round(time.monotonic() - started, 2))
            if report["outcome"] != "PASS":
                raise RuntimeError(f"{report['outcome']}: {report.get('reason','frozen threshold failed')}")
        if args.stage in ("all", "adjudicate"):
            receipt = replace(
                experiment.permission, run_state="completed", start_permitted=False, scientific_completion=True
            )
            write_json(experiment.output / "result.json", {**report, "receipt": receipt.to_dict()})
            log(
                "matrix:complete",
                outcome=report["outcome"],
                completed=1,
                total=1,
                report=str(experiment.output / "result.json"),
            )
        return 0
    except Exception as error:
        message = str(error)
        outcome = (
            "ANCESTOR_STOP"
            if message.startswith("ANCESTOR_STOP:")
            else "VALID_STOP" if message.startswith("VALID_STOP:") or "out of memory" in message.lower() else "INVALID"
        )
        report = {
            "outcome": outcome,
            "reason": message,
            "scientific_completion": False,
            "requested_stage": args.stage,
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
        if experiment is not None:
            report["contract_id"] = experiment.config["contract_id"]
            if not args.dry_run and (owns_attempt or worker_scope) and (experiment.output / "attempt.json").exists():
                receipt = replace(
                    experiment.permission,
                    outcome=StopOutcome(outcome),
                    start_permitted=False,
                    scientific_completion=False,
                    run_state="invalid-not-run" if outcome == "INVALID" else "gated-not-run",
                    reason=message,
                    ancestor_receipt_id=(
                        f"stage:{experiment.config['contract_id']}:{args.stage}" if outcome == "ANCESTOR_STOP" else None
                    ),
                )
                report["receipt"] = receipt.to_dict()
                if args.stage.startswith("_"):
                    stage = {
                        "_qualify": "qualification",
                        "_train": "training",
                        "_evaluate": "evaluation",
                        "_references": "references",
                    }[args.stage]
                    target = (
                        experiment.output / stage / f'{args.algorithm if args.stage=="_train" else args.worker}.json'
                    )
                    if not target.exists() or read_json(target).get("outcome") != "PASS":
                        write_json(target, report)
                elif not (experiment.output / "result.json").exists():
                    write_json(experiment.output / "result.json", report)
        log("stopped", **report)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
