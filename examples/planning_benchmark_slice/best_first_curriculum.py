"""Issue-67 curriculum and replacement-setting comparison contracts."""

from __future__ import annotations

import gzip
import json
import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from src.data_collect.governance import StopOutcome

from .best_first_development import (
    BestFirstDevelopmentExperiment,
    BestFirstDevelopmentTask,
    cost_balanced_task_shards,
    load_best_first_issue66,
    lower_95_bound,
)

_DESIGN_PATH = Path("configs/experiments/best-first-issue67-curriculum-v1.json")
_AUTHORIZATION_PATH = Path("configs/experiments/best-first-issue67-authorization-v1.json")
_HEURISTIC_STOP_PATH = Path("configs/experiments/best-first-issue67-heuristic-gated-not-run-v1.json")
CURRICULA = ("staged", "shuffled", "mixed_order")


def load_best_first_issue67(repo_root: str | Path) -> BestFirstDevelopmentExperiment:
    """Load the authorized representative curriculum experiment."""

    root = Path(repo_root).resolve()
    design = _json_object(root / _DESIGN_PATH)
    authorization = _json_object(root / _AUTHORIZATION_PATH)
    heuristic_stop = _json_object(root / _HEURISTIC_STOP_PATH)
    contract_id = "issue-67-best-first-curriculum-comparison-v1"
    if (
        design.get("schema_version") != "best_first_issue67_curriculum_v1"
        or design.get("contract_id") != contract_id
        or design.get("source_issue") != 67
        or design.get("parent_issue") != 38
        or design.get("algorithm") != "best_first_add_greedy"
        or tuple(design.get("curricula", ())) != CURRICULA
        or design.get("training", {}).get("seed") != 17
        or design.get("training", {}).get("replicate_count_per_cell") != 1
        or design.get("evaluation", {}).get("physical_model_conditions") != 4
        or design.get("evaluation", {}).get("decision_call_multiplier") != 2
        or design.get("evaluation", {}).get("reference_decision_ceiling") != 1_024
    ):
        raise ValueError("issue #67 curriculum design differs from the ticket")
    if (
        authorization.get("schema_version") != "best_first_issue67_authorization_v1"
        or authorization.get("authorization_id") != "issue-67-best-first-curriculum-authorization-v1"
        or authorization.get("contract_id") != contract_id
        or authorization.get("outcome") != StopOutcome.PASS.value
        or authorization.get("start_permitted") is not True
        or authorization.get("scientific_completion") is not False
        or authorization.get("gate_receipt")
        != {
            "contract_id": contract_id,
            "outcome": StopOutcome.PASS.value,
            "receipt_id": f"gate:{contract_id}:PASS",
            "source_issue": 67,
        }
    ):
        raise ValueError("issue #67 authorization differs from the active contract")
    if (
        heuristic_stop.get("schema_version") != "best_first_issue67_heuristic_gated_not_run_v1"
        or heuristic_stop.get("outcome") != StopOutcome.ANCESTOR_STOP.value
        or heuristic_stop.get("start_permitted") is not False
        or heuristic_stop.get("scientific_completion") is not False
    ):
        raise ValueError("issue #67 original-heuristic stop receipt is invalid")

    base = load_best_first_issue66(root)
    for name, expected_contract in (
        ("issue65_terminal_result", "issue-65-best-first-add-w3-development-v1"),
        ("issue66_terminal_result", "issue-66-best-first-add-greedy-development-v1"),
    ):
        result = _json_object(root / design["ancestry"][name])
        if (
            result.get("contract_id") != expected_contract
            or result.get("outcome") != StopOutcome.PASS.value
            or result.get("scientific_completion") is not True
            or result.get("semantic_replay") != {"episodes": 368, "status": "PASS"}
        ):
            raise ValueError(f"issue #67 ancestor is incomplete: {name}")

    corpus_root = root / design["data"]["corpus_root"]
    for control in CURRICULA:
        if not (corpus_root / f"curricula/process/{control}.jsonl.gz").is_file():
            raise ValueError(f"issue #67 curriculum is missing: {control}")
    tasks = tuple(replace(task, source_issue=67) for task in base.tasks)
    experiment = BestFirstDevelopmentExperiment(
        root,
        design,
        authorization,
        tasks,
        base.training_manifest,
        base.train_datasets,
        base.dev_datasets,
    )
    if experiment.training_counts != {"dev": 6_696, "train": 8_342}:
        raise ValueError("issue #67 representative corpus coverage differs from issue #66")
    for stage in authorization["authorized_stages"]:
        experiment.require_stage(str(stage))
    return experiment


