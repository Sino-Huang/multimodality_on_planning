from __future__ import annotations

import json
from pathlib import Path

from scripts.run_bfs_issue54 import (
    adjudication_command,
    checkpoint_launches,
    reference_command,
    training_commands,
    training_launches,
)

SEEDS = (17, 29, 43, 71, 101)
DEVICES = ("0", "1")


def _training_products(tmp_path: Path) -> Path:
    output_root = tmp_path / "outputs"
    for seed in SEEDS:
        training_root = output_root / f"issue54-v3-process-sft-seed-{seed}"
        checkpoints = []
        for step in (420, 840, 1260):
            checkpoint = training_root / "checkpoints" / f"checkpoint-{step}"
            checkpoint.mkdir(parents=True)
            checkpoints.append(str(checkpoint))
        (training_root / "training-report.json").write_text(
            json.dumps(
                {
                    "checkpoint_paths": checkpoints,
                    "returncode": 0,
                    "status": "training_completed",
                }
            ),
            encoding="utf-8",
        )
    return output_root


def test_reference_and_training_stages_cover_the_frozen_commands(tmp_path: Path) -> None:
    reference = reference_command(output_root=tmp_path, workers=8, dry_run=True)
    training = training_commands(
        seeds=SEEDS,
        devices=DEVICES,
        output_root=tmp_path,
        dataset_root=tmp_path / "dataset",
        dry_run=True,
    )

    assert reference[-1] == "--dry-run"
    assert len(training) == 5
    assert all(command[-1] == "--dry-run" for command in training)
    assert all(command[command.index("--world-size") + 1] == "1" for command in training)
    assert [command[command.index("--devices") + 1] for command in training] == ["0", "1", "0", "1", "0"]
    assert [command[command.index("--master-port") + 1] for command in training] == [
        "29600",
        "29601",
        "29602",
        "29603",
        "29604",
    ]

    launches = training_launches(
        seeds=SEEDS,
        devices=DEVICES,
        output_root=tmp_path,
        dataset_root=tmp_path / "dataset",
    )
    assert [(launch.seed, launch.device) for launch in launches] == [
        (17, "0"),
        (29, "1"),
        (43, "0"),
        (71, "1"),
        (101, "0"),
    ]


def test_interrupted_training_attempts_get_fresh_attempt_roots_and_ports(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    for seed in SEEDS:
        failed_root = output_root / f"issue54-v3-process-sft-seed-{seed}"
        failed_root.mkdir(parents=True)
        (failed_root / "training-report.json").write_text(
            json.dumps({"checkpoint_paths": [], "returncode": 1, "status": "training_failed"}),
            encoding="utf-8",
        )

    launches = training_launches(
        seeds=SEEDS,
        devices=DEVICES,
        output_root=output_root,
        dataset_root=tmp_path / "dataset",
    )

    assert len(launches) == 5
    assert all(launch.output_root.name.endswith("-attempt-002") for launch in launches)
    assert len({launch.command[launch.command.index("--master-port") + 1] for launch in launches}) == 5


def test_successful_training_seed_is_not_launched_again(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    training_root = output_root / "issue54-v3-process-sft-seed-17"
    checkpoint = training_root / "checkpoints" / "checkpoint-1260"
    checkpoint.mkdir(parents=True)
    (training_root / "training-report.json").write_text(
        json.dumps(
            {
                "checkpoint_paths": [str(checkpoint)],
                "returncode": 0,
                "status": "training_completed",
            }
        ),
        encoding="utf-8",
    )

    launches = training_launches(
        seeds=(17,),
        devices=DEVICES,
        output_root=output_root,
        dataset_root=tmp_path / "dataset",
    )

    assert launches == ()


def test_checkpoint_evaluation_uses_both_gpu_queues_and_all_fifteen_checkpoints(tmp_path: Path) -> None:
    output_root = _training_products(tmp_path)

    launches = checkpoint_launches(seeds=SEEDS, devices=DEVICES, output_root=output_root)

    assert len(launches) == 15
    assert {launch.device for launch in launches} == {"0", "1"}
    assert [launch.device for launch in launches[:4]] == ["0", "1", "0", "1"]
    assert all("--adapter-path" in launch.command for launch in launches)


def test_adjudication_receives_all_base_and_checkpoint_manifests(tmp_path: Path) -> None:
    output_root = _training_products(tmp_path)
    launches = checkpoint_launches(seeds=SEEDS, devices=DEVICES, output_root=output_root)

    command = adjudication_command(
        seeds=SEEDS,
        checkpoint_runs=launches,
        output_root=output_root,
        dry_run=True,
    )

    assert command.count("--base-manifest") == 5
    assert command.count("--process-manifest") == 15
    assert command[-1] == "--dry-run"


def test_v4_reuses_all_fifteen_v3_checkpoints_under_separate_receipts(tmp_path: Path) -> None:
    output_root = _training_products(tmp_path)

    launches = checkpoint_launches(
        seeds=SEEDS,
        devices=DEVICES,
        output_root=output_root,
        evaluation_phase="v4",
    )
    command = adjudication_command(
        seeds=SEEDS,
        checkpoint_runs=launches,
        output_root=output_root,
        dry_run=True,
        phase="v4",
    )

    assert len(launches) == 15
    assert all(launch.command[launch.command.index("--phase") + 1] == "v4" for launch in launches)
    assert all("issue54-v4-process" in str(launch.output_root) for launch in launches)
    assert command[command.index("--phase") + 1] == "v4"
    assert any("issue54-v4-sanity-adjudication" in argument for argument in command)


def test_v4_reference_command_uses_a_separate_output_root(tmp_path: Path) -> None:
    command = reference_command(output_root=tmp_path, workers=8, dry_run=True, phase="v4")

    assert command[command.index("--phase") + 1] == "v4"
    assert any("issue54-v4-references" in argument for argument in command)
