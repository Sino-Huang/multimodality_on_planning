from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import scripts.phase3.cgas_characterization_cli as cli
import scripts.phase3.cgas_characterization_final_validation as final_validation
from cgas_characterization_assembly_support import checkpoint_request, synthetic_request, write_checkpoint_history
from scripts.phase3.cgas_characterization_assembly import CharacterizationCandidate
from scripts.phase3.cgas_characterization_runner import RunMode, RunReport
from scripts.phase3.cgas_characterization_verifier import CharacterizationVerificationReport


def test_fresh_creates_only_derived_work_root_without_characterization(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Given: a repository-local synthetic 481-row source and private directory.
    request, private_root = synthetic_request(tmp_path)
    before = _snapshot(request.repository_root)

    # When: the public CLI initializes the named bundle lifecycle.
    status = cli.main(
        (
            "fresh",
            "--repository-root",
            str(request.repository_root),
            "--source-manifest",
            str(request.source_manifest),
            "--bundle-name",
            "fresh.cgas",
            "--private-root",
            str(private_root),
            "--shard-count",
            "3",
        )
    )

    # Then: only the durable work root exists and the terminal report is canonical.
    assert status == 0
    assert (request.repository_root / "tmp" / ".cgas-characterization" / "fresh.cgas.work" / "checkpoints").is_dir()
    assert not (request.repository_root / "tmp" / ".cgas-characterization" / "fresh.cgas").exists()
    assert _snapshot(request.repository_root) != before
    assert json.loads(capsys.readouterr().out) == {
        "bundle_name": "fresh.cgas",
        "characterized_count": 0,
        "command": "fresh",
        "status": "ok",
    }


@pytest.mark.parametrize("name", ("/absolute", "nested/name", "..", "a\\b", "a\x00b", "e\u0301.cgas"))
def test_cli_rejects_unsafe_or_normalization_drifting_bundle_name_before_side_effects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    # Given: a command whose final name is not one canonical safe component.
    calls: list[RunMode] = []
    monkeypatch.setattr(cli, "run", lambda _request, mode: calls.append(mode) or RunReport(0, tmp_path))

    # When: fresh parses the unsafe component.
    status = cli.main(_command(tmp_path, "fresh", name, "--shard-count", "1"))

    # Then: dispatch does not reach the runner and reports a stable typed error.
    assert status == 1
    assert calls == []
    assert json.loads(capsys.readouterr().out) == {"error": "unsafe_bundle_name", "status": "error"}


def test_shard_dispatches_canonical_index_and_emits_only_canonical_progress(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a runner substitute which emits one post-publication canonical progress event.
    seen: list[tuple[RunMode, int, int]] = []

    def run_stub(request, mode):
        seen.append((mode, request.shard_index, request.shard_count))
        print('{"completed":1,"index":4,"instance_id":"synthetic-0004","phase":"shard","shard_count":3,"shard_index":1,"status":"published","total":160}', file=sys.stderr, flush=True)
        return RunReport(1, request.final_root.with_name("bundle.cgas.work"))

    monkeypatch.setattr(cli, "run", run_stub)

    # When: the shard subcommand targets the middle of three canonical shards.
    status = cli.main(_command(tmp_path, "shard", "bundle.cgas", "--shard-count", "3", "--shard-index", "1"))

    # Then: dispatcher arguments and stream separation are exact.
    captured = capsys.readouterr()
    assert status == 0
    assert seen == [(RunMode.SHARD, 1, 3)]
    assert json.loads(captured.out) == {"bundle_name": "bundle.cgas", "characterized_count": 1, "command": "shard", "status": "ok"}
    assert json.loads(captured.err) == {
        "completed": 1,
        "index": 4,
        "instance_id": "synthetic-0004",
        "phase": "shard",
        "shard_count": 3,
        "shard_index": 1,
        "status": "published",
        "total": 160,
    }


@pytest.mark.parametrize("target", ("source", "private"))
def test_cli_rejects_symlinked_lifecycle_paths_before_dispatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    # Given: one caller-selected lifecycle path redirected through a symlink.
    repository = tmp_path / "repository"
    private_root = repository / "tmp" / ".cgas-characterization" / "private"
    private_root.mkdir(parents=True)
    private_root.parent.chmod(0o700)
    private_root.chmod(0o700)
    source = repository / "accepted.jsonl"
    source.write_text("", encoding="utf-8")
    linked = repository / f"{target}-link"
    linked.symlink_to(source if target == "source" else private_root)
    calls: list[RunMode] = []
    monkeypatch.setattr(cli, "run", lambda _request, mode: calls.append(mode) or RunReport(0, tmp_path))

    # When: fresh receives the redirected input path.
    status = cli.main(
        (
            "fresh",
            "--repository-root",
            str(repository),
            "--source-manifest",
            str(linked if target == "source" else source),
            "--bundle-name",
            "bundle.cgas",
            "--private-root",
            str(linked if target == "private" else private_root),
            "--shard-count",
            "1",
        )
    )

    # Then: parsing fails closed before lifecycle initialization or characterization.
    assert status == 1
    assert calls == []
    assert json.loads(capsys.readouterr().out) == {
        "error": "source_manifest_not_regular" if target == "source" else "private_root_not_directory",
        "status": "error",
    }


def test_finalize_verifies_complete_work_then_assembles_and_publishes_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a complete work verifier result and ordered finalize collaborators.
    calls: list[str] = []
    repository = tmp_path / "repository"
    private_root = repository / "tmp" / ".cgas-characterization" / "private"
    private_root.mkdir(parents=True)
    private_root.parent.chmod(0o700)
    private_root.chmod(0o700)
    (repository / "accepted.jsonl").write_text("", encoding="utf-8")
    candidate = private_root / "candidate"

    def verify_stub(request):
        calls.append("verify")
        assert request.final_root is None
        return CharacterizationVerificationReport(True, True, True, (), 481)

    monkeypatch.setattr(cli, "verify_characterization", verify_stub)
    monkeypatch.setattr(cli, "assemble_characterization_candidate", lambda _request, _private: calls.append("assemble") or CharacterizationCandidate(candidate))
    monkeypatch.setattr(cli, "publish_final_bundle", lambda _request, built, final, private, _state: calls.append("publish") if (built, final, private) == (candidate, repository / "tmp" / ".cgas-characterization" / "bundle.cgas", private_root) else None)

    # When: finalization receives a complete verified work root.
    status = cli.main(_command(repository.parent, "finalize", "bundle.cgas", repository=repository, private_root=private_root))

    # Then: it never invokes row computation and calls the atomic pipeline in order.
    assert status == 0
    assert calls == ["verify", "assemble", "publish"]
    assert json.loads(capsys.readouterr().out) == {"bundle_name": "bundle.cgas", "checkpoint_count": 481, "command": "finalize", "status": "ok"}


def test_finalize_and_final_verify_drive_the_real_synthetic_481_bundle_lifecycle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Given: complete synthetic 481-checkpoint work below the trusted repository tmp directory.
    request, private_root = synthetic_request(tmp_path)
    work_request = checkpoint_request(request, request.repository_root / "tmp" / ".cgas-characterization" / "bundle.cgas.work")
    write_checkpoint_history(work_request, tuple(range(481)))
    command = _command(
        request.repository_root.parent,
        "finalize",
        "bundle.cgas",
        "--module-root",
        "fixture.runner",
        repository=request.repository_root,
        private_root=private_root,
    )

    # When: the public facade assembles, atomically publishes, and verifies the final bundle.
    assert cli.main(command) == 0
    finalize_report = json.loads(capsys.readouterr().out)
    assert cli.main(
        _command(
            request.repository_root.parent,
            "verify",
            "bundle.cgas",
            "--module-root",
            "fixture.runner",
            "--target",
            "final",
            repository=request.repository_root,
            private_root=private_root,
        )
    ) == 0
    verify_report = json.loads(capsys.readouterr().out)

    # Then: the final is a verifier-clean direct regular bundle, never a directory profile.
    final = request.repository_root / "tmp" / ".cgas-characterization" / "bundle.cgas"
    assert finalize_report == {"bundle_name": "bundle.cgas", "checkpoint_count": 481, "command": "finalize", "status": "ok"}
    assert verify_report["valid"] is True
    assert final.is_file()
    assert not final.is_dir()


def test_finalize_recomputes_each_synthetic_row_once(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: completed structural work and a counter around the authoritative kernel.
    request, private_root = synthetic_request(tmp_path)
    work_request = checkpoint_request(request, request.repository_root / "tmp" / ".cgas-characterization" / "bundle.cgas.work")
    write_checkpoint_history(work_request, tuple(range(481)))
    original = final_validation._characterize
    calls: list[str] = []

    def characterize_once(instance):
        calls.append(instance.instance_id)
        return original(instance)

    monkeypatch.setattr(final_validation, "_characterize", characterize_once)

    # When: the public finalization pipeline publishes the synthetic bundle.
    status = cli.main(_command(request.repository_root.parent, "finalize", "bundle.cgas", "--module-root", "fixture.runner", repository=request.repository_root, private_root=private_root))

    # Then: one scientific pass validates the candidate before publication.
    assert status == 0
    assert len(calls) == 481
    assert len(set(calls)) == 481
    capsys.readouterr()


@pytest.mark.parametrize("entry", ("regular", "symlink", "directory"))
def test_finalize_rejects_existing_dangling_or_special_final_entry_before_work_or_assembly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    # Given: a named final entry that cannot be adopted or replaced.
    repository = tmp_path / "repository"
    private_root = repository / "tmp" / ".cgas-characterization" / "private"
    private_root.mkdir(parents=True)
    private_root.parent.chmod(0o700)
    private_root.chmod(0o700)
    (repository / "accepted.jsonl").write_text("", encoding="utf-8")
    final = repository / "tmp" / ".cgas-characterization" / "bundle.cgas"
    match entry:
        case "regular":
            final.write_bytes(b"existing")
        case "symlink":
                final.symlink_to(repository / "tmp" / ".cgas-characterization" / "missing")
        case "directory":
            final.mkdir()
        case _:
            raise AssertionError(entry)
    calls: list[str] = []
    monkeypatch.setattr(cli, "verify_characterization", lambda _request: calls.append("verify") or CharacterizationVerificationReport(True, True, True, (), 481))

    # When: finalization targets the occupied final component.
    status = cli.main(_command(repository.parent, "finalize", "bundle.cgas", repository=repository, private_root=private_root))

    # Then: no verifier, row assembly, or publisher can adopt the existing entry.
    assert status == 1
    assert calls == []
    assert json.loads(capsys.readouterr().out) == {"error": "final_entry_exists", "status": "error"}


def test_verify_targets_work_or_final_read_only_and_help_does_not_mutate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a repository metadata snapshot and a verifier that only observes requests.
    repository = tmp_path / "repository"
    private_root = repository / "tmp" / ".cgas-characterization" / "private"
    private_root.mkdir(parents=True)
    private_root.parent.chmod(0o700)
    private_root.chmod(0o700)
    (repository / "accepted.jsonl").write_text("", encoding="utf-8")
    seen: list[Path | None] = []
    monkeypatch.setattr(cli, "verify_characterization", lambda request: seen.append(request.final_root) or CharacterizationVerificationReport(True, False, False, (), 7))
    before = _snapshot(repository)

    # When: help and each read-only target are invoked.
    assert cli.main(("--help",)) == 0
    assert cli.main(_command(repository.parent, "verify", "bundle.cgas", "--target", "work", repository=repository, private_root=private_root)) == 0
    assert cli.main(_command(repository.parent, "verify", "bundle.cgas", "--target", "final", repository=repository, private_root=private_root)) == 0

    # Then: help/verification create no entries and map the final target to the bundle file.
    assert seen == [None, repository / "tmp" / ".cgas-characterization" / "bundle.cgas"]
    assert _snapshot(repository) == before
    assert "usage:" in capsys.readouterr().out


def test_verify_invalid_target_returns_nonzero_canonical_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a read-only verifier result that rejects the requested work state.
    repository = tmp_path / "repository"
    private_root = repository / "tmp" / ".cgas-characterization" / "private"
    private_root.mkdir(parents=True)
    private_root.parent.chmod(0o700)
    private_root.chmod(0o700)
    (repository / "accepted.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(cli, "verify_characterization", lambda _request: CharacterizationVerificationReport(False, False, False, ("invalid_work",), 0))

    # When: the verify work command observes the invalid state.
    status = cli.main(_command(repository.parent, "verify", "bundle.cgas", "--target", "work", repository=repository, private_root=private_root))

    # Then: the caller receives the immutable report shape and nonzero status.
    assert status == 1
    assert json.loads(capsys.readouterr().out) == {
        "bundle_name": "bundle.cgas",
        "checkpoint_count": 0,
        "command": "verify",
        "complete": False,
        "errors": {"0": "invalid_work"},
        "publishable": False,
        "status": "invalid",
        "target": "work",
        "valid": False,
    }


def _command(tmp_path: Path, command: str, bundle_name: str, *extra: str, repository: Path | None = None, private_root: Path | None = None) -> tuple[str, ...]:
    root = repository or tmp_path / "repository"
    private = private_root or root / "tmp" / ".cgas-characterization" / "private"
    if not private.exists():
        private.mkdir(parents=True)
    private.parent.chmod(0o700)
    private.chmod(0o700)
    source = root / "accepted.jsonl"
    if not source.exists():
        source.write_text("", encoding="utf-8")
    return (command, "--repository-root", str(root), "--source-manifest", str(source), "--bundle-name", bundle_name, "--private-root", str(private), *extra)


def _snapshot(root: Path) -> tuple[tuple[str, int, int], ...]:
    return tuple(sorted((str(path.relative_to(root)), path.stat(follow_symlinks=False).st_mode, path.stat(follow_symlinks=False).st_size) for path in root.rglob("*")))
