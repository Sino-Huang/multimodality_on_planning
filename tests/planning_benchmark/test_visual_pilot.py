"""Bound the deadline pilot without launching a model or dropping source facts."""

import json
import sys
import time

import pytest

from examples.planning_benchmark_slice.modality_view_preparation import write_json
from examples.planning_benchmark_slice.visual_experiment import ROOT, VisualExperiment, select_coverage
from examples.planning_benchmark_slice.visual_jobs import adjudicate, jobs_for
from examples.planning_benchmark_slice.visual_model import VisualDataset
from examples.planning_benchmark_slice.visual_pilot import balanced_sample
from scripts.run_visual_issue75 import main, run_children

PILOT = ROOT / "configs/experiments/issue75/pilot.json"


def test_default_cli_is_a_four_hour_single_seed_pilot(capsys):
    assert main(["all", "--dry-run"]) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert report["clock_seconds"] == 4 * 3600
    assert report["evaluation_seeds"] == [17] and report["training_seed"] == 17
    assert report["planned_condition_episodes"] == 48
    assert report["study_scope"] == "deadline_pilot"
    assert set(report["optimizer_steps"].values()) == {16}
    assert set(report["train_records"].values()) == {512}
    assert not report["model_calls_started"]


def test_pilot_datasets_use_declared_disjoint_train_and_dev_records(tmp_path):
    e = VisualExperiment(PILOT, tmp_path / "run")
    assert e.pilot is not None
    assert e.pilot["domains"] == ["storage", "blocksworld", "ferry"]
    for algorithm in e.config["algorithms"]:
        train = VisualDataset(
            ROOT, ROOT / e.config["corpus_report"], algorithm, record_ids=e.pilot["training_record_ids"][algorithm]
        )
        dev = VisualDataset(
            ROOT,
            ROOT / e.config["corpus_report"],
            algorithm,
            split="dev",
            record_ids=e.pilot["diagnostic_record_ids"][algorithm],
        )
        assert len(train) == 512 and 0 < len(dev) <= 32
        assert all(r["split"] == "train" and r["tokens"]["input"]["visual-state"] <= 4096 for r in train.records)
        assert all(r["split"] == "dev" and r["task_id"] in e.pilot["selected_task_ids"] for r in dev.records)
        assert not {r["record_id"] for r in train.records} & {r["record_id"] for r in dev.records}
    e.start()
    q, cid = e.reused_qualification()
    report = select_coverage(e, q)
    assert report["outcome"] == "PASS" and report["selection"]["mode"] == "deadline_pilot"
    report["qualification_contract_id"] = cid
    write_json(e.output / "qualification.json", report)
    e.require("train")
    jobs = [j for worker in range(2) for j in jobs_for(e, False, worker, 2)]
    assert len(jobs) == 24 and {j[3] for j in jobs} == {17}


def test_sampling_balances_domains_and_never_truncates_records():
    records = [
        {
            "record_id": f"{d}-{i}",
            "domain": d,
            "task_id": d,
            "decision_index": i,
            "difficulty": "easy",
            "tokens": {"input": {"visual-state": 100}},
            "fact": "complete",
        }
        for d in ["a", "b"]
        for i in range(10)
    ]
    selected = balanced_sample(records, 6, 100)
    assert len(selected) == 6
    assert sum(r["domain"] == "a" for r in selected) == 3
    assert all(r in records for r in selected)


def test_wall_clock_watchdog_stops_owned_worker(tmp_path, monkeypatch):
    e = VisualExperiment(PILOT, tmp_path / "run")
    e.start()
    end = time.monotonic() + 0.2
    monkeypatch.setattr(e, "deadline", lambda stage="calls": end if stage == "gate" else float("inf"))
    job = {"worker": 0, "command": [sys.executable, "-c", "import time; time.sleep(60)"], "environment": {}}
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="wall-clock limit"):
        run_children(e, "train", [job])
    assert time.monotonic() - started < 5


def test_partial_pilot_cannot_be_adjudicated_as_complete(tmp_path):
    e = VisualExperiment(PILOT, tmp_path / "run")
    e.start()
    qualifications, _ = e.reused_qualification()
    write_json(e.output / "qualification.json", select_coverage(e, qualifications))
    for stage in ("references", "evaluation"):
        write_json(e.output / f"{stage}.json", {"episodes": []})
    with pytest.raises(ValueError, match="lacks complete frozen episode coverage"):
        adjudicate(e, lambda *args, **kwargs: None)
