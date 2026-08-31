"""Independent landmark extraction, progression, and A* evidence replay."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .astar_replay import AStarReplayError, AStarReplaySummary
from .pddl_state import CanonicalState, GroundedAction, PDDLStateAuthority
from .strips_relaxation import GroundedPositiveSTRIPSTask, extract_grounded_positive_strips


@dataclass(frozen=True, slots=True)
class _Progress:
    accepted: frozenset[str]


@dataclass(frozen=True, slots=True)
class _Candidate:
    action: GroundedAction
    target: CanonicalState
    target_node_id: str
    target_progress: _Progress
    progression: dict[str, list[str]]
    progression_delta: dict[str, list[str]]
    g: int
    h: int
    prior_best: int | None
    closed: bool
    frontier: bool

    @property
    def f(self) -> int:
        return self.g + self.h

    def to_dict(self) -> dict[str, object]:
        dominated = self.prior_best is not None and self.prior_best <= self.g
        return {
            "action": {"args": list(self.action.args), "name": self.action.name},
            "best_cost": self.prior_best,
            "closed": self.closed,
            "dominated": dominated,
            "f": self.f,
            "frontier": self.frontier,
            "g": self.g,
            "h": self.h,
            "progression": self.progression,
            "progression_delta": self.progression_delta,
            "pruned": dominated,
            "target_node_id": self.target_node_id,
            "target_state_id": self.target.state_id,
        }


def replay_landmark_astar_events(
    states_payload: Mapping[str, Any],
    events: list[Mapping[str, Any]],
    *,
    authority: PDDLStateAuthority,
    max_expansions: int,
    accepted_delta_limit: int,
    persisted_catalog: object,
) -> AStarReplaySummary:
    task = extract_grounded_positive_strips(authority)
    landmarks, edges = _extract_catalog(task)
    catalog = {"edges": [list(edge) for edge in edges], "landmarks": list(landmarks)}
    if persisted_catalog != catalog:
        raise AStarReplayError("persisted landmark catalog differs from independent extraction")
    predecessors = {landmark: set() for landmark in landmarks}
    for predecessor, landmark in edges:
        predecessors[landmark].add(predecessor)

    initial = authority.initial_state
    initial_progress = _advance(_Progress(frozenset()), initial, landmarks, predecessors, task)
    initial_node = _node_id(initial, initial_progress)
    initial_h = _value(initial, initial_progress, landmarks, edges, task)
    states = {initial.state_id: initial}
    node_states = {initial_node: initial}
    node_progress = {initial_node: initial_progress}
    best_g = {initial_node: 0}
    closed_g: dict[str, int] = {}
    frontier = {initial_node: (initial_h, 0, 0)}
    next_serial = 1
    accepted_deltas: deque[dict[str, object]] = deque(maxlen=accepted_delta_limit)
    decision_count = 0
    reopen_count = 0

    if len(events) > max_expansions:
        raise AStarReplayError("landmark A* evidence exceeds its expansion budget")
    for expansion_index, event in enumerate(events):
        before = _frontier_snapshot(frontier)
        if not before:
            raise AStarReplayError("landmark A* expands after frontier exhaustion")
        node_id = str(before[0]["state_id"])
        state = node_states[node_id]
        progress = node_progress[node_id]
        if authority.is_goal(state):
            raise AStarReplayError("landmark A* expands a popped goal")
        if (
            event.get("index") != expansion_index
            or event.get("expansion_index") != expansion_index
            or event.get("expanded_state_id") != node_id
            or event.get("frontier_before") != before
        ):
            raise AStarReplayError(f"landmark A* frontier-head invariant failed at event {expansion_index}")
        _, _, g = frontier[node_id]
        h = _value(state, progress, landmarks, edges, task)
        if event.get("heuristic") != {"f": g + h, "g": g, "name": "landmark_count", "value": h}:
            raise AStarReplayError(f"landmark A* h/f differs at event {expansion_index}")
        actions = authority.applicable_actions(state)
        observation_candidates = [
            _candidate(
                authority, state, progress, action, g + 1, best_g, closed_g, frontier,
                landmarks, edges, predecessors, task,
            ).to_dict()
            for action in actions
        ]
        observation = _model_input(
            authority, node_id, state, progress, g, h, observation_candidates,
            accepted_deltas, best_g, closed_g, frontier, catalog, landmarks, edges, task,
        )
        if event.get("observation") != observation:
            raise AStarReplayError(f"landmark A* observation differs at event {expansion_index}")

        frontier.pop(node_id)
        candidates = tuple(
            _candidate(
                authority, state, progress, action, g + 1, best_g, closed_g, frontier,
                landmarks, edges, predecessors, task,
            )
            for action in actions
        )
        serial_by_target: dict[str, int] = {}
        for offset, candidate in enumerate(candidates):
            serial_by_target.setdefault(candidate.target_node_id, next_serial + offset)
        next_serial += len(candidates)
        decisions = event.get("decisions")
        if not isinstance(decisions, list):
            raise AStarReplayError("landmark A* decisions are malformed")
        submitted: set[GroundedAction] = set()
        for decision in decisions:
            visible = [
                _candidate(
                    authority, state, progress, action, g + 1, best_g, closed_g, frontier,
                    landmarks, edges, predecessors, task,
                ).to_dict()
                for action in actions
                if action not in submitted
            ]
            expected_input = _model_input(
                authority, node_id, state, progress, g, h, visible,
                accepted_deltas, best_g, closed_g, frontier, catalog, landmarks, edges, task,
            )
            if not isinstance(decision, Mapping) or decision.get("input") != expected_input:
                raise AStarReplayError(f"landmark A* decision input differs at event {expansion_index}")
            operation = _decode_operation(decision.get("operation"))
            if (
                not _raw_operation_matches(decision.get("raw_model_output"), operation)
                or operation["source_state_id"] != node_id
            ):
                raise AStarReplayError(f"landmark A* operation provenance differs at event {expansion_index}")
            action_data = operation["action"]
            action = GroundedAction(str(action_data["name"]), tuple(action_data["args"]))
            candidate = next((item for item in candidates if item.action == action), None)
            if candidate is None or action in submitted:
                raise AStarReplayError(f"landmark A* operation is not an exact candidate at event {expansion_index}")
            submitted.add(action)
            decision_count += 1
            target_node = candidate.target_node_id
            previous = best_g.get(target_node)
            status = "dominated"
            if previous is None or candidate.g < previous:
                applied = authority.apply(state, action).target_state
                if applied != candidate.target:
                    raise AStarReplayError("landmark A* transition preview differs")
                states[applied.state_id] = applied
                node_states[target_node] = applied
                node_progress[target_node] = candidate.target_progress
                best_g[target_node] = candidate.g
                if target_node in closed_g:
                    del closed_g[target_node]
                    reopen_count += 1
                    status = "reopened"
                elif target_node in frontier:
                    status = "improved"
                else:
                    status = "enqueued"
                frontier[target_node] = (candidate.f, serial_by_target[target_node], candidate.g)
                accepted_deltas.append(
                    {
                        "f": candidate.f,
                        "g": candidate.g,
                        "h": candidate.h,
                        "node_id": target_node,
                        "progression": candidate.progression,
                        "progression_delta": candidate.progression_delta,
                        "state_id": applied.state_id,
                        "status": status,
                    }
                )
            expected_runtime = {
                "accepted": True,
                "budget_charge": 0,
                "f": candidate.f,
                "g": candidate.g,
                "h": candidate.h,
                "progression": candidate.progression,
                "progression_delta": candidate.progression_delta,
                "status": status,
                "target_node_id": target_node,
                "target_state_id": candidate.target.state_id,
            }
            if decision.get("trusted_runtime_result") != expected_runtime:
                raise AStarReplayError(f"landmark A* runtime/progression differs at event {expansion_index}")
        if submitted != {candidate.action for candidate in candidates}:
            raise AStarReplayError(f"landmark A* expansion omitted candidates at event {expansion_index}")
        closed_g[node_id] = best_g[node_id]
        if event.get("frontier_after") != _frontier_snapshot(frontier):
            raise AStarReplayError(f"landmark A* frontier priority differs at event {expansion_index}")
        if event.get("invariants") != {
            "best_g_bookkeeping": True,
            "frontier_head_expanded": True,
            "hold": True,
            "priority": ["f", "generation_serial"],
            "reopen_on_cheaper_path": True,
        }:
            raise AStarReplayError(f"landmark A* persisted invariant differs at event {expansion_index}")

    if len(events) == max_expansions:
        termination, goal_reached = "expansion_budget", False
    else:
        head = _frontier_snapshot(frontier)
        if not head:
            termination, goal_reached = "frontier_exhausted", False
        elif authority.is_goal(node_states[str(head[0]["state_id"])]):
            termination, goal_reached = "goal_reached", True
        else:
            raise AStarReplayError("landmark A* evidence stops before a terminal condition")
    expected_states = {
        state_id: {"atoms": list(state.atoms), "authority_id": state.authority_id, "fluents": list(state.fluents)}
        for state_id, state in states.items()
    }
    if dict(states_payload) != expected_states:
        raise AStarReplayError("landmark A* state table differs from transitions")
    return AStarReplaySummary(
        decision_count, len(events), goal_reached, reopen_count, frozenset(states), termination
    )


def _extract_catalog(task: GroundedPositiveSTRIPSTask) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    landmarks = set(task.goals)
    edges: set[tuple[str, str]] = set()
    processed: set[str] = set()
    while pending := sorted(landmarks - processed):
        landmark = pending[0]
        processed.add(landmark)
        if landmark in task.initial_facts:
            continue
        reachable = set(task.initial_facts)
        changed = True
        while changed:
            changed = False
            for operator in task.operators:
                if not operator.preconditions <= reachable:
                    continue
                before = len(reachable)
                reachable.update(operator.add_effects - {landmark})
                changed = changed or len(reachable) != before
        achievers = [
            operator for operator in task.operators
            if landmark in operator.add_effects and operator.preconditions <= reachable
        ]
        if not achievers:
            continue
        common = set(achievers[0].preconditions)
        for achiever in achievers[1:]:
            common.intersection_update(achiever.preconditions)
        for predecessor in sorted(common - set(task.static_facts) - {landmark}):
            landmarks.add(predecessor)
            edges.add((predecessor, landmark))
    return tuple(sorted(landmarks)), tuple(sorted(edges))


def _advance(
    progress: _Progress,
    state: CanonicalState,
    landmarks: tuple[str, ...],
    predecessors: Mapping[str, set[str]],
    task: GroundedPositiveSTRIPSTask,
) -> _Progress:
    accepted = set(progress.accepted)
    true_facts = set(state.atoms) | set(task.static_facts)
    changed = True
    while changed:
        changed = False
        for landmark in landmarks:
            if landmark not in accepted and landmark in true_facts and predecessors[landmark] <= accepted:
                accepted.add(landmark)
                changed = True
    return _Progress(frozenset(accepted))


def _progress_payload(
    state: CanonicalState,
    progress: _Progress,
    landmarks: tuple[str, ...],
    edges: tuple[tuple[str, str], ...],
    task: GroundedPositiveSTRIPSTask,
) -> dict[str, list[str]]:
    unaccepted = set(landmarks) - progress.accepted
    true_facts = set(state.atoms) | set(task.static_facts)
    required = set(task.goals) | {predecessor for predecessor, child in edges if child in unaccepted}
    needed = {fact for fact in progress.accepted if fact not in true_facts and fact in required}
    return {"accepted": sorted(progress.accepted), "needed_again": sorted(needed), "unaccepted": sorted(unaccepted)}


def _value(state, progress, landmarks, edges, task) -> int:
    payload = _progress_payload(state, progress, landmarks, edges, task)
    return len(payload["unaccepted"]) + len(payload["needed_again"])


def _node_id(state: CanonicalState, progress: _Progress) -> str:
    key = json.dumps(sorted(progress.accepted), ensure_ascii=True, separators=(",", ":"))
    return _canonical_text({"progress_key": key, "state_id": state.state_id})


def _candidate(authority, state, progress, action, g, best_g, closed_g, frontier, landmarks, edges, predecessors, task):
    target = authority.preview_apply(state, action).target_state
    target_progress = _advance(progress, target, landmarks, predecessors, task)
    target_node = _node_id(target, target_progress)
    source_facts = set(state.atoms) | set(task.static_facts)
    target_facts = set(target.atoms) | set(task.static_facts)
    delta = {
        "newly_accepted": sorted(target_progress.accepted - progress.accepted),
        "re_achieved": sorted(progress.accepted & (target_facts - source_facts)),
    }
    return _Candidate(
        action, target, target_node, target_progress,
        _progress_payload(target, target_progress, landmarks, edges, task), delta,
        g, _value(target, target_progress, landmarks, edges, task), best_g.get(target_node),
        target_node in closed_g, target_node in frontier,
    )


def _frontier_snapshot(frontier):
    return [
        {"f": f, "g": g, "generation_serial": serial, "h": f - g, "priority": [f, serial], "state_id": node}
        for f, serial, node, g in sorted((f, serial, node, g) for node, (f, serial, g) in frontier.items())
    ]


def _model_input(
    authority,
    node_id,
    state,
    progress,
    g,
    h,
    candidates,
    deltas,
    best_g,
    closed_g,
    frontier,
    catalog,
    landmarks,
    edges,
    task,
):
    snapshot = _frontier_snapshot(frontier)
    return {
        "accepted_deltas": list(deltas),
        "algorithm": "astar_landmark_count",
        "current": {
            "f": g + h, "g": g, "h": h, "node_id": node_id,
            "progression": _progress_payload(state, progress, landmarks, edges, task),
            "state_atoms": list(state.atoms), "state_id": state.state_id,
        },
        "heuristic_context": catalog,
        "search_memory": {
            "best_cost_count": len(best_g), "closed_count": len(closed_g),
            "frontier_count": len(snapshot), "frontier_head": snapshot[0] if snapshot else None,
            "visited_count": len(best_g),
        },
        "successor_candidates": candidates,
        "task_context": authority.task_context(),
    }


def _decode_operation(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {"action", "source_state_id"}:
        raise AStarReplayError("landmark A* operation has invalid fields")
    action = payload["action"]
    if not isinstance(action, dict) or set(action) != {"args", "name"} or not isinstance(action["args"], list):
        raise AStarReplayError("landmark A* operation is malformed")
    return payload


def _canonical_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _raw_operation_matches(raw_output: object, operation: Mapping[str, Any]) -> bool:
    if not isinstance(raw_output, str):
        return False
    try:
        return json.loads(raw_output) == operation
    except json.JSONDecodeError:
        return False


__all__ = ["replay_landmark_astar_events"]
