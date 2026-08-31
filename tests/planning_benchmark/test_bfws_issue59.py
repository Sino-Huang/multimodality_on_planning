from __future__ import annotations

import json
import random
from copy import deepcopy
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.bfws_issue59 import (
    BFWSModelSession,
    adjudicate_bfws_structural_gate,
    bfws_episode_payload,
    bfws_text_policy_messages,
    build_bfws_sft_command,
    exact_bfws_model_output,
    load_bfws_issue59,
    materialize_random_valid_bfws_reference,
    random_valid_bfws_model_output,
    replay_bfws_episode,
    select_bfws_coverage,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from scripts import run_bfws_issue59 as issue59_runner
from scripts.run_bfws_issue59 import main as issue59_main

REPO_ROOT = Path(__file__).resolve().parents[2]
TASK = REPO_ROOT / "tests" / "fixtures" / "planning" / "iw_width_four.json"


def test_issue59_preflight_binds_released_process_corpus_and_dev_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text

    def reject_fresh_bytes(path: Path) -> bytes:
        if path.name == "fresh-test-manifest.jsonl":
            raise AssertionError("issue #59 preflight accessed the fresh held-out test manifest")
        return original_read_bytes(path)

    def reject_fresh_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path.name == "fresh-test-manifest.jsonl":
            raise AssertionError("issue #59 preflight accessed the fresh held-out test manifest")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_bytes", reject_fresh_bytes)
    monkeypatch.setattr(Path, "read_text", reject_fresh_text)

    experiment = load_bfws_issue59(REPO_ROOT)
    report = experiment.preflight()

    assert report["phase_id"] == "issue-56-bfws-development-v1"
    assert report["training_examples"] == {"dev": 21_239, "train": 47_780}
    assert report["training_task_files"] == {"dev": 35, "train": 70}
    assert report["development_tasks"] == 35
    assert report["development_exact_decisions"] == 21_239
    assert report["maximum_model_calls"] == 42_478
    assert report["fresh_test_accessed"] is False
    assert report["contract_id"] == "issue-59-bfws-single-training-v2"
    assert report["training_runs"] == 1
    assert report["training_seeds"] == [17]
    assert report["training_epochs"] == 2


def test_bfws_generation_messages_preserve_the_training_text() -> None:
    model_input = {"observation": {"algorithm": "best_first_width"}}
    messages = bfws_text_policy_messages(model_input)

    assert [message["role"] for message in messages] == ["system", "user"]
    assert all(message["content"][0]["type"] == "text" for message in messages)
    assert json.loads(messages[1]["content"][0]["text"]) == model_input


def test_issue59_sft_command_uses_every_atomic_training_shard_and_frozen_optimizer(tmp_path: Path) -> None:
    experiment = load_bfws_issue59(REPO_ROOT)

    command = build_bfws_sft_command(
        experiment,
        seed=17,
        output_root=tmp_path / "seed-17",
        world_size=1,
        smoke=False,
    )

    dataset_index = command.index("--dataset")
    validation_index = command.index("--val_dataset")
    train_paths = command[dataset_index + 1 : validation_index]
    dev_paths = command[validation_index + 1 : command.index("--split_dataset_ratio")]
    assert len(train_paths) == 70
    assert len(dev_paths) == 35
    assert command[command.index("--num_train_epochs") + 1] == "2"
    assert command[command.index("--max_length") + 1] == "8192"
    assert command[command.index("--lora_rank") + 1] == "64"
    assert command[command.index("--seed") + 1] == "17"
    assert command[command.index("--save_strategy") + 1] == "steps"
    assert command[command.index("--save_steps") + 1] == "747"


def test_bfws_model_session_executes_exact_outputs_through_the_live_contract() -> None:
    payload = json.loads(TASK.read_bytes())
    authority = PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])
    session = BFWSModelSession(
        authority=authority,
        instance_id=payload["instance_id"],
        arm="exact_bfws",
        seed=17,
        max_model_calls=128,
        accepted_delta_limit=16,
        max_input_bytes=1_000_000,
        max_input_tokens=7_808,
        input_token_counter=lambda _value: 1,
    )

    while (request := session.next_request()) is not None:
        session.submit_output(exact_bfws_model_output(request.observation))
    result = session.result()

    assert result["goal_reached"] is True
    assert result["invariant_valid_success"] is True
    assert result["invalid_operation_count"] == 0
    assert result["decision_count"] == len(session.events)
    assert all(event["input"]["search_memory"]["schema_version"] == 1 for event in session.events)

    payload = bfws_episode_payload(session)
    assert replay_bfws_episode(payload, authority=authority, input_token_counter=lambda _value: 1) == result
    tampered = deepcopy(payload)
    tampered["events"][0]["input"]["search_memory"]["open"] += 1
    with pytest.raises(ValueError, match="model input differs"):
        replay_bfws_episode(tampered, authority=authority, input_token_counter=lambda _value: 1)


