#!/usr/bin/env python
"""CPU-only preregistered #135 choice-frontier instrument-validity analysis.

Copy of ``scripts/analyze_choice_frontier_o4.py`` (#133): the same C* planner,
episode inspector, M1-M5 summaries and task-cluster bootstrap (seed 133), pointed
at the frozen v2 panel and zoo, plus the preregistered ``instrument_validity``
ladder test and the descriptive ``adapter_reevaluation`` block.
"""

from __future__ import annotations

import argparse
import gzip
import itertools
import json
import math
import random
import sys
from collections import Counter, deque
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from examples.planning_benchmark_slice.pddl_state import GroundedAction, PDDLStateAuthority  # noqa: E402

MEMBERSHIP = ROOT / "configs/experiments/choice-frontier-v2/membership.json"
EVALUATION = ROOT / "outputs/choice-frontier/v2/evaluation"
OUT = ROOT / "outputs/choice-frontier/v2/metrics"
ZOO = ROOT / "outputs/choice-frontier/v2/zoo"
MS = (1, 1.25, 1.5, 1.75, 2)
WEIGHTS = (0.125, 0.25, 0.25, 0.25, 0.125)
COMPARATORS = (
    "exact_reference",
    "exact-eps-0.25",
    "exact-eps-0.50",
    "exact-eps-0.75",
    "random_valid",
    "hadd-greedy",
    "bfs-order",
    "novelty-first",
    "worst-first",
)
LADDER = ("exact_reference", "exact-eps-0.25", "exact-eps-0.50", "exact-eps-0.75", "random_valid")
STOCHASTIC_SEEDS = 5
ALGORITHMS = ("best_first_add_greedy", "best_first_add_w3")


def load(path):
    with gzip.open(path, "rt") if str(path).endswith(".gz") else open(path) as stream:
        return json.load(stream)


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def shortest_plan(task):
    snapshot = load(ROOT / task["row"]["task_path"])
    authority = PDDLStateAuthority.from_pddl(snapshot["domain_pddl"], snapshot["problem_pddl"])
    initial = authority.initial_state
    queue = deque([initial])
    parents = {initial.state_id: None}
    states = {initial.state_id: initial}
    goal = None
    while queue:
        state = queue.popleft()
        if authority.is_goal(state):
            goal = state
            break
        for action in authority.applicable_actions(state):
            target = authority.apply(state, action).target_state
            if target.state_id not in parents:
                parents[target.state_id] = (state.state_id, action)
                states[target.state_id] = target
                queue.append(target)
    if goal is None:
        raise ValueError("offline BFS could not find goal: " + task["row"]["task_id"])
    chain = []
    cursor = goal.state_id
    while parents[cursor] is not None:
        predecessor, action = parents[cursor]
        chain.append((predecessor, action, cursor))
        cursor = predecessor
    assert cursor == initial.state_id
    chain.reverse()
    cursor_state = initial
    for source, action, target in chain:
        assert cursor_state.state_id == source
        cursor_state = authority.apply(cursor_state, action).target_state
        assert cursor_state.state_id == target
    assert authority.is_goal(cursor_state)
    return {
        "cost": len(chain),
        "states_discovered": len(states),
        "states_expanded": len(parents) - len(queue),
        "plan": [a.serialize() for _, a, _ in chain],
        "verified_pddl_transitions": True,
    }, authority


