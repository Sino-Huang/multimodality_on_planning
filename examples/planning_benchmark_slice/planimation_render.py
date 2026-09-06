"""Local, supplied-plan-only Planimation Render Production."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from scripts.planimation_phase1_client import post_pddl_for_vfg
from scripts.planimation_phase1_frames import render_vfg_to_local_png_frames

TRACE_FILENAME = "trace.vfg.json"
FRAMES_DIRNAME = "frames"
_ACTION = re.compile(r"\s*\(\s*[^()\s;]+(?:\s+[^()\s;]+)*\s*\)\s*")


class PlanimationRenderError(RuntimeError):
    """Raised when the supplied-plan Render Production contract is violated."""


@dataclass(frozen=True, slots=True)
class PlanimationRenderRequest:
    base_url: str
    domain_path: Path
    problem_path: Path
    animation_profile_path: Path
    supplied_plan: tuple[str, ...] | None
    output_dir: Path
    timeout_seconds: int
    solver_url: str | None = None


@dataclass(frozen=True, slots=True)
class PlanimationRenderResult:
    used_endpoint: str
    trace_path: Path
    frame_paths: tuple[Path, ...]


def produce_planimation_render(
    request: PlanimationRenderRequest,
) -> PlanimationRenderResult:
    """Create a VFG and PNG frames without permitting any planning fallback."""

    base_url = request.base_url.rstrip("/")
    _require_local_base_url(base_url)
    supplied_plan = "\n".join(canonical_supplied_actions(request.supplied_plan))
    if request.solver_url is not None:
        raise PlanimationRenderError("planning fallback is prohibited")

    upload_url = f"{base_url}/upload/pddl"
    try:
        vfg_bytes, used_endpoint = post_pddl_for_vfg(
            domain_path=request.domain_path,
            problem_path=request.problem_path,
            animation_profile_path=request.animation_profile_path,
            pddl_candidates=[upload_url],
            timeout=request.timeout_seconds,
            plan=supplied_plan,
            allow_redirects=False,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise PlanimationRenderError(f"Planimation Plan Submission failed: {error}") from error
    if used_endpoint != upload_url:
        raise PlanimationRenderError("Planimation used an endpoint outside the localhost production contract")

    trace_path = request.output_dir / TRACE_FILENAME
    frames_dir = request.output_dir / FRAMES_DIRNAME
    try:
        request.output_dir.mkdir(parents=True, exist_ok=True)
        trace_path.write_bytes(vfg_bytes)
        frame_count = render_vfg_to_local_png_frames(
            vfg_bytes=vfg_bytes,
            output_dir=frames_dir,
            start_step=0,
            stop_step=len(request.supplied_plan or ()),
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise PlanimationRenderError(f"Planimation Render Production failed: {error}") from error
    if frame_count <= 0:
        raise PlanimationRenderError("Planimation Render Production produced no PNG frames")
    frame_paths = tuple(frames_dir / f"frame_{index:03d}.png" for index in range(frame_count))
    return PlanimationRenderResult(used_endpoint, trace_path, frame_paths)


def _require_local_base_url(base_url: str) -> None:
    parsed = urlsplit(base_url)
    hostname = parsed.hostname
    is_loopback = hostname == "localhost"
    if hostname and not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = False
    if parsed.scheme != "http" or not is_loopback or parsed.query or parsed.fragment:
        raise PlanimationRenderError("Planimation endpoint must be localhost over HTTP")


def canonical_supplied_actions(actions: tuple[str, ...] | None) -> tuple[str, ...]:
    """Normalize one supplied Action Sequence for submission and semantic binding."""
    if not actions:
        raise PlanimationRenderError("supplied plan is required")
    canonical: list[str] = []
    for action in actions:
        if not isinstance(action, str) or _ACTION.fullmatch(action) is None:
            raise PlanimationRenderError("supplied plan actions must be parenthesized")
        canonical.append("(" + " ".join(action.strip()[1:-1].split()).lower() + ")")
    return tuple(canonical)