def test_issue59_adjudication_uses_best_control_and_emits_governed_stop() -> None:
    seeds = (17, 29)
    task_ids = {"a", "b"}

    def rows(arm: str, successes: dict[tuple[str, int], bool], *, invalid: int = 0):
        return [
            {
                "arm": arm,
                "instance_id": task,
                "seed": seed,
                "result": {
                    "decision_count": 10,
                    "invalid_operation_count": invalid,
                    "invariant_valid_success": successes[(task, seed)],
                },
            }
            for task in sorted(task_ids)
            for seed in seeds
        ]

    all_success = {(task, seed): True for task in task_ids for seed in seeds}
    half_success = {
        ("a", 17): True,
        ("a", 29): True,
        ("b", 17): False,
        ("b", 29): False,
    }
    report = adjudicate_bfws_structural_gate(
        expected_ids=task_ids,
        seeds=seeds,
        exact_rows=[
            {"arm": "exact_bfws", "instance_id": task, "seed": None, "result": {"invariant_valid_success": True}}
            for task in sorted(task_ids)
        ],
        random_rows=rows("random_valid", half_success),
        base_rows=rows("pretrained_base", half_success),
        process_rows=rows("process_sft", all_success),
        thresholds={
            "exact_reference_invariant_valid_success": 1.0,
            "maximum_invalid_operation_rate": 0.05,
            "process_sft_absolute_gain_over_best_control": 0.1,
            "process_sft_gain_bootstrap_lower_bound": 0.0,
            "process_sft_invariant_valid_success": 0.8,
        },
        bootstrap_resamples=1_000,
        bootstrap_seed=1729,
    )
    assert report["outcome"] == "PASS"
    assert report["best_control"] == "pretrained_base"
    assert report["absolute_gain_over_best_control"] == 0.5

    stopped = adjudicate_bfws_structural_gate(
        expected_ids=task_ids,
        seeds=seeds,
        exact_rows=[
            {"arm": "exact_bfws", "instance_id": task, "seed": None, "result": {"invariant_valid_success": True}}
            for task in sorted(task_ids)
        ],
        random_rows=rows("random_valid", all_success),
        base_rows=rows("pretrained_base", half_success),
        process_rows=rows("process_sft", all_success),
        thresholds={
            "exact_reference_invariant_valid_success": 1.0,
            "maximum_invalid_operation_rate": 0.05,
            "process_sft_absolute_gain_over_best_control": 0.1,
            "process_sft_gain_bootstrap_lower_bound": 0.0,
            "process_sft_invariant_valid_success": 0.8,
        },
        bootstrap_resamples=1_000,
        bootstrap_seed=1729,
    )
    assert stopped["outcome"] == "VALID_STOP"
    assert stopped["scientific_completion"] is False


