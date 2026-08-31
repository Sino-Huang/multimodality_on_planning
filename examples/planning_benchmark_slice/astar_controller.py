"""One incremental A* controller seam shared by trusted heuristic adapters."""

from __future__ import annotations

import heapq
import json
from collections import deque
from dataclasses import dataclass
from typing import Mapping, Protocol, cast

from .pddl_state import CanonicalState, GroundedAction, PDDLStateAuthority


class AStarHeuristic(Protocol):
    name: str
    algorithm: str

    def initial(self, state: CanonicalState) -> object: ...

    def advance(self, progress: object, source_state: CanonicalState, target_state: CanonicalState) -> object: ...

    def value(self, state: CanonicalState, progress: object) -> int: ...

    def progress_key(self, progress: object) -> str: ...

    def progress_payload(self, state: CanonicalState, progress: object) -> Mapping[str, object]: ...

    def transition_payload(
        self,
        before: object,
        after: object,
        source_state: CanonicalState,
        target_state: CanonicalState,
    ) -> Mapping[str, object]: ...

    def task_payload(self) -> Mapping[str, object]: ...


class _CallableHeuristic(Protocol):
    def __call__(self, state: CanonicalState) -> int: ...


@dataclass(frozen=True, slots=True)
class AStarOperation:
    source_state_id: str
    action: GroundedAction

    def to_dict(self) -> dict[str, object]:
        return {
            "action": {"args": list(self.action.args), "name": self.action.name},
            "source_state_id": self.source_state_id,
        }


@dataclass(frozen=True, slots=True)
class AStarCandidate:
    action: GroundedAction
    target_state: CanonicalState
    g: int
    h: int
    prior_best_g: int | None
    closed: bool
    frontier: bool
    target_node_id: str
    target_progress: object
    progression: Mapping[str, object]
    progression_delta: Mapping[str, object]

    @property
    def dominated(self) -> bool:
        return self.prior_best_g is not None and self.prior_best_g <= self.g

    @property
    def f(self) -> int:
        return self.g + self.h

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "action": {"args": list(self.action.args), "name": self.action.name},
            "best_cost": self.prior_best_g,
            "closed": self.closed,
            "dominated": self.dominated,
            "f": self.f,
            "frontier": self.frontier,
            "g": self.g,
            "h": self.h,
            "pruned": self.dominated,
            "target_state_id": self.target_state.state_id,
        }
        if self.target_node_id != self.target_state.state_id or self.progression:
            payload.update(
                {
                    "progression": dict(self.progression),
                    "progression_delta": dict(self.progression_delta),
                    "target_node_id": self.target_node_id,
                }
            )
        return payload


@dataclass(frozen=True, slots=True)
class AStarDecisionResult:
    accepted: bool
    budget_charge: int
    raw_output: str
    runtime_result: Mapping[str, object]


