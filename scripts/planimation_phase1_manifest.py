"""Manifest loading, local asset validation, and source synchronization."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, TypeAlias

import requests

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True)
class ManifestEntry:
    """One Planimation domain/problem/profile asset bundle."""

    domain_id: str
    problem_id: str
    domain_path: str
    problem_path: str
    animation_profile_path: str
    domain_source_url: str
    problem_source_url: str
    animation_profile_source_url: str
    notes: str = ""
    editor_session_id: str = ""


def load_manifest(manifest_path: Path) -> list[ManifestEntry]:
    """Load the non-empty Phase 1 manifest."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    instances = payload.get("instances")
    if not isinstance(instances, list) or not instances:
        raise ValueError(f"Manifest {manifest_path} must contain a non-empty 'instances' list")
    return [ManifestEntry(**instance) for instance in instances]


def manifest_root(manifest_path: Path) -> Path:
    """Return the directory containing a manifest."""
    return manifest_path.resolve().parent


def resolve_entry_paths(entry: ManifestEntry, manifest_path: Path) -> dict[str, Path]:
    """Resolve an entry's three local PDDL files."""
    root = manifest_root(manifest_path)
    return {
        "domain": root / entry.domain_path,
        "problem": root / entry.problem_path,
        "animation_profile": root / entry.animation_profile_path,
    }


def normalize_pddl_name(value: str) -> str:
    """Normalize a PDDL identifier for domain-name comparison."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def extract_domain_name(domain_text: str) -> str | None:
    """Extract a PDDL domain declaration."""
    match = re.search(r"\(define\s*\(domain\s+([^)\s]+)\)", domain_text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def extract_problem_domain_name(problem_text: str) -> str | None:
    """Extract a PDDL problem's referenced domain."""
    match = re.search(r"\(:domain\s+([^)\s]+)\)", problem_text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def validate_entry_assets(entry: ManifestEntry, manifest_path: Path) -> list[str]:
    """Return all local asset errors for one manifest entry."""
    errors: list[str] = []
    resolved = resolve_entry_paths(entry, manifest_path)
    for label, file_path in resolved.items():
        if not file_path.exists():
            errors.append(f"Missing {label} file: {file_path}")
        elif file_path.suffix.lower() != ".pddl":
            errors.append(f"{label} file must end with .pddl: {file_path}")
    if errors:
        return errors
    domain_name = extract_domain_name(resolved["domain"].read_text(encoding="utf-8"))
    problem_domain_name = extract_problem_domain_name(resolved["problem"].read_text(encoding="utf-8"))
    if domain_name is None:
        errors.append(f"Could not parse domain name from {resolved['domain']}")
    if problem_domain_name is None:
        errors.append(f"Could not parse (:domain ...) from {resolved['problem']}")
    if domain_name and problem_domain_name and normalize_pddl_name(domain_name) != normalize_pddl_name(problem_domain_name):
        errors.append(
            "Problem domain mismatch: "
            f"domain file declares '{domain_name}', problem file references '{problem_domain_name}'"
        )
    return errors


def unique_asset_downloads(entries: Sequence[ManifestEntry]) -> list[tuple[str, str]]:
    """Return unique relative asset paths and their immutable source URLs."""
    sources: dict[str, str] = {}
    for entry in entries:
        assets = (
            (entry.domain_path, entry.domain_source_url),
            (entry.problem_path, entry.problem_source_url),
            (entry.animation_profile_path, entry.animation_profile_source_url),
        )
        for relative_path, source_url in assets:
            existing = sources.get(relative_path)
            if existing and existing != source_url:
                raise ValueError(f"Conflicting source URLs for {relative_path}: {existing} vs {source_url}")
            sources[relative_path] = source_url
    return sorted(sources.items())


def select_entries(
    entries: Sequence[ManifestEntry], domains: set[str] | None, max_per_domain: int | None
) -> list[ManifestEntry]:
    """Select manifest entries by domain filter and per-domain limit."""
    selected: list[ManifestEntry] = []
    per_domain: dict[str, int] = {}
    for entry in entries:
        if domains and entry.domain_id not in domains:
            continue
        current_count = per_domain.get(entry.domain_id, 0)
        if max_per_domain is not None and current_count >= max_per_domain:
            continue
        per_domain[entry.domain_id] = current_count + 1
        selected.append(entry)
    return selected


def ensure_parent(path: Path) -> None:
    """Create a destination's parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: JsonValue) -> None:
    """Write one serialized manifest or render record."""
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sync_assets(manifest_path: Path, timeout: int, force: bool) -> dict[str, JsonValue]:
    """Download manifest assets and return validation results."""
    entries = load_manifest(manifest_path)
    root = manifest_root(manifest_path)
    downloaded = 0
    skipped = 0
    synced_files: list[str] = []
    with requests.Session() as session:
        for relative_path, source_url in unique_asset_downloads(entries):
            local_path = root / relative_path
            ensure_parent(local_path)
            if local_path.exists() and not force:
                skipped += 1
            else:
                response = session.get(source_url, timeout=timeout)
                response.raise_for_status()
                local_path.write_bytes(response.content)
                downloaded += 1
            synced_files.append(str(local_path))
    validation_errors = {
        f"{entry.domain_id}/{entry.problem_id}": validate_entry_assets(entry, manifest_path)
        for entry in entries
    }
    return {
        "manifest": str(manifest_path),
        "downloaded": downloaded,
        "skipped": skipped,
        "synced_files": synced_files,
        "validation_errors": validation_errors,
    }
