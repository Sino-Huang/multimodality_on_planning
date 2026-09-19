import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from scripts import collect_modality_scene_assets as cli
from src.data_collect.governance import ReceiptBinding


@pytest.fixture
def reuse_setup(tmp_path):
    config = {"contract_id": "scenes", "reuse_collection": {"attempt_id": "old", "output_root": "old"}}
    panel = [
        {"task_id": name, "domain": "grid", "trace_paths": {"bfs": name}, "reference_costs": {"bfs": {"decisions": 1}}}
        for name in ("complete", "failed", "pending")
    ]
    old = tmp_path / "old"
    old.mkdir()
    catalog = {
        "task_id": "complete",
        "source_trace_paths": panel[0]["trace_paths"],
        "reference_costs": panel[0]["reference_costs"],
        "stored_scene_size": [128, 128],
        "states": [{"scene_path": "old/frame.png"}],
    }
    (old / "catalog.json").write_text(json.dumps(catalog))
    report = {
        "contract_id": "scenes",
        "binding": ReceiptBinding("scenes", "old", old).to_dict(),
        "stage": "collect",
        "outcome": "VALID_STOP",
        "stored_scene_size": [128, 128],
        "results": [
            {
                "task_id": "complete",
                "outcome": "PASS",
                "complete_state_coverage": True,
                "catalog": "old/catalog.json",
                "scene_frames": 1,
            },
            {"task_id": "failed", "outcome": "VALID_STOP", "complete_state_coverage": False},
        ],
    }
    (old / "report.json").write_text(json.dumps(report))
    return tmp_path, config, panel, report


def test_reuse_references_only_complete_tasks_and_excludes_changed_freecell(reuse_setup):
    root, config, panel, _ = reuse_setup
    results = cli.reusable_results(root, config, panel)
    assert [r["task_id"] for r in results] == ["complete"]
    assert results[0]["catalog"] == "old/catalog.json"
    assert results[0]["reused_from_report"] == "old/report.json"
    panel[0]["domain"] = "freecell"
    assert cli.reusable_results(root, config, panel) == []


@pytest.mark.parametrize("defect", ["invalid", "binding", "scope", "partial"])
def test_reuse_rejects_wrong_scope_and_never_accepts_invalid_or_partial(reuse_setup, defect):
    root, config, panel, report = reuse_setup
    if defect == "invalid":
        report["outcome"] = "INVALID"
    elif defect == "binding":
        report["binding"]["attempt_id"] = "other"
    elif defect == "scope":
        panel[0]["trace_paths"] = {"bfs": "different-task"}
    else:
        report["results"][0]["complete_state_coverage"] = False
    (root / "old/report.json").write_text(json.dumps(report))
    if defect == "partial":
        assert cli.reusable_results(root, config, panel) == []
    else:
        with pytest.raises(ValueError):
            cli.reusable_results(root, config, panel)


@pytest.mark.parametrize("new_outcome", ["PASS", "VALID_STOP"])
def test_successor_schedules_only_remaining_and_combines_coverage(reuse_setup, monkeypatch, new_outcome):
    root, config, panel, _ = reuse_setup
    config.update(
        stored_scene_size=[128, 128],
        source_phase_authorization_id="phase",
        endpoints=["localhost"],
        timeout_seconds=30,
        attempts={
            mode: {
                "attempt_id": mode,
                "output_root": mode,
                "gate_outcome": "PASS",
                "authorization_gate_id": f"gate:scenes:{mode}:PASS",
            }
            for mode in ("preflight", "collect")
        },
    )
    preflight = root / "preflight"
    preflight.mkdir()
    (preflight / "report.json").write_text(
        json.dumps(
            {
                "contract_id": "scenes",
                "binding": ReceiptBinding("scenes", "preflight", preflight).to_dict(),
                "stage": "preflight",
                "outcome": "PASS",
                "stored_scene_size": [128, 128],
                "complete_selected_coverage": True,
                "results": [{"task_id": r["task_id"], "outcome": "PASS"} for r in panel],
            }
        )
    )
    (root / "panel.json").write_text(json.dumps({"selected": panel}))
    (root / "config.json").write_text(json.dumps(config))
    monkeypatch.setattr(cli, "ROOT", root)
    monkeypatch.setattr(
        cli,
        "load_modality_phase",
        lambda: SimpleNamespace(
            authorization={"authorization_id": "phase", "outcome": "PASS"},
            components={"corpus": {"panel_manifest": "panel.json"}, "render": {"domain_profiles": {"grid": "profile"}}},
        ),
    )
    monkeypatch.setattr(cli, "inspect_modality_sources", lambda phase: None)
    monkeypatch.setattr(cli, "ProcessPoolExecutor", ThreadPoolExecutor)
    submitted = []

    def work(arguments):
        row = arguments[0]
        submitted.append(row["task_id"])
        return {
            "task_id": row["task_id"],
            "outcome": new_outcome,
            "scene_frames": 1,
            "complete_state_coverage": new_outcome == "PASS",
        }

    monkeypatch.setattr(cli, "work", work)
    assert cli.main(["--config", str(root / "config.json"), "--collect", "--workers", "1"]) == (
        0 if new_outcome == "PASS" else 2
    )
    assert "complete" not in submitted
    report = json.loads((root / "collect/report.json").read_text())
    assert report["reused_tasks"] == 1
    assert report["scene_asset_completion"] == (new_outcome == "PASS")
    assert len(report["results"]) == (3 if new_outcome == "PASS" else 2)
