"""Bounded #75 tests: real CPU inputs/runtime, no model weights or long runs."""

import copy
import json
import tempfile
import time
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.modality_corpus_replay import canonical
from examples.planning_benchmark_slice.modality_view_preparation import frozen_processor, write_json
from examples.planning_benchmark_slice.pddl_state import GroundedAction, PDDLStateAuthority
from examples.planning_benchmark_slice.scene_assets import read_json
from examples.planning_benchmark_slice.visual_bfs import VisualBFSSession
from examples.planning_benchmark_slice.visual_episode import VisualSession, VisualTaskViews, replay_visual_episode
from examples.planning_benchmark_slice.visual_experiment import (
    ALGORITHMS,
    ROOT,
    VisualExperiment,
    cheapest_panel,
    select_coverage,
)
from examples.planning_benchmark_slice.visual_model import VisualCollator
from scripts.run_visual_issue75 import commands, main


def test_complete_workflow_dry_run_has_no_experiment_writes(capsys, tmp_path):
    output = tmp_path / "dry-run"
    experiment = VisualExperiment(output=output)
    arguments = ["--config", str(ROOT / "configs/experiments/issue75/experiment.json"), "--output", str(output)]
    assert not experiment.output.exists()
    assert main(["all", "--dry-run", *arguments]) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert report["writes"] == 0 and not report["model_calls_started"] and not report["scientific_completion"]
    assert report["training_runs"] == 4 and report["training_seed"] == 17
    assert report["selected_dev_task_groups"] == 42
    assert report["planned_condition_episodes"] == 16 * report["selected_dev_algorithm_episodes"]
    assert set(report["commands"]) == {"qualify", "references", "train", "evaluate", "adjudicate"}
    assert not experiment.output.exists()
    for stage in ("qualify", "references", "train", "evaluate", "adjudicate"):
        assert main([stage, "--dry-run", *arguments]) == 0


def test_launches_keep_concurrent_gpu_and_backend_ports_distinct():
    e = VisualExperiment()
    for stage in ("qualify", "references", "evaluate"):
        jobs = commands(e, stage, ROOT / "configs/experiments/issue75/experiment.json", False)
        assert len({j["environment"]["MASTER_PORT"] for j in jobs}) == len(jobs)
    jobs = commands(e, "train", ROOT / "configs/experiments/issue75/experiment.json", True)
    assert len(jobs) == 4
    assert [j["environment"]["CUDA_VISIBLE_DEVICES"] for j in jobs] == ["0", "1", "0", "1"]
    assert all("--resume" in j["command"] for j in jobs)


def test_corpus_scope_drift_fails_without_experiment_output(tmp_path):
    c = read_json(ROOT / "configs/experiments/issue75/experiment.json")
    c["training_seed"] = 29
    path = tmp_path / "bad.json"
    write_json(path, c)
    with pytest.raises(ValueError, match="scope differs"):
        VisualExperiment(path)


def test_research_settings_and_output_override_need_no_approval(tmp_path, capsys):
    config = read_json(ROOT / "configs/experiments/issue75/experiment.json")
    assert "authorization" not in config
    config["training"]["global_batch_size"] = 16
    config.pop("qualification_source", None)
    config.pop("cost_panel", None)
    path = tmp_path / "experiment.json"
    write_json(path, config)
    output = tmp_path / "new-run"
    assert main(["all", "--dry-run", "--config", str(path), "--output", str(output)]) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert report["approval_required"] is False and not output.exists()
    for stage in ("qualify", "train", "evaluate"):
        for launch in report["commands"][stage]:
            command = launch["command"]
            assert command[command.index("--output") + 1] == str(output)
    e = VisualExperiment(path, output)
    assert "permission" not in e.start()
    assert e.start(resume=True)["experiment"] == e.config


def test_clock_resume_preserves_start_and_finished_attempt_is_immutable(tmp_path, monkeypatch):
    e = VisualExperiment()
    e.config["budget_mode"] = "hard"
    e.output = tmp_path / "run"
    original = e.start()
    deadline = e.deadline()
    monkeypatch.setattr(time, "time", lambda: original["started_unix"] - 86400)
    assert e.deadline() == deadline
    e.require("qualify")
    assert e.start(resume=True) == original
    with pytest.raises(ValueError, match="--resume"):
        e.start()
    original["started_monotonic"] = time.monotonic() - e.config["gate_seconds"] - 1
    write_json(e.output / "attempt.json", original)
    with pytest.raises(RuntimeError, match="cutoff"):
        e.require("train")
    write_json(e.output / "result.json", {"outcome": "VALID_STOP"})
    with pytest.raises(ValueError, match="new directory"):
        e.start(resume=True)


