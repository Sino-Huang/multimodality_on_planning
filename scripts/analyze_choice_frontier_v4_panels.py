#!/usr/bin/env python
"""CPU-only pre-registered #139 analysis on the fresh held-out panels P2 and P2u.

docs/experiments/choice-frontier/issue-139-protocol.md. Metric functions (M1-M5,
bootstrap, ladder test) are imported from ``scripts/analyze_choice_frontier_v2.py``
and the endpoint verdict rule from ``scripts/analyze_choice_frontier_v3.py``; no
formula is copied. Output: ``outputs/choice-frontier/v4/panels/metrics/analysis.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority  # noqa: E402
from scripts.analyze_choice_frontier_v2 import (  # noqa: E402
    ALGORITHMS,
    COMPARATORS,
    STOCHASTIC_SEEDS,
    bootstrap,
    inspect_episode,
    instrument_validity,
    load,
    shortest_plan,
    summarize,
)
from scripts.analyze_choice_frontier_v3 import verdict  # noqa: E402

CONFIG = ROOT / "configs/experiments/choice-frontier-v4"
PANELS = ROOT / "outputs/choice-frontier/v4/panels"
OUT = PANELS / "metrics"
V2 = ROOT / "outputs/choice-frontier/v2"
V3 = ROOT / "outputs/choice-frontier/v3"
V4_SEEDS = ROOT / "outputs/choice-frontier/v4/seeds"
MARGINS = {"materiality_margin": 0.05, "equivalence_margin": 0.05}
BOOTSTRAP = {"unit": "task cluster", "seed": 133, "draws": 10000, "interval": "95% percentile",
             "within_draw": "per-task difference averaged over the training seeds present"}
DETERMINISTIC = ("exact_reference", "bfs-order", "novelty-first", "worst-first")


def save(name: str, value) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def with_cost(row: dict, optimal: dict) -> dict:
    row["c_star"] = optimal[row["task"]]
    row["kappa"] = row["cost"] / row["c_star"] if row["cost"] is not None else None
    return row


def separation_verdict(lo: float, hi: float) -> str:
    if lo > 0:
        return "SEPARATED_ABOVE"
    if hi < 0:
        return "SEPARATED_BELOW"
    return "NOT_SEPARATED"


def learned_difference(learned: dict[int, dict[str, float]], reference: dict[str, float], tasks: list[str]) -> dict:
    """Per seed and per task learned-minus-reference M1; per-task mean over seeds."""

    per_seed = {str(s): {t: learned[s][t] - reference[t] for t in tasks} for s in sorted(learned)}
    per_task = {t: mean(per_seed[str(s)][t] for s in sorted(learned)) for t in tasks}
    return {"per_seed_task": per_seed, "per_task": per_task}


def endpoint(learned: dict[int, dict[str, float]], random_valid: dict[str, float], tasks: list[str]) -> dict:
    """The #138 rule: D3 = mean over seeds of M1(learned, s) - M1(random_valid); seeds averaged in-draw."""

    diff = learned_difference(learned, random_valid, tasks)
    d3 = mean(diff["per_task"].values())
    ci = bootstrap(diff["per_task"], tasks)
    points = {s: mean(values.values()) for s, values in diff["per_seed_task"].items()}
    return {
        "D3": d3,
        "ci95": ci,
        "per_seed": points,
        "per_seed_ci95": {s: bootstrap(values, tasks) for s, values in diff["per_seed_task"].items()},
        "seeds": sorted(learned),
        "tasks": len(tasks),
        "m1_learned_seed_mean": mean(mean(learned[s][t] for s in learned) for t in tasks),
        "m1_random_valid": mean(random_valid[t] for t in tasks),
        "per_task_difference": diff["per_task"],
        "bootstrap": BOOTSTRAP,
        **MARGINS,
        "rule": ("POSITIVE: lo > 0 and D3 >= 0.05 and every seed point > 0; EQUIVALENT: -0.05 < lo and "
                 "hi < 0.05; NEGATIVE: hi < 0; INCONCLUSIVE otherwise"),
        "verdict": verdict(d3, ci[0], ci[1], points, MARGINS),
    }


