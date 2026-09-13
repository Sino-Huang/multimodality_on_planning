"""Preparation admission, resource estimates and verifiable matched checkpoints."""

import math
from pathlib import Path

from .matched_scheduler import StageBudget, run_gpu_jobs
from .modality_view_preparation import write_json
from .scene_assets import read_json


def require_preparation(root, study):
    report = read_json(root / study["output_root"] / "preparation/report.json")
    if report["study"] != study or report["outcome"] != "PASS" or not report["model_input_ready"]:
        raise ValueError("matched final inputs are not completely qualified")
    panel = read_json(root / study["output_root"] / "preparation/final-panel.json")
    if (
        panel["study"] != study
        or len(panel["tasks"]) != 3
        or {t["row"]["domain"] for t in panel["tasks"]} != set(study["final"]["domains"])
    ):
        raise ValueError("final panel coverage differs")
    return report, panel


def admission_estimate(study, panel, qualifications, *, spent_training_seconds=0.0, completed_cells=()):
    estimates = {}
    membership_counts = {"bfs": 28, "best_first_width": 26, "best_first_add_w3": 27, "best_first_add_greedy": 27}
    for modality in study["modalities"]:
        reports = [r["modalities"][modality] for r in qualifications]
        micro = max(r["training_microstep_seconds"] for r in reports)
        call = max(r["seconds_per_call"] for r in reports)
        load = max(r["training_load_seconds"] for r in reports)
        infer_load = max(r["inference_load_seconds"] for r in reports)
        save = max(r["adapter_save_seconds"] for r in reports)
        # Price independent per-adapter worker loads, diagnostics and isolation.
        jobs = [
            load + micro * (512 + 2 * membership_counts[a]) + 4 * save + infer_load + 8 * call
            for a in study["algorithms"]
            if (modality, a) not in completed_cells
        ]
        slots = [0.0, 0.0]
        for seconds in jobs:
            slot = min(range(2), key=lambda i: (slots[i], i))
            slots[slot] += seconds
        decisions = sum(t["row"]["reference_costs"][a]["decisions"] for t in panel["tasks"] for a in study["algorithms"])
        # Evaluation implementation currently generates singly, so no batching speedup is assumed.
        final = (4 * decisions * call) / 2 + infer_load + 40 * max(save, 1.0)
        estimates[modality] = {
            "training_seconds": max(slots) * 1.25,
            "evaluation_seconds": final * 1.25,
            "training_microstep_seconds": micro,
            "seconds_per_call": call,
        }
    remaining_training = sum(r["training_seconds"] for r in estimates.values())
    training = spent_training_seconds + remaining_training
    evaluation = sum(r["evaluation_seconds"] for r in estimates.values())
    training_fits = training <= study["budget"]["training_development_seconds"] - 120
    evaluation_fits = evaluation <= study["budget"]["final_evaluation_seconds"] - 120
    return {
        "by_modality": estimates,
        "training_seconds": training,
        "remaining_training_seconds": remaining_training,
        "spent_training_seconds": spent_training_seconds,
        "evaluation_seconds": evaluation,
        "training_fits": training_fits,
        "evaluation_fits": evaluation_fits,
        "fits": training_fits and evaluation_fits,
    }


