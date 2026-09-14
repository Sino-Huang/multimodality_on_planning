#!/usr/bin/env python
"""Prepare expanded-panel exclusions before any new-task selection."""

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_panel import inventory
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("stage", choices=("inventory", "audit-inventory"))
    args = parser.parse_args()
    path = ROOT / "outputs/expanded-study/v1/panel/historical-inventory.json"
    if args.stage == "inventory":

        def progress(stage, **counts):
            print({"stage": stage, **counts}, flush=True)

        if path.exists():
            raise ValueError("historical inventory already exists; inspect it rather than overwrite")
        report = inventory(ROOT, progress)
        write(path, report)
        if os.environ.get("EXPANDED_PROGRESS_PATH"):
            write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": 1})
        print({k: v for k, v in report.items() if k not in ("source_evidence", "task_semantics")}, flush=True)
    else:
        terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
        if terminal["status"] != "succeeded":
            raise RuntimeError(f"inventory failed; inspect {terminal['directory']}/worker.log")
        report = read(path)
        assert len(report["domains"]) == report["source_domain_count"]
        assert len(report["task_semantics"]) == report["distinct_semantics"]
        assert all(
            (ROOT / source.get("task_path", source.get("problem_path"))).is_file()
            for source in report["source_evidence"]
        )
        compact = {k: v for k, v in report.items() if k not in ("source_evidence", "task_semantics")}
        compact["inventory_path"] = str(path.relative_to(ROOT))
        write(ROOT / "docs/experiments/expanded-study/panel-inventory.json", compact)
        print("PASS: historical exclusion inventory; new panel selection/qualification still pending")


if __name__ == "__main__":
    main()
