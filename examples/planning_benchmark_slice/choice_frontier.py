"""Choice-sensitive additive best-first contract (#132).

The #130 identity audit showed the enumeration contract has zero decision
headroom structurally: the session pops the deterministic heap head, every
decision submits one remaining candidate, ``finish_expansion()`` requires the
complete candidate set, and heap serials derive from the deterministic sorted
candidate order, so frontier evolution is submission-order invariant.

This module implements the pre-registered redesign: the policy selects **which
frontier state to expand next** from the runtime-owned frontier under a
binding expansion/decision budget. On acceptance the trusted runtime performs
the expansion atomically, inheriting candidate generation order, serial
assignment and admission rules verbatim from ``BestFirstController``. Selecting
a goal state solves the task. exact_reference (always select the heap head)
reproduces the frozen v3 exact traces expansion for expansion; random_valid
(uniform frontier choice) diverges whenever a decision sees a frontier of size
>= 2, so random_valid != exact_reference by construction.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Any, Mapping

from .best_first_controller import (
    BEST_FIRST_SETTINGS,
    BestFirstController,
    BestFirstDecisionResult,
    BestFirstOperation,
)
from .pddl_state import CanonicalState, PDDLStateAuthority

CHOICE_ARM = "visual-choice-frontier"
CHOICE_RECIPE_ID = "visual-choice-frontier-v1"
CHOICE_SCHEMA = "choice_frontier_model_input_v1"
CHOICE_REPRESENTATION = "visual-choice-frontier"
CHOICE_SYSTEM_MESSAGE = (
    "Emit exactly one frontier expansion choice. The trusted runtime owns "
    "h_add, scalar priority, duplicate detection, the frontier, and state "
    "transitions. Your choice selects which frontier state the runtime expands "
    "next; selecting the goal state solves the task."
)
CHOICE_LEGEND = (
    "Static task context, the initial-state scene and the partial-goal pages "
    "are attached, followed by one unlabelled 128px scene per frontier state "
    "in menu order, each labelled frontier-choice (label c<i>). Initial/current "
    "states are unlabelled 128px scenes without text annotations. Black robot "
    "silhouettes identify the agent. Goal constraints do not describe a "
    "complete solved state: unspecified facts are unconstrained. Goal blocks "
    "ALL, ANY, NOT, FOR EVERY and THERE EXISTS retain their labelled variable "
    "scopes. The frontier menu lists one choice label per live frontier state, "
    "unscored, in a seeded permuted order; no state identifiers, scalar search "
    "values, scores, membership flags, search memory, accepted deltas or "
    "search history are provided. The policy selects which frontier state the "
    "trusted runtime expands next; selecting the goal state solves the task."
)
MENU_MASTER_SEED = 51131
MENU_FAMILY = "choice-frontier-menu"
ARMS = ("pretrained_base", "process_sft", "random_valid", "exact_reference")
OUTPUT_KEY = "expand_choice"
EPISODE_SCHEMA = "choice_frontier_model_episode_v1"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def menu_permutation_seed(serial_ordered_state_ids: list[str]) -> int:
    """Frozen per-decision menu seed: pure function of the serial member order."""

    digest = hashlib.sha256(canonical(serial_ordered_state_ids).encode()).hexdigest()
    return int.from_bytes(
        hashlib.sha256(f"{MENU_MASTER_SEED}|{MENU_FAMILY}|{digest}".encode()).digest()[:8], "big"
    )


def permuted_menu(serial_members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Seeded Fisher-Yates of the serial member order; labels assigned after."""

    order = list(serial_members)
    random.Random(menu_permutation_seed([member["state_id"] for member in serial_members])).shuffle(order)
    return [{"choice": f"c{index}", "state_ref": member["state_id"]} for index, member in enumerate(order)]


def canonical_choice(label: str) -> str:
    return canonical({OUTPUT_KEY: label})


