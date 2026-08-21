"""Create issue-111 v3 freeze and authorization after a published qualification PASS."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DATA_ROOT = _REPO_ROOT / "data" / "bfs_pilot_v3"
_V1_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json"
_V3_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v3.json"
_V3_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v3.json"
_PHASE_ID = "issue-111-bfs-expansion-qualified-pilot-v3"
_PREREGISTRATION_REVISION = "4da3ae71531e1131c19ce552f41426241ed4308c"


def main() -> int:
    if _V3_FREEZE.exists() or _V3_AUTHORIZATION.exists():
        raise FileExistsError("BFS v3 freeze or authorization already exists")
    report_path = _DATA_ROOT / "qualification-attempt-002" / "qualification-report.json"
    receipt_path = _DATA_ROOT / "qualification-attempt-002" / "gate-receipt.json"
    manifest_path = _DATA_ROOT / "selected-manifest.jsonl"
    report = _json_object(report_path)
    receipt = _json_object(receipt_path)
    selected_rows = _jsonl_objects(manifest_path)
    selected_manifest_sha256 = _sha256(manifest_path.read_bytes())
    if (
        report.get("outcome") != "PASS"
        or report.get("selected_count") != 90
        or report.get("test_data_accessed") is not False
        or receipt.get("outcome") != "PASS"
        or receipt.get("selected_manifest_sha256") != selected_manifest_sha256
        or len(selected_rows) != 90
    ):
        raise ValueError("published BFS v3 qualification is not a complete PASS")

    artifacts = [
        _artifact(receipt_path),
        _artifact(report_path),
        _artifact(manifest_path),
        _artifact(_REPO_ROOT / "src" / "data_collect" / "configs" / "curriculum_15_domains.yaml"),
    ]
    task_paths = sorted(
        {_REPO_ROOT / str(row[field]) for row in selected_rows for field in ("domain_path", "problem_path")}
    )
    if len(task_paths) != 180:
        raise ValueError("published BFS v3 release must contain 180 domain/problem files")
    artifacts.extend(_artifact(path) for path in task_paths)

    freeze = deepcopy(_json_object(_V1_FREEZE))
    freeze.update(
        {
            "data": {
                "allowed_splits": ["train", "dev"],
                "artifacts": sorted(artifacts, key=lambda item: item["path"]),
                "dataset_root": "data/bfs_pilot_v3",
                "development_counts_by_split_and_difficulty": {
                    split: {difficulty: 15 for difficulty in ("easy", "medium", "hard")} for split in ("train", "dev")
                },
                "domains": [
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
                ],
                "held_out_split": "test",
                "qualification": {
                    "attempt_id": "qualification-attempt-002",
                    "candidate_ceiling_per_domain_split": 500,
                    "expansion_bands": report["bands"],
                    "gate_receipt_path": _relative(receipt_path),
                    "gate_receipt_sha256": _sha256(receipt_path.read_bytes()),
                    "outcome": "PASS",
                    "qualification_report_path": _relative(report_path),
                    "qualification_report_sha256": _sha256(report_path.read_bytes()),
                    "selected_manifest_path": _relative(manifest_path),
                    "selected_manifest_sha256": selected_manifest_sha256,
                    "selected_task_count": 90,
                    "selection_seed": 111,
                    "test_data_accessed": False,
                },
                "split_unit": "whole_problem_instance",
                "strata": ["easy", "medium", "hard"],
            },
            "implementation": {
                "preregistration_revision": _PREREGISTRATION_REVISION,
                "search_episode_harness": "examples.planning_benchmark_slice.search_episode.run_search_episode",
            },
            "phase_id": _PHASE_ID,
            "schema_version": "bfs_phase_freeze_v3",
            "source_issue": 111,
        }
    )
    del freeze["training"]["arms"]["operational_sft"]
    freeze["thresholds"].pop("operational_process_record_contamination")
    freeze["stop_rules"]["pass"] = (
        "PASS requires qualification coverage, exact FIFO replay for all 90 tasks, split isolation, "
        "process-only corpus regeneration, and every applicable frozen threshold to pass."
    )
    freeze_bytes = _canonical_bytes(freeze)
    authorization = {
        "authorization_id": "issue-111-bfs-expansion-qualified-pilot-authorization-v3",
        "authorized_stages": [
            "trace_generation",
            "corpus_release",
            "base_and_references",
            "process_sft_and_sanity_gate",
        ],
        "contract_id": _PHASE_ID,
        "downstream_issues": [54],
        "freeze_manifest_path": "configs/experiments/bfs_phase_freeze_v3.json",
        "freeze_manifest_sha256": _sha256(freeze_bytes),
        "outcome": "PASS",
        "parent_issue": 38,
        "phase_id": _PHASE_ID,
        "schema_version": "bfs_phase_authorization_v3",
        "scientific_completion": False,
        "source_issue": 111,
    }
    _V3_FREEZE.write_bytes(freeze_bytes)
    _V3_AUTHORIZATION.write_bytes(_canonical_bytes(authorization))
    print(
        json.dumps(
            {
                "authorization_manifest": _relative(_V3_AUTHORIZATION),
                "freeze_manifest": _relative(_V3_FREEZE),
                "freeze_manifest_sha256": authorization["freeze_manifest_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


def _artifact(path: Path) -> dict[str, str]:
    return {"path": _relative(path), "sha256": _sha256(path.read_bytes())}


def _relative(path: Path) -> str:
    return path.resolve().relative_to(_REPO_ROOT).as_posix()


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"expected JSON objects: {path}")
    return rows


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
