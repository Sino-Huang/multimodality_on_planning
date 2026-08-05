from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from .cgas_candidate_graph import Atom
from .cgas_candidate_space import Candidate, JsonValue, build_candidate, candidate_record, lehmer_rank, ordered_families

AccountingStatus = Literal["duplicate", "emitted", "solved"]


@dataclass(frozen=True, slots=True)
class AccountingRow:
    object_count: int
    raw_rank: int
    status: AccountingStatus
    candidate_id: str
    first_raw_rank: int


@dataclass(frozen=True, slots=True)
class PlannerInput:
    object_count: int
    raw_rank: int
    status: Literal["emitted"]
    candidate_id: str
    first_raw_rank: int
    candidate: Candidate


def _goal_paths(goal_atoms: frozenset[Atom]) -> tuple[tuple[str, ...], ...]:
    above = {atom[2]: atom[1] for atom in goal_atoms}
    uppers = set(above.values())
    bottoms = sorted(set(above) - uppers)
    paths: list[tuple[str, ...]] = []
    for bottom in bottoms:
        stack = [bottom]
        while stack[-1] in above:
            stack.append(above[stack[-1]])
        paths.append(tuple(stack))
    return tuple(paths)


def _init_stacks(candidate: Candidate) -> tuple[tuple[str, ...], ...]:
    names = iter(f"b{index:02d}" for index in range(candidate.object_count))
    return tuple(tuple(next(names) for _ in range(height)) for height in candidate.family.init_partition)


def _canonical_goal_sequence(
    candidate: Candidate,
    mapping: dict[int, int],
    optimistic: bool,
) -> tuple[str, ...]:
    stacks = _init_stacks(candidate)
    location = {
        name: (stack_index, level)
        for stack_index, stack in enumerate(stacks)
        for level, name in enumerate(stack)
    }
    targets_by_height: dict[int, tuple[int, ...]] = {
        height: tuple(index for index, stack in enumerate(stacks) if len(stack) == height)
        for height in set(candidate.family.init_partition)
    }
    assigned_targets = set(mapping.values())

    def mapped(name: str) -> str:
        source_stack, level = location[name]
        target_stack = mapping.get(source_stack)
        if target_stack is None:
            candidates = tuple(
                index
                for index in targets_by_height[len(stacks[source_stack])]
                if index not in assigned_targets
            )
            target_stack = candidates[0] if optimistic else source_stack
        return stacks[target_stack][level]

    paths = _goal_paths(candidate.goal_atoms)
    path_objects = {name for path in paths for name in path}
    grouped: dict[int, list[tuple[str, ...]]] = defaultdict(list)
    for path in paths:
        grouped[len(path)].append(tuple(mapped(name) for name in path))
    result: list[str] = []
    for height in candidate.family.partial_goal_partition:
        if height == 1:
            break
        if grouped[height]:
            if len(grouped[height]) > 1:
                grouped[height].sort()
            result.extend(grouped[height].pop(0))
    result.extend(sorted(
        mapped(name)
        for name in (f"b{index:02d}" for index in range(candidate.object_count))
        if name not in path_objects
    ))
    return tuple(result)


def _complete_inactive_mapping(candidate: Candidate, mapping: dict[int, int]) -> dict[int, int]:
    stacks = _init_stacks(candidate)
    completed = dict(mapping)
    for height in set(candidate.family.init_partition):
        sources = [index for index, stack in enumerate(stacks) if len(stack) == height and index not in completed]
        targets = [
            index
            for index, stack in enumerate(stacks)
            if len(stack) == height and index not in completed.values()
        ]
        completed.update(zip(sources, targets, strict=True))
    return completed


