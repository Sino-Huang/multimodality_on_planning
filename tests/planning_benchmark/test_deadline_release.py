"""Release packaging keeps replay data portable and final weight files separate."""

import shutil
import tarfile
from types import SimpleNamespace

import pytest

from examples.planning_benchmark_slice.modality_view_preparation import write_json
from examples.planning_benchmark_slice.scene_assets import read_json
from examples.planning_benchmark_slice.visual_experiment import ALGORITHMS, ROOT, VisualExperiment
from scripts import prepare_deadline_release as release
from scripts.replay_deadline_release import replay_run


def test_live_run_cannot_be_packaged(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "VisualExperiment", lambda config: SimpleNamespace(output=tmp_path / "live"))
    with pytest.raises(ValueError, match="cannot export a live or absent"):
        release.inventory([tmp_path / "config.json"])


def test_selected_task_assets_follow_explicit_replay_dependencies(tmp_path):
    row = {"task_id": "astar-pair-example", "trace_paths": {"bfs": "data/pair/trace.json.gz"}}
    write_json(
        tmp_path / "views/manifest.json",
        {
            "scene_catalog": "scenes/catalog.json",
            "reusable_pages": {"task-context": ["views/context.png"], "goal": ["views/goal.png"]},
        },
    )
    write_json(tmp_path / "scenes/catalog.json", {"states": [{"scene_path": "scenes/current.png"}]})
    paths = release.selected_task_files(tmp_path, row, "views/manifest.json")
    assert paths == {
        "data/pair/trace.json.gz",
        "data/pair/task.json",
        "views/manifest.json",
        "scenes/catalog.json",
        "scenes/current.png",
        "views/context.png",
        "views/goal.png",
    }


def test_archive_contains_only_listed_assets_and_weights_are_referenced(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    source = tmp_path / "outputs/run"
    source.mkdir(parents=True)
    (source / "result.json").write_text('{"outcome":"VALID_STOP"}')
    (source / "weights.safetensors").write_bytes(b"test weights")
    index = {
        "runs": [{"output_root": "outputs/run"}],
        "assets": [{"path": "outputs/run/result.json", "bytes": 24}],
        "checkpoints": [{"path": "outputs/run/weights.safetensors", "asset_name": "issue75-bfs.safetensors"}],
    }
    output = tmp_path / "release"
    release.package(index, output)
    with tarfile.open(output / "replay-assets.tar.gz") as archive:
        assert archive.getnames() == ["outputs/run/result.json"]
    assert (output / "issue75-bfs.safetensors").is_symlink()
    assert (output / "issue75-bfs.safetensors").resolve() == source / "weights.safetensors"
    with pytest.raises(ValueError, match="already exists"):
        release.package(index, output)
    with pytest.raises(ValueError, match="separate from original"):
        release.package(index, source / "export")


def test_real_reference_episodes_replay_from_relocated_assets(tmp_path):
    e = VisualExperiment()
    references = read_json(e.output / "references.json")["episodes"]
    chosen = [
        min(
            (r for r in references if r["algorithm"] == algorithm and r["arm"] == "exact_reference"),
            key=lambda r: r["result"]["decision_count"],
        )
        for algorithm in ALGORITHMS
    ]
    files = {str((e.output / name).relative_to(ROOT)) for name in ("attempt.json", "result.json")}
    panel = e.corpus.contract["panel_manifest"]
    files.update((panel, e.config["corpus_report"]))
    for episode in chosen:
        files.add(episode["path"])
        row = next(r for r in e.dev if r["task_id"] == episode["task_id"])
        files.update(release.selected_task_files(ROOT, row, e.corpus.results[row["task_id"]]["view_manifest"]))
        report = read_json(ROOT / episode["path"])
        files.update(str(p.relative_to(ROOT)) for p in (ROOT / report["view_root"]).rglob("*") if p.is_file())
    for name in files:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    run = {
        "issue": 75,
        "contract_id": e.config["contract_id"],
        "output_root": str(e.output.relative_to(ROOT)),
        "panel_manifest": panel,
        "corpus_report": e.config["corpus_report"],
        "episode_paths": [r["path"] for r in chosen],
    }
    report = replay_run(tmp_path, run)
    assert report["replayed_episodes"] == 4
    assert report["coverage"]["total"] == 864 and not report["coverage"]["complete"]
    assert all(report["point_metrics"][a]["exact_reference"]["invariant_valid_success"] == 1 for a in ALGORITHMS)
