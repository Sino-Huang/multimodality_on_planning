from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.phase3 import extend_curriculum_workflow
from scripts.phase3.extend_curriculum_workflow import WorkflowConfig, build_parser, inspect_shards, run_workflow, update_final_root


def test_inspect_shards_counts_hashes_and_staging(tmp_path: Path) -> None:
    shard = tmp_path / "shards" / "blocksworld"
    instance = shard / "blocksworld" / "train" / "easy" / "blocksworld-train-easy-0000"
    instance.mkdir(parents=True)
    (shard / ".staging" / "x").mkdir(parents=True)
    accepted = {
        "instance_id": "blocksworld-train-easy-0000",
        "split": "train",
        "bucket": "easy",
        "difficulty_target": "easy",
        "normalized_problem_hash": "hash-a",
    }
    rejection = {"split": "train", "bucket": "easy"}
    _write_jsonl(shard / "accepted_manifest.jsonl", [accepted])
    _write_jsonl(shard / "rejections.jsonl", [rejection])

    state = inspect_shards(tmp_path / "shards")

    assert state.accepted_total == 1
    assert state.duplicate_hashes == 0
    assert state.missing_hashes == 0
    assert state.staging_entries == 2
    assert state.counts_by_domain_split_bucket[("blocksworld", "train", "easy")] == 1
    assert state.attempts_by_domain_split_bucket[("blocksworld", "train", "easy")] == 2


def test_parser_rejects_non_positive_candidate_multiplier() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--candidate-multiplier", "0"])


def test_parser_keeps_final_root_update_disabled_by_default() -> None:
    args = build_parser().parse_args([])

    assert args.final_root == Path("data/curriculum_pddl")
    assert args.update_root is False
    assert args.target_total == 7995
    assert args.plan_limit is None


def test_update_final_root_requires_matching_clean_merge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, check, text, capture_output, cwd):
        del check, text, capture_output, cwd
        calls.append(list(command))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"summary": {"accepted_total": 12, "duplicate_accepted_problem_hashes": 0}}),
            stderr="",
        )

    monkeypatch.setattr(extend_curriculum_workflow.subprocess, "run", fake_run)

    summary = update_final_root(
        shards_root=tmp_path / "shards",
        final_root=tmp_path / "curriculum_pddl",
        safety_summary={"accepted_total": 12, "duplicate_accepted_problem_hashes": 0},
    )

    assert summary["accepted_total"] == 12
    assert "--output" in calls[0]
    assert str(tmp_path / "curriculum_pddl") in calls[0]


def test_verbose_logs_progress_to_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shards_root = tmp_path / "shards"
    shard = shards_root / "blocksworld"
    _write_jsonl(
        shard / "accepted_manifest.jsonl",
        [
            {
                "instance_id": "blocksworld-train-easy-0000",
                "split": "train",
                "bucket": "easy",
                "normalized_problem_hash": "hash-a",
            }
        ],
    )
    _write_jsonl(shard / "rejections.jsonl", [])

    monkeypatch.setattr(
        "scripts.phase3.extend_curriculum_workflow.merge_shards",
        lambda *, shards_root, candidate_root: {"accepted_total": 1, "duplicate_accepted_problem_hashes": 0},
    )

    run_workflow(
        WorkflowConfig(
            config_path=tmp_path / "config.json",
            shards_root=shards_root,
            candidate_root=tmp_path / "candidate",
            target_total=10,
            max_generate_commands=0,
            command_timeout_seconds=1,
            attempt_window=1,
            max_attempts_per_bucket=1,
            seed=123,
            candidate_multiplier=1,
            save_plans=False,
            plan_limit=0,
            plan_timeout_seconds=1,
            planner_path=tmp_path / "planner.py",
            planner_alias="lama-first",
            final_root=tmp_path / "final",
            update_root=False,
            verbose=True,
        )
    )

    captured = capsys.readouterr()
    assert "[extend-curriculum] Initial shard state" in captured.err
    assert "Safety merge complete" in captured.err


def test_save_plans_targets_updated_final_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shards_root = tmp_path / "shards"
    shard = shards_root / "blocksworld"
    _write_jsonl(
        shard / "accepted_manifest.jsonl",
        [
            {
                "instance_id": "blocksworld-train-easy-0000",
                "split": "train",
                "bucket": "easy",
                "normalized_problem_hash": "hash-a",
            }
        ],
    )
    _write_jsonl(shard / "rejections.jsonl", [])
    final_root = tmp_path / "final"
    candidate_root = tmp_path / "candidate"
    plan_roots: list[Path] = []

    monkeypatch.setattr(
        "scripts.phase3.extend_curriculum_workflow.merge_shards",
        lambda *, shards_root, candidate_root: {"accepted_total": 1, "duplicate_accepted_problem_hashes": 0},
    )
    monkeypatch.setattr(
        "scripts.phase3.extend_curriculum_workflow.update_final_root",
        lambda *, shards_root, final_root, safety_summary: {"accepted_total": 1, "duplicate_accepted_problem_hashes": 0},
    )

    def fake_save_plans(config):
        plan_roots.append(config.input_root)
        return {
            "input_root": str(config.input_root),
            "limit": config.limit,
            "attempted_total": 1,
            "plan_available_total": 1,
            "status_counts": {"success_plan_saved": 1},
        }

    monkeypatch.setattr("scripts.phase3.extend_curriculum_workflow.save_fast_downward_plans", fake_save_plans)

    result = run_workflow(
        WorkflowConfig(
            config_path=tmp_path / "config.json",
            shards_root=shards_root,
            candidate_root=candidate_root,
            target_total=1,
            max_generate_commands=0,
            command_timeout_seconds=1,
            attempt_window=1,
            max_attempts_per_bucket=1,
            seed=123,
            candidate_multiplier=1,
            save_plans=True,
            plan_limit=None,
            plan_timeout_seconds=1,
            planner_path=tmp_path / "planner.py",
            planner_alias="lama-first",
            final_root=final_root,
            update_root=True,
            verbose=False,
        )
    )

    assert plan_roots == [final_root.resolve()]
    assert result["plan_root"] == str(final_root.resolve())
    assert result["plan_summary"]["limit"] is None


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
