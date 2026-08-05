from __future__ import annotations

import importlib
import json
import tempfile
from pathlib import Path
from types import ModuleType

import pytest


def _production_candidates() -> ModuleType:
    return importlib.import_module("scripts.phase3.cgas_production_candidates")


def test_canonicalizer_individualizes_every_member_when_automorphisms_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = _production_candidates()
    graph_module = importlib.import_module("scripts.phase3.cgas_candidate_graph")
    graph = candidates.identity_graph(("a", "b", "c"), frozenset({("arm-empty",)}), frozenset())
    seen: list[int] = []
    original = candidates.individualize_colors

    def observe(colors: tuple[int, ...], vertex: int, marker: int) -> tuple[int, ...]:
        seen.append(vertex)
        return original(colors, vertex, marker)

    monkeypatch.setattr(graph_module, "individualize_colors", observe)
    candidates.canonicalize_graph(graph)
    assert seen[:3] == [0, 1, 2]


def test_real_gpfs_slice_publishes_three_files_with_receipt_last() -> None:
    candidates = _production_candidates()
    with tempfile.TemporaryDirectory(prefix="cgas-gpfs-test-", dir="tmp") as temporary:
        root = Path(temporary)
        config = root / "config.json"
        config.write_text(json.dumps({
            "schema_version": "cgas_production_candidates_v1",
            "streams": [{"object_count": 4, "raw_quota": 190}],
        }), encoding="utf-8")

        receipt = candidates.materialize_slice(config, root / "output", 4, 0, 1)

        destination = root / "output/streams/objects-04/raw-000000000000-count-000000000001"
        assert set(path.name for path in destination.iterdir()) == {
            "planner-inputs.jsonl", "raw-accounting.jsonl", "receipt.json",
        }
        assert json.loads((destination / "receipt.json").read_bytes())["count"] == receipt.count


def test_cli_serializes_expected_filesystem_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidates = _production_candidates()

    def fail(*_args: int | Path) -> None:
        raise OSError(22, "Invalid argument")

    monkeypatch.setattr(candidates, "materialize_slice", fail)
    result = candidates.main((
        "slice", "--config", "config.json", "--output", "output", "--object-count", "4",
        "--start-rank", "0", "--count", "1", "--json",
    ))
    assert result == 1
    assert json.loads(capsys.readouterr().out) == {"error": "filesystem_publication_failed", "status": "error"}


def test_receipt_last_race_preserves_winner_and_stage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    publication = importlib.import_module("scripts.phase3.cgas_candidate_publication_fs")
    stage, destination = tmp_path / "stage", tmp_path / "destination"
    stage.mkdir()
    (stage / "payload").write_bytes(b"contender")
    (stage / "receipt").write_bytes(b"contender-receipt")
    spec = publication.PublicationSpec(stage, destination, ("payload", "receipt"), "receipt")
    real_mkdir = publication.os.mkdir

    def race(path: str, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
        if path == destination.name and dir_fd is not None:
            real_mkdir(destination, mode)
            (destination / "payload").write_bytes(b"winner")
            (destination / "receipt").write_bytes(b"winner-receipt")
        real_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(publication.os, "mkdir", race)
    with pytest.raises(FileExistsError):
        publication.publish_files(spec)
    assert (destination / "payload").read_bytes() == b"winner"
    assert (stage / "payload").read_bytes() == b"contender"


def test_receipt_last_fault_cleans_partial_and_preserves_stage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    publication = importlib.import_module("scripts.phase3.cgas_candidate_publication_fs")
    stage, destination = tmp_path / "stage", tmp_path / "destination"
    stage.mkdir()
    (stage / "payload").write_bytes(b"payload")
    (stage / "receipt").write_bytes(b"receipt")
    spec = publication.PublicationSpec(stage, destination, ("payload", "receipt"), "receipt")
    real_link = publication.os.link

    def fail_receipt(source: str, target: str, **arguments: int | bool) -> None:
        if source == "receipt":
            raise OSError(5, "injected receipt fault")
        real_link(source, target, **arguments)

    monkeypatch.setattr(publication.os, "link", fail_receipt)
    with pytest.raises(OSError, match="injected receipt fault"):
        publication.publish_files(spec)
    assert not destination.exists()
    assert (stage / "payload").read_bytes() == b"payload"


def test_post_receipt_fault_removes_commit_and_partial(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    publication = importlib.import_module("scripts.phase3.cgas_candidate_publication_fs")
    stage, destination = tmp_path / "stage", tmp_path / "destination"
    stage.mkdir()
    (stage / "payload").write_bytes(b"payload")
    (stage / "receipt").write_bytes(b"receipt")
    spec = publication.PublicationSpec(stage, destination, ("payload", "receipt"), "receipt")
    real_fsync = publication.os.fsync
    calls = 0

    def fail_after_receipt(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError(5, "injected post-receipt fault")
        real_fsync(descriptor)

    monkeypatch.setattr(publication.os, "fsync", fail_after_receipt)
    with pytest.raises(OSError, match="injected post-receipt fault"):
        publication.publish_files(spec)
    assert not destination.exists()
    assert (stage / "receipt").read_bytes() == b"receipt"


def test_real_gpfs_slice_recovers_partial_and_ignores_hidden_stage() -> None:
    candidates = _production_candidates()
    with tempfile.TemporaryDirectory(prefix="cgas-gpfs-recovery-", dir="tmp") as temporary:
        root = Path(temporary)
        config = root / "config.json"
        config.write_text(json.dumps({
            "schema_version": "cgas_production_candidates_v1",
            "streams": [{"object_count": 4, "raw_quota": 190}],
        }), encoding="utf-8")
        stream = root / "output/streams/objects-04"
        destination = stream / "raw-000000000000-count-000000000001"
        destination.mkdir(parents=True)
        (destination / "raw-accounting.jsonl").write_bytes(b"partial")
        (stream / ".range-stage-orphan").mkdir()

        candidates.materialize_slice(config, root / "output", 4, 0, 1)

        assert set(path.name for path in destination.iterdir()) == {
            "planner-inputs.jsonl", "raw-accounting.jsonl", "receipt.json",
        }
