"""Remote Planimation endpoint discovery, health checks, and requests."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Sequence, TypedDict
from urllib.parse import urlparse

import requests

DEFAULT_BASE_URL = "https://planimation.planning.domains"


class HostPreflightResult(TypedDict, total=False):
    """The serializable outcome of a Planimation host probe."""

    root_url: str
    reachable: bool
    status_code: int
    elapsed_seconds: float
    error: str


def derive_endpoint_candidates(
    base_url: str | None, pddl_url: str | None, vfg_url: str | None
) -> tuple[list[str], list[str], str]:
    """Derive the legacy upload and visualization endpoint fallback lists."""
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
        vfg_candidates = [f"{trimmed}/downloadVisualisation", f"{trimmed}/downloadVisualisation/"]
    root_source = base_url or pddl_candidates[0]
    parsed = urlparse(root_source)
    root_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else root_source
    return pddl_candidates, vfg_candidates, root_url


def preflight_host(root_url: str, timeout: int) -> HostPreflightResult:
    """Return reachability information without converting programming errors."""
    started_at = time.time()
    try:
        response = requests.get(root_url, timeout=timeout)
    except requests.RequestException as error:
        return {
            "root_url": root_url,
            "reachable": False,
            "error": str(error),
            "elapsed_seconds": round(time.time() - started_at, 3),
        }
    return {
        "root_url": root_url,
        "reachable": True,
        "status_code": response.status_code,
        "elapsed_seconds": round(time.time() - started_at, 3),
    }


def post_pddl_for_vfg(
    domain_path: Path,
    problem_path: Path,
    animation_profile_path: Path,
    pddl_candidates: Sequence[str],
    timeout: int,
) -> tuple[bytes, str]:
    """Submit one PDDL bundle through ordered upload endpoints."""
    files = {
        "domain": (None, domain_path.read_text(encoding="utf-8")),
        "problem": (None, problem_path.read_text(encoding="utf-8")),
        "animation": (None, animation_profile_path.read_text(encoding="utf-8")),
    }
    errors: list[str] = []
    for url in pddl_candidates:
        try:
            response = requests.post(url, files=files, timeout=timeout)
        except requests.RequestException as error:
            errors.append(f"{url} -> {error}")
            continue
        if response.status_code != 200:
            errors.append(f"{url} -> HTTP {response.status_code}: {response.text[:300]}")
            continue
        try:
            payload = response.json()
        except ValueError:
            return response.content, url
        if payload.get("status") == "error":
            errors.append(f"{url} -> API error: {payload.get('message', 'Unknown error')}")
            continue
        return json.dumps(payload).encode("utf-8"), url
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
    """Render VFG bytes through ordered visualization endpoints."""
    try:
        vfg_text = json.dumps(json.loads(vfg_bytes.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Returned VFG payload is not valid UTF-8 JSON") from error
    payload = {"vfg": vfg_text, "fileType": output_format}
    if output_format in {"gif", "mp4", "webm", "png"}:
        payload["params"] = {
            "fileType": output_format,
            "startStep": start_step,
            "stopStep": stop_step,
            "quality": quality,
        }
    errors: list[str] = []
    for url in vfg_candidates:
        request_attempts = (
            {"json": payload},
            {"data": json.dumps(payload), "headers": {"Content-Type": "application/json"}},
        )
        for attempt in request_attempts:
            try:
                response = requests.post(url, timeout=timeout, **attempt)
            except requests.RequestException as error:
                errors.append(f"{url} -> {error}")
                continue
            if response.status_code == 200:
                return response.content, url
            errors.append(f"{url} -> HTTP {response.status_code}: {response.text[:300]}")
    raise RuntimeError("Failed to render VFG payload. Attempts: " + " | ".join(errors))
