from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PANEL = REPO_ROOT / "data" / "bfs_eval_v8" / "selected-panel.json"
PERFORMANCE = REPO_ROOT / "data" / "bfs_eval_v8" / "performance-selection.json"
TRACE_ROOT = REPO_ROOT / "data" / "bfs_pilot_v6" / "exact-traces"


def test_v8_panel_is_an_outcome_blind_projection_of_existing_v6_dev_tasks() -> None:
    panel = json.loads(PANEL.read_bytes())
    source_rows = [
        json.loads(line) for line in (REPO_ROOT / panel["source_manifest"]).read_text(encoding="utf-8").splitlines()
    ]
    source_by_id = {row["instance_id"]: row for row in source_rows}
    tasks = panel["tasks"]

    assert panel["selection_uses_model_outcomes"] is False
    assert len(tasks) == 15
    assert len({task["domain_id"] for task in tasks}) == 15
    assert all(source_by_id[task["instance_id"]]["split"] == "dev" for task in tasks)
    assert all(source_by_id[task["instance_id"]]["domain_id"] == task["domain_id"] for task in tasks)
    assert all(source_by_id[task["instance_id"]]["bucket"] == task["difficulty"] for task in tasks)


def test_v8_panel_decision_costs_match_exact_retained_traces_and_fit() -> None:
    panel = json.loads(PANEL.read_bytes())
    performance = json.loads(PERFORMANCE.read_bytes())
    trace_manifest = json.loads((TRACE_ROOT / "manifests" / "bfs-expert-traces.json").read_bytes())
    traces = {row["instance_id"]: row for row in trace_manifest["traces"] if row["source"]["split"] == "dev"}
    observed_decisions = {}
    for task in panel["tasks"]:
        row = traces[task["instance_id"]]
        observed_decisions[task["instance_id"]] = json.loads((TRACE_ROOT / row["search_trace"]["path"]).read_bytes())[
            "record_count"
        ]

    assert observed_decisions == {task["instance_id"]: task["exact_reference_decisions"] for task in panel["tasks"]}
    assert sum(observed_decisions.values()) == 899
    assert performance["coverage"]["maximum_scheduled_calls"] == 899 * 2 * 6
    assert performance["coverage"]["projected_rollout_seconds"] <= 15 * 60 * 60
    assert performance["performance_receipt"]["outcomes_observed"] is False
