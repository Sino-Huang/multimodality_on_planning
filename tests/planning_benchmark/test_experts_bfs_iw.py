from __future__ import annotations

import filecmp
import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.generate_experts import generate_experts
from examples.planning_benchmark_slice.trajectory_schema import validate_path


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "planning"
NONTRIVIAL_FIXTURE = FIXTURE_DIR / "blocksworld_nontrivial.json"


def _run_generate(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "examples.planning_benchmark_slice.generate_experts", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def _load_steps(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload["steps"])


def test_bfs_and_iw_generators_create_valid_solving_trajectories(tmp_path: Path) -> None:
    output = tmp_path / "experts"
    payload = generate_experts(
        fixture_path=NONTRIVIAL_FIXTURE,
        algorithms=("bfs", "iterated_width"),
        output_dir=output,
    )

    assert payload["valid"] is True
    assert payload["algorithms"]["bfs"]["trajectory_count"] == 1
    assert payload["algorithms"]["iterated_width"]["trajectory_count"] == 1
    assert payload["algorithms"]["bfs"]["selected_actions"] == ["pickup(a)", "stack(a,b)"]
    assert payload["algorithms"]["iterated_width"]["selected_actions"] == ["pickup(a)", "stack(a,b)"]

    validation = validate_path(output)
    assert validation["valid"] is True
    assert validation["by_algorithm"] == {"bfs": 2, "iterated_width": 2}
    assert validation["trajectory_count"] == 4


def test_bfs_trace_preserves_fifo_frontier_order_and_sorted_sets(tmp_path: Path) -> None:
    output = tmp_path / "experts"
    generate_experts(fixture_path=NONTRIVIAL_FIXTURE, algorithms=("bfs",), output_dir=output)
    steps = _load_steps(output / "blocksworld-dev-fixture-0000__bfs.json")
    first_step = steps[0]
    bfs = first_step["bfs"]

    successors = {successor["action"]: successor for successor in bfs["successors"]}
    expected_fifo_after = [
        successors["pickup(a)"]["state_id"],
        successors["pickup(b)"]["state_id"],
        successors["pickup(c)"]["state_id"],
    ]

    assert bfs["frontier_before"] == [first_step["state_id"]]
    assert bfs["frontier_after"] == expected_fifo_after
    assert bfs["visited_before"] == sorted(bfs["visited_before"])
    assert bfs["visited_after"] == sorted(bfs["visited_after"])
    assert bfs["dequeued_state_id"] == first_step["state_id"]
    assert bfs["tie_break_rule"] == "legal_actions_sorted_by_canonical_action_string"


def test_iterated_width_trace_records_novelty_fields(tmp_path: Path) -> None:
    output = tmp_path / "experts"
    generate_experts(fixture_path=NONTRIVIAL_FIXTURE, algorithms=("iterated_width",), output_dir=output)
    steps = _load_steps(output / "blocksworld-dev-fixture-0000__iterated_width.json")
    first_step = steps[0]
    iw = first_step["iterated_width"]

    assert iw["width"] == 1
    assert iw["decision"] == "expand"
    assert iw["novelty_table_before"] == []
    assert iw["novel_item"] == "arm-empty"
    assert iw["novelty_table_after"] == first_step["state_atoms"]
    assert iw["atoms"] == first_step["state_atoms"]
    assert iw["tuples"] == first_step["state_atoms"]
    assert iw["tie_break_rule"] == "legal_actions_sorted_by_canonical_action_string"


def test_generate_experts_cli_writes_json_and_rejects_unsupported_algorithms(tmp_path: Path) -> None:
    output = tmp_path / "experts"
    result = _run_generate(
        "--fixture",
        str(NONTRIVIAL_FIXTURE),
        "--algorithms",
        "bfs",
        "iterated_width",
        "--output",
        str(output),
        "--json",
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert result.stderr == ""
    assert payload["valid"] is True
    assert (output / "blocksworld-dev-fixture-0000__bfs.json").exists()
    assert (output / "blocksworld-dev-fixture-0000__iterated_width.json").exists()

    unsupported = _run_generate(
        "--fixture",
        str(NONTRIVIAL_FIXTURE),
        "--algorithms",
        "astar",
        "--output",
        str(tmp_path / "unsupported"),
        "--json",
    )
    unsupported_payload = json.loads(unsupported.stdout)
    assert unsupported.returncode != 0
    assert unsupported_payload["valid"] is False
    assert unsupported_payload["error"]["code"] == "unsupported_algorithm"
    assert "unsupported algorithms" in unsupported_payload["error"]["message"]


def test_generate_experts_outputs_are_byte_identical_across_runs(tmp_path: Path) -> None:
    output_a = tmp_path / "run_a"
    output_b = tmp_path / "run_b"
    generate_experts(fixture_path=NONTRIVIAL_FIXTURE, algorithms=("bfs", "iterated_width"), output_dir=output_a)
    generate_experts(fixture_path=NONTRIVIAL_FIXTURE, algorithms=("bfs", "iterated_width"), output_dir=output_b)

    comparison = filecmp.dircmp(output_a, output_b)
    assert comparison.left_only == []
    assert comparison.right_only == []
    assert comparison.diff_files == []
