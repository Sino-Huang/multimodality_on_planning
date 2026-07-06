from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.trajectory_schema import (
    SCHEMA_VERSION,
    canonical_json_text,
    canonical_mutex_pairs,
    canonical_novelty_table,
    canonicalize_trajectory_step,
    validate_path,
)
from examples.planning_benchmark_slice.zero_shot import ALGORITHMS


REPO_ROOT = Path(__file__).resolve().parents[2]
TRAJECTORY_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "planning" / "trajectories"
VALID_DIR = TRAJECTORY_FIXTURE_DIR / "valid"


def _run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "examples.planning_benchmark_slice.validate_trajectories", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def test_valid_trajectory_fixture_directory_reports_all_algorithms() -> None:
    payload = validate_path(VALID_DIR)

    assert payload["valid"] is True
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["trajectory_count"] == 4
    assert payload["algorithms_validated"] == list(ALGORITHMS)
    assert payload["by_algorithm"] == {algorithm: 1 for algorithm in ALGORITHMS}
    assert payload["error_count"] == 0


def test_validator_cli_accepts_directory_and_emits_json_only_on_success() -> None:
    result = _run_validator("--input", str(VALID_DIR), "--json")

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert result.stderr == ""
    assert payload["valid"] is True
    assert payload["algorithms_validated"] == list(ALGORITHMS)
    assert payload["file_count"] == 4


def test_validator_accepts_single_json_and_jsonl_files() -> None:
    bfs = _run_validator("--input", str(VALID_DIR / "bfs.json"), "--json")
    iw = _run_validator("--input", str(VALID_DIR / "iterated_width.jsonl"), "--json")

    bfs_payload = json.loads(bfs.stdout)
    iw_payload = json.loads(iw.stdout)

    assert bfs.returncode == 0
    assert bfs_payload["algorithms_validated"] == ["bfs"]
    assert iw.returncode == 0
    assert iw_payload["algorithms_validated"] == ["iterated_width"]


def test_missing_algorithm_fields_are_structured_and_path_specific() -> None:
    cases = {
        "invalid_missing_bfs_frontier": "bfs.frontier_before",
        "invalid_missing_fast_forward_heuristic": "fast_forward.heuristic_value",
        "invalid_missing_iterated_width_novelty": "iterated_width.novelty_table_after",
        "invalid_missing_graphplan_mutex_layer": "graphplan.mutex_pairs",
    }

    for directory, expected_path in cases.items():
        result = _run_validator("--input", str(TRAJECTORY_FIXTURE_DIR / directory), "--json")
        payload = json.loads(result.stdout)
        paths = [error["path"] for error in payload["errors"]]

        assert result.returncode != 0
        assert payload["valid"] is False
        assert expected_path in paths
        assert expected_path in result.stderr
        assert "Traceback" not in result.stdout + result.stderr


def test_deterministic_serialization_helpers_sort_unordered_fields() -> None:
    assert canonical_novelty_table([{ "clear(b)", "on-table(a)"}, ["clear(a)", "arm-empty"], "holding(a)"]) == [
        "holding(a)",
        ["arm-empty", "clear(a)"],
        ["clear(b)", "on-table(a)"],
    ]
    assert canonical_mutex_pairs([["pickup(c)", "pickup(a)"], ("pickup(b)", "pickup(a)")]) == [
        ["pickup(a)", "pickup(b)"],
        ["pickup(a)", "pickup(c)"],
    ]


def test_canonicalize_bfs_preserves_fifo_frontier_order_but_sorts_visited_sets() -> None:
    raw_step = {
        "trajectory_id": "t",
        "algorithm": "bfs",
        "domain": "blocksworld",
        "instance_id": "i",
        "step_index": 0,
        "state_id": "state_z",
        "state_atoms": [],
        "goal_atoms": [],
        "legal_actions": [],
        "selected_action": None,
        "is_terminal": False,
        "metadata": {},
        "bfs": {
            "frontier_before": ["state_z", "state_a"],
            "frontier_after": ["state_m", "state_b", "state_y"],
            "visited_before": ["state_z", "state_a"],
            "visited_after": ["state_m", "state_b", "state_y"],
            "dequeued_state_id": "state_z",
            "successors": [
                {"action": "pickup(c)", "state_id": "state_y", "state_atoms": ["clear(c)", "arm-empty"]},
                {"action": "pickup(a)", "state_id": "state_b", "state_atoms": ["clear(b)", "arm-empty"]},
            ],
        },
    }

    canonical = canonicalize_trajectory_step(raw_step)

    assert canonical["bfs"]["frontier_before"] == ["state_z", "state_a"]
    assert canonical["bfs"]["frontier_after"] == ["state_m", "state_b", "state_y"]
    assert canonical["bfs"]["visited_before"] == ["state_a", "state_z"]
    assert canonical["bfs"]["visited_after"] == ["state_b", "state_m", "state_y"]
    assert [successor["action"] for successor in canonical["bfs"]["successors"]] == ["pickup(a)", "pickup(c)"]


def test_canonicalize_trajectory_step_sorts_atoms_actions_bfs_and_graphplan_fields() -> None:
    raw_step = {
        "trajectory_id": "t",
        "algorithm": "graphplan",
        "domain": "blocksworld",
        "instance_id": "i",
        "step_index": 0,
        "state_id": "s",
        "state_atoms": ["clear(b)", "arm-empty"],
        "goal_atoms": ["on(a,b)", "clear(a)"],
        "legal_actions": ["pickup(c)", "pickup(a)"],
        "selected_action": "pickup(a)",
        "is_terminal": False,
        "metadata": {"z": 1, "a": 2},
        "graphplan": {
            "proposition_layers": [
                {"layer_index": 1, "atoms": ["holding(a)", "clear(b)"]},
                {"layer_index": 0, "atoms": ["clear(b)", "arm-empty"]},
            ],
            "action_layers": [{"layer_index": 0, "actions": ["pickup(c)", "pickup(a)"]}],
            "mutex_pairs": [["pickup(c)", "pickup(a)"]],
            "extraction": {"no_goods": []},
        },
    }

    canonical = canonicalize_trajectory_step(raw_step)

    assert canonical["state_atoms"] == ["arm-empty", "clear(b)"]
    assert canonical["goal_atoms"] == ["clear(a)", "on(a,b)"]
    assert canonical["legal_actions"] == ["pickup(a)", "pickup(c)"]
    assert canonical["graphplan"]["mutex_pairs"] == [["pickup(a)", "pickup(c)"]]
    assert canonical["graphplan"]["proposition_layers"][0]["layer_index"] == 0
    assert canonical["graphplan"]["action_layers"][0]["actions"] == ["pickup(a)", "pickup(c)"]
    assert json.loads(canonical_json_text(canonical))["metadata"] == {"a": 2, "z": 1}
