"""Preparation commands must expose a resource stop without starting GPU work."""

import copy
import json

import pytest

from examples.planning_benchmark_slice.matched_tasks import DEFAULT_STUDY, require_pool_coverage
from examples.planning_benchmark_slice.scene_assets import read_json
from scripts.run_matched_modalities import main, validate_settings


@pytest.mark.parametrize("stage", ["prepare", "verify", "qualify", "train", "decide", "evaluate"])
def test_stage_dry_runs_do_not_create_outputs_or_claim_readiness(tmp_path, capsys, stage):
    study = read_json(DEFAULT_STUDY)
    study["output_root"] = str(tmp_path / "absent-output")
    path = tmp_path / "study.json"
    path.write_text(json.dumps(study))
    assert main([stage, "--study", str(path), "--dry-run"]) == 0
    output = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert output["writes"] == output["model_calls"] == 0
    assert output["execution_admitted"] is False and output["model_input_ready"] is False
    assert not (tmp_path / "absent-output").exists()


@pytest.mark.parametrize("stage", ["qualify", "train", "evaluate"])
def test_missing_final_tasks_prevent_gpu_stage_and_budget_spend(tmp_path, capsys, stage):
    study = read_json(DEFAULT_STUDY)
    study["output_root"] = str(tmp_path / "absent-output")
    path = tmp_path / "study.json"
    path.write_text(json.dumps(study))
    assert main([stage, "--study", str(path), "--resume"]) == 2
    output = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert output["outcome"] == "VALID_STOP"
    assert output["gpu_stage_seconds"] == 0 and output["model_calls"] == 0
    assert not (tmp_path / "absent-output").exists()


def test_ports_and_cumulative_budget_cannot_be_reset():
    study = read_json(DEFAULT_STUDY)
    with pytest.raises(ValueError, match="MASTER_PORT"):
        validate_settings(study, ["0", "1"], [18775, 18775])
    changed = copy.deepcopy(study)
    changed["budget"]["reset_on_resume"] = True
    with pytest.raises(ValueError, match="budget"):
        validate_settings(changed, ["0", "1"], [18775, 18776])
    # Negative performance is not an admission criterion for the new study.
    study["development_metrics"] = {"success": 0, "invalid_rate": 1}
    validate_settings(study, ["0", "1"], [18775, 18776])


def test_partial_candidate_pool_cannot_be_reused_as_complete():
    study = read_json(DEFAULT_STUDY)
    rows = [
        {"domain": d, "seed": s}
        for d in study["final"]["domains"]
        for s in study["final"]["candidate_profiles"][d]["seeds"]
    ]
    pool = {"study": study, "candidate_preparation_complete": True, "candidates": rows}
    require_pool_coverage(pool, study)
    pool["candidates"] = rows[:-1]
    with pytest.raises(ValueError, match="incomplete"):
        require_pool_coverage(pool, study)


def test_terminal_preparation_cannot_be_resumed_or_overwritten(tmp_path, capsys):
    study = read_json(DEFAULT_STUDY)
    study["output_root"] = str(tmp_path / "output")
    path = tmp_path / "study.json"
    path.write_text(json.dumps(study))
    result = tmp_path / "output/preparation/report.json"
    result.parent.mkdir(parents=True)
    result.write_text('{"outcome":"VALID_STOP"}\n')
    assert main(["prepare", "--study", str(path), "--resume"]) == 2
    assert "terminal preparation" in capsys.readouterr().out
    assert result.read_text() == '{"outcome":"VALID_STOP"}\n'


def test_interrupted_preparation_needs_explicit_resume(tmp_path, capsys):
    study = read_json(DEFAULT_STUDY)
    study["output_root"] = str(tmp_path / "output")
    path = tmp_path / "study.json"
    path.write_text(json.dumps(study))
    marker = tmp_path / "output/preparation/preparing.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"study": study, "gpu_stage_seconds": 0}))
    assert main(["prepare", "--study", str(path)]) == 2
    assert "--resume" in capsys.readouterr().out
