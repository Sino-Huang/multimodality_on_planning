"""Run one stage of the governed issue-54 BFS sanity workflow."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from examples.planning_benchmark_slice.bfs_phase import BFSPhaseGate, load_bfs_phase_gate
from scripts.run_bfs_base_seeds import SeedLaunch, run_seed_launches

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT_ROOT = _REPO_ROOT / "outputs" / "bfs_phase"
_DATASET_ROOTS = {
    "v3": _REPO_ROOT / "data" / "bfs_pilot_v3" / "ms-swift-process",
    "v6": _REPO_ROOT / "data" / "bfs_pilot_v6" / "ms-swift-process",
}
_PHASES = {
    phase: (
        _REPO_ROOT / "configs" / "experiments" / f"bfs_phase_freeze_{phase}.json",
        _REPO_ROOT / "configs" / "experiments" / f"bfs_phase_authorization_{phase}.json",
    )
    for phase in ("v3", "v4", "v6")
}
_STAGES = ("preflight", "diagnose", "probe", "references", "base", "train", "evaluate", "adjudicate")


def reference_command(
    *,
    output_root: Path,
    workers: int,
    dry_run: bool,
    phase: str = "v3",
) -> tuple[str, ...]:
    command = (
        sys.executable,
        "scripts/run_bfs_references.py",
        "--phase",
        phase,
        "--output-root",
        str(output_root / f"issue54-{phase}-references"),
        "--attempt-id",
        f"issue-54-{phase}-references",
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
    phase: str = "v3",
) -> tuple[SeedLaunch, ...]:
    reference_manifest = output_root / f"issue54-{phase}-references" / "manifests" / "bfs-references.json"
    launches = []
    for index, seed in enumerate(seeds):
        device = devices[index % len(devices)]
        attempt = _next_training_attempt(output_root, seed, phase=phase)
        if attempt is None:
            continue
        training_root, attempt_id = attempt
        command = (
            sys.executable,
            "scripts/run_bfs_sft.py",
            "--phase",
            phase,
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
    phase: str = "v3",
) -> tuple[tuple[str, ...], ...]:
    launches = training_launches(
        seeds=seeds,
        devices=devices,
        output_root=output_root,
        dataset_root=dataset_root,
        phase=phase,
    )
    return tuple((*launch.command, "--dry-run") if dry_run else launch.command for launch in launches)


def checkpoint_launches(
    *,
    seeds: Sequence[int],
    devices: Sequence[str],
    output_root: Path,
    evaluation_phase: str = "v3",
    resume: bool = False,
) -> tuple[SeedLaunch, ...]:
    launches = []
    launch_index = 0
    training_phase = "v3" if evaluation_phase == "v4" else evaluation_phase
    for seed in seeds:
        training_root = _successful_training_root(output_root, seed, phase=training_phase)
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
            evaluation_root = output_root / f"issue54-{evaluation_phase}-process-seed-{seed}-{checkpoint_name}"
            attempt_id = f"issue-54-{evaluation_phase}-process-seed-{seed}-{checkpoint_name}"
            command = [
                sys.executable,
                "scripts/run_bfs_model_shard.py",
            ]
            if evaluation_phase != "v3":
                command.extend(("--phase", evaluation_phase))
            command.extend(
                (
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
            )
            launches.append(
                SeedLaunch(
                    seed=seed,
                    device=device,
                    attempt_id=attempt_id,
                    output_root=evaluation_root,
                    console_log=evaluation_root.parent / f"{evaluation_root.name}.console.log",
                    command=(*command, "--resume") if resume else tuple(command),
                )
            )
    return tuple(launches)


def _next_training_attempt(output_root: Path, seed: int, *, phase: str = "v3") -> tuple[Path, str] | None:
    roots = _training_attempt_roots(output_root, seed, phase=phase)
    if any(_is_successful_training(root) for root in roots):
        return None
    next_attempt = len(roots) + 1
    output_name = f"issue54-{phase}-process-sft-seed-{seed}"
    attempt_id = f"issue-54-{phase}-process-sft-seed-{seed}"
    if next_attempt > 1:
        suffix = f"-attempt-{next_attempt:03d}"
        output_name += suffix
        attempt_id += suffix
    return output_root / output_name, attempt_id


def _successful_training_root(output_root: Path, seed: int, *, phase: str = "v3") -> Path:
    successful = [
        root
        for root in _training_attempt_roots(output_root, seed, phase=phase)
        if _is_successful_training(root)
    ]
    if not successful:
        raise ValueError(f"seed {seed} has no successful process-SFT training attempt")
    return successful[-1]


def _training_attempt_roots(output_root: Path, seed: int, *, phase: str = "v3") -> list[Path]:
    first = output_root / f"issue54-{phase}-process-sft-seed-{seed}"
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
    phase: str = "v3",
) -> tuple[str, ...]:
    command = [
        sys.executable,
        "scripts/adjudicate_bfs_sanity_v3.py",
    ]
    if phase != "v3":
        command.extend(("--phase", phase))
    command.extend(
        [
            "--reference-manifest",
            str(output_root / f"issue54-{phase}-references" / "manifests" / "bfs-references.json"),
            "--output-root",
            str(output_root / f"issue54-{phase}-sanity-adjudication"),
            "--attempt-id",
            f"issue-54-{phase}-sanity-adjudication",
        ]
    )
    for seed in seeds:
        command.extend(
            (
                "--base-manifest",
                str(output_root / f"issue54-{phase}-base-seed-{seed}" / "manifest.json"),
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


def _v4_preflight(phase_gate: BFSPhaseGate) -> dict[str, object]:
    freeze = phase_gate.freeze
    materialization = _json_object(_REPO_ROOT / "data" / "bfs_pilot_v3" / "materialization-report.json")
    diagnostic = _json_object(
        _OUTPUT_ROOT / "issue54-v3-diagnostics" / "diagnostic-report.json"
    )
    if (
        materialization.get("trace_count") != 90
        or materialization.get("trusted_trace_replay_count") != 90
        or materialization.get("corpus_regeneration_byte_identical") is not True
        or materialization.get("ms_swift_projection_regeneration_byte_identical") is not True
    ):
        raise ValueError("v4 inherited corpus materialization is not replay-verified")
    corpus_manifest = _json_object(
        _REPO_ROOT / "data" / "bfs_pilot_v3" / "process-release" / "manifests" / "bfs-text-corpus.json"
    )
    rolling_context = corpus_manifest.get("rolling_context")
    if (
        not isinstance(rolling_context, dict)
        or rolling_context.get("accepted_delta_limit") != freeze["budgets"]["accepted_delta_limit"]
        or rolling_context.get("max_model_input_bytes") != freeze["budgets"]["max_model_input_bytes"]
    ):
        raise ValueError("v4 input limits differ from the inherited process-SFT corpus")
    findings = diagnostic.get("findings")
    training_contract = diagnostic.get("training_contract")
    if not isinstance(findings, dict) or not isinstance(training_contract, dict):
        raise ValueError("v4 diagnostic report is malformed")
    split_reports = training_contract.get("splits")
    if (
        findings.get("adapter_checkpoint_changes_model_output") is not True
        or findings.get("teacher_targets_derive_from_replayed_traces") is not True
        or training_contract.get("total_parse_failures") != 0
        or not isinstance(split_reports, dict)
        or any(
            not isinstance(report, dict) or report.get("over_successor_budget") != 0
            for report in split_reports.values()
        )
    ):
        raise ValueError("v4 diagnostic evidence does not authorize inherited checkpoint evaluation")
    checkpoints = []
    for seed in freeze["seeds"]:
        training_root = _successful_training_root(_OUTPUT_ROOT, int(seed))
        report = _json_object(training_root / "training-report.json")
        paths = report.get("checkpoint_paths")
        if not isinstance(paths, list):
            raise ValueError(f"seed {seed} training report has no checkpoint paths")
        steps = sorted(int(Path(str(path)).name.removeprefix("checkpoint-")) for path in paths)
        if steps != freeze["training"]["inherited_process_sft"]["checkpoint_steps"]:
            raise ValueError(f"seed {seed} inherited checkpoint steps differ from the v4 freeze")
        checkpoints.extend(paths)
    return {
        "checkpoint_count": len(checkpoints),
        "accepted_delta_limit": freeze["budgets"]["accepted_delta_limit"],
        "learning_commands": 0,
        "max_model_input_bytes": freeze["budgets"]["max_model_input_bytes"],
        "max_output_tokens_per_operation": freeze["budgets"]["max_output_tokens_per_operation"],
        "phase_id": phase_gate.phase_id,
        "status": "ready",
        "teacher_target_count": freeze["repair"]["teacher_target_count"],
    }


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=_STAGES)
    parser.add_argument("--phase", choices=tuple(_PHASES), default="v4")
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

    phase_gate = load_bfs_phase_gate(*_PHASES[args.phase])
    if args.stage == "preflight":
        if args.phase != "v4":
            raise ValueError("preflight is defined only for the v4 contract repair")
        print(json.dumps(_v4_preflight(phase_gate), sort_keys=True))
        return 0
    seeds = tuple(phase_gate.freeze["seeds"])
    if args.stage == "references":
        return _run_command(
            reference_command(
                output_root=_OUTPUT_ROOT,
                workers=args.reference_workers,
                dry_run=args.dry_run,
                phase=args.phase,
            ),
            label="references",
        )
    if args.stage == "base":
        command = [
            sys.executable,
            "scripts/run_bfs_base_seeds.py",
            "--phase",
            args.phase,
            "--output-prefix",
            str(_OUTPUT_ROOT / f"issue54-{args.phase}-base"),
            "--attempt-id-prefix",
            f"issue-54-{args.phase}-base",
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
        if args.phase == "v4":
            print(
                json.dumps(
                    {
                        "dry_run": args.dry_run,
                        "learning_commands": 0,
                        "source_phase_id": "issue-111-bfs-expansion-qualified-pilot-v3",
                        "status": "inherited_process_sft_checkpoints",
                    },
                    sort_keys=True,
                )
            )
            return 0
        launches = training_launches(
            seeds=seeds,
            devices=devices,
            output_root=_OUTPUT_ROOT,
            dataset_root=_DATASET_ROOTS[args.phase],
            phase=args.phase,
        )
        if args.dry_run:
            return _run_sequential([(*launch.command, "--dry-run") for launch in launches], label="train")
        return run_seed_launches(launches, processes_per_gpu=args.training_processes_per_gpu)

    launches = checkpoint_launches(
        seeds=seeds,
        devices=devices,
        output_root=_OUTPUT_ROOT,
        evaluation_phase=args.phase,
        resume=args.resume,
    )
    if args.stage == "evaluate":
        if args.dry_run:
            return _run_sequential(
                [(*launch.command, "--dry-run") for launch in launches],
                label="evaluate",
            )
        return run_seed_launches(launches, processes_per_gpu=args.inference_processes_per_gpu)
    command = adjudication_command(
        seeds=seeds,
        checkpoint_runs=launches,
        output_root=_OUTPUT_ROOT,
        dry_run=args.dry_run,
        phase=args.phase,
    )
    if args.dry_run:
        manifest_paths = [
            Path(command[index + 1])
            for index, argument in enumerate(command[:-1])
            if argument in {"--reference-manifest", "--base-manifest", "--process-manifest"}
        ]
        missing = [str(path) for path in manifest_paths if not path.is_file()]
        if missing:
            print(
                json.dumps(
                    {
                        "command": command,
                        "missing_upstream_manifests": missing,
                        "stage": "adjudicate",
                        "status": "waiting_for_upstream_products",
                    },
                    sort_keys=True,
                )
            )
            return 0
    return _run_command(command, label="adjudicate")


if __name__ == "__main__":
    raise SystemExit(main())
