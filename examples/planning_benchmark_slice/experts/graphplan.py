from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

from ..benchmark_loop import shortest_action_plan
from ..blocksworld import AtomSet, BlocksworldAction, BlocksworldProblem, canonical_atom
from ..trajectory_schema import SCHEMA_VERSION, canonicalize_trajectory_step
from .bfs import WORLD_MODEL


GRAPHPLAN_APPROXIMATION_ID = "deterministic_p0_action_mutex_only_graphplan"
DEFAULT_MAX_LAYERS = 4


@dataclass(frozen=True)
class GraphplanLayer:
    proposition_layers: list[dict[str, Any]]
    action_layers: list[dict[str, Any]]
    mutex_pairs: list[list[str]]
    extraction: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "action_layers": self.action_layers,
            "extraction": self.extraction,
            "mutex_pairs": self.mutex_pairs,
            "proposition_layers": self.proposition_layers,
        }


def generate_graphplan_trajectory(
    *,
    problem: BlocksworldProblem,
    instance_id: str,
    fixture_path: Path,
    max_steps: int = 64,
) -> list[dict[str, Any]]:
    """Generate deterministic Graphplan-style records for Blocksworld.

    The Phase 1-3 proposal explicitly permits a feasibility simplification that
    records action-level mutex only. This generator still emits Graphplan layer
    structure at every selected trajectory step: proposition layers, applicable
    action layers, next proposition layers, action mutex pairs, and extraction
    status. Proposition mutex propagation and exhaustive backward search are not
    implemented for P0.
    """

    records: list[dict[str, Any]] = []
    current_state = problem.initial_state()

    for step_index in range(max_steps):
        if problem.is_goal(current_state):
            break
        plan = shortest_action_plan(problem, current_state, max_depth=max_steps)
        if not plan:
            break
        selected_action = plan[0]
        records.append(
            build_graphplan_step_record(
                problem=problem,
                instance_id=instance_id,
                fixture_path=fixture_path,
                state=current_state,
                step_index=step_index,
                selected_action=selected_action,
            )
        )
        current_state = problem.transition(current_state, selected_action)

    return records


def build_graphplan_step_record(
    *,
    problem: BlocksworldProblem,
    instance_id: str,
    fixture_path: Path,
    state: Iterable[str],
    step_index: int,
    selected_action: BlocksworldAction,
    max_layers: int = DEFAULT_MAX_LAYERS,
) -> dict[str, Any]:
    atom_set = frozenset(state)
    graph = build_graphplan_layers(problem, atom_set, max_layers=max_layers)
    selected_successor = problem.transition(atom_set, selected_action)

    record = {
        "algorithm": "graphplan",
        "domain": "blocksworld",
        "goal_atoms": sorted(problem.goal_atoms),
        "graphplan": graph.to_payload(),
        "instance_id": instance_id,
        "is_terminal": problem.is_goal(atom_set),
        "legal_actions": list(problem.legal_action_strings(atom_set)),
        "metadata": {
            "fixture": str(fixture_path),
            "schema_version": SCHEMA_VERSION,
            "source": "local_graphplan_p0_expert_generator",
            "world_model": WORLD_MODEL,
        },
        "selected_action": selected_action.serialize(),
        "state_atoms": sorted(atom_set),
        "state_id": problem.state_id(atom_set),
        "step_index": step_index,
        "trajectory_id": f"{instance_id}__graphplan",
    }
    record["graphplan"]["extraction"]["selected_action"] = selected_action.serialize()
    record["graphplan"]["extraction"]["selected_successor_id"] = problem.state_id(selected_successor)
    return canonicalize_trajectory_step(record)


