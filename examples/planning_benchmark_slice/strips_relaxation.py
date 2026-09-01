"""Grounded positive STRIPS extraction shared by trusted heuristic adapters."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from plado import pddl

from .pddl_state import GroundedAction, PDDLStateAuthority


class UnsupportedSTRIPSTaskError(ValueError):
    """Raised for constructs outside deterministic positive-conjunctive STRIPS."""


@dataclass(frozen=True, slots=True)
class GroundedRelaxedOperator:
    action: GroundedAction
    preconditions: frozenset[str]
    add_effects: frozenset[str]


@dataclass(frozen=True, slots=True)
class GroundedPositiveSTRIPSTask:
    goals: frozenset[str]
    initial_facts: frozenset[str]
    static_facts: frozenset[str]
    operators: tuple[GroundedRelaxedOperator, ...]


def estimated_grounded_operator_count(authority: PDDLStateAuthority) -> int:
    """Return the exact Cartesian grounding count used by this relaxation adapter."""

    object_count = len({item for _, values in authority.objects_by_type for item in values})
    return sum(object_count ** len(action.parameters) for action in authority._domain.actions)


def extract_grounded_positive_strips(authority: PDDLStateAuthority) -> GroundedPositiveSTRIPSTask:
    if authority.goal_atoms is None:
        raise UnsupportedSTRIPSTaskError("positive-conjunctive goals are required")
    domain = authority._domain  # package-internal normalized PDDL authority
    all_objects = tuple(sorted({item for _, values in authority.objects_by_type for item in values}))
    operators: list[GroundedRelaxedOperator] = []
    for action in domain.actions:
        preconditions = _positive_atoms(action.precondition, "action precondition")
        add_effects = _add_effect_atoms(action.effect)
        choices = [all_objects for _parameter in action.parameters]
        if any(not choice for choice in choices):
            continue
        assignments = product(*choices) if choices else ((),)
        for arguments in assignments:
            binding = {
                parameter.name: value
                for parameter, value in zip(action.parameters, arguments, strict=True)
            }
            operators.append(
                GroundedRelaxedOperator(
                    action=GroundedAction(action.name, tuple(arguments)),
                    preconditions=frozenset(_ground_atom(atom, binding) for atom in preconditions),
                    add_effects=frozenset(_ground_atom(atom, binding) for atom in add_effects),
                )
            )
    return GroundedPositiveSTRIPSTask(
        goals=frozenset(authority.goal_atoms),
        initial_facts=frozenset(authority.initial_state.atoms) | frozenset(authority.static_initial_facts),
        static_facts=frozenset(authority.static_initial_facts),
        operators=tuple(sorted(operators, key=lambda item: item.action.serialize())),
    )


def _positive_atoms(expression: pddl.BooleanExpression, label: str) -> tuple[pddl.Atom, ...]:
    if isinstance(expression, pddl.Truth):
        return ()
    if isinstance(expression, pddl.Atom):
        atoms = (expression,)
    elif isinstance(expression, pddl.Conjunction) and all(
        isinstance(child, pddl.Atom) for child in expression.sub_formulas
    ):
        atoms = tuple(child for child in expression.sub_formulas if isinstance(child, pddl.Atom))
    else:
        raise UnsupportedSTRIPSTaskError(f"positive-conjunctive {label} is required")
    if any(atom.name == "=" for atom in atoms):
        raise UnsupportedSTRIPSTaskError("normalized equality preconditions are unsupported")
    return atoms


def _add_effect_atoms(effect: pddl.ActionEffect) -> tuple[pddl.Atom | pddl.AtomEffect, ...]:
    if isinstance(effect, pddl.AtomEffect):
        return (effect,)
    if isinstance(effect, pddl.NegativeEffect):
        return ()
    if isinstance(effect, pddl.ConjunctiveEffect):
        atoms: list[pddl.Atom | pddl.AtomEffect] = []
        for child in effect.effects:
            atoms.extend(_add_effect_atoms(child))
        return tuple(atoms)
    raise UnsupportedSTRIPSTaskError(
        "conditional, probabilistic, and numeric effects are unsupported"
    )


def _ground_atom(atom: pddl.Atom | pddl.AtomEffect, binding: dict[str, str]) -> str:
    arguments = tuple(binding.get(argument.name, argument.name) for argument in atom.arguments)
    return atom.name if not arguments else f"{atom.name}({','.join(arguments)})"


__all__ = [
    "GroundedPositiveSTRIPSTask",
    "GroundedRelaxedOperator",
    "UnsupportedSTRIPSTaskError",
    "estimated_grounded_operator_count",
    "extract_grounded_positive_strips",
]
