"""Run the issue #139 CPU-only choice-frontier selector zoo on a frozen v4 panel.

Copy of ``scripts/run_choice_frontier_v2_zoo.py`` (#135) with a ``--panel {p2,p2u}``
flag and output ``outputs/choice-frontier/v4/panels/<panel>/zoo/``
(docs/experiments/choice-frontier/issue-139-protocol.md). The selectors, episode
runner and replay are imported unchanged from the frozen #135 zoo, so the arms are
identical by construction; only the membership, output root and a process pool
(``--workers``; episodes are independent) differ.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.choice_frontier import replay_choice_episode  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402
from scripts.run_choice_frontier_v2_zoo import (  # noqa: E402
    ALGORITHMS,
    DETERMINISTIC,
    EVALUATION_SEEDS,
    EXACT_SEED,
    MULTIPLIERS,
    SELECTORS,
    authority_for,
    load_episode,
    reference_expansions,
    run_episode,
    save_episode,
    task_identity,
)

CONFIG = ROOT / "configs/experiments/choice-frontier-v4"
PROTOCOL = "docs/experiments/choice-frontier/issue-139-protocol.md"
PANELS = ("p2", "p2u")


def membership_path(panel: str) -> Path:
    return CONFIG / f"membership-{panel}.json"


def output_dir(panel: str) -> Path:
    return ROOT / "outputs/choice-frontier/v4/panels" / panel / "zoo"


def load_tasks(panel: str) -> list[dict]:
    membership = read_json(membership_path(panel))
    tasks = membership["tasks"]
    if [task["row"]["task_id"] for task in tasks] != membership["task_ids"]:
        raise ValueError(f"v4 {panel} panel rows differ from the frozen membership")
    return tasks


def bindings(panel: str, tasks: list[dict]) -> list[dict]:
    output = output_dir(panel)
    result = []
    for task in tasks:
        task_id = task["row"]["task_id"]
        directory = task_id.replace("/", "__")
        for algorithm in ALGORITHMS:
            for multiplier in MULTIPLIERS:
                for arm in ("exact_reference", "random_valid", *SELECTORS):
                    seeds = [EXACT_SEED] if arm == "exact_reference" or arm in DETERMINISTIC else EVALUATION_SEEDS
                    for seed in seeds:
                        path = output / "episodes" / directory / f"{algorithm}-{arm}-m{multiplier}-{seed}.json.gz"
                        result.append(
                            {
                                "task_id": task_id,
                                "algorithm": algorithm,
                                "arm": arm,
                                "selector": arm if arm in SELECTORS else None,
                                "multiplier": multiplier,
                                "seed": seed,
                                "source": f"v4-{panel}",
                                "episode_path": str(path.relative_to(ROOT)),
                                "expected_decision_cap": multiplier * reference_expansions(task, algorithm),
                                "status": "pending",
                                "replay_status": "pending",
                            }
                        )
    return result


def process_binding(item: tuple[dict, dict, bool]) -> dict:
    """Run (if requested and absent), then verify identity and replay one binding."""

    binding, row, run = item
    binding = dict(binding)
    task = task_identity(row, binding["algorithm"])
    path = ROOT / binding["episode_path"]
    try:
        if run and not path.exists():
            episode = run_episode(row, binding["algorithm"], binding["arm"], binding["multiplier"], binding["seed"])
            save_episode(path, episode)
        if path.exists():
            episode = load_episode(path)
            if episode["instance_id"] != binding["task_id"] or binding["selector"] != episode.get("selector"):
                raise ValueError("v4 episode identity or selector mismatch")
            if (
                episode["algorithm"] != binding["algorithm"]
                or episode["seed"] != binding["seed"]
                or episode["decision_cap"] != binding["expected_decision_cap"]
            ):
                raise ValueError("stored episode algorithm, seed or decision cap mismatch")
            replay_choice_episode(authority_for(row), task, episode)
            binding["status"] = "observed"
            binding["replay_status"] = "passed"
            binding["result"] = episode["result"]
            binding["admission_status_counts"] = episode.get("admission_status_counts")
        else:
            binding["status"] = "missing"
            binding["replay_status"] = "not_run"
    except Exception as error:
        binding["status"] = "error"
        binding["replay_status"] = "failed"
        binding["error"] = f"{type(error).__name__}: {error}"
        print(f"ERROR {binding['episode_path']}: {error}", flush=True)
    return binding


def write_manifest(panel: str, expected: list[dict]) -> dict:
    counts = {
        status: sum(item["status"] == status for item in expected)
        for status in ("observed", "missing", "error", "pending")
    }
    payload = {
        "schema_version": "choice_frontier_v4_zoo_manifest_v1",
        "protocol": PROTOCOL,
        "panel": panel,
        "membership": str(membership_path(panel).relative_to(ROOT)),
        "membership_sha256": read_json(membership_path(panel))["membership_sha256"],
        "episode_format": (
            "#133 envelope: frozen session arm (exact_reference for rule selectors) plus "
            "top-level selector identity and per-decision selector_evidence. CPU selectors "
            "use identical model_input and permuted menu, without image or scene rendering."
        ),
        "expected_bindings": len(expected),
        "counts": counts,
        "complete": counts["observed"] == len(expected),
        "bindings": expected,
    }
    output_dir(panel).mkdir(parents=True, exist_ok=True)
    (output_dir(panel) / "manifest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", choices=PANELS, required=True)
    parser.add_argument("--limit", type=int, help="Run only the first N missing new episodes (smoke)")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    tasks = load_tasks(args.panel)
    task_by_id = {task["row"]["task_id"]: task["row"] for task in tasks}
    expected = bindings(args.panel, tasks)
    if len(expected) != 58 * len(tasks):
        raise ValueError("v4 zoo binding matrix differs from the frozen protocol")
    budget = args.limit
    items = []
    for binding in expected:
        run = False
        if not (ROOT / binding["episode_path"]).exists() and (budget is None or budget > 0):
            run = True
            budget = None if budget is None else budget - 1
        items.append((binding, task_by_id[binding["task_id"]], run))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for index, binding in enumerate(pool.map(process_binding, items)):
            expected[index] = binding
            if index % 25 == 0 or index == len(expected) - 1:
                counts = write_manifest(args.panel, expected)
                print(f"{counts['observed']}/{len(expected)} {binding['arm']} {binding['task_id']} "
                      f"{binding['algorithm']} seed{binding['seed']} {binding['replay_status']}", flush=True)
    counts = write_manifest(args.panel, expected)
    print(json.dumps(counts), flush=True)
    if args.limit is None and any(item["status"] != "observed" for item in expected):
        raise SystemExit("v4 zoo incomplete; inspect manifest missing/error bindings")


if __name__ == "__main__":
    main()
