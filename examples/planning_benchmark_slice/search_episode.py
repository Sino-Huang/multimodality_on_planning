from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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

from .astar_episode import ASTAR_ACCEPTED_DELTA_LIMIT, run_astar_hmax
from .bfws_episode import (
    BFWS_NOVELTY_PRECISION,
    BFWSSearchStep,
    build_bfws_observation,
    run_best_first_width,
)
from .episode_evidence import (
    EVIDENCE_SCHEMA_VERSION,
    EpisodeEvidenceError,
    replay_episode,
    serialize_operation,
    serialize_state,
)
from .iw_episode import (
    IW_MAX_WIDTH,
    IW_START_WIDTH,
    IWSearchStep,
    build_iw_observation,
    run_iterative_width,
    serialize_novelty_table,
)
from .pddl_state import CanonicalState, PDDLStateAuthority
from .search_memory import (
    AcceptedTransition,
    MutableBFSMemory,
    SearchMemory,
    StateEvaluation,
)
from .search_trace import TraceSegmentLimits
from .validate_instance import load_fixture

TASK_SCHEMA_VERSION = "search_episode_task_v1"
REQUEST_SCHEMA_VERSION = "search_episode_request_v1"


class SearchEpisodeError(ValueError):
    """Raised when an episode request or evidence is invalid."""


@dataclass(frozen=True, slots=True)
class SearchEpisodeVariant:
    policy: str
    random_seed: int | None = None


