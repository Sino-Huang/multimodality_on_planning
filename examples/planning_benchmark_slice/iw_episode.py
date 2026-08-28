from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Callable, Iterable

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

IW_START_WIDTH = 1
IW_MAX_WIDTH = 3
NoveltyItem = tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IWSearchStep:
    width_attempt: int
    width: int
    expansion_index: int
    expanded_state_id: str
    memory_before: SearchMemory
    operation: SearchOperation
    result: SearchTransitionResult
    decision: str
    novel_item: NoveltyItem | None
    novelty_table_before: frozenset[NoveltyItem]
    novelty_table_after: frozenset[NoveltyItem]
    target_novel_item: NoveltyItem | None


@dataclass(frozen=True, slots=True)
class IWAttemptSummary:
    width: int
    expansion_count: int
    decision_count: int
    generated_count: int
    novelty_pruned_count: int
    duplicate_count: int
    peak_frontier: int
    termination: str


@dataclass(frozen=True, slots=True)
class IWSearchSummary:
    memory: SearchMemory
    states: tuple[CanonicalState, ...]
    attempts: tuple[IWAttemptSummary, ...]
    goal_reached: bool
    solving_width: int | None
    plan: tuple[GroundedAction, ...]

    @property
    def expansion_count(self) -> int:
        return sum(attempt.expansion_count for attempt in self.attempts)

    @property
    def decision_count(self) -> int:
        return sum(attempt.decision_count for attempt in self.attempts)


def iw_novelty_items(state: CanonicalState, width: int) -> tuple[NoveltyItem, ...]:
    """Return canonical atom tuples up to the active IW width."""

    return tuple(_iter_iw_novelty_items(state, width))


def _iter_iw_novelty_items(state: CanonicalState, width: int) -> Iterable[NoveltyItem]:
    return (item for size in range(1, width + 1) for item in combinations(state.atoms, size))


def first_novel_item(
    items: Iterable[NoveltyItem],
    novelty_table: set[NoveltyItem],
) -> NoveltyItem | None:
    return next((item for item in items if item not in novelty_table), None)


def serialize_novelty_table(items: Iterable[NoveltyItem]) -> list[list[str]]:
    return [list(item) for item in sorted(items)]


def build_iw_evaluator(novelty: int) -> StateEvaluator:
    def evaluate(_state: CanonicalState) -> StateEvaluation:
        return StateEvaluation(novelty=novelty, heuristic=HeuristicValue("not_applicable", 0))

    return evaluate


def build_iw_observation(
    *,
    authority: PDDLStateAuthority,
    state: CanonicalState,
    memory: SearchMemory,
    novelty_table: set[NoveltyItem],
    width: int,
) -> dict[str, Any]:
    """Build the shared Markov-sufficient view used by exact traces and replay."""

    candidates: list[dict[str, Any]] = []
    for action in authority.applicable_actions(state):
        target = authority.preview_apply(state, action).target_state
        target_novel_item = first_novel_item(iw_novelty_items(target, width), novelty_table)
        visited = target.state_id in memory.visited
        candidates.append(
            {
                "action": action.serialize(),
                "enqueue_eligible": not visited and target_novel_item is not None,
                "novel_item": None if target_novel_item is None else list(target_novel_item),
                "pruned": visited or target_novel_item is None,
                "target_atoms": list(target.atoms),
                "target_fluents": list(target.fluents),
                "target_state_id": target.state_id,
                "visited": visited,
            }
        )
    return {
        "algorithm": "iterated_width",
        "expanded_state": {
            "atoms": list(state.atoms),
            "fluents": list(state.fluents),
            "state_id": state.state_id,
        },
        "search_memory": {
            "frontier": list(memory.frontier),
            "novelty_by_state": dict(sorted(memory.novelty.items())),
            "novelty_table": serialize_novelty_table(novelty_table),
            "visited": sorted(memory.visited),
        },
        "successor_candidates": candidates,
        "task_context": authority.task_context(),
        "width": width,
    }


