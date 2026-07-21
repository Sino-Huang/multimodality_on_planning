"""Phase 1 manifest rendering orchestration and output reporting."""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from .planimation_phase1_client import derive_endpoint_candidates, post_pddl_for_vfg, post_vfg_for_visualisation, preflight_host
from .planimation_phase1_frames import extract_png_archive, render_vfg_to_local_png_frames
from .planimation_phase1_manifest import JsonValue, ManifestEntry, load_manifest, resolve_entry_paths, select_entries, validate_entry_assets, write_json


def verify_output_dir(output_dir: Path) -> dict[str, JsonValue]:
    """Count persisted Phase 1 render artifacts by type."""
    other_visuals = [
        path for path in output_dir.rglob("*") if path.suffix.lower() in {".gif", ".mp4", ".webm"}
    ]
    return {
        "output_dir": str(output_dir),
        "result_files": len(list(output_dir.rglob("result.json"))),
        "png_files": len(list(output_dir.rglob("*.png"))),
        "vfg_files": len(list(output_dir.rglob("*.vfg.json"))),
        "other_visual_files": len(other_visuals),
    }


def _entry_payload(entry: ManifestEntry) -> dict[str, JsonValue]:
    return {
        "domain_id": entry.domain_id,
        "problem_id": entry.problem_id,
        "domain_path": entry.domain_path,
        "problem_path": entry.problem_path,
        "animation_profile_path": entry.animation_profile_path,
        "domain_source_url": entry.domain_source_url,
        "problem_source_url": entry.problem_source_url,
        "animation_profile_source_url": entry.animation_profile_source_url,
        "notes": entry.notes,
        "editor_session_id": entry.editor_session_id,
    }


def render_entries(
    manifest_path: Path,
    output_dir: Path,
    base_url: str | None,
    pddl_url: str | None,
    vfg_url: str | None,
    output_format: str,
    start_step: int,
    stop_step: int,
    quality: int,
    max_per_domain: int | None,
    domains: set[str] | None,
    timeout: int,
    sleep_seconds: float,
    min_successes: int,
    preflight_only: bool,
) -> dict[str, JsonValue]:
    """Render selected assets, retaining the PNG-only local fallback policy."""
    if stop_step <= start_step:
        raise ValueError("--stop-step must be greater than --start-step")
    selected = select_entries(load_manifest(manifest_path), domains=domains, max_per_domain=max_per_domain)
    if not selected:
        raise ValueError("No manifest entries selected for rendering")
    validation_errors = {
        f"{entry.domain_id}/{entry.problem_id}": validate_entry_assets(entry, manifest_path)
        for entry in selected
    }
    broken_entries = {key: errors for key, errors in validation_errors.items() if errors}
    if broken_entries:
        raise ValueError(f"Local asset validation failed: {json.dumps(broken_entries, indent=2)}")
    pddl_candidates, vfg_candidates, root_url = derive_endpoint_candidates(base_url, pddl_url, vfg_url)
    preflight = preflight_host(root_url, timeout=timeout)
    output_dir.mkdir(parents=True, exist_ok=True)
    if preflight_only:
        summary: dict[str, JsonValue] = {
            "mode": "preflight",
            "manifest": str(manifest_path),
            "root_url": root_url,
            "preflight": dict(preflight),
            "selected_entries": [_entry_payload(entry) for entry in selected],
        }
        write_json(output_dir / "summary.json", summary)
        return summary
    results: list[JsonValue] = []
    success_count = 0
    for index, entry in enumerate(selected):
        resolved = resolve_entry_paths(entry, manifest_path)
        instance_dir = output_dir / entry.domain_id / entry.problem_id
        instance_dir.mkdir(parents=True, exist_ok=True)
        started_at = time.time()
        result: dict[str, JsonValue] = {
            "domain_id": entry.domain_id,
            "problem_id": entry.problem_id,
            "format": output_format,
            "domain_path": str(resolved["domain"]),
            "problem_path": str(resolved["problem"]),
            "animation_profile_path": str(resolved["animation_profile"]),
            "status": "failed",
            "png_count": 0,
            "used_pddl_url": None,
            "used_vfg_url": None,
        }
        try:
            vfg_bytes, used_pddl_url = post_pddl_for_vfg(
                resolved["domain"], resolved["problem"], resolved["animation_profile"], pddl_candidates, timeout
            )
            result["used_pddl_url"] = used_pddl_url
            if output_format == "vfg":
                artifact_path = instance_dir / "trace.vfg.json"
                artifact_path.write_bytes(vfg_bytes)
            else:
                try:
                    render_bytes, used_vfg_url = post_vfg_for_visualisation(
                        vfg_bytes, output_format, vfg_candidates, start_step, stop_step, quality, timeout
                    )
                    result["used_vfg_url"] = used_vfg_url
                    if output_format == "png":
                        artifact_path = instance_dir / "frames"
                        result["png_count"] = extract_png_archive(render_bytes, artifact_path)
                    else:
                        artifact_path = instance_dir / f"animation.{output_format}"
                        artifact_path.write_bytes(render_bytes)
                except RuntimeError:
                    if output_format != "png":
                        raise
                    artifact_path = instance_dir / "frames"
                    result["png_count"] = render_vfg_to_local_png_frames(vfg_bytes, artifact_path, start_step, stop_step)
                    result["used_local_renderer"] = True
            result["artifact_path"] = str(artifact_path)
            result["status"] = "success"
            success_count += 1
        except (OSError, RuntimeError, ValueError, requests.RequestException) as error:
            result["error"] = str(error)
        result["elapsed_seconds"] = round(time.time() - started_at, 3)
        write_json(instance_dir / "result.json", result)
        results.append(result)
        if index < len(selected) - 1 and sleep_seconds > 0:
            time.sleep(sleep_seconds)
    summary = {
        "mode": "render",
        "manifest": str(manifest_path),
        "root_url": root_url,
        "preflight": dict(preflight),
        "selected_count": len(selected),
        "success_count": success_count,
        "failure_count": len(selected) - success_count,
        "min_successes": min_successes,
        "selected_entries": [_entry_payload(entry) for entry in selected],
        "results": results,
        "output_verification": verify_output_dir(output_dir),
    }
    write_json(output_dir / "summary.json", summary)
    if success_count < min_successes:
        raise RuntimeError(
            f"Only {success_count} render(s) succeeded, below required minimum {min_successes}. "
            f"See {output_dir / 'summary.json'} for details."
        )
    return summary
