from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
from collections import Counter
from pathlib import Path
from time import sleep
from typing import Any, Callable

from .attempt_runner import run_planner_jobs
from .gbfs import gbfs_estimate_exceeds_resource_gate, gbfs_trace, run_gbfs
from .io_utils import clear_output_root, count_jsonl, ensure_layout, file_sha256, read_jsonl, relpath, repo_root, stable_hash, write_json, write_jsonl
from .local_goal_regression import GoalRegressionRequest, recover_goal_regression_plan, should_try_goal_regression_first
from .local_planners import LocalPlannerRequest, run_local_planner
from .pddl import PDDLError, ground_actions, normalize_action_string, parse_task, replay_plan
from .schema import SCHEMA_VERSION, validate_instance_accounting, validate_planner_attempt, validate_supervised_example, write_schema_documents

DEFAULT_PLANNERS = ("gbfs", "ff", "iw", "graphplan")
FAST_DOWNWARD_ALIAS_BY_PLANNER = {"ff": ("ff", "fast-forward"), "iw": ("iw", "iterated-width")}
_FAST_DOWNWARD_ALIASES: set[str] | None = None
RESOURCE_LIMITS = {
    "planner_timeout": 60,
    "planner_attempt_timeout_seconds": 1200,
    "domain_timeout_seconds": 3600,
    "grounding_timeout": 60,
    "max_grounded_actions": 100000,
    "max_grounded_atoms": 100000,
    "gbfs_max_applicable_actions": 2000,
    "gbfs_max_expansions": 250000,
    "gbfs_max_depth": 200,
    "max_plan_length": 500,
    "max_trace_steps": 500,
    "max_jsonl_target_chars": 10000000,
    "local_graphplan_max_expansions": 250000,
    "local_ff_best_first_max_expansions": 500,
    "local_iw_width": 3,
    "local_iw_max_width": 3,
    "local_iw_novelty_max_expansions": 500,
    "local_iw_recovery_trace_steps": 20,
    "local_goal_regression_goal_threshold": 8,
    "local_goal_regression_max_attempts": 10000,
    "local_max_mutex_pairs": 1000000,
    "local_serial_recovery_max_expansions": 250000,
}


def build_instance_accounting(input_root: Path, output_root: Path) -> list[dict[str, Any]]:
    ensure_layout(output_root)
    manifest_path = input_root / "accepted_manifest.jsonl"
    rows = read_jsonl(manifest_path)
    records: list[dict[str, Any]] = []
    for row in rows:
        domain_path = Path(str(row.get("domain_path", "")))
        problem_path = Path(str(row.get("problem_path", "")))
        result_path = Path(str(row.get("render_result_path", "")))
        trace_path = result_path.parent / "trace.vfg.json" if str(result_path) else Path("")
        frames = sorted((result_path.parent / "frames").glob("*.png")) if result_path.parent.exists() else []
        vision_status = _vision_status(result_path=result_path, trace_path=trace_path, frames=frames)
        record = {
            "schema_version": SCHEMA_VERSION,
            "manifest_index": row.get("index"),
            "domain": str(row.get("domain_id", "")),
            "instance_id": str(row.get("instance_id", "")),
            "split": str(row.get("split", "")),
            "bucket": str(row.get("bucket", "")),
            "domain_path": relpath(domain_path),
            "problem_path": relpath(problem_path),
            "render_result_path": relpath(result_path),
            "render_trace_path": relpath(trace_path),
            "frame_paths": [relpath(path) for path in frames],
            "source_manifest": relpath(manifest_path),
            "vision_status": vision_status,
            "files": {
                "domain_exists": domain_path.exists(),
                "problem_exists": problem_path.exists(),
                "result_json_exists": result_path.exists(),
                "trace_vfg_exists": trace_path.exists(),
                "frame_count": len(frames),
            },
        }
        errors = validate_instance_accounting(record)
        if errors:
            record["schema_errors"] = errors
        records.append(record)
    records.sort(key=lambda item: (item["domain"], item["split"], item["instance_id"]))
    write_jsonl(output_root / "diagnostics" / "instance_accounting.jsonl", records)
    return records


