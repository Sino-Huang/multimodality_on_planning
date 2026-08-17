from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = REPOSITORY_ROOT / "data/phase3_supervised_planning/summary.json"
VISION_VALIDATION_PATH = (
    REPOSITORY_ROOT / "data/phase3_supervised_planning/diagnostics/vision_validation.jsonl"
)


def test_snapshot_cli_writes_observation_only_current_contract(tmp_path: Path) -> None:
    # Given: the checked-in Phase 3 summary and vision diagnostics.
    output_path = tmp_path / "input_contract.json"

    # When: the read-only readiness snapshot command observes them.
    result = _run_snapshot(output_path)

    # Then: it records the exact incomplete corpus and Qwen handoff contract.
    assert result.returncode == 0, result.stderr
    snapshot = json.loads(output_path.read_text(encoding="utf-8"))
    assert snapshot["phase3"] == {
        "active_planners": ["gbfs", "ff", "iw", "graphplan"],
        "current_bfs_examples": 411,
        "current_iw_examples": 0,
        "current_vision_alignment_rows": 0,
    }
    assert snapshot["observation"] == {
        "readiness_approved": False,
        "status": "observed_not_ready",
    }
    assert snapshot["qwen_vl"] == {
        "conversations": {
            "assistant_role": "assistant",
            "human_role": "human",
            "required_human_image_tokens": 1,
        },
        "image": {
            "cardinality": 1,
            "path_kind": "relative_string",
        },
    }


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("emitted_examples", None),
        ("planner_status_summary", []),
    ],
)
def test_snapshot_cli_rejects_invalid_required_summary_field(
    tmp_path: Path, field: str, replacement: list[str] | None
) -> None:
    # Given: a copied summary whose required field is absent or has the wrong JSON type.
    invalid_summary = tmp_path / "summary.json"
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    if replacement is None:
        del summary[field]
    else:
        summary[field] = replacement
    invalid_summary.write_text(json.dumps(summary), encoding="utf-8")

    # When: the command observes the malformed source summary.
    result = _run_snapshot(
        tmp_path / "input_contract.json", summary_path=invalid_summary
    )

    # Then: it fails closed and identifies the invalid field.
    assert result.returncode != 0
    assert field in result.stderr


def test_snapshot_cli_rejects_missing_bfs_success_count_without_output(tmp_path: Path) -> None:
    # Given: a copied summary without the required BFS success count.
    invalid_summary = tmp_path / "summary.json"
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    del summary["planner_status_summary"]["bfs"]["success_full_trace"]
    invalid_summary.write_text(json.dumps(summary), encoding="utf-8")
    output_path = tmp_path / "input_contract.json"

    # When: the command observes the malformed source summary.
    result = _run_snapshot(output_path, summary_path=invalid_summary)

    # Then: it fails closed before writing a readiness snapshot.
    assert result.returncode != 0
    assert "planner_status_summary.bfs.success_full_trace" in result.stderr
    assert not output_path.exists()


def _run_snapshot(output_path: Path, *, summary_path: Path = SUMMARY_PATH) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.phase3.cgas_readiness_snapshot",
            "--summary-path",
            str(summary_path),
            "--vision-validation-path",
            str(VISION_VALIDATION_PATH),
            "--output-path",
            str(output_path),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
