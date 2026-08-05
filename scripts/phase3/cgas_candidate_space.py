from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise
from typing import TypeAlias

from .cgas_candidate_graph import Atom, CanonicalGraph, canonicalize_graph, identity_graph
from .cgas_characterization_rows import canonical_composition_signature
from .pddl import PDDLTask

JsonValue: TypeAlias = str | int | bool | list["JsonValue"] | dict[str, "JsonValue"] | None


@dataclass(frozen=True, slots=True)
class CandidateSpaceError(ValueError):
    code: str

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class LehmerStep:
    index: int
    divisor: int
    quotient: int
    remainder: int
    selected: str


@dataclass(frozen=True, slots=True)
class Family:
    family_index: int
    init_partition_index: int
    partial_goal_partition_index: int
    init_partition: tuple[int, ...]
    partial_goal_partition: tuple[int, ...]
    composition_signature: str
    composition_sha256: str


@dataclass(frozen=True, slots=True)
class Candidate:
    object_count: int
    raw_rank: int
    permutation_ordinal: int
    family: Family
    permutation: tuple[str, ...]
    init_atoms: frozenset[Atom]
    goal_atoms: frozenset[Atom]
    graph: CanonicalGraph
    leaf_bytes: bytes
    candidate_id: str
    solved: bool
    problem: str

    @property
    def composition_signature(self) -> str:
        return self.family.composition_signature


def _object_names(object_count: int) -> tuple[str, ...]:
    return tuple(f"b{index:02d}" for index in range(object_count))


@lru_cache(maxsize=None)
def integer_partitions(object_count: int) -> tuple[tuple[int, ...], ...]:
    if object_count <= 0:
        raise CandidateSpaceError("object_count_not_positive")

    def visit(remaining: int, ceiling: int, prefix: tuple[int, ...]) -> list[tuple[int, ...]]:
        if remaining == 0:
            return [prefix]
        return [
            partition
            for part in range(min(remaining, ceiling), 0, -1)
            for partition in visit(remaining - part, part, (*prefix, part))
        ]

    return tuple(sorted(visit(object_count, object_count, ())))


def _stacks(partition: tuple[int, ...]) -> tuple[tuple[str, ...], ...]:
    names = iter(_object_names(sum(partition)))
    return tuple(tuple(next(names) for _ in range(height)) for height in partition)


def stable_initial_atoms(partition: tuple[int, ...]) -> frozenset[Atom]:
    atoms: set[Atom] = {("arm-empty",)}
    for stack in _stacks(partition):
        atoms.add(("on-table", stack[0]))
        atoms.add(("clear", stack[-1]))
        atoms.update(("on", upper, lower) for lower, upper in pairwise(stack))
    return frozenset(atoms)


def partial_goal_atoms(partition: tuple[int, ...], permutation: tuple[str, ...]) -> frozenset[Atom]:
    atoms: set[Atom] = set()
    offset = 0
    for height in partition:
        stack = permutation[offset : offset + height]
        atoms.update(("on", upper, lower) for lower, upper in pairwise(stack))
        offset += height
    return frozenset(atoms)


def _composition_signature(object_count: int, init: tuple[int, ...], goal: tuple[int, ...]) -> str:
    task = PDDLTask(
        domain_name="blocksworld-4ops",
        problem_name="composition-signature",
        objects_by_type={"object": _object_names(object_count)},
        init=stable_initial_atoms(init),
        goal=partial_goal_atoms(goal, _object_names(object_count)),
        actions=(),
        unsupported_features=(),
    )
    return canonical_composition_signature(task)


@lru_cache(maxsize=None)
def ordered_families(object_count: int) -> tuple[Family, ...]:
    partitions = integer_partitions(object_count)
    unordered = tuple(
        (
            hashlib.sha256(signature.encode("utf-8")).hexdigest(),
            init_index,
            goal_index,
            init,
            goal,
            signature,
        )
        for init_index, init in enumerate(partitions)
        for goal_index, goal in enumerate(partitions)
        for signature in (_composition_signature(object_count, init, goal),)
    )
    return tuple(
        Family(family_index, init_index, goal_index, init, goal, signature, digest)
        for family_index, (digest, init_index, goal_index, init, goal, signature) in enumerate(
            sorted(unordered, key=lambda item: item[:3])
        )
    )


