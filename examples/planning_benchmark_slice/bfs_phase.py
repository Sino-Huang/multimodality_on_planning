"""Frozen issue-49 inputs and authorization for BFS development runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FREEZE_SCHEMA = "bfs_phase_freeze_v1"
_AUTHORIZATION_SCHEMA = "bfs_phase_authorization_v1"
_DIFFICULTIES = ("easy", "medium", "hard")
_AUTHORIZED_STAGES = (
    "trace_generation",
    "corpus_release",
    "base_and_references",
    "operational_sft",
    "process_sft_and_sanity_gate",
)
_DOWNSTREAM_ISSUES = (50, 51, 52, 53, 54)
_TRAINING_ARMS = {"base", "exact_classical", "operational_sft", "process_sft", "random_valid"}


class BFSPhaseGateError(ValueError):
    """Raised when a BFS freeze or authorization cannot gate a run."""


@dataclass(frozen=True, slots=True)
class BFSPhaseGate:
    """A validated phase freeze paired with its committed authorization."""

    freeze: dict[str, Any]
    authorization: dict[str, Any]
    freeze_manifest_path: Path
    authorization_manifest_path: Path
    freeze_manifest_bytes: bytes
    authorization_manifest_bytes: bytes

    @property
    def phase_id(self) -> str:
        return str(self.freeze["phase_id"])

    def require_run(self, *, stage: str, contract_id: str, difficulty: str | None = None) -> int | None:
        """Authorize one stage and return its frozen expansion budget when applicable."""

        if stage not in self.authorization["authorized_stages"]:
            raise BFSPhaseGateError(f"BFS stage is not authorized: {stage}")
        if contract_id != self.authorization["contract_id"]:
            raise BFSPhaseGateError("BFS run contract_id does not match the phase authorization")
        if difficulty is None:
            return None
        budgets = self.freeze["budgets"]["episode_max_expansions_by_difficulty"]
        if difficulty not in budgets:
            raise BFSPhaseGateError(f"BFS difficulty is not frozen: {difficulty}")
        return int(budgets[difficulty])

    def receipt(self, *, stage: str, difficulty: str | None = None) -> dict[str, object]:
        """Return the run-specific provenance record retained by downstream evidence."""

        receipt: dict[str, object] = {
            "authorization_id": self.authorization["authorization_id"],
            "authorization_manifest_sha256": _sha256(self.authorization_manifest_bytes),
            "freeze_manifest_sha256": _sha256(self.freeze_manifest_bytes),
            "outcome": self.authorization["outcome"],
            "phase_id": self.phase_id,
            "stage": stage,
        }
        if difficulty is not None:
            receipt["difficulty"] = difficulty
            receipt["max_expansions"] = self.freeze["budgets"]["episode_max_expansions_by_difficulty"][difficulty]
        return receipt


def load_bfs_phase_gate(
    freeze_manifest_path: str | Path,
    authorization_manifest_path: str | Path,
    *,
    repo_root: str | Path = _REPO_ROOT,
) -> BFSPhaseGate:
    """Load and verify the committed freeze, its data inputs, and authorization."""

    root = Path(repo_root).resolve()
    freeze_path = Path(freeze_manifest_path).resolve()
    authorization_path = Path(authorization_manifest_path).resolve()
    freeze_bytes, freeze = _load_json_object(freeze_path, "BFS freeze manifest")
    authorization_bytes, authorization = _load_json_object(authorization_path, "BFS authorization manifest")

    _validate_freeze(freeze, root)
    _validate_authorization(authorization, freeze, freeze_path, freeze_bytes, root)
    return BFSPhaseGate(
        freeze=freeze,
        authorization=authorization,
        freeze_manifest_path=freeze_path,
        authorization_manifest_path=authorization_path,
        freeze_manifest_bytes=freeze_bytes,
        authorization_manifest_bytes=authorization_bytes,
    )


def _validate_freeze(freeze: dict[str, Any], repo_root: Path) -> None:
    expected_fields = {
        "algorithm",
        "budgets",
        "data",
        "implementation",
        "modality",
        "models",
        "parent_issue",
        "phase_id",
        "schema_version",
        "seeds",
        "source_issue",
        "statistics",
        "stop_rules",
        "thresholds",
        "training",
    }
    if set(freeze) != expected_fields:
        raise BFSPhaseGateError("BFS freeze manifest has noncanonical fields")
    if (
        freeze["schema_version"] != _FREEZE_SCHEMA
        or freeze["algorithm"] != "bfs"
        or freeze["modality"] != "text-state"
        or freeze["source_issue"] != 49
        or freeze["parent_issue"] != 38
    ):
        raise BFSPhaseGateError("BFS freeze manifest has the wrong authority or phase identity")

    data = _mapping(freeze, "data")
    if (
        data.get("allowed_splits") != ["train", "dev"]
        or data.get("held_out_split") != "test"
        or data.get("split_unit") != "whole_problem_instance"
        or data.get("strata") != list(_DIFFICULTIES)
    ):
        raise BFSPhaseGateError("BFS data splits or difficulty strata are not frozen correctly")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise BFSPhaseGateError("BFS data artifacts must be a non-empty list")
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            raise BFSPhaseGateError("BFS data artifact entry is malformed")
        path = repo_root / _text(artifact, "path")
        if not path.is_file() or _sha256(path.read_bytes()) != _digest(artifact, "sha256"):
            raise BFSPhaseGateError(f"BFS frozen data artifact has drifted: {artifact.get('path')}")

    budgets = _mapping(_mapping(freeze, "budgets"), "episode_max_expansions_by_difficulty")
    if set(budgets) != set(_DIFFICULTIES) or any(
        isinstance(budgets[difficulty], bool) or not isinstance(budgets[difficulty], int) or budgets[difficulty] <= 0
        for difficulty in _DIFFICULTIES
    ):
        raise BFSPhaseGateError("BFS expansion budgets are malformed")
    if not budgets["easy"] < budgets["medium"] < budgets["hard"]:
        raise BFSPhaseGateError("BFS expansion budgets must increase with difficulty")

    seeds = freeze["seeds"]
    if (
        not isinstance(seeds, list)
        or len(seeds) != 5
        or len(set(seeds)) != 5
        or any(isinstance(seed, bool) or not isinstance(seed, int) for seed in seeds)
    ):
        raise BFSPhaseGateError("BFS headline seeds must be five distinct integers")

    primary_model = _mapping(_mapping(freeze, "models"), "primary")
    if primary_model.get("role") != "primary_open_vlm":
        raise BFSPhaseGateError("BFS primary model role is invalid")
    _digest(primary_model, "revision")

    arms = _mapping(_mapping(freeze, "training"), "arms")
    if set(arms) != _TRAINING_ARMS:
        raise BFSPhaseGateError("BFS training arms do not match the frozen study design")
    if set(_mapping(freeze, "stop_rules")) != {"ancestor_stop", "invalid", "no_retuning", "pass", "valid_stop"}:
        raise BFSPhaseGateError("BFS stop rules are incomplete")


def _validate_authorization(
    authorization: dict[str, Any],
    freeze: dict[str, Any],
    freeze_path: Path,
    freeze_bytes: bytes,
    repo_root: Path,
) -> None:
    expected_fields = {
        "authorization_id",
        "authorized_stages",
        "contract_id",
        "downstream_issues",
        "freeze_manifest_path",
        "freeze_manifest_sha256",
        "outcome",
        "parent_issue",
        "phase_id",
        "schema_version",
        "scientific_completion",
        "source_issue",
    }
    if set(authorization) != expected_fields:
        raise BFSPhaseGateError("BFS authorization manifest has noncanonical fields")
    if (
        authorization["schema_version"] != _AUTHORIZATION_SCHEMA
        or authorization["outcome"] != "PASS"
        or authorization["scientific_completion"] is not False
        or authorization["source_issue"] != 49
        or authorization["parent_issue"] != 38
        or authorization["phase_id"] != freeze["phase_id"]
        or authorization["contract_id"] != freeze["phase_id"]
    ):
        raise BFSPhaseGateError("BFS authorization manifest does not authorize this phase")
    if authorization["authorized_stages"] != list(_AUTHORIZED_STAGES):
        raise BFSPhaseGateError("BFS authorization stages are incomplete or reordered")
    if authorization["downstream_issues"] != list(_DOWNSTREAM_ISSUES):
        raise BFSPhaseGateError("BFS authorization does not cover the exact downstream issue chain")
    expected_freeze_path = (repo_root / _text(authorization, "freeze_manifest_path")).resolve()
    if freeze_path != expected_freeze_path:
        raise BFSPhaseGateError("BFS authorization points to a different freeze manifest")
    if _digest(authorization, "freeze_manifest_sha256") != _sha256(freeze_bytes):
        raise BFSPhaseGateError("BFS freeze manifest does not match its authorization")


def _load_json_object(path: Path, name: str) -> tuple[bytes, dict[str, Any]]:
    try:
        payload = path.read_bytes()
        parsed: Any = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BFSPhaseGateError(f"{name} cannot be loaded: {path}") from error
    if not isinstance(parsed, dict):
        raise BFSPhaseGateError(f"{name} must contain a JSON object")
    return payload, parsed


def _mapping(value: dict[str, Any], field: str) -> dict[str, Any]:
    item = value.get(field)
    if not isinstance(item, dict):
        raise BFSPhaseGateError(f"BFS manifest field must be an object: {field}")
    return item


def _text(value: dict[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise BFSPhaseGateError(f"BFS manifest field must be non-empty text: {field}")
    return item


def _digest(value: dict[str, Any], field: str) -> str:
    item = _text(value, field)
    if len(item) != 40 and len(item) != 64:
        raise BFSPhaseGateError(f"BFS manifest digest has invalid length: {field}")
    if any(character not in "0123456789abcdef" for character in item):
        raise BFSPhaseGateError(f"BFS manifest digest is not lowercase hexadecimal: {field}")
    return item


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


__all__ = ["BFSPhaseGate", "BFSPhaseGateError", "load_bfs_phase_gate"]
