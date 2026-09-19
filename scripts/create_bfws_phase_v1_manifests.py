"""Freeze the replay-proven BFWS development phase authorized by issue 56."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority

_REPO_ROOT = Path(__file__).resolve().parents[1]
_QUALIFICATION_ROOT = _REPO_ROOT / "outputs" / "bfws2_curriculum_qualification"
_DATA_ROOT = _REPO_ROOT / "data" / "bfws_phase_v1"
_QUALIFIED = _DATA_ROOT / "qualified-solved-manifest.jsonl"
_DEVELOPMENT = _DATA_ROOT / "development-manifest.jsonl"
_FRESH_TEST = _DATA_ROOT / "fresh-test-manifest.jsonl"
_REPORT = _DATA_ROOT / "qualification-report.json"
_SOURCE_MANIFEST = _REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl"
_CONFIG_ROOT = _REPO_ROOT / "configs" / "experiments"
_FREEZE = _CONFIG_ROOT / "bfws_phase_freeze_v1.json"
_AUTHORIZATION = _CONFIG_ROOT / "bfws_phase_authorization_v1.json"
_PHASE_ID = "issue-56-bfws-development-v1"
_MODEL_REVISION = "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
_SEEDS = [17, 29, 43, 71, 101]
_COMPONENT_PATHS = {
    name: _CONFIG_ROOT / f"bfws_phase_{name}_v1.json"
    for name in ("trace", "corpus", "training", "reference", "threshold", "stop")
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification-root", type=Path, default=_QUALIFICATION_ROOT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="validate inputs and print the frozen plan")
    mode.add_argument("--check", action="store_true", help="require byte-identical committed products")
    mode.add_argument("--refresh", action="store_true", help="replace only the deterministic freeze products")
    args = parser.parse_args(argv)

    print("[1/4] Reading the replay-proven BFWS qualification ledger", flush=True)
    products, summary = _build_products(args.qualification_root.resolve())
    print(
        "[2/4] Selected "
        f"{summary['selected_instance_count']} tasks across {summary['selected_stratum_count']} strata "
        f"({summary['selected_exact_decision_count']} exact decisions)",
        flush=True,
    )
    print(
        "[3/4] Validated train/dev isolation, excluded former-test rows, and froze 45 fresh test tasks",
        flush=True,
    )

    if args.dry_run:
        print("[4/4] Dry run complete; no files written", flush=True)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.check:
        for path, payload in products.items():
            if not path.is_file() or path.read_bytes() != payload:
                raise ValueError(f"committed BFWS freeze differs from deterministic regeneration: {_relative(path)}")
        print("[4/4] All committed products regenerate byte-identically", flush=True)
        return 0

    existing = [path for path in products if path.exists()]
    if existing and not args.refresh:
        raise FileExistsError(f"BFWS freeze products already exist: {_relative(existing[0])}")
    for path, payload in products.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(f"[4/4] Wrote {len(products)} frozen products", flush=True)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _build_products(qualification_root: Path) -> tuple[dict[Path, bytes], dict[str, int]]:
    result_rows = _latest_results(qualification_root / "instance-results.jsonl")
    source_rows = {row["instance_id"]: row for row in _jsonl_objects(qualification_root / "solved-manifest.jsonl")}
    solved_results = {instance_id: row for instance_id, row in result_rows.items() if row["status"] == "solved"}
    if set(solved_results) != set(source_rows):
        raise ValueError("BFWS solved manifest differs from latest replay-proven results")

    qualified_rows = [
        _qualified_row(source_rows[instance_id], result) for instance_id, result in sorted(solved_results.items())
    ]
    status_counts = Counter(row["status"] for row in result_rows.values())
    source_split_counts = Counter(row["source_split"] for row in qualified_rows)
    if status_counts != Counter(
        {"solved": 3_186, "expansion_limit": 1_304, "timeout": 172, "frontier_exhausted": 16}
    ) or source_split_counts != Counter({"train": 2_905, "test": 281}):
        raise ValueError("BFWS qualification counts differ from the completed issue-55 result")

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in qualified_rows:
        if row["source_split"] == "train" and row["exact_reference_decision_count"] > 0:
            grouped[(row["domain_id"], row["difficulty"])].append(row)
    selected: list[dict[str, Any]] = []
    for (_domain_id, _difficulty), rows in sorted(grouped.items()):
        if len(rows) < 3:
            continue
        ordered = sorted(rows, key=lambda row: (row["normalized_problem_hash"], row["instance_id"]))
        distinct: list[tuple[dict[str, Any], str]] = []
        seen_identities: set[str] = set()
        for row in ordered:
            authority = PDDLStateAuthority.from_pddl(
                (_REPO_ROOT / row["domain_path"]).read_text(encoding="utf-8"),
                (_REPO_ROOT / row["problem_path"]).read_text(encoding="utf-8"),
            )
            identity = authority.semantic_task_identity()
            if identity in seen_identities:
                continue
            _replay_selected_plan(authority, row)
            seen_identities.add(identity)
            distinct.append((row, identity))
            if len(distinct) == 3:
                break
        if len(distinct) < 3:
            continue
        for selection_rank, (split, (row, identity)) in enumerate(zip(("train", "train", "dev"), distinct, strict=True)):
            selected.append(
                {
                    **row,
                    "schema_version": "bfws_development_instance_v1",
                    "selection_rank": selection_rank,
                    "semantic_task_identity": identity,
                    "split": split,
                }
            )

    identities_by_split = {
        split: {row["semantic_task_identity"] for row in selected if row["split"] == split} for split in ("train", "dev")
    }
    selected_counts = Counter(row["split"] for row in selected)
    strata = {(row["domain_id"], row["difficulty"]) for row in selected}
    if (
        len(selected) != 105
        or selected_counts != Counter({"train": 70, "dev": 35})
        or len(strata) != 35
        or identities_by_split["train"] & identities_by_split["dev"]
        or any(row["source_split"] != "train" for row in selected)
    ):
        raise ValueError("BFWS development selection is not the frozen isolated 35-stratum panel")

    fresh_test = _select_fresh_test(identities_by_split["train"] | identities_by_split["dev"])

    selected.sort(
        key=lambda row: (
            _difficulty_index(row["difficulty"]),
            row["domain_id"],
            row["split"],
            row["instance_id"],
        )
    )
    selected_decisions = sum(row["exact_reference_decision_count"] for row in selected)
    selected_expansions = sum(row["exact_reference_expansion_count"] for row in selected)
    report = {
        "algorithm": "best_first_width",
        "excluded_former_test_instance_count": 281,
        "fresh_held_out_test": {
            "access_authorized": False,
            "bfws_qualification_accessed": False,
            "instance_count": len(fresh_test),
            "manifest_path": _relative(_FRESH_TEST),
            "source_split": "dev",
            "status": "frozen_unaccessed",
        },
        "phase_id": _PHASE_ID,
        "qualification_commit": "dbc8245",
        "qualification_instance_count": 4_678,
        "qualification_status_counts": dict(sorted(status_counts.items())),
        "schema_version": "bfws_development_qualification_report_v1",
        "selected_exact_decision_count": selected_decisions,
        "selected_exact_expansion_count": selected_expansions,
        "selected_instance_count": len(selected),
        "selected_instance_count_by_split": dict(sorted(selected_counts.items())),
        "selected_manifest_path": _relative(_DEVELOPMENT),
        "selected_plan_replay_count": len(selected),
        "selected_stratum_count": len(strata),
        "selection_rule": (
            "For every domain-by-source-difficulty stratum with at least three nontrivial replay-proven "
            "semantically distinct source-train solutions, order by normalized_problem_hash then "
            "instance_id; assign the first two distinct tasks to train and the third to dev."
        ),
        "solved_instance_count": len(qualified_rows),
        "solved_instance_count_by_source_split": dict(sorted(source_split_counts.items())),
        "solved_manifest_path": _relative(_QUALIFIED),
        "variant": "full_bfws_goal_count",
    }
    components = _component_manifests(report)
    freeze = {
        "algorithm": "best_first_width",
        "component_manifests": {name: _relative(path) for name, path in _COMPONENT_PATHS.items()},
        "modality": "text-state",
        "parent_issue": 38,
        "phase_id": _PHASE_ID,
        "schema_version": "bfws_phase_freeze_v1",
        "source_issue": 56,
        "variant": "full_bfws_goal_count",
    }
    authorization = {
        "authorization_id": "issue-56-bfws-development-authorization-v1",
        "authorized_stages": [
            "trace_generation",
            "corpus_release",
            "process_sft_training",
            "development_references",
            "development_structural_gate",
        ],
        "contract_id": _PHASE_ID,
        "downstream_issues": [57, 58, 59],
        "efficacy_test_access_authorized": False,
        "freeze_manifest_path": _relative(_FREEZE),
        "outcome": "PASS",
        "parent_issue": 38,
        "phase_id": _PHASE_ID,
        "schema_version": "bfws_phase_authorization_v1",
        "scientific_completion": False,
        "source_issue": 56,
    }
    products = {
        _QUALIFIED: _jsonl_bytes(qualified_rows),
        _DEVELOPMENT: _jsonl_bytes(selected),
        _FRESH_TEST: _jsonl_bytes(fresh_test),
        _REPORT: _canonical_bytes(report),
        **{_COMPONENT_PATHS[name]: _canonical_bytes(payload) for name, payload in components.items()},
        _FREEZE: _canonical_bytes(freeze),
        _AUTHORIZATION: _canonical_bytes(authorization),
    }
    summary = {
        "selected_exact_decision_count": selected_decisions,
        "selected_exact_expansion_count": selected_expansions,
        "selected_instance_count": len(selected),
        "selected_stratum_count": len(strata),
        "fresh_test_instance_count": len(fresh_test),
        "solved_instance_count": len(qualified_rows),
    }
    return products, summary


def _qualified_row(source: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    if result.get("replay_valid") is not True:
        raise ValueError(f"solved BFWS row lacks replay evidence: {source.get('instance_id')}")
    return {
        "algorithm": "best_first_width",
        "difficulty": source["bucket"],
        "domain_id": source["domain_id"],
        "domain_path": _source_path(source["domain_path"]),
        "exact_reference_decision_count": result["decision_count"],
        "exact_reference_duplicate_count": result["duplicate_count"],
        "exact_reference_expansion_count": result["expansion_count"],
        "exact_reference_generated_count": result["generated_count"],
        "exact_reference_peak_frontier": result["peak_frontier"],
        "exact_reference_plan": result["plan"],
        "instance_id": source["instance_id"],
        "normalized_domain_hash": source["normalized_domain_hash"],
        "normalized_problem_hash": source["normalized_problem_hash"],
        "problem_path": _source_path(source["problem_path"]),
        "qualification_replay_valid": True,
        "qualification_status": "solved",
        "schema_version": "bfws_qualified_solved_instance_v1",
        "source_split": source["split"],
        "variant": "full_bfws_goal_count",
    }


def _select_fresh_test(development_identities: set[str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for source in _jsonl_objects(_SOURCE_MANIFEST):
        if source.get("split") == "dev":
            grouped[(source["domain_id"], source["bucket"])].append(source)
    selected: list[dict[str, Any]] = []
    selected_identities: set[str] = set()
    for (domain_id, difficulty), rows in sorted(grouped.items()):
        for source in sorted(rows, key=lambda row: (row["normalized_problem_hash"], row["instance_id"])):
            authority = PDDLStateAuthority.from_pddl(
                (_REPO_ROOT / _source_path(source["domain_path"])).read_text(encoding="utf-8"),
                (_REPO_ROOT / _source_path(source["problem_path"])).read_text(encoding="utf-8"),
            )
            identity = authority.semantic_task_identity()
            if identity in development_identities or identity in selected_identities:
                continue
            selected_identities.add(identity)
            selected.append(
                {
                    "algorithm_outcome_used_for_selection": False,
                    "bfws_qualification_accessed": False,
                    "difficulty": difficulty,
                    "domain_id": domain_id,
                    "domain_path": _source_path(source["domain_path"]),
                    "instance_id": source["instance_id"],
                    "normalized_domain_hash": source["normalized_domain_hash"],
                    "normalized_problem_hash": source["normalized_problem_hash"],
                    "problem_path": _source_path(source["problem_path"]),
                    "schema_version": "bfws_fresh_heldout_instance_v1",
                    "semantic_task_identity": identity,
                    "source_split": "dev",
                    "split": "test",
                }
            )
            break
    if (
        len(selected) != 45
        or len({(row["domain_id"], row["difficulty"]) for row in selected}) != 45
        or selected_identities & development_identities
    ):
        raise ValueError("BFWS fresh held-out selection does not cover 15 domains by three difficulties")
    return sorted(selected, key=lambda row: (row["domain_id"], _difficulty_index(row["difficulty"])))


def _component_manifests(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    common = {"parent_issue": 38, "phase_id": _PHASE_ID, "source_issue": 56}
    trace = {
        **common,
        "algorithm": {
            "high_novelty_policy": "enqueue",
            "identifier": "best_first_width",
            "novelty_partition": "unachieved_goal_count",
            "novelty_precision": 2,
            "priority": ["novelty_bucket", "unachieved_goal_count", "path_depth", "generation_serial"],
            "recovery_policy": "prohibited",
            "variant": "full_bfws_goal_count",
        },
        "component": "trace",
        "development_manifest_path": _relative(_DEVELOPMENT),
        "episode_budget": "per-instance exact_reference_expansion_count",
        "evidence_schema": "search_episode_evidence_v4",
        "exact_reference_decision_count_field": "exact_reference_decision_count",
        "observation_builder": "examples.planning_benchmark_slice.bfws_episode.build_bfws_observation",
        "qualification_report_path": _relative(_REPORT),
        "replay_required": True,
        "schema_version": "bfws_trace_freeze_v1",
        "selected_instance_count": report["selected_instance_count"],
        "selected_plan_replay_count": report["selected_plan_replay_count"],
        "selected_stratum_count": report["selected_stratum_count"],
        "solved_manifest_path": _relative(_QUALIFIED),
    }
    corpus = {
        **common,
        "accepted_delta_limit": 16,
        "required_audit_results": {
            "canonical_input_overlap_count": 0,
            "future_step_leakage_count": 0,
            "held_out_instance_count": 0,
            "identical_input_conflicting_target_count": 0,
            "input_target_overlap_count": 0,
            "live_training_input_mismatch_count": 0,
            "semantic_task_overlap_count": 0,
            "teacher_decision_rejection_count": 0,
        },
        "byte_identical_regeneration_required": [
            "corpus",
            "curriculum",
            "split_ledger",
            "training_projection",
        ],
        "component": "corpus",
        "input_builder": "examples.planning_benchmark_slice.bfws_model_input.build_bounded_bfws_model_input",
        "model_input_byte_preference": 3_840,
        "model_input_schema": "bounded_bfws_search_memory_v1",
        "model_input_token_limit": 7_808,
        "model_output_token_limit": 384,
        "process_target_fields": ["canonical_rationale", "typed_operation", "runtime_result"],
        "process_target_runtime_result": None,
        "schema_version": "bfws_corpus_freeze_v1",
        "segment_alignment": "atomic_search_event",
        "split_unit": "semantic_task_identity",
        "tokenizer_context_limit": 8_192,
        "views": ["operational", "process"],
    }
    training = {
        **common,
        "component": "training",
        "libraries": {
            "accelerate": "1.5.2",
            "peft": "0.17.1",
            "torch": "2.7.1",
            "transformers": "4.57.0",
        },
        "lora": {"alpha": 128, "bias": "none", "dropout": 0.05, "rank": 64, "target_modules": "all-linear"},
        "model": {
            "license": "apache-2.0",
            "model_id": "Qwen/Qwen3-VL-8B-Instruct",
            "revision": _MODEL_REVISION,
        },
        "optimization": {
            "bf16": True,
            "deterministic_algorithms": True,
            "epochs": 3,
            "global_batch_size": 32,
            "gradient_checkpointing": True,
            "learning_rate": 0.0001,
            "lr_scheduler": "cosine",
            "max_gradient_norm": 1.0,
            "optimizer": "adamw_torch",
            "warmup_ratio": 0.03,
            "weight_decay": 0.0,
        },
        "process_sft_only": True,
        "schema_version": "bfws_training_freeze_v1",
        "seeds": _SEEDS,
        "training_max_length": 8_192,
        "checkpoint_policy": {
            "diagnostic_fractions": ["1/3", "2/3"],
            "rollout": "final",
            "teacher_forced_diagnostics_only_for_nonfinal": True,
        },
    }
    reference = {
        **common,
        "batching": {
            "adapter_isolated_cache": True,
            "deterministic_round_robin": True,
            "inference_dtype": "float32",
            "max_batch_input_tokens": 48_000,
            "max_batch_size": 8,
            "one_request_per_active_episode_per_round": True,
        },
        "component": "reference",
        "conditions": ["pretrained_base", "process_sft", "random_valid", "exact_bfws"],
        "development_instance_count": 35,
        "episode_model_call_limit": "2 * matching exact_reference_decision_count",
        "exact_expansion_limit": "matching exact_reference_expansion_count",
        "exact_reference_replay_required": True,
        "fresh_held_out_test_access_authorized": False,
        "fresh_held_out_test_instance_count": 45,
        "fresh_held_out_test_manifest_path": _relative(_FRESH_TEST),
        "fresh_held_out_test_selection": "one semantic-unique source-dev task per domain-by-difficulty cell",
        "rollout_checkpoint": "final",
        "schema_version": "bfws_reference_freeze_v1",
        "seeds": _SEEDS,
    }
    threshold = {
        **common,
        "bootstrap": {
            "confidence_level": 0.95,
            "interval": "paired_percentile_bootstrap",
            "resamples": 10_000,
            "seed": 1_729,
            "uncertainty_unit": "whole_problem_instance",
        },
        "component": "threshold",
        "metrics": {
            "exact_reference_invariant_valid_success": 1.0,
            "expert_trace_replay_rate": 1.0,
            "maximum_invalid_operation_rate": 0.05,
            "process_sft_absolute_gain_over_best_control": 0.1,
            "process_sft_gain_bootstrap_lower_bound": 0.0,
            "process_sft_invariant_valid_success": 0.8,
        },
        "primary_outcome": "full_episode_invariant_valid_success",
        "report_each_seed": True,
        "schema_version": "bfws_threshold_freeze_v1",
    }
    stop = {
        **common,
        "component": "stop",
        "gate_clock": {
            "gate_hours": 20,
            "rollout_certification_hours": 15,
            "rollout_cutoff_hours": 18,
            "safety_margin": 1.2,
            "start_once_after_hardware_qualification": True,
        },
        "hardware_qualification": {
            "coverage_order": ["full_development", "preregistered_exact_cost_panel"],
            "model_success_may_influence_selection": False,
            "repeated_batch_probe_required": True,
            "scalar_batch_byte_parity_required": True,
            "settings": ["hardware", "batch_size", "precision", "token_limits", "adapter_cache_semantics"],
        },
        "outcomes": {
            "ANCESTOR_STOP": "required predecessor is not PASS; emit gated-not-run",
            "INVALID": "manifest, split, replay, provenance, parity, or required-coverage mismatch",
            "PASS": "complete selected coverage, replay validity, and every frozen threshold",
            "VALID_STOP": "ordinary threshold or resource failure with otherwise valid complete evidence",
        },
        "rules": {
            "fresh_test_required_before_efficacy": True,
            "no_retuning": True,
            "partial_coverage_cannot_satisfy_gate": True,
            "stop_new_calls_at_cutoff": True,
        },
        "schema_version": "bfws_stop_freeze_v1",
    }
    return {
        "trace": trace,
        "corpus": corpus,
        "training": training,
        "reference": reference,
        "threshold": threshold,
        "stop": stop,
    }


def _latest_results(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in _jsonl_objects(path):
        latest[row["instance_id"]] = row
    return latest


def _replay_selected_plan(authority: PDDLStateAuthority, row: Mapping[str, Any]) -> None:
    state = authority.initial_state
    plan = row.get("exact_reference_plan")
    if not isinstance(plan, list) or not all(isinstance(action, str) for action in plan):
        raise ValueError(f"BFWS selected plan is malformed: {row.get('instance_id')}")
    for serialized in plan:
        actions = {action.serialize(): action for action in authority.applicable_actions(state)}
        action = actions.get(serialized)
        if action is None:
            raise ValueError(f"BFWS selected plan is not applicable: {row.get('instance_id')}")
        state = authority.apply(state, action).target_state
    if not authority.is_goal(state):
        raise ValueError(f"BFWS selected plan does not reach the goal: {row.get('instance_id')}")


def _jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"expected JSON objects: {path}")
    return rows


def _source_path(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("qualification source path must be text")
    path = Path(value).resolve()
    try:
        relative = path.relative_to(_REPO_ROOT)
    except ValueError as error:
        raise ValueError(f"qualification source path is outside the repository: {path}") from error
    if not path.is_file():
        raise ValueError(f"qualification source artifact is missing: {path}")
    return relative.as_posix()


def _difficulty_index(value: object) -> int:
    return {"easy": 0, "medium": 1, "hard": 2}[str(value)]


def _relative(path: Path) -> str:
    return path.resolve().relative_to(_REPO_ROOT).as_posix()


def _jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(row) for row in rows)


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