def inspect_episode(episode, authority, reference, arm, multiplier):
    events = episode["events"]
    cap = episode["decision_cap"]
    assert episode["result"]["decision_count"] == len(events)
    assert episode["result"]["expansion_count"] == sum(
        e["trusted_runtime_result"]["status"] == "expanded" for e in events
    )
    assert len(events) <= cap and episode["result"]["expansion_count"] <= cap
    assert episode["result"]["goal_reached"] == (
        bool(events) and events[-1]["trusted_runtime_result"]["status"] == "goal_reached"
    )
    assert all(e["decision_index"] == i for i, e in enumerate(events))
    parents = {"s0": None}
    states = {"s0": authority.initial_state}
    frontier = {"s0": (0, 0)}
    next_serial = 1
    expanded = 0
    agreements = []
    histogram = Counter()
    first_count = 0
    last_count = 0
    goal = None
    for event in events:
        result = event["trusted_runtime_result"]
        menu = event["menu"]
        choice = json.loads(event["raw_output"]).get("expand_choice") if result["accepted"] else None
        selected = next((entry["state_ref"] for entry in menu if entry["choice"] == choice), None)
        if result["accepted"]:
            assert selected == result["expanded_state_id"]
        if len(menu) >= 2 and selected is not None:
            labels = [entry["choice"] for entry in menu]
            index = labels.index(choice)
            histogram[str(index + 1)] += 1
            first_count += index == 0
            last_count += index == len(labels) - 1
            # The reference heap head is the minimum (priority, generation serial).
            # Reconstruct live serials from admitted candidates in generation order.
            head = min((entry["state_ref"] for entry in menu), key=lambda ref: frontier[ref])
            agreements.append((selected == head, 1 / len(menu)))
        if result["status"] == "goal_reached":
            assert goal is None and selected in states and authority.is_goal(states[selected])
            cursor = selected
            chain = []
            while parents[cursor] is not None:
                prior, action = parents[cursor]
                chain.append((prior, action, cursor))
                cursor = prior
            assert cursor == "s0"
            cursor_state = authority.initial_state
            for prior, action, target in reversed(chain):
                assert states[prior].state_id == cursor_state.state_id
                cursor_state = authority.apply(cursor_state, action).target_state
                assert cursor_state.state_id == states[target].state_id
            assert authority.is_goal(cursor_state)
            goal = {"decision": event["decision_index"] + 1, "preceding_expansions": expanded, "cost": len(chain)}
            break
        if result["status"] != "expanded":
            continue
        assert selected in states
        expanded += 1
        candidate_serials = {}
        for admission in result["admissions"]:
            a = admission["action"]
            action = GroundedAction(a["name"], tuple(a["args"]))
            successor = authority.apply(states[selected], action).target_state
            data = admission["trusted_runtime_result"]
            target = data["target_state_id"]
            if target in states:
                assert states[target].state_id == successor.state_id
            else:
                states[target] = successor
            if data["status"] in ("enqueued", "improved", "reopened"):
                parents[target] = (selected, action)
            # Candidate serials are assigned before admission, using the first
            # generated occurrence of each target within this expansion.
            serial = candidate_serials.setdefault(target, next_serial)
            next_serial += 1
            if data["status"] in ("enqueued", "improved", "reopened"):
                frontier[target] = (data["priority"], serial)
        frontier.pop(selected)
    assert expanded == episode["result"]["expansion_count"]
    r = reference
    solves = {
        str(m): bool(
            goal and goal["decision"] <= math.floor(m * r) and goal["preceding_expansions"] <= math.floor(m * r)
        )
        for m in MS
    }
    if multiplier == 2:
        assert cap in (2 * r, 1) and (cap == 1) == (arm == "pretrained_base")
    return {
        "arm": arm,
        "task": episode.get("task_id", episode.get("instance_id")),
        "algorithm": episode["algorithm"],
        "seed": episode["seed"],
        "multiplier": multiplier,
        "reference_expansions": r,
        "decision_cap": cap,
        "decisions": len(events),
        "expansions": expanded,
        "termination": episode["result"]["termination_reason"],
        "goal": goal,
        "solves": solves,
        "auc": sum(w * solves[str(m)] for w, m in zip(WEIGHTS, MS, strict=False)),
        "rho": expanded / r if goal else None,
        "cost": goal["cost"] if goal else None,
        "teacher_agreements": sum(a for a, _ in agreements),
        "teacher_chance_sum": sum(p for _, p in agreements),
        "teacher_decisions": len(agreements),
        "selected_label_position_histogram": dict(histogram),
        "selected_first_count": first_count,
        "selected_last_count": last_count,
        "classification": "descriptive #135 adapter re-evaluation"
        if arm in ("learned_adapter", "pretrained_base")
        else "preregistered CPU #135",
    }


def percentile(sorted_values, probability):
    if not sorted_values:
        return None
    return sorted_values[min(len(sorted_values) - 1, int(probability * (len(sorted_values) - 1)))]


def bootstrap(values_by_task, tasks, seed=133):
    rng = random.Random(seed)
    keys = list(tasks)
    samples = sorted(mean(values_by_task[t] for t in (rng.choice(keys) for _ in keys)) for _ in range(10000))
    return [percentile(samples, 0.025), percentile(samples, 0.975)]


