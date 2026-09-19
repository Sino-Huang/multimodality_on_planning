"""Shared bounded model-input projection for BFS process supervision and evaluation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Callable

from .pddl_state import PDDLStateAuthority
from .search_trace import _serialize_evaluation, _serialize_operation, _serialize_transition


def build_bounded_bfs_model_input(
    *,
    goal_atoms: list[str],
    observation: Mapping[str, Any],
    checkpoint: Any,
    accepted_deltas: tuple[Any, ...],
    max_bytes: int,
) -> tuple[dict[str, Any], int]:
    """Project trusted BFS state into the bounded schema used for process SFT."""

    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("BFS model input byte budget must be a positive integer")
    frontier = observation.get("frontier")
    if not isinstance(frontier, list) or not all(isinstance(state_id, str) for state_id in frontier):
        raise ValueError("BFS observation frontier must be an array of state IDs")
    snapshot = checkpoint.snapshot
    if tuple(frontier) != tuple(snapshot.frontier):
        raise ValueError("BFS observation frontier differs from trusted search memory")
    bounded_observation = {
        "frontier_head": frontier[0] if frontier else None,
        "frontier_size": len(frontier),
        "modality": observation.get("modality"),
        "state_atoms": observation.get("state_atoms"),
        "state_id": observation.get("state_id"),
    }
    compact_deltas = [_compact_delta(delta) for delta in accepted_deltas]
    original_delta_count = len(compact_deltas)
    while True:
        search_memory = {
            "accepted_deltas": compact_deltas,
            "authority_id": checkpoint.authority_id,
            "context_type": "bounded_bfs_search_memory",
            "frontier_head": snapshot.frontier[0] if snapshot.frontier else None,
            "frontier_size": len(snapshot.frontier),
            "known_state_count": len(snapshot.known_states),
            "provenance_count": len(snapshot.provenance),
            "schema_version": 3,
            "visited_count": len(snapshot.visited),
        }
        model_input = {
            "goal_atoms": goal_atoms,
            "observation": bounded_observation,
            "search_memory": search_memory,
        }
        if len(_canonical_json_bytes(model_input)) <= max_bytes:
            return model_input, original_delta_count - len(compact_deltas)
        if not compact_deltas:
            raise ValueError("BFS model input cannot fit the frozen byte budget")
        compact_deltas.pop(0)


def build_bounded_bfs_model_input_v4(
    *,
    authority: PDDLStateAuthority,
    goal_atoms: list[str],
    observation: Mapping[str, Any],
    checkpoint: Any,
    accepted_deltas: tuple[Any, ...],
    max_bytes: int,
    max_input_tokens: int | None = None,
    token_counter: Callable[[Mapping[str, Any]], int] | None = None,
) -> tuple[dict[str, Any], int]:
    """Project observable BFS state with exact successor membership.

    The byte boundary remains a compaction preference. Required task and
    successor fields are never removed; a pinned token counter is authoritative
    when supplied.
    """

    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("BFS model input byte budget must be a positive integer")
    if (max_input_tokens is None) != (token_counter is None):
        raise ValueError("BFS token budget and token counter must be supplied together")
    if max_input_tokens is not None and (
        isinstance(max_input_tokens, bool) or not isinstance(max_input_tokens, int) or max_input_tokens <= 0
    ):
        raise ValueError("BFS model input token budget must be a positive integer")

    frontier = observation.get("frontier")
    if not isinstance(frontier, list) or not all(isinstance(state_id, str) for state_id in frontier):
        raise ValueError("BFS observation frontier must be an array of state IDs")
    snapshot = checkpoint.snapshot
    if tuple(frontier) != tuple(snapshot.frontier):
        raise ValueError("BFS observation frontier differs from trusted search memory")
    state_id = observation.get("state_id")
    if not isinstance(state_id, str) or state_id not in snapshot.known_states:
        raise ValueError("BFS observation state is absent from trusted search memory")
    state = snapshot.known_states[state_id]
    candidates = [
        {
            "grounded_action": {"args": list(action.args), "name": action.name},
            "target_state_id": preview.target_state.state_id,
            "visited": preview.target_state.state_id in snapshot.visited,
        }
        for action in authority.applicable_actions(state)
        for preview in (authority.preview_apply(state, action),)
    ]
    bounded_observation = {
        "frontier_head": frontier[0] if frontier else None,
        "frontier_size": len(frontier),
        "modality": observation.get("modality"),
        "state_atoms": observation.get("state_atoms"),
        "state_id": state_id,
    }
    compact_deltas = [_compact_delta(delta) for delta in accepted_deltas]
    original_delta_count = len(compact_deltas)
    while True:
        model_input = {
            "goal_atoms": goal_atoms,
            "observation": bounded_observation,
            "search_memory": {
                "accepted_deltas": compact_deltas,
                "authority_id": checkpoint.authority_id,
                "context_type": "bounded_bfs_search_memory",
                "frontier_head": snapshot.frontier[0] if snapshot.frontier else None,
                "frontier_size": len(snapshot.frontier),
                "known_state_count": len(snapshot.known_states),
                "provenance_count": len(snapshot.provenance),
                "schema_version": 4,
                "successor_candidates": candidates,
                "visited_count": len(snapshot.visited),
            },
            "task_context": authority.task_context(),
        }
        if len(_canonical_json_bytes(model_input)) > max_bytes and compact_deltas:
            compact_deltas.pop(0)
            continue
        input_tokens = token_counter(model_input) if token_counter is not None else None
        fits_tokens = input_tokens is None or input_tokens <= max_input_tokens
        if fits_tokens:
            return model_input, original_delta_count - len(compact_deltas)
        if not compact_deltas:
            raise ValueError(
                f"BFS required model input uses {input_tokens} tokens, exceeding the {max_input_tokens}-token budget"
            )
        compact_deltas.pop(0)


def _compact_delta(delta: Any) -> dict[str, Any]:
    transition = _serialize_transition(delta.transition)
    return {
        "evaluation": _serialize_evaluation(delta.evaluation),
        "operation": _serialize_operation(delta.operation),
        "record_index": delta.record_index,
        "transition": {
            "action": transition["action"],
            "source_state_id": transition["source_state"]["state_id"],
            "target_state_id": transition["target_state"]["state_id"],
        },
    }


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


__all__ = ["build_bounded_bfs_model_input", "build_bounded_bfs_model_input_v4"]
