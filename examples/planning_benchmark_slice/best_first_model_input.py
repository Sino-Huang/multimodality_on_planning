"""Canonical teacher/live text input for additive best-first search."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .best_first_controller import BestFirstController
from .pddl_state import PDDLStateAuthority

_SYSTEM_MESSAGE = (
    "Emit exactly one typed best-first successor operation. The trusted runtime owns "
    "h_add, scalar priority, duplicate detection, the frontier, and state transitions."
)


def build_best_first_model_input(
    authority: PDDLStateAuthority,
    controller: BestFirstController,
) -> dict[str, Any]:
    node_id = controller.active_state_id
    state_ref = controller.active_state_ref
    if node_id is None or state_ref is None:
        raise ValueError("best-first model input requires an active expansion")
    state = controller.node_state(node_id)
    g = controller.best_g[node_id]
    h = controller.heuristic(state)
    return {
        "accepted_deltas": controller.accepted_deltas(),
        "algorithm": controller.algorithm,
        "current": {
            "g": g,
            "h": h,
            "priority": controller.setting.priority(g, h),
            "state_atoms": list(state.atoms),
            "state_id": state_ref,
        },
        "search_memory": {
            "best_cost_count": len(controller.best_g),
            "closed_count": len(controller.closed_g),
            "frontier_count": controller.frontier_count,
            "frontier_head": controller.frontier_head(),
            "visited_count": controller.visited_count,
        },
        "successor_candidates": [candidate.to_dict() for candidate in controller.current_candidates()],
        "task_context": authority.task_context(),
    }


def build_best_first_teacher_model_input(
    authority: PDDLStateAuthority,
    controller: BestFirstController,
) -> dict[str, Any]:
    return build_best_first_model_input(authority, controller)


def build_best_first_live_model_input(
    authority: PDDLStateAuthority,
    controller: BestFirstController,
) -> dict[str, Any]:
    return build_best_first_model_input(authority, controller)


def serialize_best_first_message_prefix(
    model_input: Mapping[str, Any],
) -> list[dict[str, str]]:
    return [
        {"content": _SYSTEM_MESSAGE, "role": "system"},
        {
            "content": json.dumps(
                dict(model_input),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ),
            "role": "user",
        },
    ]


__all__ = [
    "build_best_first_live_model_input",
    "build_best_first_model_input",
    "build_best_first_teacher_model_input",
    "serialize_best_first_message_prefix",
]