def select_issue67_coverage(
    tasks: Sequence[BestFirstDevelopmentTask],
    *,
    model_load_seconds: float,
    throughput_samples: Sequence[float],
    runtime_seconds_per_call: float,
    rollout_shard_count: int,
    physical_model_conditions: int = 4,
    certification_seconds: float = 15 * 60 * 60,
    safety_margin: float = 1.2,
) -> dict[str, Any]:
    """Select the full panel or the frozen cheapest-per-domain fallback."""

    task_list = tuple(tasks)
    if len(task_list) != 23 or rollout_shard_count <= 0:
        raise ValueError("issue #67 qualification requires the 23-task issue-64 panel")
    throughput = lower_95_bound(throughput_samples)
    by_domain: dict[str, list[BestFirstDevelopmentTask]] = defaultdict(list)
    for task in task_list:
        by_domain[task.domain_id].append(task)
    fallback = tuple(
        min(rows, key=lambda task: (task.model_call_limit, task.difficulty, task.pair_id))
        for _, rows in sorted(by_domain.items())
    )
    candidates = (
        ("complete_issue64_v3_development_panel", task_list),
        ("cheapest_complete_task_per_domain", fallback),
    )
    projections = []
    selected: tuple[BestFirstDevelopmentTask, ...] = ()
    selected_mode: str | None = None
    for mode, candidate in candidates:
        shards = cost_balanced_task_shards(candidate, shard_count=rollout_shard_count)
        maximum_shard_calls = physical_model_conditions * max(
            sum(task.model_call_limit for task in shard) for shard in shards
        )
        projected = safety_margin * (
            model_load_seconds + maximum_shard_calls / throughput + maximum_shard_calls * runtime_seconds_per_call
        )
        projections.append(
            {
                "maximum_scheduled_calls": physical_model_conditions * sum(task.model_call_limit for task in candidate),
                "maximum_shard_scheduled_calls": maximum_shard_calls,
                "mode": mode,
                "projected_rollout_seconds": projected,
                "task_count": len(candidate),
            }
        )
        if selected_mode is None and projected <= certification_seconds:
            selected = candidate
            selected_mode = mode
    selected_projection = next((row for row in projections if row["mode"] == selected_mode), projections[-1])
    return {
        "calls_per_second_lower_95": throughput,
        "candidate_projections": projections,
        "coverage": {
            **selected_projection,
            "mode": selected_mode,
            "outcome": StopOutcome.PASS.value if selected_mode is not None else StopOutcome.VALID_STOP.value,
            "task_ids": [task.instance_id for task in selected],
        },
        "model_load_seconds": model_load_seconds,
        "outcomes_observed": False,
        "runtime_seconds_per_call": runtime_seconds_per_call,
        "schema_version": "best_first_issue67_hardware_qualification_v1",
    }


