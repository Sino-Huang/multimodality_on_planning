from __future__ import annotations

import json
from dataclasses import replace
from typing import Mapping, NoReturn, Sequence

from .graphplan_replay import project_graphplan_replay
from .pddl import Atom, GroundAction, PDDLError, canonical_atom, ground_actions, normalize_action_string, parse_task
from .trace_contracts import CONCRETE_EVENT_KINDS, TRACE_CONTRACT_VERSION, FrozenSourceIdentity, TraceContractError, TraversalEvent, project_traversal_events
from .traversal_state_types import (
    JSONMapping,
    JSONValue,
    STATE_SOURCES,
    TraversalCandidateExclusion,
    TraversalProjectionInput,
    TraversalStateCandidate,
    TraversalStateProjection,
    exclusion,
    state_asset_hash,
)


def project_traversal_state_candidates(request: TraversalProjectionInput) -> TraversalStateProjection:
    """Extract render-eligible concrete states without merging their search events."""
    try:
        events = project_traversal_events(request.source_identity, request.source_row)
    except TraceContractError as error:
        return TraversalStateProjection(
            (),
            (_exclusion(request.source_identity, request.source_identity.planner, _source_exclusion_id(request.source_identity), error.reason),),
        )
    task = parse_task(request.domain_path, request.problem_path)
    if task.unsupported_features:
        return TraversalStateProjection(
            (),
            (
                _exclusion(
                    request.source_identity,
                    request.source_identity.planner,
                    _source_exclusion_id(request.source_identity),
                    f"unsupported_pddl_features:{','.join(task.unsupported_features)}",
                ),
            ),
        )
    grounded, grounding_reason = ground_actions(
        task,
        max_grounded_actions=request.max_grounded_actions,
        max_grounded_atoms=request.max_grounded_atoms,
    )
    actions = {action.canonical: action for action in grounded}
    if request.source_identity.planner == "graphplan":
        return project_graphplan_replay(events, task.init, task.goal, actions, grounding_reason)
    candidates: list[TraversalStateCandidate] = []
    exclusions: list[TraversalCandidateExclusion] = []
    for event in events:
        _project_event(event, actions, grounding_reason, candidates, exclusions)
    return TraversalStateProjection(tuple(candidates), tuple(exclusions))


def _project_event(
    event: TraversalEvent,
    actions: Mapping[str, GroundAction],
    grounding_reason: str | None,
    candidates: list[TraversalStateCandidate],
    exclusions: list[TraversalCandidateExclusion],
) -> None:
    if event.supervision_mode != "concrete_state":
        exclusions.append(_exclusion(event.source_identity, event.planner, event.node_id, "non_concrete_event"))
        return
    try:
        parent_atoms = _recorded_atoms(event)
    except PDDLError as error:
        exclusions.append(_exclusion(event.source_identity, event.planner, event.node_id, f"invalid_parent_atoms:{error}"))
        return
    parent = _candidate(event, _event_id(event, "selected"), None, "selected_state", "trace_recorded", None, parent_atoms)
    candidates.append(parent)
    for index, successor in enumerate(_successors(event)):
        successor_id = _event_id(event, f"successor:{index}")
        if not isinstance(successor, dict):
            exclusions.append(_exclusion(event.source_identity, event.planner, successor_id, "malformed_successor_record"))
            continue
        result = _successor_candidate(event, successor_id, parent, successor, actions, grounding_reason)
        match result:
            case TraversalStateCandidate():
                candidates.append(result)
            case TraversalCandidateExclusion():
                exclusions.append(result)
            case unexpected:
                assert_never(unexpected)


