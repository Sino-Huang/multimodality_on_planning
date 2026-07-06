from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..blocksworld import AtomSet, BlocksworldAction, BlocksworldProblem, canonical_atom
from ..trajectory_schema import SCHEMA_VERSION, canonicalize_trajectory_step
from .bfs import WORLD_MODEL


FAST_FORWARD_TIE_BREAK_RULE = "min_heuristic_then_action_lexicographic"
P0_APPROXIMATION_ID = "deterministic_p0_hmax_relaxed_reachability"
UNREACHABLE_HEURISTIC_VALUE = 1_000_000


@dataclass(frozen=True)
class RelaxedHeuristic:
    heuristic_value: int
    relaxed_plan_actions: tuple[str, ...]
    relaxed_plan_length: int
    goal_costs: dict[str, int | None]
    supporter_actions: dict[str, str]
    unreachable_goal_atoms: tuple[str, ...]

    def to_metadata(self) -> dict[str, Any]:
        return {
            "approximation": P0_APPROXIMATION_ID,
            "approximation_scope": "P0 Blocksworld-only symbolic approximation, not full Fast Downward FF",
            "heuristic_definition": (
                "Ground all Blocksworld operators, ignore delete effects after the current concrete state, "
                "propagate h_max-style relaxed atom costs, then count the deterministic supporter-action "
                "closure for unsatisfied goals as an approximate relaxed plan length."
            ),
            "ignored_delete_effects": True,
            "is_exact_ff_delete_relaxation": False,
            "relaxed_plan_actions": list(self.relaxed_plan_actions),
            "relaxed_plan_length": self.relaxed_plan_length,
            "goal_costs": {goal: cost for goal, cost in sorted(self.goal_costs.items())},
            "supporter_actions": {atom: action for atom, action in sorted(self.supporter_actions.items())},
            "unreachable_goal_atoms": list(self.unreachable_goal_atoms),
        }


@dataclass(frozen=True)
class FastForwardSuccessor:
    action: str
    state_id: str
    state_atoms: list[str]
    heuristic_value: int
    relaxed_plan_length: int
    is_goal: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "heuristic_value": self.heuristic_value,
            "is_goal": self.is_goal,
            "relaxed_plan_length": self.relaxed_plan_length,
            "state_atoms": self.state_atoms,
            "state_id": self.state_id,
        }


def generate_fast_forward_trajectory(
    *,
    problem: BlocksworldProblem,
    instance_id: str,
    fixture_path: Path,
    max_steps: int = 64,
) -> list[dict[str, Any]]:
    """Generate deterministic FF-style greedy expert records for Blocksworld.

    This is intentionally documented as a P0 approximation rather than full FF:
    each step evaluates all legal successors with ``relaxed_plan_heuristic`` and
    takes the successor with the lowest approximate relaxed-plan length, breaking
    ties by the canonical action string. The non-trivial Phase 1-3 fixture is
    solved greedily by this rule while preserving Task 5 trace fields.
    """

    records: list[dict[str, Any]] = []
    current_state = problem.initial_state()

    for step_index in range(max_steps):
        if problem.is_goal(current_state):
            break
        step_record = build_fast_forward_step_record(
            problem=problem,
            instance_id=instance_id,
            fixture_path=fixture_path,
            state=current_state,
            step_index=step_index,
        )
        records.append(step_record)
        selected_action = select_fast_forward_action(problem, current_state)
        if selected_action is None:
            break
        current_state = problem.transition(current_state, selected_action)

    return records