class ChoiceFrontierController(BestFirstController):
    """BestFirstController whose expansion target is policy-selected, not head-popped."""

    def frontier_members(self) -> list[dict[str, Any]]:
        """Live frontier membership in generation-serial order (refs only)."""

        return [
            {"state_id": self._state_ref_by_id[state_id], "generation_serial": entry[1]}
            for state_id, entry in sorted(self._frontier_entries.items(), key=lambda item: item[1][1])
        ]

    def expand_member(self, state_id: str) -> dict[str, Any]:
        """Atomically expand one chosen live frontier member.

        Candidate generation, serial assignment and admission are the same code
        path ``start_expansion``/``apply_operation``/``finish_expansion`` use;
        the per-candidate admissions are runtime-internal and do not count as
        policy decisions.
        """

        if self.budget_exhausted:
            raise ValueError("choice-frontier controller budget is exhausted")
        if self._active_state_id is not None:
            raise ValueError("a choice-frontier expansion is already active")
        if state_id not in self._frontier_entries:
            raise ValueError("expansion choice is not a live frontier member")
        decisions_before = self.decision_count
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
        admissions = []
        active_ref = self.active_state_ref
        if active_ref is None:
            raise ValueError("choice-frontier expansion lost its active state reference")
        for candidate in self._active_candidates:
            result = self.apply_operation(BestFirstOperation(active_ref, candidate.action))
            if not result.accepted:
                raise ValueError("choice-frontier runtime admission rejected a generated candidate")
            admissions.append(
                {
                    "action": {"args": list(candidate.action.args), "name": candidate.action.name},
                    "trusted_runtime_result": dict(result.runtime_result),
                }
            )
        self.finish_expansion()
        self.decision_count = decisions_before
        return {
            "admissions": admissions,
            "expanded_state_id": self._state_ref_by_id[state_id],
            "frontier_after": {"count": self.frontier_count, "head": self.frontier_head()},
        }

    def apply_choice(self, raw_output: str, menu_binding: list[dict[str, str]]) -> BestFirstDecisionResult:
        """Validate and execute one frontier expansion choice."""

        self.decision_count += 1
        if self.budget_exhausted:
            return self._budget_stop(raw_output)
        try:
            payload = json.loads(raw_output)
            if not isinstance(payload, dict) or set(payload) != {OUTPUT_KEY}:
                raise ValueError(f"choice must contain exactly {OUTPUT_KEY}")
            if not isinstance(payload[OUTPUT_KEY], str):
                raise ValueError("expansion choice label is malformed")
            label = payload[OUTPUT_KEY]
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            return self._reject(raw_output, str(error))
        offered = {binding["choice"]: binding["state_ref"] for binding in menu_binding}
        if label not in offered:
            return self._reject(raw_output, "expansion choice is not an offered frontier label")
        state_ref = offered[label]
        state = self._states_by_ref[state_ref]
        if state.state_id not in self._frontier_entries:
            return self._reject(raw_output, "expansion choice is not a live frontier member")
        if self.authority.is_goal(state):
            result = BestFirstDecisionResult(
                True,
                0,
                raw_output,
                {
                    "accepted": True,
                    "budget_charge": 0,
                    "expanded_state_id": state_ref,
                    "status": "goal_reached",
                },
            )
            self._retain(result)
            return result
        expansion = self.expand_member(state.state_id)
        result = BestFirstDecisionResult(
            True,
            0,
            raw_output,
            {"accepted": True, "budget_charge": 0, "status": "expanded", **expansion},
        )
        self._retain(result)
        return result


@dataclass(frozen=True, slots=True)
class ChoiceFrontierTask:
    """Episode identity and reference costs for one choice-contract episode."""

    instance_id: str
    pair_id: str
    domain: str
    algorithm: str
    exact_expansions: int

    @property
    def decision_cap(self) -> int:
        """Binding budget: 2 x reference expansions for decisions and expansions."""

        return 2 * self.exact_expansions


