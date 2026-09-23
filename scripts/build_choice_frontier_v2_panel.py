#!/usr/bin/env python
"""Issue #135 fresh choice-frontier panel: generate, C*, controls-only screening, freeze.

Subcommands (docs/experiments/choice-frontier/issue-135-protocol.md):

- ``generate`` — 12 domains x fresh seeds 935000-935019 from the frozen ``expanded``
  profiles; write each task.json; compute C* with a bounded copy of the #133
  ``shortest_plan()`` BFS; keep 8 <= C* <= 20.
- ``screen`` — per kept candidate and algorithm: uncapped exact_reference (seed 17)
  gives R (exact expansions); random_valid seeds 101..505 at cap 2R.
- ``freeze`` — sort admitted by (domain, seed), <= 2 per domain, up to 12 tasks.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.choice_frontier import (  # noqa: E402
    ChoiceFrontierModelSession,
    ChoiceFrontierTask,
    replay_choice_episode,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority  # noqa: E402

PANEL_PROTOCOL = ROOT / "configs/experiments/expanded-study/panel-protocol-v2.json"
SNAPSHOTS = ROOT / "configs/experiments/expanded-study/tasks"
CONFIG = ROOT / "configs/experiments/choice-frontier-v2"
CANDIDATES = CONFIG / "candidates.json"
MEMBERSHIP = CONFIG / "membership.json"
OUTPUT = ROOT / "outputs/choice-frontier/v2"
PROTOCOL_DOC = "docs/experiments/choice-frontier/issue-135-protocol.md"
SEEDS = tuple(range(935000, 935020))
CSTAR_RANGE = (8, 20)
CSTAR_MAX_EXPANDED = 2_000_000
CSTAR_MAX_SECONDS = 600
ALGORITHMS = ("best_first_add_greedy", "best_first_add_w3")
EXACT_SEED = 17
SCREEN_SEEDS = (101, 202, 303, 404, 505)
UNCAPPED = 10**7
PANEL_SIZE = 12
PER_DOMAIN = 2
MIN_TASKS = 8
MIN_DOMAINS = 5


def read(path: Path):
    with gzip.open(path, "rt") if str(path).endswith(".gz") else open(path) as stream:
        return json.load(stream)


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if str(path).endswith(".gz"):
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
    else:
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def profiles() -> dict[str, dict]:
    protocol = read(PANEL_PROTOCOL)
    result = {s["domain"]: s for s in protocol["strata"] if s["stratum"] == "expanded"}
    assert len(result) == 12
    for domain in result:
        assert (SNAPSHOTS / f"{domain}-expanded.json").is_file()
    return result


def bounded_shortest_plan(task_path: Path) -> dict:
    """Copy of ``analyze_choice_frontier_o4.shortest_plan`` with the #135 limits."""

    snapshot = read(task_path)
    authority = PDDLStateAuthority.from_pddl(snapshot["domain_pddl"], snapshot["problem_pddl"])
    initial = authority.initial_state
    queue = deque([initial])
    parents = {initial.state_id: None}
    goal = None
    expanded = 0
    started = time.monotonic()
    while queue:
        state = queue.popleft()
        if authority.is_goal(state):
            goal = state
            break
        expanded += 1
        if expanded > CSTAR_MAX_EXPANDED or (expanded % 1000 == 0 and time.monotonic() - started > CSTAR_MAX_SECONDS):
            return {"status": "cstar_too_expensive", "states_expanded": expanded,
                    "seconds": time.monotonic() - started}
        for action in authority.applicable_actions(state):
            target = authority.apply(state, action).target_state
            if target.state_id not in parents:
                parents[target.state_id] = (state.state_id, action)
                queue.append(target)
    if goal is None:
        return {"status": "cstar_unsolvable", "states_expanded": expanded, "seconds": time.monotonic() - started}
    chain = []
    cursor = goal.state_id
    while parents[cursor] is not None:
        predecessor, action = parents[cursor]
        chain.append((predecessor, action, cursor))
        cursor = predecessor
    chain.reverse()
    cursor_state = initial
    for source, action, target in chain:
        assert cursor_state.state_id == source
        cursor_state = authority.apply(cursor_state, action).target_state
        assert cursor_state.state_id == target
    assert authority.is_goal(cursor_state)
    return {
        "status": "solved",
        "cost": len(chain),
        "plan": [a.serialize() for _, a, _ in chain],
        "states_discovered": len(parents),
        "states_expanded": len(parents) - len(queue),
        "verified_pddl_transitions": True,
        "seconds": time.monotonic() - started,
    }


