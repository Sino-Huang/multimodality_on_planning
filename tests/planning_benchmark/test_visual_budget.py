"""Replay the real v3 budget rejection without model calls."""

import copy
import math

import pytest

from examples.planning_benchmark_slice.modality_view_preparation import write_json
from examples.planning_benchmark_slice.scene_assets import read_json
from examples.planning_benchmark_slice.visual_experiment import ROOT, VisualExperiment, select_coverage

SOURCE = ROOT / "outputs/visual_development/issue75-32k-v3/attempt-001/qualification.json"


def test_advisory_estimate_does_not_reject_passed_hardware_qualification(tmp_path):
    experiment = VisualExperiment(output=tmp_path / "run")
    experiment.config["budget_mode"] = "advisory"
    experiment.start()
    source = read_json(SOURCE)
    assert all(q["outcome"] == "PASS" for q in source["device_qualifications"])
    report = select_coverage(experiment, source["device_qualifications"])
    assert report["outcome"] == "PASS"
    assert report["selection"]["mode"] == "full"
    assert len(report["selection"]["task_ids"]) == 97
    assert report["estimates"][0]["projected_total_seconds"] > experiment.config["gate_seconds"]


def test_hard_budget_still_reports_the_measured_rejection(tmp_path):
    experiment = VisualExperiment(output=tmp_path / "run")
    experiment.config["budget_mode"] = "hard"
    experiment.start()
    report = select_coverage(experiment, read_json(SOURCE)["device_qualifications"])
    assert report["outcome"] == "VALID_STOP"
    assert report["hardware_qualification"] == "PASS"
    assert report["estimate_kind"] == "stress_projection_not_eta"
    assert not any(e["fits_reference_budget"] for e in report["estimates"])


def test_advisory_mode_has_no_hidden_wall_time_cutoff(tmp_path):
    experiment = VisualExperiment(output=tmp_path / "run")
    experiment.config["budget_mode"] = "advisory"
    attempt = experiment.start()
    attempt["started_monotonic"] -= 100 * experiment.config["gate_seconds"]
    write_json(experiment.output / "attempt.json", attempt)
    assert math.isinf(experiment.deadline()) and math.isinf(experiment.deadline("gate"))
    experiment.require("qualify")


def test_reuse_of_completed_hardware_probes_keeps_their_original_contract(tmp_path):
    experiment = VisualExperiment(output=tmp_path / "run")
    qualifications, original_contract = experiment.reused_qualification()
    assert original_contract == "issue-75-visual-development-32k-v3"
    assert len(qualifications) == 2 and all(q["probe_records"] == 31 for q in qualifications)
    experiment.start()
    report = select_coverage(experiment, qualifications)
    report["qualification_contract_id"] = original_contract
    write_json(experiment.output / "qualification.json", report)
    experiment.require("train")
    experiment.require("references")
    experiment.config["max_batch_size"] = 1
    with pytest.raises(ValueError, match="unchanged model"):
        experiment.reused_qualification()


def test_public_qualification_reuse_runs_without_launching_models(tmp_path, monkeypatch):
    from scripts import run_visual_issue75 as runner

    def no_children(*args):
        pytest.fail("reusing qualification must not launch GPU workers")

    monkeypatch.setattr(runner, "run_children", no_children)
    output = tmp_path / "reused"
    assert runner.main(["qualify", "--output", str(output)]) == 0
    report = read_json(output / "qualification.json")
    assert report["outcome"] == "PASS" and report["budget_mode"] == "advisory"
    assert report["qualification_contract_id"] == "issue-75-visual-development-32k-v3"
    assert len(report["selection"]["task_ids"]) == 97
    assert not (output / "result.json").exists()


@pytest.mark.parametrize("defect", ["missing_worker", "failed_worker"])
def test_advisory_mode_never_accepts_missing_or_failed_hardware(tmp_path, defect):
    experiment = VisualExperiment(output=tmp_path / "run")
    experiment.start()
    qualifications = copy.deepcopy(read_json(SOURCE)["device_qualifications"])
    if defect == "missing_worker":
        qualifications.pop()
    else:
        qualifications[0]["outcome"] = "INVALID"
    with pytest.raises(ValueError, match="complete passed hardware"):
        select_coverage(experiment, qualifications)
