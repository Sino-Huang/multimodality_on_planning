from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.phase3.trace_contracts import FrozenSourceIdentity, TraceContractError, project_traversal_events

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_CASES = REPOSITORY_ROOT / "tests/phase3/fixtures/traversal_trace_contract_cases.json"
RELEASE_SHA256 = "3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3"


def test_existing_release_digest_and_trace_v1_verifier_are_characterized() -> None:
    # Given: the canonical 12-row release and frozen trace-v1 verifier vectors.
    release = REPOSITORY_ROOT / "data/planning_cgas_v1/release_manifest.json"
    cases = json.loads(FIXTURE_CASES.read_text(encoding="utf-8"))

    # When: the current release and every legacy vector are verified without v2 code.
    outcomes: list[tuple[str, str]] = []
    for case in cases:
        row = case["source_row"]
        identity = FrozenSourceIdentity(
            "fixture-root",
            "train.jsonl",
            0,
            f"hash-{row['example_id']}",
            row["example_id"],
            row["planner"],
        )
        try:
            project_traversal_events(identity, row)
        except TraceContractError as error:
            outcomes.append((case["name"], error.reason))
        else:
            outcomes.append((case["name"], "projected"))

    # Then: release bytes and trace-v1 behavior remain pinned exactly.
    assert hashlib.sha256(release.read_bytes()).hexdigest() == RELEASE_SHA256
    assert outcomes == [
        ("ff_valid", "projected"),
        ("ff_malformed", "missing_required_field: selected_action"),
        ("gbfs_valid", "projected"),
        ("gbfs_malformed", "missing_required_field: heuristic_source"),
        ("iw_valid", "projected"),
        ("iw_malformed", "missing_required_field: decision"),
        ("graphplan_valid", "projected"),
        ("graphplan_malformed", "missing_required_field: layer_index"),
    ]


def test_archive_is_byte_preserving_idempotent_and_regular(tmp_path: Path) -> None:
    from scripts.phase3.cgas_fixture_archive import archive_fixture

    # Given: a release-shaped source tree with the pinned release manifest.
    source = _source_tree(tmp_path)
    archive = tmp_path / "fixture"

    # When: the archive is published and the exact command is rerun.
    first = archive_fixture(source, archive, RELEASE_SHA256)
    before = _tree_bytes(archive)
    second = archive_fixture(source, archive, RELEASE_SHA256)

    # Then: every leaf is independent, regular, and byte-identical on rerun.
    assert first.status == "archived"
    assert second.status == "already_archived"
    assert _tree_bytes(source) == before == _tree_bytes(archive)
    assert all(not path.is_symlink() for path in archive.rglob("*"))
    assert all(os.stat(path).st_nlink == 1 for path in archive.rglob("*") if path.is_file())


def test_archive_rejects_mismatch_and_symlink_without_mutation(tmp_path: Path) -> None:
    from scripts.phase3.cgas_fixture_archive import FixtureArchiveError, archive_fixture

    # Given: a source tree, an existing mismatched archive, and stable snapshots.
    source = _source_tree(tmp_path)
    archive = tmp_path / "fixture"
    archive.mkdir()
    (archive / "different.txt").write_bytes(b"different")
    source_before = _tree_bytes(source)
    archive_before = _tree_bytes(archive)

    # When: publication encounters mismatched existing bytes.
    with pytest.raises(FixtureArchiveError, match="fixture_archive_mismatch"):
        archive_fixture(source, archive, RELEASE_SHA256)

    # Then: neither root changes, and symlink input also fails closed.
    assert _tree_bytes(source) == source_before
    assert _tree_bytes(archive) == archive_before
    linked_source = _source_tree(tmp_path / "linked")
    (linked_source / "link").symlink_to(linked_source / "payload.bin")
    with pytest.raises(FixtureArchiveError, match="fixture_archive_symlink"):
        archive_fixture(linked_source, tmp_path / "linked-archive", RELEASE_SHA256)
    assert not (tmp_path / "linked-archive").exists()


def _source_tree(root: Path) -> Path:
    source = root / "source"
    source.mkdir(parents=True)
    (source / "release_manifest.json").write_bytes(
        (REPOSITORY_ROOT / "data/planning_cgas_v1/release_manifest.json").read_bytes()
    )
    (source / "nested").mkdir()
    (source / "nested/empty.bin").write_bytes(b"")
    (source / "payload.bin").write_bytes(b"\x00fixture-bytes\xff")
    return source


def _tree_bytes(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): None if path.is_dir() else path.read_bytes()
        for path in sorted(root.rglob("*"))
        if not path.is_symlink()
    }
