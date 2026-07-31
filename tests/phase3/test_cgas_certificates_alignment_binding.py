from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Callable

import pytest

from scripts.phase3.cgas_alignment import build_alignment
from scripts.phase3.cgas_certificates import build_steps, verify_steps
from scripts.phase3.cgas_provenance import SPLITS
from scripts.phase3.cgas_serialization import canonical, digest, digest_text
from test_cgas_alignment import _build_cgas_source, _write_render_manifest


Mutation = Callable[[list[dict[str, object]]], None]


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        ("missing", "missing_alignment_manifest"),
        ("malformed", "malformed_alignment_manifest"),
        ("digest", "alignment_manifest_mismatch"),
    ],
)
def test_build_rejects_invalid_persisted_alignment_manifest_before_step_emission(
    tmp_path: Path, mode: str, reason: str
) -> None:
    # Given: accepted source and alignment output with one persisted-manifest defect.
    source_root, alignment_root = _accepted_alignment(tmp_path)
    manifest_path = alignment_root / "alignment" / "manifest.json"
    match mode:
        case "missing":
            manifest_path.unlink()
        case "malformed":
            manifest_path.write_text("{not-json", encoding="utf-8")
        case "digest":
            manifest = _manifest(alignment_root)
            manifest["alignment_digest"] = "stale-alignment-digest"
            manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        case _:
            raise AssertionError(mode)
    output_root = tmp_path / f"steps-{mode}"

    # When: Todo 4 consumes the persisted accepted-alignment boundary.
    report = build_steps(source_root, alignment_root, output_root)

    # Then: invalid acceptance metadata fails closed before certificate publication.
    assert report["accepted_rows"] == 0
    assert reason in _reasons(report)
    assert not output_root.exists()


@pytest.mark.parametrize(
    ("name", "mutate", "reason"),
    [
        ("path", lambda rows: rows[0].__setitem__("png_path", "missing-frame.png"), "alignment_png_unreadable"),
        ("hash", lambda rows: rows[0].__setitem__("png_sha256", "0" * 64), "alignment_png_hash_mismatch"),
        ("status", lambda rows: rows[0].__setitem__("vision_status", "vision_rejected"), "alignment_vision_status_mismatch"),
        ("action", lambda rows: rows[0].__setitem__("action", "(stale-action)"), "alignment_action_mismatch"),
        ("state", lambda rows: rows[0].__setitem__("state_before_hash", "0" * 64), "alignment_state_before_hash_mismatch"),
        ("split", lambda rows: rows[0].__setitem__("split", "dev"), "alignment_split_mismatch"),
    ],
)
def test_build_rejects_tampered_persisted_alignment_row_before_step_emission(
    tmp_path: Path, name: str, mutate: Mutation, reason: str
) -> None:
    # Given: a persisted alignment row changed after Todo 3 acceptance.
    source_root, alignment_root = _accepted_alignment(tmp_path)
    rows = _rows(alignment_root)
    mutate(rows)
    _write_rows_and_matching_manifest(source_root, alignment_root, rows)
    output_root = tmp_path / f"steps-{name}"

    # When: Todo 4 builds from the tampered persisted artifact.
    report = build_steps(source_root, alignment_root, output_root)

    # Then: row-level validation rejects it even with a recomputed manifest digest.
    assert report["accepted_rows"] == 0
    assert reason in _reasons(report)
    assert not output_root.exists()


@pytest.mark.parametrize(
    ("name", "mutate", "reason"),
    [
        ("duplicate", lambda rows: rows.append(dict(rows[0])), "duplicate_alignment_source_transition"),
        ("missing", lambda rows: rows.pop(0), "missing_accepted_alignment"),
        (
            "unknown",
            lambda rows: rows.append({**rows[0], "source_transition_id": "unknown-transition"}),
            "unknown_alignment_source_transition",
        ),
    ],
)
def test_verify_rejects_persisted_alignment_set_mismatch_before_step_validation(
    tmp_path: Path, name: str, mutate: Mutation, reason: str
) -> None:
    # Given: a valid certificate output and a one-to-one alignment-set violation.
    source_root, alignment_root = _accepted_alignment(tmp_path)
    output_root = tmp_path / f"steps-{name}"
    assert build_steps(source_root, alignment_root, output_root)["accepted_rows"] == 12
    rows = _rows(alignment_root)
    mutate(rows)
    _write_rows_and_matching_manifest(source_root, alignment_root, rows)

    # When: verification reloads its persisted Todo 3 dependency.
    report = verify_steps(source_root, alignment_root, output_root)

    # Then: it rejects the dependency before accepting stale certificate rows.
    assert report["accepted_rows"] == 0
    assert reason in _reasons(report)


def _accepted_alignment(root: Path) -> tuple[Path, Path]:
    source_root = _build_cgas_source(root)
    alignment_root = root / "alignment-output"
    assert not build_alignment(source_root, _write_render_manifest(source_root, root / "renders"), alignment_root)["rejections"]
    return source_root, alignment_root


def _rows(alignment_root: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for split in SPLITS
        for line in (alignment_root / "alignment" / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def _manifest(alignment_root: Path) -> dict[str, object]:
    value = json.loads((alignment_root / "alignment" / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _reasons(report: dict[str, object]) -> set[str]:
    rejections = report["rejections"]
    assert isinstance(rejections, list)
    return {
        item["reason"]
        for item in rejections
        if isinstance(item, dict) and isinstance(item.get("reason"), str)
    }


def _write_rows_and_matching_manifest(source_root: Path, alignment_root: Path, rows: list[dict[str, object]]) -> None:
    alignment = alignment_root / "alignment"
    for split in SPLITS:
        split_rows = [row for row in rows if row.get("split") == split]
        (alignment / f"{split}.jsonl").write_text("".join(canonical(row) + "\n" for row in split_rows), encoding="utf-8")
    persisted_rows = _rows(alignment_root)
    manifest = _manifest(alignment_root)
    manifest["source_digest"] = digest_text("|".join(digest(source_root / "source" / f"{split}.jsonl") for split in SPLITS))
    manifest["alignment_digest"] = digest_text(canonical(persisted_rows))
    manifest["counts"] = dict(sorted(Counter(str(row["split"]) for row in persisted_rows).items()))
    (alignment / "manifest.json").write_text(canonical(manifest) + "\n", encoding="utf-8")