def separation(learned: dict[int, dict[str, float]], rung: dict[str, float], tasks: list[str], name: str) -> dict:
    """S = M1(learned, seed mean) - M1(rung, its 5-seed mean); paired task-cluster bootstrap."""

    diff = learned_difference(learned, rung, tasks)
    s = mean(diff["per_task"].values())
    ci = bootstrap(diff["per_task"], tasks)
    return {
        "rung": name,
        "S": s,
        "ci95": ci,
        "per_seed": {k: mean(v.values()) for k, v in diff["per_seed_task"].items()},
        "m1_rung": mean(rung[t] for t in tasks),
        "per_task_difference": diff["per_task"],
        "bootstrap": BOOTSTRAP,
        "rule": "SEPARATED_ABOVE if lo > 0; SEPARATED_BELOW if hi < 0; otherwise NOT_SEPARATED",
        "verdict": separation_verdict(ci[0], ci[1]),
    }


def model_rows(evaluation_dir: Path, name_of, authorities, refs, optimal, tasks) -> list[dict]:
    evaluation = load(evaluation_dir / "evaluation.json")
    if not evaluation["complete"] or evaluation["missing_bindings"] or evaluation.get("replay_mismatches"):
        raise ValueError(f"{evaluation_dir} is not complete with 0 missing and 0 mismatches")
    rows = []
    for binding in load(evaluation_dir / "bindings.json")["bindings"]:
        if binding["task_id"] not in tasks:
            continue
        episode = load(evaluation_dir / "episodes" / binding["task_id"].replace("/", "__") / name_of(binding))
        if (episode["task_id"], episode["algorithm"], episode["condition"]) != (
            binding["task_id"], binding["algorithm"], binding["condition"]
        ) or episode.get("training_seed") != binding.get("training_seed"):
            raise ValueError("model episode identity differs from its binding")
        ref = refs[binding["task_id"]][binding["algorithm"]]["expansions"]
        row = inspect_episode(episode, authorities[binding["task_id"]], ref, binding["condition"], 2)
        row["training_seed"] = binding.get("training_seed")
        rows.append(with_cost(row, optimal))
    return rows


def v3_name(binding: dict) -> str:
    return f"{binding['algorithm']}-{binding['condition']}-s{binding['training_seed']}-{binding['seed']}.json.gz"


def v4_panel_name(binding: dict) -> str:
    trained = "base" if binding["training_seed"] is None else f"s{binding['training_seed']}"
    return f"{binding['algorithm']}-{binding['condition']}-{trained}-{binding['seed']}.json.gz"


def zoo_rows(manifest_path: Path, authorities, refs, optimal, tasks) -> list[dict]:
    manifest = load(manifest_path)
    if not manifest["complete"] or manifest["expected_bindings"] != 58 * len(tasks):
        raise ValueError(f"{manifest_path} is incomplete")
    rows = []
    for binding in manifest["bindings"]:
        if binding["status"] != "observed" or binding["replay_status"] != "passed":
            raise ValueError("zoo episode is not observed and replayed")
        episode = load(ROOT / binding["episode_path"])
        if episode.get("selector", episode["arm"]) != binding["arm"] or episode["instance_id"] != binding["task_id"]:
            raise ValueError("zoo episode identity differs from its binding")
        ref = refs[binding["task_id"]][binding["algorithm"]]["expansions"]
        rows.append(with_cost(inspect_episode(episode, authorities[binding["task_id"]], ref, binding["arm"], 2),
                              optimal))
    for arm in COMPARATORS:
        for task in tasks:
            for algorithm in ALGORITHMS:
                n = sum(r["arm"] == arm and r["task"] == task and r["algorithm"] == algorithm for r in rows)
                if n != (1 if arm in DETERMINISTIC else STOCHASTIC_SEEDS):
                    raise ValueError(f"zoo coverage differs: {arm} {task} {algorithm} {n}")
    return rows


