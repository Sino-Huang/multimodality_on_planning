from __future__ import annotations

from itertools import combinations
from typing import Final

from .pddl import Atom, canonical_atom

MAX_IW_TRACE_NOVELTY_ITEMS: Final = 200


def novelty_items(state: frozenset[Atom], width: int) -> tuple[tuple[str, ...], ...]:
    atoms = tuple(canonical_atom(atom) for atom in sorted(state))
    return tuple(item for size in range(1, width + 1) for item in combinations(atoms, size))


def first_novel(
    items: tuple[tuple[str, ...], ...], table: set[tuple[str, ...]]
) -> tuple[str, ...] | None:
    for item in items:
        if item not in table:
            return item
    return None


def serialize_tuple(item: tuple[str, ...]) -> str:
    return " | ".join(item)


def serialized_novelty_table(table: set[tuple[str, ...]]) -> list[str]:
    return sorted(serialize_tuple(item) for item in table)[:MAX_IW_TRACE_NOVELTY_ITEMS]


def state_atoms(state: frozenset[Atom]) -> list[str]:
    return sorted(canonical_atom(atom) for atom in state)
