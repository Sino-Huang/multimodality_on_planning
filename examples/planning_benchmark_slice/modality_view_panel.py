"""Whole-task context selection on existing BFS/BFWS/additive source inputs."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .modality_view_preparation import CONTRACT, EXPECTED, OUTPUT_TOKENS
from .scene_assets import read_json

PANEL_ID = "issue-72-readable-pages-panel-32k-v2"
VIEW_CONTRACT_ID = "issue-72-readable-pages-v2"
MAX_INPUT_TOKENS = 32768 - OUTPUT_TOKENS
SOURCE_PANEL = "configs/experiments/issue71/v2/panel.json"


def counts(rows: list[dict], measurements: dict[str, dict]) -> dict:
    return {
        "tasks": len(rows),
        "states": sum(measurements[r["task_id"]]["states"] for r in rows),
        "decisions": sum(measurements[r["task_id"]]["decisions"] for r in rows),
    }


def select_view_panel(parent: list[dict], results: list[dict], measurement_report: str) -> dict:
    measured = {r["task_id"]: r for r in results}
    if len(measured) != len(results) or set(measured) != {r["task_id"] for r in parent}:
        raise ValueError("token selection requires complete parent-panel measurements")
    selected, excluded, decisions, strata = [], [], Counter(), Counter()
    for row in parent:
        result = measured[row["task_id"]]
        expected_decisions = sum(c["decisions"] for c in row["reference_costs"].values())
        if result["decisions"] != expected_decisions or not result.get("processor_cross_checked"):
            raise ValueError("missing complete family/processor measurements")
        distributions = result["token_distributions"]
        if set(distributions) != {"text-state", "visual-state", "multimodal-state"} or any(
            sum(histogram.values()) != expected_decisions for histogram in distributions.values()
        ):
            raise ValueError("partial modality decision counts cannot select a task")
        maximum = max(int(n) for histogram in distributions.values() for n in histogram)
        if maximum != result["maximum_input_tokens"]:
            raise ValueError("task token maximum disagrees with measurements")
        if maximum > MAX_INPUT_TOKENS:
            excluded.append(
                {
                    **row,
                    "outcome": "VALID_STOP",
                    "reason": "complete_input_exceeds_32k_context",
                    "maximum_input_tokens": maximum,
                    "overflow_decisions_by_modality": {
                        m: sum(v for n, v in h.items() if int(n) > MAX_INPUT_TOKENS) for m, h in distributions.items()
                    },
                    "decision_measurements": result["decision_measurements"],
                }
            )
        else:
            selected.append(row)
        status = "excluded" if maximum > MAX_INPUT_TOKENS else "selected"
        for algorithm, cost in row["reference_costs"].items():
            strata[f"{status}/{algorithm}/{row['split']}/{row['domain']}/{row['difficulty']}"] += 1
            decisions[f"{status}/{algorithm}/{row['split']}"] += cost["decisions"]
    if not selected:
        raise ValueError("no complete tasks fit the 32K context")
    return {
        "schema_version": "modality_view_panel_v2",
        "panel_id": PANEL_ID,
        "source_panel": SOURCE_PANEL,
        "measurement_report": measurement_report,
        "selection_uses_model_outcomes": False,
        "authorization_basis": (
            "User authorized exclusion of instances requiring more than 32K tokens, "
            "aligned with BFS/BFWS source training data."
        ),
        "selection_rule": (
            "Exclude whole task group when any decision/modality exceeds 32384 input tokens; "
            "additive settings enter and leave together."
        ),
        "max_context_tokens": 32768,
        "reserved_output_tokens": OUTPUT_TOKENS,
        "max_input_tokens": MAX_INPUT_TOKENS,
        "source_counts": counts(parent, measured),
        "expected": counts(selected, measured),
        "selected": selected,
        "excluded": excluded,
        "exclusion_counts": counts(excluded, measured),
        "strata": dict(sorted(strata.items())),
        "decisions_by_algorithm_split": dict(sorted(decisions.items())),
        "maximum_retained_input_tokens": max(measured[r["task_id"]]["maximum_input_tokens"] for r in selected),
        "model_input_ready": False,
        "scientific_completion": False,
    }


def load_view_panel(root: Path, path: Path) -> tuple[list[dict], dict]:
    """Validate the successor selection and return its exact view contract."""
    panel = read_json(path)
    if panel.get("panel_id") != PANEL_ID or panel.get("source_panel") != SOURCE_PANEL:
        raise ValueError("unknown readable-view panel")
    measurement = read_json(root / panel["measurement_report"])
    if measurement.get("contract") != CONTRACT or not measurement.get("complete_parent_coverage"):
        raise ValueError("panel lacks complete matching processor measurements")
    parent = read_json(root / SOURCE_PANEL)["selected"]
    expected_panel = select_view_panel(parent, measurement["results"], panel["measurement_report"])
    if panel != expected_panel or panel["source_counts"] != EXPECTED:
        raise ValueError("successor panel differs from measured whole-task selection")
    return panel["selected"], {
        **CONTRACT,
        "contract_id": VIEW_CONTRACT_ID,
        "expected": panel["expected"],
        "panel_manifest": str(path.resolve().relative_to(root.resolve())),
        "panel_id": PANEL_ID,
    }
