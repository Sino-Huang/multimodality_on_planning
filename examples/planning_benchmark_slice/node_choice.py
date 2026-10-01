"""Node-choice contract for all four algorithms (#146).

Extends the #132 choice-sensitive contract (``choice_frontier.py``) from the two
additive algorithms to BFS and BFWS. At every decision the policy selects which
live open-list node the trusted runtime expands next, from an unscored menu of
opaque labels in a seeded per-decision permutation (the frozen #132 menu
machinery). The runtime generates and admits every successor of the chosen node
with the algorithm's own rules and owns the ordering key kappa_A:

- ``bfs``: FIFO; key = generation serial; duplicates = generated set.
- ``best_first_width``: key = (novelty bucket w, unachieved goals #g, depth g,
  generation serial), novelty tables partitioned by #g at precision 2, unpruned;
  duplicates = generated set (the frozen ``bfws_episode`` semantics).
- ``best_first_add_greedy`` / ``best_first_add_w3``: the frozen
  ``ChoiceFrontierController``, unchanged.

The goal test is at selection for all four algorithms (native BFWS tests at
generation; the exact node-choice expansion sequence has the native sequence as
a prefix). exact_reference always selects the kappa_A head; random_valid selects
uniformly from the menu. The observation carries only states (text facts,
scenes, or both); no depth, serial, score, novelty or history is exposed.

An episode also ends, without a decision, when its next observation would
exceed the context capacity of its observation type (``observation_overflow``);
the rule applies to every arm, controls included.
"""

from __future__ import annotations

import heapq
import json
import random
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .best_first_controller import BEST_FIRST_SETTINGS, BestFirstDecisionResult
from .bfws_episode import BFWS_NOVELTY_PRECISION, _unachieved_goal_count
from .choice_frontier import (
    CHOICE_SYSTEM_MESSAGE,
    OUTPUT_KEY,
    ChoiceFrontierController,
    canonical,
    canonical_choice,
    permuted_menu,
)
from .iw_episode import NoveltyItem, first_novel_item, iw_novelty_items
from .pddl_state import CanonicalState, PDDLStateAuthority

ADDITIVE_ALGORITHMS = ("best_first_add_greedy", "best_first_add_w3")
KEYED_ALGORITHMS = ("bfs", "best_first_width")
ALGORITHMS = (*KEYED_ALGORITHMS, *ADDITIVE_ALGORITHMS)
OBSERVATIONS = ("text", "visual", "multimodal")
NODE_CHOICE_SCHEMA = "node_choice_model_input_v1"
REPRESENTATIONS = {
    "text": "text-node-choice",
    "visual": "visual-node-choice",
    "multimodal": "multimodal-node-choice",
}
ARMS = ("pretrained_base", "zero_shot_base", "process_sft", "random_valid", "exact_reference", "scored_heuristic")
EPISODE_SCHEMA = "node_choice_model_episode_v1"
_SYSTEM_TAIL = (
    "Your choice selects which frontier state the runtime expands next; selecting the goal state solves the task."
)
SYSTEM_MESSAGES: Mapping[str, str] = {
    "bfs": (
        "Emit exactly one frontier expansion choice. The trusted runtime owns the first-in first-out open "
        "list, generation order, duplicate detection, the frontier, and state transitions. " + _SYSTEM_TAIL
    ),
    "best_first_width": (
        "Emit exactly one frontier expansion choice. The trusted runtime owns novelty, unachieved-goal counts, "
        "depth, the priority order, duplicate detection, the frontier, and state transitions. " + _SYSTEM_TAIL
    ),
    # The additive algorithms keep the frozen #132 system message verbatim.
    "best_first_add_greedy": CHOICE_SYSTEM_MESSAGE,
    "best_first_add_w3": CHOICE_SYSTEM_MESSAGE,
}