def qualification(root, study, progress, resume):
    _, panel = require_preparation(root, study)
    output = root / study["output_root"]
    completed = set()
    if study.get("scene_views"):
        for job in training_jobs(root, study):
            if (root / job["result_path"]).exists():
                verify_training_cell(root, study, job)
                completed.add((job["modality"], job["algorithm"]))
    jobs = [
        {"assigned_worker": i, "result_path": str((output / "qualification" / f"gpu-{i}.json").relative_to(root))}
        for i in range(2)
    ]
    pending = []
    for job in jobs:
        if (root / job["result_path"]).exists():
            prior = read_json(root / job["result_path"])
            if prior["study"] != study or prior["outcome"] != "PASS":
                raise ValueError("retained qualification differs")
        else:
            pending.append(job)
    run_gpu_jobs(root, study, "qualify", pending, progress, resume=resume)
    results = [read_json(root / j["result_path"]) for j in jobs]
    spent = 0.0
    if study.get("scene_views"):
        for modality in ("visual-state", "multimodal-state"):
            if {a for r in results for a in r["modalities"][modality]["semantic_algorithms"]} != set(
                study["algorithms"]
            ):
                raise ValueError("native GPU semantic family coverage is incomplete")
            if not all(r["modalities"][modality]["covers_selected_input_envelope"] for r in results):
                raise ValueError("native GPU input-shape coverage is incomplete")
        ledger = read_json(StageBudget(root, study, "train").path)
        spent = sum(s["ended"] - s["started"] for s in ledger["segments"] if s["stage"] == "train")
    estimate = admission_estimate(study, panel, results, spent_training_seconds=spent, completed_cells=completed)
    report = {
        "study": study,
        "outcome": "PASS" if estimate["fits"] else "VALID_STOP",
        "hardware_passed": True,
        "estimate": estimate,
        "worker_reports": [j["result_path"] for j in jobs],
        "model_outcomes_used_for_selection": False,
    }
    write_json(output / "qualification.json", report)
    return report


def training_jobs(root, study):
    output = root / study["output_root"]
    text_output = (
        root / read_json(root / study["text_training_predecessor"])["output_root"]
        if study.get("text_training_predecessor")
        else output
    )
    return [
        {
            "modality": m,
            "algorithm": a,
            "result_path": str(
                ((text_output if m == "text-state" else output) / "training" / m / a / "report.json").relative_to(root)
            ),
        }
        for m in study["modalities"]
        for a in study["algorithms"]
    ]


def verify_training_cell(root, study, job):
    if job.get("modality") == "text-state" and study.get("text_training_predecessor"):
        previous = read_json(root / study["text_training_predecessor"])
        unchanged = (
            "membership",
            "corpus_report",
            "training",
            "training_seed",
            "model_id",
            "model_revision",
            "processor_class",
            "processor_revision",
            "processor_overrides",
            "context_tokens",
            "maximum_input_tokens",
            "output_tokens",
            "search_memory",
            "inference",
            "algorithms",
        )
        views = read_json(root / study["scene_views"])
        if (
            any(study[k] != previous[k] for k in unchanged)
            or views["study"] != study
            or views["outcome"] != "PASS"
            or not views["text_inputs_unchanged"]
            or views["counts"]["records"] != 2156
        ):
            raise ValueError("retained text training is not matched to the scene-only successor")
        expected = next(
            j
            for j in training_jobs(root, previous)
            if j["modality"] == "text-state" and j["algorithm"] == job["algorithm"]
        )
        if job != expected:
            raise ValueError("retained text checkpoint path differs")
        return verify_training_cell(root, previous, job)
    report = read_json(root / job["result_path"])
    membership = read_json(root / study["membership"])
    if (
        report["study"] != study
        or report["outcome"] != "PASS"
        or report["steps"] != 16
        or report["seed"] != 17
        or report["training_record_ids"] != membership["training_record_ids"][job["algorithm"]]
        or report["training_settings"] != study["training"]
        or not report["adapter_isolation_passed"]
    ):
        raise ValueError("training checkpoint coverage, exposure or technical binding differs")
    folder = (root / job["result_path"]).parent
    if (
        root / report["final_checkpoint"] != folder / "final"
        or not (folder / "final/adapter_model.safetensors").is_file()
    ):
        raise ValueError("missing or substituted matched final adapter")
    state = read_json(folder / "training_state.json")
    if state["global_step"] != 16 or [r["step"] for r in report["diagnostics"]] != [5, 10]:
        raise ValueError("incomplete training updates or development diagnostics")
    if any(not math.isfinite(r["eval_loss"]) for r in report["diagnostics"]):
        raise ValueError("non-finite development loss")
    if study.get("scene_views"):
        binding = read_json(folder / "training-binding.json")
        if (
            binding["study"] != study
            or binding["training_record_ids"] != report["training_record_ids"]
            or binding["diagnostic_record_ids"] != membership["diagnostic_record_ids"][job["algorithm"]]
        ):
            raise ValueError("native training checkpoint input binding differs")
        losses = [r for r in state["log_history"] if "loss" in r]
        if [r["step"] for r in losses] != list(range(1, 17)) or any(
            not math.isfinite(r[k]) for r in losses for k in ("loss", "grad_norm")
        ):
            raise ValueError("native training updates or numerical validity are incomplete")
    adapter = read_json(folder / "final/adapter_config.json")
    if adapter["r"] != 64 or adapter["lora_alpha"] != 128:
        raise ValueError("adapter settings differ")
    return report


