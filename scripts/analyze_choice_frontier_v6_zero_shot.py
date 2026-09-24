#!/usr/bin/env python
"""CPU-only pre-registered #141 analysis: the zero-shot base arm on the #135 panel and P2.

docs/experiments/choice-frontier/issue-141-protocol.md. Metric functions are imported,
not copied: M1-M4 and the task-cluster bootstrap from ``scripts/analyze_choice_frontier_v2.py``;
the panel loaders (controls, ladder, Qwen adapter seeds), the #138 D3 rule and the
separation test from ``scripts/analyze_choice_frontier_v4_panels.py``. New here: the
arm-minus-adapter verdict and the exact sign-flip permutation p-value. Output:
``outputs/choice-frontier/v6/metrics/analysis.json``.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.analyze_choice_frontier_v2 import LADDER, bootstrap, load, summarize  # noqa: E402
from scripts.analyze_choice_frontier_v4_panels import (  # noqa: E402
    endpoint,
    learned_m1,
    model_rows,
    panel_data,
    separation,
    task_m1,
)

PROTOCOL = ROOT / "configs/experiments/choice-frontier-v6/protocol.json"
V6 = ROOT / "outputs/choice-frontier/v6"
OUT = V6 / "metrics"
FROZEN_V4_PANELS = ROOT / "outputs/choice-frontier/v4/panels/metrics/analysis.json"
PANELS = {"v2": "p135", "p2": "p2"}
CONDITION = "zero_shot_base"
ADAPTER_SEEDS = (17, 29, 71)
EQUIVALENCE_MARGIN = 0.05
BOOTSTRAP = {"unit": "task cluster", "seed": 133, "draws": 10000, "interval": "95% percentile",
             "within_draw": "resample tasks with replacement; the adapter's 3 seeds are averaged per task (equivalent "
                            "to averaging inside the draw)", "paired": True}
TOLERANCE = 1e-12


def save(name: str, value) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def adapter_verdict(lo: float, hi: float, margin: float = EQUIVALENCE_MARGIN) -> str:
    """SEPARATED_ABOVE, SEPARATED_BELOW, EQUIVALENT, NOT_SEPARATED — evaluated in that order."""

    if lo > 0:
        return "SEPARATED_ABOVE"
    if hi < 0:
        return "SEPARATED_BELOW"
    if -margin < lo and hi < margin:
        return "EQUIVALENT"
    return "NOT_SEPARATED"


def sign_flip_p(differences: list[float]) -> dict:
    """Exact two-sided sign-flip permutation p-value of the mean over all 2^n sign vectors."""

    d = np.asarray(differences, dtype=np.float64)
    n = len(d)
    low = min(n, 16)
    bits_low = (np.arange(2**low)[:, None] >> np.arange(low)) & 1
    sums_low = (bits_low * 2 - 1) @ d[:low]
    high = n - low
    bits_high = (np.arange(2**high)[:, None] >> np.arange(high)) & 1
    sums_high = (bits_high * 2 - 1) @ d[low:] if high else np.zeros(1)
    observed = abs(d.sum())
    extreme = sum(int(np.count_nonzero(np.abs(s + sums_low) >= observed - TOLERANCE)) for s in sums_high)
    return {"p_two_sided": extreme / 2**n, "sign_vectors": 2**n, "tasks": n, "statistic": "mean per-task difference",
            "exact": True}


def arm_rows(panel: str, data: dict) -> list[dict]:
    membership = data["membership"]
    refs = {t["row"]["task_id"]: t["row"]["reference_costs"] for t in membership["tasks"]}
    authorities = {}
    optimal = {}
    for row in data["rows"]:
        optimal[row["task"]] = row["c_star"]
    # The panel loader already built the authorities; rebuild them the same way for the arm's episodes.
    from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority

    for task in membership["tasks"]:
        snapshot = load(ROOT / task["row"]["task_path"])
        authorities[task["row"]["task_id"]] = PDDLStateAuthority.from_pddl(snapshot["domain_pddl"],
                                                                            snapshot["problem_pddl"])
    rows = model_rows(V6 / "evaluation" / panel, lambda b: f"{b['algorithm']}-{b['condition']}-{b['seed']}.json.gz",
                      authorities, refs, optimal, data["tasks"])
    if len(rows) != 2 * len(data["tasks"]) or any(r["arm"] != CONDITION for r in rows):
        raise ValueError(f"{panel} zero-shot episodes do not cover every task and algorithm")
    return rows


def reuse_check(name: str, data: dict) -> dict:
    """Recomputed control/adapter per-task M1 equals the frozen #139 analysis (arms.<panel>)."""

    frozen = load(FROZEN_V4_PANELS)["arms"][name]
    rungs = {arm: abs(data["arms"][arm]["m1_auc"] - frozen[arm]["m1"]) for arm in (*LADDER, "pretrained_base")}
    adapter = {t: mean(learned_m1(data)[s][t] for s in ADAPTER_SEEDS) for t in data["tasks"]}
    frozen_adapter = frozen["learned_adapter_seed_mean"]["per_task"]
    per_task = max(abs(adapter[t] - frozen_adapter[t]) for t in data["tasks"])
    ok = max(rungs.values()) < TOLERANCE and per_task < TOLERANCE and sorted(data["seeds"]) == list(ADAPTER_SEEDS)
    if not ok:
        raise ValueError(f"reused {name} controls/adapter differ from the frozen #139 analysis")
    return {"rung_m1_max_abs_diff": max(rungs.values()), "adapter_per_task_max_abs_diff": per_task, "ok": ok}