class KeyedChoiceController:
    """Trusted BFS / BFWS open list whose expansion target is policy-selected.

    Mirrors the ``ChoiceFrontierController`` surface the session and views use:
    ``frontier_members``, ``frontier_head_state_id``, ``apply_choice``,
    ``_states_by_ref`` / ``_state_ref_by_id`` and the budget counters.
    """

    def __init__(self, authority: PDDLStateAuthority, algorithm: str, *, max_budget: int | None = None) -> None:
        if algorithm not in KEYED_ALGORITHMS:
            raise ValueError(f"keyed node-choice algorithm is invalid: {algorithm}")
        if max_budget is not None and (
            isinstance(max_budget, bool) or not isinstance(max_budget, int) or max_budget <= 0
        ):
            raise ValueError("max_budget must be positive when supplied")
        self.authority = authority
        self.algorithm = algorithm
        initial = authority.initial_state
        self.states: dict[str, CanonicalState] = {initial.state_id: initial}
        self._state_ref_by_id: dict[str, str] = {initial.state_id: "s0"}
        self._states_by_ref: dict[str, CanonicalState] = {"s0": initial}
        self._next_state_ref = 1
        self._generated: set[str] = {initial.state_id}
        self._depth: dict[str, int] = {initial.state_id: 0}
        self._tables: dict[int, set[NoveltyItem]] = {}
        self._next_serial = 1
        key = self._initial_key(initial)
        self._frontier_entries: dict[str, tuple[int, ...]] = {initial.state_id: key}
        self._heap: list[tuple[tuple[int, ...], str]] = [(key, initial.state_id)]
        self.max_budget = max_budget
        self.budget_used = 0
        self.decision_count = 0
        self.expansion_count = 0
        self.invalid_operation_count = 0

    # ------------------------------------------------------------------ keys

    def _initial_key(self, initial: CanonicalState) -> tuple[int, ...]:
        if self.algorithm == "bfs":
            return (0,)
        partition = _unachieved_goal_count(self.authority, initial)
        items = iw_novelty_items(initial, BFWS_NOVELTY_PRECISION)
        novel = first_novel_item(items, set())
        bucket = len(novel) if novel is not None else BFWS_NOVELTY_PRECISION + 1
        self._tables[partition] = set(items)
        return (bucket, partition, 0, 0)

    def _successor_key(self, target: CanonicalState, depth: int, serial: int) -> tuple[int, ...]:
        if self.algorithm == "bfs":
            return (serial,)
        partition = _unachieved_goal_count(self.authority, target)
        table = self._tables.setdefault(partition, set())
        items = iw_novelty_items(target, BFWS_NOVELTY_PRECISION)
        novel = first_novel_item(items, table)
        bucket = len(novel) if novel is not None else BFWS_NOVELTY_PRECISION + 1
        table.update(items)
        return (bucket, partition, depth, serial)

    # ------------------------------------------------------------ inspection

    @property
    def frontier_count(self) -> int:
        return len(self._frontier_entries)

    @property
    def budget_exhausted(self) -> bool:
        return self.max_budget is not None and self.budget_used >= self.max_budget

    def frontier_members(self) -> list[dict[str, Any]]:
        """Live open-list membership in generation-serial order (refs only)."""

        return [
            {"state_id": self._state_ref_by_id[state_id], "generation_serial": key[-1]}
            for state_id, key in sorted(self._frontier_entries.items(), key=lambda item: item[1][-1])
        ]

    def _discard_stale_heap_entries(self) -> None:
        while self._heap and self._heap[0][1] not in self._frontier_entries:
            heapq.heappop(self._heap)

    def frontier_head_state_id(self) -> str | None:
        """The kappa_A head: minimum key over the live open list."""

        self._discard_stale_heap_entries()
        return None if not self._heap else self._heap[0][1]

    def frontier_head(self) -> dict[str, Any] | None:
        state_id = self.frontier_head_state_id()
        if state_id is None:
            return None
        return {"key": list(self._frontier_entries[state_id]), "state_id": self._state_ref_by_id[state_id]}

    def _register_state_ref(self, state: CanonicalState) -> str:
        existing = self._state_ref_by_id.get(state.state_id)
        if existing is not None:
            return existing
        state_ref = f"s{self._next_state_ref}"
        self._next_state_ref += 1
        self._state_ref_by_id[state.state_id] = state_ref
        self._states_by_ref[state_ref] = state
        return state_ref

    # -------------------------------------------------------------- expansion

    def expand_member(self, state_id: str) -> dict[str, Any]:
        """Atomically expand one chosen live open-list member.

        Successors are generated in canonical applicable-action order; each
        non-duplicate successor receives the next generation serial and its key
        (novelty tables updated in generation order), exactly as the frozen
        native runtimes admit them. Admissions are not policy decisions.
        """

        if self.budget_exhausted:
            raise ValueError("node-choice controller budget is exhausted")
        if state_id not in self._frontier_entries:
            raise ValueError("expansion choice is not a live frontier member")
        del self._frontier_entries[state_id]
        state = self.states[state_id]
        depth = self._depth[state_id] + 1
        admissions = []
        for action in self.authority.applicable_actions(state):
            target = self.authority.apply(state, action).target_state
            target_ref = self._register_state_ref(target)
            if target.state_id in self._generated:
                runtime = {"status": "duplicate", "target_state_id": target_ref}
            else:
                self._generated.add(target.state_id)
                self.states[target.state_id] = target
                self._depth[target.state_id] = depth
                serial = self._next_serial
                self._next_serial += 1
                key = self._successor_key(target, depth, serial)
                self._frontier_entries[target.state_id] = key
                heapq.heappush(self._heap, (key, target.state_id))
                runtime = {"key": list(key), "status": "enqueued", "target_state_id": target_ref}
            admissions.append(
                {"action": {"args": list(action.args), "name": action.name}, "trusted_runtime_result": runtime}
            )
        self.budget_used += 1
        self.expansion_count += 1
        return {
            "admissions": admissions,
            "expanded_state_id": self._state_ref_by_id[state_id],
            "frontier_after": {"count": self.frontier_count, "head": self.frontier_head()},
        }

    def apply_choice(self, raw_output: str, menu_binding: list[dict[str, str]]) -> BestFirstDecisionResult:
        """Validate and execute one open-list expansion choice (the #132 validation rules)."""

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
        state = self._states_by_ref[offered[label]]
        if state.state_id not in self._frontier_entries:
            return self._reject(raw_output, "expansion choice is not a live frontier member")
        if self.authority.is_goal(state):
            return BestFirstDecisionResult(
                True,
                0,
                raw_output,
                {"accepted": True, "budget_charge": 0, "expanded_state_id": offered[label], "status": "goal_reached"},
            )
        expansion = self.expand_member(state.state_id)
        return BestFirstDecisionResult(
            True, 0, raw_output, {"accepted": True, "budget_charge": 0, "status": "expanded", **expansion}
        )

    def _reject(self, raw_output: str, reason: str) -> BestFirstDecisionResult:
        self.invalid_operation_count += 1
        self.budget_used += 1
        return BestFirstDecisionResult(
            False, 1, raw_output, {"accepted": False, "budget_charge": 1, "reason": reason, "status": "rejected"}
        )

    def _budget_stop(self, raw_output: str) -> BestFirstDecisionResult:
        return BestFirstDecisionResult(
            False,
            0,
            raw_output,
            {
                "accepted": False,
                "budget_charge": 0,
                "reason": "node-choice controller budget is exhausted",
                "status": "budget_exhausted",
            },
        )


