#!/usr/bin/env python
"""Recompute the frozen expanded-modality-stress admission artifact (#126).

Inputs are existing evidence only: the frozen 24-problem panel, the v2 probe
per-combo call-time maxima, the replay-verified baseline evaluation and episode
store, and the shared budget ledger. No corrupted-observation model outcome
exists or is used. The artifact pins the source-task membership, the runtime
estimand and the budget arithmetic; it mutates no ledger state. The control
arm-invariance claim (random_valid / exact_reference decisions are identical
across observation arms) is re-verified from the baseline episode store before
the shared per-(task, algorithm) control bindings are admitted.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROTOCOL_PATH = ROOT / "configs/experiments/expanded-study/modality-stress-protocol.json"
PANEL_PATH = ROOT / "configs/experiments/expanded-study/final-panel.json"
PROBE_PATH = ROOT / "outputs/expanded-study/v1/generalization-robustness/probe.json"
BASELINE_EVAL_PATH = ROOT / "docs/experiments/expanded-study/baseline-evaluation.json"
BASELINE_EPISODES_ROOT = ROOT / "outputs/expanded-study/v1/baseline/episodes"
LEDGER_PATH = ROOT / "outputs/expanded-study/v1/budget.json"
ADMISSION_PATH = ROOT / "outputs/expanded-study/v1/modality-stress/admission.json"

PROTOCOL_ID = "expanded-modality-stress-v1"
BRANCH = "generalization_robustness"
LEARNED_ALGORITHMS = ["best_first_add_greedy", "best_first_add_w3"]
ARMS = ["text-state", "visual-state", "multimodal-state"]
FAMILY_ARMS = {
    "visual-blank": ["visual-state", "multimodal-state"],
    "visual-degraded": ["visual-state", "multimodal-state"],
    "text-shuffled": ["text-state", "multimodal-state"],
    "text-masked": ["text-state", "multimodal-state"],
}
DECISION_CAP_MULTIPLIER = 2
SAFETY_FACTOR = 1.25
PLANNED_WORKER_JOBS = 2
MAX_TRANSFER_GPU_HOURS = 11.89
MIN_MEANINGFUL_K = 4


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def read_episode(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def _branch_spend(ledger: dict, branch: str) -> float:
    total = 0.0
    for attempt in ledger["attempts"]:
        if attempt.get("branch") == branch:
            total += float(attempt.get("gpu_hours") or 0.0)
    return total


def per_combo_maxobs(probe: dict) -> dict[str, float]:
    return {
        combo: float(row["max_observed_call_seconds"])
        for combo, row in probe["per_combo_bounds"].items()
    }


def task_estimand_seconds(reference_costs: dict, maxobs: dict[str, float]) -> float:
    total = 0.0
    for arms in FAMILY_ARMS.values():
        for algorithm in LEARNED_ALGORITHMS:
            arm_sum = sum(maxobs[f"{algorithm}__{arm}"] for arm in arms)
            decisions = int(reference_costs[algorithm]["decisions"])
            total += (DECISION_CAP_MULTIPLIER * decisions + 1) * arm_sum
    return total


def verify_control_arm_invariance(tasks: list[dict]) -> dict:
    """Re-verify that CPU-control outcomes do not depend on the observation arm."""

    checked = 0
    mismatches = []
    for task in tasks:
        task_id = task["row"]["task_id"]
        folder = BASELINE_EPISODES_ROOT / "text-state" / task_id.replace("/", "__")
        for algorithm in LEARNED_ALGORITHMS:
            for condition in ("random_valid", "exact_reference"):
                signatures = []
                for arm in ARMS:
                    episode = read_episode(
                        BASELINE_EPISODES_ROOT
                        / arm
                        / task_id.replace("/", "__")
                        / f"{algorithm}-{condition}.json.gz"
                    )
                    result = episode["result"]
                    signatures.append(
                        (
                            result["decision_count"],
                            result["invariant_valid_success"],
                            result["invalid_operation_count"],
                            result["expansion_count"],
                            episode["seed"],
                        )
                    )
                checked += 1
                if len(set(signatures)) != 1:
                    mismatches.append({"task_id": task_id, "algorithm": algorithm, "condition": condition})
        if not folder.is_dir():
            raise ValueError(f"baseline episode store is missing {folder}")
    if mismatches:
        raise ValueError(f"control arm-invariance violated in baseline evidence: {mismatches}")
    return {"checked_triples": checked, "mismatches": 0}


def main() -> dict:
    protocol = read_json(PROTOCOL_PATH)
    panel = read_json(PANEL_PATH)
    probe = read_json(PROBE_PATH)
    baseline = read_json(BASELINE_EVAL_PATH)
    ledger = read_json(LEDGER_PATH)

    if protocol["protocol_id"] != PROTOCOL_ID or panel["panel_id"] != protocol["panel_id"]:
        raise ValueError("modality-stress protocol/panel identity differs")
    tasks = panel["tasks"]
    if len(tasks) != 24:
        raise ValueError("frozen panel no longer holds 24 source tasks")

    base_evidence = baseline["by_condition"]["pretrained_base"]
    if not (
        base_evidence["episodes"] == 288
        and base_evidence["decisions"] == 288
        and base_evidence["invalid_operations"] == 288
        and base_evidence["successes"] == 0
    ):
        raise ValueError(
            "baseline pretrained_base evidence no longer matches the frozen 288/288 first-decision termination"
        )

    invariance = verify_control_arm_invariance(tasks)

    maxobs = per_combo_maxobs(probe)
    ranked = sorted(
        (
            {
                "task_id": task["row"]["task_id"],
                "domain": task["row"]["domain"],
                "decisions_best_first_add_greedy": task["row"]["reference_costs"]["best_first_add_greedy"][
                    "decisions"
                ],
                "decisions_best_first_add_w3": task["row"]["reference_costs"]["best_first_add_w3"]["decisions"],
                "estimand_seconds": task_estimand_seconds(task["row"]["reference_costs"], maxobs),
            }
            for task in tasks
        ),
        key=lambda row: (row["estimand_seconds"], row["task_id"]),
    )

    branch_cap = ledger["allocations_gpu_hours"][BRANCH]
    branch_spent = _branch_spend(ledger, BRANCH)
    remainder = branch_cap - branch_spent
    overhead_gpu_hours = PLANNED_WORKER_JOBS * probe["planned_worker_overhead_seconds"] / 3600.0

    ladder = {}
    for k in range(1, len(ranked) + 1):
        matrix_gpu_hours = sum(row["estimand_seconds"] for row in ranked[:k]) / 3600.0
        required = matrix_gpu_hours * SAFETY_FACTOR + overhead_gpu_hours
        ladder[str(k)] = {
            "source_tasks": k,
            "variant_cells": k * len(FAMILY_ARMS) * len(LEARNED_ALGORITHMS) * 2,
            "matrix_gpu_hours": matrix_gpu_hours,
            "planned_worker_overhead_gpu_hours": overhead_gpu_hours,
            "required_gpu_hours": required,
            "fits_branch_remainder": required <= remainder,
        }

    fitting = [k for k in range(1, len(ranked) + 1) if ladder[str(k)]["fits_branch_remainder"]]
    transfer = None
    if not fitting:
        minimal_required = ladder[str(MIN_MEANINGFUL_K)]["required_gpu_hours"]
        shortfall = minimal_required - remainder
        if 0 < shortfall <= MAX_TRANSFER_GPU_HOURS:
            chosen_k = MIN_MEANINGFUL_K
            decision = "PASS"
            transfer = {
                "from": "recovery_reserve",
                "to": BRANCH,
                "gpu_hours": shortfall,
                "executed": False,
                "reason": "Minimum sufficient prospective transfer to admit the frozen minimum meaningful scope (k=4).",
            }
        else:
            chosen_k = 0
            decision = "VALID_STOP"
    else:
        chosen_k = max(fitting)
        if chosen_k < MIN_MEANINGFUL_K:
            decision = "VALID_STOP"
            chosen_k = 0
        else:
            decision = "PASS"

    membership = [row["task_id"] for row in ranked[:chosen_k]]
    canonical_blob = json.dumps(sorted(membership), sort_keys=True, separators=(",", ":"))
    membership_sha256 = hashlib.sha256(canonical_blob.encode()).hexdigest()

    if decision == "PASS":
        frozen = protocol["membership_rule"]
        if (
            frozen["chosen_k"] != chosen_k
            or sorted(frozen["membership"]) != sorted(membership)
            or frozen["membership_sha256"] != membership_sha256
        ):
            raise ValueError("frozen protocol membership differs from the recomputed admission")

    required = ladder[str(chosen_k)]["required_gpu_hours"] if chosen_k else overhead_gpu_hours
    artifact = {
        "schema_version": "expanded_modality_stress_admission_v1",
        "protocol_id": PROTOCOL_ID,
        "decision": decision,
        "outcome": decision,
        "ledger_mutated": False,
        "equation": {
            "prose": (
                "required_gpu_hours = (sum over admitted source tasks t, corruption families f, learned "
                "algorithms a of (2 x reference_costs(t, a).decisions + 1) x sum over applicable arms d of "
                "max_observed_call_seconds(a, d)) / 3600 x 1.25 + planned_worker_jobs x "
                "planned_worker_overhead_seconds / 3600. Each learned cell is priced at its hard decision-call "
                "cap (2 x reference decisions); each pretrained_base cell is priced at exactly one call; "
                "random_valid and exact_reference controls are CPU-only at zero; the clean-observation "
                "comparators are reused replay-verified baseline episodes at zero new GPU cost. Corruption "
                "preserves image dimensions and page structure exactly, so the clean probe maxima remain "
                "valid per-combo price bounds; runtime-enforced caps backstop any overrun as explicit "
                "missingness."
            ),
            "decision_cap_multiplier": DECISION_CAP_MULTIPLIER,
            "pretrained_base_calls_per_episode": 1,
            "control_price_gpu_hours": 0.0,
            "comparator_price_gpu_hours": 0.0,
            "safety_factor": SAFETY_FACTOR,
            "planned_worker_jobs": PLANNED_WORKER_JOBS,
            "probe_spend_added": 0.0,
        },
        "inputs": {
            "panel": {"path": str(PANEL_PATH.relative_to(ROOT)), "source_tasks": len(tasks)},
            "probe": {
                "path": str(PROBE_PATH.relative_to(ROOT)),
                "per_combo_max_observed_call_seconds": maxobs,
                "planned_worker_overhead_seconds": probe["planned_worker_overhead_seconds"],
                "note": "v2 probe maxima reused; corruption preserves image dimensions and page structure",
            },
            "baseline_pretrained_base_evidence": {
                "path": str(BASELINE_EVAL_PATH.relative_to(ROOT)),
                "episodes": base_evidence["episodes"],
                "decisions": base_evidence["decisions"],
                "invalid_operations": base_evidence["invalid_operations"],
                "successes": base_evidence["successes"],
            },
            "control_arm_invariance": {
                "episodes_root": str(BASELINE_EPISODES_ROOT.relative_to(ROOT)),
                **invariance,
                "consequence": "CPU controls bound per (task, algorithm, seed), shared across families and arms",
            },
            "ledger": {
                "path": str(LEDGER_PATH.relative_to(ROOT)),
                "branch_cap_gpu_hours": branch_cap,
                "branch_spent_gpu_hours": branch_spent,
                "branch_remainder_gpu_hours": remainder,
                "max_transfer_available_gpu_hours": MAX_TRANSFER_GPU_HOURS,
            },
        },
        "membership_rule": {
            "rank": "source tasks by (estimand_seconds, task_id); cheapest prefix of size k",
            "uniform_k": True,
            "objective": "maximize admitted source tasks subject to required_gpu_hours fitting the branch remainder",
            "stop_rule": (
                "VALID_STOP if no k >= 4 fits the remainder and the k=4 shortfall exceeds the 11.89 GPU-h "
                "maximum transfer"
            ),
        },
        "chosen_k": chosen_k,
        "total_source_tasks": chosen_k,
        "variant_cells": chosen_k * len(FAMILY_ARMS) * len(LEARNED_ALGORITHMS) * 2,
        "membership_sha256": membership_sha256,
        "membership_canonical_form": "sha256 of json.dumps(sorted(task_ids), sort_keys=True, separators=(',', ':'))",
        "membership": membership,
        "membership_detail": [
            {**row, "matrix_gpu_hours": row["estimand_seconds"] / 3600.0} for row in ranked[:chosen_k]
        ],
        "ladder_by_k": ladder,
        "budget": {
            "branch_cap_gpu_hours": branch_cap,
            "branch_spent_gpu_hours": branch_spent,
            "branch_remainder_gpu_hours": remainder,
            "matrix_gpu_hours": (sum(row["estimand_seconds"] for row in ranked[:chosen_k]) / 3600.0)
            if chosen_k
            else 0.0,
            "planned_worker_overhead_gpu_hours": overhead_gpu_hours,
            "required_gpu_hours": required,
            "headroom_gpu_hours": remainder - required,
            "fits_branch_remainder": bool(chosen_k) and required <= remainder,
        },
        "transfer_request": transfer,
        "next_rung": {
            "k": chosen_k + 1 if chosen_k and chosen_k < len(ranked) else None,
            "required_gpu_hours": ladder[str(chosen_k + 1)]["required_gpu_hours"]
            if chosen_k and chosen_k < len(ranked)
            else None,
            "note": "next rung exceeds the remainder; the remainder-first rule admits the largest fitting k",
        },
    }

    ADMISSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    ADMISSION_PATH.write_text(json.dumps(artifact, indent=1, sort_keys=False) + "\n")
    print(
        json.dumps(
            {
                "decision": decision,
                "chosen_k": chosen_k,
                "required_gpu_hours": artifact["budget"]["required_gpu_hours"],
                "membership_sha256": membership_sha256,
            }
        )
    )
    return artifact


if __name__ == "__main__":
    main()