def generate_task(domain: str, profile: dict, seed: int) -> dict:
    """Run the frozen profile generator once; serial only (some generators share cwd temp files)."""

    from examples.planning_benchmark_slice.expanded_candidates import generate

    directory = OUTPUT / "candidates" / f"{domain}-expanded-{seed}"
    task_path = directory / "task.json"
    if task_path.exists():
        return {"task_path": task_path}
    try:
        task = generate(ROOT, profile, seed, directory / "generator")
    except Exception as error:  # generator binary/normalization failure is a recorded rejection
        return {"task_path": task_path, "error": f"{type(error).__name__}: {error}"}
    task["authority_transformations"] = list(task["authority_transformations"])
    write(task_path, task)
    return {"task_path": task_path}


def evaluate_candidate(domain: str, seed: int, generation: dict) -> dict:
    name = f"{domain}-expanded-{seed}"
    task_path = generation["task_path"]
    record = {
        "task_id": f"choice-frontier-v2/{name}",
        "domain": domain,
        "seed": seed,
        "generator_command": None,
        "problem_sha256": None,
        "task_path": str(task_path.relative_to(ROOT)),
        "cstar": None,
        "cstar_status": "rejected",
        "reject_reason": None,
    }
    if "error" in generation:
        record["reject_reason"] = "generator_failed"
        record["error"] = generation["error"]
        return record
    task = read(task_path)
    record["generator_command"] = [c.replace(str(ROOT) + "/", "") for c in task["generator_command"]]
    record["problem_sha256"] = hashlib.sha256(task["problem_pddl"].encode()).hexdigest()
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    if authority.is_goal(authority.initial_state):
        record["reject_reason"] = "initial_goal"
        return record
    plan = bounded_shortest_plan(task_path)
    record["cstar_search"] = plan
    if plan["status"] != "solved":
        record["reject_reason"] = plan["status"]
        return record
    record["cstar"] = plan["cost"]
    if CSTAR_RANGE[0] <= plan["cost"] <= CSTAR_RANGE[1]:
        record["cstar_status"] = "kept"
    else:
        record["reject_reason"] = "cstar_out_of_range"
    return record


def generate_stage(workers: int) -> None:
    jobs = [(domain, profile, seed) for domain, profile in sorted(profiles().items()) for seed in SEEDS]
    generations = [generate_task(*job) for job in jobs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(evaluate_candidate, domain, seed, generation)
            for (domain, _profile, seed), generation in zip(jobs, generations, strict=True)
        ]
        records = []
        for future in futures:
            record = future.result()
            records.append(record)
            print(record["task_id"], record["cstar"], record["cstar_status"], record["reject_reason"], flush=True)
    assert len(records) == 240
    write(
        CANDIDATES,
        {
            "schema_version": "choice_frontier_v2_candidates_v1",
            "protocol": PROTOCOL_DOC,
            "seeds": list(SEEDS),
            "cstar_rule": {"range": list(CSTAR_RANGE), "max_states_expanded": CSTAR_MAX_EXPANDED,
                           "max_seconds": CSTAR_MAX_SECONDS},
            "candidates": records,
        },
    )


def panel_row(record: dict, reference_costs: dict | None = None) -> dict:
    """Panel record in the shape of configs/experiments/expanded-study/final-panel.json rows."""

    return {
        "task_id": record["task_id"],
        "domain": record["domain"],
        "difficulty": "expanded",
        "split": "test",
        "task_path": record["task_path"],
        "trace_paths": {},
        "reference_costs": reference_costs or {},
    }


