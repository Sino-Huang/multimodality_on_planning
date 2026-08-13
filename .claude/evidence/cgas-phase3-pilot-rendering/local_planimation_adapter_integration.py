#!/usr/bin/env python3
"""LOCAL-ONLY loopback integration harness for the CGAS Phase 3 Planimation adapter.

Drives the actual integrated production path

    render_missing_states -> render_state_with_planimation_compat
        -> render_state_with_planimation -> post_pddl_for_vfg

against the pinned local ``planimation/backend`` clone
(``.slim/clonedeps/repos/planimation__backend`` at commit
``94d82afb5ee122ce579dd11ca1953b7c85ca5824``) running under the existing isolated
venv, with a synthetic 4-object Blocksworld fixture and a real supplied action in
the compat ``b1..b4`` namespace. Loopback only: every HTTP POST issued by the
integrated client path is recorded in-process and must resolve to ``127.0.0.1``.

The supplied-plan path is selected by the presence of the multipart ``plan``
field; the harness records that observable on the outbound request and confirms
the backend parsed the supplied actions (its log prints them) rather than
contacting its hosted solver. It does not claim stronger network interception
than that.

Hard-stops on any failure. Never falls back to a hosted or solver URL. Never uses
the mapping-bound 8-object or representative 12-object fixtures. Writes a
machine-readable ``proof-report.json`` into the output root.

Usage (invocation shape; do not execute here):
  source ~/cd_vlaplan && python \
      .claude/evidence/cgas-phase3-pilot-rendering/local_planimation_adapter_integration.py \
      --output-root /absolute/new/output-root \
      [--backend-python <repo>/.slim/clonedeps/.venv-planimation-v0.1.7/bin/python] \
      [--port 8000]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# --------------------------------------------------------------------------- #
# Pinned inputs.                                                               #
# --------------------------------------------------------------------------- #

BACKEND_CLONE = ".slim/clonedeps/repos/planimation__backend"
BACKEND_PIN = "94d82afb5ee122ce579dd11ca1953b7c85ca5824"
ISOLATED_VENV_PYTHON = ".slim/clonedeps/.venv-planimation-v0.1.7/bin/python"
DOMAIN_REL = "modules/pddl-generators/blocksworld/4ops/domain.pddl"
PROFILE_REL = "data/pddl_instances/blocksworld/blocksworld_AP.pddl"

EXPECTED_DOMAIN_SHA256 = "2eed94c5a8fdfe2ac608c45cdf8a68274d69c1920bb4f831529f7bfaaaf79d81"
EXPECTED_PROFILE_SHA256 = "9ded071f7ae255de719d753a815bf56ed6756393e14a6065a331e7d5297a8d32"

# Synthetic 4-object Blocksworld fixture: candidate (object_count=4, raw_rank=0)
# from the production candidate space, pinned so module drift hard-stops instead
# of silently re-deriving a different fixture.
FIXTURE_OBJECT_COUNT = 4
FIXTURE_RAW_RANK = 0
FIXTURE_CANDIDATE_ID = "cdc2bc668b870ab316bb2b9fa0353e41a8350f7372f8277e8c680c6bc4869102"
FIXTURE_SOURCE_RECORD_SHA256 = "33ff55268caaf78958b488f9bcc14cf1a872236b709208ab0e348ab031afaf15"

# Supplied plan: one real action applicable to the compat-renamed b1..b4 problem
# (b1 is on-table, clear, and the arm is empty). Renaming b00..b03 -> b1..b4 is
# produced by the adapter's own planimation-compat formatter.
PLAN_ACTIONS = ["(pickup b1)"]
PLAN_TEXT = "\n".join(PLAN_ACTIONS)

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
SERVER_STARTUP_TIMEOUT_SECONDS = 180.0
SERVER_TERMINATE_GRACE_SECONDS = 10.0
UPLOAD_TIMEOUT_SECONDS = 120.0

SCHEMA_VERSION = "cgas_phase3_pilot_planimation_local_loopback_v1"


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


def _file_record(path: Path, display: str) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": display, "sha256": _sha256_bytes(data), "size": len(data)}


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _materialize_profile_text(profile_text: str) -> str:
    """Replace the Planimation ``RANDOMCOLOR`` sentinel with one fixed color.

    The pinned backend's ``Random_color`` extension turns the exact literal
    ``(color RANDOMCOLOR)`` into a process-global random choice, so consecutive
    requests carrying that sentinel differ byte-for-byte. Replacing only that
    exact sentinel with ``(color GREY)`` makes the submitted profile
    deterministic while the on-disk source profile and its verified hash stay
    untouched. ``str.replace`` matches exactly and is a no-op otherwise.
    """
    return profile_text.replace("(color RANDOMCOLOR)", "(color GREY)")


def _assert_loopback_url(url: str) -> None:
    """Refuse any server URL that is not an HTTP loopback URL."""
    parts = urlsplit(url)
    host = parts.hostname
    if parts.scheme != "http" or host is None or host.lower() not in LOOPBACK_HOSTS:
        raise ProofError("refusing_non_loopback_url", f"refusing non-loopback URL: {url}")


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    while True:
        if (current / "scripts" / "planimation_phase1_frames.py").is_file() and (
            current / BACKEND_CLONE / "server" / "manage.py"
        ).is_file():
            return current
        parent = current.parent
        if parent == current:
            raise ProofError("repo_root_not_found", f"could not resolve repo root from {start}")
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


# --------------------------------------------------------------------------- #
# Backend server lifecycle (loopback only, no .pyc into the clone).            #
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
# In-process outbound-request recorder (defensible loopback observable).       #
# --------------------------------------------------------------------------- #


def _install_post_recorder(repo_root: Path) -> dict[str, Any]:
    """Wrap ``requests.post`` used by the integrated client path.

    Every HTTP POST issued through ``scripts.planimation_phase1_client`` (the
    only outbound path in the integrated seam) is recorded, asserted loopback
    only, and inspected for the multipart ``plan`` field that selects the
    backend's supplied-plan path. Restore in ``finally``.
    """
    sys.path.insert(0, str(repo_root))
    import scripts.planimation_phase1_client as client_module

    real_post = client_module.requests.post
    state: dict[str, Any] = {"calls": []}

    def recording_post(url: str, *args: Any, **kwargs: Any) -> Any:
        _assert_loopback_url(str(url))
        state["calls"].append(
            {
                "url": str(url),
                "plan_present": isinstance(kwargs.get("files"), dict) and "plan" in kwargs["files"],
            }
        )
        return real_post(url, *args, **kwargs)

    client_module.requests.post = recording_post
    state["restore"] = lambda: setattr(client_module.requests, "post", real_post)
    return state


# --------------------------------------------------------------------------- #
# Synthetic 4-object fixture.                                                  #
# --------------------------------------------------------------------------- #


def _build_fixture(repo_root: Path, fixture_dir: Path) -> dict[str, Any]:
    sys.path.insert(0, str(repo_root))
    from scripts.phase3.cgas_candidate_accounting import PlannerInput, planner_input_record
    from scripts.phase3.cgas_candidate_space import build_candidate
    from scripts.phase3.cgas_pilot_expansion_index import state_sha256
    from scripts.phase3.io_utils import stable_hash

    candidate = build_candidate(FIXTURE_OBJECT_COUNT, FIXTURE_RAW_RANK)
    if candidate.candidate_id != FIXTURE_CANDIDATE_ID:
        raise ProofError(
            "fixture_candidate_drift",
            f"candidate_id {candidate.candidate_id} != pinned {FIXTURE_CANDIDATE_ID}",
        )
    source = planner_input_record(
        PlannerInput(
            FIXTURE_OBJECT_COUNT,
            FIXTURE_RAW_RANK,
            "emitted",
            candidate.candidate_id,
            FIXTURE_RAW_RANK,
            candidate,
        )
    )
    source_digest = hashlib.sha256(
        (json.dumps(source, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode()
    ).hexdigest()
    if source_digest != FIXTURE_SOURCE_RECORD_SHA256:
        raise ProofError(
            "fixture_source_record_drift",
            f"source_record_sha256 {source_digest} != pinned {FIXTURE_SOURCE_RECORD_SHA256}",
        )
    state_atoms = sorted(f"({' '.join(atom)})" for atom in candidate.init_atoms)
    digest = state_sha256(state_atoms)
    index_row: dict[str, object] = {
        "schema_version": "cgas_phase3_pilot_expansion_index_v1",
        "candidate_id": candidate.candidate_id,
        "instance_id": candidate.candidate_id,
        "object_count": FIXTURE_OBJECT_COUNT,
        "raw_rank": FIXTURE_RAW_RANK,
        "role": "train",
        "planner": "bfs",
        "row_id": "cgas-local-loopback-4obj-row-0",
        "event_sequence": 0,
        "event_sha256": hashlib.sha256(b"event-local-loopback").hexdigest(),
        "trace_path": "traces/local-loopback-4obj.jsonl",
        "trace_stream_sha256": hashlib.sha256(b"stream-local-loopback").hexdigest(),
        "trace_contract_id": "cgas_trace_contract_v3",
        "trace_contract_sha256": hashlib.sha256(b"contract-local-loopback").hexdigest(),
        "replay_plan_member": True,
        "replay_step_index": 0,
        "source_record_sha256": source_digest,
        "state_atoms": state_atoms,
        "state_sha256": digest,
        "supplied_plan": PLAN_TEXT,
    }
    request_row = {
        "partitions": ["train|4|bfs"],
        "state_atoms": state_atoms,
        "state_sha256": digest,
    }
    index_path = fixture_dir / "index.jsonl"
    request_path = fixture_dir / "request.jsonl"
    for path, rows in ((index_path, [index_row]), (request_path, [request_row])):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(
                json.dumps(row, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
                for row in rows
            ),
            encoding="utf-8",
        )
    return {
        "object_count": FIXTURE_OBJECT_COUNT,
        "raw_rank": FIXTURE_RAW_RANK,
        "candidate_id": candidate.candidate_id,
        "state_atoms": state_atoms,
        "state_sha256": digest,
        "source_record_sha256": source_digest,
        "supplied_plan_text": PLAN_TEXT,
        "supplied_plan_sha256": stable_hash(PLAN_TEXT),
        "plan_namespace": "b1..b4 (planimation-compat rename of b00..b03)",
        "plan_applicability": "(pickup b1): b1 is clear, on-table, and arm-empty in the 4-object initial state",
        "index_path": str(index_path),
        "request_path": str(request_path),
    }


# --------------------------------------------------------------------------- #
# Report emitters.                                                             #
# --------------------------------------------------------------------------- #


def _emit_hard_stop(output_root: Path, report: dict[str, Any], reason: str, **extra: Any) -> int:
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
        description="LOCAL-ONLY loopback integration harness for the CGAS Phase 3 Planimation adapter."
    )
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--backend-python", type=Path)
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args(argv)

    if not 1 <= args.port <= 65535:
        print(f"ERROR: --port must be in 1..65535 (got {args.port})", file=sys.stderr)
        return 2

    repo_root = _find_repo_root(Path(__file__).resolve().parent)
    output_root = args.output_root.expanduser().resolve()
    if output_root.exists():
        print(f"ERROR: --output-root must not exist: {output_root}", file=sys.stderr)
        return 2
    repository = repo_root.resolve()
    if output_root.is_symlink() or not any(
        output_root.is_relative_to(parent) for parent in (repository / "outputs", repository / "tmp")
    ):
        print(
            f"ERROR: --output-root must be under repo outputs/ or tmp/: {output_root}",
            file=sys.stderr,
        )
        return 2

    backend_python = args.backend_python if args.backend_python is not None else repo_root / ISOLATED_VENV_PYTHON
    backend_python = Path(os.path.abspath(backend_python.expanduser()))
    if not backend_python.is_file() or not os.access(backend_python, os.X_OK):
        print(
            f"ERROR: --backend-python is not an executable interpreter: {backend_python}",
            file=sys.stderr,
        )
        return 2

    clone = repo_root / BACKEND_CLONE
    server_dir = clone / "server"
    if not (server_dir / "manage.py").is_file():
        print(f"ERROR: no manage.py at {server_dir}", file=sys.stderr)
        return 2
    try:
        commit = _git_rev(clone)
        if commit != BACKEND_PIN:
            print(
                f"ERROR: backend HEAD is {commit}, expected pinned {BACKEND_PIN}",
                file=sys.stderr,
            )
            return 2
    except ProofError as exc:
        print(f"ERROR: {exc.detail}", file=sys.stderr)
        return 2

    domain_path = repo_root / DOMAIN_REL
    profile_path = repo_root / PROFILE_REL
    for path, label in ((domain_path, "domain"), (profile_path, "profile")):
        if not path.is_file():
            print(f"ERROR: missing {label} input: {path}", file=sys.stderr)
            return 2
    domain_rec = _file_record(domain_path, str(domain_path))
    profile_rec = _file_record(profile_path, str(profile_path))
    if domain_rec["sha256"] != EXPECTED_DOMAIN_SHA256:
        print(f"ERROR: domain sha mismatch: {domain_rec['sha256']}", file=sys.stderr)
        return 2
    if profile_rec["sha256"] != EXPECTED_PROFILE_SHA256:
        print(f"ERROR: profile sha mismatch: {profile_rec['sha256']}", file=sys.stderr)
        return 2

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "backend": {
            "clone_path": str(clone),
            "server_dir": str(server_dir),
            "commit": commit,
            "commit_pinned": commit == BACKEND_PIN,
            "backend_python": str(backend_python),
            "isolated_venv": backend_python.is_relative_to((repo_root / ".slim").resolve()),
            "startup_log": "backend.log",
            "started": False,
        },
        "inputs": {
            "domain": domain_rec,
            "profile_source": profile_rec,
            "profile_materialization": "RANDOMCOLOR sentinel -> GREY (in-memory/temp fixture only; source untouched)",
        },
        "fixture": None,
        "adapter": None,
        "render": None,
        "provenance": None,
        "network": None,
        "hosted_requests": 0,
    }

    proc: subprocess.Popen[bytes] | None = None
    log_handle: Any = None
    recorder: dict[str, Any] | None = None
    try:
        output_root.mkdir(parents=True, exist_ok=False)
        base_url = f"http://127.0.0.1:{args.port}"
        _assert_loopback_url(base_url)
        report["backend"]["endpoint"] = f"{base_url}/upload/pddl"

        # Deterministic project-owned profile fixture: hash-verified source,
        # materialized only for RANDOMCOLOR -> GREY, never edits clone/source.
        profile_dir = output_root / "deterministic-profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        materialized_profile = profile_dir / "blocksworld_AP.deterministic.pddl"
        _atomic_write_text(
            materialized_profile,
            _materialize_profile_text(profile_path.read_text(encoding="utf-8")),
        )
        report["inputs"]["profile_materialized"] = _file_record(materialized_profile, str(materialized_profile))

        fixture = _build_fixture(repo_root, output_root / "fixture")
        report["fixture"] = fixture

        proc, log_handle = _start_server(backend_python, server_dir, args.port, output_root / "backend.log")
        _wait_for_loopback(proc, args.port, output_root / "backend.log")
        report["backend"]["started"] = True
        print(f"backend listening on {base_url}")

        # Recorder must be installed before the integrated path runs.
        recorder = _install_post_recorder(repo_root)

        sys.path.insert(0, str(repo_root))
        from scripts.phase3.cgas_pilot_planimation_adapter import (
            PilotRenderRequest,
            render_missing_states,
        )
        from scripts.phase3.planimation_pairing_contracts import RenderConfig
        from scripts.phase3.render_semantics import validate_render_artifacts

        result = render_missing_states(
            PilotRenderRequest(
                repository_root=repo_root,
                request_path=Path(fixture["request_path"]),
                expansion_index_path=Path(fixture["index_path"]),
                output_root=output_root,
                domain_path=domain_path,
                profile_path=materialized_profile,
                config=RenderConfig(
                    base_url=base_url,
                    timeout_seconds=90,
                    request_delay_seconds=0,
                    max_attempts=1,
                ),
            )
        )

        expected_counts = {
            "requested": 1,
            "processed": 1,
            "succeeded": 1,
            "failed": 0,
            "duplicate": 0,
            "collision": 0,
            "remaining": 0,
        }
        if result.counts != expected_counts:
            raise ProofError(
                "adapter_counts_mismatch",
                f"expected {expected_counts}, got {result.counts}",
            )
        manifest_path = result.manifest_path
        report["adapter"] = {
            "manifest_path": str(manifest_path),
            "report_path": str(result.report_path),
            "counts": dict(result.counts),
            "run_contract_path": str(output_root / "diagnostics" / "run-contract.json"),
        }

        rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(rows) != 1:
            raise ProofError("manifest_row_count_mismatch", f"expected 1 row, got {len(rows)}")
        record = rows[0]
        if record.get("status") != "success":
            raise ProofError("render_not_success", f"manifest status: {record.get('status')}")
        if record.get("supplied_plan_sha256") != fixture["supplied_plan_sha256"]:
            raise ProofError(
                "supplied_plan_digest_mismatch",
                f"record {record.get('supplied_plan_sha256')} != fixture {fixture['supplied_plan_sha256']}",
            )

        frame_rel = str(record["frame_path"])
        trace_rel = str(record["trace_path"])
        frame_path = Path(frame_rel) if Path(frame_rel).is_absolute() else repo_root / frame_rel
        trace_path = Path(trace_rel) if Path(trace_rel).is_absolute() else repo_root / trace_rel
        if not frame_path.is_file() or not trace_path.is_file():
            raise ProofError("render_artifacts_missing", f"frame={frame_path} trace={trace_path}")
        if record.get("png_sha256") != _sha256_bytes(frame_path.read_bytes()):
            raise ProofError("render_png_hash_mismatch")
        if record.get("vfg_sha256") != _sha256_bytes(trace_path.read_bytes()):
            raise ProofError("render_vfg_hash_mismatch")
        vfg = json.loads(trace_path.read_text(encoding="utf-8"))
        if not isinstance(vfg, dict) or not isinstance(vfg.get("visualStages"), list):
            raise ProofError("render_vfg_invalid", "VFG has no visualStages list")
        receipt = validate_render_artifacts(trace_path, frame_path)
        if receipt.status != "success":
            raise ProofError(
                "render_semantic_invalid",
                f"semantic gate: {receipt.reason}",
            )
        report["render"] = {
            "status": "success",
            "frame_path": str(frame_path),
            "frame_sha256": record.get("png_sha256"),
            "png_dimensions": list(receipt.png_dimensions),
            "vfg_path": str(trace_path),
            "vfg_sha256": record.get("vfg_sha256"),
            "visualStages_count": len(vfg["visualStages"]),
            "semantic_receipt": receipt.to_record(),
            "supplied_plan_sha256": record.get("supplied_plan_sha256"),
            "renderer_config_sha256": record.get("renderer_config_sha256"),
            "cache_key": record.get("cache_key"),
        }

        run_contract_path = output_root / "diagnostics" / "run-contract.json"
        run_contract = json.loads(run_contract_path.read_text(encoding="utf-8"))
        report["provenance"] = {
            "run_contract_sha256": run_contract.get("run_contract_sha256"),
            "request_sha256": run_contract.get("request_sha256"),
            "expansion_index_sha256": run_contract.get("expansion_index_sha256"),
            "domain_sha256": run_contract.get("domain_sha256"),
            "profile_sha256": run_contract.get("profile_sha256"),
            "adapter_implementation_sha256": run_contract.get("adapter_implementation_sha256"),
            "rendering_implementation_sha256": run_contract.get("rendering_implementation_sha256"),
            "renderer_implementation_sha256": run_contract.get("renderer_implementation_sha256"),
            "planimation_client_implementation_sha256": run_contract.get("planimation_client_implementation_sha256"),
            "render_config": run_contract.get("render_config"),
            "binding_note": (
                "the shared run-contract render_config cannot hold a per-state plan; the supplied "
                "plan is bound transitively by the expansion-index SHA256 (the row carrying "
                "supplied_plan lives in that index) plus the per-record supplied_plan_sha256 and "
                "the plan-bearing cache identity"
            ),
        }

        calls = recorder["calls"]
        if len(calls) != 1:
            raise ProofError("unexpected_request_count", f"expected 1 POST, got {len(calls)}")
        call = calls[0]
        if not call["plan_present"]:
            raise ProofError(
                "supplied_plan_field_absent",
                "the recorded POST did not carry the multipart 'plan' field",
            )
        if call["url"] != f"{base_url}/upload/pddl":
            raise ProofError("unexpected_endpoint", f"POSTed {call['url']}")
        _assert_loopback_url(call["url"])

        log_text = (output_root / "backend.log").read_text(encoding="utf-8", errors="replace")
        plan_parse_evidence = PLAN_TEXT.lower() in log_text.lower()
        solver_url_absent = "solver.planning.domains" not in log_text
        report["network"] = {
            "recorded_post_urls": [call["url"]],
            "all_loopback": True,
            "hosted_requests": 0,
            "supplied_plan_selected_by_multipart_field": True,
            "plan_field_observed_on_request": call["plan_present"],
            "backend_log_plan_parse_evidence": plan_parse_evidence,
            "backend_log_solver_url_absent": solver_url_absent,
            "basis": (
                "every HTTP POST issued by the integrated client path was recorded in-process and "
                "asserted loopback-only; the supplied-plan path is selected by the multipart 'plan' "
                "field, whose presence was observed on the recorded request (the client adds it "
                "only when a plan is set); the backend log shows the supplied actions being parsed "
                "by get_plan_actions and contains no solver URL. hosted_requests=0 means zero "
                "requests to any non-loopback URL by this harness and by the integrated client "
                "path; no claim of network-level interception of the backend subprocess is made."
            ),
        }
        if not plan_parse_evidence or not solver_url_absent:
            raise ProofError(
                "backend_log_evidence_missing",
                f"plan_parse_evidence={plan_parse_evidence} solver_url_absent={solver_url_absent}",
            )

        return _emit_success(output_root, report)

    except ProofError as exc:
        report["exception"] = {"type": type(exc).__name__, "detail": exc.detail}
        return _emit_hard_stop(output_root, report, exc.reason, exception=report["exception"])
    except Exception as exc:
        report["exception"] = {"type": type(exc).__name__, "detail": str(exc)}
        return _emit_hard_stop(output_root, report, "harness_exception", exception=report["exception"])
    finally:
        if recorder is not None:
            recorder["restore"]()
        _terminate_server(proc, log_handle)


if __name__ == "__main__":
    raise SystemExit(main())
