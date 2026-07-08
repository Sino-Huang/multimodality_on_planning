from __future__ import annotations

import os
import signal
from dataclasses import dataclass
from multiprocessing import get_context
from multiprocessing.queues import Queue
from queue import Empty
from time import monotonic, sleep
from typing import Any

from .attempt_records import AttemptFunction, AttemptResult, JSONRecord, PlannerJob, ProgressCallback, emit_finished, emit_started, process_error_result, skipped_domain_budget_attempt, timeout_result


@dataclass(frozen=True, slots=True)
class RunningJob:
    job: PlannerJob
    process: Any
    queue: Queue[Any]
    started_at: float
    reserved_timeout_seconds: int


def run_planner_jobs(jobs: int, accounting: list[JSONRecord], planners: tuple[str, ...], preflight_by_id: dict[str, JSONRecord], vision_by_id: dict[str, JSONRecord], limits: dict[str, int], progress_callback: ProgressCallback | None, attempt_function: AttemptFunction) -> tuple[list[JSONRecord], list[JSONRecord], list[JSONRecord]]:
    if jobs < 1:
        raise ValueError("jobs must be at least 1")
    _validate_timeout_limits(limits)
    planner_jobs = _planner_jobs(accounting, planners, preflight_by_id, vision_by_id)
    return _run_bounded(jobs, planner_jobs, limits, progress_callback, attempt_function)


def _planner_jobs(accounting: list[JSONRecord], planners: tuple[str, ...], preflight_by_id: dict[str, JSONRecord], vision_by_id: dict[str, JSONRecord]) -> list[PlannerJob]:
    total_attempts = len(accounting) * len(planners)
    planner_jobs: list[PlannerJob] = []
    for account in accounting:
        for planner in planners:
            planner_jobs.append(
                PlannerJob(
                    account=account,
                    preflight=preflight_by_id.get(str(account["instance_id"]), {}),
                    vision=vision_by_id.get(str(account["instance_id"]), {}),
                    planner=planner,
                    attempt_number=len(planner_jobs) + 1,
                    total_attempts=total_attempts,
                )
            )
    return planner_jobs


def _run_bounded(jobs: int, planner_jobs: list[PlannerJob], limits: dict[str, int], progress_callback: ProgressCallback | None, attempt_function: AttemptFunction) -> tuple[list[JSONRecord], list[JSONRecord], list[JSONRecord]]:
    attempts: list[JSONRecord] = []
    replay_rows: list[JSONRecord] = []
    examples: list[JSONRecord] = []
    running: list[RunningJob] = []
    pending = list(planner_jobs)
    timed_out_seconds_by_domain: dict[str, int] = {}
    reserved_seconds_by_domain: dict[str, int] = {}
    attempt_timeout_seconds = _positive_limit(limits, "planner_attempt_timeout_seconds")
    domain_timeout_seconds = _positive_limit(limits, "domain_timeout_seconds")
    context = get_context("fork")

    try:
        while pending or running:
            while pending and len(running) < jobs:
                selected = _next_schedulable_job(pending, timed_out_seconds_by_domain, reserved_seconds_by_domain, attempt_timeout_seconds, domain_timeout_seconds, has_running=bool(running))
                if selected is None:
                    break
                job = pending.pop(selected)
                if _domain_budget_exhausted(job, timed_out_seconds_by_domain, domain_timeout_seconds):
                    attempt = skipped_domain_budget_attempt(job)
                    emit_started(job, progress_callback)
                    _append_result(attempts, replay_rows, examples, attempt, None, None)
                    emit_finished(job, attempt, progress_callback)
                    continue
                reserved_timeout_seconds = _reserve_domain_budget(job, reserved_seconds_by_domain, attempt_timeout_seconds, domain_timeout_seconds)
                emit_started(job, progress_callback)
                queue = context.Queue()
                process = context.Process(target=_run_job, args=(job, limits, attempt_function, queue))
                process.start()
                running.append(RunningJob(job=job, process=process, queue=queue, started_at=monotonic(), reserved_timeout_seconds=reserved_timeout_seconds))
            if running:
                _collect_running(running, attempts, replay_rows, examples, timed_out_seconds_by_domain, reserved_seconds_by_domain, attempt_timeout_seconds, progress_callback)
                if running:
                    sleep(0.05)
    finally:
        _cleanup_running(running)
    return attempts, replay_rows, examples


def _run_job(job: PlannerJob, limits: dict[str, int], attempt_function: AttemptFunction, queue: Queue[Any]) -> None:
    os.setsid()
    queue.put(attempt_function(job.account, job.preflight, job.vision, job.planner, limits))


def _collect_running(running: list[RunningJob], attempts: list[JSONRecord], replay_rows: list[JSONRecord], examples: list[JSONRecord], timed_out_seconds_by_domain: dict[str, int], reserved_seconds_by_domain: dict[str, int], attempt_timeout_seconds: int | None, progress_callback: ProgressCallback | None) -> None:
    for item in tuple(running):
        result = _completed_result(item, attempt_timeout_seconds)
        if result is None:
            continue
        running.remove(item)
        attempt, replay, example = result
        _release_domain_budget(item, reserved_seconds_by_domain)
        _record_timeout_budget(item.job, attempt, timed_out_seconds_by_domain, attempt_timeout_seconds)
        _append_result(attempts, replay_rows, examples, attempt, replay, example)
        emit_finished(item.job, attempt, progress_callback)