def run_control(row: dict, algorithm: str, arm: str, seed: int, cap: int, exact_expansions: int) -> dict:
    source = read(ROOT / row["task_path"])
    task = ChoiceFrontierTask(row["task_id"], row["task_id"], row["domain"], algorithm, exact_expansions)
    session = ChoiceFrontierModelSession(
        authority=PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"]),
        task=task, arm=arm, seed=seed, decision_cap=cap,
    )
    while session.next_request() is not None:
        session.submit_output(session.reference_output())
    episode = session.episode()
    replay_choice_episode(PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"]), task, episode)
    return episode


def screen_one(record: dict) -> dict:
    row = panel_row(record)
    directory = OUTPUT / "screen" / record["task_id"].replace("/", "__")
    exact_goal = {}
    costs = {}
    random_goals = 0
    detail = {}
    for algorithm in ALGORITHMS:
        # Uncapped exact reference; its placeholder exact_expansions is unused by the runtime.
        exact = run_control(row, algorithm, "exact_reference", EXACT_SEED, UNCAPPED, UNCAPPED)
        write(directory / f"{algorithm}-exact_reference-{EXACT_SEED}.json.gz", exact)
        exact_goal[algorithm] = exact["result"]["goal_reached"]
        r = exact["result"]["expansion_count"]
        costs[algorithm] = {"decisions": exact["result"]["decision_count"], "expansions": r}
        detail[algorithm] = {"exact": exact["result"], "random_valid": {}}
        if not exact_goal[algorithm]:
            continue
        for seed in SCREEN_SEEDS:
            episode = run_control(row, algorithm, "random_valid", seed, 2 * r, r)
            write(directory / f"{algorithm}-random_valid-{seed}.json.gz", episode)
            random_goals += episode["result"]["goal_reached"]
            detail[algorithm]["random_valid"][str(seed)] = {
                "goal_reached": episode["result"]["goal_reached"],
                "decision_count": episode["result"]["decision_count"],
                "expansion_count": episode["result"]["expansion_count"],
                "termination_reason": episode["result"]["termination_reason"],
            }
    all_exact = all(exact_goal.values())
    return {
        "screen_exact_goal": all_exact,
        "screen_exact_goal_by_algorithm": exact_goal,
        "screen_R": {a: c["expansions"] for a, c in costs.items()},
        "screen_exact_decisions": {a: c["decisions"] for a, c in costs.items()},
        "screen_random_goals": random_goals if all_exact else None,
        "screen_random_episodes": 2 * len(SCREEN_SEEDS) if all_exact else 0,
        "screen_detail": detail,
        "reference_costs": costs,
        "admitted": all_exact and 1 <= random_goals <= 9,
    }


def screen_stage(workers: int) -> None:
    payload = read(CANDIDATES)
    kept = [r for r in payload["candidates"] if r["cstar_status"] == "kept"]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = dict(zip((r["task_id"] for r in kept), pool.map(screen_one, kept), strict=True))
    for record in payload["candidates"]:
        if record["task_id"] in results:
            record.update(results[record["task_id"]])
            print(record["task_id"], record["screen_R"], record["screen_random_goals"], record["admitted"], flush=True)
        else:
            record.update(screen_exact_goal=None, screen_R=None, screen_random_goals=None, admitted=False)
    payload["screening_rule"] = {
        "exact_reference_seed": EXACT_SEED,
        "random_valid_screening_seeds": list(SCREEN_SEEDS),
        "cap": "2 x R, R = uncapped exact_reference expansion count (the #133 R_t)",
        "admit": "exact goal for both algorithms and 1 <= random goals <= 9 of 10",
    }
    write(CANDIDATES, payload)


def membership_sha256(task_ids: list[str]) -> str:
    return hashlib.sha256(json.dumps(sorted(task_ids), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def freeze_stage() -> None:
    payload = read(CANDIDATES)
    admitted = sorted((r for r in payload["candidates"] if r.get("admitted")), key=lambda r: (r["domain"], r["seed"]))
    chosen = []
    per_domain: dict[str, int] = {}
    for record in admitted:
        if len(chosen) == PANEL_SIZE:
            break
        if per_domain.get(record["domain"], 0) < PER_DOMAIN:
            chosen.append(record)
            per_domain[record["domain"]] = per_domain.get(record["domain"], 0) + 1
    counts = {}
    for record in payload["candidates"]:
        entry = counts.setdefault(record["domain"], {"candidates": 0, "kept": 0, "admitted": 0})
        entry["candidates"] += 1
        entry["kept"] += record["cstar_status"] == "kept"
        entry["admitted"] += bool(record.get("admitted"))
    print(json.dumps(counts, indent=1))
    if len(chosen) < MIN_TASKS or len(per_domain) < MIN_DOMAINS:
        raise SystemExit(f"STOP: {len(chosen)} tasks from {len(per_domain)} domains (need >= 8 from >= 5)")
    task_ids = sorted(r["task_id"] for r in chosen)
    by_id = {r["task_id"]: r for r in chosen}
    write(
        MEMBERSHIP,
        {
            "schema_version": "choice_frontier_v2_membership_v1",
            "protocol": PROTOCOL_DOC,
            "task_ids": task_ids,
            "membership_sha256": membership_sha256(task_ids),
            "membership_canonical_form": "sha256 of json.dumps(sorted(task_ids), sort_keys=True, separators=(',', ':'))",
            "freeze_rule": "admitted sorted by (domain, seed); at most 2 per domain; first 12",
            "per_domain_counts": counts,
            "domains": sorted(per_domain),
            "per_task": {
                task_id: {
                    "cstar": by_id[task_id]["cstar"],
                    "R": by_id[task_id]["screen_R"],
                    "exact_decisions": by_id[task_id]["screen_exact_decisions"],
                    "screen_random_goals": by_id[task_id]["screen_random_goals"],
                }
                for task_id in task_ids
            },
            "tasks": [{"row": panel_row(by_id[t], by_id[t]["reference_costs"])} for t in task_ids],
        },
    )
    print("frozen", len(task_ids), "tasks from", len(per_domain), "domains", membership_sha256(task_ids))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("generate", "screen", "freeze"))
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    if args.stage == "generate":
        generate_stage(args.workers)
    elif args.stage == "screen":
        screen_stage(args.workers)
    else:
        freeze_stage()


if __name__ == "__main__":
    main()