def panel_data(name: str, models: bool = True) -> dict:
    """Controls, ladder arms, learned per seed and base for one panel."""

    if name == "p135":
        membership = load(ROOT / "configs/experiments/choice-frontier-v2/membership.json")
        frozen_optimal = load(V2 / "metrics/optimal-costs.json")
    else:
        membership = load(CONFIG / f"membership-{name}.json")
        frozen_optimal = None
    tasks = membership["task_ids"]
    refs = {t["row"]["task_id"]: t["row"]["reference_costs"] for t in membership["tasks"]}
    domains = {t["row"]["task_id"]: t["row"]["domain"] for t in membership["tasks"]}
    authorities, optimal = {}, {}
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
    zoo_manifest = V2 / "zoo/manifest.json" if name == "p135" else PANELS / name / "zoo/manifest.json"
    controls = zoo_rows(zoo_manifest, authorities, refs, optimal, tasks)
    learned, base = [], []
    if models and name == "p135":
        learned = model_rows(V3 / "evaluation", v3_name, authorities, refs, optimal, tasks)
        if (V4_SEEDS / "evaluation/evaluation.json").is_file():
            learned += model_rows(V4_SEEDS / "evaluation", v3_name, authorities, refs, optimal, tasks)
        base = [r for r in model_rows(V2 / "evaluation", lambda b: f"{b['algorithm']}-{b['condition']}-{b['seed']}"
                                      ".json.gz", authorities, refs, optimal, tasks)
                if r["arm"] == "pretrained_base"]
    elif models:
        models_ = model_rows(PANELS / name / "evaluation", v4_panel_name, authorities, refs, optimal, tasks)
        learned = [r for r in models_ if r["arm"] == "learned_adapter"]
        base = [r for r in models_ if r["arm"] == "pretrained_base"]
    arms = summarize(controls + base, tasks, (*COMPARATORS, "pretrained_base") if models else COMPARATORS)
    seeds = sorted({r["training_seed"] for r in learned})
    per_seed = {s: summarize([r for r in learned if r["training_seed"] == s], tasks, ("learned_adapter",))
                ["learned_adapter"] for s in seeds}
    for seed, summary in per_seed.items():
        if summary.get("tasks_present") != len(tasks):
            raise ValueError(f"{name} seed {seed} learned episodes do not cover every task")
    return {"membership": membership, "tasks": tasks, "domains": domains, "arms": arms, "per_seed": per_seed,
            "seeds": seeds, "rows": controls + base + learned}


def task_m1(summary: dict) -> dict[str, float]:
    return {t: v["auc"] for t, v in summary["per_task"].items()}


def learned_m1(data: dict) -> dict[int, dict[str, float]]:
    return {s: task_m1(summary) for s, summary in data["per_seed"].items()}


def arm_table(data: dict) -> dict:
    table = {
        arm: {"m1": data["arms"][arm]["m1_auc"], "ci95": data["arms"][arm]["m1_task_cluster_95pct_ci_10000_seed133"],
              "solved_at_2": data["arms"][arm]["m3_solved_coverage"],
              "teacher_agreement_minus_chance": data["arms"][arm]["m4_teacher_agreement"]["observed_minus_chance"]}
        for arm in (*COMPARATORS, "pretrained_base")
    }
    for seed, summary in data["per_seed"].items():
        m4 = summary["m4_teacher_agreement"]
        table[f"learned_adapter_s{seed}"] = {
            "m1": summary["m1_auc"], "ci95": summary["m1_task_cluster_95pct_ci_10000_seed133"],
            "solved_at_2": summary["m3_solved_coverage"],
            "teacher_agreement_minus_chance": m4["observed_minus_chance"], "last_label_rate": m4["selected_last_rate"],
        }
    mean_task = {t: mean(learned_m1(data)[s][t] for s in data["seeds"]) for t in data["tasks"]}
    table["learned_adapter_seed_mean"] = {"m1": mean(mean_task.values()), "ci95": bootstrap(mean_task, data["tasks"]),
                                          "per_task": mean_task}
    return table


