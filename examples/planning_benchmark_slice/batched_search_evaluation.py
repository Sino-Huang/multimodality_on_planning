"""Deterministic resource-bounded scheduling for governed search evaluation."""

from __future__ import annotations

import json
import math
import signal
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from src.data_collect.governance import StopOutcome

from .model_search_episode import SearchEpisodeSession, SearchPolicyRequest
from .qwen_text_policy import (
    FROZEN_MAX_BATCH_INPUT_TOKENS,
    FROZEN_MAX_BATCH_SIZE,
    BatchedPolicyAdapter,
)

DIFFICULTIES = ("easy", "medium", "hard")
QUALIFICATION_SECONDS = 60 * 60
ROLLOUT_CUTOFF_SECONDS = 18 * 60 * 60
GATE_DEADLINE_SECONDS = 20 * 60 * 60
ROLLOUT_CERTIFICATION_SECONDS = 15 * 60 * 60
SAFETY_MARGIN = 1.20


@dataclass(frozen=True, slots=True)
class DeterministicBatch:
    adapter_id: str | None
    requests: tuple[SearchPolicyRequest, ...]
    input_token_lengths: tuple[int, ...]

    @property
    def padded_input_tokens(self) -> int:
        return max(self.input_token_lengths) * len(self.input_token_lengths)


def form_deterministic_batches(
    requests: Sequence[SearchPolicyRequest],
    *,
    token_length: Callable[[SearchPolicyRequest], int],
    max_batch_size: int = FROZEN_MAX_BATCH_SIZE,
    max_batch_input_tokens: int = FROZEN_MAX_BATCH_INPUT_TOKENS,
) -> tuple[DeterministicBatch, ...]:
    """Sort and pack one deterministic scheduler round."""

    measured = [(request, token_length(request)) for request in requests]
    if any(length <= 0 for _request, length in measured):
        raise ValueError("request token lengths must be positive")
    measured.sort(
        key=lambda item: (
            item[0].adapter_id or "",
            item[0].seed,
            item[0].instance_id,
            item[0].decision_index,
            item[1],
        )
    )
    batches: list[DeterministicBatch] = []
    current: list[tuple[SearchPolicyRequest, int]] = []
    for item in measured:
        request, length = item
        if length > max_batch_input_tokens:
            raise ValueError("one request exceeds max_batch_input_tokens")
        candidate = [*current, item]
        same_adapter = not current or request.adapter_id == current[0][0].adapter_id
        padded_tokens = max(value for _request, value in candidate) * len(candidate)
        if current and (not same_adapter or len(candidate) > max_batch_size or padded_tokens > max_batch_input_tokens):
            batches.append(_batch_from_items(current))
            current = [item]
        else:
            current = candidate
    if current:
        batches.append(_batch_from_items(current))
    return tuple(batches)


def _batch_from_items(items: Sequence[tuple[SearchPolicyRequest, int]]) -> DeterministicBatch:
    return DeterministicBatch(
        adapter_id=items[0][0].adapter_id,
        requests=tuple(request for request, _length in items),
        input_token_lengths=tuple(length for _request, length in items),
    )


class SchedulerStopToken:
    """Shared stop state checked before every inference launch."""

    def __init__(self) -> None:
        self.requested = False
        self.reason: str | None = None

    def request_stop(self, reason: str) -> None:
        if not self.requested:
            self.requested = True
            self.reason = reason


@dataclass(frozen=True, slots=True)
class SchedulerResult:
    completed: Mapping[str, dict[str, Any]]
    incomplete_session_ids: tuple[str, ...]
    launched_batches: int
    stop_reason: str | None


