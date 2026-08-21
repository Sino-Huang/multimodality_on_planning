from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_materialization_cli_dry_run_validates_every_planned_stage_without_writes() -> None:
    release_root = REPO_ROOT / "data" / "bfs_pilot_v3"
    governed_inputs = {
        path.relative_to(release_root).as_posix(): path.read_bytes()
        for path in release_root.rglob("*")
        if path.is_file()
    }

    result = subprocess.run(
        [sys.executable, "scripts/materialize_bfs_pilot_v3.py", "--workers", "4", "--dry-run"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(result.stdout)
    assert report["dry_run"] is True
    assert report["selected_task_count"] == 90
    assert report["budgets"] == {"easy": 64, "medium": 256, "hard": 1024}
    assert report["planned_stages"] == [
        "trace_generation",
        "corpus_release",
        "corpus_byte_regeneration",
        "ms_swift_process_projection",
        "ms_swift_projection_byte_regeneration",
    ]
    assert governed_inputs == {
        path.relative_to(release_root).as_posix(): path.read_bytes()
        for path in release_root.rglob("*")
        if path.is_file()
    }
