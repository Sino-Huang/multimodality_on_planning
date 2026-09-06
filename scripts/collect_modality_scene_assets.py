"""Collect small replay-bound scene assets; this is not a matched training-corpus release."""

# Standalone project imports.
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

from examples.planning_benchmark_slice.modality_phase import inspect_modality_sources, load_modality_phase
from examples.planning_benchmark_slice.scene_assets import (
    build_scene_catalog,
    catalog_paths,
    collect_task_scenes,
    load_scene_task,
    read_json,
)
from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    StopOutcome,
    evaluate_execution_permission,
)


def work(arguments):
    row, profile, endpoint, output, timeout, preflight = arguments
    started = time.monotonic()

    def progress(event):
        print(
            json.dumps(
                {
                    **event,
                    "task_id": row["task_id"],
                    "endpoint": endpoint,
                    "task_elapsed_seconds": round(time.monotonic() - started, 2),
                }
            ),
            flush=True,
        )

    try:
        return collect_task_scenes(
            root=ROOT,
            row=row,
            profile=Path(profile),
            endpoint=endpoint,
            output=Path(output),
            timeout=timeout,
            preflight=preflight,
            progress=progress,
        )
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        return {
            "task_id": row["task_id"],
            "outcome": "VALID_STOP" if isinstance(error, RuntimeError) else "INVALID",
            "reason": str(error),
            "scene_frames": 0,
            "complete_state_coverage": False,
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/experiments/issue72/scenes128.json")
    mode = parser.add_mutually_exclusive_group(required=True)
    for name in ("dry-run", "smoke", "preflight", "collect"):
        mode.add_argument(f"--{name}", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--full-replay", action="store_true", help="with --dry-run, replay all selected task groups")
    args = parser.parse_args(argv)
    if args.full_replay and not args.dry_run:
        parser.error("--full-replay requires --dry-run")
    started = time.monotonic()

    def log(stage, **values):
        print(
            json.dumps({"stage": stage, "elapsed_seconds": round(time.monotonic() - started, 2), **values}), flush=True
        )

    try:
        config = read_json(args.config)
        stage = "collect" if args.collect else "smoke" if args.smoke else "preflight"
        if config["stored_scene_size"] != [128, 128]:
            raise ValueError("this successor stores 128 x 128 scenes")
        attempt = config["attempts"][stage]
        binding = ReceiptBinding(config["contract_id"], attempt["attempt_id"], ROOT / attempt["output_root"])
        gate = GateReceipt(binding, StopOutcome(attempt["gate_outcome"]), attempt.get("ancestor_receipt_id"))
        authorization = AuthorizationReceipt(binding, attempt["authorization_gate_id"])
        permission = evaluate_execution_permission(
            binding=binding,
            gate_receipt=gate,
            authorization_receipt=authorization,
            ancestor_receipt_id=gate.ancestor_receipt_id,
        )
        if not permission.start_permitted:
            log("gated_not_run", **permission.to_dict())
            return 1
        phase = load_modality_phase()
        if (
            phase.authorization["authorization_id"] != config["source_phase_authorization_id"]
            or phase.authorization["outcome"] != "PASS"
        ):
            raise ValueError("source phase authorization mismatch")
        inspect_modality_sources(phase)
        panel = read_json(ROOT / phase.components["corpus"]["panel_manifest"])["selected"]
        endpoints = config["endpoints"]
        if not 1 <= args.workers <= len(endpoints):
            raise ValueError("workers must fit the configured isolated backend endpoints")
        output = Path(binding.output_root)
        log(
            "start",
            mode=stage,
            dry_run=args.dry_run,
            task_groups=len(panel),
            workers=args.workers,
            endpoints=endpoints[: args.workers],
            stored_scene_size=[128, 128],
        )
        if (args.dry_run and not args.full_replay) or args.smoke:
            sample = []
            for family in ("bfs", "best_first_width", "best_first_add_w3"):
                sample.append(next(row for row in panel if family in row["trace_paths"]))
            panel = sample
        if args.dry_run:
            total_states = 0
            total_decisions = 0
            for index, row in enumerate(panel):
                domain, problem, traces = load_scene_task(ROOT, row)
                catalog = build_scene_catalog(domain, problem, traces)
                paths = catalog_paths(catalog)
                total_states += len(catalog["states"])
                total_decisions += len(catalog["decisions"])
                log(
                    "dry_replay",
                    completed=index + 1,
                    total=len(panel),
                    task_id=row["task_id"],
                    states=len(catalog["states"]),
                    decisions=len(catalog["decisions"]),
                    supplied_paths=len(paths),
                )
            log(
                "dry_run_complete",
                outcome="PASS",
                scientific_completion=False,
                writes=0,
                http_requests=0,
                replayed_task_groups=len(panel),
                catalog_states=total_states,
                decisions=total_decisions,
                note=(
                    "Full source inventory inspected; replay scope reported above. "
                    "No profile/goal-image qualification claimed."
                ),
            )
            return 0
        if output.exists():
            raise ValueError("attempt output exists; preserve it and supply a successor attempt config")
        if args.collect:
            expected_preflight = config["attempts"]["preflight"]
            predecessor = read_json(ROOT / expected_preflight["output_root"] / "report.json")
            if (
                predecessor.get("contract_id") != config["contract_id"]
                or predecessor.get("binding")
                != ReceiptBinding(
                    config["contract_id"], expected_preflight["attempt_id"], ROOT / expected_preflight["output_root"]
                ).to_dict()
                or predecessor.get("stage") != "preflight"
                or predecessor.get("outcome") != "PASS"
                or predecessor.get("stored_scene_size") != [128, 128]
                or any(row["outcome"] != "PASS" for row in predecessor["results"])
                or not predecessor.get("complete_selected_coverage")
                or sorted(row["task_id"] for row in predecessor["results"]) != sorted(row["task_id"] for row in panel)
            ):
                raise ValueError("collection requires a complete matching scene preflight PASS")
        output.mkdir(parents=True)
        results = []
        stopped = False
        iterator = iter(enumerate(panel))
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            pending = {}

            def submit(slot):
                item = next(iterator, None)
                if item is None:
                    return
                index, row = item
                arguments = (
                    row,
                    str(ROOT / phase.components["render"]["domain_profiles"][row["domain"]]),
                    endpoints[slot],
                    str(output / f"task-{index:06d}"),
                    config["timeout_seconds"],
                    not args.collect,
                )
                pending[pool.submit(work, arguments)] = slot

            for slot in range(args.workers):
                submit(slot)
            while pending:
                ready, _ = wait(pending, timeout=10, return_when=FIRST_COMPLETED)
                if not ready:
                    log("heartbeat", completed=len(results), total=len(panel), active=len(pending))
                for future in ready:
                    slot = pending.pop(future)
                    result = future.result()
                    results.append(result)
                    with (output / "task-results.jsonl").open("a") as journal:
                        journal.write(json.dumps(result) + "\n")
                    stopped = stopped or result["outcome"] != "PASS"
                    elapsed = time.monotonic() - started
                    log(
                        "task_complete",
                        completed=len(results),
                        total=len(panel),
                        **result,
                        eta_seconds=round(elapsed / len(results) * (len(panel) - len(results)), 2),
                    )
                    if not stopped:
                        submit(slot)
        complete = len(results) == len(panel) and not stopped
        outcome = "PASS" if complete else "INVALID" if any(r["outcome"] == "INVALID" for r in results) else "VALID_STOP"
        report = {
            "schema_version": "scene_assets_run_v1",
            "contract_id": config["contract_id"],
            "binding": binding.to_dict(),
            "stage": stage,
            "outcome": outcome,
            "scientific_completion": False,
            "scene_asset_completion": complete and args.collect,
            "complete_selected_coverage": complete and not args.smoke,
            "partial_goal_images_complete": False,
            "model_input_ready": False,
            "permission": permission.to_dict(),
            "results": sorted(results, key=lambda r: r["task_id"]),
            "endpoint_mapping": endpoints[: args.workers],
            "stored_scene_size": [128, 128],
            "elapsed_seconds": time.monotonic() - started,
        }
        if outcome == "VALID_STOP":
            report["gated_not_run_receipt"] = {
                "outcome": "VALID_STOP",
                "start_permitted": False,
                "scientific_completion": False,
                "reason": "scene_preflight_or_collection_stopped",
                "binding": binding.to_dict(),
            }
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        log(
            "complete",
            outcome=outcome,
            completed=len(results),
            total=len(panel),
            scientific_completion=False,
            scene_asset_completion=report["scene_asset_completion"],
            output=str(output / "report.json"),
        )
        return 0 if outcome == "PASS" else 2 if outcome == "VALID_STOP" else 1
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        log("stopped", outcome="INVALID", scientific_completion=False, reason=str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
