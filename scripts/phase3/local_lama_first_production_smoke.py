"""Bounded retained integration smoke for the local LAMA-first production seam."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Sequence

from scripts.phase3.cgas_candidate_space import build_candidate
from scripts.phase3.cgas_pilot_lama_first_renderer import (
    FAST_DOWNWARD_REVISION,
    LAMA_FIRST_ALIAS,
    LamaFirstHardStop,
    LocalLamaFirstRenderer,
)

# Deliberately reuse the production lifecycle and recorder helpers so this retained
# certification path cannot drift from the security-sensitive runtime seam.
from scripts.phase3.cgas_pilot_planimation_production import (
    BACKEND_COMMIT,
    BACKEND_PYTHON_RELATIVE_PATH,
    BACKEND_RELATIVE_PATH,
    DOMAIN_RELATIVE_PATH,
    FAST_DOWNWARD_RELATIVE_PATH,
    PLANNER_TIME_LIMIT_SECONDS,
    PLANNER_WATCHDOG_SECONDS,
    PROFILE_RELATIVE_PATH,
    _assert_loopback_url,
    _backend_commit,
    _fast_downward_revision,
    _install_post_recorder,
    _start_server,
    _terminate_server,
    _wait_for_loopback,
)
from scripts.phase3.planimation_pairing_contracts import RenderConfig
from scripts.phase3.render_semantics import validate_render_artifacts

SCHEMA_VERSION: Final = "cgas_lama_first_production_smoke_v1"
AUTHORIZATION_SCHEMA_VERSION: Final = "cgas_lama_first_production_smoke_authorization_v1"
ISSUE_NUMBER: Final = 8
AUTHORIZED_OUTPUT_ROOT: Final = Path(
    "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning/outputs/image_frames/"
    "cgas-lama-first-production-smoke-20260817-attempt-001"
)
AUTHORIZED_PORT: Final = 18083
CASES: Final = (
    ("8-object-raw-rank-93", 8, 93, "0322c69e499f0e2ba7161d25787a1260a275bd22382438a7f48e51e9da3737c4"),
    ("12-object-raw-rank-9", 12, 9, "ca6fb5aa595c065744e0172f1b50d4e237bd4c851d094de684127a240cd3e85d"),
)


@dataclass(frozen=True, slots=True)
class SmokeError(RuntimeError):
    rule: str

    def __str__(self) -> str:
        return self.rule


@dataclass(frozen=True, slots=True)
class SmokeAuthorization:
    path: Path
    output_root: Path
    port: int
    base_url: str

    @property
    def solver_url(self) -> str:
        return self.base_url + "/forbidden-solver"

    def record(self) -> dict[str, object]:
        return {
            "authorized": True,
            "backend_commit": BACKEND_COMMIT,
            "base_url": self.base_url,
            "case_ids": [case[0] for case in CASES],
            "fallback_allowed": False,
            "fast_downward_revision": FAST_DOWNWARD_REVISION,
            "hosted_requests": 0,
            "issue": ISSUE_NUMBER,
            "output_root": str(self.output_root),
            "planner_alias": LAMA_FIRST_ALIAS,
            "planner_time_limit_seconds": PLANNER_TIME_LIMIT_SECONDS,
            "port": self.port,
            "schema_version": AUTHORIZATION_SCHEMA_VERSION,
            "solver_url": self.solver_url,
        }


@dataclass(frozen=True, slots=True)
class SmokeRequest:
    authorization_path: Path
    output_root: Path
    port: int


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_authorization(path: Path, output_root: Path, port: int) -> SmokeAuthorization:
    base_url = f"http://127.0.0.1:{port}"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SmokeError("authorization_receipt_unreadable") from error
    if not isinstance(value, dict):
        raise SmokeError("authorization_receipt_invalid")
    authorization = SmokeAuthorization(path.expanduser().resolve(), output_root, port, base_url)
    expected = authorization.record()
    for key, required in expected.items():
        actual = value.get(key)
        if isinstance(required, bool):
            valid = actual is required
        elif isinstance(required, int):
            valid = isinstance(actual, int) and not isinstance(actual, bool) and actual == required
        else:
            valid = actual == required
        if not valid:
            raise SmokeError("authorization_receipt_mismatch")
    _assert_loopback_url(base_url)
    return authorization


def _assert_fresh_output(root: Path) -> None:
    if root != AUTHORIZED_OUTPUT_ROOT.resolve():
        raise SmokeError("output_root_not_authorized")
    if root.exists():
        raise SmokeError("output_root_not_fresh")
    if root.is_symlink() or not root.is_relative_to(_repository_root().resolve() / "outputs"):
        raise SmokeError("output_root_invalid")


def _required_paths(repository: Path) -> dict[str, Path]:
    paths = {
        "backend_python": repository / BACKEND_PYTHON_RELATIVE_PATH,
        "fast_downward": repository / FAST_DOWNWARD_RELATIVE_PATH,
        "server_dir": repository / BACKEND_RELATIVE_PATH / "server",
        "domain": repository / DOMAIN_RELATIVE_PATH,
        "profile": repository / PROFILE_RELATIVE_PATH,
    }
    if not (paths["server_dir"] / "manage.py").is_file():
        raise SmokeError("backend_manage_py_unavailable")
    for name in ("backend_python", "fast_downward", "domain", "profile"):
        if not paths[name].is_file():
            raise SmokeError(f"{name}_unavailable")
    for name in ("backend_python", "fast_downward"):
        if not os.access(paths[name], os.X_OK):
            raise SmokeError(f"{name}_not_executable")
    return paths


def _candidate_cases() -> tuple[tuple[str, int, int, str, str], ...]:
    cases: list[tuple[str, int, int, str, str]] = []
    for case_id, object_count, raw_rank, candidate_id in CASES:
        candidate = build_candidate(object_count, raw_rank)
        if candidate.candidate_id != candidate_id:
            raise SmokeError("candidate_identity_mismatch")
        cases.append((case_id, object_count, raw_rank, candidate_id, candidate.problem))
    return tuple(cases)


def _atomic_write_json(path: Path, value: dict[str, object]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _artifact_path(repository: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise SmokeError("render_artifact_missing")
    path = Path(value)
    return path if path.is_absolute() else repository / path


def _case_record(
    repository: Path,
    case_id: str,
    object_count: int,
    raw_rank: int,
    candidate_id: str,
    result: dict[str, object],
) -> dict[str, object]:
    if result.get("status") != "success":
        raise SmokeError("case_render_not_success")
    metadata = result.get("planner_metadata")
    if not isinstance(metadata, dict):
        raise SmokeError("planner_metadata_missing")
    if (
        metadata.get("source") != "local_lama_first"
        or result.get("planning_status") != "planning_submitted"
        or metadata.get("planning_status") != "planning_submitted"
        or result.get("planimation_request_count") != 1
        or metadata.get("planimation_request_count") != 1
    ):
        raise SmokeError("planner_provenance_invalid")
    actions = metadata.get("actions")
    if not isinstance(actions, list) or not actions or not all(
        isinstance(action, str) and action.startswith("(") and action.endswith(")") for action in actions
    ):
        raise SmokeError("planner_actions_invalid")
    frame_path = _artifact_path(repository, result.get("frame_path"))
    trace_path = _artifact_path(repository, result.get("trace_path"))
    if not frame_path.is_file() or not trace_path.is_file():
        raise SmokeError("render_artifact_missing")
    if validate_render_artifacts(trace_path, frame_path).status != "success":
        raise SmokeError("render_semantics_invalid")
    return {
        "candidate_id": candidate_id,
        "case_id": case_id,
        "object_count": object_count,
        "raw_rank": raw_rank,
        "artifacts": {"frame_path": str(frame_path), "trace_path": str(trace_path)},
        "plan": list(actions),
        "planner_metadata": metadata,
        "planning_status": "planning_submitted",
        "planimation_request_count": 1,
    }


def run(request: SmokeRequest) -> int:
    repository = _repository_root().resolve()
    output_root = request.output_root.expanduser().resolve()
    if request.port != AUTHORIZED_PORT:
        raise SmokeError("port_not_authorized")
    _assert_fresh_output(output_root)
    authorization = _load_authorization(request.authorization_path, output_root, request.port)
    paths = _required_paths(repository)
    if _backend_commit(repository / BACKEND_RELATIVE_PATH) != BACKEND_COMMIT:
        raise SmokeError("backend_commit_mismatch")
    if _fast_downward_revision(paths["fast_downward"]) != FAST_DOWNWARD_REVISION:
        raise SmokeError("fast_downward_revision_mismatch")
    cases = _candidate_cases()
    output_root.mkdir(mode=0o700, parents=True)
    report_path = output_root / "proof-report.json"
    base_url = authorization.base_url
    report: dict[str, object] = {
        "authorization": authorization.record(),
        "authorization_receipt_path": str(authorization.path),
        "backend": {
            "commit": BACKEND_COMMIT,
            "exited_cleanly": None,
            "returncode": None,
            "server_log": str(output_root / "backend.log"),
            "started": False,
        },
        "cases": [],
        "certified": False,
        "fast_downward": {
            "alias": LAMA_FIRST_ALIAS,
            "path": str(paths["fast_downward"]),
            "revision": FAST_DOWNWARD_REVISION,
            "time_limit_seconds": PLANNER_TIME_LIMIT_SECONDS,
            "watchdog_seconds": PLANNER_WATCHDOG_SECONDS,
        },
        "network": None,
        "schema_version": SCHEMA_VERSION,
        "status": "hard_stop",
    }
    process: Any | None = None
    log_handle: Any | None = None
    recorder: dict[str, Any] | None = None
    reason: str | None = None
    try:
        process, log_handle = _start_server(
            paths["backend_python"], paths["server_dir"], request.port, output_root / "backend.log"
        )
        _wait_for_loopback(process, request.port, output_root / "backend.log")
        backend = report["backend"]
        assert isinstance(backend, dict)
        backend["started"] = True
        recorder = _install_post_recorder(base_url)
        renderer = LocalLamaFirstRenderer(
            repository,
            paths["fast_downward"],
            FAST_DOWNWARD_REVISION,
            PLANNER_TIME_LIMIT_SECONDS,
            PLANNER_WATCHDOG_SECONDS,
            authorization.solver_url,
        )
        config = RenderConfig(base_url, 120, 0, 1, None, authorization.solver_url)
        case_records: list[dict[str, object]] = []
        for case_id, object_count, raw_rank, candidate_id, problem in cases:
            problem_path = output_root / "candidate_problems" / f"{candidate_id}.pddl"
            problem_path.parent.mkdir(parents=True, exist_ok=True)
            problem_path.write_text(problem, encoding="utf-8")
            result = dict(
                renderer(paths["domain"], problem_path, paths["profile"], output_root / "cases" / case_id, config)
            )
            case_records.append(_case_record(repository, case_id, object_count, raw_rank, candidate_id, result))
        if recorder is None or len(recorder["calls"]) != len(CASES):
            raise SmokeError("planimation_post_count_invalid")
        report["cases"] = case_records
        report["network"] = {
            "all_loopback": True,
            "call_count": len(recorder["calls"]),
            "hosted_requests": 0,
            "limitation": (
                "Only project-client requests.post calls are intercepted; this proves loopback "
                "forbidden-solver containment, not OS-level network interception."
            ),
            "recorded_post_urls": list(recorder["calls"]),
        }
        report["status"] = "success"
        report["certified"] = True
    except (SmokeError, LamaFirstHardStop) as error:
        reason = str(error)
    except Exception as error:
        reason = f"smoke_exception:{type(error).__name__}"
        report["exception"] = {"detail": str(error), "type": type(error).__name__}
    finally:
        if recorder is not None:
            recorder["restore"]()
        returncode, exited_cleanly = _terminate_server(process, log_handle)
        backend = report["backend"]
        assert isinstance(backend, dict)
        backend["returncode"] = returncode
        backend["exited_cleanly"] = exited_cleanly
        if report["network"] is None:
            calls = [] if recorder is None else list(recorder["calls"])
            report["network"] = {
                "all_loopback": True,
                "call_count": len(calls),
                "hosted_requests": 0,
                "limitation": (
                    "Only project-client requests.post calls are intercepted; this proves loopback "
                    "forbidden-solver containment, not OS-level network interception."
                ),
                "recorded_post_urls": calls,
            }
        if reason is not None:
            report["reason"] = reason
        _atomic_write_json(report_path, report)
    return 0 if report["certified"] is True else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the authorized bounded local LAMA-first production smoke.")
    parser.add_argument("--authorization-path", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    try:
        return run(SmokeRequest(parsed.authorization_path, parsed.output_root, parsed.port))
    except SmokeError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
