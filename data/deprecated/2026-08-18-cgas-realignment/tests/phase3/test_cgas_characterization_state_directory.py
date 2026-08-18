from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

import scripts.phase3.cgas_characterization_cli as cli
from scripts.phase3.cgas_characterization_runner import RunMode, RunReport
from scripts.phase3.cgas_characterization_state_directory import StateDirectoryError, open_trusted_state_directory


def test_mode_2755_gpfs_tmp_creates_pinned_owner_only_state_child(tmp_path: Path) -> None:
    # Given: the actual GPFS-compatible owner-owned, setgid-readable tmp parent.
    repository = tmp_path / "repository"
    repository.mkdir(mode=0o700)
    tmp = repository / "tmp"
    tmp.mkdir(mode=0o2755)
    tmp.chmod(0o2755)

    # When: fresh-state preflight opens and creates the dedicated child by descriptors.
    with open_trusted_state_directory(repository, create=True) as state:
        # Then: all lifecycle roots derive beneath the pinned owner-only child.
        assert state.path == tmp / ".cgas-characterization"
        assert stat.S_IMODE(os.fstat(state.descriptor).st_mode) == 0o700
        assert state.final_path("bundle.cgas") == state.path / "bundle.cgas"
        assert state.work_path("bundle.cgas") == state.path / "bundle.cgas.work"


@pytest.mark.parametrize("parent_mode", (0o2775, 0o2777))
def test_state_preflight_rejects_shared_writable_tmp_before_creating_child(tmp_path: Path, parent_mode: int) -> None:
    # Given: a shared tmp parent writable by a group or other user.
    repository = tmp_path / "repository"
    repository.mkdir(mode=0o700)
    tmp = repository / "tmp"
    tmp.mkdir(mode=parent_mode)
    tmp.chmod(parent_mode)

    # When: lifecycle state is preflighted.
    with pytest.raises(StateDirectoryError, match="tmp_parent_not_owner_safe"):
        with open_trusted_state_directory(repository, create=True):
            pass

    # Then: no trusted child is created below the unsafe parent.
    assert not (tmp / ".cgas-characterization").exists()


def test_state_preflight_rejects_symlink_or_invalid_existing_child_without_replacing_it(tmp_path: Path) -> None:
    # Given: a safe parent with an attacker-supplied state-child symlink.
    repository = tmp_path / "repository"
    repository.mkdir(mode=0o700)
    tmp = repository / "tmp"
    tmp.mkdir(mode=0o2755)
    tmp.chmod(0o2755)
    child = tmp / ".cgas-characterization"
    child.symlink_to(tmp / "elsewhere")

    # When: preflight encounters the existing non-directory child.
    with pytest.raises(StateDirectoryError, match="state_child_not_owner_mode0700"):
        with open_trusted_state_directory(repository, create=True):
            pass

    # Then: it is never removed, normalized, or adopted.
    assert child.is_symlink()


