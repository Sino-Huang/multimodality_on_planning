from __future__ import annotations

from typing import Mapping

from .pddl import Atom, GroundAction, PDDLError, canonical_atom, normalize_action_string
from .trace_contracts import TRACE_CONTRACT_VERSION, TraversalEvent
from .traversal_state_types import (
    TraversalCandidateExclusion,
    TraversalStateCandidate,
    TraversalStateProjection,
    exclusion,
    state_asset_hash,
)


def project_graphplan_replay(
    events: tuple[TraversalEvent, ...],
    init: frozenset[Atom],
    goal: frozenset[Atom],
    actions: Mapping[str, GroundAction],
    grounding_reason: str | None,
) -> TraversalStateProjection:
    """Project only a fully validated Graphplan extraction into replay states."""
    candidates: list[TraversalStateCandidate] = []
    exclusions: list[TraversalCandidateExclusion] = []
    for event in events:
        if event.event_kind != "extraction":
            exclusions.append(exclusion(event.source_identity, event.planner, event.node_id, f"graphplan_nonvisual_event:{event.event_kind}"))
            continue
        result = _replay_extraction(event, init, goal, actions, grounding_reason)
        if isinstance(result, TraversalCandidateExclusion):
            exclusions.append(result)
        else:
            candidates.extend(result)
    return TraversalStateProjection(tuple(candidates), tuple(exclusions))


def _replay_extraction(
    event: TraversalEvent,
    init: frozenset[Atom],
    goal: frozenset[Atom],
    actions: Mapping[str, GroundAction],
    grounding_reason: str | None,
) -> tuple[TraversalStateCandidate, ...] | TraversalCandidateExclusion:
    if grounding_reason is not None:
        return exclusion(event.source_identity, event.planner, event.node_id, grounding_reason)
    selected_plan = event.planner_metadata["selected_plan"]
    if not isinstance(selected_plan, list) or not all(isinstance(action, str) for action in selected_plan):
        return exclusion(event.source_identity, event.planner, event.node_id, "malformed_extraction_plan")
    transitions: list[tuple[str, tuple[str, ...]]] = []
    state = init
    for index, raw_action in enumerate(selected_plan):
        try:
            normalized_action = normalize_action_string(raw_action)
        except PDDLError:
            return exclusion(event.source_identity, event.planner, _replay_event_id(event, index), "invalid_extraction_action")
        action = actions.get(normalized_action)
        if action is None:
            return exclusion(event.source_identity, event.planner, _replay_event_id(event, index), "unknown_extraction_action")
        if not action.preconditions.issubset(state):
            return exclusion(event.source_identity, event.planner, _replay_event_id(event, index), "inapplicable_extraction_action")
        state = frozenset((state - action.del_effects) | action.add_effects)
        transitions.append((normalized_action, _canonical_atoms(state)))
    if not goal.issubset(state):
        return exclusion(event.source_identity, event.planner, event.node_id, "extraction_goal_not_satisfied")
    return _replay_candidates(event, _canonical_atoms(init), transitions)


def _replay_candidates(
    event: TraversalEvent,
    initial_atoms: tuple[str, ...],
    transitions: list[tuple[str, tuple[str, ...]]],
) -> tuple[TraversalStateCandidate, ...]:
    initial_id = _replay_event_id(event, 0)
    candidates = [
        TraversalStateCandidate(
            event_id=initial_id,
            parent_event_id=event.node_id,
            source_identity=event.source_identity,
            planner=event.planner,
            trace_contract_version=TRACE_CONTRACT_VERSION,
            event_kind="extracted_plan_replay",
            state_role="extracted_plan_initial",
            state_source="extracted_plan_replay",
            normalized_action=None,
            state_atoms=initial_atoms,
            state_asset_hash=state_asset_hash(initial_atoms),
            extraction_event_id=event.node_id,
            extraction_step_index=0,
        )
    ]
    parent_event_id = initial_id
    for index, (action, atoms) in enumerate(transitions, start=1):
        candidate_id = _replay_event_id(event, index)
        candidates.append(
            TraversalStateCandidate(
                event_id=candidate_id,
                parent_event_id=parent_event_id,
                source_identity=event.source_identity,
                planner=event.planner,
                trace_contract_version=TRACE_CONTRACT_VERSION,
                event_kind="extracted_plan_replay",
                state_role="extracted_plan_successor",
                state_source="extracted_plan_replay",
                normalized_action=action,
                state_atoms=atoms,
                state_asset_hash=state_asset_hash(atoms),
                extraction_event_id=event.node_id,
                extraction_step_index=index,
            )
        )
        parent_event_id = candidate_id
    return tuple(candidates)


def _canonical_atoms(state: frozenset[Atom]) -> tuple[str, ...]:
    return tuple(sorted(canonical_atom(atom) for atom in state))


def _replay_event_id(event: TraversalEvent, step_index: int) -> str:
    identity = event.source_identity
    return f"{identity.source_root_id}:{identity.source_jsonl}:{identity.source_line_index}:{event.node_id}:extracted-plan-replay:{step_index}"
