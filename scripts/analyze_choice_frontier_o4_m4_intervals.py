#!/usr/bin/env python
"""Issue #134 R2: M4 task-cluster bootstrap intervals (post-hoc diagnostics, CPU-only).

Frozen protocol: docs/experiments/choice-frontier/issue-134-protocol.md.

From ``outputs/choice-frontier/o4/metrics/all-episode-metrics.json`` (the stored
#132 learned_adapter episodes), computes task-cluster bootstrap 95% intervals —
the zoo convention of ``scripts/analyze_choice_frontier_o4.py``: nine task
clusters drawn with replacement, fixed seed 133, 10,000 draws, percentile
interval — for (a) observed minus chance heap-head agreement and (b) last-label
rate minus its chance rate. M4 carries diagnostic status under the frozen #133
protocol; these intervals are post-hoc diagnostics, not confirmatory tests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.analyze_choice_frontier_o4 import bootstrap  # noqa: E402

RECORDS_PATH = ROOT / "outputs/choice-frontier/o4/metrics/all-episode-metrics.json"
ANALYSIS_PATH = ROOT / "outputs/choice-frontier/o4/metrics/analysis.json"
PROTOCOL_PATH = ROOT / "configs/experiments/choice-frontier/choice-frontier-protocol-v1.json"
OUTPUT_PATH = ROOT / "outputs/choice-frontier/o4/metrics/m4-task-cluster-intervals.json"
ARM = "learned_adapter"


def main() -> None:
    records = json.loads(RECORDS_PATH.read_text())["records"]
    analysis = json.loads(ANALYSIS_PATH.read_text())
    protocol = json.loads(PROTOCOL_PATH.read_text())
    membership = list(protocol["evaluation"]["membership"])

    rows = [r for r in records if r["arm"] == ARM and r["teacher_decisions"]]
    tasks = sorted({r["task"] for r in rows})
    if tasks != sorted(membership):
        raise ValueError(f"M4 subset tasks differ from the frozen membership: {tasks}")
    algorithms = sorted({r["algorithm"] for r in rows})
    if len(rows) != 18 or any(
        len([r for r in rows if r["task"] == task]) != 2 for task in tasks
    ):
        raise ValueError(f"M4 subset is not the 18 stored #132 learned episodes: {len(rows)} rows")

    # Gate: pooled points reproduce analysis.json arms.learned_adapter.m4_teacher_agreement.
    pooled = analysis["arms"][ARM]["m4_teacher_agreement"]
    decisions = sum(r["teacher_decisions"] for r in rows)
    agreements = sum(r["teacher_agreements"] for r in rows)
    chance = sum(r["teacher_chance_sum"] for r in rows)
    last = sum(r["selected_last_count"] for r in rows)
    checks = {
        "on_policy_decisions_k_ge_2": (decisions, pooled["on_policy_decisions_k_ge_2"]),
        "observed": (agreements / decisions, pooled["observed"]),
        "chance": (chance / decisions, pooled["chance"]),
        "observed_minus_chance": ((agreements - chance) / decisions, pooled["observed_minus_chance"]),
        "selected_last_count": (last, pooled["selected_last_count"]),
        "selected_last_rate": (last / decisions, pooled["selected_last_rate"]),
    }
    drift = {}
    for key, (mine, theirs) in checks.items():
        matches = abs(mine - theirs) <= 1e-12 if isinstance(mine, float) else mine == theirs
        if not matches:
            drift[key] = (mine, theirs)

    per_task = {}
    for task in membership:
        cell = [r for r in rows if r["task"] == task]
        n = sum(r["teacher_decisions"] for r in cell)
        per_task[task] = {
            "episodes": len(cell),
            "teacher_decisions": n,
            "observed_agreement": sum(r["teacher_agreements"] for r in cell) / n,
            "chance_rate": sum(r["teacher_chance_sum"] for r in cell) / n,
            "observed_minus_chance_agreement": (
                sum(r["teacher_agreements"] for r in cell) - sum(r["teacher_chance_sum"] for r in cell)
            )
            / n,
            "last_label_rate": sum(r["selected_last_count"] for r in cell) / n,
            "last_label_minus_chance": (
                sum(r["selected_last_count"] for r in cell) - sum(r["teacher_chance_sum"] for r in cell)
            )
            / n,
        }

    agreement_by_task = {task: v["observed_minus_chance_agreement"] for task, v in per_task.items()}
    last_by_task = {task: v["last_label_minus_chance"] for task, v in per_task.items()}
    statistics = {
        "observed_minus_chance_agreement": {
            "task_cluster_point": mean(agreement_by_task.values()),
            "pooled_point": pooled["observed_minus_chance"],
            "task_cluster_95pct_ci_10000_seed133": bootstrap(agreement_by_task, membership),
            "per_task": {task: per_task[task]["observed_minus_chance_agreement"] for task in membership},
        },
        "last_label_minus_chance": {
            "task_cluster_point": mean(last_by_task.values()),
            "pooled_point": pooled["selected_last_rate"] - pooled["chance_first_or_last"],
            "task_cluster_95pct_ci_10000_seed133": bootstrap(last_by_task, membership),
            "per_task": {task: per_task[task]["last_label_minus_chance"] for task in membership},
        },
    }

    report = {
        "schema_version": "choice_frontier_o4_m4_task_cluster_intervals_v1",
        "issue": 134,
        "protocol": "docs/experiments/choice-frontier/issue-134-protocol.md",
        "generated_by": "scripts/analyze_choice_frontier_o4_m4_intervals.py",
        "classification": (
            "post-hoc diagnostics; M4 has diagnostic (non-confirmatory) status under the frozen "
            "#133 protocol and these intervals do not change that classification"
        ),
        "source_records": "outputs/choice-frontier/o4/metrics/all-episode-metrics.json",
        "subset": {
            "arm": ARM,
            "episodes": len(rows),
            "tasks": len(tasks),
            "algorithms": algorithms,
            "multiplier": 2,
            "seed": 17,
            "note": "the 18 stored #132 learned_adapter episodes (9 task clusters x 2 algorithms)",
        },
        "pooled_point_estimates": {
            "on_policy_decisions_k_ge_2": decisions,
            "observed_agreement": agreements / decisions,
            "chance": chance / decisions,
            "observed_minus_chance": (agreements - chance) / decisions,
            "selected_last_count": last,
            "selected_last_rate": last / decisions,
            "matches_analysis_json_m4": True,
        },
        "bootstrap": {
            "unit": "task cluster (nine tasks; both algorithms pooled inside the cluster)",
            "task_order": "choice-frontier-protocol-v1.json evaluation.membership",
            "seed": 133,
            "resamples": 10000,
            "confidence": 0.95,
            "interval": "percentile",
            "convention": "scripts/analyze_choice_frontier_o4.py bootstrap()/percentile()",
        },
        "statistics": statistics,
        "per_task": per_task,
    }

    temporary = OUTPUT_PATH.with_name(OUTPUT_PATH.name + ".partial")
    temporary.write_text(json.dumps(report, indent=1, sort_keys=False) + "\n")
    temporary.replace(OUTPUT_PATH)
    print(json.dumps(statistics, indent=1))


if __name__ == "__main__":
    main()
