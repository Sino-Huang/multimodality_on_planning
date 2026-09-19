"""CPU-only Phase 2 runner tests for Goal 11."""

import hashlib
from pathlib import Path

import pytest

from examples.planning_benchmark_slice import expanded_generalization_run as runner
from scripts import audit_expanded_baseline as baseline_audit
from scripts import run_expanded_generalization as cli


def protocol(tmp_path):
    return {
        "protocol_id": "test-generalization",
        "output_root": "qualification",
        "budget_branch": "generalization_robustness",
        "budget_gpu_hours": 32,
        "algorithms": ["bfs"],
        "modalities": ["text-state"],
        "eligibility": {
            "grounding_estimate_ceiling": 200000,
            "max_decisions_per_algorithm": 256,
            "max_expansions_per_algorithm": 128,
            "max_summed_decisions": 512,
            "max_input_tokens_per_call": 32384,
        },
        "evaluation": {"reference_decision_multiplier": 2},
        "throughput_probe": {"timing_calls": 180, "call_time_margin": 1.5},
        "admission": {"safety_factor": 1.25},
        "source_problems": [],
        "panel": "panel.json",
    }


def task_row(name, family, decisions, *, stratum="compact"):
    return {
        "variant_id": name,
        "family": family,
        "source_stratum": stratum,
        "row": {
            "task_id": name,
            "reference_costs": {"bfs": {"decisions": decisions, "expansions": 1}},
        },
    }


def test_variant_id_is_deterministic_and_family_bound():
    assert runner.variant_id("grid", "scale-up", 930012) == "grid-scale-up-930012"
    assert runner.variant_id("grid", "scale-up", 930012) == runner.variant_id("grid", "scale-up", 930012)
    with pytest.raises(ValueError, match="variant identity"):
        runner.variant_id("grid", "unknown", 1)


def test_screen_records_ineligibility_without_replacement(tmp_path, monkeypatch):
    p = protocol(tmp_path)
    monkeypatch.setattr(runner, "load_protocol", lambda root: p)
    generated = {
        "variants": [
            {
                "variant_id": "tiny-scale-up-930000",
                "family": "scale-up",
                "source": {"domain": "tiny", "stratum_origin": "compact", "task_id": "source"},
                "task_path": "qualification/candidates/scale-up/tiny-scale-up-930000/task.json",
            }
        ]
    }
    runner.write(tmp_path / p["output_root"] / "generation.json", generated)
    task_path = tmp_path / generated["variants"][0]["task_path"]
    runner.write(task_path, {"domain_pddl": "domain", "problem_pddl": "problem"})
    monkeypatch.setattr(
        runner,
        "_structural_references",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("grounding_estimate_ceiling")),
    )
    report = runner.screen_stage(tmp_path)
    assert report["replacements"] == 0
    assert report["eligible_before_view_audit"] == 0
    assert len(report["variants"]) == 1
    assert report["variants"][0]["eligible"] is False
    assert report["variants"][0]["reason"] == "grounding_estimate_ceiling"


def test_freeze_emits_expanded_task_views_shape(tmp_path, monkeypatch):
    p = protocol(tmp_path)
    monkeypatch.setattr(runner, "load_protocol", lambda root: p)
    task_path = tmp_path / "qualification/candidates/object-renaming/tiny/task-with-views.json"
    task_path.parent.mkdir(parents=True)
    task_path.write_text("{}")
    scene = task_path.parent / "scene.png"
    scene.write_bytes(b"png")
    audit = {
        "variants": [
            {
                "variant_id": "tiny-object-renaming-950000",
                "family": "object-renaming",
                "eligible": True,
                "reason": "audit_pass",
                "audits": {"recoverability": {}},
                "task_path": str(task_path.relative_to(tmp_path)),
                "row": {"task_id": "tiny", "reference_costs": {"bfs": {"decisions": 1, "expansions": 1}}},
                "native_views": {
                    "source_manifest": "qualification/manifest.json",
                    "scenes": {"0": str(scene.relative_to(tmp_path))},
                    "goal_pages": [],
                },
                "view_manifest": {"scene_catalog": "qualification/catalog.json"},
                "measurements": [],
                "reference_paths": {},
                "source_stratum": "compact",
            }
        ]
    }
    runner.write(tmp_path / p["output_root"] / "audit.json", audit)
    suite = runner.freeze_stage(tmp_path)
    assert suite["eligible"] == 1
    frozen = suite["tasks"][0]
    assert {"row", "native_views", "view_manifest"} <= set(frozen)
    qualification = runner.read(tmp_path / p["output_root"] / "qualification.json")
    assert qualification["variants"][0]["asset_sha256"][str(scene.relative_to(tmp_path))] == runner.sha256(scene)


