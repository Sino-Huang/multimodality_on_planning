from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.phase3 import generate_planimation_vlm
from scripts.phase3.generate_curriculum_trace_dataset import DEFAULT_OUTPUT_ROOT
from scripts.phase3.planimation_pairing import CURRENT_TRACE_ROOTS, PairingConfig
from scripts.phase3.traversal_state_types import JSONValue


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TEMPRUN = REPOSITORY_ROOT / "temprun.sh"
CANONICAL_TRACE_ROOT = Path(
    "outputs/reasoning_traces/curriculum/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round"
)
DEPRECATED_VISITALL_TRACE_ROOT = Path(
    "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_visitall_strict_v1_1st_round"
)
DEPRECATED_15PUZZLE_TRACE_ROOT = Path(
    "outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_15puzzle_easy_strict_v1_1st_round"
)
DEFAULT_CURRICULUM_OUTPUT_ROOT = Path("outputs/reasoning_traces/curriculum")


def test_curriculum_generator_default_uses_structured_reasoning_root() -> None:
    # Given: the approved structured parent for new curriculum traces.
    expected_root = DEFAULT_CURRICULUM_OUTPUT_ROOT

    # When: the curriculum generator default is resolved.
    observed_root = DEFAULT_OUTPUT_ROOT

    # Then: it cannot recreate a removed flat output root.
    assert observed_root == expected_root


def test_generator_without_dataset_root_uses_current_trace_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: the CLI omits a dataset root and the manifest builder is isolated.
    output_root = tmp_path / "output"
    received_roots: list[Path] = []

    def fake_build_pairing_manifest(
        dataset_roots: tuple[Path, ...], _output_root: Path, **_kwargs: PairingConfig
    ) -> dict[str, JSONValue]:
        received_roots.extend(dataset_roots)
        return {"summary": {"pairs": 0}}

    monkeypatch.setattr(generate_planimation_vlm, "build_pairing_manifest", fake_build_pairing_manifest)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_planimation_vlm.py",
            "--output-root",
            str(output_root),
            "--manifest-only",
        ],
    )

    # When: the default consumer runs through its CLI surface.
    result = generate_planimation_vlm.main()

    # Then: the fallback roots reach the builder without touching trace outputs.
    assert result == 0
    assert received_roots == list(CURRENT_TRACE_ROOTS)


def test_current_trace_roots_use_canonical_reasoning_location() -> None:
    # Given: the canonical curriculum source for current Planimation work.
    expected_roots = (CANONICAL_TRACE_ROOT,)

    # When: the default consumer's trace roots are resolved.
    observed_roots = tuple(CURRENT_TRACE_ROOTS)

    # Then: it reads only the canonical reasoning-trace root.
    assert observed_roots == expected_roots


def test_strict_shell_trace_roots_use_canonical_reasoning_locations() -> None:
    # Given: the approved curriculum root and the retained deprecated trace roots.
    expected_trace_roots = (
        CANONICAL_TRACE_ROOT,
        DEPRECATED_VISITALL_TRACE_ROOT,
        DEPRECATED_15PUZZLE_TRACE_ROOT,
    )
    trace_roots = tuple(re.findall(r'^TRACE_ROOT="([^"]+)"$', TEMPRUN.read_text(encoding="utf-8"), re.MULTILINE))

    # When: the shell assignments are resolved.
    observed_trace_roots = tuple(Path(trace_root) for trace_root in trace_roots)

    # Then: every active trace producer and consumer uses an existing structured root.
    assert observed_trace_roots == (
        expected_trace_roots[0],
        expected_trace_roots[1],
        expected_trace_roots[2],
        expected_trace_roots[0],
        expected_trace_roots[1],
        expected_trace_roots[2],
    )


@pytest.mark.parametrize(
    ("arguments", "expected_returncode"),
    (("--help", 0), ("--unknown", 2)),
)
def test_temprun_argument_guard_does_not_start_the_render_workflow(
    tmp_path: Path, arguments: str, expected_returncode: int
) -> None:
    # Given: a bounded launcher invocation with a test-local no-op sleep command.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    sleep_command = bin_dir / "sleep"
    sleep_command.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    sleep_command.chmod(0o755)
    environment = os.environ | {"HOME": str(tmp_path), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    command = ("bash", str(TEMPRUN), arguments)

    # When: help or an unsupported argument reaches the launcher.
    result = subprocess.run(
        command,
        cwd=tmp_path,
        check=False,
        capture_output=True,
        env=environment,
        text=True,
        timeout=5,
    )

    # Then: the launcher exits before invoking the generation or rendering commands.
    assert result.returncode == expected_returncode
    assert "Usage: temprun.sh" in result.stdout + result.stderr


def test_temprun_preserves_non_relocation_shell_contracts() -> None:
    # Given: the shell workflow as text, without sourcing or executing it.
    shell_text = TEMPRUN.read_text(encoding="utf-8")
    activation_lines = tuple(
        re.findall(r"^source ~/cd_vlaplan && source \.venv/bin/activate$", shell_text, re.MULTILINE)
    )
    trace_roots = tuple(re.findall(r'^TRACE_ROOT="([^"]+)"$', shell_text, re.MULTILINE))
    frame_roots = tuple(re.findall(r'^FRAME_ROOT="([^"]+)"$', shell_text, re.MULTILINE))

    # When: the protected shell contract is parsed by its stable assignment and argument forms.
    dataset_root_arguments = tuple(re.findall(r'^[ \t]+(--dataset-root "\$TRACE_ROOT") \\$', shell_text, re.MULTILINE))
    output_root_arguments = tuple(re.findall(r'^[ \t]+(--output-root "\$FRAME_ROOT") \\$', shell_text, re.MULTILINE))

    # Then: activation, canonical roots, and explicit consumers/producers are preserved.
    assert activation_lines == ("source ~/cd_vlaplan && source .venv/bin/activate",) * 6
    assert trace_roots[0] == str(CANONICAL_TRACE_ROOT)
    assert trace_roots[3] == str(CANONICAL_TRACE_ROOT)
    assert frame_roots == (
        "outputs/image_frames/phase3_planimation_frames_safe_no_visitall_$(date +%Y%m%d_%H%M%S)",
        "outputs/image_frames/phase3_planimation_frames_visitall_$(date +%Y%m%d_%H%M%S)",
        "outputs/image_frames/phase3_planimation_frames_15puzzle_easy_$(date +%Y%m%d_%H%M%S)",
    )
    assert dataset_root_arguments == ('--dataset-root "$TRACE_ROOT"',) * 3
    assert output_root_arguments == ('--output-root "$FRAME_ROOT"',) * 3
