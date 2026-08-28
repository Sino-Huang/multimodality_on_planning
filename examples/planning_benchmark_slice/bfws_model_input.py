"""Shared bounded model input for BFWS corpus and live evaluation."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from .search_trace import _serialize_evaluation, _serialize_operation, _serialize_transition


def build_bounded_bfws_model_input(
    *,
    observation: Mapping[str, Any],
    checkpoint: Any,
    accepted_deltas: tuple[Any, ...],
    max_bytes: int,
    max_input_tokens: int | None = None,
    token_counter: Callable[[Mapping[str, Any]], int] | None = None,
) -> tuple[dict[str, Any], int]:
    """Project one trusted BFWS decision into the frozen observable schema."""

    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("BFWS model input byte preference must be a positive integer")
    if (max_input_tokens is None) != (token_counter is None):
        raise ValueError("BFWS token budget and token counter must be supplied together")
    if max_input_tokens is not None and (
        isinstance(max_input_tokens, bool) or not isinstance(max_input_tokens, int) or max_input_tokens <= 0
    ):
        raise ValueError("BFWS model input token budget must be a positive integer")
    if observation.get("algorithm") != "best_first_width":
        raise ValueError("BFWS observation has the wrong algorithm")

    observed_memory = observation.get("search_memory")
    if not isinstance(observed_memory, Mapping):
        raise ValueError("BFWS observation Search Memory must be an object")
    candidates = observation.get("successor_candidates")
    if not isinstance(candidates, list) or not all(isinstance(item, Mapping) for item in candidates):
        raise ValueError("BFWS observation candidates must be objects")
    snapshot = checkpoint.snapshot
    expected_head = snapshot.frontier[0] if snapshot.frontier else None
    if (
        observed_memory.get("frontier_head") != expected_head
        or observed_memory.get("frontier_size") != len(snapshot.frontier)
        or observed_memory.get("known_state_count") != len(snapshot.known_states)
        or observed_memory.get("visited_count") != len(snapshot.visited)
    ):
        raise ValueError("BFWS observation differs from trusted Search Memory")

    compact_deltas = [_compact_delta(delta) for delta in accepted_deltas]
    original_delta_count = len(compact_deltas)
    while True:
        model_input = {
            "observation": {
                "algorithm": observation["algorithm"],
                "expanded_state": observation["expanded_state"],
                "high_novelty_policy": observation["high_novelty_policy"],
                "novelty_precision": observation["novelty_precision"],
                "successor_candidates": candidates,
            },
            "search_memory": {
                **dict(observed_memory),
                "accepted_deltas": compact_deltas,
                "authority_id": checkpoint.authority_id,
                "context_type": "bounded_bfws_search_memory",
                "schema_version": 1,
            },
            "task_context": observation["task_context"],
        }
        if len(_canonical_json_bytes(model_input)) > max_bytes and compact_deltas:
            compact_deltas.pop(0)
            continue
        input_tokens = token_counter(model_input) if token_counter is not None else None
        if input_tokens is None:
            return model_input, original_delta_count - len(compact_deltas)
        assert max_input_tokens is not None
        if input_tokens <= max_input_tokens:
            return model_input, original_delta_count - len(compact_deltas)
        if not compact_deltas:
            raise ValueError(
                f"BFWS required model input uses {input_tokens} tokens, exceeding the {max_input_tokens}-token budget"
            )
        compact_deltas.pop(0)


def validate_bfws_teacher_operation(
    observation: Mapping[str, Any],
    operation: Mapping[str, Any],
) -> None:
    """Require the operation implied by the exact observable candidate facts."""

    expanded = observation.get("expanded_state")
    candidates = observation.get("successor_candidates")
    if not isinstance(expanded, Mapping) or not isinstance(candidates, list):
        raise ValueError("BFWS model observation is malformed")
    expected = next(
        (
            candidate
            for candidate in candidates
            if isinstance(candidate, Mapping) and candidate.get("duplicate") is False
        ),
        None,
    )
    source_state_id = expanded.get("state_id")
    if expected is None:
        if operation != {"operation_type": "retire_frontier", "state_id": source_state_id}:
            raise ValueError("BFWS teacher did not retire an exhausted frontier head")
        return

    evaluation = expected.get("evaluation")
    if not isinstance(evaluation, Mapping):
        raise ValueError("BFWS next candidate lacks its exact evaluation")
    if (
        operation.get("source_state_id") != source_state_id
        or operation.get("action") != expected.get("grounded_action")
        or operation.get("frontier_intent") != evaluation.get("frontier_intent")
        or operation.get("visit_target") is not True
        or operation.get("evaluate_target") is not True
    ):
        raise ValueError("BFWS teacher operation differs from the first nonduplicate candidate")


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
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


__all__ = ["build_bounded_bfws_model_input", "validate_bfws_teacher_operation"]
