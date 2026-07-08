from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts.phase3.attempt_runner import run_planner_jobs
from scripts.phase3.pddl import ground_actions, normalize_action_string, parse_task, replay_plan
from scripts.phase3.pipeline import DEFAULT_PLANNERS, _available_fast_downward_aliases, _external_plan, build_instance_accounting, generate_supervised_data
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
        "planner": "gbfs",
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
    assert DEFAULT_PLANNERS == ("gbfs", "ff", "iw", "graphplan")
    assert verify_planner_attempts(input_root / "accepted_manifest.jsonl", output_root / "diagnostics" / "planner_attempts.jsonl", ["gbfs", "ff", "iw", "graphplan"])["missing_attempt_records"] == 0
    assert validate_jsonl_schema(output_root / "schema" / "supervised_planning_example.schema.json", [output_root / "train.jsonl", output_root / "dev.jsonl", output_root / "test.jsonl"])["invalid_rows"] == 0
    assert validate_jsonl_schema(output_root / "schema" / "planner_attempt.schema.json", [output_root / "diagnostics" / "planner_attempts.jsonl"])["invalid_rows"] == 0
    assert validate_jsonl_schema(output_root / "schema" / "instance_accounting.schema.json", [output_root / "diagnostics" / "instance_accounting.jsonl"])["invalid_rows"] == 0
    assert verify_replay_validated_examples(output_root)["examples_with_failed_replay"] == 0
    assert verify_fidelity_labels(output_root)["invalid_external_full_trace_labels"] == 0
    rows = [json.loads(line) for line in (output_root / "train.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert {row["planner"] for row in rows} == {"gbfs", "ff", "iw", "graphplan"}
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


def test_external_planner_timeout_kills_child_process_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    marker_path = tmp_path / "external_child_terminated.txt"
    script = tmp_path / "planner.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import subprocess, sys, textwrap, time\n"
        "child = textwrap.dedent('''\n"
        "import signal, sys, time\n"
        "marker = sys.argv[1]\n"
        "def handle(_signum, _frame):\n"
        "    open(marker, 'w', encoding='utf-8').write('terminated')\n"
        "    raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM, handle)\n"
        "time.sleep(30)\n"
        "''')\n"
        f"subprocess.Popen([sys.executable, '-c', child, {str(marker_path)!r}])\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    account = {"domain_path": "domain.pddl", "problem_path": "problem.pddl"}
    monkeypatch.setenv("PHASE3_FF_PLANNER", str(script))

    _plan, _command, status = _external_plan("ff", account, {"planner_timeout": 1})

    assert status == "failed_planner_timeout"
    assert _wait_for_file(marker_path)


def test_fast_downward_alias_probe_controls_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = tmp_path / "fast-downward.py"
    script.write_text("#!/usr/bin/env python3\nprint('lama')\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setattr("scripts.phase3.pipeline._FAST_DOWNWARD_ALIASES", None)

    assert _available_fast_downward_aliases(script) == {"lama"}


def test_generate_supervised_data_rejects_old_bfs_planner_label(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_reject_old_bfs_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)

    with pytest.raises(ValueError, match="unsupported Phase 3 planner: bfs"):
        generate_supervised_data(input_root, fixture_root / "phase3", planners=("bfs",))

    shutil.rmtree(fixture_root)


def test_duplicate_plan_hashes_are_preserved_as_distinct_planner_examples(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_duplicate_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    output_root = fixture_root / "phase3"
    summary = generate_supervised_data(input_root, output_root, planners=("gbfs",))["summary"]

    rows = [json.loads(line) for line in (output_root / "train.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert summary["emitted_examples"] == len(rows) == 1
    assert len({(row["planner"], row["plan_hash"]) for row in rows}) == 1
    shutil.rmtree(fixture_root)


def test_generate_supervised_data_parallel_jobs_match_sequential_records(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_parallel_jobs_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    sequential_root = fixture_root / "sequential"
    parallel_root = fixture_root / "parallel"

    sequential_summary = generate_supervised_data(input_root, sequential_root, jobs=1)["summary"]
    parallel_summary = generate_supervised_data(input_root, parallel_root, jobs=2)["summary"]

    assert parallel_summary == sequential_summary
    for relative in ("diagnostics/planner_attempts.jsonl", "diagnostics/replay_validation.jsonl", "train.jsonl", "dev.jsonl", "test.jsonl"):
        assert (parallel_root / relative).read_text(encoding="utf-8") == (sequential_root / relative).read_text(encoding="utf-8")
    shutil.rmtree(fixture_root)


def test_generate_curriculum_trace_dataset_rejects_zero_jobs(tmp_path: Path) -> None:
    output_root = tmp_path / "out"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/phase3/generate_curriculum_trace_dataset.py",
            "--limit",
            "1",
            "--jobs",
            "0",
            "--output-root",
            str(output_root),
            "--quiet",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "--jobs must be at least 1" in completed.stderr


def test_generate_supervised_data_cli_rejects_zero_jobs(tmp_path: Path) -> None:
    output_root = tmp_path / "out"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.phase3.generate_supervised_data",
            "--jobs",
            "0",
            "--output-root",
            str(output_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "--jobs must be at least 1" in completed.stderr


def test_run_planner_jobs_times_out_slow_attempt() -> None:
    account = _attempt_account("tiny", "tiny-1")

    attempts, replay_rows, examples = run_planner_jobs(1, [account], ("gbfs",), {"tiny-1": {"status": "supported"}}, {"tiny-1": {}}, {"planner_attempt_timeout_seconds": 1, "domain_timeout_seconds": 60}, None, _slow_attempt)

    assert replay_rows == []
    assert examples == []
    assert attempts[0]["status"] == "failed_planner_timeout"
    assert attempts[0]["resource_gate"] == "planner_attempt_timeout"


def test_run_planner_jobs_blocks_domain_after_accumulated_timeouts() -> None:
    account = _attempt_account("tiny", "tiny-1")

    attempts, _replay_rows, _examples = run_planner_jobs(1, [account], ("gbfs", "ff", "iw"), {"tiny-1": {"status": "supported"}}, {"tiny-1": {}}, {"planner_attempt_timeout_seconds": 1, "domain_timeout_seconds": 2}, None, _slow_attempt)

    assert [attempt["status"] for attempt in attempts] == ["failed_planner_timeout", "failed_planner_timeout", "skipped_resource_limit"]
    assert attempts[2]["resource_gate"] == "domain_timeout_budget"


def test_run_planner_jobs_reserves_parallel_domain_timeout_budget() -> None:
    account = _attempt_account("tiny", "tiny-1")

    attempts, _replay_rows, _examples = run_planner_jobs(4, [account], ("gbfs", "ff", "iw", "graphplan"), {"tiny-1": {"status": "supported"}}, {"tiny-1": {}}, {"planner_attempt_timeout_seconds": 1, "domain_timeout_seconds": 3}, None, _slow_attempt)

    assert [attempt["status"] for attempt in attempts].count("failed_planner_timeout") == 3
    assert [attempt["resource_gate"] for attempt in attempts].count("domain_timeout_budget") == 1


def test_run_planner_jobs_defers_reserved_domain_budget_until_actual_timeout() -> None:
    account = _attempt_account("tiny", "tiny-1")

    sequential, _sequential_replay, _sequential_examples = run_planner_jobs(1, [account], ("gbfs", "ff", "iw", "graphplan"), {"tiny-1": {"status": "supported"}}, {"tiny-1": {}}, {"planner_attempt_timeout_seconds": 1200, "domain_timeout_seconds": 3600}, None, _fast_attempt)
    parallel, _parallel_replay, _parallel_examples = run_planner_jobs(4, [account], ("gbfs", "ff", "iw", "graphplan"), {"tiny-1": {"status": "supported"}}, {"tiny-1": {}}, {"planner_attempt_timeout_seconds": 1200, "domain_timeout_seconds": 3600}, None, _fast_attempt)

    assert [attempt["status"] for attempt in parallel] == ["success_full_trace", "success_full_trace", "success_full_trace", "success_full_trace"]
    assert sorted(parallel, key=lambda attempt: str(attempt["planner"])) == sorted(sequential, key=lambda attempt: str(attempt["planner"]))


def test_run_planner_jobs_kills_child_process_group_on_timeout(tmp_path: Path) -> None:
    marker_path = tmp_path / "child_terminated.txt"
    account = {**_attempt_account("tiny", "tiny-1"), "marker_path": str(marker_path)}

    attempts, _replay_rows, _examples = run_planner_jobs(1, [account], ("gbfs",), {"tiny-1": {"status": "supported"}}, {"tiny-1": {}}, {"planner_attempt_timeout_seconds": 1, "domain_timeout_seconds": 60}, None, _attempt_with_child_process)

    assert attempts[0]["status"] == "failed_planner_timeout"
    assert _wait_for_file(marker_path)


def test_run_planner_jobs_kills_external_planner_group_on_parent_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pid_path = tmp_path / "external_child_parent_timeout.pid"
    script = _external_sigterm_resistant_script(tmp_path, pid_path)
    account = _attempt_account("tiny", "tiny-1")
    monkeypatch.setenv("PHASE3_FF_PLANNER", str(script))

    attempts, _replay_rows, _examples = run_planner_jobs(1, [account], ("ff",), {"tiny-1": {"status": "supported"}}, {"tiny-1": {}}, {"planner_attempt_timeout_seconds": 1, "domain_timeout_seconds": 60, "planner_timeout": 30}, None, _external_plan_attempt)

    assert attempts[0]["status"] == "failed_planner_timeout"
    pid = int(pid_path.read_text(encoding="utf-8"))
    assert _wait_for_process_exit(pid)


def test_run_planner_jobs_kills_sigterm_resistant_external_child_on_parent_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pid_path = tmp_path / "external_parent_timeout_ignores_sigterm.pid"
    script = _external_sigterm_resistant_script(tmp_path, pid_path)
    account = _attempt_account("tiny", "tiny-1")
    monkeypatch.setenv("PHASE3_FF_PLANNER", str(script))

    attempts, _replay_rows, _examples = run_planner_jobs(1, [account], ("ff",), {"tiny-1": {"status": "supported"}}, {"tiny-1": {}}, {"planner_attempt_timeout_seconds": 1, "domain_timeout_seconds": 60, "planner_timeout": 30}, None, _external_plan_attempt)

    assert attempts[0]["status"] == "failed_planner_timeout"
    pid = int(pid_path.read_text(encoding="utf-8"))
    assert _wait_for_process_exit(pid)


def test_external_planner_timeout_kills_sigterm_resistant_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pid_path = tmp_path / "external_ignores_sigterm.pid"
    script = _external_sigterm_resistant_script(tmp_path, pid_path)
    account = {"domain_path": "domain.pddl", "problem_path": "problem.pddl"}
    monkeypatch.setenv("PHASE3_FF_PLANNER", str(script))

    _plan, _command, status = _external_plan("ff", account, {"planner_timeout": 1})

    assert status == "failed_planner_timeout"
    pid = int(pid_path.read_text(encoding="utf-8"))
    assert _wait_for_process_exit(pid)


def test_run_planner_jobs_rejects_negative_timeout_limits() -> None:
    account = _attempt_account("tiny", "tiny-1")

    with pytest.raises(ValueError, match="planner_attempt_timeout_seconds must be non-negative"):
        run_planner_jobs(1, [account], ("gbfs",), {"tiny-1": {"status": "supported"}}, {"tiny-1": {}}, {"planner_attempt_timeout_seconds": -1, "domain_timeout_seconds": 60}, None, _slow_attempt)


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
                "planner": "gbfs",
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


def _attempt_account(domain: str, instance_id: str) -> dict[str, object]:
    return {
        "schema_version": "phase3_supervised_planning_v1",
        "domain": domain,
        "instance_id": instance_id,
        "split": "train",
        "bucket": "easy",
        "domain_path": "domain.pddl",
        "problem_path": "problem.pddl",
    }


def _slow_attempt(_account: dict[str, object], _preflight: dict[str, object], _vision: dict[str, object], planner: str, _limits: dict[str, int]) -> tuple[dict[str, object], None, None]:
    time.sleep(5)
    return {"schema_version": "phase3_supervised_planning_v1", "domain": "tiny", "instance_id": "tiny-1", "split": "train", "planner": planner, "status": "success_full_trace", "trace_fidelity": "success_full_trace", "replay_validation_id": "r", "plan_hash": "h"}, None, None


def _fast_attempt(_account: dict[str, object], _preflight: dict[str, object], _vision: dict[str, object], planner: str, _limits: dict[str, int]) -> tuple[dict[str, object], None, None]:
    return {"schema_version": "phase3_supervised_planning_v1", "domain": "tiny", "instance_id": "tiny-1", "split": "train", "planner": planner, "domain_path": "domain.pddl", "problem_path": "problem.pddl", "planner_command": None, "planner_version": None, "status": "success_full_trace", "trace_fidelity": "none", "replay_validation_id": None, "plan_hash": None}, None, None


def _external_plan_attempt(account: dict[str, object], _preflight: dict[str, object], _vision: dict[str, object], planner: str, limits: dict[str, int]) -> tuple[dict[str, object], None, None]:
    _plan, _command, status = _external_plan(planner, account, limits)
    return {"schema_version": "phase3_supervised_planning_v1", "domain": account["domain"], "instance_id": account["instance_id"], "split": account["split"], "planner": planner, "domain_path": account["domain_path"], "problem_path": account["problem_path"], "planner_command": _command, "planner_version": None, "trace_fidelity": "none", "replay_validation_id": None, "plan_hash": None, "status": status}, None, None


def _attempt_with_child_process(account: dict[str, object], _preflight: dict[str, object], _vision: dict[str, object], planner: str, _limits: dict[str, int]) -> tuple[dict[str, object], None, None]:
    marker_path = str(account["marker_path"])
    script = "import signal, sys, time\nmarker = sys.argv[1]\ndef handle(_signum, _frame):\n    open(marker, 'w', encoding='utf-8').write('terminated')\n    raise SystemExit(0)\nsignal.signal(signal.SIGTERM, handle)\ntime.sleep(30)\n"
    subprocess.Popen([sys.executable, "-c", script, marker_path])
    time.sleep(30)
    return {"schema_version": "phase3_supervised_planning_v1", "domain": "tiny", "instance_id": "tiny-1", "split": "train", "planner": planner, "status": "success_full_trace", "trace_fidelity": "success_full_trace", "replay_validation_id": "r", "plan_hash": "h"}, None, None


def _external_sigterm_resistant_script(root: Path, pid_path: Path) -> Path:
    script = root / "planner_sigterm_resistant.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import signal, subprocess, sys, textwrap, time\n"
        "child = textwrap.dedent('''\n"
        "import os, signal, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(str(os.getpid()))\n"
        "time.sleep(30)\n"
        "''')\n"
        f"subprocess.Popen([sys.executable, '-c', child, {str(pid_path)!r}])\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def _wait_for_file(path: Path) -> bool:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return False


def _wait_for_process_exit(pid: int) -> bool:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False
