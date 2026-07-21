"""Compatibility facade for Phase 3 Planimation pairing workflows."""

from __future__ import annotations

from collections.abc import Iterable
from . import planimation_pairing_implementation as _implementation
from pathlib import Path

from .planimation_pairing_contracts import PairingConfig, ProgressCallback, RenderConfig, StateRenderer
from .traversal_state_types import JSONValue

globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)


def _synchronize_source_hooks() -> None:
    _implementation._source_jsonl_rows = _source_jsonl_rows
    _implementation._source_root_snapshot = _source_root_snapshot


def build_pairing_manifest(
    dataset_roots: Iterable[Path], output_root: Path, *, config: PairingConfig = PairingConfig()
) -> dict[str, JSONValue]:
    _synchronize_source_hooks()
    return _implementation.build_pairing_manifest(dataset_roots, output_root, config=config)


def render_replay_states(
    output_root: Path,
    *,
    renderer: StateRenderer | None = None,
    config: RenderConfig = RenderConfig(),
    max_states: int | None = None,
    output_mode: str = "production",
    progress_callback: ProgressCallback | None = None,
    progress_every: int = 100,
) -> dict[str, JSONValue]:
    _synchronize_source_hooks()
    return _implementation.render_replay_states(
        output_root,
        renderer=renderer,
        config=config,
        max_states=max_states,
        output_mode=output_mode,
        progress_callback=progress_callback,
        progress_every=progress_every,
    )


def build_vlm_records(output_root: Path, *, reasoning_budget_chars: int = 8192) -> dict[str, JSONValue]:
    _synchronize_source_hooks()
    return _implementation.build_vlm_records(output_root, reasoning_budget_chars=reasoning_budget_chars)


def validate_pairing_output(output_root: Path) -> dict[str, JSONValue]:
    """Validate output while preserving legacy monkeypatchable source seams."""
    _synchronize_source_hooks()
    return _implementation.validate_pairing_output(output_root)