def panel_tests(data: dict) -> dict:
    tasks = data["tasks"]
    learned = learned_m1(data)
    random_valid = task_m1(data["arms"]["random_valid"])
    return {
        "primary": endpoint(learned, random_valid, tasks),
        "separation": {
            "vs_eps_0.75": separation(learned, task_m1(data["arms"]["exact-eps-0.75"]), tasks, "exact-eps-0.75"),
            "vs_eps_0.50": separation(learned, task_m1(data["arms"]["exact-eps-0.50"]), tasks, "exact-eps-0.50"),
        },
        "ladder": instrument_validity(data["arms"], tasks),
    }


def combine(datasets: list[dict]) -> tuple[list[str], dict[int, dict[str, float]], dict[str, float], dict, dict]:
    """Union of task-keyed per-task values across panels (task ids are disjoint)."""

    seeds = sorted(set.intersection(*(set(d["seeds"]) for d in datasets)))
    tasks = [t for d in datasets for t in d["tasks"]]
    if len(set(tasks)) != len(tasks):
        raise ValueError("panels share a task id")
    learned = {s: {t: v for d in datasets for t, v in learned_m1(d)[s].items()} for s in seeds}
    random_valid = {t: v for d in datasets for t, v in task_m1(d["arms"]["random_valid"]).items()}
    eps = {t: v for d in datasets for t, v in task_m1(d["arms"]["exact-eps-0.75"]).items()}
    domains = {t: v for d in datasets for t, v in d["domains"].items()}
    return tasks, learned, random_valid, eps, domains


def sign_counts(values: dict[str, float]) -> dict[str, int]:
    return {"positive": sum(v > 0 for v in values.values()), "zero": sum(v == 0 for v in values.values()),
            "negative": sum(v < 0 for v in values.values())}


def cpu_ladders() -> None:
    """CPU-only ladder verdicts (posted before GPU work); written to ladder-cpu.json."""

    result = {}
    for name in ("p2", "p2u"):
        data = panel_data(name, models=False)
        result[name] = {
            "membership_sha256": data["membership"]["membership_sha256"],
            "confirmatory": data["membership"].get("confirmatory", True) if name == "p2" else False,
            "ladder": instrument_validity(data["arms"], data["tasks"]),
            "m1": {arm: data["arms"][arm]["m1_auc"] for arm in COMPARATORS},
        }
    save("ladder-cpu.json", result)
    brief = {}
    for name, r in result.items():
        pairs = [(p["left"], p["right"], round(p["difference"], 4), [round(x, 4) for x in p["ci95"]])
                 for p in r["ladder"]["pairs"]]
        brief[name] = {"verdict": r["ladder"]["verdict"], "pairs": pairs,
                       "m1": {k: round(v, 4) for k, v in r["m1"].items()}}
    print(json.dumps(brief, indent=1))