@dataclass(frozen=True, slots=True)
class ChoiceFrontierRequest:
    session_id: str
    adapter_id: str | None
    seed: int
    instance_id: str
    decision_index: int
    model_input: dict[str, Any]
    menu_binding: list[dict[str, str]]


class ChoiceFrontierModelSession:
    """Incremental choice-contract episode with a binding decision/expansion budget."""

    def __init__(
        self,
        *,
        authority: PDDLStateAuthority,
        task: ChoiceFrontierTask,
        arm: str,
        seed: int,
        adapter_id: str | None = None,
        decision_cap: int | None = None,
    ) -> None:
        if arm not in ARMS:
            raise ValueError(f"choice-frontier episode arm is invalid: {arm}")
        self.authority = authority
        self.task = task
        self.arm = arm
        self.seed = seed
        self.adapter_id = adapter_id
        self.decision_cap = decision_cap if decision_cap is not None else task.decision_cap
        self.controller = ChoiceFrontierController(
            authority,
            BEST_FIRST_SETTINGS[task.algorithm],
            accepted_delta_limit=16,
            max_budget=self.decision_cap,
            retain_decision_evidence=False,
        )
        self.random = random.Random(seed)
        self.events: list[dict[str, Any]] = []
        self.termination_reason: str | None = "goal_reached" if authority.is_goal(authority.initial_state) else None
        self._pending: ChoiceFrontierRequest | None = None
        self.session_id = f"{arm}:{adapter_id or 'reference'}:{seed}:{task.instance_id}"

    @property
    def complete(self) -> bool:
        return self.termination_reason is not None

    def next_request(self) -> ChoiceFrontierRequest | None:
        if self._pending is not None:
            return self._pending
        if self.complete:
            return None
        if len(self.events) >= self.decision_cap:
            self.termination_reason = "decision_budget_exhausted"
            return None
        if self.controller.budget_exhausted:
            self.termination_reason = "expansion_budget_exhausted"
            return None
        members = self.controller.frontier_members()
        if not members:
            self.termination_reason = "frontier_exhausted"
            return None
        binding = permuted_menu(members)
        model_input = {
            "algorithm": self.task.algorithm,
            "frontier_menu": {"choices": [entry["choice"] for entry in binding]},
            "representation": CHOICE_REPRESENTATION,
            "schema_version": CHOICE_SCHEMA,
        }
        self._pending = ChoiceFrontierRequest(
            session_id=self.session_id,
            adapter_id=self.adapter_id,
            seed=self.seed,
            instance_id=self.task.instance_id,
            decision_index=len(self.events),
            model_input=model_input,
            menu_binding=binding,
        )
        return self._pending

    def menu_states(self, request: ChoiceFrontierRequest | None = None) -> list[CanonicalState]:
        """Menu states in menu order, resolved through the trusted controller."""

        request = request or self._pending
        if request is None:
            raise ValueError("choice-frontier episode has no pending request")
        return [self.controller._states_by_ref[entry["state_ref"]] for entry in request.menu_binding]

    def reference_output(self) -> str:
        if self._pending is None:
            raise ValueError("choice-frontier episode has no pending model request")
        if self.arm == "exact_reference":
            head = self.controller.frontier_head_state_id()
            if head is None:
                raise ValueError("choice-frontier exact reference lost the frontier head")
            head_ref = self.controller._state_ref_by_id[head]
            label = next(
                entry["choice"] for entry in self._pending.menu_binding if entry["state_ref"] == head_ref
            )
        elif self.arm == "random_valid":
            label = self.random.choice([entry["choice"] for entry in self._pending.menu_binding])
        else:
            raise ValueError(f"reference outputs exist for the control arms only: {self.arm}")
        return canonical_choice(label)

    def submit_output(self, output: str) -> None:
        if self._pending is None or self.complete:
            raise ValueError("choice-frontier episode has no pending model request")
        request = self._pending
        result = self.controller.apply_choice(output, request.menu_binding)
        self.events.append(
            {
                "decision_index": request.decision_index,
                "input": dict(request.model_input),
                "menu": [dict(entry) for entry in request.menu_binding],
                "raw_output": output,
                "trusted_runtime_result": dict(result.runtime_result),
            }
        )
        self._pending = None
        if not result.accepted:
            self.termination_reason = "deterministic_invalid_operation"
        elif result.runtime_result["status"] == "goal_reached":
            self.termination_reason = "goal_reached"

    def result(self) -> dict[str, Any]:
        if not self.complete:
            raise ValueError("choice-frontier episode is not complete")
        goal_reached = self.termination_reason == "goal_reached"
        return {
            "algorithm_invariants_hold": self.controller.invalid_operation_count == 0,
            "decision_count": len(self.events),
            "expansion_count": self.controller.expansion_count,
            "goal_reached": goal_reached,
            "invariant_valid_success": goal_reached and self.controller.invalid_operation_count == 0,
            "invalid_operation_count": self.controller.invalid_operation_count,
            "invalid_operation_rate": self.controller.invalid_operation_count / len(self.events)
            if self.events
            else 0.0,
            "model_call_limit": self.decision_cap,
            "termination_reason": self.termination_reason,
        }

    def episode(self) -> dict[str, Any]:
        if not self.complete or self._pending is not None:
            raise ValueError("choice-frontier episode is not complete")
        return {
            "adapter_id": self.adapter_id,
            "algorithm": self.task.algorithm,
            "arm": self.arm,
            "decision_cap": self.decision_cap,
            "events": self.events,
            "exact_reference_expansions": self.task.exact_expansions,
            "instance_id": self.task.instance_id,
            "pair_id": self.task.pair_id,
            "result": self.result(),
            "schema_version": EPISODE_SCHEMA,
            "seed": self.seed,
        }


