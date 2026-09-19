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


def build_compact_best_first_model_input(
    authority: PDDLStateAuthority,
    controller: BestFirstController,
) -> dict[str, Any]:
    """Losslessly factor repeated facts and record keys for the v2 corpus/live input."""

    legacy = build_best_first_model_input(authority, controller)
    current = dict(legacy["current"])
    current["state_facts"] = compact_best_first_facts(current.pop("state_atoms"))
    task = legacy["task_context"]
    return {
        "accepted_deltas": _compact_table(
            legacy["accepted_deltas"],
            (
                "action",
                "g",
                "h",
                "priority",
                "source_state_id",
                "status",
                "target_state_id",
            ),
        ),
        "algorithm": legacy["algorithm"],
        "current": current,
        "schema_version": "best_first_compact_model_input_v2",
        "search_memory": legacy["search_memory"],
        "successor_candidates": _compact_table(
            legacy["successor_candidates"],
            (
                "action",
                "best_cost",
                "closed",
                "dominated",
                "frontier",
                "g",
                "h",
                "priority",
                "pruned",
                "target_state_id",
            ),
        ),
        "task_context": {
            "goal_facts": compact_best_first_facts(authority.goal_atoms or ()),
            "initial_dynamic_facts": compact_best_first_facts(task["initial_dynamic_atoms"]),
            "initial_dynamic_fluents": task["initial_dynamic_fluents"],
            "static_facts": compact_best_first_facts(task["static_initial_facts"]),
        },
    }


def build_compact_best_first_teacher_model_input(
    authority: PDDLStateAuthority,
    controller: BestFirstController,
) -> dict[str, Any]:
    return build_compact_best_first_model_input(authority, controller)


def build_compact_best_first_live_model_input(
    authority: PDDLStateAuthority,
    controller: BestFirstController,
) -> dict[str, Any]:
    return build_compact_best_first_model_input(authority, controller)


def compact_best_first_facts(facts: Any) -> dict[str, Any]:
    parsed: dict[str, list[tuple[str, ...]]] = {}
    for fact in facts:
        name, separator, tail = str(fact).partition("(")
        if not separator:
            parsed.setdefault(name, []).append(())
            continue
        if not tail.endswith(")"):
            raise ValueError(f"best-first canonical fact is malformed: {fact}")
        arguments = tuple(tail[:-1].split(",")) if tail[:-1] else ()
        parsed.setdefault(name, []).append(arguments)

    arguments = sorted({argument for rows in parsed.values() for row in rows for argument in row})
    argument_index = {argument: index for index, argument in enumerate(arguments)}
    unary_by_arguments: dict[tuple[int, ...], list[str]] = {}
    binary: dict[str, list[list[Any]]] = {}
    nary: dict[str, list[list[int]]] = {}
    zero_arity: list[str] = []
    for predicate, rows in parsed.items():
        arities = {len(row) for row in rows}
        if len(arities) != 1:
            raise ValueError(f"best-first predicate has inconsistent arity: {predicate}")
        arity = next(iter(arities))
        if arity == 0:
            zero_arity.append(predicate)
        elif arity == 1:
            indexes = tuple(argument_index[row[0]] for row in rows)
            unary_by_arguments.setdefault(indexes, []).append(predicate)
        elif arity == 2:
            by_first: dict[int, list[int]] = {}
            for first, second in rows:
                by_first.setdefault(argument_index[first], []).append(argument_index[second])
            binary[predicate] = [[first, seconds] for first, seconds in sorted(by_first.items())]
        else:
            nary[predicate] = [[argument_index[argument] for argument in row] for row in rows]
    unary_groups = [
        {"arguments": list(arguments), "predicates": sorted(predicates)}
        for arguments, predicates in sorted(unary_by_arguments.items())
    ]
    return {
        "arguments": arguments,
        "binary_by_first": binary,
        "nary": nary,
        "unary_groups": unary_groups,
        "zero_arity": sorted(zero_arity),
    }


def expand_compact_best_first_facts(compact: Mapping[str, Any]) -> list[str]:
    arguments = compact["arguments"]
    facts = list(compact["zero_arity"])
    for group in compact["unary_groups"]:
        facts.extend(
            f"{predicate}({arguments[index]})" for predicate in group["predicates"] for index in group["arguments"]
        )
    for predicate, rows in compact["binary_by_first"].items():
        facts.extend(
            f"{predicate}({arguments[first]},{arguments[second]})" for first, seconds in rows for second in seconds
        )
    for predicate, rows in compact["nary"].items():
        facts.extend(f"{predicate}({','.join(arguments[index] for index in row)})" for row in rows)
    return sorted(facts)


def _compact_table(rows: Any, columns: tuple[str, ...]) -> dict[str, Any]:
    return {
        "columns": list(columns),
        "rows": [
            [
                ([value["name"], *value["args"]] if column == "action" and isinstance(value, Mapping) else value)
                for column in columns
                for value in (row[column],)
            ]
            for row in rows
        ],
    }


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


def best_first_policy_messages(model_input: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Render the same best-first prefix for live Qwen inference."""

    return [
        {
            "role": message["role"],
            "content": [{"type": "text", "text": message["content"]}],
        }
        for message in serialize_best_first_message_prefix(model_input)
    ]


__all__ = [
    "best_first_policy_messages",
    "build_best_first_live_model_input",
    "build_best_first_model_input",
    "build_best_first_teacher_model_input",
    "build_compact_best_first_live_model_input",
    "build_compact_best_first_model_input",
    "build_compact_best_first_teacher_model_input",
    "compact_best_first_facts",
    "expand_compact_best_first_facts",
    "serialize_best_first_message_prefix",
]
