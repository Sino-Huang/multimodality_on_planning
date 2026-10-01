#!/usr/bin/env python
"""Pre-registered #149 analysis (``docs/experiments/choice-frontier/issue-149-protocol.md`` §2, §11).

Reads the v8 controls, scorer, VLM and D3 episodes; writes
``outputs/choice-frontier/v8/metrics/analysis.json`` and the solve / expansions vs budget figure.
No model calls. Conventions (§2): R_t = uncapped exact expansions; solved at m iff goal decision
<= floor(m R_t) and expansions-to-goal <= floor(m R_t); restricted expansions
E = expansions-to-goal if solved within 2 R_t else 2 R_t; e = E / R_t - 1; plan length = g of the
selected goal node.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.node_choice import NodeChoiceTask, run_control_episode  # noqa: E402
from scripts import run_choice_frontier_v7 as v7  # noqa: E402
from scripts import run_choice_frontier_v8 as v8  # noqa: E402

MS = (1.0, 1.25, 1.5, 1.75, 2.0)
WEIGHTS = (0.125, 0.25, 0.25, 0.25, 0.125)
GRID = tuple(i / 20 for i in range(41))
DRAWS = 10_000
BOOTSTRAP_SEED = 133
DELTA, EQUIVALENCE_D3, EQUIVALENCE_E = 0.05, 0.05, 0.10
CSTAR_TRAINING_MAX = 15
OUT = ROOT / v8.OUT / "metrics"
GREEDY, W3 = v8.GREEDY, v8.W3


# ---------------------------------------------------------------------------- episodes


def summarize(report: dict, r: int) -> dict:
    """Goal decision, expansions-to-goal, plan length (g of the goal node), kappa agreement, stops."""

    events = report["events"]
    g_of = {"s0": 0}
    key_of: dict[str, tuple] = {"s0": (0, 0)}
    h_of: dict[str, float] = {}
    next_serial = 1
    expanded = 0
    goal = None
    hits = chance = decisions = 0.0
    low_fifth = 0
    for index, event in enumerate(events):
        result = event["trusted_runtime_result"]
        menu = [e["state_ref"] for e in event["menu"]]
        chosen = result.get("expanded_state_id") if result.get("accepted") else None
        if chosen is not None and len(menu) >= 2:
            head = min(menu, key=lambda ref: key_of[ref])
            hits += chosen == head
            chance += 1 / len(menu)
            decisions += 1
            hs = sorted(h_of.get(ref, 0.0) for ref in menu)
            low_fifth += h_of.get(chosen, 0.0) <= hs[max(0, math.ceil(len(hs) / 5) - 1)]
        if result["status"] == "goal_reached":
            goal = {"decision": index + 1, "expansions": expanded, "plan_length": g_of[chosen]}
            break
        if result["status"] != "expanded":
            continue
        expanded += 1
        candidate_serials: dict[str, int] = {}
        for admission in result["admissions"]:
            data = admission["trusted_runtime_result"]
            target = data["target_state_id"]
            serial = candidate_serials.setdefault(target, next_serial)
            next_serial += 1
            if data["status"] in ("enqueued", "improved", "reopened"):
                g_of[target] = data["g"]
                h_of[target] = data["h"]
                key_of[target] = (data["priority"], serial)
    if report["result"]["goal_reached"] != (goal is not None):
        raise ValueError("goal reconstruction differs from the stored result")
    if not events and report["result"]["goal_reached"]:
        goal = {"decision": 0, "expansions": 0, "plan_length": 0}
    return {
        "goal": goal,
        "R": r,
        "termination": report["result"]["termination_reason"],
        "overflow": report["result"]["termination_reason"] == "observation_overflow",
        "invalid": report["result"]["invalid_operation_count"],
        "agreement": [hits, chance, decisions],
        "low_fifth": [low_fifth, decisions],
    }


def solved_at(summary: dict, m: float) -> bool:
    goal, r = summary["goal"], summary["R"]
    return bool(goal) and goal["decision"] <= math.floor(m * r) and goal["expansions"] <= math.floor(m * r)


def metrics(summary: dict) -> dict:
    r = summary["R"]
    solves = {m: solved_at(summary, m) for m in MS}
    curve_solve = [float(solved_at(summary, m)) for m in GRID]
    curve_e = [
        (summary["goal"]["expansions"] if solved_at(summary, m) else m * r) / r if m > 0 else 0.0 for m in GRID
    ]
    e = (summary["goal"]["expansions"] if solves[2.0] else 2 * r) / r - 1
    return {
        "auc": sum(w * solves[m] for w, m in zip(WEIGHTS, MS, strict=True)),
        "solved_at_2": float(solves[2.0]),
        "e": e,
        "rho": summary["goal"]["expansions"] / r if solves[2.0] else None,
        "plan_length": summary["goal"]["plan_length"] if solves[2.0] else None,
        "curve_solve": curve_solve,
        "curve_e": curve_e,
        "overflow": float(summary["overflow"]),
        "invalid_stop": float(summary["termination"] == "deterministic_invalid_operation"),
        "agreement": summary["agreement"],
        "low_fifth": summary["low_fifth"],
    }


def native_gbfs(row: dict, algorithm: str) -> dict:
    """GBFS(h_add) / WA*(h_add): the uncapped exact episode, no context limit (defines R_t)."""

    authority, _ = v8.task_source(row)
    session = run_control_episode(
        authority, NodeChoiceTask(row["task_id"], row["domain"], algorithm, 2 * row["R"][algorithm]),
        "text", "exact_reference", 17,
    )
    summary = summarize(session.episode(), row["R"][algorithm])
    if summary["goal"]["expansions"] != row["R"][algorithm]:
        raise ValueError(f"native exact expansions differ from R_t: {row['task_id']}")
    return metrics(summary)


def load_metrics(path: Path, r: int) -> dict | None:
    return metrics(summarize(v7.load(path), r)) if path.exists() else None


def average(rows: list[dict]) -> dict:
    """Seed mean of per-episode metrics (None-valued quality fields averaged over solved seeds)."""

    out = {}
    for key in ("auc", "solved_at_2", "e", "overflow", "invalid_stop"):
        out[key] = mean(r[key] for r in rows)
    for key in ("curve_solve", "curve_e"):
        out[key] = [mean(values) for values in zip(*(r[key] for r in rows), strict=True)]
    for key in ("rho", "plan_length"):
        values = [r[key] for r in rows if r[key] is not None]
        out[key] = mean(values) if values else None
    out["seed_auc"] = [r["auc"] for r in rows]
    out["seed_e"] = [r["e"] for r in rows]
    out["agreement"] = [sum(r["agreement"][i] for r in rows) for i in range(3)]
    out["low_fifth"] = [sum(r["low_fifth"][i] for r in rows) for i in range(2)]
    return out


# ---------------------------------------------------------------------------- arm registry


def arm_paths(arm: tuple, row: dict) -> list[Path]:
    kind = arm[0]
    task_id = row["task_id"]
    if kind == "exact":
        return [ROOT / v8.control_path(task_id, arm[1], arm[2], "exact_reference", 17)]
    if kind == "random":
        return [ROOT / v8.control_path(task_id, arm[1], arm[2], "random_valid", s) for s in v8.RANDOM_SEEDS]
    if kind == "scored":
        return [ROOT / v8.scored_path(task_id, arm[1], arm[2])]
    if kind == "d3":
        return [v8.scored_gpu_path(task_id, arm[1], f"{arm[2]}_s{s}")[0] for s in v8.SEEDS]
    if kind == "vlm":
        _, method, algorithm, observation = arm
        return [
            v8.episode_paths(
                "evaluation",
                {"method": method, "algorithm": algorithm, "observation": observation,
                 "condition": "learned_adapter", "seed": s},
                task_id,
            )[0]
            for s in v8.SEEDS
        ]
    if kind == "zeroshot":
        _, algorithm, observation = arm
        if row["stratum"] == "s0":
            cell = {"algorithm": algorithm, "observation": observation, "condition": "zero_shot_base", "seed": 0}
            return [v7.episode_paths("zeroshot", cell, task_id)[0]]
        cell = {"method": "zeroshot", "algorithm": algorithm, "observation": observation,
                "condition": "zero_shot_base", "seed": 0}
        return [v8.episode_paths("evaluation", cell, task_id)[0]]
    raise ValueError(arm)


def arms() -> list[tuple]:
    result: list[tuple] = [("gbfs", a) for a in v8.ALGORITHMS]
    for algorithm in v8.ALGORITHMS:
        for observation in v8.OBSERVATIONS:
            result += [("exact", algorithm, observation), ("random", algorithm, observation)]
        result.append(("scored", algorithm, "goal_count"))
    result.append(("scored", GREEDY, "hstar_oracle"))
    for backbone in v8.D3_BACKBONES:
        for target in v8.D3_TARGETS:
            for algorithm in v8.d3_algorithms(target):
                result.append(("d3", algorithm, f"{backbone}_{target}"))
    for method in v8.METHODS:
        for algorithm in v8.ALGORITHMS if method == "hadd" else (GREEDY,):
            for observation in v8.OBSERVATIONS:
                result.append(("vlm", method, algorithm, observation))
    result += [("zeroshot", a, "text") for a in v8.ALGORITHMS]
    return result


def arm_name(arm: tuple) -> str:
    return "/".join(str(part) for part in arm)


def arm_algorithm(arm: tuple) -> str:
    return arm[2] if arm[0] == "vlm" else arm[1]


def collect() -> tuple[dict, dict]:
    """per_arm[name][task_id] = seed-mean metrics; coverage[name] = {complete, missing}."""

    per_arm, coverage = {}, {}
    rows = v8.panel_rows()
    for arm in arms():
        name = arm_name(arm)
        algorithm = arm_algorithm(arm)
        per_arm[name], missing = {}, []
        for row in rows:
            r = row["R"][algorithm]
            if arm[0] == "gbfs":
                per_arm[name][row["task_id"]] = average([native_gbfs(row, algorithm)])
                continue
            loaded = [load_metrics(p, r) for p in arm_paths(arm, row)]
            if any(m is None for m in loaded):
                missing.append(row["task_id"])
                continue
            per_arm[name][row["task_id"]] = average(loaded)
        coverage[name] = {"tasks": len(per_arm[name]), "missing": missing}
    return per_arm, coverage


# ---------------------------------------------------------------------------- statistics


def percentile(samples: list[float], q: float) -> float:
    return samples[min(len(samples) - 1, max(0, math.ceil(q * len(samples)) - 1))]


def interval(values: dict[str, float], tasks: list[str]) -> dict | None:
    if not tasks:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    draws = sorted(mean(values[t] for t in (rng.choice(tasks) for _ in tasks)) for _ in range(DRAWS))
    return {
        "point": mean(values[t] for t in tasks),
        "ci95": [percentile(draws, 0.025), percentile(draws, 0.975)],
        "p_le_0": sum(d <= 0 for d in draws) / DRAWS,
        "p_ge_0": sum(d >= 0 for d in draws) / DRAWS,
        "tasks": len(tasks),
    }


def unpaired(a: dict[str, float], ta: list[str], b: dict[str, float], tb: list[str]) -> dict | None:
    if not ta or not tb:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    draws = sorted(
        mean(a[t] for t in (rng.choice(ta) for _ in ta)) - mean(b[t] for t in (rng.choice(tb) for _ in tb))
        for _ in range(DRAWS)
    )
    return {"point": mean(a[t] for t in ta) - mean(b[t] for t in tb),
            "ci95": [percentile(draws, 0.025), percentile(draws, 0.975)]}


def separation(stat: dict | None) -> str | None:
    if stat is None:
        return None
    lo, hi = stat["ci95"]
    return "SEPARATED_ABOVE" if lo > 0 else "SEPARATED_BELOW" if hi < 0 else "NOT_SEPARATED"


def verdict_e(stat: dict | None) -> str | None:
    if stat is None:
        return None
    lo, hi = stat["ci95"]
    if hi < 0:
        return "FEWER"
    if lo > 0:
        return "MORE"
    if -EQUIVALENCE_E < lo and hi < EQUIVALENCE_E:
        return "EQUIVALENT"
    return "INCONCLUSIVE"


def verdict_d3(stat: dict | None, seed_points: list[float]) -> str | None:
    if stat is None:
        return None
    lo, hi = stat["ci95"]
    if lo > 0 and stat["point"] >= DELTA and all(p > 0 for p in seed_points):
        return "POSITIVE"
    if -EQUIVALENCE_D3 < lo and hi < EQUIVALENCE_D3:
        return "EQUIVALENT"
    if hi < 0:
        return "NEGATIVE"
    return "INCONCLUSIVE"


def holm(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    ordered = sorted(pvalues, key=lambda k: pvalues[k])
    result, stopped = {}, False
    for rank, key in enumerate(ordered):
        stopped = stopped or pvalues[key] > alpha / (len(ordered) - rank)
        result[key] = not stopped
    return result


# ---------------------------------------------------------------------------- tests


def strata_tasks(stratum: str) -> list[str]:
    if stratum == "beyond":
        return [r["task_id"] for r in v8.panel_rows() if r["stratum"] in v8.NEW_STRATA]
    if stratum.startswith("cstar"):
        low = stratum == "cstar_le_15"
        return [r["task_id"] for r in v8.panel_rows() if (r["cstar"] <= CSTAR_TRAINING_MAX) == low]
    return [r["task_id"] for r in v8.panel_rows(stratum)]


STRATA_REPORTED = ("s0", "s1", "s2", "beyond", "cstar_le_15", "cstar_gt_15")


def common(per_arm: dict, names: list[str], tasks: list[str]) -> list[str]:
    return [t for t in tasks if all(t in per_arm[n] for n in names)]


def field(per_arm: dict, name: str, key: str) -> dict[str, float]:
    return {t: v[key] for t, v in per_arm[name].items()}


def diff(per_arm: dict, a: str, b: str, key: str, tasks: list[str]) -> dict[str, float]:
    return {t: per_arm[a][t][key] - per_arm[b][t][key] for t in tasks}


def test_a(per_arm: dict) -> dict:
    out, pvalues = {}, {}
    for method in ("hstar", "ei"):
        for observation in v8.OBSERVATIONS:
            name = arm_name(("vlm", method, GREEDY, observation))
            for stratum in ("s0", "s1", "s2"):
                tasks = common(per_arm, [name], strata_tasks(stratum))
                stat = interval(field(per_arm, name, "e"), tasks)
                key = f"{method}/{observation}/{stratum}"
                out[key] = {"delta": stat, "verdict": verdict_e(stat),
                            "seed_points": seed_points(per_arm, name, tasks, "seed_e")}
                if stat is not None:
                    pvalues[key] = stat["p_ge_0"]
    for key, passed in holm(pvalues).items():
        out[key]["fewer_holm"] = passed
    return out


def seed_points(per_arm: dict, name: str, tasks: list[str], key: str) -> list[float] | None:
    if not tasks:
        return None
    return [mean(per_arm[name][t][key][i] for t in tasks) for i in range(len(per_arm[name][tasks[0]][key]))]


def test_b(per_arm: dict) -> dict:
    out = {}
    for method in ("hstar", "ei"):
        for observation in v8.OBSERVATIONS:
            a = arm_name(("vlm", method, GREEDY, observation))
            b = arm_name(("vlm", "hadd", GREEDY, observation))
            for stratum in ("s0", "s1", "s2", "beyond"):
                tasks = common(per_arm, [a, b], strata_tasks(stratum))
                stat = interval(diff(per_arm, a, b, "e", tasks), tasks)
                auc = interval(diff(per_arm, a, b, "auc", tasks), tasks)
                out[f"{method}/{observation}/{stratum}"] = {
                    "e_difference": stat, "verdict": separation(stat),
                    "m1_difference": auc, "m1_verdict": separation(auc),
                }
    return out


def test_c(per_arm: dict) -> dict:
    out = {}
    for algorithm in v8.ALGORITHMS:
        for observation in v8.OBSERVATIONS:
            learned = arm_name(("vlm", "hadd", algorithm, observation))
            rnd = arm_name(("random", algorithm, observation))
            goal = arm_name(("scored", algorithm, "goal_count"))
            d3_values, d3_tasks = {}, {}
            for stratum in STRATA_REPORTED:
                tasks = common(per_arm, [learned, rnd, goal], strata_tasks(stratum))
                d3 = {t: per_arm[learned][t]["auc"] - per_arm[rnd][t]["auc"] for t in tasks}
                d3_values[stratum], d3_tasks[stratum] = d3, tasks
                stat = interval(d3, tasks)
                seeds = None
                if tasks:
                    seeds = [mean(per_arm[learned][t]["seed_auc"][i] - per_arm[rnd][t]["auc"] for t in tasks)
                             for i in range(len(v8.SEEDS))]
                vs_goal = interval(diff(per_arm, learned, goal, "auc", tasks), tasks)
                out[f"{algorithm}/{observation}/{stratum}"] = {
                    "d3": stat, "verdict": verdict_d3(stat, seeds or []), "seed_points": seeds,
                    "learned_minus_goal_count_m1": vs_goal, "vs_goal_count": separation(vs_goal),
                    "e": interval(field(per_arm, learned, "e"), tasks), "e_verdict": verdict_e(
                        interval(field(per_arm, learned, "e"), tasks)),
                }
            for stratum in ("s1", "s2", "beyond"):
                trend = unpaired(d3_values[stratum], d3_tasks[stratum], d3_values["s0"], d3_tasks["s0"])
                out[f"{algorithm}/{observation}/{stratum}"]["d3_minus_s0"] = trend
    return out


def test_d(per_arm: dict) -> dict:
    out = {}
    for arm in arms():
        name = arm_name(arm)
        algorithm = arm_algorithm(arm)
        anchor = arm_name(("vlm", "hadd", algorithm, "visual"))
        for stratum in STRATA_REPORTED:
            tasks = common(per_arm, [name], strata_tasks(stratum))
            row = {
                "m1": interval(field(per_arm, name, "auc"), tasks),
                "solved_at_2": interval(field(per_arm, name, "solved_at_2"), tasks),
                "e": interval(field(per_arm, name, "e"), tasks),
                "e_verdict": None,
            }
            row["e_verdict"] = verdict_e(row["e"]) if arm[0] != "gbfs" else None
            if arm[0] in ("scored", "d3", "zeroshot") or (arm[0] == "vlm" and name != anchor):
                paired = common(per_arm, [name, anchor], strata_tasks(stratum))
                m1 = interval(diff(per_arm, name, anchor, "auc", paired), paired)
                e = interval(diff(per_arm, name, anchor, "e", paired), paired)
                row["minus_visual_hadd_adapter"] = {"m1": m1, "m1_verdict": separation(m1), "e": e,
                                                    "e_verdict": separation(e)}
            out[f"{name}/{stratum}"] = row
    return out


def quality(per_arm: dict) -> dict:
    """Plan length / C*, plan length / exact plan, rho, on solved episodes (descriptive)."""

    rows = {r["task_id"]: r for r in v8.panel_rows()}
    out = {}
    for arm in arms():
        name = arm_name(arm)
        algorithm = arm_algorithm(arm)
        exact = arm_name(("gbfs", algorithm))
        for stratum in ("s0", "s1", "s2"):
            tasks = [t for t in common(per_arm, [name], strata_tasks(stratum)) if per_arm[name][t]["rho"] is not None]
            to_cstar = [per_arm[name][t]["plan_length"] / rows[t]["cstar"] for t in tasks]
            to_exact = [per_arm[name][t]["plan_length"] / per_arm[exact][t]["plan_length"] for t in tasks
                        if per_arm[exact][t]["plan_length"]]
            rho = [per_arm[name][t]["rho"] for t in tasks]
            out[f"{name}/{stratum}"] = {
                "solved_tasks": len(tasks),
                "plan_over_cstar": describe(to_cstar),
                "plan_over_exact": describe(to_exact),
                "rho": describe(rho),
            }
    return out


def describe(values: list[float]) -> dict | None:
    if not values:
        return None
    ordered = sorted(values)
    return {"n": len(values), "median": median(ordered), "q1": percentile(ordered, 0.25),
            "q3": percentile(ordered, 0.75), "mean": mean(ordered), "min": ordered[0], "max": ordered[-1]}


def descriptives(per_arm: dict) -> dict:
    out = {}
    for arm in arms():
        name = arm_name(arm)
        for stratum in ("s0", "s1", "s2"):
            tasks = common(per_arm, [name], strata_tasks(stratum))
            if not tasks:
                continue
            hits, chance, decisions = (sum(per_arm[name][t]["agreement"][i] for t in tasks) for i in range(3))
            low, low_n = (sum(per_arm[name][t]["low_fifth"][i] for t in tasks) for i in range(2))
            out[f"{name}/{stratum}"] = {
                "curve_solve": [mean(per_arm[name][t]["curve_solve"][i] for t in tasks) for i in range(len(GRID))],
                "curve_e": [mean(per_arm[name][t]["curve_e"][i] for t in tasks) for i in range(len(GRID))],
                "overflow_rate": mean(per_arm[name][t]["overflow"] for t in tasks),
                "invalid_stop_rate": mean(per_arm[name][t]["invalid_stop"] for t in tasks),
                "hadd_head_agreement_minus_chance": (hits - chance) / decisions if decisions else None,
                "lowest_fifth_hadd_share": low / low_n if low_n else None,
                "decisions_menu_ge_2": decisions,
            }
    return out


# ---------------------------------------------------------------------------- figure


FIGURE_ARMS = (
    (("gbfs", GREEDY), "GBFS(h_add)", "black", "-"),
    (("scored", GREEDY, "goal_count"), "GBFS(goal count)", "grey", "--"),
    (("random", GREEDY, "visual"), "random-valid (visual)", "lightgrey", ":"),
    (("vlm", "hadd", GREEDY, "visual"), "h_add adapter, visual", "tab:blue", "-"),
    (("vlm", "hadd", GREEDY, "text"), "h_add adapter, text", "tab:blue", "--"),
    (("vlm", "hstar", GREEDY, "visual"), "h* adapter, visual", "tab:green", "-"),
    (("vlm", "hstar", GREEDY, "text"), "h* adapter, text", "tab:green", "--"),
    (("vlm", "ei", GREEDY, "visual"), "EI adapter, visual", "tab:orange", "-"),
    (("vlm", "ei", GREEDY, "text"), "EI adapter, text", "tab:orange", "--"),
    (("d3", GREEDY, "cnn_hstar"), "CNN h* regressor", "tab:purple", "-"),
    (("d3", GREEDY, "vit_hstar"), "ViT h* regressor", "tab:purple", "--"),
    (("d3", GREEDY, "cnn_rank"), "CNN ranker", "tab:brown", "-"),
    (("zeroshot", GREEDY, "text"), "zero-shot base, text", "tab:red", ":"),
)


def figure(descriptive: dict) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(13, 7), sharex=True)
    for column, stratum in enumerate(("s0", "s1", "s2")):
        for arm, label, color, style in FIGURE_ARMS:
            entry = descriptive.get(f"{arm_name(arm)}/{stratum}")
            if entry is None:
                continue
            axes[0][column].plot(GRID, entry["curve_solve"], color=color, linestyle=style, label=label)
            axes[1][column].plot(GRID, entry["curve_e"], color=color, linestyle=style, label=label)
        axes[0][column].set_title({"s0": "S0 (in range)", "s1": "S1 (larger)", "s2": "S2 (largest)"}[stratum])
        axes[1][column].set_xlabel("budget multiplier m (expansions / R_t)")
    axes[0][0].set_ylabel("solved within m R_t")
    axes[1][0].set_ylabel("restricted expansions / R_t")
    axes[0][2].legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    paths = []
    for suffix in ("png", "pdf"):
        path = OUT / f"solve-expansions-vs-budget.{suffix}"
        fig.savefig(path, dpi=150)
        paths.append(str(path.relative_to(ROOT)))
    plt.close(fig)
    return paths


# ---------------------------------------------------------------------------- main


def side_facts() -> dict:
    facts = {}
    if (ROOT / v8.HSTAR_MEMBERSHIP).exists():
        facts["hstar_teacher_changed"] = v7.load(v8.HSTAR_MEMBERSHIP)["teacher_changed"]
    if (ROOT / v8.EI_MEMBERSHIP).exists():
        facts["ei_counts"] = v7.load(v8.EI_MEMBERSHIP)["counts"]
    labels = v7.load(v8.LABELS_PATH)
    facts["hstar_labels"] = {"status_counts": labels["status_counts"], "blind_check": labels["blind_check"]}
    d3 = {}
    for backbone in v8.D3_BACKBONES:
        for target in v8.D3_TARGETS:
            for seed in v8.SEEDS:
                path = ROOT / v8.d3_dir(backbone, target, seed) / "result.json"
                if path.exists():
                    result = v7.load(path)
                    d3[f"{backbone}_{target}_s{seed}"] = {
                        k: result.get(k) for k in ("best_epoch", "best_val_loss", "val_mae", "val_pairwise_accuracy")
                    }
    facts["d3_validation"] = d3
    facts["panels"] = {
        s: {"tasks": len(v8.panel_rows(s)),
            "objects": describe([r["objects"] for r in v8.panel_rows(s)]),
            "cstar": describe([r["cstar"] for r in v8.panel_rows(s)]),
            "R_greedy": describe([r["R"][GREEDY] for r in v8.panel_rows(s)])}
        for s in v8.STRATA
    }
    return facts


def main() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    per_arm, coverage = collect()
    descriptive = descriptives(per_arm)
    analysis = {
        "schema_version": "choice_frontier_v8_analysis_v1",
        "protocol": "docs/experiments/choice-frontier/issue-149-protocol.md",
        "conventions": v8.protocol()["conventions"],
        "coverage": coverage,
        "test_a_primary": test_a(per_arm),
        "test_b_target_contrast": test_b(per_arm),
        "test_c_size": test_c(per_arm),
        "test_d_all_arms": test_d(per_arm),
        "quality": quality(per_arm),
        "descriptive": descriptive,
        "facts": side_facts(),
        "grid": list(GRID),
    }
    analysis["figure"] = figure(descriptive)
    v8.write(v8.OUT / "metrics" / "analysis.json", analysis)
    return {
        "test_a": {k: v["verdict"] for k, v in analysis["test_a_primary"].items()},
        "coverage_missing": {k: len(v["missing"]) for k, v in coverage.items() if v["missing"]},
        "figure": analysis["figure"],
    }


if __name__ == "__main__":
    import json

    print(json.dumps(main(), indent=1))
