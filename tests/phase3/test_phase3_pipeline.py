from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.phase3.pddl import ground_actions, normalize_action_string, parse_task, replay_plan
from scripts.phase3.pipeline import _available_fast_downward_aliases, _bfs, _external_plan, build_instance_accounting, generate_supervised_data
from scripts.phase3.schema import validate_instance_accounting, validate_planner_attempt, validate_supervised_example
from scripts.phase3.verifiers import VerificationError, validate_jsonl_schema, verify_fidelity_labels, verify_manifest_coverage, verify_planner_attempts, verify_replay_validated_examples


DOMAIN = """
(define (domain tiny)
  (:requirements :strips :typing)
  (:types loc - object)
  (:predicates (at ?x - loc) (connected ?x ?y - loc))
  (:action move
    :parameters (?from ?to - loc)
    :precondition (and (at ?from) (connected ?from ?to))
    :effect (and (at ?to) (not (at ?from))))
)
"""

PROBLEM = """
(define (problem tiny-p1)
  (:domain tiny)
  (:objects a b - loc)
  (:init (at a) (connected a b))
  (:goal (and (at b)))
)
"""


def test_action_normalization_handles_case_and_parentheses() -> None:
    assert normalize_action_string(" MOVE A B ") == "(move a b)"
    assert normalize_action_string("(MOVE A B)") == "(move a b)"


def test_replay_validator_accepts_valid_plan(tmp_path: Path) -> None:
    domain, problem = _write_pddl(tmp_path)
    task = parse_task(domain, problem)
    grounded, status = ground_actions(task, max_grounded_actions=100, max_grounded_atoms=100)

    assert status is None
    replay = replay_plan(task, ["(move a b)"], grounded_actions=grounded)

    assert replay["replay_ok"] is True
    assert replay["goal_satisfied"] is True


def test_replay_validator_rejects_invalid_action(tmp_path: Path) -> None:
    domain, problem = _write_pddl(tmp_path)
    task = parse_task(domain, problem)
    grounded, _status = ground_actions(task, max_grounded_actions=100, max_grounded_atoms=100)

    replay = replay_plan(task, ["(move b a)"], grounded_actions=grounded)

    assert replay["replay_ok"] is False
    assert replay["status"] == "failed_replay_invalid_action"


def test_zero_length_solved_instance_replays_success(tmp_path: Path) -> None:
    domain, problem = _write_pddl(tmp_path, problem_text=PROBLEM.replace("(:goal (and (at b)))", "(:goal (and (at a)))"))
    task = parse_task(domain, problem)
    grounded, _status = ground_actions(task, max_grounded_actions=100, max_grounded_atoms=100)

    replay = replay_plan(task, [], grounded_actions=grounded)

    assert replay["replay_ok"] is True
    assert replay["goal_satisfied"] is True


def test_preflight_detects_unsupported_negative_and_conditional_constructs(tmp_path: Path) -> None:
    domain, problem = _write_pddl(
        tmp_path,
        domain_text=DOMAIN.replace(":requirements :strips :typing", ":requirements :strips :typing :negative-preconditions :conditional-effects").replace("(at ?from) (connected ?from ?to)", "(not (at ?to)) (connected ?from ?to)").replace("(at ?to) (not (at ?from))", "(when (connected ?from ?to) (at ?to)) (not (at ?from))"),
    )
    task = parse_task(domain, problem)

    assert "negative_preconditions_requirement" in task.unsupported_features
    assert "conditional_effects_requirement" in task.unsupported_features


def test_schema_rejects_unknown_status_and_absolute_path() -> None:
    assert validate_planner_attempt({"status": "made_up"})
    assert validate_instance_accounting(
        {
            "schema_version": "phase3_supervised_planning_v1",
            "domain": "tiny",
            "instance_id": "tiny-1",
            "split": "train",
            "domain_path": "/absolute/domain.pddl",
            "problem_path": "problem.pddl",
            "vision_status": "vision_missing_frames",
        }
    )
    assert validate_supervised_example({"schema_version": "phase3_supervised_planning_v1"})