def make_controller(authority: PDDLStateAuthority, algorithm: str, max_budget: int):
    """The trusted open list for one algorithm (additive: the frozen #132 controller)."""

    if algorithm in KEYED_ALGORITHMS:
        return KeyedChoiceController(authority, algorithm, max_budget=max_budget)
    if algorithm in ADDITIVE_ALGORITHMS:
        return ChoiceFrontierController(
            authority,
            BEST_FIRST_SETTINGS[algorithm],
            accepted_delta_limit=16,
            max_budget=max_budget,
            retain_decision_evidence=False,
        )
    raise ValueError(f"node-choice algorithm is invalid: {algorithm}")


@dataclass(frozen=True, slots=True)
class NodeChoiceTask:
    """Episode identity and the reference expansion count R_t."""

    instance_id: str
    domain: str
    algorithm: str
    exact_expansions: int

    @property
    def decision_cap(self) -> int:
        """Binding budget: 2 x R_t for decisions and expansions."""

        return 2 * self.exact_expansions


@dataclass(frozen=True, slots=True)
class NodeChoiceRequest:
    session_id: str
    adapter_id: str | None
    seed: int
    instance_id: str
    decision_index: int
    model_input: dict[str, Any]
    menu_binding: list[dict[str, str]]


# (model_input, menu states in menu order) -> complete input tokens of the observation
TokenCounter = Callable[[dict[str, Any], list[CanonicalState]], int]