def run_search_episode(
    task_path: str | Path,
    algorithm: str,
    modality: str,
    policy: str,
    max_expansions: int,
    gate_receipt: GateReceipt,
    authorization_receipt: AuthorizationReceipt | None,
    ancestor_receipt_id: str | None = None,
    random_seed: int | None = None,
    frozen_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one governed search episode through the public harness seam."""

    return run_search_episode_batch(
        task_path=task_path,
        algorithm=algorithm,
        modality=modality,
        variants=(SearchEpisodeVariant(policy, random_seed),),
        max_expansions=max_expansions,
        gate_receipt=gate_receipt,
        authorization_receipt=authorization_receipt,
        ancestor_receipt_id=ancestor_receipt_id,
        frozen_binding=frozen_binding,
    )[0]


def run_search_episode_batch(
    task_path: str | Path,
    algorithm: str,
    modality: str,
    variants: Sequence[SearchEpisodeVariant],
    max_expansions: int,
    gate_receipt: GateReceipt,
    authorization_receipt: AuthorizationReceipt | None,
    ancestor_receipt_id: str | None = None,
    frozen_binding: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Run ordered policy variants after one authorized task parse."""

    variant_list = tuple(variants)
    if not variant_list or any(not isinstance(variant, SearchEpisodeVariant) for variant in variant_list):
        raise SearchEpisodeError("episode variants must be a non-empty sequence")
    if not isinstance(gate_receipt, GateReceipt):
        raise SearchEpisodeError("gate_receipt must expose a governed binding")
    permission = evaluate_execution_permission(
        binding=gate_receipt.binding,
        gate_receipt=gate_receipt,
        authorization_receipt=authorization_receipt,
        ancestor_receipt_id=ancestor_receipt_id,
    )
    if not permission.start_permitted:
        return tuple(_stopped_episode(permission) for _variant in variant_list)

    for variant in variant_list:
        _validate_request(algorithm, modality, variant.policy, max_expansions, variant.random_seed)
    fixture = load_fixture(Path(task_path))
    task = {
        "domain_pddl": fixture.domain_pddl,
        "instance_id": str(fixture.payload.get("instance_id") or ""),
        "problem_pddl": fixture.problem_pddl,
        "schema_version": TASK_SCHEMA_VERSION,
    }
    authority = _authority_from_task(task)
    assert authorization_receipt is not None
    return tuple(
        _execute_authorized_episode(
            task=task,
            algorithm=algorithm,
            modality=modality,
            policy=variant.policy,
            random_seed=variant.random_seed,
            max_expansions=max_expansions,
            gate_receipt=gate_receipt,
            authorization_receipt=authorization_receipt,
            frozen_binding=frozen_binding,
            authority=authority,
        )
        for variant in variant_list
    )


def replay_search_episode(evidence: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(evidence, Mapping) or evidence.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        raise SearchEpisodeError("evidence schema is invalid")
    try:
        replay_episode(evidence)
    except EpisodeEvidenceError as error:
        raise SearchEpisodeError(str(error)) from error
    return {"evidence": dict(evidence), "result": evidence["result"]}


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
    frozen_binding: Mapping[str, Any] | None,
    authority: PDDLStateAuthority | None = None,
) -> dict[str, Any]:
    _validate_request(algorithm, modality, policy, max_expansions, random_seed)
    authority = _authority_from_task(task) if authority is None else authority
    if algorithm == "astar_hmax":
        return _execute_exact_astar_hmax_episode(
            task=task,
            max_expansions=max_expansions,
            gate_receipt=gate_receipt,
            authorization_receipt=authorization_receipt,
            frozen_binding=frozen_binding,
            authority=authority,
        )
    if algorithm == "iterated_width":
        return _execute_exact_iw_episode(
            task=task,
            max_expansions=max_expansions,
            gate_receipt=gate_receipt,
            authorization_receipt=authorization_receipt,
            frozen_binding=frozen_binding,
            authority=authority,
        )
    if algorithm == "best_first_width":
        return _execute_exact_bfws_episode(
            task=task,
            max_expansions=max_expansions,
            gate_receipt=gate_receipt,
            authorization_receipt=authorization_receipt,
            frozen_binding=frozen_binding,
            authority=authority,
        )
    rng = random.Random(random_seed) if policy == "random" else None
    memory = MutableBFSMemory(authority)
    states = {authority.initial_state.state_id: serialize_state(authority.initial_state)}
    events: list[dict[str, Any]] = []
    expansion_count = 0

    while memory.frontier and expansion_count < max_expansions:
        expanded_state_id = memory.frontier[0]
        state = memory.state(expanded_state_id)
        if authority.is_goal(state):
            break
        retire_source = True
        applicable_actions = list(authority.applicable_actions(state))
        if rng is not None:
            rng.shuffle(applicable_actions)
        for action in applicable_actions:
            applied = memory.apply_generated_action(
                expanded_state_id,
                action,
                retire_source=retire_source,
            )
            if applied is None:
                continue
            request, transition = applied
            target = transition.target_state
            states[target.state_id] = serialize_state(target)
            events.append(
                {
                    "expanded_state_id": expanded_state_id,
                    "expansion_index": expansion_count,
                    "index": len(events),
                    "newly_enqueued_state_ids": [target.state_id],
                    "operation": serialize_operation(request),
                    "rationale": (
                        "exact_bfs_canonical_successor" if policy == "exact" else "random_bfs_seeded_successor"
                    ),
                }
            )
            retire_source = False

        if retire_source:
            request = memory.retire_frontier_head(expanded_state_id)
            events.append(
                {
                    "expanded_state_id": expanded_state_id,
                    "expansion_index": expansion_count,
                    "index": len(events),
                    "newly_enqueued_state_ids": [],
                    "operation": serialize_operation(request),
                    "rationale": f"{policy}_bfs_retire_exhausted_frontier_head",
                }
            )
        expansion_count += 1

    frozen_memory = memory.freeze()
    goal_reached = bool(frozen_memory.frontier and authority.is_goal(frozen_memory.state(frozen_memory.frontier[0])))
    completed = RunReceipt(
        binding=gate_receipt.binding,
        outcome=StopOutcome.PASS,
        run_state="completed",
        start_permitted=False,
        scientific_completion=True,
        gate_receipt_id=gate_receipt.receipt_id,
        authorization_receipt_id=authorization_receipt.receipt_id,
    )
    result = {
        "completion": "completed",
        "expansion_count": expansion_count,
        "goal_reached": goal_reached,
        "outcome": StopOutcome.PASS.value,
        "run_receipt": completed.to_dict(),
        "scientific_completion": True,
    }
    request = {
        "algorithm": algorithm,
        "max_expansions": max_expansions,
        "modality": modality,
        "policy": policy,
        "schema_version": REQUEST_SCHEMA_VERSION,
    }
    if policy == "random":
        request["random_seed"] = random_seed
    evidence = {
        "events": events,
        "header": {
            "authorization_receipt": authorization_receipt.to_dict(),
            "authority_id": authority.authority_id,
            "frozen_binding": None if frozen_binding is None else dict(frozen_binding),
            "gate_receipt": gate_receipt.to_dict(),
            "request": request,
            "task": dict(task),
        },
        "result": result,
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "states": states,
    }
    return {"result": result, "evidence": evidence}


def _execute_exact_astar_hmax_episode(
    *,
    task: Mapping[str, Any],
    max_expansions: int,
    gate_receipt: GateReceipt,
    authorization_receipt: AuthorizationReceipt,
    frozen_binding: Mapping[str, Any] | None,
    authority: PDDLStateAuthority,
) -> dict[str, Any]:
    search = run_astar_hmax(
        authority,
        max_expansions=max_expansions,
        accepted_delta_limit=ASTAR_ACCEPTED_DELTA_LIMIT,
    )
    completed = RunReceipt(
        binding=gate_receipt.binding,
        outcome=StopOutcome.PASS,
        run_state="completed",
        start_permitted=False,
        scientific_completion=True,
        gate_receipt_id=gate_receipt.receipt_id,
        authorization_receipt_id=authorization_receipt.receipt_id,
    )
    result = {
        "algorithm_invariants_hold": True,
        "budget_used": search.controller.budget_used,
        "completion": "completed",
        "decision_count": search.decision_count,
        "exact_reference_decision_count": search.decision_count,
        "expansion_count": search.expansion_count,
        "goal_reached": search.goal_reached,
        "invariant_valid_success": search.goal_reached,
        "invalid_operation_count": 0,
        "outcome": StopOutcome.PASS.value,
        "reopen_count": search.controller.reopen_count,
        "run_receipt": completed.to_dict(),
        "scientific_completion": True,
        "termination": search.termination,
    }
    request = {
        "accepted_delta_limit": ASTAR_ACCEPTED_DELTA_LIMIT,
        "algorithm": "astar_hmax",
        "heuristic": "h_max",
        "max_expansions": max_expansions,
        "modality": "text-state",
        "policy": "exact",
        "priority": ["f", "generation_serial"],
        "recovery_policy": "prohibited",
        "schema_version": REQUEST_SCHEMA_VERSION,
    }
    evidence = {
        "events": list(search.events),
        "header": {
            "authorization_receipt": authorization_receipt.to_dict(),
            "authority_id": authority.authority_id,
            "frozen_binding": None if frozen_binding is None else dict(frozen_binding),
            "gate_receipt": gate_receipt.to_dict(),
            "request": request,
            "task": dict(task),
        },
        "result": result,
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "states": {state.state_id: serialize_state(state) for state in search.states},
    }
    try:
        replay_episode(evidence)
    except EpisodeEvidenceError as error:
        raise SearchEpisodeError("exact A* h_max episode failed semantic replay") from error
    return {"result": result, "evidence": evidence}


def _execute_exact_bfws_episode(
    *,
    task: Mapping[str, Any],
    max_expansions: int,
    gate_receipt: GateReceipt,
    authorization_receipt: AuthorizationReceipt,
    frozen_binding: Mapping[str, Any] | None,
    authority: PDDLStateAuthority,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []

    def retain_step(step: BFWSSearchStep) -> None:
        state = step.memory_before.state(step.expanded_state_id)
        observation = build_bfws_observation(
            authority=authority,
            state=state,
            memory=step.memory_before,
            partition_tables=step.partition_tables_before,
            priority_by_state=step.priority_by_state,
        )
        newly_enqueued: list[str] = []
        if isinstance(step.result, AcceptedTransition):
            newly_enqueued.append(step.result.transition.target_state.state_id)
        events.append(
            {
                "bfws_transition": {
                    "novel_item": None if step.novel_item is None else list(step.novel_item),
                    "novelty_bucket": step.novelty_bucket,
                    "priority": list(step.priority),
                    "residual_novelty_retained": step.residual_novelty_retained,
                },
                "expanded_state_id": step.expanded_state_id,
                "expansion_index": step.expansion_index,
                "index": len(events),
                "newly_enqueued_state_ids": newly_enqueued,
                "observation": observation,
                "operation": serialize_operation(step.operation),
                "rationale": (
                    "exact_bfws_goal_count_priority_successor"
                    if isinstance(step.result, AcceptedTransition)
                    else "exact_bfws_retire_exhausted_frontier_head"
                ),
            }
        )

    search = run_best_first_width(
        authority,
        max_expansions=max_expansions,
        on_step=retain_step,
    )
    completed = RunReceipt(
        binding=gate_receipt.binding,
        outcome=StopOutcome.PASS,
        run_state="completed",
        start_permitted=False,
        scientific_completion=True,
        gate_receipt_id=gate_receipt.receipt_id,
        authorization_receipt_id=authorization_receipt.receipt_id,
    )
    result = {
        "algorithm_invariants_hold": True,
        "completion": "completed",
        "decision_count": search.decision_count,
        "duplicate_count": search.duplicate_count,
        "expansion_count": search.expansion_count,
        "generated_count": search.generated_count,
        "goal_reached": search.goal_reached,
        "invariant_valid_success": search.goal_reached,
        "novelty_pruned_count": search.novelty_pruned_count,
        "outcome": StopOutcome.PASS.value,
        "peak_frontier": search.peak_frontier,
        "residual_novelty_retained_count": search.residual_novelty_retained_count,
        "run_receipt": completed.to_dict(),
        "scientific_completion": True,
        "termination": search.termination,
    }
    request = {
        "algorithm": "best_first_width",
        "high_novelty_policy": "enqueue",
        "max_expansions": max_expansions,
        "modality": "text-state",
        "novelty_partition": "unachieved_goal_count",
        "novelty_precision": BFWS_NOVELTY_PRECISION,
        "policy": "exact",
        "priority": ["novelty_bucket", "unachieved_goal_count", "path_depth", "generation_serial"],
        "recovery_policy": "prohibited",
        "schema_version": REQUEST_SCHEMA_VERSION,
        "variant": "full_bfws_goal_count",
    }
    evidence = {
        "events": events,
        "header": {
            "authorization_receipt": authorization_receipt.to_dict(),
            "authority_id": authority.authority_id,
            "frozen_binding": None if frozen_binding is None else dict(frozen_binding),
            "gate_receipt": gate_receipt.to_dict(),
            "request": request,
            "task": dict(task),
        },
        "result": result,
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "states": {state.state_id: serialize_state(state) for state in search.states},
    }
    try:
        replay_episode(evidence)
    except EpisodeEvidenceError as error:
        raise SearchEpisodeError("exact BFWS episode failed semantic replay") from error
    return {"result": result, "evidence": evidence}


def _execute_exact_iw_episode(
    *,
    task: Mapping[str, Any],
    max_expansions: int,
    gate_receipt: GateReceipt,
    authorization_receipt: AuthorizationReceipt,
    frozen_binding: Mapping[str, Any] | None,
    authority: PDDLStateAuthority,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []

    def retain_step(step: IWSearchStep) -> None:
        state = step.memory_before.state(step.expanded_state_id)
        observation = build_iw_observation(
            authority=authority,
            state=state,
            memory=step.memory_before,
            novelty_table=set(step.novelty_table_after),
            width=step.width,
        )
        newly_enqueued: list[str] = []
        if isinstance(step.result, AcceptedTransition):
            newly_enqueued.append(step.result.transition.target_state.state_id)
        events.append(
            {
                "expanded_state_id": step.expanded_state_id,
                "expansion_index": step.expansion_index,
                "index": len(events),
                "newly_enqueued_state_ids": newly_enqueued,
                "novelty_transition": {
                    "decision": step.decision,
                    "novel_item": None if step.novel_item is None else list(step.novel_item),
                    "novelty_table_after": serialize_novelty_table(step.novelty_table_after),
                    "novelty_table_before": serialize_novelty_table(step.novelty_table_before),
                    "target_novel_item": (
                        None if step.target_novel_item is None else list(step.target_novel_item)
                    ),
                    "width": step.width,
                },
                "observation": observation,
                "operation": serialize_operation(step.operation),
                "rationale": (
                    f"exact_iw{step.width}_canonical_novel_successor"
                    if isinstance(step.result, AcceptedTransition)
                    else f"exact_iw{step.width}_{step.decision}_frontier_head"
                ),
                "width_attempt": step.width_attempt,
            }
        )

    search = run_iterative_width(
        authority,
        max_expansions=max_expansions,
        on_step=retain_step,
    )
    attempts = search.attempts
    states = {state.state_id: serialize_state(state) for state in search.states}

    completed = RunReceipt(
        binding=gate_receipt.binding,
        outcome=StopOutcome.PASS,
        run_state="completed",
        start_permitted=False,
        scientific_completion=True,
        gate_receipt_id=gate_receipt.receipt_id,
        authorization_receipt_id=authorization_receipt.receipt_id,
    )
    result = {
        "algorithm_invariants_hold": True,
        "completion": "completed",
        "decision_count": search.decision_count,
        "decision_count_by_width": [attempt.decision_count for attempt in attempts],
        "expansion_count": search.expansion_count,
        "expansion_count_by_width": [attempt.expansion_count for attempt in attempts],
        "fallback_used": False,
        "goal_reached": search.goal_reached,
        "invariant_valid_success": search.goal_reached,
        "outcome": StopOutcome.PASS.value,
        "run_receipt": completed.to_dict(),
        "scientific_completion": True,
        "solving_width": search.solving_width,
        "termination_by_width": [attempt.termination for attempt in attempts],
        "width_sequence": [attempt.width for attempt in attempts],
    }
    request = {
        "algorithm": "iterated_width",
        "max_width": IW_MAX_WIDTH,
        "max_expansions": max_expansions,
        "modality": "text-state",
        "policy": "exact",
        "recovery_policy": "prohibited",
        "schema_version": REQUEST_SCHEMA_VERSION,
        "start_width": IW_START_WIDTH,
        "width_policy": "iterate_1_to_max_until_solved",
    }
    evidence = {
        "events": events,
        "header": {
            "authorization_receipt": authorization_receipt.to_dict(),
            "authority_id": authority.authority_id,
            "frozen_binding": None if frozen_binding is None else dict(frozen_binding),
            "gate_receipt": gate_receipt.to_dict(),
            "request": request,
            "task": dict(task),
        },
        "result": result,
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "states": states,
    }
    try:
        replay_episode(evidence)
    except EpisodeEvidenceError as error:
        raise SearchEpisodeError("exact IW episode failed semantic replay") from error
    return {"result": result, "evidence": evidence}


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
    if modality != "text-state":
        raise SearchEpisodeError("this slice supports only text-state episodes")
    if algorithm == "bfs" and policy not in {"exact", "random"}:
        raise SearchEpisodeError("supported BFS policies are 'exact' and 'random'")
    if algorithm == "iterated_width" and policy != "exact":
        raise SearchEpisodeError("the IW slice supports only the exact policy")
    if algorithm == "best_first_width" and policy != "exact":
        raise SearchEpisodeError("the BFWS slice supports only the exact policy")
    if algorithm == "astar_hmax" and policy != "exact":
        raise SearchEpisodeError("the A* h_max slice supports only the exact policy")
    if algorithm not in {"astar_hmax", "best_first_width", "bfs", "iterated_width"}:
        raise SearchEpisodeError(
            "supported algorithms are 'astar_hmax', 'best_first_width', 'bfs', and 'iterated_width'"
        )
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
    try:
        receipt = GateReceipt(
            binding=_binding_from_payload(payload["binding"]),
            outcome=payload["outcome"],
            ancestor_receipt_id=payload["ancestor_receipt_id"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SearchEpisodeError("gate receipt is malformed") from error
    if receipt.to_dict() != payload:
        raise SearchEpisodeError("gate receipt has noncanonical fields")
    return receipt


def _authorization_from_payload(payload: Any) -> AuthorizationReceipt:
    try:
        receipt = AuthorizationReceipt(
            binding=_binding_from_payload(payload["binding"]),
            gate_receipt_id=payload["gate_receipt_id"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SearchEpisodeError("authorization receipt is malformed") from error
    if receipt.to_dict() != payload:
        raise SearchEpisodeError("authorization receipt has noncanonical fields")
    return receipt


def _run_receipt_from_payload(payload: Any) -> RunReceipt:
    try:
        receipt = RunReceipt(
            binding=_binding_from_payload(payload["binding"]),
            outcome=payload["outcome"],
            run_state=payload["run_state"],
            start_permitted=payload["start_permitted"],
            scientific_completion=payload["scientific_completion"],
            gate_receipt_id=payload["gate_receipt_id"],
            authorization_receipt_id=payload["authorization_receipt_id"],
            ancestor_receipt_id=payload["ancestor_receipt_id"],
            reason=payload["reason"],
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
    "SearchEpisodeVariant",
    "replay_search_episode",
    "run_search_episode",
    "run_search_episode_batch",
]
