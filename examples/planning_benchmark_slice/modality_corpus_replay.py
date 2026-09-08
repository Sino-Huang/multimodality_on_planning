"""Reconstruct released teacher inputs through the existing family runtimes."""

from __future__ import annotations

import json
from collections import deque
from typing import Any

from .best_first_controller import BEST_FIRST_SETTINGS, BestFirstController
from .best_first_model_input import build_compact_best_first_live_model_input
from .bfs_corpus import _validate_v5_teacher_decision
from .bfs_model_input import build_bounded_bfs_model_input_v4
from .bfws_episode import build_bfws_observation, run_best_first_width
from .bfws_model_input import (
    bfws_text_policy_training_messages,
    build_bounded_bfws_model_input,
    compact_bfws_teacher_operation,
    resolve_bfws_model_operation,
)
from .bfws_trace_audit import _append_delta, _checkpoint_for_memory
from .model_search_episode import _parse_model_output
from .pddl_state import PDDLStateAuthority
from .qwen_text_policy import qwen_text_policy_training_messages
from .search_context import IncrementalSearchContext, _apply_persisted_transition
from .search_memory import AcceptedRetirement, AcceptedTransition, SearchMemory
from .search_trace import TraceSegmentLimits, _decode_operation, _serialize_operation, _serialize_result


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def replay_inputs(authority: PDDLStateAuthority, algorithm: str, trace: dict, processor: Any) -> list[dict]:
    """Return independently reconstructed inputs/targets/results in decision order.

    Preserve the source 8K compaction policy and its 16-delta capacity; the
    approved 32K allowance is for the later matched modality projection.
    """
    if algorithm.startswith("best_first_add"):
        return _additive(authority, algorithm, trace)
    if trace["authority_id"] != authority.authority_id or trace["record_count"] != len(trace["records"]):
        raise ValueError("trace authority/count differs")
    if any(record["index"] != i for i, record in enumerate(trace["records"])):
        raise ValueError("trace decision indices differ")
    tokenizer = processor.processor.tokenizer
    builder = (
        bfws_text_policy_training_messages if algorithm == "best_first_width" else qwen_text_policy_training_messages
    )

    def counter(payload):
        text = processor.processor.apply_chat_template(builder(payload), tokenize=False, add_generation_prompt=True)
        return len(tokenizer(text)["input_ids"])

    rows = []
    if algorithm == "best_first_width":
        deltas = deque(maxlen=16)

        def on_step(step):
            index = len(rows)
            record = trace["records"][index]
            observation = build_bfws_observation(
                authority=authority,
                state=step.memory_before.state(step.expanded_state_id),
                memory=step.memory_before,
                partition_tables=step.partition_tables_before,
                priority_by_state=step.priority_by_state,
            )
            if observation != record["observation"] or _serialize_operation(step.operation) != record["operation"]:
                raise ValueError(f"BFWS live observation/operation differs at {index}")
            raw, _ = build_bounded_bfws_model_input(
                observation=observation,
                checkpoint=_checkpoint_for_memory(step.memory_before),
                accepted_deltas=tuple(deltas),
                max_bytes=3840,
                max_input_tokens=7808,
                token_counter=counter,
            )
            target = {
                "canonical_rationale": record["rationale"],
                "runtime_result": None,
                "typed_operation": compact_bfws_teacher_operation(observation, record["operation"]),
            }
            parsed, error = _parse_model_output(canonical(target))
            if parsed is None or resolve_bfws_model_operation(parsed["operation"], observation) != step.operation:
                raise ValueError(f"BFWS strict target rejected: {error}")
            if _serialize_result(step.result) != record["result"]:
                raise ValueError("BFWS runtime result differs")
            rows.append({"input": raw, "target": target, "result": record["result"]})
            _append_delta(deltas, index, step.operation, step.result)

        summary = run_best_first_width(authority, max_expansions=len(trace["records"]), on_step=on_step)
        if not summary.goal_reached or len(rows) != len(trace["records"]):
            raise ValueError("BFWS replay is incomplete")
        return rows
    if algorithm != "bfs":
        raise ValueError(f"unsupported algorithm: {algorithm}")
    context = IncrementalSearchContext(
        SearchMemory.initial(authority),
        accepted_delta_limit=16,
        limits=TraceSegmentLimits(max_records=max(1, len(trace["records"])), max_bytes=100_000_000),
    )
    active_state = None
    for index, record in enumerate(trace["records"]):
        memory = context.memory
        observation = record["observation"]
        state = memory.state(observation["state_id"])
        if active_state != state.state_id:
            if active_state is not None and any(
                authority.preview_apply(memory.state(active_state), action).target_state.state_id not in memory.visited
                for action in authority.applicable_actions(memory.state(active_state))
            ):
                raise ValueError("BFS advanced before exhausting canonical successors")
            if not memory.frontier or state.state_id != memory.frontier[0] or authority.is_goal(state):
                raise ValueError("BFS expansion violates FIFO/goal termination")
            active_state = state.state_id
        operation_payload = record["operation"]
        if "frontier_intent" in operation_payload:
            retire = state.state_id in memory.frontier
            if (
                operation_payload["frontier_intent"]
                != {"retire_source": retire, "target_position": len(memory.frontier) - int(retire)}
                or operation_payload["visit_target"] is not True
                or operation_payload["evaluate_target"] is not False
            ):
                raise ValueError("BFS teacher violates FIFO update contract")
        if observation["state_atoms"] != list(state.atoms) or observation["frontier"] != list(memory.frontier):
            raise ValueError("BFS observed state/frontier differs from live memory")
        rolling = context.rolling_context()
        raw, _ = build_bounded_bfs_model_input_v4(
            authority=authority,
            goal_atoms=list(authority.goal_atoms or ()),
            observation=observation,
            checkpoint=rolling.checkpoint,
            accepted_deltas=rolling.accepted_deltas,
            max_bytes=3840,
            max_input_tokens=7808,
            token_counter=counter,
        )
        _validate_v5_teacher_decision(record, raw)
        target = {
            "canonical_rationale": record["rationale"],
            "runtime_result": None,
            "typed_operation": record["operation"],
        }
        parsed, error = _parse_model_output(canonical(target))
        operation = _decode_operation(record["operation"])
        if parsed is None or parsed["operation"] != operation:
            raise ValueError(f"BFS strict target rejected: {error}")
        result = _apply_persisted_transition(memory, record["operation"], record["result"])
        if (
            not isinstance(result, (AcceptedTransition, AcceptedRetirement))
            or _serialize_result(result) != record["result"]
        ):
            raise ValueError("BFS runtime rejected teacher/result")
        context.accept(record_index=index, operation=operation, result=result)
        rows.append({"input": raw, "target": target, "result": record["result"]})
    if not context.memory.frontier or not authority.is_goal(context.memory.state(context.memory.frontier[0])):
        raise ValueError("BFS replay did not reach its goal")
    return rows


