#!/usr/bin/env python3
"""Prepare the fixed #91 final candidate pool without model calls."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.matched_tasks import DEFAULT_STUDY, Progress, prepare_candidates  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be positive")
    with Progress() as progress:
        try:
            report = prepare_candidates(ROOT, read_json(args.study), args.workers, progress, args.dry_run)
        except (ValueError, OSError) as error:
            progress("candidates:stopped", outcome="INVALID", reason=str(error))
            return 2
    return 0 if report is None or report["outcome"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