def test_cost_selection_keeps_additive_pairs_and_stops_when_nothing_fits(tmp_path):
    e = VisualExperiment()
    e.cost_panel = None
    e.config["budget_mode"] = "hard"
    e.output = tmp_path / "run"
    e.start()
    rows = cheapest_panel(e.dev)
    assert len(rows) == 42
    assert all(set(r["reference_costs"]) == set(ALGORITHMS[2:]) for r in rows if r["task_id"].startswith("astar-pair-"))
    fast = [
        {"seconds_per_call": 0.001, "training_microstep_seconds": 0.001, "worker": i, "outcome": "PASS"}
        for i in range(2)
    ]
    assert select_coverage(e, fast)["selection"]["mode"] == "full"
    slow = [
        {"seconds_per_call": 1e6, "training_microstep_seconds": 1e6, "worker": i, "outcome": "PASS"} for i in range(2)
    ]
    stopped = select_coverage(e, slow)
    assert stopped["outcome"] == "VALID_STOP" and not stopped["model_outcomes_used_for_selection"]


def test_training_loader_activates_training_mode_for_hardware_probe(monkeypatch):
    from types import SimpleNamespace

    import peft
    import torch
    from transformers import Qwen3VLForConditionalGeneration

    from examples.planning_benchmark_slice.visual_model import load_training_model

    model = torch.nn.Sequential(torch.nn.Linear(2, 2), torch.nn.Dropout(0.5)).eval()
    monkeypatch.setattr(model, "config", SimpleNamespace(use_cache=True), raising=False)
    flags = {}
    monkeypatch.setattr(model, "to", lambda *args, **kwargs: model)
    monkeypatch.setattr(model, "gradient_checkpointing_enable", lambda **kw: flags.update(kw), raising=False)
    monkeypatch.setattr(model, "enable_input_require_grads", lambda: None, raising=False)
    monkeypatch.setattr(Qwen3VLForConditionalGeneration, "from_pretrained", lambda *args, **kwargs: model)
    monkeypatch.setattr(peft, "get_peft_model", lambda model, config: model)
    loaded = load_training_model(VisualExperiment().config)
    assert loaded.training and loaded[1].training
    assert not loaded.config.use_cache
    assert flags == {"gradient_checkpointing_kwargs": {"use_reentrant": False}}


DOMAIN = """(define (domain rooms) (:requirements :strips) (:predicates (at ?x) (link ?x ?y))
(:action move :parameters (?x ?y) :precondition (and (at ?x) (link ?x ?y))
:effect (and (not (at ?x)) (at ?y))))"""
PROBLEM = """(define (problem rooms-p) (:domain rooms) (:objects a b c d)
(:init (at a) (link a b) (link a c) (link b d) (link c d)) (:goal (at d)))"""


def test_bfs_accepts_noncanonical_tie_but_rejects_invalid_fifo_update():
    authority = PDDLStateAuthority.from_pddl(DOMAIN, PROBLEM)
    for wrong_position in (False, True):
        session = VisualBFSSession(authority, 20, 10)
        request = session.next_request()
        assert request is not None
        raw = request.model_input
        candidates = raw["search_memory"]["successor_candidates"]
        assert candidates[1]["grounded_action"]["args"] == ["a", "c"]
        operation = {
            "source_state_id": raw["observation"]["state_id"],
            "action": candidates[1]["grounded_action"],
            "frontier_intent": {"retire_source": True, "target_position": 1 if wrong_position else 0},
            "visit_target": True,
            "evaluate_target": False,
        }
        session.submit_output(
            canonical({"canonical_rationale": "tie", "runtime_result": None, "typed_operation": operation})
        )
        assert session.invalid_operation_count == int(wrong_position)
        if wrong_position:
            assert session.termination_reason == "deterministic_invalid_operation"
        else:
            assert "at(c)" in session.context.memory.state(session.context.memory.frontier[0]).atoms


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_bounded_real_visual_reference_replays_and_collator_masks_prompt(algorithm):
    e = VisualExperiment()
    row = min(
        (r for r in e.panel if algorithm in r["reference_costs"]),
        key=lambda r: r["reference_costs"][algorithm]["decisions"],
    )
    with tempfile.TemporaryDirectory(dir=ROOT / "outputs", prefix="test-visual75-") as temporary:
        output = Path(temporary)
        for arm in ("exact_reference", "random_valid"):
            views = VisualTaskViews(
                ROOT,
                row,
                e.corpus.results[row["task_id"]]["view_manifest"],
                output / "views",
                e.config["backend_endpoints"][0],
            )
            session = VisualSession(ROOT, row, algorithm, arm, 17, output, e.config["contract_id"], views=views)
            while (request := session.next_request()) is not None:
                observation = views.observe(dict(request.model_input), algorithm)
                assert observation["binding"]["input_pages"][0][0] == "task-context"
                session.submit(session.reference_output(), observation["binding"])
            views.save()
            report = {
                "contract_id": e.config["contract_id"],
                "algorithm": algorithm,
                "arm": arm,
                "seed": 17,
                "output": str(output.relative_to(ROOT)),
                "events": session.events,
                "result": session.result(),
            }
            assert report["result"]["invalid_operation_count"] == 0
            assert replay_visual_episode(ROOT, row, report, views) == session.result()
            broken = copy.deepcopy(report)
            broken["events"][0]["view"]["state"] = -1
            with pytest.raises(ValueError, match="binding differs"):
                replay_visual_episode(ROOT, row, broken, views)
        record = next(e.corpus.records(algorithm=algorithm, split="train"))
        example = e.corpus.training_example(record)
        encoded = VisualCollator(frozen_processor().processor)([example])
        labels = encoded["labels"][0]
        prefix = frozen_processor().count(example["messages"][:-1])
        assert (labels[:prefix] == -100).all()
        assert (labels[prefix:] != -100).any()
        decoded = frozen_processor().processor.tokenizer.decode(labels[labels != -100])
        assert canonical(record["target"]) in decoded


