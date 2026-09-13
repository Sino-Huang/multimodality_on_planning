"""Real process clocks and complete final-view bindings, without training GPUs."""

import json
import subprocess
import sys
import time

import pytest

from examples.planning_benchmark_slice.matched_execution import admission_estimate, verify_training_cell
from examples.planning_benchmark_slice.matched_scheduler import StageBudget, run_gpu_jobs
from examples.planning_benchmark_slice.matched_tasks import ROOT
from examples.planning_benchmark_slice.scene_assets import read_json


def small_study():
    return {
        "output_root": "run",
        "budget": {
            "qualification_seconds": 2,
            "training_development_seconds": 2,
            "final_evaluation_seconds": 2,
            "shutdown_reserve_seconds_per_stage": 0.05,
        },
        "launch": {"devices": [0, 1], "master_ports": [18775, 18776]},
    }


def test_stage_clock_is_shared_locked_and_resumes_remaining_budget(tmp_path):
    study = small_study()
    with StageBudget(tmp_path, study, "qualify"):
        time.sleep(0.02)
        with pytest.raises(RuntimeError, match="live"):
            with StageBudget(tmp_path, study, "train"):
                pass
    with StageBudget(tmp_path, study, "qualify") as second:
        assert second.segment["prior_spent"] >= 0.02
        assert second.hard - time.monotonic() < 1.99
    ledger = read_json(tmp_path / "run/budget.json")
    assert len(ledger["segments"]) == 2
    assert all(s["ended"] >= s["started"] for s in ledger["segments"])


def test_hard_deadline_kills_only_owned_process_group(tmp_path):
    script = tmp_path / "scripts/run_matched_modalities.py"
    script.parent.mkdir()
    script.write_text("import time\ntime.sleep(10)\n")
    study = small_study()
    study["budget"]["qualification_seconds"] = 0.3
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    started = time.monotonic()
    try:
        with pytest.raises(RuntimeError, match="deadline"):
            run_gpu_jobs(tmp_path, study, "qualify", [{"result_path": "unused"}], lambda *a, **k: None)
        assert time.monotonic() - started < 2
        assert other.poll() is None
        with pytest.raises(RuntimeError, match="exhausted"):
            with StageBudget(tmp_path, study, "qualify"):
                pass
    finally:
        other.terminate()
        other.wait()


def test_successor_carries_budget_and_refuses_changed_training(tmp_path):
    previous = small_study()
    previous.update(study_id="v2", final={}, training={"epochs": 1})
    (tmp_path / "previous.json").write_text(json.dumps(previous))
    current = {
        **previous,
        "study_id": "v3",
        "output_root": "successor",
        "predecessor_study": "v2",
        "qualification_predecessor": "previous.json",
    }
    with StageBudget(tmp_path, previous, "qualify"):
        time.sleep(0.02)
    with StageBudget(tmp_path, current, "qualify") as clock:
        assert clock.segment["prior_spent"] >= 0.02
        assert clock.path == tmp_path / "run/budget.json"
        with pytest.raises(RuntimeError, match="live"):
            with StageBudget(tmp_path, previous, "train"):
                pass
    current["training"] = {"epochs": 2}
    with pytest.raises(ValueError, match="identical training"):
        StageBudget(tmp_path, current, "qualify")


def test_missing_matched_checkpoint_never_passes(tmp_path):
    study = read_json(ROOT / "configs/experiments/matched-modalities/study-v2.json")
    with pytest.raises(FileNotFoundError):
        verify_training_cell(tmp_path, study, {"result_path": "absent", "algorithm": "bfs"})


def test_admission_prices_all_modalities_and_worst_gpu():
    study = read_json(ROOT / "configs/experiments/matched-modalities/study-v2.json")
    panel = {"tasks": [{"row": {"reference_costs": {a: {"decisions": 10} for a in study["algorithms"]}}}] * 3}
    worker = {
        "modalities": {
            m: {
                "training_microstep_seconds": 1,
                "seconds_per_call": 2,
                "training_load_seconds": 3,
                "inference_load_seconds": 4,
                "adapter_save_seconds": 1,
            }
            for m in study["modalities"]
        }
    }
    other = json.loads(json.dumps(worker))
    other["modalities"]["multimodal-state"]["seconds_per_call"] = 500
    estimate = admission_estimate(study, panel, [worker, other])
    assert not estimate["fits"]
    assert estimate["training_fits"]
    assert not estimate["evaluation_fits"]
    assert estimate["by_modality"]["multimodal-state"]["seconds_per_call"] == 500
