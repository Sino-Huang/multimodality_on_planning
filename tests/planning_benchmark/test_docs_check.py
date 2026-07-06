from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.docs_check import validate_docs, validate_no_phase4_claims, validate_phase


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_docs_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "examples.planning_benchmark_slice.docs_check", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def test_validate_each_closeout_phase() -> None:
    for phase in (1, 2, 3):
        payload = validate_phase(phase)
        assert payload["valid"] is True
        assert payload["missing_documents"] == []
        assert payload["missing_evidence"] == []
        assert payload["missing_phrases"] == []


def test_no_phase4_claims_guard_passes() -> None:
    payload = validate_no_phase4_claims()

    assert payload["valid"] is True
    assert payload["required_missing"] == []
    assert payload["forbidden_hits"] == []


def test_docs_check_cli_phase_json() -> None:
    result = _run_docs_check("--phase", "1", "2", "3", "--json")

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert result.stderr == ""
    assert payload["valid"] is True
    assert payload["checked_phases"] == [1, 2, 3]
    assert payload["phase_results"]["1"]["valid"] is True
    assert payload["phase_results"]["2"]["valid"] is True
    assert payload["phase_results"]["3"]["valid"] is True


def test_docs_check_cli_no_phase4_claims_json() -> None:
    result = _run_docs_check("--no-phase4-claims", "--json")

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert result.stderr == ""
    assert payload["valid"] is True
    assert payload["checked_phases"] == []
    assert payload["no_phase4_claims"]["valid"] is True


def test_validate_docs_defaults_to_all_phases_when_no_flags() -> None:
    payload = validate_docs(phases=(), no_phase4_claims=False)

    assert payload["valid"] is True
    assert payload["checked_phases"] == [1, 2, 3]
