#!/usr/bin/env python
"""CPU-only pre-registered #138 3-seed analysis on the frozen #135 panel.

Loads the v4 learned-adapter episodes for training seeds 29/71 (replayed by
``run_choice_frontier_v4_seeds.py finalize``), the #136 seed-17 learned episodes,
and the #135 controls (zoo), pretrained base and optimal costs, all read-only.
M1-M4 come from ``scripts/analyze_choice_frontier_v2.py`` (``inspect_episode``,
``summarize``, ``bootstrap``, ``percentile``); no formula is copied.
Protocol: ``docs/experiments/choice-frontier/issue-138-protocol.md``.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from statistics import mean, stdev

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
from scripts.analyze_choice_frontier_v3 import ratio_bootstrap, verdict, with_cost  # noqa: E402

PROTOCOL = ROOT / "configs/experiments/choice-frontier-v4/seeds-protocol.json"
MEMBERSHIP = ROOT / "configs/experiments/choice-frontier-v2/membership.json"
V2 = ROOT / "outputs/choice-frontier/v2"
V3 = ROOT / "outputs/choice-frontier/v3"
V4 = ROOT / "outputs/choice-frontier/v4/seeds"
OUT = V4 / "metrics"
BOOTSTRAP_SEED = 133
DRAWS = 10000
SEEDS = (17, 29, 71)
SEPARATION_RUNGS = {"vs_eps_0.75": "exact-eps-0.75", "vs_eps_0.50": "exact-eps-0.50"}


def save(name: str, value) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def seed_averaged_bootstrap(
    values_by_seed: dict[str, dict[str, float]], tasks: list[str], seed: int = BOOTSTRAP_SEED, draws: int = DRAWS
) -> list[float | None]:
    """Task-cluster bootstrap: resample tasks, then average the seeds inside each draw.

    Each draw takes ``len(tasks)`` tasks with replacement (the #135 ``rng.choice`` sequence),
    computes every seed's mean over the drawn tasks and averages those seed means.
    Returns the 95% percentile interval with the #135 percentile convention.
    """

    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        drawn = [rng.choice(tasks) for _ in tasks]
        samples.append(mean(mean(values[t] for t in drawn) for values in values_by_seed.values()))
    samples.sort()
    return [percentile(samples, 0.025), percentile(samples, 0.975)]


def separation_verdict(lo: float, hi: float) -> str:
    if lo > 0:
        return "SEPARATED_ABOVE"
    if hi < 0:
        return "SEPARATED_BELOW"
    return "NOT_SEPARATED"


def point(values_by_seed: dict[str, dict[str, float]], tasks: list[str]) -> float:
    return mean(mean(values[t] for t in tasks) for values in values_by_seed.values())


def learned_rows_from(root: Path, authorities, ref, optimal, training_seeds: set[int]) -> tuple[dict, dict]:
    evaluation = load(root / "evaluation/evaluation.json")
    if not evaluation["complete"] or evaluation["missing_bindings"] or evaluation["replay_mismatches"]:
        raise ValueError(f"{root} evaluation is not complete with 0 missing and 0 mismatches")
    rows: dict[int, list[dict]] = {}
    for binding in load(root / "evaluation/bindings.json")["bindings"]:
        if binding["training_seed"] not in training_seeds:
            continue
        name = f"{binding['algorithm']}-{binding['condition']}-s{binding['training_seed']}-{binding['seed']}.json.gz"
        episode = load(root / "evaluation/episodes" / binding["task_id"].replace("/", "__") / name)
        if (episode["task_id"], episode["algorithm"], episode["training_seed"]) != (
            binding["task_id"], binding["algorithm"], binding["training_seed"]
        ):
            raise ValueError("learned episode identity differs from its binding")
        row = inspect_episode(episode, authorities[binding["task_id"]], ref(binding), "learned_adapter", 2)
        row["training_seed"] = binding["training_seed"]
        rows.setdefault(binding["training_seed"], []).append(with_cost(row, optimal))
    return rows, evaluation


def main() -> None:
    protocol = load(PROTOCOL)
    membership = load(MEMBERSHIP)
    if membership["membership_sha256"] != protocol["evaluation"]["membership_sha256"]:
        raise ValueError("#135 membership_sha256 differs from the frozen #138 protocol")
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

    # #135 controls and ladder rungs (read-only zoo) and pretrained base (read-only evaluation).
    control_arms = ("exact_reference", "exact-eps-0.50", "exact-eps-0.75", "random_valid")
    zoo = load(V2 / "zoo/manifest.json")
    if not zoo["complete"]:
        raise ValueError("#135 zoo is incomplete")
    control_rows = []
    for binding in zoo["bindings"]:
        if binding["arm"] not in control_arms:
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
    controls = summarize(control_rows + base_rows, tasks, (*control_arms, "pretrained_base"))
    frozen = load(V2 / "metrics/analysis.json")
    for arm in control_arms:
        for task in tasks:
            if abs(controls[arm]["per_task"][task]["auc"] - frozen["arms"][arm]["per_task"][task]["auc"]) > 1e-12:
                raise ValueError(f"recomputed #135 {arm} M1 differs from the frozen analysis: {task}")

    # Learned episodes: seed 17 from #136 (read-only), seeds 29/71 from v4.
    rows17, evaluation17 = learned_rows_from(V3, authorities, ref, optimal, {17})
    rows_new, evaluation_new = learned_rows_from(V4, authorities, ref, optimal, set(protocol["training_seeds"]))
    learned_rows = {**rows17, **rows_new}
    if sorted(learned_rows) != list(SEEDS):
        raise ValueError(f"learned seeds differ from {SEEDS}: {sorted(learned_rows)}")
    learned = {s: summarize(rows, tasks, ("learned_adapter",))["learned_adapter"] for s, rows in learned_rows.items()}
    for seed, summary in learned.items():
        if summary.get("tasks_present") != len(tasks):
            raise ValueError(f"seed {seed} learned episodes do not cover every panel task")
    frozen136 = load(V3 / "metrics/analysis.json")
    for task in tasks:
        if abs(learned[17]["per_task"][task]["auc"] - frozen136["per_seed"]["17"]["per_task"][task]["auc"]) > 1e-12:
            raise ValueError(f"recomputed #136 seed-17 M1 differs from the frozen analysis: {task}")

    m1 = {str(s): {t: learned[s]["per_task"][t]["auc"] for t in tasks} for s in SEEDS}
    rung = {arm: {t: controls[arm]["per_task"][t]["auc"] for t in tasks} for arm in control_arms}
    bootstrap_spec = {"unit": "task cluster", "seed": BOOTSTRAP_SEED, "draws": DRAWS, "interval": "95% percentile",
                      "within_draw": "resample tasks; average the seeds inside each draw"}

    def contrast(reference: dict[str, float]) -> tuple[dict, float, list, dict]:
        values = {s: {t: m1[s][t] - reference[t] for t in tasks} for s in m1}
        per_seed_points = {s: mean(v.values()) for s, v in values.items()}
        return values, point(values, tasks), seed_averaged_bootstrap(values, tasks), per_seed_points

    margins = {
        "materiality_margin": protocol["analysis"]["materiality_margin"],
        "equivalence_margin": protocol["analysis"]["equivalence_margin"],
    }
    d_values, d3, d_ci, d_points = contrast(rung["random_valid"])
    primary = {
        "estimand": protocol["analysis"]["primary"],
        "D3": d3,
        "ci95": d_ci,
        "per_seed": d_points,
        "per_seed_ci95": {s: bootstrap(v, tasks) for s, v in d_values.items()},
        "per_task_difference_seed_mean": {t: mean(d_values[s][t] for s in d_values) for t in tasks},
        "m1_learned_3seed_mean": point(m1, tasks),
        "m1_learned_3seed_mean_ci95": seed_averaged_bootstrap(m1, tasks),
        "m1_random_valid": controls["random_valid"]["m1_auc"],
        "seeds": list(SEEDS),
        "bootstrap": bootstrap_spec,
        **margins,
        "rule": protocol["analysis"]["decision_rule"],
        "verdict": verdict(d3, d_ci[0], d_ci[1], d_points, margins),
    }

    separation = {}
    for key, arm in SEPARATION_RUNGS.items():
        values, s_point, s_ci, s_points = contrast(rung[arm])
        separation[key] = {
            "rung": arm,
            "m1_rung_5seed_mean": controls[arm]["m1_auc"],
            "S": s_point,
            "ci95": s_ci,
            "per_seed": s_points,
            "per_task_difference_seed_mean": {t: mean(values[s][t] for s in values) for t in tasks},
            "bootstrap": {**bootstrap_spec, "paired": True},
            "verdict": separation_verdict(s_ci[0], s_ci[1]),
            "role": "co-primary (pre-registered)" if arm == "exact-eps-0.75" else "descriptive only",
        }

    per_seed = {}
    for seed in SEEDS:
        summary = learned[seed]
        rows = learned_rows[seed]
        numerators = {t: sum(r["teacher_agreements"] - r["teacher_chance_sum"] for r in rows if r["task"] == t)
                      for t in tasks}
        denominators = {t: sum(r["teacher_decisions"] for r in rows if r["task"] == t) for t in tasks}
        m4 = summary["m4_teacher_agreement"]
        per_seed[str(seed)] = {
            "source": "outputs/choice-frontier/v3 (#136, reused)" if seed == 17 else "outputs/choice-frontier/v4/seeds",
            "m1_auc": summary["m1_auc"],
            "ci95": summary["m1_task_cluster_95pct_ci_10000_seed133"],
            "m1_minus_random_valid": d_points[str(seed)],
            "m1_minus_random_valid_ci95": primary["per_seed_ci95"][str(seed)],
            "m1_minus_eps_0_75": separation["vs_eps_0.75"]["per_seed"][str(seed)],
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
    seed_m1 = [per_seed[str(s)]["m1_auc"] for s in SEEDS]
    seed_variance = {
        "m1_per_seed": {str(s): {"m1_auc": per_seed[str(s)]["m1_auc"], "ci95": per_seed[str(s)]["ci95"]} for s in SEEDS},
        "teacher_agreement_minus_chance_per_seed": {
            str(s): {
                "value": per_seed[str(s)]["teacher_agreement_minus_chance"],
                "ci95": per_seed[str(s)]["teacher_agreement_minus_chance_ci95"],
            }
            for s in SEEDS
        },
        "last_label_rate_per_seed": {str(s): per_seed[str(s)]["last_label_rate"] for s in SEEDS},
        "m1_mean": mean(seed_m1),
        "m1_between_seed_sd": stdev(seed_m1),
        "m1_range": [min(seed_m1), max(seed_m1)],
        "sd_definition": "statistics.stdev (n-1) over the 3 seed M1 values",
    }

    ladder = {arm: frozen["arms"][arm]["m1_auc"] for arm in LADDER}

    def position(value: float) -> dict:
        beaten = [arm for arm in LADDER if ladder[arm] <= value]
        higher = [arm for arm in LADDER if ladder[arm] > value]
        return {
            "learned_m1": value,
            "next_higher_rung": higher[-1] if higher else None,
            "next_lower_or_equal_rung": beaten[0] if beaten else None,
        }

    ladder_position = {
        "ladder_m1_135": ladder,
        "learned_3seed_mean": position(primary["m1_learned_3seed_mean"]),
        "learned": {str(s): position(per_seed[str(s)]["m1_auc"]) for s in SEEDS},
    }
    report = {
        "status": "pre-registered #138 3-seed analysis (issue-138-protocol.md)",
        "membership_sha256": membership["membership_sha256"],
        "reused": {
            "controls_135": "outputs/choice-frontier/v2/zoo (exact_reference, exact-eps-0.50/0.75, random_valid)",
            "pretrained_base_135": "outputs/choice-frontier/v2/evaluation",
            "optimal_costs_135": "outputs/choice-frontier/v2/metrics/optimal-costs.json",
            "learned_seed_17_136": "outputs/choice-frontier/v3/evaluation",
            "recomputed_control_m1_matches_frozen_135": True,
            "recomputed_seed_17_m1_matches_frozen_136": True,
        },
        "episode_accounting": {
            "learned_episodes": {str(s): len(learned_rows[s]) for s in SEEDS},
            "v4_replayed": evaluation_new["episodes_replayed"],
            "v4_missing": evaluation_new["missing_bindings"],
            "v4_replay_mismatches": evaluation_new["replay_mismatches"],
            "v3_seed_17_replayed": evaluation17["episodes_replayed"],
        },
        "primary": primary,
        "separation": separation,
        "per_seed": per_seed,
        "seed_variance": seed_variance,
        "ladder_position": ladder_position,
        "controls_135": {
            arm: {"m1_auc": controls[arm]["m1_auc"], "ci95": controls[arm]["m1_task_cluster_95pct_ci_10000_seed133"]}
            for arm in (*control_arms, "pretrained_base")
        },
        "interpretation": (
            "development-stage, one panel (12 tasks, 7 domains); controls and base reused from #135, seed-17 "
            "learned episodes reused from #136; M2/M3 condition on solving"
        ),
    }
    save("all-episode-metrics.json", {"records": [r for s in SEEDS for r in learned_rows[s]]})
    save("analysis.json", report)
    print(json.dumps({k: primary[k] for k in ("D3", "ci95", "per_seed", "verdict")}, indent=2))
    print(json.dumps({k: {x: v[x] for x in ("S", "ci95", "per_seed", "verdict")} for k, v in separation.items()},
                     indent=2))
    print(json.dumps({k: v for k, v in seed_variance.items() if k != "sd_definition"}, indent=2))


if __name__ == "__main__":
    main()
