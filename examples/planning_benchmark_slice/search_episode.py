from __future__ import annotations

import base64
import json
import random
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn

from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    RunReceipt,
    StopOutcome,
    evaluate_execution_permission,
)
from src.data_collect.replay import (
    build_canonical_bundle,
    parse_canonical_bundle,
)

from .pddl_state import CanonicalState, PDDLStateAuthority
from .search_memory import (
    AcceptedRetirement,
    AcceptedTransition,
    FrontierIntent,
    SearchMemory,
    SearchRetireRequest,
    SearchTransitionRequest,
    StateEvaluation,
    apply_search_retirement,
    apply_search_transition,
)
from .search_trace import (
    TraceSegmentLimits,
    append_search_trace_record,
    replay_search_trace_segment,
    start_search_trace,
)
from .validate_instance import load_fixture

EVIDENCE_SCHEMA_VERSION = "search_episode_evidence_v1"
TASK_SCHEMA_VERSION = "search_episode_task_v1"
REQUEST_SCHEMA_VERSION = "search_episode_request_v1"
_BUNDLE_ARTIFACTS = {
    "authorization-receipt.json",
    "expansions.json",
    "gate-receipt.json",
    "request.json",
    "result.json",
    "run-receipt.json",
    "search-trace.json",
    "task.json",
}


class SearchEpisodeError(ValueError):
    """Raised when an episode request or evidence bundle is invalid."""


def run_search_episode(
    task_path: str | Path,
    algorithm: str,
    modality: str,
    policy: str,
    max_expansions: int,
    gate_receipt: GateReceipt,
    authorization_receipt: AuthorizationReceipt | None,
    signing_key: bytes | str,
    ancestor_receipt_digest: str | None = None,
    random_seed: int | None = None,
) -> dict[str, Any]:
    """Run one governed search episode through the public harness seam."""

    if not isinstance(gate_receipt, GateReceipt):
        raise SearchEpisodeError("gate_receipt must expose a governed binding")

    # This check intentionally precedes Path construction, fixture reads, PDDL
    # parsing, and all search-memory creation.
    permission = evaluate_execution_permission(
        binding=gate_receipt.binding,
        gate_receipt=gate_receipt,
        authorization_receipt=authorization_receipt,
        signing_key=signing_key,
        ancestor_receipt_digest=ancestor_receipt_digest,
    )
    if not permission.start_permitted:
        return _stopped_episode(permission)

    _validate_request(algorithm, modality, policy, max_expansions, random_seed)
    fixture = load_fixture(Path(task_path))
    task = {
        "domain_pddl": fixture.domain_pddl,
        "instance_id": str(fixture.payload.get("instance_id") or ""),
        "problem_pddl": fixture.problem_pddl,
        "schema_version": TASK_SCHEMA_VERSION,
    }
    assert authorization_receipt is not None
    return _execute_authorized_episode(
        task=task,
        algorithm=algorithm,
        modality=modality,
        policy=policy,
        random_seed=random_seed,
        max_expansions=max_expansions,
        gate_receipt=gate_receipt,
        authorization_receipt=authorization_receipt,
        signing_key=signing_key,
    )


