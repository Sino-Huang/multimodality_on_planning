from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.best_first_development import (
    BestFirstModelSession,
    build_best_first_sft_command,
    load_best_first_issue65,
    replay_best_first_model_episode,
    run_reference_episode,
    select_issue65_coverage,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority

ROOT = Path(__file__).resolve().parents[2]


def test_issue65_contract_selects_only_the_w3_development_product() -> None:
    experiment = load_best_first_issue65(ROOT)

    assert experiment.contract_id == "issue-65-best-first-add-w3-development-v1"
    assert len(experiment.tasks) == 23
    assert sum(task.exact_decisions for task in experiment.tasks) == 7_095
    assert max(task.exact_decisions for task in experiment.tasks) == 918
    assert len(experiment.train_datasets) == 41
    assert len(experiment.dev_datasets) == 23
    assert experiment.preflight()["training_w3_counts"] == {"dev": 7_095, "train": 9_398}


def test_issue65_exact_and_random_valid_episodes_replay_semantically() -> None:
    experiment = load_best_first_issue65(ROOT)
    task = next(item for item in experiment.tasks if item.exact_decisions == 8)

    for arm, seed in (("exact_reference", 17), ("random_valid", 29)):
        episode = run_reference_episode(task, arm=arm, seed=seed)

        assert replay_best_first_model_episode(episode, task=task) == episode["result"]
        assert episode["result"]["invariant_valid_success"] is True
        assert episode["result"]["decision_count"] == task.exact_decisions
        assert episode["result"]["expansion_count"] == task.exact_expansions


def test_issue65_deterministic_invalid_output_is_charged_once() -> None:
    experiment = load_best_first_issue65(ROOT)
    task = next(item for item in experiment.tasks if item.exact_decisions == 8)
    task_payload = json.loads(task.task_path.read_text(encoding="utf-8"))
    session = BestFirstModelSession(
        authority=PDDLStateAuthority.from_pddl(task_payload["domain_pddl"], task_payload["problem_pddl"]),
        task=task,
        arm="pretrained_base",
        seed=17,
    )

    assert session.next_request() is not None
    session.submit_output("{}")

    assert session.next_request() is None
    assert session.result()["termination_reason"] == "deterministic_invalid_operation"
    assert session.result()["decision_count"] == 1
    assert session.result()["invalid_operation_count"] == 1


def test_issue65_qualification_requires_the_complete_panel_to_fit() -> None:
    experiment = load_best_first_issue65(ROOT)

    passed = select_issue65_coverage(
        experiment.tasks,
        model_load_seconds=1.0,
        throughput_samples=(100.0,),
        runtime_seconds_per_call=0.0,
        rollout_shard_count=2,
    )
    stopped = select_issue65_coverage(
        experiment.tasks,
        model_load_seconds=1.0,
        throughput_samples=(0.01,),
        runtime_seconds_per_call=0.0,
        rollout_shard_count=2,
    )

    assert passed.outcome.value == "PASS"
    assert len(passed.task_ids) == 23
    assert passed.maximum_scheduled_calls == 28_380
    assert passed.maximum_shard_scheduled_calls == 14_196
    assert stopped.outcome.value == "VALID_STOP"
    assert stopped.task_ids == ()


def test_issue65_training_command_is_one_seed_and_one_gpu_process(tmp_path: Path) -> None:
    experiment = load_best_first_issue65(ROOT)
    command = build_best_first_sft_command(
        experiment,
        dataset_root=tmp_path / "dataset",
        output_root=tmp_path / "checkpoints",
    )

    assert command.count("--seed") == 1
    assert command[command.index("--seed") + 1] == "17"
    assert command[command.index("--num_train_epochs") + 1] == "2"
    assert command[command.index("--save_steps") + 1] == "147"
    assert "best_first_add_greedy" not in " ".join(command)


def test_issue65_training_resume_selects_the_latest_complete_checkpoint(tmp_path: Path) -> None:
    from scripts import run_best_first_issue65 as command

    incomplete = tmp_path / "attempt-001" / "checkpoints" / "checkpoint-294"
    complete = tmp_path / "attempt-002" / "checkpoints" / "checkpoint-147"
    newer = tmp_path / "attempt-002" / "checkpoints" / "checkpoint-441"
    incomplete.mkdir(parents=True)
    complete.mkdir(parents=True)
    newer.mkdir(parents=True)
    (complete / "trainer_state.json").write_text("{}", encoding="utf-8")
    (newer / "trainer_state.json").write_text("{}", encoding="utf-8")

    assert command._next_training_attempt(tmp_path) == 3
    assert command._latest_checkpoint(tmp_path) == newer


def test_issue65_complete_dry_run_plans_progress_reporting_without_writes() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_best_first_issue65.py"), "all", "--dry-run"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.splitlines()[-1])
    assert result["dry_run"] is True
    assert result["writes"] == 0
    assert result["plans"]["qualify"]["maximum_scheduled_calls"] == 28_380
    assert result["plans"]["train"]["estimated_optimizer_steps"] == 588
    assert result["plans"]["evaluate"]["episodes"] == 230
    assert result["plans"]["references"]["workers"] == 8


def test_issue65_qualification_stop_adjudicates_without_downstream_runs(tmp_path: Path) -> None:
    qualification = tmp_path / "qualification" / "qualification.json"
    qualification.parent.mkdir(parents=True)
    qualification.write_text(
        json.dumps(
            {
                "coverage": {
                    "mode": None,
                    "outcome": "VALID_STOP",
                    "projected_rollout_seconds": 60_000,
                    "task_ids": [],
                }
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_best_first_issue65.py"),
            "adjudicate",
            "--output-root",
            str(tmp_path),
        ],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads((tmp_path / "adjudication" / "report.json").read_text(encoding="utf-8"))
    receipt = json.loads((tmp_path / "adjudication" / "gate-receipt.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "VALID_STOP"
    assert report["scientific_completion"] is False
    assert receipt["start_permitted"] is False
