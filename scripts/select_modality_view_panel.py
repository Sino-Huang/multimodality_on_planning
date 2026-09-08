"""Measure all parent-panel inputs and retain matched whole tasks fitting 32K."""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.modality_view_panel import SOURCE_PANEL, select_view_panel
from examples.planning_benchmark_slice.modality_view_preparation import (
    CONTRACT,
    EXPECTED,
    prepare_task,
    validate_scene_selection,
    write_json,
)
from examples.planning_benchmark_slice.scene_assets import read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/modality_views/select-32k-001")
    parser.add_argument(
        "--panel-output", type=Path, default=ROOT / "configs/experiments/issue72/views-panel-32k-v2.json"
    )
    args = parser.parse_args(argv)
    start = time.monotonic()
    completed = 0
    total = EXPECTED["tasks"]

    def log(stage, **fields):
        elapsed = time.monotonic() - start
        print(
            json.dumps(
                {
                    "stage": stage,
                    "completed": completed,
                    "total": total,
                    "elapsed_seconds": round(elapsed, 2),
                    "eta_seconds": round(elapsed / completed * (total - completed), 2) if completed else None,
                    **fields,
                }
            ),
            flush=True,
        )

    try:
        output, panel_output = args.output.resolve(), args.panel_output.resolve()
        if args.workers < 1 or not output.is_relative_to(ROOT) or not panel_output.is_relative_to(ROOT):
            raise ValueError("positive workers and repository-relative outputs required")
        if output.exists() or panel_output.exists():
            raise ValueError("use fresh selection outputs; prior attempts are retained")
        parent = read_json(ROOT / SOURCE_PANEL)["selected"]
        scenes = validate_scene_selection(ROOT, parent, read_json(ROOT / CONTRACT["scene_report"]))
        output.mkdir(parents=True)
        results = []
        log("measure_inputs", workers=args.workers)
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            pending, iterator, failure = {}, iter(enumerate(parent)), None
            while True:
                while len(pending) < args.workers and failure is None:
                    job = next(iterator, None)
                    if job is None:
                        break
                    index, row = job
                    task_output = output / f"task-{index:06d}"
                    pending[pool.submit(prepare_task, ROOT, row, scenes[row["task_id"]], "measure", task_output)] = (
                        task_output
                    )
                if not pending:
                    break
                done, _ = wait(pending, timeout=10, return_when=FIRST_COMPLETED)
                if not done:
                    log("measure_inputs:heartbeat", active=len(pending))
                for future in done:
                    task_output = pending.pop(future)
                    try:
                        result = future.result()
                        results.append(result)
                        write_json(task_output / "result.json", result)
                        completed += 1
                        log(
                            "measure_inputs",
                            task_id=result["task_id"],
                            maximum_input_tokens=result["maximum_input_tokens"],
                        )
                    except (ValueError, KeyError, OSError) as error:
                        failure = error
                        log("measure_inputs:stopped", reason=str(error))
        if failure is not None:
            raise failure
        results.sort(key=lambda r: r["task_id"])
        measured_counts = {
            "tasks": len(results),
            "states": sum(r["states"] for r in results),
            "decisions": sum(r["decisions"] for r in results),
        }
        if measured_counts != EXPECTED:
            raise ValueError("partial parent coverage cannot produce a successor panel")
        report_path = output / "report.json"
        panel = select_view_panel(parent, results, str(report_path.relative_to(ROOT)))
        report = {
            "contract": CONTRACT,
            "stage": "token_selection",
            "outcome": "PASS",
            "complete_parent_coverage": True,
            "counts": measured_counts,
            "results": results,
            "selected_counts": panel["expected"],
            "excluded_counts": panel["exclusion_counts"],
            "model_input_ready": False,
            "scientific_completion": False,
            "elapsed_seconds": time.monotonic() - start,
        }
        write_json(report_path, report)
        write_json(panel_output, panel)
        log(
            "selection_complete", selected=panel["expected"], excluded=panel["exclusion_counts"], panel=str(panel_output)
        )
        return 0
    except (ValueError, KeyError, OSError) as error:
        log("selection_stopped", outcome="INVALID", reason=str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
