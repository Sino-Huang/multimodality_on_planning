from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPOSITORY_ROOT / "temp_fast_planimation_render.sh"
DATASET_ROOT = "outputs/reasoning_traces/curriculum/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round"
FULL_OUTPUT_ROOT = "outputs/image_frames/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800"
PILOT_OUTPUT_ROOT = "outputs/image_frames/phase3_planimation_frames_stratified_pilot_20260725"
SELECTION_FILE = f"{FULL_OUTPUT_ROOT}/diagnostics/rollout_selection.json"


@dataclass(frozen=True, slots=True)
class LauncherRequest:
    arguments: tuple[str, ...]
    pilot_output_root: str
    working_directory: Path


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_launcher(tmp_path: Path, request: LauncherRequest) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "python",
        "#!/usr/bin/env bash\n"
        "touch \"$PYTHON_MARKER\"\n"
        "exit 98\n",
    )
    (tmp_path / "cd_vlaplan").write_text(
        "touch \"$ACTIVATION_MARKER\"\nreturn 97\n",
        encoding="utf-8",
    )

    environment = os.environ | {
        "ACTIVATION_MARKER": str(tmp_path / "activation-marker"),
        "HOME": str(tmp_path),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "PILOT_OUTPUT_ROOT": request.pilot_output_root,
        "PYTHON_MARKER": str(tmp_path / "python-marker"),
    }
    return subprocess.run(
        ["bash", str(LAUNCHER), *request.arguments],
        cwd=request.working_directory,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
        env=environment,
    )


def _assert_preflight_stopped_before_activation(tmp_path: Path) -> None:
    assert not (tmp_path / "activation-marker").exists()
    assert not (tmp_path / "python-marker").exists()


