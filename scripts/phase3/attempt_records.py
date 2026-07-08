from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


JSONRecord = dict[str, Any]
AttemptResult = tuple[JSONRecord, JSONRecord | None, JSONRecord | None]
AttemptFunction = Callable[[JSONRecord, JSONRecord, JSONRecord, str, dict[str, int]], AttemptResult]
ProgressCallback = Callable[[JSONRecord], None]


@dataclass(frozen=True, slots=True)
class PlannerJob:
    account: JSONRecord
    preflight: JSONRecord
    vision: JSONRecord
    planner: str
    attempt_number: int
    total_attempts: int


def timeout_result(job: PlannerJob) -> AttemptResult:
    return attempt_record(job, "failed_planner_timeout", resource_gate="planner_attempt_timeout"), None, None


def process_error_result(job: PlannerJob) -> AttemptResult:
    return attempt_record(job, "failed_planner_error", resource_gate="planner_process_exit"), None, None


def skipped_domain_budget_attempt(job: PlannerJob) -> JSONRecord:
    return attempt_record(job, "skipped_resource_limit", resource_gate="domain_timeout_budget")


def attempt_record(job: PlannerJob, status: str, *, resource_gate: str) -> JSONRecord:
    return {
        "schema_version": "phase3_supervised_planning_v1",
        "domain": job.account["domain"],
        "instance_id": job.account["instance_id"],
        "split": job.account["split"],
        "planner": job.planner,
        "domain_path": job.account["domain_path"],
        "problem_path": job.account["problem_path"],
        "planner_command": None,
        "planner_version": None,
        "trace_fidelity": "none",
        "replay_validation_id": None,
        "plan_hash": None,
        "status": status,
        "resource_gate": resource_gate,
    }


def emit_started(job: PlannerJob, progress_callback: ProgressCallback | None) -> None:
    if progress_callback is None:
        return
    progress_callback(progress_event("attempt_started", job))


def emit_finished(job: PlannerJob, attempt: JSONRecord, progress_callback: ProgressCallback | None) -> None:
    if progress_callback is None:
        return
    progress_callback({**progress_event("attempt_finished", job), "status": attempt["status"], "trace_fidelity": attempt["trace_fidelity"]})


def progress_event(phase: str, job: PlannerJob) -> JSONRecord:
    return {
        "attempt_number": job.attempt_number,
        "bucket": job.account["bucket"],
        "domain": job.account["domain"],
        "instance_id": job.account["instance_id"],
        "phase": phase,
        "planner": job.planner,
        "split": job.account["split"],
        "total_attempts": job.total_attempts,
    }
