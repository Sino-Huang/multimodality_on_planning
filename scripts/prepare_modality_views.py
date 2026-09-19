"""Prepare readable views from the completed scene catalogs; never regenerate scenes."""

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

from examples.planning_benchmark_slice.modality_phase import load_modality_phase
from examples.planning_benchmark_slice.modality_view_panel import load_view_panel
from examples.planning_benchmark_slice.modality_view_preparation import (
    CONTRACT,
    EXPECTED,
    check_task,
    prepare_task,
    recommend_context,
    require_approval,
    reuse_task,
    validate_scene_selection,
    write_json,
)
from examples.planning_benchmark_slice.scene_assets import read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("dry-run", "qualify", "materialize", "check"):
        modes.add_argument(f"--{mode}", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit-tasks", type=int, help="bounded development run; cannot authorize materialization")
    parser.add_argument("--task-id", action="append", help="bounded task selection; cannot claim complete coverage")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--panel", type=Path, help="measured whole-task 32K successor panel; omit for retained v1")
    parser.add_argument("--qualification", type=Path, default=ROOT / "outputs/modality_views/qualify-001/report.json")
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--resume", action="store_true", help="reuse completed materialization task manifests")
    args = parser.parse_args(argv)
    mode = next(name for name in ("dry-run", "qualify", "materialize", "check") if getattr(args, name.replace("-", "_")))
    started = time.monotonic()

    def log(stage, completed, total, **fields):
        elapsed = time.monotonic() - started
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
        if args.workers < 1 or (args.limit_tasks is not None and args.limit_tasks < 1):
            raise ValueError("workers and task limit must be positive")
        if mode in ("materialize", "check") and (args.limit_tasks or args.task_id):
            raise ValueError("materialization/check require the whole selected panel")
        if args.resume and mode != "materialize":
            raise ValueError("resume is only for interrupted materialization")
        output = (
            args.output or ROOT / f"outputs/modality_views/{'materialize' if mode == 'check' else mode}-001"
        ).resolve()
        if mode != "dry-run" and not output.is_relative_to(ROOT):
            raise ValueError("view output must be inside the repository for relative bindings")
        phase = load_modality_phase()
        panel = read_json(ROOT / phase.components["corpus"]["panel_manifest"])["selected"]
        if len(panel) != EXPECTED["tasks"]:
            raise ValueError("selected task count differs from successor contract")
        scene_report = read_json(ROOT / CONTRACT["scene_report"])
        scenes = validate_scene_selection(ROOT, panel, scene_report)
        contract = CONTRACT
        if args.panel:
            panel, contract = load_view_panel(ROOT, args.panel)
        expected = contract["expected"]
        full_panel = panel
        if args.task_id:
            panel = [r for r in panel if r["task_id"] in args.task_id]
            if {r["task_id"] for r in panel} != set(args.task_id):
                raise ValueError("requested task is absent from the frozen selection")
        if args.limit_tasks:
            panel = panel[: args.limit_tasks]
        approval = qualification = None
        if mode in ("materialize", "check"):
            if not args.approval:
                raise ValueError("--approval is required after human review of qualification previews/context")
            qualification = read_json(args.qualification)
            approval = read_json(args.approval)
            require_approval(approval, qualification, output, contract)
        binding = {"contract": contract, "attempt_id": output.name, "output": str(output), "approval": approval}
        previous = {}
        if mode == "check":
            report = read_json(output / "report.json")
            if (
                report.get("outcome") != "PASS"
                or not report.get("model_input_ready")
                or report.get("binding") != binding
            ):
                raise ValueError("no complete matching authorized materialization report")
            previous = {r["task_id"]: r for r in report["results"]}
            if set(previous) != {r["task_id"] for r in full_panel}:
                raise ValueError("materialization task coverage is incomplete")
        elif mode != "dry-run":
            if output.exists():
                if not args.resume or read_json(output / "binding.json") != binding:
                    raise ValueError("output exists: use a fresh attempt or matching --resume materialization")
                if (output / "report.json").exists():
                    raise ValueError("completed attempt report exists; use --check")
            else:
                output.mkdir(parents=True)
                write_json(output / "binding.json", binding)
        results = []
        jobs = []
        for index, row in enumerate(panel):
            task_output = output / f"task-{index:06d}"
            jobs.append((row, task_output))
        log(mode, len(results), len(panel), workers=args.workers)
        failure = None
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            pending = {}
            iterator = iter(jobs)
            while True:
                while failure is None and len(pending) < args.workers:
                    job = next(iterator, None)
                    if job is None:
                        break
                    row, task_output = job
                    if args.resume and (task_output / "result.json").is_file():
                        future = pool.submit(reuse_task, ROOT, read_json(task_output / "result.json"), row, contract)
                    else:
                        future = (
                            pool.submit(check_task, ROOT, previous[row["task_id"]], row, contract)
                            if mode == "check"
                            else pool.submit(
                                prepare_task, ROOT, row, scenes[row["task_id"]], mode, task_output, contract
                            )
                        )
                    pending[future] = (row, task_output)
                if not pending:
                    break
                done, _ = wait(pending, timeout=10, return_when=FIRST_COMPLETED)
                if not done:
                    log(
                        mode + ":heartbeat",
                        len(results),
                        len(panel),
                        active_tasks=[r["task_id"] for r, _ in pending.values()],
                    )
                for future in done:
                    row, task_output = pending.pop(future)
                    try:
                        result = future.result()
                    except (ValueError, KeyError, OSError) as error:
                        failure = error
                        log(mode + ":task_stopped", len(results), len(panel), task_id=row["task_id"], reason=str(error))
                        continue
                    results.append(result)
                    if mode not in ("dry-run", "check") and not (
                        args.resume and (task_output / "result.json").is_file()
                    ):
                        write_json(task_output / "result.json", result)
                    log(
                        mode,
                        len(results),
                        len(panel),
                        task_id=row["task_id"],
                        states=result["states"],
                        decisions=result["decisions"],
                    )
        if failure is not None:
            raise failure
        results.sort(key=lambda r: r["task_id"])
        counts = {
            "tasks": len(results),
            "states": sum(r["states"] for r in results),
            "decisions": sum(r["decisions"] for r in results),
        }
        complete = counts == expected and {r["task_id"] for r in results} == {r["task_id"] for r in full_panel}
        report = {
            "contract": contract,
            "attempt_id": output.name,
            "binding": binding,
            "stage": mode,
            "counts": counts,
            "complete_selected_coverage": complete,
            "results": results,
            "outcome": "PASS" if complete else "INCOMPLETE",
            "model_input_ready": mode in ("materialize", "check") and complete,
            "partial_goal_images_complete": mode in ("materialize", "check") and complete,
            "scientific_completion": False,
            "gpu_throughput_qualified": False,
            "elapsed_seconds": time.monotonic() - started,
        }
        if mode == "qualify":
            maximum = max(r["maximum_input_tokens"] for r in results)
            recommended = recommend_context(maximum)
            preview_index = output / "previews.json"
            write_json(
                preview_index,
                [{"task_id": r["task_id"], "domain": r["domain"], "pages": r["previews"]} for r in results],
            )
            report.update(
                maximum_input_tokens=maximum,
                recommended_context=recommended,
                processor_qualified=complete and all(r["processor_cross_checked"] for r in results),
                preview_index=str(preview_index),
                readability_approved=False,
                context_comparison=[
                    {
                        "total_tokens": size,
                        "reserved_output": 384,
                        "fits": maximum + 384 <= size,
                        "relative_sequence_memory": size / 8192,
                        "dense_attention_work_ratio": (size / 8192) ** 2,
                    }
                    for size in CONTRACT["contexts"]
                ],
                memory_estimate_note=(
                    "Sequence activations/KV scale approximately linearly; dense attention work quadratically. "
                    "These are relative estimates, not GPU throughput or peak-memory qualification."
                ),
            )
            page_sizes = [n for r in results for n in r["preview_png_bytes"]]
            reusable_count = sum(r["context_pages"] + r["goal_pages"] for r in results)
            report["storage_estimate"] = {
                "mean_preview_png_bytes": sum(page_sizes) / len(page_sizes),
                "reusable_pages": reusable_count,
                "estimated_reusable_png_bytes": int(reusable_count * sum(page_sizes) / len(page_sizes)),
                "state_pngs_stored": 0,
                "scene_copies": 0,
                "metadata_bytes_measured_after_materialization": True,
            }
            if recommended is None:
                report.update(
                    outcome="VALID_STOP",
                    reason=(
                        "complete inputs exceed 32768 total tokens; "
                        "no task dropping, truncation or automatic context increase"
                    ),
                )
        if mode == "materialize":
            assert qualification is not None and approval is not None
            report["qualification_attempt"] = qualification["attempt_id"]
            report["qualification_report"] = str(args.qualification.resolve())
            report["approved_context"] = approval["approved_context"]
        if mode not in ("dry-run", "check"):
            write_json(output / "report.json", report)
        log(
            mode + ":complete",
            len(results),
            len(panel),
            **{
                k: v
                for k, v in report.items()
                if k in ("outcome", "counts", "recommended_context", "model_input_ready", "maximum_input_tokens")
            },
        )
        return 2 if report["outcome"] == "VALID_STOP" else 0
    except (ValueError, KeyError, OSError) as error:
        log(mode + ":stopped", 0, 0, outcome="INVALID", reason=str(error), model_input_ready=False)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
