from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.phase3 import output_layout_view_content, output_layout_view_stage
from scripts.phase3.output_layout_view import OutputLayoutViewError, create_output_layout_view
from test_output_layout_view import EXPECTED_LINKS, _seed_protected_targets


def test_new_view_revalidates_protected_content_after_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_protected_targets(tmp_path)
    target = tmp_path / EXPECTED_LINKS[0][1]
    original_publish = output_layout_view_stage.publish

    def publish_then_mutate(
        stage: output_layout_view_stage.PrivateStage,
        final_name: str,
    ) -> output_layout_view_stage.PublishedStage:
        published = original_publish(stage, final_name)
        target.write_text("changed after publication\n", encoding="utf-8")
        return published

    monkeypatch.setattr(output_layout_view_stage, "publish", publish_then_mutate)
    with pytest.raises(OutputLayoutViewError, match="protected target changed"):
        create_output_layout_view(tmp_path)
    assert (tmp_path / "outputs/datasets/phase3/planimation/stratified_pilot_20260725").is_dir()


def test_protected_content_fifo_substitution_before_regular_file_open_is_nonblocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = tmp_path / "protected.txt"
    protected.write_text("approved\n", encoding="utf-8")
    original_open = output_layout_view_content.os.open
    replaced = False

    def replace_regular_file_with_fifo(path: str | bytes | os.PathLike[str] | os.PathLike[bytes], flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
        nonlocal replaced
        if os.fsdecode(path) == protected.name and not replaced:
            replaced = True
            protected.unlink()
            os.mkfifo(protected)
            assert flags & os.O_NONBLOCK
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(output_layout_view_content.os, "open", replace_regular_file_with_fifo)
    with pytest.raises(OSError, match="protected file changed during tokenization"):
        output_layout_view_content.protected_content_token(protected)
