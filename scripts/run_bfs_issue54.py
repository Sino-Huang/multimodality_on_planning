"""Run one stage of the governed issue-54 BFS sanity workflow."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from scripts.run_bfs_base_seeds import SeedLaunch, run_seed_launches

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT_ROOT = _REPO_ROOT / "outputs" / "bfs_phase"
_DATASET_ROOT = _REPO_ROOT / "data" / "bfs_pilot_v3" / "ms-swift-process"
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v3.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v3.json"
_STAGES = ("diagnose", "probe", "references", "base", "train", "evaluate", "adjudicate")


def reference_command(*, output_root: Path, workers: int, dry_run: bool) -> tuple[str, ...]:
    command = (
        sys.executable,
        "scripts/run_bfs_references.py",
        "--phase",
        "v3",
        "--output-root",
        str(output_root / "issue54-v3-references"),
        "--attempt-id",
        "issue-54-v3-references",
        "--shard-index",
        "0",
        "--shard-count",
        "1",
        "--workers",
        str(workers),
    )
    return (*command, "--dry-run") if dry_run else command


def training_launches(
    *,
    seeds: Sequence[int],
    devices: Sequence[str],
    output_root: Path,
    dataset_root: Path,
) -> tuple[SeedLaunch, ...]:
    reference_manifest = output_root / "issue54-v3-references" / "manifests" / "bfs-references.json"
    launches = []
    for index, seed in enumerate(seeds):
        device = devices[index % len(devices)]
        attempt = _next_training_attempt(output_root, seed)
        if attempt is None:
            continue
        training_root, attempt_id = attempt
        command = (
            sys.executable,
            "scripts/run_bfs_sft.py",
            "--phase",
            "v3",
            "--dataset-root",
            str(dataset_root),
            "--reference-manifest",
            str(reference_manifest),
            "--output-root",
            str(training_root),
            "--view",
            "process",
            "--seed",
            str(seed),
            "--world-size",
            "1",
            "--devices",
            device,
            "--master-port",
            str(29600 + index),
            "--attempt-id",
            attempt_id,
        )
        launches.append(
            SeedLaunch(
                seed=seed,
                device=device,
                attempt_id=attempt_id,
                output_root=training_root,
                console_log=training_root.parent / f"{training_root.name}.console.log",
                command=command,
            )
        )
    return tuple(launches)


def training_commands(
    *,
    seeds: Sequence[int],
    devices: Sequence[str],
    output_root: Path,
    dataset_root: Path,
    dry_run: bool,
) -> tuple[tuple[str, ...], ...]:
    launches = training_launches(
        seeds=seeds,
        devices=devices,
        output_root=output_root,
        dataset_root=dataset_root,
    )
    return tuple((*launch.command, "--dry-run") if dry_run else launch.command for launch in launches)


def checkpoint_launches(
    *,
    seeds: Sequence[int],
    devices: Sequence[str],
    output_root: Path,
    resume: bool = False,
) -> tuple[SeedLaunch, ...]:
    launches = []
    launch_index = 0
    for seed in seeds:
        training_root = _successful_training_root(output_root, seed)
        report_path = training_root / "training-report.json"
        report = _json_object(report_path)
        checkpoints = report.get("checkpoint_paths")
        if (
            not isinstance(checkpoints, list)
            or not checkpoints
            or any(not isinstance(path, str) for path in checkpoints)
        ):
            raise ValueError(f"training report has no checkpoint paths: {report_path}")
        for checkpoint_text in checkpoints:
            checkpoint = Path(checkpoint_text).expanduser().resolve()
            if not checkpoint.is_dir():
                raise ValueError(f"process-SFT checkpoint does not exist: {checkpoint}")
            checkpoint_name = checkpoint.name
            device = devices[launch_index % len(devices)]
            launch_index += 1
            evaluation_root = output_root / f"issue54-v3-process-seed-{seed}-{checkpoint_name}"
            attempt_id = f"issue-54-v3-process-seed-{seed}-{checkpoint_name}"
            command = (
                sys.executable,
                "scripts/run_bfs_model_shard.py",
                "--arm",
                "process_sft",
                "--adapter-path",
                str(checkpoint),
                "--output-root",
                str(evaluation_root),
                "--attempt-id",
                attempt_id,
                "--device",
                f"cuda:{device}",
                "--seed",
                str(seed),
                "--shard-index",
                "0",
                "--shard-count",
                "1",
            )
            launches.append(
                SeedLaunch(
                    seed=seed,
                    device=device,
                    attempt_id=attempt_id,
                    output_root=evaluation_root,
                    console_log=evaluation_root.parent / f"{evaluation_root.name}.console.log",
                    command=(*command, "--resume") if resume else command,
                )
            )
    return tuple(launches)


def _next_training_attempt(output_root: Path, seed: int) -> tuple[Path, str] | None:
    roots = _training_attempt_roots(output_root, seed)
    if any(_is_successful_training(root) for root in roots):
        return None
    next_attempt = len(roots) + 1
    output_name = f"issue54-v3-process-sft-seed-{seed}"
    attempt_id = f"issue-54-v3-process-sft-seed-{seed}"
    if next_attempt > 1:
        suffix = f"-attempt-{next_attempt:03d}"
        output_name += suffix
        attempt_id += suffix
    return output_root / output_name, attempt_id


def _successful_training_root(output_root: Path, seed: int) -> Path:
    successful = [root for root in _training_attempt_roots(output_root, seed) if _is_successful_training(root)]
    if not successful:
        raise ValueError(f"seed {seed} has no successful process-SFT training attempt")
    return successful[-1]


def _training_attempt_roots(output_root: Path, seed: int) -> list[Path]:
    first = output_root / f"issue54-v3-process-sft-seed-{seed}"
    roots = [first] if first.is_dir() else []
    roots.extend(sorted(output_root.glob(f"{first.name}-attempt-*")))
    return roots


def _is_successful_training(root: Path) -> bool:
    report_path = root / "training-report.json"
    if not report_path.is_file():
        return False
    report = _json_object(report_path)
    checkpoints = report.get("checkpoint_paths")
    return (
        report.get("returncode") == 0
        and report.get("status") == "training_completed"
        and isinstance(checkpoints, list)
        and bool(checkpoints)
        and all(isinstance(path, str) and Path(path).is_dir() for path in checkpoints)
    )


def adjudication_command(
    *,
    seeds: Sequence[int],
    checkpoint_runs: Sequence[SeedLaunch],
    output_root: Path,
    dry_run: bool,
) -> tuple[str, ...]:
    command = [
        sys.executable,
        "scripts/adjudicate_bfs_sanity_v3.py",
        "--reference-manifest",
        str(output_root / "issue54-v3-references" / "manifests" / "bfs-references.json"),
        "--output-root",
        str(output_root / "issue54-v3-sanity-adjudication"),
        "--attempt-id",
        "issue-54-v3-sanity-adjudication",
    ]
    for seed in seeds:
        command.extend(
            (
                "--base-manifest",
                str(output_root / f"issue54-v3-base-seed-{seed}" / "manifest.json"),
            )
        )
    for launch in checkpoint_runs:
        command.extend(("--process-manifest", str(launch.output_root / "manifest.json")))
    if dry_run:
        command.append("--dry-run")
    return tuple(command)


def _run_command(command: Sequence[str], *, label: str) -> int:
    print(json.dumps({"command": command, "stage": label}, sort_keys=True), flush=True)
    return subprocess.run(command, cwd=_REPO_ROOT, check=False).returncode


def _run_sequential(commands: Sequence[Sequence[str]], *, label: str) -> int:
    for index, command in enumerate(commands, start=1):
        returncode = _run_command(command, label=f"{label}-{index}-of-{len(commands)}")
        if returncode != 0:
            return returncode
    return 0


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=_STAGES)
    parser.add_argument("--devices", nargs="+", default=("0", "1"))
    parser.add_argument("--reference-workers", type=int, default=8)
    parser.add_argument("--inference-processes-per-gpu", type=int, default=3)
    parser.add_argument("--training-processes-per-gpu", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-tokenizer", action="store_true")
    parser.add_argument("--probe-seed", type=int, default=17)
    parser.add_argument("--probe-checkpoint-step", type=int, default=1260)
    parser.add_argument("--probe-device", default="cuda:0")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)
    devices = tuple(args.devices)
    if not devices or len(set(devices)) != len(devices):
        raise ValueError("devices must be a non-empty unique list")
    if args.inference_processes_per_gpu <= 0 or args.training_processes_per_gpu <= 0:
        raise ValueError("per-GPU process counts must be positive")
    if args.resume and args.stage not in {"base", "evaluate"}:
        raise ValueError("--resume is supported only for base and checkpoint evaluation")

    if args.stage == "diagnose":
        command = [sys.executable, "scripts/diagnose_bfs_issue54.py"]
        if args.skip_tokenizer:
            command.append("--skip-tokenizer")
        if args.dry_run:
            command.append("--dry-run")
        return _run_command(command, label="diagnose")
    if args.stage == "probe":
        training_root = _successful_training_root(_OUTPUT_ROOT, args.probe_seed)
        checkpoint = training_root / "checkpoints" / f"checkpoint-{args.probe_checkpoint_step}"
        command = [
            sys.executable,
            "scripts/probe_bfs_issue54_adapter.py",
            "--adapter-path",
            str(checkpoint),
            "--device",
            args.probe_device,
            "--seed",
            str(args.probe_seed),
            "--output",
            str(
                _OUTPUT_ROOT
                / "issue54-v3-diagnostics"
                / f"adapter-probe-seed-{args.probe_seed}-checkpoint-{args.probe_checkpoint_step}.json"
            ),
        ]
        if args.dry_run:
            command.append("--dry-run")
        return _run_command(command, label="probe")

    phase_gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    seeds = tuple(phase_gate.freeze["seeds"])
    if args.stage == "references":
        return _run_command(
            reference_command(output_root=_OUTPUT_ROOT, workers=args.reference_workers, dry_run=args.dry_run),
            label="references",
        )
    if args.stage == "base":
        command = [
            sys.executable,
            "scripts/run_bfs_base_seeds.py",
            "--devices",
            *devices,
            "--processes-per-gpu",
            str(args.inference_processes_per_gpu),
        ]
        if args.resume:
            command.append("--resume")
        if args.dry_run:
            command.append("--dry-run")
        return _run_command(command, label="base")
    if args.stage == "train":
        launches = training_launches(
            seeds=seeds,
            devices=devices,
            output_root=_OUTPUT_ROOT,
            dataset_root=_DATASET_ROOT,
        )
        if args.dry_run:
            return _run_sequential([(*launch.command, "--dry-run") for launch in launches], label="train")
        return run_seed_launches(launches, processes_per_gpu=args.training_processes_per_gpu)

    launches = checkpoint_launches(seeds=seeds, devices=devices, output_root=_OUTPUT_ROOT, resume=args.resume)
    if args.stage == "evaluate":
        if args.dry_run:
            return _run_sequential(
                [(*launch.command, "--dry-run") for launch in launches],
                label="evaluate",
            )
        return run_seed_launches(launches, processes_per_gpu=args.inference_processes_per_gpu)
    return _run_command(
        adjudication_command(
            seeds=seeds,
            checkpoint_runs=launches,
            output_root=_OUTPUT_ROOT,
            dry_run=args.dry_run,
        ),
        label="adjudicate",
    )


if __name__ == "__main__":
    raise SystemExit(main())
