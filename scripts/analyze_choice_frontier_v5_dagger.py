#!/usr/bin/env python
"""CPU-only pre-registered #140 DAgger analysis: pooled #135 panel (12) + #139 P2 (11).

docs/experiments/choice-frontier/issue-140-protocol.md. Metric functions are imported,
not copied: M1-M4 and the task-cluster bootstrap from
``scripts/analyze_choice_frontier_v2.py``; the in-draw seed-averaged bootstrap and the
separation rule from ``scripts/analyze_choice_frontier_v4_seeds.py``; the panel loaders
(controls, ladder, pre-DAgger learned episodes) and the #138 D3 rule from
``scripts/analyze_choice_frontier_v4_panels.py``. Output:
``outputs/choice-frontier/v5/metrics/analysis.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority  # noqa: E402
from scripts.analyze_choice_frontier_v2 import LADDER, bootstrap, load, shortest_plan, summarize  # noqa: E402
from scripts.analyze_choice_frontier_v4_panels import (  # noqa: E402
    endpoint,
    learned_m1,
    model_rows,
    panel_data,
    task_m1,
    v3_name,
)
from scripts.analyze_choice_frontier_v4_seeds import point, seed_averaged_bootstrap, separation_verdict  # noqa: E402

PROTOCOL = ROOT / "configs/experiments/choice-frontier-v5/protocol.json"
MEMBERSHIP = ROOT / "configs/experiments/choice-frontier-v5/membership.json"
V2 = ROOT / "outputs/choice-frontier/v2"
V5 = ROOT / "outputs/choice-frontier/v5"
OUT = V5 / "metrics"
SEEDS = (17, 29, 71)
PANELS = {"v2": "p135", "p2": "p2"}
EQUIVALENCE_MARGIN = 0.05
BOOTSTRAP = {"unit": "task cluster", "seed": 133, "draws": 10000, "interval": "95% percentile",
             "within_draw": "resample tasks with replacement; average the seeds inside each draw", "paired": True}


def save(name: str, value) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def primary_verdict(lo: float, hi: float, smoke_gate: str = "PASS") -> str:
    if smoke_gate != "PASS":
        return "SMOKE_FAIL"
    return separation_verdict(lo, hi)


def co_primary_verdict(lo: float, hi: float, margin: float = EQUIVALENCE_MARGIN) -> str:
    """IMPROVED, EQUIVALENT, WORSE, INCONCLUSIVE — evaluated in that order."""

    if lo > 0:
        return "IMPROVED"
    if -margin < lo and hi < margin:
        return "EQUIVALENT"
    if hi < 0:
        return "WORSE"
    return "INCONCLUSIVE"


def contrast(values: dict[str, dict[str, float]], reference, tasks: list[str]) -> dict:
    """Seed-mean of M1(DAgger, s) - reference; ``reference`` is per task, or per seed and task (paired)."""

    diff = {
        s: {t: v[t] - (reference[s][t] if s in reference else reference[t]) for t in tasks} for s, v in values.items()
    }
    ci = seed_averaged_bootstrap(diff, tasks)
    return {
        "point": point(diff, tasks),
        "ci95": ci,
        "per_seed": {s: mean(d.values()) for s, d in diff.items()},
        "per_seed_ci95": {s: bootstrap(d, tasks) for s, d in diff.items()},
        "per_task_seed_mean": {t: mean(diff[s][t] for s in diff) for t in tasks},
        "tasks": len(tasks),
        "bootstrap": BOOTSTRAP,
    }


def panel_context(name: str, data: dict) -> tuple[dict, dict]:
    """PDDL authorities and C* per task, recomputed exactly as the #139 analyzer does."""

    membership = data["membership"]
    authorities, optimal = {}, {}
    frozen_optimal = load(V2 / "metrics/optimal-costs.json") if name == "p135" else None
    for task in membership["tasks"]:
        task_id = task["row"]["task_id"]
        if frozen_optimal is None:
            plan, authorities[task_id] = shortest_plan(task)
            optimal[task_id] = plan["cost"]
        else:
            snapshot = load(ROOT / task["row"]["task_path"])
            authorities[task_id] = PDDLStateAuthority.from_pddl(snapshot["domain_pddl"], snapshot["problem_pddl"])
            optimal[task_id] = frozen_optimal[task_id]["cost"]
        if optimal[task_id] != membership["per_task"][task_id]["cstar"]:
            raise ValueError(f"optimal cost differs from the frozen C*: {task_id}")
    return authorities, optimal