class AStarController:
    """Trusted A* bookkeeping; policies only submit one bounded operation at a time."""

    def __init__(
        self,
        authority: PDDLStateAuthority,
        heuristic: AStarHeuristic | object,
        *,
        accepted_delta_limit: int,
        max_budget: int | None = None,
    ) -> None:
        if (
            isinstance(accepted_delta_limit, bool)
            or not isinstance(accepted_delta_limit, int)
            or accepted_delta_limit <= 0
        ):
            raise ValueError("accepted_delta_limit must be positive")
        if max_budget is not None and (
            isinstance(max_budget, bool) or not isinstance(max_budget, int) or max_budget <= 0
        ):
            raise ValueError("max_budget must be positive when supplied")
        self.authority = authority
        self.heuristic = _normalize_heuristic(heuristic)
        initial = authority.initial_state
        initial_progress = self.heuristic.initial(initial)
        initial_node_id = self._node_id(initial, initial_progress)
        initial_h = self._evaluate(initial, initial_progress)
        self.best_g: dict[str, int] = {initial_node_id: 0}
        self.closed_g: dict[str, int] = {}
        self.states: dict[str, CanonicalState] = {initial.state_id: initial}
        self._node_states: dict[str, CanonicalState] = {initial_node_id: initial}
        self._node_progress: dict[str, object] = {initial_node_id: initial_progress}
        self._frontier_entries: dict[str, tuple[int, int, int]] = {initial_node_id: (initial_h, 0, 0)}
        self._heap: list[tuple[int, int, str, int]] = [(initial_h, 0, initial_node_id, 0)]
        self._next_serial = 1
        self._active_serial_by_target: dict[str, int] = {}
        self._active_state_id: str | None = None
        self._active_candidates: tuple[AStarCandidate, ...] = ()
        self._submitted_actions: set[GroundedAction] = set()
        self._accepted_deltas: deque[dict[str, object]] = deque(maxlen=accepted_delta_limit)
        self._decision_evidence: list[dict[str, object]] = []
        self.decision_count = 0
        self.expansion_count = 0
        self.invalid_operation_count = 0
        self.reopen_count = 0
        self.budget_used = 0
        self.max_budget = max_budget

    @property
    def heuristic_name(self) -> str:
        return self.heuristic.name

    @property
    def algorithm(self) -> str:
        return self.heuristic.algorithm

    @property
    def active_state_id(self) -> str | None:
        return self._active_state_id

    @property
    def budget_exhausted(self) -> bool:
        return self.max_budget is not None and self.budget_used >= self.max_budget

    def frontier_head_state_id(self) -> str | None:
        self._discard_stale_heap_entries()
        return None if not self._heap else self._heap[0][2]

    def frontier_snapshot(self) -> list[dict[str, object]]:
        entries = sorted(
            (f, serial, state_id, g)
            for state_id, (f, serial, g) in self._frontier_entries.items()
        )
        return [
            {
                "f": f,
                "g": g,
                "generation_serial": serial,
                "h": f - g,
                "priority": [f, serial],
                "state_id": state_id,
            }
            for f, serial, state_id, g in entries
        ]

    def accepted_deltas(self) -> list[dict[str, object]]:
        return list(self._accepted_deltas)

    @property
    def visited_count(self) -> int:
        """Count trusted composite nodes with a best-known path cost."""

        return len(self.best_g)

    def node_state(self, node_id: str) -> CanonicalState:
        return self._node_states[node_id]

    def node_progress(self, node_id: str) -> object:
        return self._node_progress[node_id]

    def progress_payload(self, node_id: str) -> Mapping[str, object]:
        return self.heuristic.progress_payload(self.node_state(node_id), self.node_progress(node_id))

    def decision_evidence(self) -> tuple[dict[str, object], ...]:
        return tuple(self._decision_evidence)

    def start_expansion(self) -> CanonicalState:
        if self.budget_exhausted:
            raise ValueError("A* controller budget is exhausted")
        if self._active_state_id is not None:
            raise ValueError("an A* expansion is already active")
        state_id = self.frontier_head_state_id()
        if state_id is None:
            raise ValueError("A* frontier is exhausted")
        entry = self._frontier_entries.pop(state_id)
        self._discard_stale_heap_entries()
        state = self.node_state(state_id)
        progress = self.node_progress(state_id)
        g = entry[2]
        self._active_state_id = state_id
        self._active_candidates = tuple(
            self._candidate(state, progress, action, g + 1)
            for action in self.authority.applicable_actions(state)
        )
        serial_start = self._next_serial
        self._active_serial_by_target = {}
        for offset, candidate in enumerate(self._active_candidates):
            self._active_serial_by_target.setdefault(candidate.target_node_id, serial_start + offset)
        self._next_serial += len(self._active_candidates)
        self._submitted_actions = set()
        return state

    def current_candidates(self) -> tuple[AStarCandidate, ...]:
        state_id = self._active_state_id or self.frontier_head_state_id()
        if state_id is None:
            return ()
        state = self.node_state(state_id)
        progress = self.node_progress(state_id)
        g = self.best_g[state_id]
        return tuple(
            self._candidate(state, progress, action, g + 1)
            for action in self.authority.applicable_actions(state)
            if self._active_state_id is None or action not in self._submitted_actions
        )

    def apply_operation(self, operation: AStarOperation, *, raw_output: str | None = None) -> AStarDecisionResult:
        raw = raw_output if raw_output is not None else _canonical_text(operation.to_dict())
        self.decision_count += 1
        if self.budget_exhausted:
            return self._budget_stop(raw)
        if self._active_state_id is None:
            return self._reject(raw, "no A* expansion is active")
        if operation.source_state_id != self._active_state_id:
            return self._reject(raw, "operation source is not the popped A* frontier head")
        candidate = next((item for item in self._active_candidates if item.action == operation.action), None)
        if candidate is None:
            return self._reject(raw, "operation action is not an exact successor candidate")
        if operation.action in self._submitted_actions:
            return self._reject(raw, "successor candidate was already submitted")
        self._submitted_actions.add(operation.action)

        target_id = candidate.target_node_id
        status = "dominated"
        previous = self.best_g.get(target_id)
        if previous is None or candidate.g < previous:
            registered_target = self.authority.apply(
                self.node_state(self._active_state_id), operation.action
            ).target_state
            if registered_target != candidate.target_state:
                raise ValueError("PDDL authority preview differs from applied A* transition")
            was_closed = target_id in self.closed_g
            self.states[registered_target.state_id] = registered_target
            self._node_states[target_id] = registered_target
            self._node_progress[target_id] = candidate.target_progress
            self.best_g[target_id] = candidate.g
            if was_closed:
                del self.closed_g[target_id]
                self.reopen_count += 1
                status = "reopened"
            elif target_id in self._frontier_entries:
                status = "improved"
            else:
                status = "enqueued"
            serial = self._active_serial_by_target[target_id]
            entry = (candidate.f, serial, candidate.g)
            self._frontier_entries[target_id] = entry
            heapq.heappush(self._heap, (candidate.f, serial, target_id, candidate.g))
            delta: dict[str, object] = {
                "f": candidate.f,
                "g": candidate.g,
                "h": candidate.h,
                "state_id": registered_target.state_id,
                "status": status,
            }
            if target_id != registered_target.state_id or candidate.progression:
                delta.update(
                    {
                        "node_id": target_id,
                        "progression": dict(candidate.progression),
                        "progression_delta": dict(candidate.progression_delta),
                    }
                )
            self._accepted_deltas.append(delta)
        runtime = {
            "accepted": True,
            "budget_charge": 0,
            "f": candidate.f,
            "g": candidate.g,
            "h": candidate.h,
            "status": status,
            "target_state_id": target_id,
        }
        runtime["target_state_id"] = candidate.target_state.state_id
        if target_id != candidate.target_state.state_id or candidate.progression:
            runtime.update(
                {
                    "progression": dict(candidate.progression),
                    "progression_delta": dict(candidate.progression_delta),
                    "target_node_id": target_id,
                }
            )
        result = AStarDecisionResult(True, 0, raw, runtime)
        self._retain_decision(result)
        return result

    def apply_raw_output(self, raw_output: str) -> AStarDecisionResult:
        if self.budget_exhausted:
            self.decision_count += 1
            return self._budget_stop(raw_output)
        try:
            payload = json.loads(raw_output)
            if not isinstance(payload, dict) or set(payload) != {"action", "source_state_id"}:
                raise ValueError("operation must contain exactly action and source_state_id")
            action = payload["action"]
            if not isinstance(action, dict) or set(action) != {"args", "name"}:
                raise ValueError("operation action is malformed")
            if not isinstance(action["name"], str) or not isinstance(action["args"], list) or any(
                not isinstance(item, str) for item in action["args"]
            ):
                raise ValueError("operation action is malformed")
            if not isinstance(payload["source_state_id"], str):
                raise ValueError("operation source_state_id is malformed")
            operation = AStarOperation(payload["source_state_id"], GroundedAction(action["name"], tuple(action["args"])))
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            self.decision_count += 1
            return self._reject(raw_output, str(error))
        return self.apply_operation(operation, raw_output=raw_output)

    def finish_expansion(self) -> None:
        if self._active_state_id is None:
            raise ValueError("no A* expansion is active")
        expected = {candidate.action for candidate in self._active_candidates}
        if self._submitted_actions != expected:
            raise ValueError("A* expansion omitted exact successor candidates")
        state_id = self._active_state_id
        self.closed_g[state_id] = self.best_g[state_id]
        self.budget_used += 1
        self.expansion_count += 1
        self._active_state_id = None
        self._active_candidates = ()
        self._active_serial_by_target = {}
        self._submitted_actions = set()

    def snapshot(self) -> dict[str, object]:
        return {
            "accepted_deltas": self.accepted_deltas(),
            "active_state_id": self._active_state_id,
            "best_g": dict(sorted(self.best_g.items())),
            "closed_g": dict(sorted(self.closed_g.items())),
            "frontier": self.frontier_snapshot(),
        }

    def _candidate(
        self,
        state: CanonicalState,
        progress: object,
        action: GroundedAction,
        g: int,
    ) -> AStarCandidate:
        target = self.authority.preview_apply(state, action).target_state
        target_progress = self.heuristic.advance(progress, state, target)
        target_node_id = self._node_id(target, target_progress)
        return AStarCandidate(
            action,
            target,
            g,
            self._evaluate(target, target_progress),
            self.best_g.get(target_node_id),
            target_node_id in self.closed_g,
            target_node_id in self._frontier_entries,
            target_node_id,
            target_progress,
            self.heuristic.progress_payload(target, target_progress),
            self.heuristic.transition_payload(progress, target_progress, state, target),
        )

    def _evaluate(self, state: CanonicalState, progress: object) -> int:
        value = self.heuristic.value(state, progress)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("A* heuristic adapters must return non-negative integers")
        return value

    def _node_id(self, state: CanonicalState, progress: object) -> str:
        key = self.heuristic.progress_key(progress)
        if key == "singleton":
            return state.state_id
        return _canonical_text({"progress_key": key, "state_id": state.state_id})

    def _reject(self, raw_output: str, reason: str) -> AStarDecisionResult:
        self.invalid_operation_count += 1
        self.budget_used += 1
        result = AStarDecisionResult(
            False,
            1,
            raw_output,
            {"accepted": False, "budget_charge": 1, "reason": reason, "status": "rejected"},
        )
        self._retain_decision(result)
        return result

    def _budget_stop(self, raw_output: str) -> AStarDecisionResult:
        result = AStarDecisionResult(
            False,
            0,
            raw_output,
            {
                "accepted": False,
                "budget_charge": 0,
                "reason": "A* controller budget is exhausted",
                "status": "budget_exhausted",
            },
        )
        self._retain_decision(result)
        return result

    def _retain_decision(self, result: AStarDecisionResult) -> None:
        self._decision_evidence.append(
            {
                "budget_charge": result.budget_charge,
                "raw_model_output": result.raw_output,
                "trusted_runtime_result": dict(result.runtime_result),
            }
        )

    def _discard_stale_heap_entries(self) -> None:
        while self._heap:
            f, serial, state_id, g = self._heap[0]
            if self._frontier_entries.get(state_id) == (f, serial, g):
                break
            heapq.heappop(self._heap)


