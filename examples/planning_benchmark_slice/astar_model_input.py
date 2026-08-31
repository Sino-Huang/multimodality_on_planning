"""Canonical teacher/live A* model input and chat-message builders."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .astar_controller import AStarController
from .pddl_state import PDDLStateAuthority

_SYSTEM_MESSAGE = (
    "Emit exactly one A* typed operation. The trusted runtime owns the declared heuristic, "
    "best-g, closed/frontier bookkeeping, progression, and all state transitions."
)


def build_astar_model_input(
    authority: PDDLStateAuthority,
    controller: AStarController,
) -> dict[str, Any]:
    state_id = controller.active_state_id or controller.frontier_head_state_id()
    if state_id is None:
        raise ValueError("cannot build A* model input after frontier exhaustion")
    state = controller.node_state(state_id)
    progress = controller.node_progress(state_id)
    g = controller.best_g[state_id]
    candidates = controller.current_candidates()
    h = controller.heuristic.value(state, progress)
    model_input: dict[str, Any] = {
        "accepted_deltas": controller.accepted_deltas(),
        "algorithm": controller.algorithm,
        "current": {
            "f": g + h,
            "g": g,
            "h": h,
            "state_atoms": list(state.atoms),
            "state_id": state_id,
        },
        "search_memory": {
            "best_cost_count": len(controller.best_g),
            "closed_count": len(controller.closed_g),
            "frontier_count": len(controller.frontier_snapshot()),
            "frontier_head": controller.frontier_snapshot()[0] if controller.frontier_snapshot() else None,
            "visited_count": controller.visited_count,
        },
        "successor_candidates": [candidate.to_dict() for candidate in candidates],
        "task_context": authority.task_context(),
    }
    heuristic_context = controller.heuristic.task_payload()
    progression = controller.heuristic.progress_payload(state, progress)
    if heuristic_context or progression:
        model_input["heuristic_context"] = dict(heuristic_context)
        model_input["current"].update(
            {
                "node_id": state_id,
                "progression": dict(progression),
                "state_id": state.state_id,
            }
        )
    return model_input


def build_astar_teacher_model_input(
    authority: PDDLStateAuthority,
    controller: AStarController,
) -> dict[str, Any]:
    return build_astar_model_input(authority, controller)


def build_astar_live_model_input(
    authority: PDDLStateAuthority,
    controller: AStarController,
) -> dict[str, Any]:
    return build_astar_model_input(authority, controller)


def build_astar_live_chat_messages(model_input: Mapping[str, Any]) -> list[dict[str, str]]:
    return _message_prefix(model_input)


def build_astar_teacher_chat_messages(
    model_input: Mapping[str, Any],
    expected_output: str,
) -> list[dict[str, str]]:
    if not isinstance(expected_output, str):
        raise TypeError("expected_output must be text")
    return [*_message_prefix(model_input), {"content": expected_output, "role": "assistant"}]


def _message_prefix(model_input: Mapping[str, Any]) -> list[dict[str, str]]:
    content = json.dumps(dict(model_input), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return [
        {"content": _SYSTEM_MESSAGE, "role": "system"},
        {"content": content, "role": "user"},
    ]


__all__ = [
    "build_astar_live_chat_messages",
    "build_astar_live_model_input",
    "build_astar_model_input",
    "build_astar_teacher_chat_messages",
    "build_astar_teacher_model_input",
]
