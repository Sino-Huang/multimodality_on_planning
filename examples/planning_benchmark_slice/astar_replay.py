"""Independent mechanical replay for persisted A* h_max evidence."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .astar_hmax import HMaxHeuristic
from .pddl_state import CanonicalState, GroundedAction, PDDLStateAuthority


class AStarReplayError(ValueError):
    """Raised when persisted A* evidence violates a mechanical invariant."""


@dataclass(frozen=True, slots=True)
class AStarReplaySummary:
    decision_count: int
    expansion_count: int
    goal_reached: bool
    reopen_count: int
    state_ids: frozenset[str]
    termination: str


@dataclass(frozen=True, slots=True)
class _Candidate:
    action: GroundedAction
    target: CanonicalState
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
            "pruned": dominated,
            "target_state_id": self.target.state_id,
        }


def replay_astar_events(
    states_payload: Mapping[str, Any],
    events: list[Mapping[str, Any]],
    *,
    authority: PDDLStateAuthority,
    max_expansions: int,
    accepted_delta_limit: int,
) -> AStarReplaySummary:
    """Rebuild A* state without calling the production controller or runner."""

    heuristic = HMaxHeuristic(authority)
    initial = authority.initial_state
    initial_h = heuristic(initial)
    states = {initial.state_id: initial}
    best_g = {initial.state_id: 0}
    closed_g: dict[str, int] = {}
    frontier = {initial.state_id: (initial_h, 0, 0)}
    next_serial = 1
    accepted_deltas: deque[dict[str, object]] = deque(maxlen=accepted_delta_limit)
    decision_count = 0
    reopen_count = 0

    if len(events) > max_expansions:
        raise AStarReplayError("A* evidence exceeds its expansion budget")
    for expansion_index, event in enumerate(events):
        before = _frontier_snapshot(frontier)
        if not before:
            raise AStarReplayError("A* evidence expands after frontier exhaustion")
        state_id = str(before[0]["state_id"])
        state = states[state_id]
        if authority.is_goal(state):
            raise AStarReplayError("A* evidence expands a popped goal state")
        if (
            event.get("index") != expansion_index
            or event.get("expansion_index") != expansion_index
            or event.get("expanded_state_id") != state_id
            or event.get("frontier_before") != before
        ):
            raise AStarReplayError(f"A* frontier-head invariant failed at event {expansion_index}")

        f, _, g = frontier[state_id]
        h = heuristic(state)
        expected_heuristic = {"f": g + h, "g": g, "name": "h_max", "value": h}
        if f != g + h or event.get("heuristic") != expected_heuristic:
            raise AStarReplayError(f"A* h/f invariant failed at event {expansion_index}")

        actions = authority.applicable_actions(state)
        observation_candidates = tuple(
            _candidate(authority, heuristic, state, action, g + 1, best_g, closed_g, frontier)
            for action in actions
        )
        observation = _model_input(
            authority,
            state,
            g,
            h,
            [candidate.to_dict() for candidate in observation_candidates],
            accepted_deltas,
            best_g,
            closed_g,
            frontier,
        )
        if event.get("observation") != observation:
            raise AStarReplayError(f"A* observation invariant failed at event {expansion_index}")

        frontier.pop(state_id)
        candidates = tuple(
            _candidate(authority, heuristic, state, action, g + 1, best_g, closed_g, frontier)
            for action in actions
        )
        serial_by_target: dict[str, int] = {}
        for offset, candidate in enumerate(candidates):
            serial_by_target.setdefault(candidate.target.state_id, next_serial + offset)
        next_serial += len(candidates)
        decisions = event.get("decisions")
        if not isinstance(decisions, list):
            raise AStarReplayError(f"A* decisions are malformed at event {expansion_index}")
        submitted: set[GroundedAction] = set()
        for decision in decisions:
            visible_candidates = [
                _candidate(authority, heuristic, state, action, g + 1, best_g, closed_g, frontier).to_dict()
                for action in actions
                if action not in submitted
            ]
            expected_input = _model_input(
                authority,
                state,
                g,
                h,
                visible_candidates,
                accepted_deltas,
                best_g,
                closed_g,
                frontier,
            )
            if not isinstance(decision, Mapping) or decision.get("input") != expected_input:
                raise AStarReplayError(f"A* decision input differs at event {expansion_index}")
            operation = _decode_operation(decision.get("operation"))
            if (
                not _raw_operation_matches(decision.get("raw_model_output"), operation)
                or operation["source_state_id"] != state_id
            ):
                raise AStarReplayError(f"A* operation provenance differs at event {expansion_index}")
            action_payload = operation["action"]
            action = GroundedAction(str(action_payload["name"]), tuple(action_payload["args"]))
            candidate = next((item for item in candidates if item.action == action), None)
            if candidate is None or action in submitted:
                raise AStarReplayError(f"A* operation is not an exact candidate at event {expansion_index}")
            submitted.add(action)
            decision_count += 1

            target_id = candidate.target.state_id
            previous = best_g.get(target_id)
            status = "dominated"
            if previous is None or candidate.g < previous:
                applied = authority.apply(state, action).target_state
                if applied != candidate.target:
                    raise AStarReplayError(f"A* transition preview differs at event {expansion_index}")
                states[target_id] = applied
                best_g[target_id] = candidate.g
                if target_id in closed_g:
                    del closed_g[target_id]
                    reopen_count += 1
                    status = "reopened"
                elif target_id in frontier:
                    status = "improved"
                else:
                    status = "enqueued"
                serial = serial_by_target[target_id]
                frontier[target_id] = (candidate.f, serial, candidate.g)
                accepted_deltas.append(
                    {
                        "f": candidate.f,
                        "g": candidate.g,
                        "h": candidate.h,
                        "state_id": target_id,
                        "status": status,
                    }
                )
            expected_runtime = {
                "accepted": True,
                "budget_charge": 0,
                "f": candidate.f,
                "g": candidate.g,
                "h": candidate.h,
                "status": status,
                "target_state_id": target_id,
            }
            if decision.get("trusted_runtime_result") != expected_runtime:
                raise AStarReplayError(f"A* runtime status differs at event {expansion_index}")

        if submitted != {candidate.action for candidate in candidates}:
            raise AStarReplayError(f"A* expansion omitted candidates at event {expansion_index}")
        closed_g[state_id] = best_g[state_id]
        after = _frontier_snapshot(frontier)
        if event.get("frontier_after") != after:
            raise AStarReplayError(f"A* frontier priority differs at event {expansion_index}")
        expected_verdict = {
            "best_g_bookkeeping": True,
            "frontier_head_expanded": True,
            "hold": True,
            "priority": ["f", "generation_serial"],
            "reopen_on_cheaper_path": True,
        }
        if event.get("invariants") != expected_verdict:
            raise AStarReplayError(f"A* persisted invariant verdict differs at event {expansion_index}")

    if len(events) == max_expansions:
        termination = "expansion_budget"
        goal_reached = False
    else:
        head = _frontier_snapshot(frontier)
        if not head:
            termination = "frontier_exhausted"
            goal_reached = False
        elif authority.is_goal(states[str(head[0]["state_id"])]):
            termination = "goal_reached"
            goal_reached = True
        else:
            raise AStarReplayError("A* evidence stops before a terminal condition")

    expected_states = {
        state_id: {
            "atoms": list(state.atoms),
            "authority_id": state.authority_id,
            "fluents": list(state.fluents),
        }
        for state_id, state in states.items()
    }
    if dict(states_payload) != expected_states:
        raise AStarReplayError("A* state table differs from replayed transitions")
    return AStarReplaySummary(
        decision_count=decision_count,
        expansion_count=len(events),
        goal_reached=goal_reached,
        reopen_count=reopen_count,
        state_ids=frozenset(states),
        termination=termination,
    )


def _candidate(
    authority: PDDLStateAuthority,
    heuristic: HMaxHeuristic,
    state: CanonicalState,
    action: GroundedAction,
    g: int,
    best_g: Mapping[str, int],
    closed_g: Mapping[str, int],
    frontier: Mapping[str, tuple[int, int, int]],
) -> _Candidate:
    target = authority.preview_apply(state, action).target_state
    return _Candidate(
        action=action,
        target=target,
        g=g,
        h=heuristic(target),
        prior_best=best_g.get(target.state_id),
        closed=target.state_id in closed_g,
        frontier=target.state_id in frontier,
    )


def _frontier_snapshot(frontier: Mapping[str, tuple[int, int, int]]) -> list[dict[str, object]]:
    return [
        {
            "f": f,
            "g": g,
            "generation_serial": serial,
            "h": f - g,
            "priority": [f, serial],
            "state_id": state_id,
        }
        for f, serial, state_id, g in sorted(
            (f, serial, state_id, g) for state_id, (f, serial, g) in frontier.items()
        )
    ]


def _model_input(
    authority: PDDLStateAuthority,
    state: CanonicalState,
    g: int,
    h: int,
    candidates: list[dict[str, object]],
    accepted_deltas: deque[dict[str, object]],
    best_g: Mapping[str, int],
    closed_g: Mapping[str, int],
    frontier: Mapping[str, tuple[int, int, int]],
) -> dict[str, object]:
    snapshot = _frontier_snapshot(frontier)
    return {
        "accepted_deltas": list(accepted_deltas),
        "algorithm": "astar_hmax",
        "current": {
            "f": g + h,
            "g": g,
            "h": h,
            "state_atoms": list(state.atoms),
            "state_id": state.state_id,
        },
        "search_memory": {
            "best_cost_count": len(best_g),
            "closed_count": len(closed_g),
            "frontier_count": len(snapshot),
            "frontier_head": snapshot[0] if snapshot else None,
            "visited_count": len(best_g),
        },
        "successor_candidates": candidates,
        "task_context": authority.task_context(),
    }


def _decode_operation(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {"action", "source_state_id"}:
        raise AStarReplayError("A* operation has invalid fields")
    action = payload["action"]
    if (
        not isinstance(action, dict)
        or set(action) != {"args", "name"}
        or not isinstance(action["name"], str)
        or not isinstance(action["args"], list)
        or any(not isinstance(item, str) for item in action["args"])
        or not isinstance(payload["source_state_id"], str)
    ):
        raise AStarReplayError("A* operation is malformed")
    return payload


def _raw_operation_matches(raw_output: object, operation: Mapping[str, Any]) -> bool:
    if not isinstance(raw_output, str):
        return False
    try:
        return json.loads(raw_output) == operation
    except json.JSONDecodeError:
        return False


__all__ = ["AStarReplayError", "AStarReplaySummary", "replay_astar_events"]
