from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from heapq import heappop, heappush
from typing import Any, Callable, Mapping

from .iw_episode import NoveltyItem, first_novel_item, iw_novelty_items, serialize_novelty_table
from .pddl_state import CanonicalState, GroundedAction, PDDLStateAuthority
from .search_memory import (
    AcceptedRetirement,
    AcceptedTransition,
    FrontierIntent,
    HeuristicValue,
    SearchMemory,
    SearchOperation,
    SearchRetireRequest,
    SearchTransitionRequest,
    SearchTransitionResult,
    StateEvaluation,
    StateEvaluator,
    apply_search_retirement,
    apply_search_transition,
)

BFWS_NOVELTY_PRECISION = 2
PriorityKey = tuple[int, int, int, int]
PartitionTables = Mapping[int, frozenset[NoveltyItem]]


@dataclass(frozen=True, slots=True)
class BFWSSearchStep:
    expansion_index: int
    expanded_state_id: str
    memory_before: SearchMemory
    operation: SearchOperation
    result: SearchTransitionResult
    partition_tables_before: PartitionTables
    partition_tables_after: PartitionTables
    priority_by_state: Mapping[str, PriorityKey]
    novelty_bucket: int
    novel_item: NoveltyItem | None
    priority: PriorityKey
    residual_novelty_retained: bool


@dataclass(frozen=True, slots=True)
class BFWSSearchSummary:
    memory: SearchMemory
    states: tuple[CanonicalState, ...]
    goal_reached: bool
    plan: tuple[GroundedAction, ...]
    expansion_count: int
    decision_count: int
    generated_count: int
    duplicate_count: int
    novelty_pruned_count: int
    residual_novelty_retained_count: int
    peak_frontier: int
    termination: str


def build_bfws_evaluator(novelty_bucket: int, unachieved_goals: int) -> StateEvaluator:
    def evaluate(_state: CanonicalState) -> StateEvaluation:
        return StateEvaluation(
            novelty=novelty_bucket,
            heuristic=HeuristicValue("unachieved_goals", unachieved_goals),
        )

    return evaluate


