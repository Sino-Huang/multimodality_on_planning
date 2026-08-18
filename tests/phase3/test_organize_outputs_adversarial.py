from __future__ import annotations

import multiprocessing as mp
import subprocess
import sys
from multiprocessing.connection import Connection
from pathlib import Path

import pytest

from scripts.phase3 import organize_outputs_preflight
from scripts.phase3.organize_outputs import OrganizerCheckpoint, OrganizerError, apply, main
from scripts.phase3.output_layout_contracts import DEFAULT_OUTPUT_LAYOUT
from scripts.phase3.output_layout_journal import journal_path
from scripts.phase3.output_layout_lock import exclusive_output_layout_lock
from scripts.phase3.output_layout_rename import OutputLayoutRenameError
from organize_outputs_support import repository


def _apply_in_process(repository_root: Path, completed: Connection) -> None:
    try:
        apply(repository_root)
        completed.send("complete")
    finally:
        completed.close()


def test_recognized_proc_writer_blocks_and_incidental_text_does_not(tmp_path: Path) -> None:
    repository_root = repository(tmp_path)
    path = journal_path(repository_root)
    source = repository_root / DEFAULT_OUTPUT_LAYOUT.relocations[0].source.value
    script = tmp_path / "scripts/phase3/generate_planimation_vlm.py"
    script.parent.mkdir(parents=True)
    script.write_text("import time\ntime.sleep(3)\n", encoding="utf-8")
    process = subprocess.Popen([sys.executable, str(script), "--output-root", str(source)])
    try:
        with pytest.raises(OrganizerError):
            apply(repository_root)
    finally:
        process.terminate()
        process.wait(timeout=3)
    assert source.is_dir()
    assert not path.exists()
    proc = tmp_path / "proc/123/cmdline"
    proc.parent.mkdir(parents=True)
    proc.write_bytes(b"python\0note=--output-root=" + str(source).encode() + b"\0")
    organize_outputs_preflight.reject_uncooperative_writers(source, proc.parents[1])


def test_moved_verified_entry_with_physical_source_stops_resume_before_next_move(tmp_path: Path) -> None:
    repository_root = repository(tmp_path)
    path = journal_path(repository_root)
    with pytest.raises(OrganizerCheckpoint, match="move_verified"):
        apply(repository_root, checkpoint="move_verified")
    first = DEFAULT_OUTPUT_LAYOUT.relocations[0]
    first_source = repository_root / first.source.value
    first_source.mkdir(parents=True)
    (first_source / "payload-0.txt").write_text("payload-0\n", encoding="utf-8")
    second_source = repository_root / DEFAULT_OUTPUT_LAYOUT.relocations[1].source.value
    with pytest.raises(OrganizerError):
        apply(repository_root)
    assert first_source.is_dir()
    assert second_source.is_dir()


@pytest.mark.parametrize("rule", ("renameat2 is unavailable", "cross-filesystem rename is forbidden"))
def test_rename_failures_preserve_source_and_racing_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rule: str) -> None:
    repository_root = repository(tmp_path)
    path = journal_path(repository_root)
    first = DEFAULT_OUTPUT_LAYOUT.relocations[0]
    source = repository_root / first.source.value
    destination = repository_root / first.destination.value

    def fail_rename(_source: Path, _destination: Path) -> None:
        raise OutputLayoutRenameError(rule=rule, source=_source, destination=_destination)

    monkeypatch.setattr("scripts.phase3.organize_outputs.rename_noreplace", fail_rename)
    with pytest.raises(OrganizerError):
        apply(repository_root)
    assert source.is_dir()
    assert not destination.exists()


def test_exclusive_organizer_lock_blocks_second_preflight(tmp_path: Path) -> None:
    repository_root = repository(tmp_path)
    path = journal_path(repository_root)
    receiver, sender = mp.get_context("spawn").Pipe(duplex=False)
    process = mp.get_context("spawn").Process(target=_apply_in_process, args=(repository_root, sender))
    try:
        with exclusive_output_layout_lock(repository_root):
            process.start()
            assert not receiver.poll(0.2)
            assert not path.exists()
        assert receiver.poll(3.0)
        assert receiver.recv() == "complete"
        process.join(3.0)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.terminate()
        process.join(3.0)
        receiver.close()
        sender.close()


def test_cli_emits_machine_readable_success_and_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repository_root = repository(tmp_path)
    assert main(["catalog", "--repo-root", str(repository_root)]) == 0
    assert '"schema_version"' in capsys.readouterr().out
    assert main(["apply", "--repo-root", str(repository_root)]) == 0
    assert capsys.readouterr().out == '{"command": "apply", "ok": true}\n'
    (repository_root / "outputs/unexpected").mkdir()
    assert main(["verify", "--repo-root", str(repository_root)]) == 1
    assert '"ok": false' in capsys.readouterr().err
