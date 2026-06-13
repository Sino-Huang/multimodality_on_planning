from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = REPO_ROOT / "data" / "curriculum_pddl"


def run_example(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "examples.planning_benchmark_slice", *args],
        cwd=cwd or REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def test_example_slice_outputs_real_blocksworld_instance() -> None:
    result = run_example(
        "--dataset",
        str(DATASET_ROOT),
        "--domain",
        "blocksworld",
        "--split",
        "dev",
        "--index",
        "0",
        "--json",
    )

    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["instance_id"] == "blocksworld-dev-easy-0000"
    assert payload["domain"] == "blocksworld"
    assert payload["split"] == "dev"
    assert "(:action pickup" in payload["domain_pddl"]
    assert payload["goal_or_problem_view"]["problem_name"] == "BW-rand-4"
    assert payload["goal_or_problem_view"]["goal_block"] == "(:goal\n(and)\n)"
    assert payload["action_vocabulary"] == ["pickup", "putdown", "stack", "unstack"]
    assert len(payload["render_frames"]) >= 1
    assert Path(payload["render_trace"]).exists()
    for frame_path in payload["render_frames"]:
        assert Path(frame_path).exists()
    assert payload["render_trace_payload"]["visualStages"]


def test_missing_summary_fails_clearly(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    dataset_root.mkdir()

    result = run_example(
        "--dataset",
        str(dataset_root),
        "--domain",
        "blocksworld",
        "--split",
        "dev",
        "--index",
        "0",
        "--json",
    )

    assert result.returncode != 0
    assert "summary.json is missing" in result.stderr


@pytest.mark.parametrize(
    ("domain", "split", "index", "message"),
    [
        ("not-a-domain", "dev", 0, "invalid domain"),
        ("blocksworld", "not-a-split", 0, "invalid split"),
        ("blocksworld", "dev", 999, "out of range"),
    ],
)
def test_invalid_selection_failures(domain: str, split: str, index: int, message: str) -> None:
    result = run_example(
        "--dataset",
        str(DATASET_ROOT),
        "--domain",
        domain,
        "--split",
        split,
        "--index",
        str(index),
        "--json",
    )

    assert result.returncode != 0
    assert message in result.stderr
