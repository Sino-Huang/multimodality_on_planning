from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCOPE_LOCK_PATH = REPO_ROOT / "doc" / "detailed_implementation_summary" / "phase1_scope_lock_and_diagnostic_summary.md"
MISSING_WORLD_MODEL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "scope_lock_missing_world_model.md"


def run_scope_lock(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "examples.planning_benchmark_slice.scope_lock", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def test_scope_lock_artifact_validates() -> None:
    result = run_scope_lock("validate", "--path", str(SCOPE_LOCK_PATH), "--json")

    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert result.stderr == ""
    assert payload["valid"] is True
    assert payload["required_decisions_present"] is True
    assert payload["missing_decisions"] == []
    assert "frozen_world_model_decision" in payload["checked_decisions"]


def test_missing_world_model_decision_fails() -> None:
    result = run_scope_lock("validate", "--path", str(MISSING_WORLD_MODEL_FIXTURE), "--json")

    payload = json.loads(result.stdout)

    assert result.returncode != 0
    assert payload["valid"] is False
    assert payload["required_decisions_present"] is False
    assert "frozen_world_model_decision" in payload["missing_decisions"]
    assert "frozen_world_model_decision" in result.stderr
