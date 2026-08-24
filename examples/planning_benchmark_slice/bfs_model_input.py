"""Shared bounded model-input projection for BFS process supervision and evaluation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

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


__all__ = ["build_bounded_bfs_model_input"]
