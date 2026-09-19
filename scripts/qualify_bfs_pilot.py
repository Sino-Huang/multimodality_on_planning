"""Run the issue-111 expansion-qualified BFS pilot gate without rendering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from examples.planning_benchmark_slice.bfs_pilot import (
    run_observable_v5_qualification,
    run_observable_v6_qualification,
    run_qualification,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--contract", choices=("v3", "v5", "v6"), default="v3")
    args = parser.parse_args()
    report = (
        run_observable_v6_qualification(args.output_root)
        if args.contract == "v6"
        else run_observable_v5_qualification(args.output_root)
        if args.contract == "v5"
        else run_qualification(args.output_root)
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if report["outcome"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
