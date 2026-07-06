from __future__ import annotations

import json
from pathlib import Path

from scripts.phase3.save_fast_downward_plans import PlanSaveConfig, save_fast_downward_plans


def test_save_fast_downward_plans_skips_existing_plan(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    instance_dir = dataset / "blocksworld" / "train" / "easy" / "blocksworld-train-easy-0000"
    plan_dir = instance_dir / "plan"
    plan_dir.mkdir(parents=True)
    (instance_dir / "domain.pddl").write_text("(define (domain blocksworld))\n", encoding="utf-8")
    (instance_dir / "problem.pddl").write_text("(define (problem p) (:domain blocksworld))\n", encoding="utf-8")
    (plan_dir / "sas_plan").write_text("; cost = 0 (unit cost)\n", encoding="utf-8")
    _write_manifest(dataset, instance_dir)

    summary = save_fast_downward_plans(
        PlanSaveConfig(
            input_root=dataset,
            alias="lama-first",
            timeout_seconds=1,
            force=False,
            limit=None,
            planner_path=Path("/definitely/not/used/fast-downward.py"),
        )
    )

    assert summary["attempted_total"] == 1
    assert summary["plan_available_total"] == 1
    assert summary["status_counts"] == {"skipped_existing_plan": 1}
    diagnostics = _read_jsonl(dataset / "diagnostics" / "fast_downward_plan_saves.jsonl")
    assert diagnostics[0]["plan_paths"] == ["sas_plan"]
    assert diagnostics[0]["plan_count"] == 1


def test_save_fast_downward_plans_reports_missing_pddl(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    instance_dir = dataset / "blocksworld" / "train" / "easy" / "blocksworld-train-easy-0000"
    instance_dir.mkdir(parents=True)
    _write_manifest(dataset, instance_dir)

    summary = save_fast_downward_plans(
        PlanSaveConfig(
            input_root=dataset,
            alias="lama-first",
            timeout_seconds=1,
            force=False,
            limit=None,
            planner_path=Path("/definitely/not/used/fast-downward.py"),
        )
    )

    assert summary["plan_available_total"] == 0
    assert summary["status_counts"] == {"failed_missing_pddl": 1}
    diagnostics = _read_jsonl(dataset / "diagnostics" / "fast_downward_plan_saves.jsonl")
    assert diagnostics[0]["status"] == "failed_missing_pddl"


def test_save_fast_downward_plans_force_rewrites_existing_plan_with_fake_planner(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    instance_dir = dataset / "blocksworld" / "train" / "easy" / "blocksworld-train-easy-0000"
    plan_dir = instance_dir / "plan"
    plan_dir.mkdir(parents=True)
    (instance_dir / "domain.pddl").write_text("(define (domain blocksworld))\n", encoding="utf-8")
    (instance_dir / "problem.pddl").write_text("(define (problem p) (:domain blocksworld))\n", encoding="utf-8")
    (plan_dir / "sas_plan").write_text("stale\n", encoding="utf-8")
    _write_manifest(dataset, instance_dir)
    fake_planner = _write_fake_planner(tmp_path)

    summary = save_fast_downward_plans(
        PlanSaveConfig(
            input_root=dataset,
            alias="lama-first",
            timeout_seconds=5,
            force=True,
            limit=None,
            planner_path=fake_planner,
        )
    )

    assert summary["plan_available_total"] == 1
    assert summary["status_counts"] == {"success_plan_saved": 1}
    assert (plan_dir / "sas_plan").read_text(encoding="utf-8") == "fresh-plan\n"


def test_save_fast_downward_plans_reports_missing_planner(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    instance_dir = dataset / "blocksworld" / "train" / "easy" / "blocksworld-train-easy-0000"
    instance_dir.mkdir(parents=True)
    (instance_dir / "domain.pddl").write_text("(define (domain blocksworld))\n", encoding="utf-8")
    (instance_dir / "problem.pddl").write_text("(define (problem p) (:domain blocksworld))\n", encoding="utf-8")
    _write_manifest(dataset, instance_dir)

    summary = save_fast_downward_plans(
        PlanSaveConfig(
            input_root=dataset,
            alias="lama-first",
            timeout_seconds=1,
            force=False,
            limit=None,
            planner_path=tmp_path / "missing-fast-downward.py",
        )
    )

    assert summary["plan_available_total"] == 0
    assert summary["status_counts"] == {"failed_planner_error": 1}
    diagnostics = _read_jsonl(dataset / "diagnostics" / "fast_downward_plan_saves.jsonl")
    assert "could not be launched" in str(diagnostics[0]["message"])


def test_save_fast_downward_plans_rejects_manifest_path_outside_input_root(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "domain.pddl").write_text("(define (domain blocksworld))\n", encoding="utf-8")
    (outside / "problem.pddl").write_text("(define (problem p) (:domain blocksworld))\n", encoding="utf-8")
    _write_manifest(dataset, outside)

    summary = save_fast_downward_plans(
        PlanSaveConfig(
            input_root=dataset,
            alias="lama-first",
            timeout_seconds=1,
            force=True,
            limit=None,
            planner_path=tmp_path / "missing-fast-downward.py",
        )
    )

    assert summary["plan_available_total"] == 0
    assert summary["status_counts"] == {"failed_path_outside_input_root": 1}
    assert not (outside / "plan").exists()


def _write_manifest(dataset: Path, instance_dir: Path) -> None:
    manifest_row = {
        "instance_id": "blocksworld-train-easy-0000",
        "candidate_id": "blocksworld-train-easy-attempt-000000",
        "domain_id": "blocksworld",
        "split": "train",
        "bucket": "easy",
        "index": 0,
        "attempt_index": 0,
        "domain_path": str(instance_dir / "domain.pddl"),
        "problem_path": str(instance_dir / "problem.pddl"),
    }
    dataset.mkdir(parents=True, exist_ok=True)
    (dataset / "accepted_manifest.jsonl").write_text(json.dumps(manifest_row) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_fake_planner(tmp_path: Path) -> Path:
    planner = tmp_path / "fake-fast-downward.py"
    planner.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import sys\n"
        "plan_file = Path(sys.argv[sys.argv.index('--plan-file') + 1])\n"
        "assert plan_file.parent.exists(), plan_file.parent\n"
        "plan_file.write_text('fresh-plan\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    planner.chmod(planner.stat().st_mode | 0o111)
    return planner
