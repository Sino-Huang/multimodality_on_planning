#!/usr/bin/env python
"""CPU-only pre-registered #136 endpoint analysis on the frozen #135 panel.

Loads the v3 learned-adapter episodes (replayed by ``run_choice_frontier_v3.py
finalize``), the #135 control (zoo) and pretrained-base episodes read-only, and
the #135 ``optimal-costs.json``. M1-M4 come from ``scripts/analyze_choice_frontier_v2.py``
(``inspect_episode``, ``summarize``, ``bootstrap``); no formula is copied.
Protocol: ``docs/experiments/choice-frontier/issue-136-protocol.md``.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority  # noqa: E402
from scripts.analyze_choice_frontier_v2 import (  # noqa: E402
    LADDER,
    bootstrap,
    inspect_episode,
    load,
    percentile,
    summarize,
)

PROTOCOL = ROOT / "configs/experiments/choice-frontier-v3/protocol.json"
MEMBERSHIP = ROOT / "configs/experiments/choice-frontier-v2/membership.json"
V2 = ROOT / "outputs/choice-frontier/v2"
V3 = ROOT / "outputs/choice-frontier/v3"
OUT = V3 / "metrics"
BOOTSTRAP_SEED = 133
DRAWS = 10000


def save(name: str, value) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def with_cost(row: dict, optimal: dict) -> dict:
    row["c_star"] = optimal[row["task"]]["cost"]
    row["kappa"] = row["cost"] / row["c_star"] if row["cost"] is not None else None
    return row


def ratio_bootstrap(numerators: dict, denominators: dict, tasks: list[str]) -> list[float | None]:
    """Task-cluster bootstrap of sum(numerator) / sum(denominator), Random(133), 10,000 draws."""

    rng = random.Random(BOOTSTRAP_SEED)
    samples = []
    for _ in range(DRAWS):
        drawn = [rng.choice(tasks) for _ in tasks]
        total = sum(denominators[t] for t in drawn)
        if total:
            samples.append(sum(numerators[t] for t in drawn) / total)
    samples.sort()
    return [percentile(samples, 0.025), percentile(samples, 0.975)]


def verdict(d: float, lo: float, hi: float, per_seed: dict[str, float], margins: dict) -> str:
    delta = margins["materiality_margin"]
    equivalence = margins["equivalence_margin"]
    if lo > 0 and d >= delta and all(value > 0 for value in per_seed.values()):
        return "POSITIVE"
    if -equivalence < lo and hi < equivalence:
        return "EQUIVALENT"
    if hi < 0:
        return "NEGATIVE"
    return "INCONCLUSIVE"


def main() -> None:
    protocol = load(PROTOCOL)
    membership = load(MEMBERSHIP)
    if membership["membership_sha256"] != protocol["evaluation"]["membership_sha256"]:
        raise ValueError("#135 membership_sha256 differs from the frozen #136 protocol")
    tasks = membership["task_ids"]
    rows_by_id = {task["row"]["task_id"]: task["row"] for task in membership["tasks"]}
    optimal = load(V2 / "metrics/optimal-costs.json")
    authorities = {}
    for task in tasks:
        snapshot = load(ROOT / rows_by_id[task]["task_path"])
        authorities[task] = PDDLStateAuthority.from_pddl(snapshot["domain_pddl"], snapshot["problem_pddl"])
        if optimal[task]["cost"] != membership["per_task"][task]["cstar"]:
            raise ValueError("#135 optimal cost differs from the frozen C*")

    def ref(binding: dict) -> int:
        """R_t: the #135 uncapped exact_reference expansion count for the binding's cell."""

        return rows_by_id[binding["task_id"]]["reference_costs"][binding["algorithm"]]["expansions"]

    # #135 controls (read-only zoo) and pretrained base (read-only evaluation).
    zoo = load(V2 / "zoo/manifest.json")
    if not zoo["complete"]:
        raise ValueError("#135 zoo is incomplete")
    control_rows = []
    for binding in zoo["bindings"]:
        if binding["arm"] not in ("random_valid", "exact_reference"):
            continue
        if binding["status"] != "observed" or binding["replay_status"] != "passed":
            raise ValueError("#135 control episode is not observed and replayed")
        episode = load(ROOT / binding["episode_path"])
        row = inspect_episode(episode, authorities[binding["task_id"]], ref(binding), binding["arm"], 2)
        control_rows.append(with_cost(row, optimal))
    base_rows = []
    for binding in load(V2 / "evaluation/bindings.json")["bindings"]:
        if binding["condition"] != "pretrained_base":
            continue
        name = f"{binding['algorithm']}-{binding['condition']}-{binding['seed']}.json.gz"
        episode = load(V2 / "evaluation/episodes" / binding["task_id"].replace("/", "__") / name)
        row = inspect_episode(episode, authorities[binding["task_id"]], ref(binding), "pretrained_base", 2)
        base_rows.append(with_cost(row, optimal))
    controls = summarize(control_rows + base_rows, tasks, ("exact_reference", "random_valid", "pretrained_base"))
    frozen = load(V2 / "metrics/analysis.json")
    for arm in ("exact_reference", "random_valid"):
        for task in tasks:
            if abs(controls[arm]["per_task"][task]["auc"] - frozen["arms"][arm]["per_task"][task]["auc"]) > 1e-12:
                raise ValueError(f"recomputed #135 {arm} M1 differs from the frozen analysis: {task}")

    # v3 learned episodes (every one independently replayed at finalize).
    evaluation = load(V3 / "evaluation/evaluation.json")
    if not evaluation["complete"] or evaluation["missing_bindings"] or evaluation["replay_mismatches"]:
        raise ValueError("v3 evaluation is not complete with 0 missing and 0 mismatches")
    bindings = load(V3 / "evaluation/bindings.json")["bindings"]
    seeds = sorted({b["training_seed"] for b in bindings})
    learned_rows: dict[int, list[dict]] = {seed: [] for seed in seeds}
    for binding in bindings:
        name = f"{binding['algorithm']}-{binding['condition']}-s{binding['training_seed']}-{binding['seed']}.json.gz"
        episode = load(V3 / "evaluation/episodes" / binding["task_id"].replace("/", "__") / name)
        if (episode["task_id"], episode["algorithm"], episode["training_seed"]) != (
            binding["task_id"], binding["algorithm"], binding["training_seed"]
        ):
            raise ValueError("v3 episode identity differs from its binding")
        row = inspect_episode(episode, authorities[binding["task_id"]], ref(binding), "learned_adapter", 2)
        row["training_seed"] = binding["training_seed"]
        learned_rows[binding["training_seed"]].append(with_cost(row, optimal))
    learned = {s: summarize(rows, tasks, ("learned_adapter",))["learned_adapter"] for s, rows in learned_rows.items()}
    for seed, summary in learned.items():
        if summary["tasks_present"] != len(tasks):
            raise ValueError(f"seed {seed} learned episodes do not cover every panel task")

    random_task = {t: controls["random_valid"]["per_task"][t]["auc"] for t in tasks}
    per_seed_difference = {
        str(seed): {t: learned[seed]["per_task"][t]["auc"] - random_task[t] for t in tasks} for seed in seeds
    }
    per_task_d = {t: mean(per_seed_difference[str(seed)][t] for seed in seeds) for t in tasks}
    d = mean(per_task_d.values())
    ci = bootstrap(per_task_d, tasks)
    seed_points = {seed: mean(values.values()) for seed, values in per_seed_difference.items()}
    margins = {
        "materiality_margin": protocol["analysis"]["materiality_margin"],
        "equivalence_margin": protocol["analysis"]["equivalence_margin"],
    }
    primary = {
        "estimand": protocol["analysis"]["primary"],
        "D": d,
        "ci95": ci,
        "per_seed_points": seed_points,
        "per_task_difference": per_task_d,
        "m1_random_valid": controls["random_valid"]["m1_auc"],
        "seeds": seeds,
        "bootstrap": {"unit": "task cluster", "seed": BOOTSTRAP_SEED, "draws": DRAWS, "interval": "95% percentile",
                      "within_draw": "average over seeds present"},
        **margins,
        "rule": protocol["analysis"]["decision_rule"],
        "verdict": verdict(d, ci[0], ci[1], seed_points, margins),
    }

    per_seed = {}
    for seed in seeds:
        summary = learned[seed]
        rows = learned_rows[seed]
        numerators = {t: sum(r["teacher_agreements"] - r["teacher_chance_sum"] for r in rows if r["task"] == t)
                      for t in tasks}
        denominators = {t: sum(r["teacher_decisions"] for r in rows if r["task"] == t) for t in tasks}
        m4 = summary["m4_teacher_agreement"]
        per_seed[str(seed)] = {
            "m1_auc": summary["m1_auc"],
            "ci95": summary["m1_task_cluster_95pct_ci_10000_seed133"],
            "m1_minus_random_valid": seed_points[str(seed)],
            "m1_minus_random_valid_ci95": bootstrap(per_seed_difference[str(seed)], tasks),
            "teacher_agreement_minus_chance": m4["observed_minus_chance"],
            "teacher_agreement_minus_chance_ci95": ratio_bootstrap(numerators, denominators, tasks),
            "teacher_agreement_observed": m4["observed"],
            "teacher_agreement_chance": m4["chance"],
            "on_policy_decisions_k_ge_2": m4["on_policy_decisions_k_ge_2"],
            "last_label_rate": m4["selected_last_rate"],
            "first_label_rate": m4["selected_first_rate"],
            "solved_at_2": summary["m3_solved_coverage"],
            "m2_solved_only_geometric_rho": summary["m2_solved_only_geometric_rho_task_weighted"],
            "m3_solved_kappa": summary["m3_solved_kappa_mean_task_weighted"],
            "per_task": summary["per_task"],
        }

    ladder = {arm: frozen["arms"][arm]["m1_auc"] for arm in LADDER}
    ladder_position = {}
    for seed in seeds:
        value = learned[seed]["m1_auc"]
        beaten = [arm for arm in LADDER if ladder[arm] <= value]
        higher = [arm for arm in LADDER if ladder[arm] > value]
        ladder_position[str(seed)] = {
            "learned_m1": value,
            "next_higher_rung": higher[-1] if higher else None,
            "next_lower_or_equal_rung": beaten[0] if beaten else None,
        }
    report = {
        "status": "pre-registered #136 endpoint analysis (issue-136-protocol.md)",
        "membership_sha256": membership["membership_sha256"],
        "reused_from_135": {
            "controls": "outputs/choice-frontier/v2/zoo (exact_reference, random_valid)",
            "pretrained_base": "outputs/choice-frontier/v2/evaluation",
            "optimal_costs": "outputs/choice-frontier/v2/metrics/optimal-costs.json",
            "recomputed_control_m1_matches_frozen_135": True,
        },
        "episode_accounting": {
            "learned_episodes": sum(len(rows) for rows in learned_rows.values()),
            "replayed": evaluation["episodes_replayed"],
            "missing": evaluation["missing_bindings"],
            "replay_mismatches": evaluation["replay_mismatches"],
        },
        "primary": primary,
        "per_seed": per_seed,
        "ladder_position": {"ladder_m1_135": ladder, "learned": ladder_position},
        "controls_135": {
            arm: {"m1_auc": controls[arm]["m1_auc"], "ci95": controls[arm]["m1_task_cluster_95pct_ci_10000_seed133"]}
            for arm in ("exact_reference", "random_valid", "pretrained_base")
        },
        "interpretation": (
            "development-stage, one panel (12 tasks, 7 domains); controls and base reused from #135; "
            "M2/M3 condition on solving"
        ),
    }
    save("all-episode-metrics.json", {"records": [r for rows in learned_rows.values() for r in rows]})
    save("analysis.json", report)
    print(json.dumps({k: primary[k] for k in ("D", "ci95", "per_seed_points", "verdict")}, indent=2))
    print(json.dumps({s: {k: v for k, v in p.items() if k != "per_task"} for s, p in per_seed.items()}, indent=2))


if __name__ == "__main__":
    main()
