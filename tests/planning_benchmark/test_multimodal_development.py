"""Exercise real multimodal inputs and replay without model launches."""

import copy
import json
import tempfile
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.modality_view_preparation import frozen_processor
from examples.planning_benchmark_slice.visual_episode import VisualSession, VisualTaskViews, replay_visual_episode
from examples.planning_benchmark_slice.visual_experiment import ALGORITHMS, ROOT, VisualExperiment
from examples.planning_benchmark_slice.visual_jobs import select_probes
from examples.planning_benchmark_slice.visual_model import VisualCollator, VisualDataset
from scripts.run_visual_issue75 import main

CONFIG = ROOT / "configs/experiments/issue76/experiment.json"


def test_multimodal_dry_run_requires_fresh_qualification_and_bounds_work(capsys):
    assert main(["all", "--dry-run", "--config", str(CONFIG)]) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert report["modality"] == "multimodal-state"
    assert report["clock_seconds"] == 14400
    assert report["planned_condition_episodes"] == 48
    assert set(report["optimizer_steps"].values()) == {16}
    assert len(report["commands"]["qualify"]) == 2
    assert report["master_ports"] == [18675, 18676]
    assert not report["model_calls_started"]
    assert "training_unmatched" in report["comparison_scope"]


def test_multimodal_pilot_probes_cover_maximum_inputs_without_full_corpus_probes():
    e = VisualExperiment(CONFIG)
    assert e.pilot is not None
    probes = select_probes(e)
    assert len(probes) == 8
    for algorithm in ALGORITHMS:
        ids = set(e.pilot["training_record_ids"][algorithm])
        records = [
            r
            for split in ("train", "dev")
            for r in e.corpus.records(algorithm=algorithm, split=split)
            if r["record_id"] in ids or (r["split"] == "dev" and r["task_id"] in e.pilot["selected_task_ids"])
        ]
        assert max(r["tokens"]["input"]["multimodal-state"] for r in records) == max(
            r["tokens"]["input"]["multimodal-state"] for r in probes if r["algorithm"] == algorithm
        )


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_multimodal_training_and_live_reference_use_same_modality_and_replay(algorithm):
    e = VisualExperiment(CONFIG)
    assert e.pilot is not None
    dataset = VisualDataset(
        ROOT,
        ROOT / e.config["corpus_report"],
        algorithm,
        record_ids=e.pilot["training_record_ids"][algorithm],
        modality="multimodal-state",
    )
    example = dataset[0]
    count = frozen_processor().count(example["messages"][:-1])
    assert count == dataset.records[0]["tokens"]["input"]["multimodal-state"]
    assert count > dataset.records[0]["tokens"]["input"]["visual-state"]
    labels = VisualCollator(frozen_processor().processor)([example])["labels"][0]
    assert (labels[:count] == -100).all() and (labels[count:] != -100).any()
    row = min(
        (r for r in e.dev if algorithm in r["reference_costs"] and r["task_id"] in e.pilot["selected_task_ids"]),
        key=lambda r: r["reference_costs"][algorithm]["decisions"],
    )
    with tempfile.TemporaryDirectory(dir=ROOT / "outputs", prefix="test-mm76-") as temporary:
        output = Path(temporary)
        views = VisualTaskViews(
            ROOT,
            row,
            e.corpus.results[row["task_id"]]["view_manifest"],
            output / "views",
            e.config["backend_endpoints"][0],
        )
        session = VisualSession(
            ROOT, row, algorithm, "exact_reference", 17, output, e.config["contract_id"], views=views
        )
        while (request := session.next_request()) is not None:
            observation = views.observe(dict(request.model_input), algorithm, modality="multimodal-state")
            session.submit(session.reference_output(), observation["binding"])
        views.save()
        report = {
            "contract_id": e.config["contract_id"],
            "modality": "multimodal-state",
            "algorithm": algorithm,
            "arm": "exact_reference",
            "seed": 17,
            "output": str(output.relative_to(ROOT)),
            "events": session.events,
            "result": session.result(),
        }
        assert replay_visual_episode(ROOT, row, report, views) == session.result()
        wrong_modality = copy.deepcopy(report)
        wrong_modality["modality"] = "visual-state"
        with pytest.raises(ValueError, match="binding differs"):
            replay_visual_episode(ROOT, row, wrong_modality, views)
