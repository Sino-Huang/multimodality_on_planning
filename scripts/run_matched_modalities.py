#!/usr/bin/env python3
"""Prepare/verify matched inputs and expose the fixed study's resource admission stop.

The v1 candidate pool is exhausted for Storage. GPU execution remains blocked;
this entry point does not pretend the unfulfilled #92 GPU scheduler is implemented.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.matched_preparation import audit_training, verify_candidate_stop  # noqa: E402
from examples.planning_benchmark_slice.matched_tasks import DEFAULT_STUDY, Progress, prepare_candidates  # noqa: E402
from examples.planning_benchmark_slice.modality_view_preparation import write_json  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402

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
    parser.add_argument("stage", choices=("prepare", "verify", "qualify", "train", "decide", "evaluate"))
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--devices", nargs="+", default=["0", "1"])
    parser.add_argument("--master-ports", nargs="+", type=int, default=[18775, 18776])
    parser.add_argument("--modality", choices=("text-state", "visual-state", "multimodal-state"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be positive")
    with Progress() as progress:
        try:
            study = read_json(args.study)
            validate_settings(study, args.devices, args.master_ports)
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
        except (ValueError, OSError) as error:
            progress(f"{args.stage}:stopped", outcome="INVALID", model_input_ready=False, reason=str(error))
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
