from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from scripts.phase3.output_layout_writer_detection import (
    WriterDetectionError,
    find_overlapping_writer,
)
from scripts.phase3.output_layout_writer_registry import writer_targets


def test_writer_registry_recognizes_active_direct_and_module_writers() -> None:
    cases = (
        (("python", "scripts/phase3/generate_planimation_vlm.py", "--output-root", "planimation"), ("planimation",)),
        (("python", "-m", "scripts.phase3.generate_curriculum_trace_dataset", "--output-root=traces"), ("traces",)),
        (("python", "scripts/phase3/generate_supervised_data.py", "--output-root", "supervised"), ("supervised",)),
        (("python", "-m", "scripts.phase3.rollout_gates", "prepare", "--output-root", "gates", "--stage", "pilot"), ("gates",)),
        (("python", "scripts/phase3/save_fast_downward_plans.py", "--input-root=plans"), ("plans",)),
        (("python", "-m", "scripts.phase3.extend_curriculum_workflow", "--shards-root", "shards", "--candidate-root=candidate", "--final-root", "final", "--update-root"), ("shards", "candidate", "final")),
        (("python", "-m", "src.data_collect", "generate", "--output", "generated", "--seed", "7"), ("generated",)),
        (("python", "-m", "src.data_collect", "merge-shards", "--shards-root", "shards", "--output=merged"), ("merged",)),
        (("python", "src/data_collect/__main__.py", "merge-shards", "--shards-root", "shards", "--output", "merged"), ("merged",)),
    )

    for arguments, expected_targets in cases:
        assert tuple(target.value for target in writer_targets(arguments)) == expected_targets


def test_writer_registry_uses_last_value_and_excludes_read_only_commands() -> None:
    assert tuple(target.value for target in writer_targets(("python", "scripts/phase3/generate_planimation_vlm.py", "--output-root", "old", "--output-root=new"))) == ("new",)
    assert writer_targets(("python", "-m", "src.data_collect", "inspect-tools", "--json")) == ()
    assert writer_targets(("python", "-m", "src.data_collect", "generate", "--output", "generated", "--dry-run", "--seed", "7")) == ()
    assert tuple(
        target.value
        for target in writer_targets(
            ("python", "-m", "scripts.phase3.rollout_gates", "assess", "--output-root", "gates", "--stage", "pilot", "--selection-file", "selection.json")
        )
    ) == ("gates",)
    assert writer_targets(("python", "notes/scripts.phase3.generate_planimation_vlm", "--output-root", "incidental")) == ()
    assert writer_targets(("python", "--note", "generate_planimation_vlm.py", "--output-root", "incidental")) == ()


def test_writer_registry_supports_direct_and_module_forms() -> None:
    cases = (
        (("scripts/phase3/generate_planimation_vlm.py", "--output-root", "root"), ("scripts.phase3.generate_planimation_vlm", "--output-root", "root"), ("root",)),
        (("scripts/phase3/generate_curriculum_trace_dataset.py", "--output-root", "root"), ("scripts.phase3.generate_curriculum_trace_dataset", "--output-root", "root"), ("root",)),
        (("scripts/phase3/generate_supervised_data.py", "--output-root", "root"), ("scripts.phase3.generate_supervised_data", "--output-root", "root"), ("root",)),
        (("scripts/phase3/rollout_gates.py", "prepare", "--output-root", "root"), ("scripts.phase3.rollout_gates", "prepare", "--output-root", "root"), ("root",)),
        (("scripts/phase3/save_fast_downward_plans.py", "--input-root", "root"), ("scripts.phase3.save_fast_downward_plans", "--input-root", "root"), ("root",)),
        (("scripts/phase3/extend_curriculum_workflow.py", "--shards-root", "root"), ("scripts.phase3.extend_curriculum_workflow", "--shards-root", "root"), ("root", "/tmp/opencode/curriculum_pddl_candidate_auto")),
    )
    for direct, module, expected_targets in cases:
        assert tuple(target.value for target in writer_targets(("python", *direct))) == expected_targets
        assert tuple(target.value for target in writer_targets(("python", "-m", *module))) == expected_targets


def test_writer_registry_uses_writer_parser_defaults() -> None:
    assert tuple(target.value for target in writer_targets(("python", "scripts/phase3/generate_curriculum_trace_dataset.py"))) == (
        "outputs/reasoning_traces/curriculum",
    )
    assert tuple(target.value for target in writer_targets(("python", "scripts/phase3/generate_supervised_data.py"))) == ("data/phase3_supervised_planning",)
    assert tuple(target.value for target in writer_targets(("python", "scripts/phase3/save_fast_downward_plans.py"))) == ("data/curriculum_pddl",)
    assert tuple(target.value for target in writer_targets(("python", "scripts/phase3/extend_curriculum_workflow.py"))) == ("data/curriculum_pddl_shards", "/tmp/opencode/curriculum_pddl_candidate_auto")