def run_best_first_width(
    authority: PDDLStateAuthority,
    *,
    max_expansions: int,
    on_step: Callable[[BFWSSearchStep], None] | None = None,
) -> BFWSSearchSummary:
    if on_step is None:
        return _run_best_first_width_compact(authority, max_expansions=max_expansions)

    initial = authority.initial_state
    initial_goals = _unachieved_goal_count(authority, initial)
    initial_items = iw_novelty_items(initial, BFWS_NOVELTY_PRECISION)
    initial_novel_item = first_novel_item(initial_items, set())
    initial_bucket = len(initial_novel_item) if initial_novel_item is not None else BFWS_NOVELTY_PRECISION + 1
    partition_tables: dict[int, set[NoveltyItem]] = {initial_goals: set(initial_items)}
    priority_by_state: dict[str, PriorityKey] = {
        initial.state_id: (initial_bucket, initial_goals, 0, 0)
    }
    depth_by_state = {initial.state_id: 0}
    parents: dict[str, tuple[str, GroundedAction]] = {}
    memory = SearchMemory.initial(authority)
    states = {initial.state_id: initial}
    goal_reached = authority.is_goal(initial)
    goal_state_id = initial.state_id if goal_reached else None
    expansion_count = 0
    decision_count = 0
    generated_count = 0
    duplicate_count = 0
    residual_count = 0
    peak_frontier = 1
    generation_serial = 0

    while memory.frontier and expansion_count < max_expansions and not goal_reached:
        expanded_state_id = memory.frontier[0]
        state = memory.state(expanded_state_id)
        accepted_successor = False
        for action in authority.applicable_actions(state):
            target = authority.preview_apply(state, action).target_state
            generated_count += 1
            if target.state_id in memory.visited:
                duplicate_count += 1
                continue

            partition = _unachieved_goal_count(authority, target)
            table = partition_tables.setdefault(partition, set())
            tables_before = _freeze_tables(partition_tables)
            target_items = iw_novelty_items(target, BFWS_NOVELTY_PRECISION)
            novel_item = first_novel_item(target_items, table)
            novelty_bucket = len(novel_item) if novel_item is not None else BFWS_NOVELTY_PRECISION + 1
            table.update(target_items)
            tables_after = _freeze_tables(partition_tables)
            generation_serial += 1
            target_depth = depth_by_state[expanded_state_id] + 1
            priority = (novelty_bucket, partition, target_depth, generation_serial)

            retire_source = not accepted_successor
            remaining = list(memory.frontier)
            if retire_source:
                remaining.remove(expanded_state_id)
            target_position = bisect_right([priority_by_state[state_id] for state_id in remaining], priority)
            request = SearchTransitionRequest(
                source_state_id=expanded_state_id,
                action=action,
                frontier_intent=FrontierIntent(retire_source=retire_source, target_position=target_position),
                visit_target=True,
                evaluate_target=True,
            )
            memory_before = memory
            result = apply_search_transition(
                memory,
                request,
                evaluator=build_bfws_evaluator(novelty_bucket, partition),
            )
            if not isinstance(result, AcceptedTransition):
                raise ValueError("trusted BFWS transition was rejected")
            memory = result.memory
            states[target.state_id] = target
            parents[target.state_id] = (expanded_state_id, action)
            depth_by_state[target.state_id] = target_depth
            priority_by_state[target.state_id] = priority
            residual_retained = novelty_bucket == BFWS_NOVELTY_PRECISION + 1
            residual_count += int(residual_retained)
            if on_step is not None:
                on_step(
                    BFWSSearchStep(
                        expansion_index=expansion_count,
                        expanded_state_id=expanded_state_id,
                        memory_before=memory_before,
                        operation=request,
                        result=result,
                        partition_tables_before=tables_before,
                        partition_tables_after=tables_after,
                        priority_by_state=dict(priority_by_state),
                        novelty_bucket=novelty_bucket,
                        novel_item=novel_item,
                        priority=priority,
                        residual_novelty_retained=residual_retained,
                    )
                )
            decision_count += 1
            accepted_successor = True
            peak_frontier = max(peak_frontier, len(memory.frontier))
            if authority.is_goal(target):
                goal_reached = True
                goal_state_id = target.state_id
                break

        if not accepted_successor:
            request = SearchRetireRequest(expanded_state_id)
            memory_before = memory
            result = apply_search_retirement(memory, request)
            if not isinstance(result, AcceptedRetirement):
                raise ValueError("trusted BFWS retirement was rejected")
            memory = result.memory
            if on_step is not None:
                source_priority = priority_by_state[expanded_state_id]
                tables = _freeze_tables(partition_tables)
                on_step(
                    BFWSSearchStep(
                        expansion_index=expansion_count,
                        expanded_state_id=expanded_state_id,
                        memory_before=memory_before,
                        operation=request,
                        result=result,
                        partition_tables_before=tables,
                        partition_tables_after=tables,
                        priority_by_state=dict(priority_by_state),
                        novelty_bucket=source_priority[0],
                        novel_item=None,
                        priority=source_priority,
                        residual_novelty_retained=False,
                    )
                )
            decision_count += 1
        expansion_count += 1

    termination = (
        "goal_reached"
        if goal_reached
        else "frontier_exhausted"
        if not memory.frontier
        else "expansion_budget"
    )
    plan = () if goal_state_id is None else _reconstruct_plan(goal_state_id, parents, initial.state_id)
    return BFWSSearchSummary(
        memory=memory,
        states=tuple(states[state_id] for state_id in sorted(states)),
        goal_reached=goal_reached,
        plan=plan,
        expansion_count=expansion_count,
        decision_count=decision_count,
        generated_count=generated_count,
        duplicate_count=duplicate_count,
        novelty_pruned_count=0,
        residual_novelty_retained_count=residual_count,
        peak_frontier=peak_frontier,
        termination=termination,
    )


