#!/usr/bin/env python
"""#147 data-cost preparation: nested training sets, scene-only views, decision sufficiency.

    python scripts/data_cost_prepare.py sets         # training-sets.json + membership.json
    python scripts/data_cost_prepare.py views        # outputs/data-cost/v1/preparation/scene-views.json
    python scripts/data_cost_prepare.py sufficiency  # outputs/data-cost/v1/preparation/sufficiency.json

Every stage is resumable: rerunning the same command reuses cached per-task measurements and
already-rasterized scenes and continues where it stopped.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.data_cost_corpus import build_sets, check_sufficiency, prepare_views  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=("sets", "views", "sufficiency"))
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    stage = {"sets": build_sets, "views": prepare_views, "sufficiency": check_sufficiency}[args.stage]
    stage(ROOT, workers=args.workers)


if __name__ == "__main__":
    main()