class DeterministicSearchScheduler:
    """Drive concurrent trusted-runtime sessions one request per round."""

    def __init__(
        self,
        policy: BatchedPolicyAdapter,
        *,
        stop_token: SchedulerStopToken | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        self.policy = policy
        self.stop_token = stop_token or SchedulerStopToken()
        self.should_stop = should_stop

    def run(
        self,
        sessions: Sequence[SearchEpisodeSession],
        *,
        on_episode_complete: Callable[[SearchEpisodeSession, Mapping[str, Any]], None] | None = None,
    ) -> SchedulerResult:
        active = {session.session_id: session for session in sessions}
        if len(active) != len(sessions):
            raise ValueError("scheduler session IDs must be unique")
        completed: dict[str, dict[str, Any]] = {}
        launched_batches = 0
        try:
            while active and not self._stop_requested():
                requests: list[SearchPolicyRequest] = []
                for session_id in sorted(active):
                    session = active[session_id]
                    request = session.next_request()
                    if request is None:
                        episode = session.episode()
                        completed[session_id] = episode
                        if on_episode_complete is not None:
                            on_episode_complete(session, episode)
                    else:
                        requests.append(request)
                for session_id in completed:
                    active.pop(session_id, None)
                if not requests:
                    continue
                batches = form_deterministic_batches(
                    requests,
                    token_length=self.policy.input_token_length,
                    max_batch_size=self.policy.max_batch_size,
                    max_batch_input_tokens=self.policy.max_batch_input_tokens,
                )
                for batch in batches:
                    if self._stop_requested():
                        break
                    outputs = self.policy.generate_many(batch.requests)
                    if len(outputs) != len(batch.requests):
                        raise ValueError("batched policy returned the wrong output count")
                    launched_batches += 1
                    for request, output in zip(batch.requests, outputs, strict=True):
                        session = active[request.session_id]
                        session.submit_output(output)
                        if getattr(session, "complete", False):
                            episode = session.episode()
                            completed[request.session_id] = episode
                            if on_episode_complete is not None:
                                on_episode_complete(session, episode)
                            active.pop(request.session_id)
        except KeyboardInterrupt:
            self.stop_token.request_stop("SIGINT")
        return SchedulerResult(
            completed=completed,
            incomplete_session_ids=tuple(sorted(active)),
            launched_batches=launched_batches,
            stop_reason=self.stop_token.reason,
        )

    def _stop_requested(self) -> bool:
        if self.should_stop is not None and self.should_stop():
            self.stop_token.request_stop("wall_clock_cutoff")
        return self.stop_token.requested


@dataclass(frozen=True, slots=True)
class EvaluationTask:
    domain: str
    difficulty: str
    instance_id: str
    exact_reference_decisions: int

    def __post_init__(self) -> None:
        if self.difficulty not in DIFFICULTIES:
            raise ValueError("task difficulty must be easy, medium, or hard")
        if not self.domain or not self.instance_id:
            raise ValueError("task domain and instance_id must be non-empty")
        if self.exact_reference_decisions <= 0:
            raise ValueError("exact_reference_decisions must be positive")

    @property
    def model_call_limit(self) -> int:
        return 2 * self.exact_reference_decisions


def balanced_fallback_panel(tasks: Sequence[EvaluationTask]) -> tuple[EvaluationTask, ...]:
    """Select the preregistered 15-domain, five-per-difficulty panel."""

    by_cell = {(task.domain, task.difficulty): task for task in tasks}
    domains = sorted({task.domain for task in tasks})
    if len(domains) != 15:
        raise ValueError("balanced fallback requires exactly 15 domains")
    panel = tuple(by_cell[(domain, DIFFICULTIES[index % 3])] for index, domain in enumerate(domains))
    if {difficulty: sum(task.difficulty == difficulty for task in panel) for difficulty in DIFFICULTIES} != {
        difficulty: 5 for difficulty in DIFFICULTIES
    }:
        raise AssertionError("fallback panel is not difficulty-balanced")
    return panel


def cost_balanced_task_shards(
    tasks: Sequence[EvaluationTask],
    *,
    shard_count: int = 2,
) -> tuple[tuple[EvaluationTask, ...], ...]:
    """Assign frozen tasks to GPU shards by exact-reference cost only."""

    if shard_count <= 0:
        raise ValueError("shard_count must be positive")
    shards: list[list[EvaluationTask]] = [[] for _ in range(shard_count)]
    loads = [0] * shard_count
    for task in sorted(tasks, key=lambda item: (-item.model_call_limit, item.instance_id)):
        shard_index = min(range(shard_count), key=lambda index: (loads[index], index))
        shards[shard_index].append(task)
        loads[shard_index] += task.model_call_limit
    return tuple(tuple(sorted(shard, key=lambda item: item.instance_id)) for shard in shards)


def evaluation_tasks_from_manifests(
    selected_rows: Sequence[Mapping[str, Any]],
    trace_rows: Sequence[Mapping[str, Any]],
    *,
    trace_record_count: Callable[[Mapping[str, Any]], int],
) -> tuple[EvaluationTask, ...]:
    """Join the 45 dev cells to their matching exact-reference call limits."""

    dev_rows = {str(row["instance_id"]): row for row in selected_rows if row.get("split") == "dev"}
    exact_rows = {str(row["instance_id"]): row for row in trace_rows if row.get("source", {}).get("split") == "dev"}
    if len(dev_rows) != 45 or set(dev_rows) != set(exact_rows):
        raise ValueError("selected tasks and exact references do not form the 45-task dev product")
    return tuple(
        EvaluationTask(
            domain=str(row["domain_id"]),
            difficulty=str(row["bucket"]),
            instance_id=instance_id,
            exact_reference_decisions=trace_record_count(exact_rows[instance_id]),
        )
        for instance_id, row in sorted(dev_rows.items())
    )


@dataclass(frozen=True, slots=True)
class PerformanceQualificationReceipt:
    """Outcome-blind measurements used to select rollout coverage."""

    model_load_seconds: float
    calls_per_second_lower_95: float
    runtime_overhead_seconds_per_call: float
    replay_calls_per_second: float
    probe_ids: tuple[str, ...]
    max_batch_size: int = FROZEN_MAX_BATCH_SIZE
    max_batch_input_tokens: int = FROZEN_MAX_BATCH_INPUT_TOKENS

    def __post_init__(self) -> None:
        if self.model_load_seconds < 0 or self.runtime_overhead_seconds_per_call < 0:
            raise ValueError("performance durations must be non-negative")
        if self.calls_per_second_lower_95 <= 0 or self.replay_calls_per_second <= 0:
            raise ValueError("performance throughputs must be positive")
        if not self.probe_ids:
            raise ValueError("performance qualification requires frozen probes")
        if self.max_batch_size != FROZEN_MAX_BATCH_SIZE or (
            self.max_batch_input_tokens != FROZEN_MAX_BATCH_INPUT_TOKENS
        ):
            raise ValueError("performance receipt differs from frozen batching settings")

    def projected_rollout_seconds(self, maximum_scheduled_calls: int) -> float:
        if maximum_scheduled_calls <= 0:
            raise ValueError("maximum_scheduled_calls must be positive")
        measured = (
            self.model_load_seconds
            + maximum_scheduled_calls / self.calls_per_second_lower_95
            + maximum_scheduled_calls * self.runtime_overhead_seconds_per_call
        )
        return SAFETY_MARGIN * measured

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls_per_second_lower_95": self.calls_per_second_lower_95,
            "max_batch_input_tokens": self.max_batch_input_tokens,
            "max_batch_size": self.max_batch_size,
            "model_load_seconds": self.model_load_seconds,
            "outcomes_observed": False,
            "probe_ids": list(self.probe_ids),
            "replay_calls_per_second": self.replay_calls_per_second,
            "runtime_overhead_seconds_per_call": self.runtime_overhead_seconds_per_call,
            "schema_version": "search_performance_qualification_v1",
        }