def test_fresh_preflights_mode_2755_parent_before_runner_and_uses_state_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Given: a 2755 repository tmp and a runner substitute that records its output root.
    repository = tmp_path / "repository"
    repository.mkdir(mode=0o700)
    shared_tmp = repository / "tmp"
    shared_tmp.mkdir(mode=0o2755)
    shared_tmp.chmod(0o2755)
    private = shared_tmp / ".cgas-characterization" / "private"
    source = repository / "accepted.jsonl"
    source.write_text("", encoding="utf-8")
    seen: list[Path] = []
    monkeypatch.setattr(cli, "run", lambda request, mode: seen.append(request.final_root) or RunReport(0, request.final_root.with_name("bundle.cgas.work")))

    # When: fresh enters the real CLI lifecycle.
    status = cli.main(
        (
            "fresh",
            "--repository-root",
            str(repository),
            "--source-manifest",
            str(source),
            "--bundle-name",
            "bundle.cgas",
            "--private-root",
            str(private),
            "--shard-count",
            "1",
        )
    )

    # Then: the boundary is created before the runner and no root remains directly below shared tmp.
    assert status == 0
    assert seen == [shared_tmp / ".cgas-characterization" / "bundle.cgas"]
    assert (shared_tmp / ".cgas-characterization").is_dir()
    assert not (shared_tmp / "bundle.cgas.work").exists()
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_read_only_verify_does_not_create_missing_state_child(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Given: an otherwise valid repository whose shared tmp has no lifecycle child.
    repository = tmp_path / "repository"
    repository.mkdir(mode=0o700)
    shared_tmp = repository / "tmp"
    shared_tmp.mkdir(mode=0o2755)
    shared_tmp.chmod(0o2755)
    source = repository / "accepted.jsonl"
    source.write_text("", encoding="utf-8")
    private = shared_tmp / "private"
    private.mkdir(mode=0o700)

    # When: read-only verification preflights the absent lifecycle state.
    status = cli.main(
        (
            "verify",
            "--repository-root",
            str(repository),
            "--source-manifest",
            str(source),
            "--bundle-name",
            "bundle.cgas",
            "--private-root",
            str(private),
            "--target",
            "work",
        )
    )

    # Then: the error is reported without creating state.
    assert status == 1
    assert not (shared_tmp / ".cgas-characterization").exists()
    assert json.loads(capsys.readouterr().out) == {"error": "state_child_missing", "status": "error"}


def test_fresh_rejects_legacy_shared_tmp_work_root_without_adopting_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Given: a complete-looking legacy work directory directly below shared tmp.
    repository = tmp_path / "repository"
    repository.mkdir(mode=0o700)
    shared_tmp = repository / "tmp"
    shared_tmp.mkdir(mode=0o2755)
    shared_tmp.chmod(0o2755)
    legacy = shared_tmp / "bundle.cgas.work"
    legacy.mkdir(mode=0o700)
    source = repository / "accepted.jsonl"
    source.write_text("", encoding="utf-8")

    # When: fresh uses the same bundle name.
    status = cli.main(
        (
            "fresh",
            "--repository-root",
            str(repository),
            "--source-manifest",
            str(source),
            "--bundle-name",
            "bundle.cgas",
            "--private-root",
            str(shared_tmp / ".cgas-characterization" / "private"),
            "--shard-count",
            "1",
        )
    )

    # Then: no legacy state is migrated or adopted as lifecycle work.
    assert status == 1
    assert legacy.is_dir()
    assert not (shared_tmp / ".cgas-characterization" / "bundle.cgas.work").exists()
    assert json.loads(capsys.readouterr().out) == {"error": "legacy_state_root_present", "status": "error"}


def test_documented_relative_private_root_reaches_fresh_state_preflight_in_subprocess() -> None:
    # Given: a GPFS-backed synthetic repository invoked as the documented relative-root command.
    workspace = Path.cwd()
    environment = {**os.environ, "PYTHONPATH": str(workspace)}
    with TemporaryDirectory(dir=workspace / "tmp", prefix="cgas-relative-command-") as sandbox:
        repository = Path(sandbox) / "repository"
        repository.mkdir(mode=0o700)
        shared_tmp = repository / "tmp"
        shared_tmp.mkdir(mode=0o2755)
        shared_tmp.chmod(0o2755)
        (repository / "accepted.jsonl").write_text("", encoding="utf-8")

        # When: fresh receives `.` and the documented relative private-root syntax.
        result = subprocess.run(
            (
                sys.executable,
                "-m",
                "scripts.phase3.cgas_partition_characterization",
                "fresh",
                "--repository-root",
                ".",
                "--source-manifest",
                "accepted.jsonl",
                "--bundle-name",
                "documented-relative.cgas",
                "--private-root",
                "tmp/.cgas-characterization/private",
                "--shard-count",
                "1",
            ),
            cwd=repository,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        # Then: path preflight succeeds before the intentionally empty source rejects contract construction.
        assert result.returncode != 0
        assert "private_root_outside_state" not in result.stdout
        assert (shared_tmp / ".cgas-characterization" / "private").is_dir()


@pytest.mark.parametrize("private_root", ("../private", "tmp/.cgas-characterization/../private", "tmp/.cgas-characterization/e\u0301"))
def test_fresh_rejects_traversal_or_normalization_drifting_private_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], private_root: str
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir(mode=0o700)
    shared_tmp = repository / "tmp"
    shared_tmp.mkdir(mode=0o2755)
    shared_tmp.chmod(0o2755)
    source = repository / "accepted.jsonl"
    source.write_text("", encoding="utf-8")
    calls: list[RunMode] = []
    monkeypatch.setattr(cli, "run", lambda _request, mode: calls.append(mode) or RunReport(0, tmp_path))

    status = cli.main(
        (
            "fresh",
            "--repository-root",
            str(repository),
            "--source-manifest",
            str(source),
            "--bundle-name",
            "bundle.cgas",
            "--private-root",
            private_root,
            "--shard-count",
            "1",
        )
    )

    assert status == 1
    assert calls == []
    assert json.loads(capsys.readouterr().out) == {"error": "private_root_not_directory", "status": "error"}
