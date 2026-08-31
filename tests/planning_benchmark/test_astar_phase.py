from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.astar_phase import (
    AStarPairedPhaseGateError,
    load_astar_paired_phase_gate,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from scripts.create_astar_paired_phase_v1_manifests import main

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "planning"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _synthetic_source(tmp_path: Path) -> tuple[Path, Path]:
    tasks = tmp_path / "tasks"
    tasks.mkdir(exist_ok=True)
    rows = []
    for index, (name, split) in enumerate(
        (("blocksworld_nontrivial.json", "train"), ("landmark_progression.json", "dev"))
    ):
        target = tasks / name
        target.write_bytes((FIXTURES / name).read_bytes())
        rows.append(
            {
                "difficulty": "easy" if index == 0 else "medium",
                "domain_id": "blocksworld" if index == 0 else "landmark-progression",
                "generation_max_expansions": 16,
                "instance_id": f"paired-{index}",
                "split": split,
                "task_path": f"tasks/{name}",
            }
        )
    source = tmp_path / "source-task-manifest.jsonl"
    source.write_bytes(b"".join(_canonical(row) + b"\n" for row in rows))
    authority_path = tmp_path / "configs" / "experiments" / "bfws_phase_authorization_v1.json"
    authority_path.parent.mkdir(parents=True, exist_ok=True)
    authority_path.write_bytes(
        _canonical(
            {
                "authorization_id": "issue-56-bfws-development-authorization-v1",
                "authorized_stages": [
                    "trace_generation",
                    "corpus_release",
                    "process_sft_training",
                    "development_references",
                    "development_structural_gate",
                ],
                "contract_id": "issue-56-bfws-development-v1",
                "downstream_issues": [57, 58, 59],
                "efficacy_test_access_authorized": False,
                "freeze_manifest_path": "configs/experiments/bfws_phase_freeze_v1.json",
                "outcome": "PASS",
                "parent_issue": 38,
                "phase_id": "issue-56-bfws-development-v1",
                "schema_version": "bfws_phase_authorization_v1",
                "scientific_completion": False,
                "source_issue": 56,
            }
        )
    )
    traces = []
    for row in rows:
        task = json.loads((tmp_path / row["task_path"]).read_bytes())
        identity = PDDLStateAuthority.from_pddl(
            task["domain_pddl"], task["problem_pddl"]
        ).semantic_task_identity()
        traces.append(
            {
                "algorithm": "best_first_width",
                "difficulty": row["difficulty"],
                "domain_id": row["domain_id"],
                "instance_id": row["instance_id"],
                "semantic_task_identity": identity,
                "source": {"split": row["split"]},
                "split": row["split"],
                "trace_scope": "complete_exact_bfws_episode",
                "variant": "full_bfws_goal_count",
            }
        )
    evidence_path = (
        tmp_path / "data" / "bfws_phase_v1" / "exact-traces" / "manifests" / "bfws-expert-traces.json"
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_bytes(
        _canonical(
            {
                "algorithm": {
                    "high_novelty_policy": "enqueue",
                    "identifier": "best_first_width",
                    "novelty_partition": "unachieved_goal_count",
                    "novelty_precision": 2,
                    "priority": [
                        "novelty_bucket",
                        "unachieved_goal_count",
                        "path_depth",
                        "generation_serial",
                    ],
                    "recovery_policy": "prohibited",
                    "variant": "full_bfws_goal_count",
                },
                "coverage": {
                    "exact_reference_decision_count": 2,
                    "instance_count": len(traces),
                    "replay_verified_instance_count": len(traces),
                    "split_counts": {"dev": 1, "train": 1},
                    "stratum_count": 2,
                },
                "evidence_schema": "search_episode_evidence_v4",
                "phase_receipt": {
                    "authorization_id": "issue-56-bfws-development-authorization-v1",
                    "outcome": "PASS",
                    "phase_id": "issue-56-bfws-development-v1",
                    "stage": "trace_generation",
                },
                "schema_version": "bfws_expert_trace_generation_v1",
                "source_issue": 57,
                "traces": traces,
            }
        )
    )

    def binding(path: Path, identifier: str, schema_version: str) -> dict[str, object]:
        payload = path.read_bytes()
        return {
            "identifier": identifier,
            "path": path.relative_to(tmp_path).as_posix(),
            "schema_version": schema_version,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }

    audit = tmp_path / "source-audit.json"
    audit.write_bytes(
        _canonical(
            {
                "audit_id": "reviewed-synthetic-source-v1",
                "efficacy_data": False,
                "expected_pair_count": len(rows),
                "expected_task_count": len(rows),
                "generation_budget": {
                    "adapters": ["astar_hmax", "astar_landmark_count"],
                    "decision_outcome_blind": True,
                    "frozen_before_astar_execution": True,
                    "max_expansions_by_difficulty": {"easy": 16, "hard": 16, "medium": 16},
                    "policy": "shared_ceiling_by_development_difficulty",
                    "task_specific_overrides_allowed": False,
                },
                "panel_purpose": "paired_astar_development",
                "replay_proven": True,
                "review_status": "reviewed",
                "schema_version": "astar_paired_source_audit_v1",
                "selection_outcome_blind": True,
                "source_authorization": binding(
                    authority_path,
                    "issue-56-bfws-development-authorization-v1",
                    "bfws_phase_authorization_v1",
                ),
                "source_evidence": binding(
                    evidence_path,
                    "issue-57-bfws-expert-traces-v1",
                    "bfws_expert_trace_generation_v1",
                ),
            }
        )
    )
    return source, audit


def _run_args(source: Path, audit: Path, mode: str) -> list[str]:
    return ["--source-manifest", str(source), "--source-audit", str(audit), mode]


def _products(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "astar_paired_phase_v1_products"
    return root, root / "astar-paired-freeze-v1.json", root / "astar-paired-authorization-v1.json"


def test_fixture_contract_dry_run_prints_progress_and_never_writes(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_write(*_args, **_kwargs):
        raise AssertionError("fixture contract attempted to write")

    monkeypatch.setattr(Path, "write_bytes", forbidden_write)
    assert main(["--fixture-contract", "--dry-run"]) == 0
    output = capsys.readouterr().out
    progress = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    assert progress
    assert all(
        {"completed", "total", "elapsed_seconds", "estimated_remaining_seconds"} <= row.keys()
        for row in progress[:-1]
    )
    assert progress[-1]["status"] == "contract_validation_only"
    assert progress[-1]["scientific_authorization"] is False


def test_fixture_contract_direct_script_execution_uses_this_checkout() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "create_astar_paired_phase_v1_manifests.py"),
            "--fixture-contract",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    output = [json.loads(line) for line in completed.stdout.splitlines()]
    assert output[:-1]
    assert all(
        {"completed", "total", "elapsed_seconds", "estimated_remaining_seconds"} <= row.keys()
        for row in output[:-1]
    )
    assert output[-1]["status"] == "contract_validation_only"
    assert output[-1]["scientific_authorization"] is False


def test_real_products_regenerate_and_gate_pair_bindings(tmp_path: Path) -> None:
    source, audit = _synthetic_source(tmp_path)
    assert main(_run_args(source, audit, "--refresh")) == 0
    root, freeze, authorization = _products(tmp_path)
    original = {path.name: path.read_bytes() for path in root.iterdir()}
    assert main(_run_args(source, audit, "--check")) == 0
    assert {path.name: path.read_bytes() for path in root.iterdir()} == original

    gate = load_astar_paired_phase_gate(freeze, authorization, repo_root=tmp_path)
    assert gate.phase_id == "issue-62-astar-paired-development-v1"
    assert set(gate.components) == {"task", "trace", "corpus", "model", "budget", "analysis"}
    for row in gate.components["task"]["pairs"]:
        assert row["eligible_adapters"] == ["astar_hmax", "astar_landmark_count"]
        assert row["astar_outcome_used_for_selection"] is False
        assert row["pair_id"]
    assert gate.receipt(stage="trace_generation")["outcome"] == "PASS"
    assert gate.receipt(stage="corpus_release")["scientific_completion"] is False


def test_gate_rejects_swapped_hash_task_and_split_drift(tmp_path: Path) -> None:
    source, audit = _synthetic_source(tmp_path)
    main(_run_args(source, audit, "--refresh"))
    root, freeze_path, authorization = _products(tmp_path)
    freeze = json.loads(freeze_path.read_bytes())

    swapped = deepcopy(freeze)
    swapped["component_manifests"]["task"], swapped["component_manifests"]["trace"] = (
        swapped["component_manifests"]["trace"],
        swapped["component_manifests"]["task"],
    )
    swapped_path = root / "swapped.json"
    swapped_path.write_bytes(_canonical(swapped))
    with pytest.raises(AStarPairedPhaseGateError, match="component"):
        load_astar_paired_phase_gate(swapped_path, authorization, repo_root=tmp_path)

    task_path = root / "astar-paired-task-v1.json"
    original_task_bytes = task_path.read_bytes()
    task = json.loads(original_task_bytes)
    task["pairs"][0]["task_sha256"] = "0" * 64
    task_path.write_bytes(_canonical(task))
    with pytest.raises(AStarPairedPhaseGateError, match=r"hash|task"):
        load_astar_paired_phase_gate(freeze_path, authorization, repo_root=tmp_path)

    task_path.write_bytes(original_task_bytes)
    task = json.loads(task_path.read_bytes())
    task["pairs"][1]["semantic_task_identity"] = task["pairs"][0]["semantic_task_identity"]
    task_path.write_bytes(_canonical(task))
    with pytest.raises(AStarPairedPhaseGateError, match=r"split|identity"):
        load_astar_paired_phase_gate(freeze_path, authorization, repo_root=tmp_path)

    task_path.write_bytes(original_task_bytes)
    (tmp_path / "tasks" / "blocksworld_nontrivial.json").write_text("{}", encoding="utf-8")
    with pytest.raises(AStarPairedPhaseGateError, match="task"):
        load_astar_paired_phase_gate(freeze_path, authorization, repo_root=tmp_path)


def test_gate_freezes_model_budget_analysis_and_narrow_authorization(tmp_path: Path) -> None:
    source, audit = _synthetic_source(tmp_path)
    main(_run_args(source, audit, "--refresh"))
    _root, freeze, authorization = _products(tmp_path)
    gate = load_astar_paired_phase_gate(freeze, authorization, repo_root=tmp_path)

    with pytest.raises(AStarPairedPhaseGateError, match="not authorized"):
        gate.require_run(stage="training", contract_id=gate.phase_id)
    with pytest.raises(AStarPairedPhaseGateError, match="not authorized"):
        gate.require_run(stage="model_rollout", contract_id=gate.phase_id)
    with pytest.raises(AStarPairedPhaseGateError, match="not authorized"):
        gate.require_run(stage="efficacy_test", contract_id=gate.phase_id)
    with pytest.raises(AStarPairedPhaseGateError, match="contract_id"):
        gate.require_run(stage="trace_generation", contract_id="wrong")

    model = gate.components["model"]
    assert model["training_seeds"] == [17]
    assert model["training_seed_variance_authorized"] is False
    assert model["checkpoint_policy"] == {
        "final_checkpoint_rollout": True,
        "nonfinal_teacher_forced_diagnostics_only": True,
    }
    assert model["evaluation_reference_seeds"] == [17, 29, 43, 71, 101]
    assert model["library_versions"] == {
        "accelerate": "1.5.2",
        "peft": "0.17.1",
        "torch": "2.7.1",
        "transformers": "4.57.0",
    }
    assert model["training_cell_rule"] == "one_distinct_cell_with_single_seed_17"
    assert model["training_cells"] == [
        {"adapter": adapter, "curriculum": curriculum, "training_seed": 17}
        for adapter in ("astar_hmax", "astar_landmark_count")
        for curriculum in ("staged", "shuffled", "mixed_order")
    ]

    budget = gate.components["budget"]
    assert budget["per_adapter_model_call_limit"] == "2 * matching exact_reference_decision_count"
    assert budget["per_adapter_expansion_limit"] == "matching exact_reference_expansion_count"
    assert budget["expert_generation_expansion_limit"] == "source_row.generation_max_expansions"
    assert budget["generation_budget"]["max_expansions_by_difficulty"] == {
        "easy": 16,
        "hard": 16,
        "medium": 16,
    }
    assert budget["panel_selection"]["outcome_blind"] is True
    assert budget["panel_selection"]["full_paired_panel_first"] is True
    assert budget["precision_qualification"] == ["scalar", "batch", "repeated_batch"]
    assert budget["qualified_hardware_precision"] == {
        "hardware": "qualification_recorded_accelerator",
        "inference_dtype": "float32",
    }
    assert budget["adapter_cache_key"] == [
        "model_revision",
        "adapter_id",
        "canonical_input",
        "decoding_config",
        "qualified_precision",
    ]
    assert budget["clock"]["start_policy"] == "start_once_after_hardware_qualification"
    assert budget["clock"]["restart_allowed"] is False
    assert budget["qualification_failure_outcome"] == "VALID_STOP"
    assert budget["panel_selection"]["fallback_outcome_blind"] is True
    assert budget["panel_selection"]["fallback"] == {
        "cost": "sum_of_two_adapter_exact_reference_decision_counts_per_pair",
        "pairs_per_domain": 1,
        "tie_break": ["summed_exact_decision_count", "difficulty", "pair_id"],
        "uses_model_outcomes": False,
    }

    analysis = gate.components["analysis"]
    assert set(analysis["outcomes"]) == {"PASS", "VALID_STOP", "INVALID", "ANCESTOR_STOP"}
    assert analysis["partial_coverage_can_satisfy_gate"] is False
    assert analysis["pass_requires_complete_coverage"] is True
    assert analysis["mismatch_outcome"] == "INVALID"
    assert analysis["classification"] == {
        "ANCESTOR_STOP": ["failed_predecessor"],
        "INVALID": ["pairing_mismatch", "parity_mismatch", "replay_mismatch", "provenance_mismatch"],
        "PASS": ["complete_coverage_and_all_frozen_criteria"],
        "VALID_STOP": ["ordinary_threshold_failure", "ordinary_resource_failure"],
    }
    assert analysis["paired_bootstrap"] == {
        "confidence": 0.95,
        "resamples": 10000,
        "seed": 1729,
        "unit": "whole_problem_pair",
    }
    assert analysis["efficacy_thresholds_authorized"] is False
    assert analysis["model_efficacy_run_requires_successor_authorization"] is True
    assert analysis["deterministic_acceptance"] == {
        "mismatch_count": 0,
        "overflow_count": 0,
        "pair_completeness_rate": 1.0,
        "parity_rate": 1.0,
        "rejection_count": 0,
        "replay_rate": 1.0,
    }
    corpus = gate.components["corpus"]
    assert corpus["bounded_input_schema"] == "bounded_astar_search_memory_v1"
    assert corpus["model_input_builder"].endswith(".build_bounded_astar_model_input")
    assert corpus["message_prefix_serializer"].endswith(".serialize_astar_message_prefix")
    assert gate.components["corpus"]["required_audit_results"] == {
        "conflict": 0,
        "leakage": 0,
        "live_parity": 0,
        "overlap": 0,
        "rejection": 0,
        "token_overflow": 0,
    }
    assert gate.authorization == {
        "authorization_id": "issue-62-astar-paired-authorization-v1",
        "authorized_stages": ["trace_generation", "corpus_release"],
        "contract_id": gate.phase_id,
        "downstream_issues": [63, 64],
        "efficacy_test_access_authorized": False,
        "freeze_manifest_path": "astar_paired_phase_v1_products/astar-paired-freeze-v1.json",
        "outcome": "PASS",
        "parent_issue": 38,
        "phase_id": gate.phase_id,
        "schema_version": "astar_paired_phase_authorization_v1",
        "scientific_completion": False,
        "source_bindings": gate.components["task"]["source_bindings"],
        "source_issue": 62,
    }


def test_real_source_requires_matching_reviewed_audit_before_writes(tmp_path: Path) -> None:
    source, audit = _synthetic_source(tmp_path)
    audit.unlink()
    with pytest.raises((FileNotFoundError, ValueError), match="audit"):
        main(_run_args(source, audit, "--refresh"))
    assert not _products(tmp_path)[0].exists()


def test_source_generation_budget_requires_positive_shared_difficulty_cap(tmp_path: Path) -> None:
    source, audit = _synthetic_source(tmp_path)
    rows = [json.loads(line) for line in source.read_bytes().splitlines()]
    rows[0]["generation_max_expansions"] = 15
    source.write_bytes(b"".join(_canonical(row) + b"\n" for row in rows))
    with pytest.raises(ValueError, match="difficulty cap"):
        main(_run_args(source, audit, "--refresh"))
    assert not _products(tmp_path)[0].exists()

    source, audit = _synthetic_source(tmp_path)
    payload = json.loads(audit.read_bytes())
    payload["generation_budget"]["max_expansions_by_difficulty"]["easy"] = 0
    audit.write_bytes(_canonical(payload))
    with pytest.raises(ValueError, match="positive integers"):
        main(_run_args(source, audit, "--refresh"))

    _source, audit = _synthetic_source(tmp_path)
    payload = json.loads(audit.read_bytes())
    payload["expected_pair_count"] = 3
    audit.write_bytes(_canonical(payload))
    with pytest.raises(ValueError, match="count"):
        main(_run_args(source, audit, "--refresh"))
    assert not _products(tmp_path)[0].exists()


@pytest.mark.parametrize("invalid", ["invalid_split", "duplicate_identity"])
def test_generator_rejects_invalid_splits_and_duplicate_semantic_tasks(
    tmp_path: Path,
    invalid: str,
) -> None:
    source, audit = _synthetic_source(tmp_path)
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    if invalid == "invalid_split":
        rows[0]["split"] = "test"
        expected = "split"
    else:
        rows[1]["task_path"] = rows[0]["task_path"]
        rows[1]["instance_id"] = "different-instance"
        expected = "identity"
    source.write_bytes(b"".join(_canonical(row) + b"\n" for row in rows))
    with pytest.raises(ValueError, match=expected):
        main(_run_args(source, audit, "--refresh"))
    assert not _products(tmp_path)[0].exists()


def test_gate_rejects_source_audit_and_strengthened_contract_drift(tmp_path: Path) -> None:
    source, audit = _synthetic_source(tmp_path)
    main(_run_args(source, audit, "--refresh"))
    root, freeze, authorization = _products(tmp_path)
    task_path = root / "astar-paired-task-v1.json"
    original_task_bytes = task_path.read_bytes()
    task = json.loads(original_task_bytes)
    task["source_bindings"]["source_audit"]["sha256"] = "0" * 64
    task_path.write_bytes(_canonical(task))
    with pytest.raises(AStarPairedPhaseGateError, match="audit"):
        load_astar_paired_phase_gate(freeze, authorization, repo_root=tmp_path)

    task_path.write_bytes(original_task_bytes)
    budget_path = root / "astar-paired-budget-v1.json"
    budget = json.loads(budget_path.read_bytes())
    budget["clock"]["restart_allowed"] = True
    budget_path.write_bytes(_canonical(budget))
    with pytest.raises(AStarPairedPhaseGateError, match="budget"):
        load_astar_paired_phase_gate(freeze, authorization, repo_root=tmp_path)


@pytest.mark.parametrize("variant", ["pretty", "duplicate_key", "non_finite"])
def test_cli_rejects_noncanonical_source_jsonl_before_products(tmp_path: Path, variant: str) -> None:
    source, audit = _synthetic_source(tmp_path)
    rows = source.read_bytes().splitlines()
    first = json.loads(rows[0])
    if variant == "pretty":
        rows[0] = json.dumps(first, indent=2).encode()
    elif variant == "duplicate_key":
        canonical = _canonical(first).decode()
        rows[0] = canonical[:-1].encode() + b',"split":"train"}'
    else:
        rows[0] = _canonical(first).replace(b'"difficulty":"easy"', b'"difficulty":NaN')
    source.write_bytes(b"\n".join(rows) + b"\n")
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "create_astar_paired_phase_v1_manifests.py"),
            "--source-manifest",
            str(source),
            "--source-audit",
            str(audit),
            "--refresh",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "canonical" in completed.stderr or "duplicate" in completed.stderr or "non-finite" in completed.stderr
    assert not _products(tmp_path)[0].exists()


@pytest.mark.parametrize(
    "drift",
    ["arbitrary_identifier", "wrong_hash", "wrong_outcome", "missing_evidence", "mismatched_task"],
)
def test_real_source_requires_mechanical_immutable_bfws_authority(
    tmp_path: Path,
    drift: str,
) -> None:
    source, audit_path = _synthetic_source(tmp_path)
    audit = json.loads(audit_path.read_bytes())
    authority_path = tmp_path / audit["source_authorization"]["path"]
    evidence_path = tmp_path / audit["source_evidence"]["path"]
    if drift == "arbitrary_identifier":
        audit["source_authorization"]["identifier"] = "self-authored"
    elif drift == "wrong_hash":
        audit["source_evidence"]["sha256"] = "0" * 64
    elif drift == "wrong_outcome":
        authority = json.loads(authority_path.read_bytes())
        authority["outcome"] = "VALID_STOP"
        authority_path.write_bytes(_canonical(authority))
        payload = authority_path.read_bytes()
        audit["source_authorization"]["sha256"] = hashlib.sha256(payload).hexdigest()
        audit["source_authorization"]["size_bytes"] = len(payload)
    elif drift == "missing_evidence":
        evidence_path.unlink()
    else:
        evidence = json.loads(evidence_path.read_bytes())
        evidence["traces"][0]["semantic_task_identity"] = "not-the-task"
        evidence_path.write_bytes(_canonical(evidence))
        payload = evidence_path.read_bytes()
        audit["source_evidence"]["sha256"] = hashlib.sha256(payload).hexdigest()
        audit["source_evidence"]["size_bytes"] = len(payload)
    audit_path.write_bytes(_canonical(audit))
    with pytest.raises((FileNotFoundError, ValueError), match=r"authority|authorization|evidence|task"):
        main(_run_args(source, audit_path, "--refresh"))
    assert not _products(tmp_path)[0].exists()


def test_refresh_never_replaces_a_different_v1_product(tmp_path: Path) -> None:
    source, audit = _synthetic_source(tmp_path)
    main(_run_args(source, audit, "--refresh"))
    assert main(_run_args(source, audit, "--refresh")) == 0
    root, freeze, _authorization = _products(tmp_path)
    changed = json.loads(freeze.read_bytes())
    changed["modality"] = "changed"
    changed_bytes = _canonical(changed)
    freeze.write_bytes(changed_bytes)
    with pytest.raises(ValueError, match="immutable"):
        main(_run_args(source, audit, "--refresh"))
    assert freeze.read_bytes() == changed_bytes
    assert root.exists()