def test_freeze_blocks_empty_suite_and_records_absent_audit_reason(tmp_path, monkeypatch):
    p = protocol(tmp_path)
    monkeypatch.setattr(runner, "load_protocol", lambda root: p)
    runner.write(
        tmp_path / p["output_root"] / "audit.json",
        {
            "variants": [
                {
                    "variant_id": "tiny-scale-up-930000",
                    "family": "scale-up",
                    "eligible": False,
                    "reason": "exact_reference_failed:bfs:expansion_budget_exhausted",
                }
            ]
        },
    )
    with pytest.raises(RuntimeError, match="BLOCKED: zero eligible"):
        runner.freeze_stage(tmp_path)
    suite = runner.read(tmp_path / p["output_root"] / "suite.json")
    qualification = runner.read(tmp_path / p["output_root"] / "qualification.json")
    assert suite["outcome"] == qualification["outcome"] == "BLOCKED"
    assert qualification["variants"][0]["audit_status"] == "absent-because-ineligible"
    assert qualification["variants"][0]["audit_absence_reason"].startswith("exact_reference_failed")


def test_mapped_reference_translation_uses_live_canonical_input_and_target_position(monkeypatch, tmp_path):
    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.events = []
            self.done = False

        def next_request(self):
            if self.done:
                return None
            return type(
                "Request",
                (),
                {
                    "model_input": {
                        "observation": {"state_id": "derived-state"},
                        "search_memory": {
                            "successor_candidates": [
                                {"grounded_action": {"name": "move", "args": ["other"]}},
                                {"grounded_action": {"name": "move", "args": ["renamed"]}},
                            ]
                        },
                    }
                },
            )()

        def reference_output(self):
            return (
                '{"typed_operation":{"action":{"name":"move","args":["other"]},'
                '"source_state_id":"derived-state","frontier_intent":{"target_position":1}}}'
            )

        def submit(self, raw_output):
            operation = __import__("json").loads(raw_output)
            self.events.append(
                {
                    "accepted": True,
                    "input": {
                        "observation": {"state_id": "derived-state"},
                        "search_memory": {
                            "successor_candidates": [
                                {"grounded_action": {"name": "move", "args": ["other"]}},
                                {"grounded_action": {"name": "move", "args": ["renamed"]}},
                            ]
                        },
                    },
                    "raw_output": raw_output,
                }
            )
            self.operation = operation
            self.done = True

        def result(self):
            return {
                "algorithm_invariants_hold": True,
                "decision_count": 1,
                "expansion_count": 1,
                "goal_reached": True,
                "invalid_operation_count": 0,
                "invariant_valid_success": True,
                "termination_reason": "goal_reached",
                "model_call_limit": 2,
            }

    monkeypatch.setattr(runner, "VisualSession", FakeSession)
    source = {
        "events": [
            {
                "raw_output": (
                    '{"typed_operation":{"action":{"name":"move","args":["source"]},'
                    '"source_state_id":"source-state","frontier_intent":{"target_position":0}}}'
                )
            }
        ],
        "result": {
            "algorithm_invariants_hold": True,
            "decision_count": 1,
            "expansion_count": 1,
            "goal_reached": True,
            "invalid_operation_count": 0,
            "invariant_valid_success": True,
            "termination_reason": "goal_reached",
        },
    }
    translated = runner._translate_reference_report(
        tmp_path,
        {"task_id": "tiny"},
        "bfs",
        source,
        {"source": "renamed"},
        "test",
    )
    operation = __import__("json").loads(translated["events"][0]["raw_output"])
    assert operation["typed_operation"]["source_state_id"] == "derived-state"
    assert operation["typed_operation"]["frontier_intent"]["target_position"] == 1
    assert translated["events"][0]["input"]["observation"]["state_id"] == "derived-state"


