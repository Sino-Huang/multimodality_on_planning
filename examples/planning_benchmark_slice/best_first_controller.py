"""Small trusted runtime for the declared additive best-first search settings."""

from __future__ import annotations

import heapq
import json
from collections import deque
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .best_first_add import AdditiveHeuristic
from .pddl_state import CanonicalState, GroundedAction, PDDLStateAuthority


@dataclass(frozen=True, slots=True)
class BestFirstSetting:
    algorithm: str
    heuristic_weight: int | None
    reopen_closed: bool

    @property
    def priority_name(self) -> str:
        return "h" if self.heuristic_weight is None else f"g_plus_{self.heuristic_weight}h"

    def priority(self, g: int, h: int) -> int:
        return h if self.heuristic_weight is None else g + self.heuristic_weight * h


BEST_FIRST_SETTINGS: Mapping[str, BestFirstSetting] = MappingProxyType(
    {
        "best_first_add_w2": BestFirstSetting("best_first_add_w2", 2, True),
        "best_first_add_w3": BestFirstSetting("best_first_add_w3", 3, True),
        "best_first_add_greedy": BestFirstSetting("best_first_add_greedy", None, False),
    }
)


@dataclass(frozen=True, slots=True)
class BestFirstOperation:
    source_state_id: str
    action: GroundedAction

    def to_dict(self) -> dict[str, object]:
        return {
            "action": {"args": list(self.action.args), "name": self.action.name},
            "source_state_id": self.source_state_id,
        }


@dataclass(frozen=True, slots=True)
class BestFirstCandidate:
    action: GroundedAction
    target_state: CanonicalState
    g: int
    h: int
    priority: int
    prior_best_g: int | None
    closed: bool
    frontier: bool
    reopen_closed: bool
    target_state_ref: str

    @property
    def dominated(self) -> bool:
        return (self.prior_best_g is not None and self.prior_best_g <= self.g) or (
            self.closed and not self.reopen_closed
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "action": {"args": list(self.action.args), "name": self.action.name},
            "best_cost": self.prior_best_g,
            "closed": self.closed,
            "dominated": self.dominated,
            "frontier": self.frontier,
            "g": self.g,
            "h": self.h,
            "priority": self.priority,
            "pruned": self.dominated,
            "target_state_id": self.target_state_ref,
        }


@dataclass(frozen=True, slots=True)
class BestFirstDecisionResult:
    accepted: bool
    budget_charge: int
    raw_output: str
    runtime_result: Mapping[str, object]


