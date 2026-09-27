#!/usr/bin/env python
"""#147 data-cost runner (study data-cost-v1).

  units [--stages]         frozen priority order of the 115 claimable slots (dry run; no side effects)
  status                   units done/running/pending/blocked, GPU-h charged, attempts, backend, inputs
  launch [--dry-run]       write the schedule + two worker job JSONs (GPU 0 / GPU 1) and admit them via
                           scripts/run_expanded_study.py launch
  resume [--reason R]      after a reboot: start the Planimation backend if down, reconcile dead attempts,
                           relaunch missing workers (idempotent while workers are alive)
  worker --gpu N           scheduler job body: claim -> train -> eval loop (never run by hand on a busy GPU)
  controls [--workers K]   CPU: exact_reference (seed 17) + random_valid (5 seeds) per algorithm, text-state
  finalize [--workers K]   CPU: independently replay every episode; per-episode metrics table
  hook                     scheduler completion hook (CPU)

Run every command inside the project environment: `source ~/cd_vlaplan && python scripts/run_data_cost.py ...`.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice import data_cost_runner as runner

ROOT = runner.ROOT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "action", choices=("units", "status", "launch", "resume", "worker", "controls", "finalize", "hook")
    )
    parser.add_argument("--gpu", type=int, choices=(0, 1))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--reason")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stages", action="store_true", help="units: list the 224 stage units instead of slots")
    parser.add_argument("--max-slots", type=int)
    args = parser.parse_args(argv)
    if args.action == "units":
        if args.stages:
            for index, unit in enumerate(runner.units(), 1):
                print(f"{index:3d} {unit}")
        else:
            for index, slot in enumerate(runner.slots(), 1):
                print(f"{index:3d} {' -> '.join(slot['stages'])}")
        return 0
    if args.action == "worker":
        if args.gpu is None:
            parser.error("worker requires --gpu")
        result = runner.worker(ROOT, args.gpu, max_slots=args.max_slots)
    elif args.action == "status":
        result = runner.status(ROOT)
    elif args.action == "launch":
        result = runner.launch_workers(ROOT, resume_reason=args.reason, dry_run=args.dry_run)
    elif args.action == "resume":
        result = runner.resume(ROOT, reason=args.reason)
    elif args.action == "controls":
        result = runner.run_controls(ROOT, workers=args.workers)
    elif args.action == "finalize":
        result = runner.finalize(ROOT, workers=args.workers)
    else:
        result = runner.hook()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
