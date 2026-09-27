#!/usr/bin/env python
"""#147 analyzer: writes outputs/data-cost/v1/metrics/analysis.json and data-cost-curves.{pdf,png}.

Episode source (first available): --episodes PATH (an episodes.json table), else the replay-verified table written by
`run_data_cost.py finalize` (metrics/episodes.json), else a read-only scan of the recorded episodes (no replay;
reported as `replay_verified: false`). Works on partial data; every missing cell/episode is listed explicitly.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice import data_cost_analysis as analysis
from examples.planning_benchmark_slice import data_cost_runner as runner

ROOT = runner.ROOT
NODE_CHOICE = Path("outputs/choice-frontier/v4/seeds/metrics/analysis.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--episodes", type=Path, help="episodes.json table (rows + accounting); default: finalize output"
    )
    parser.add_argument("--panel", type=Path, default=runner.PANEL)
    parser.add_argument("--sufficiency", type=Path, default=runner.SUFFICIENCY)
    parser.add_argument("--node-choice", type=Path, default=NODE_CHOICE)
    parser.add_argument("--output", type=Path, default=runner.METRICS)
    parser.add_argument("--draws", type=int, default=analysis.DRAWS)
    args = parser.parse_args(argv)

    def resolve(path):
        return path if path.is_absolute() else ROOT / path

    panel = runner.read(resolve(args.panel))
    tasks = [entry["row"]["task_id"] for entry in panel["tasks"]]
    domains = {entry["row"]["task_id"]: entry["row"]["domain"] for entry in panel["tasks"]}
    finalized = ROOT / runner.METRICS / "episodes.json"
    if args.episodes is not None:
        table = runner.read(resolve(args.episodes))
        source = str(args.episodes)
    elif finalized.exists():
        table = runner.read(finalized)
        source = str(finalized.relative_to(ROOT))
    else:
        table = runner.collect_episodes(ROOT, replay=False)
        source = "read-only scan of recorded episodes (not replayed; run `run_data_cost.py finalize`)"
    sufficiency_path = resolve(args.sufficiency)
    node_choice_path = resolve(args.node_choice)
    result = analysis.analyze(
        table["rows"],
        tasks,
        task_domains=domains,
        sufficiency=runner.read(sufficiency_path) if sufficiency_path.exists() else None,
        node_choice=runner.read(node_choice_path) if node_choice_path.exists() else None,
        node_choice_path=str(args.node_choice),
        accounting={k: v for k, v in table.items() if k != "rows"},
        draws=args.draws,
    )
    result["episode_source"] = source
    result["panel_id"] = panel.get("panel_id")
    output = resolve(args.output)
    output.mkdir(parents=True, exist_ok=True)
    result["figure"] = [
        str(Path(p).relative_to(ROOT)) if Path(p).is_relative_to(ROOT) else p
        for p in analysis.figure(result, str(output / "data-cost-curves"))
    ]
    (output / "analysis.json").write_text(json.dumps(result, indent=1, allow_nan=False, default=_json_default) + "\n")
    summary = {
        "analysis": str(output / "analysis.json"),
        "figure": result["figure"],
        "missingness": result["missingness"]
        | {"learned_cells_missing": len(result["missingness"]["learned_cells_missing"])},
        "separated": result["success_contrasts"]["separated"],
        "n_quantiles": {k: {q: v[q]["label"] for q in analysis.QUANTILES} for k, v in result["n_quantiles"].items()},
    }
    print(json.dumps(summary, indent=2))
    return 0


def _json_default(value):
    return float(value)


if __name__ == "__main__":
    sys.exit(main())
