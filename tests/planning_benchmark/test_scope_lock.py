from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "planning"
CURRENT_SCOPE_LOCK_FIXTURE = FIXTURE_DIR / "scope_lock_current.md"
RETIRED_ALGORITHMS_FIXTURE = FIXTURE_DIR / "scope_lock_retired_algorithms.md"
MISSING_WORLD_MODEL_FIXTURE = FIXTURE_DIR / "scope_lock_missing_world_model.md"


def run_scope_lock(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "examples.planning_benchmark_slice.scope_lock", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def test_current_scope_lock_fixture_validates_exact_bfs_iw_matrix() -> None:
    result = run_scope_lock("validate", "--path", str(CURRENT_SCOPE_LOCK_FIXTURE), "--json")

    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert result.stderr == ""
    assert payload["valid"] is True
    assert payload["required_decisions_present"] is True
    assert payload["missing_decisions"] == []
    assert payload["algorithm_matrix_valid"] is True
    assert payload["declared_algorithms"] == ["bfs", "iterated_width"]
    assert "frozen_world_model_decision" in payload["checked_decisions"]


def test_scope_lock_rejects_retired_algorithms() -> None:
    result = run_scope_lock("validate", "--path", str(RETIRED_ALGORITHMS_FIXTURE), "--json")

    payload = json.loads(result.stdout)

    assert result.returncode != 0
    assert payload["valid"] is False
    assert payload["algorithm_matrix_valid"] is False
    assert payload["declared_algorithms"] == ["bfs", "fast_forward", "graphplan", "iterated_width"]
    assert payload["missing_decisions"] == ["algorithm_matrix_decision"]
    assert "algorithm_matrix_decision" in result.stderr


def test_missing_world_model_decision_fails() -> None:
    result = run_scope_lock("validate", "--path", str(MISSING_WORLD_MODEL_FIXTURE), "--json")

    payload = json.loads(result.stdout)

    assert result.returncode != 0
    assert payload["valid"] is False
    assert payload["required_decisions_present"] is False
    assert payload["algorithm_matrix_valid"] is True
    assert payload["missing_decisions"] == ["frozen_world_model_decision"]
    assert "frozen_world_model_decision" in result.stderr
