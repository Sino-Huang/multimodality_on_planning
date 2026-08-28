"""Frozen issue-56 BFWS development inputs and authorization gate."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE_ID = "issue-56-bfws-development-v1"
_COMPONENTS = ("trace", "corpus", "training", "reference", "threshold", "stop")
_AUTHORIZED_STAGES = (
    "trace_generation",
    "corpus_release",
    "process_sft_training",
    "development_references",
    "development_structural_gate",
)


class BFWSPhaseGateError(ValueError):
    """Raised when the BFWS freeze cannot authorize a development run."""


@dataclass(frozen=True, slots=True)
class BFWSPhaseGate:
    freeze: dict[str, Any]
    components: Mapping[str, dict[str, Any]]
    authorization: dict[str, Any]
    freeze_manifest_path: Path
    authorization_manifest_path: Path

    @property
    def phase_id(self) -> str:
        return str(self.freeze["phase_id"])

    def require_run(self, *, stage: str, contract_id: str, split: str | None = None) -> None:
        if stage not in self.authorization["authorized_stages"]:
            raise BFWSPhaseGateError(f"BFWS stage is not authorized: {stage}")
        if contract_id != self.authorization["contract_id"]:
            raise BFWSPhaseGateError("BFWS run contract_id does not match the phase authorization")
        if split is not None and split not in {"train", "dev"}:
            raise BFWSPhaseGateError("BFWS efficacy-test access is not authorized by the development phase")

    def receipt(self, *, stage: str) -> dict[str, object]:
        self.require_run(stage=stage, contract_id=self.phase_id)
        return {
            "authorization_id": self.authorization["authorization_id"],
            "authorization_manifest_path": _relative(self.authorization_manifest_path),
            "component_manifest_paths": dict(self.freeze["component_manifests"]),
            "freeze_manifest_path": _relative(self.freeze_manifest_path),
            "outcome": self.authorization["outcome"],
            "phase_id": self.phase_id,
            "stage": stage,
        }


def load_bfws_phase_gate(
    freeze_manifest_path: str | Path,
    authorization_manifest_path: str | Path,
    *,
    repo_root: str | Path = _REPO_ROOT,
) -> BFWSPhaseGate:
    """Load the six component freezes and their exact development authorization."""

    root = Path(repo_root).resolve()
    freeze_path = Path(freeze_manifest_path).resolve()
    authorization_path = Path(authorization_manifest_path).resolve()
    freeze = _json_object(freeze_path, "BFWS freeze manifest")
    authorization = _json_object(authorization_path, "BFWS authorization manifest")
    if set(freeze) != {
        "algorithm",
        "component_manifests",
        "modality",
        "parent_issue",
        "phase_id",
        "schema_version",
        "source_issue",
        "variant",
    } or (
        freeze["schema_version"] != "bfws_phase_freeze_v1"
        or freeze["phase_id"] != _PHASE_ID
        or freeze["algorithm"] != "best_first_width"
        or freeze["variant"] != "full_bfws_goal_count"
        or freeze["modality"] != "text-state"
        or freeze["source_issue"] != 56
        or freeze["parent_issue"] != 38
    ):
        raise BFWSPhaseGateError("BFWS freeze has the wrong schema or authority")

    component_paths = freeze["component_manifests"]
    if not isinstance(component_paths, dict) or tuple(sorted(component_paths)) != tuple(sorted(_COMPONENTS)):
        raise BFWSPhaseGateError("BFWS freeze must bind all six component manifests")
    components: dict[str, dict[str, Any]] = {}
    for name in _COMPONENTS:
        path = _repository_path(root, component_paths[name], f"BFWS {name} manifest")
        component = _json_object(path, f"BFWS {name} manifest")
        if (
            component.get("component") != name
            or component.get("phase_id") != _PHASE_ID
            or component.get("source_issue") != 56
            or component.get("parent_issue") != 38
            or component.get("schema_version") != f"bfws_{name}_freeze_v1"
        ):
            raise BFWSPhaseGateError(f"BFWS {name} component has the wrong schema or authority")
        components[name] = component

    _validate_trace_and_data(components["trace"], root)
    _validate_corpus(components["corpus"])
    _validate_training(components["training"])
    _validate_reference(components["reference"], root, components["trace"])
    _validate_threshold(components["threshold"])
    _validate_stop(components["stop"])
    _validate_authorization(authorization, freeze_path, root)
    return BFWSPhaseGate(
        freeze=freeze,
        components=components,
        authorization=authorization,
        freeze_manifest_path=freeze_path,
        authorization_manifest_path=authorization_path,
    )


def _validate_trace_and_data(trace: Mapping[str, Any], root: Path) -> None:
    algorithm = trace.get("algorithm")
    if not isinstance(algorithm, Mapping) or algorithm != {
        "high_novelty_policy": "enqueue",
        "identifier": "best_first_width",
        "novelty_partition": "unachieved_goal_count",
        "novelty_precision": 2,
        "priority": ["novelty_bucket", "unachieved_goal_count", "path_depth", "generation_serial"],
        "recovery_policy": "prohibited",
        "variant": "full_bfws_goal_count",
    }:
        raise BFWSPhaseGateError("BFWS trace algorithm contract has drifted")
    if (
        trace.get("selected_instance_count") != 105
        or trace.get("selected_plan_replay_count") != 105
        or trace.get("selected_stratum_count") != 35
        or trace.get("episode_budget") != "per-instance exact_reference_expansion_count"
        or trace.get("replay_required") is not True
    ):
        raise BFWSPhaseGateError("BFWS trace coverage or replay contract is invalid")
    manifest_path = _repository_path(root, trace.get("development_manifest_path"), "BFWS development manifest")
    rows = _jsonl_objects(manifest_path)
    split_counts = Counter(row.get("split") for row in rows)
    stratum_counts = Counter((row.get("domain_id"), row.get("difficulty"), row.get("split")) for row in rows)
    identities = [row.get("semantic_task_identity") for row in rows]
    if (
        len(rows) != 105
        or split_counts != Counter({"train": 70, "dev": 35})
        or len(set(identities)) != len(rows)
        or any(
            row.get("source_split") != "train"
            or row.get("qualification_status") != "solved"
            or row.get("qualification_replay_valid") is not True
            or not isinstance(row.get("exact_reference_decision_count"), int)
            or row["exact_reference_decision_count"] <= 0
            for row in rows
        )
    ):
        raise BFWSPhaseGateError("BFWS development manifest is not the isolated replay-proven panel")
    strata = {(domain, difficulty) for domain, difficulty, _split in stratum_counts}
    if len(strata) != 35 or any(
        stratum_counts[domain, difficulty, "train"] != 2 or stratum_counts[domain, difficulty, "dev"] != 1
        for domain, difficulty in strata
    ):
        raise BFWSPhaseGateError("BFWS development manifest does not cover the frozen 35 strata")
    for row in rows:
        _repository_path(root, row.get("domain_path"), "BFWS domain PDDL")
        _repository_path(root, row.get("problem_path"), "BFWS problem PDDL")

    report_path = _repository_path(root, trace.get("qualification_report_path"), "BFWS qualification report")
    report = _json_object(report_path, "BFWS qualification report")
    qualified_path = _repository_path(root, trace.get("solved_manifest_path"), "BFWS solved manifest")
    if (
        report.get("solved_manifest_path") != trace.get("solved_manifest_path")
        or report.get("selected_manifest_path") != trace.get("development_manifest_path")
        or report.get("qualification_status_counts")
        != {"expansion_limit": 1_304, "frontier_exhausted": 16, "solved": 3_186, "timeout": 172}
        or report.get("selected_instance_count") != 105
        or report.get("selected_plan_replay_count") != 105
        or report.get("excluded_former_test_instance_count") != 281
        or report.get("fresh_held_out_test")
        != {
            "access_authorized": False,
            "bfws_qualification_accessed": False,
            "instance_count": 45,
            "manifest_path": "data/bfws_phase_v1/fresh-test-manifest.jsonl",
            "source_split": "dev",
            "status": "frozen_unaccessed",
        }
        or len(_jsonl_objects(qualified_path)) != 3_186
    ):
        raise BFWSPhaseGateError("BFWS qualification report is not the completed issue-55 result")


def _validate_corpus(corpus: Mapping[str, Any]) -> None:
    audits = corpus.get("required_audit_results")
    if (
        corpus.get("accepted_delta_limit") != 16
        or corpus.get("model_input_schema") != "bounded_bfws_search_memory_v1"
        or corpus.get("model_input_token_limit") != 7_808
        or corpus.get("model_output_token_limit") != 384
        or corpus.get("tokenizer_context_limit") != 8_192
        or corpus.get("process_target_runtime_result", object()) is not None
        or corpus.get("split_unit") != "semantic_task_identity"
        or not isinstance(audits, Mapping)
        or any(value != 0 for value in audits.values())
    ):
        raise BFWSPhaseGateError("BFWS corpus does not satisfy the observable v6-style contract")


def _validate_training(training: Mapping[str, Any]) -> None:
    if (
        training.get("seeds") != [17, 29, 43, 71, 101]
        or training.get("training_max_length") != 8_192
        or training.get("process_sft_only") is not True
        or training.get("checkpoint_policy")
        != {
            "diagnostic_fractions": ["1/3", "2/3"],
            "rollout": "final",
            "teacher_forced_diagnostics_only_for_nonfinal": True,
        }
        or training.get("model", {}).get("revision") != "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
    ):
        raise BFWSPhaseGateError("BFWS training inputs or checkpoint policy have drifted")


def _validate_reference(reference: Mapping[str, Any], root: Path, trace: Mapping[str, Any]) -> None:
    if (
        reference.get("conditions") != ["pretrained_base", "process_sft", "random_valid", "exact_bfws"]
        or reference.get("seeds") != [17, 29, 43, 71, 101]
        or reference.get("development_instance_count") != 35
        or reference.get("episode_model_call_limit") != "2 * matching exact_reference_decision_count"
        or reference.get("rollout_checkpoint") != "final"
        or reference.get("fresh_held_out_test_access_authorized") is not False
        or reference.get("fresh_held_out_test_instance_count") != 45
        or reference.get("batching", {}).get("inference_dtype") != "float32"
    ):
        raise BFWSPhaseGateError("BFWS reference or resource-bounded evaluation contract has drifted")
    test_path = _repository_path(
        root,
        reference.get("fresh_held_out_test_manifest_path"),
        "BFWS fresh held-out test manifest",
    )
    development_path = _repository_path(
        root,
        trace.get("development_manifest_path"),
        "BFWS development manifest",
    )
    test_rows = _jsonl_objects(test_path)
    development_identities = {row.get("semantic_task_identity") for row in _jsonl_objects(development_path)}
    test_identities = {row.get("semantic_task_identity") for row in test_rows}
    cells = Counter((row.get("domain_id"), row.get("difficulty")) for row in test_rows)
    if (
        len(test_rows) != 45
        or len(test_identities) != 45
        or test_identities & development_identities
        or len(cells) != 45
        or any(count != 1 for count in cells.values())
        or any(
            row.get("source_split") != "dev"
            or row.get("split") != "test"
            or row.get("bfws_qualification_accessed") is not False
            or row.get("algorithm_outcome_used_for_selection") is not False
            for row in test_rows
        )
    ):
        raise BFWSPhaseGateError("BFWS fresh held-out test manifest is not isolated and outcome-blind")
    for row in test_rows:
        _repository_path(root, row.get("domain_path"), "BFWS held-out domain PDDL")
        _repository_path(root, row.get("problem_path"), "BFWS held-out problem PDDL")


def _validate_threshold(threshold: Mapping[str, Any]) -> None:
    if (
        threshold.get("metrics")
        != {
            "exact_reference_invariant_valid_success": 1.0,
            "expert_trace_replay_rate": 1.0,
            "maximum_invalid_operation_rate": 0.05,
            "process_sft_absolute_gain_over_best_control": 0.1,
            "process_sft_gain_bootstrap_lower_bound": 0.0,
            "process_sft_invariant_valid_success": 0.8,
        }
        or threshold.get("primary_outcome") != "full_episode_invariant_valid_success"
    ):
        raise BFWSPhaseGateError("BFWS thresholds have drifted")


def _validate_stop(stop: Mapping[str, Any]) -> None:
    if (
        set(stop.get("outcomes", {})) != {"PASS", "VALID_STOP", "INVALID", "ANCESTOR_STOP"}
        or stop.get("rules", {}).get("fresh_test_required_before_efficacy") is not True
        or stop.get("rules", {}).get("partial_coverage_cannot_satisfy_gate") is not True
        or stop.get("hardware_qualification", {}).get("model_success_may_influence_selection") is not False
        or stop.get("hardware_qualification", {}).get("scalar_batch_byte_parity_required") is not True
        or stop.get("gate_clock", {}).get("gate_hours") != 20
    ):
        raise BFWSPhaseGateError("BFWS stop or hardware-qualification protocol has drifted")


def _validate_authorization(authorization: Mapping[str, Any], freeze_path: Path, root: Path) -> None:
    expected_fields = {
        "authorization_id",
        "authorized_stages",
        "contract_id",
        "downstream_issues",
        "efficacy_test_access_authorized",
        "freeze_manifest_path",
        "outcome",
        "parent_issue",
        "phase_id",
        "schema_version",
        "scientific_completion",
        "source_issue",
    }
    if set(authorization) != expected_fields or (
        authorization.get("schema_version") != "bfws_phase_authorization_v1"
        or authorization.get("phase_id") != _PHASE_ID
        or authorization.get("contract_id") != _PHASE_ID
        or authorization.get("authorization_id") != "issue-56-bfws-development-authorization-v1"
        or authorization.get("authorized_stages") != list(_AUTHORIZED_STAGES)
        or authorization.get("downstream_issues") != [57, 58, 59]
        or authorization.get("efficacy_test_access_authorized") is not False
        or authorization.get("outcome") != "PASS"
        or authorization.get("scientific_completion") is not False
        or authorization.get("source_issue") != 56
        or authorization.get("parent_issue") != 38
    ):
        raise BFWSPhaseGateError("BFWS authorization does not match the frozen development phase")
    expected_freeze = _repository_path(root, authorization.get("freeze_manifest_path"), "BFWS freeze manifest")
    if expected_freeze != freeze_path:
        raise BFWSPhaseGateError("BFWS authorization points to a different freeze manifest")


def _repository_path(root: Path, value: object, name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise BFWSPhaseGateError(f"{name} path must be non-empty text")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise BFWSPhaseGateError(f"{name} path must be repository-relative")
    path = (root / relative).resolve()
    if not path.is_file():
        raise BFWSPhaseGateError(f"{name} is missing: {value}")
    return path


def _json_object(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise BFWSPhaseGateError(f"{name} is not readable canonical JSON") from error
    if not isinstance(value, dict):
        raise BFWSPhaseGateError(f"{name} must be a JSON object")
    return value


def _jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not all(isinstance(row, dict) for row in rows):
        raise BFWSPhaseGateError(f"BFWS manifest rows must be objects: {path}")
    return rows


def _relative(path: Path) -> str:
    return path.resolve().relative_to(_REPO_ROOT).as_posix()


__all__ = ["BFWSPhaseGate", "BFWSPhaseGateError", "load_bfws_phase_gate"]
