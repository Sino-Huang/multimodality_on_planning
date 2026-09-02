"""Frozen replacement authority for paired additive best-first search."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .best_first_controller import BEST_FIRST_SETTINGS


class BestFirstPhaseError(ValueError):
    """Raised when the replacement design or its fixed panel has drifted."""


@dataclass(frozen=True, slots=True)
class BestFirstPhase:
    design: Mapping[str, Any]
    authorization: Mapping[str, Any]
    pairs: tuple[Mapping[str, Any], ...]
    repo_root: Path

    @property
    def phase_id(self) -> str:
        return str(self.design["phase_id"])

    def require_stage(self, stage: str) -> None:
        if (
            self.authorization.get("contract_id") != self.phase_id
            or self.authorization.get("outcome") != "PASS"
            or self.authorization.get("start_permitted") is not True
            or stage not in self.authorization.get("authorized_stages", [])
        ):
            raise BestFirstPhaseError(f"best-first stage is not authorized: {stage}")


def load_best_first_phase(
    design_path: str | Path,
    authorization_path: str | Path,
    *,
    repo_root: str | Path,
) -> BestFirstPhase:
    root = Path(repo_root).resolve()
    design_file = Path(design_path).resolve()
    authorization_file = Path(authorization_path).resolve()
    design = _json_object(design_file)
    authorization = _json_object(authorization_file)
    if (
        design.get("schema_version") != "best_first_paired_design_v2"
        or design.get("phase_id") != "issue-63-best-first-paired-v2"
        or design.get("source_issue") != 63
        or design.get("parent_issue") != 38
        or design.get("optimality_required") is not False
        or design.get("panel_selection_used_search_outcomes") is not False
        or set(design.get("algorithms", {})) != set(BEST_FIRST_SETTINGS)
        or design.get("accepted_delta_limit") != 16
        or design.get("pair_count") != 75
    ):
        raise BestFirstPhaseError("best-first replacement design has drifted")
    expected_algorithms = {
        "best_first_add_greedy": {
            "closed_node_policy": "do_not_reopen",
            "heuristic": "h_add",
            "priority": ["h", "generation_serial"],
        },
        "best_first_add_w2": {
            "closed_node_policy": "reopen_on_cheaper_path",
            "heuristic": "h_add",
            "priority": ["g_plus_2h", "generation_serial"],
        },
    }
    caps = design.get("caps")
    trace = design.get("trace_contract")
    if (
        design.get("algorithms") != expected_algorithms
        or caps
        != {
            "max_decisions_per_trace": 55_000,
            "max_expansions_per_trace": 15_000,
            "max_uncompressed_trace_bytes": 37_400_000,
            "overflow_outcome": "VALID_STOP",
            "segmentation_allowed": False,
        }
        or not isinstance(trace, Mapping)
        or trace.get("schema_version") != "best_first_compact_trace_v1"
        or trace.get("full_frontier_arrays_persisted") is not False
        or trace.get("repeated_model_inputs_persisted") is not False
        or trace.get("independent_replay") is not True
        or trace.get("state_references") != "deterministic_s_integer"
        or trace.get("state_storage") != "each_model_observed_state_once"
    ):
        raise BestFirstPhaseError("best-first algorithms, caps, or trace contract have drifted")

    task_binding = design.get("task_manifest")
    task_path = _bound_path(root, task_binding, "task manifest")
    task_manifest = _json_object(task_path)
    pairs = task_manifest.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != 75 or task_manifest.get("pair_count") != 75:
        raise BestFirstPhaseError("best-first replacement requires the complete fixed 75-task panel")
    seen: set[str] = set()
    for row in pairs:
        if not isinstance(row, Mapping):
            raise BestFirstPhaseError("fixed panel row is malformed")
        pair_id = row.get("pair_id")
        task_file = root / str(row.get("task_path"))
        if (
            not isinstance(pair_id, str)
            or pair_id in seen
            or not task_file.is_file()
            or _sha256(task_file) != row.get("task_sha256")
            or row.get("split") not in {"train", "dev"}
        ):
            raise BestFirstPhaseError("fixed panel identity or task binding has drifted")
        seen.add(pair_id)

    if (
        authorization.get("schema_version") != "best_first_paired_authorization_v2"
        or authorization.get("authorization_id") != "issue-63-best-first-paired-authorization-v2"
        or authorization.get("contract_id") != design["phase_id"]
        or authorization.get("authorized_stages") != ["qualification", "trace_generation"]
        or authorization.get("outcome") != "PASS"
        or authorization.get("start_permitted") is not True
        or authorization.get("scientific_completion") is not False
        or authorization.get("supersedes_contract_id") != "issue-62-astar-paired-development-v1"
        or authorization.get("supersedes_algorithms") != ["astar_hmax", "astar_landmark_count"]
        or _bound_path(root, authorization.get("design_manifest"), "design manifest") != design_file
    ):
        raise BestFirstPhaseError("best-first replacement authorization has drifted")
    phase = BestFirstPhase(design, authorization, tuple(pairs), root)
    phase.require_stage("qualification")
    return phase


def qualification_jobs(phase: BestFirstPhase) -> tuple[dict[str, Any], ...]:
    phase.require_stage("qualification")
    caps = phase.design["caps"]
    return tuple(
        {
            "algorithm": algorithm,
            "difficulty": row["difficulty"],
            "domain_id": row["domain_id"],
            "instance_id": row["instance_id"],
            "max_decisions": caps["max_decisions_per_trace"],
            "max_expansions": caps["max_expansions_per_trace"],
            "pair_id": row["pair_id"],
            "split": row["split"],
            "task_path": row["task_path"],
            "task_sha256": row["task_sha256"],
        }
        for row in phase.pairs
        for algorithm in BEST_FIRST_SETTINGS
    )


def _bound_path(root: Path, binding: object, label: str) -> Path:
    if not isinstance(binding, Mapping) or set(binding) != {"path", "sha256", "size_bytes"}:
        raise BestFirstPhaseError(f"{label} binding is malformed")
    path = (root / str(binding["path"])).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise BestFirstPhaseError(f"{label} escapes the repository") from error
    if not path.is_file() or path.stat().st_size != binding["size_bytes"] or _sha256(path) != binding["sha256"]:
        raise BestFirstPhaseError(f"{label} binding has drifted")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise BestFirstPhaseError(f"cannot load best-first authority: {path}") from error
    if not isinstance(value, dict):
        raise BestFirstPhaseError(f"best-first authority is not an object: {path}")
    return value


__all__ = [
    "BestFirstPhase",
    "BestFirstPhaseError",
    "load_best_first_phase",
    "qualification_jobs",
]
