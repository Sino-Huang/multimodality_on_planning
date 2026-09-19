#!/usr/bin/env python
"""Materialize and independently replay the frozen successor inputs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write
from examples.planning_benchmark_slice.expanded_successor_protocol import prepare_views, validate_protocol

PROTOCOL = ROOT / "configs/experiments/expanded-study/successor-protocol.json"


def progress(stage: str, **fields) -> None:
    payload = {"stage": stage, **fields}
    path = os.environ.get("EXPANDED_PROGRESS_PATH")
    if path:
        write(Path(path), payload)
    print(json.dumps(payload), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("stage", choices=("prepare", "audit"))
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    args = parser.parse_args()
    protocol = read(args.protocol)
    context = validate_protocol(ROOT, protocol)
    if args.stage == "prepare":
        report = prepare_views(ROOT, protocol, context, progress)
        print(json.dumps({"outcome": report["outcome"], "counts": report["counts"]}, indent=2))
        return
    terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
    if terminal["status"] != "succeeded":
        raise RuntimeError(f"successor input preparation failed: {terminal['directory']}/worker.log")
    report = prepare_views(ROOT, protocol, context, progress, check=True)
    print(
        "PASS: all 512 successor targets and three modality projections independently replayed; "
        f"maxima={report['max_tokens']}"
    )


if __name__ == "__main__":
    main()
