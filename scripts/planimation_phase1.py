from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import zipfile
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

import requests


DEFAULT_BASE_URL = "https://planimation.planning.domains"


@dataclass(frozen=True)
class ManifestEntry:
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
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    instances = payload.get("instances")
    if not isinstance(instances, list) or not instances:
        raise ValueError(f"Manifest {manifest_path} must contain a non-empty 'instances' list")
    return [ManifestEntry(**instance) for instance in instances]


def manifest_root(manifest_path: Path) -> Path:
    return manifest_path.resolve().parent


def resolve_entry_paths(entry: ManifestEntry, manifest_path: Path) -> dict[str, Path]:
    root = manifest_root(manifest_path)
    return {
        "domain": root / entry.domain_path,
        "problem": root / entry.problem_path,
        "animation_profile": root / entry.animation_profile_path,
    }


def normalize_pddl_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def extract_domain_name(domain_text: str) -> str | None:
    match = re.search(r"\(define\s*\(domain\s+([^)\s]+)\)", domain_text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def extract_problem_domain_name(problem_text: str) -> str | None:
    match = re.search(r"\(:domain\s+([^)\s]+)\)", problem_text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def validate_entry_assets(entry: ManifestEntry, manifest_path: Path) -> list[str]:
    errors: list[str] = []
    resolved = resolve_entry_paths(entry, manifest_path)

    for label, file_path in resolved.items():
        if not file_path.exists():
            errors.append(f"Missing {label} file: {file_path}")
            continue
        if file_path.suffix.lower() != ".pddl":
            errors.append(f"{label} file must end with .pddl: {file_path}")

    if errors:
        return errors

    domain_text = resolved["domain"].read_text(encoding="utf-8")
    problem_text = resolved["problem"].read_text(encoding="utf-8")
    domain_name = extract_domain_name(domain_text)
    problem_domain_name = extract_problem_domain_name(problem_text)

    if domain_name is None:
        errors.append(f"Could not parse domain name from {resolved['domain']}")
    if problem_domain_name is None:
        errors.append(f"Could not parse (:domain ...) from {resolved['problem']}")
    if domain_name and problem_domain_name:
        if normalize_pddl_name(domain_name) != normalize_pddl_name(problem_domain_name):
            errors.append(
                "Problem domain mismatch: "
                f"domain file declares '{domain_name}', problem file references '{problem_domain_name}'"
            )

    return errors


def unique_asset_downloads(entries: Sequence[ManifestEntry]) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for entry in entries:
        asset_pairs = {
            entry.domain_path: entry.domain_source_url,
            entry.problem_path: entry.problem_source_url,
            entry.animation_profile_path: entry.animation_profile_source_url,
        }
        for relative_path, source_url in asset_pairs.items():
            existing = seen.get(relative_path)
            if existing and existing != source_url:
                raise ValueError(f"Conflicting source URLs for {relative_path}: {existing} vs {source_url}")
            seen[relative_path] = source_url
    return sorted(seen.items())


def derive_endpoint_candidates(
    base_url: str | None,
    pddl_url: str | None,
    vfg_url: str | None,
) -> tuple[list[str], list[str], str]:
    if pddl_url:
        pddl_candidates = [pddl_url]
    else:
        if not base_url:
            raise ValueError("Either --base-url or --pddl-url must be provided")
        trimmed = base_url.rstrip("/")
        pddl_candidates = [
            f"{trimmed}/upload/pddl",
            f"{trimmed}/upload/(?P<filename>[^/]+)$",
            f"{trimmed}/upload/",
        ]

    if vfg_url:
        vfg_candidates = [vfg_url]
    else:
        if not base_url:
            raise ValueError("Either --base-url or --vfg-url must be provided")
        trimmed = base_url.rstrip("/")
        vfg_candidates = [
            f"{trimmed}/downloadVisualisation",
            f"{trimmed}/downloadVisualisation/",
        ]

    root_source = base_url or pddl_candidates[0]
    parsed = urlparse(root_source)
    root_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else root_source
    return pddl_candidates, vfg_candidates, root_url


def select_entries(
    entries: Sequence[ManifestEntry],
    domains: set[str] | None,
    max_per_domain: int | None,
) -> list[ManifestEntry]:
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
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sync_assets(manifest_path: Path, timeout: int, force: bool) -> dict[str, Any]:
    entries = load_manifest(manifest_path)
    downloads = unique_asset_downloads(entries)
    root = manifest_root(manifest_path)

    downloaded = 0
    skipped = 0
    synced_files: list[str] = []

    with requests.Session() as session:
        for relative_path, source_url in downloads:
            local_path = root / relative_path
            ensure_parent(local_path)
            if local_path.exists() and not force:
                skipped += 1
                synced_files.append(str(local_path))
                continue

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


def preflight_host(root_url: str, timeout: int) -> dict[str, Any]:
    started_at = time.time()
    try:
        response = requests.get(root_url, timeout=timeout)
        return {
            "root_url": root_url,
            "reachable": True,
            "status_code": response.status_code,
            "elapsed_seconds": round(time.time() - started_at, 3),
        }
    except requests.RequestException as exc:
        return {
            "root_url": root_url,
            "reachable": False,
            "error": str(exc),
            "elapsed_seconds": round(time.time() - started_at, 3),
        }


def post_pddl_for_vfg(
    domain_path: Path,
    problem_path: Path,
    animation_profile_path: Path,
    pddl_candidates: Sequence[str],
    timeout: int,
) -> tuple[bytes, str]:
    domain_text = domain_path.read_text(encoding="utf-8")
    problem_text = problem_path.read_text(encoding="utf-8")
    animation_profile_text = animation_profile_path.read_text(encoding="utf-8")
    errors: list[str] = []

    for url in pddl_candidates:
        try:
            response = requests.post(
                url,
                files={
                    "domain": (None, domain_text),
                    "problem": (None, problem_text),
                    "animation": (None, animation_profile_text),
                },
                timeout=timeout,
            )
            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError:
                    return response.content, url

                if payload.get("status") == "error":
                    errors.append(f"{url} -> API error: {payload.get('message', 'Unknown error')}")
                    continue

                return json.dumps(payload).encode("utf-8"), url
            errors.append(f"{url} -> HTTP {response.status_code}: {response.text[:300]}")
        except requests.RequestException as exc:
            errors.append(f"{url} -> {exc}")

    raise RuntimeError("Failed to submit PDDL bundle. Attempts: " + " | ".join(errors))


def post_vfg_for_visualisation(
    vfg_bytes: bytes,
    output_format: str,
    vfg_candidates: Sequence[str],
    start_step: int,
    stop_step: int,
    quality: int,
    timeout: int,
) -> tuple[bytes, str]:
    try:
        vfg_text = json.dumps(json.loads(vfg_bytes.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Returned VFG payload is not valid UTF-8 JSON") from exc

    payload: dict[str, Any] = {
        "vfg": vfg_text,
        "fileType": output_format,
    }
    if output_format in {"gif", "mp4", "webm", "png"}:
        payload["params"] = {
            "fileType": output_format,
            "startStep": start_step,
            "stopStep": stop_step,
            "quality": quality,
        }

    errors: list[str] = []

    for url in vfg_candidates:
        request_attempts = [
            {"json": payload},
            {"data": json.dumps(payload), "headers": {"Content-Type": "application/json"}},
        ]
        for attempt in request_attempts:
            try:
                response = requests.post(url, timeout=timeout, **attempt)
                if response.status_code == 200:
                    return response.content, url
                errors.append(f"{url} -> HTTP {response.status_code}: {response.text[:300]}")
            except requests.RequestException as exc:
                errors.append(f"{url} -> {exc}")

    raise RuntimeError("Failed to render VFG payload. Attempts: " + " | ".join(errors))


def extract_png_archive(archive_bytes: bytes, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BytesIO(archive_bytes), "r") as archive:
        archive.extractall(output_dir)
    return len(list(output_dir.rglob("*.png")))


def _import_pillow() -> tuple[Any, Any, Any]:
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as exc:  # pragma: no cover - validated by runtime environment
        raise RuntimeError("Pillow is required for local PNG rendering fallback") from exc
    return Image, ImageDraw, ImageOps


def _sprite_bounds(sprite: dict[str, Any], canvas_size: int) -> tuple[int, int, int, int]:
    min_x = float(sprite.get("minX", 0.0))
    max_x = float(sprite.get("maxX", 1.0))
    min_y = float(sprite.get("minY", 0.0))
    max_y = float(sprite.get("maxY", 1.0))
    left = max(int(min_x * canvas_size), 0)
    right = min(max(int(max_x * canvas_size), left + 1), canvas_size)
    top = max(int((1.0 - max_y) * canvas_size), 0)
    bottom = min(max(int((1.0 - min_y) * canvas_size), top + 1), canvas_size)
    return left, top, right, bottom


def _sprite_rgba(sprite: dict[str, Any]) -> tuple[int, int, int, int]:
    color = sprite.get("color") or {}
    return (
        int(float(color.get("r", 0.65)) * 255),
        int(float(color.get("g", 0.65)) * 255),
        int(float(color.get("b", 0.65)) * 255),
        int(float(color.get("a", 1.0)) * 255),
    )


def render_vfg_to_local_png_frames(
    vfg_bytes: bytes,
    output_dir: Path,
    start_step: int,
    stop_step: int,
    canvas_size: int = 1024,
) -> int:
    Image, ImageDraw, ImageOps = _import_pillow()

    payload = json.loads(vfg_bytes.decode("utf-8"))
    stages = payload.get("visualStages") or []
    if not stages:
        raise RuntimeError("VFG payload does not contain any visualStages")
    image_table = payload.get("imageTable") or {}
    prefab_keys = image_table.get("m_keys") or []
    prefab_values = image_table.get("m_values") or []

    prefab_images: dict[str, Any] = {}
    for key, encoded in zip(prefab_keys, prefab_values):
        decoded = base64.b64decode(encoded)
        prefab_images[key] = Image.open(BytesIO(decoded)).convert("RGBA")

    selected_stages = stages[start_step : min(stop_step + 1, len(stages))]
    output_dir.mkdir(parents=True, exist_ok=True)

    frame_count = 0
    for index, stage in enumerate(selected_stages):
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        sprites = stage.get("visualSprites") or []
        sprites = sorted(sprites, key=lambda item: item.get("depth", 0))

        for sprite in sprites:
            left, top, right, bottom = _sprite_bounds(sprite, canvas_size)
            width = max(right - left, 1)
            height = max(bottom - top, 1)
            rgba = _sprite_rgba(sprite)
            prefab_key = sprite.get("prefabImage") or sprite.get("prefabimage")
            prefab_image = prefab_images.get(prefab_key)

            if prefab_image is not None:
                resized = prefab_image.resize((width, height))
                alpha = resized.split()[-1]
                tinted = Image.new("RGBA", (width, height), rgba)
                tinted.putalpha(ImageOps.autocontrast(alpha))
                canvas.alpha_composite(tinted, (left, top))
            else:
                draw.rectangle([left, top, right, bottom], fill=rgba, outline=(0, 0, 0, 255))

            if sprite.get("showName") or sprite.get("showname") or sprite.get("showlabel"):
                label = sprite.get("label") or sprite.get("name") or ""
                if label:
                    draw.text((left + 4, top + 4), str(label), fill=(0, 0, 0, 255))

        frame_path = output_dir / f"frame_{index:03d}.png"
        canvas.save(frame_path)
        frame_count += 1

    if frame_count == 0:
        raise RuntimeError("Local VFG rendering produced zero PNG frames")

    return frame_count


def verify_output_dir(output_dir: Path) -> dict[str, Any]:
    instance_reports = list(output_dir.rglob("result.json"))
    png_files = list(output_dir.rglob("*.png"))
    vfg_files = list(output_dir.rglob("*.vfg.json"))
    other_visuals = [
        path
        for path in output_dir.rglob("*")
        if path.suffix.lower() in {".gif", ".mp4", ".webm"}
    ]
    return {
        "output_dir": str(output_dir),
        "result_files": len(instance_reports),
        "png_files": len(png_files),
        "vfg_files": len(vfg_files),
        "other_visual_files": len(other_visuals),
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
) -> dict[str, Any]:
    if stop_step <= start_step:
        raise ValueError("--stop-step must be greater than --start-step")

    entries = load_manifest(manifest_path)
    selected = select_entries(entries, domains=domains, max_per_domain=max_per_domain)
    if not selected:
        raise ValueError("No manifest entries selected for rendering")

    validation_errors = {
        f"{entry.domain_id}/{entry.problem_id}": validate_entry_assets(entry, manifest_path)
        for entry in selected
    }
    broken_entries = {key: value for key, value in validation_errors.items() if value}
    if broken_entries:
        raise ValueError(f"Local asset validation failed: {json.dumps(broken_entries, indent=2)}")

    pddl_candidates, vfg_candidates, root_url = derive_endpoint_candidates(base_url, pddl_url, vfg_url)
    preflight = preflight_host(root_url, timeout=timeout)
    output_dir.mkdir(parents=True, exist_ok=True)

    if preflight_only:
        summary = {
            "mode": "preflight",
            "manifest": str(manifest_path),
            "root_url": root_url,
            "preflight": preflight,
            "selected_entries": [asdict(entry) for entry in selected],
        }
        write_json(output_dir / "summary.json", summary)
        return summary

    results: list[dict[str, Any]] = []
    success_count = 0

    for index, entry in enumerate(selected):
        resolved = resolve_entry_paths(entry, manifest_path)
        instance_dir = output_dir / entry.domain_id / entry.problem_id
        instance_dir.mkdir(parents=True, exist_ok=True)
        started_at = time.time()
        result: dict[str, Any] = {
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
                domain_path=resolved["domain"],
                problem_path=resolved["problem"],
                animation_profile_path=resolved["animation_profile"],
                pddl_candidates=pddl_candidates,
                timeout=timeout,
            )
            result["used_pddl_url"] = used_pddl_url

            if output_format == "vfg":
                vfg_path = instance_dir / "trace.vfg.json"
                vfg_path.write_bytes(vfg_bytes)
                result["artifact_path"] = str(vfg_path)
            else:
                try:
                    render_bytes, used_vfg_url = post_vfg_for_visualisation(
                        vfg_bytes=vfg_bytes,
                        output_format=output_format,
                        vfg_candidates=vfg_candidates,
                        start_step=start_step,
                        stop_step=stop_step,
                        quality=quality,
                        timeout=timeout,
                    )
                    result["used_vfg_url"] = used_vfg_url

                    if output_format == "png":
                        frames_dir = instance_dir / "frames"
                        result["png_count"] = extract_png_archive(render_bytes, frames_dir)
                        result["artifact_path"] = str(frames_dir)
                    else:
                        visual_path = instance_dir / f"animation.{output_format}"
                        visual_path.write_bytes(render_bytes)
                        result["artifact_path"] = str(visual_path)
                except RuntimeError:
                    if output_format != "png":
                        raise
                    frames_dir = instance_dir / "frames"
                    result["png_count"] = render_vfg_to_local_png_frames(
                        vfg_bytes=vfg_bytes,
                        output_dir=frames_dir,
                        start_step=start_step,
                        stop_step=stop_step,
                    )
                    result["artifact_path"] = str(frames_dir)
                    result["used_local_renderer"] = True

            result["status"] = "success"
            success_count += 1
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)

        result["elapsed_seconds"] = round(time.time() - started_at, 3)
        write_json(instance_dir / "result.json", result)
        results.append(result)

        if index < len(selected) - 1 and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    summary = {
        "mode": "render",
        "manifest": str(manifest_path),
        "root_url": root_url,
        "preflight": preflight,
        "selected_count": len(selected),
        "success_count": success_count,
        "failure_count": len(selected) - success_count,
        "min_successes": min_successes,
        "selected_entries": [asdict(entry) for entry in selected],
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 1 Planimation asset sync and rendering utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync-assets", help="Download the curated Planimation PDDL/AP corpus.")
    sync_parser.add_argument("--manifest", type=Path, required=True)
    sync_parser.add_argument("--timeout", type=int, default=30)
    sync_parser.add_argument("--force", action="store_true")

    render_parser = subparsers.add_parser("render", help="Render curated Planimation PDDL/AP instances.")
    render_parser.add_argument("--manifest", type=Path, required=True)
    render_parser.add_argument("--output-dir", type=Path, required=True)
    render_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    render_parser.add_argument("--pddl-url")
    render_parser.add_argument("--vfg-url")
    render_parser.add_argument("--format", dest="output_format", choices=["png", "gif", "webm", "mp4", "vfg"], default="png")
    render_parser.add_argument("--start-step", type=int, default=0)
    render_parser.add_argument("--stop-step", type=int, default=3)
    render_parser.add_argument("--quality", type=int, default=1)
    render_parser.add_argument("--max-per-domain", type=int, default=None)
    render_parser.add_argument("--domains", nargs="*", default=None)
    render_parser.add_argument("--timeout", type=int, default=60)
    render_parser.add_argument("--sleep-seconds", type=float, default=1.0)
    render_parser.add_argument("--min-successes", type=int, default=1)
    render_parser.add_argument("--preflight-only", action="store_true")

    verify_parser = subparsers.add_parser("verify-output", help="Inspect a render output directory.")
    verify_parser.add_argument("--output-dir", type=Path, required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "sync-assets":
            summary = sync_assets(manifest_path=args.manifest, timeout=args.timeout, force=args.force)
        elif args.command == "render":
            selected_domains = set(args.domains) if args.domains else None
            summary = render_entries(
                manifest_path=args.manifest,
                output_dir=args.output_dir,
                base_url=args.base_url,
                pddl_url=args.pddl_url,
                vfg_url=args.vfg_url,
                output_format=args.output_format,
                start_step=args.start_step,
                stop_step=args.stop_step,
                quality=args.quality,
                max_per_domain=args.max_per_domain,
                domains=selected_domains,
                timeout=args.timeout,
                sleep_seconds=args.sleep_seconds,
                min_successes=args.min_successes,
                preflight_only=args.preflight_only,
            )
        else:
            summary = verify_output_dir(output_dir=args.output_dir)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
