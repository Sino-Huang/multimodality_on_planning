"""Eventless bounded qualification for additive best-first search."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass

from .best_first_controller import (
    BEST_FIRST_SETTINGS,
    BestFirstController,
    BestFirstOperation,
)
from .pddl_state import PDDLStateAuthority


@dataclass(frozen=True, slots=True)
class BestFirstQualificationResult:
    algorithm: str
    decision_count: int
    expansion_count: int
    reopen_count: int
    runtime_seconds: float
    solution_cost: int | None
    termination: str
    visited_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_best_first_qualification(
    authority: PDDLStateAuthority,
    algorithm: str,
    *,
    max_expansions: int,
    max_decisions: int,
    progress: Callable[[dict[str, object]], None] | None = None,
    progress_interval_seconds: float = 10.0,
) -> BestFirstQualificationResult:
    if algorithm not in BEST_FIRST_SETTINGS:
        raise ValueError(f"unsupported additive best-first algorithm: {algorithm}")
    for value, label in ((max_expansions, "max_expansions"), (max_decisions, "max_decisions")):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{label} must be a positive integer")
    started = time.monotonic()
    last_progress = started
    controller = BestFirstController(
        authority,
        BEST_FIRST_SETTINGS[algorithm],
        accepted_delta_limit=1,
        max_budget=max_expansions,
        retain_decision_evidence=False,
    )
    solution_cost: int | None = None

    try:
        while True:
            state_id = controller.frontier_head_state_id()
            if state_id is None:
                termination = "frontier_exhausted"
                break
            state = controller.node_state(state_id)
            if authority.is_goal(state):
                termination = "goal_reached"
                solution_cost = controller.best_g[state_id]
                break
            if controller.expansion_count >= max_expansions:
                termination = "expansion_budget"
                break
            if controller.decision_count + len(authority.applicable_actions(state)) > max_decisions:
                termination = "decision_budget"
                break

            controller.start_expansion()
            source_ref = controller.active_state_ref
            if source_ref is None:
                raise AssertionError("best-first qualification lost its active state reference")
            for candidate in controller.current_candidates():
                result = controller.apply_operation(BestFirstOperation(source_ref, candidate.action))
                if not result.accepted:
                    raise AssertionError("exact best-first qualification emitted an invalid operation")
            controller.finish_expansion()
            authority.discard_transient_search_caches()
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
    except MemoryError:
        termination = "memory_limit"

    return BestFirstQualificationResult(
        algorithm=algorithm,
        decision_count=controller.decision_count,
        expansion_count=controller.expansion_count,
        reopen_count=controller.reopen_count,
        runtime_seconds=round(time.monotonic() - started, 6),
        solution_cost=solution_cost,
        termination=termination,
        visited_count=controller.visited_count,
    )


__all__ = ["BestFirstQualificationResult", "run_best_first_qualification"]