def _start_fake_python_process(
    *, arguments: tuple[str, ...], environment: dict[str, str] | None = None
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, *arguments],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop_fake_python_process(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _write_sleeping_generator_script(path: Path) -> None:
    path.write_text("from time import sleep\nsleep(30)\n", encoding="utf-8")


def test_fresh_mode_refuses_existing_output_root_before_activation(tmp_path: Path) -> None:
    # Given: an existing pilot root and sentinels that would expose activation.
    # When: fresh mode runs against the existing repository metadata directory.
    result = _run_launcher(
        tmp_path,
        LauncherRequest(
            arguments=(),
            pilot_output_root=".git",
            working_directory=REPOSITORY_ROOT,
        ),
    )

    # Then: the launcher fails before activation.
    assert result.returncode == 1
    assert result.stderr == "Refusing to overwrite existing pilot output root: .git\n"
    _assert_preflight_stopped_before_activation(tmp_path)


@pytest.mark.parametrize("arguments", [("--unknown",), ("--resume", "extra")])
def test_launcher_rejects_invalid_arguments_before_preflight(tmp_path: Path, arguments: tuple[str, ...]) -> None:
    # Given: invalid launcher arguments and an otherwise non-blocking environment.
    request = LauncherRequest(
        arguments=arguments,
        pilot_output_root=str(tmp_path / "new-pilot"),
        working_directory=REPOSITORY_ROOT,
    )

    # When: the launcher receives an unsupported argument shape.
    result = _run_launcher(tmp_path, request)

    # Then: usage fails closed before process checks or activation.
    assert result.returncode == 2
    assert result.stderr == "Usage: temp_fast_planimation_render.sh [--resume]\n"
    _assert_preflight_stopped_before_activation(tmp_path)


def test_resume_refuses_missing_pilot_root_before_activation(tmp_path: Path) -> None:
    # Given: resume mode targets a nonexistent pilot root.
    pilot_root = tmp_path / "missing-pilot"
    request = LauncherRequest(
        arguments=("--resume",),
        pilot_output_root=str(pilot_root),
        working_directory=REPOSITORY_ROOT,
    )

    # When: the launcher attempts the missing-root resume.
    result = _run_launcher(tmp_path, request)

    # Then: resume refuses the root before activation or Python.
    assert result.returncode == 1
    assert result.stderr == f"Resume requires existing pilot output root: {pilot_root}\n"
    _assert_preflight_stopped_before_activation(tmp_path)


def test_resume_refuses_missing_frozen_selection_before_activation(tmp_path: Path) -> None:
    # Given: resume mode has a pilot root but no frozen selection at its relative path.
    pilot_root = tmp_path / "pilot"
    pilot_root.mkdir()
    request = LauncherRequest(
        arguments=("--resume",),
        pilot_output_root=str(pilot_root),
        working_directory=tmp_path,
    )

    # When: the launcher checks the resume prerequisites.
    result = _run_launcher(tmp_path, request)

    # Then: resume refuses the absent selection before activation or Python.
    assert result.returncode == 1
    assert result.stderr == f"Resume requires existing frozen selection file: {SELECTION_FILE}\n"
    _assert_preflight_stopped_before_activation(tmp_path)


def test_launcher_ignores_wrapper_like_command_line_mentioning_full_root(tmp_path: Path) -> None:
    # Given: a non-generator Python wrapper mentions the generator and full root as prompt text.
    wrapper_process = _start_fake_python_process(
        arguments=(
            "-c",
            "from time import sleep; sleep(30)",
            f"prompt: generate_planimation_vlm --output-root {FULL_OUTPUT_ROOT}",
        )
    )
    request = LauncherRequest(
        arguments=(),
        pilot_output_root=str(tmp_path / "new-pilot"),
        working_directory=REPOSITORY_ROOT,
    )

    try:
        # When: fresh mode checks processes before activation.
        result = _run_launcher(tmp_path, request)
    finally:
        _stop_fake_python_process(wrapper_process)

    # Then: the false-positive process does not block the safe activation sentinel.
    assert result.returncode == 97
    assert (tmp_path / "activation-marker").exists()
    assert not (tmp_path / "python-marker").exists()


def test_launcher_refuses_active_fake_module_generator_for_full_root_before_activation(tmp_path: Path) -> None:
    # Given: a temporary module has the generator module name and writes to the full root.
    fake_module = tmp_path / "scripts" / "phase3" / "generate_planimation_vlm.py"
    fake_module.parent.mkdir(parents=True)
    (fake_module.parent.parent / "__init__.py").touch()
    (fake_module.parent / "__init__.py").touch()
    _write_sleeping_generator_script(fake_module)
    generator_environment = os.environ | {"PYTHONPATH": str(tmp_path)}
    generator_process = _start_fake_python_process(
        arguments=("-m", "scripts.phase3.generate_planimation_vlm", "--output-root", FULL_OUTPUT_ROOT),
        environment=generator_environment,
    )
    request = LauncherRequest(
        arguments=(),
        pilot_output_root=str(tmp_path / "new-pilot"),
        working_directory=REPOSITORY_ROOT,
    )

    try:
        # When: fresh mode checks for active writers.
        result = _run_launcher(tmp_path, request)
    finally:
        _stop_fake_python_process(generator_process)

    # Then: the matching module writer blocks before activation.
    assert result.returncode == 1
    assert result.stderr == (
        f"Refusing to run while the full renderer still writes to {FULL_OUTPUT_ROOT}. "
        "Stop it first, then rerun this script.\n"
    )
    _assert_preflight_stopped_before_activation(tmp_path)


def test_launcher_refuses_active_fake_script_generator_for_literal_metacharacter_pilot_root_before_activation(
    tmp_path: Path,
) -> None:
    # Given: a fake script generator targets a pilot root containing regex metacharacters.
    pilot_root = tmp_path / "pilot[one].*"
    fake_script = tmp_path / "fake" / "generate_planimation_vlm.py"
    fake_script.parent.mkdir()
    _write_sleeping_generator_script(fake_script)
    generator_process = _start_fake_python_process(
        arguments=(str(fake_script), f"--output-root={pilot_root}"),
    )
    request = LauncherRequest(
        arguments=("--resume",),
        pilot_output_root=str(pilot_root),
        working_directory=REPOSITORY_ROOT,
    )

    try:
        # When: resume mode checks for active writers.
        result = _run_launcher(tmp_path, request)
    finally:
        _stop_fake_python_process(generator_process)

    # Then: the literal matching pilot writer blocks before path checks or activation.
    assert result.returncode == 1
    assert result.stderr == (
        f"Refusing to run while the pilot renderer still writes to {pilot_root}. "
        "Stop it first, then rerun this script.\n"
    )
    _assert_preflight_stopped_before_activation(tmp_path)


def test_launcher_source_contract_preserves_resume_safety() -> None:
    # Given: the launcher source text.
    source = LAUNCHER.read_text(encoding="utf-8")

    # When: the launch contract is inspected without executing the success path.
    activation_block = "\n".join(
        (
            "# Conda's deactivate hook reads an unset variable under Bash nounset.",
            "set +u",
            "source ~/cd_vlaplan",
            "source .venv/bin/activate",
            "set -u",
        )
    )

    # Then: immutable inputs, selection-bound verification, and no reset path are present.
    assert 'case "$#" in' in source
    assert '1)\n    if [[ "$1" != "--resume" ]]' in source
    assert source.index('case "$#" in') < source.rindex("active_generator_writes_to")
    assert source.count("active_generator_writes_to") == 3
    assert "pgrep -f" not in source
    assert '[[ "$output_root_argument" == "$output_root" ]]' in source
    assert activation_block in source
    assert 'if [[ "$resume" == false ]]; then' in source
    assert source.index('if [[ "$resume" == false ]]; then') < source.index("prepare_selection(")
    assert f'DATASET_ROOT="{DATASET_ROOT}"' in source
    assert f'FULL_OUTPUT_ROOT="{FULL_OUTPUT_ROOT}"' in source
    assert f'PILOT_OUTPUT_ROOT="${{PILOT_OUTPUT_ROOT:-{PILOT_OUTPUT_ROOT}}}"' in source
    assert '--dataset-root "$DATASET_ROOT"' in source
    assert '--selection-file "$SELECTION_FILE"' in source
    assert "for verification_mode in manifest render release; do" in source
    assert source.count('--selection-file "$SELECTION_FILE"') == 2
    assert "state_cache" not in source
    assert "--reset" not in source
    assert "rm " not in source
    assert "mv " not in source
