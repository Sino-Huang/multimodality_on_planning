"""Cost-only pruning, shared modality membership and execution coverage."""

import copy

import pytest

from examples.planning_benchmark_slice import visual_panel as panels
from examples.planning_benchmark_slice.modality_corpus import MODALITIES
from examples.planning_benchmark_slice.modality_view_preparation import write_json
from examples.planning_benchmark_slice.visual_experiment import ROOT, VisualExperiment, select_coverage
from examples.planning_benchmark_slice.visual_jobs import jobs_for


def row(task_id, algorithm, domain="rooms"):
    return {"task_id": task_id, "domain": domain, "reference_costs": {algorithm: {"decisions": 1}}}


def test_input_cost_curve_does_not_charge_every_input_the_global_maximum():
    curve = panels.InputCostCurve(
        [
            {"input_tokens": 1000, "seconds_per_call": 2},
            {"input_tokens": 2000, "seconds_per_call": 1},
            {"input_tokens": 4000, "seconds_per_call": 8},
        ]
    )
    assert [curve.seconds(n) for n in [500, 1500, 3000, 8000]] == [2, 2, 8, 16]
    assert 10 * curve.seconds(1000) < 4 * curve.seconds(4000)


def test_cost_pruning_preserves_coverage_even_when_the_floor_exceeds_budget():
    rows = [
        row("small", "bfs"),
        row("expensive", "bfs"),
        row("bfws", "best_first_width"),
        row("paired", "best_first_add_w3"),
    ]
    rows[-1]["reference_costs"]["best_first_add_greedy"] = {"decisions": 1}
    costs = {"small": 2, "expensive": 100, "bfws": 4, "paired": 3}
    groups = [[r["task_id"]] for r in rows]
    selected, mandatory, floor, total = panels.choose_groups(rows, groups, costs, 1, 8, 1)
    assert selected == mandatory == ["bfws", "paired", "small"]
    assert floor == total == 9
    assert panels.choose_groups(list(reversed(rows)), list(reversed(groups)), costs, 1, 8, 1)[0] == selected


def test_shared_problem_algorithms_are_kept_or_removed_together():
    rows = [row("shared-bfs", "bfs"), row("shared-bfws", "best_first_width"), row("expensive", "bfs")]
    groups = [["shared-bfs", "shared-bfws"], ["expensive"]]
    selected, _, _, _ = panels.choose_groups(
        rows, groups, {"shared-bfs": 1, "shared-bfws": 2, "expensive": 100}, 1, 3, 1
    )
    assert selected == ["shared-bfs", "shared-bfws"]


def test_real_panel_has_identical_modality_membership_and_no_lost_family(tmp_path):
    e = VisualExperiment(output=tmp_path / "run")
    panel = e.cost_panel
    assert panel is not None
    assert len(panel["selected_task_ids"]) == 42 and len(panel["excluded_task_ids"]) == 55
    all_keys = {(r["domain"], panels.family(a)) for r in e.dev for a in r["reference_costs"]}
    selected = [r for r in e.dev if r["task_id"] in panel["selected_task_ids"]]
    assert {(r["domain"], panels.family(a)) for r in selected for a in r["reference_costs"]} == all_keys
    for algorithm in e.config["algorithms"]:
        ids = [panels.panel_task_ids(panel, m, algorithm) for m in MODALITIES]
        assert ids[0] == ids[1] == ids[2]
    assert panels.panel_task_ids(panel, "visual-state", "best_first_add_w3") == panels.panel_task_ids(
        panel, "visual-state", "best_first_add_greedy"
    )
    assert panel["training"]["corpus_changed"] is False
    assert sum(t["training_records"] for t in panel["training"]["settings"]) == 43876
    assert panel["evaluation"]["proxy_work_reduction_percent"] > 80
    assert panel["evaluation"]["fits_evaluation_budget"] is False
    e.start()
    q, source = e.reused_qualification()
    report = select_coverage(e, q)
    report["qualification_contract_id"] = source
    write_json(e.output / "qualification.json", report)
    e.require("references")
    jobs = [j for worker in range(2) for j in jobs_for(e, False, worker, 2)]
    assert {j[0]["task_id"] for j in jobs} == set(panel["selected_task_ids"])
    assert len(jobs) == sum(len(r["reference_costs"]) for r in selected) * 2 * 5
    report["selection"] = {"mode": "full", "task_ids": [r["task_id"] for r in e.dev]}
    write_json(e.output / "qualification.json", report)
    with pytest.raises(ValueError, match="cost-ranked panel"):
        e.require("references")


def test_changing_reference_outputs_cannot_change_the_cost_selection(monkeypatch):
    e = VisualExperiment()
    assert e.cost_panel is not None
    original = panels.iter_shard

    def changed(path):
        for record in original(path):
            record["target"] = {"unrelated": "teacher output is not a selection signal"}
            record["after_operation"] = {"runtime_result": {"accepted": False}}
            yield record

    monkeypatch.setattr(panels, "iter_shard", changed)
    rebuilt = panels.build_cost_panel(e)
    assert rebuilt["selected_task_ids"] == e.cost_panel["selected_task_ids"]
    assert {t["task_id"]: t["proxy_gpu_seconds"] for t in rebuilt["tasks"]} == {
        t["task_id"]: t["proxy_gpu_seconds"] for t in e.cost_panel["tasks"]
    }


def test_panel_binding_rejects_changed_seeds_or_partial_source_scope(tmp_path):
    e = VisualExperiment()
    assert e.cost_panel is not None
    config = copy.deepcopy(e.config)
    config["evaluation_seeds"] = [17]
    with pytest.raises(ValueError, match="settings differ"):
        panels.load_cost_panel(ROOT / e.config["cost_panel"], config, e.dev)
    partial = copy.deepcopy(e.cost_panel)
    partial["tasks"].pop()
    write_json(tmp_path / "partial.json", partial)
    with pytest.raises(ValueError, match="every source dev task"):
        panels.load_cost_panel(tmp_path / "partial.json", e.config, e.dev)


def test_resume_keeps_the_selected_panel_snapshot(tmp_path):
    e = VisualExperiment(output=tmp_path / "run")
    assert e.cost_panel is not None
    attempt = e.start()
    assert attempt["cost_panel"] == e.cost_panel
    e.cost_panel["policy"]["evaluation_budget_seconds"] += 1
    with pytest.raises(ValueError, match="experiment differs"):
        e.start(resume=True)
