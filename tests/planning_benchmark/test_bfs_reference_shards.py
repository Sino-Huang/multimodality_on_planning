from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.run_bfs_reference_shards import build_shard_launches, run_shards


def test_shard_launches_have_unique_governed_bindings_and_complete_indices(tmp_path: Path) -> None:
    aggregate_root = tmp_path / "issue52-v3-shards"

    launches = build_shard_launches(
        output_root=aggregate_root,
        attempt_id_prefix="issue-52-reference-v3",
        shard_count=8,
        workers_per_shard=1,
    )

    assert [launch.shard_index for launch in launches] == list(range(8))
    assert len({launch.attempt_id for launch in launches}) == 8
    assert len({launch.output_root for launch in launches}) == 8
    for index, launch in enumerate(launches):
        assert launch.attempt_id == f"issue-52-reference-v3-shard-{index:03d}-of-008"
        assert launch.output_root == (aggregate_root / f"shard-{index:03d}").resolve()
        assert launch.command == (
            sys.executable,
            "scripts/run_bfs_references.py",
            "--output-root",
            str(launch.output_root),
            "--attempt-id",
            launch.attempt_id,
            "--shard-index",
            str(index),
            "--shard-count",
            "8",
            "--workers",
            "1",
        )


def test_shard_failure_does_not_cancel_sibling_attempts(tmp_path: Path, monkeypatch) -> None:
    launches = build_shard_launches(
        output_root=tmp_path / "shards",
        attempt_id_prefix="failure-retention",
        shard_count=3,
        workers_per_shard=1,
    )
    called: list[int] = []

    def fake_run(command, **_kwargs):
        shard_index = int(command[command.index("--shard-index") + 1])
        called.append(shard_index)
        return subprocess.CompletedProcess(
            command,
            1 if shard_index == 1 else 0,
            stdout=f"completed {shard_index}\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    exit_code = run_shards(launches, max_concurrent_shards=2)

    assert exit_code == 1
    assert sorted(called) == [0, 1, 2]