def test_probe_batches_cover_mixed_lengths_at_the_actual_batch_ceiling():
    from examples.planning_benchmark_slice.visual_jobs import probe_records

    config = {"max_batch_size": 8, "max_batch_input_tokens": 48000}
    big = {"algorithm": "bfs", "tokens": {"input": {"visual-state": 16000}}}
    small = {"algorithm": "bfs", "tokens": {"input": {"visual-state": 3000}}}
    assert probe_records(config, [big, small], big, "visual-state") == [big, small, big]
    assert len(probe_records(config, [big, small], small, "visual-state")) == 8


def test_new_accepted_state_uses_supplied_local_path_and_replay_never_renders(monkeypatch):
    from PIL import Image

    from examples.planning_benchmark_slice.planimation_render import PlanimationRenderResult

    e = VisualExperiment()
    row = next(r for r in e.panel if r["task_id"] == "bfs/15puzzle-dev-easy-0000")
    calls = []

    def render(request):
        calls.append(request)
        assert request.base_url.startswith("http://127.0.0.1:")
        assert request.supplied_plan and request.canvas_size == 128
        request.output_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for i in range(len(request.supplied_plan) + 1):
            frame = request.output_dir / f"{i}.png"
            Image.new("RGB", (128, 128), "white").save(frame)
            frames.append(frame)
        vfg = request.output_dir / "trace.json"
        write_json(
            vfg,
            {
                "visualStages": [
                    {"stageName": name, "visualSprites": []} for name in ("Initial Stage", *request.supplied_plan)
                ]
            },
        )
        return PlanimationRenderResult(request.base_url + "/upload/pddl", vfg, tuple(frames))

    monkeypatch.setattr("examples.planning_benchmark_slice.visual_episode.produce_planimation_render", render)
    with tempfile.TemporaryDirectory(dir=ROOT / "outputs", prefix="test-new-visual75-") as temporary:
        views = VisualTaskViews(
            ROOT,
            row,
            e.corpus.results[row["task_id"]]["view_manifest"],
            Path(temporary),
            e.config["backend_endpoints"][0],
        )
        found = None
        for entry in views.states:
            source = views.authority.initial_state
            for action_text in views.path(entry["index"]):
                parts = action_text[1:-1].split()
                source = views.authority.apply(source, GroundedAction(parts[0], tuple(parts[1:]))).target_state
            for action in views.authority.applicable_actions(source):
                target = views.authority.preview_apply(source, action).target_state
                if views.key(target.atoms, target.fluents) not in views.indices:
                    found = (source, action)
                    break
            if found:
                break
        assert found is not None
        source, action = found
        operation = {"name": action.name, "args": list(action.args)}
        assert calls == []
        state_index = views.register(source, operation)
        assert len(calls) == 1 and views.states[state_index]["scene_path"]
        assert views.states[state_index]["supplied_actions"][-1] == f"({action.name} {' '.join(action.args)})"
        views.save()
        reader = VisualTaskViews(
            ROOT,
            row,
            e.corpus.results[row["task_id"]]["view_manifest"],
            Path(temporary),
            e.config["backend_endpoints"][0],
            read_only=True,
        )
        replayed_source = reader.authority.initial_state
        source_index = reader.indices[reader.key(source.atoms, source.fluents)]
        for action_text in reader.path(source_index):
            parts = action_text[1:-1].split()
            replayed_source = reader.authority.apply(
                replayed_source, GroundedAction(parts[0], tuple(parts[1:]))
            ).target_state
        assert reader.register(replayed_source, operation) == state_index and len(calls) == 1


