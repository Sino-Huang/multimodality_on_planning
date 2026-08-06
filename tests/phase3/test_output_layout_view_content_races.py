from __future__ import annotations

from pathlib import Path

import pytest

from scripts.phase3 import output_layout_view
from scripts.phase3.output_layout_view import OutputLayoutViewError, create_output_layout_view
from test_output_layout_view import EXPECTED_LINKS, _seed_protected_targets


def test_protected_regular_file_content_change_preserving_inode_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a synthetic protected file changes in place after preflight.
    _seed_protected_targets(tmp_path)
    target = tmp_path / EXPECTED_LINKS[0][1]
    original_inode = target.stat().st_ino
    original_preflight = output_layout_view._preflight

    def mutate_after_preflight(repository: Path):
        plan = original_preflight(repository)
        target.write_text("mutated\n", encoding="utf-8")
        return plan

    monkeypatch.setattr(output_layout_view, "_preflight", mutate_after_preflight)

    # When: the view verifies a plan captured before the in-place mutation.
    with pytest.raises(OutputLayoutViewError, match="protected target changed"):
        create_output_layout_view(tmp_path)

    # Then: identity was preserved, but no view was published against changed content.
    assert target.stat().st_ino == original_inode
    assert not (tmp_path / "outputs/datasets").exists()


def test_protected_directory_tree_change_preserving_root_inode_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a synthetic protected directory gains a descendant after preflight.
    _seed_protected_targets(tmp_path)
    target = tmp_path / EXPECTED_LINKS[9][1]
    original_inode = target.stat().st_ino
    original_preflight = output_layout_view._preflight

    def mutate_after_preflight(repository: Path):
        plan = original_preflight(repository)
        (target / "racer-child").write_text("mutated\n", encoding="utf-8")
        return plan

    monkeypatch.setattr(output_layout_view, "_preflight", mutate_after_preflight)

    # When: creation resumes with a changed protected directory tree.
    with pytest.raises(OutputLayoutViewError, match="protected target changed"):
        create_output_layout_view(tmp_path)

    # Then: the root identity was stable, but content drift prevents publication.
    assert target.stat().st_ino == original_inode
    assert not (tmp_path / "outputs/datasets").exists()