def replay_search_episode(evidence: Mapping[str, Any], *, signing_key: bytes | str) -> dict[str, Any]:
    """Verify and deterministically reconstruct a complete public episode."""

    if not isinstance(evidence, Mapping) or set(evidence) != {
        "bundle",
        "bundle_encoding",
        "expansions",
        "schema_version",
    }:
        raise SearchEpisodeError("evidence has invalid fields")
    if evidence["schema_version"] != EVIDENCE_SCHEMA_VERSION or evidence["bundle_encoding"] != "base64":
        raise SearchEpisodeError("evidence schema or encoding is invalid")
    encoded_bundle = evidence["bundle"]
    if not isinstance(encoded_bundle, str):
        raise SearchEpisodeError("evidence bundle must be base64 text")
    try:
        bundle = base64.b64decode(encoded_bundle.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as error:
        raise SearchEpisodeError("evidence bundle is not canonical base64") from error
    if base64.b64encode(bundle).decode("ascii") != encoded_bundle:
        raise SearchEpisodeError("evidence bundle is not canonical base64")

    try:
        artifacts = parse_canonical_bundle(bundle)
    except ValueError as error:
        raise SearchEpisodeError(str(error)) from error
    if set(artifacts) != _BUNDLE_ARTIFACTS:
        raise SearchEpisodeError("evidence bundle has missing or unexpected artifacts")

    task = _load_canonical_json(artifacts["task.json"], "task")
    request = _load_canonical_json(artifacts["request.json"], "request")
    bundled_expansions = _load_canonical_json(artifacts["expansions.json"], "expansions")
    bundled_result = _load_canonical_json(artifacts["result.json"], "result")
    gate = _gate_from_payload(_load_canonical_json(artifacts["gate-receipt.json"], "gate receipt"))
    authorization = _authorization_from_payload(
        _load_canonical_json(artifacts["authorization-receipt.json"], "authorization receipt")
    )
    completed = _run_receipt_from_payload(_load_canonical_json(artifacts["run-receipt.json"], "run receipt"))
    if not isinstance(evidence["expansions"], list) or evidence["expansions"] != bundled_expansions:
        raise SearchEpisodeError("public expansion evidence differs from its bundle")

    algorithm, modality, policy, max_expansions, random_seed = _parse_request(request)
    permission = evaluate_execution_permission(
        binding=gate.binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=signing_key,
    )
    if not permission.start_permitted:
        raise SearchEpisodeError("bundled receipts do not authorize replay")
    if (
        completed.binding != gate.binding
        or completed.outcome is not StopOutcome.PASS
        or completed.run_state != "completed"
        or not completed.scientific_completion
        or not completed.verify_signature(signing_key)
    ):
        raise SearchEpisodeError("completed run receipt is invalid")

    authority = _authority_from_task(task)
    limits = _trace_limits(authority, max_expansions)
    replay_search_trace_segment(artifacts["search-trace.json"], authority=authority, limits=limits)

    regenerated = _execute_authorized_episode(
        task=task,
        algorithm=algorithm,
        modality=modality,
        policy=policy,
        random_seed=random_seed,
        max_expansions=max_expansions,
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=signing_key,
    )
    regenerated_bundle = base64.b64decode(regenerated["evidence"]["bundle"], validate=True)
    if regenerated_bundle != bundle or regenerated["result"] != bundled_result:
        raise SearchEpisodeError("deterministic episode replay differs from bundled evidence")
    return regenerated


def _execute_authorized_episode(
    *,
    task: Mapping[str, Any],
    algorithm: str,
    modality: str,
    policy: str,
    random_seed: int | None,
    max_expansions: int,
    gate_receipt: GateReceipt,
    authorization_receipt: AuthorizationReceipt,
    signing_key: bytes | str,
) -> dict[str, Any]:
    _validate_request(algorithm, modality, policy, max_expansions, random_seed)
    authority = _authority_from_task(task)
    rng = random.Random(random_seed) if policy == "random" else None
    memory = SearchMemory.initial(authority)
    limits = _trace_limits(authority, max_expansions)
    trace = start_search_trace(memory, limits=limits)
    expansions: list[dict[str, Any]] = []

    while memory.frontier and len(expansions) < max_expansions:
        frontier_before = list(memory.frontier)
        expanded_state_id = frontier_before[0]
        state = memory.state(expanded_state_id)
        if authority.is_goal(state):
            break

        enqueued_state_ids: list[str] = []
        retire_source = True
        applicable_actions = list(authority.applicable_actions(state))
        if rng is not None:
            rng.shuffle(applicable_actions)
        for action in applicable_actions:
            preview = authority.preview_apply(state, action)
            if preview.target_state.state_id in memory.visited:
                continue
            request = SearchTransitionRequest(
                source_state_id=expanded_state_id,
                action=action,
                frontier_intent=FrontierIntent(
                    retire_source=retire_source,
                    target_position=len(memory.frontier) - (1 if retire_source else 0),
                ),
                visit_target=True,
                evaluate_target=False,
            )
            before = memory
            result = apply_search_transition(before, request, evaluator=_unexpected_evaluator)
            if not isinstance(result, AcceptedTransition):
                raise SearchEpisodeError("trusted BFS transition was rejected")
            trace = append_search_trace_record(
                trace,
                memory_before=before,
                observation=_text_observation(state, before),
                rationale="exact_bfs_canonical_successor" if policy == "exact" else "random_bfs_seeded_successor",
                operation=request,
                result=result,
                limits=limits,
            )
            memory = result.memory
            enqueued_state_ids.append(result.transition.target_state.state_id)
            retire_source = False

        if retire_source:
            request = SearchRetireRequest(expanded_state_id)
            before = memory
            result = apply_search_retirement(before, request)
            if not isinstance(result, AcceptedRetirement):
                raise SearchEpisodeError("trusted BFS retirement was rejected")
            trace = append_search_trace_record(
                trace,
                memory_before=before,
                observation=_text_observation(state, before),
                rationale=f"{policy}_bfs_retire_exhausted_frontier_head",
                operation=request,
                result=result,
                limits=limits,
            )
            memory = result.memory

        frontier_after = list(memory.frontier)
        expected_frontier = [*frontier_before[1:], *enqueued_state_ids]
        if frontier_after != expected_frontier:
            raise SearchEpisodeError("trusted BFS violated FIFO frontier discipline")
        expansions.append(
            {
                "expanded_state_id": expanded_state_id,
                "frontier_before": frontier_before,
                "enqueued_state_ids": enqueued_state_ids,
                "frontier_after": frontier_after,
            }
        )

    goal_reached = bool(memory.frontier and authority.is_goal(memory.state(memory.frontier[0])))
    completed = RunReceipt(
        binding=gate_receipt.binding,
        outcome=StopOutcome.PASS,
        run_state="completed",
        start_permitted=False,
        scientific_completion=True,
        gate_receipt_digest=gate_receipt.digest,
        authorization_receipt_digest=authorization_receipt.digest,
    ).signed(signing_key)
    result_payload = {
        "completion": "completed",
        "expansion_count": len(expansions),
        "goal_reached": goal_reached,
        "outcome": StopOutcome.PASS.value,
        "run_receipt": completed.to_dict(),
        "scientific_completion": True,
    }
    request_payload = {
        "algorithm": algorithm,
        "max_expansions": max_expansions,
        "modality": modality,
        "policy": policy,
        "schema_version": REQUEST_SCHEMA_VERSION,
    }
    if policy == "random":
        request_payload["random_seed"] = random_seed
    artifacts = {
        "authorization-receipt.json": _canonical_bytes(authorization_receipt.to_dict()),
        "expansions.json": _canonical_bytes(expansions),
        "gate-receipt.json": _canonical_bytes(gate_receipt.to_dict()),
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
        "schema_version": EVIDENCE_SCHEMA_VERSION,
    }
    return {"result": result_payload, "evidence": evidence}


def _stopped_episode(receipt: RunReceipt) -> dict[str, Any]:
    return {
        "result": {
            "completion": receipt.run_state,
            "expansion_count": 0,
            "goal_reached": False,
            "outcome": receipt.outcome.value,
            "run_receipt": receipt.to_dict(),
            "scientific_completion": receipt.scientific_completion,
        },
        "evidence": None,
    }


def _validate_request(
    algorithm: str,
    modality: str,
    policy: str,
    max_expansions: int,
    random_seed: int | None,
) -> None:
    if algorithm != "bfs":
        raise SearchEpisodeError("slice 1 supports only algorithm='bfs'")
    if modality != "text-state":
        raise SearchEpisodeError("slice 1 supports only modality='text-state'")
    if policy not in {"exact", "random"}:
        raise SearchEpisodeError("supported policies are 'exact' and 'random'")
    if policy == "random":
        if isinstance(random_seed, bool) or not isinstance(random_seed, int):
            raise SearchEpisodeError("random policy requires an integer random_seed")
    elif random_seed is not None:
        raise SearchEpisodeError("random_seed is only valid for random policy")
    if isinstance(max_expansions, bool) or not isinstance(max_expansions, int) or max_expansions <= 0:
        raise SearchEpisodeError("max_expansions must be a positive integer")


def _authority_from_task(task: Mapping[str, Any]) -> PDDLStateAuthority:
    if not isinstance(task, Mapping) or set(task) != {
        "domain_pddl",
        "instance_id",
        "problem_pddl",
        "schema_version",
    }:
        raise SearchEpisodeError("task artifact has invalid fields")
    if task["schema_version"] != TASK_SCHEMA_VERSION:
        raise SearchEpisodeError("task artifact schema is invalid")
    if not all(isinstance(task[field], str) for field in ("domain_pddl", "instance_id", "problem_pddl")):
        raise SearchEpisodeError("task artifact fields must be text")
    return PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])


