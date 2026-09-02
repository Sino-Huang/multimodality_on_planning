"""Independent mechanical replay for compact additive best-first traces."""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .best_first_add import AdditiveHeuristic
from .best_first_controller import BEST_FIRST_SETTINGS, BestFirstSetting
from .pddl_state import CanonicalState, GroundedAction, PDDLStateAuthority


class BestFirstReplayError(ValueError):
    """Raised when compact best-first evidence violates its declared search."""


@dataclass(frozen=True, slots=True)
class BestFirstReplaySummary:
    decision_count: int
    expansion_count: int
    goal_reached: bool
    reopen_count: int
    solution_cost: int | None
    termination: str


@dataclass(frozen=True, slots=True)
class _Candidate:
    action: GroundedAction
    target: CanonicalState
    g: int
    h: int
    priority: int
    prior_best: int | None
    closed: bool
    frontier: bool
    target_ref: str

    def to_dict(self, setting: BestFirstSetting) -> dict[str, object]:
        dominated = (self.prior_best is not None and self.prior_best <= self.g) or (
            self.closed and not setting.reopen_closed
        )
        return {
            "action": {"args": list(self.action.args), "name": self.action.name},
            "best_cost": self.prior_best,
            "closed": self.closed,
            "dominated": dominated,
            "frontier": self.frontier,
            "g": self.g,
            "h": self.h,
            "priority": self.priority,
            "pruned": dominated,
            "target_state_id": self.target_ref,
        }


