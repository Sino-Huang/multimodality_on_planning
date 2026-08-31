"""Exact-reference A* h_max episode execution over the shared controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .astar_controller import AStarController, AStarOperation
from .astar_hmax import HMaxHeuristic
from .astar_landmarks import LandmarkCountHeuristic
from .astar_model_input import build_astar_live_model_input
from .pddl_state import CanonicalState, PDDLStateAuthority

ASTAR_ACCEPTED_DELTA_LIMIT = 16


@dataclass(frozen=True, slots=True)
class AStarSearchSummary:
    controller: AStarController
    events: tuple[dict[str, Any], ...]
    expansion_count: int
    goal_reached: bool
    termination: str

    @property
    def decision_count(self) -> int:
        return self.controller.decision_count

    @property
    def states(self) -> tuple[CanonicalState, ...]:
        return tuple(self.controller.states[state_id] for state_id in sorted(self.controller.states))


def run_astar_hmax(
    authority: PDDLStateAuthority,
    *,
    max_expansions: int,
    accepted_delta_limit: int = ASTAR_ACCEPTED_DELTA_LIMIT,
) -> AStarSearchSummary:
    """Run exact A*; generated goals terminate only when they become frontier head."""

    return _run_astar_exact(
        authority,
        HMaxHeuristic(authority),
        max_expansions=max_expansions,
        accepted_delta_limit=accepted_delta_limit,
    )


def run_astar_landmark_count(
    authority: PDDLStateAuthority,
    *,
    max_expansions: int,
    accepted_delta_limit: int = ASTAR_ACCEPTED_DELTA_LIMIT,
) -> AStarSearchSummary:
    return _run_astar_exact(
        authority,
        LandmarkCountHeuristic(authority),
        max_expansions=max_expansions,
        accepted_delta_limit=accepted_delta_limit,
    )


def _run_astar_exact(
    authority: PDDLStateAuthority,
    heuristic: object,
    *,
    max_expansions: int,
    accepted_delta_limit: int,
) -> AStarSearchSummary:
    controller = AStarController(
        authority,
        heuristic,
        accepted_delta_limit=accepted_delta_limit,
        max_budget=max_expansions,
    )
    events: list[dict[str, Any]] = []
    expansion_count = 0
    termination = "frontier_exhausted"
    goal_reached = False

    while expansion_count < max_expansions:
        state_id = controller.frontier_head_state_id()
        if state_id is None:
            termination = "frontier_exhausted"
            break
        state = controller.node_state(state_id)
        if authority.is_goal(state):
            termination = "goal_reached"
            goal_reached = True
            break

        observation = build_astar_live_model_input(authority, controller)
        frontier_before = controller.frontier_snapshot()
        controller.start_expansion()
        decisions: list[dict[str, Any]] = []
        for candidate in controller.current_candidates():
            operation = AStarOperation(state_id, candidate.action)
            raw_output = _canonical_operation(operation)
            model_input = build_astar_live_model_input(authority, controller)
            result = controller.apply_operation(operation, raw_output=raw_output)
            if not result.accepted:
                raise AssertionError("the exact A* reference emitted an invalid operation")
            decisions.append(
                {
                    "input": model_input,
                    "operation": operation.to_dict(),
                    "raw_model_output": result.raw_output,
                    "trusted_runtime_result": dict(result.runtime_result),
                }
            )
        controller.finish_expansion()
        if controller.expansion_count != expansion_count + 1 or controller.budget_used != expansion_count + 1:
            raise AssertionError("exact A* expansion charging differs from its frozen budget")
        events.append(
            {
                "decisions": decisions,
                "expanded_state_id": state_id,
                "expansion_index": expansion_count,
                "frontier_after": controller.frontier_snapshot(),
                "frontier_before": frontier_before,
                "heuristic": {
                    "f": observation["current"]["f"],
                    "g": observation["current"]["g"],
                    "name": controller.heuristic_name,
                    "value": observation["current"]["h"],
                },
                "index": len(events),
                "invariants": {
                    "best_g_bookkeeping": True,
                    "frontier_head_expanded": True,
                    "hold": True,
                    "priority": ["f", "generation_serial"],
                    "reopen_on_cheaper_path": True,
                },
                "observation": observation,
            }
        )
        expansion_count += 1
    else:
        termination = "expansion_budget"

    return AStarSearchSummary(
        controller=controller,
        events=tuple(events),
        expansion_count=expansion_count,
        goal_reached=goal_reached,
        termination=termination,
    )


def _canonical_operation(operation: AStarOperation) -> str:
    import json

    return json.dumps(operation.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


__all__ = [
    "ASTAR_ACCEPTED_DELTA_LIMIT",
    "AStarSearchSummary",
    "run_astar_hmax",
    "run_astar_landmark_count",
]
