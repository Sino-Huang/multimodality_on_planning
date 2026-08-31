"""Issue-62 paired A* development freeze and narrow downstream gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .astar_hmax import HMaxHeuristic
from .astar_landmarks import LandmarkCountHeuristic
from .pddl_state import PDDLStateAuthority

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE_ID = "issue-62-astar-paired-development-v1"
_COMPONENTS = ("task", "trace", "corpus", "model", "budget", "analysis")
_AUTHORIZED_STAGES = ("trace_generation", "corpus_release")
_MODEL_REVISION = "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"


class AStarPairedPhaseGateError(ValueError):
    """Raised when the paired A* freeze cannot authorize a downstream stage."""


@dataclass(frozen=True, slots=True)
class AStarPairedPhaseGate:
    freeze: dict[str, Any]
    components: Mapping[str, dict[str, Any]]
    authorization: dict[str, Any]
    freeze_manifest_path: Path
    authorization_manifest_path: Path
    repo_root: Path

    @property
    def phase_id(self) -> str:
        return str(self.freeze["phase_id"])

    def require_run(self, stage: str, contract_id: str) -> None:
        if stage not in self.authorization["authorized_stages"]:
            raise AStarPairedPhaseGateError(f"A* paired stage is not authorized: {stage}")
        if contract_id != self.authorization["contract_id"]:
            raise AStarPairedPhaseGateError("A* paired run contract_id does not match authorization")

    def receipt(self, stage: str) -> dict[str, object]:
        self.require_run(stage, self.phase_id)
        return {
            "authorization_id": self.authorization["authorization_id"],
            "authorization_manifest_path": _relative(self.authorization_manifest_path, self.repo_root),
            "component_manifest_paths": dict(self.freeze["component_manifests"]),
            "freeze_manifest_path": _relative(self.freeze_manifest_path, self.repo_root),
            "outcome": self.authorization["outcome"],
            "phase_id": self.phase_id,
            "scientific_completion": self.authorization["scientific_completion"],
            "stage": stage,
        }


def load_astar_paired_phase_gate(
    freeze: str | Path,
    authorization: str | Path,
    *,
    repo_root: str | Path = _REPO_ROOT,
) -> AStarPairedPhaseGate:
    root = Path(repo_root).resolve()
    freeze_path = Path(freeze).resolve()
    authorization_path = Path(authorization).resolve()
    freeze_payload = _json_object(freeze_path, "A* paired freeze")
    authorization_payload = _json_object(authorization_path, "A* paired authorization")
    if freeze_payload != {
        "algorithms": ["astar_hmax", "astar_landmark_count"],
        "component_manifests": freeze_payload.get("component_manifests"),
        "modality": "text-state",
        "parent_issue": 38,
        "phase_id": _PHASE_ID,
        "schema_version": "astar_paired_phase_freeze_v1",
        "source_issue": 62,
    }:
        raise AStarPairedPhaseGateError("A* paired freeze has the wrong schema or authority")
    component_paths = freeze_payload["component_manifests"]
    if not isinstance(component_paths, dict) or tuple(sorted(component_paths)) != tuple(sorted(_COMPONENTS)):
        raise AStarPairedPhaseGateError("A* paired freeze must bind exactly six component manifests")
    components: dict[str, dict[str, Any]] = {}
    for name in _COMPONENTS:
        path = _repository_path(root, component_paths[name], f"A* paired {name} component")
        component = _json_object(path, f"A* paired {name} component")
        if (
            component.get("component") != name
            or component.get("phase_id") != _PHASE_ID
            or component.get("source_issue") != 62
            or component.get("parent_issue") != 38
            or component.get("schema_version") != f"astar_paired_{name}_freeze_v1"
        ):
            raise AStarPairedPhaseGateError(f"A* paired {name} component has wrong schema or authority")
        components[name] = component

    _validate_task(components["task"], root)
    _validate_trace(components["trace"])
    _validate_corpus(components["corpus"])
    _validate_model(components["model"])
    _validate_budget(components["budget"])
    _validate_analysis(components["analysis"])
    _validate_authorization(
        authorization_payload,
        freeze_path,
        root,
        components["task"]["source_bindings"],
    )
    return AStarPairedPhaseGate(
        freeze=freeze_payload,
        components=components,
        authorization=authorization_payload,
        freeze_manifest_path=freeze_path,
        authorization_manifest_path=authorization_path,
        repo_root=root,
    )


def _validate_task(component: Mapping[str, Any], root: Path) -> None:
    pairs = component.get("pairs")
    if (
        component.get("split_unit") != "semantic_task_identity"
        or not isinstance(pairs, list)
        or not pairs
        or component.get("pair_count") != len(pairs)
    ):
        raise AStarPairedPhaseGateError("A* paired task component has invalid pair coverage")
    _validate_source_bindings(component.get("source_bindings"), pairs, root)
    identities: dict[str, str] = {}
    pair_ids: set[str] = set()
    for row in pairs:
        if not isinstance(row, dict):
            raise AStarPairedPhaseGateError("A* paired task row must be an object")
        path = _repository_path(root, row.get("task_path"), "A* paired task")
        task_bytes = path.read_bytes()
        if row.get("task_sha256") != hashlib.sha256(task_bytes).hexdigest() or row.get("task_bytes") != len(task_bytes):
            raise AStarPairedPhaseGateError("A* paired task hash or byte binding has drifted")
        try:
            task = json.loads(task_bytes)
        except json.JSONDecodeError as error:
            raise AStarPairedPhaseGateError("A* paired task JSON has drifted") from error
        if not isinstance(task, dict) or not isinstance(task.get("domain_pddl"), str) or not isinstance(
            task.get("problem_pddl"), str
        ):
            raise AStarPairedPhaseGateError("A* paired task artifact is malformed")
        authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
        HMaxHeuristic(authority)
        LandmarkCountHeuristic(authority)
        identity = authority.semantic_task_identity()
        pair_digest = hashlib.sha256(f"{identity}\0{row.get('instance_id')}".encode()).hexdigest()
        if (
            row.get("schema_version") != "astar_paired_task_row_v1"
            or row.get("semantic_task_identity") != identity
            or row.get("normalized_domain_hash") != _pddl_hash(task["domain_pddl"])
            or row.get("normalized_problem_hash") != _pddl_hash(task["problem_pddl"])
            or row.get("pair_id") != f"astar-pair-{pair_digest[:24]}"
            or row.get("eligible_adapters") != ["astar_hmax", "astar_landmark_count"]
            or row.get("astar_outcome_used_for_selection") is not False
            or row.get("split") not in {"train", "dev"}
        ):
            raise AStarPairedPhaseGateError("A* paired task identity, hash, or pair binding has drifted")
        split = row["split"]
        if identity in identities:
            raise AStarPairedPhaseGateError(
                "A* paired task repeats a semantic identity or violates semantic split isolation"
            )
        identities[identity] = split
        pair_id = row["pair_id"]
        if pair_id in pair_ids:
            raise AStarPairedPhaseGateError("A* paired task repeats a pair identity")
        pair_ids.add(pair_id)


def _validate_trace(component: Mapping[str, Any]) -> None:
    if (
        component.get("algorithms") != ["astar_hmax", "astar_landmark_count"]
        or component.get("controller") != "AStarController"
        or component.get("priority") != ["f", "generation_serial"]
        or component.get("stable_candidate_ordering") is not True
        or component.get("reopen") != "cheaper_path_same_composite_node"
        or component.get("goal_test") != "popped_frontier_head_world_state"
        or component.get("independent_replay_per_adapter") is not True
        or component.get("traces_per_pair") != 2
        or component.get("pair_binding") != "exactly_two_traces_per_pair_on_identical_task_artifact"
        or component.get("adapter_specific_counts")
        != ["exact_reference_decision_count", "exact_reference_expansion_count"]
    ):
        raise AStarPairedPhaseGateError("A* paired trace contract has drifted")


def _validate_corpus(component: Mapping[str, Any]) -> None:
    audits = component.get("required_audit_results")
    if (
        component.get("accepted_delta_limit") != 16
        or component.get("input_token_limit") != 7808
        or component.get("output_token_limit") != 384
        or component.get("total_token_limit") != 8192
        or component.get("bounded_input_schema") != "bounded_astar_search_memory_v1"
        or component.get("model_input_builder")
        != "examples.planning_benchmark_slice.astar_model_input.build_bounded_astar_model_input"
        or component.get("message_prefix_serializer")
        != "examples.planning_benchmark_slice.astar_model_input.serialize_astar_message_prefix"
        or component.get("projection_policy")
        != "drop_oldest_accepted_deltas_only_preserve_all_required_facts"
        or component.get("required_future_parity_audits")
        != {
            "pinned_token_budget_overflow_count": 0,
            "teacher_live_canonical_byte_mismatch_count": 0,
        }
        or component.get("split_unit") != "semantic_task_identity"
        or component.get("fact_contract")
        != ["static_task", "candidate", "pruning", "best_cost", "frontier", "closed", "landmark_progression"]
        or component.get("byte_identical_regeneration")
        != ["corpus", "curriculum", "split_ledger", "training_projection"]
        or component.get("controls") != ["operational", "process", "staged", "shuffled", "mixed_order"]
        or not isinstance(audits, Mapping)
        or set(audits) != {"overlap", "conflict", "leakage", "rejection", "live_parity", "token_overflow"}
        or any(value != 0 for value in audits.values())
    ):
        raise AStarPairedPhaseGateError("A* paired corpus contract has drifted")


def _validate_model(component: Mapping[str, Any]) -> None:
    if (
        component.get("model_revision") != _MODEL_REVISION
        or component.get("training_seeds") != [17]
        or component.get("training_seed_variance_authorized") is not False
        or component.get("training_authorized") is not False
        or component.get("evaluation_reference_seeds") != [17, 29, 43, 71, 101]
        or component.get("library_versions")
        != {
            "accelerate": "1.5.2",
            "peft": "0.17.1",
            "torch": "2.7.1",
            "transformers": "4.57.0",
        }
        or component.get("training_cell_rule") != "one_distinct_cell_with_single_seed_17"
        or component.get("training_cells")
        != [
            {"adapter": adapter, "curriculum": curriculum, "training_seed": 17}
            for adapter in ("astar_hmax", "astar_landmark_count")
            for curriculum in ("staged", "shuffled", "mixed_order")
        ]
        or component.get("checkpoint_policy")
        != {"final_checkpoint_rollout": True, "nonfinal_teacher_forced_diagnostics_only": True}
    ):
        raise AStarPairedPhaseGateError("A* paired model or checkpoint policy has drifted")


def _validate_budget(component: Mapping[str, Any]) -> None:
    panel = component.get("panel_selection")
    if (
        component.get("per_adapter_model_call_limit") != "2 * matching exact_reference_decision_count"
        or component.get("per_adapter_expansion_limit") != "matching exact_reference_expansion_count"
        or component.get("deterministic_round_scheduling") is not True
        or component.get("request_session_round_policy") != "one_request_one_session_per_round"
        or component.get("adapter_isolated_cache") is not True
        or component.get("adapter_cache_key")
        != ["model_revision", "adapter_id", "canonical_input", "decoding_config", "qualified_precision"]
        or component.get("precision_qualification") != ["scalar", "batch", "repeated_batch"]
        or component.get("qualified_hardware_precision")
        != {"hardware": "qualification_recorded_accelerator", "inference_dtype": "float32"}
        or component.get("qualification_failure_outcome") != "VALID_STOP"
        or component.get("clock")
        != {
            "launch_cutoff_hours": 18,
            "restart_allowed": False,
            "start_policy": "start_once_after_hardware_qualification",
            "total_hours": 20,
        }
        or panel
        != {
            "cheapest_summed_exact_cost_per_domain": True,
            "fallback": {
                "cost": "sum_of_two_adapter_exact_reference_decision_counts_per_pair",
                "pairs_per_domain": 1,
                "tie_break": ["summed_exact_decision_count", "difficulty", "pair_id"],
                "uses_model_outcomes": False,
            },
            "fallback_outcome_blind": True,
            "full_paired_panel_first": True,
            "outcome_blind": True,
            "preregistered": True,
        }
    ):
        raise AStarPairedPhaseGateError("A* paired budget or outcome-blind panel contract has drifted")


def _validate_analysis(component: Mapping[str, Any]) -> None:
    if (
        component.get("pair_unit") != "complete_pair_whole_semantic_task"
        or component.get("metrics") != ["paired_adapter", "learned_vs_best_control"]
        or component.get("paired_bootstrap")
        != {"confidence": 0.95, "resamples": 10_000, "seed": 1729, "unit": "whole_problem_pair"}
        or component.get("efficacy_thresholds_authorized") is not False
        or component.get("model_efficacy_run_requires_successor_authorization") is not True
        or component.get("deterministic_acceptance")
        != {
            "mismatch_count": 0,
            "overflow_count": 0,
            "pair_completeness_rate": 1.0,
            "parity_rate": 1.0,
            "rejection_count": 0,
            "replay_rate": 1.0,
        }
        or set(component.get("outcomes", {})) != {"PASS", "VALID_STOP", "INVALID", "ANCESTOR_STOP"}
        or component.get("mismatch_outcome") != "INVALID"
        or component.get("partial_coverage_can_satisfy_gate") is not False
        or component.get("pass_requires_complete_coverage") is not True
        or component.get("classification")
        != {
            "ANCESTOR_STOP": ["failed_predecessor"],
            "INVALID": ["pairing_mismatch", "parity_mismatch", "replay_mismatch", "provenance_mismatch"],
            "PASS": ["complete_coverage_and_all_frozen_criteria"],
            "VALID_STOP": ["ordinary_threshold_failure", "ordinary_resource_failure"],
        }
    ):
        raise AStarPairedPhaseGateError("A* paired analysis, outcome, or coverage contract has drifted")


def _validate_authorization(
    authorization: Mapping[str, Any],
    freeze_path: Path,
    root: Path,
    source_bindings: object,
) -> None:
    expected = {
        "authorization_id": "issue-62-astar-paired-authorization-v1",
        "authorized_stages": list(_AUTHORIZED_STAGES),
        "contract_id": _PHASE_ID,
        "downstream_issues": [63, 64],
        "efficacy_test_access_authorized": False,
        "freeze_manifest_path": authorization.get("freeze_manifest_path"),
        "outcome": "PASS",
        "parent_issue": 38,
        "phase_id": _PHASE_ID,
        "schema_version": "astar_paired_phase_authorization_v1",
        "scientific_completion": False,
        "source_bindings": source_bindings,
        "source_issue": 62,
    }
    if dict(authorization) != expected:
        raise AStarPairedPhaseGateError("A* paired authorization has drifted")
    if _repository_path(root, authorization["freeze_manifest_path"], "A* paired freeze") != freeze_path:
        raise AStarPairedPhaseGateError("A* paired authorization points to a different freeze")


def _validate_source_bindings(bindings: object, pairs: list[dict[str, Any]], root: Path) -> None:
    if not isinstance(bindings, dict) or set(bindings) != {
        "source_audit",
        "source_authorization",
        "source_evidence",
        "source_manifest",
    }:
        raise AStarPairedPhaseGateError("A* paired source bindings are malformed")
    if (
        not isinstance(bindings["source_authorization"], dict)
        or bindings["source_authorization"].get("path")
        != "configs/experiments/bfws_phase_authorization_v1.json"
        or not isinstance(bindings["source_evidence"], dict)
        or bindings["source_evidence"].get("path")
        != "data/bfws_phase_v1/exact-traces/manifests/bfws-expert-traces.json"
    ):
        raise AStarPairedPhaseGateError("A* paired source authority or evidence path is not allowlisted")
    payloads = {
        name: _binding_payload(bindings[name], root, f"A* paired {name.replace('_', ' ')}")
        for name in bindings
    }
    audit = _canonical_object(payloads["source_audit"], "A* paired source audit")
    authorization = _canonical_object(payloads["source_authorization"], "A* paired source authorization")
    evidence = _canonical_object(payloads["source_evidence"], "A* paired source evidence")
    expected_authority_reference = {
        "identifier": "issue-56-bfws-development-authorization-v1",
        "schema_version": "bfws_phase_authorization_v1",
        **bindings["source_authorization"],
    }
    expected_evidence_reference = {
        "identifier": "issue-57-bfws-expert-traces-v1",
        "schema_version": "bfws_expert_trace_generation_v1",
        **bindings["source_evidence"],
    }
    if (
        set(audit)
        != {
            "audit_id",
            "efficacy_data",
            "expected_pair_count",
            "expected_task_count",
            "panel_purpose",
            "replay_proven",
            "review_status",
            "schema_version",
            "selection_outcome_blind",
            "source_authorization",
            "source_evidence",
        }
        or not isinstance(audit.get("audit_id"), str)
        or not audit["audit_id"]
        or audit.get("schema_version") != "astar_paired_source_audit_v1"
        or audit.get("panel_purpose") != "paired_astar_development"
        or audit.get("review_status") != "reviewed"
        or audit.get("replay_proven") is not True
        or audit.get("selection_outcome_blind") is not True
        or audit.get("efficacy_data") is not False
        or not isinstance(audit.get("expected_task_count"), int)
        or isinstance(audit.get("expected_task_count"), bool)
        or not isinstance(audit.get("expected_pair_count"), int)
        or isinstance(audit.get("expected_pair_count"), bool)
        or audit.get("expected_task_count") != len(pairs)
        or audit.get("expected_pair_count") != len(pairs)
        or audit.get("source_authorization") != expected_authority_reference
        or audit.get("source_evidence") != expected_evidence_reference
    ):
        raise AStarPairedPhaseGateError("A* paired source audit authority or count has drifted")
    _validate_bound_bfws_authorization(authorization)
    _validate_bound_source_rows(payloads["source_manifest"], pairs)
    _validate_bound_bfws_evidence(evidence, pairs)


def _binding_payload(binding: object, root: Path, label: str) -> bytes:
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256", "size_bytes"}:
        raise AStarPairedPhaseGateError(f"{label} binding is malformed")
    path = _repository_path(root, binding["path"], label)
    payload = path.read_bytes()
    if binding["sha256"] != hashlib.sha256(payload).hexdigest() or binding["size_bytes"] != len(payload):
        raise AStarPairedPhaseGateError(f"{label} bytes or hash has drifted")
    return payload


def _validate_bound_bfws_authorization(value: Mapping[str, Any]) -> None:
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
        raise AStarPairedPhaseGateError("A* paired source authorization is not the issue-56 PASS authority")


def _validate_bound_source_rows(payload: bytes, pairs: list[dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for line in payload.splitlines(keepends=True):
        if line == b"\n" or not line.endswith(b"\n"):
            raise AStarPairedPhaseGateError("A* paired source manifest has noncanonical newline framing")
        row = _strict_json(line[:-1], "A* paired source manifest row")
        if not isinstance(row, dict) or _canonical_bytes(row) != line[:-1]:
            raise AStarPairedPhaseGateError("A* paired source manifest row is not canonical")
        rows.append(row)
    source_rows = {
        (row.get("domain_id"), row.get("difficulty"), row.get("instance_id"), row.get("split"), row.get("task_path"))
        for row in rows
    }
    pair_rows = {
        (row["domain_id"], row["difficulty"], row["instance_id"], row["split"], row["task_path"])
        for row in pairs
    }
    if source_rows != pair_rows or len(rows) != len(pairs):
        raise AStarPairedPhaseGateError("A* paired bound source manifest does not match task pairs")


def _validate_bound_bfws_evidence(value: Mapping[str, Any], pairs: list[dict[str, Any]]) -> None:
    traces = value.get("traces")
    coverage = value.get("coverage")
    receipt = value.get("phase_receipt")
    if (
        value.get("schema_version") != "bfws_expert_trace_generation_v1"
        or value.get("algorithm")
        != {
            "high_novelty_policy": "enqueue",
            "identifier": "best_first_width",
            "novelty_partition": "unachieved_goal_count",
            "novelty_precision": 2,
            "priority": ["novelty_bucket", "unachieved_goal_count", "path_depth", "generation_serial"],
            "recovery_policy": "prohibited",
            "variant": "full_bfws_goal_count",
        }
        or value.get("source_issue") != 57
        or value.get("evidence_schema") != "search_episode_evidence_v4"
        or not isinstance(traces, list)
        or not isinstance(coverage, dict)
        or coverage.get("instance_count") != len(pairs)
        or coverage.get("replay_verified_instance_count") != len(pairs)
        or not isinstance(receipt, dict)
        or receipt.get("authorization_id") != "issue-56-bfws-development-authorization-v1"
        or receipt.get("phase_id") != "issue-56-bfws-development-v1"
        or receipt.get("stage") != "trace_generation"
        or receipt.get("outcome") != "PASS"
        or any(
            not isinstance(trace, dict)
            or trace.get("algorithm") != "best_first_width"
            or trace.get("variant") != "full_bfws_goal_count"
            or trace.get("trace_scope") != "complete_exact_bfws_episode"
            or not isinstance(trace.get("source"), dict)
            or trace["source"].get("split") != trace.get("split")
            for trace in traces
        )
    ):
        raise AStarPairedPhaseGateError("A* paired source evidence is not replay-proven issue-57 evidence")
    observed = {
        (
            trace.get("domain_id"),
            trace.get("difficulty"),
            trace.get("instance_id"),
            trace.get("semantic_task_identity"),
            trace.get("split"),
        )
        for trace in traces
        if isinstance(trace, dict)
    }
    expected = {
        (row["domain_id"], row["difficulty"], row["instance_id"], row["semantic_task_identity"], row["split"])
        for row in pairs
    }
    if observed != expected or len(traces) != len(pairs):
        raise AStarPairedPhaseGateError("A* paired source evidence task identity bindings do not match")


def _repository_path(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise AStarPairedPhaseGateError(f"{label} path must be non-empty text")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise AStarPairedPhaseGateError(f"{label} path must be repository-relative")
    path = (root / relative).resolve()
    if not path.is_file():
        raise AStarPairedPhaseGateError(f"{label} is missing: {value}")
    return path


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        value = _strict_json(payload, label)
    except (OSError, ValueError) as error:
        raise AStarPairedPhaseGateError(f"{label} is not readable JSON") from error
    if not isinstance(value, dict) or _canonical_bytes(value) != payload:
        raise AStarPairedPhaseGateError(f"{label} must be canonical JSON object")
    return value


def _canonical_object(payload: bytes, label: str) -> dict[str, Any]:
    value = _strict_json(payload, label)
    if not isinstance(value, dict) or _canonical_bytes(value) != payload:
        raise AStarPairedPhaseGateError(f"{label} must be a canonical JSON object")
    return value


def _strict_json(payload: bytes, label: str) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise AStarPairedPhaseGateError(f"{label} has duplicate JSON key: {key}")
            value[key] = item
        return value

    def reject_constant(constant: str) -> None:
        raise AStarPairedPhaseGateError(f"{label} contains non-finite JSON constant: {constant}")

    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=object_pairs, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AStarPairedPhaseGateError(f"{label} is invalid UTF-8 JSON") from error


def _pddl_hash(value: str) -> str:
    return hashlib.sha256(" ".join(value.split()).encode()).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


__all__ = ["AStarPairedPhaseGate", "AStarPairedPhaseGateError", "load_astar_paired_phase_gate"]
