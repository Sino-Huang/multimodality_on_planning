"""Context selection keeps matched whole tasks and source training assignments."""

import copy

import pytest

from examples.planning_benchmark_slice.modality_view_panel import MAX_INPUT_TOKENS, select_view_panel
from examples.planning_benchmark_slice.modality_view_preparation import CONTRACT, require_approval


def task(identity, algorithms=("bfs",), split="train", domain="visitall"):
    return {
        "task_id": identity,
        "split": split,
        "domain": domain,
        "difficulty": "hard",
        "trace_paths": {a: f"{identity}/{a}.json" for a in algorithms},
        "reference_costs": {a: {"decisions": 2, "expansions": 1} for a in algorithms},
    }


def measured(row, maximum=MAX_INPUT_TOKENS):
    decisions = sum(c["decisions"] for c in row["reference_costs"].values())
    return {
        "task_id": row["task_id"],
        "states": 3,
        "decisions": decisions,
        "maximum_input_tokens": maximum,
        "processor_cross_checked": True,
        "token_distributions": {m: {maximum: decisions} for m in ("text-state", "visual-state", "multimodal-state")},
        "decision_measurements": f"measure/{row['task_id']}.json.gz",
    }


def test_32k_boundary_excludes_whole_task_across_modalities():
    rows = [task("bfs/fit"), task("best_first_width/over", ("best_first_width",), "dev")]
    results = [measured(rows[0]), measured(rows[1], MAX_INPUT_TOKENS + 1)]
    panel = select_view_panel(rows, results, "measure/report.json")
    assert panel["selected"] == rows[:1]
    assert panel["excluded"][0]["task_id"] == rows[1]["task_id"]
    assert panel["excluded"][0]["outcome"] == "VALID_STOP"
    assert panel["expected"] == {"tasks": 1, "states": 3, "decisions": 2}
    assert panel["source_counts"] == {"tasks": 2, "states": 6, "decisions": 4}
    assert not panel["selection_uses_model_outcomes"]
    assert not panel["model_input_ready"]


def test_one_overflow_decision_in_one_modality_excludes_both_additive_settings():
    rows = [task("bfs/fit"), task("pair", ("best_first_add_greedy", "best_first_add_w3"))]
    pair = measured(rows[1], 100)
    pair["maximum_input_tokens"] = MAX_INPUT_TOKENS + 1
    pair["token_distributions"]["multimodal-state"] = {100: 3, MAX_INPUT_TOKENS + 1: 1}
    panel = select_view_panel(rows, [measured(rows[0]), pair], "measure/report.json")
    excluded = panel["excluded"][0]
    assert set(excluded["reference_costs"]) == {"best_first_add_greedy", "best_first_add_w3"}
    assert excluded["overflow_decisions_by_modality"] == {"text-state": 0, "visual-state": 0, "multimodal-state": 1}
    assert panel["exclusion_counts"]["decisions"] == 4


def test_source_splits_traces_costs_and_domain_are_preserved():
    rows = [task("bfs/source-name-train", split="dev", domain="snake"), task("bfws/fit", ("best_first_width",))]
    original = copy.deepcopy(rows)
    panel = select_view_panel(rows, [measured(r) for r in rows], "measure/report.json")
    assert panel["selected"] == rows == original
    assert panel["strata"]["selected/bfs/dev/snake/hard"] == 1
    assert panel["decisions_by_algorithm_split"]["selected/bfs/dev"] == 2


@pytest.mark.parametrize(
    "corruption",
    ["missing_task", "duplicate_task", "partial_modality", "missing_modality", "unchecked_processor", "wrong_maximum"],
)
def test_partial_or_inconsistent_measurements_cannot_select(corruption):
    rows = [task("a"), task("b")]
    results = [measured(r) for r in rows]
    if corruption == "missing_task":
        results.pop()
    elif corruption == "duplicate_task":
        results.append(results[0])
    elif corruption == "partial_modality":
        results[0]["token_distributions"]["text-state"] = {MAX_INPUT_TOKENS: 1}
    elif corruption == "missing_modality":
        del results[0]["token_distributions"]["visual-state"]
    elif corruption == "unchecked_processor":
        results[0]["processor_cross_checked"] = False
    else:
        results[0]["maximum_input_tokens"] += 1
    with pytest.raises(ValueError):
        select_view_panel(rows, results, "report.json")


def test_smaller_panel_approval_is_bound_to_successor_contract(tmp_path):
    contract = {
        **CONTRACT,
        "contract_id": "issue-72-readable-pages-v2",
        "expected": {"tasks": 1, "states": 3, "decisions": 2},
        "panel_id": "selected-panel",
        "panel_manifest": "panel.json",
    }
    qualification = {
        "contract": contract,
        "counts": contract["expected"],
        "complete_selected_coverage": True,
        "outcome": "PASS",
        "processor_qualified": True,
        "attempt_id": "q2",
        "recommended_context": 32768,
        "preview_index": "q2/previews.json",
    }
    approval = {
        "contract_id": contract["contract_id"],
        "qualification_attempt": "q2",
        "materialization_output": str(tmp_path.resolve()),
        "approved_context": 32768,
        "readability_approved": True,
        "preview_index": "q2/previews.json",
        "approved_by": "human",
    }
    require_approval(approval, qualification, tmp_path, contract)
    with pytest.raises(ValueError):
        require_approval(approval, qualification, tmp_path)
    with pytest.raises(ValueError):
        require_approval(approval, {**qualification, "counts": CONTRACT["expected"]}, tmp_path, contract)


def test_loading_panel_binds_retained_counts_and_rejects_changed_split(tmp_path, monkeypatch):
    from examples.planning_benchmark_slice import modality_view_panel as selection
    from examples.planning_benchmark_slice.modality_view_preparation import write_json

    rows = [task("bfs/fit", split="dev"), task("bfws/over", ("best_first_width",))]
    results = [measured(rows[0]), measured(rows[1], MAX_INPUT_TOKENS + 1)]
    panel = select_view_panel(rows, results, "measurement.json")
    monkeypatch.setattr(selection, "EXPECTED", panel["source_counts"])
    write_json(tmp_path / selection.SOURCE_PANEL, {"selected": rows})
    write_json(
        tmp_path / "measurement.json", {"contract": CONTRACT, "complete_parent_coverage": True, "results": results}
    )
    path = tmp_path / "panel.json"
    write_json(path, panel)
    selected, contract = selection.load_view_panel(tmp_path, path)
    assert selected == rows[:1]
    assert contract["expected"] == {"tasks": 1, "states": 3, "decisions": 2}
    assert contract["contract_id"] == selection.VIEW_CONTRACT_ID
    panel["selected"][0]["split"] = "train"
    write_json(path, panel)
    with pytest.raises(ValueError, match="differs"):
        selection.load_view_panel(tmp_path, path)
