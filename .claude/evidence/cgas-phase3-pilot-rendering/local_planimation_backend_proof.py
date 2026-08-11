#!/usr/bin/env python3
"""LOCAL-ONLY planimation backend proof harness (inert unless explicitly run).

Bounded, loopback-only verification harness for the pinned GPL-separated
planimation backend source clone at ``.slim/clonedeps/repos/planimation__backend``
(commit ``94d82afb5ee122ce579dd11ca1953b7c85ca5824``).

The harness NEVER edits the GPL clone and NEVER issues a request to any
non-loopback URL. It launches the clone's Django server under the provided
isolated interpreter and exercises exactly the flows below:

1. Replay-3 bundle (bundle-03-canonicalized-pilot-delta) is submitted TWICE with
   the exact supplied plan. Raw response bytes are persisted as
   ``replay3-run1.vfg.json`` / ``replay3-run2.vfg.json`` and must match byte for
   byte; otherwise a hard-stop report (``replay3_vfg_nondeterministic``) with a
   recursive JSON path delta (including color paths/values) is written and the
   harness exits nonzero immediately without rendering, empty-plan probing, or
   the 12-object submission.
2. On match, the local VFG is compared semantically / envelope / color against
   the hosted replay-3 trace (expected sha256 and size). Exact path deltas are
   recorded, but deterministic local byte divergence alone does not fail. Stage
   0 is rendered to one PNG and passed through the existing semantic gate
   (``scripts.phase3.render_semantics.validate_render_artifacts``).
3. An empty-plan probe sends ``plan=""`` plus multipart
   ``url=http://127.0.0.1:9/solve`` so any planner attempt is loopback-only; an
   error response is required (the default hosted solver URL must never be used).
4. A canonical 12-object problem (b1..b12, init facts preserved from
   bundle-04-12obj-empty-goal, non-empty goal ``(on b10 b9)``, supplied
   one-step plan ``(stack b10 b9)``) is submitted, stage 0 rendered and
   semantically validated.
5. On full success a deterministic ``proof-report.json`` (``indent=2,
   sort_keys=True``) records input/output SHA256, sizes, stage counts, semantic
   receipts, the empty-plan result, 12-object details, the backend pin and
   ``hosted_requests=0``; exit code 0.

Usage:
  python local_planimation_backend_proof.py \
      --backend-python /path/to/isolated/venv/bin/python \
      --output-root /absolute/new/output-root \
      [--port 8000]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

# --------------------------------------------------------------------------- #
# Pinned inputs (from the 2026-08-11 regression-replay staging bundle).        #
# --------------------------------------------------------------------------- #

BACKEND_CLONE = ".slim/clonedeps/repos/planimation__backend"
BACKEND_PIN = "94d82afb5ee122ce579dd11ca1953b7c85ca5824"
REPLAY3_BUNDLE = (
    "tmp/cgas-phase3-planimation-regression-replays-20260811/"
    "bundle-03-canonicalized-pilot-delta"
)
BUNDLE04_DIR = (
    "tmp/cgas-phase3-planimation-regression-replays-20260811/"
    "bundle-04-12obj-empty-goal"
)
HOSTED_VFG_REL = (
    "outputs/image_frames/cgas-phase3-planimation-regression-replay-03-20260811/"
    "trace.vfg.json"
)

REPLAY3_PLAN_ACTIONS = ["(unstack b5 b6)", "(stack b5 b4)", "(pickup b6)", "(stack b6 b5)"]
REPLAY3_PLAN_TEXT = "\n".join(REPLAY3_PLAN_ACTIONS)

TWELVE_OBJ_GOAL_ATOM = "(on b10 b9)"
TWELVE_OBJ_PLAN_ACTIONS = ["(stack b10 b9)"]
TWELVE_OBJ_PLAN_TEXT = "\n".join(TWELVE_OBJ_PLAN_ACTIONS)
TWELVE_OBJ_RENAMING = {f"b{i:02d}": f"b{i + 1}" for i in range(12)}

EXPECTED_DOMAIN_SHA256 = "2eed94c5a8fdfe2ac608c45cdf8a68274d69c1920bb4f831529f7bfaaaf79d81"
EXPECTED_PROBLEM_SHA256 = "8a27cbb59978e68e9a48a1770d7852d0ad91b33e5af98643dea578c210244549"
EXPECTED_PROFILE_SHA256 = "9ded071f7ae255de719d753a815bf56ed6756393e14a6065a331e7d5297a8d32"
EXPECTED_HOSTED_VFG_SHA256 = "337b988571ba3127c4d8a63fc99e2ea2fb77938d6e30bef95bf0199350dc1c64"
EXPECTED_HOSTED_VFG_SIZE = 20655

UPLOAD_TIMEOUT_SECONDS = 120.0
PROBE_TIMEOUT_SECONDS = 60.0
SERVER_STARTUP_TIMEOUT_SECONDS = 180.0
SERVER_TERMINATE_GRACE_SECONDS = 10.0
EMPTY_PLAN_PROBE_URL = "http://127.0.0.1:9/solve"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class ProofError(RuntimeError):
    """Harness failure carrying a stable, reportable ``reason``."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail or reason


