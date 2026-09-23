#!/usr/bin/env python
"""CPU-only, post-hoc #132 and preregistered #133 choice-frontier analysis."""

from __future__ import annotations

import argparse
import gzip
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

BASE = ROOT / "outputs/choice-frontier/v1/evaluation"
OUT = ROOT / "outputs/choice-frontier/o4/metrics"
ZOO = ROOT / "outputs/choice-frontier/o4/zoo"
MS = (1, 1.25, 1.5, 1.75, 2)
WEIGHTS = (0.125, 0.25, 0.25, 0.25, 0.125)
COMPARATORS = ("bfs-order", "novelty-first", "worst-first", "exact_reference", "random_valid")
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
        "classification": "post-hoc exploratory #132"
        if multiplier == 2 and arm in ("learned_adapter", "pretrained_base", "random_valid", "exact_reference")
        else "preregistered CPU #133",
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


def paired_report(rows, tasks):
    tests = []
    paired = {}
    rng = random.Random(133)
    for comparator in COMPARATORS:
        metrics = {}
        for metric in ("m1_auc", "m2_log_rho", "m3_kappa"):
            per_task = {}
            paired_cells = {}
            co_solved_values = {}
            for task in tasks:
                contrasts = []
                for alg in ALGORITHMS:
                    lhs = [
                        r for r in rows if r["task"] == task and r["algorithm"] == alg and r["arm"] == "learned_adapter"
                    ]
                    rhs = [r for r in rows if r["task"] == task and r["algorithm"] == alg and r["arm"] == comparator]
                    if len(lhs) != 1 or not rhs:
                        continue
                    learned = lhs[0]
                    if metric == "m1_auc":
                        contrasts.append(learned["auc"] - mean(r["auc"] for r in rhs))
                    elif learned["solves"]["2"]:
                        valid = [r for r in rhs if r["solves"]["2"]]
                        if valid:
                            co_solved_values.setdefault(task, []).append(
                                (
                                    math.log(learned["rho"]) if metric == "m2_log_rho" else learned["kappa"],
                                    mean(math.log(r["rho"]) if metric == "m2_log_rho" else r["kappa"] for r in valid),
                                )
                            )
                            if metric == "m2_log_rho":
                                contrasts.append(mean(math.log(r["rho"]) for r in valid) - math.log(learned["rho"]))
                            else:
                                contrasts.append(mean(r["kappa"] for r in valid) - learned["kappa"])
                            paired_cells[task] = paired_cells.get(task, 0) + len(valid)
                if contrasts:
                    per_task[task] = mean(contrasts)
            # Positive contrasts favor learned for all three metrics.
            adequate = len(per_task) >= 2 and (metric == "m1_auc" or any(abs(v) > 1e-12 for v in per_task.values()))
            nulls = []
            if adequate:
                for _ in range(10000):
                    sampled = [per_task[t] for t in (rng.choice(tasks) for _ in tasks) if t in per_task]
                    if sampled:
                        nulls.append(mean(sampled))
            estimate = mean(per_task.values()) if per_task else None
            p = (1 + sum(v <= 0 for v in nulls)) / (1 + len(nulls)) if adequate else None
            interval = [percentile(sorted(nulls), 0.025), percentile(sorted(nulls), 0.975)] if adequate else None
            entry = {
                "difference_favoring_learned": estimate,
                "per_task_difference": per_task,
                "co_solved_comparator_seed_pairs_by_task": paired_cells if metric != "m1_auc" else None,
                "conditional_on_co_solved": metric != "m1_auc",
                "status": "defined" if adequate else "undefined_or_uninformative",
                "task_cluster_resamples_requested": 10000,
                "resamples_with_co_solved_support": len(nulls) if adequate else None,
                "one_sided_bootstrap_p": p,
                "cluster_bootstrap_95pct_ci": interval,
            }
            if metric != "m1_auc":
                left = {task: mean(a for a, _ in values) for task, values in co_solved_values.items()}
                right = {task: mean(b for _, b in values) for task, values in co_solved_values.items()}
                entry["paired_co_solved_cells_by_task"] = {
                    task: len(values) for task, values in co_solved_values.items()
                }
                entry[
                    "learned_co_solved_geometric_mean_rho" if metric == "m2_log_rho" else "learned_co_solved_mean_kappa"
                ] = (math.exp(mean(left.values())) if metric == "m2_log_rho" else mean(left.values())) if left else None
                entry[
                    "comparator_co_solved_geometric_mean_rho"
                    if metric == "m2_log_rho"
                    else "comparator_co_solved_mean_kappa"
                ] = (
                    (math.exp(mean(right.values())) if metric == "m2_log_rho" else mean(right.values()))
                    if right
                    else None
                )
            metrics[metric] = entry
            tests.append((comparator, metric, entry))
        paired[comparator] = metrics
    valid = sorted(
        (entry["one_sided_bootstrap_p"], cmp, metric, entry)
        for cmp, metric, entry in tests
        if entry["one_sided_bootstrap_p"] is not None
    )
    running = 0
    # Holm family size remains 15 even when a contrast is undefined: an
    # undefined test consumes a hypothesis, but cannot be called a win.
    for index, (p, _cmp, _metric, entry) in enumerate(valid):
        running = max(running, min(1, p * (15 - index)))
        entry["holm_adjusted_p_15_test_family"] = running
    for cmp in COMPARATORS:
        metrics = paired[cmp]
        paired[cmp]["dominance"] = {
            "descriptive_strict_pareto": all(
                metrics[m]["difference_favoring_learned"] is not None and metrics[m]["difference_favoring_learned"] >= 0
                for m in ("m1_auc", "m2_log_rho", "m3_kappa")
            )
            and any(metrics[m]["difference_favoring_learned"] > 0 for m in ("m1_auc", "m2_log_rho", "m3_kappa")),
            "inferential_positive_after_holm": all(
                metrics[m].get("holm_adjusted_p_15_test_family", 1) > 0
                and metrics[m].get("holm_adjusted_p_15_test_family", 1) <= 0.05
                and (metrics[m]["difference_favoring_learned"] or 0) >= 0
                for m in ("m1_auc", "m2_log_rho", "m3_kappa")
            )
            and any((metrics[m]["difference_favoring_learned"] or 0) > 0 for m in ("m1_auc", "m2_log_rho", "m3_kappa")),
        }
    return {
        "scope": "5 comparators x 3 metrics = 15 one-sided paired task-cluster hypotheses, Holm step-down",
        "undefined_tests": 15 - len(valid),
        "comparisons": paired,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-zoo", action="store_true")
    args = parser.parse_args()
    protocol = load(ROOT / "configs/experiments/choice-frontier/choice-frontier-protocol-v1.json")
    tasks = protocol["evaluation"]["membership"]
    panel = load(ROOT / protocol["evaluation"]["panel"])
    panel_by_id = {row["row"]["task_id"]: row for row in panel["tasks"]}
    optimal, authorities = {}, {}
    for task in tasks:
        optimal[task], authorities[task] = shortest_plan(panel_by_id[task])
    save("optimal-costs.json", optimal)
    original = sorted((BASE / "episodes").glob("**/*.json.gz"))
    bindings = load(BASE / "bindings.json")["bindings"]
    assert len(original) == len(bindings) == 144
    expected = {(b["task_id"], b["algorithm"], b["condition"], b["seed"]) for b in bindings}
    assert len(expected) == 144
    records = []
    for path in original:
        episode = load(path)
        identity = (episode["task_id"], episode["algorithm"], episode["condition"], episode["seed"])
        assert identity in expected
        expected.remove(identity)
        reference = panel_by_id[episode["task_id"]]["row"]["reference_costs"][episode["algorithm"]]["expansions"]
        records.append(inspect_episode(episode, authorities[episode["task_id"]], reference, episode["condition"], 2))
    assert not expected
    for row in records:
        row["c_star"] = optimal[row["task"]]["cost"]
        row["kappa"] = row["cost"] / row["c_star"] if row["cost"] is not None else None
    save(
        "stored-144-episodes.json", {"count": len(records), "original_binding_coverage": "complete", "records": records}
    )
    native = {}
    for task in tasks:
        references = panel_by_id[task]["row"]["reference_costs"]
        native[task] = {
            alg: {
                "decisions": references[alg]["decisions"],
                "expansions": references[alg]["expansions"],
                "source_path": panel_by_id[task]["reference_paths"][alg],
            }
            for alg in ("bfs", "best_first_width", *ALGORITHMS)
        }
        for alg in native[task]:
            ref = load(ROOT / native[task][alg]["source_path"])["result"]
            assert (
                ref["decision_count"] == native[task][alg]["decisions"]
                and ref["expansion_count"] == native[task][alg]["expansions"]
                and ref["goal_reached"]
            )
    save(
        "native-four-algorithm-reference-costs.json",
        {
            "note": (
                "Native trace decisions/expansions are not shortest solution costs; "
                "C* computed independently with unit-cost PDDL BFS."
            ),
            "per_task": native,
        },
    )
    original_summary = summarize(
        records, tasks, ("learned_adapter", "pretrained_base", "random_valid", "exact_reference")
    )
    random_task = {task: original_summary["random_valid"]["per_task"][task]["solved_at_2"] for task in tasks}
    D = [task for task in tasks if 0 < random_task[task] < 1]
    save(
        "stored-posthoc-analysis.json",
        {
            "status": "post-hoc exploratory, all 144 frozen #132 episodes; 2x traces never extrapolated beyond m=2",
            "arms": original_summary,
            "m5_controls_only_random_solve_fraction_by_task": random_task,
            "m5_informative_tasks_D": D,
            "m5_D_descriptive": summarize(
                records, D, ("learned_adapter", "pretrained_base", "random_valid", "exact_reference")
            )
            if D
            else {},
            "original_base_cap": (
                "pretrained_base: one model call, not 2x; all valid controls/learned: 2R decision and expansion budget"
            ),
        },
    )
    manifest_path = ZOO / "manifest.json"
    if not manifest_path.is_file():
        if args.require_zoo:
            raise FileNotFoundError(manifest_path)
        print("Zoo not yet present; stored post-hoc report complete")
        return
    manifest = load(manifest_path)
    bindings = manifest["bindings"]
    assert len(bindings) == manifest["expected_bindings"] == 432
    manifest_ids = {(b["task_id"], b["algorithm"], b["arm"], b["multiplier"], b["seed"]) for b in bindings}
    assert len(manifest_ids) == 432
    missing = [
        b
        for b in bindings
        if b["status"] != "observed" or b["replay_status"] != "passed" or not (ROOT / b["episode_path"]).is_file()
    ]
    assert not missing, f"missing or unverified comparator episodes: {missing[:3]}"
    zoo_records = []
    original_paths = {path.resolve() for path in original}
    for binding in bindings:
        arm = binding["arm"]
        if binding["source"] != "o4":
            assert arm == "random_valid" and binding["multiplier"] == 2 and binding["source"] == "frozen-132"
            assert (ROOT / binding["episode_path"]).resolve() in original_paths
            continue
        episode = load(ROOT / binding["episode_path"])
        assert episode.get("selector", episode["arm"]) == arm
        assert (
            episode["instance_id"] == binding["task_id"]
            and episode["algorithm"] == binding["algorithm"]
            and episode["seed"] == binding["seed"]
        )
        ref = panel_by_id[binding["task_id"]]["row"]["reference_costs"][binding["algorithm"]]["expansions"]
        row = inspect_episode(episode, authorities[binding["task_id"]], ref, arm, binding["multiplier"])
        row["c_star"] = optimal[row["task"]]["cost"]
        row["kappa"] = row["cost"] / row["c_star"] if row["cost"] is not None else None
        zoo_records.append(row)
    complete_records = records + zoo_records
    assert len(zoo_records) == 342
    for arm in ("bfs-order", "novelty-first", "worst-first", "random_valid"):
        for task in tasks:
            for algorithm in ALGORITHMS:
                for multiplier in (2, 3, 4) if arm != "random_valid" else (3, 4):
                    actual = [
                        r
                        for r in zoo_records
                        if r["arm"] == arm
                        and r["task"] == task
                        and r["algorithm"] == algorithm
                        and r["multiplier"] == multiplier
                    ]
                    assert len(actual) == (5 if arm == "random_valid" else 1), (
                        arm,
                        task,
                        algorithm,
                        multiplier,
                        len(actual),
                    )
    primary = [r for r in complete_records if r["multiplier"] == 2]
    arms = (
        "learned_adapter",
        "pretrained_base",
        "random_valid",
        "exact_reference",
        "bfs-order",
        "novelty-first",
        "worst-first",
    )
    all_summary = summarize(primary, tasks, arms)
    comparisons = paired_report(primary, tasks)
    d_paired = paired_report([r for r in primary if r["task"] in D], D)["comparisons"] if D else {}
    for comparison in d_paired.values():
        comparison.pop("dominance")
        for value in comparison.values():
            for key in ("one_sided_bootstrap_p", "holm_adjusted_p_15_test_family", "cluster_bootstrap_95pct_ci"):
                value.pop(key, None)
    extended = {}
    for arm in ("random_valid", "bfs-order", "novelty-first", "worst-first"):
        extended[arm] = {}
        for m in (3, 4):
            per_task = {}
            for task in tasks:
                alg_rows = {
                    alg: [
                        r
                        for r in zoo_records
                        if r["arm"] == arm and r["task"] == task and r["algorithm"] == alg and r["multiplier"] == m
                    ]
                    for alg in ALGORITHMS
                }
                flat = [r for group in alg_rows.values() for r in group]
                solved = [r for r in flat if r["goal"] is not None]
                per_task[task] = {
                    "by_algorithm": {
                        alg: [
                            {
                                "seed": r["seed"],
                                "goal": r["goal"],
                                "expansions": r["expansions"],
                                "decision_count": r["decisions"],
                                "termination": r["termination"],
                                "kappa": r["kappa"],
                            }
                            for r in group
                        ]
                        for alg, group in alg_rows.items()
                    },
                    "solve_fraction_equal_algorithms": mean(
                        mean(r["goal"] is not None for r in group) for group in alg_rows.values()
                    ),
                    "mean_observed_min_expansions_cap_over_reference": mean(
                        mean(
                            min(r["expansions"], m * r["reference_expansions"]) / r["reference_expansions"]
                            for r in group
                        )
                        for group in alg_rows.values()
                    ),
                    "solved_only_kappa": mean(r["kappa"] for r in solved) if solved else None,
                    "failed_count": len(flat) - len(solved),
                }
            extended[arm][str(m)] = {
                "per_task": per_task,
                "solved_fraction_equal_task_algorithm_seed": mean(
                    row["solve_fraction_equal_algorithms"] for row in per_task.values()
                ),
                "episode_count": sum(len(group) for row in per_task.values() for group in row["by_algorithm"].values()),
                "failed_count": sum(row["failed_count"] for row in per_task.values()),
            }
    report = {
        "status": "preregistered #133 CPU comparator analysis; frozen #132 reused post-hoc",
        "episode_accounting": {
            "stored_original": len(records),
            "new_cpu": len(zoo_records),
            "zoo_manifest_total_including_reused_2x_random": len(bindings),
            "missing": missing,
            "replay_passed": len(bindings),
        },
        "arms": all_summary,
        "m5_informative_tasks_D": D,
        "m5_D_descriptive": summarize(primary, D, arms) if D else {},
        "m5_D_paired_descriptive_only_no_additional_tests": d_paired,
        "m5_random_controls_only_by_task": random_task,
        "m1_m2_m3_dominance_holm": comparisons,
        "additional_cpu_3x_4x_not_primary_m1": extended,
        "interpretation": (
            "M2/M3 paired estimates condition on co-solving; unequal solved sets are "
            "asymmetric and cannot establish unconditional dominance. Undefined "
            "co-solved tests prohibit positive claims."
        ),
    }
    save("all-episode-metrics.json", {"records": complete_records})
    save("analysis.json", report)
    print(
        "Zoo integrated:", len(zoo_records), "new CPU episodes; D=", D, "Holm undefined=", comparisons["undefined_tests"]
    )
    print("Stored 144 episodes accounted; offline optimal costs:", {k: v["cost"] for k, v in optimal.items()})


if __name__ == "__main__":
    main()
