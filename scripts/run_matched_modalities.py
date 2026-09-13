#!/usr/bin/env python3
"""Prepare, qualify, train and verify matched modalities with cumulative stage budgets."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.matched_preparation import audit_training, verify_candidate_stop  # noqa: E402
from examples.planning_benchmark_slice.matched_tasks import Progress, prepare_candidates  # noqa: E402
from examples.planning_benchmark_slice.modality_view_preparation import write_json  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402


def execute_v2(args, study, progress):
    from examples.planning_benchmark_slice import matched_execution as execution
    from examples.planning_benchmark_slice.matched_scheduler import run_gpu_jobs
    from examples.planning_benchmark_slice.matched_views import check_final_task, prepare_final_panel

    output = ROOT / study["output_root"]
    if args.dry_run:
        progress(
            f"{args.stage}:dry_run",
            completed=1,
            total=1,
            outcome="PASS",
            writes=0,
            model_calls=0,
            training_cells=12,
            implemented=True,
            gpu_cap_seconds=study["budget"],
            preparation_exists=(output / "preparation/report.json").exists(),
            qualification_exists=(output / "qualification.json").exists(),
        )
        return 0
    if args.stage in ("prepare", "verify"):
        pool = (
            read_json(output / "preparation/candidates.json")
            if (output / "preparation/candidates.json").exists()
            else None
        )
        if pool is None:
            if args.stage == "verify":
                raise ValueError("missing candidate preparation")
            pool = prepare_candidates(ROOT, study, args.workers, progress)
        training = audit_training(ROOT, study, progress)
        if args.stage == "prepare":
            tasks = prepare_final_panel(ROOT, study, pool, progress)
            write_json(output / "preparation/final-panel.json", {"study": study, "tasks": tasks, "outcome": "PASS"})
            report = {
                "study": study,
                "outcome": "PASS",
                "model_input_ready": True,
                "training": training,
                "final_tasks": [t["row"]["task_id"] for t in tasks],
                "final_states": sum(t["states"] for t in tasks),
                "gpu_throughput_qualified": False,
            }
            write_json(output / "preparation/report.json", report)
        else:
            report, panel = execution.require_preparation(ROOT, study)
            if report["training"] != training:
                raise ValueError("source input audit differs")
            for task in panel["tasks"]:
                if check_final_task(ROOT, study, task, progress) != task["measurements"]:
                    raise ValueError("final input measurements differ")
            if (output / "training").exists():
                for job in execution.training_jobs(ROOT, study):
                    execution.verify_training_cell(ROOT, study, job)
            if (output / "evaluation").exists():
                if execution.verify_evaluations(ROOT, study, panel) != 144:
                    raise ValueError("partial final episode coverage")
        progress(f"{args.stage}:complete", completed=2156, total=2156, outcome="PASS", model_input_ready=True)
        return 0
    if args.stage == "qualify":
        report = execution.qualification(ROOT, study, progress, args.resume)
    elif args.stage == "train":
        report = execution.train(ROOT, study, progress, args.resume)
    elif args.stage == "decide":
        report = execution.decide(ROOT, study)
    elif args.stage == "evaluate":
        decision = read_json(output / "decision.json")
        if decision["study"] != study or decision["decision"] != "CONTINUE":
            raise ValueError("technical continuation decision required")
        if not args.modality:
            raise ValueError("--modality is required for evaluation")
        jobs = [
            {
                "modality": args.modality,
                "assigned_worker": i,
                "result_path": str((output / "evaluation" / args.modality / f"gpu-{i}.json").relative_to(ROOT)),
            }
            for i in range(2)
        ]
        run_gpu_jobs(ROOT, study, "evaluate", jobs, progress, resume=args.resume)
        report = {
            "study": study,
            "outcome": "PASS",
            "modality": args.modality,
            "worker_reports": [j["result_path"] for j in jobs],
        }
        write_json(output / "evaluation" / f"{args.modality}.json", report)
    else:
        raise ValueError("unknown stage")
    progress(f"{args.stage}:complete", completed=1, total=1, **report)
    return 0 if report["outcome"] == "PASS" else 2


UNFULFILLED = [
    "eligible Storage task under the frozen candidate/profile/reference limits",
    "complete three-domain final state/goal views and processed preview inspection",
    "final live-input processor qualification",
    "GPU worker scheduler, cumulative deadline/resume enforcement and hardware throughput qualification",
    "final adapter training, technical checkpoint decision and final evaluation (later goals)",
]


def validate_settings(study, devices, ports):
    budget = study["budget"]
    if (
        [budget[k] for k in ("qualification_seconds", "training_development_seconds", "final_evaluation_seconds")]
        != [3600, 18000, 21600]
        or budget["total_seconds"] != 43200
        or budget["borrowing"]
        or budget["reset_on_resume"]
    ):
        raise ValueError("cumulative stage budget differs from the fixed twelve-hour plan")
    if len(devices) != len(set(devices)) or len(ports) != len(set(ports)) or len(devices) != len(ports):
        raise ValueError("concurrent workers require distinct explicit GPU/MASTER_PORT mappings")
    if study["historical_checkpoint_reuse"] or study["continuation"]["positive_model_score_required"]:
        raise ValueError("checkpoint reuse or positive-score gate differs from the successor plan")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "verify", "qualify", "train", "decide", "evaluate", "_worker"))
    parser.add_argument("--study", type=Path, default=ROOT / "configs/experiments/matched-modalities/study-v3.json")
    parser.add_argument("--job", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--devices", nargs="+", default=["0", "1"])
    parser.add_argument("--master-ports", nargs="+", type=int, default=[18775, 18776])
    parser.add_argument("--modality", choices=("text-state", "visual-state", "multimodal-state"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.stage == "_worker":
        from examples.planning_benchmark_slice.matched_workers import worker_main

        return worker_main(ROOT, read_json(args.job))
    if args.workers < 1:
        parser.error("--workers must be positive")
    with Progress() as progress:
        try:
            study = read_json(args.study)
            validate_settings(study, args.devices, args.master_ports)
            if study["study_id"] in {"matched-modalities-v2", "matched-modalities-v3"}:
                if (
                    list(map(str, study["launch"]["devices"])) != args.devices
                    or study["launch"]["master_ports"] != args.master_ports
                ):
                    raise ValueError("GPU/port arguments must match the recorded study launch mapping")
                return execute_v2(args, study, progress)
            output = ROOT / study["output_root"] / "preparation"
            pool_path, report_path = output / "candidates.json", output / "report.json"
            pool = read_json(pool_path) if pool_path.exists() else None
            if pool and pool["study"] != study:
                raise ValueError("candidate pool differs from requested settings")
            if args.dry_run:
                progress(
                    f"{args.stage}:dry_run",
                    completed=1,
                    total=1,
                    outcome="PASS",
                    writes=0,
                    model_calls=0,
                    execution_admitted=False,
                    model_input_ready=False,
                    missing_domains=pool["missing_domains"] if pool else study["final"]["domains"],
                    unfulfilled_prerequisites=UNFULFILLED,
                    note="command/preparation preflight only; GPU execution is unimplemented and blocked",
                )
                return 0
            if args.stage not in ("prepare", "verify"):
                progress(
                    f"{args.stage}:stopped",
                    outcome="VALID_STOP",
                    model_input_ready=False,
                    reason="fixed final task set is not qualified; no GPU worker may start",
                    unfulfilled_prerequisites=UNFULFILLED,
                    gpu_stage_seconds=0,
                    model_calls=0,
                )
                return 2
            if args.stage == "verify" and not report_path.exists():
                raise ValueError("no completed preparation report to verify")
            if args.stage == "prepare" and report_path.exists():
                raise ValueError("terminal preparation already exists; use verify, not resume or overwrite")
            attempt_path = output / "preparing.json"
            if args.stage == "prepare":
                if attempt_path.exists():
                    if not args.resume or read_json(attempt_path)["study"] != study:
                        raise ValueError("interrupted preparation requires --resume with unchanged settings")
                else:
                    if args.resume:
                        raise ValueError("no preparation attempt to resume")
                    write_json(attempt_path, {"study": study, "gpu_stage_seconds": 0})
            if args.stage == "prepare" and pool is None:
                pool = prepare_candidates(ROOT, study, args.workers, progress)
            if pool is None:
                raise ValueError("missing candidate pool")
            training = audit_training(ROOT, study, progress)
            stop = verify_candidate_stop(ROOT, study, pool, progress)
            if not stop["resource_stop_verified"]:
                raise ValueError(
                    "candidate pool is not a verified resource stop; full #92 view/worker implementation required"
                )
            report = {
                "study": study,
                "outcome": "VALID_STOP",
                "preparation_stop_verified": True,
                "model_input_ready": False,
                "gpu_throughput_qualified": False,
                "scientific_completion": False,
                "training": training,
                "resource_stop": stop,
                "unfulfilled_prerequisites": UNFULFILLED,
                "gpu_stage_seconds": {"qualification": 0, "training_development": 0, "final_evaluation": 0},
                "new_model_calls": 0,
                "input_assets_reused": True,
                "implementation_scope": "CPU candidates, selected semantic projections and resource-stop verification",
            }
            if args.stage == "prepare":
                write_json(report_path, report)
            else:
                if read_json(report_path) != report:
                    raise ValueError("preparation report differs from independent semantic verification")
            progress(
                f"{args.stage}:complete",
                completed=training["records"],
                total=training["records"],
                outcome="VALID_STOP",
                verification="PASS",
                model_input_ready=False,
                missing_domains=stop["missing_domains"],
                gpu_stage_seconds=0,
                report=str(report_path),
                unfulfilled_prerequisites=UNFULFILLED,
            )
            return 0 if args.stage == "verify" else 2
        except (ValueError, OSError, RuntimeError) as error:
            outcome = "VALID_STOP" if str(error).startswith("VALID_STOP:") else "INVALID"
            progress(f"{args.stage}:stopped", outcome=outcome, model_input_ready=False, reason=str(error))
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