def contrast_block(arm: dict[str, float], reference: dict[str, float], tasks: list[str], name: str) -> dict:
    diff = {t: arm[t] - reference[t] for t in tasks}
    ci = bootstrap(diff, tasks)
    return {"contrast": name, "value": mean(diff.values()), "ci95": ci, "per_task_difference": diff,
            "m1_arm": mean(arm[t] for t in tasks), "m1_reference": mean(reference[t] for t in tasks),
            "tasks": len(tasks), "bootstrap": BOOTSTRAP, "sign_flip": sign_flip_p([diff[t] for t in tasks])}


def endpoints(arm: dict[str, float], data_by_panel: dict[str, dict], panels: list[str]) -> dict:
    tasks = [t for p in panels for t in data_by_panel[p]["tasks"]]
    if len(set(tasks)) != len(tasks):
        raise ValueError("panels share a task id")

    def merged(fn):
        return {t: v for p in panels for t, v in fn(data_by_panel[p]).items()}

    rnd = merged(lambda d: task_m1(d["arms"]["random_valid"]))
    eps75 = merged(lambda d: task_m1(d["arms"]["exact-eps-0.75"]))
    eps50 = merged(lambda d: task_m1(d["arms"]["exact-eps-0.50"]))
    adapter = merged(lambda d: {t: mean(learned_m1(d)[s][t] for s in ADAPTER_SEEDS) for t in d["tasks"]})
    arm_t = {t: arm[t] for t in tasks}
    d3 = endpoint({17: arm_t}, rnd, tasks)
    d3["sign_flip"] = sign_flip_p([d3["per_task_difference"][t] for t in tasks])
    s = separation({17: arm_t}, eps75, tasks, "exact-eps-0.75")
    s["sign_flip"] = sign_flip_p([s["per_task_difference"][t] for t in tasks])
    s50 = separation({17: arm_t}, eps50, tasks, "exact-eps-0.50")
    s50["sign_flip"] = sign_flip_p([s50["per_task_difference"][t] for t in tasks])
    a = contrast_block(arm_t, adapter, tasks, "zero_shot_base - Qwen adapter (3-seed mean 17/29/71)")
    a["rule"] = ("SEPARATED_ABOVE lo > 0; SEPARATED_BELOW hi < 0; EQUIVALENT -0.05 < lo and hi < 0.05; "
                 "NOT_SEPARATED otherwise (in that order)")
    a["equivalence_margin"] = EQUIVALENCE_MARGIN
    a["verdict"] = adapter_verdict(*a["ci95"])
    a["adapter_per_seed_m1"] = {str(sd): mean(v for p in panels for t, v in learned_m1(data_by_panel[p])[sd].items())
                                for sd in ADAPTER_SEEDS}
    a["adapter_per_seed_difference"] = {str(sd): mean(arm_t[t] - learned_m1(data_by_panel[p])[sd][t]
                                                      for p in panels for t in data_by_panel[p]["tasks"])
                                        for sd in ADAPTER_SEEDS}
    return {"tasks": len(tasks), "D3": d3, "S": s, "S_vs_eps_0_50_descriptive": s50, "A": a,
            "m1_arm": mean(arm_t.values()), "m1_arm_ci95": bootstrap(arm_t, tasks),
            "m1_adapter_seed_mean": mean(adapter.values()), "m1_adapter_seed_mean_ci95": bootstrap(adapter, tasks)}


