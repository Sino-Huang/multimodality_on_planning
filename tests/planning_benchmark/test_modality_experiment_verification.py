"""Ensure closeout counts actual task/condition/seed coverage, including missing runs."""

import pytest

from examples.planning_benchmark_slice.modality_view_preparation import write_json
from examples.planning_benchmark_slice.visual_experiment import ROOT, VisualExperiment
from scripts.verify_modality_experiment import coverage, expected_episodes, point_metrics, verify


def test_coverage_requires_every_frozen_condition_and_seed():
    rows = [{"task_id": "a", "reference_costs": {"bfs": {}}}, {"task_id": "b", "reference_costs": {"bfs": {}}}]
    expected = expected_episodes(rows, [17, 29])
    assert len(expected) == 14
    episodes = [dict(zip(("task_id", "algorithm", "arm", "seed"), key, strict=True)) for key in sorted(expected)]
    assert coverage(episodes, expected)["complete"]
    partial = coverage(episodes[:-1], expected)
    assert not partial["complete"] and partial["completed"] == 13 and len(partial["missing"]) == 1
    with pytest.raises(ValueError, match="duplicate"):
        coverage(episodes + episodes[:1], expected)
    with pytest.raises(ValueError, match="outside declared"):
        coverage([{**episodes[0], "task_id": "unselected"}], expected)


def test_point_metrics_charge_invalid_operations_and_do_not_confuse_success_with_validity():
    episodes = [
        {
            "algorithm": "bfs",
            "arm": "process_sft",
            "result": {
                "invariant_valid_success": success,
                "invalid_operation_count": invalid,
                "decision_count": decisions,
                "model_call_limit": 10,
            },
        }
        for success, invalid, decisions in [(True, 0, 5), (False, 1, 1)]
    ]
    result = point_metrics(episodes)["bfs"]["process_sft"]
    assert result["invariant_valid_success"] == 0.5
    assert result["invalid_operation_rate"] == 1 / 6
    assert result["budget_usage"] == 6 / 20


def test_live_or_absent_run_is_not_a_terminal_experiment(tmp_path):
    e = VisualExperiment(ROOT / "configs/experiments/issue76/experiment.json", tmp_path / "run")
    with pytest.raises(ValueError, match="no terminal result"):
        verify(e)


@pytest.mark.parametrize("claims_complete", [False, True])
def test_terminal_stop_keeps_missing_coverage_explicit(tmp_path, claims_complete):
    e = VisualExperiment(ROOT / "configs/experiments/issue76/experiment.json", tmp_path / "run")
    e.start()
    write_json(
        e.output / "result.json",
        {
            "contract_id": e.config["contract_id"],
            "outcome": "VALID_STOP",
            "scientific_completion": False,
            "pilot_complete": claims_complete,
        },
    )
    if claims_complete:
        with pytest.raises(ValueError, match="claims completion without complete evidence"):
            verify(e)
    else:
        report = verify(e)
        assert report["verification_outcome"] == "PARTIAL"
        assert not report["execution_complete"]
        assert report["coverage"]["completed"] == 0 and report["coverage"]["total"] == 48