def replay_choice_episode(
    authority: PDDLStateAuthority,
    task: ChoiceFrontierTask,
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute every menu and trusted transition of a stored episode, exactly."""

    session = ChoiceFrontierModelSession(
        authority=authority,
        task=task,
        arm=report["arm"],
        seed=int(report["seed"]),
        adapter_id=report.get("adapter_id"),
        decision_cap=int(report["decision_cap"]),
    )
    for event in report["events"]:
        request = session.next_request()
        if request is None:
            raise ValueError("choice-frontier replay ended before the stored events")
        if dict(request.model_input) != event["input"]:
            raise ValueError("choice-frontier replay input differs")
        if [dict(entry) for entry in request.menu_binding] != event["menu"]:
            raise ValueError("choice-frontier replay menu binding differs")
        session.submit_output(event["raw_output"])
        if session.events[-1]["trusted_runtime_result"] != event["trusted_runtime_result"]:
            raise ValueError("choice-frontier replay trusted runtime result differs")
    if session.next_request() is not None:
        raise ValueError("choice-frontier replay continued past the stored events")
    if not session.complete:
        raise ValueError("choice-frontier replay remained incomplete")
    if session.result() != report["result"]:
        raise ValueError("choice-frontier replay result differs")
    return session.result()


__all__ = [
    "ARMS",
    "CHOICE_ARM",
    "CHOICE_LEGEND",
    "CHOICE_RECIPE_ID",
    "CHOICE_REPRESENTATION",
    "CHOICE_SCHEMA",
    "CHOICE_SYSTEM_MESSAGE",
    "EPISODE_SCHEMA",
    "MENU_FAMILY",
    "MENU_MASTER_SEED",
    "OUTPUT_KEY",
    "ChoiceFrontierController",
    "ChoiceFrontierModelSession",
    "ChoiceFrontierRequest",
    "ChoiceFrontierTask",
    "canonical",
    "canonical_choice",
    "menu_permutation_seed",
    "permuted_menu",
    "replay_choice_episode",
]