def dagger_panel(panel: str, data: dict) -> dict:
    authorities, optimal = panel_context(PANELS[panel], data)
    refs = {t["row"]["task_id"]: t["row"]["reference_costs"] for t in data["membership"]["tasks"]}
    tasks = data["tasks"]
    rows = model_rows(V5 / "evaluation" / panel / "evaluation", v3_name, authorities, refs, optimal, tasks)
    for row in rows:
        if row["arm"] != "learned_adapter":
            raise ValueError("unexpected condition among DAgger episodes")
    per_seed = {s: summarize([r for r in rows if r["training_seed"] == s], tasks, ("learned_adapter",))
                ["learned_adapter"] for s in SEEDS}
    for seed, summary in per_seed.items():
        if summary.get("tasks_present") != len(tasks):
            raise ValueError(f"{panel} DAgger seed {seed} does not cover every task")
    return {"rows": rows, "per_seed": per_seed}


def seed_stats(summary: dict, tasks: list[str]) -> dict:
    m4 = summary["m4_teacher_agreement"]
    return {
        "m1_auc": summary["m1_auc"],
        "ci95": bootstrap({t: summary["per_task"][t]["auc"] for t in tasks}, tasks),
        "teacher_agreement_minus_chance": m4["observed_minus_chance"],
        "teacher_agreement_observed": m4["observed"],
        "teacher_agreement_chance": m4["chance"],
        "on_policy_decisions_k_ge_2": m4["on_policy_decisions_k_ge_2"],
        "last_label_rate": m4["selected_last_rate"],
        "first_label_rate": m4["selected_first_rate"],
        "solved_at_2": summary["m3_solved_coverage"],
    }


def ladder_position(arms: dict, value: float) -> dict:
    ladder = {arm: arms[arm]["m1_auc"] for arm in LADDER}
    beaten = [arm for arm in LADDER if ladder[arm] <= value]
    higher = [arm for arm in LADDER if ladder[arm] > value]
    return {"ladder_m1": ladder, "dagger_m1": value, "next_higher_rung": higher[-1] if higher else None,
            "next_lower_or_equal_rung": beaten[0] if beaten else None}


def collection_block() -> dict:
    membership = load(MEMBERSHIP)
    audit = load(V5 / "collection/audit.json")
    cells = {}
    for key, cell in membership["cells"].items():
        algorithm, seed = cell["algorithm"], cell["training_seed"]
        episodes = [load(V5 / "collection/episodes" / t.replace("/", "__") / f"{algorithm}-s{seed}.json.gz")
                    for t in cell["tasks"]]
        decisions = [d for e in episodes for d in e["decisions"]]
        eligible = [d for e in episodes for d, ev in zip(e["decisions"], e["events"], strict=True)
                    if len(ev["menu"]) >= 2]
        terminations: dict[str, int] = {}
        for e in episodes:
            terminations[e["termination_reason"]] = terminations.get(e["termination_reason"], 0) + 1
        audited = next(c for c in audit["cells"] if c["algorithm"] == algorithm and c["training_seed"] == seed)
        cells[key] = {
            "episodes": len(episodes),
            "tasks_walked": len(cell["tasks"]),
            "model_calls": len(decisions),
            "on_policy_records": cell["on_policy_records"],
            "replay_records": cell["replay_records"],
            "samples": cell["samples"],
            "agreement_rate_used_records": cell["on_policy_agreement_rate"],
            "agreement_rate_all_k_ge_2_decisions": sum(d["agree"] for d in eligible) / len(eligible),
            "chance_all_k_ge_2_decisions": mean(1 / len(ev["menu"]) for e in episodes for ev in e["events"]
                                                if len(ev["menu"]) >= 2),
            "goal_reached_episodes": terminations.get("goal_reached", 0),
            "terminations": terminations,
            "walk_exhausted": audited["walk_exhausted"],
            "replayed": audited["episodes_replayed"],
            "replay_mismatches": len(audited["replay_mismatches"]),
        }
    return {"membership_sha256": membership["membership_sha256"], "audit_ok": audit["ok"], "cells": cells}


