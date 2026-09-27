#!/usr/bin/env python
"""Pre-registered #146 analysis (``docs/experiments/choice-frontier/issue-146-protocol.md`` §9).

Reads the v7 controls, learned and zero-shot episodes and the reused #139 additive x visual
learned episodes; writes ``outputs/choice-frontier/v7/metrics/analysis.json``. No model calls.

- Test 1 (primary): per (algorithm, observation) cell on the pooled 23 tasks,
  D3 = mean_s M1(learned, s) - M1(random_valid 5-seed mean); #138 verdict rule; Holm over 12 cells.
- Test 2: Test 1 per panel (P2, P2u).
- Test 3: text/image split contrasts on learned M1 and on D3, per algorithm and pooled.
- Secondary: learned vs exact, learned vs zero-shot, zero-shot vs random, kappa-head agreement,
  overflow and invalid counts. Sensitivity: exclude (task, algorithm) pairs where exact overflows.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.node_choice import (  # noqa: E402
    ADDITIVE_ALGORITHMS,
    ALGORITHMS,
    OBSERVATIONS,
    NodeChoiceSession,
    NodeChoiceTask,
)
from scripts import run_choice_frontier_v7 as v7  # noqa: E402
from scripts.analyze_choice_frontier_v2 import MS, WEIGHTS, bootstrap, percentile  # noqa: E402

DELTA = 0.05
DRAWS = 10000
BOOTSTRAP_SEED = 133
OUT = ROOT / v7.OUT / "metrics"
V4_PANELS = ROOT / "outputs/choice-frontier/v4/panels"


# ---------------------------------------------------------------------------- episodes


def reused_additive_visual(task_id: str, group: str, algorithm: str, seed: int) -> Path:
    name = f"{algorithm}-learned_adapter-s{seed}-17.json.gz"
    return V4_PANELS / group / "evaluation" / "episodes" / task_id.replace("/", "__") / name


def learned_path(task_id: str, group: str, algorithm: str, observation: str, seed: int) -> Path:
    if algorithm in ADDITIVE_ALGORITHMS and observation == "visual":
        return reused_additive_visual(task_id, group, algorithm, seed)
    cell = {"algorithm": algorithm, "observation": observation, "condition": "learned_adapter", "seed": seed}
    return v7.episode_paths("evaluation", cell, task_id)[0]


def zero_shot_path(task_id: str, algorithm: str, observation: str) -> Path:
    cell = {"algorithm": algorithm, "observation": observation, "condition": "zero_shot_base", "seed": 0}
    return v7.episode_paths("zeroshot", cell, task_id)[0]


def control_path(task_id: str, algorithm: str, observation: str, arm: str, seed: int) -> Path:
    return ROOT / v7.control_path(task_id, algorithm, observation, arm, seed)


def episode_row(report: dict, r: int) -> dict:
    """M1 row from one episode (the #133 prefix rule): goal decision and preceding expansions within floor(m R)."""

    events = report["events"]
    goal, expanded = None, 0
    for index, event in enumerate(events):
        status = event["trusted_runtime_result"]["status"]
        if status == "goal_reached":
            goal = {"decision": index + 1, "preceding_expansions": expanded}
            break
        if status == "expanded":
            expanded += 1
    assert report["result"]["goal_reached"] == (goal is not None)
    assert len(events) <= int(report["decision_cap"]) == 2 * r
    solves = {
        str(m): bool(
            goal and goal["decision"] <= math.floor(m * r) and goal["preceding_expansions"] <= math.floor(m * r)
        )
        for m in MS
    }
    return {
        "auc": sum(w * solves[str(m)] for w, m in zip(WEIGHTS, MS, strict=True)),
        "solved_at_2": solves["2"],
        "termination": report["result"]["termination_reason"],
        "decisions": len(events),
        "invalid": report["result"]["invalid_operation_count"],
        "overflow": report["result"]["termination_reason"] == "observation_overflow",
    }


def agreement(report: dict, row: dict, algorithm: str) -> tuple[float, float, int]:
    """kappa-head agreement minus chance on decisions with menu >= 2 (menus re-derived by the trusted runtime)."""

    authority, _source = v7.authority_of(row["task_path"])
    session = NodeChoiceSession(
        authority=authority,
        task=NodeChoiceTask(row["task_id"], row["domain"], algorithm, row["R"][algorithm]),
        observation="text",
        arm="process_sft",
        seed=17,
    )
    hits = chance = 0.0
    count = 0
    for event in report["events"]:
        request = session.next_request()
        if request is None or [dict(e) for e in request.menu_binding] != event["menu"]:
            raise ValueError("agreement replay menu differs")
        if len(event["menu"]) >= 2 and event["trusted_runtime_result"]["accepted"]:
            head = session.kappa_head_ref()
            chosen = event["trusted_runtime_result"]["expanded_state_id"]
            hits += chosen == head
            chance += 1 / len(event["menu"])
            count += 1
        session.submit_output(event["raw_output"])
    return hits, chance, count


# ---------------------------------------------------------------------------- statistics


def draws(values: dict[str, float], tasks: list[str]) -> list[float]:
    rng = random.Random(BOOTSTRAP_SEED)
    return sorted(mean(values[t] for t in (rng.choice(tasks) for _ in tasks)) for _ in range(DRAWS))


def interval(values: dict[str, float], tasks: list[str]) -> dict:
    samples = draws(values, tasks)
    ci = [percentile(samples, 0.025), percentile(samples, 0.975)]
    if ci != bootstrap(values, tasks, seed=BOOTSTRAP_SEED):
        raise ValueError("v7 bootstrap differs from the frozen #133 bootstrap")
    return {
        "point": mean(values[t] for t in tasks),
        "ci95": ci,
        "p_one_sided_le_0": sum(1 for s in samples if s <= 0) / len(samples),
        "tasks": len(tasks),
    }


def verdict_138(stat: dict, seed_points: list[float]) -> str:
    lo, hi = stat["ci95"]
    if lo > 0 and stat["point"] >= DELTA and all(p > 0 for p in seed_points):
        return "POSITIVE"
    if -DELTA < lo and hi < DELTA:
        return "EQUIVALENT"
    if hi < 0:
        return "NEGATIVE"
    return "INCONCLUSIVE"


def separation(stat: dict) -> str:
    lo, hi = stat["ci95"]
    return "SEPARATED_ABOVE" if lo > 0 else "SEPARATED_BELOW" if hi < 0 else "NOT_SEPARATED"


def holm(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    order = sorted(pvalues, key=lambda k: pvalues[k])
    result, stopped = {}, False
    for rank, key in enumerate(order):
        if not stopped and pvalues[key] <= alpha / (len(order) - rank):
            result[key] = True
        else:
            stopped = True
            result[key] = False
    return result


# ---------------------------------------------------------------------------- main


def collect() -> dict:
    rows = {r["task_id"]: r for r in v7.panel_rows() if r["group"] in v7.PANELS}
    data: dict = {"missing": [], "cells": {}}
    for algorithm in ALGORITHMS:
        for observation in OBSERVATIONS:
            cell = {"learned": {}, "random": {}, "exact": {}, "zero_shot": {}, "agreement": {}, "counts": {}}
            gate = None
            if not (algorithm in ADDITIVE_ALGORITHMS and observation == "visual"):
                gate = v7.smoke_verdict(algorithm, observation)
            cell["smoke_gate"] = gate if gate is not None else ("REUSED_139" if observation == "visual" else "MISSING")
            for task_id, row in rows.items():
                r = row["R"][algorithm]
                exact_report = v7.load(control_path(task_id, algorithm, observation, "exact_reference", 17))
                cell["exact"][task_id] = episode_row(exact_report, r)
                cell["random"][task_id] = [
                    episode_row(v7.load(control_path(task_id, algorithm, observation, "random_valid", s)), r)
                    for s in v7.RANDOM_SEEDS
                ]
                path = zero_shot_path(task_id, algorithm, observation)
                if path.exists():
                    cell["zero_shot"][task_id] = episode_row(v7.load(path), r)
                else:
                    data["missing"].append(["zero_shot", algorithm, observation, task_id])
                if cell["smoke_gate"] in ("PASS", "REUSED_139"):
                    for seed in v7.SEEDS:
                        path = learned_path(task_id, row["group"], algorithm, observation, seed)
                        if not path.exists():
                            data["missing"].append(["learned", algorithm, observation, seed, task_id])
                            continue
                        report = v7.load(path)
                        cell["learned"].setdefault(task_id, {})[seed] = episode_row(report, r)
                        cell["agreement"].setdefault(seed, []).append(agreement(report, row, algorithm))
            data["cells"][f"{algorithm}/{observation}"] = cell
    return data


def m1_tables(cell: dict, tasks: list[str]) -> dict:
    learned = {t: mean(cell["learned"][t][s]["auc"] for s in v7.SEEDS) for t in tasks}
    random_ = {t: mean(x["auc"] for x in cell["random"][t]) for t in tasks}
    return {
        "learned": learned,
        "random": random_,
        "exact": {t: cell["exact"][t]["auc"] for t in tasks},
        "d3": {t: learned[t] - random_[t] for t in tasks},
        "per_seed_d": {s: mean(cell["learned"][t][s]["auc"] - random_[t] for t in tasks) for s in v7.SEEDS},
    }


def complete_tasks(cell: dict, tasks: list[str]) -> list[str]:
    return [t for t in tasks if t in cell["learned"] and all(s in cell["learned"][t] for s in v7.SEEDS)]


def test_1(data: dict, tasks: list[str], identity: dict) -> dict:
    result, pvalues = {}, {}
    for key, cell in data["cells"].items():
        algorithm = key.split("/")[0]
        entry: dict = {"smoke_gate": cell["smoke_gate"], "identity_gate": identity["verdicts"][algorithm]}
        present = complete_tasks(cell, tasks)
        if cell["smoke_gate"] == "FAIL":
            entry["verdict"] = "SMOKE_FAIL"
        elif identity["verdicts"][algorithm] != "CHOICE_SENSITIVE":
            entry["verdict"] = "ZERO_DECISION_HEADROOM"
        elif not present:
            entry["verdict"] = "MISSING"
        else:
            tables = m1_tables(cell, present)
            stat = interval(tables["d3"], present)
            entry.update(
                d3=stat,
                per_seed=tables["per_seed_d"],
                verdict=verdict_138(stat, list(tables["per_seed_d"].values())),
                m1_learned=interval(tables["learned"], present),
                m1_random=interval(tables["random"], present),
                m1_exact=interval(tables["exact"], present),
                solved_at_2={
                    "learned": mean(mean(cell["learned"][t][s]["solved_at_2"] for s in v7.SEEDS) for t in present),
                    "random": mean(mean(x["solved_at_2"] for x in cell["random"][t]) for t in present),
                    "exact": mean(cell["exact"][t]["solved_at_2"] for t in present),
                },
                missing_tasks=sorted(set(tasks) - set(present)),
            )
            pvalues[key] = stat["p_one_sided_le_0"]
        result[key] = entry
    for key, passed in holm(pvalues).items():
        result[key]["beats_random_holm"] = passed
    return result


def secondary(data: dict, tasks: list[str]) -> dict:
    result = {}
    for key, cell in data["cells"].items():
        present = complete_tasks(cell, tasks)
        zs = [t for t in tasks if t in cell["zero_shot"]]
        entry: dict = {}
        if present:
            tables = m1_tables(cell, present)
            entry["learned_minus_exact"] = interval(
                {t: tables["learned"][t] - tables["exact"][t] for t in present}, present
            )
            both = [t for t in present if t in cell["zero_shot"]]
            if both:
                entry["learned_minus_zero_shot"] = interval(
                    {t: tables["learned"][t] - cell["zero_shot"][t]["auc"] for t in both}, both
                )
            agreements = {}
            for seed, triples in cell["agreement"].items():
                hits, chance, count = (sum(x[i] for x in triples) for i in range(3))
                agreements[str(seed)] = {
                    "decisions": count,
                    "observed": hits / count if count else None,
                    "chance": chance / count if count else None,
                    "observed_minus_chance": (hits - chance) / count if count else None,
                }
            entry["kappa_head_agreement"] = agreements
        if zs:
            random_ = {t: mean(x["auc"] for x in cell["random"][t]) for t in zs}
            entry["zero_shot_minus_random"] = interval({t: cell["zero_shot"][t]["auc"] - random_[t] for t in zs}, zs)
            entry["m1_zero_shot"] = mean(cell["zero_shot"][t]["auc"] for t in zs)
        counts = {}
        for arm, episodes in (
            ("exact", [cell["exact"][t] for t in tasks]),
            ("random", [x for t in tasks for x in cell["random"][t]]),
            ("learned", [cell["learned"][t][s] for t in cell["learned"] for s in cell["learned"][t]]),
            ("zero_shot", [cell["zero_shot"][t] for t in zs]),
        ):
            counts[arm] = {
                "episodes": len(episodes),
                "overflow": sum(e["overflow"] for e in episodes),
                "invalid_terminations": sum(e["termination"] == "deterministic_invalid_operation" for e in episodes),
            }
        entry["counts"] = counts
        result[key] = entry
    return result


def split_contrasts(data: dict, tasks: list[str], exclude: set[tuple[str, str]] | None = None) -> dict:
    exclude = exclude or set()
    pairs = (("text", "visual"), ("multimodal", "visual"), ("text", "multimodal"))
    result: dict = {}
    for measure in ("learned", "d3"):
        block: dict = {}
        per_algorithm_values: dict[str, dict[str, dict[str, float]]] = {}
        for algorithm in ALGORITHMS:
            cells = {o: data["cells"][f"{algorithm}/{o}"] for o in OBSERVATIONS}
            present = [
                t
                for t in tasks
                if (t, algorithm) not in exclude and all(t in complete_tasks(cells[o], tasks) for o in OBSERVATIONS)
            ]
            if not present:
                block[algorithm] = {"missing": True}
                continue
            tables = {o: m1_tables(cells[o], present)[measure] for o in OBSERVATIONS}
            entry = {}
            for a, b in pairs:
                diff = {t: tables[a][t] - tables[b][t] for t in present}
                per_algorithm_values.setdefault(f"{a}-{b}", {})[algorithm] = diff
                stat = interval(diff, present)
                entry[f"{a}-{b}"] = {**stat, "verdict": separation(stat)}
            block[algorithm] = entry
        pooled = {}
        for pair, by_algorithm in per_algorithm_values.items():
            common = [t for t in tasks if any(t in values for values in by_algorithm.values())]
            values = {t: mean(v[t] for v in by_algorithm.values() if t in v) for t in common}
            stat = interval(values, common)
            pooled[pair] = {**stat, "verdict": separation(stat), "algorithms": sorted(by_algorithm)}
        block["pooled"] = pooled
        result[measure] = block
    return result


def exact_overflow_pairs(data: dict, tasks: list[str]) -> set[tuple[str, str]]:
    return {
        (t, algorithm)
        for algorithm in ALGORITHMS
        for t in tasks
        if any(data["cells"][f"{algorithm}/{o}"]["exact"][t]["overflow"] for o in OBSERVATIONS)
    }


def sensitivity(data: dict, tasks: list[str], identity: dict) -> dict:
    excluded = exact_overflow_pairs(data, tasks)
    result = {"excluded_pairs": sorted(excluded), "test_1": {}}
    for key, cell in data["cells"].items():
        algorithm = key.split("/")[0]
        kept = [t for t in complete_tasks(cell, tasks) if (t, algorithm) not in excluded]
        if not kept or cell["smoke_gate"] == "FAIL" or identity["verdicts"][algorithm] != "CHOICE_SENSITIVE":
            continue
        tables = m1_tables(cell, kept)
        stat = interval(tables["d3"], kept)
        result["test_1"][key] = {"d3": stat, "verdict": verdict_138(stat, list(tables["per_seed_d"].values()))}
    result["test_3"] = split_contrasts(data, tasks, excluded)
    return result


def main() -> dict:
    identity = v7.load(v7.OUT / "controls" / "identity-gate.json")
    data = collect()
    pooled = v7.pooled_task_ids()
    by_panel = {p: [r["task_id"] for r in v7.panel_rows(p)] for p in v7.PANELS}
    analysis = {
        "schema_version": "choice_frontier_v7_analysis_v1",
        "protocol_id": v7.protocol()["protocol_id"],
        "identity_gate": identity["verdicts"],
        "missing": data["missing"],
        "test_1_pooled": test_1(data, pooled, identity),
        "test_2_per_panel": {p: test_1(data, tasks, identity) for p, tasks in by_panel.items()},
        "test_3_split": split_contrasts(data, pooled),
        "secondary": secondary(data, pooled),
        "sensitivity_exact_overflow_excluded": sensitivity(data, pooled, identity),
        "per_task": {
            key: {
                t: {
                    "exact": cell["exact"][t]["auc"],
                    "random": mean(x["auc"] for x in cell["random"][t]),
                    "learned": {s: cell["learned"][t][s]["auc"] for s in cell["learned"].get(t, {})},
                    "zero_shot": cell["zero_shot"][t]["auc"] if t in cell["zero_shot"] else None,
                }
                for t in pooled
            }
            for key, cell in data["cells"].items()
        },
    }
    v7.write(OUT / "analysis.json", analysis)
    return {
        "test_1": {k: v.get("verdict") for k, v in analysis["test_1_pooled"].items()},
        "missing": len(data["missing"]),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(main(), indent=1))