def curriculum_metadata(
    experiment: BestFirstDevelopmentExperiment,
    control: str,
) -> dict[str, list[dict[str, Any]]]:
    """Read the released process ordering for one curriculum control."""

    if control not in CURRICULA:
        raise ValueError(f"unsupported issue #67 curriculum: {control}")
    corpus_root = experiment.repo_root / experiment.design["data"]["corpus_root"]
    by_split: dict[str, list[dict[str, Any]]] = {"train": [], "dev": []}
    with gzip.open(corpus_root / f"curricula/process/{control}.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("algorithm") != experiment.algorithm:
                continue
            split = str(row.get("split"))
            if split in by_split:
                by_split[split].append(row)
    if {split: len(rows) for split, rows in by_split.items()} != experiment.training_counts:
        raise ValueError(f"issue #67 {control} curriculum coverage is incomplete")
    return by_split


def paired_bootstrap_interval(
    left: Mapping[str, float],
    right: Mapping[str, float],
    *,
    resamples: int,
    seed: int,
    confidence: float,
) -> dict[str, float]:
    """Return a whole-instance paired mean-difference interval."""

    ids = sorted(left)
    if not ids or set(ids) != set(right):
        raise ValueError("paired curriculum statistics require identical task coverage")
    differences = [float(left[item]) - float(right[item]) for item in ids]
    generator = random.Random(seed)
    draws = sorted(
        sum(differences[generator.randrange(len(differences))] for _ in differences) / len(differences)
        for _ in range(resamples)
    )
    tail = (1.0 - confidence) / 2.0
    return {
        "lower": _quantile(draws, tail),
        "point": sum(differences) / len(differences),
        "upper": _quantile(draws, 1.0 - tail),
    }


def replacement_setting_summary(
    experiment: BestFirstDevelopmentExperiment,
) -> dict[str, Any]:
    """Summarize the matched #65/#66 result without claiming a heuristic contrast."""

    design = experiment.design
    w3 = _json_object(experiment.repo_root / design["ancestry"]["issue65_terminal_result"])
    greedy = _json_object(experiment.repo_root / design["ancestry"]["issue66_terminal_result"])
    trace_manifest = _json_object(experiment.repo_root / design["data"]["trace_manifest"])
    selected = {task.pair_id for task in experiment.tasks}
    rows = [row for row in trace_manifest["pairs"] if str(row["pair_id"]) in selected]
    if len(rows) != len(selected):
        raise ValueError("issue #67 replacement comparison is not pair-complete")
    totals = {
        algorithm: {
            metric: sum(int(row["traces"][algorithm][metric]) for row in rows)
            for metric in ("decision_count", "expansion_count", "solution_cost")
        }
        for algorithm in ("best_first_add_w3", "best_first_add_greedy")
    }
    threshold = float(design["analysis"]["material_decision_reduction"])
    decision_interval = _paired_ratio_reduction_interval(
        [int(row["traces"]["best_first_add_w3"]["decision_count"]) for row in rows],
        [int(row["traces"]["best_first_add_greedy"]["decision_count"]) for row in rows],
        resamples=int(design["analysis"]["bootstrap_resamples"]),
        seed=int(design["analysis"]["bootstrap_seed"]),
        confidence=float(design["analysis"]["bootstrap_confidence"]),
    )
    return {
        "algorithm_difference": "priority_and_reopening_rule",
        "conclusion": (
            "greedy_materially_reduces_model_decisions"
            if decision_interval["point"] >= threshold and decision_interval["lower"] > 0
            else "no_material_model_decision_advantage"
        ),
        "greedy_relative_decision_reduction": decision_interval,
        "learned_success_difference_greedy_minus_w3": (
            greedy["condition_results"]["process_sft"]["invariant_valid_success"]
            - w3["condition_results"]["process_sft"]["invariant_valid_success"]
        ),
        "material_decision_reduction_threshold": threshold,
        "totals": totals,
    }


def _paired_ratio_reduction_interval(
    baseline: Sequence[int],
    comparison: Sequence[int],
    *,
    resamples: int,
    seed: int,
    confidence: float,
) -> dict[str, float]:
    if not baseline or len(baseline) != len(comparison) or any(value <= 0 for value in baseline):
        raise ValueError("paired efficiency statistics require positive matched baselines")
    generator = random.Random(seed)
    draws = []
    for _ in range(resamples):
        indices = [generator.randrange(len(baseline)) for _ in baseline]
        draws.append(1.0 - sum(comparison[index] for index in indices) / sum(baseline[index] for index in indices))
    draws.sort()
    tail = (1.0 - confidence) / 2.0
    return {
        "lower": _quantile(draws, tail),
        "point": 1.0 - sum(comparison) / sum(baseline),
        "upper": _quantile(draws, 1.0 - tail),
    }


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot take a quantile of no values")
    position = probability * (len(values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[lower])
    fraction = position - lower
    return float(values[lower] * (1.0 - fraction) + values[upper] * fraction)


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


__all__ = [
    "CURRICULA",
    "curriculum_metadata",
    "load_best_first_issue67",
    "paired_bootstrap_interval",
    "replacement_setting_summary",
    "select_issue67_coverage",
]
