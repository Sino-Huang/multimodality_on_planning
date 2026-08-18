"""Authorized localhost production runner for the frozen CGAS pilot render."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

# These legacy SHA identifiers are frozen Phase 3 wire compatibility only, not
# a generic design or binding mechanism.
from .cgas_pilot_planimation_adapter import (
    PRODUCTION_INDEX_COUNT,
    PRODUCTION_INDEX_SHA256,
    PRODUCTION_MAPPING_COUNT,
    PRODUCTION_MAPPING_SHA256,
    PRODUCTION_REQUEST_COUNT,
    PRODUCTION_REQUEST_SHA256,
    SCHEMA_VERSION as ADAPTER_SCHEMA_VERSION,
    PilotRenderRequest,
    render_missing_states,
)
from .cgas_pilot_lama_first_renderer import (
    FAST_DOWNWARD_REVISION,
    LAMA_FIRST_ALIAS,
    LamaFirstHardStop,
    LocalLamaFirstRenderer,
)
from .planimation_pairing_contracts import RenderConfig


SCHEMA_VERSION: Final = "cgas_phase3_pilot_planimation_production_v3"
AUTHORIZATION_SCHEMA_VERSION: Final = "cgas_phase3_pilot_planimation_production_authorization_v4"
ISSUE_NUMBER: Final = 8
BACKEND_RELATIVE_PATH: Final = Path(".slim/clonedeps/repos/planimation__backend")
BACKEND_COMMIT: Final = "94d82afb5ee122ce579dd11ca1953b7c85ca5824"
BACKEND_PYTHON_RELATIVE_PATH: Final = Path(".slim/clonedeps/.venv-planimation-v0.1.7/bin/python")
FAST_DOWNWARD_RELATIVE_PATH: Final = Path("modules/downward/fast-downward.py")
PLANNER_TIME_LIMIT_SECONDS: Final = 120
PLANNER_WATCHDOG_SECONDS: Final = 130.0
REQUEST_RELATIVE_PATH: Final = Path("tmp/cgas-phase3-pilot-expansion-index-v1/missing-render-request.jsonl")
INDEX_RELATIVE_PATH: Final = Path("tmp/cgas-phase3-pilot-expansion-index-v1/pilot-expansion-index.jsonl")
MAPPING_RELATIVE_PATH: Final = Path(
    "tmp/cgas-phase3-pilot-representative-mapping-v1/representative-source-mapping.jsonl"
)
DOMAIN_RELATIVE_PATH: Final = Path("modules/pddl-generators/blocksworld/4ops/domain.pddl")
PROFILE_RELATIVE_PATH: Final = Path("data/pddl_instances/blocksworld/blocksworld_AP.pddl")
PRODUCTION_REPORT_RELATIVE_PATH: Final = Path("reports/planimation-production-report.json")
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "localhost", "::1"})
SERVER_STARTUP_TIMEOUT_SECONDS: Final = 180.0
SERVER_TERMINATE_GRACE_SECONDS: Final = 10.0
RESUME_ROOT_NAMES: Final = frozenset({"backend.log", "candidate_problems", "diagnostics", "reports", "state_cache"})
RESUME_DIAGNOSTIC_NAMES: Final = frozenset({"render-checkpoint.jsonl", "run-contract.json", "state_render_manifest.jsonl"})
RESUME_REPORT_NAMES: Final = frozenset({"planimation-production-report.json", "render-report.json"})
ABORTED_ATTEMPT_ROOT_NAME: Final = "cgas-phase3-pilot-production-attempt-001"


@dataclass(frozen=True, slots=True)
class ProductionRenderError(RuntimeError):
    rule: str

    def __str__(self) -> str:
        return self.rule


@dataclass(frozen=True, slots=True)
class AuthorizationReceipt:
    path: Path
    output_root: Path
    port: int
    base_url: str

    @property
    def solver_url(self) -> str:
        return self.base_url + "/forbidden-solver"

    def report_record(self) -> dict[str, object]:
        return {
            "backend_commit": BACKEND_COMMIT,
            "base_url": self.base_url,
            "authorized": True,
            "fallback_allowed": False,
            "hosted_requests": 0,
            "index_count": PRODUCTION_INDEX_COUNT,
            "index_sha256": PRODUCTION_INDEX_SHA256,
            "issue": ISSUE_NUMBER,
            "mapping_count": PRODUCTION_MAPPING_COUNT,
            "mapping_sha256": PRODUCTION_MAPPING_SHA256,
            "output_root": str(self.output_root),
            "port": self.port,
            "fast_downward_revision": FAST_DOWNWARD_REVISION,
            "planner_alias": LAMA_FIRST_ALIAS,
            "planner_time_limit_seconds": PLANNER_TIME_LIMIT_SECONDS,
            "request_count": PRODUCTION_REQUEST_COUNT,
            "request_sha256": PRODUCTION_REQUEST_SHA256,
            "schema_version": AUTHORIZATION_SCHEMA_VERSION,
            "solver_url": self.solver_url,
        }


@dataclass(frozen=True, slots=True)
class ProductionRenderRequest:
    authorization_path: Path
    repository_root: Path
    output_root: Path
    port: int


@dataclass(frozen=True, slots=True)
class ProductionRenderResult:
    report_path: Path
    status: str
    counts: dict[str, int] | None


def _assert_loopback_url(url: str) -> None:
    parts = urlsplit(url)
    host = parts.hostname
    if parts.scheme != "http" or host is None or host.lower() not in LOOPBACK_HOSTS:
        raise ProductionRenderError("refusing_non_loopback_url")


def _assert_output_root(repository_root: Path, output_root: Path) -> tuple[Path, Path]:
    repository = repository_root.expanduser().resolve()
    if not repository.is_dir():
        raise ProductionRenderError("repository_root_invalid")
    raw_output = output_root.expanduser()
    resolved_output = raw_output.resolve()
    allowed_roots = (repository / "outputs", repository / "tmp")
    if raw_output.is_symlink() or not any(resolved_output.is_relative_to(parent) for parent in allowed_roots):
        raise ProductionRenderError("output_root_invalid")
    if resolved_output.exists() and not resolved_output.is_dir():
        raise ProductionRenderError("output_root_invalid")
    return repository, resolved_output


def _integer(value: object, rule: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProductionRenderError(rule)
    return value


def _text(value: object, rule: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProductionRenderError(rule)
    return value


def _load_authorization(path: Path, output_root: Path, port: int, base_url: str) -> AuthorizationReceipt:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProductionRenderError("authorization_receipt_unreadable") from error
    if not isinstance(value, dict):
        raise ProductionRenderError("authorization_receipt_invalid")
    expected: dict[str, object] = {
        "schema_version": AUTHORIZATION_SCHEMA_VERSION,
        "issue": ISSUE_NUMBER,
        "authorized": True,
        "backend_commit": BACKEND_COMMIT,
        "output_root": str(output_root),
        "port": port,
        "base_url": base_url,
        "request_sha256": PRODUCTION_REQUEST_SHA256,
        "request_count": PRODUCTION_REQUEST_COUNT,
        "index_sha256": PRODUCTION_INDEX_SHA256,
        "index_count": PRODUCTION_INDEX_COUNT,
        "mapping_sha256": PRODUCTION_MAPPING_SHA256,
        "mapping_count": PRODUCTION_MAPPING_COUNT,
        "hosted_requests": 0,
        "fallback_allowed": False,
        "fast_downward_revision": FAST_DOWNWARD_REVISION,
        "planner_alias": LAMA_FIRST_ALIAS,
        "planner_time_limit_seconds": PLANNER_TIME_LIMIT_SECONDS,
        "solver_url": base_url + "/forbidden-solver",
    }
    for key, required in expected.items():
        actual = value.get(key)
        if isinstance(required, bool):
            if actual is not required:
                raise ProductionRenderError("authorization_receipt_mismatch")
        elif isinstance(required, int):
            if _integer(actual, "authorization_receipt_mismatch") != required:
                raise ProductionRenderError("authorization_receipt_mismatch")
        elif _text(actual, "authorization_receipt_mismatch") != required:
            raise ProductionRenderError("authorization_receipt_mismatch")
    _assert_loopback_url(base_url)
    return AuthorizationReceipt(path.expanduser().resolve(), output_root, port, base_url)


def _report_path(output_root: Path) -> Path:
    reports = output_root / PRODUCTION_REPORT_RELATIVE_PATH.parent
    if reports.exists() and (reports.is_symlink() or not reports.is_dir()):
        raise ProductionRenderError("production_report_directory_invalid")
    reports.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not reports.resolve().is_relative_to(output_root):
        raise ProductionRenderError("production_report_directory_invalid")
    return reports / PRODUCTION_REPORT_RELATIVE_PATH.name


def _directory_entries(path: Path, rule: str) -> set[str]:
    try:
        return {entry.name for entry in path.iterdir()}
    except OSError as error:
        raise ProductionRenderError(rule) from error


def _require_directory(path: Path, rule: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ProductionRenderError(rule)


def _require_file(path: Path, rule: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ProductionRenderError(rule)


def _has_content(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                if chunk.strip():
                    return True
    except OSError as error:
        raise ProductionRenderError("resume_checkpoint_unreadable") from error
    return False


def _classify_output_root(output_root: Path) -> str:
    """Accept a new root or the exact adapter-owned production residue shape."""
    if not output_root.exists():
        return "fresh"
    entries = _directory_entries(output_root, "output_root_unreadable")
    if not entries:
        return "fresh"
    if entries != RESUME_ROOT_NAMES:
        raise ProductionRenderError("output_root_residue_invalid")
    _require_file(output_root / "backend.log", "output_root_residue_invalid")
    for name in ("candidate_problems", "state_cache", "diagnostics", "reports"):
        _require_directory(output_root / name, "output_root_residue_invalid")
    diagnostics = output_root / "diagnostics"
    diagnostic_entries = _directory_entries(diagnostics, "output_root_residue_invalid")
    required_diagnostics = {"run-contract.json", "render-checkpoint.jsonl"}
    if not required_diagnostics.issubset(diagnostic_entries) or not diagnostic_entries.issubset(RESUME_DIAGNOSTIC_NAMES):
        raise ProductionRenderError("output_root_residue_invalid")
    for name in diagnostic_entries:
        _require_file(diagnostics / name, "output_root_residue_invalid")
    if not _has_content(diagnostics / "render-checkpoint.jsonl"):
        raise ProductionRenderError("output_root_residue_invalid")
    reports = output_root / "reports"
    report_entries = _directory_entries(reports, "output_root_residue_invalid")
    if not report_entries.issubset(RESUME_REPORT_NAMES):
        raise ProductionRenderError("output_root_residue_invalid")
    for name in report_entries:
        _require_file(reports / name, "output_root_residue_invalid")
    # The adapter owns checkpoint, provenance, and artifact validation below this boundary.
    return "resume"


def _is_nonnegative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_zero(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def _counts_are_accounted(counts: object, status: object) -> bool:
    if not isinstance(counts, dict) or status not in {"complete", "complete_with_failures", "incomplete"}:
        return False
    required = ("requested", "succeeded", "failed", "remaining")
    if any(not _is_nonnegative_integer(counts.get(key)) for key in required):
        return False
    if counts["requested"] != counts["succeeded"] + counts["failed"] + counts["remaining"]:
        return False
    return status == "incomplete" or counts["remaining"] == 0


def _prior_report_is_structurally_valid(prior: dict[str, object]) -> bool:
    if prior.get("schema_version") != SCHEMA_VERSION or prior.get("status") not in {"complete", "complete_with_failures", "hard_stop"}:
        return False
    if prior.get("backend_commit") != BACKEND_COMMIT or not _is_zero(prior.get("hosted_requests")):
        return False
    backend = prior.get("backend")
    network = prior.get("network")
    if not isinstance(backend, dict) or not isinstance(network, dict):
        return False
    if not all(isinstance(backend.get(key), str) and backend[key] for key in ("clone_path", "server_log")):
        return False
    commit = backend.get("commit")
    returncode = backend.get("returncode")
    exited_cleanly = backend.get("exited_cleanly")
    if (commit is not None and commit != BACKEND_COMMIT) or not isinstance(backend.get("started"), bool):
        return False
    if exited_cleanly is not None and not isinstance(exited_cleanly, bool):
        return False
    if returncode is not None and (not isinstance(returncode, int) or isinstance(returncode, bool)):
        return False
    calls = network.get("recorded_post_urls")
    if (
        network.get("all_loopback") is not True
        or not _is_zero(network.get("hosted_requests"))
        or not _is_nonnegative_integer(network.get("call_count"))
        or not isinstance(network.get("limitation"), str)
        or not network["limitation"]
        or not isinstance(calls, list)
        or not all(isinstance(url, str) for url in calls)
        or network["call_count"] != len(calls)
    ):
        return False
    adapter = prior.get("adapter")
    if adapter is None:
        return prior["status"] == "hard_stop"
    if not isinstance(adapter, dict):
        return False
    if not all(isinstance(adapter.get(key), str) and adapter[key] for key in ("manifest_path", "report_path")):
        return False
    if not _counts_are_accounted(adapter.get("counts"), adapter.get("status")):
        return False
    return prior["status"] not in {"complete", "complete_with_failures"} or adapter["status"] == prior["status"]


def _assert_prior_authorization(report_path: Path, receipt: AuthorizationReceipt) -> None:
    if not report_path.exists():
        return
    if report_path.is_symlink() or not report_path.is_file():
        raise ProductionRenderError("production_report_invalid")
    try:
        prior = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProductionRenderError("production_report_invalid") from error
    if not isinstance(prior, dict):
        raise ProductionRenderError("production_report_invalid")
    if (
        prior.get("authorization_receipt_path") != str(receipt.path)
        or prior.get("authorization") != receipt.report_record()
    ):
        raise ProductionRenderError("authorization_receipt_mismatch")
    if not _prior_report_is_structurally_valid(prior):
        raise ProductionRenderError("production_report_invalid")


def _backend_commit(clone_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(clone_path), "rev-parse", "HEAD"], capture_output=True, check=False, text=True
    )
    if result.returncode != 0:
        raise ProductionRenderError("backend_git_unavailable")
    return result.stdout.strip()


def _fast_downward_revision(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path.parent), "rev-parse", "HEAD"], capture_output=True, check=False, text=True
    )
    if result.returncode != 0:
        raise ProductionRenderError("fast_downward_git_unavailable")
    return result.stdout.strip()


def _required_paths(repository_root: Path) -> dict[str, Path]:
    paths = {
        "backend_python": repository_root / BACKEND_PYTHON_RELATIVE_PATH,
        "fast_downward": repository_root / FAST_DOWNWARD_RELATIVE_PATH,
        "server_dir": repository_root / BACKEND_RELATIVE_PATH / "server",
        "request": repository_root / REQUEST_RELATIVE_PATH,
        "index": repository_root / INDEX_RELATIVE_PATH,
        "mapping": repository_root / MAPPING_RELATIVE_PATH,
        "domain": repository_root / DOMAIN_RELATIVE_PATH,
        "profile": repository_root / PROFILE_RELATIVE_PATH,
    }
    for label, path in paths.items():
        if label == "server_dir":
            if not (path / "manage.py").is_file():
                raise ProductionRenderError("backend_manage_py_unavailable")
        elif not path.is_file():
            raise ProductionRenderError(f"production_{label}_unavailable")
    if not os.access(paths["backend_python"], os.X_OK):
        raise ProductionRenderError("backend_python_unavailable")
    if not os.access(paths["fast_downward"], os.X_OK):
        raise ProductionRenderError("fast_downward_unavailable")
    return paths


def _start_server(backend_python: Path, server_dir: Path, port: int, log_path: Path) -> tuple[Any, Any]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    log_handle = log_path.open("ab", buffering=0)
    try:
        process = subprocess.Popen(
            [str(backend_python), "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
            cwd=str(server_dir),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
    except Exception:
        log_handle.close()
        raise
    return process, log_handle


def _wait_for_loopback(process: Any, port: int, log_path: Path) -> None:
    deadline = time.monotonic() + SERVER_STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            try:
                log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            except OSError:
                log_tail = ""
            raise ProductionRenderError(f"backend_server_exited_during_startup:{log_tail}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.5)
    raise ProductionRenderError("backend_server_startup_timeout")


def _terminate_server(process: Any | None, log_handle: Any | None) -> tuple[int | None, bool | None]:
    try:
        if process is None:
            return None, None
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=SERVER_TERMINATE_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=SERVER_TERMINATE_GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    pass
        returncode = process.poll()
        return returncode, returncode == 0
    finally:
        if log_handle is not None:
            log_handle.close()


def _plan_field(files: object) -> str | None:
    if not isinstance(files, dict):
        return None
    field = files.get("plan")
    return field[1] if isinstance(field, tuple) and len(field) >= 2 and isinstance(field[1], str) else None


def _url_field(files: object) -> str | None:
    if not isinstance(files, dict):
        return None
    field = files.get("url")
    return field[1] if isinstance(field, tuple) and len(field) >= 2 and isinstance(field[1], str) else None


def _is_parenthesized_plan(plan: str | None) -> bool:
    if not isinstance(plan, str) or not plan.strip():
        return False
    return all(line.strip().startswith("(") and line.strip().endswith(")") for line in plan.splitlines() if line.strip())


def _install_post_recorder(base_url: str) -> dict[str, Any]:
    """Record all posts from the project Planimation client and enforce loopback."""
    import scripts.planimation_phase1_client as client_module

    real_post = client_module.requests.post
    calls: list[str] = []
    expected_upload = base_url + "/upload/pddl"
    expected_solver = base_url + "/forbidden-solver"

    def recording_post(url: str, *args: Any, **kwargs: Any) -> Any:
        _assert_loopback_url(str(url))
        if (
            str(url) != expected_upload
            or not _is_parenthesized_plan(_plan_field(kwargs.get("files")))
            or _url_field(kwargs.get("files")) != expected_solver
        ):
            raise ProductionRenderError("production_post_contract_invalid")
        calls.append(str(url))
        return real_post(url, *args, **kwargs)

    client_module.requests.post = recording_post
    return {"calls": calls, "restore": lambda: setattr(client_module.requests, "post", real_post)}


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _adapter_summary(result: Any, resume_command: str) -> dict[str, object]:
    report_path = Path(result.report_path)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProductionRenderError("adapter_report_unavailable") from error
    if (
        not isinstance(report, dict)
        or report.get("schema_version") != ADAPTER_SCHEMA_VERSION
        or report.get("status") not in {"complete", "incomplete"}
    ):
        raise ProductionRenderError("adapter_report_invalid")
    if not isinstance(result.counts, dict) or not isinstance(report.get("counts"), dict):
        raise ProductionRenderError("adapter_report_invalid")
    counts = result.counts
    if report["counts"] != counts:
        raise ProductionRenderError("adapter_report_counts_mismatch")
    if not _counts_are_accounted(counts, report["status"]):
        raise ProductionRenderError("adapter_report_unaccounted")
    reported_resume = report.get("resume_command")
    if reported_resume is not None and reported_resume != resume_command:
        raise ProductionRenderError("adapter_report_resume_command_invalid")
    coverage_status = "complete" if counts["remaining"] == 0 else "incomplete"
    status = (
        "complete_with_failures"
        if coverage_status == "complete" and counts["failed"] > 0
        else "complete"
        if coverage_status == "complete"
        else "incomplete"
    )
    return {
        "counts": dict(counts),
        "coverage_status": coverage_status,
        "failure_breakdown": {"failed": counts["failed"], **_planning_accounting(Path(result.manifest_path))},
        "manifest_path": str(result.manifest_path),
        "planning": _planning_accounting(Path(result.manifest_path)),
        "report_path": str(report_path),
        "resume_command": resume_command,
        "status": status,
    }


def _planning_accounting(manifest_path: Path) -> dict[str, int]:
    try:
        rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError):
        return {"planning_failures": 0, "planimation_calls": 0, "submitted_plans": 0}
    planning_rows = [row for row in rows if isinstance(row, dict) and isinstance(row.get("planning_status"), str)]
    return {
        "planning_failures": sum(row["planning_status"] != "planning_submitted" for row in planning_rows),
        "planimation_calls": sum(
            value if isinstance(value := row.get("planimation_request_count"), int) and not isinstance(value, bool) else 0
            for row in planning_rows
        ),
        "submitted_plans": sum(row["planning_status"] == "planning_submitted" for row in planning_rows),
    }


def _network_record(recorder: dict[str, Any] | None) -> dict[str, object]:
    calls = [] if recorder is None else list(recorder["calls"])
    return {
        "all_loopback": True,
        "call_count": len(calls),
        "hosted_requests": 0,
        "limitation": "Only requests.post calls through scripts.planimation_phase1_client are intercepted; subprocess network traffic is not intercepted.",
        "recorded_post_urls": calls,
    }


def _production_resume_command(request: ProductionRenderRequest) -> str:
    return "source ~/cd_vlaplan && " + shlex.join(
        [
            "python",
            "-m",
            "scripts.phase3.cgas_pilot_planimation_production",
            "--authorization-path",
            str(request.authorization_path),
            "--repository-root",
            str(request.repository_root),
            "--output-root",
            str(request.output_root),
            "--port",
            str(request.port),
        ]
    )


def run(request: ProductionRenderRequest) -> ProductionRenderResult:
    if not 1 <= request.port <= 65535:
        raise ProductionRenderError("port_invalid")
    repository_root, output_root = _assert_output_root(request.repository_root, request.output_root)
    if output_root.name == ABORTED_ATTEMPT_ROOT_NAME:
        raise ProductionRenderError("attempt_001_aborted")
    base_url = f"http://127.0.0.1:{request.port}"
    receipt = _load_authorization(request.authorization_path, output_root, request.port, base_url)
    output_root_state = _classify_output_root(output_root)
    if output_root_state == "resume":
        existing_report = output_root / PRODUCTION_REPORT_RELATIVE_PATH
        _assert_prior_authorization(existing_report, receipt)
    output_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    report_path = _report_path(output_root)
    paths: dict[str, Path] | None = None
    process: Any | None = None
    log_handle: Any | None = None
    recorder: dict[str, Any] | None = None
    adapter: dict[str, object] | None = None
    status = "hard_stop"
    reason: str | None = None
    backend: dict[str, object] = {
        "clone_path": str(repository_root / BACKEND_RELATIVE_PATH),
        "commit": None,
        "exited_cleanly": None,
        "returncode": None,
        "server_log": str(output_root / "backend.log"),
        "started": False,
    }
    report: dict[str, object] = {
        "adapter": None,
        "authorization": receipt.report_record(),
        "authorization_receipt_path": str(receipt.path),
        "backend": backend,
        "backend_commit": BACKEND_COMMIT,
        "hosted_requests": 0,
        "network": None,
        "coverage_status": "incomplete",
        "failure_breakdown": None,
        "output_root_state": output_root_state,
        "planner": {
            "alias": LAMA_FIRST_ALIAS,
            "fast_downward_path": str(repository_root / FAST_DOWNWARD_RELATIVE_PATH),
            "revision": None,
            "time_limit_seconds": PLANNER_TIME_LIMIT_SECONDS,
            "watchdog_seconds": PLANNER_WATCHDOG_SECONDS,
            "solver_url": receipt.solver_url,
        },
        "schema_version": SCHEMA_VERSION,
        "status": status,
    }
    try:
        paths = _required_paths(repository_root)
        commit = _backend_commit(repository_root / BACKEND_RELATIVE_PATH)
        backend["commit"] = commit
        if commit != BACKEND_COMMIT:
            raise ProductionRenderError("backend_commit_mismatch")
        fast_downward_revision = _fast_downward_revision(paths["fast_downward"])
        planner = report["planner"]
        assert isinstance(planner, dict)
        planner["revision"] = fast_downward_revision
        if fast_downward_revision != FAST_DOWNWARD_REVISION:
            raise ProductionRenderError("fast_downward_revision_mismatch")
        process, log_handle = _start_server(paths["backend_python"], paths["server_dir"], request.port, output_root / "backend.log")
        _wait_for_loopback(process, request.port, output_root / "backend.log")
        backend["started"] = True
        recorder = _install_post_recorder(base_url)
        renderer = LocalLamaFirstRenderer(
            repository_root,
            paths["fast_downward"],
            fast_downward_revision,
            PLANNER_TIME_LIMIT_SECONDS,
            PLANNER_WATCHDOG_SECONDS,
            receipt.solver_url,
        )
        resume_command = _production_resume_command(request)
        result = render_missing_states(
            PilotRenderRequest(
                repository_root=repository_root,
                request_path=paths["request"],
                expansion_index_path=paths["index"],
                output_root=output_root,
                domain_path=paths["domain"],
                profile_path=paths["profile"],
                config=RenderConfig(base_url, 120, 0, 1, None, receipt.solver_url),
                representative_mapping_path=paths["mapping"],
                expected_request_sha256=PRODUCTION_REQUEST_SHA256,
                expected_request_count=PRODUCTION_REQUEST_COUNT,
                expected_index_sha256=PRODUCTION_INDEX_SHA256,
                expected_index_count=PRODUCTION_INDEX_COUNT,
                expected_mapping_sha256=PRODUCTION_MAPPING_SHA256,
                expected_mapping_count=PRODUCTION_MAPPING_COUNT,
                resume_command=resume_command,
            ),
            renderer=renderer,
        )
        adapter = _adapter_summary(result, resume_command)
        report["coverage_status"] = adapter["coverage_status"]
        report["failure_breakdown"] = adapter["failure_breakdown"]
        if adapter["status"] == "incomplete":
            reason = "adapter_report_incomplete"
        else:
            status = str(adapter["status"])
    except (ProductionRenderError, LamaFirstHardStop) as error:
        reason = error.rule
    except Exception as error:
        reason = f"production_runner_exception:{type(error).__name__}"
        report["exception"] = {"detail": str(error), "type": type(error).__name__}
    finally:
        if recorder is not None:
            recorder["restore"]()
        returncode, exited_cleanly = _terminate_server(process, log_handle)
        backend["returncode"] = returncode
        backend["exited_cleanly"] = exited_cleanly
        report["adapter"] = adapter
        report["network"] = _network_record(recorder)
        report["status"] = status
        if reason is not None:
            report["reason"] = reason
        _atomic_write_json(report_path, report)
    counts = adapter["counts"] if adapter is not None else None
    return ProductionRenderResult(report_path, status, counts if isinstance(counts, dict) else None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the authorized localhost CGAS Phase 3 Planimation production render.")
    parser.add_argument("--authorization-path", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    try:
        result = run(
            ProductionRenderRequest(
                authorization_path=parsed.authorization_path,
                repository_root=parsed.repository_root,
                output_root=parsed.output_root,
                port=parsed.port,
            )
        )
    except ProductionRenderError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"counts": result.counts, "report_path": str(result.report_path), "status": result.status},
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0 if result.status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