def _run_best_first_width_compact(
    authority: PDDLStateAuthority,
    *,
    max_expansions: int,
) -> BFWSSearchSummary:
    initial = authority.initial_state
    initial_goals = _unachieved_goal_count(authority, initial)
    initial_items = iw_novelty_items(initial, BFWS_NOVELTY_PRECISION)
    initial_novel_item = first_novel_item(initial_items, set())
    initial_bucket = len(initial_novel_item) if initial_novel_item is not None else BFWS_NOVELTY_PRECISION + 1
    partition_tables: dict[int, set[NoveltyItem]] = {initial_goals: set(initial_items)}
    priority_by_state: dict[str, PriorityKey] = {
        initial.state_id: (initial_bucket, initial_goals, 0, 0)
    }
    depth_by_state = {initial.state_id: 0}
    parents: dict[str, tuple[str, GroundedAction]] = {}
    frontier = [(priority_by_state[initial.state_id], initial.state_id)]
    visited = {initial.state_id}
    states = {initial.state_id: initial}
    novelty_by_state: dict[str, int] = {}
    heuristics: dict[str, HeuristicValue] = {}
    provenance = []
    goal_reached = authority.is_goal(initial)
    goal_state_id = initial.state_id if goal_reached else None
    expansion_count = 0
    decision_count = 0
    generated_count = 0
    duplicate_count = 0
    residual_count = 0
    peak_frontier = 1
    generation_serial = 0

    while frontier and expansion_count < max_expansions and not goal_reached:
        _, expanded_state_id = heappop(frontier)
        state = states[expanded_state_id]
        accepted_successor = False
        for action in authority.applicable_actions(state):
            transition = authority.apply(state, action)
            target = transition.target_state
            generated_count += 1
            if target.state_id in visited:
                duplicate_count += 1
                continue

            partition = _unachieved_goal_count(authority, target)
            table = partition_tables.setdefault(partition, set())
            target_items = iw_novelty_items(target, BFWS_NOVELTY_PRECISION)
            novel_item = first_novel_item(target_items, table)
            novelty_bucket = len(novel_item) if novel_item is not None else BFWS_NOVELTY_PRECISION + 1
            table.update(target_items)
            generation_serial += 1
            target_depth = depth_by_state[expanded_state_id] + 1
            priority = (novelty_bucket, partition, target_depth, generation_serial)
            heappush(frontier, (priority, target.state_id))
            visited.add(target.state_id)
            states[target.state_id] = target
            novelty_by_state[target.state_id] = novelty_bucket
            heuristics[target.state_id] = HeuristicValue("unachieved_goals", partition)
            provenance.append(transition.provenance)
            parents[target.state_id] = (expanded_state_id, action)
            depth_by_state[target.state_id] = target_depth
            priority_by_state[target.state_id] = priority
            residual_count += int(novelty_bucket == BFWS_NOVELTY_PRECISION + 1)
            decision_count += 1
            accepted_successor = True
            peak_frontier = max(peak_frontier, len(frontier))
            if authority.is_goal(target):
                goal_reached = True
                goal_state_id = target.state_id
                break

        if not accepted_successor:
            decision_count += 1
        expansion_count += 1

    termination = (
        "goal_reached"
        if goal_reached
        else "frontier_exhausted"
        if not frontier
        else "expansion_budget"
    )
    plan = () if goal_state_id is None else _reconstruct_plan(goal_state_id, parents, initial.state_id)
    memory = SearchMemory._create(
        authority=authority,
        frontier=tuple(state_id for _, state_id in sorted(frontier)),
        visited=frozenset(visited),
        novelty=novelty_by_state,
        heuristics=heuristics,
        provenance=tuple(provenance),
        known_states=states,
    )
    return BFWSSearchSummary(
        memory=memory,
        states=tuple(states[state_id] for state_id in sorted(states)),
        goal_reached=goal_reached,
        plan=plan,
        expansion_count=expansion_count,
        decision_count=decision_count,
        generated_count=generated_count,
        duplicate_count=duplicate_count,
        novelty_pruned_count=0,
        residual_novelty_retained_count=residual_count,
        peak_frontier=peak_frontier,
        termination=termination,
    )


def build_bfws_observation(
    *,
    authority: PDDLStateAuthority,
    state: CanonicalState,
    memory: SearchMemory,
    partition_tables: PartitionTables,
    priority_by_state: Mapping[str, PriorityKey],
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for action in authority.applicable_actions(state):
        target = authority.preview_apply(state, action).target_state
        partition = _unachieved_goal_count(authority, target)
        table = set(partition_tables.get(partition, frozenset()))
        novel_item = first_novel_item(iw_novelty_items(target, BFWS_NOVELTY_PRECISION), table)
        bucket = len(novel_item) if novel_item is not None else BFWS_NOVELTY_PRECISION + 1
        candidates.append(
            {
                "action": action.serialize(),
                "novel_item": None if novel_item is None else list(novel_item),
                "novelty_bucket": bucket,
                "partition": partition,
                "residual_novelty": bucket == BFWS_NOVELTY_PRECISION + 1,
                "target_atoms": list(target.atoms),
                "target_fluents": list(target.fluents),
                "target_state_id": target.state_id,
                "visited": target.state_id in memory.visited,
            }
        )
    return {
        "algorithm": "best_first_width",
        "expanded_state": {
            "atoms": list(state.atoms),
            "fluents": list(state.fluents),
            "state_id": state.state_id,
        },
        "search_memory": {
            "frontier": list(memory.frontier),
            "frontier_priorities": [list(priority_by_state[state_id]) for state_id in memory.frontier],
            "partition_novelty_tables": {
                str(partition): serialize_novelty_table(table)
                for partition, table in sorted(partition_tables.items())
            },
            "visited": sorted(memory.visited),
        },
        "successor_candidates": candidates,
        "task_context": authority.task_context(),
        "novelty_precision": BFWS_NOVELTY_PRECISION,
        "high_novelty_policy": "enqueue",
    }


def _unachieved_goal_count(authority: PDDLStateAuthority, state: CanonicalState) -> int:
    if authority.goal_atoms is None:
        return 1
    return len(set(authority.goal_atoms) - set(state.atoms))


def _freeze_tables(tables: Mapping[int, set[NoveltyItem]]) -> dict[int, frozenset[NoveltyItem]]:
    return {partition: frozenset(table) for partition, table in tables.items()}


def _reconstruct_plan(
    goal_state_id: str,
    parents: Mapping[str, tuple[str, GroundedAction]],
    initial_state_id: str,
) -> tuple[GroundedAction, ...]:
    reversed_plan: list[GroundedAction] = []
    state_id = goal_state_id
    while state_id != initial_state_id:
        state_id, action = parents[state_id]
        reversed_plan.append(action)
    return tuple(reversed(reversed_plan))


__all__ = [
    "BFWS_NOVELTY_PRECISION",
    "BFWSSearchStep",
    "BFWSSearchSummary",
    "build_bfws_evaluator",
    "build_bfws_observation",
    "run_best_first_width",
]