def test_random_valid_bfws_reference_never_submits_an_invalid_operation() -> None:
    payload = json.loads(TASK.read_bytes())
    for seed in (17, 29, 43, 71, 101):
        authority = PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])
        session = BFWSModelSession(
            authority=authority,
            instance_id=payload["instance_id"],
            arm="random_valid",
            seed=seed,
            max_model_calls=128,
            max_expansions=64,
            accepted_delta_limit=16,
            max_input_bytes=1_000_000,
            max_input_tokens=7_808,
            input_token_counter=lambda _value: 1,
        )
        generator = random.Random(seed)
        while (request := session.next_request()) is not None:
            session.submit_output(random_valid_bfws_model_output(request.observation, generator))

        assert session.result()["invalid_operation_count"] == 0


def test_hardware_qualification_tries_full_then_preregistered_exact_cost_panel() -> None:
    experiment = load_bfws_issue59(REPO_ROOT)

    full = select_bfws_coverage(
        experiment.tasks,
        model_load_seconds=0,
        throughput_samples=(10.0, 10.0),
        runtime_seconds_per_call=0,
        model_sessions_per_task=2,
    )
    panel = select_bfws_coverage(
        experiment.tasks,
        model_load_seconds=0,
        throughput_samples=(1.5, 1.5),
        runtime_seconds_per_call=0,
        model_sessions_per_task=2,
    )
    stopped = select_bfws_coverage(
        experiment.tasks,
        model_load_seconds=0,
        throughput_samples=(0.03, 0.03),
        runtime_seconds_per_call=0,
        model_sessions_per_task=2,
    )
    distributed = select_bfws_coverage(
        experiment.tasks,
        model_load_seconds=68,
        throughput_samples=(0.180490565,) * 8,
        runtime_seconds_per_call=0.000078,
        model_sessions_per_task=2,
        rollout_shard_count=4,
    )

    assert full.coverage_mode == "full_development"
    assert len(full.task_ids) == 35
    assert panel.coverage_mode == "preregistered_exact_cost_panel"
    assert len(panel.task_ids) == 15
    assert panel.maximum_scheduled_calls == 9_076
    assert stopped.outcome.value == "VALID_STOP"
    assert stopped.task_ids == ()
    assert distributed.coverage_mode == "preregistered_exact_cost_panel"
    assert distributed.rollout_shard_count == 4
    assert distributed.maximum_scheduled_calls == 9_076
    assert distributed.projected_rollout_seconds < 15 * 60 * 60


def test_live_issue59_session_matches_a_released_exact_dev_trace() -> None:
    experiment = load_bfws_issue59(REPO_ROOT)
    task = next(item for item in experiment.tasks if item.instance_id == "storage-train-easy-0004")
    authority = PDDLStateAuthority.from_pddl(
        task.domain_path.read_text(encoding="utf-8"),
        task.problem_path.read_text(encoding="utf-8"),
    )
    session = BFWSModelSession(
        authority=authority,
        instance_id=task.instance_id,
        arm="exact_bfws",
        seed=17,
        max_model_calls=task.model_call_limit,
        max_expansions=task.exact_expansions,
        accepted_delta_limit=16,
        max_input_bytes=10_000_000,
        max_input_tokens=7_808,
        input_token_counter=lambda _value: 1,
    )
    while (request := session.next_request()) is not None:
        session.submit_output(exact_bfws_model_output(request.observation))

    result = session.result()
    assert result["invariant_valid_success"] is True
    assert result["decision_count"] == task.exact_decisions == 3
    assert result["expansion_count"] == task.exact_expansions == 3


