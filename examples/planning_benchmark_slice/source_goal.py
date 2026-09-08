"""Source PDDL goals, before normalization introduces execution auxiliaries."""

from __future__ import annotations

import json
from itertools import product
from typing import Any

from plado.parser import LookaheadStreamer, parse_domain, parse_problem, tokenize

from .pddl_state import _canonical_formula, _canonical_term, _compile_either_parameter_types


def source_task(domain_text: str, problem_text: str) -> dict[str, Any]:
    # Plado cannot parse action-parameter (either ...) types in collected domains.
    # The existing compatibility projection changes only those parameter types;
    # the original problem goal is parsed separately, without normalization.
    domain = parse_domain(LookaheadStreamer(tokenize(_compile_either_parameter_types(domain_text))))
    problem = parse_problem(LookaheadStreamer(tokenize(problem_text)))
    # Quantifier parameter pairs from the execution serializer are tuples.
    # Expose the JSON representation used by persisted source-goal manifests.
    goal = json.loads(json.dumps(_canonical_formula(problem.goal)))
    validate_goal(goal)
    parents = {item.name: item.parent_type_name for item in domain.types}
    objects: dict[str, list[str]] = {}
    for item in (*domain.constants, *problem.objects):
        objects.setdefault(item.type_name, []).append(item.name)
    return {
        "source_goal": goal,
        "objects_by_type": {k: sorted(v) for k, v in sorted(objects.items())},
        "type_parents": parents,
    }


def validate_goal(goal: Any, scope: frozenset[str] = frozenset()) -> None:
    op = goal[0]
    if op == "atom":
        if goal[1].startswith("@"):
            raise ValueError("compiler auxiliary is not a source goal")
        if any(arg.startswith("?") and arg not in scope for arg in goal[2]):
            raise ValueError("unbound source-goal variable")
    elif op in ("and", "or"):
        for child in goal[1]:
            validate_goal(child, scope)
    elif op == "not":
        validate_goal(goal[1], scope)
    elif op in ("forall", "exists"):
        names = [name for name, _ in goal[1]]
        if len(names) != len(set(names)):
            raise ValueError("duplicate quantified variable")
        validate_goal(goal[2], scope | frozenset(names))
    elif op not in ("true", "false"):
        raise ValueError(f"unsupported source-goal expression: {goal}")


def evaluate_goal(goal: Any, facts: set[str], source: dict[str, Any]) -> bool:
    """Evaluate source constraints with lexical scope and inherited PDDL types."""
    validate_goal(goal)
    domains: dict[str, set[str]] = {"object": set()}
    for kind, names in source["objects_by_type"].items():
        domains["object"].update(names)
        while kind != "object":
            domains.setdefault(kind, set()).update(names)
            kind = source["type_parents"].get(kind) or "object"

    def visit(node, bindings):
        op = node[0]
        if op == "atom":
            args = tuple(bindings.get(arg, arg) for arg in node[2])
            if node[1] == "=":
                return len(args) == 2 and args[0] == args[1]
            return _canonical_term(node[1], args) in facts
        if op == "not":
            return not visit(node[1], bindings)
        if op in ("and", "or"):
            values = (visit(child, bindings) for child in node[1])
            return all(values) if op == "and" else any(values)
        if op in ("forall", "exists"):
            names = [name for name, _ in node[1]]
            choices = product(*(sorted(domains.get(kind, ())) for _, kind in node[1]))
            values = (visit(node[2], {**bindings, **dict(zip(names, choice, strict=True))}) for choice in choices)
            return all(values) if op == "forall" else any(values)
        return op == "true"

    return visit(goal, {})


def goal_blocks(goal: Any) -> list[dict[str, str]]:
    """Explicit parent IDs preserve scope across full-width continuation pages."""
    validate_goal(goal)
    blocks = []
    labels = {"and": "ALL", "or": "ANY", "not": "NOT", "forall": "FOR EVERY", "exists": "THERE EXISTS"}

    def visit(node, identity, parent):
        op = node[0]
        label = labels.get(op, op.upper())
        text = ""
        if op == "atom":
            text = _canonical_term(node[1], tuple(node[2]))
        elif op in ("forall", "exists"):
            text = "; ".join(f"{name} : {kind}" for name, kind in node[1])
        elif op in ("and", "or") and not node[1]:
            text = "TRUE (empty ALL)" if op == "and" else "FALSE (empty ANY)"
        blocks.append({"id": identity, "label": f"{identity} {label} (in {parent})", "text": text})
        children = node[1] if op in ("and", "or") else [node[-1]] if op in ("not", "forall", "exists") else []
        for index, child in enumerate(children, 1):
            visit(child, f"{identity}.{index}", identity)

    visit(goal, "G", "ROOT")
    return blocks
