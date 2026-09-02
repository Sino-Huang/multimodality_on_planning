from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.run_bfs_batched_rollout import _atomic_write, _prepare_output_root

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts" / "run_bfs_v8_evaluation.sh"


def test_v8_helper_is_executable_valid_bash_and_launches_both_a100_shards() -> None:
    assert HELPER.stat().st_mode & 0o111
    subprocess.run(("bash", "-n", str(HELPER)), check=True)
    source = HELPER.read_text(encoding="utf-8")
    assert "launch_shard 0 cuda:0" in source
    assert "launch_shard 1 cuda:1" in source
    assert "prepare_bfs_v8_evaluation.py" in source


def test_sigint_stopped_rollout_root_can_resume_but_pass_cannot(tmp_path: Path) -> None:
    output_root = tmp_path / "rollout"
    plan = {"phase_id": "issue-54-bfs-deadline-panel-v8"}
    _prepare_output_root(output_root, plan, resume=False)
    _atomic_write(output_root / "manifest.json", {"outcome": "VALID_STOP", "stop_reason": "SIGINT"})

    _prepare_output_root(output_root, plan, resume=True)

    _atomic_write(output_root / "manifest.json", {"outcome": "PASS", "stop_reason": None})
    with pytest.raises(ValueError, match="already complete"):
        _prepare_output_root(output_root, plan, resume=True)