def lower_95_throughput_bound(samples: Sequence[float]) -> float:
    """Return the preregistered normal lower bound for outcome-blind throughput samples."""

    values = tuple(float(value) for value in samples)
    if not values or any(value <= 0 for value in values):
        raise ValueError("throughput samples must be positive")
    if len(values) == 1:
        return values[0]
    return max(
        math.nextafter(0.0, 1.0),
        statistics.mean(values) - 1.96 * statistics.stdev(values) / math.sqrt(len(values)),
    )


def build_performance_receipt(
    *,
    model_load_seconds: float,
    calls_per_second_samples: Sequence[float],
    runtime_overhead_seconds_per_call: float,
    replay_calls_per_second_samples: Sequence[float],
    probe_ids: Sequence[str],
) -> PerformanceQualificationReceipt:
    return PerformanceQualificationReceipt(
        model_load_seconds=model_load_seconds,
        calls_per_second_lower_95=lower_95_throughput_bound(calls_per_second_samples),
        runtime_overhead_seconds_per_call=runtime_overhead_seconds_per_call,
        replay_calls_per_second=lower_95_throughput_bound(replay_calls_per_second_samples),
        probe_ids=tuple(probe_ids),
    )


@dataclass(frozen=True, slots=True)
class CoverageSelection:
    mode: str | None
    tasks: tuple[EvaluationTask, ...]
    maximum_scheduled_calls: int
    projected_rollout_seconds: float
    outcome: StopOutcome


