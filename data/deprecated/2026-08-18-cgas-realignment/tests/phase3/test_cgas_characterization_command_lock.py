from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

import pytest

import scripts.phase3.cgas_characterization_cli as cli
from scripts.phase3.cgas_characterization_command_lock import command_lock, lock_path
from scripts.phase3.cgas_characterization_runner import RunReport


def test_no_wait_busy_exits_75_before_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    repository, private, source = _paths(tmp_path)
    final = repository / "tmp" / ".cgas-characterization" / "bundle.cgas"
    descriptor = _hold(lock_path(final))
    calls: list[str] = []
    monkeypatch.setattr(cli, "run", lambda _request, _mode: calls.append("run") or RunReport(0, final.with_name("bundle.cgas.work")))

    try:
        status = cli.main(_command(repository, private, source, "fresh", "--shard-count", "1", "--no-wait"))
    finally:
        os.close(descriptor)

    assert status == 75
    assert calls == []
    assert json.loads(capsys.readouterr().out) == {"error": "work_locked", "status": "error"}


def test_lock_release_after_exception_allows_waiter(tmp_path: Path) -> None:
    final = tmp_path / "tmp" / "bundle.cgas"
    final.parent.mkdir(mode=0o700)

    with pytest.raises(RuntimeError):
        with command_lock(final, exclusive=True, wait=True):
            raise RuntimeError("stop")

    with command_lock(final, exclusive=True, wait=False):
        assert lock_path(final).is_file()


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    repository = tmp_path / "repository"
    private = repository / "tmp" / ".cgas-characterization" / "private"
    source = repository / "accepted.jsonl"
    private.mkdir(parents=True, mode=0o700)
    private.parent.chmod(0o700)
    private.chmod(0o700)
    source.write_text("", encoding="utf-8")
    return repository, private, source


def _command(repository: Path, private: Path, source: Path, command: str, *extra: str) -> tuple[str, ...]:
    return (
        command,
        "--repository-root",
        str(repository),
        "--source-manifest",
        str(source),
        "--bundle-name",
        "bundle.cgas",
        "--private-root",
        str(private),
        *extra,
    )


def _hold(path: Path) -> int:
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    os.fchmod(descriptor, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    return descriptor