def main() -> None:
    if "--cpu-only" in sys.argv[1:]:
        cpu_ladders()
        return
    data = {name: panel_data(name) for name in ("p2", "p2u", "p135")}
    confirmatory_p2 = data["p2"]["membership"].get("confirmatory", True)
    p2 = panel_tests(data["p2"])
    p2u = panel_tests(data["p2u"])

    tasks, learned, random_valid, eps, _domains = combine([data["p135"], data["p2"], data["p2u"]])
    pooled = {
        "tasks": len(tasks),
        "panels": {"p135": len(data["p135"]["tasks"]), "p2": len(data["p2"]["tasks"]), "p2u": len(data["p2u"]["tasks"])},
        "status": "descriptive",
        "primary": endpoint(learned, random_valid, tasks),
        "separation_vs_eps_0.75": separation(learned, eps, tasks, "exact-eps-0.75"),
    }

    per_task = {}
    for name in ("p135", "p2", "p2u"):
        d = data[name]
        diff = learned_difference(learned_m1(d), task_m1(d["arms"]["random_valid"]), d["tasks"])["per_task"]
        per_task[name] = {"per_task_difference": diff, "counts": sign_counts(diff),
                          "domains": {t: d["domains"][t] for t in d["tasks"]}}
    all_diff = {t: v for name in per_task for t, v in per_task[name]["per_task_difference"].items()}
    lodo_tasks, lodo_learned, lodo_random, _eps, lodo_domains = combine([data["p135"], data["p2"]])
    leave_one_domain_out = {}
    for domain in sorted(set(lodo_domains.values())):
        kept = [t for t in lodo_tasks if lodo_domains[t] != domain]
        result = endpoint({s: {t: v[t] for t in kept} for s, v in lodo_learned.items()},
                          {t: lodo_random[t] for t in kept}, kept)
        leave_one_domain_out[domain] = {"tasks_left": len(kept), "D3": result["D3"], "ci95": result["ci95"],
                                        "verdict_rule_applied": result["verdict"]}
    concentration = {
        "status": "descriptive (reviewer point c)",
        "per_panel": per_task,
        "all_36_counts": sign_counts(all_diff),
        "leave_one_domain_out_p2_union_p135": leave_one_domain_out,
    }

    report = {
        "status": "pre-registered #139 analysis (issue-139-protocol.md, Amendment A1)",
        "memberships": {n: data[n]["membership"]["membership_sha256"] for n in ("p2", "p2u", "p135")},
        "training_seeds": {n: data[n]["seeds"] for n in ("p2", "p2u", "p135")},
        "p2_confirmatory": confirmatory_p2,
        "ladder_p2": {**p2["ladder"], "status": "confirmatory" if confirmatory_p2 else "descriptive (A1 fallback)"},
        "heldout_p2": {"primary": p2["primary"], "separation": p2["separation"],
                       "status": "confirmatory" if confirmatory_p2 else "descriptive (A1 fallback)"},
        "unscreened_p2u": {"primary": p2u["primary"], "separation": p2u["separation"], "ladder": p2u["ladder"],
                           "status": "primary endpoint confirmatory; separation and ladder descriptive"},
        "pooled": pooled,
        "concentration": concentration,
        "arms": {n: arm_table(data[n]) for n in ("p2", "p2u", "p135")},
        "interpretation": ("M1 = trapezoidal solve-versus-budget AUC; task-cluster bootstrap Random(133), 10,000 draws; "
                           "exact-eps and hadd-greedy read privileged information; M2/M3 condition on solving"),
    }
    save("all-episode-metrics.json", {n: data[n]["rows"] for n in ("p2", "p2u")})
    save("analysis.json", report)
    brief = {
        "ladder_p2": report["ladder_p2"]["verdict"],
        "heldout_p2": {k: p2["primary"][k] for k in ("D3", "ci95", "per_seed", "verdict")},
        "separation_p2": {k: p2["separation"]["vs_eps_0.75"][k] for k in ("S", "ci95", "verdict")},
        "unscreened_p2u": {k: p2u["primary"][k] for k in ("D3", "ci95", "per_seed", "verdict")},
        "pooled": {"D3": pooled["primary"]["D3"], "ci95": pooled["primary"]["ci95"],
                   "S": pooled["separation_vs_eps_0.75"]["S"], "S_ci95": pooled["separation_vs_eps_0.75"]["ci95"]},
        "concentration": concentration["all_36_counts"],
    }
    print(json.dumps(brief, indent=2))


if __name__ == "__main__":
    main()