def select_certified_coverage(
    tasks: Sequence[EvaluationTask],
    receipt: PerformanceQualificationReceipt,
    *,
    model_sessions_per_task: int,
) -> CoverageSelection:
    """Try the complete 45-task product, then its frozen panel."""

    task_list = tuple(tasks)
    if len(task_list) != 45:
        raise ValueError("primary coverage must contain all 45 development tasks")
    if model_sessions_per_task <= 0:
        raise ValueError("model_sessions_per_task must be positive")
    for mode, candidate in (("full", task_list), ("panel", balanced_fallback_panel(task_list))):
        calls = model_sessions_per_task * sum(task.model_call_limit for task in candidate)
        projected = receipt.projected_rollout_seconds(calls)
        if projected <= ROLLOUT_CERTIFICATION_SECONDS:
            return CoverageSelection(mode, candidate, calls, projected, StopOutcome.PASS)
    panel = balanced_fallback_panel(task_list)
    calls = model_sessions_per_task * sum(task.model_call_limit for task in panel)
    return CoverageSelection(
        None,
        (),
        calls,
        receipt.projected_rollout_seconds(calls),
        StopOutcome.VALID_STOP,
    )


class GateClock:
    """One monotonic 20-hour clock shared by every stage of a gate."""

    def __init__(self, *, now: Callable[[], float] = monotonic, started_at: float | None = None) -> None:
        self._now = now
        self.started_at = now() if started_at is None else started_at

    @property
    def elapsed_seconds(self) -> float:
        return self._now() - self.started_at

    @property
    def phase(self) -> str:
        elapsed = self.elapsed_seconds
        if elapsed < QUALIFICATION_SECONDS:
            return "qualification"
        if elapsed < ROLLOUT_CUTOFF_SECONDS:
            return "rollout"
        if elapsed < GATE_DEADLINE_SECONDS:
            return "replay_and_adjudication"
        return "expired"

    def can_launch_model_call(self) -> bool:
        return self.elapsed_seconds < ROLLOUT_CUTOFF_SECONDS


def adjudicate_resource_bounded_gate(
    *,
    coverage_complete: bool,
    invariants_match: bool,
    provenance_matches: bool,
    replay_matches: bool,
    thresholds_pass: bool,
    elapsed_seconds: float,
) -> StopOutcome:
    if not (invariants_match and provenance_matches and replay_matches):
        return StopOutcome.INVALID
    if elapsed_seconds > GATE_DEADLINE_SECONDS or not coverage_complete:
        return StopOutcome.VALID_STOP
    return StopOutcome.PASS if thresholds_pass else StopOutcome.VALID_STOP


def final_checkpoint(checkpoint_paths: Sequence[str | Path]) -> Path:
    """Return only the numerically final checkpoint for rollout evaluation."""

    paths = [Path(path) for path in checkpoint_paths]
    if not paths:
        raise ValueError("checkpoint list must not be empty")
    try:
        return max(paths, key=lambda path: int(path.name.removeprefix("checkpoint-")))
    except ValueError as error:
        raise ValueError("checkpoint names must use checkpoint-<step>") from error


def intermediate_checkpoints(checkpoint_paths: Sequence[str | Path]) -> tuple[Path, ...]:
    selected = final_checkpoint(checkpoint_paths)
    return tuple(path for path in map(Path, checkpoint_paths) if path != selected)


def install_sigint_stop(stop_token: SchedulerStopToken) -> Callable[[], None]:
    """Install a queue-stop SIGINT handler and return a restoration callback."""

    previous = signal.getsignal(signal.SIGINT)

    def handler(_signum: int, _frame: Any) -> None:
        stop_token.request_stop("SIGINT")

    signal.signal(signal.SIGINT, handler)

    def restore() -> None:
        signal.signal(signal.SIGINT, previous)

    return restore


def canonical_receipt_bytes(receipt: PerformanceQualificationReceipt) -> bytes:
    return (
        json.dumps(receipt.to_dict(), allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


__all__ = [
    "BatchedPolicyAdapter",
    "CoverageSelection",
    "DeterministicBatch",
    "DeterministicSearchScheduler",
    "EvaluationTask",
    "GateClock",
    "PerformanceQualificationReceipt",
    "SchedulerResult",
    "SchedulerStopToken",
    "SearchEpisodeSession",
    "adjudicate_resource_bounded_gate",
    "balanced_fallback_panel",
    "build_performance_receipt",
    "canonical_receipt_bytes",
    "cost_balanced_task_shards",
    "evaluation_tasks_from_manifests",
    "final_checkpoint",
    "form_deterministic_batches",
    "install_sigint_stop",
    "intermediate_checkpoints",
    "lower_95_throughput_bound",
    "select_certified_coverage",
]
