from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.run_bfs_base_seeds import SeedLaunch, build_seed_launches, run_seed_launches
from scripts.run_bfs_model_shard import _output_state


def test_builds_two_dedicated_gpu_queues_for_the_five_frozen_seeds(tmp_path: Path) -> None:
    launches = build_seed_launches(
        seeds=(17, 29, 43, 71, 101),
        devices=("0", "1"),
        output_prefix=tmp_path / "issue54-v3-base",
        attempt_id_prefix="issue-54-v3-base",
    )

    assert [(launch.seed, launch.device) for launch in launches] == [
        (17, "0"),
        (29, "1"),
        (43, "0"),
        (71, "1"),
        (101, "0"),
    ]
    assert len({launch.output_root for launch in launches}) == 5
    assert all("scripts/run_bfs_model_shard.py" in launch.command for launch in launches)


def test_resume_launches_reuse_only_the_matching_partial_attempt(tmp_path: Path) -> None:
    output_root = tmp_path / "partial"
    output_root.mkdir()
    plan = {"arm": "base", "seed": 17}
    (output_root / "launch.json").write_text(json.dumps(plan), encoding="utf-8")

    assert _output_state(output_root, plan, resume=True) == "resume"
    (output_root / "manifest.json").write_text("{}", encoding="utf-8")
    assert _output_state(output_root, plan, resume=True) == "complete"

    with pytest.raises(ValueError, match="launch differs"):
        _output_state(output_root, {"arm": "base", "seed": 29}, resume=True)


def test_two_device_queues_really_overlap_child_processes(tmp_path: Path) -> None:
    marker_root = tmp_path / "markers"
    marker_root.mkdir()
    child = (
        "import pathlib,sys,time;"
        "root=pathlib.Path(sys.argv[1]);"
        "(root / (sys.argv[2] + '.started')).write_text('started');"
        "deadline=time.monotonic()+3;"
        "\nwhile len(list(root.glob('*.started'))) < 2:\n"
        "    if time.monotonic() >= deadline: raise SystemExit(9)\n"
        "    time.sleep(0.01)\n"
        "print('parallel-overlap-confirmed', flush=True)"
    )
    launches = tuple(
        SeedLaunch(
            seed=seed,
            device=device,
            attempt_id=f"test-{seed}",
            output_root=tmp_path / f"seed-{seed}",
            console_log=tmp_path / f"seed-{seed}.console.log",
            command=(sys.executable, "-c", child, str(marker_root), str(seed)),
        )
        for seed, device in ((17, "0"), (29, "1"))
    )

    assert run_seed_launches(launches) == 0
    assert all("parallel-overlap-confirmed" in launch.console_log.read_text() for launch in launches)


def test_two_slots_on_the_same_gpu_really_overlap_child_processes(tmp_path: Path) -> None:
    marker_root = tmp_path / "same-gpu-markers"
    marker_root.mkdir()
    child = (
        "import pathlib,sys,time;"
        "root=pathlib.Path(sys.argv[1]);"
        "(root / (sys.argv[2] + '.started')).write_text('started');"
        "deadline=time.monotonic()+3;"
        "\nwhile len(list(root.glob('*.started'))) < 2:\n"
        "    if time.monotonic() >= deadline: raise SystemExit(9)\n"
        "    time.sleep(0.01)\n"
        "print('same-gpu-overlap-confirmed', flush=True)"
    )
    launches = tuple(
        SeedLaunch(
            seed=seed,
            device="0",
            attempt_id=f"same-gpu-{seed}",
            output_root=tmp_path / f"same-gpu-seed-{seed}",
            console_log=tmp_path / f"same-gpu-seed-{seed}.console.log",
            command=(sys.executable, "-c", child, str(marker_root), str(seed)),
        )
        for seed in (17, 43)
    )

    assert run_seed_launches(launches, processes_per_gpu=2) == 0
    assert all("same-gpu-overlap-confirmed" in launch.console_log.read_text() for launch in launches)
