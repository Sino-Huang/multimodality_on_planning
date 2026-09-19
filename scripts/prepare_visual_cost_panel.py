"""Rank and select shared dev tasks from retained timings; no GPU/model calls."""

# ruff: noqa: E402
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.modality_view_preparation import write_json
from examples.planning_benchmark_slice.visual_experiment import VisualExperiment
from examples.planning_benchmark_slice.visual_panel import build_cost_panel
from scripts.run_visual_issue75 import heartbeat, log


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/experiments/issue75/experiment.json")
    parser.add_argument("--output", type=Path, default=ROOT / "configs/experiments/issue75/cost-panel-v1.json")
    parser.add_argument("--evaluation-hours", type=float, default=15)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.evaluation_hours <= 0:
        parser.error("--evaluation-hours must be positive")
    started = time.monotonic()
    panel = heartbeat(
        lambda: build_cost_panel(VisualExperiment(args.config), args.evaluation_hours * 3600, progress=log), "panel"
    )
    if not args.dry_run:
        write_json(args.output, panel)
    log(
        "panel:complete",
        completed=len(panel["tasks"]),
        total=len(panel["tasks"]),
        elapsed_seconds=round(time.monotonic() - started, 2),
        selected=len(panel["selected_task_ids"]),
        excluded=len(panel["excluded_task_ids"]),
        evaluation=panel["evaluation"],
        training=panel["training"],
        dry_run=args.dry_run,
        model_calls=0,
        output=None if args.dry_run else str(args.output),
    )


if __name__ == "__main__":
    main()