def build_fast_forward_step_record(
    *,
    problem: BlocksworldProblem,
    instance_id: str,
    fixture_path: Path,
    state: Iterable[str],
    step_index: int,
) -> dict[str, Any]:
    atom_set = frozenset(state)
    state_id = problem.state_id(atom_set)
    heuristic = relaxed_plan_heuristic(problem, atom_set)
    successors = successor_heuristics(problem, atom_set)
    selected_successor = successors[0] if successors else None
    selected_action = selected_successor.action if selected_successor is not None else None
    selected_successor_id = selected_successor.state_id if selected_successor is not None else state_id
    failure_reason = None if successors else "no_legal_successor"

    record = {
        "algorithm": "fast_forward",
        "domain": "blocksworld",
        "fast_forward": {
            "failure_reason": failure_reason,
            "heuristic_value": heuristic.heuristic_value,
            "relaxed_plan_metadata": heuristic.to_metadata(),
            "selected_action": selected_action,
            "selected_successor_id": selected_successor_id,
            "successor_heuristics": [successor.to_dict() for successor in successors],
            "tie_break_rule": FAST_FORWARD_TIE_BREAK_RULE,
        },
        "goal_atoms": sorted(problem.goal_atoms),
        "instance_id": instance_id,
        "is_terminal": problem.is_goal(atom_set),
        "legal_actions": list(problem.legal_action_strings(atom_set)),
        "metadata": {
            "fixture": str(fixture_path),
            "schema_version": SCHEMA_VERSION,
            "source": "local_fast_forward_p0_expert_generator",
            "world_model": WORLD_MODEL,
        },
        "selected_action": selected_action,
        "state_atoms": sorted(atom_set),
        "state_id": state_id,
        "step_index": step_index,
        "trajectory_id": f"{instance_id}__fast_forward",
    }
    return canonicalize_trajectory_step(record)


def select_fast_forward_action(problem: BlocksworldProblem, state: Iterable[str]) -> BlocksworldAction | None:
    ranked = rank_legal_successors(problem, state)
    return ranked[0][1] if ranked else None


def successor_heuristics(problem: BlocksworldProblem, state: Iterable[str]) -> list[FastForwardSuccessor]:
    ranked = rank_legal_successors(problem, state)
    successors: list[FastForwardSuccessor] = []
    for heuristic, action, next_state in ranked:
        successors.append(
            FastForwardSuccessor(
                action=action.serialize(),
                heuristic_value=heuristic.heuristic_value,
                is_goal=problem.is_goal(next_state),
                relaxed_plan_length=heuristic.relaxed_plan_length,
                state_atoms=sorted(next_state),
                state_id=problem.state_id(next_state),
            )
        )
    return successors


def rank_legal_successors(
    problem: BlocksworldProblem,
    state: Iterable[str],
) -> list[tuple[RelaxedHeuristic, BlocksworldAction, AtomSet]]:
    atom_set = frozenset(state)
    ranked: list[tuple[RelaxedHeuristic, BlocksworldAction, AtomSet]] = []
    for action in problem.legal_actions(atom_set):
        next_state = problem.transition(atom_set, action)
        ranked.append((relaxed_plan_heuristic(problem, next_state), action, next_state))
    return sorted(ranked, key=lambda item: (item[0].heuristic_value, item[1].serialize()))


def relaxed_plan_heuristic(problem: BlocksworldProblem, state: Iterable[str]) -> RelaxedHeuristic:
    """Return the deterministic P0 relaxed-plan approximation for ``state``.

    This is not exact FF relaxed-plan extraction. It grounds only the supported
    four Blocksworld operators, starts from the concrete state, ignores every
    delete effect during relaxed reachability, and computes h_max-style atom
    costs. Supporter actions are then traced recursively from unsatisfied goals;
    the heuristic value is the number of unique supporter actions in that
    deterministic closure. Unreachable goals receive a large finite sentinel so
    generated JSON remains schema-valid and deterministic.
    """

    atom_set = frozenset(state)
    costs: dict[str, int] = {atom: 0 for atom in atom_set}
    supporters: dict[str, BlocksworldAction] = {}
    grounded_actions = _ground_actions(problem)

    changed = True
    while changed:
        changed = False
        for action in grounded_actions:
            preconditions = _positive_preconditions(action)
            if not all(precondition in costs for precondition in preconditions):
                continue
            candidate_cost = 1 + max((costs[precondition] for precondition in preconditions), default=0)
            for add_atom in _add_effects(action):
                current_cost = costs.get(add_atom)
                if current_cost is None or candidate_cost < current_cost:
                    costs[add_atom] = candidate_cost
                    supporters[add_atom] = action
                    changed = True

    goal_costs: dict[str, int | None] = {
        goal: costs.get(goal) for goal in sorted(problem.goal_atoms)
    }
    unreachable_goals = tuple(goal for goal, cost in goal_costs.items() if cost is None)
    relaxed_plan_actions = _extract_relaxed_plan_actions(problem.goal_atoms, atom_set, supporters)
    heuristic_value = UNREACHABLE_HEURISTIC_VALUE if unreachable_goals else len(relaxed_plan_actions)

    return RelaxedHeuristic(
        heuristic_value=heuristic_value,
        relaxed_plan_actions=relaxed_plan_actions,
        relaxed_plan_length=len(relaxed_plan_actions),
        goal_costs=goal_costs,
        supporter_actions={atom: action.serialize() for atom, action in supporters.items()},
        unreachable_goal_atoms=unreachable_goals,
    )