def summarize(rows, tasks, arms):
    result = {}
    for arm in arms:
        task_rows = {}
        for task in tasks:
            cell_rows = [
                [r for r in rows if r["arm"] == arm and r["task"] == task and r["algorithm"] == alg]
                for alg in ALGORITHMS
            ]
            if any(not cell for cell in cell_rows):
                continue
            curves = {str(m): mean(mean(row["solves"][str(m)] for row in cell) for cell in cell_rows) for m in MS}
            flat = [row for cell in cell_rows for row in cell]
            solved_cells = [[r for r in cell if r["solves"]["2"]] for cell in cell_rows]
            kappas = [mean(r["kappa"] for r in cell) for cell in solved_cells if cell]
            rho_logs = [mean(math.log(r["rho"]) for r in cell) for cell in solved_cells if cell]
            task_rows[task] = {
                "solve_fraction": curves,
                "auc": sum(w * curves[str(m)] for w, m in zip(WEIGHTS, MS, strict=False)),
                "solved_at_2": curves["2"],
                "episodes": len(flat),
                "kappa_solved_only": mean(kappas) if kappas else None,
                "rho_geometric_solved_only": math.exp(mean(rho_logs)) if rho_logs else None,
            }
        if not task_rows:
            result[arm] = {"missing_tasks": list(tasks)}
            continue
        all_rows = [r for r in rows if r["arm"] == arm and r["task"] in task_rows]
        diagnostic = [r for r in all_rows if r["teacher_decisions"]]
        histogram = Counter()
        for row in diagnostic:
            histogram.update(row["selected_label_position_histogram"])
        teacher_n = sum(r["teacher_decisions"] for r in diagnostic)
        censor = {}
        for m in MS:
            key = str(m)
            # Mean over task cells, then algorithms; never let the five random seeds
            # or two algorithms reweight the nine independent task units.
            observed = []
            solved = []
            censored = 0
            early_invalid = 0
            other_early = 0
            for task in task_rows:
                for alg in ALGORITHMS:
                    cell = [r for r in all_rows if r["task"] == task and r["algorithm"] == alg]
                    observed.append(
                        mean(
                            min(r["expansions"], math.floor(m * r["reference_expansions"])) / r["reference_expansions"]
                            for r in cell
                        )
                    )
                    solved.append(mean(r["solves"][key] for r in cell))
                    for r in cell:
                        if r["solves"][key]:
                            continue
                        budget = math.floor(m * r["reference_expansions"])
                        if r["goal"] is not None or (
                            r["termination"] in ("decision_budget_exhausted", "expansion_budget_exhausted")
                            and (r["decisions"] >= budget or r["expansions"] >= budget)
                        ):
                            censored += 1
                        elif r["termination"] == "deterministic_invalid_operation":
                            early_invalid += 1
                        else:
                            other_early += 1
            censor[key] = {
                "solved_fraction": mean(solved),
                "mean_observed_min_expansions_cap_over_reference": mean(observed),
                "right_censored_count": censored,
                "early_invalid_count": early_invalid,
                "other_early_stop_or_administrative_cap_count": other_early,
                "episodes": len(all_rows),
            }
        aucs = {task: data["auc"] for task, data in task_rows.items()}
        result[arm] = {
            "per_task": task_rows,
            "tasks_present": len(task_rows),
            "missing_tasks": sorted(set(tasks) - task_rows.keys()),
            "m1_auc": mean(aucs.values()),
            "m1_task_cluster_95pct_ci_10000_seed133": bootstrap(aucs, list(task_rows)),
            "m2_censoring_by_budget": censor,
            "m2_solved_only_geometric_rho_task_weighted": math.exp(
                mean(
                    math.log(x["rho_geometric_solved_only"])
                    for x in task_rows.values()
                    if x["rho_geometric_solved_only"] is not None
                )
            )
            if any(x["rho_geometric_solved_only"] is not None for x in task_rows.values())
            else None,
            "m3_solved_coverage": censor["2"]["solved_fraction"],
            "m3_solved_kappa_mean_task_weighted": mean(
                x["kappa_solved_only"] for x in task_rows.values() if x["kappa_solved_only"] is not None
            )
            if any(x["kappa_solved_only"] is not None for x in task_rows.values())
            else None,
            "m4_teacher_agreement": {
                "on_policy_decisions_k_ge_2": teacher_n,
                "observed": sum(r["teacher_agreements"] for r in diagnostic) / teacher_n if teacher_n else None,
                "chance": sum(r["teacher_chance_sum"] for r in diagnostic) / teacher_n if teacher_n else None,
                "observed_minus_chance": sum(r["teacher_agreements"] - r["teacher_chance_sum"] for r in diagnostic)
                / teacher_n
                if teacher_n
                else None,
                "selected_first_count": sum(r["selected_first_count"] for r in diagnostic),
                "selected_last_count": sum(r["selected_last_count"] for r in diagnostic),
                "selected_first_rate": sum(r["selected_first_count"] for r in diagnostic) / teacher_n
                if teacher_n
                else None,
                "selected_last_rate": sum(r["selected_last_count"] for r in diagnostic) / teacher_n
                if teacher_n
                else None,
                "chance_first_or_last": sum(r["teacher_chance_sum"] for r in diagnostic) / teacher_n
                if teacher_n
                else None,
                "selected_label_position_histogram": dict(sorted(histogram.items(), key=lambda x: int(x[0]))),
            },
        }
    return result


