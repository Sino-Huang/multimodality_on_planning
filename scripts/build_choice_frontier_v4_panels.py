#!/usr/bin/env python
"""Issue #139 fresh held-out panels P2 (screened) and P2u (unscreened).

Copy of ``scripts/build_choice_frontier_v2_panel.py`` (#135) with the #139 changes
(docs/experiments/choice-frontier/issue-139-protocol.md):

- ``generate`` — 12 domains x fresh seeds 955000-955039 from the frozen ``expanded``
  profiles, **serial** generation; exclusion by problem_sha256 against the #135
  candidates, the #136 training tasks, the expanded-study final panel, the #132
  corpus and earlier candidates; bounded #135 C* BFS, keep 8 <= C* <= 20.
- ``screen`` — per kept candidate and algorithm: uncapped exact_reference (seed 17)
  gives R (exact expansions); random_valid seeds 101..505 at cap 2R (#135 verbatim).
- ``freeze`` — P2: the #135 screen + freeze rule; P2u: kept candidates not in P2
  whose exact reaches the goal for both algorithms (random screening not consulted).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_choice_frontier_v2_panel import (  # noqa: E402
    ALGORITHMS,
    CSTAR_MAX_EXPANDED,
    CSTAR_MAX_SECONDS,
    CSTAR_RANGE,
    EXACT_SEED,
    MIN_DOMAINS,
    MIN_TASKS,
    PANEL_SIZE,
    PER_DOMAIN,
    SCREEN_SEEDS,
    UNCAPPED,
    bounded_shortest_plan,
    membership_sha256,
    panel_row,
    profiles,
    read,
    run_control,
    write,
)

CONFIG = ROOT / "configs/experiments/choice-frontier-v4"
CANDIDATES = CONFIG / "candidates.json"
MEMBERSHIP = {"p2": CONFIG / "membership-p2.json", "p2u": CONFIG / "membership-p2u.json"}
OUTPUT = ROOT / "outputs/choice-frontier/v4/panels"
PROTOCOL_DOC = "docs/experiments/choice-frontier/issue-139-protocol.md"
SEEDS = tuple(range(955000, 955040))
TASK_PREFIX = "choice-frontier-v4"
EXCLUSION_SOURCES = {
    "a": "configs/experiments/choice-frontier-v2/candidates.json",
    "b": "configs/experiments/choice-frontier-v3/training-tasks.json",
    "c": "configs/experiments/expanded-study/final-panel.json",
    "d": "configs/experiments/choice-frontier/membership.json",
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def exclusion_hashes() -> dict[str, str]:
    """problem_sha256 -> '<source>:<label>:<task_id>' for the four #139 exclusion sources."""

    hashes: dict[str, str] = {}
    for record in read(ROOT / EXCLUSION_SOURCES["a"])["candidates"]:
        if record.get("problem_sha256"):
            hashes.setdefault(record["problem_sha256"], f"a:choice-frontier-v2-candidate:{record['task_id']}")
    for record in read(ROOT / EXCLUSION_SOURCES["b"])["tasks"]:
        if record.get("problem_sha256"):
            hashes.setdefault(record["problem_sha256"], f"b:choice-frontier-v3-training-task:{record['task_id']}")
    for task in read(ROOT / EXCLUSION_SOURCES["c"])["tasks"]:
        row = task.get("row", task)
        problem = read(ROOT / row["task_path"])["problem_pddl"]
        hashes.setdefault(sha256_text(problem), f"c:expanded-study-final-panel:{row['task_id']}")
    membership = read(ROOT / EXCLUSION_SOURCES["d"])
    task_ids = sorted(
        {
            rid.split(":")[0]
            for key in ("training_record_ids", "diagnostic_record_ids")
            for ids in membership[key].values()
            for rid in ids
        }
    )
    for task_id in task_ids:
        pairs = ROOT / "data/best_first_paired_phase_v3/exact-traces/pairs"
        problem = read(pairs / task_id / "task.json")["problem_pddl"]
        hashes.setdefault(sha256_text(problem), f"d:choice-frontier-v1-corpus:{task_id}")
    return hashes


def exclusion_reason(problem_sha256: str, excluded_by: dict[str, str], seen: dict[str, str]) -> str | None:
    """Overlap with an exclusion source, else duplicate of an earlier candidate, else None."""

    if problem_sha256 in excluded_by:
        return "overlap:" + excluded_by[problem_sha256]
    if problem_sha256 in seen:
        return "duplicate_candidate:" + seen[problem_sha256]
    return None