def test_structural_reference_limit_is_normalized_after_cost_freeze(tmp_path):
    p = protocol(tmp_path)
    path = tmp_path / "reference-bfs.json.gz"
    runner.write(path, {"events": [], "result": {"model_call_limit": 512}})
    variant = {
        "reference_paths": {"bfs": str(path.relative_to(tmp_path))},
        "row": {"reference_costs": {"bfs": {"decisions": 7}}},
    }
    runner._normalize_reference_limits(tmp_path, variant, p)
    assert runner.read(path)["result"]["model_call_limit"] == 14


def test_audit_only_reruns_selected_variant_and_preserves_prior_aggregate(tmp_path, monkeypatch):
    p = protocol(tmp_path)
    monkeypatch.setattr(runner, "load_protocol", lambda root: p)
    monkeypatch.setattr(runner, "_panel_views", lambda root, protocol: {})
    first = {
        "variant_id": "first",
        "family": "scale-up",
        "eligible": False,
        "reason": "first-screen-failure",
        "row": {"task_path": "qualification/first/task.json"},
    }
    second = {
        "variant_id": "second",
        "family": "scale-up",
        "eligible": False,
        "reason": "second-screen-failure",
        "row": {"task_path": "qualification/second/task.json"},
    }
    for row in (first, second):
        (tmp_path / row["row"]["task_path"]).parent.mkdir(parents=True)
    runner.write(tmp_path / p["output_root"] / "screening.json", {"variants": [first, second]})
    runner.write(
        tmp_path / p["output_root"] / "generation.json",
        {"variants": [{"variant_id": "first"}, {"variant_id": "second"}]},
    )
    runner.write(
        tmp_path / p["output_root"] / "audit.json",
        {"variants": [{"variant_id": "second", "family": "scale-up", "eligible": False, "reason": "retained"}]},
    )
    result = runner.audit_stage(tmp_path, only=["first"], disjointness_inventory_rows=[])
    assert [row["variant_id"] for row in result["variants"]] == ["first"]
    aggregate = runner.read(tmp_path / p["output_root"] / "audit.json")
    assert {row["variant_id"] for row in aggregate["variants"]} == {"first", "second"}


def test_full_audit_recomputes_stale_candidate_receipts(tmp_path, monkeypatch):
    p = protocol(tmp_path)
    monkeypatch.setattr(runner, "load_protocol", lambda root: p)
    monkeypatch.setattr(runner, "_panel_views", lambda root, protocol: {})
    screened = {
        "variant_id": "stale",
        "family": "scale-up",
        "eligible": False,
        "reason": "current-screen-failure",
        "row": {"task_path": "qualification/stale/task.json"},
    }
    folder = (tmp_path / screened["row"]["task_path"]).parent
    folder.mkdir(parents=True)
    runner.write(folder / "audit.json", {**screened, "reason": "stale-audit-failure"})
    runner.write(tmp_path / p["output_root"] / "screening.json", {"variants": [screened]})
    runner.write(tmp_path / p["output_root"] / "generation.json", {"variants": [{"variant_id": "stale"}]})

    report = runner.audit_stage(tmp_path, disjointness_inventory_rows=[])

    assert report["variants"][0]["reason"] == "current-screen-failure"
    assert runner.read(folder / "audit.json")["reason"] == "current-screen-failure"