def instrument_validity(summary, tasks):
    """Preregistered adjacent-pair ladder test on per-task M1 (seeds, then algorithms averaged)."""

    pairs = []
    for left, right in itertools.pairwise(LADDER):
        per_task = {t: summary[left]["per_task"][t]["auc"] - summary[right]["per_task"][t]["auc"] for t in tasks}
        pairs.append(
            {
                "left": left,
                "right": right,
                "m1_left": summary[left]["m1_auc"],
                "m1_right": summary[right]["m1_auc"],
                "difference": mean(per_task.values()),
                # Fresh random.Random(133) per pair: paired task-cluster resampling.
                "ci95": bootstrap(per_task, tasks),
                "per_task_difference": per_task,
            }
        )
    if all(p["ci95"][0] > 0 for p in pairs):
        verdict = "PASS"
    elif all(p["difference"] > 0 for p in pairs):
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"
    return {
        "rule": (
            "PASS: all four paired task-cluster 95% lower bounds > 0; PARTIAL: all four point "
            "estimates > 0 but some lower bound <= 0; FAIL: any point estimate <= 0"
        ),
        "bootstrap": {"seed": 133, "draws": 10000, "interval": "95% percentile", "unit": "task cluster"},
        "aggregation": "each arm averaged over its seeds within (task, algorithm), then over the two algorithms",
        "tasks": len(tasks),
        "pairs": pairs,
        "verdict": verdict,
    }