class NodeChoiceSession:
    """Incremental node-choice episode with a binding budget and the overflow rule."""

    def __init__(
        self,
        *,
        authority: PDDLStateAuthority,
        task: NodeChoiceTask,
        observation: str,
        arm: str,
        seed: int,
        adapter_id: str | None = None,
        decision_cap: int | None = None,
        token_limit: int | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        if arm not in ARMS:
            raise ValueError(f"node-choice episode arm is invalid: {arm}")
        if observation not in OBSERVATIONS:
            raise ValueError(f"node-choice observation is invalid: {observation}")
        if (token_limit is None) != (token_counter is None):
            raise ValueError("node-choice overflow rule needs both a token limit and a counter")
        self.authority = authority
        self.task = task
        self.observation = observation
        self.arm = arm
        self.seed = seed
        self.adapter_id = adapter_id
        self.decision_cap = decision_cap if decision_cap is not None else task.decision_cap
        self.token_limit = token_limit
        self.token_counter = token_counter
        self.controller = make_controller(authority, task.algorithm, self.decision_cap)
        self.random = random.Random(seed)
        self.events: list[dict[str, Any]] = []
        self.overflow: dict[str, int] | None = None
        self.termination_reason: str | None = "goal_reached" if authority.is_goal(authority.initial_state) else None
        self._pending: NodeChoiceRequest | None = None
        self.session_id = f"{arm}:{adapter_id or 'reference'}:{seed}:{observation}:{task.instance_id}"

    @property
    def complete(self) -> bool:
        return self.termination_reason is not None

    def next_request(self) -> NodeChoiceRequest | None:
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
            "representation": REPRESENTATIONS[self.observation],
            "schema_version": NODE_CHOICE_SCHEMA,
        }
        request = NodeChoiceRequest(
            session_id=self.session_id,
            adapter_id=self.adapter_id,
            seed=self.seed,
            instance_id=self.task.instance_id,
            decision_index=len(self.events),
            model_input=model_input,
            menu_binding=binding,
        )
        if self.token_counter is not None and self.token_limit is not None:
            tokens = self.token_counter(model_input, self._menu_states(binding))
            if tokens > self.token_limit:
                self.overflow = {"decision_index": len(self.events), "input_tokens": tokens}
                self.termination_reason = "observation_overflow"
                return None
        self._pending = request
        return request

    def _menu_states(self, binding: list[dict[str, str]]) -> list[CanonicalState]:
        return [self.controller._states_by_ref[entry["state_ref"]] for entry in binding]

    def menu_states(self, request: NodeChoiceRequest | None = None) -> list[CanonicalState]:
        """Menu states in menu order, resolved through the trusted controller."""

        request = request or self._pending
        if request is None:
            raise ValueError("node-choice episode has no pending request")
        return self._menu_states(request.menu_binding)

    def kappa_head_ref(self) -> str:
        head = self.controller.frontier_head_state_id()
        if head is None:
            raise ValueError("node-choice episode lost the frontier head")
        return self.controller._state_ref_by_id[head]

    def reference_output(self) -> str:
        if self._pending is None:
            raise ValueError("node-choice episode has no pending model request")
        if self.arm == "exact_reference":
            head_ref = self.kappa_head_ref()
            label = next(entry["choice"] for entry in self._pending.menu_binding if entry["state_ref"] == head_ref)
        elif self.arm == "random_valid":
            label = self.random.choice([entry["choice"] for entry in self._pending.menu_binding])
        else:
            raise ValueError(f"reference outputs exist for the control arms only: {self.arm}")
        return canonical_choice(label)

    def submit_output(self, output: str) -> None:
        if self._pending is None or self.complete:
            raise ValueError("node-choice episode has no pending model request")
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
            raise ValueError("node-choice episode is not complete")
        goal_reached = self.termination_reason == "goal_reached"
        return {
            "algorithm_invariants_hold": self.controller.invalid_operation_count == 0,
            "decision_count": len(self.events),
            "expansion_count": self.controller.expansion_count,
            "goal_reached": goal_reached,
            "invariant_valid_success": goal_reached and self.controller.invalid_operation_count == 0,
            "invalid_operation_count": self.controller.invalid_operation_count,
            "invalid_operation_rate": self.controller.invalid_operation_count / len(self.events) if self.events else 0.0,
            "model_call_limit": self.decision_cap,
            "observation_overflow": self.overflow,
            "termination_reason": self.termination_reason,
        }

    def episode(self) -> dict[str, Any]:
        if not self.complete or self._pending is not None:
            raise ValueError("node-choice episode is not complete")
        return {
            "adapter_id": self.adapter_id,
            "algorithm": self.task.algorithm,
            "arm": self.arm,
            "decision_cap": self.decision_cap,
            "events": self.events,
            "exact_reference_expansions": self.task.exact_expansions,
            "instance_id": self.task.instance_id,
            "observation": self.observation,
            "result": self.result(),
            "schema_version": EPISODE_SCHEMA,
            "seed": self.seed,
            "token_limit": self.token_limit,
        }


