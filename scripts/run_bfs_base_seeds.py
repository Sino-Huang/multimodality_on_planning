"""Run the five frozen v3 BFS base seeds across dedicated GPU queues."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v3.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v3.json"


@dataclass(frozen=True, slots=True)
class SeedLaunch:
    seed: int
    device: str
    attempt_id: str
    output_root: Path
    console_log: Path
    command: tuple[str, ...]


def build_seed_launches(
    *,
    seeds: Sequence[int],
    devices: Sequence[str],
    output_prefix: Path,
    attempt_id_prefix: str,
    resume: bool = False,
) -> tuple[SeedLaunch, ...]:
    if not seeds:
        raise ValueError("at least one frozen seed is required")
    if not devices or len(set(devices)) != len(devices) or any(not device for device in devices):
        raise ValueError("devices must be a non-empty unique list")
    if not attempt_id_prefix:
        raise ValueError("attempt ID prefix must not be empty")

    prefix = output_prefix.expanduser().resolve()
    launches = []
    for index, seed in enumerate(seeds):
        device = devices[index % len(devices)]
        output_root = prefix.parent / f"{prefix.name}-seed-{seed}"
        attempt_id = f"{attempt_id_prefix}-seed-{seed}"
        command = (
            sys.executable,
            "scripts/run_bfs_model_shard.py",
            "--arm",
            "base",
            "--output-root",
            str(output_root),
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
                output_root=output_root,
                console_log=output_root.parent / f"{output_root.name}.console.log",
                command=(*command, "--resume") if resume else command,
            )
        )
    return tuple(launches)


def run_seed_launches(launches: Sequence[SeedLaunch], *, processes_per_gpu: int = 1) -> int:
    if not launches:
        raise ValueError("at least one seed launch is required")
    if processes_per_gpu <= 0:
        raise ValueError("processes_per_gpu must be positive")
    by_device: dict[str, list[SeedLaunch]] = defaultdict(list)
    for launch in launches:
        by_device[launch.device].append(launch)
    queues: dict[tuple[str, int], list[SeedLaunch]] = defaultdict(list)
    for device, device_launches in by_device.items():
        for index, launch in enumerate(device_launches):
            queues[(device, index % processes_per_gpu)].append(launch)

    terminal_lock = threading.Lock()
    failed = False
    with ThreadPoolExecutor(max_workers=len(queues)) as executor:
        futures = [
            executor.submit(_run_device_queue, queued_launches, terminal_lock) for queued_launches in queues.values()
        ]
        for future in as_completed(futures):
            if any(returncode != 0 for _launch, returncode in future.result()):
                failed = True
    return 1 if failed else 0


def _run_device_queue(launches: Sequence[SeedLaunch], terminal_lock: threading.Lock) -> list[tuple[SeedLaunch, int]]:
    results = []
    for launch in launches:
        launch.console_log.parent.mkdir(parents=True, exist_ok=True)
        prefix = f"[attempt={launch.attempt_id} gpu={launch.device}]"
        with terminal_lock:
            print(f"{prefix} launching", flush=True)
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        process = subprocess.Popen(
            launch.command,
            cwd=_REPO_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        with launch.console_log.open("a", encoding="utf-8") as console:
            for line in process.stdout:
                console.write(line)
                console.flush()
                with terminal_lock:
                    print(f"{prefix} {line}", end="", flush=True)
        returncode = process.wait()
        with terminal_lock:
            print(f"{prefix} finished with exit code {returncode}", flush=True)
        results.append((launch, returncode))
    return results


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devices", nargs="+", default=("0", "1"))
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=Path("outputs/bfs_phase/issue54-v3-base"),
    )
    parser.add_argument("--attempt-id-prefix", default="issue-54-v3-base")
    parser.add_argument("--processes-per-gpu", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)

    phase_gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    phase_gate.require_run(stage="base_and_references", contract_id=phase_gate.phase_id)
    launches = build_seed_launches(
        seeds=tuple(phase_gate.freeze["seeds"]),
        devices=tuple(args.devices),
        output_prefix=args.output_prefix,
        attempt_id_prefix=args.attempt_id_prefix,
        resume=args.resume,
    )
    if args.dry_run:
        print(
            json.dumps(
                [
                    {
                        "attempt_id": launch.attempt_id,
                        "command": launch.command,
                        "console_log": str(launch.console_log),
                        "device": launch.device,
                        "output_root": str(launch.output_root),
                        "seed": launch.seed,
                    }
                    for launch in launches
                ],
                sort_keys=True,
            )
        )
        return 0
    return run_seed_launches(launches, processes_per_gpu=args.processes_per_gpu)


if __name__ == "__main__":
    raise SystemExit(main())