def _additive(authority: PDDLStateAuthority, algorithm: str, trace: dict) -> list[dict]:
    request = trace["request"]
    if request["accepted_delta_limit"] != 16:
        raise ValueError("additive Search Memory capacity differs")
    controller = BestFirstController(
        authority,
        BEST_FIRST_SETTINGS[algorithm],
        accepted_delta_limit=16,
        max_budget=request["max_expansions"],
    )
    rows = []
    for event_index, event in enumerate(trace["events"]):
        if event["index"] != event_index or event["frontier_before"] != {
            "count": controller.frontier_count,
            "head": controller.frontier_head(),
        }:
            raise ValueError("additive event/frontier-before binding differs")
        controller.start_expansion()
        if event["expanded_state_id"] != controller.active_state_ref:
            raise ValueError("additive expansion binding differs")
        for decision in event["decisions"]:
            raw = build_compact_best_first_live_model_input(authority, controller)
            target_text = decision["target"]
            candidate = controller.current_candidates()[0]
            target = json.loads(target_text)
            if target != {
                "action": {"name": candidate.action.name, "args": list(candidate.action.args)},
                "source_state_id": controller.active_state_ref,
            }:
                raise ValueError("additive teacher differs from canonical candidate")
            result = controller.apply_raw_output(target_text)
            if not result.accepted or any(result.runtime_result.get(k) != v for k, v in decision["runtime"].items()):
                raise ValueError("additive strict target/runtime rejected")
            rows.append({"input": raw, "target": target, "result": dict(result.runtime_result)})
        if controller.current_candidates():
            raise ValueError("additive candidate coverage is incomplete")
        controller.finish_expansion()
        if event["frontier_after"] != {"count": controller.frontier_count, "head": controller.frontier_head()}:
            raise ValueError("additive frontier-after binding differs")
        authority.discard_transient_search_caches()
    head = controller.frontier_head_state_id()
    if (
        head is None
        or not authority.is_goal(controller.node_state(head))
        or len(rows) != trace["result"]["decision_count"]
    ):
        raise ValueError("additive replay is incomplete")
    return rows
