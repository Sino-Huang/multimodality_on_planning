"""CPU-only smoke tests for the generalization-robustness-v2 evaluation stage (#124)."""

import json
from pathlib import Path

import pytest

from examples.planning_benchmark_slice import expanded_generalization_eval as gen_eval
from examples.planning_benchmark_slice.expanded_scheduler import ROOT
from scripts import run_expanded_generalization as cli

SMOKE_VARIANT = "gripper-shifted-init-940014"
ENDPOINT = "http://127.0.0.1:18092"


def smoke_protocol(tmp_path):
    protocol = gen_eval.load_protocol_v2(ROOT)
    # Keep the real repo root for candidate asset resolution; redirect only the
    # episode/view outputs into the pytest tmp dir and relativize identities to "/".
    protocol["root"] = "/"
    protocol["output_root"] = str(tmp_path / "generalization-v2-smoke")
    return protocol


def test_bindings_match_the_frozen_admission_membership():
    protocol = gen_eval.load_protocol_v2(ROOT)
    admission = gen_eval.load_admission(ROOT, protocol)
    tasks = gen_eval.load_tasks(ROOT, protocol, admission)
    rows = gen_eval.bindings(tasks, protocol)

    assert len(tasks) == 25
    assert len(rows) == 1200
    models = [row for row in rows if row["condition"] in gen_eval.GPU_CONDITIONS]
    controls = [row for row in rows if row["condition"] in gen_eval.CPU_CONDITIONS]
    assert len(models) == 300
    assert len(controls) == 900

    variants = {task["variant_id"] for task in tasks}
    assert variants == {variant for ids in admission["membership"].values() for variant in ids}
    per_variant = {variant: [row for row in rows if row["variant_id"] == variant] for variant in variants}
    assert all(len(rows_for_variant) == 48 for rows_for_variant in per_variant.values())
    assert all(
        len([row for row in rows_for_variant if row["condition"] in gen_eval.GPU_CONDITIONS]) == 12
        for rows_for_variant in per_variant.values()
    )
    assert all(
        len([row for row in rows_for_variant if row["condition"] in gen_eval.CPU_CONDITIONS]) == 36
        for rows_for_variant in per_variant.values()
    )
    for rows_for_variant in per_variant.values():
        seeds = sorted(row["seed"] for row in rows_for_variant if row["condition"] == "random_valid")
        assert seeds == sorted([17, 1013, 2027, 3041, 4001] * 6)
        non_control_seeds = {
            row["seed"] for row in rows_for_variant if row["condition"] != "random_valid"
        }
        assert non_control_seeds == {17}

    parts = [
        gen_eval.assigned_bindings(rows, worker, kind)
        for kind in ("models", "controls")
        for worker in range(gen_eval.WORKERS)
    ]
    assert [len(part) for part in parts] == [150, 150, 450, 450]
    assert sorted(row["index"] for part in parts for row in part) == list(range(1200))


def _run_control_binding(tmp_path, condition, seed):
    protocol = smoke_protocol(tmp_path)
    admission = gen_eval.load_admission(ROOT, protocol)
    tasks = gen_eval.load_tasks(ROOT, protocol, admission, only=[SMOKE_VARIANT])
    rows = [
        row
        for row in gen_eval.bindings(tasks, protocol)
        if row["condition"] == condition and row["seed"] == seed and row["modality"] == "text-state"
    ]
    assert len(rows) == len(protocol["learned_algorithms"])
    reports = []
    for binding in rows:
        report, retained = gen_eval.run_binding(
            ROOT,
            protocol,
            tasks[0],
            binding,
            None,
            ENDPOINT,
            None,
        )
        assert retained is False
        reports.append((binding, report))
    return protocol, reports


def _validate_episode_schema(binding, report):
    identity = {
        "schema_version": "expanded_baseline_episode_v1",
        "protocol_id": "expanded-generalization-robustness-v2",
        "panel_id": "expanded-panel-v2-qualified",
        "family": binding["family"],
        "task_id": binding["variant_id"],
        "modality": binding["modality"],
        "algorithm": binding["algorithm"],
        "arm": binding["condition"],
        "seed": binding["seed"],
        "checkpoint": None,
        "model_id": "Qwen/Qwen3-VL-8B-Instruct",
        "model_revision": "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
        "oracle_assisted_valid_operation_control": binding["condition"] == "random_valid",
    }
    for key, value in identity.items():
        assert report[key] == value, key
    assert report["outcome"] == "RECORDED"
    result = report["result"]
    for key in (
        "invariant_valid_success",
        "goal_reached",
        "algorithm_invariants_hold",
        "decision_count",
        "expansion_count",
        "invalid_operation_count",
        "invalid_operation_rate",
        "model_call_limit",
        "termination_reason",
    ):
        assert key in result, key
    assert len(report["events"]) == result["decision_count"]
    assert len(report["call_measurements"]) == result["decision_count"]
    assert all(measurement["model_call"] is False for measurement in report["call_measurements"])
    assert all(event["view"] is not None for event in report["events"])