# --------------------------------------------------------------------------- #
# Small deterministic helpers.                                                 #
# --------------------------------------------------------------------------- #


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _materialize_profile_text(profile_text: str) -> str:
    """Replace the Planimation ``RANDOMCOLOR`` sentinel with one fixed color.

    The pinned backend's ``Random_color`` extension turns the exact literal
    ``(color RANDOMCOLOR)`` into a process-global ``random.choice`` draw, so
    consecutive requests carrying that sentinel differ byte-for-byte and
    seeding once cannot cover the server process's draws. Replacing the exact
    sentinel with one valid concrete color (``(color GREY)``) here makes the
    submitted profile deterministic while the on-disk profile and its verified
    hash stay untouched. ``str.replace`` matches exactly, is a no-op for any
    other text, and is idempotent across repeated calls.
    """
    return profile_text.replace("(color RANDOMCOLOR)", "(color GREY)")


def _file_record(path: Path, display: str) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": display, "sha256": _sha256_bytes(data), "size": len(data)}


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def _assert_loopback_url(url: str) -> None:
    """Refuse any server URL that is not an HTTP loopback URL."""
    parts = urlsplit(url)
    host = parts.hostname
    if parts.scheme != "http" or host is None or host.lower() not in LOOPBACK_HOSTS:
        raise ProofError("refusing_non_loopback_url", f"refusing non-loopback URL: {url}")


def _find_repo_root(start: Path) -> Path:
    """Walk up from the script location until the repo root is found."""
    current = start.resolve()
    while True:
        if (current / "scripts" / "planimation_phase1_frames.py").is_file() and (
            current / BACKEND_CLONE / "server" / "manage.py"
        ).is_file():
            return current
        parent = current.parent
        if parent == current:
            raise ProofError(
                "repo_root_not_found",
                f"could not resolve repo root from {start}",
            )
        current = parent