def test_planimation_collection_retries_transient_failures_serially(tmp_path, monkeypatch):
    attempts = []
    sleeps = []

    def collect(**kwargs):
        attempts.append(kwargs["output"])
        kwargs["output"].mkdir()
        if len(attempts) < 3:
            raise RuntimeError("connection refused")

    monkeypatch.setattr(runner, "collect_task_scenes", collect)
    monkeypatch.setattr(
        "scripts.planimation_phase1_client.preflight_host",
        lambda *_args, **_kwargs: {"reachable": True},
    )
    monkeypatch.setattr(runner.time, "sleep", sleeps.append)
    output = tmp_path / "scenes"

    runner._collect_task_scenes_with_retry(
        root=tmp_path,
        row={},
        profile=tmp_path / "profile.pddl",
        endpoint="http://127.0.0.1:18092",
        output=output,
        catalog={},
    )

    assert len(attempts) == 3
    assert sleeps == [0.25, 0.5]
    assert sorted(path.name for path in tmp_path.glob("scenes-interrupted-*")) == [
        "scenes-interrupted-1",
        "scenes-interrupted-2",
    ]


def test_baseline_published_evidence_validation_is_read_only(tmp_path):
    evaluation_path = tmp_path / "baseline-evaluation.json"
    replay_path = tmp_path / "baseline-independent-replay.json"
    runner.write(evaluation_path, {"outcome": "PASS", "finished": 123.0})
    runner.write(replay_path, {"outcome": "PASS", "episodes_replayed": 1152})
    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (evaluation_path, replay_path)
    }

    baseline_audit.validate_published_reports(
        {"outcome": "PASS"},
        {"outcome": "PASS", "episodes_replayed": 1152},
        evaluation_path,
        replay_path,
    )

    assert {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (evaluation_path, replay_path)
    } == before


def test_baseline_final_stage_does_not_write_published_evidence(tmp_path, monkeypatch):
    evaluation_path = tmp_path / "baseline-evaluation.json"
    replay_path = tmp_path / "baseline-independent-replay.json"
    runner.write(evaluation_path, {"published": True})
    runner.write(replay_path, {"published": True})
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (evaluation_path, replay_path)}
    protocol = {
        "protocol_id": "baseline",
        "panel_id": "panel",
        "modalities": ["text-state"],
        "algorithms": ["bfs"],
        "conditions": ["exact_reference"],
        "logical_bindings": 24,
        "endpoints": ["unused"],
    }
    reports = [
        {
            "modality": "text-state",
            "algorithm": "bfs",
            "arm": "exact_reference",
            "result": {"invariant_valid_success": True, "decision_count": 1, "invalid_operation_count": 0},
            "raw_invalid_outputs_preserved": 0,
        }
        for _ in range(24)
    ]
    attempts = [
        {
            "job_id": f"baseline-{kind}-{worker}",
            "status": "succeeded",
            "branch": "expanded_baseline",
            "gpu_hours": 0.0,
        }
        for kind in ("controls", "models")
        for worker in range(2)
    ]
    monkeypatch.setattr(baseline_audit, "load_context", lambda _config: (protocol, {}, {}))
    monkeypatch.setattr(baseline_audit, "bindings", lambda *_args: list(range(24)))
    monkeypatch.setattr(baseline_audit, "audit_subset", lambda *_args: (reports, []))
    monkeypatch.setattr(
        baseline_audit,
        "read",
        lambda path: {
            "attempts": attempts,
            "allocations_gpu_hours": {"expanded_baseline": 1.0},
        },
    )
    validated = []
    monkeypatch.setattr(
        baseline_audit,
        "validate_published_reports",
        lambda evaluation, replay: validated.append((evaluation, replay)),
    )
    progress = tmp_path / "progress.json"
    monkeypatch.setenv("EXPANDED_PROGRESS_PATH", str(progress))

    assert baseline_audit.main(["final", "--config", str(tmp_path / "protocol.json")]) == 0

    assert validated
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (evaluation_path, replay_path)} == before