def preflight_pddl_features(input_root: Path, accounting_path: Path, output_path: Path) -> list[dict[str, Any]]:
    del input_root
    records: list[dict[str, Any]] = []
    for account in read_jsonl(accounting_path):
        domain_path = repo_root() / str(account["domain_path"])
        problem_path = repo_root() / str(account["problem_path"])
        try:
            task = parse_task(domain_path, problem_path)
            status = "supported" if not task.unsupported_features else "skipped_unsupported_pddl"
            unsupported = list(task.unsupported_features)
            action_count = len(task.actions)
            object_count = len(task.objects_by_type.get("object", ()))
        except Exception as exc:
            status = "failed_parse_domain" if not problem_path.exists() else "failed_parse_problem"
            unsupported = [type(exc).__name__]
            action_count = 0
            object_count = 0
        records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "domain": account["domain"],
                "instance_id": account["instance_id"],
                "split": account["split"],
                "status": status,
                "unsupported_features": unsupported,
                "action_schema_count": action_count,
                "object_count": object_count,
                "domain_path": account["domain_path"],
                "problem_path": account["problem_path"],
            }
        )
    write_jsonl(output_path, records)
    return records


def validate_vision_assets(accounting_path: Path, output_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for account in read_jsonl(accounting_path):
        frames = [repo_root() / path for path in account.get("frame_paths", [])]
        unreadable = [relpath(path) for path in frames if not _is_readable_png(path)]
        status = str(account.get("vision_status"))
        if not unreadable and status.startswith("vision_available"):
            status = _alignment_status(account)
        elif unreadable:
            status = "vision_unreadable_frames"
        records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "domain": account["domain"],
                "instance_id": account["instance_id"],
                "split": account["split"],
                "status": status,
                "vision_supervision_available": status in {"vision_available_step_aligned", "vision_available_unaligned"},
                "missing_frames": 0 if frames else 1,
                "unreadable_frames": unreadable,
                "frame_paths": account.get("frame_paths", []),
                "render_result_path": account.get("render_result_path"),
                "render_trace_path": account.get("render_trace_path"),
            }
        )
    write_jsonl(output_path, records)
    return records


def generate_supervised_data(input_root: Path, output_root: Path, planners: tuple[str, ...] = DEFAULT_PLANNERS, limits: dict[str, int] | None = None, progress_callback: Callable[[dict[str, Any]], None] | None = None, jobs: int = 1) -> dict[str, Any]:
    _validate_planners(planners)
    if jobs < 1:
        raise ValueError("jobs must be at least 1")
    limits = {**RESOURCE_LIMITS, **(limits or {})}
    clear_output_root(output_root, input_root=input_root)
    write_schema_documents(output_root)
    accounting = build_instance_accounting(input_root, output_root)
    preflight = preflight_pddl_features(input_root, output_root / "diagnostics" / "instance_accounting.jsonl", output_root / "diagnostics" / "pddl_feature_preflight.jsonl")
    vision = validate_vision_assets(output_root / "diagnostics" / "instance_accounting.jsonl", output_root / "diagnostics" / "vision_validation.jsonl")
    preflight_by_id = {row["instance_id"]: row for row in preflight}
    vision_by_id = {row["instance_id"]: row for row in vision}

    attempts, replay_rows, examples = run_planner_jobs(jobs, accounting, planners, preflight_by_id, vision_by_id, limits, progress_callback, _attempt_planner)

    attempts.sort(key=lambda item: (item["domain"], item["split"], item["instance_id"], item["planner"]))
    replay_rows.sort(key=lambda item: str(item["replay_validation_id"]))
    examples.sort(key=lambda item: str(item["example_id"]))
    write_jsonl(output_root / "diagnostics" / "planner_attempts.jsonl", attempts)
    write_jsonl(output_root / "diagnostics" / "replay_validation.jsonl", replay_rows)
    for split in ("train", "dev", "test"):
        write_jsonl(output_root / f"{split}.jsonl", [example for example in examples if example["split"] == split])
    reports = _write_reports(input_root, output_root, accounting, attempts, examples, limits)
    return reports


