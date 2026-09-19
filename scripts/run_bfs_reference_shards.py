"""Launch independently governed BFS reference shards with bounded concurrency."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class ShardLaunch:
    shard_index: int
    attempt_id: str
    output_root: Path
    command: tuple[str, ...]


def available_cpus() -> int:
    affinity = getattr(os, "sched_getaffinity", None)
    if affinity is not None:
        return max(1, len(affinity(0)))
    return max(1, os.cpu_count() or 1)


def build_shard_launches(
    *,
    output_root: Path,
    attempt_id_prefix: str,
    shard_count: int,
    workers_per_shard: int,
) -> tuple[ShardLaunch, ...]:
    if shard_count <= 0:
        raise ValueError("shard_count must be positive")
    if workers_per_shard <= 0:
        raise ValueError("workers_per_shard must be positive")
    if not attempt_id_prefix:
        raise ValueError("attempt_id_prefix must not be empty")

    root = output_root.expanduser().resolve()
    width = max(3, len(str(shard_count)))
    launches = []
    for shard_index in range(shard_count):
        shard_root = root / f"shard-{shard_index:0{width}d}"
        attempt_id = f"{attempt_id_prefix}-shard-{shard_index:0{width}d}-of-{shard_count:0{width}d}"
        command = (
            sys.executable,
            "scripts/run_bfs_references.py",
            "--output-root",
            str(shard_root),
            "--attempt-id",
            attempt_id,
            "--shard-index",
            str(shard_index),
            "--shard-count",
            str(shard_count),
            "--workers",
            str(workers_per_shard),
        )
        launches.append(ShardLaunch(shard_index, attempt_id, shard_root, command))
    return tuple(launches)


def run_shards(launches: Sequence[ShardLaunch], *, max_concurrent_shards: int) -> int:
    if max_concurrent_shards <= 0:
        raise ValueError("max_concurrent_shards must be positive")

    def run(launch: ShardLaunch) -> tuple[ShardLaunch, subprocess.CompletedProcess[str]]:
        completed = subprocess.run(
            launch.command,
            cwd=_REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        return launch, completed

    failed = False
    with ThreadPoolExecutor(max_workers=min(max_concurrent_shards, len(launches))) as executor:
        futures = [executor.submit(run, launch) for launch in launches]
        for future in as_completed(futures):
            launch, completed = future.result()
            if completed.stdout:
                print(completed.stdout, end="")
            if completed.stderr:
                print(completed.stderr, end="", file=sys.stderr)
            if completed.returncode != 0:
                failed = True
                print(f"shard {launch.shard_index} failed with exit code {completed.returncode}", file=sys.stderr)
    return 1 if failed else 0


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--attempt-id-prefix", required=True)
    parser.add_argument("--shard-count", type=int, default=available_cpus())
    parser.add_argument("--workers-per-shard", type=int, default=1)
    parser.add_argument("--max-concurrent-shards", type=int, default=available_cpus())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)
    launches = build_shard_launches(
        output_root=args.output_root,
        attempt_id_prefix=args.attempt_id_prefix,
        shard_count=args.shard_count,
        workers_per_shard=args.workers_per_shard,
    )
    if args.dry_run:
        print(
            json.dumps(
                [
                    {"attempt_id": item.attempt_id, "command": item.command, "output_root": str(item.output_root)}
                    for item in launches
                ],
                sort_keys=True,
            )
        )
        return 0
    return run_shards(launches, max_concurrent_shards=args.max_concurrent_shards)


if __name__ == "__main__":
    raise SystemExit(main())
