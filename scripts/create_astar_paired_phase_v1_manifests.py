"""Construct the preparatory issue-62 paired A* development freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from examples.planning_benchmark_slice.astar_hmax import HMaxHeuristic  # noqa: E402
from examples.planning_benchmark_slice.astar_landmarks import LandmarkCountHeuristic  # noqa: E402
from examples.planning_benchmark_slice.astar_phase import (  # noqa: E402
    ASTAR_PAIRED_ADAPTERS,
    positive_astar_generation_cap,
    validate_astar_generation_budget,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority  # noqa: E402

_DEFAULT_SOURCE = _REPO_ROOT / "data" / "astar_paired_phase_v1" / "source-task-manifest.jsonl"
_DEFAULT_SOURCE_AUDIT = _REPO_ROOT / "data" / "astar_paired_phase_v1" / "source-audit.json"
_PHASE_ID = "issue-62-astar-paired-development-v1"
_COMPONENTS = ("task", "trace", "corpus", "model", "budget", "analysis")
_MODEL_REVISION = "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
_SELECTION_RULE = (
    "Use the supplied source panel in canonical source-row order with whole semantic-task split isolation; "
    "validate both adapters without executing A* and never use an A* outcome for selection."
)
_BFWS_AUTHORIZATION_PATH = Path("configs/experiments/bfws_phase_authorization_v1.json")
_BFWS_EVIDENCE_PATH = Path("data/bfws_phase_v1/exact-traces/manifests/bfws-expert-traces.json")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, default=_DEFAULT_SOURCE)
    parser.add_argument("--source-audit", type=Path, default=_DEFAULT_SOURCE_AUDIT)
    parser.add_argument("--fixture-contract", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)
    if args.fixture_contract and not args.dry_run:
        parser.error("--fixture-contract is contract-validation-only and requires --dry-run")

    if args.fixture_contract:
        rows = _fixture_rows()
        artifact_root = _REPO_ROOT
        _validated_pairs(rows, artifact_root)
        summary = {
            "pair_count": len(rows),
            "scientific_authorization": False,
            "status": "contract_validation_only",
            "writes": 0,
        }
        print(json.dumps(summary, sort_keys=True), flush=True)
        return 0

    source = args.source_manifest.resolve()
    artifact_root = _REPO_ROOT if source == _DEFAULT_SOURCE.resolve() else source.parent.resolve()
    rows, source_bytes = _jsonl_rows(source)
    source_bindings, source_evidence, generation_budget = _source_audit(
        args.source_audit.resolve(), len(rows), artifact_root
    )
    source_bindings["source_manifest"] = _artifact_binding(source, source_bytes, artifact_root)
    pairs = _validated_pairs(rows, artifact_root)
    _validate_evidence_pairs(pairs, source_evidence)
    _validate_generation_caps(pairs, generation_budget)
    products = _products(
        pairs,
        source_bindings,
        artifact_root,
        source == _DEFAULT_SOURCE.resolve(),
        generation_budget,
    )
    if args.dry_run:
        summary = {
            "pair_count": len(pairs),
            "product_count": len(products),
            "scientific_authorization": False,
            "status": "dry_run_valid_real_source",
            "writes": 0,
        }
        print(json.dumps(summary, sort_keys=True), flush=True)
        return 0
    if args.check:
        for path, payload in products.items():
            if not path.is_file() or path.read_bytes() != payload:
                raise ValueError(f"A* paired product differs from deterministic regeneration: {path}")
        print(json.dumps({"checked": len(products), "status": "byte_identical"}, sort_keys=True), flush=True)
        return 0
    differing = [path for path, payload in products.items() if path.is_file() and path.read_bytes() != payload]
    if differing:
        raise ValueError(f"immutable A* paired v1 product differs; create v2 instead: {differing[0]}")
    missing = [(path, payload) for path, payload in products.items() if not path.is_file()]
    for path, payload in missing:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(json.dumps({"status": "refreshed", "written": len(missing)}, sort_keys=True), flush=True)
    return 0


def _validated_pairs(rows: list[dict[str, Any]], artifact_root: Path) -> list[dict[str, Any]]:
    if not rows:
        raise ValueError("A* paired source manifest is empty")
    started = time.monotonic()
    total = len(rows)
    pairs: list[dict[str, Any]] = []
    identities_by_split: dict[str, str] = {}
    for completed, source in enumerate(rows, start=1):
        pairs.append(_pair_row(source, artifact_root))
        identity = pairs[-1]["semantic_task_identity"]
        split = pairs[-1]["split"]
        if identity in identities_by_split:
            raise ValueError(
                "A* paired source repeats a semantic identity; whole-task split isolation requires uniqueness"
            )
        identities_by_split[identity] = split
        elapsed = time.monotonic() - started
        remaining = 0.0 if completed == total else elapsed / completed * (total - completed)
        print(
            json.dumps(
                {
                    "completed": completed,
                    "elapsed_seconds": round(elapsed, 6),
                    "estimated_remaining_seconds": round(remaining, 6),
                    "total": total,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    pairs.sort(key=lambda row: (row["split"], row["domain_id"], row["difficulty"], row["instance_id"]))
    if len({row["pair_id"] for row in pairs}) != len(pairs):
        raise ValueError("A* paired source repeats a pair binding")
    return pairs


def _pair_row(source: Mapping[str, Any], artifact_root: Path) -> dict[str, Any]:
    expected = {"difficulty", "domain_id", "generation_max_expansions", "instance_id", "split", "task_path"}
    text_fields = expected - {"generation_max_expansions"}
    if (
        set(source) != expected
        or any(not isinstance(source[field], str) or not source[field] for field in text_fields)
        or not positive_astar_generation_cap(source["generation_max_expansions"])
    ):
        raise ValueError("A* paired source row has invalid fields")
    if source["split"] not in {"train", "dev"}:
        raise ValueError("A* paired source split must be train or dev")
    relative = Path(source["task_path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("A* paired task path must be repository-relative")
    task_path = (artifact_root / relative).resolve()
    if not task_path.is_file():
        raise ValueError(f"A* paired task is missing: {relative.as_posix()}")
    task_bytes = task_path.read_bytes()
    try:
        task = json.loads(task_bytes)
    except json.JSONDecodeError as error:
        raise ValueError(f"A* paired task is invalid JSON: {relative.as_posix()}") from error
    if not isinstance(task, dict) or not isinstance(task.get("domain_pddl"), str) or not isinstance(
        task.get("problem_pddl"), str
    ):
        raise ValueError("A* paired task must contain domain_pddl and problem_pddl")
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    HMaxHeuristic(authority)
    LandmarkCountHeuristic(authority)
    identity = authority.semantic_task_identity()
    pair_digest = hashlib.sha256(f"{identity}\0{source['instance_id']}".encode()).hexdigest()
    return {
        "astar_outcome_used_for_selection": False,
        "difficulty": source["difficulty"],
        "domain_id": source["domain_id"],
        "eligible_adapters": list(ASTAR_PAIRED_ADAPTERS),
        "generation_max_expansions": source["generation_max_expansions"],
        "instance_id": source["instance_id"],
        "normalized_domain_hash": _pddl_hash(task["domain_pddl"]),
        "normalized_problem_hash": _pddl_hash(task["problem_pddl"]),
        "pair_id": f"astar-pair-{pair_digest[:24]}",
        "schema_version": "astar_paired_task_row_v1",
        "selection_rule": _SELECTION_RULE,
        "semantic_task_identity": identity,
        "split": source["split"],
        "task_bytes": len(task_bytes),
        "task_path": relative.as_posix(),
        "task_sha256": hashlib.sha256(task_bytes).hexdigest(),
    }


def _products(
    pairs: list[dict[str, Any]],
    source_bindings: dict[str, Any],
    artifact_root: Path,
    default_paths: bool,
    generation_budget: Mapping[str, Any],
) -> dict[Path, bytes]:
    product_root = (
        artifact_root / "configs" / "experiments"
        if default_paths
        else artifact_root / "astar_paired_phase_v1_products"
    )
    component_paths = {
        name: product_root / f"astar-paired-{name}-v1.json" for name in _COMPONENTS
    }
    components = _components(pairs, source_bindings, generation_budget)
    freeze_path = product_root / "astar-paired-freeze-v1.json"
    authorization_path = product_root / "astar-paired-authorization-v1.json"
    freeze = {
        "algorithms": list(ASTAR_PAIRED_ADAPTERS),
        "component_manifests": {
            name: _relative(path, artifact_root) for name, path in component_paths.items()
        },
        "modality": "text-state",
        "parent_issue": 38,
        "phase_id": _PHASE_ID,
        "schema_version": "astar_paired_phase_freeze_v1",
        "source_issue": 62,
    }
    authorization = {
        "authorization_id": "issue-62-astar-paired-authorization-v1",
        "authorized_stages": ["trace_generation", "corpus_release"],
        "contract_id": _PHASE_ID,
        "downstream_issues": [63, 64],
        "efficacy_test_access_authorized": False,
        "freeze_manifest_path": _relative(freeze_path, artifact_root),
        "outcome": "PASS",
        "parent_issue": 38,
        "phase_id": _PHASE_ID,
        "schema_version": "astar_paired_phase_authorization_v1",
        "scientific_completion": False,
        "source_bindings": source_bindings,
        "source_issue": 62,
    }
    return {
        **{component_paths[name]: _canonical_bytes(component) for name, component in components.items()},
        freeze_path: _canonical_bytes(freeze),
        authorization_path: _canonical_bytes(authorization),
    }


def _components(
    pairs: list[dict[str, Any]], source_bindings: dict[str, Any], generation_budget: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    common = {"parent_issue": 38, "phase_id": _PHASE_ID, "source_issue": 62}
    audits = [
        "overlap", "conflict", "leakage", "rejection", "live_parity", "token_overflow"
    ]
    return {
        "task": {
            **common,
            "component": "task",
            "pair_count": len(pairs),
            "pairs": pairs,
            "schema_version": "astar_paired_task_freeze_v1",
            "source_bindings": source_bindings,
            "split_unit": "semantic_task_identity",
        },
        "trace": {
            **common,
            "adapter_specific_counts": ["exact_reference_decision_count", "exact_reference_expansion_count"],
            "algorithms": list(ASTAR_PAIRED_ADAPTERS),
            "component": "trace",
            "controller": "AStarController",
            "goal_test": "popped_frontier_head_world_state",
            "independent_replay_per_adapter": True,
            "pair_binding": "exactly_two_traces_per_pair_on_identical_task_artifact",
            "priority": ["f", "generation_serial"],
            "reopen": "cheaper_path_same_composite_node",
            "schema_version": "astar_paired_trace_freeze_v1",
            "stable_candidate_ordering": True,
            "traces_per_pair": 2,
        },
        "corpus": {
            **common,
            "accepted_delta_limit": 16,
            "bounded_input_schema": "bounded_astar_search_memory_v1",
            "required_audit_results": {name: 0 for name in audits},
            "required_future_parity_audits": {
                "pinned_token_budget_overflow_count": 0,
                "teacher_live_canonical_byte_mismatch_count": 0,
            },
            "byte_identical_regeneration": ["corpus", "curriculum", "split_ledger", "training_projection"],
            "component": "corpus",
            "controls": ["operational", "process", "staged", "shuffled", "mixed_order"],
            "fact_contract": [
                "static_task", "candidate", "pruning", "best_cost", "frontier", "closed", "landmark_progression"
            ],
            "input_token_limit": 7808,
            "message_prefix_serializer": (
                "examples.planning_benchmark_slice.astar_model_input.serialize_astar_message_prefix"
            ),
            "model_input_builder": (
                "examples.planning_benchmark_slice.astar_model_input.build_bounded_astar_model_input"
            ),
            "output_token_limit": 384,
            "projection_policy": "drop_oldest_accepted_deltas_only_preserve_all_required_facts",
            "schema_version": "astar_paired_corpus_freeze_v1",
            "split_unit": "semantic_task_identity",
            "total_token_limit": 8192,
        },
        "model": {
            **common,
            "checkpoint_policy": {
                "final_checkpoint_rollout": True,
                "nonfinal_teacher_forced_diagnostics_only": True,
            },
            "component": "model",
            "evaluation_reference_seeds": [17, 29, 43, 71, 101],
            "library_versions": {
                "accelerate": "1.5.2",
                "peft": "0.17.1",
                "torch": "2.7.1",
                "transformers": "4.57.0",
            },
            "model_revision": _MODEL_REVISION,
            "schema_version": "astar_paired_model_freeze_v1",
            "training_authorized": False,
            "training_seed_variance_authorized": False,
            "training_seeds": [17],
            "training_cells": [
                {"adapter": adapter, "curriculum": curriculum, "training_seed": 17}
                for adapter in ASTAR_PAIRED_ADAPTERS
                for curriculum in ("staged", "shuffled", "mixed_order")
            ],
            "training_cell_rule": "one_distinct_cell_with_single_seed_17",
        },
        "budget": {
            **common,
            "adapter_isolated_cache": True,
            "adapter_cache_key": [
                "model_revision",
                "adapter_id",
                "canonical_input",
                "decoding_config",
                "qualified_precision",
            ],
            "clock": {
                "launch_cutoff_hours": 18,
                "restart_allowed": False,
                "start_policy": "start_once_after_hardware_qualification",
                "total_hours": 20,
            },
            "component": "budget",
            "deterministic_round_scheduling": True,
            "expert_generation_expansion_limit": "source_row.generation_max_expansions",
            "generation_budget": dict(generation_budget),
            "panel_selection": {
                "cheapest_summed_exact_cost_per_domain": True,
                "fallback": {
                    "cost": "sum_of_two_adapter_exact_reference_decision_counts_per_pair",
                    "pairs_per_domain": 1,
                    "tie_break": ["summed_exact_decision_count", "difficulty", "pair_id"],
                    "uses_model_outcomes": False,
                },
                "full_paired_panel_first": True,
                "fallback_outcome_blind": True,
                "outcome_blind": True,
                "preregistered": True,
            },
            "per_adapter_expansion_limit": "matching exact_reference_expansion_count",
            "per_adapter_model_call_limit": "2 * matching exact_reference_decision_count",
            "precision_qualification": ["scalar", "batch", "repeated_batch"],
            "qualification_failure_outcome": "VALID_STOP",
            "qualified_hardware_precision": {
                "hardware": "qualification_recorded_accelerator",
                "inference_dtype": "float32",
            },
            "request_session_round_policy": "one_request_one_session_per_round",
            "schema_version": "astar_paired_budget_freeze_v1",
        },
        "analysis": {
            **common,
            "classification": {
                "ANCESTOR_STOP": ["failed_predecessor"],
                "INVALID": [
                    "pairing_mismatch",
                    "parity_mismatch",
                    "replay_mismatch",
                    "provenance_mismatch",
                ],
                "PASS": ["complete_coverage_and_all_frozen_criteria"],
                "VALID_STOP": ["ordinary_threshold_failure", "ordinary_resource_failure"],
            },
            "component": "analysis",
            "deterministic_acceptance": {
                "mismatch_count": 0,
                "overflow_count": 0,
                "pair_completeness_rate": 1.0,
                "parity_rate": 1.0,
                "rejection_count": 0,
                "replay_rate": 1.0,
            },
            "efficacy_thresholds_authorized": False,
            "metrics": ["paired_adapter", "learned_vs_best_control"],
            "mismatch_outcome": "INVALID",
            "model_efficacy_run_requires_successor_authorization": True,
            "outcomes": {
                "ANCESTOR_STOP": "blocking ancestor",
                "INVALID": "pairing parity replay or provenance mismatch",
                "PASS": "all frozen criteria met",
                "VALID_STOP": "governed non-scientific stop",
            },
            "pair_unit": "complete_pair_whole_semantic_task",
            "partial_coverage_can_satisfy_gate": False,
            "pass_requires_complete_coverage": True,
            "paired_bootstrap": {
                "confidence": 0.95,
                "resamples": 10_000,
                "seed": 1729,
                "unit": "whole_problem_pair",
            },
            "schema_version": "astar_paired_analysis_freeze_v1",
        },
    }


def _fixture_rows() -> list[dict[str, Any]]:
    return [
        {
            "difficulty": difficulty,
            "domain_id": domain,
            "generation_max_expansions": 16,
            "instance_id": f"contract-{index}",
            "split": split,
            "task_path": f"tests/fixtures/planning/{name}",
        }
        for index, (name, domain, difficulty, split) in enumerate(
            (
                ("blocksworld_nontrivial.json", "blocksworld", "easy", "train"),
                ("landmark_progression.json", "landmark-progression", "medium", "dev"),
            )
        )
    ]


def _jsonl_rows(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    if not path.is_file():
        raise FileNotFoundError(f"A* paired real source manifest is absent: {path}")
    payload = path.read_bytes()
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.splitlines(keepends=True), start=1):
        if line == b"\n" or not line.endswith(b"\n"):
            raise ValueError("A* paired source JSONL requires one nonempty canonical object followed by LF")
        raw = line[:-1]
        try:
            row = _strict_json(raw, f"A* paired source line {line_number}")
        except ValueError as error:
            raise ValueError(f"A* paired source line {line_number} is not canonical JSON") from error
        if not isinstance(row, dict):
            raise ValueError("A* paired source manifest rows must be objects")
        if _canonical_bytes(row) != raw:
            raise ValueError(f"A* paired source line {line_number} is not canonical JSON")
        rows.append(row)
    return rows, payload


def _source_audit(
    path: Path,
    source_count: int,
    artifact_root: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"A* paired reviewed source audit is absent: {path}")
    payload = path.read_bytes()
    audit = _strict_json(payload, "A* paired source audit")
    if not isinstance(audit, dict) or _canonical_bytes(audit) != payload:
        raise ValueError("A* paired source audit must be a canonical JSON object")
    expected_keys = {
        "audit_id",
        "efficacy_data",
        "expected_pair_count",
        "expected_source_candidate_count",
        "expected_task_count",
        "generation_budget",
        "generation_budget_basis",
        "panel_purpose",
        "replay_proven",
        "review_status",
        "schema_version",
        "selection_outcome_blind",
        "selection_policy",
        "source_authorization",
        "source_evidence",
    }
    if (
        set(audit) != expected_keys
        or audit.get("schema_version") != "astar_paired_source_audit_v1"
        or not isinstance(audit.get("audit_id"), str)
        or not audit["audit_id"]
        or audit.get("panel_purpose") != "paired_astar_development"
        or audit.get("review_status") != "reviewed"
        or audit.get("replay_proven") is not True
        or audit.get("selection_outcome_blind") is not True
        or audit.get("selection_policy")
        != {
            "astar_outcome_used_for_selection": False,
            "estimated_grounded_operator_ceiling": 200_000,
            "estimated_grounded_operator_formula": "sum(object_count ** action_parameter_count)",
            "required_adapters": ["astar_hmax", "astar_landmark_count"],
            "unsupported_adapter_contract": "exclude",
        }
        or audit.get("efficacy_data") is not False
        or audit.get("generation_budget_basis")
        != "maximum_issue57_exact_bfws_expansion_count_by_source_difficulty"
        or not _audit_count(audit.get("expected_task_count"))
        or not _audit_count(audit.get("expected_pair_count"))
        or not _audit_count(audit.get("expected_source_candidate_count"))
        or audit["expected_source_candidate_count"] < source_count
    ):
        raise ValueError("A* paired source audit does not prove a reviewed replay-proven development source")
    if audit.get("expected_task_count") != source_count or audit.get("expected_pair_count") != source_count:
        raise ValueError("A* paired source audit count does not match the source manifest")
    authorization_path, authorization = _bound_source_artifact(
        audit.get("source_authorization"),
        artifact_root,
        expected_identifier="issue-56-bfws-development-authorization-v1",
        expected_path=_BFWS_AUTHORIZATION_PATH,
        expected_schema="bfws_phase_authorization_v1",
        label="source authorization",
    )
    evidence_path, evidence = _bound_source_artifact(
        audit.get("source_evidence"),
        artifact_root,
        expected_identifier="issue-57-bfws-expert-traces-v1",
        expected_path=_BFWS_EVIDENCE_PATH,
        expected_schema="bfws_expert_trace_generation_v1",
        label="source evidence",
    )
    _validate_bfws_authorization(authorization)
    _validate_bfws_evidence(evidence, audit["expected_source_candidate_count"])
    generation_budget = _validate_generation_budget(audit.get("generation_budget"))
    return {
        "source_audit": _artifact_binding(path, payload, artifact_root),
        "source_authorization": _artifact_binding(
            authorization_path, authorization_path.read_bytes(), artifact_root
        ),
        "source_evidence": _artifact_binding(evidence_path, evidence_path.read_bytes(), artifact_root),
    }, evidence, generation_budget


def _validate_generation_budget(value: object) -> dict[str, Any]:
    return validate_astar_generation_budget(value)


def _validate_generation_caps(
    pairs: Sequence[Mapping[str, Any]], generation_budget: Mapping[str, Any]
) -> None:
    validate_astar_generation_budget(generation_budget, tuple(pairs))


def _bound_source_artifact(
    value: object,
    artifact_root: Path,
    *,
    expected_identifier: str,
    expected_path: Path,
    expected_schema: str,
    label: str,
) -> tuple[Path, dict[str, Any]]:
    if not isinstance(value, dict) or value != {
        "identifier": expected_identifier,
        "path": expected_path.as_posix(),
        "schema_version": expected_schema,
        "sha256": value.get("sha256"),
        "size_bytes": value.get("size_bytes"),
    }:
        raise ValueError(f"A* paired {label} authority identifier, path, or schema is not allowlisted")
    path = (artifact_root / expected_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"A* paired {label} artifact is missing: {path}")
    payload = path.read_bytes()
    if value["sha256"] != hashlib.sha256(payload).hexdigest() or value["size_bytes"] != len(payload):
        raise ValueError(f"A* paired {label} hash or byte size does not match")
    parsed = _strict_json(payload, f"A* paired {label}")
    canonical = _canonical_bytes(parsed)
    if not isinstance(parsed, dict) or payload not in {canonical, canonical + b"\n"}:
        raise ValueError(f"A* paired {label} must be canonical JSON with at most one trailing LF")
    return path, parsed


def _validate_bfws_authorization(value: Mapping[str, Any]) -> None:
    if value != {
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
    }:
        raise ValueError("A* paired source authorization is not the completed issue-56 PASS authority")


def _validate_bfws_evidence(value: Mapping[str, Any], candidate_count: int) -> None:
    traces = value.get("traces")
    coverage = value.get("coverage")
    receipt = value.get("phase_receipt")
    if (
        set(value)
        != {
            "algorithm",
            "coverage",
            "evidence_schema",
            "phase_receipt",
            "schema_version",
            "source_issue",
            "traces",
        }
        or value.get("algorithm") != _bfws_algorithm()
        or value.get("evidence_schema") != "search_episode_evidence_v4"
        or value.get("schema_version") != "bfws_expert_trace_generation_v1"
        or value.get("source_issue") != 57
        or not isinstance(traces, list)
        or len(traces) != candidate_count
        or not isinstance(coverage, dict)
        or set(coverage)
        != {
            "exact_reference_decision_count",
            "instance_count",
            "replay_verified_instance_count",
            "split_counts",
            "stratum_count",
        }
        or not isinstance(coverage.get("exact_reference_decision_count"), int)
        or isinstance(coverage.get("exact_reference_decision_count"), bool)
        or coverage["exact_reference_decision_count"] <= 0
        or coverage.get("instance_count") != candidate_count
        or coverage.get("replay_verified_instance_count") != candidate_count
        or not isinstance(receipt, dict)
        or receipt.get("authorization_id") != "issue-56-bfws-development-authorization-v1"
        or receipt.get("phase_id") != "issue-56-bfws-development-v1"
        or receipt.get("stage") != "trace_generation"
        or receipt.get("outcome") != "PASS"
    ):
        raise ValueError("A* paired source evidence is not a replay-proven issue-57 BFWS trace manifest")


def _validate_evidence_pairs(pairs: list[dict[str, Any]], evidence: Mapping[str, Any]) -> None:
    expected = {
        (
            row["domain_id"],
            row["difficulty"],
            row["instance_id"],
            row["semantic_task_identity"],
            row["split"],
        )
        for row in pairs
    }
    observed: set[tuple[object, ...]] = set()
    for trace in evidence["traces"]:
        if (
            not isinstance(trace, dict)
            or trace.get("algorithm") != "best_first_width"
            or trace.get("variant") != "full_bfws_goal_count"
            or trace.get("trace_scope") != "complete_exact_bfws_episode"
            or not isinstance(trace.get("source"), dict)
            or trace["source"].get("split") != trace.get("split")
        ):
            raise ValueError("A* paired source evidence contains an invalid trace entry")
        observed.add(
            (
                trace.get("domain_id"),
                trace.get("difficulty"),
                trace.get("instance_id"),
                trace.get("semantic_task_identity"),
                trace.get("split"),
            )
        )
    if not expected <= observed or len(observed) != len(evidence["traces"]):
        raise ValueError("A* paired source task identities do not match replay-proven evidence")


def _audit_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _artifact_binding(path: Path, payload: bytes, artifact_root: Path) -> dict[str, Any]:
    return {
        "path": _relative(path, artifact_root),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def _strict_json(payload: bytes, label: str) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"{label} has duplicate JSON key: {key}")
            value[key] = item
        return value

    def reject_constant(constant: str) -> None:
        raise ValueError(f"{label} contains non-finite JSON constant: {constant}")

    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=object_pairs, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid UTF-8 JSON") from error


def _bfws_algorithm() -> dict[str, Any]:
    return {
        "high_novelty_policy": "enqueue",
        "identifier": "best_first_width",
        "novelty_partition": "unachieved_goal_count",
        "novelty_precision": 2,
        "priority": ["novelty_bucket", "unachieved_goal_count", "path_depth", "generation_serial"],
        "recovery_policy": "prohibited",
        "variant": "full_bfws_goal_count",
    }


def _pddl_hash(value: str) -> str:
    return hashlib.sha256(" ".join(value.split()).encode()).hexdigest()


def _relative(path: Path, artifact_root: Path) -> str:
    return path.resolve().relative_to(artifact_root.resolve()).as_posix()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


if __name__ == "__main__":
    raise SystemExit(main())
