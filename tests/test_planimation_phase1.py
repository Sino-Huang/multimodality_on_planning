from __future__ import annotations

import io
import importlib
import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import requests
from PIL import Image

from scripts.planimation_phase1 import (
    derive_endpoint_candidates,
    extract_png_archive,
    load_manifest,
    post_pddl_for_vfg,
    preflight_host,
    render_vfg_to_local_png_frames,
    select_entries,
    unique_asset_downloads,
    validate_entry_assets,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_MANIFEST_PATH = REPO_ROOT / "data" / "pddl_instances" / "manifest.json"
EXPECTED_REAL_DOMAIN_IDS = {
    "15puzzle",
    "block3op",
    "blocksworld",
    "depot",
    "driverlog",
    "elevators",
    "family_and_fisherman",
    "farmer_crosses_river",
    "ferry",
    "flowfree",
    "freecell",
    "grid",
    "gripper",
    "logistics",
    "snake",
    "storage",
    "switching_soldier",
    "towers_of_hanoi",
    "visitall",
    "bloxorz",
    "lights_out",
    "sokoban",
    "traffic_rush",
}
LEGACY_README_ONLY_DOMAIN_IDS = {"zenotravel", "floortile", "hiking", "nurikabe", "peg", "tpp"}



def build_base64_png() -> str:
    image = Image.new("RGBA", (1, 1), (255, 255, 255, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    import base64

    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "manifest.json"
    manifest = {
        "instances": [
            {
                "domain_id": "grid",
                "problem_id": "prob01",
                "domain_path": "grid/domain_grid.pddl",
                "problem_path": "grid/prob01.pddl",
                "animation_profile_path": "grid/grid_AP.pddl",
                "domain_source_url": "https://example.com/domain_grid.pddl",
                "problem_source_url": "https://example.com/prob01.pddl",
                "animation_profile_source_url": "https://example.com/grid_AP.pddl",
                "notes": "test entry",
                "editor_session_id": "abc123",
            },
            {
                "domain_id": "logistics",
                "problem_id": "prob01",
                "domain_path": "logistics/domain.pddl",
                "problem_path": "logistics/prob01.pddl",
                "animation_profile_path": "logistics/logistics_ap.pddl",
                "domain_source_url": "https://example.com/logistics/domain.pddl",
                "problem_source_url": "https://example.com/logistics/prob01.pddl",
                "animation_profile_source_url": "https://example.com/logistics/logistics_ap.pddl",
                "notes": "test entry",
                "editor_session_id": "def456",
            },
        ]
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_load_manifest_and_unique_downloads(tmp_path: Path) -> None:
    manifest_path = build_manifest(tmp_path)
    entries = load_manifest(manifest_path)

    assert len(entries) == 2
    downloads = unique_asset_downloads(entries)
    assert len(downloads) == 6
    assert downloads[0][0] == "grid/domain_grid.pddl"


def test_phase1_facade_reexports_remote_and_frame_boundaries_by_identity() -> None:
    facade = importlib.import_module("scripts.planimation_phase1")
    client = importlib.import_module("scripts.planimation_phase1_client")
    frames = importlib.import_module("scripts.planimation_phase1_frames")

    assert facade.post_pddl_for_vfg is client.post_pddl_for_vfg
    assert facade.post_vfg_for_visualisation is client.post_vfg_for_visualisation
    assert facade.preflight_host is client.preflight_host
    assert facade.render_vfg_to_local_png_frames is frames.render_vfg_to_local_png_frames


def test_real_manifest_matches_current_actionable_domain_set() -> None:
    entries = load_manifest(REAL_MANIFEST_PATH)
    domain_ids = {entry.domain_id for entry in entries}

    assert len(entries) == 23
    assert domain_ids == EXPECTED_REAL_DOMAIN_IDS
    assert LEGACY_README_ONLY_DOMAIN_IDS.isdisjoint(domain_ids)
    assert {"grid", "logistics", "towers_of_hanoi", "driverlog", "freecell"}.issubset(domain_ids)

    for entry in entries:
        assert entry.domain_path.endswith(".pddl")
        assert entry.problem_path.endswith(".pddl")
        assert entry.animation_profile_path.endswith(".pddl")
        assert entry.domain_source_url.startswith("https://raw.githubusercontent.com/planimation/documentation/master/")
        assert entry.problem_source_url.startswith("https://raw.githubusercontent.com/planimation/documentation/master/")
        assert entry.animation_profile_source_url.startswith(
            "https://raw.githubusercontent.com/planimation/documentation/master/"
        )


def test_validate_entry_assets_accepts_matching_domain_names(tmp_path: Path) -> None:
    manifest_path = build_manifest(tmp_path)
    entries = load_manifest(manifest_path)

    write_text(tmp_path / "grid/domain_grid.pddl", "(define (domain grid))")
    write_text(tmp_path / "grid/prob01.pddl", "(define (problem p1) (:domain grid))")
    write_text(tmp_path / "grid/grid_AP.pddl", "(define (domain grid-visuals))")

    assert validate_entry_assets(entries[0], manifest_path) == []


def test_validate_entry_assets_rejects_mismatched_problem_domain(tmp_path: Path) -> None:
    manifest_path = build_manifest(tmp_path)
    entries = load_manifest(manifest_path)

    write_text(tmp_path / "grid/domain_grid.pddl", "(define (domain grid))")
    write_text(tmp_path / "grid/prob01.pddl", "(define (problem p1) (:domain logistics))")
    write_text(tmp_path / "grid/grid_AP.pddl", "(define (domain grid-visuals))")

    errors = validate_entry_assets(entries[0], manifest_path)
    assert any("Problem domain mismatch" in error for error in errors)


def test_derive_endpoint_candidates_from_base_url() -> None:
    pddl_candidates, vfg_candidates, root_url = derive_endpoint_candidates(
        base_url="https://planimation.planning.domains",
        pddl_url=None,
        vfg_url=None,
    )

    assert pddl_candidates[0].endswith("/upload/pddl")
    assert pddl_candidates[1].endswith("/upload/(?P<filename>[^/]+)$")
    assert pddl_candidates[2].endswith("/upload/")
    assert vfg_candidates[0].endswith("/downloadVisualisation")
    assert root_url == "https://planimation.planning.domains"


def test_derive_endpoint_candidates_preserves_explicit_overrides() -> None:
    pddl_candidates, vfg_candidates, root_url = derive_endpoint_candidates(
        base_url=None,
        pddl_url="https://example.test/api/upload",
        vfg_url="https://example.test/api/render",
    )

    assert pddl_candidates == ["https://example.test/api/upload"]
    assert vfg_candidates == ["https://example.test/api/render"]
    assert root_url == "https://example.test"


def test_preflight_host_reports_named_request_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_get(*_args: object, **_kwargs: object) -> None:
        raise requests.ConnectionError("offline")

    monkeypatch.setattr("scripts.planimation_phase1_client.requests.get", fail_get)

    report = preflight_host("https://example.test", timeout=7)

    assert report["reachable"] is False
    assert report["root_url"] == "https://example.test"
    assert "offline" in str(report["error"])


def test_post_pddl_propagates_unexpected_adapter_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    domain_path = tmp_path / "domain.pddl"
    problem_path = tmp_path / "problem.pddl"
    profile_path = tmp_path / "profile.pddl"
    for path in (domain_path, problem_path, profile_path):
        path.write_text("(define)", encoding="utf-8")

    def broken_post(*_args: object, **_kwargs: object) -> None:
        raise AttributeError("request adapter contract violation")

    monkeypatch.setattr("scripts.planimation_phase1_client.requests.post", broken_post)

    with pytest.raises(AttributeError, match="request adapter contract violation"):
        post_pddl_for_vfg(
            domain_path,
            problem_path,
            profile_path,
            ["https://example.test/upload"],
            timeout=3,
        )


def test_select_entries_respects_domain_filter_and_limit(tmp_path: Path) -> None:
    manifest_path = build_manifest(tmp_path)
    entries = load_manifest(manifest_path)

    selected = select_entries(entries, domains={"grid"}, max_per_domain=1)
    assert len(selected) == 1
    assert selected[0].domain_id == "grid"


def test_extract_png_archive_unzips_frames(tmp_path: Path) -> None:
    output_dir = tmp_path / "frames"
    archive_buffer = io.BytesIO()
    frame_buffer = io.BytesIO()
    Image.new("RGBA", (1, 1), (255, 255, 255, 255)).save(frame_buffer, format="PNG")
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("frame_000.png", frame_buffer.getvalue())
        archive.writestr("frame_001.png", frame_buffer.getvalue())

    png_count = extract_png_archive(archive_buffer.getvalue(), output_dir)
    assert png_count == 2
    assert (output_dir / "frame_000.png").exists()


def test_render_vfg_to_local_png_frames_writes_pngs(tmp_path: Path) -> None:
    payload = {
        "visualStages": [
            {
                "visualSprites": [
                    {
                        "prefabImage": "Block",
                        "name": "a",
                        "showName": True,
                        "color": {"r": 0.8, "g": 0.2, "b": 0.2, "a": 1.0},
                        "minX": 0.1,
                        "maxX": 0.3,
                        "minY": 0.1,
                        "maxY": 0.3,
                    }
                ]
            }
        ],
        "imageTable": {
            "m_keys": ["Block"],
            "m_values": [build_base64_png()],
        },
    }

    frame_count = render_vfg_to_local_png_frames(
        vfg_bytes=json.dumps(payload).encode("utf-8"),
        output_dir=tmp_path / "rendered",
        start_step=0,
        stop_step=0,
        canvas_size=128,
    )

    assert frame_count == 1
    frame_path = tmp_path / "rendered" / "frame_000.png"
    assert frame_path.exists()
    with Image.open(frame_path) as frame:
        frame.verify()
    with Image.open(frame_path) as frame:
        assert frame.size == (128, 128)