def test_probe_selection_uses_hardest_sum_then_task_id_tiebreak():
    p = protocol(Path("."))
    p["algorithms"] = ["bfs", "best_first_width", "best_first_add_w3", "best_first_add_greedy"]
    p["modalities"] = ["text-state", "visual-state", "multimodal-state"]
    tasks = []
    for family in runner.FAMILIES:
        low = task_row(f"z-{family}", family, 3)
        high_z = task_row(f"z-hard-{family}", family, 5)
        high_a = task_row(f"a-hard-{family}", family, 5)
        for row in (low, high_z, high_a):
            row["row"]["reference_costs"] = {
                algorithm: {"decisions": row["row"]["reference_costs"]["bfs"]["decisions"], "expansions": 1}
                for algorithm in p["algorithms"]
            }
        tasks.extend((low, high_z, high_a))
    selected = runner.select_probe_inputs(tasks, p)
    assert len(selected) == 60
    assert {row["variant_id"] for row in selected} == {f"a-hard-{family}" for family in runner.FAMILIES}


def test_probe_finalize_uses_max_times_margin_and_worker_overhead():
    measurements = [
        {
            "call_wall_seconds": seconds,
            "input_tokens": 10,
            "output_tokens": 2,
            "algorithm": "bfs",
            "modality": "text-state",
            "family": "scale-up",
            "batch_size": 1,
        }
        for seconds in (1.0, 2.0, 1.5)
    ]
    report = runner.aggregate_probe(
        measurements,
        [{"worker": 0, "model_load_wall_seconds": 3.0, "model_save_wall_seconds": 2.0}],
        probe_gpu_hours=0.25,
    )
    assert report["per_combo_bounds"]["bfs__text-state"] == {
        "max_observed_call_seconds": 2.0,
        "bound_seconds": 3.0,
        "samples": 3,
    }
    assert report["planned_worker_overhead_seconds"] == 5.0
    assert report["probe_gpu_hours"] == 0.25


def admission_fixture():
    p = protocol(Path("."))
    tasks = [
        task_row("expanded-scale", "scale-up", 1, stratum="expanded"),
        task_row("expanded-p1", "object-renaming", 1, stratum="expanded"),
        task_row("compact-p1", "object-renaming", 1),
        task_row("compact-p3", "name-compression", 1),
    ]
    probe = {
        "per_combo_bounds": {"bfs__text-state": {"bound_seconds": 450.0}},
        "probe_gpu_hours": 0.0,
        "planned_worker_overhead_seconds": 0.0,
    }
    return p, tasks, probe


@pytest.mark.parametrize(
    ("remainder", "recovery", "expected"),
    [(3.0, 0.0, "L0"), (2.0, 1.0, "L1"), (2.0, 0.0, "L2"), (1.5, 0.0, "L3"), (1.0, 0.0, "L4")],
)
def test_admission_ladder_arithmetic(remainder, recovery, expected):
    p, tasks, probe = admission_fixture()
    report = runner.decide_admission(
        tasks,
        probe,
        p,
        branch_spent_gpu_hours=32 - remainder,
        recovery_available_gpu_hours=recovery,
    )
    assert report["decision"] == expected
    assert report["ledger_mutated"] is False
    if expected == "L1":
        assert report["transfer_request"]["executed"] is False
        assert report["transfer_request"]["gpu_hours"] == pytest.approx(0.5)
    else:
        assert report["transfer_request"] is None
    if expected == "L4":
        assert report["outcome"] == "VALID_STOP"


@pytest.mark.parametrize(
    "stage",
    [
        runner.validate_stage,
        runner.generate_stage,
        runner.screen_stage,
        runner.audit_stage,
        runner.freeze_stage,
        runner.probe_inputs_stage,
        runner.probe_finalize_stage,
        runner.admit_stage,
    ],
)
def test_every_cpu_stage_fails_before_work_when_protocol_validation_fails(tmp_path, monkeypatch, stage):
    monkeypatch.setattr(runner, "load_protocol", lambda root: (_ for _ in ()).throw(ValueError("invalid protocol")))
    with pytest.raises(ValueError, match="invalid protocol"):
        stage(tmp_path)


def test_probe_worker_fails_before_gpu_setup_when_protocol_validation_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_protocol", lambda root: (_ for _ in ()).throw(ValueError("invalid protocol")))
    with pytest.raises(ValueError, match="invalid protocol"):
        cli.probe_worker(tmp_path, 0)