def _parse_request(request: Mapping[str, Any]) -> tuple[str, str, str, int, int | None]:
    if not isinstance(request, Mapping):
        raise SearchEpisodeError("request artifact has invalid fields")
    policy_value = request.get("policy")
    expected_fields = {
        "algorithm",
        "max_expansions",
        "modality",
        "policy",
        "schema_version",
    }
    if policy_value == "random":
        expected_fields.add("random_seed")
    if set(request) != expected_fields:
        raise SearchEpisodeError("request artifact has invalid fields")
    if request["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise SearchEpisodeError("request artifact schema is invalid")
    algorithm = request["algorithm"]
    modality = request["modality"]
    policy = request["policy"]
    if not isinstance(policy, str):
        raise SearchEpisodeError("request policy must be text")
    max_expansions = request["max_expansions"]
    random_seed = request.get("random_seed")
    _validate_request(algorithm, modality, policy, max_expansions, random_seed)
    return algorithm, modality, policy, max_expansions, random_seed


def _trace_limits(authority: PDDLStateAuthority, max_expansions: int) -> TraceSegmentLimits:
    arity_bound = max(1, len(authority.objects) ** 2)
    max_records = max_expansions * max(1, len(authority.action_vocabulary) * arity_bound)
    return TraceSegmentLimits(max_records=max_records, max_bytes=max(1_000_000, max_records * 16_384))


def _text_observation(state: CanonicalState, memory: SearchMemory) -> dict[str, Any]:
    return {
        "frontier": list(memory.frontier),
        "goal_atoms": list(memory.authority.goal_atoms or ()),
        "modality": "text-state",
        "state_atoms": list(state.atoms),
        "state_id": state.state_id,
    }


def _unexpected_evaluator(_state: CanonicalState) -> StateEvaluation:
    raise AssertionError("BFS transitions do not request state evaluation")


def _binding_from_payload(payload: Any) -> ReceiptBinding:
    if not isinstance(payload, dict) or set(payload) != {"attempt_id", "contract_id", "output_root"}:
        raise SearchEpisodeError("receipt binding is malformed")
    return ReceiptBinding(payload["contract_id"], payload["attempt_id"], payload["output_root"])


def _gate_from_payload(payload: Any) -> GateReceipt:
    if not isinstance(payload, dict):
        raise SearchEpisodeError("gate receipt is malformed")
    try:
        receipt = GateReceipt(
            binding=_binding_from_payload(payload["binding"]),
            outcome=payload["outcome"],
            ancestor_receipt_digest=payload["ancestor_receipt_digest"],
            signature=payload["signature"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SearchEpisodeError("gate receipt is malformed") from error
    if receipt.to_dict() != payload:
        raise SearchEpisodeError("gate receipt has noncanonical fields")
    return receipt


def _authorization_from_payload(payload: Any) -> AuthorizationReceipt:
    if not isinstance(payload, dict):
        raise SearchEpisodeError("authorization receipt is malformed")
    try:
        receipt = AuthorizationReceipt(
            binding=_binding_from_payload(payload["binding"]),
            gate_receipt_digest=payload["gate_receipt_digest"],
            signature=payload["signature"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SearchEpisodeError("authorization receipt is malformed") from error
    if receipt.to_dict() != payload:
        raise SearchEpisodeError("authorization receipt has noncanonical fields")
    return receipt


def _run_receipt_from_payload(payload: Any) -> RunReceipt:
    if not isinstance(payload, dict):
        raise SearchEpisodeError("run receipt is malformed")
    try:
        receipt = RunReceipt(
            binding=_binding_from_payload(payload["binding"]),
            outcome=payload["outcome"],
            run_state=payload["run_state"],
            start_permitted=payload["start_permitted"],
            scientific_completion=payload["scientific_completion"],
            gate_receipt_digest=payload["gate_receipt_digest"],
            authorization_receipt_digest=payload["authorization_receipt_digest"],
            ancestor_receipt_digest=payload["ancestor_receipt_digest"],
            reason=payload["reason"],
            signature=payload["signature"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SearchEpisodeError("run receipt is malformed") from error
    if receipt.to_dict() != payload:
        raise SearchEpisodeError("run receipt has noncanonical fields")
    return receipt


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _load_canonical_json(payload: bytes, label: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SearchEpisodeError(f"duplicate field in {label}: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise SearchEpisodeError(f"invalid number in {label}: {value}")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except SearchEpisodeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SearchEpisodeError(f"{label} is not valid UTF-8 JSON") from error
    if _canonical_bytes(value) != payload:
        raise SearchEpisodeError(f"{label} is not canonical JSON")
    return value


__all__ = [
    "EVIDENCE_SCHEMA_VERSION",
    "SearchEpisodeError",
    "replay_search_episode",
    "run_search_episode",
]