def adapter_paths(root, study, modality):
    return {
        j["algorithm"]: str((root / j["result_path"]).parent / "final")
        for j in training_jobs(root, study)
        if j["modality"] == modality
    }


def train(root, study, progress, resume):
    require_preparation(root, study)
    output = root / study["output_root"]
    q = read_json(output / "qualification.json")
    if q["study"] != study or q["outcome"] != "PASS":
        raise ValueError("actual hardware qualification/admission is required before training")
    jobs = training_jobs(root, study)
    pending = []
    for job in jobs:
        if (root / job["result_path"]).exists():
            verify_training_cell(root, study, job)
        else:
            pending.append(job)
    run_gpu_jobs(root, study, "train", pending, progress, resume=resume)
    for job in jobs:
        verify_training_cell(root, study, job)
    report = {
        "study": study,
        "outcome": "PASS",
        "complete_training_coverage": True,
        "cells": jobs,
        "training_cells": len(jobs),
        "record_presentations": 6144,
        "optimizer_updates": 192,
        "final_model_episodes": 0,
        "retained_text_cells": 4 if study.get("text_training_predecessor") else 0,
    }
    write_json(output / "training.json", report)
    return report


def decide(root, study):
    require_preparation(root, study)
    output = root / study["output_root"]
    q = read_json(output / "qualification.json")
    if q["study"] != study or q["outcome"] != "PASS":
        raise ValueError("hardware admission is not complete")
    for job in training_jobs(root, study):
        verify_training_cell(root, study, job)
    report = {
        "study": study,
        "outcome": "PASS",
        "decision": "CONTINUE",
        "training_cells": 12,
        "positive_score_required": False,
        "final_evaluation_executed": False,
    }
    write_json(output / "decision.json", report)
    return report


def verify_evaluations(root, study, panel):
    from .matched_views import final_view_store
    from .visual_episode import replay_visual_episode

    output = root / study["output_root"]
    count = 0
    for modality in study["modalities"]:
        checkpoints = adapter_paths(root, study, modality)
        for task in panel["tasks"]:
            row = task["row"]
            views = final_view_store(root, study, task)
            for algorithm in study["algorithms"]:
                for arm in ("pretrained_base", "process_sft", "exact_reference", "random_valid"):
                    path = (
                        output
                        / "evaluation"
                        / modality
                        / row["task_id"].replace("/", "__")
                        / f"{algorithm}-{arm}.json.gz"
                    )
                    report = read_json(path)
                    if (
                        report["contract_id"],
                        report["modality"],
                        report["algorithm"],
                        report["arm"],
                        report["seed"],
                    ) != (study["study_id"], modality, algorithm, arm, 17):
                        raise ValueError("final episode identity differs")
                    expected_checkpoint = (
                        str(Path(checkpoints[algorithm]).relative_to(root)) if arm == "process_sft" else None
                    )
                    if (
                        report.get("checkpoint") != expected_checkpoint
                        or report.get("model_id") != study["model_id"]
                        or report.get("model_revision") != study["model_revision"]
                    ):
                        raise ValueError("final episode model/checkpoint binding differs")
                    replay_visual_episode(root, row, report, views)
                    count += 1
    return count
