"""Model-owned typed operations through the governed Search Episode Harness."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
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

from .bfs_model_input import build_bounded_bfs_model_input
from .pddl_state import CanonicalState, PDDLStateAuthority
from .search_context import materialize_search_trace
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
    append_search_trace_record,
    replay_search_trace_segment,
    start_search_trace,
)
from .validate_instance import load_fixture

MODEL_EVIDENCE_SCHEMA_VERSION = "model_search_episode_evidence_v1"
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
    if request.get("schema_version") not in {
        _LEGACY_MODEL_REQUEST_SCHEMA_VERSION,
        MODEL_REQUEST_SCHEMA_VERSION,
    } or request.get("model") != model:
        raise SearchEpisodeError("model request artifact is invalid")
    if request["schema_version"] == MODEL_REQUEST_SCHEMA_VERSION:
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
    authority = _authority_from_task(task)
    limits = _trace_limits(authority, max_expansions)
    replay_search_trace_segment(artifacts["search-trace.json"], authority=authority, limits=limits)
    _verify_model_event_summary(policy_events, expansions, result, max_expansions)
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
) -> dict[str, Any]:
    authority = _authority_from_task(task)
    memory = SearchMemory.initial(authority)
    limits = _trace_limits(authority, max_expansions)
    trace = start_search_trace(memory, limits=limits)
    expansions: list[dict[str, Any]] = []
    policy_events: list[dict[str, Any]] = []
    invalid_operation_count = 0
    budget_used = 0
    termination_reason: str | None = None
    deterministic_memoized = (
        model_identity.get("decoding") == "greedy"
        and model_identity.get("memoize_identical_inputs") is True
    )

    while memory.frontier and budget_used < max_expansions:
        frontier_before = list(memory.frontier)
        expanded_state_id = frontier_before[0]
        state = memory.state(expanded_state_id)
        if authority.is_goal(state):
            break
        enqueued_state_ids: list[str] = []
        expansion_complete = False

        while budget_used < max_expansions and not expansion_complete:
            model_input = _model_input(
                state=state,
                memory=memory,
                trace_bytes=trace.to_bytes(),
                authority=authority,
                max_expansions=max_expansions,
                accepted_delta_limit=accepted_delta_limit,
                max_input_bytes=max_input_bytes,
                projection=model_input_projection,
            )
            raw_output = policy(model_input)
            if not isinstance(raw_output, str):
                raise SearchEpisodeError("model policy must return text")
            parsed, parse_error = _parse_model_output(raw_output)
            operation = parsed["operation"] if parsed is not None else None
            rationale = parsed["rationale"] if parsed is not None else ""
            before = memory
            result, invariant_error = _apply_bfs_model_operation(
                memory=before,
                authority=authority,
                expanded_state_id=expanded_state_id,
                operation=operation,
            )
            error = parse_error or invariant_error
            event: dict[str, Any] = {
                "budget_charge": 0,
                "input": model_input,
                "raw_output": raw_output,
                "runtime_result": None,
                "status": "accepted",
                "trace_record_index": None,
            }
            if error is not None or isinstance(result, RejectedTransition):
                invalid_operation_count += 1
                budget_used += 1
                reason = error or result.reason
                event.update(
                    {
                        "budget_charge": 1,
                        "runtime_result": {"budget_charge": 1, "reason": reason, "status": "rejected"},
                        "status": "rejected",
                    }
                )
                policy_events.append(event)
                if deterministic_memoized:
                    termination_reason = "deterministic_invalid_operation"
                    break
                continue

            assert operation is not None
            trace_record_index = json.loads(trace.to_bytes())["record_count"]
            trace = append_search_trace_record(
                trace,
                memory_before=before,
                observation=_text_observation(state, before),
                rationale=rationale,
                operation=operation,
                result=result,
                limits=limits,
            )
            memory = result.memory
            event["runtime_result"] = _serialize_result(result)
            event["trace_record_index"] = trace_record_index
            policy_events.append(event)

            if isinstance(result, AcceptedTransition):
                enqueued_state_ids.append(result.transition.target_state.state_id)
                expansion_complete = expanded_state_id not in memory.frontier and not _unvisited_successors(
                    authority, state, memory
                )
            elif isinstance(result, AcceptedRetirement):
                expansion_complete = True

        if not expansion_complete:
            break
        frontier_after = list(memory.frontier)
        expected_frontier = [*frontier_before[1:], *enqueued_state_ids]
        if frontier_after != expected_frontier:
            raise SearchEpisodeError("model-owned BFS violated FIFO frontier discipline")
        expansions.append(
            {
                "expanded_state_id": expanded_state_id,
                "frontier_after": frontier_after,
                "frontier_before": frontier_before,
                "enqueued_state_ids": enqueued_state_ids,
            }
        )
        budget_used += 1

    goal_reached = bool(memory.frontier and authority.is_goal(memory.state(memory.frontier[0])))
    if termination_reason is None:
        if goal_reached:
            termination_reason = "goal_reached"
        elif budget_used >= max_expansions:
            termination_reason = "budget_exhausted"
        elif not memory.frontier:
            termination_reason = "frontier_exhausted"
        else:
            termination_reason = "incomplete_expansion"
    completed = RunReceipt(
        binding=gate_receipt.binding,
        outcome=StopOutcome.PASS,
        run_state="completed",
        start_permitted=False,
        scientific_completion=True,
        gate_receipt_id=gate_receipt.receipt_id,
        authorization_receipt_id=authorization_receipt.receipt_id,
    )
    result_payload = {
        "algorithm_invariants_hold": True,
        "budget_used": budget_used,
        "completion": "completed",
        "decision_count": len(policy_events),
        "expansion_count": len(expansions),
        "goal_reached": goal_reached,
        "invalid_operation_count": invalid_operation_count,
        "invalid_operation_rate": invalid_operation_count / len(policy_events) if policy_events else 0.0,
        "outcome": StopOutcome.PASS.value,
        "run_receipt": completed.to_dict(),
        "scientific_completion": True,
        "termination_reason": termination_reason,
    }
    model_payload = _normalized_model_identity(model_identity)
    request_payload = {
        "accepted_delta_limit": accepted_delta_limit,
        "algorithm": algorithm,
        "arm": arm,
        "max_input_bytes": max_input_bytes,
        "max_expansions": max_expansions,
        "max_output_tokens": max_output_tokens,
        "model_input_projection": model_input_projection,
        "modality": modality,
        "model": model_payload,
        "schema_version": MODEL_REQUEST_SCHEMA_VERSION,
        "seed": seed,
    }
    artifacts = {
        "authorization-receipt.json": _canonical_bytes(authorization_receipt.to_dict()),
        "expansions.json": _canonical_bytes(expansions),
        "gate-receipt.json": _canonical_bytes(gate_receipt.to_dict()),
        "model.json": _canonical_bytes(model_payload),
        "policy-events.json": _canonical_bytes(policy_events),
        "request.json": _canonical_bytes(request_payload),
        "result.json": _canonical_bytes(result_payload),
        "run-receipt.json": _canonical_bytes(completed.to_dict()),
        "search-trace.json": trace.to_bytes(),
        "task.json": _canonical_bytes(dict(task)),
    }
    bundle = build_canonical_bundle(artifacts)
    evidence = {
        "bundle": base64.b64encode(bundle).decode("ascii"),
        "bundle_encoding": "base64",
        "expansions": expansions,
        "policy_events": policy_events,
        "schema_version": MODEL_EVIDENCE_SCHEMA_VERSION,
    }
    return {"result": result_payload, "evidence": evidence}


def _model_input(
    *,
    state: CanonicalState,
    memory: SearchMemory,
    trace_bytes: bytes,
    authority: PDDLStateAuthority,
    max_expansions: int,
    accepted_delta_limit: int,
    max_input_bytes: int,
    projection: str,
) -> dict[str, Any]:
    limits = _trace_limits(authority, max_expansions)
    materialized = materialize_search_trace(trace_bytes, authority=authority, limits=limits)
    record_count = json.loads(trace_bytes)["record_count"]
    rolling_context = materialized.rolling_context_before(
        record_count,
        accepted_delta_limit=accepted_delta_limit,
    )
    if projection == "bounded_bfs_search_memory_v3":
        model_input, _dropped = build_bounded_bfs_model_input(
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
        if not isinstance(parsed, dict) or "typed_operation" not in parsed:
            raise ValueError("model output must be an object containing typed_operation")
        rationale = parsed.get("canonical_rationale", "")
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
    if model_input_projection not in {
        "bounded_bfs_search_memory_v3",
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
    ):
        raise SearchEpisodeError("model evidence summary differs from its events")
    expected_rate = invalid_count / len(events) if events else 0.0
    if result.get("invalid_operation_rate") != expected_rate:
        raise SearchEpisodeError("model invalid-operation rate differs from its events")


def _validate_projection_request(request: Mapping[str, Any]) -> None:
    max_input_bytes = request.get("max_input_bytes")
    if isinstance(max_input_bytes, bool) or not isinstance(max_input_bytes, int) or max_input_bytes <= 0:
        raise SearchEpisodeError("model request input budget is invalid")
    if request.get("model_input_projection") not in {
        "bounded_bfs_search_memory_v3",
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