def replay_best_first_events(
    states_payload: Mapping[str, Any],
    events: list[Mapping[str, Any]],
    *,
    authority: PDDLStateAuthority,
    algorithm: str,
    max_expansions: int,
    accepted_delta_limit: int,
) -> BestFirstReplaySummary:
    if algorithm not in BEST_FIRST_SETTINGS:
        raise BestFirstReplayError(f"unsupported additive best-first algorithm: {algorithm}")
    setting = BEST_FIRST_SETTINGS[algorithm]
    heuristic = AdditiveHeuristic(authority)
    initial = authority.initial_state
    initial_h = heuristic(initial)
    states = {initial.state_id: initial}
    state_ref_by_id = {initial.state_id: "s0"}
    states_by_ref = {"s0": initial}
    best_g = {initial.state_id: 0}
    closed_g: dict[str, int] = {}
    frontier = {initial.state_id: (setting.priority(0, initial_h), 0, 0, initial_h)}
    accepted_deltas: deque[dict[str, object]] = deque(maxlen=accepted_delta_limit)
    next_serial = 1
    decision_count = 0
    reopen_count = 0

    if len(events) > max_expansions:
        raise BestFirstReplayError("best-first evidence exceeds its expansion budget")
    for expansion_index, event in enumerate(events):
        before = _frontier_summary(frontier, state_ref_by_id)
        head = before["head"]
        if not isinstance(head, Mapping):
            raise BestFirstReplayError("best-first evidence expands after frontier exhaustion")
        state_ref = str(head["state_id"])
        state = states_by_ref[state_ref]
        state_id = state.state_id
        if authority.is_goal(state):
            raise BestFirstReplayError("best-first evidence expands a popped goal state")
        if (
            event.get("index") != expansion_index
            or event.get("expansion_index") != expansion_index
            or event.get("expanded_state_id") != state_ref
            or event.get("frontier_before") != before
        ):
            raise BestFirstReplayError(f"frontier-head invariant failed at event {expansion_index}")

        _priority, _serial, g, _h = frontier.pop(state_id)
        actions = authority.applicable_actions(state)
        candidates = tuple(
            _candidate(
                authority,
                heuristic,
                setting,
                state,
                action,
                g + 1,
                best_g,
                closed_g,
                frontier,
                state_ref_by_id,
                states_by_ref,
            )
            for action in actions
        )
        serial_by_target: dict[str, int] = {}
        for offset, candidate in enumerate(candidates):
            serial_by_target.setdefault(candidate.target.state_id, next_serial + offset)
        next_serial += len(candidates)
        decisions = event.get("decisions")
        if not isinstance(decisions, list) or len(decisions) != len(candidates):
            raise BestFirstReplayError(f"candidate coverage differs at event {expansion_index}")

        for candidate_index, (candidate, decision) in enumerate(zip(candidates, decisions, strict=True)):
            if not isinstance(decision, Mapping):
                raise BestFirstReplayError(f"decision is malformed at event {expansion_index}")
            remaining = candidates[candidate_index:]
            model_input = _model_input(
                authority,
                algorithm,
                setting,
                state,
                state_ref,
                g,
                heuristic(state),
                remaining,
                accepted_deltas,
                best_g,
                closed_g,
                frontier,
                state_ref_by_id,
            )
            if decision.get("input_sha256") != hashlib.sha256(_canonical_bytes(model_input)).hexdigest():
                raise BestFirstReplayError(f"model-input bytes differ at event {expansion_index}")
            operation = _decode_target(decision.get("target"))
            if operation != {
                "action": {"args": list(candidate.action.args), "name": candidate.action.name},
                "source_state_id": state_ref,
            }:
                raise BestFirstReplayError(f"teacher target differs at event {expansion_index}")

            target_id = candidate.target.state_id
            previous = best_g.get(target_id)
            status = "dominated"
            can_improve = previous is None or candidate.g < previous
            if candidate.closed and not setting.reopen_closed:
                status = "closed_pruned"
            elif can_improve:
                target = authority.apply(state, candidate.action).target_state
                if target != candidate.target:
                    raise BestFirstReplayError(f"transition differs at event {expansion_index}")
                was_closed = target_id in closed_g
                states[target_id] = target
                best_g[target_id] = candidate.g
                if was_closed:
                    del closed_g[target_id]
                    reopen_count += 1
                    status = "reopened"
                elif target_id in frontier:
                    status = "improved"
                else:
                    status = "enqueued"
                frontier[target_id] = (
                    candidate.priority,
                    serial_by_target[target_id],
                    candidate.g,
                    candidate.h,
                )
                accepted_deltas.append(
                    {
                        "action": {"args": list(candidate.action.args), "name": candidate.action.name},
                        "g": candidate.g,
                        "h": candidate.h,
                        "priority": candidate.priority,
                        "source_state_id": state_ref,
                        "status": status,
                        "target_state_id": candidate.target_ref,
                    }
                )
            runtime = {
                "best_cost_before": previous,
                "g": candidate.g,
                "h": candidate.h,
                "priority": candidate.priority,
                "status": status,
                "target_state_id": candidate.target_ref,
            }
            if decision.get("runtime") != runtime:
                raise BestFirstReplayError(f"runtime result differs at event {expansion_index}")
            decision_count += 1

        closed_g[state_id] = best_g[state_id]
        after = _frontier_summary(frontier, state_ref_by_id)
        if event.get("frontier_after") != after:
            raise BestFirstReplayError(f"frontier summary differs at event {expansion_index}")

    head = _frontier_summary(frontier, state_ref_by_id)["head"]
    goal_reached = bool(isinstance(head, Mapping) and authority.is_goal(states_by_ref[str(head["state_id"])]))
    observed_refs = {str(event["expanded_state_id"]): None for event in events}
    if goal_reached and isinstance(head, Mapping):
        observed_refs.setdefault(str(head["state_id"]), None)
    expected_states = {state_ref: _serialize_state(states_by_ref[state_ref]) for state_ref in observed_refs}
    if dict(states_payload) != expected_states:
        raise BestFirstReplayError("persisted model-observed states differ from replay")
    if goal_reached:
        termination = "goal_reached"
    elif not frontier:
        termination = "frontier_exhausted"
    elif len(events) == max_expansions:
        termination = "expansion_budget"
    else:
        termination = "trace_record_limit"
    return BestFirstReplaySummary(
        decision_count=decision_count,
        expansion_count=len(events),
        goal_reached=goal_reached,
        reopen_count=reopen_count,
        solution_cost=(
            best_g[states_by_ref[str(head["state_id"])].state_id] if goal_reached and isinstance(head, Mapping) else None
        ),
        termination=termination,
    )


def replay_best_first_trace(
    trace: Mapping[str, Any],
    *,
    authority: PDDLStateAuthority,
) -> BestFirstReplaySummary:
    if set(trace) != {"algorithm", "events", "request", "result", "schema_version", "states"}:
        raise BestFirstReplayError("compact best-first trace fields are invalid")
    if trace.get("schema_version") != "best_first_compact_trace_v1":
        raise BestFirstReplayError("compact best-first trace schema is invalid")
    request = trace.get("request")
    events = trace.get("events")
    states = trace.get("states")
    if (
        not isinstance(request, Mapping)
        or set(request)
        != {
            "accepted_delta_limit",
            "max_decisions",
            "max_expansions",
            "max_uncompressed_trace_bytes",
        }
        or not isinstance(events, list)
        or not isinstance(states, Mapping)
    ):
        raise BestFirstReplayError("compact best-first trace request is invalid")
    replay = replay_best_first_events(
        states,
        events,
        authority=authority,
        algorithm=str(trace.get("algorithm")),
        max_expansions=int(request["max_expansions"]),
        accepted_delta_limit=int(request["accepted_delta_limit"]),
    )
    expected_result = {
        "decision_count": replay.decision_count,
        "expansion_count": replay.expansion_count,
        "goal_reached": replay.goal_reached,
        "reopen_count": replay.reopen_count,
        "solution_cost": replay.solution_cost,
        "termination": replay.termination,
    }
    if trace.get("result") != expected_result:
        raise BestFirstReplayError("compact best-first trace result differs from replay")
    if replay.decision_count > request["max_decisions"]:
        raise BestFirstReplayError("compact best-first trace exceeds its decision ceiling")
    if len(_canonical_bytes(trace)) + 1 > request["max_uncompressed_trace_bytes"]:
        raise BestFirstReplayError("compact best-first trace exceeds its byte ceiling")
    return replay


