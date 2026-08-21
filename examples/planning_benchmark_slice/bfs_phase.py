"""Frozen issue-49 inputs and authorization for BFS development runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data_collect.splits import whole_instance_identity

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FREEZE_SCHEMA_V1 = "bfs_phase_freeze_v1"
_AUTHORIZATION_SCHEMA_V1 = "bfs_phase_authorization_v1"
_FREEZE_SCHEMA_V3 = "bfs_phase_freeze_v3"
_AUTHORIZATION_SCHEMA_V3 = "bfs_phase_authorization_v3"
_DIFFICULTIES = ("easy", "medium", "hard")
_AUTHORIZED_STAGES_V1 = (
    "trace_generation",
    "corpus_release",
    "base_and_references",
    "operational_sft",
    "process_sft_and_sanity_gate",
)
_AUTHORIZED_STAGES_V3 = (
    "trace_generation",
    "corpus_release",
    "base_and_references",
    "process_sft_and_sanity_gate",
)
_DOWNSTREAM_ISSUES_V1 = (50, 51, 52, 53, 54)
_DOWNSTREAM_ISSUES_V3 = (54,)
_TRAINING_ARMS_V1 = {"base", "exact_classical", "operational_sft", "process_sft", "random_valid"}
_TRAINING_ARMS_V3 = {"base", "exact_classical", "process_sft", "random_valid"}
_V3_PHASE_ID = "issue-111-bfs-expansion-qualified-pilot-v3"
_V3_MODEL_REVISION = "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
_V3_PREREGISTRATION_REVISION = "4da3ae71531e1131c19ce552f41426241ed4308c"
_V3_CORPUS_MATERIALIZATION_REVISION = "82422c2269c22ddbb8da76889a222cc7500ea74c"
_V3_SEEDS = [17, 29, 43, 71, 101]
_V3_BANDS = {"easy": (1, 64), "medium": (65, 256), "hard": (257, 1024)}
_V3_DOMAINS = (
    "15puzzle",
    "blocksworld",
    "depot",
    "driverlog",
    "elevators",
    "ferry",
    "freecell",
    "grid",
    "gripper",
    "logistics",
    "snake",
    "sokoban",
    "storage",
    "towers_of_hanoi",
    "visitall",
)


class BFSPhaseGateError(ValueError):
    """Raised when a BFS freeze or authorization cannot gate a run."""


@dataclass(frozen=True, slots=True)
class BFSPhaseGate:
    """A validated phase freeze paired with its committed authorization."""

    freeze: dict[str, Any]
    authorization: dict[str, Any]
    freeze_manifest_path: Path
    authorization_manifest_path: Path

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
            "authorization_manifest_path": self.authorization_manifest_path.relative_to(_REPO_ROOT).as_posix(),
            "freeze_manifest_path": self.freeze_manifest_path.relative_to(_REPO_ROOT).as_posix(),
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
    _freeze_bytes, freeze = _load_json_object(freeze_path, "BFS freeze manifest")
    _authorization_bytes, authorization = _load_json_object(authorization_path, "BFS authorization manifest")

    schema = freeze.get("schema_version")
    if schema == _FREEZE_SCHEMA_V1:
        _validate_freeze_v1(freeze, root)
        _validate_authorization_v1(authorization, freeze, freeze_path, root)
    elif schema == _FREEZE_SCHEMA_V3:
        _validate_freeze_v3(freeze, root)
        _validate_authorization_v3(authorization, freeze, freeze_path, root)
    else:
        raise BFSPhaseGateError("BFS freeze manifest has an unsupported schema version")
    return BFSPhaseGate(
        freeze=freeze,
        authorization=authorization,
        freeze_manifest_path=freeze_path,
        authorization_manifest_path=authorization_path,
    )


def _validate_freeze_v1(freeze: dict[str, Any], repo_root: Path) -> None:
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
        freeze["schema_version"] != _FREEZE_SCHEMA_V1
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
        if not isinstance(artifact, dict) or set(artifact) != {"path"}:
            raise BFSPhaseGateError("BFS data artifact entry is malformed")
        path = repo_root / _text(artifact, "path")
        if not path.is_file():
            raise BFSPhaseGateError(f"BFS data artifact is missing: {artifact.get('path')}")

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
    _text(primary_model, "revision")

    arms = _mapping(_mapping(freeze, "training"), "arms")
    if set(arms) != _TRAINING_ARMS_V1:
        raise BFSPhaseGateError("BFS training arms do not match the frozen study design")
    if set(_mapping(freeze, "stop_rules")) != {"ancestor_stop", "invalid", "no_retuning", "pass", "valid_stop"}:
        raise BFSPhaseGateError("BFS stop rules are incomplete")


def _validate_authorization_v1(
    authorization: dict[str, Any],
    freeze: dict[str, Any],
    freeze_path: Path,
    repo_root: Path,
) -> None:
    expected_fields = {
        "authorization_id",
        "authorized_stages",
        "contract_id",
        "downstream_issues",
        "freeze_manifest_path",
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
        authorization["schema_version"] != _AUTHORIZATION_SCHEMA_V1
        or authorization["outcome"] != "PASS"
        or authorization["scientific_completion"] is not False
        or authorization["source_issue"] != 49
        or authorization["parent_issue"] != 38
        or authorization["phase_id"] != freeze["phase_id"]
        or authorization["contract_id"] != freeze["phase_id"]
    ):
        raise BFSPhaseGateError("BFS authorization manifest does not authorize this phase")
    if authorization["authorized_stages"] != list(_AUTHORIZED_STAGES_V1):
        raise BFSPhaseGateError("BFS authorization stages are incomplete or reordered")
    if authorization["downstream_issues"] != list(_DOWNSTREAM_ISSUES_V1):
        raise BFSPhaseGateError("BFS authorization does not cover the exact downstream issue chain")
    expected_freeze_path = (repo_root / _text(authorization, "freeze_manifest_path")).resolve()
    if freeze_path != expected_freeze_path:
        raise BFSPhaseGateError("BFS authorization points to a different freeze manifest")


def _validate_freeze_v3(freeze: dict[str, Any], repo_root: Path) -> None:
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
        raise BFSPhaseGateError("BFS v3 freeze manifest has noncanonical fields")
    if (
        freeze["schema_version"] != _FREEZE_SCHEMA_V3
        or freeze["phase_id"] != _V3_PHASE_ID
        or freeze["algorithm"] != "bfs"
        or freeze["modality"] != "text-state"
        or freeze["source_issue"] != 111
        or freeze["parent_issue"] != 38
    ):
        raise BFSPhaseGateError("BFS v3 freeze manifest has the wrong authority or phase identity")

    data = _mapping(freeze, "data")
    expected_data_fields = {
        "allowed_splits",
        "artifacts",
        "dataset_root",
        "development_counts_by_split_and_difficulty",
        "domains",
        "held_out_split",
        "qualification",
        "split_unit",
        "strata",
    }
    if set(data) != expected_data_fields:
        raise BFSPhaseGateError("BFS v3 data freeze has noncanonical fields")
    if (
        data["allowed_splits"] != ["train", "dev"]
        or data["held_out_split"] != "test"
        or data["split_unit"] != "whole_problem_instance"
        or data["strata"] != list(_DIFFICULTIES)
        or data["domains"] != list(_V3_DOMAINS)
    ):
        raise BFSPhaseGateError("BFS v3 data coverage is not frozen correctly")
    expected_counts = {split: {band: 15 for band in _DIFFICULTIES} for split in ("train", "dev")}
    if data["development_counts_by_split_and_difficulty"] != expected_counts:
        raise BFSPhaseGateError("BFS v3 selected task counts are not the complete 90-cell product")
    artifacts = _validate_artifacts(data, repo_root, schema_name="BFS v3")
    _validate_v3_qualification(_mapping(data, "qualification"), artifacts, repo_root)

    budgets = _mapping(_mapping(freeze, "budgets"), "episode_max_expansions_by_difficulty")
    if budgets != {band: upper for band, (_lower, upper) in _V3_BANDS.items()}:
        raise BFSPhaseGateError("BFS v3 expansion budgets differ from the qualified bands")
    if freeze["seeds"] != _V3_SEEDS:
        raise BFSPhaseGateError("BFS v3 headline seeds differ from the frozen five-seed design")
    primary_model = _mapping(_mapping(freeze, "models"), "primary")
    if primary_model.get("role") != "primary_open_vlm" or primary_model.get("revision") != _V3_MODEL_REVISION:
        raise BFSPhaseGateError("BFS v3 primary model differs from the governed Qwen revision")
    implementation = _mapping(freeze, "implementation")
    if implementation != {
        "corpus_materialization_revision": _V3_CORPUS_MATERIALIZATION_REVISION,
        "preregistration_revision": _V3_PREREGISTRATION_REVISION,
        "process_memory_projection": "bounded_bfs_search_memory_v3",
        "search_episode_harness": "examples.planning_benchmark_slice.search_episode.run_search_episode",
    }:
        raise BFSPhaseGateError("BFS v3 implementation provenance or bounded memory projection has drifted")
    arms = _mapping(_mapping(freeze, "training"), "arms")
    if set(arms) != _TRAINING_ARMS_V3 or arms["process_sft"].get("corpus_view") != "process":
        raise BFSPhaseGateError("BFS v3 training contract must be process-SFT only")
    if "operational_sft" in arms:
        raise BFSPhaseGateError("BFS v3 must not authorize operational-SFT")
    if set(_mapping(freeze, "stop_rules")) != {"ancestor_stop", "invalid", "no_retuning", "pass", "valid_stop"}:
        raise BFSPhaseGateError("BFS v3 stop rules are incomplete")


def _validate_v3_qualification(
    qualification: dict[str, Any],
    artifacts: set[str],
    repo_root: Path,
) -> None:
    expected_fields = {
        "attempt_id",
        "candidate_ceiling_per_domain_split",
        "expansion_bands",
        "gate_receipt_path",
        "outcome",
        "qualification_report_path",
        "selected_manifest_path",
        "selected_task_count",
        "selection_seed",
        "test_data_accessed",
    }
    if set(qualification) != expected_fields:
        raise BFSPhaseGateError("BFS v3 qualification binding has noncanonical fields")
    if (
        qualification["attempt_id"] != "qualification-attempt-002"
        or qualification["outcome"] != "PASS"
        or qualification["selected_task_count"] != 90
        or qualification["selection_seed"] != 111
        or qualification["candidate_ceiling_per_domain_split"] != 500
        or qualification["test_data_accessed"] is not False
        or qualification["expansion_bands"]
        != {band: {"lower": lower, "upper": upper} for band, (lower, upper) in _V3_BANDS.items()}
    ):
        raise BFSPhaseGateError("BFS v3 qualification protocol differs from issue 111")

    bound: dict[str, bytes] = {}
    for name in ("gate_receipt", "qualification_report", "selected_manifest"):
        relative = _text(qualification, f"{name}_path")
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise BFSPhaseGateError("BFS v3 qualification paths must be repository-relative")
        path = repo_root / relative
        if not path.is_file():
            raise BFSPhaseGateError(f"BFS v3 {name.replace('_', ' ')} is missing")
        bound[name] = path.read_bytes()
    if qualification["selected_manifest_path"] not in artifacts:
        raise BFSPhaseGateError("BFS v3 selected manifest is not a frozen data artifact")

    receipt = _json_bytes_object(bound["gate_receipt"], "BFS v3 gate receipt")
    report = _json_bytes_object(bound["qualification_report"], "BFS v3 qualification report")
    if (
        receipt.get("schema_version") != "bfs_pilot_gate_receipt_v3"
        or receipt.get("attempt_id") != qualification["attempt_id"]
        or receipt.get("phase_id") != _V3_PHASE_ID
        or receipt.get("outcome") != "PASS"
        or report.get("schema_version") != "bfs_pilot_qualification_v3"
        or report.get("attempt_id") != qualification["attempt_id"]
        or report.get("phase_id") != _V3_PHASE_ID
        or report.get("outcome") != "PASS"
        or report.get("selected_count") != 90
        or report.get("test_data_accessed") is not False
        or report.get("missing_cells") != []
    ):
        raise BFSPhaseGateError("BFS v3 qualification receipt and report do not prove PASS")
    _validate_v3_selected_manifest(bound["selected_manifest"], artifacts, repo_root)


def _validate_v3_selected_manifest(payload: bytes, artifacts: set[str], repo_root: Path) -> None:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.decode("utf-8").splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise BFSPhaseGateError(f"BFS v3 selected manifest has invalid JSON at line {line_number}") from error
        if not isinstance(row, dict):
            raise BFSPhaseGateError("BFS v3 selected manifest rows must be objects")
        rows.append(row)
    cells = {(row.get("domain_id"), row.get("band"), row.get("split")) for row in rows}
    required = {(domain, band, split) for domain in _V3_DOMAINS for band in _DIFFICULTIES for split in ("train", "dev")}
    if len(rows) != 90 or cells != required:
        raise BFSPhaseGateError("BFS v3 selected manifest does not cover all 90 cells")
    identities: dict[str, str] = {}
    for row in rows:
        band = row["band"]
        count = row.get("expansion_count")
        if (
            row.get("status") != "accepted"
            or row.get("bucket") != band
            or isinstance(count, bool)
            or not isinstance(count, int)
            or not (_V3_BANDS[band][0] <= count <= _V3_BANDS[band][1])
        ):
            raise BFSPhaseGateError("BFS v3 selected manifest contains an unqualified task")
        split = row["split"]
        for field in ("domain_path", "problem_path"):
            path = row.get(field)
            if not isinstance(path, str) or path not in artifacts:
                raise BFSPhaseGateError("BFS v3 selected task is not bound by the freeze artifacts")
        identity = whole_instance_identity(
            repo_root / row["domain_path"],
            repo_root / row["problem_path"],
        )
        if identities.get(identity, split) != split:
            raise BFSPhaseGateError("BFS v3 selected manifest violates whole-instance split isolation")
        identities[identity] = split


def _validate_artifacts(data: dict[str, Any], repo_root: Path, *, schema_name: str) -> set[str]:
    entries = data.get("artifacts")
    if not isinstance(entries, list) or not entries:
        raise BFSPhaseGateError(f"{schema_name} data artifacts must be a non-empty list")
    artifacts: set[str] = set()
    for artifact in entries:
        if not isinstance(artifact, dict) or set(artifact) != {"path"}:
            raise BFSPhaseGateError(f"{schema_name} data artifact entry is malformed")
        relative = _text(artifact, "path")
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise BFSPhaseGateError(f"{schema_name} data artifact path must be repository-relative")
        path = repo_root / relative
        if not path.is_file():
            raise BFSPhaseGateError(f"{schema_name} data artifact is missing: {relative}")
        if relative in artifacts:
            raise BFSPhaseGateError(f"{schema_name} repeats a frozen data artifact: {relative}")
        artifacts.add(relative)
    return artifacts


def _validate_authorization_v3(
    authorization: dict[str, Any],
    freeze: dict[str, Any],
    freeze_path: Path,
    repo_root: Path,
) -> None:
    expected_fields = {
        "authorization_id",
        "authorized_stages",
        "contract_id",
        "downstream_issues",
        "freeze_manifest_path",
        "outcome",
        "parent_issue",
        "phase_id",
        "schema_version",
        "scientific_completion",
        "source_issue",
    }
    if set(authorization) != expected_fields:
        raise BFSPhaseGateError("BFS v3 authorization manifest has noncanonical fields")
    if (
        authorization["schema_version"] != _AUTHORIZATION_SCHEMA_V3
        or authorization["outcome"] != "PASS"
        or authorization["scientific_completion"] is not False
        or authorization["source_issue"] != 111
        or authorization["parent_issue"] != 38
        or authorization["phase_id"] != _V3_PHASE_ID
        or authorization["phase_id"] != freeze["phase_id"]
        or authorization["contract_id"] != freeze["phase_id"]
        or authorization["authorized_stages"] != list(_AUTHORIZED_STAGES_V3)
        or authorization["downstream_issues"] != list(_DOWNSTREAM_ISSUES_V3)
    ):
        raise BFSPhaseGateError("BFS v3 authorization manifest does not authorize this phase")
    expected_freeze_path = (repo_root / _text(authorization, "freeze_manifest_path")).resolve()
    if freeze_path != expected_freeze_path:
        raise BFSPhaseGateError("BFS v3 authorization points to a different freeze manifest")


def _load_json_object(path: Path, name: str) -> tuple[bytes, dict[str, Any]]:
    try:
        payload = path.read_bytes()
        parsed: Any = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BFSPhaseGateError(f"{name} cannot be loaded: {path}") from error
    if not isinstance(parsed, dict):
        raise BFSPhaseGateError(f"{name} must contain a JSON object")
    return payload, parsed


def _json_bytes_object(payload: bytes, name: str) -> dict[str, Any]:
    try:
        parsed: Any = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BFSPhaseGateError(f"{name} is invalid JSON") from error
    if not isinstance(parsed, dict):
        raise BFSPhaseGateError(f"{name} must contain a JSON object")
    return parsed


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


__all__ = ["BFSPhaseGate", "BFSPhaseGateError", "load_bfs_phase_gate"]
