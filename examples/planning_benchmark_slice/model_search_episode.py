"""Model-owned typed operations through the governed Search Episode Harness."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    RunReceipt,
    StopOutcome,
    evaluate_execution_permission,
)
from src.data_collect.replay import build_canonical_bundle, parse_canonical_bundle

from .bfs_model_input import build_bounded_bfs_model_input, build_bounded_bfs_model_input_v4
from .pddl_state import CanonicalState, PDDLStateAuthority
from .search_context import IncrementalSearchContext, RollingSearchContext, materialize_search_trace
from .search_episode import (
    TASK_SCHEMA_VERSION,
    SearchEpisodeError,
    _authority_from_task,
    _authorization_from_payload,
    _canonical_bytes,
    _gate_from_payload,
    _run_receipt_from_payload,
    _stopped_episode,
    _text_observation,
    _trace_limits,
)
from .search_memory import (
    AcceptedRetirement,
    AcceptedTransition,
    RejectedTransition,
    SearchMemory,
    SearchOperation,
    SearchRetireRequest,
    StateEvaluation,
    apply_search_retirement,
    apply_search_transition,
)
from .search_trace import (
    _decode_operation,
    _serialize_result,
    append_trusted_search_trace_record,
    replay_search_trace_segment,
    start_search_trace,
    verify_search_trace_segment,
)
from .validate_instance import load_fixture

MODEL_EVIDENCE_SCHEMA_VERSION = "model_search_episode_evidence_v1"
MODEL_REQUEST_SCHEMA_VERSION_V3 = "model_search_episode_request_v3"
MODEL_REQUEST_SCHEMA_VERSION_V4 = "model_search_episode_request_v4"
MODEL_REQUEST_SCHEMA_VERSION = "model_search_episode_request_v2"
_LEGACY_MODEL_REQUEST_SCHEMA_VERSION = "model_search_episode_request_v1"
_MODEL_BUNDLE_ARTIFACTS = {
    "authorization-receipt.json",
    "expansions.json",
    "gate-receipt.json",
    "model.json",
    "policy-events.json",
    "request.json",
    "result.json",
    "run-receipt.json",
    "search-trace.json",
    "task.json",
}

ModelPolicy = Callable[[Mapping[str, Any]], str]


@dataclass(frozen=True, slots=True)
class SearchPolicyRequest:
    """One canonical model request emitted by an incremental episode session."""

    session_id: str
    adapter_id: str | None
    seed: int
    instance_id: str
    decision_index: int
    model_input: Mapping[str, Any]

    @property
    def canonical_input(self) -> bytes:
        return _canonical_bytes(dict(self.model_input))


def run_model_search_episode(
    task_path: str | Path,
    *,
    algorithm: str,
    modality: str,
    arm: str,
    model_identity: Mapping[str, Any],
    policy: ModelPolicy,
    max_expansions: int,
    max_input_bytes: int,
    max_output_tokens: int,
    accepted_delta_limit: int,
    model_input_projection: str,
    seed: int,
    gate_receipt: GateReceipt,
    authorization_receipt: AuthorizationReceipt | None,
    ancestor_receipt_id: str | None = None,
    max_model_calls: int | None = None,
    adapter_id: str | None = None,
) -> dict[str, Any]:
    """Run model-emitted typed BFS operations without repairing model output."""

    if not isinstance(gate_receipt, GateReceipt):
        raise SearchEpisodeError("gate_receipt must expose a governed binding")
    permission = evaluate_execution_permission(
        binding=gate_receipt.binding,
        gate_receipt=gate_receipt,
        authorization_receipt=authorization_receipt,
        ancestor_receipt_id=ancestor_receipt_id,
    )
    if not permission.start_permitted:
        return _stopped_episode(permission)

    _validate_model_request(
        algorithm=algorithm,
        modality=modality,
        arm=arm,
        model_identity=model_identity,
        policy=policy,
        max_expansions=max_expansions,
        max_input_bytes=max_input_bytes,
        max_output_tokens=max_output_tokens,
        accepted_delta_limit=accepted_delta_limit,
        model_input_projection=model_input_projection,
        seed=seed,
        max_model_calls=max_model_calls,
    )
    fixture = load_fixture(Path(task_path))
    task = {
        "domain_pddl": fixture.domain_pddl,
        "instance_id": str(fixture.payload.get("instance_id") or ""),
        "problem_pddl": fixture.problem_pddl,
        "schema_version": TASK_SCHEMA_VERSION,
    }
    assert authorization_receipt is not None
    return _execute_authorized_model_episode(
        task=task,
        algorithm=algorithm,
        modality=modality,
        arm=arm,
        model_identity=model_identity,
        policy=policy,
        max_expansions=max_expansions,
        max_input_bytes=max_input_bytes,
        max_output_tokens=max_output_tokens,
        accepted_delta_limit=accepted_delta_limit,
        model_input_projection=model_input_projection,
        seed=seed,
        gate_receipt=gate_receipt,
        authorization_receipt=authorization_receipt,
        max_model_calls=max_model_calls,
        adapter_id=adapter_id,
    )


def replay_model_search_episode(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Verify receipts, events, and trusted state effects without rerunning the model."""

    expected_fields = {"bundle", "bundle_encoding", "expansions", "policy_events", "schema_version"}
    if not isinstance(evidence, Mapping) or set(evidence) != expected_fields:
        raise SearchEpisodeError("model evidence has invalid fields")
    if evidence["schema_version"] != MODEL_EVIDENCE_SCHEMA_VERSION or evidence["bundle_encoding"] != "base64":
        raise SearchEpisodeError("model evidence schema or encoding is invalid")
    encoded_bundle = evidence["bundle"]
    if not isinstance(encoded_bundle, str):
        raise SearchEpisodeError("model evidence bundle must be base64 text")
    try:
        bundle = base64.b64decode(encoded_bundle.encode("ascii"), validate=True)
        artifacts = parse_canonical_bundle(bundle)
    except (UnicodeEncodeError, ValueError) as error:
        raise SearchEpisodeError("model evidence bundle is invalid") from error
    if set(artifacts) != _MODEL_BUNDLE_ARTIFACTS:
        raise SearchEpisodeError("model evidence bundle has missing or unexpected artifacts")

    expansions = _load_canonical_json(artifacts["expansions.json"], "model expansions")
    policy_events = _load_canonical_json(artifacts["policy-events.json"], "model policy events")
    result = _load_canonical_json(artifacts["result.json"], "model result")
    task = _load_canonical_json(artifacts["task.json"], "model task")
    request = _load_canonical_json(artifacts["request.json"], "model request")
    model = _load_canonical_json(artifacts["model.json"], "model identity")
    if evidence["expansions"] != expansions or evidence["policy_events"] != policy_events:
        raise SearchEpisodeError("public model evidence differs from its bundle")
    if (
        request.get("schema_version")
        not in {
            _LEGACY_MODEL_REQUEST_SCHEMA_VERSION,
            MODEL_REQUEST_SCHEMA_VERSION,
            MODEL_REQUEST_SCHEMA_VERSION_V3,
            MODEL_REQUEST_SCHEMA_VERSION_V4,
        }
        or request.get("model") != model
    ):
        raise SearchEpisodeError("model request artifact is invalid")
    if request["schema_version"] in {
        MODEL_REQUEST_SCHEMA_VERSION,
        MODEL_REQUEST_SCHEMA_VERSION_V3,
        MODEL_REQUEST_SCHEMA_VERSION_V4,
    }:
        _validate_projection_request(request)

    gate = _gate_from_payload(_load_canonical_json(artifacts["gate-receipt.json"], "model gate receipt"))
    authorization = _authorization_from_payload(
        _load_canonical_json(artifacts["authorization-receipt.json"], "model authorization receipt")
    )
    completed = _run_receipt_from_payload(_load_canonical_json(artifacts["run-receipt.json"], "model run receipt"))
    permission = evaluate_execution_permission(
        binding=gate.binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )
    if not permission.start_permitted:
        raise SearchEpisodeError("bundled model receipts do not authorize replay")
    if (
        completed.binding != gate.binding
        or completed.outcome is not StopOutcome.PASS
        or completed.run_state != "completed"
        or not completed.scientific_completion
        or result.get("run_receipt") != completed.to_dict()
    ):
        raise SearchEpisodeError("completed model run receipt is invalid")

    max_expansions = request.get("max_expansions")
    if isinstance(max_expansions, bool) or not isinstance(max_expansions, int) or max_expansions <= 0:
        raise SearchEpisodeError("model request expansion budget is invalid")
    if request["schema_version"] == MODEL_REQUEST_SCHEMA_VERSION_V4:
        max_model_calls = request.get("max_model_calls")
        if isinstance(max_model_calls, bool) or not isinstance(max_model_calls, int) or max_model_calls <= 0:
            raise SearchEpisodeError("model request decision budget is invalid")
    else:
        max_model_calls = max(1, len(policy_events))
    authority = _authority_from_task(task)
    limits = _trace_limits(authority, max_expansions)
    replay_search_trace_segment(artifacts["search-trace.json"], authority=authority, limits=limits)
    _verify_model_event_summary(
        policy_events,
        expansions,
        result,
        max_expansions,
        max_model_calls=max_model_calls,
        request=request,
    )
    replayed_evidence = {
        "bundle": encoded_bundle,
        "bundle_encoding": "base64",
        "expansions": expansions,
        "policy_events": policy_events,
        "schema_version": MODEL_EVIDENCE_SCHEMA_VERSION,
    }
    return {"result": result, "evidence": replayed_evidence}


