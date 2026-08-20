from __future__ import annotations

from pathlib import Path

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_references import frozen_bfs_development_tasks

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_frozen_reference_task_set_is_the_complete_declared_dev_split() -> None:
    phase_gate = load_bfs_phase_gate(
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json",
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json",
    )

    tasks = frozen_bfs_development_tasks(
        REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl",
        phase_gate,
    )

    assert len(tasks) == 475
    assert all(task["split"] == "dev" for task in tasks)
    assert {(task["domain_id"], task["bucket"]) for task in tasks} == {
        (domain, difficulty)
        for domain in phase_gate.freeze["data"]["domains"]
        for difficulty in phase_gate.freeze["data"]["strata"]
    }


def test_modulo_shards_form_an_exact_partition_of_frozen_reference_tasks() -> None:
    phase_gate = load_bfs_phase_gate(
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json",
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json",
    )
    tasks = frozen_bfs_development_tasks(
        REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl",
        phase_gate,
    )

    shards = [[task for index, task in enumerate(tasks) if index % 8 == shard] for shard in range(8)]

    assert sum(len(shard) for shard in shards) == len(tasks)
    assert {task["instance_id"] for shard in shards for task in shard} == {task["instance_id"] for task in tasks}
