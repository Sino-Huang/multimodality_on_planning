"""Create the issue-54 v4 contract-repair freeze and authorization."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_V3_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v3.json"
_V4_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v4.json"
_V4_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v4.json"
_PHASE_ID = "issue-54-bfs-contract-repair-v4"
_REPAIR_REVISION = "aab79248ee5889ec3d677d0356d3cbd0c7e485a5"


def main() -> int:
    if _V4_FREEZE.exists() or _V4_AUTHORIZATION.exists():
        raise FileExistsError("BFS v4 freeze or authorization already exists")
    freeze = deepcopy(_json_object(_V3_FREEZE))
    freeze.update(
        {
            "budgets": {
                **freeze["budgets"],
                "accepted_delta_limit": 16,
                "max_model_input_bytes": 3_840,
                "max_output_tokens_per_operation": 384,
            },
            "implementation": {
                "contract_repair_revision": _REPAIR_REVISION,
                "corpus_materialization_revision": freeze["implementation"]["corpus_materialization_revision"],
                "deterministic_invalid_operation_policy": "charge_once_and_terminate",
                "evaluation_request_schema": "model_search_episode_request_v2",
                "process_memory_projection": "bounded_bfs_search_memory_v3",
                "search_episode_harness": (
                    "examples.planning_benchmark_slice.model_search_episode.run_model_search_episode"
                ),
            },
            "phase_id": _PHASE_ID,
            "repair": {
                "adapter_probe_changed_output": True,
                "inherited_training_phase_id": "issue-111-bfs-expansion-qualified-pilot-v3",
                "previous_gate_outcome": "VALID_STOP",
                "previous_phase_id": "issue-111-bfs-expansion-qualified-pilot-v3",
                "retained_decision_count": 404_107,
                "retained_deterministic_replay_count": 402_037,
                "retained_input_contract": "rolling_search_context",
                "teacher_model_input_max_bytes": 3_840,
                "teacher_target_count": 26_492,
                "teacher_target_max_tokens": 308,
                "teacher_targets_over_previous_budget": 1_161,
                "teacher_targets_over_successor_budget": 0,
            },
            "schema_version": "bfs_phase_freeze_v4",
            "source_issue": 54,
        }
    )
    freeze["training"]["inherited_process_sft"] = {
        "checkpoint_steps": [420, 840, 1260],
        "parameter_updates_in_v4": False,
        "source_attempt_pattern": "issue54-v3-process-sft-seed-{seed}-attempt-002",
        "source_phase_id": "issue-111-bfs-expansion-qualified-pilot-v3",
    }
    freeze["stop_rules"]["pass"] = (
        "PASS requires exact-reference validity and the inherited process-SFT checkpoints evaluated through the "
        "repaired bounded input contract to pass every frozen threshold."
    )
    authorization = {
        "authorization_id": "issue-54-bfs-contract-repair-authorization-v4",
        "authorized_stages": ["base_and_references", "process_sft_and_sanity_gate"],
        "contract_id": _PHASE_ID,
        "downstream_issues": [54],
        "freeze_manifest_path": "configs/experiments/bfs_phase_freeze_v4.json",
        "outcome": "PASS",
        "parent_issue": 38,
        "phase_id": _PHASE_ID,
        "schema_version": "bfs_phase_authorization_v4",
        "scientific_completion": False,
        "source_issue": 54,
    }
    _V4_FREEZE.write_bytes(_canonical_bytes(freeze))
    _V4_AUTHORIZATION.write_bytes(_canonical_bytes(authorization))
    print(
        json.dumps(
            {
                "authorization_manifest": _relative(_V4_AUTHORIZATION),
                "freeze_manifest": _relative(_V4_FREEZE),
            },
            sort_keys=True,
        )
    )
    return 0


def _relative(path: Path) -> str:
    return path.resolve().relative_to(_REPO_ROOT).as_posix()


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
