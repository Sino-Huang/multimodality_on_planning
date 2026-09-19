"""Compact exact-reference episodes for additive best-first search."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Mapping

from .best_first_controller import (
    BEST_FIRST_SETTINGS,
    BestFirstController,
    BestFirstOperation,
)
from .best_first_model_input import build_best_first_teacher_model_input
from .pddl_state import CanonicalState, PDDLStateAuthority

BEST_FIRST_ACCEPTED_DELTA_LIMIT = 16


class BestFirstTraceLimitError(RuntimeError):
    """Raised instead of retaining an expert trace beyond its frozen byte ceiling."""


@dataclass(frozen=True, slots=True)
class BestFirstSearchSummary:
    controller: BestFirstController
    events: tuple[dict[str, Any], ...]
    goal_reached: bool
    states_payload: Mapping[str, Mapping[str, Any]]
    termination: str
    trace_payload: Mapping[str, Any]
    trace_size_bytes: int

    @property
    def decision_count(self) -> int:
        return self.controller.decision_count

    @property
    def expansion_count(self) -> int:
        return self.controller.expansion_count


def run_best_first(
    authority: PDDLStateAuthority,
    *,
    algorithm: str,
    max_expansions: int,
    max_trace_records: int,
    max_trace_bytes: int,
    accepted_delta_limit: int = BEST_FIRST_ACCEPTED_DELTA_LIMIT,
    progress: Callable[[dict[str, object]], None] | None = None,
    progress_interval_seconds: float = 10.0,
) -> BestFirstSearchSummary:
    if algorithm not in BEST_FIRST_SETTINGS:
        raise ValueError(f"unsupported additive best-first algorithm: {algorithm}")
    for value, label in (
        (max_expansions, "max_expansions"),
        (max_trace_records, "max_trace_records"),
        (max_trace_bytes, "max_trace_bytes"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{label} must be a positive integer")
    controller = BestFirstController(
        authority,
        BEST_FIRST_SETTINGS[algorithm],
        accepted_delta_limit=accepted_delta_limit,
        max_budget=max_expansions,
    )
    events: list[dict[str, Any]] = []
    observed_state_refs: dict[str, None] = {}
    termination = "frontier_exhausted"
    goal_reached = False
    started = time.monotonic()
    last_progress = started

    while True:
        state_id = controller.frontier_head_state_id()
        if state_id is None:
            termination = "frontier_exhausted"
            break
        state = controller.node_state(state_id)
        if authority.is_goal(state):
            termination = "goal_reached"
            goal_reached = True
            break
        if controller.expansion_count >= max_expansions:
            termination = "expansion_budget"
            break
        candidate_count = len(authority.applicable_actions(state))
        if controller.decision_count + candidate_count > max_trace_records:
            termination = "trace_record_limit"
            break

        frontier_before = _frontier_summary(controller)
        head_before = frontier_before["head"]
        if not isinstance(head_before, Mapping):
            raise AssertionError("best-first frontier head vanished before expansion")
        source_ref = str(head_before["state_id"])
        observed_state_refs.setdefault(source_ref, None)
        controller.start_expansion()
        decisions: list[dict[str, Any]] = []
        for candidate in controller.current_candidates():
            model_input = build_best_first_teacher_model_input(authority, controller)
            operation = BestFirstOperation(source_ref, candidate.action)
            raw_output = _canonical_text(operation.to_dict())
            result = controller.apply_operation(operation, raw_output=raw_output)
            if not result.accepted:
                raise AssertionError("exact best-first reference emitted an invalid operation")
            decisions.append(
                {
                    "input_sha256": hashlib.sha256(_canonical_bytes(model_input)).hexdigest(),
                    "runtime": {
                        field: result.runtime_result[field]
                        for field in (
                            "best_cost_before",
                            "g",
                            "h",
                            "priority",
                            "status",
                            "target_state_id",
                        )
                    },
                    "target": result.raw_output,
                }
            )
        controller.finish_expansion()
        authority.discard_transient_search_caches()
        events.append(
            {
                "decisions": decisions,
                "expanded_state_id": source_ref,
                "expansion_index": controller.expansion_count - 1,
                "frontier_after": _frontier_summary(controller),
                "frontier_before": frontier_before,
                "index": len(events),
            }
        )
        now = time.monotonic()
        if progress is not None and now - last_progress >= progress_interval_seconds:
            progress(
                {
                    "decision_count": controller.decision_count,
                    "expansion_count": controller.expansion_count,
                    "reopen_count": controller.reopen_count,
                    "runtime_seconds": round(now - started, 6),
                    "visited_count": controller.visited_count,
                }
            )
            last_progress = now

    terminal_head = controller.frontier_head()
    if goal_reached and terminal_head is not None:
        observed_state_refs.setdefault(str(terminal_head["state_id"]), None)
    states = {state_ref: _serialize_state(controller.trace_state(state_ref)) for state_ref in observed_state_refs}
    trace_payload = {
        "algorithm": algorithm,
        "events": events,
        "request": {
            "accepted_delta_limit": accepted_delta_limit,
            "max_decisions": max_trace_records,
            "max_expansions": max_expansions,
            "max_uncompressed_trace_bytes": max_trace_bytes,
        },
        "result": {
            "decision_count": controller.decision_count,
            "expansion_count": controller.expansion_count,
            "goal_reached": goal_reached,
            "reopen_count": controller.reopen_count,
            "solution_cost": (
                controller.best_g[controller.frontier_head_state_id()]
                if goal_reached and controller.frontier_head_state_id() is not None
                else None
            ),
            "termination": termination,
        },
        "schema_version": "best_first_compact_trace_v1",
        "states": states,
    }
    trace_size = len(serialize_best_first_trace(trace_payload))
    if trace_size > max_trace_bytes:
        raise BestFirstTraceLimitError(
            f"compact best-first trace requires {trace_size} bytes; limit is {max_trace_bytes}"
        )
    return BestFirstSearchSummary(
        controller=controller,
        events=tuple(events),
        goal_reached=goal_reached,
        states_payload=states,
        termination=termination,
        trace_payload=trace_payload,
        trace_size_bytes=trace_size,
    )


def _frontier_summary(controller: BestFirstController) -> dict[str, object]:
    return {"count": controller.frontier_count, "head": controller.frontier_head()}


def _serialize_state(state: CanonicalState) -> dict[str, Any]:
    return {
        "atoms": list(state.atoms),
        "fluents": list(state.fluents),
    }


def _canonical_bytes(value: object) -> bytes:
    return _canonical_text(value).encode()


def serialize_best_first_trace(trace: Mapping[str, Any]) -> bytes:
    return _canonical_bytes(trace) + b"\n"


def _canonical_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


__all__ = [
    "BEST_FIRST_ACCEPTED_DELTA_LIMIT",
    "BestFirstSearchSummary",
    "BestFirstTraceLimitError",
    "run_best_first",
    "serialize_best_first_trace",
]
