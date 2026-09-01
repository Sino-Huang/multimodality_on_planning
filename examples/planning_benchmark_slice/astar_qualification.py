"""Eventless exact A* qualification over the fixed paired-task panel."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass

from .astar_controller import AStarController, AStarOperation
from .astar_episode import ASTAR_ACCEPTED_DELTA_LIMIT
from .astar_hmax import HMaxHeuristic
from .astar_landmarks import LandmarkCountHeuristic
from .pddl_state import PDDLStateAuthority

ASTAR_QUALIFICATION_ADAPTERS = ("astar_hmax", "astar_landmark_count")


@dataclass(frozen=True, slots=True)
class AStarQualificationResult:
    adapter: str
    composite_node_count: int
    decision_count: int
    expansion_count: int
    reopen_count: int
    runtime_seconds: float
    solution_cost: int | None
    termination: str
    world_state_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_astar_qualification(
    authority: PDDLStateAuthority,
    adapter: str,
    *,
    progress: Callable[[dict[str, object]], None] | None = None,
    progress_interval_seconds: float = 10.0,
) -> AStarQualificationResult:
    """Run exact A* without retaining per-decision or per-expansion evidence."""

    if adapter not in ASTAR_QUALIFICATION_ADAPTERS:
        raise ValueError(f"unsupported A* qualification adapter: {adapter}")
    started = time.monotonic()
    heuristic = HMaxHeuristic(authority) if adapter == "astar_hmax" else LandmarkCountHeuristic(authority)
    controller = AStarController(
        authority,
        heuristic,
        accepted_delta_limit=ASTAR_ACCEPTED_DELTA_LIMIT,
        retain_decision_evidence=False,
    )
    last_progress = started
    solution_cost: int | None = None

    while True:
        node_id = controller.frontier_head_state_id()
        if node_id is None:
            termination = "frontier_exhausted"
            break
        if authority.is_goal(controller.node_state(node_id)):
            termination = "goal_reached"
            solution_cost = controller.best_g[node_id]
            break

        controller.start_expansion()
        for candidate in controller.expansion_candidates():
            result = controller.apply_operation(AStarOperation(node_id, candidate.action))
            if not result.accepted:
                raise AssertionError("exact A* qualification emitted an invalid operation")
        controller.finish_expansion()

        now = time.monotonic()
        if progress is not None and now - last_progress >= progress_interval_seconds:
            progress(
                {
                    "composite_node_count": controller.visited_count,
                    "decision_count": controller.decision_count,
                    "expansion_count": controller.expansion_count,
                    "reopen_count": controller.reopen_count,
                    "runtime_seconds": round(now - started, 6),
                    "world_state_count": len(controller.states),
                }
            )
            last_progress = now

    return AStarQualificationResult(
        adapter=adapter,
        composite_node_count=controller.visited_count,
        decision_count=controller.decision_count,
        expansion_count=controller.expansion_count,
        reopen_count=controller.reopen_count,
        runtime_seconds=round(time.monotonic() - started, 6),
        solution_cost=solution_cost,
        termination=termination,
        world_state_count=len(controller.states),
    )


__all__ = [
    "ASTAR_QUALIFICATION_ADAPTERS",
    "AStarQualificationResult",
    "run_astar_qualification",
]
