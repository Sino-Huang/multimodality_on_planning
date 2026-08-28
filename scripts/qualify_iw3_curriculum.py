from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from examples.planning_benchmark_slice.iw_qualification import qualify_bfws_curriculum, qualify_curriculum


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qualify exact capped IW(1..3) over curriculum tasks.")
    parser.add_argument("--algorithm", choices=("iw3", "bfws"), default="iw3")
    parser.add_argument("--manifest", type=Path, default=Path("data/curriculum_pddl/accepted_manifest.jsonl"))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--splits", nargs="+", default=("train", "test"))
    parser.add_argument("--max-expansions", type=int, default=500)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--retry-status", nargs="*", default=())
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args(argv)
    qualify = qualify_curriculum if args.algorithm == "iw3" else qualify_bfws_curriculum
    report = qualify(
        args.manifest,
        args.output_root,
        splits=args.splits,
        max_expansions=args.max_expansions,
        timeout_seconds=args.timeout_seconds,
        retry_statuses=args.retry_status,
        shard_index=args.shard_index,
        shard_count=args.shard_count,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