def run_control_episode(
    authority: PDDLStateAuthority,
    task: NodeChoiceTask,
    observation: str,
    arm: str,
    seed: int,
    *,
    decision_cap: int | None = None,
    token_limit: int | None = None,
    token_counter: TokenCounter | None = None,
    on_request: Callable[[NodeChoiceSession, NodeChoiceRequest], None] | None = None,
) -> NodeChoiceSession:
    """Run an exact_reference / random_valid episode to completion (CPU)."""

    session = NodeChoiceSession(
        authority=authority,
        task=task,
        observation=observation,
        arm=arm,
        seed=seed,
        decision_cap=decision_cap,
        token_limit=token_limit,
        token_counter=token_counter,
    )
    while (request := session.next_request()) is not None:
        if on_request is not None:
            on_request(session, request)
        session.submit_output(session.reference_output())
    return session


def replay_node_choice_episode(
    authority: PDDLStateAuthority,
    task: NodeChoiceTask,
    report: Mapping[str, Any],
    *,
    token_counter: TokenCounter | None = None,
    on_request: Callable[[NodeChoiceSession, NodeChoiceRequest], None] | None = None,
) -> NodeChoiceSession:
    """Recompute every menu, trusted transition and the overflow stop of a stored episode, exactly."""

    token_limit = report.get("token_limit")
    session = NodeChoiceSession(
        authority=authority,
        task=task,
        observation=report["observation"],
        arm=report["arm"],
        seed=int(report["seed"]),
        adapter_id=report.get("adapter_id"),
        decision_cap=int(report["decision_cap"]),
        token_limit=token_limit,
        token_counter=token_counter if token_limit is not None else None,
    )
    for event in report["events"]:
        request = session.next_request()
        if request is None:
            raise ValueError("node-choice replay ended before the stored events")
        if dict(request.model_input) != event["input"]:
            raise ValueError("node-choice replay input differs")
        if [dict(entry) for entry in request.menu_binding] != event["menu"]:
            raise ValueError("node-choice replay menu binding differs")
        if on_request is not None:
            on_request(session, request)
        session.submit_output(event["raw_output"])
        if session.events[-1]["trusted_runtime_result"] != event["trusted_runtime_result"]:
            raise ValueError("node-choice replay trusted runtime result differs")
    if session.next_request() is not None:
        raise ValueError("node-choice replay continued past the stored events")
    if not session.complete:
        raise ValueError("node-choice replay remained incomplete")
    if session.result() != report["result"]:
        raise ValueError("node-choice replay result differs")
    return session


def episode_digest(report: Mapping[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(canonical(dict(report)).encode()).hexdigest()


__all__ = [
    "ADDITIVE_ALGORITHMS",
    "ALGORITHMS",
    "ARMS",
    "EPISODE_SCHEMA",
    "KEYED_ALGORITHMS",
    "NODE_CHOICE_SCHEMA",
    "OBSERVATIONS",
    "OUTPUT_KEY",
    "REPRESENTATIONS",
    "SYSTEM_MESSAGES",
    "KeyedChoiceController",
    "NodeChoiceRequest",
    "NodeChoiceSession",
    "NodeChoiceTask",
    "TokenCounter",
    "canonical_choice",
    "episode_digest",
    "make_controller",
    "replay_node_choice_episode",
    "run_control_episode",
]
