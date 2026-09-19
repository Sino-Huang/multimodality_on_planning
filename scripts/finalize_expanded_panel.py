#!/usr/bin/env python
"""Audit measured capacity and cost admission before freezing the Goal-2 panel."""

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write


def main():
    if (ROOT / "configs/experiments/expanded-study/final-panel.json").exists():
        raise ValueError("panel already frozen; verify it without rewriting its freeze time")
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    views = read(ROOT / "outputs/expanded-study/v1/panel-v2/reference-views.json")
    audit = read(ROOT / "docs/experiments/expanded-study/panel-independent-audit.json")
    live = read(ROOT / "docs/experiments/expanded-study/panel-live-views.json")
    protocol = read(ROOT / "configs/experiments/expanded-study/panel-capacity-protocol.json")
    admission = read(ROOT / "configs/experiments/expanded-study/panel-cost-admission-v2.json")
    historical_qualification = read(ROOT / admission["historical_qualification"])
    historical_evaluation = read(ROOT / admission["historical_evaluation"])
    assert historical_evaluation["complete_coverage"] and historical_evaluation["independent_replay_passed"] == 144
    for job in ("panel-runtime-parity", "panel-common-memory", "panel-live-views"):
        latest = [a for a in ledger["attempts"] if a["job_id"] == job][-1]
        assert latest["status"] == "succeeded", f"required audit still incomplete: {job}"
        assert read(Path(latest["directory"]) / "hook-result.json")["returncode"] == 0
    assert audit["outcome"] == live["outcome"] == "PASS" and len(audit["tasks"]) == len(live["tasks"]) == 24
    workers = []
    for gpu in (0, 1):
        attempt = [a for a in ledger["attempts"] if a["job_id"] == f"panel-gpu-{gpu}"][-1]
        if attempt["status"] != "succeeded":
            raise RuntimeError(f"GPU {gpu} qualification is {attempt['status']}; do not freeze")
        folder = Path(attempt["directory"])
        assert read(folder / "hook-result.json")["returncode"] == 0
        report = read(folder / "qualification.json")
        assert int(report["cuda_visible_devices"]) == gpu and int(report["master_port"]) == attempt["master_port"]
        assert len(report["modalities"]) == 3
        for modality in report["modalities"]:
            assert len(modality["adapters"]) == 4
            cases = {c["name"]: c for c in modality["cases"]}
            assert cases["single_limit"]["input_tokens"] == [32384]
            assert cases["batch_limit"]["input_tokens"] == [12000, 12000]
            assert all(c["generated_tokens"] == 384 and not c["scored"] for c in cases.values())
        workers.append(dict(attempt=attempt, qualification=report))
    assert workers[0]["attempt"]["master_port"] != workers[1]["attempt"]["master_port"]
    reference_decisions = sum(len(t["measurements"]) for t in views["tasks"])
    assert reference_decisions * 12 == protocol["max_declared_model_calls"]
    spent = sum(a["gpu_hours"] for a in ledger["attempts"] if a["branch"] == "expanded_baseline")
    estimates = []
    for modality in ("text-state", "visual-state", "multimodal-state"):
        measurements = [next(m for m in w["qualification"]["modalities"] if m["modality"] == modality) for w in workers]
        reference_seconds = max(
            c["seconds"] / c["batch_size"]
            for m in measurements
            for c in m["cases"]
            if c["name"].startswith("reference_envelope")
        )
        full_seconds = max(
            c["seconds"] / c["batch_size"]
            for m in measurements
            for c in m["cases"]
            if c["name"] in ("single_limit", "batch_limit")
        )
        calls = reference_decisions * 4  # two conditions times twice-reference call allowance
        load = 2 * max(m["load_seconds"] for m in measurements)
        estimates.append(
            dict(
                modality=modality,
                maximum_model_calls=calls,
                reference_envelope_seconds_per_call=reference_seconds,
                full_capacity_seconds_per_call=full_seconds,
                model_loading_gpu_seconds=load,
                reference_proxy_gpu_hours=(calls * reference_seconds + load) * 1.25 / 3600,
                full_capacity_proxy_gpu_hours=(calls * full_seconds + load) * 1.25 / 3600,
            )
        )
        prior = next(r for r in admission["historical_scaling"] if r["modality"] == modality)
        assert prior["new_reference_decisions"] == reference_decisions
        old_decisions = sum(
            e["result"]["decision_count"]
            for e in historical_evaluation["episodes"]
            if e["modality"] == modality and e["arm"] == "exact_reference"
        )
        old_seconds = sum(
            w["finished"] - w["started"] for w in historical_evaluation["worker_reports"] if w["modality"] == modality
        )
        assert prior["old_reference_decisions"] == old_decisions
        assert prior["old_gpu_worker_seconds"] == old_seconds
        assert (
            prior["unadjusted_historical_proxy_gpu_hours"]
            == old_seconds * reference_decisions / old_decisions * 1.25 / 3600
        )
        slowdown = max(
            1, reference_seconds / historical_qualification["estimate"]["by_modality"][modality]["seconds_per_call"]
        )
        estimates[-1].update(
            historical_slowdown_factor=slowdown,
            historical_consumption_proxy_gpu_hours=prior["unadjusted_historical_proxy_gpu_hours"] * slowdown,
        )
    proxy = sum(e["reference_proxy_gpu_hours"] for e in estimates)
    historical_proxy = sum(e["historical_consumption_proxy_gpu_hours"] for e in estimates)
    fits = spent + historical_proxy <= ledger["allocations_gpu_hours"]["expanded_baseline"]
    summary = dict(
        outcome="QUALIFIED_WITH_CONDITIONAL_COST_ADMISSION" if fits else "COST_INFEASIBLE",
        verified_at=time.time(),
        tasks=24,
        hardware_capacity_passed=True,
        budget_branch="expanded_baseline",
        branch_cap_gpu_hours=ledger["allocations_gpu_hours"]["expanded_baseline"],
        spent_gpu_hours=spent,
        reference_proxy_gpu_hours=proxy,
        reference_allowance_proxy_fits=spent + proxy <= ledger["allocations_gpu_hours"]["expanded_baseline"],
        historical_consumption_proxy_gpu_hours=historical_proxy,
        admission_protocol="configs/experiments/expanded-study/panel-cost-admission-v2.json",
        historical_estimate_limitation=admission["limitation"],
        full_capacity_proxy_gpu_hours=sum(e["full_capacity_proxy_gpu_hours"] for e in estimates),
        estimates=estimates,
        workers=workers,
        estimate_limitations=protocol["bound_vs_estimate"],
        final_panel_frozen=fits,
    )
    write(ROOT / "docs/experiments/expanded-study/panel-gpu-qualification.json", summary)
    if not fits:
        print("COST_INFEASIBLE: retain full 24-task scope and measured evidence; no silent reduction or final freeze")
        return 2
    source_by_id = {t["task_id"]: t["source_snapshot"] for t in audit["tasks"]}
    panel = dict(
        program_id="expanded-nine-day-v1",
        panel_id="expanded-panel-v2-qualified",
        frozen_at=time.time(),
        protocol="configs/experiments/expanded-study/panel-protocol-v2.json",
        capacity_protocol="configs/experiments/expanded-study/panel-capacity-protocol.json",
        cost_admission_protocol="configs/experiments/expanded-study/panel-cost-admission-v2.json",
        algorithms=views["protocol"]["reference"]["algorithms"],
        modalities=["text-state", "visual-state", "multimodal-state"],
        conditions=["pretrained_base", "process_sft", "random_valid", "exact_reference"],
        logical_bindings=1152,
        model_episodes=576,
        reference_decision_multiplier=2,
        evaluation_seed=17,
        view_report="outputs/expanded-study/v1/panel-v2/reference-views.json",
        view_runtime="examples.planning_benchmark_slice.expanded_views.ExpandedTaskViews",
        tasks=[
            dict(row=t["row"], source_snapshot=source_by_id[t["row"]["task_id"]], reference_paths=t["reference_paths"])
            for t in views["tasks"]
        ],
        evidence=[
            "docs/experiments/expanded-study/panel-independent-audit.json",
            "docs/experiments/expanded-study/panel-live-views.json",
            "docs/experiments/expanded-study/panel-gpu-qualification.json",
        ],
        bounded_input_failure="Preserve complete oversized requests as explicit failures; no truncation or task removal",
        cost_basis="historical worker consumption scaled by reference complexity and measured slowdown, with 1.25 margin; full-allowance projections do not fit; all 24 tasks retained under the shared hard cap",
        completion_within_budget_guaranteed=False,
        checkpoint_source="docs/experiments/expanded-study/readiness.json",
        new_training=False,
        episode_runner_implemented_by_goal2=False,
    )
    write(ROOT / "configs/experiments/expanded-study/final-panel.json", panel)
    print(
        f"PASS: 24 tasks frozen; conditional historical proxy {historical_proxy:.3f} GPU-hours plus {spent:.3f} spent within 56; maximum-allowance proxy {proxy:.3f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