def stream_capacity(object_count: int) -> int:
    return math.factorial(object_count) * len(integer_partitions(object_count)) ** 2


def lehmer_steps(object_count: int, ordinal: int) -> tuple[LehmerStep, ...]:
    capacity = math.factorial(object_count)
    if ordinal < 0 or ordinal >= capacity:
        raise CandidateSpaceError("lehmer_ordinal_out_of_range")
    pool = list(_object_names(object_count))
    remainder = ordinal
    steps: list[LehmerStep] = []
    for index in range(object_count):
        divisor = math.factorial(object_count - 1 - index)
        quotient, remainder = divmod(remainder, divisor)
        selected = pool.pop(quotient)
        steps.append(LehmerStep(index, divisor, quotient, remainder, selected))
    return tuple(steps)


def lehmer_unrank(object_count: int, ordinal: int) -> tuple[str, ...]:
    return tuple(step.selected for step in lehmer_steps(object_count, ordinal))


def lehmer_rank(permutation: tuple[str, ...]) -> int:
    pool = list(sorted(permutation))
    ordinal = 0
    for index, selected in enumerate(permutation):
        quotient = pool.index(selected)
        ordinal += quotient * math.factorial(len(permutation) - 1 - index)
        pool.pop(quotient)
    return ordinal


def problem_pddl(
    object_count: int,
    raw_rank: int,
    init_atoms: frozenset[Atom],
    goal_atoms: frozenset[Atom],
) -> str:
    objects = " ".join(_object_names(object_count))
    init = "\n".join(f"    ({' '.join(atom)})" for atom in sorted(init_atoms))
    goal = "\n".join(f"    ({' '.join(atom)})" for atom in sorted(goal_atoms))
    goal_block = f"\n{goal}\n  " if goal else ""
    return (
        f"(define (problem cgas-production-{object_count:02d}-{raw_rank:012d})\n"
        "  (:domain blocksworld-4ops)\n"
        f"  (:objects {objects})\n"
        f"  (:init\n{init}\n  )\n"
        f"  (:goal (and{goal_block}))\n"
        ")\n"
    )


@lru_cache(maxsize=8192)
def build_candidate(object_count: int, raw_rank: int) -> Candidate:
    capacity = stream_capacity(object_count)
    if raw_rank < 0 or raw_rank >= capacity:
        raise CandidateSpaceError("raw_rank_out_of_range")
    families = ordered_families(object_count)
    permutation_ordinal, family_index = divmod(raw_rank, len(families))
    family = families[family_index]
    permutation = lehmer_unrank(object_count, permutation_ordinal)
    init_atoms = stable_initial_atoms(family.init_partition)
    goal_atoms = partial_goal_atoms(family.partial_goal_partition, permutation)
    graph = identity_graph(_object_names(object_count), init_atoms, goal_atoms)
    canonical = canonicalize_graph(graph)
    return Candidate(
        object_count,
        raw_rank,
        permutation_ordinal,
        family,
        permutation,
        init_atoms,
        goal_atoms,
        graph,
        canonical.leaf_bytes,
        canonical.candidate_id,
        goal_atoms.issubset(init_atoms),
        problem_pddl(object_count, raw_rank, init_atoms, goal_atoms),
    )


def candidate_record(candidate: Candidate) -> dict[str, JsonValue]:
    goal_atoms: list[JsonValue] = [list(atom) for atom in sorted(candidate.goal_atoms)]
    init_atoms: list[JsonValue] = [list(atom) for atom in sorted(candidate.init_atoms)]
    return {
        "candidate_id": candidate.candidate_id,
        "canonical_composition_signature": candidate.composition_signature,
        "goal_atoms": goal_atoms,
        "init_atoms": init_atoms,
        "object_count": candidate.object_count,
        "problem_pddl": candidate.problem,
        "raw_rank": candidate.raw_rank,
        "schema_version": "cgas_production_planner_input_v1",
    }