def _extract_relaxed_plan_actions(
    goals: Iterable[str],
    initial_atoms: AtomSet,
    supporters: dict[str, BlocksworldAction],
) -> tuple[str, ...]:
    selected: set[str] = set()
    visiting: set[str] = set()

    def visit(atom: str) -> None:
        if atom in initial_atoms or atom in visiting:
            return
        supporter = supporters.get(atom)
        if supporter is None:
            return
        visiting.add(atom)
        for precondition in _positive_preconditions(supporter):
            visit(precondition)
        selected.add(supporter.serialize())
        visiting.remove(atom)

    for goal_atom in sorted(goals):
        visit(goal_atom)
    return tuple(sorted(selected))


def _ground_actions(problem: BlocksworldProblem) -> tuple[BlocksworldAction, ...]:
    actions: list[BlocksworldAction] = []
    for block in problem.objects:
        actions.append(BlocksworldAction("pickup", (block,)))
        actions.append(BlocksworldAction("putdown", (block,)))
    for block in problem.objects:
        for other in problem.objects:
            if block == other:
                continue
            actions.append(BlocksworldAction("stack", (block, other)))
            actions.append(BlocksworldAction("unstack", (block, other)))
    return tuple(sorted(actions, key=lambda action: action.serialize()))


def _positive_preconditions(action: BlocksworldAction) -> tuple[str, ...]:
    if action.name == "pickup":
        block = action.args[0]
        return (
            canonical_atom("arm-empty"),
            canonical_atom("clear", block),
            canonical_atom("on-table", block),
        )
    if action.name == "putdown":
        return (canonical_atom("holding", action.args[0]),)
    if action.name == "stack":
        block, other = action.args
        return (canonical_atom("clear", other), canonical_atom("holding", block))
    if action.name == "unstack":
        block, other = action.args
        return (
            canonical_atom("arm-empty"),
            canonical_atom("clear", block),
            canonical_atom("on", block, other),
        )
    raise ValueError(f"unsupported action: {action.name}")


def _add_effects(action: BlocksworldAction) -> tuple[str, ...]:
    if action.name == "pickup":
        return (canonical_atom("holding", action.args[0]),)
    if action.name == "putdown":
        block = action.args[0]
        return (
            canonical_atom("arm-empty"),
            canonical_atom("clear", block),
            canonical_atom("on-table", block),
        )
    if action.name == "stack":
        block, other = action.args
        return (
            canonical_atom("arm-empty"),
            canonical_atom("clear", block),
            canonical_atom("on", block, other),
        )
    if action.name == "unstack":
        block, other = action.args
        return (canonical_atom("clear", other), canonical_atom("holding", block))
    raise ValueError(f"unsupported action: {action.name}")


__all__ = [
    "FAST_FORWARD_TIE_BREAK_RULE",
    "P0_APPROXIMATION_ID",
    "UNREACHABLE_HEURISTIC_VALUE",
    "build_fast_forward_step_record",
    "generate_fast_forward_trajectory",
    "rank_legal_successors",
    "relaxed_plan_heuristic",
    "select_fast_forward_action",
    "successor_heuristics",
]
