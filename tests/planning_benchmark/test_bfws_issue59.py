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
    assert command[command.index("--num_train_epochs") + 1] == "3"
    assert command[command.index("--max_length") + 1] == "8192"
    assert command[command.index("--lora_rank") + 1] == "64"
    assert command[command.index("--seed") + 1] == "17"


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
    )
    panel = select_bfws_coverage(
        experiment.tasks,
        model_load_seconds=0,
        throughput_samples=(5.0, 5.0),
        runtime_seconds_per_call=0,
    )
    stopped = select_bfws_coverage(
        experiment.tasks,
        model_load_seconds=0,
        throughput_samples=(0.1, 0.1),
        runtime_seconds_per_call=0,
    )

    assert full.coverage_mode == "full_development"
    assert len(full.task_ids) == 35
    assert panel.coverage_mode == "preregistered_exact_cost_panel"
    assert len(panel.task_ids) == 15
    assert panel.maximum_scheduled_calls == 27_228
    assert stopped.outcome.value == "VALID_STOP"
    assert stopped.task_ids == ()


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
