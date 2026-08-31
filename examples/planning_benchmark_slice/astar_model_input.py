"""Canonical teacher/live A* model input and chat-message builders."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
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


def build_bounded_astar_model_input(
    authority: PDDLStateAuthority,
    controller: AStarController,
    *,
    max_bytes: int,
) -> dict[str, Any]:
    """Build bounded search memory by removing only oldest accepted deltas."""

    return project_bounded_astar_model_input(
        build_astar_model_input(authority, controller),
        max_bytes=max_bytes,
    )


def project_bounded_astar_model_input(
    model_input: Mapping[str, Any],
    *,
    max_bytes: int | None = None,
    max_input_tokens: int | None = None,
    token_counter: Callable[[Mapping[str, Any]], int] | None = None,
) -> dict[str, Any]:
    """Apply the frozen drop-oldest-only projection to an exact A* input."""

    if max_bytes is not None and (
        not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0
    ):
        raise ValueError("max_bytes must be a positive integer")
    if max_input_tokens is not None and (
        not isinstance(max_input_tokens, int)
        or isinstance(max_input_tokens, bool)
        or max_input_tokens <= 0
        or token_counter is None
    ):
        raise ValueError("max_input_tokens requires a positive integer and token_counter")
    if max_bytes is None and max_input_tokens is None:
        raise ValueError("at least one A* input bound is required")
    projected = json.loads(json.dumps(dict(model_input), allow_nan=False))
    projected["schema_version"] = "bounded_astar_search_memory_v1"
    for candidate in projected.get("successor_candidates", []):
        if isinstance(candidate, dict) and "target_node_id" not in candidate:
            candidate["target_node_id"] = candidate.get("target_state_id")
    accepted_deltas = projected.get("accepted_deltas")
    if not isinstance(accepted_deltas, list):
        raise ValueError("accepted_deltas must be an array")

    def exceeds() -> bool:
        return (max_bytes is not None and _canonical_size(projected) > max_bytes) or (
            max_input_tokens is not None
            and token_counter is not None
            and token_counter(projected) > max_input_tokens
        )

    while exceeds() and accepted_deltas:
        del accepted_deltas[0]
    if exceeds():
        raise ValueError("required facts alone exceed the A* input bound")
    return projected


def build_astar_teacher_model_input(
    authority: PDDLStateAuthority,
    controller: AStarController,
) -> dict[str, Any]:
    return build_astar_model_input(authority, controller)


def build_bounded_astar_teacher_model_input(
    authority: PDDLStateAuthority,
    controller: AStarController,
    *,
    max_input_tokens: int,
    token_counter: Callable[[Mapping[str, Any]], int],
) -> dict[str, Any]:
    return project_bounded_astar_model_input(
        build_astar_teacher_model_input(authority, controller),
        max_input_tokens=max_input_tokens,
        token_counter=token_counter,
    )


def build_astar_live_model_input(
    authority: PDDLStateAuthority,
    controller: AStarController,
) -> dict[str, Any]:
    return build_astar_model_input(authority, controller)


def build_bounded_astar_live_model_input(
    authority: PDDLStateAuthority,
    controller: AStarController,
    *,
    max_input_tokens: int,
    token_counter: Callable[[Mapping[str, Any]], int],
) -> dict[str, Any]:
    return project_bounded_astar_model_input(
        build_astar_live_model_input(authority, controller),
        max_input_tokens=max_input_tokens,
        token_counter=token_counter,
    )


def build_astar_live_chat_messages(model_input: Mapping[str, Any]) -> list[dict[str, str]]:
    return serialize_astar_message_prefix(model_input)


def build_astar_teacher_chat_messages(
    model_input: Mapping[str, Any],
    expected_output: str,
) -> list[dict[str, str]]:
    if not isinstance(expected_output, str):
        raise TypeError("expected_output must be text")
    return [*serialize_astar_message_prefix(model_input), {"content": expected_output, "role": "assistant"}]


def serialize_astar_message_prefix(model_input: Mapping[str, Any]) -> list[dict[str, str]]:
    """Serialize the canonical teacher/live message prefix."""

    content = json.dumps(dict(model_input), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return [
        {"content": _SYSTEM_MESSAGE, "role": "system"},
        {"content": content, "role": "user"},
    ]


def _canonical_size(value: Mapping[str, Any]) -> int:
    return len(json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())


__all__ = [
    "build_astar_live_chat_messages",
    "build_astar_live_model_input",
    "build_astar_model_input",
    "build_astar_teacher_chat_messages",
    "build_astar_teacher_model_input",
    "build_bounded_astar_live_model_input",
    "build_bounded_astar_model_input",
    "build_bounded_astar_teacher_model_input",
    "project_bounded_astar_model_input",
    "serialize_astar_message_prefix",
]