def adapter_reevaluation(tasks, rows_by_id, authorities, optimal):
    evaluation_path = EVALUATION / "evaluation.json"
    if not evaluation_path.is_file():
        return {"status": "pending: GPU adapter re-evaluation not finalized"}
    evaluation = load(evaluation_path)
    assert evaluation["complete"] and not evaluation["missing_bindings"]
    bindings = [b for b in load(EVALUATION / "bindings.json")["bindings"] if b["kind"] == "models"]
    assert evaluation["episodes_replayed"] == len(bindings) == 4 * len(tasks)
    records = []
    for binding in bindings:
        name = f"{binding['algorithm']}-{binding['condition']}-{binding['seed']}.json.gz"
        episode = load(EVALUATION / "episodes" / binding["task_id"].replace("/", "__") / name)
        assert (episode["task_id"], episode["algorithm"], episode["condition"], episode["seed"]) == (
            binding["task_id"],
            binding["algorithm"],
            binding["condition"],
            binding["seed"],
        )
        reference = rows_by_id[binding["task_id"]]["reference_costs"][binding["algorithm"]]["expansions"]
        row = inspect_episode(episode, authorities[binding["task_id"]], reference, binding["condition"], 2)
        row["c_star"] = optimal[row["task"]]["cost"]
        row["kappa"] = row["cost"] / row["c_star"] if row["cost"] is not None else None
        records.append(row)
    summary = summarize(records, tasks, ("learned_adapter", "pretrained_base"))
    for arm in summary.values():
        arm["teacher_agreement_minus_chance"] = arm["m4_teacher_agreement"]["observed_minus_chance"]
    return {
        "status": "descriptive only; frozen #132 adapters, seed 17, no retraining; not part of the validity test",
        "episodes": len(records),
        "independent_replay": "scripts/run_choice_frontier_v2.py finalize (every model episode replayed)",
        "pretrained_base_cap": "frozen #132 one-call cap",
        **summary,
        "records": records,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-zoo", action="store_true")
    args = parser.parse_args()
    membership = load(MEMBERSHIP)
    tasks = membership["task_ids"]
    rows_by_id = {task["row"]["task_id"]: task["row"] for task in membership["tasks"]}
    assert sorted(rows_by_id) == tasks
    optimal, authorities = {}, {}
    for task in tasks:
        optimal[task], authorities[task] = shortest_plan({"row": rows_by_id[task]})
        assert optimal[task]["cost"] == membership["per_task"][task]["cstar"]
    save("optimal-costs.json", optimal)
    manifest_path = ZOO / "manifest.json"
    if not manifest_path.is_file():
        if args.require_zoo:
            raise FileNotFoundError(manifest_path)
        print("Zoo not yet present; optimal costs written")
        return
    manifest = load(manifest_path)
    bindings = manifest["bindings"]
    assert len(bindings) == manifest["expected_bindings"] == 58 * len(tasks)
    assert len({(b["task_id"], b["algorithm"], b["arm"], b["multiplier"], b["seed"]) for b in bindings}) == len(bindings)
    missing = [
        b
        for b in bindings
        if b["status"] != "observed" or b["replay_status"] != "passed" or not (ROOT / b["episode_path"]).is_file()
    ]
    assert not missing, f"missing or unverified comparator episodes: {missing[:3]}"
    records = []
    for binding in bindings:
        arm = binding["arm"]
        episode = load(ROOT / binding["episode_path"])
        assert episode.get("selector", episode["arm"]) == arm
        assert (
            episode["instance_id"] == binding["task_id"]
            and episode["algorithm"] == binding["algorithm"]
            and episode["seed"] == binding["seed"]
            and binding["multiplier"] == 2
        )
        ref = rows_by_id[binding["task_id"]]["reference_costs"][binding["algorithm"]]["expansions"]
        row = inspect_episode(episode, authorities[binding["task_id"]], ref, arm, 2)
        row["c_star"] = optimal[row["task"]]["cost"]
        row["kappa"] = row["cost"] / row["c_star"] if row["cost"] is not None else None
        records.append(row)
    for arm in COMPARATORS:
        for task in tasks:
            for algorithm in ALGORITHMS:
                actual = sum(r["arm"] == arm and r["task"] == task and r["algorithm"] == algorithm for r in records)
                deterministic = arm in ("exact_reference", "bfs-order", "novelty-first", "worst-first")
                assert actual == (1 if deterministic else STOCHASTIC_SEEDS), (arm, task, algorithm, actual)
    summary = summarize(records, tasks, COMPARATORS)
    random_task = {task: summary["random_valid"]["per_task"][task]["solved_at_2"] for task in tasks}
    D = [task for task in tasks if 0 < random_task[task] < 1]
    report = {
        "status": "preregistered #135 CPU instrument-validity analysis (issue-135-protocol.md)",
        "membership_sha256": membership["membership_sha256"],
        "episode_accounting": {
            "cpu_episodes": len(records),
            "expected": manifest["expected_bindings"],
            "missing": missing,
            "replay_passed": sum(b["replay_status"] == "passed" for b in bindings),
        },
        "optimal_costs": {task: optimal[task]["cost"] for task in tasks},
        "arms": summary,
        "instrument_validity": instrument_validity(summary, tasks),
        "descriptive_only_arms": ["hadd-greedy", "bfs-order", "novelty-first", "worst-first"],
        "m5_informative_tasks_D": D,
        "m5_random_controls_only_by_task": random_task,
        "m5_D_descriptive": summarize(records, D, COMPARATORS) if D else {},
        "adapter_reevaluation": adapter_reevaluation(tasks, rows_by_id, authorities, optimal),
        "interpretation": (
            "Measures the instrument (does M1 order a graded exact-to-random selector ladder), "
            "not model planning ability. hadd-greedy and exact-eps read privileged information "
            "(h_add, heap head). M2/M3 condition on solving."
        ),
    }
    save("all-episode-metrics.json", {"records": records})
    save("analysis.json", report)
    print(json.dumps(report["instrument_validity"], indent=2, default=str))
    print({arm: round(summary[arm]["m1_auc"], 4) for arm in COMPARATORS})


if __name__ == "__main__":
    main()
