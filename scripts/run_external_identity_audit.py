#!/usr/bin/env python
"""External identity audit (#137): control arms on a published action-choice interface.

Frozen protocol: ``docs/experiments/external-audit/issue-137-protocol.md``.

Benchmark ``scienceworld`` (Wang, Jansen, Cote, Ammanabrolu, EMNLP 2022). The upstream
repository is cloned (untracked) under ``outputs/external-audit/v1/upstream/scienceworld``
and imported, never copied: episodes run in the upstream ``ScienceWorldEnv`` (bundled Scala
simulator via py4j), tasks are the upstream test variations, the reference is the upstream
gold trajectory and the budget is the paper's 100 steps (``envStepLimit=100``).

Arms (no model is run, no GPU is used):

- ``reference``    - execute ``get_gold_action_sequence()`` action by action.
- ``random_valid`` - at each decision pick uniformly among the simulator's valid
  action-object combinations for the current state (seeds 17, 5077, 6131, 7409, 8527).

The upstream package lives in the separate venv ``outputs/external-audit/v1/venv-sw``;
started from ada_vla, the script re-executes itself with that interpreter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import random
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "external-audit" / "v1"
VENV_PYTHON = OUT / "venv-sw" / "bin" / "python"
UPSTREAM = {"scienceworld": OUT / "upstream" / "scienceworld"}
MANIFEST = OUT / "upstream-manifest.json"

SEEDS = (17, 5077, 6131, 7409, 8527)
MAX_TASKS = 200
STEP_LIMIT = 100
ACTION_CAP = 1000
DETERMINISM_EPISODES = 10
DETERMINISM_SEED = 137

# Paper Table 2 (normalized scores on test variations): DRRN (best model) and Random-Valid.
PUBLISHED_DRRN = {
    "1-1": 0.03, "1-2": 0.04, "1-3": 0.01, "1-4": 0.03, "2-1": 0.10, "2-2": 0.08, "2-3": 0.06,
    "3-1": 0.13, "3-2": 0.10, "3-3": 0.07, "3-4": 0.20, "4-1": 0.26, "4-2": 0.56, "4-3": 0.19,
    "4-4": 0.19, "5-1": 0.09, "5-2": 0.16, "6-1": 0.20, "6-2": 0.29, "6-3": 0.11, "7-1": 0.48,
    "7-2": 0.47, "7-3": 0.31, "8-1": 0.09, "8-2": 0.10, "9-1": 0.13, "9-2": 0.13, "9-3": 0.13,
    "10-1": 0.19, "10-2": 0.17,
}
PUBLISHED_RANDOM_VALID = {
    "1-1": 0.00, "1-2": 0.00, "1-3": 0.00, "1-4": 0.00, "2-1": 0.00, "2-2": 0.00, "2-3": 0.00,
    "3-1": 0.01, "3-2": 0.01, "3-3": 0.01, "3-4": 0.00, "4-1": 0.03, "4-2": 0.63, "4-3": 0.01,
    "4-4": 0.01, "5-1": 0.07, "5-2": 0.02, "6-1": 0.01, "6-2": 0.01, "6-3": 0.00, "7-1": 0.02,
    "7-2": 0.03, "7-3": 0.01, "8-1": 0.00, "8-2": 0.00, "9-1": 0.01, "9-2": 0.00, "9-3": 0.01,
    "10-1": 0.01, "10-2": 0.01,
}


def ensure_upstream_interpreter() -> None:
    try:
        import scienceworld  # noqa: F401
    except ImportError:
        if Path(sys.prefix).resolve() == VENV_PYTHON.parents[1].resolve():  # already inside venv-sw
            raise
        env = dict(os.environ, CUDA_VISIBLE_DEVICES="")
        os.execve(str(VENV_PYTHON), [str(VENV_PYTHON), __file__, *sys.argv[1:]], env)


def sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def dumps(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(obj))


def new_env():
    from scienceworld import ScienceWorldEnv

    return ScienceWorldEnv("", envStepLimit=STEP_LIMIT)


def load_tasks() -> list[dict]:
    """Test variations of all 30 tasks in Table 2 order (upstream tasks.json), first MAX_TASKS."""
    import scienceworld

    table = json.loads((Path(scienceworld.__file__).parent / "tasks.json").read_text())
    env = new_env()
    tasks = []
    for row in table:
        env.load(row["task_name"], 0)
        for v in env.get_variations_test():
            tasks.append({"task": f"{row['task_id']}__{row['task_name']}__var{v}", "task_id": row["task_id"],
                          "task_name": row["task_name"], "variation": v})
    env.close()
    return tasks[:MAX_TASKS]


def episode_seed(seed: int, task: str) -> int:
    return int(hashlib.sha256(f"{seed}|{task}".encode()).hexdigest()[:16], 16)


def run_episode(env, task: dict, arm: str, seed: int | None) -> dict:
    env.load(task["task_name"], task["variation"], "", generateGoldPath=(arm == "reference"))
    _, info = env.reset()
    gold = env.get_gold_action_sequence() if arm == "reference" else None
    rng = random.Random(episode_seed(seed, task["task"])) if arm == "random_valid" else None
    valid = info["valid"]
    decisions, n_valid, scores = [], [], []
    done, terminated = False, None
    while not done:
        if len(decisions) >= ACTION_CAP:
            terminated = "action_cap"
            break
        if arm == "reference":
            if len(decisions) >= len(gold):
                terminated = "plan_exhausted"
                break
            action = gold[len(decisions)]
        else:
            candidates = sorted(valid)
            if not candidates:
                terminated = "no_valid_action"
                break
            action = rng.choice(candidates)
        n_valid.append(len(valid))
        _, _, done, info = env.step(action)
        decisions.append(action)
        scores.append(info["score"])
        valid = info["valid"]
    final = info["score"]
    goal = final >= 100
    if terminated is None:
        if goal:
            terminated = "success"
        elif final < 0:
            terminated = "failure"
        else:
            terminated = "step_limit" if info["moves"] > STEP_LIMIT else "completed"
    return {
        "benchmark": "scienceworld",
        "task": task["task"],
        "arm": arm,
        "seed": seed,
        "budget": {"env_step_limit": STEP_LIMIT, "action_cap": ACTION_CAP},
        "decisions": decisions,
        "n_valid": n_valid,
        "scores": scores,
        "final_score": final,
        "moves": info["moves"],
        "goal_reached": goal,
        "steps": len(decisions),
        "terminated": terminated,
    }


def episode_path(out_dir: Path, task: str, arm: str, seed) -> Path:
    return out_dir / "episodes" / task / f"{arm}-{'ref' if seed is None else seed}.json"


_WORKER_ENV = None


def _worker_init() -> None:
    global _WORKER_ENV
    _WORKER_ENV = new_env()


def _run_task(args) -> str:
    task, out_dir = args
    for arm, seed in [("reference", None)] + [("random_valid", s) for s in SEEDS]:
        write_json(episode_path(out_dir, task["task"], arm, seed), run_episode(_WORKER_ENV, task, arm, seed))
    return task["task"]


def first_divergence(a: list, b: list) -> int | None:
    for i, (x, y) in enumerate(zip(a, b, strict=False)):
        if x != y:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def build_audit(tasks, out_dir: Path, manifest: dict) -> dict:
    pairs_checked = pairs_identical = 0
    divergences = []
    ref_success = 0
    ref_scores, rnd_scores = [], []
    seed_success = {str(s): 0 for s in SEEDS}
    for task in tasks:
        ref = json.loads(episode_path(out_dir, task["task"], "reference", None).read_text())
        ref_success += ref["goal_reached"]
        ref_scores.append(max(ref["final_score"], 0) / 100)
        for s in SEEDS:
            ep = json.loads(episode_path(out_dir, task["task"], "random_valid", s).read_text())
            seed_success[str(s)] += ep["goal_reached"]
            rnd_scores.append(max(ep["final_score"], 0) / 100)
            pairs_checked += 1
            idx = first_divergence(ref["decisions"], ep["decisions"])
            if idx is None and ref["goal_reached"] == ep["goal_reached"]:
                pairs_identical += 1
            else:
                divergences.append(0 if idx is None else idx)
    n = len(tasks)
    success_ref = ref_success / n
    per_seed = {k: v / n for k, v in seed_success.items()}
    rnd_mean = statistics.fmean(per_seed.values())
    saturation = rnd_mean >= 0.9 * success_ref
    published = sum(PUBLISHED_DRRN[t["task_id"]] for t in tasks) / n
    published_rnd = sum(PUBLISHED_RANDOM_VALID[t["task_id"]] for t in tasks) / n
    if pairs_identical == pairs_checked:
        verdict = "IDENTICAL"
    elif saturation:
        verdict = "SATURATED"
    else:
        verdict = "CHOICE_REGISTERED"
    up = manifest["benchmarks"]["scienceworld"]
    task_ids = sorted({t["task_id"] for t in tasks}, key=lambda s: [int(x) for x in s.split("-")])
    return {
        "schema_version": "external_identity_audit_v1",
        "benchmark": "scienceworld",
        "upstream": {"repo": up["repo"], "commit": up["commit"], "license": up["license"]},
        "interface_type": "B",
        "prediction": "divergent",
        "tasks": n,
        "pairs_checked": pairs_checked,
        "pairs_identical": pairs_identical,
        "pairs_divergent": pairs_checked - pairs_identical,
        "first_divergence_index": (
            {"median": int(statistics.median_low(divergences)), "min": min(divergences), "max": max(divergences)}
            if divergences else None
        ),
        "success": {"reference": success_ref, "random_valid_per_seed": per_seed, "random_valid_mean": rnd_mean},
        "saturation": saturation,
        "published_model_success": {
            "value": published,
            "source": (
                "Wang et al. EMNLP 2022 (arXiv 2203.07540) Table 2, DRRN (best model) normalized score on test "
                f"variations, averaged over the audited tasks {task_ids} weighted by audited variation counts; "
                "the paper reports scores, not success rates (success <= score); headline over 30 tasks 0.17"
            ),
        },
        "random_fraction_of_published": rnd_mean / published,
        "verdict": verdict,
        "structural_basis": (
            "ScienceWorld is a sequential action-choice contract: each decision executes one valid action in the "
            "simulator, which changes the state, the next valid set and the score, and a wrong 'focus on' ends the "
            "episode, so the order of choices determines the outcome and no data structure re-orders them; uniform "
            "choice among hundreds of valid actions does not complete the multi-step gold procedure within 100 steps."
        ),
        "supplementary": {
            "mean_clipped_score": {
                "reference": statistics.fmean(ref_scores), "random_valid": statistics.fmean(rnd_scores),
            },
            "published_random_valid_score_same_tasks": published_rnd,
            "published_headline_drrn_score_30_tasks": 0.17,
        },
    }


def main() -> None:
    ensure_upstream_interpreter()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--benchmark", required=True, choices=sorted(UPSTREAM))
    parser.add_argument("--limit", type=int, default=None, help="smoke: first N tasks, written to <name>-smoke/")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    assert os.environ.get("CUDA_VISIBLE_DEVICES", "") == "", "CUDA_VISIBLE_DEVICES must be empty (CPU only)"

    manifest = json.loads(MANIFEST.read_text())
    up = manifest["benchmarks"][args.benchmark]
    head = subprocess.run(["git", "-C", str(UPSTREAM[args.benchmark]), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()
    assert head == up["commit"], f"upstream checkout {head} != pinned {up['commit']}"
    import scienceworld

    module = Path(scienceworld.__file__).resolve()
    assert module.is_relative_to(UPSTREAM[args.benchmark].resolve()), module

    tasks = load_tasks()
    out_dir = OUT / (args.benchmark if args.limit is None else f"{args.benchmark}-smoke")
    if args.limit is not None:
        tasks = tasks[: args.limit]
    write_json(out_dir / "tasks.json", tasks)
    write_json(out_dir / "run-info.json", {
        "interpreter": sys.executable,
        "scienceworld_module": scienceworld.__file__,
        "scienceworld_version": scienceworld.__version__,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "seeds": list(SEEDS),
        "env_step_limit": STEP_LIMIT,
        "limit": args.limit,
        "workers": args.workers,
    })

    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(args.workers, initializer=_worker_init) as pool:
        for k, name in enumerate(pool.imap_unordered(_run_task, [(t, out_dir) for t in tasks])):
            print(f"[{k + 1}/{len(tasks)}] {name}", flush=True)

    det_rng = random.Random(DETERMINISM_SEED)
    picks = det_rng.sample([(t, s) for t in tasks for s in SEEDS], min(DETERMINISM_EPISODES, len(tasks) * len(SEEDS)))
    env = new_env()
    det = []
    for task, seed in picks:
        path = episode_path(out_dir, task["task"], "random_valid", seed)
        rerun = dumps(run_episode(env, task, "random_valid", seed)).encode()
        det.append({"task": task["task"], "seed": seed, "identical": path.read_bytes() == rerun, "sha16": sha16(path)})
    env.close()
    write_json(out_dir / "determinism.json", {
        "description": "random_valid episodes re-run in a fresh simulator process; logs compared byte for byte",
        "episodes": len(det), "all_identical": all(d["identical"] for d in det), "reruns": det,
    })
    assert all(d["identical"] for d in det), "determinism check failed"

    audit = build_audit(tasks, out_dir, manifest)
    write_json(out_dir / "identity-audit.json", audit)
    keys = ("tasks", "pairs_checked", "pairs_identical", "success", "saturation", "verdict")
    print(json.dumps({k: audit[k] for k in keys}, indent=1))


if __name__ == "__main__":
    main()