class BestFirstController:
    """Own frontier, duplicate detection, and deterministic best-first ordering."""

    def __init__(
        self,
        authority: PDDLStateAuthority,
        setting: BestFirstSetting,
        *,
        accepted_delta_limit: int = 16,
        max_budget: int | None = None,
        retain_decision_evidence: bool = True,
    ) -> None:
        if setting not in BEST_FIRST_SETTINGS.values():
            raise ValueError("setting must be one of the declared additive best-first settings")
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
        self.setting = setting
        self.heuristic = AdditiveHeuristic(authority)
        initial = authority.initial_state
        initial_h = self._evaluate(initial)
        initial_priority = setting.priority(0, initial_h)
        self.best_g: dict[str, int] = {initial.state_id: 0}
        self.closed_g: dict[str, int] = {}
        self.states: dict[str, CanonicalState] = {initial.state_id: initial}
        self._state_ref_by_id: dict[str, str] = {initial.state_id: "s0"}
        self._states_by_ref: dict[str, CanonicalState] = {"s0": initial}
        self._next_state_ref = 1
        self._frontier_entries: dict[str, tuple[int, int, int, int]] = {
            initial.state_id: (initial_priority, 0, 0, initial_h)
        }
        self._heap: list[tuple[int, int, str, int]] = [(initial_priority, 0, initial.state_id, 0)]
        self._next_serial = 1
        self._active_state_id: str | None = None
        self._active_candidates: tuple[BestFirstCandidate, ...] = ()
        self._serial_by_target: dict[str, int] = {}
        self._submitted_actions: set[GroundedAction] = set()
        self._accepted_deltas: deque[dict[str, object]] = deque(maxlen=accepted_delta_limit)
        self._decision_evidence: list[dict[str, object]] = []
        self._retain_decision_evidence = retain_decision_evidence
        self.max_budget = max_budget
        self.budget_used = 0
        self.decision_count = 0
        self.expansion_count = 0
        self.invalid_operation_count = 0
        self.reopen_count = 0

    @property
    def algorithm(self) -> str:
        return self.setting.algorithm

    @property
    def active_state_id(self) -> str | None:
        return self._active_state_id

    @property
    def active_state_ref(self) -> str | None:
        return None if self._active_state_id is None else self._state_ref_by_id[self._active_state_id]

    @property
    def frontier_count(self) -> int:
        return len(self._frontier_entries)

    @property
    def visited_count(self) -> int:
        return len(self.best_g)

    @property
    def budget_exhausted(self) -> bool:
        return self.max_budget is not None and self.budget_used >= self.max_budget

    def accepted_deltas(self) -> list[dict[str, object]]:
        return list(self._accepted_deltas)

    def decision_evidence(self) -> tuple[dict[str, object], ...]:
        return tuple(self._decision_evidence)

    def trace_state(self, state_ref: str) -> CanonicalState:
        return self._states_by_ref[state_ref]

    def frontier_head(self) -> dict[str, object] | None:
        self._discard_stale_heap_entries()
        if not self._heap:
            return None
        priority, serial, state_id, g = self._heap[0]
        h = self._frontier_entries[state_id][3]
        return {
            "g": g,
            "generation_serial": serial,
            "h": h,
            "priority": priority,
            "state_id": self._state_ref_by_id[state_id],
        }

    def frontier_head_state_id(self) -> str | None:
        self._discard_stale_heap_entries()
        return None if not self._heap else self._heap[0][2]

    def node_state(self, state_id: str) -> CanonicalState:
        return self.states[state_id]

    def start_expansion(self) -> CanonicalState:
        if self.budget_exhausted:
            raise ValueError("best-first controller budget is exhausted")
        if self._active_state_id is not None:
            raise ValueError("a best-first expansion is already active")
        state_id = self.frontier_head_state_id()
        if state_id is None:
            raise ValueError("best-first frontier is exhausted")
        _priority, _serial, g, _h = self._frontier_entries.pop(state_id)
        self._discard_stale_heap_entries()
        state = self.states[state_id]
        self._active_state_id = state_id
        self._active_candidates = tuple(
            self._candidate(state, action, g + 1) for action in self.authority.applicable_actions(state)
        )
        serial_start = self._next_serial
        self._serial_by_target = {}
        for offset, candidate in enumerate(self._active_candidates):
            self._serial_by_target.setdefault(candidate.target_state.state_id, serial_start + offset)
        self._next_serial += len(self._active_candidates)
        self._submitted_actions = set()
        return state

    def current_candidates(self) -> tuple[BestFirstCandidate, ...]:
        if self._active_state_id is None:
            raise ValueError("no best-first expansion is active")
        return tuple(
            candidate for candidate in self._active_candidates if candidate.action not in self._submitted_actions
        )

    def apply_operation(
        self,
        operation: BestFirstOperation,
        *,
        raw_output: str | None = None,
    ) -> BestFirstDecisionResult:
        raw = raw_output if raw_output is not None else _canonical_text(operation.to_dict())
        self.decision_count += 1
        if self.budget_exhausted:
            return self._budget_stop(raw)
        if self._active_state_id is None:
            return self._reject(raw, "no best-first expansion is active")
        if operation.source_state_id != self.active_state_ref:
            return self._reject(raw, "operation source is not the popped frontier head")
        candidate = next(
            (item for item in self._active_candidates if item.action == operation.action),
            None,
        )
        if candidate is None:
            return self._reject(raw, "operation action is not an exact successor candidate")
        if operation.action in self._submitted_actions:
            return self._reject(raw, "successor candidate was already submitted")
        self._submitted_actions.add(operation.action)

        target_id = candidate.target_state.state_id
        status = "dominated"
        previous = self.best_g.get(target_id)
        can_improve = previous is None or candidate.g < previous
        if candidate.closed and not self.setting.reopen_closed:
            status = "closed_pruned"
        elif can_improve:
            target = self.authority.apply(self.states[self._active_state_id], operation.action).target_state
            if target != candidate.target_state:
                raise ValueError("PDDL preview differs from applied best-first transition")
            was_closed = target_id in self.closed_g
            self.states[target_id] = target
            self.best_g[target_id] = candidate.g
            if was_closed:
                del self.closed_g[target_id]
                self.reopen_count += 1
                status = "reopened"
            elif target_id in self._frontier_entries:
                status = "improved"
            else:
                status = "enqueued"
            serial = self._serial_by_target[target_id]
            entry = (candidate.priority, serial, candidate.g, candidate.h)
            self._frontier_entries[target_id] = entry
            heapq.heappush(self._heap, (candidate.priority, serial, target_id, candidate.g))
            self._accepted_deltas.append(
                {
                    "action": {"args": list(candidate.action.args), "name": candidate.action.name},
                    "g": candidate.g,
                    "h": candidate.h,
                    "priority": candidate.priority,
                    "source_state_id": self.active_state_ref,
                    "status": status,
                    "target_state_id": candidate.target_state_ref,
                }
            )
        runtime = {
            "accepted": True,
            "best_cost_before": previous,
            "budget_charge": 0,
            "g": candidate.g,
            "h": candidate.h,
            "priority": candidate.priority,
            "status": status,
            "target_state_id": candidate.target_state_ref,
        }
        result = BestFirstDecisionResult(True, 0, raw, runtime)
        self._retain(result)
        return result

    def apply_raw_output(self, raw_output: str) -> BestFirstDecisionResult:
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
            if (
                not isinstance(action["name"], str)
                or not isinstance(action["args"], list)
                or any(not isinstance(item, str) for item in action["args"])
            ):
                raise ValueError("operation action is malformed")
            if not isinstance(payload["source_state_id"], str):
                raise ValueError("operation source_state_id is malformed")
            operation = BestFirstOperation(
                payload["source_state_id"],
                GroundedAction(action["name"], tuple(action["args"])),
            )
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            self.decision_count += 1
            return self._reject(raw_output, str(error))
        return self.apply_operation(operation, raw_output=raw_output)

    def finish_expansion(self) -> None:
        if self._active_state_id is None:
            raise ValueError("no best-first expansion is active")
        if self._submitted_actions != {candidate.action for candidate in self._active_candidates}:
            raise ValueError("best-first expansion omitted exact successor candidates")
        state_id = self._active_state_id
        self.closed_g[state_id] = self.best_g[state_id]
        self.budget_used += 1
        self.expansion_count += 1
        self._active_state_id = None
        self._active_candidates = ()
        self._serial_by_target = {}
        self._submitted_actions = set()

    def _candidate(
        self,
        state: CanonicalState,
        action: GroundedAction,
        g: int,
    ) -> BestFirstCandidate:
        target = self.authority.preview_apply(state, action).target_state
        target_state_ref = self._register_state_ref(target)
        h = self._evaluate(target)
        target_id = target.state_id
        return BestFirstCandidate(
            action=action,
            target_state=target,
            g=g,
            h=h,
            priority=self.setting.priority(g, h),
            prior_best_g=self.best_g.get(target_id),
            closed=target_id in self.closed_g,
            frontier=target_id in self._frontier_entries,
            reopen_closed=self.setting.reopen_closed,
            target_state_ref=target_state_ref,
        )

    def _register_state_ref(self, state: CanonicalState) -> str:
        existing = self._state_ref_by_id.get(state.state_id)
        if existing is not None:
            return existing
        state_ref = f"s{self._next_state_ref}"
        self._next_state_ref += 1
        self._state_ref_by_id[state.state_id] = state_ref
        self._states_by_ref[state_ref] = state
        return state_ref

    def _evaluate(self, state: CanonicalState) -> int:
        value = self.heuristic(state)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("best-first heuristic must return a non-negative integer")
        return value

    def _reject(self, raw_output: str, reason: str) -> BestFirstDecisionResult:
        self.invalid_operation_count += 1
        self.budget_used += 1
        result = BestFirstDecisionResult(
            False,
            1,
            raw_output,
            {"accepted": False, "budget_charge": 1, "reason": reason, "status": "rejected"},
        )
        self._retain(result)
        return result

    def _budget_stop(self, raw_output: str) -> BestFirstDecisionResult:
        result = BestFirstDecisionResult(
            False,
            0,
            raw_output,
            {
                "accepted": False,
                "budget_charge": 0,
                "reason": "best-first controller budget is exhausted",
                "status": "budget_exhausted",
            },
        )
        self._retain(result)
        return result

    def _retain(self, result: BestFirstDecisionResult) -> None:
        if self._retain_decision_evidence:
            self._decision_evidence.append(
                {
                    "budget_charge": result.budget_charge,
                    "raw_model_output": result.raw_output,
                    "trusted_runtime_result": dict(result.runtime_result),
                }
            )

    def _discard_stale_heap_entries(self) -> None:
        while self._heap:
            priority, serial, state_id, g = self._heap[0]
            entry = self._frontier_entries.get(state_id)
            if entry is not None and entry[:3] == (priority, serial, g):
                break
            heapq.heappop(self._heap)


def _canonical_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


__all__ = [
    "BEST_FIRST_SETTINGS",
    "BestFirstCandidate",
    "BestFirstController",
    "BestFirstDecisionResult",
    "BestFirstOperation",
    "BestFirstSetting",
]