def test_exact_reference_control_episode_end_to_end(tmp_path):
    protocol, reports = _run_control_binding(tmp_path, "exact_reference", 17)
    for binding, report in reports:
        _validate_episode_schema(binding, report)
        assert report["result"]["termination_reason"] == "goal_reached"
        assert report["result"]["invariant_valid_success"] is True
        assert report["result"]["invalid_operation_count"] == 0
        episode, _, view_output = gen_eval.binding_paths(ROOT, protocol, binding)
        assert episode.is_file()
        assert (view_output / "views.json.gz").is_file()
        replay = gen_eval.independently_replay(ROOT, _task(tmp_path), report, ENDPOINT)
        assert replay == report["result"]


def _task(tmp_path):
    protocol = smoke_protocol(tmp_path)
    admission = gen_eval.load_admission(ROOT, protocol)
    tasks = gen_eval.load_tasks(ROOT, protocol, admission, only=[SMOKE_VARIANT])
    return tasks[0]


def test_random_valid_control_episode_end_to_end(tmp_path):
    _, reports = _run_control_binding(tmp_path, "random_valid", 1013)
    for binding, report in reports:
        _validate_episode_schema(binding, report)
        assert report["result"]["decision_count"] >= 1
        assert report["result"]["termination_reason"] in {
            "goal_reached",
            "decision_budget_exhausted",
            "expansion_budget_exhausted",
            "frontier_exhausted",
            "deterministic_invalid_operation",
        }
        replay = gen_eval.independently_replay(ROOT, _task(tmp_path), report, ENDPOINT)
        assert replay == report["result"]


def _smoke_session(tmp_path, arm, model_call_cap):
    protocol = smoke_protocol(tmp_path)
    admission = gen_eval.load_admission(ROOT, protocol)
    tasks = gen_eval.load_tasks(ROOT, protocol, admission, only=[SMOKE_VARIANT])
    session = gen_eval.V2VisualSession(
        ROOT,
        tasks[0]["row"],
        "best_first_add_greedy",
        arm,
        17,
        tmp_path / "session-output",
        protocol["protocol_id"],
        model_call_cap=model_call_cap,
    )
    return session


def test_pretrained_base_arm_is_capped_at_one_model_call(tmp_path):
    session = _smoke_session(tmp_path, "pretrained_base", gen_eval.BASE_MODEL_CALL_CAP)
    assert session.next_request() is not None
    session.submit(session.reference_output())
    assert session.next_request() is None
    result = session.result()
    assert result["termination_reason"] == "model_call_limit"
    assert result["decision_count"] == 1
    assert result["model_call_limit"] == 1


def test_learned_arm_without_cap_continues_past_one_call(tmp_path):
    session = _smoke_session(tmp_path, "process_sft", None)
    assert session.next_request() is not None
    session.submit(session.reference_output())
    assert session.next_request() is not None


def test_summarize_reports_aggregates_by_condition_family_modality():
    report = {
        "arm": "exact_reference",
        "family": "shifted-init",
        "modality": "text-state",
        "result": {
            "invariant_valid_success": True,
            "decision_count": 6,
            "expansion_count": 4,
            "invalid_operation_count": 0,
        },
    }
    summary = gen_eval.summarize_reports([report, dict(report, arm="random_valid")])
    assert summary["episodes"] == 2
    assert summary["by_condition"]["exact_reference"]["episodes"] == 1
    assert summary["by_condition"]["random_valid"]["decisions"] == 6
    assert summary["by_family"]["shifted-init"]["invariant_valid_success"] == 2
    assert summary["by_modality"]["text-state"]["expansions"] == 8


def _mini_context(tmp_path, monkeypatch):
    """One fabricated admitted variant with tmp episode outputs and a patched context."""

    protocol = gen_eval.load_protocol_v2(ROOT)
    protocol["root"] = "/"
    protocol["output_root"] = str(tmp_path / "audit-out")
    admission = {"membership_sha256": protocol["membership_rule"]["membership_sha256"]}
    task = {"variant_id": "tiny-scale-up-930000", "family": "scale-up", "task_index": 0}
    rows = gen_eval.bindings([task], protocol)
    monkeypatch.setattr(cli, "_evaluation_context", lambda root: (protocol, admission, [task], rows))
    return protocol, admission, task, rows


