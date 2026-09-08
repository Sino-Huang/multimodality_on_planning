"""Release/check approved matched modality corpora with four CPU workers."""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.modality_corpus import (
    CorpusStop,
    audit_release,
    build_task,
    release_permission,
    source_release,
)
from examples.planning_benchmark_slice.modality_view_panel import load_view_panel
from examples.planning_benchmark_slice.modality_view_preparation import write_json
from examples.planning_benchmark_slice.scene_assets import read_json
from src.data_collect.governance import ReceiptBinding, RunReceipt, StopOutcome


def main(argv=None, *, issue=73):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("dry-run", "materialize", "check"):
        modes.add_argument(f"--{mode}", action="store_true")
    config = ROOT / f"configs/experiments/issue{issue}"
    parser.add_argument("--contract", type=Path, default=config / "contract.json")
    parser.add_argument("--authorization", type=Path, default=config / "authorization.json")
    parser.add_argument("--gate", type=Path, default=config / "gate.json")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true", help="reuse completed shards of an interrupted attempt")
    parser.add_argument(
        "--limit-tasks", type=int, help="bounded development only; always produces incomplete VALID_STOP"
    )
    args = parser.parse_args(argv)
    mode = "dry-run" if args.dry_run else "check" if args.check else "materialize"
    started = time.monotonic()
    completed, total = 0, 0
    output = None
    permission = None
    contract = None
    results = []
    persist = False

    def log(stage, **fields):
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
        contract = read_json(args.contract)
        output = (ROOT / contract["output_root"]).resolve()
        if (
            not output.is_relative_to(ROOT)
            or args.workers < 1
            or (args.limit_tasks is not None and args.limit_tasks < 1)
        ):
            raise ValueError("output must be repository-relative; worker/task counts must be positive")
        if args.resume and mode != "materialize":
            raise ValueError("resume is only for interrupted materialization")
        if args.limit_tasks and mode == "check":
            raise ValueError("release check requires complete coverage")
        if mode == "materialize":
            if (output / "report.json").exists() or (output.exists() and not args.resume):
                raise ValueError("attempt exists; retain completed attempts, use --resume only after interruption")
            persist = True
        authorization, gate = read_json(args.authorization), read_json(args.gate)
        permission = release_permission(ROOT, contract, authorization, gate, output)
        if not permission.start_permitted:
            raise CorpusStop(permission.outcome, permission.reason or "not authorized", permission.ancestor_receipt_id)
        panel, _ = load_view_panel(ROOT, ROOT / contract["panel_manifest"])
        view_report = read_json(ROOT / contract["views_report"])
        views = {r["task_id"]: r for r in view_report["results"]}
        source = source_release(ROOT, contract) if contract["source_issue"] == 74 else None
        source_results = {r["task_id"]: r for r in source["results"]} if source else {}
        record_root = ROOT / source["contract"]["output_root"] if source else output
        total = len(panel)
        if mode == "dry-run":
            log(
                "dry-run:complete",
                outcome="PASS",
                start_permitted=True,
                scientific_completion=False,
                counts=contract["expected"],
                writes=0,
            )
            return 0
        previous = None
        if mode == "check":
            previous = read_json(output / "report.json")
            if (
                previous.get("contract") != contract
                or previous.get("authorization") != authorization
                or previous.get("gate") != gate
                or previous.get("outcome") != "PASS"
                or not previous.get("complete_selected_coverage")
                or not previous.get("scientific_completion")
            ):
                raise ValueError("no complete matching release to check")
        else:
            output.mkdir(parents=True, exist_ok=True)
            binding_path = output / "attempt.json"
            binding = {"contract": contract, "authorization": authorization, "gate": gate}
            if binding_path.exists() and read_json(binding_path) != binding:
                raise ValueError("interrupted attempt settings differ")
            write_json(binding_path, binding)
        selected = panel[: args.limit_tasks] if args.limit_tasks else panel
        pending_rows = iter(selected)
        failure = None
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            pending = {}

            def submit():
                row = next(pending_rows, None)
                if row is None:
                    return
                task_path = output / "tasks" / row["task_id"].replace("/", "__") / "task.json"
                checking = mode == "check" or (args.resume and task_path.exists())
                future = executor.submit(
                    build_task, ROOT, row, views[row["task_id"]], contract, record_root, checking or source is not None
                )
                pending[future] = row["task_id"]

            for _ in range(args.workers):
                submit()
            log(f"{mode}:start")
            while pending:
                done, _ = wait(pending, timeout=10, return_when=FIRST_COMPLETED)
                if not done:
                    log(f"{mode}:heartbeat")
                for future in done:
                    task_id = pending.pop(future)
                    try:
                        result = future.result()
                        if source is not None and result != source_results[task_id]:
                            raise ValueError("replayed task does not match the source release binding")
                        results.append(result)
                        completed += 1
                        log(f"{mode}:task", task_id=task_id)
                    except Exception as error:
                        failure = failure or error
                        log(f"{mode}:task-failed", task_id=task_id, reason=str(error))
                    if failure is None:
                        submit()
        if failure:
            raise failure
        results.sort(key=lambda r: r["task_id"])
        counts = {
            "tasks": len(results),
            "states": sum(r["states"] for r in results),
            "decisions": sum(r["records"] for r in results),
        }
        if counts != contract["expected"] or {r["task_id"] for r in results} != {r["task_id"] for r in panel}:
            raise CorpusStop(StopOutcome.VALID_STOP, "partial coverage cannot complete the corpus release")
        log(f"{mode}:isolation-start")
        # The streaming global audit reports progress too, independently of worker completion.
        audit = audit_release(ROOT, results, progress=lambda n: log(f"{mode}:isolation", audited_tasks=n))
        if previous is not None and (
            previous["results"] != results or previous["counts"] != counts or previous["audit"] != audit
        ):
            raise ValueError("release coverage/audit differs from retained receipt")
        receipt = replace(permission, run_state="completed", scientific_completion=True, start_permitted=False)
        report = {
            "schema_version": "matched_modality_corpus_release_v1" if source else "visual_state_corpus_release_v1",
            "contract": contract,
            "authorization": authorization,
            "gate": gate,
            "receipt": receipt.to_dict(),
            "outcome": "PASS",
            "scientific_completion": True,
            "complete_selected_coverage": True,
            "counts": counts,
            "results": results,
            "audit": audit,
            "qualified_modalities": contract["qualified_modalities"],
            "released_modalities": contract["released_modalities"],
            "checks": {name: True for name in contract["required_checks"]},
            "gpu_throughput_qualified": False,
            "training_started": False,
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
        if mode == "materialize":
            write_json(output / "report.json", report)
        log(f"{mode}:complete", outcome="PASS", counts=counts, scientific_completion=True)
        return 0
    except Exception as error:
        outcome = error.outcome if isinstance(error, CorpusStop) else StopOutcome.INVALID
        if contract is not None and output is not None:
            receipt = RunReceipt(
                binding=ReceiptBinding(contract["contract_id"], output.name, output),
                outcome=outcome,
                run_state="invalid-not-run" if outcome is StopOutcome.INVALID else "gated-not-run",
                start_permitted=False,
                scientific_completion=False,
                gate_receipt_id=permission.gate_receipt_id if permission else None,
                ancestor_receipt_id=error.ancestor if isinstance(error, CorpusStop) else None,
                reason=str(error),
            )
            if persist:
                write_json(
                    output / "report.json",
                    {
                        "contract": contract,
                        "outcome": outcome.value,
                        "receipt": receipt.to_dict(),
                        "scientific_completion": False,
                        "complete_selected_coverage": False,
                        "results": results,
                        "reason": str(error),
                    },
                )
        log(f"{mode}:stopped", outcome=outcome.value, scientific_completion=False, reason=str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
