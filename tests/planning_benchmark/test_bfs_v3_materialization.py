from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from scripts.materialize_bfs_pilot_v3 import _validate_reusable_traces

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


def test_resume_validation_requires_and_accepts_the_exact_90_trace_product(tmp_path: Path) -> None:
    gate = load_bfs_phase_gate(
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v3.json",
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v3.json",
    )
    trace_root = tmp_path / "exact-traces"
    artifact_path = trace_root / "artifact.bin"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"verified-trace-artifact")
    artifact = {
        "path": "artifact.bin",
        "size_bytes": artifact_path.stat().st_size,
    }
    receipt = gate.receipt(stage="trace_generation")
    traces = [
        {
            "difficulty": difficulty,
            "domain_id": domain,
            "evidence": artifact,
            "phase_receipt": receipt,
            "search_trace": artifact,
            "source": {"split": split},
        }
        for domain in gate.freeze["data"]["domains"]
        for difficulty in gate.freeze["data"]["strata"]
        for split in gate.freeze["data"]["allowed_splits"]
    ]
    manifest_path = trace_root / "manifests" / "bfs-expert-traces.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "algorithm": "bfs",
                "phase_receipt": receipt,
                "schema_version": "bfs_expert_trace_generation_v3",
                "traces": traces,
            }
        ),
        encoding="utf-8",
    )

    assert _validate_reusable_traces(manifest_path, gate) == 90
