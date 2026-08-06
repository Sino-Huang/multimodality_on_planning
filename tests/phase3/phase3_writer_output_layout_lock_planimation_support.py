from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Literal, TypeAlias

from typing_extensions import assert_never

import pytest

from scripts.phase3 import generate_planimation_vlm
from phase3_writer_output_layout_lock_support import WriterMutationError


PlanimationMode: TypeAlias = Literal["render-only", "full"]


def patch_planimation_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    mode: PlanimationMode,
    raises_after_validation: bool,
    output_root: Path,
) -> Callable[[], None]:
    def build_manifest(_roots: list[Path], _output_root: Path, *, config) -> dict[str, dict[str, str]]:
        _ = config
        events.append("manifest")
        return {"summary": {}}

    def render(_output_root: Path, *, config, max_states, output_mode, progress_callback, progress_every) -> dict[str, str]:
        _ = config, max_states, output_mode, progress_callback, progress_every
        events.append("render")
        return {}

    def records(_output_root: Path, *, reasoning_budget_chars: int) -> list[dict[str, str]]:
        _ = reasoning_budget_chars
        events.append("records")
        return []

    def validate(_output_root: Path) -> dict[str, str]:
        events.append("validate")
        if raises_after_validation:
            raise WriterMutationError()
        return {}

    monkeypatch.setattr(generate_planimation_vlm, "build_pairing_manifest", build_manifest)
    monkeypatch.setattr(generate_planimation_vlm, "render_replay_states", render)
    monkeypatch.setattr(generate_planimation_vlm, "build_vlm_records", records)
    monkeypatch.setattr(generate_planimation_vlm, "validate_pairing_output", validate)
    arguments = ["generate_planimation_vlm.py", "--output-root", str(output_root)]
    match mode:
        case "render-only":
            arguments.append("--render-only")
        case "full":
            pass
        case unreachable:
            assert_never(unreachable)
    monkeypatch.setattr(sys, "argv", arguments)
    return _run_planimation


def _run_planimation() -> None:
    _ = generate_planimation_vlm.main()
