"""Trusted delete-relaxed h_max for the supported deterministic PDDL slice."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from plado import pddl

from .pddl_state import CanonicalState, PDDLStateAuthority

HMAX_UNREACHABLE = 1_000_000_000


class UnsupportedHMaxTaskError(ValueError):
    """Raised when h_max is asked to approximate outside its trusted subset."""


@dataclass(frozen=True, slots=True)
class _RelaxedOperator:
    preconditions: frozenset[str]
    add_effects: frozenset[str]


class HMaxHeuristic:
    """Exact h_max recurrence over grounded positive STRIPS operators."""

    name = "h_max"

    def __init__(self, authority: PDDLStateAuthority) -> None:
        if authority.goal_atoms is None:
            raise UnsupportedHMaxTaskError("h_max requires a positive-conjunctive goal")
        self._authority = authority
        self._goals = frozenset(authority.goal_atoms)
        self._static = frozenset(authority.static_initial_facts)
        self._operators = _ground_relaxed_operators(authority)

    def __call__(self, state: CanonicalState) -> int:
        if state.authority_id != self._authority.authority_id:
            raise ValueError("h_max state belongs to a different PDDL authority")
        costs = {fact: 0 for fact in (*state.atoms, *self._static)}
        changed = True
        while changed:
            changed = False
            for operator in self._operators:
                if not operator.preconditions <= costs.keys():
                    continue
                candidate = 1 + max((costs[item] for item in operator.preconditions), default=0)
                for effect in operator.add_effects:
                    if candidate < costs.get(effect, HMAX_UNREACHABLE):
                        costs[effect] = candidate
                        changed = True
        if not self._goals:
            return 0
        return max(costs.get(goal, HMAX_UNREACHABLE) for goal in self._goals)


def _ground_relaxed_operators(authority: PDDLStateAuthority) -> tuple[_RelaxedOperator, ...]:
    domain = authority._domain  # package-internal normalized PDDL authority
    all_objects = tuple(sorted({item for _, values in authority.objects_by_type for item in values}))
    operators: list[_RelaxedOperator] = []
    for action in domain.actions:
        preconditions = _positive_atoms(action.precondition, "action precondition")
        add_effects = _add_effect_atoms(action.effect)
        # Normalization inserts static type predicates into preconditions. Grounding
        # over every object therefore handles subtypes without inventing an extra
        # type hierarchy; mismatched tuples can never satisfy those predicates.
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
                _RelaxedOperator(
                    frozenset(_ground_atom(atom, binding) for atom in preconditions),
                    frozenset(_ground_atom(atom, binding) for atom in add_effects),
                )
            )
    return tuple(operators)


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
        raise UnsupportedHMaxTaskError(f"h_max requires a positive-conjunctive {label}")
    if any(atom.name == "=" for atom in atoms):
        raise UnsupportedHMaxTaskError("h_max does not support normalized equality preconditions")
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
    raise UnsupportedHMaxTaskError("h_max requires deterministic unconditional STRIPS effects")


def _ground_atom(atom: pddl.Atom | pddl.AtomEffect, binding: dict[str, str]) -> str:
    arguments = tuple(binding.get(argument.name, argument.name) for argument in atom.arguments)
    return atom.name if not arguments else f"{atom.name}({','.join(arguments)})"


__all__ = ["HMAX_UNREACHABLE", "HMaxHeuristic", "UnsupportedHMaxTaskError"]