def generate_task(domain: str, profile: dict, seed: int) -> dict:
    """Run the frozen profile generator once; serial only (blocksworld shares a cwd STATES file)."""

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


def base_record(domain: str, seed: int, generation: dict) -> dict:
    task_path = generation["task_path"]
    record = {
        "task_id": f"{TASK_PREFIX}/{domain}-expanded-{seed}",
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
    record["problem_sha256"] = sha256_text(task["problem_pddl"])
    return record


def cstar_record(record: dict) -> dict:
    from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority

    task = read(ROOT / record["task_path"])
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    if authority.is_goal(authority.initial_state):
        return {**record, "reject_reason": "initial_goal"}
    plan = bounded_shortest_plan(ROOT / record["task_path"])
    record = {**record, "cstar_search": plan}
    if plan["status"] != "solved":
        return {**record, "reject_reason": plan["status"]}
    record["cstar"] = plan["cost"]
    if CSTAR_RANGE[0] <= plan["cost"] <= CSTAR_RANGE[1]:
        record["cstar_status"] = "kept"
    else:
        record["reject_reason"] = "cstar_out_of_range"
    return record


def generate_stage(workers: int) -> None:
    jobs = [(domain, profile, seed) for domain, profile in sorted(profiles().items()) for seed in SEEDS]
    excluded_by = exclusion_hashes()
    seen: dict[str, str] = {}
    records = []
    for domain, profile, seed in jobs:  # serial generation, walk order (domain, seed)
        record = base_record(domain, seed, generate_task(domain, profile, seed))
        if record["problem_sha256"] is not None:
            reason = exclusion_reason(record["problem_sha256"], excluded_by, seen)
            if reason is None:
                seen[record["problem_sha256"]] = record["task_id"]
            else:
                record["reject_reason"] = reason
        records.append(record)
    pending = [i for i, r in enumerate(records) if r["reject_reason"] is None]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for index, result in zip(pending, pool.map(cstar_record, [records[i] for i in pending]), strict=True):
            records[index] = result
    for record in records:
        print(record["task_id"], record["cstar"], record["cstar_status"], record["reject_reason"], flush=True)
    assert len(records) == 480
    counts: dict[str, int] = {}
    for record in records:
        key = (record["reject_reason"] or "kept").split(":")[0]
        counts[key] = counts.get(key, 0) + 1
    source_counts = {k: 0 for k in EXCLUSION_SOURCES}
    for label in excluded_by.values():
        source_counts[label[0]] += 1
    write(
        CANDIDATES,
        {
            "schema_version": "choice_frontier_v4_candidates_v1",
            "protocol": PROTOCOL_DOC,
            "seeds": list(SEEDS),
            "exclusion_key": "sha256(problem_pddl)",
            "exclusion_sources": EXCLUSION_SOURCES,
            "exclusion_source_hash_counts": source_counts,
            "cstar_rule": {"range": list(CSTAR_RANGE), "max_states_expanded": CSTAR_MAX_EXPANDED,
                           "max_seconds": CSTAR_MAX_SECONDS},
            "counts": dict(sorted(counts.items())),
            "candidates": records,
        },
    )
    print(json.dumps(counts, indent=1))


def screen_one(record: dict) -> dict:
    """The #135 ``screen_one`` with v4 output paths."""

    row = panel_row(record)
    directory = OUTPUT / "screen" / record["task_id"].replace("/", "__")
    exact_goal = {}
    costs = {}
    random_goals = 0
    detail = {}
    for algorithm in ALGORITHMS:
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
        "admit_p2": "exact goal for both algorithms and 1 <= random goals <= 9 of 10",
        "admit_p2u": "kept, not in P2, exact goal for both algorithms (random screening not consulted)",
    }
    write(CANDIDATES, payload)


def take_per_domain(records: list[dict]) -> list[dict]:
    """The #135 freeze walk: sort by (domain, seed), at most 2 per domain, first 12."""

    chosen = []
    per_domain: dict[str, int] = {}
    for record in sorted(records, key=lambda r: (r["domain"], r["seed"])):
        if len(chosen) == PANEL_SIZE:
            break
        if per_domain.get(record["domain"], 0) < PER_DOMAIN:
            chosen.append(record)
            per_domain[record["domain"]] = per_domain.get(record["domain"], 0) + 1
    return chosen


