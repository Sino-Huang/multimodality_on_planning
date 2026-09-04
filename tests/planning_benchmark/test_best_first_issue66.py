from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.best_first_development import (
    BestFirstModelSession,
    build_best_first_sft_command,
    load_best_first_issue65,
    load_best_first_issue66,
    replay_best_first_model_episode,
    run_reference_episode,
    select_best_first_coverage,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority

ROOT = Path(__file__).resolve().parents[2]


def test_issue66_contract_is_cell_matched_to_issue65() -> None:
    experiment = load_best_first_issue66(ROOT)
    issue65 = load_best_first_issue65(ROOT)

    assert experiment.contract_id == "issue-66-best-first-add-greedy-development-v1"
    assert [task.instance_id for task in experiment.tasks] == [task.instance_id for task in issue65.tasks]
    assert {task.algorithm for task in experiment.tasks} == {"best_first_add_greedy"}
    assert len(experiment.tasks) == 23
    assert sum(task.exact_decisions for task in experiment.tasks) == 6_696
    assert max(task.exact_decisions for task in experiment.tasks) == 923
    assert len(experiment.train_datasets) == 41
    assert len(experiment.dev_datasets) == 23
    assert experiment.preflight()["training_greedy_counts"] == {"dev": 6_696, "train": 8_342}


def test_issue66_exact_and_random_valid_episodes_replay_semantically() -> None:
    experiment = load_best_first_issue66(ROOT)
    task = min(experiment.tasks, key=lambda item: item.exact_decisions)

    for arm, seed in (("exact_reference", 17), ("random_valid", 29)):
        episode = run_reference_episode(task, arm=arm, seed=seed)

        assert replay_best_first_model_episode(episode, task=task) == episode["result"]
        assert episode["algorithm"] == "best_first_add_greedy"
        assert episode["result"]["invariant_valid_success"] is True


def test_issue66_deterministic_invalid_output_is_charged_once() -> None:
    experiment = load_best_first_issue66(ROOT)
    task = min(experiment.tasks, key=lambda item: item.exact_decisions)
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


def test_issue66_qualification_requires_the_complete_panel_to_fit() -> None:
    experiment = load_best_first_issue66(ROOT)

    passed = select_best_first_coverage(
        experiment.tasks,
        model_load_seconds=1.0,
        throughput_samples=(100.0,),
        runtime_seconds_per_call=0.0,
        rollout_shard_count=2,
        source_issue=66,
    )
    stopped = select_best_first_coverage(
        experiment.tasks,
        model_load_seconds=1.0,
        throughput_samples=(0.01,),
        runtime_seconds_per_call=0.0,
        rollout_shard_count=2,
        source_issue=66,
    )

    assert passed.outcome.value == "PASS"
    assert len(passed.task_ids) == 23
    assert passed.maximum_scheduled_calls == 26_784
    assert stopped.outcome.value == "VALID_STOP"
    assert stopped.task_ids == ()


def test_issue66_training_command_uses_one_seed_and_one_gpu_process(tmp_path: Path) -> None:
    experiment = load_best_first_issue66(ROOT)
    command = build_best_first_sft_command(
        experiment,
        dataset_root=tmp_path / "dataset",
        output_root=tmp_path / "checkpoints",
    )

    assert command.count("--seed") == 1
    assert command[command.index("--seed") + 1] == "17"
    assert command[command.index("--num_train_epochs") + 1] == "2"
    assert command[command.index("--save_steps") + 1] == "130"


def test_issue66_complete_dry_run_plans_progress_reporting_without_writes() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_best_first_issue66.py"), "all", "--dry-run"],
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
    assert result["plans"]["qualify"]["maximum_scheduled_calls"] == 26_784
    assert result["plans"]["train"]["estimated_optimizer_steps"] == 522
    assert result["plans"]["train"]["environment"]["MASTER_PORT"] == "29660"
    assert result["plans"]["evaluate"]["episodes"] == 230
    assert result["plans"]["references"]["workers"] == 8


def test_issue66_qualification_stop_adjudicates_without_downstream_runs(tmp_path: Path) -> None:
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
            str(ROOT / "scripts/run_best_first_issue66.py"),
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
    assert report["schema_version"] == "best_first_issue66_adjudication_v1"
    assert report["outcome"] == "VALID_STOP"
    assert report["scientific_completion"] is False
    assert receipt["receipt_id"] == "gate:issue-66-best-first-add-greedy-development-v1:attempt-001"
    assert receipt["start_permitted"] is False