def _successor_candidate(
    event: TraversalEvent,
    successor_id: str,
    parent: TraversalStateCandidate,
    successor: JSONMapping,
    actions: Mapping[str, GroundAction],
    grounding_reason: str | None,
) -> TraversalStateCandidate | TraversalCandidateExclusion:
    semantic = successor.get("event_kind")
    if not isinstance(semantic, str):
        return _exclusion(event.source_identity, event.planner, successor_id, "missing_successor_event_kind")
    if semantic not in CONCRETE_EVENT_KINDS:
        return _exclusion(event.source_identity, event.planner, successor_id, f"unsupported_successor_event_kind:{semantic}")
    if grounding_reason is not None:
        return _exclusion(event.source_identity, event.planner, successor_id, grounding_reason)
    raw_action = successor.get("action")
    if not isinstance(raw_action, str):
        return _exclusion(event.source_identity, event.planner, successor_id, "missing_successor_action")
    try:
        normalized_action = normalize_action_string(raw_action)
    except PDDLError:
        return _exclusion(event.source_identity, event.planner, successor_id, "invalid_action")
    action = actions.get(normalized_action)
    if action is None:
        return _exclusion(event.source_identity, event.planner, successor_id, "unknown_action")
    state = _state_from_atoms(parent.state_atoms)
    if not action.preconditions.issubset(state):
        return _exclusion(event.source_identity, event.planner, successor_id, "inapplicable_action")
    reconstructed = frozenset((state - action.del_effects) | action.add_effects)
    reconstructed_atoms = _canonical_atoms(reconstructed)
    recorded = successor.get("state_atoms")
    if recorded is None and event.planner == "ff":
        return _exclusion(event.source_identity, event.planner, successor_id, "ff_missing_recorded_successor_state")
    if recorded is not None:
        try:
            recorded_atoms = _recorded_atom_list(recorded)
        except PDDLError as error:
            return _exclusion(event.source_identity, event.planner, successor_id, f"invalid_successor_atoms:{error}")
        if recorded_atoms != reconstructed_atoms:
            return _exclusion(event.source_identity, event.planner, successor_id, "successor_atom_mismatch")
        return replace(_candidate(event, successor_id, parent.event_id, "successor", "trace_recorded", normalized_action, recorded_atoms), event_kind=semantic)
    return replace(_candidate(event, successor_id, parent.event_id, "successor", "pddl_action_reconstruction", normalized_action, reconstructed_atoms), event_kind=semantic)


def _recorded_atoms(event: TraversalEvent) -> tuple[str, ...]:
    key = "selected_state_atoms" if event.planner == "gbfs" else "state_atoms"
    return _recorded_atom_list(event.planner_metadata.get(key))


def _successors(event: TraversalEvent) -> tuple[JSONValue, ...]:
    metadata = event.planner_metadata
    selected = metadata.get("selected_successor")
    if selected is None:
        selected = metadata.get("selected_goal_successor")
    listed = metadata.get("successor_heuristics") or metadata.get("successors") or []
    values = [selected] if selected is not None else []
    if isinstance(listed, list):
        values.extend(listed)
    unique: list[JSONValue] = []
    seen_records: set[str] = set()
    for value in values:
        key = json.dumps(value, sort_keys=True)
        if key not in seen_records:
            seen_records.add(key)
            unique.append(value)
    return tuple(unique)


def _recorded_atom_list(value: JSONValue | None) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(atom, str) for atom in value):
        raise PDDLError("state_atoms must be a string array")
    return _canonical_atoms(_state_from_atoms(tuple(value)))


def _state_from_atoms(atoms: Sequence[str]) -> frozenset[Atom]:
    parsed: list[Atom] = []
    for raw_atom in atoms:
        tokens = raw_atom.strip().lower().removeprefix("(").removesuffix(")").split()
        if not tokens or canonical_atom(tuple(tokens)) != raw_atom.strip().lower():
            raise PDDLError("noncanonical state atom")
        parsed.append(tuple(tokens))
    if len(set(parsed)) != len(parsed):
        raise PDDLError("duplicate state atom")
    return frozenset(parsed)


def _canonical_atoms(state: frozenset[Atom]) -> tuple[str, ...]:
    return tuple(sorted(canonical_atom(atom) for atom in state))


def _candidate(
    event: TraversalEvent,
    event_id: str,
    parent_event_id: str | None,
    state_role: str,
    state_source: STATE_SOURCES,
    normalized_action: str | None,
    state_atoms: tuple[str, ...],
) -> TraversalStateCandidate:
    return TraversalStateCandidate(
        event_id,
        parent_event_id,
        event.source_identity,
        event.planner,
        TRACE_CONTRACT_VERSION,
        event.event_kind,
        state_role,
        state_source,
        normalized_action,
        state_atoms,
        state_asset_hash(state_atoms),
    )


def _exclusion(identity: FrozenSourceIdentity, planner: str, event_id: str, reason: str) -> TraversalCandidateExclusion:
    return exclusion(identity, planner, event_id, reason)


def _source_exclusion_id(identity: FrozenSourceIdentity) -> str:
    return f"{identity.source_record_sha256}:source"


def _event_id(event: TraversalEvent, role: str) -> str:
    identity = event.source_identity
    return f"{identity.source_root_id}:{identity.source_jsonl}:{identity.source_line_index}:{event.node_id}:{role}"


def assert_never(value: NoReturn) -> NoReturn:
    raise AssertionError(f"unreachable value: {value!r}")