def test_missing_predecessor_writes_a_stop_not_a_success(tmp_path, monkeypatch, capsys):
    from scripts import run_visual_issue75

    e = VisualExperiment()
    e.output = tmp_path / "attempt"
    e.start()
    monkeypatch.setattr(run_visual_issue75, "VisualExperiment", lambda *_: e)
    assert main(["train", "--resume"]) == 1
    result = read_json(e.output / "result.json")
    assert result["outcome"] == "VALID_STOP" and not result["scientific_completion"]
    assert "receipt" not in result
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["outcome"] == "VALID_STOP"


def test_reference_worker_preserves_last_completed_episode_at_cutoff():
    from examples.planning_benchmark_slice.visual_jobs import run_jobs

    e = VisualExperiment()
    row = min(
        (r for r in e.dev if "bfs" in r["reference_costs"]), key=lambda r: r["reference_costs"]["bfs"]["decisions"]
    )
    with tempfile.TemporaryDirectory(dir=ROOT / "outputs", prefix="test-worker75-") as temporary:
        e.output = Path(temporary)
        e.config = copy.deepcopy(e.config)
        e.config["evaluation_seeds"] = [17]
        e.config["budget_mode"] = "hard"
        write_json(e.output / "attempt.json", {"started_monotonic": time.monotonic()})
        write_json(e.output / "qualification.json", {"selection": {"task_ids": [row["task_id"]]}})
        progress = []

        def completed(stage, **fields):
            progress.append((stage, fields))
            if stage == "references" and fields["completed"] == fields["total"]:
                write_json(
                    e.output / "attempt.json", {"started_monotonic": time.monotonic() - e.config["gate_seconds"] - 1}
                )

        result = run_jobs(e, 0, True, completed)
        assert result["outcome"] == "PASS"
        assert len(result["episodes"]) == 2
        assert all((ROOT / r["path"]).is_file() for r in result["episodes"])
        assert progress[-1][1]["completed"] == 2


def test_duplicate_start_does_not_overwrite_an_existing_attempt(tmp_path, monkeypatch, capsys):
    from scripts import run_visual_issue75

    e = VisualExperiment()
    e.output = tmp_path / "attempt"
    e.start()
    original = read_json(e.output / "attempt.json")
    monkeypatch.setattr(run_visual_issue75, "VisualExperiment", lambda *_: e)
    assert main(["all"]) == 1
    assert read_json(e.output / "attempt.json") == original
    assert not (e.output / "result.json").exists()
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["outcome"] == "INVALID"


def test_failed_worker_stops_sibling_and_queued_work(tmp_path):
    import sys

    from scripts.run_visual_issue75 import run_children

    e = VisualExperiment()
    e.output = tmp_path / "attempt"
    e.start()
    write_json(e.output / "qualification/0.json", {"outcome": "VALID_STOP", "reason": "resource limit"})
    marker = tmp_path / "must-not-run"
    jobs = [
        {
            "worker": 0,
            "command": [sys.executable, "-c", "import time;time.sleep(0.2);raise SystemExit(1)"],
            "environment": {},
        },
        {"worker": 1, "command": [sys.executable, "-c", "import time;time.sleep(60)"], "environment": {}},
        {
            "worker": 1,
            "command": [sys.executable, "-c", f"from pathlib import Path;Path({str(marker)!r}).touch()"],
            "environment": {},
        },
    ]
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="VALID_STOP: resource limit"):
        run_children(e, "qualify", jobs)
    assert time.monotonic() - started < 10
    assert not marker.exists()


def test_bfws_live_probe_preserves_explicit_empty_novelty_partitions():
    from examples.planning_benchmark_slice.modality_corpus import iter_shard
    from examples.planning_benchmark_slice.visual_jobs import semantic_output

    e = VisualExperiment()
    result = e.corpus.results["best_first_width/gripper-train-easy-0050"]
    record = next(r for r in iter_shard(ROOT / result["path"]) if r["decision_index"] == 236)
    assert semantic_output(e, record, canonical(record["target"]))["accepted"]