def test_writer_registry_rejects_malformed_recognized_invocation() -> None:
    with pytest.raises(WriterDetectionError, match="missing required --output-root"):
        _ = writer_targets(("python", "-m", "scripts.phase3.generate_planimation_vlm"))


def test_writer_registry_skips_python_options_before_exact_direct_and_module_entries() -> None:
    assert tuple(
        target.value
        for target in writer_targets(
            ("python", "-u", "-B", "scripts/phase3/generate_planimation_vlm.py", "--output-root", "direct")
        )
    ) == ("direct",)
    assert tuple(
        target.value
        for target in writer_targets(
            ("python", "-u", "-B", "-m", "scripts.phase3.generate_planimation_vlm", "--output-root=module")
        )
    ) == ("module",)
    assert tuple(
        target.value
        for target in writer_targets(
            ("python", "--", "scripts/phase3/generate_planimation_vlm.py", "--output-root", "terminated")
        )
    ) == ("terminated",)
    assert writer_targets(("python", "--", "-m", "scripts.phase3.generate_planimation_vlm", "--output-root", "near")) == ()
    assert writer_targets(("python", "other/phase3/generate_planimation_vlm.py", "--output-root", "near")) == ()
    assert writer_targets(("python", "-m", "scripts.phase3.generate_planimation_vlm_extra", "--output-root", "near")) == ()


def test_writer_registry_tracks_only_concrete_mutating_subcommands_and_effective_roots() -> None:
    assert writer_targets(("python", "scripts/phase3/rollout_gates.py", "unknown", "--output-root", "ignored")) == ()
    assert tuple(
        target.value
        for target in writer_targets(
            ("python", "scripts/phase3/rollout_gates.py", "assess", "--output-root", "assessed", "--stage", "fixture", "--selection-file", "selection.json")
        )
    ) == ("assessed",)
    assert tuple(
        target.value
        for target in writer_targets(
            ("python", "scripts/phase3/extend_curriculum_workflow.py", "--shards-root=shards", "--candidate-root", "candidate", "--final-root", "final")
        )
    ) == ("shards", "candidate")
    assert tuple(
        target.value
        for target in writer_targets(
            ("python", "scripts/phase3/extend_curriculum_workflow.py", "--shards-root=shards", "--candidate-root", "candidate", "--final-root", "final", "--update-root")
        )
    ) == ("shards", "candidate", "final")
    assert writer_targets(("python", "src/data_collect/__main__.py", "inspect-tools")) == ()
    assert writer_targets(("python", "src/data_collect/__main__.py", "generate", "--output", "generated", "--seed", "1", "--dry-run")) == ()
    assert tuple(
        target.value
        for target in writer_targets(("python", "src/data_collect/__main__.py", "merge-shards", "--shards-root", "shards", "--output", "merged"))
    ) == ("merged",)