def _attempt_planner(account: dict[str, Any], preflight: dict[str, Any], vision: dict[str, Any], planner: str, limits: dict[str, int]) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    base = {
        "schema_version": SCHEMA_VERSION,
        "domain": account["domain"],
        "instance_id": account["instance_id"],
        "split": account["split"],
        "planner": planner,
        "domain_path": account["domain_path"],
        "problem_path": account["problem_path"],
        "planner_command": None,
        "planner_version": None,
        "trace_fidelity": "none",
        "replay_validation_id": None,
        "plan_hash": None,
    }
    if preflight.get("status") not in {"supported"}:
        return _attempt(base, str(preflight.get("status", "skipped_unsupported_pddl"))), None, None
    try:
        task = parse_task(repo_root() / account["domain_path"], repo_root() / account["problem_path"])
        if planner == "gbfs" and gbfs_estimate_exceeds_resource_gate(task, limits):
            return _attempt(base, "skipped_resource_limit", resource_gate="gbfs_estimated_applicable_actions"), None, None
        grounded, grounding_status = ground_actions(task, max_grounded_actions=limits["max_grounded_actions"], max_grounded_atoms=limits["max_grounded_atoms"])
    except PDDLError:
        return _attempt(base, "failed_parse_domain"), None, None
    except Exception:
        return _attempt(base, "failed_grounding"), None, None
    if grounding_status:
        return _attempt(base, grounding_status), None, None
    if planner == "gbfs":
        if should_try_goal_regression_first(task, limits):
            recovery = recover_goal_regression_plan(GoalRegressionRequest(task, tuple(grounded), limits, "goal_regression_before_gbfs", "many_goal_recovery_preferred"))
            if recovery.status == "success_full_trace":
                trace = gbfs_trace([], 0, 1)
                trace["plan_recovery"] = {**recovery.trace, "is_exact_gbfs": False}
                replay_payload = replay_plan(task, recovery.plan, grounded_actions=grounded)
                return _successful_attempt(base, account, vision, planner, recovery.status, recovery.plan, replay_payload, trace, limits=limits)
        plan, trace, status = run_gbfs(task, grounded, limits=limits)
        if status != "success_full_trace":
            recovery = recover_goal_regression_plan(GoalRegressionRequest(task, tuple(grounded), limits, "goal_regression_after_gbfs", status))
            if recovery.status == "success_full_trace":
                trace["plan_recovery"] = {
                    **recovery.trace,
                    "is_exact_gbfs": False,
                }
                replay_payload = replay_plan(task, recovery.plan, grounded_actions=grounded)
                return _successful_attempt(base, account, vision, planner, recovery.status, recovery.plan, replay_payload, trace, limits=limits)
            return _attempt(base, status, expansion_count=trace.get("expansion_count", 0)), None, None
        replay_payload = replay_plan(task, plan, grounded_actions=grounded)
        return _successful_attempt(base, account, vision, planner, status, plan, replay_payload, trace, limits=limits)
    if planner in {"ff", "iw", "graphplan"}:
        command = _external_planner_command(planner)
        if command:
            plan, command_label, status = _external_plan(planner, account, limits)
            base["planner_command"] = command_label
            if status == "success_plan_replayed":
                replay_payload = replay_plan(task, plan, grounded_actions=grounded)
                return _successful_attempt(base, account, vision, planner, "success_plan_replayed", plan, replay_payload, {"external_plan_only": True}, limits=limits)
        local = run_local_planner(LocalPlannerRequest(planner=planner, task=task, grounded=tuple(grounded), limits=limits))
        if local.status == "success_full_trace":
            replay_payload = replay_plan(task, local.plan, grounded_actions=grounded)
            return _successful_attempt(base, account, vision, planner, local.status, local.plan, replay_payload, local.trace, limits=limits)
        return _attempt(base, local.status), None, None
    plan, command, status = _external_plan(planner, account, limits)
    base["planner_command"] = command
    if status != "success_plan_replayed":
        return _attempt(base, status), None, None
    replay_payload = replay_plan(task, plan, grounded_actions=grounded)
    return _successful_attempt(base, account, vision, planner, "success_plan_replayed", plan, replay_payload, {"external_plan_only": True}, limits=limits)