def main() -> None:
    protocol = load(PROTOCOL)
    smoke = load(V5 / "smoke/smoke.json")["gate"]
    datasets, dagger = {}, {}
    for panel, name in PANELS.items():
        data = panel_data(name)
        if data["membership"]["membership_sha256"] != protocol["evaluation"]["panels"][panel]["membership_sha256"]:
            raise ValueError(f"{panel} membership differs from the frozen v5 protocol")
        if data["seeds"] != list(SEEDS):
            raise ValueError(f"{panel} pre-DAgger seeds are {data['seeds']}, not {SEEDS}")
        datasets[panel] = data
        if smoke == "PASS":
            dagger[panel] = dagger_panel(panel, data)
    if smoke != "PASS":
        report = {"status": "pre-registered #140 analysis", "smoke_gate": smoke,
                  "primary": {"verdict": "SMOKE_FAIL"}, "co_primary": {"verdict": "SMOKE_FAIL"},
                  "collection": collection_block()}
        save("analysis.json", report)
        print(json.dumps(report["primary"], indent=2))
        return

    def values(panels):
        tasks = [t for p in panels for t in datasets[p]["tasks"]]
        if len(set(tasks)) != len(tasks):
            raise ValueError("panels share a task id")
        dag = {str(s): {t: v for p in panels for t, v in task_m1(dagger[p]["per_seed"][s]).items()} for s in SEEDS}
        pre = {str(s): {t: v for p in panels for t, v in learned_m1(datasets[p])[s].items()} for s in SEEDS}
        eps = {t: v for p in panels for t, v in task_m1(datasets[p]["arms"]["exact-eps-0.75"]).items()}
        rnd = {t: v for p in panels for t, v in task_m1(datasets[p]["arms"]["random_valid"]).items()}
        return tasks, dag, pre, eps, rnd

    tasks, dag, pre, eps, _rnd = values(list(PANELS))
    s_pool = contrast(dag, eps, tasks)
    d_pool = contrast(dag, pre, tasks)
    primary = {
        "estimand": protocol["analysis"]["primary"]["estimand"],
        "S_pool": s_pool["point"],
        "ci95": s_pool["ci95"],
        "per_seed": s_pool["per_seed"],
        "per_seed_ci95": s_pool["per_seed_ci95"],
        "per_task_difference_seed_mean": s_pool["per_task_seed_mean"],
        "m1_dagger_3seed_mean": point(dag, tasks),
        "m1_dagger_3seed_mean_ci95": seed_averaged_bootstrap(dag, tasks),
        "m1_eps_0_75_5seed_mean": mean(eps.values()),
        "tasks": len(tasks),
        "panels": {p: len(datasets[p]["tasks"]) for p in PANELS},
        "bootstrap": BOOTSTRAP,
        "rule": protocol["analysis"]["primary"]["decision_rule"],
        "smoke_gate": smoke,
        "verdict": primary_verdict(s_pool["ci95"][0], s_pool["ci95"][1], smoke),
    }
    co_primary = {
        "estimand": protocol["analysis"]["co_primary"]["estimand"],
        "delta_pool": d_pool["point"],
        "ci95": d_pool["ci95"],
        "per_seed": d_pool["per_seed"],
        "per_seed_ci95": d_pool["per_seed_ci95"],
        "per_task_difference_seed_mean": d_pool["per_task_seed_mean"],
        "m1_pre_dagger_3seed_mean": point(pre, tasks),
        "bootstrap": BOOTSTRAP,
        "equivalence_margin": EQUIVALENCE_MARGIN,
        "rule": protocol["analysis"]["co_primary"]["decision_rule"],
        "verdict": co_primary_verdict(d_pool["ci95"][0], d_pool["ci95"][1]),
    }

    per_panel, per_seed, ladder = {}, {}, {}
    for panel in PANELS:
        p_tasks, p_dag, p_pre, p_eps, p_rnd = values([panel])
        s = contrast(p_dag, p_eps, p_tasks)
        d = contrast(p_dag, p_pre, p_tasks)
        d3 = endpoint({int(k): v for k, v in p_dag.items()}, p_rnd, p_tasks)
        per_panel[panel] = {
            "tasks": len(p_tasks),
            "S": s["point"], "S_ci95": s["ci95"], "S_per_seed": s["per_seed"],
            "S_verdict_rule_applied": separation_verdict(*s["ci95"]),
            "delta": d["point"], "delta_ci95": d["ci95"], "delta_per_seed": d["per_seed"],
            "delta_verdict_rule_applied": co_primary_verdict(*d["ci95"]),
            "D3": d3["D3"], "D3_ci95": d3["ci95"], "D3_per_seed": d3["per_seed"], "D3_verdict_138_rule": d3["verdict"],
            "m1_dagger_3seed_mean": point(p_dag, p_tasks),
            "m1_pre_dagger_3seed_mean": point(p_pre, p_tasks),
            "m1_eps_0_75": mean(p_eps.values()),
            "m1_random_valid": mean(p_rnd.values()),
            "status": "descriptive (secondary)",
        }
        per_seed[panel] = {
            str(seed): {
                "dagger": seed_stats(dagger[panel]["per_seed"][seed], p_tasks),
                "pre_dagger": seed_stats(datasets[panel]["per_seed"][seed], p_tasks),
            }
            for seed in SEEDS
        }
        ladder[panel] = {
            "dagger_3seed_mean": ladder_position(datasets[panel]["arms"], per_panel[panel]["m1_dagger_3seed_mean"]),
            "pre_dagger_3seed_mean": ladder_position(datasets[panel]["arms"],
                                                     per_panel[panel]["m1_pre_dagger_3seed_mean"]),
            "dagger_per_seed": {str(s): ladder_position(datasets[panel]["arms"],
                                                        dagger[panel]["per_seed"][s]["m1_auc"]) for s in SEEDS},
        }
    per_seed["pooled"] = {
        str(seed): {
            "dagger_m1": mean(dag[str(seed)].values()),
            "dagger_m1_ci95": bootstrap(dag[str(seed)], tasks),
            "pre_dagger_m1": mean(pre[str(seed)].values()),
            "S": s_pool["per_seed"][str(seed)],
            "delta": d_pool["per_seed"][str(seed)],
        }
        for seed in SEEDS
    }
    report = {
        "status": "pre-registered #140 analysis (issue-140-protocol.md)",
        "memberships": {p: datasets[p]["membership"]["membership_sha256"] for p in PANELS},
        "reused": {
            "pre_dagger_v2": "outputs/choice-frontier/v3/evaluation (s17) + outputs/choice-frontier/v4/seeds/evaluation",
            "pre_dagger_p2": "outputs/choice-frontier/v4/panels/p2/evaluation",
            "controls_v2": "outputs/choice-frontier/v2/zoo",
            "controls_p2": "outputs/choice-frontier/v4/panels/p2/zoo",
        },
        "episode_accounting": {p: {"dagger_episodes": len(dagger[p]["rows"]),
                                   "evaluation": load(V5 / "evaluation" / p / "evaluation/evaluation.json")}
                               for p in PANELS},
        "primary": primary,
        "co_primary": co_primary,
        "per_panel": per_panel,
        "per_seed": per_seed,
        "collection": collection_block(),
        "ladder_position": ladder,
        "interpretation": ("M1 = trapezoidal solve-versus-budget AUC (#135); paired task-cluster bootstrap "
                           "Random(133), 10,000 draws, seeds averaged inside each draw; the teacher (exact heap "
                           "head) and exact-eps read privileged h_add information"),
    }
    save("analysis.json", report)
    save("dagger-episode-metrics.json", {p: dagger[p]["rows"] for p in PANELS})
    brief = {
        "primary": {k: primary[k] for k in ("S_pool", "ci95", "per_seed", "verdict")},
        "co_primary": {k: co_primary[k] for k in ("delta_pool", "ci95", "per_seed", "verdict")},
        "per_panel": {p: {k: v[k] for k in ("S", "S_ci95", "delta", "delta_ci95", "D3", "D3_ci95")}
                      for p, v in per_panel.items()},
    }
    print(json.dumps(brief, indent=2))


if __name__ == "__main__":
    main()