def build_graphplan_layers(
    problem: BlocksworldProblem,
    state: Iterable[str],
    *,
    max_layers: int = DEFAULT_MAX_LAYERS,
) -> GraphplanLayer:
    if max_layers <= 0:
        raise ValueError("max_layers must be positive")

    current_layer = frozenset(state)
    proposition_layers: list[dict[str, Any]] = [_proposition_layer(0, current_layer)]
    action_layers: list[dict[str, Any]] = []
    all_mutex_pairs: list[list[str]] = []
    selected_goal_layer: int | None = 0 if problem.goal_atoms.issubset(current_layer) else None

    for layer_index in range(max_layers):
        actions = tuple(problem.legal_actions(current_layer))
        mutex_pairs = action_mutex_pairs(actions)
        serialized_mutex_pairs = [[left.serialize(), right.serialize()] for left, right in mutex_pairs]
        all_mutex_pairs.extend(serialized_mutex_pairs)

        next_layer = _next_proposition_layer(problem, current_layer, actions)
        action_layers.append(
            {
                "actions": [action.serialize() for action in actions],
                "layer_index": layer_index,
                "mutex_pairs": serialized_mutex_pairs,
                "next_layer_index": layer_index + 1,
            }
        )
        proposition_layers.append(_proposition_layer(layer_index + 1, next_layer))

        if selected_goal_layer is None and problem.goal_atoms.issubset(next_layer):
            selected_goal_layer = layer_index + 1
            break
        if next_layer == current_layer:
            break
        current_layer = next_layer

    goal_present_without_mutex = selected_goal_layer is not None
    extraction = {
        "approximation": GRAPHPLAN_APPROXIMATION_ID,
        "goal_present_without_mutex": goal_present_without_mutex,
        "mutex_scope": "action_level_only",
        "no_goods": [],
        "proposition_mutex_computed": False,
        "selected_goal_layer": selected_goal_layer,
        "simplification_note": (
            "P0 follows the proposal feasibility simplification: action mutex pairs are recorded; "
            "proposition mutex propagation and exhaustive backward extraction are not required."
        ),
    }

    return GraphplanLayer(
        proposition_layers=proposition_layers,
        action_layers=action_layers,
        mutex_pairs=_unique_mutex_pairs(all_mutex_pairs),
        extraction=extraction,
    )


def action_mutex_pairs(actions: Iterable[BlocksworldAction]) -> list[tuple[BlocksworldAction, BlocksworldAction]]:
    pairs: list[tuple[BlocksworldAction, BlocksworldAction]] = []
    sorted_actions = tuple(sorted(actions, key=lambda action: action.serialize()))
    for left, right in combinations(sorted_actions, 2):
        if are_action_mutex(left, right):
            pairs.append((left, right))
    return pairs


def are_action_mutex(left: BlocksworldAction, right: BlocksworldAction) -> bool:
    left_preconditions = set(positive_preconditions(left))
    right_preconditions = set(positive_preconditions(right))
    left_adds = set(add_effects(left))
    right_adds = set(add_effects(right))
    left_deletes = set(delete_effects(left))
    right_deletes = set(delete_effects(right))

    inconsistent_effects = bool((left_adds & right_deletes) or (right_adds & left_deletes))
    interference = bool((left_deletes & right_preconditions) or (right_deletes & left_preconditions))
    single_gripper_competition = _compete_for_single_gripper(left_preconditions, right_preconditions)
    same_object_competition = _compete_for_same_manipulated_block(left, right)
    return inconsistent_effects or interference or single_gripper_competition or same_object_competition


def positive_preconditions(action: BlocksworldAction) -> tuple[str, ...]:
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


def add_effects(action: BlocksworldAction) -> tuple[str, ...]:
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


def delete_effects(action: BlocksworldAction) -> tuple[str, ...]:
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


def _next_proposition_layer(
    problem: BlocksworldProblem,
    current_layer: AtomSet,
    actions: Iterable[BlocksworldAction],
) -> AtomSet:
    next_atoms: set[str] = set()
    for action in actions:
        next_atoms.update(problem.transition(current_layer, action))
    if not next_atoms:
        next_atoms.update(current_layer)
    return frozenset(next_atoms)


def _proposition_layer(layer_index: int, atoms: Iterable[str]) -> dict[str, Any]:
    return {
        "atoms": sorted(frozenset(atoms)),
        "layer_index": layer_index,
    }


def _compete_for_single_gripper(left: set[str], right: set[str]) -> bool:
    if canonical_atom("arm-empty") in left and canonical_atom("arm-empty") in right:
        return True
    left_holding = sorted(atom for atom in left if atom.startswith("holding("))
    right_holding = sorted(atom for atom in right if atom.startswith("holding("))
    return bool(left_holding and right_holding and left_holding != right_holding)


def _compete_for_same_manipulated_block(left: BlocksworldAction, right: BlocksworldAction) -> bool:
    return left.args[0] == right.args[0]


def _unique_mutex_pairs(pairs: Iterable[Iterable[str]]) -> list[list[str]]:
    unique = {tuple(sorted(str(item) for item in pair)) for pair in pairs}
    return [list(pair) for pair in sorted(unique)]


__all__ = [
    "DEFAULT_MAX_LAYERS",
    "GRAPHPLAN_APPROXIMATION_ID",
    "action_mutex_pairs",
    "add_effects",
    "are_action_mutex",
    "build_graphplan_layers",
    "build_graphplan_step_record",
    "delete_effects",
    "generate_graphplan_trajectory",
    "positive_preconditions",
]