def _execute_authorized_model_episode(
    *,
    task: Mapping[str, Any],
    algorithm: str,
    modality: str,
    arm: str,
    model_identity: Mapping[str, Any],
    policy: ModelPolicy,
    max_expansions: int,
    max_input_bytes: int,
    max_output_tokens: int,
    accepted_delta_limit: int,
    model_input_projection: str,
    seed: int,
    gate_receipt: GateReceipt,
    authorization_receipt: AuthorizationReceipt,
    max_model_calls: int | None,
    adapter_id: str | None,
) -> dict[str, Any]:
    session = SearchEpisodeSession(
        task=task,
        algorithm=algorithm,
        modality=modality,
        arm=arm,
        model_identity=model_identity,
        max_expansions=max_expansions,
        max_model_calls=max_model_calls,
        max_input_bytes=max_input_bytes,
        max_output_tokens=max_output_tokens,
        accepted_delta_limit=accepted_delta_limit,
        model_input_projection=model_input_projection,
        seed=seed,
        gate_receipt=gate_receipt,
        authorization_receipt=authorization_receipt,
        adapter_id=adapter_id,
    )
    while (request := session.next_request()) is not None:
        session.submit_output(policy(request.model_input))
    return session.episode()


class SearchEpisodeSession:
    """Incremental trusted-runtime BFS episode with one outstanding request."""

    def __init__(
        self,
        *,
        task: Mapping[str, Any],
        algorithm: str,
        modality: str,
        arm: str,
        model_identity: Mapping[str, Any],
        max_expansions: int,
        max_model_calls: int | None,
        max_input_bytes: int,
        max_output_tokens: int,
        accepted_delta_limit: int,
        model_input_projection: str,
        seed: int,
        gate_receipt: GateReceipt,
        authorization_receipt: AuthorizationReceipt,
        adapter_id: str | None = None,
        authority: PDDLStateAuthority | None = None,
    ) -> None:
        if algorithm != "bfs" or modality != "text-state":
            raise SearchEpisodeError("incremental session supports only BFS text-state")
        for name, value in (
            ("max_expansions", max_expansions),
            ("max_input_bytes", max_input_bytes),
            ("max_output_tokens", max_output_tokens),
            ("accepted_delta_limit", accepted_delta_limit),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise SearchEpisodeError(f"{name} must be a positive integer")
        if max_model_calls is not None and (
            isinstance(max_model_calls, bool) or not isinstance(max_model_calls, int) or max_model_calls <= 0
        ):
            raise SearchEpisodeError("max_model_calls must be a positive integer")
        if not isinstance(gate_receipt, GateReceipt) or not isinstance(authorization_receipt, AuthorizationReceipt):
            raise SearchEpisodeError("incremental session requires governed receipts")
        permission = evaluate_execution_permission(
            binding=gate_receipt.binding,
            gate_receipt=gate_receipt,
            authorization_receipt=authorization_receipt,
        )
        if not permission.start_permitted:
            raise SearchEpisodeError("incremental session requires matching PASS authorization receipts")
        self.task = dict(task)
        self.algorithm = algorithm
        self.modality = modality
        self.arm = arm
        self.model_identity = _normalized_model_identity(model_identity)
        self.max_expansions = max_expansions
        self._explicit_model_call_budget = max_model_calls is not None
        self.max_input_bytes = max_input_bytes
        self.max_output_tokens = max_output_tokens
        self.accepted_delta_limit = accepted_delta_limit
        self.model_input_projection = model_input_projection
        self.seed = seed
        self.gate_receipt = gate_receipt
        self.authorization_receipt = authorization_receipt
        self.adapter_id = adapter_id if adapter_id is not None else self.model_identity.get("adapter_path")
        if authority is not None and not isinstance(authority, PDDLStateAuthority):
            raise TypeError("authority must be a PDDLStateAuthority")
        self.authority = _authority_from_task(task) if authority is None else authority
        initial_memory = SearchMemory.initial(self.authority)
        self.limits = _trace_limits(self.authority, max_expansions)
        self.max_model_calls = self.limits.max_records if max_model_calls is None else max_model_calls
        self.context = IncrementalSearchContext(
            initial_memory,
            accepted_delta_limit=accepted_delta_limit,
            limits=self.limits,
        )
        self.trace = start_search_trace(initial_memory, limits=self.limits)
        self.expansions: list[dict[str, Any]] = []
        self.policy_events: list[dict[str, Any]] = []
        self._event_record_indices: list[int] = []
        self.invalid_operation_count = 0
        self.budget_used = 0
        self.termination_reason: str | None = None
        self.exited_through_goal_check = False
        self._frontier_before: list[str] | None = None
        self._expanded_state_id: str | None = None
        self._expanded_state: CanonicalState | None = None
        self._enqueued_state_ids: list[str] = []
        self._pending: SearchPolicyRequest | None = None
        self._episode: dict[str, Any] | None = None
        self.deterministic_memoized = (
            self.model_identity.get("decoding") == "greedy"
            and self.model_identity.get("memoize_identical_inputs") is True
        )
        self.session_id = f"{self.arm}:{self.adapter_id or 'base'}:{self.seed}:{self.task['instance_id']}"

    @property
    def complete(self) -> bool:
        return self.termination_reason is not None

    def next_request(self) -> SearchPolicyRequest | None:
        if self._pending is not None:
            return self._pending
        self._prepare_decision()
        if self.complete:
            return None
        assert self._expanded_state is not None
        if len(self.policy_events) >= self.max_model_calls:
            self.termination_reason = "decision_budget_exhausted"
            return None
        rolling_context = self.context.rolling_context()
        model_input = _model_input_from_context(
            state=self._expanded_state,
            memory=self.context.memory,
            rolling_context=rolling_context,
            authority=self.authority,
            max_input_bytes=self.max_input_bytes,
            projection=self.model_input_projection,
        )
        self._pending = SearchPolicyRequest(
            session_id=self.session_id,
            adapter_id=self.adapter_id,
            seed=self.seed,
            instance_id=str(self.task["instance_id"]),
            decision_index=len(self.policy_events),
            model_input=model_input,
        )
        return self._pending

    def submit_output(self, raw_output: str) -> None:
        request = self._pending
        if request is None:
            raise SearchEpisodeError("submit_output requires an outstanding model request")
        if not isinstance(raw_output, str):
            raise SearchEpisodeError("model policy must return text")
        assert self._expanded_state_id is not None and self._expanded_state is not None
        before = self.context.memory
        record_index = self.trace.record_count
        parsed, parse_error = _parse_model_output(raw_output)
        operation = parsed["operation"] if parsed is not None else None
        rationale = parsed["rationale"] if parsed is not None else ""
        result, invariant_error = _apply_bfs_model_operation(
            memory=before,
            authority=self.authority,
            expanded_state_id=self._expanded_state_id,
            operation=operation,
        )
        error = parse_error or invariant_error
        event: dict[str, Any] = {
            "budget_charge": 0,
            "input": dict(request.model_input),
            "raw_output": raw_output,
            "runtime_result": None,
            "status": "accepted",
            "trace_record_index": None,
        }
        self._event_record_indices.append(record_index)
        self._pending = None
        if error is not None or isinstance(result, RejectedTransition):
            self.invalid_operation_count += 1
            self.budget_used += 1
            reason = error or result.reason
            event.update(
                {
                    "budget_charge": 1,
                    "runtime_result": {"budget_charge": 1, "reason": reason, "status": "rejected"},
                    "status": "rejected",
                }
            )
            self.policy_events.append(event)
            if self.deterministic_memoized:
                self.termination_reason = "deterministic_invalid_operation"
            return

        assert operation is not None and isinstance(result, (AcceptedTransition, AcceptedRetirement))
        self.trace = append_trusted_search_trace_record(
            self.trace,
            memory_before=before,
            observation=_text_observation(self._expanded_state, before),
            rationale=rationale,
            operation=operation,
            result=result,
            limits=self.limits,
        )
        self.context.accept(record_index=record_index, operation=operation, result=result)
        event["runtime_result"] = _serialize_result(result)
        event["trace_record_index"] = record_index
        self.policy_events.append(event)

        expansion_complete = isinstance(result, AcceptedRetirement)
        if isinstance(result, AcceptedTransition):
            self._enqueued_state_ids.append(result.transition.target_state.state_id)
            expansion_complete = (
                self._expanded_state_id not in self.context.memory.frontier
                and not _unvisited_successors(self.authority, self._expanded_state, self.context.memory)
            )
        if expansion_complete:
            self._complete_expansion()

    def episode(self) -> dict[str, Any]:
        if not self.complete or self._pending is not None:
            raise SearchEpisodeError("episode is not complete")
        if self._episode is None:
            self._episode = self._build_episode()
        return self._episode

    def _prepare_decision(self) -> None:
        if self.complete or self._expanded_state_id is not None:
            return
        memory = self.context.memory
        if not memory.frontier:
            self.termination_reason = "frontier_exhausted"
            return
        if self.budget_used >= self.max_expansions:
            self.termination_reason = "budget_exhausted"
            return
        state_id = memory.frontier[0]
        state = memory.state(state_id)
        if self.authority.is_goal(state):
            self.exited_through_goal_check = True
            self.termination_reason = "goal_reached"
            return
        self._frontier_before = list(memory.frontier)
        self._expanded_state_id = state_id
        self._expanded_state = state
        self._enqueued_state_ids = []

    def _complete_expansion(self) -> None:
        assert self._frontier_before is not None and self._expanded_state_id is not None
        frontier_after = list(self.context.memory.frontier)
        expected_frontier = [*self._frontier_before[1:], *self._enqueued_state_ids]
        if frontier_after != expected_frontier:
            raise SearchEpisodeError("model-owned BFS violated FIFO frontier discipline")
        self.expansions.append(
            {
                "expanded_state_id": self._expanded_state_id,
                "frontier_after": frontier_after,
                "frontier_before": self._frontier_before,
                "enqueued_state_ids": list(self._enqueued_state_ids),
            }
        )
        self.budget_used += 1
        self._frontier_before = None
        self._expanded_state_id = None
        self._expanded_state = None
        self._enqueued_state_ids = []

    def _build_episode(self) -> dict[str, Any]:
        trace_bytes = self.trace.to_bytes()
        verify_search_trace_segment(trace_bytes, limits=self.limits)
        replayed_tail = replay_search_trace_segment(trace_bytes, authority=self.authority, limits=self.limits)
        if replayed_tail.to_bytes() != self.context.memory.to_bytes():
            raise SearchEpisodeError("incremental Search Memory differs from completed trace replay")
        materialized = materialize_search_trace(
            trace_bytes,
            authority=self.authority,
            limits=self.limits,
            include_atomic_segments=False,
        )
        replay_contexts = materialized.rolling_contexts_before(
            tuple(self._event_record_indices),
            accepted_delta_limit=self.accepted_delta_limit,
        )
        for event, rolling_context in zip(self.policy_events, replay_contexts, strict=True):
            state_id = event["input"]["observation"]["state_id"]
            replay_memory = rolling_context.checkpoint.restore(self.authority)
            replay_input = _model_input_from_context(
                state=replay_memory.state(state_id),
                memory=replay_memory,
                rolling_context=rolling_context,
                authority=self.authority,
                max_input_bytes=self.max_input_bytes,
                projection=self.model_input_projection,
            )
            if _canonical_bytes(replay_input) != _canonical_bytes(event["input"]):
                raise SearchEpisodeError("incremental model input differs from completed trace replay")

        completed = RunReceipt(
            binding=self.gate_receipt.binding,
            outcome=StopOutcome.PASS,
            run_state="completed",
            start_permitted=False,
            scientific_completion=True,
            gate_receipt_id=self.gate_receipt.receipt_id,
            authorization_receipt_id=self.authorization_receipt.receipt_id,
        )
        goal_reached = self.exited_through_goal_check
        result_payload = {
            "algorithm_invariants_hold": True,
            "budget_used": self.budget_used,
            "completion": "completed",
            "decision_count": len(self.policy_events),
            "expansion_count": len(self.expansions),
            "goal_reached": goal_reached,
            "invariant_valid_success": goal_reached and self.termination_reason == "goal_reached",
            "invalid_operation_count": self.invalid_operation_count,
            "invalid_operation_rate": (
                self.invalid_operation_count / len(self.policy_events) if self.policy_events else 0.0
            ),
            "outcome": StopOutcome.PASS.value,
            "run_receipt": completed.to_dict(),
            "scientific_completion": True,
            "termination_reason": self.termination_reason,
        }
        request_payload = {
            "accepted_delta_limit": self.accepted_delta_limit,
            "algorithm": self.algorithm,
            "arm": self.arm,
            "max_input_bytes": self.max_input_bytes,
            "max_expansions": self.max_expansions,
            "max_output_tokens": self.max_output_tokens,
            "model_input_projection": self.model_input_projection,
            "modality": self.modality,
            "model": self.model_identity,
            "schema_version": (
                MODEL_REQUEST_SCHEMA_VERSION_V4
                if self._explicit_model_call_budget
                else (
                    MODEL_REQUEST_SCHEMA_VERSION_V3
                    if self.model_input_projection == "bounded_bfs_search_memory_v4"
                    else MODEL_REQUEST_SCHEMA_VERSION
                )
            ),
            "seed": self.seed,
        }
        if self._explicit_model_call_budget:
            request_payload["max_model_calls"] = self.max_model_calls
        artifacts = {
            "authorization-receipt.json": _canonical_bytes(self.authorization_receipt.to_dict()),
            "expansions.json": _canonical_bytes(self.expansions),
            "gate-receipt.json": _canonical_bytes(self.gate_receipt.to_dict()),
            "model.json": _canonical_bytes(self.model_identity),
            "policy-events.json": _canonical_bytes(self.policy_events),
            "request.json": _canonical_bytes(request_payload),
            "result.json": _canonical_bytes(result_payload),
            "run-receipt.json": _canonical_bytes(completed.to_dict()),
            "search-trace.json": trace_bytes,
            "task.json": _canonical_bytes(self.task),
        }
        bundle = build_canonical_bundle(artifacts)
        evidence = {
            "bundle": base64.b64encode(bundle).decode("ascii"),
            "bundle_encoding": "base64",
            "expansions": self.expansions,
            "policy_events": self.policy_events,
            "schema_version": MODEL_EVIDENCE_SCHEMA_VERSION,
        }
        return {"result": result_payload, "evidence": evidence}


def _model_input_from_context(
    *,
    state: CanonicalState,
    memory: SearchMemory,
    rolling_context: RollingSearchContext,
    authority: PDDLStateAuthority,
    max_input_bytes: int,
    projection: str,
) -> dict[str, Any]:
    if projection == "bounded_bfs_search_memory_v3":
        model_input, _dropped = build_bounded_bfs_model_input(
            goal_atoms=list(authority.goal_atoms or ()),
            observation=_text_observation(state, memory),
            checkpoint=rolling_context.checkpoint,
            accepted_deltas=rolling_context.accepted_deltas,
            max_bytes=max_input_bytes,
        )
        return model_input
    if projection == "bounded_bfs_search_memory_v4":
        model_input, _dropped = build_bounded_bfs_model_input_v4(
            authority=authority,
            goal_atoms=list(authority.goal_atoms or ()),
            observation=_text_observation(state, memory),
            checkpoint=rolling_context.checkpoint,
            accepted_deltas=rolling_context.accepted_deltas,
            max_bytes=max_input_bytes,
        )
        return model_input
    if projection != "rolling_search_context_v1":
        raise SearchEpisodeError(f"unsupported model input projection: {projection}")
    return {
        "goal_atoms": list(authority.goal_atoms or ()),
        "observation": _text_observation(state, memory),
        "search_memory": json.loads(rolling_context.to_bytes()),
    }


def _apply_bfs_model_operation(
    *,
    memory: SearchMemory,
    authority: PDDLStateAuthority,
    expanded_state_id: str,
    operation: SearchOperation | None,
) -> tuple[AcceptedTransition | AcceptedRetirement | RejectedTransition | None, str | None]:
    if operation is None:
        return None, "model output does not contain a typed operation"
    state = memory.state(expanded_state_id)
    remaining = _unvisited_successors(authority, state, memory)
    if isinstance(operation, SearchRetireRequest):
        if remaining:
            return None, "BFS retirement omitted unvisited successors"
        if not memory.frontier or memory.frontier[0] != expanded_state_id or operation.state_id != expanded_state_id:
            return None, "BFS retirement must retire the current frontier head"
        result = apply_search_retirement(memory, operation)
        return result, None

    if operation.source_state_id != expanded_state_id:
        return None, "BFS transition source must be the current expansion state"
    if not operation.visit_target or operation.evaluate_target:
        return None, "BFS transition must visit the target without heuristic evaluation"
    source_is_frontier_head = bool(memory.frontier and memory.frontier[0] == expanded_state_id)
    expected_position = len(memory.frontier) - (1 if source_is_frontier_head else 0)
    if operation.frontier_intent.retire_source is not source_is_frontier_head:
        return None, "the first BFS successor must retire the frontier head exactly once"
    if operation.frontier_intent.target_position != expected_position:
        return None, "BFS successors must be appended at the frontier tail"
    try:
        preview = authority.preview_apply(state, operation.action)
    except (ValueError, KeyError) as error:
        return None, str(error)
    if preview.target_state.state_id in memory.visited:
        return None, "BFS successor target was already visited"
    expected_action = next(
        action
        for action in authority.applicable_actions(state)
        if authority.preview_apply(state, action).target_state.state_id not in memory.visited
    )
    if operation.action != expected_action:
        return None, "BFS transition must select the first canonical unvisited successor"
    result = apply_search_transition(memory, operation, evaluator=_unexpected_evaluator)
    return result, None


def _unvisited_successors(
    authority: PDDLStateAuthority,
    state: CanonicalState,
    memory: SearchMemory,
) -> tuple[str, ...]:
    return tuple(
        preview.target_state.state_id
        for action in authority.applicable_actions(state)
        if (preview := authority.preview_apply(state, action)).target_state.state_id not in memory.visited
    )


def _parse_model_output(raw_output: str) -> tuple[dict[str, Any] | None, str | None]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate model output field: {key}")
            value[key] = item
        return value

    def reject_constant(value: str) -> NoReturn:
        raise ValueError(f"invalid model output number: {value}")

    try:
        parsed = json.loads(raw_output, object_pairs_hook=reject_duplicates, parse_constant=reject_constant)
        required_fields = {"canonical_rationale", "runtime_result", "typed_operation"}
        if not isinstance(parsed, dict) or set(parsed) != required_fields:
            raise ValueError(
                "model output must contain exactly canonical_rationale, runtime_result, and typed_operation"
            )
        if parsed["runtime_result"] is not None:
            raise ValueError("runtime_result must be null")
        rationale = parsed["canonical_rationale"]
        if not isinstance(rationale, str):
            raise ValueError("canonical_rationale must be text")
        operation = _decode_operation(parsed["typed_operation"])
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        return None, str(error)
    return {"operation": operation, "rationale": rationale}, None


def _normalized_model_identity(model_identity: Mapping[str, Any]) -> dict[str, Any]:
    try:
        normalized = json.loads(_canonical_bytes(dict(model_identity)))
    except (TypeError, ValueError) as error:
        raise SearchEpisodeError("model_identity must be JSON serializable") from error
    if not isinstance(normalized, dict):
        raise SearchEpisodeError("model_identity must be an object")
    return normalized


def _validate_model_request(
    *,
    algorithm: str,
    modality: str,
    arm: str,
    model_identity: Mapping[str, Any],
    policy: ModelPolicy,
    max_expansions: int,
    max_input_bytes: int,
    max_output_tokens: int,
    accepted_delta_limit: int,
    model_input_projection: str,
    seed: int,
    max_model_calls: int | None,
) -> None:
    if algorithm != "bfs" or modality != "text-state":
        raise SearchEpisodeError("model episode slice supports only BFS text-state")
    if not isinstance(arm, str) or not arm:
        raise SearchEpisodeError("model episode arm must be non-empty text")
    _normalized_model_identity(model_identity)
    if not callable(policy):
        raise SearchEpisodeError("model policy must be callable")
    for name, value in (
        ("max_expansions", max_expansions),
        ("max_input_bytes", max_input_bytes),
        ("max_output_tokens", max_output_tokens),
        ("accepted_delta_limit", accepted_delta_limit),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise SearchEpisodeError(f"{name} must be a positive integer")
    if max_model_calls is not None and (
        isinstance(max_model_calls, bool) or not isinstance(max_model_calls, int) or max_model_calls <= 0
    ):
        raise SearchEpisodeError("max_model_calls must be a positive integer")
    if model_input_projection not in {
        "bounded_bfs_search_memory_v3",
        "bounded_bfs_search_memory_v4",
        "rolling_search_context_v1",
    }:
        raise SearchEpisodeError("model_input_projection is unsupported")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise SearchEpisodeError("seed must be an integer")


def _verify_model_event_summary(
    events: Any,
    expansions: Any,
    result: Any,
    max_expansions: int,
    max_model_calls: int,
    *,
    request: Mapping[str, Any],
) -> None:
    if not isinstance(events, list) or not isinstance(expansions, list) or not isinstance(result, dict):
        raise SearchEpisodeError("model evidence summary is malformed")
    invalid_count = sum(1 for event in events if isinstance(event, dict) and event.get("status") == "rejected")
    budget_used = invalid_count + len(expansions)
    if (
        result.get("decision_count") != len(events)
        or result.get("invalid_operation_count") != invalid_count
        or result.get("expansion_count") != len(expansions)
        or result.get("budget_used") != budget_used
        or budget_used > max_expansions
        or len(events) > max_model_calls
    ):
        raise SearchEpisodeError("model evidence summary differs from its events")
    expected_rate = invalid_count / len(events) if events else 0.0
    if result.get("invalid_operation_rate") != expected_rate:
        raise SearchEpisodeError("model invalid-operation rate differs from its events")
    if request.get("schema_version") in {MODEL_REQUEST_SCHEMA_VERSION_V3, MODEL_REQUEST_SCHEMA_VERSION_V4}:
        goal_reached = result.get("goal_reached") is True
        strict_success = (
            goal_reached
            and result.get("termination_reason") == "goal_reached"
            and result.get("algorithm_invariants_hold") is True
        )
        if result.get("invariant_valid_success") is not strict_success:
            raise SearchEpisodeError("model invariant-valid success differs from strict v5 adjudication")


def _validate_projection_request(request: Mapping[str, Any]) -> None:
    max_input_bytes = request.get("max_input_bytes")
    if isinstance(max_input_bytes, bool) or not isinstance(max_input_bytes, int) or max_input_bytes <= 0:
        raise SearchEpisodeError("model request input budget is invalid")
    if request.get("model_input_projection") not in {
        "bounded_bfs_search_memory_v3",
        "bounded_bfs_search_memory_v4",
        "rolling_search_context_v1",
    }:
        raise SearchEpisodeError("model request input projection is invalid")


def _load_canonical_json(payload: bytes, label: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SearchEpisodeError(f"duplicate field in {label}: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SearchEpisodeError(f"{label} is not valid JSON") from error
    if _canonical_bytes(value) != payload:
        raise SearchEpisodeError(f"{label} is not canonical JSON")
    return value


def _unexpected_evaluator(_state: CanonicalState) -> StateEvaluation:
    raise AssertionError("BFS transitions do not request state evaluation")


__all__ = [
    "MODEL_EVIDENCE_SCHEMA_VERSION",
    "ModelPolicy",
    "replay_model_search_episode",
    "run_model_search_episode",
]
