"""Learned-heuristic -> node-choice driver (#149 §8; imported read-only by #158).

Any ``StateScorer`` (menu states -> scores s, lower = closer to the goal) drives the frozen
node-choice runtime: at each decision the driver submits the menu label of the minimum key
(s for GBFS, g + w*s for weighted A*; g = the runtime's path cost of the node), ties broken by
generation serial, through ``NodeChoiceSession`` as arm ``scored_heuristic``. Menus, the frozen
``ChoiceFrontierController`` transitions, the 2 R_t cap and (optionally) the overflow rule are the
runtime's, unchanged. Each event additionally stores the per-menu scores, so an episode is
verified by ``replay_node_choice_episode`` plus the stored-score argmin check, and a deterministic
scorer can be re-run exactly.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from .best_first_add import AdditiveHeuristic
from .best_first_controller import BEST_FIRST_SETTINGS
from .bfws_episode import _unachieved_goal_count
from .choice_frontier import canonical_choice
from .node_choice import (
    ADDITIVE_ALGORITHMS,
    NodeChoiceSession,
    NodeChoiceTask,
    TokenCounter,
    replay_node_choice_episode,
)
from .pddl_state import CanonicalState, PDDLStateAuthority

ARM = "scored_heuristic"
DEAD_END = math.inf


class StateScorer(Protocol):
    """Scores states of one task; lower is closer to the goal; ``math.inf`` = dead end."""

    scorer_id: str

    def __call__(self, states: Sequence[CanonicalState]) -> list[float]: ...


class FunctionScorer:
    """A scorer from a per-state function, memoised by state id."""

    def __init__(self, scorer_id: str, function: Callable[[CanonicalState], float]) -> None:
        self.scorer_id = scorer_id
        self._function = function
        self._cache: dict[str, float] = {}

    def __call__(self, states: Sequence[CanonicalState]) -> list[float]:
        scores = []
        for state in states:
            if state.state_id not in self._cache:
                self._cache[state.state_id] = float(self._function(state))
            scores.append(self._cache[state.state_id])
        return scores


def goal_count_scorer(authority: PDDLStateAuthority) -> FunctionScorer:
    """Unachieved goal atoms (the GBFS goal-count heuristic)."""

    return FunctionScorer("goal_count", lambda state: _unachieved_goal_count(authority, state))


def hadd_scorer(authority: PDDLStateAuthority) -> FunctionScorer:
    heuristic = AdditiveHeuristic(authority)
    return FunctionScorer("h_add", heuristic)


def weight_of(algorithm: str) -> float | None:
    """None for GBFS (key = s); w for weighted A* (key = g + w s)."""

    if algorithm not in ADDITIVE_ALGORITHMS:
        raise ValueError(f"the scored driver supports the additive best-first runtimes only: {algorithm}")
    weight = BEST_FIRST_SETTINGS[algorithm].heuristic_weight
    return None if weight is None else float(weight)


def menu_keys(session: NodeChoiceSession, request, scores: Sequence[float]) -> list[tuple[float, int]]:
    """(key, generation serial) per menu entry, from the trusted controller's frontier entries."""

    controller = session.controller
    weight = weight_of(session.task.algorithm)
    keys = []
    for entry, score in zip(request.menu_binding, scores, strict=True):
        state = controller._states_by_ref[entry["state_ref"]]
        _priority, serial, g, _h = controller._frontier_entries[state.state_id]
        key = score if weight is None else g + weight * score
        keys.append((key, serial))
    return keys


def scored_choice(session: NodeChoiceSession, request, scorer: StateScorer) -> tuple[str, list[float]]:
    """The canonical output for the minimum-key menu label, and the menu scores (menu order)."""

    scores = [float(s) for s in scorer(session.menu_states(request))]
    if any(math.isnan(s) for s in scores):
        raise ValueError(f"scorer {scorer.scorer_id} returned NaN")
    keys = menu_keys(session, request, scores)
    best = min(range(len(keys)), key=lambda i: keys[i])
    return canonical_choice(request.menu_binding[best]["choice"]), scores


def run_scored_episode(
    authority: PDDLStateAuthority,
    task: NodeChoiceTask,
    scorer: StateScorer,
    *,
    observation: str = "text",
    decision_cap: int | None = None,
    token_limit: int | None = None,
    token_counter: TokenCounter | None = None,
    on_request: Callable[[NodeChoiceSession, Any], None] | None = None,
    on_event: Callable[[NodeChoiceSession, dict], None] | None = None,
) -> NodeChoiceSession:
    """Drive one node-choice episode with ``scorer``; events carry ``scores`` (menu order)."""

    weight_of(task.algorithm)
    session = NodeChoiceSession(
        authority=authority,
        task=task,
        observation=observation,
        arm=ARM,
        seed=0,
        adapter_id=scorer.scorer_id,
        decision_cap=decision_cap,
        token_limit=token_limit,
        token_counter=token_counter,
    )
    while (request := session.next_request()) is not None:
        if on_request is not None:
            on_request(session, request)
        output, scores = scored_choice(session, request, scorer)
        session.submit_output(output)
        session.events[-1]["scores"] = [_json_score(s) for s in scores]
        if on_event is not None:
            on_event(session, session.events[-1])
    return session


def _json_score(score: float) -> float | None:
    return None if math.isinf(score) else score


def _from_json(score: float | None) -> float:
    return DEAD_END if score is None else float(score)


def verify_scored_episode(
    authority: PDDLStateAuthority,
    task: NodeChoiceTask,
    report: Mapping[str, Any],
    *,
    scorer: StateScorer | None = None,
    tolerance: float = 0.0,
    token_counter: TokenCounter | None = None,
) -> dict:
    """Independent replay + every choice is the stored-score argmin (+ exact re-scoring if given)."""

    if report["arm"] != ARM:
        raise ValueError("not a scored-heuristic episode")
    events = report["events"]
    state = {"index": 0, "max_score_difference": 0.0}

    def check(session: NodeChoiceSession, request) -> None:
        event = events[state["index"]]
        stored = [_from_json(s) for s in event["scores"]]
        keys = menu_keys(session, request, stored)
        best = min(range(len(keys)), key=lambda i: keys[i])
        if canonical_choice(request.menu_binding[best]["choice"]) != event["raw_output"]:
            raise ValueError(f"scored choice is not the stored-score argmin at decision {state['index']}")
        if scorer is not None:
            fresh = [float(s) for s in scorer(session.menu_states(request))]
            for a, b in zip(fresh, stored, strict=True):
                if math.isinf(a) or math.isinf(b):
                    if a != b:
                        raise ValueError("re-scored dead-end flag differs")
                    continue
                difference = abs(a - b)
                state["max_score_difference"] = max(state["max_score_difference"], difference)
                if difference > tolerance:
                    raise ValueError(f"re-scored state differs by {difference} at decision {state['index']}")
        state["index"] += 1

    session = replay_node_choice_episode(authority, task, report, token_counter=token_counter, on_request=check)
    if state["index"] != len(events):
        raise ValueError("scored replay did not visit every stored event")
    return {"result": session.result(), "max_score_difference": state["max_score_difference"]}


__all__ = [
    "ARM",
    "DEAD_END",
    "FunctionScorer",
    "StateScorer",
    "goal_count_scorer",
    "hadd_scorer",
    "menu_keys",
    "run_scored_episode",
    "scored_choice",
    "verify_scored_episode",
    "weight_of",
]
