from __future__ import annotations

import json
from pathlib import Path

from examples.planning_benchmark_slice.iw_qualification import qualify_bfws_curriculum, qualify_curriculum

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "planning"


def test_qualification_distinguishes_solved_from_width_cap_exhaustion(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    rows = [
        _row("iw-width-two", "train", FIXTURES / "iw_width_two.json", tmp_path),
        _row("iw-width-four", "test", FIXTURES / "iw_width_four.json", tmp_path),
    ]
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    report = qualify_curriculum(
        manifest,
        tmp_path / "qualification",
        max_expansions=64,
        timeout_seconds=5,
    )

    assert report["status_counts"] == {"solved": 1, "width_cap_exhausted": 1}
    assert report["migration_required"] is True
    assert report["qualification_conclusive"] is True
    assert report["test_split_consumed_for_algorithm_selection"] is True

    bfws_report = qualify_bfws_curriculum(
        manifest,
        tmp_path / "bfws-qualification",
        max_expansions=64,
        timeout_seconds=5,
    )

    assert bfws_report["status_counts"] == {"solved": 2}
    assert bfws_report["all_solved"] is True
    solved_rows = (tmp_path / "bfws-qualification" / "solved-manifest.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert [json.loads(line)["instance_id"] for line in solved_rows] == ["iw-width-two", "iw-width-four"]


def test_qualification_shards_partition_manifest_without_duplicates(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    rows = [
        _row(f"iw-width-two-{index}", "train", FIXTURES / "iw_width_two.json", tmp_path)
        for index in range(4)
    ]
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    output = tmp_path / "qualification"

    qualify_curriculum(manifest, output, shard_index=0, shard_count=2)
    report = qualify_curriculum(manifest, output, shard_index=1, shard_count=2)

    result_rows = (output / "instance-results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(result_rows) == 4
    assert report["instance_count"] == 4
    assert report["status_counts"] == {"solved": 4}


def _row(instance_id: str, split: str, fixture_path: Path, output_dir: Path) -> dict[str, object]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    domain_path = output_dir / f"{instance_id}-domain.pddl"
    problem_path = output_dir / f"{instance_id}-problem.pddl"
    domain_path.write_text(fixture["domain_pddl"], encoding="utf-8")
    problem_path.write_text(fixture["problem_pddl"], encoding="utf-8")
    return {
        "instance_id": instance_id,
        "domain_id": fixture["domain"],
        "split": split,
        "bucket": "easy",
        "domain_path": str(domain_path),
        "problem_path": str(problem_path),
        "normalized_problem_hash": instance_id,
    }