def _minimum_equivalent_permutation(candidate: Candidate) -> tuple[str, ...]:
    names = tuple(f"b{index:02d}" for index in range(candidate.object_count))
    if len(candidate.family.init_partition) == candidate.object_count:
        return names
    stacks = _init_stacks(candidate)
    location = {name: stack_index for stack_index, stack in enumerate(stacks) for name in stack}
    active = {location[name] for path in _goal_paths(candidate.goal_atoms) for name in path}
    if not active:
        return names
    first_occurrence = {
        stack_index: min(
            position
            for position, name in enumerate(name for path in _goal_paths(candidate.goal_atoms) for name in path)
            if location[name] == stack_index
        )
        for stack_index in active
    }
    variables = tuple(sorted(active, key=lambda index: (first_occurrence[index], index)))
    targets_by_height = {
        height: tuple(index for index, stack in enumerate(stacks) if len(stack) == height)
        for height in set(candidate.family.init_partition)
    }
    best = _canonical_goal_sequence(candidate, _complete_inactive_mapping(candidate, {}), False)
    mapping: dict[int, int] = {}

    def search(position: int) -> None:
        nonlocal best
        lower = _canonical_goal_sequence(candidate, mapping, True)
        if lower >= best:
            return
        if position == len(variables):
            sequence = _canonical_goal_sequence(candidate, _complete_inactive_mapping(candidate, mapping), False)
            if sequence < best:
                best = sequence
            return
        source = variables[position]
        used = set(mapping.values())
        for target in targets_by_height[len(stacks[source])]:
            if target in used:
                continue
            mapping[source] = target
            search(position + 1)
            del mapping[source]

    search(0)
    return best


@lru_cache(maxsize=16384)
def _first_raw_rank(object_count: int, family_index: int, candidate_id: str, raw_rank: int) -> int:
    candidate = build_candidate(object_count, raw_rank)
    minimum_ordinal = lehmer_rank(_minimum_equivalent_permutation(candidate))
    first = minimum_ordinal * len(ordered_families(object_count)) + family_index
    if build_candidate(object_count, first).candidate_id != candidate_id:
        for ordinal in range(candidate.permutation_ordinal):
            possible = ordinal * len(ordered_families(object_count)) + family_index
            if build_candidate(object_count, possible).candidate_id == candidate_id:
                return possible
        return raw_rank
    return first


def accounting_row(candidate: Candidate) -> AccountingRow:
    first = _first_raw_rank(
        candidate.object_count,
        candidate.family.family_index,
        candidate.candidate_id,
        candidate.raw_rank,
    )
    if candidate.solved:
        status: AccountingStatus = "solved"
    elif first == candidate.raw_rank:
        status = "emitted"
    else:
        status = "duplicate"
    return AccountingRow(candidate.object_count, candidate.raw_rank, status, candidate.candidate_id, first)


def iter_accounting_slice(
    object_count: int,
    start_rank: int,
    count: int,
) -> Iterator[tuple[AccountingRow, PlannerInput | None]]:
    for raw_rank in range(start_rank, start_rank + count):
        candidate = build_candidate(object_count, raw_rank)
        row = accounting_row(candidate)
        planner = (
            PlannerInput(object_count, raw_rank, "emitted", candidate.candidate_id, raw_rank, candidate)
            if row.status == "emitted"
            else None
        )
        yield row, planner


def accounting_slice(
    object_count: int,
    start_rank: int,
    count: int,
) -> tuple[tuple[AccountingRow, ...], tuple[PlannerInput, ...]]:
    pairs = tuple(iter_accounting_slice(object_count, start_rank, count))
    return tuple(row for row, _ in pairs), tuple(planner for _, planner in pairs if planner is not None)


def accounting_record(row: AccountingRow) -> dict[str, JsonValue]:
    return {
        "candidate_id": row.candidate_id,
        "first_raw_rank": row.first_raw_rank,
        "object_count": row.object_count,
        "raw_rank": row.raw_rank,
        "schema_version": "cgas_production_raw_accounting_v1",
        "status": row.status,
    }


def planner_input_record(planner: PlannerInput) -> dict[str, JsonValue]:
    return {
        **candidate_record(planner.candidate),
        "first_raw_rank": planner.first_raw_rank,
        "status": planner.status,
    }