def _successful_attempt(base: dict[str, Any], account: dict[str, Any], vision: dict[str, Any], planner: str, status: str, plan: list[str], replay_payload: dict[str, Any], trace: dict[str, Any], *, limits: dict[str, int]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    if not replay_payload["replay_ok"]:
        failed = str(replay_payload["status"])
        return _attempt(base, failed), _replay_row(base, replay_payload, plan, limits=limits), None
    plan_hash = stable_hash(plan)
    replay_id = f"{account['instance_id']}::{planner}::{plan_hash[:12]}"
    attempt = _attempt(base, status, trace_fidelity=status, replay_validation_id=replay_id, plan_hash=plan_hash, plan_length=len(plan))
    replay = _replay_row({**attempt, "replay_validation_id": replay_id}, replay_payload, plan, limits=limits)
    example = _build_example(account, vision, attempt, plan, replay, trace, limits=limits)
    example_text = json.dumps(example, sort_keys=True, ensure_ascii=True)
    if len(example_text) > limits["max_jsonl_target_chars"]:
        return _attempt(base, "skipped_resource_limit"), replay, None
    errors = validate_supervised_example(example)
    if errors:
        attempt["status"] = "failed_schema_validation"
        attempt["schema_errors"] = errors
        return attempt, replay, None
    return attempt, replay, example


def _attempt(base: dict[str, Any], status: str, **extra: Any) -> dict[str, Any]:
    record = {**base, "status": status, **extra}
    errors = validate_planner_attempt(record)
    if errors:
        record["schema_errors"] = errors
    return record


def _replay_row(attempt: dict[str, Any], replay_payload: dict[str, Any], plan: list[str], *, limits: dict[str, int]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "replay_validation_id": attempt.get("replay_validation_id") or f"{attempt['instance_id']}::{attempt['planner']}::failed",
        "domain": attempt["domain"],
        "instance_id": attempt["instance_id"],
        "planner": attempt["planner"],
        "status": replay_payload["status"],
        "replay_ok": replay_payload["replay_ok"],
        "goal_satisfied": replay_payload["goal_satisfied"],
        "plan": plan,
        "transition_count": replay_payload["transition_count"],
        "transitions": replay_payload["transitions"][: limits["max_trace_steps"]],
        "final_state_atoms": replay_payload["final_state_atoms"],
    }


def _build_example(account: dict[str, Any], vision: dict[str, Any], attempt: dict[str, Any], plan: list[str], replay: dict[str, Any], trace: dict[str, Any], *, limits: dict[str, int]) -> dict[str, Any]:
    example_id = stable_hash([account["instance_id"], attempt["planner"], attempt["plan_hash"]])[:32]
    vision_available = bool(vision.get("vision_supervision_available"))
    return {
        "schema_version": SCHEMA_VERSION,
        "example_id": example_id,
        "domain": account["domain"],
        "instance_id": account["instance_id"],
        "split": account["split"],
        "planner": attempt["planner"],
        "plan_hash": attempt["plan_hash"],
        "trace_fidelity": attempt["trace_fidelity"],
        "vision_supervision_available": vision_available,
        "model_facing": {
            "task": "Produce a replay-valid PDDL action plan for the given planning instance.",
            "domain": account["domain"],
            "planner": attempt["planner"],
            "problem_source": account["problem_path"],
            "domain_source": account["domain_path"],
            "vision": {
                "available": vision_available,
                "status": vision.get("status"),
                "frame_paths": vision.get("frame_paths", []) if vision_available else [],
                "trace_path": vision.get("render_trace_path") if vision_available else None,
            },
            "response_format": {"plan": "list of canonical action strings"},
        },
        "supervised_target": {
            "plan": plan,
            "planner_trace": trace,
            "replay_transitions": replay["transitions"],
        },
        "evaluation_metadata": {
            "validation_authority": "generic_replay_validator",
            "replay_validation_id": replay["replay_validation_id"],
            "goal_satisfied": replay["goal_satisfied"],
            "final_state_atoms": replay["final_state_atoms"],
            "source_manifest": account["source_manifest"],
            "generation_config": {"resource_limits": limits},
        },
    }


def _external_plan(planner: str, account: dict[str, Any], limits: dict[str, int]) -> tuple[list[str], str | None, str]:
    command = _external_planner_command(planner, account)
    if not command:
        return [], None, "skipped_planner_unavailable"
    try:
        completed = _run_external_command(command, timeout=limits["planner_timeout"])
    except subprocess.TimeoutExpired:
        return [], _command_label(command), "failed_planner_timeout"
    if completed.returncode != 0:
        return [], _command_label(command), "failed_planner_error"
    plan: list[str] = []
    for line in completed.stdout.splitlines():
        match = re_action(line)
        if match:
            try:
                plan.append(normalize_action_string(match))
            except PDDLError:
                return [], _command_label(command), "failed_action_normalization"
    if not plan:
        return [], _command_label(command), "failed_no_plan_extracted"
    return plan, _command_label(command), "success_plan_replayed"


def _run_external_command(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def handle_sigterm(signum: int, _frame: Any) -> None:
        _kill_process_group(process, grace_seconds=0)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, handle_sigterm)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _kill_process_group(process, grace_seconds=1)
        raise exc
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _kill_process_group(process: subprocess.Popen[str], *, grace_seconds: float) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.terminate()
    if grace_seconds > 0:
        sleep(grace_seconds)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        if process.poll() is None:
            process.kill()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _external_planner_command(planner: str, account: dict[str, Any] | None = None) -> list[str] | None:
    env = {"ff": "PHASE3_FF_PLANNER", "iw": "PHASE3_IW_PLANNER", "graphplan": "PHASE3_GRAPHPLAN_PLANNER"}[planner]
    configured = os.environ.get(env)
    domain_problem = []
    if account is not None:
        domain_problem = [str(repo_root() / account["domain_path"]), str(repo_root() / account["problem_path"])]
    if configured:
        return [configured, *domain_problem]
    if planner in {"ff", "iw"}:
        fallback = repo_root() / "modules" / "downward" / "fast-downward.py"
        alias = _fast_downward_alias_for(planner, fallback)
        if alias is not None:
            return [str(fallback), f"--alias={alias}", *domain_problem]
    return None


def _command_label(command: list[str]) -> str:
    return " ".join(relpath(part) for part in command)


def _fast_downward_alias_for(planner: str, fallback: Path) -> str | None:
    if not fallback.exists():
        return None
    aliases = _available_fast_downward_aliases(fallback)
    for alias in FAST_DOWNWARD_ALIAS_BY_PLANNER.get(planner, ()):
        if alias in aliases:
            return alias
    return None


def _available_fast_downward_aliases(fallback: Path) -> set[str]:
    global _FAST_DOWNWARD_ALIASES
    if _FAST_DOWNWARD_ALIASES is not None:
        return _FAST_DOWNWARD_ALIASES
    try:
        completed = subprocess.run([str(fallback), "--show-aliases"], check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        _FAST_DOWNWARD_ALIASES = set()
        return _FAST_DOWNWARD_ALIASES
    if completed.returncode != 0:
        _FAST_DOWNWARD_ALIASES = set()
    else:
        _FAST_DOWNWARD_ALIASES = {line.strip() for line in completed.stdout.splitlines() if line.strip()}
    return _FAST_DOWNWARD_ALIASES


def _validate_planners(planners: tuple[str, ...]) -> None:
    supported = set(DEFAULT_PLANNERS)
    for planner in planners:
        if planner not in supported:
            raise ValueError(f"unsupported Phase 3 planner: {planner}")


def re_action(line: str) -> str | None:
    text = line.strip()
    if text.startswith("(") and text.endswith(")"):
        return text
    if ":" in text:
        candidate = text.split(":", 1)[1].strip()
        if candidate.startswith("(") and candidate.endswith(")"):
            return candidate
    return None


def _vision_status(*, result_path: Path, trace_path: Path, frames: list[Path]) -> str:
    if not result_path.exists():
        return "vision_missing_result_json"
    if not trace_path.exists():
        return "vision_missing_trace_vfg"
    if not frames:
        return "vision_missing_frames"
    if any(not _is_readable_png(path) for path in frames):
        return "vision_unreadable_frames"
    return "vision_available_unaligned"


def _is_readable_png(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(8) == b"\x89PNG\r\n\x1a\n"
    except OSError:
        return False


def _alignment_status(account: dict[str, Any]) -> str:
    trace_path = repo_root() / str(account.get("render_trace_path", ""))
    try:
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
    except Exception:
        return "vision_available_unaligned"
    actions = trace.get("actions") if isinstance(trace, dict) else None
    frame_count = len(account.get("frame_paths", []))
    if isinstance(actions, list) and frame_count in {len(actions), len(actions) + 1}:
        return "vision_available_step_aligned"
    return "vision_available_unaligned"


def _write_reports(input_root: Path, output_root: Path, accounting: list[dict[str, Any]], attempts: list[dict[str, Any]], examples: list[dict[str, Any]], limits: dict[str, int]) -> dict[str, Any]:
    domain_counts = Counter(row["domain"] for row in accounting)
    split_counts = Counter(row["split"] for row in accounting)
    active_planners = tuple(sorted({row["planner"] for row in attempts}))
    planner_status = {planner: dict(Counter(row["status"] for row in attempts if row["planner"] == planner)) for planner in active_planners}
    fidelity = dict(Counter(row["trace_fidelity"] for row in examples))
    reports = {
        "domain_coverage": {"domains": dict(sorted(domain_counts.items())), "domain_count": len(domain_counts)},
        "split_coverage": {"splits": dict(sorted(split_counts.items()))},
        "planner_status_summary": planner_status,
        "fidelity_summary": fidelity,
    }
    for name, payload in reports.items():
        write_json(output_root / "reports" / f"{name}.json", payload)
    generated_files = ["train.jsonl", "dev.jsonl", "test.jsonl", "diagnostics/instance_accounting.jsonl", "diagnostics/planner_attempts.jsonl", "diagnostics/replay_validation.jsonl", "diagnostics/vision_validation.jsonl", "diagnostics/pddl_feature_preflight.jsonl"]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "input_root": relpath(input_root),
        "output_root": relpath(output_root),
        "planners": list(active_planners),
        "resource_limits": limits,
        "stable_sorting": ["domain", "split", "instance_id", "planner"],
        "generated_file_digests": {path: file_sha256(output_root / path) for path in generated_files if (output_root / path).exists()},
        "ignored_nondeterministic_fields": [],
    }
    summary = {
        "schema_version": SCHEMA_VERSION,
        "accepted_instances": len(accounting),
        "planner_attempts": len(attempts),
        "emitted_examples": len(examples),
        "split_examples": {split: count_jsonl(output_root / f"{split}.jsonl") for split in ("train", "dev", "test")},
        "planner_status_summary": planner_status,
        "fidelity_summary": fidelity,
        "diagnostics": {"instance_accounting": "diagnostics/instance_accounting.jsonl", "planner_attempts": "diagnostics/planner_attempts.jsonl", "replay_validation": "diagnostics/replay_validation.jsonl", "vision_validation": "diagnostics/vision_validation.jsonl", "pddl_feature_preflight": "diagnostics/pddl_feature_preflight.jsonl"},
    }
    write_json(output_root / "generation_manifest.json", manifest)
    write_json(output_root / "summary.json", summary)
    return {"summary": summary, "reports": reports, "manifest": manifest}


def add_common_generation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-root", type=Path, default=Path("data/curriculum_pddl"))
    parser.add_argument("--output-root", type=Path, default=Path("data/phase3_supervised_planning"))
    parser.add_argument("--json", action="store_true")


def print_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
