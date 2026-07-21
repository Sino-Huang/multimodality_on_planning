"""Compatibility CLI facade for Phase 1 Planimation utilities."""

from __future__ import annotations

from scripts.planimation_phase1_cli import build_parser, main
from scripts.planimation_phase1_client import (
    DEFAULT_BASE_URL,
    derive_endpoint_candidates,
    post_pddl_for_vfg,
    post_vfg_for_visualisation,
    preflight_host,
)
from scripts.planimation_phase1_frames import extract_png_archive, render_vfg_to_local_png_frames
from scripts.planimation_phase1_manifest import (
    ManifestEntry,
    ensure_parent,
    extract_domain_name,
    extract_problem_domain_name,
    load_manifest,
    manifest_root,
    normalize_pddl_name,
    resolve_entry_paths,
    select_entries,
    sync_assets,
    unique_asset_downloads,
    validate_entry_assets,
    write_json,
)
from scripts.planimation_phase1_runner import render_entries, verify_output_dir

__all__ = [
    "DEFAULT_BASE_URL",
    "ManifestEntry",
    "build_parser",
    "derive_endpoint_candidates",
    "ensure_parent",
    "extract_domain_name",
    "extract_png_archive",
    "extract_problem_domain_name",
    "load_manifest",
    "main",
    "manifest_root",
    "normalize_pddl_name",
    "post_pddl_for_vfg",
    "post_vfg_for_visualisation",
    "preflight_host",
    "render_entries",
    "render_vfg_to_local_png_frames",
    "resolve_entry_paths",
    "select_entries",
    "sync_assets",
    "unique_asset_downloads",
    "validate_entry_assets",
    "verify_output_dir",
    "write_json",
]


if __name__ == "__main__":
    raise SystemExit(main())