def _candidate(
    authority: PDDLStateAuthority,
    heuristic: AdditiveHeuristic,
    setting: BestFirstSetting,
    state: CanonicalState,
    action: GroundedAction,
    g: int,
    best_g: Mapping[str, int],
    closed_g: Mapping[str, int],
    frontier: Mapping[str, tuple[int, int, int, int]],
    state_ref_by_id: dict[str, str],
    states_by_ref: dict[str, CanonicalState],
) -> _Candidate:
    target = authority.preview_apply(state, action).target_state
    target_ref = state_ref_by_id.get(target.state_id)
    if target_ref is None:
        target_ref = f"s{len(state_ref_by_id)}"
        state_ref_by_id[target.state_id] = target_ref
        states_by_ref[target_ref] = target
    h = heuristic(target)
    return _Candidate(
        action=action,
        target=target,
        g=g,
        h=h,
        priority=setting.priority(g, h),
        prior_best=best_g.get(target.state_id),
        closed=target.state_id in closed_g,
        frontier=target.state_id in frontier,
        target_ref=target_ref,
    )


def _model_input(
    authority: PDDLStateAuthority,
    algorithm: str,
    setting: BestFirstSetting,
    state: CanonicalState,
    state_ref: str,
    g: int,
    h: int,
    candidates: tuple[_Candidate, ...],
    accepted_deltas: deque[dict[str, object]],
    best_g: Mapping[str, int],
    closed_g: Mapping[str, int],
    frontier: Mapping[str, tuple[int, int, int, int]],
    state_ref_by_id: Mapping[str, str],
) -> dict[str, object]:
    return {
        "accepted_deltas": list(accepted_deltas),
        "algorithm": algorithm,
        "current": {
            "g": g,
            "h": h,
            "priority": setting.priority(g, h),
            "state_atoms": list(state.atoms),
            "state_id": state_ref,
        },
        "search_memory": {
            "best_cost_count": len(best_g),
            "closed_count": len(closed_g),
            "frontier_count": len(frontier),
            "frontier_head": _frontier_head(frontier, state_ref_by_id),
            "visited_count": len(best_g),
        },
        "successor_candidates": [candidate.to_dict(setting) for candidate in candidates],
        "task_context": authority.task_context(),
    }


def _frontier_head(
    frontier: Mapping[str, tuple[int, int, int, int]],
    state_ref_by_id: Mapping[str, str],
) -> dict[str, object] | None:
    if not frontier:
        return None
    state_id, (priority, serial, g, h) = min(frontier.items(), key=lambda item: (item[1][0], item[1][1]))
    return {
        "g": g,
        "generation_serial": serial,
        "h": h,
        "priority": priority,
        "state_id": state_ref_by_id[state_id],
    }


def _frontier_summary(
    frontier: Mapping[str, tuple[int, int, int, int]],
    state_ref_by_id: Mapping[str, str],
) -> dict[str, object]:
    return {
        "count": len(frontier),
        "head": _frontier_head(frontier, state_ref_by_id),
    }


def _decode_target(value: object) -> dict[str, object]:
    if not isinstance(value, str):
        raise BestFirstReplayError("teacher target must be canonical text")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise BestFirstReplayError("teacher target is invalid JSON") from error
    if not isinstance(decoded, dict) or _canonical_text(decoded) != value:
        raise BestFirstReplayError("teacher target is not canonical typed-operation text")
    return decoded


def _serialize_state(state: CanonicalState) -> dict[str, object]:
    return {
        "atoms": list(state.atoms),
        "fluents": list(state.fluents),
    }


def _canonical_bytes(value: object) -> bytes:
    return _canonical_text(value).encode()


def _canonical_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


__all__ = [
    "BestFirstReplayError",
    "BestFirstReplaySummary",
    "replay_best_first_events",
    "replay_best_first_trace",
]