def ladder_position(rungs: dict[str, float], value: float) -> dict:
    beaten = [arm for arm in LADDER if rungs[arm] <= value]
    higher = [arm for arm in LADDER if rungs[arm] > value]
    return {"ladder_m1": rungs, "arm_m1": value, "next_higher_rung": higher[-1] if higher else None,
            "next_lower_or_equal_rung": beaten[0] if beaten else None}


def behaviour(summary: dict, rows: list[dict], panel: str) -> dict:
    episodes = [load(V6 / "evaluation" / panel / "episodes" / r["task"].replace("/", "__")
                     / f"{r['algorithm']}-{CONDITION}-{r['seed']}.json.gz") for r in rows]
    measurements = [m for e in episodes for m in e["call_measurements"]]
    calls = len(measurements)
    invalid = sum(e["result"]["invalid_operation_count"] for e in episodes)
    m4 = summary["m4_teacher_agreement"]
    return {
        "episodes": len(episodes),
        "model_calls": calls,
        "accepted_calls": calls - invalid,
        "valid_output_rate": (calls - invalid) / calls if calls else None,
        "extraction_rules": dict(Counter(m["extraction_rule"] for m in measurements)),
        "terminations": dict(Counter(e["result"]["termination_reason"] for e in episodes)),
        "solved_at_2": summary["m3_solved_coverage"],
        "teacher_agreement_observed": m4["observed"],
        "teacher_agreement_chance": m4["chance"],
        "teacher_agreement_minus_chance": m4["observed_minus_chance"],
        "on_policy_decisions_k_ge_2": m4["on_policy_decisions_k_ge_2"],
        "first_label_rate": m4["selected_first_rate"],
        "last_label_rate": m4["selected_last_rate"],
        "mean_generated_tokens": mean(m["generated_sequence_tokens"] for m in measurements) if calls else None,
        "mean_call_wall_seconds": mean(m["call_wall_seconds"] for m in measurements) if calls else None,
    }


def arm_table(data: dict, arm_summary: dict) -> dict:
    table = {arm: {"m1": data["arms"][arm]["m1_auc"], "ci95": data["arms"][arm]["m1_task_cluster_95pct_ci_10000_seed133"],
                   "solved_at_2": data["arms"][arm]["m3_solved_coverage"]}
             for arm in data["arms"]}
    for seed in ADAPTER_SEEDS:
        summary = data["per_seed"][seed]
        table[f"learned_adapter_s{seed}"] = {"m1": summary["m1_auc"],
                                             "ci95": summary["m1_task_cluster_95pct_ci_10000_seed133"],
                                             "solved_at_2": summary["m3_solved_coverage"]}
    table[CONDITION] = {"m1": arm_summary["m1_auc"], "ci95": arm_summary["m1_task_cluster_95pct_ci_10000_seed133"],
                        "solved_at_2": arm_summary["m3_solved_coverage"],
                        "per_task": task_m1(arm_summary)}
    return table


