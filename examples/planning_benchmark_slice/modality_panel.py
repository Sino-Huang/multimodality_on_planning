"""Outcome-blind complete-task selection from existing exact-reference costs."""

from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any


def select_modality_panel(rows: list[dict[str, Any]], ceiling: int = 1024) -> dict[str, Any]:
    """Keep whole task groups; additive settings enter and leave together."""
    selected, excluded = [], []
    for row in rows:
        costs = row["reference_costs"]
        if row["split"] not in {"train", "dev"} or not costs:
            raise ValueError("panel requires development tasks and exact-reference costs")
        if any(cost["decisions"] <= 0 or cost["expansions"] <= 0 for cost in costs.values()):
            raise ValueError("reference costs must be positive")
        if max(cost["decisions"] for cost in costs.values()) > ceiling:
            excluded.append({**row, "outcome": "VALID_STOP", "reason": "reference_decision_ceiling"})
        else:
            selected.append(row)
    counts: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    for row in selected:
        for algorithm, cost in row["reference_costs"].items():
            counts[f"{algorithm}/{row['split']}"] += 1
            decisions[algorithm] += cost["decisions"]
    return {
        "schema_version": "modality_panel_v1",
        "selection_uses_model_outcomes": False,
        "max_reference_decisions": ceiling,
        "selected": selected,
        "excluded": excluded,
        "counts": {
            "selected_task_groups": len(selected),
            "excluded_task_groups": len(excluded),
            "episodes_by_algorithm_split": dict(sorted(counts.items())),
            "reference_decisions_by_algorithm": dict(sorted(decisions.items())),
        },
    }


def collect_modality_candidates(root: Path) -> list[dict[str, Any]]:
    """Read scientific source metadata; inherited integrity fields are unused."""
    rows = []
    bfs_root = root / "data/bfs_pilot_v6/exact-traces"
    bfs = json.loads((bfs_root / "manifests/bfs-expert-traces.json").read_text())
    for item in bfs["traces"]:
        trace_path = bfs_root / item["search_trace"]["path"]
        trace = json.loads(trace_path.read_text())
        rows.append(
            {
                "task_id": f"bfs/{item['instance_id']}",
                "domain": item["domain_id"],
                "difficulty": item["difficulty"],
                "split": item["source"]["split"],
                "trace_paths": {"bfs": str(trace_path.relative_to(root))},
                "reference_costs": {
                    "bfs": {"decisions": trace["record_count"], "expansions": item["result"]["expansion_count"]}
                },
            }
        )
    bfws_root = root / "data/bfws_phase_v1/exact-traces"
    bfws = json.loads((bfws_root / "manifests/bfws-expert-traces.json").read_text())
    for item in bfws["traces"]:
        rows.append(
            {
                "task_id": f"best_first_width/{item['instance_id']}",
                "domain": item["domain_id"],
                "difficulty": item["difficulty"],
                "split": item["source"]["split"],
                "trace_paths": {"best_first_width": str((bfws_root / item["search_trace"]["path"]).relative_to(root))},
                "reference_costs": {
                    "best_first_width": {
                        "decisions": item["exact_reference_decision_count"],
                        "expansions": item["result"]["expansion_count"],
                    }
                },
            }
        )
    paired_root = root / "data/best_first_paired_phase_v3"
    with gzip.open(paired_root / "corpus-release-v3/splits/assignments.jsonl.gz", "rt") as stream:
        splits = {item["pair_id"]: item["split"] for item in map(json.loads, stream)}
    tasks = {
        item["pair_id"]: item
        for item in json.loads((root / "configs/experiments/astar-paired-task-v1.json").read_text())["pairs"]
    }
    pairs = json.loads((paired_root / "exact-traces/manifest.json").read_text())["pairs"]
    for pair in pairs:
        if pair["pair_id"] not in splits:
            continue  # The issue64 source release already excludes these pairs.
        task = tasks[pair["pair_id"]]
        rows.append(
            {
                "task_id": pair["pair_id"],
                "domain": task["domain_id"],
                "difficulty": task["difficulty"],
                "split": splits[pair["pair_id"]],
                "trace_paths": {
                    algorithm: str(
                        (paired_root / "exact-traces/pairs" / pair["pair_id"] / item["path"]).relative_to(root)
                    )
                    for algorithm, item in pair["traces"].items()
                },
                "reference_costs": {
                    algorithm: {"decisions": item["decision_count"], "expansions": item["expansion_count"]}
                    for algorithm, item in pair["traces"].items()
                },
            }
        )
    return sorted(rows, key=lambda row: row["task_id"])