def test_random_reference_resume_replays_existing_evidence_without_regeneration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experiment = load_bfws_issue59(REPO_ROOT)
    task = next(item for item in experiment.tasks if item.instance_id == "storage-train-easy-0004")
    evidence_path = tmp_path / "episode.json.gz"

    generated, generated_status = materialize_random_valid_bfws_reference(
        task=task,
        seed=17,
        evidence_path=evidence_path,
        input_token_counter=lambda _value: 1,
    )
    retained_bytes = evidence_path.read_bytes()

    def reject_regeneration(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("resume regenerated an existing random-valid episode")

    monkeypatch.setattr(
        "examples.planning_benchmark_slice.bfws_issue59.random_valid_bfws_model_output",
        reject_regeneration,
    )
    resumed, resumed_status = materialize_random_valid_bfws_reference(
        task=task,
        seed=17,
        evidence_path=evidence_path,
        input_token_counter=lambda _value: 1,
    )

    assert generated_status == "generated"
    assert resumed_status == "reused"
    assert resumed == generated
    assert evidence_path.read_bytes() == retained_bytes


def test_reference_dry_run_exposes_bounded_parallel_worker_count(capsys: pytest.CaptureFixture[str]) -> None:
    assert issue59_main(["references", "--dry-run", "--reference-workers", "4"]) == 0

    plan = json.loads(capsys.readouterr().out)
    assert plan["workers"] == 4
    assert plan["resume"] is False


def test_parallel_training_dry_run_assigns_distinct_rendezvous_ports(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        issue59_main(
            [
                "train",
                "--dry-run",
                "--devices",
                "cuda:0",
                "cuda:1",
                "--output-root",
                str(tmp_path / "issue59"),
            ]
        )
        == 0
    )

    launches = json.loads(capsys.readouterr().out)["launches"]
    assert len(launches) == 1
    assert launches[0]["seed"] == 17
    assert launches[0]["device"] == "cuda:1"
    assert launches[0]["environment"]["CUDA_VISIBLE_DEVICES"] == "1"
    assert launches[0]["environment"]["MASTER_PORT"] == "29600"


def test_resumed_all_dry_run_qualifies_the_new_training_attempt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_root = tmp_path / "issue59"
    (output_root / "training" / "seed-17-attempt-001").mkdir(parents=True)
    (output_root / "training" / "seed-17-attempt-002").mkdir()

    assert (
        issue59_main(
            [
                "all",
                "--dry-run",
                "--resume",
                "--devices",
                "cuda:0",
                "cuda:1",
                "--output-root",
                str(output_root),
            ]
        )
        == 0
    )

    stages = json.loads(capsys.readouterr().out)["stages"]
    training_root = Path(stages["train"][0]["output_root"])
    assert training_root.name == "seed-17-attempt-003"
    assert stages["qualify"]["adapter_paths"]["17"] == str(training_root / "checkpoints" / "checkpoint-2988")


def test_resumed_training_uses_the_newest_complete_checkpoint(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_root = tmp_path / "issue59"
    first = output_root / "training" / "seed-17-attempt-001" / "checkpoints" / "checkpoint-747"
    second = output_root / "training" / "seed-17-attempt-002" / "checkpoints" / "checkpoint-1494"
    incomplete = output_root / "training" / "seed-17-attempt-002" / "checkpoints" / "checkpoint-2241"
    for checkpoint, step in ((first, 747), (second, 1494)):
        checkpoint.mkdir(parents=True)
        (checkpoint / "trainer_state.json").write_text(json.dumps({"global_step": step}))
        for name in (
            "adapter_config.json",
            "adapter_model.safetensors",
            "optimizer.pt",
            "rng_state.pth",
            "scheduler.pt",
        ):
            (checkpoint / name).write_bytes(b"checkpoint")
    incomplete.mkdir()
    (incomplete / "trainer_state.json").write_text("{")
    for name in (
        "adapter_config.json",
        "adapter_model.safetensors",
        "optimizer.pt",
        "rng_state.pth",
        "scheduler.pt",
    ):
        (incomplete / name).write_bytes(b"partial-checkpoint")

    assert (
        issue59_main(
            [
                "train",
                "--dry-run",
                "--resume",
                "--devices",
                "cuda:0",
                "cuda:1",
                "--output-root",
                str(output_root),
            ]
        )
        == 0
    )

    launch = json.loads(capsys.readouterr().out)["launches"][0]
    assert Path(launch["output_root"]).name == "seed-17-attempt-003"
    assert launch["resume_from_checkpoint"] == str(second.resolve())
    command = launch["command"]
    assert command[command.index("--resume_from_checkpoint") + 1] == str(second.resolve())


def test_distributed_dry_run_uses_distinct_node_and_global_shard_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_root = tmp_path / "issue59"

    node_plans = []
    for node_index in (0, 1):
        assert (
            issue59_main(
                [
                    "qualify-node",
                    "--dry-run",
                    "--run-id",
                    "four-gpu-v1",
                    "--node-index",
                    str(node_index),
                    "--devices",
                    "cuda:0",
                    "cuda:1",
                    "--output-root",
                    str(output_root),
                ]
            )
            == 0
        )
        node_plans.append(json.loads(capsys.readouterr().out))

    assert node_plans[0]["rollout_shard_indices"] == [0, 1]
    assert node_plans[1]["rollout_shard_indices"] == [2, 3]
    assert node_plans[0]["output"] != node_plans[1]["output"]
    assert node_plans[0]["output"].endswith("qualification/nodes/node-0/report.json")
    assert node_plans[1]["output"].endswith("qualification/nodes/node-1/report.json")

    assert (
        issue59_main(
            [
                "evaluate-node",
                "--dry-run",
                "--run-id",
                "four-gpu-v1",
                "--node-index",
                "1",
                "--devices",
                "cuda:0",
                "cuda:1",
                "--output-root",
                str(output_root),
            ]
        )
        == 0
    )
    commands = json.loads(capsys.readouterr().out)["commands"]
    assert [command[command.index("--shard-index") + 1] for command in commands] == ["2", "3"]
    assert all(command[command.index("--run-id") + 1] == "four-gpu-v1" for command in commands)


def test_distributed_merge_and_adjudication_plan_cover_all_four_shards(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_root = tmp_path / "issue59"
    common = ["--dry-run", "--run-id", "four-gpu-v1", "--output-root", str(output_root)]

    assert issue59_main(["qualify-merge", *common]) == 0
    merge = json.loads(capsys.readouterr().out)
    assert len(merge["inputs"]) == 2
    assert merge["rollout_shard_count"] == 4
    assert merge["output"].endswith("runs/four-gpu-v1/qualification.json")

    assert issue59_main(["adjudicate", *common]) == 0
    adjudication = json.loads(capsys.readouterr().out)
    rollout_inputs = [path for path in adjudication["inputs"] if "/rollout/shard-" in path]
    assert len(rollout_inputs) == 4
    assert rollout_inputs[-1].endswith("rollout/shard-3/manifest.json")


def test_distributed_qualification_merges_both_node_measurements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "issue59"
    experiment = load_bfws_issue59(REPO_ROOT)
    nodes_root = output_root / "runs" / "four-gpu-v1" / "qualification" / "nodes"
    for node_index in (0, 1):
        node_root = nodes_root / f"node-{node_index}"
        node_root.mkdir(parents=True)
        (node_root / "report.json").write_text(
            json.dumps(
                {
                    "contract_id": experiment.distributed_contract_id,
                    "model_load_samples": [67.0 + node_index, 68.0 + node_index],
                    "node_count": 2,
                    "node_index": node_index,
                    "outcomes_observed": False,
                    "phase_id": experiment.phase_gate.phase_id,
                    "runtime_samples": [0.000078, 0.000077],
                    "schema_version": "bfws_issue59_hardware_qualification_node_v1",
                    "throughput_samples": [0.180490565] * 4,
                }
            )
        )
    monkeypatch.setattr(issue59_runner, "_require_reference_gate", lambda *_args: None)

    assert (
        issue59_main(
            [
                "qualify-merge",
                "--run-id",
                "four-gpu-v1",
                "--output-root",
                str(output_root),
            ]
        )
        == 0
    )

    qualification = json.loads(
        (output_root / "runs" / "four-gpu-v1" / "qualification.json").read_text()
    )
    assert qualification["coverage"]["outcome"] == "PASS"
    assert qualification["coverage"]["mode"] == "preregistered_exact_cost_panel"
    assert qualification["coverage"]["rollout_shard_count"] == 4
    assert qualification["coverage"]["maximum_scheduled_calls"] == 9_076
    assert qualification["outcomes_observed"] is False