def _completed_result(item: RunningJob, attempt_timeout_seconds: int | None) -> AttemptResult | None:
    result = _queue_result(item.queue)
    if result is not None:
        item.process.join()
        _close_queue(item.queue)
        return result
    if attempt_timeout_seconds is not None and monotonic() - item.started_at >= attempt_timeout_seconds:
        _terminate_process_group(item.process)
        _close_queue(item.queue)
        return timeout_result(item.job)
    if not item.process.is_alive():
        item.process.join()
        result = _queue_result(item.queue)
        _close_queue(item.queue)
        if result is not None:
            return result
        return process_error_result(item.job)
    return None


def _queue_result(queue: Queue[Any]) -> AttemptResult | None:
    try:
        return queue.get_nowait()
    except Empty:
        return None


def _close_queue(queue: Queue[Any]) -> None:
    queue.close()
    queue.join_thread()


def _close_queue_safely(queue: Queue[Any]) -> None:
    try:
        _close_queue(queue)
    except (OSError, ValueError):
        pass


def _terminate_process_group(process: Any) -> None:
    pid = process.pid
    if pid is None:
        process.terminate()
        process.join(timeout=1)
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        process.terminate()
    sleep(1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        if process.is_alive():
            process.kill()
    process.join(timeout=1)
    if process.is_alive():
        process.kill()
        process.join()


def _cleanup_running(running: list[RunningJob]) -> None:
    for item in tuple(running):
        _terminate_process_group(item.process)
        _close_queue_safely(item.queue)
        running.remove(item)


def _record_timeout_budget(job: PlannerJob, attempt: JSONRecord, timed_out_seconds_by_domain: dict[str, int], attempt_timeout_seconds: int | None) -> None:
    if attempt_timeout_seconds is None:
        return
    if attempt.get("resource_gate") != "planner_attempt_timeout":
        return
    domain = str(job.account["domain"])
    timed_out_seconds_by_domain[domain] = timed_out_seconds_by_domain.get(domain, 0) + attempt_timeout_seconds


def _next_schedulable_job(pending: list[PlannerJob], timed_out_seconds_by_domain: dict[str, int], reserved_seconds_by_domain: dict[str, int], attempt_timeout_seconds: int | None, domain_timeout_seconds: int | None, *, has_running: bool) -> int | None:
    fallback: int | None = None
    for index, job in enumerate(pending):
        if _domain_budget_exhausted(job, timed_out_seconds_by_domain, domain_timeout_seconds):
            return index
        if not _domain_budget_saturated_by_reservations(job, timed_out_seconds_by_domain, reserved_seconds_by_domain, attempt_timeout_seconds, domain_timeout_seconds):
            return index
        if fallback is None:
            fallback = index
    if has_running:
        return None
    return fallback


def _domain_budget_exhausted(job: PlannerJob, timed_out_seconds_by_domain: dict[str, int], domain_timeout_seconds: int | None) -> bool:
    if domain_timeout_seconds is None:
        return False
    domain = str(job.account["domain"])
    return timed_out_seconds_by_domain.get(domain, 0) >= domain_timeout_seconds


def _domain_budget_saturated_by_reservations(job: PlannerJob, timed_out_seconds_by_domain: dict[str, int], reserved_seconds_by_domain: dict[str, int], attempt_timeout_seconds: int | None, domain_timeout_seconds: int | None) -> bool:
    if attempt_timeout_seconds is None or domain_timeout_seconds is None:
        return False
    domain = str(job.account["domain"])
    reserved = reserved_seconds_by_domain.get(domain, 0)
    if reserved == 0:
        return False
    return timed_out_seconds_by_domain.get(domain, 0) + reserved + attempt_timeout_seconds > domain_timeout_seconds


def _reserve_domain_budget(job: PlannerJob, reserved_seconds_by_domain: dict[str, int], attempt_timeout_seconds: int | None, domain_timeout_seconds: int | None) -> int:
    if attempt_timeout_seconds is None or domain_timeout_seconds is None:
        return 0
    domain = str(job.account["domain"])
    reserved_seconds_by_domain[domain] = reserved_seconds_by_domain.get(domain, 0) + attempt_timeout_seconds
    return attempt_timeout_seconds


def _release_domain_budget(item: RunningJob, reserved_seconds_by_domain: dict[str, int]) -> None:
    if item.reserved_timeout_seconds == 0:
        return
    domain = str(item.job.account["domain"])
    remaining = reserved_seconds_by_domain.get(domain, 0) - item.reserved_timeout_seconds
    if remaining > 0:
        reserved_seconds_by_domain[domain] = remaining
    else:
        reserved_seconds_by_domain.pop(domain, None)


def _positive_limit(limits: dict[str, int], key: str) -> int | None:
    value = limits.get(key)
    if value is None or value <= 0:
        return None
    return value


def _validate_timeout_limits(limits: dict[str, int]) -> None:
    for key in ("planner_attempt_timeout_seconds", "domain_timeout_seconds"):
        value = limits.get(key)
        if value is not None and value < 0:
            raise ValueError(f"{key} must be non-negative")


def _append_result(attempts: list[JSONRecord], replay_rows: list[JSONRecord], examples: list[JSONRecord], attempt: JSONRecord, replay: JSONRecord | None, example: JSONRecord | None) -> None:
    attempts.append(attempt)
    if replay is not None:
        replay_rows.append(replay)
    if example is not None:
        examples.append(example)

