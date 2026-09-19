"""CPU-only smoke tests for the generalization-robustness-v2 evaluation stage (#124)."""

from examples.planning_benchmark_slice import expanded_generalization_eval as gen_eval
from examples.planning_benchmark_slice.expanded_scheduler import ROOT

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