def select_p2(candidates: list[dict]) -> list[dict]:
    return take_per_domain([r for r in candidates if r.get("admitted")])


def select_p2u(candidates: list[dict], p2_ids: set[str]) -> list[dict]:
    """Kept, not in P2, exact reaches the goal for both algorithms. Reads no random-screen field."""

    pool = [
        {"task_id": r["task_id"], "domain": r["domain"], "seed": r["seed"]}
        for r in candidates
        if r["cstar_status"] == "kept"
        and r["task_id"] not in p2_ids
        and all((r.get("screen_exact_goal_by_algorithm") or {}).get(a) is True for a in ALGORITHMS)
    ]
    ids = {r["task_id"] for r in take_per_domain(pool)}
    return [r for r in candidates if r["task_id"] in ids]


def write_membership(panel: str, chosen: list[dict], counts: dict, freeze_rule: str) -> str:
    task_ids = sorted(r["task_id"] for r in chosen)
    by_id = {r["task_id"]: r for r in chosen}
    sha = membership_sha256(task_ids)
    write(
        MEMBERSHIP[panel],
        {
            "schema_version": "choice_frontier_v4_membership_v1",
            "protocol": PROTOCOL_DOC,
            "panel": panel,
            "task_ids": task_ids,
            "membership_sha256": sha,
            "membership_canonical_form": "sha256 of json.dumps(sorted(task_ids), sort_keys=True, separators=(',', ':'))",
            "freeze_rule": freeze_rule,
            "per_domain_counts": counts,
            "domains": sorted({r["domain"] for r in chosen}),
            "per_task": {
                task_id: {
                    "cstar": by_id[task_id]["cstar"],
                    "R": by_id[task_id]["screen_R"],
                    "exact_decisions": by_id[task_id]["screen_exact_decisions"],
                    # P2u rows carry the screening outcome for description only; it never selected them.
                    "screen_random_goals": by_id[task_id]["screen_random_goals"],
                }
                for task_id in task_ids
            },
            "tasks": [{"row": panel_row(by_id[t], by_id[t]["reference_costs"])} for t in task_ids],
        },
    )
    return sha


def freeze_stage() -> None:
    candidates = read(CANDIDATES)["candidates"]
    counts = {}
    for record in candidates:
        entry = counts.setdefault(record["domain"], {"candidates": 0, "kept": 0, "exact_goal": 0, "admitted": 0})
        entry["candidates"] += 1
        entry["kept"] += record["cstar_status"] == "kept"
        entry["exact_goal"] += bool(record.get("screen_exact_goal"))
        entry["admitted"] += bool(record.get("admitted"))
    print(json.dumps(counts, indent=1))
    p2 = select_p2(candidates)
    p2_domains = {r["domain"] for r in p2}
    if len(p2) < MIN_TASKS or len(p2_domains) < MIN_DOMAINS:
        raise SystemExit(f"STOP: P2 has {len(p2)} tasks from {len(p2_domains)} domains (need >= 8 from >= 5)")
    p2u = select_p2u(candidates, {r["task_id"] for r in p2})
    p2u_domains = {r["domain"] for r in p2u}
    assert not {r["task_id"] for r in p2} & {r["task_id"] for r in p2u}
    sha = write_membership(
        "p2", p2, counts, "admitted (#135 screen) sorted by (domain, seed); at most 2 per domain; first 12"
    )
    print("P2 frozen", len(p2), "tasks from", len(p2_domains), "domains", sha)
    if len(p2u) < MIN_TASKS or len(p2u_domains) < MIN_DOMAINS:
        print(f"P2u dropped: {len(p2u)} tasks from {len(p2u_domains)} domains (need >= 8 from >= 5)")
        return
    sha = write_membership(
        "p2u", p2u, counts,
        "kept, not in P2, exact goal for both algorithms (no random screen), sorted by (domain, seed); "
        "at most 2 per domain; first 12",
    )
    print("P2u frozen", len(p2u), "tasks from", len(p2u_domains), "domains", sha)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("generate", "screen", "freeze"))
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if args.stage == "generate":
        generate_stage(args.workers)
    elif args.stage == "screen":
        screen_stage(args.workers)
    else:
        freeze_stage()


if __name__ == "__main__":
    main()