def _canonical_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class _LegacyHeuristicAdapter:
    algorithm = "astar_hmax"

    def __init__(self, heuristic: object) -> None:
        self._heuristic = heuristic
        self.name = str(getattr(heuristic, "name", "custom"))

    def initial(self, state: CanonicalState) -> None:
        del state
        return None

    def advance(
        self,
        progress: object,
        source_state: CanonicalState,
        target_state: CanonicalState,
    ) -> None:
        del progress, source_state, target_state
        return None

    def value(self, state: CanonicalState, progress: object) -> int:
        del progress
        callback = self._heuristic
        if not callable(callback):
            raise TypeError("A* heuristic must be callable or implement the progress adapter")
        return cast(_CallableHeuristic, callback)(state)

    def progress_key(self, progress: object) -> str:
        del progress
        return "singleton"

    def progress_payload(self, state: CanonicalState, progress: object) -> Mapping[str, object]:
        del state, progress
        return {}

    def transition_payload(
        self,
        before: object,
        after: object,
        source_state: CanonicalState,
        target_state: CanonicalState,
    ) -> Mapping[str, object]:
        del before, after, source_state, target_state
        return {}

    def task_payload(self) -> Mapping[str, object]:
        return {}


def _normalize_heuristic(heuristic: object) -> AStarHeuristic:
    required = (
        "initial",
        "advance",
        "value",
        "progress_key",
        "progress_payload",
        "transition_payload",
        "task_payload",
    )
    if all(callable(getattr(heuristic, field, None)) for field in required):
        return cast(AStarHeuristic, heuristic)
    return _LegacyHeuristicAdapter(heuristic)


__all__ = [
    "AStarCandidate",
    "AStarController",
    "AStarDecisionResult",
    "AStarHeuristic",
    "AStarOperation",
]