def test_schema_rejects_wrong_diagnostic_schema_version() -> None:
    attempt = {
        "schema_version": "wrong",
        "domain": "tiny",
        "instance_id": "tiny-1",
        "split": "train",
        "planner": "bfs",
        "status": "success_full_trace",
        "trace_fidelity": "success_full_trace",
        "replay_validation_id": "r1",
    }
    assert any("schema_version" in error for error in validate_planner_attempt(attempt))


def test_instance_accounting_missing_frames_is_diagnostic(tmp_path: Path) -> None:
    input_root = _fixture_dataset(tmp_path, with_frame=False)
    output_root = tmp_path / "phase3"

    rows = build_instance_accounting(input_root, output_root)

    assert len(rows) == 1
    assert rows[0]["vision_status"] == "vision_missing_frames"


def test_generate_supervised_data_and_verifiers_on_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(Path.cwd())
    fixture_root = Path("tmp") / f"phase3_pytest_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    output_root = fixture_root / "phase3"

    summary = generate_supervised_data(input_root, output_root)["summary"]

    assert summary["accepted_instances"] == 1
    assert summary["planner_attempts"] == 4
    assert summary["emitted_examples"] == 4
    assert verify_manifest_coverage(input_root / "accepted_manifest.jsonl", output_root / "diagnostics" / "instance_accounting.jsonl")["missing_from_diagnostics"] == 0
    assert verify_planner_attempts(input_root / "accepted_manifest.jsonl", output_root / "diagnostics" / "planner_attempts.jsonl", ["bfs", "ff", "iw", "graphplan"])["missing_attempt_records"] == 0
    assert validate_jsonl_schema(output_root / "schema" / "supervised_planning_example.schema.json", [output_root / "train.jsonl", output_root / "dev.jsonl", output_root / "test.jsonl"])["invalid_rows"] == 0
    assert validate_jsonl_schema(output_root / "schema" / "planner_attempt.schema.json", [output_root / "diagnostics" / "planner_attempts.jsonl"])["invalid_rows"] == 0
    assert validate_jsonl_schema(output_root / "schema" / "instance_accounting.schema.json", [output_root / "diagnostics" / "instance_accounting.jsonl"])["invalid_rows"] == 0
    assert verify_replay_validated_examples(output_root)["examples_with_failed_replay"] == 0
    assert verify_fidelity_labels(output_root)["invalid_external_full_trace_labels"] == 0
    rows = [json.loads(line) for line in (output_root / "train.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert {row["planner"] for row in rows} == {"bfs", "ff", "iw", "graphplan"}
    for row in rows:
        assert row["trace_fidelity"] == "success_full_trace"
        assert row["supervised_target"]["planner_trace"]
    shutil.rmtree(fixture_root)


def test_schema_cli_uses_schema_document(tmp_path: Path) -> None:
    schema = tmp_path / "schema.json"
    jsonl = tmp_path / "rows.jsonl"
    schema.write_text(
        json.dumps(
            {
                "required": ["schema_version"],
                "properties": {"schema_version": {"const": "phase3_supervised_planning_v1"}},
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )
    jsonl.write_text(json.dumps({"schema_version": "wrong"}) + "\n", encoding="utf-8")

    with pytest.raises(VerificationError):
        validate_jsonl_schema(schema, [jsonl])


def test_external_planner_success_replay_plan_extraction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = tmp_path / "planner.py"
    script.write_text("#!/usr/bin/env python3\nprint('0: (move a b)')\n", encoding="utf-8")
    script.chmod(0o755)
    account = {"domain_path": "domain.pddl", "problem_path": "problem.pddl"}
    monkeypatch.setenv("PHASE3_FF_PLANNER", str(script))

    plan, command, status = _external_plan("ff", account, {"planner_timeout": 5})

    assert status == "success_plan_replayed"
    assert plan == ["(move a b)"]
    assert command is not None


def test_external_planner_timeout_maps_to_controlled_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = tmp_path / "planner.py"
    script.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(2)\n", encoding="utf-8")
    script.chmod(0o755)
    account = {"domain_path": "domain.pddl", "problem_path": "problem.pddl"}
    monkeypatch.setenv("PHASE3_FF_PLANNER", str(script))

    _plan, _command, status = _external_plan("ff", account, {"planner_timeout": 1})

    assert status == "failed_planner_timeout"


def test_fast_downward_alias_probe_controls_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = tmp_path / "fast-downward.py"
    script.write_text("#!/usr/bin/env python3\nprint('lama')\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setattr("scripts.phase3.pipeline._FAST_DOWNWARD_ALIASES", None)

    assert _available_fast_downward_aliases(script) == {"lama"}


def test_bfs_resource_limit_returns_controlled_status(tmp_path: Path) -> None:
    domain, problem = _write_pddl(tmp_path)
    task = parse_task(domain, problem)
    grounded, _status = ground_actions(task, max_grounded_actions=100, max_grounded_atoms=100)

    _plan, trace, status = _bfs(task, grounded, limits={"bfs_max_depth": 200, "bfs_max_expansions": 0, "max_plan_length": 500, "max_trace_steps": 500})

    assert status == "skipped_resource_limit"
    assert trace["expansion_count"] == 1


def test_duplicate_plan_hashes_are_preserved_as_distinct_planner_examples(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_duplicate_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    output_root = fixture_root / "phase3"
    summary = generate_supervised_data(input_root, output_root, planners=("bfs",))["summary"]

    rows = [json.loads(line) for line in (output_root / "train.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert summary["emitted_examples"] == len(rows) == 1
    assert len({(row["planner"], row["plan_hash"]) for row in rows}) == 1
    shutil.rmtree(fixture_root)


def test_verify_replay_validated_examples_detects_failed_replay(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    (root / "diagnostics").mkdir(parents=True)
    (root / "train.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "phase3_supervised_planning_v1",
                "example_id": "ex",
                "domain": "tiny",
                "instance_id": "tiny-1",
                "split": "train",
                "planner": "bfs",
                "plan_hash": "h",
                "trace_fidelity": "success_full_trace",
                "vision_supervision_available": False,
                "model_facing": {},
                "supervised_target": {},
                "evaluation_metadata": {"replay_validation_id": "r1"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "dev.jsonl").write_text("", encoding="utf-8")
    (root / "test.jsonl").write_text("", encoding="utf-8")
    (root / "diagnostics" / "replay_validation.jsonl").write_text(
        json.dumps({"replay_validation_id": "r1", "replay_ok": False, "goal_satisfied": False}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(VerificationError):
        verify_replay_validated_examples(root)


def _write_pddl(root: Path, *, domain_text: str = DOMAIN, problem_text: str = PROBLEM) -> tuple[Path, Path]:
    domain = root / "domain.pddl"
    problem = root / "problem.pddl"
    domain.write_text(domain_text, encoding="utf-8")
    problem.write_text(problem_text, encoding="utf-8")
    return domain, problem


def _fixture_dataset(root: Path, *, with_frame: bool) -> Path:
    instance = root / "data" / "tiny" / "train" / "easy" / "tiny-train-easy-0000"
    render = instance / "render"
    frames = render / "frames"
    frames.mkdir(parents=True)
    domain, problem = _write_pddl(instance)
    (render / "result.json").write_text('{"status":"success"}\n', encoding="utf-8")
    (render / "trace.vfg.json").write_text('{"actions":["(move a b)"]}\n', encoding="utf-8")
    if with_frame:
        (frames / "frame_000.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    input_root = root / "data"
    (input_root / "summary.json").write_text('{"accepted_total":1}\n', encoding="utf-8")
    row = {
        "index": 0,
        "domain_id": "tiny",
        "instance_id": "tiny-train-easy-0000",
        "split": "train",
        "bucket": "easy",
        "domain_path": str(domain),
        "problem_path": str(problem),
        "render_result_path": str(render / "result.json"),
    }
    (input_root / "accepted_manifest.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    return input_root