def run_iterative_width(
    authority: PDDLStateAuthority,
    *,
    max_expansions: int,
    on_step: Callable[[IWSearchStep], None] | None = None,
) -> IWSearchSummary:
    if on_step is None:
        return _run_iterative_width_compact(authority, max_expansions=max_expansions)

    initial = authority.initial_state
    all_states = {initial.state_id: initial}
    attempts: list[IWAttemptSummary] = []
    goal_reached = authority.is_goal(initial)
    solving_width: int | None = IW_START_WIDTH if goal_reached else None
    plan: tuple[GroundedAction, ...] = ()
    memory = SearchMemory.initial(authority)
    global_expansion = 0

    for width_attempt, width in enumerate(range(IW_START_WIDTH, IW_MAX_WIDTH + 1)):
        memory = SearchMemory.initial(authority)
        novelty_table: set[NoveltyItem] = set()
        parents: dict[str, tuple[str, GroundedAction]] = {}
        attempt_expansions = 0
        attempt_decisions = 0
        generated_count = 0
        novelty_pruned_count = 0
        duplicate_count = 0
        peak_frontier = len(memory.frontier)

        while memory.frontier and attempt_expansions < max_expansions and not goal_reached:
            expanded_state_id = memory.frontier[0]
            state = memory.state(expanded_state_id)
            table_before = frozenset(novelty_table)
            novel_item = first_novel_item(_iter_iw_novelty_items(state, width), novelty_table)
            if attempt_expansions == 0 and novel_item is None:
                novel_item = ()
            decision = "expand" if novel_item is not None else "prune"
            if decision == "expand":
                novelty_table.update(_iter_iw_novelty_items(state, width))
            table_after = frozenset(novelty_table)

            accepted_successor = False
            if decision == "expand":
                for action in authority.applicable_actions(state):
                    target = authority.preview_apply(state, action).target_state
                    generated_count += 1
                    if target.state_id in memory.visited:
                        duplicate_count += 1
                        continue
                    target_novel_item = first_novel_item(
                        _iter_iw_novelty_items(target, width),
                        novelty_table,
                    )
                    if target_novel_item is None:
                        novelty_pruned_count += 1
                        continue

                    retire_source = not accepted_successor
                    request = SearchTransitionRequest(
                        source_state_id=expanded_state_id,
                        action=action,
                        frontier_intent=FrontierIntent(
                            retire_source=retire_source,
                            target_position=len(memory.frontier) - (1 if retire_source else 0),
                        ),
                        visit_target=True,
                        evaluate_target=True,
                    )
                    memory_before = memory
                    result = apply_search_transition(
                        memory,
                        request,
                        evaluator=build_iw_evaluator(len(target_novel_item)),
                    )
                    if not isinstance(result, AcceptedTransition):
                        raise ValueError("trusted IW transition was rejected")
                    memory = result.memory
                    target = result.transition.target_state
                    all_states[target.state_id] = target
                    parents[target.state_id] = (expanded_state_id, action)
                    if on_step is not None:
                        on_step(
                            IWSearchStep(
                                width_attempt=width_attempt,
                                width=width,
                                expansion_index=global_expansion,
                                expanded_state_id=expanded_state_id,
                                memory_before=memory_before,
                                operation=request,
                                result=result,
                                decision=decision,
                                novel_item=novel_item,
                                novelty_table_before=table_before,
                                novelty_table_after=table_after,
                                target_novel_item=target_novel_item,
                            )
                        )
                    attempt_decisions += 1
                    accepted_successor = True
                    peak_frontier = max(peak_frontier, len(memory.frontier))
                    if authority.is_goal(target):
                        goal_reached = True
                        solving_width = width
                        plan = _reconstruct_plan(target.state_id, parents, initial.state_id)
                        break

            if not accepted_successor:
                request = SearchRetireRequest(expanded_state_id)
                memory_before = memory
                result = apply_search_retirement(memory, request)
                if not isinstance(result, AcceptedRetirement):
                    raise ValueError("trusted IW retirement was rejected")
                memory = result.memory
                if on_step is not None:
                    on_step(
                        IWSearchStep(
                            width_attempt=width_attempt,
                            width=width,
                            expansion_index=global_expansion,
                            expanded_state_id=expanded_state_id,
                            memory_before=memory_before,
                            operation=request,
                            result=result,
                            decision=decision,
                            novel_item=novel_item,
                            novelty_table_before=table_before,
                            novelty_table_after=table_after,
                            target_novel_item=None,
                        )
                    )
                attempt_decisions += 1
            attempt_expansions += 1
            global_expansion += 1

        termination = (
            "goal_reached"
            if goal_reached
            else "frontier_exhausted"
            if not memory.frontier
            else "expansion_budget"
        )
        attempts.append(
            IWAttemptSummary(
                width=width,
                expansion_count=attempt_expansions,
                decision_count=attempt_decisions,
                generated_count=generated_count,
                novelty_pruned_count=novelty_pruned_count,
                duplicate_count=duplicate_count,
                peak_frontier=peak_frontier,
                termination=termination,
            )
        )
        if goal_reached:
            break

    return IWSearchSummary(
        memory=memory,
        states=tuple(all_states[state_id] for state_id in sorted(all_states)),
        attempts=tuple(attempts),
        goal_reached=goal_reached,
        solving_width=solving_width,
        plan=plan,
    )