def _git_rev(clone_dir: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ProofError("backend_git_unavailable", result.stderr.strip())
    return result.stdout.strip()


def _json_scalar(value: Any) -> Any:
    """Collapse containers to a compact string so deltas stay JSON-safe."""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if len(text) > 200:
            text = text[:200] + f"...(truncated,len={len(text)})"
        return text
    return value


def _json_diff_paths(left: Any, right: Any) -> list[dict[str, Any]]:
    """Recursive JSON path delta: concise list of differing paths + values."""
    deltas: list[dict[str, Any]] = []

    def walk(local: Any, other: Any, path: str) -> None:
        if type(local) is not type(other):
            deltas.append(
                {
                    "path": path or "$",
                    "left": _json_scalar(local),
                    "right": _json_scalar(other),
                }
            )
            return
        if isinstance(local, dict):
            for key in sorted(set(local) | set(other)):
                child = f"{path}.{key}" if path else key
                if key not in local:
                    deltas.append({"path": child, "left": None, "right": _json_scalar(other[key])})
                elif key not in other:
                    deltas.append({"path": child, "left": _json_scalar(local[key]), "right": None})
                else:
                    walk(local[key], other[key], child)
        elif isinstance(local, list):
            for index in range(max(len(local), len(other))):
                child = f"{path}[{index}]"
                if index >= len(local):
                    deltas.append({"path": child, "left": None, "right": _json_scalar(other[index])})
                elif index >= len(other):
                    deltas.append({"path": child, "left": _json_scalar(local[index]), "right": None})
                else:
                    walk(local[index], other[index], child)
        elif local != other:
            deltas.append(
                {"path": path or "$", "left": _json_scalar(local), "right": _json_scalar(other)}
            )

    walk(left, right, "")
    return deltas


def _parse_vfg(payload: bytes, label: str) -> dict[str, Any]:
    """Parse VFG bytes and require a nonempty ``visualStages`` list."""
    try:
        obj = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProofError("vfg_json_decode_failed", f"{label}: {exc}") from exc
    if not isinstance(obj, dict):
        raise ProofError("vfg_not_object", f"{label}: VFG payload is not a JSON object")
    stages = obj.get("visualStages")
    if not isinstance(stages, list) or not stages:
        raise ProofError("vfg_no_visual_stages", f"{label}: VFG payload has no nonempty visualStages")
    return obj


# --------------------------------------------------------------------------- #
# Backend server lifecycle (loopback only).                                    #
# --------------------------------------------------------------------------- #


def _start_server(
    backend_python: Path,
    server_dir: Path,
    port: int,
    log_path: Path,
) -> tuple[subprocess.Popen[bytes], Any]:
    env = dict(os.environ)
    # Keep the GPL clone pristine: never write .pyc into it.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    log_handle = open(log_path, "ab", buffering=0)
    proc = subprocess.Popen(
        [
            str(backend_python),
            "manage.py",
            "runserver",
            f"127.0.0.1:{port}",
            "--noreload",
        ],
        cwd=str(server_dir),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    return proc, log_handle


def _wait_for_loopback(
    proc: subprocess.Popen[bytes],
    port: int,
    log_path: Path,
    timeout: float = SERVER_STARTUP_TIMEOUT_SECONDS,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            tail = ""
            try:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            except OSError:
                pass
            raise ProofError(
                "backend_server_exited_during_startup",
                f"backend exited rc={proc.returncode}; log tail:\n{tail}",
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.5)
    raise ProofError(
        "backend_server_startup_timeout",
        f"backend did not listen on 127.0.0.1:{port} within {timeout:.0f}s",
    )


def _terminate_server(proc: subprocess.Popen[bytes] | None, log_handle: Any) -> None:
    if log_handle is not None:
        try:
            log_handle.close()
        except OSError:
            pass
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=SERVER_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=SERVER_TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass


# --------------------------------------------------------------------------- #
# HTTP interactions (strictly loopback).                                       #
# --------------------------------------------------------------------------- #


def _post_bundle(
    base_url: str,
    domain_text: str,
    problem_text: str,
    profile_text: str,
    plan_text: str,
    extra_data: dict[str, str] | None = None,
    timeout: float = UPLOAD_TIMEOUT_SECONDS,
    fail_reason: str = "upload_failed",
) -> bytes:
    url = f"{base_url}/upload/pddl"
    _assert_loopback_url(url)
    files = {
        "domain": (None, domain_text),
        "problem": (None, problem_text),
        "animation": (None, profile_text),
        "plan": (None, plan_text),
    }
    response = requests.post(url, files=files, data=extra_data or {}, timeout=timeout)
    if response.status_code != 200:
        raise ProofError(
            fail_reason,
            f"POST {url} returned HTTP {response.status_code}: {response.text[:500]}",
        )
    return response.content


# --------------------------------------------------------------------------- #
# Render + existing semantic gate.                                             #
# --------------------------------------------------------------------------- #


def _render_stage_zero_and_validate(
    repo_root: Path,
    vfg_bytes: bytes,
    trace_path: Path,
    frames_dir: Path,
    label: str,
) -> dict[str, Any]:
    sys.path.insert(0, str(repo_root))
    from scripts.phase3.render_semantics import validate_render_artifacts
    from scripts.planimation_phase1_frames import render_vfg_to_local_png_frames

    frame_count = render_vfg_to_local_png_frames(vfg_bytes, frames_dir, 0, 0)
    frame_path = frames_dir / "frame_000.png"
    if frame_count != 1 or not frame_path.is_file():
        raise ProofError("stage_zero_render_failed", f"{label}: expected exactly one stage-0 PNG")
    receipt = validate_render_artifacts(trace_path, frame_path)
    return {
        "stage_range": [0, 0],
        "frame_count": frame_count,
        "frame_path": str(frame_path.relative_to(frames_dir.parent)),
        "frame_sha256": _sha256_bytes(frame_path.read_bytes()),
        "semantic_status": receipt.status,
        "semantic_reason": receipt.reason,
        "semantic_receipt": receipt.to_record(),
    }


# --------------------------------------------------------------------------- #
# 12-object canonical problem builder (b00..b11 -> b1..b12).                   #
# --------------------------------------------------------------------------- #


def _build_twelve_object_problem(source_text: str) -> str:
    renamed = re.sub(
        r"\bb(\d\d)\b",
        lambda match: f"b{int(match.group(1)) + 1}",
        source_text,
    )
    renamed, name_count = re.subn(
        r"\(problem [^)]*\)",
        "(problem cgas-phase3-local-proof-04-12obj-nonempty-goal)",
        renamed,
        count=1,
    )
    if name_count != 1:
        raise ProofError("twelve_object_problem_build_failed", "could not rename problem")
    renamed, goal_count = re.subn(
        r"\(:goal\s*\(and\)\)",
        f"(:goal (and\n{TWELVE_OBJ_GOAL_ATOM})\n)",
        renamed,
        count=1,
    )
    if goal_count != 1:
        raise ProofError("twelve_object_problem_build_failed", "could not replace empty goal")
    if "(holding b10)" not in renamed or "(clear b9)" not in renamed:
        raise ProofError(
            "twelve_object_problem_build_failed",
            "mapped init lacks (holding b10) and/or (clear b9)",
        )
    return renamed


# --------------------------------------------------------------------------- #
# Report emitters.                                                             #
# --------------------------------------------------------------------------- #


def _emit_hard_stop(
    output_root: Path,
    report: dict[str, Any],
    reason: str,
    **extra: Any,
) -> int:
    report["status"] = "hard_stop"
    report["reason"] = reason
    report["hosted_requests"] = 0
    report.update(extra)
    _write_json(output_root / "proof-report.json", report)
    print(f"HARD STOP: {reason}", file=sys.stderr)
    return 1


def _emit_success(output_root: Path, report: dict[str, Any]) -> int:
    report["status"] = "success"
    report["hosted_requests"] = 0
    _write_json(output_root / "proof-report.json", report)
    print("SUCCESS: proof-report.json written")
    return 0


# --------------------------------------------------------------------------- #
# Main flow.                                                                   #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LOCAL-ONLY planimation backend proof harness (loopback only)."
    )
    parser.add_argument("--backend-python", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args(argv)

    if not 1 <= args.port <= 65535:
        print(f"ERROR: --port must be in 1..65535 (got {args.port})", file=sys.stderr)
        return 2
    output_root = args.output_root.expanduser().resolve()
    if output_root.exists():
        print(f"ERROR: --output-root must not exist: {output_root}", file=sys.stderr)
        return 2
    backend_python = Path(os.path.abspath(args.backend_python.expanduser()))
    if not backend_python.is_file() or not os.access(backend_python, os.X_OK):
        print(
            f"ERROR: --backend-python is not an executable interpreter: {backend_python}",
            file=sys.stderr,
        )
        return 2

    try:
        repo_root = _find_repo_root(Path(__file__).resolve().parent)
        clone = repo_root / BACKEND_CLONE
        server_dir = clone / "server"
        if not (server_dir / "manage.py").is_file():
            raise ProofError("backend_server_missing", f"no manage.py at {server_dir}")
        commit = _git_rev(clone)
        if commit != BACKEND_PIN:
            raise ProofError(
                "backend_pin_mismatch",
                f"backend HEAD is {commit}, expected pinned {BACKEND_PIN}",
            )

        replay3_dir = repo_root / REPLAY3_BUNDLE
        domain_path = replay3_dir / "domain.pddl"
        problem_path = replay3_dir / "problem.pddl"
        profile_path = replay3_dir / "blocksworld_AP.pddl"
        domain_rec = _file_record(domain_path, str(domain_path))
        problem_rec = _file_record(problem_path, str(problem_path))
        profile_rec = _file_record(profile_path, str(profile_path))
        if domain_rec["sha256"] != EXPECTED_DOMAIN_SHA256:
            raise ProofError("input_domain_sha_mismatch", f"got {domain_rec['sha256']}")
        if problem_rec["sha256"] != EXPECTED_PROBLEM_SHA256:
            raise ProofError("input_problem_sha_mismatch", f"got {problem_rec['sha256']}")
        if profile_rec["sha256"] != EXPECTED_PROFILE_SHA256:
            raise ProofError("input_profile_sha_mismatch", f"got {profile_rec['sha256']}")

        hosted_path = repo_root / HOSTED_VFG_REL
        if not hosted_path.is_file():
            raise ProofError("hosted_vfg_missing", f"missing hosted trace: {hosted_path}")
        hosted_bytes = hosted_path.read_bytes()
        hosted_rec = _file_record(hosted_path, str(hosted_path))
        if hosted_rec["sha256"] != EXPECTED_HOSTED_VFG_SHA256 or hosted_rec["size"] != EXPECTED_HOSTED_VFG_SIZE:
            raise ProofError(
                "hosted_vfg_pin_mismatch",
                f"hosted trace sha/size {hosted_rec['sha256']}/{hosted_rec['size']}"
                f" != expected {EXPECTED_HOSTED_VFG_SHA256}/{EXPECTED_HOSTED_VFG_SIZE}",
            )

        bundle04 = repo_root / BUNDLE04_DIR
        for name in ("domain.pddl", "problem.pddl", "blocksworld_AP.pddl"):
            if not (bundle04 / name).is_file():
                raise ProofError("bundle04_input_missing", f"missing {bundle04 / name}")
    except ProofError as exc:
        print(f"ERROR: {exc.detail}", file=sys.stderr)
        return 2

    report: dict[str, Any] = {
        "backend": {
            "clone_path": str(clone),
            "server_dir": str(server_dir),
            "commit": commit,
            "backend_python": str(backend_python),
            "startup_log": "backend.log",
            "started": False,
        },
        "inputs": {
            "replay3": {
                "domain": domain_rec,
                "problem": problem_rec,
                "profile": profile_rec,
                "plan_text": REPLAY3_PLAN_TEXT,
                "plan_actions": REPLAY3_PLAN_ACTIONS,
            },
            "hosted_trace": hosted_rec,
            "twelve_object_source": {
                "domain": _file_record(bundle04 / "domain.pddl", str(bundle04 / "domain.pddl")),
                "problem": _file_record(bundle04 / "problem.pddl", str(bundle04 / "problem.pddl")),
                "profile": _file_record(bundle04 / "blocksworld_AP.pddl", str(bundle04 / "blocksworld_AP.pddl")),
                "renaming": TWELVE_OBJ_RENAMING,
                "goal_atom": TWELVE_OBJ_GOAL_ATOM,
            },
        },
        "replay3": None,
        "empty_plan_probe": None,
        "twelve_object": None,
        "hosted_requests": 0,
    }

    proc: subprocess.Popen[bytes] | None = None
    log_handle: Any = None
    try:
        output_root.mkdir(parents=True, exist_ok=False)
        base_url = f"http://127.0.0.1:{args.port}"
        _assert_loopback_url(base_url)

        proc, log_handle = _start_server(
            backend_python, server_dir, args.port, output_root / "backend.log"
        )
        _wait_for_loopback(proc, args.port, output_root / "backend.log")
        report["backend"]["started"] = True
        print(f"backend listening on {base_url}")

        # --- Replay-3, exactly twice --------------------------------------- #
        domain_text = domain_path.read_text(encoding="utf-8")
        problem_text = problem_path.read_text(encoding="utf-8")
        # Hash-verified above; materialize once so run1/run2, the empty-plan
        # probe, and the 12-object submission all send the same deterministic text.
        profile_text = _materialize_profile_text(
            profile_path.read_text(encoding="utf-8")
        )

        run1_path = output_root / "replay3-run1.vfg.json"
        run2_path = output_root / "replay3-run2.vfg.json"
        run1_bytes = _post_bundle(
            base_url, domain_text, problem_text, profile_text,
            REPLAY3_PLAN_TEXT, fail_reason="replay3_submission_failed",
        )
        _atomic_write_bytes(run1_path, run1_bytes)
        run2_bytes = _post_bundle(
            base_url, domain_text, problem_text, profile_text,
            REPLAY3_PLAN_TEXT, fail_reason="replay3_submission_failed",
        )
        _atomic_write_bytes(run2_path, run2_bytes)

        run1_obj = _parse_vfg(run1_bytes, "replay3-run1")
        run2_obj = _parse_vfg(run2_bytes, "replay3-run2")
        stage_count = len(run1_obj["visualStages"])

        replay3_section: dict[str, Any] = {
            "run1": {"path": run1_path.name, "sha256": _sha256_bytes(run1_bytes), "size": len(run1_bytes)},
            "run2": {"path": run2_path.name, "sha256": _sha256_bytes(run2_bytes), "size": len(run2_bytes)},
            "raw_bytes_equal": run1_bytes == run2_bytes,
            "visualStages_count": stage_count,
        }
        report["replay3"] = replay3_section

        if run1_bytes != run2_bytes:
            return _emit_hard_stop(
                output_root,
                report,
                "replay3_vfg_nondeterministic",
                replay3={
                    "run1": replay3_section["run1"],
                    "run2": replay3_section["run2"],
                    "path_deltas": _json_diff_paths(run1_obj, run2_obj),
                    "delta_meaning": {"left": "run1", "right": "run2"},
                },
            )

        # --- Compare local vs hosted replay-3 trace ------------------------ #
        local_sha = replay3_section["run1"]["sha256"]
        local_size = replay3_section["run1"]["size"]
        hosted_obj = _parse_vfg(hosted_bytes, "hosted-replay3")
        hosted_comparison = {
            "hosted_sha256": hosted_rec["sha256"],
            "hosted_size": hosted_rec["size"],
            "local_sha256": local_sha,
            "local_size": local_size,
            "sha256_equal": local_sha == hosted_rec["sha256"],
            "size_equal": local_size == hosted_rec["size"],
            "raw_bytes_equal": run1_bytes == hosted_bytes,
            "hosted_visualStages_count": len(hosted_obj["visualStages"]),
            "path_deltas": _json_diff_paths(run1_obj, hosted_obj),
            "delta_meaning": {"left": "local", "right": "hosted"},
        }
        replay3_section["hosted_comparison"] = hosted_comparison
        print(
            f"replay3 deterministic; local sha {local_sha[:16]}... "
            f"sha_equal={hosted_comparison['sha256_equal']} "
            f"size_equal={hosted_comparison['size_equal']} "
            f"path_deltas={len(hosted_comparison['path_deltas'])}"
        )

        # --- Render stage 0 + semantic gate -------------------------------- #
        replay3_section["render"] = _render_stage_zero_and_validate(
            repo_root,
            run1_bytes,
            run1_path,
            output_root / "replay3-frames",
            "replay3",
        )
        if replay3_section["render"]["semantic_status"] != "success":
            return _emit_hard_stop(
                output_root, report, "replay3_semantic_validation_failed",
                replay3=replay3_section,
            )

        # --- Empty-plan probe (loopback-only planner URL) ------------------ #
        probe_bytes = _post_bundle(
            base_url, domain_text, problem_text, profile_text,
            plan_text="",
            extra_data={"url": EMPTY_PLAN_PROBE_URL},
            timeout=PROBE_TIMEOUT_SECONDS,
            fail_reason="empty_plan_probe_failed",
        )
        probe_path = output_root / "empty-plan-probe.json"
        _atomic_write_bytes(probe_path, probe_bytes)
        probe_obj: dict[str, Any] = {}
        try:
            parsed = json.loads(probe_bytes.decode("utf-8"))
            if isinstance(parsed, dict):
                probe_obj = parsed
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        status_field = probe_obj.get("status") if isinstance(probe_obj, dict) else None
        message = probe_obj.get("message") if isinstance(probe_obj, dict) else None
        probe_record = {
            "plan_text": "",
            "solver_url": EMPTY_PLAN_PROBE_URL,
            "response_path": probe_path.name,
            "response_sha256": _sha256_bytes(probe_bytes),
            "response_size": len(probe_bytes),
            "rejected": status_field == "error",
            "status_field": status_field,
            "message": message,
            "planner_routed": bool(
                status_field == "error" and isinstance(message, str)
                and "exception" in message.lower()
            ),
        }
        report["empty_plan_probe"] = probe_record
        if probe_record["rejected"] is not True:
            return _emit_hard_stop(
                output_root, report, "empty_plan_not_rejected",
                empty_plan_probe=probe_record,
            )
        print("empty-plan probe: error response confirmed (loopback planner route)")

        # --- Canonical 12-object non-empty-goal bundle --------------------- #
        twelve_source = (bundle04 / "problem.pddl").read_text(encoding="utf-8")
        twelve_problem = _build_twelve_object_problem(twelve_source)
        twelve_problem_path = output_root / "12obj-problem.pddl"
        _atomic_write_text(twelve_problem_path, twelve_problem)
        twelve_plan_path = output_root / "12obj-plan.txt"
        _atomic_write_text(twelve_plan_path, TWELVE_OBJ_PLAN_TEXT)

        twelve_bytes = _post_bundle(
            base_url,
            domain_text,
            twelve_problem,
            profile_text,
            TWELVE_OBJ_PLAN_TEXT,
            fail_reason="twelve_object_submission_failed",
        )
        twelve_trace_path = output_root / "12obj-trace.vfg.json"
        _atomic_write_bytes(twelve_trace_path, twelve_bytes)
        twelve_obj = _parse_vfg(twelve_bytes, "12obj-trace")
        twelve_render = _render_stage_zero_and_validate(
            repo_root,
            twelve_bytes,
            twelve_trace_path,
            output_root / "12obj-frames",
            "12obj",
        )
        if twelve_render["semantic_status"] != "success":
            return _emit_hard_stop(
                output_root, report, "twelve_object_semantic_validation_failed",
                twelve_object={
                    "problem": _file_record(twelve_problem_path, twelve_problem_path.name),
                    "plan_path": twelve_plan_path.name,
                    "plan_text": TWELVE_OBJ_PLAN_TEXT,
                    "trace": _file_record(twelve_trace_path, twelve_trace_path.name),
                    "visualStages_count": len(twelve_obj["visualStages"]),
                    "render": twelve_render,
                },
            )
        report["twelve_object"] = {
            "problem": _file_record(twelve_problem_path, twelve_problem_path.name),
            "plan_path": twelve_plan_path.name,
            "plan_text": TWELVE_OBJ_PLAN_TEXT,
            "trace": _file_record(twelve_trace_path, twelve_trace_path.name),
            "visualStages_count": len(twelve_obj["visualStages"]),
            "render": twelve_render,
        }
        print(f"12-object bundle ok: {report['twelve_object']['visualStages_count']} visualStages")

        return _emit_success(output_root, report)

    except ProofError as exc:
        report["exception"] = {"type": type(exc).__name__, "detail": exc.detail}
        return _emit_hard_stop(output_root, report, exc.reason, exception=report["exception"])
    except Exception as exc:  # noqa: BLE001 - capture exact unexpected failures.
        detail = f"{type(exc).__name__}: {exc}"
        report["exception"] = {"type": type(exc).__name__, "detail": str(exc)}
        return _emit_hard_stop(output_root, report, "harness_exception", exception=report["exception"])
    finally:
        _terminate_server(proc, log_handle)


if __name__ == "__main__":
    raise SystemExit(main())