def main() -> None:
    protocol = load(PROTOCOL)
    datasets, arms, rows_by_panel, reuse = {}, {}, {}, {}
    for panel, name in PANELS.items():
        data = panel_data(name)
        if data["membership"]["membership_sha256"] != protocol["evaluation"]["panels"][panel]["membership_sha256"]:
            raise ValueError(f"{panel} membership differs from the frozen v6 protocol")
        reuse[panel] = reuse_check(name, data)
        rows = arm_rows(panel, data)
        summary = summarize(rows, data["tasks"], (CONDITION,))[CONDITION]
        if summary.get("tasks_present") != len(data["tasks"]):
            raise ValueError(f"{panel} zero-shot arm does not cover every task")
        datasets[panel], arms[panel], rows_by_panel[panel] = data, summary, rows

    per_panel, primary, co_primary, ladder = {}, {}, {}, {}
    for panel in PANELS:
        block = endpoints(task_m1(arms[panel]), datasets, [panel])
        stage = protocol["evaluation"]["panels"][panel]["stage"]
        per_panel[panel] = {"stage": stage, **block, "arms": arm_table(datasets[panel], arms[panel]),
                            "behaviour": behaviour(arms[panel], rows_by_panel[panel], panel)}
        primary[panel] = {"estimand": protocol["analysis"]["primary"]["estimand"], "stage": stage,
                          "D3": block["D3"]["D3"], "ci95": block["D3"]["ci95"], "verdict": block["D3"]["verdict"],
                          "sign_flip_p": block["D3"]["sign_flip"]["p_two_sided"], "tasks": block["tasks"]}
        co_primary[panel] = {
            "S": {"value": block["S"]["S"], "ci95": block["S"]["ci95"], "verdict": block["S"]["verdict"],
                  "sign_flip_p": block["S"]["sign_flip"]["p_two_sided"], "m1_eps_0_75": block["S"]["m1_rung"]},
            "A": {"value": block["A"]["value"], "ci95": block["A"]["ci95"], "verdict": block["A"]["verdict"],
                  "sign_flip_p": block["A"]["sign_flip"]["p_two_sided"],
                  "m1_adapter_seed_mean": block["m1_adapter_seed_mean"]},
            "stage": stage,
        }
        rungs = {arm: datasets[panel]["arms"][arm]["m1_auc"] for arm in LADDER}
        ladder[panel] = ladder_position(rungs, block["m1_arm"])
        ladder[panel]["adapter_seed_mean_m1"] = block["m1_adapter_seed_mean"]

    all_arm = {t: v for p in PANELS for t, v in task_m1(arms[p]).items()}
    pooled = endpoints(all_arm, datasets, list(PANELS))
    pooled_tasks = [t for p in PANELS for t in datasets[p]["tasks"]]
    pooled_rungs = {arm: mean(v for p in PANELS for v in task_m1(datasets[p]["arms"][arm]).values()) for arm in LADDER}
    ladder["pooled"] = ladder_position(pooled_rungs, pooled["m1_arm"])
    ladder["pooled"]["adapter_seed_mean_m1"] = pooled["m1_adapter_seed_mean"]
    ladder["pooled"]["rung_ci95"] = {arm: bootstrap({t: v for p in PANELS for t, v in
                                                     task_m1(datasets[p]["arms"][arm]).items()}, pooled_tasks)
                                     for arm in LADDER}
    permutation = {scope: {k: (per_panel[scope] if scope in per_panel else pooled)[k]["sign_flip"]
                           for k in ("D3", "S", "A", "S_vs_eps_0_50_descriptive")}
                   for scope in (*PANELS, "pooled")}
    report = {
        "status": "pre-registered #141 analysis (issue-141-protocol.md; frozen 0fa497c)",
        "arm": {"condition": CONDITION, "system_message_sha256": protocol["arm"]["system_message_sha256"],
                "decision_cap": protocol["arm"]["decision_cap"], "realisations": protocol["arm"]["realisations"]},
        "memberships": {p: datasets[p]["membership"]["membership_sha256"] for p in PANELS},
        "episode_accounting": {p: load(V6 / "evaluation" / p / "evaluation.json") for p in PANELS},
        "reused": protocol["evaluation"]["reused_not_rerun"],
        "reuse_checks": reuse,
        "primary": primary,
        "co_primary": co_primary,
        "pooled": {"status": "descriptive", **pooled},
        "per_panel": per_panel,
        "ladder_position": ladder,
        "permutation": permutation,
        "smoke": load(V6 / "smoke/smoke.json") if (V6 / "smoke/smoke.json").is_file() else None,
        "interpretation": ("M1 = trapezoidal solve-versus-budget AUC (#135), caps 2 x R_t; paired task-cluster "
                           "bootstrap Random(133), 10,000 draws; sign-flip p-values are exact and descriptive; "
                           "the zero-shot arm is one greedy realisation per (task, algorithm)"),
    }
    save("analysis.json", report)
    save("zero-shot-episode-metrics.json", rows_by_panel)
    brief = {"primary": {p: {k: v[k] for k in ("D3", "ci95", "verdict", "sign_flip_p")} for p, v in primary.items()},
             "co_primary": co_primary,
             "pooled": {k: {"value": pooled[k].get("D3", pooled[k].get("S", pooled[k].get("value"))),
                            "ci95": pooled[k]["ci95"], "verdict": pooled[k]["verdict"]} for k in ("D3", "S", "A")},
             "ladder": {k: {"arm_m1": v["arm_m1"], "next_higher": v["next_higher_rung"],
                            "next_lower_or_equal": v["next_lower_or_equal_rung"]} for k, v in ladder.items()}}
    print(json.dumps(brief, indent=2))


if __name__ == "__main__":
    main()