def test_proc_detection_rejects_equal_ancestor_and_descendant_targets(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    source = tmp_path / "workspace" / "outputs" / "source"
    source.mkdir(parents=True)
    cwd = tmp_path / "workspace"
    for pid, target in (("100", "outputs/source"), ("101", "outputs"), ("102", "outputs/source/child")):
        _write_process(proc_root, pid, ("python", "-m", "scripts.phase3.generate_planimation_vlm", "--output-root", target), cwd)

    match = find_overlapping_writer(source, proc_root=proc_root, own_pid=-1)

    assert match is not None
    assert match.pid == 100
    assert match.target == source.resolve()


def test_proc_detection_resolves_relative_target_against_process_cwd_and_skips_own_pid(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    source = tmp_path / "workspace" / "outputs" / "source"
    source.mkdir(parents=True)
    cwd = tmp_path / "workspace"
    _write_process(proc_root, "100", ("python", "scripts/phase3/generate_supervised_data.py", "--output-root", "outputs/source"), cwd)
    _write_process(proc_root, "101", ("python", "scripts/phase3/generate_supervised_data.py", "--output-root", "outputs/source"), cwd)

    match = find_overlapping_writer(source, proc_root=proc_root, own_pid=100)

    assert match is not None
    assert match.pid == 101


def test_proc_detection_resolves_relative_separate_and_equals_values_per_pid_cwd(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    source = tmp_path / "workspace" / "outputs" / "source"
    source.mkdir(parents=True)
    cwd = tmp_path / "workspace"
    _write_process(proc_root, "100", ("python", "scripts/phase3/generate_supervised_data.py", "--output-root", "outputs/other"), cwd)
    _write_process(proc_root, "101", ("python", "scripts/phase3/generate_supervised_data.py", "--output-root=outputs/source"), cwd)

    match = find_overlapping_writer(source, proc_root=proc_root, own_pid=-1)

    assert match is not None
    assert match.pid == 101
    assert match.target == source.resolve()


def test_proc_detection_recognizes_terminated_direct_writer_with_relative_target(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    source = tmp_path / "workspace" / "outputs" / "source"
    source.mkdir(parents=True)
    _write_process(
        proc_root,
        "100",
        ("python", "--", "scripts/phase3/generate_planimation_vlm.py", "--output-root", "outputs/source"),
        tmp_path / "workspace",
    )

    match = find_overlapping_writer(source, proc_root=proc_root, own_pid=-1)

    assert match is not None
    assert match.pid == 100
    assert match.target == source.resolve()


def test_proc_detection_does_not_read_cwd_for_absolute_registered_targets(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    source = tmp_path / "source"
    source.mkdir()
    _write_process(proc_root, "100", ("python", "-m", "scripts.phase3.generate_planimation_vlm", "--output-root", str(source)), tmp_path)
    (proc_root / "100" / "cwd").unlink()

    match = find_overlapping_writer(source, proc_root=proc_root, own_pid=-1)

    assert match is not None
    assert match.pid == 100
    assert match.target == source.resolve()


def test_proc_detection_fails_closed_for_unframed_or_live_missing_cmdline(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    source = tmp_path / "source"
    source.mkdir()
    process = proc_root / "100"
    process.mkdir(parents=True)
    (process / "cmdline").write_bytes(b"python\0-m\0scripts.phase3.generate_planimation_vlm\0--output-root\0source")
    with pytest.raises(WriterDetectionError, match="malformed cmdline framing"):
        _ = find_overlapping_writer(source, proc_root=proc_root, own_pid=-1)
    (process / "cmdline").unlink()
    with pytest.raises(WriterDetectionError, match="cannot read cmdline"):
        _ = find_overlapping_writer(source, proc_root=proc_root, own_pid=-1)


def test_proc_detection_allows_pid_disappearance_during_cmdline_and_cwd_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proc_root = tmp_path / "proc"
    source = tmp_path / "source"
    source.mkdir()
    proc_root.mkdir()
    vanished = proc_root / "100"
    vanished.symlink_to(tmp_path / "missing-process")
    assert find_overlapping_writer(source, proc_root=proc_root, own_pid=-1) is None

    process = proc_root / "101"
    process.mkdir()
    _write_process(proc_root, "101", ("python", "-m", "scripts.phase3.generate_planimation_vlm", "--output-root", "source"), tmp_path)
    original_read_bytes = Path.read_bytes

    def remove_process_after_cmdline(path: Path) -> bytes:
        payload = original_read_bytes(path)
        if path == process / "cmdline":
            shutil.rmtree(process)
        return payload

    monkeypatch.setattr(Path, "read_bytes", remove_process_after_cmdline)
    assert find_overlapping_writer(source, proc_root=proc_root, own_pid=-1) is None
    monkeypatch.undo()

    esrch_process = proc_root / "102"
    _write_process(proc_root, "102", ("python", "-m", "scripts.phase3.generate_planimation_vlm", "--output-root", "source"), tmp_path)
    original_read_bytes = Path.read_bytes

    def raise_esrch_for_cmdline(path: Path) -> bytes:
        if path == esrch_process / "cmdline":
            raise ProcessLookupError()
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", raise_esrch_for_cmdline)
    assert find_overlapping_writer(source, proc_root=proc_root, own_pid=-1) is None
    monkeypatch.undo()
    shutil.rmtree(esrch_process)

    cwd_esrch_process = proc_root / "103"
    _write_process(proc_root, "103", ("python", "-m", "scripts.phase3.generate_planimation_vlm", "--output-root", "source"), tmp_path)
    original_resolve = Path.resolve

    def raise_esrch_for_cwd(path: Path, strict: bool = False) -> Path:
        if path == cwd_esrch_process / "cwd":
            raise ProcessLookupError()
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", raise_esrch_for_cwd)
    assert find_overlapping_writer(source, proc_root=proc_root, own_pid=-1) is None


def test_proc_detection_allows_vanished_process_and_fails_closed_for_live_bad_metadata(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    source = tmp_path / "source"
    source.mkdir()
    proc_root.mkdir()
    (proc_root / "100").symlink_to(tmp_path / "missing-process")
    assert find_overlapping_writer(source, proc_root=proc_root, own_pid=-1) is None

    (proc_root / "101" / "cmdline").mkdir(parents=True)
    with pytest.raises(WriterDetectionError, match="cannot read cmdline"):
        _ = find_overlapping_writer(source, proc_root=proc_root, own_pid=-1)
    (proc_root / "101" / "cmdline").rmdir()
    (proc_root / "101").rmdir()

    _write_process(
        proc_root,
        "102",
        ("python", "-m", "scripts.phase3.generate_planimation_vlm", "--output-root", "source"),
        tmp_path,
    )
    (proc_root / "102" / "cwd").unlink()
    with pytest.raises(WriterDetectionError, match="cannot resolve cwd"):
        _ = find_overlapping_writer(source, proc_root=proc_root, own_pid=-1)


def _write_process(proc_root: Path, pid: str, arguments: tuple[str, ...], cwd: Path) -> None:
    process = proc_root / pid
    process.mkdir(parents=True, exist_ok=True)
    (process / "cmdline").write_bytes(b"\0".join(argument.encode("utf-8") for argument in arguments) + b"\0")
    os.symlink(cwd, process / "cwd")