def _worker_audit_fixture(tmp_path, monkeypatch, *, worker=0, kind="models", completed=None, skip_episode=False):
    protocol, _, _, rows = _mini_context(tmp_path, monkeypatch)
    selected = gen_eval.assigned_bindings(rows, worker, kind)
    attempt = tmp_path / f"generalization-v2-evaluate-{kind}-{worker}" / "1"
    attempt.mkdir(parents=True)
    (attempt / "terminal.json").write_text(json.dumps({"status": "succeeded"}))
    if completed is None:
        completed = len(selected)
    (attempt / "worker-result.json").write_text(
        json.dumps(
            {
                "schema_version": gen_eval.WORKER_SCHEMA,
                "outcome": "PASS",
                "protocol_id": protocol["protocol_id"],
                "worker": worker,
                "kind": kind,
                "completed": completed,
            }
        )
    )
    for position, binding in enumerate(selected):
        episode, _, _ = gen_eval.binding_paths(ROOT, protocol, binding)
        episode.parent.mkdir(parents=True, exist_ok=True)
        if not (skip_episode and position == len(selected) - 1):
            episode.touch()
    monkeypatch.setenv("EXPANDED_TERMINAL_PATH", str(attempt / "terminal.json"))
    return selected


def test_audit_evaluate_worker_passes_for_complete_attempt(tmp_path, monkeypatch, capsys):
    selected = _worker_audit_fixture(tmp_path, monkeypatch)
    summary = cli.audit_evaluate_worker(ROOT, 0, "models")
    assert summary["completed"] == len(selected)
    output = capsys.readouterr().out
    assert "PASS" in output
    assert f"completed {len(selected)}/{len(selected)}" in output


def test_audit_evaluate_worker_fails_on_count_mismatch(tmp_path, monkeypatch):
    _worker_audit_fixture(tmp_path, monkeypatch, completed=0)
    with pytest.raises(ValueError, match="completed count differs"):
        cli.audit_evaluate_worker(ROOT, 0, "models")


def test_audit_evaluate_worker_fails_on_missing_episode_file(tmp_path, monkeypatch):
    _worker_audit_fixture(tmp_path, monkeypatch, skip_episode=True)
    with pytest.raises(ValueError, match="missing episode files"):
        cli.audit_evaluate_worker(ROOT, 0, "models")


def _final_audit_fixture(tmp_path, monkeypatch, *, outcome="PASS", missing=None, replayed=None):
    protocol, admission, _, rows = _mini_context(tmp_path, monkeypatch)
    if replayed is None:
        replayed = len(rows)
    if missing is None:
        missing = [] if outcome == "PASS" else [1, 2]
    evaluation = {
        "schema_version": gen_eval.EVALUATION_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "membership_sha256": admission["membership_sha256"],
        "outcome": outcome,
        "bindings": len(rows),
        "episodes_replayed": replayed,
        "missing_bindings": missing,
        "by_condition": {
            "learned_adapter": {"episodes": 6},
            "pretrained_base": {"episodes": 6},
            "random_valid": {"episodes": 30},
            "exact_reference": {"episodes": 6},
        },
    }
    output_dir = Path(protocol["output_root"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation.json").write_text(json.dumps(evaluation))
    return rows


def test_audit_evaluate_final_passes_for_complete_evaluation(tmp_path, monkeypatch, capsys):
    rows = _final_audit_fixture(tmp_path, monkeypatch)
    summary = cli.audit_evaluate_final(ROOT)
    assert summary["episodes_replayed"] == len(rows)
    output = capsys.readouterr().out
    assert "PASS" in output
    assert "12 model + 36 control" in output
    assert f"{len(rows)}/{len(rows)} bindings" in output


def test_audit_evaluate_final_fails_on_incomplete_evaluation(tmp_path, monkeypatch):
    _final_audit_fixture(tmp_path, monkeypatch, outcome="INCOMPLETE")
    with pytest.raises(ValueError, match="incomplete"):
        cli.audit_evaluate_final(ROOT)


def test_audit_evaluate_final_fails_on_membership_sha_mismatch(tmp_path, monkeypatch):
    protocol, _, _, rows = _mini_context(tmp_path, monkeypatch)
    output_dir = Path(protocol["output_root"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation.json").write_text(
        json.dumps(
            {
                "schema_version": gen_eval.EVALUATION_SCHEMA,
                "protocol_id": protocol["protocol_id"],
                "membership_sha256": "0" * 64,
                "outcome": "PASS",
                "bindings": len(rows),
                "episodes_replayed": len(rows),
                "missing_bindings": [],
                "by_condition": {},
            }
        )
    )
    with pytest.raises(ValueError, match="provenance differs"):
        cli.audit_evaluate_final(ROOT)
