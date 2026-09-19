"""Create the 8,192-token observable BFS v6 freeze after qualification PASS."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DATA_ROOT = _REPO_ROOT / "data" / "bfs_pilot_v6"
_V4_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v4.json"
_V6_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v6.json"
_V6_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v6.json"
_PHASE_ID = "issue-111-bfs-observable-process-pilot-v6"


def main() -> int:
    if _V6_FREEZE.exists() or _V6_AUTHORIZATION.exists():
        raise FileExistsError("BFS v6 freeze or authorization already exists")
    attempt_root = _DATA_ROOT / "qualification-attempt-004"
    report_path = attempt_root / "qualification-report.json"
    receipt_path = attempt_root / "gate-receipt.json"
    manifest_path = _DATA_ROOT / "selected-manifest.jsonl"
    report = _json_object(report_path)
    receipt = _json_object(receipt_path)
    rows = _jsonl_objects(manifest_path)
    if (
        report.get("outcome") != "PASS"
        or report.get("selected_count") != 90
        or report.get("semantic_split_overlap_count") != 0
        or report.get("max_context_tokens") != 8_192
        or report.get("max_input_tokens") != 7_808
        or report.get("max_output_tokens") != 384
        or receipt.get("outcome") != "PASS"
        or len(rows) != 90
    ):
        raise ValueError("published BFS v6 qualification is not a complete observable PASS")

    task_paths = sorted({_REPO_ROOT / row[field] for row in rows for field in ("domain_path", "problem_path")})
    if len(task_paths) != 180 or not all(path.is_file() for path in task_paths):
        raise ValueError("published BFS v6 release must contain 180 task files")
    artifacts = [receipt_path, report_path, manifest_path, *task_paths]

    freeze = deepcopy(_json_object(_V4_FREEZE))
    freeze.pop("repair")
    freeze.update(
        {
            "data": {
                "allowed_splits": ["train", "dev"],
                "artifacts": [{"path": _relative(path)} for path in sorted(artifacts)],
                "dataset_root": "data/bfs_pilot_v6",
                "development_counts_by_split_and_difficulty": {
                    split: {difficulty: 15 for difficulty in ("easy", "medium", "hard")}
                    for split in ("train", "dev")
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
                    "attempt_id": "qualification-attempt-004",
                    "candidate_ceiling_per_domain_split": 500,
                    "expansion_bands": report["bands"],
                    "gate_receipt_path": _relative(receipt_path),
                    "outcome": "PASS",
                    "qualification_report_path": _relative(report_path),
                    "selected_manifest_path": _relative(manifest_path),
                    "selected_task_count": 90,
                    "selection_seed": 111,
                    "test_data_accessed": False,
                },
                "split_unit": "semantic_task_identity",
                "strata": ["easy", "medium", "hard"],
            },
            "implementation": {
                "deterministic_invalid_operation_policy": "charge_once_and_terminate",
                "evaluation_request_schema": "model_search_episode_request_v3",
                "process_memory_projection": "bounded_bfs_search_memory_v4",
                "search_episode_harness": (
                    "examples.planning_benchmark_slice.model_search_episode.run_model_search_episode"
                ),
            },
            "phase_id": _PHASE_ID,
            "schema_version": "bfs_phase_freeze_v6",
            "source_issue": 111,
        }
    )
    freeze["budgets"]["max_context_tokens"] = 8_192
    freeze["training"].pop("inherited_process_sft", None)
    freeze["stop_rules"]["pass"] = (
        "PASS requires all 90 observable teacher traces, semantic split isolation, zero canonical "
        "input overlap, strict token budgets, deterministic regeneration, and every frozen threshold."
    )
    authorization = {
        "authorization_id": "issue-111-bfs-observable-process-pilot-authorization-v6",
        "authorized_stages": [
            "trace_generation",
            "corpus_release",
            "base_and_references",
            "process_sft_and_sanity_gate",
        ],
        "contract_id": _PHASE_ID,
        "downstream_issues": [54],
        "freeze_manifest_path": "configs/experiments/bfs_phase_freeze_v6.json",
        "outcome": "PASS",
        "parent_issue": 38,
        "phase_id": _PHASE_ID,
        "schema_version": "bfs_phase_authorization_v6",
        "scientific_completion": False,
        "source_issue": 111,
    }
    _V6_FREEZE.write_bytes(_canonical_bytes(freeze))
    _V6_AUTHORIZATION.write_bytes(_canonical_bytes(authorization))
    print(json.dumps({"freeze": _relative(_V6_FREEZE), "authorization": _relative(_V6_AUTHORIZATION)}, sort_keys=True))
    return 0


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
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode()


if __name__ == "__main__":
    raise SystemExit(main())
