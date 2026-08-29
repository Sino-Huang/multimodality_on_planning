"""Shared bounded model input for BFWS corpus and live evaluation."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from .search_memory import SearchRetireRequest, SearchTransitionRequest
from .search_trace import _serialize_evaluation, _serialize_operation, _serialize_transition

BFWS_TEXT_POLICY_SYSTEM_PROMPT = """JSON keys canonical_rationale,typed_operation,runtime_result(null).
First nondup copy action/frontier. $=expanded; all dup retire $. Keep residual; no repair."""


def bfws_text_policy_training_messages(
    model_input: Mapping[str, Any],
    target: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build the canonical BFWS text messages shared by audit, corpus, and live use."""

    messages = [
        {"role": "system", "content": BFWS_TEXT_POLICY_SYSTEM_PROMPT},
        {"role": "user", "content": _canonical_json_text(dict(model_input))},
    ]
    if target is not None:
        messages.append({"role": "assistant", "content": _canonical_json_text(dict(target))})
    return messages


def build_bounded_bfws_model_input(
    *,
    observation: Mapping[str, Any],
    checkpoint: Any,
    accepted_deltas: tuple[Any, ...],
    max_bytes: int,
    max_input_tokens: int | None = None,
    token_counter: Callable[[Mapping[str, Any]], int] | None = None,
) -> tuple[dict[str, Any], int]:
    """Project one trusted BFWS decision into the frozen observable schema.

    A nonduplicate candidate target ID of ``$`` denotes the canonical target
    state reconstructed from its lossless atom/fluent delta. Task-context atom
    arguments and type memberships use indices into ``object_symbols``; unary
    integer sets use hexadecimal membership bitsets.
    """

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
    source_candidates = observation.get("successor_candidates")
    if not isinstance(source_candidates, list) or not all(isinstance(item, Mapping) for item in source_candidates):
        raise ValueError("BFWS observation candidates must be objects")
    expanded = observation.get("expanded_state")
    if not isinstance(expanded, Mapping):
        raise ValueError("BFWS expanded state must be an object")
    task_context = _compact_task_context(observation["task_context"])
    symbols = {symbol: index for index, symbol in enumerate(task_context["objects"])}
    candidates = _compact_candidates(source_candidates, expanded, symbols)
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
    projected_memory = {
        "head": "$"
        if observed_memory.get("frontier_head") == expanded.get("state_id")
        else observed_memory.get("frontier_head"),
        "open": observed_memory["frontier_size"],
        "partition_sizes": observed_memory["partition_novelty_cardinalities"],
        "priority": observed_memory["current_priority"],
        "visited": observed_memory["visited_count"],
    }
    original_delta_count = len(compact_deltas)
    while True:
        model_input = {
            "observation": {
                "algorithm": observation["algorithm"],
                "state": {
                    "atoms": _group_atoms(observation["expanded_state"]["atoms"], symbols),
                    "fluents": observation["expanded_state"]["fluents"],
                    "state_id": "$",
                },
                "residual_policy": observation["high_novelty_policy"],
                "novelty_k": observation["novelty_precision"],
                "candidates": candidates,
            },
            "search_memory": {
                **projected_memory,
                "authority": checkpoint.authority_id,
                "context_type": "bounded_bfws_search_memory",
                "deltas": compact_deltas,
                "schema_version": 1,
            },
            "task_context": task_context,
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


def compact_bfws_teacher_operation(
    observation: Mapping[str, Any],
    operation: Mapping[str, Any],
) -> dict[str, Any]:
    """Replace the already-visible expanded state ID with the runtime alias ``$``."""

    validate_bfws_teacher_operation(observation, operation)
    compact = dict(operation)
    if operation.get("operation_type") == "retire_frontier":
        compact["state_id"] = "$"
    else:
        compact["source_state_id"] = "$"
    return compact


def resolve_bfws_model_operation(
    operation: SearchTransitionRequest | SearchRetireRequest,
    observation: Mapping[str, Any],
) -> SearchTransitionRequest | SearchRetireRequest:
    """Resolve the model-facing expanded-state alias through the live observation."""

    expanded = observation["expanded_state"]
    state_id = expanded["state_id"]
    if isinstance(operation, SearchRetireRequest):
        if operation.state_id != "$":
            raise ValueError("BFWS compact retirement target must use the expanded-state alias")
        return SearchRetireRequest(state_id)
    if operation.source_state_id != "$":
        raise ValueError("BFWS compact transition source must use the expanded-state alias")
    return SearchTransitionRequest(
        source_state_id=state_id,
        action=operation.action,
        frontier_intent=operation.frontier_intent,
        visit_target=operation.visit_target,
        evaluate_target=operation.evaluate_target,
    )


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


def _compact_candidates(
    candidates: list[Mapping[str, Any]],
    expanded_state: Mapping[str, Any],
    symbols: Mapping[str, int],
) -> list[dict[str, Any]]:
    expanded_atoms = set(expanded_state.get("atoms", ()))
    expanded_fluents = set(expanded_state.get("fluents", ()))
    compact: list[dict[str, Any]] = []
    for source in candidates:
        candidate = {
            "action": {
                "args": [symbols.get(argument, argument) for argument in source["grounded_action"]["args"]],
                "name": source["grounded_action"]["name"],
            },
            "dup": source["duplicate"],
            "enqueue": source["enqueued"],
        }
        evaluation = source.get("evaluation")
        if isinstance(evaluation, Mapping):
            projected = {
                "frontier": evaluation["frontier_intent"],
                "novel": evaluation["novel_item"],
                "novelty": evaluation["novelty_bucket"],
                "partition": evaluation["partition"],
                "priority": evaluation["priority"],
                "residual": evaluation["residual_novelty"],
            }
            target_atoms = set(evaluation["target_atoms"])
            target_fluents = set(evaluation["target_fluents"])
            candidate["eval"] = projected
        else:
            target_atoms, target_fluents = _decode_state_id(source["target_state_id"])
            candidate["eval"] = None
        atom_delta = _set_delta(expanded_atoms, target_atoms)
        candidate["atoms"] = {
            "added": _group_atoms(atom_delta["added"], symbols),
            "removed": _group_atoms(atom_delta["removed"], symbols),
        }
        candidate["fluents"] = _set_delta(expanded_fluents, target_fluents)
        candidate["target"] = "$"
        compact.append(candidate)
    return compact


def _compact_task_context(value: Any) -> dict[str, Any]:
    context = dict(value)
    object_symbols = list(dict.fromkeys(symbol for values in context["objects_by_type"].values() for symbol in values))
    symbols = {symbol: index for index, symbol in enumerate(object_symbols)}
    context["object_types"] = {
        type_name: [symbols[symbol] for symbol in type_symbols]
        for type_name, type_symbols in context.pop("objects_by_type").items()
    }
    context["object_symbols"] = object_symbols
    context["goal"] = _compact_goal(context.pop("canonical_goal"), symbols)
    context["initial_fluents"] = context.pop("initial_dynamic_fluents")
    context["objects"] = context.pop("object_symbols")
    context["types"] = context.pop("object_types")
    for source, target in (
        ("initial_dynamic_atoms", "initial_atoms"),
        ("static_initial_facts", "static_atoms"),
    ):
        context[target] = _group_atoms(context.pop(source), symbols)
    if _types_match_static_facts(context["types"], context["static_atoms"]):
        context.pop("types")
    return context


def _types_match_static_facts(types: Mapping[str, list[int]], static_atoms: Mapping[str, list[Any]]) -> bool:
    return all(
        static_atoms.get(f"@type-{type_name}@") == [1, f"0x{sum(1 << member for member in members):x}"]
        for type_name, members in types.items()
    )


def _group_atoms(atoms: Any, symbols: Mapping[str, int]) -> dict[str, list[Any]]:
    rows: dict[str, list[list[str | int]]] = {}
    for atom in atoms:
        predicate, separator, arguments = atom.partition("(")
        if not separator:
            rows.setdefault(predicate, []).append([])
            continue
        if not arguments.endswith(")"):
            raise ValueError("BFWS task-context atom is not canonically serialized")
        values = arguments[:-1].split(",") if arguments[:-1] else []
        rows.setdefault(predicate, []).append([symbols.get(argument, argument) for argument in values])
    grouped: dict[str, list[Any]] = {}
    for predicate, predicate_rows in rows.items():
        arity = len(predicate_rows[0])
        if any(len(row) != arity for row in predicate_rows):
            raise ValueError("BFWS task-context predicate has inconsistent arity")
        flattened = [argument for row in predicate_rows for argument in row]
        if arity == 1 and all(isinstance(argument, int) for argument in flattened):
            bitset = sum(1 << int(argument) for argument in flattened)
            grouped[predicate] = [arity, f"0x{bitset:x}"]
        else:
            grouped[predicate] = [arity, flattened]
    return grouped


def _replace_symbols(value: Any, symbols: Mapping[str, int]) -> Any:
    if isinstance(value, str):
        return symbols.get(value, value)
    if isinstance(value, list):
        return [_replace_symbols(item, symbols) for item in value]
    return value


def _compact_goal(value: Any, symbols: Mapping[str, int]) -> Any:
    if (
        isinstance(value, list)
        and len(value) == 2
        and value[0] == "and"
        and isinstance(value[1], list)
        and all(isinstance(item, list) and len(item) == 3 and item[0] == "atom" for item in value[1])
    ):
        grouped: dict[str, list[list[Any]]] = {}
        for _atom, predicate, arguments in value[1]:
            grouped.setdefault(predicate, []).append([_replace_symbols(argument, symbols) for argument in arguments])
        return ["and_atoms", grouped]
    return _replace_symbols(value, symbols)


def _set_delta(source: set[Any], target: set[Any]) -> dict[str, list[Any]]:
    return {
        "added": sorted(target - source),
        "removed": sorted(source - target),
    }


def _decode_state_id(value: Any) -> tuple[set[Any], set[Any]]:
    payload = json.loads(value)
    if isinstance(payload, list):
        return set(payload), set()
    return set(payload["atoms"]), set(payload["fluents"])


def _canonical_json_bytes(value: object) -> bytes:
    return (_canonical_json_text(value) + "\n").encode("utf-8")


def _canonical_json_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


__all__ = [
    "BFWS_TEXT_POLICY_SYSTEM_PROMPT",
    "bfws_text_policy_training_messages",
    "build_bounded_bfws_model_input",
    "compact_bfws_teacher_operation",
    "resolve_bfws_model_operation",
    "validate_bfws_teacher_operation",
]