def _run_iterative_width_compact(
    authority: PDDLStateAuthority,
    *,
    max_expansions: int,
) -> IWSearchSummary:
    initial = authority.initial_state
    all_states = {initial.state_id: initial}
    attempts: list[IWAttemptSummary] = []
    goal_reached = authority.is_goal(initial)
    solving_width: int | None = IW_START_WIDTH if goal_reached else None
    plan: tuple[GroundedAction, ...] = ()
    memory = SearchMemory.initial(authority)

    for width in range(IW_START_WIDTH, IW_MAX_WIDTH + 1):
        frontier = deque((initial.state_id,))
        visited = {initial.state_id}
        known_states = {initial.state_id: initial}
        novelty_by_state: dict[str, int] = {}
        heuristics: dict[str, HeuristicValue] = {}
        provenance = []
        novelty_table: set[NoveltyItem] = set()
        parents: dict[str, tuple[str, GroundedAction]] = {}
        attempt_expansions = 0
        attempt_decisions = 0
        generated_count = 0
        novelty_pruned_count = 0
        duplicate_count = 0
        peak_frontier = 1

        while frontier and attempt_expansions < max_expansions and not goal_reached:
            expanded_state_id = frontier[0]
            state = known_states[expanded_state_id]
            novel_item = first_novel_item(_iter_iw_novelty_items(state, width), novelty_table)
            if attempt_expansions == 0 and novel_item is None:
                novel_item = ()
            decision = "expand" if novel_item is not None else "prune"
            if decision == "expand":
                novelty_table.update(_iter_iw_novelty_items(state, width))

            accepted_successor = False
            if decision == "expand":
                for action in authority.applicable_actions(state):
                    transition = authority.apply(state, action)
                    target = transition.target_state
                    generated_count += 1
                    if target.state_id in visited:
                        duplicate_count += 1
                        continue
                    target_novel_item = first_novel_item(
                        _iter_iw_novelty_items(target, width),
                        novelty_table,
                    )
                    if target_novel_item is None:
                        novelty_pruned_count += 1
                        continue
                    if not accepted_successor:
                        frontier.popleft()
                    frontier.append(target.state_id)
                    visited.add(target.state_id)
                    known_states[target.state_id] = target
                    all_states[target.state_id] = target
                    novelty_by_state[target.state_id] = len(target_novel_item)
                    heuristics[target.state_id] = HeuristicValue("not_applicable", 0)
                    provenance.append(transition.provenance)
                    parents[target.state_id] = (expanded_state_id, action)
                    attempt_decisions += 1
                    accepted_successor = True
                    peak_frontier = max(peak_frontier, len(frontier))
                    if authority.is_goal(target):
                        goal_reached = True
                        solving_width = width
                        plan = _reconstruct_plan(target.state_id, parents, initial.state_id)
                        break

            if not accepted_successor:
                frontier.popleft()
                attempt_decisions += 1
            attempt_expansions += 1

        termination = (
            "goal_reached"
            if goal_reached
            else "frontier_exhausted"
            if not frontier
            else "expansion_budget"
        )
        attempts.append(
            IWAttemptSummary(
                width=width,
                expansion_count=attempt_expansions,
                decision_count=attempt_decisions,
                generated_count=generated_count,
                novelty_pruned_count=novelty_pruned_count,
                duplicate_count=duplicate_count,
                peak_frontier=peak_frontier,
                termination=termination,
            )
        )
        memory = SearchMemory._create(
            authority=authority,
            frontier=tuple(frontier),
            visited=frozenset(visited),
            novelty=novelty_by_state,
            heuristics=heuristics,
            provenance=tuple(provenance),
            known_states=known_states,
        )
        if goal_reached:
            break

    return IWSearchSummary(
        memory=memory,
        states=tuple(all_states[state_id] for state_id in sorted(all_states)),
        attempts=tuple(attempts),
        goal_reached=goal_reached,
        solving_width=solving_width,
        plan=plan,
    )


def _reconstruct_plan(
    goal_state_id: str,
    parents: dict[str, tuple[str, GroundedAction]],
    initial_state_id: str,
) -> tuple[GroundedAction, ...]:
    reversed_plan: list[GroundedAction] = []
    state_id = goal_state_id
    while state_id != initial_state_id:
        state_id, action = parents[state_id]
        reversed_plan.append(action)
    return tuple(reversed(reversed_plan))


__all__ = [
    "IW_MAX_WIDTH",
    "IW_START_WIDTH",
    "IWAttemptSummary",
    "IWSearchStep",
    "IWSearchSummary",
    "NoveltyItem",
    "build_iw_evaluator",
    "build_iw_observation",
    "first_novel_item",
    "iw_novelty_items",
    "run_iterative_width",
    "serialize_novelty_table",
]
