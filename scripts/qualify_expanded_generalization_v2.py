#!/usr/bin/env python
"""Recompute the frozen expanded-generalization-robustness-v2 admission artifact.

Reads only existing evidence (qualification, probe, baseline evaluation) and the
read-only budget ledger, reapplies the v2 estimand and membership rule frozen in
``configs/experiments/expanded-study/generalization-robustness-protocol-v2.json``,
and writes ``outputs/expanded-study/v1/generalization-robustness/admission-v2.json``.

The ledger and all evidence inputs are never mutated. The script is deterministic
and idempotent: rerunning it reproduces byte-identical admission content.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

QUALIFICATION_PATH = ROOT / "outputs/expanded-study/v1/generalization-robustness/qualification.json"
PROBE_PATH = ROOT / "outputs/expanded-study/v1/generalization-robustness/probe.json"
BASELINE_EVAL_PATH = ROOT / "docs/experiments/expanded-study/baseline-evaluation.json"
LEDGER_PATH = ROOT / "outputs/expanded-study/v1/budget.json"
V1_ADMISSION_PATH = ROOT / "outputs/expanded-study/v1/generalization-robustness/admission.json"
ADMISSION_V2_PATH = ROOT / "outputs/expanded-study/v1/generalization-robustness/admission-v2.json"

PROTOCOL_ID = "expanded-generalization-robustness-v2"
BRANCH = "generalization_robustness"
LEARNED_ALGORITHMS = ["best_first_add_greedy", "best_first_add_w3"]
MODALITIES = ["text-state", "visual-state", "multimodal-state"]
FAMILIES = ["scale-up", "shifted-init", "object-renaming", "render-restyle", "name-compression"]
DECISION_CAP_MULTIPLIER = 2
SAFETY_FACTOR = 1.25
PLANNED_WORKER_JOBS = 2
MAX_TRANSFER_GPU_HOURS = 11.89


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _branch_spend(ledger: dict, branch: str) -> float:
    total = 0.0
    for attempt in ledger["attempts"]:
        if attempt["branch"] != branch:
            continue
        total += (
            attempt["max_seconds"] * len(attempt["gpus"]) / 3600
            if attempt["status"] in {"reserved", "running"}
            else attempt["gpu_hours"]
        )
    return total


def per_algo_modality_seconds(probe: dict) -> dict[str, float]:
    bounds = probe["per_combo_bounds"]
    return {
        algorithm: sum(bounds[f"{algorithm}__{modality}"]["max_observed_call_seconds"] for modality in MODALITIES)
        for algorithm in LEARNED_ALGORITHMS
    }


def task_estimand_seconds(task: dict, per_algo: dict[str, float]) -> float:
    learned = sum(
        DECISION_CAP_MULTIPLIER * task["reference_costs"][algorithm]["decisions"] * per_algo[algorithm]
        for algorithm in LEARNED_ALGORITHMS
    )
    base = sum(per_algo.values())
    return learned + base


def rank_families(eligible: list[dict]) -> dict[str, list[dict]]:
    families: dict[str, list[dict]] = defaultdict(list)
    for variant in eligible:
        families[variant["family"]].append(variant)
    for variants in families.values():
        variants.sort(
            key=lambda variant: (
                variant["reference_costs"]["best_first_add_greedy"]["decisions"]
                + variant["reference_costs"]["best_first_add_w3"]["decisions"],
                variant["variant_id"],
            )
        )
    return families


def scope_cost(families: dict[str, list[dict]], per_algo: dict[str, float], k: int) -> dict[str, float]:
    return {
        family: sum(task_estimand_seconds(variant, per_algo) for variant in variants[:k]) / 3600.0
        for family, variants in sorted(families.items())
    }


def main() -> dict:
    qualification = read_json(QUALIFICATION_PATH)
    probe = read_json(PROBE_PATH)
    baseline = read_json(BASELINE_EVAL_PATH)
    ledger = read_json(LEDGER_PATH)
    v1_admission = read_json(V1_ADMISSION_PATH)

    eligible = [variant for variant in qualification["variants"] if variant["eligible"]]
    families = rank_families(eligible)
    per_algo = per_algo_modality_seconds(probe)

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

    branch_cap = ledger["allocations_gpu_hours"][BRANCH]
    branch_spent = _branch_spend(ledger, BRANCH)
    remainder = branch_cap - branch_spent
    overhead_gpu_hours = PLANNED_WORKER_JOBS * probe["planned_worker_overhead_seconds"] / 3600.0
    max_budget = remainder + MAX_TRANSFER_GPU_HOURS

    max_k = min(len(families[family]) for family in FAMILIES)
    ladder = {}
    for k in range(1, max_k + 1):
        matrix_by_family = scope_cost(families, per_algo, k)
        matrix_gpu_hours = sum(matrix_by_family.values())
        required = matrix_gpu_hours * SAFETY_FACTOR + overhead_gpu_hours
        ladder[k] = {
            "variants": k * len(FAMILIES),
            "matrix_gpu_hours": matrix_gpu_hours,
            "matrix_gpu_hours_by_family": matrix_by_family,
            "planned_worker_overhead_gpu_hours": overhead_gpu_hours,
            "required_gpu_hours": required,
            "fits_branch_remainder": required <= remainder,
            "fits_with_max_transfer": required <= max_budget,
        }

    fitting = [k for k in range(1, max_k + 1) if ladder[k]["fits_branch_remainder"]]
    if not fitting:
        decision = "VALID_STOP"
        chosen_k = 0
        transfer = None
    else:
        chosen_k = max(fitting)
        if chosen_k < 2:
            decision = "VALID_STOP"
        else:
            decision = "PASS"
        required = ladder[chosen_k]["required_gpu_hours"]
        transfer = None
        if required > remainder and decision == "PASS":
            transfer = {
                "from": "recovery_reserve",
                "to": BRANCH,
                "gpu_hours": required - remainder,
                "executed": False,
                "reason": "Minimum sufficient prospective transfer to admit the frozen v2 scope.",
            }

    membership = {
        family: [variant["variant_id"] for variant in families[family][:chosen_k]] for family in FAMILIES
    }
    canonical_ids = sorted(variant_id for ids in membership.values() for variant_id in ids)
    canonical_blob = json.dumps(canonical_ids, sort_keys=True, separators=(",", ":"))
    membership_sha256 = hashlib.sha256(canonical_blob.encode()).hexdigest()

    membership_detail = {}
    for family in FAMILIES:
        rows = []
        for variant in families[family][:chosen_k]:
            reference_costs = variant["reference_costs"]
            rows.append(
                {
                    "variant_id": variant["variant_id"],
                    "decisions_best_first_add_greedy": reference_costs["best_first_add_greedy"]["decisions"],
                    "decisions_best_first_add_w3": reference_costs["best_first_add_w3"]["decisions"],
                    "estimand_seconds": task_estimand_seconds(variant, per_algo),
                }
            )
        membership_detail[family] = {
            "k": len(rows),
            "matrix_gpu_hours": ladder[chosen_k]["matrix_gpu_hours_by_family"][family] if chosen_k else 0.0,
            "variants": rows,
        }

    artifact = {
        "schema_version": "expanded_generalization_admission_v2",
        "protocol_id": PROTOCOL_ID,
        "decision": decision,
        "outcome": "PASS" if decision == "PASS" else "VALID_STOP",
        "ledger_mutated": False,
        "equation": {
            "prose": (
                "required_gpu_hours = (sum over admitted variants t of (sum over learned algorithms a in "
                "{best_first_add_greedy, best_first_add_w3} of (2 x reference_costs(t, a).decisions x "
                "sum over modalities d of max_observed_call_seconds(a, d)) + sum over a, d of "
                "1 x max_observed_call_seconds(a, d)) / 3600) x 1.25 + planned_worker_jobs x "
                "planned_worker_overhead_seconds / 3600 + 0. The pretrained_base cell is priced at exactly "
                "one decision call per episode; the random_valid and exact_reference controls are CPU-only "
                "and priced at zero. Probe spend is already inside the ledger branch spend and is not added "
                "again (the v1 admission's 0.6273 GPU-h probe double-count is recorded as a nit and not repeated)."
            ),
            "learned_cell_seconds": "cap(t, a) x max_observed_call_seconds(a, d), cap = 2 x reference decisions",
            "pretrained_base_cell_seconds": "1 x max_observed_call_seconds(a, d)",
            "control_cell_seconds": 0,
            "safety_factor": SAFETY_FACTOR,
            "planned_worker_jobs": PLANNED_WORKER_JOBS,
            "probe_spend_added": 0.0,
        },
        "inputs": {
            "qualification": {
                "path": str(QUALIFICATION_PATH.relative_to(ROOT)),
                "sha256": "cb5badf72543e351fff2a822b0cf4e2fc3b754405f7ef1d1369118891921118f",
                "eligible_variants": len(eligible),
            },
            "suite_sha256": "a20c30cc7b57a784e955626b07e4eea28a956964c300b6404467d956e092a742",
            "probe": {
                "path": str(PROBE_PATH.relative_to(ROOT)),
                "per_algo_max_observed_call_seconds_summed_over_modalities": per_algo,
                "planned_worker_overhead_seconds": probe["planned_worker_overhead_seconds"],
                "probe_gpu_hours": probe["probe_gpu_hours"],
            },
            "baseline_pretrained_base_evidence": {
                "path": str(BASELINE_EVAL_PATH.relative_to(ROOT)),
                "episodes": base_evidence["episodes"],
                "decisions": base_evidence["decisions"],
                "invalid_operations": base_evidence["invalid_operations"],
                "successes": base_evidence["successes"],
                "interpretation": (
                    "pretrained base terminated on an invalid first operation in every baseline episode "
                    "(1 decision each)"
                ),
            },
            "ledger": {
                "path": str(LEDGER_PATH.relative_to(ROOT)),
                "branch_cap_gpu_hours": branch_cap,
                "branch_spent_gpu_hours": branch_spent,
                "branch_remainder_gpu_hours": remainder,
                "max_transfer_available_gpu_hours": MAX_TRANSFER_GPU_HOURS,
            },
            "v1_admission": {
                "path": str(V1_ADMISSION_PATH.relative_to(ROOT)),
                "decision": v1_admission["decision"],
                "outcome": v1_admission["outcome"],
                "note": "v1 L4 VALID_STOP retained; v2 does not close issues #96/#98.",
            },
        },
        "membership_rule": {
            "rank": (
                "per family, eligible variants by (reference_costs.best_first_add_greedy.decisions + "
                "reference_costs.best_first_add_w3.decisions, then variant_id); cheapest prefix of size k per family"
            ),
            "uniform_k": True,
            "objective": (
                "maximize total admitted variants subject to required_gpu_hours fitting the budget, trying "
                "branch remainder first and only then a transfer of at most 11.89 GPU-h"
            ),
            "stop_rule": (
                "STOP if even k=1 per family does not fit or the largest remainder-feasible scope is under "
                "k=2 per family (<10 variants)"
            ),
        },
        "chosen_k": chosen_k,
        "total_variants": chosen_k * len(FAMILIES),
        "membership_sha256": membership_sha256,
        "membership_canonical_form": "sha256 of json.dumps(sorted(variant_ids), sort_keys=True, separators=(',', ':'))",
        "membership": membership,
        "membership_detail": membership_detail,
        "ladder_by_k": ladder,
        "budget": {
            "branch_cap_gpu_hours": branch_cap,
            "branch_spent_gpu_hours": branch_spent,
            "branch_remainder_gpu_hours": remainder,
            "matrix_gpu_hours": ladder[chosen_k]["matrix_gpu_hours"] if chosen_k else 0.0,
            "planned_worker_overhead_gpu_hours": overhead_gpu_hours,
            "required_gpu_hours": ladder[chosen_k]["required_gpu_hours"] if chosen_k else overhead_gpu_hours,
            "headroom_gpu_hours": (remainder - ladder[chosen_k]["required_gpu_hours"]) if chosen_k else remainder,
            "fits_branch_remainder": bool(chosen_k) and ladder[chosen_k]["fits_branch_remainder"],
            "max_available_with_transfer_gpu_hours": max_budget,
        },
        "transfer_request": transfer,
        "next_rung": {
            "k": chosen_k + 1 if chosen_k < max_k else None,
            "required_gpu_hours": ladder[chosen_k + 1]["required_gpu_hours"] if chosen_k < max_k else None,
            "transfer_that_would_be_required_gpu_hours": (
                ladder[chosen_k + 1]["required_gpu_hours"] - remainder
                if chosen_k < max_k and ladder[chosen_k + 1]["required_gpu_hours"] > remainder
                else 0.0
            ),
            "note": (
                "k=6 fits only with a 10.8875 GPU-h transfer; not proposed because k=5 fits the branch "
                "remainder alone."
            ),
        },
    }

    ADMISSION_V2_PATH.write_text(json.dumps(artifact, indent=1, sort_keys=False) + "\n")
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
