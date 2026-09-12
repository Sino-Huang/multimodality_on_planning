"""Replay released episodes from restored assets, without loading a model or rewriting receipts."""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.modality_view_preparation import write_json
from examples.planning_benchmark_slice.scene_assets import read_json
from examples.planning_benchmark_slice.visual_episode import VisualTaskViews, replay_visual_episode
from scripts.run_visual_issue75 import heartbeat, log
from scripts.verify_modality_experiment import coverage, expected_episodes, identity, point_metrics


def replay_run(root, run):
    directory = root / run["output_root"]
    attempt = read_json(directory / "attempt.json")
    terminal = read_json(directory / "result.json")
    config = attempt["experiment"]
    if terminal["contract_id"] != run["contract_id"] or config["contract_id"] != run["contract_id"]:
        raise ValueError("release run identity differs from original receipts")
    panel = read_json(root / run["panel_manifest"])["selected"]
    selector = attempt.get("pilot_manifest") or attempt.get("cost_panel")
    selected = selector["selected_task_ids"] if selector else [r["task_id"] for r in panel if r["split"] == "dev"]
    rows = {r["task_id"]: r for r in panel if r["split"] == "dev" and r["task_id"] in selected}
    expected = expected_episodes(rows.values(), config["evaluation_seeds"])
    corpus = read_json(root / run["corpus_report"])
    sources = {r["task_id"]: r for r in corpus["results"]}
    episodes = []
    for name in run["episode_paths"]:
        report = read_json(root / name)
        if (
            report["contract_id"] != run["contract_id"]
            or identity(report) not in expected
            or report.get("modality", "visual-state") != config["modality"]
            or report["output"] != name
        ):
            raise ValueError("released episode differs from its declared scope")
        row = rows[report["task_id"]]
        views = VisualTaskViews(
            root,
            row,
            sources[row["task_id"]]["view_manifest"],
            root / report["view_root"],
            config["backend_endpoints"][0],
            read_only=True,
        )
        replay_visual_episode(root, row, report, views)
        episodes.append({k: report[k] for k in ("task_id", "algorithm", "arm", "seed", "result")})
        log("release:replay", issue=run["issue"], completed=len(episodes), total=len(run["episode_paths"]))
    scope = coverage(episodes, expected)
    metrics = point_metrics(episodes)
    adjudication = directory / "adjudicate.json"
    if adjudication.exists():
        saved = read_json(adjudication)
        if saved["episodes"] != len(episodes) or not scope["complete"]:
            raise ValueError("released adjudication is missing declared episode coverage")
        for algorithm, arms in metrics.items():
            for arm, values in arms.items():
                for key in ("invariant_valid_success", "invalid_operation_rate", "budget_usage"):
                    if values[key] != saved["metrics"][algorithm][key][arm]:
                        raise ValueError("released point metrics differ from independently replayed results")
    return {
        "contract_id": run["contract_id"],
        "modality": config["modality"],
        "coverage": scope,
        "replayed_episodes": len(episodes),
        "point_metrics": metrics,
        "retained_outcome": terminal["outcome"],
        "retained_scientific_completion": terminal["scientific_completion"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument(
        "--assets-root", type=Path, required=True, help="Directory containing the restored relative paths"
    )
    parser.add_argument("--output", type=Path, required=True, help="Separate replay audit JSON")
    args = parser.parse_args()
    index = read_json(args.index)
    if index["schema"] != "deadline_replay_release_v1":
        raise ValueError("unsupported release index")
    for run in index["runs"]:
        if args.output.resolve().is_relative_to((args.assets_root / run["output_root"]).resolve()):
            raise ValueError("audit output must not rewrite an original experiment")
    reports = [heartbeat(lambda run=run: replay_run(args.assets_root, run), "release") for run in index["runs"]]
    complete = all(r["coverage"]["complete"] for r in reports)
    write_json(
        args.output, {"verification_outcome": "PASS" if complete else "PARTIAL", "runs": reports, "new_model_calls": 0}
    )
    log(
        "release:complete",
        outcome="PASS" if complete else "PARTIAL",
        completed=sum(r["replayed_episodes"] for r in reports),
        total=sum(r["coverage"]["total"] for r in reports),
    )
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
