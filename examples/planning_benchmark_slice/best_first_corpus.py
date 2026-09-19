"""Replay-derived corpus views for paired additive best-first traces."""

from __future__ import annotations

import gzip
import io
import json
import os
import random
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Protocol

from src.data_collect.splits import split_assignment_id

from .best_first_controller import BEST_FIRST_SETTINGS, BestFirstController
from .best_first_model_input import (
    build_compact_best_first_live_model_input,
    build_compact_best_first_teacher_model_input,
    serialize_best_first_message_prefix,
)
from .pddl_state import CanonicalState, PDDLStateAuthority


class BestFirstCorpusTokenCounter(Protocol):
    def input_tokens(self, model_input: Mapping[str, Any]) -> int: ...

    def target_tokens(self, target_text: str) -> int: ...


class BestFirstCorpusLimitError(RuntimeError):
    """Raised when a required corpus row exceeds a frozen tokenizer limit."""


class QwenBestFirstCorpusTokenCounter:
    """Pinned chat-template counter for best-first process inputs and targets."""

    def __init__(self, tokenizer: Any) -> None:
        self.tokenizer = tokenizer

    def input_tokens(self, model_input: Mapping[str, Any]) -> int:
        return len(
            self.tokenizer.apply_chat_template(
                serialize_best_first_message_prefix(model_input),
                tokenize=True,
                add_generation_prompt=True,
            )
        )

    def input_token_counts(self, model_inputs: list[Mapping[str, Any]]) -> list[int]:
        counts: list[int] = []
        for start in range(0, len(model_inputs), 256):
            conversations = [
                serialize_best_first_message_prefix(model_input) for model_input in model_inputs[start : start + 256]
            ]
            token_ids = self.tokenizer.apply_chat_template(
                conversations,
                tokenize=True,
                add_generation_prompt=True,
            )
            counts.extend(len(row) for row in token_ids)
        return counts

    def target_tokens(self, target_text: str) -> int:
        return len(self.tokenizer.encode(target_text, add_special_tokens=False))


def load_best_first_corpus_token_counter(
    *,
    model_id: str,
    revision: str,
) -> QwenBestFirstCorpusTokenCounter:
    from transformers import AutoProcessor

    processor = AutoProcessor.from_pretrained(model_id, revision=revision)
    return QwenBestFirstCorpusTokenCounter(processor.tokenizer)


@dataclass(frozen=True, slots=True)
class BestFirstCorpusTrace:
    process_rows: tuple[dict[str, Any], ...]
    operational_rows: tuple[dict[str, Any], ...]
    training_rows: tuple[dict[str, Any], ...]
    audit: dict[str, int]
    semantic_task_identity: str


@dataclass(frozen=True, slots=True)
class BestFirstCorpusSource:
    design: Mapping[str, Any]
    authorization: Mapping[str, Any]
    pairs: tuple[Mapping[str, Any], ...]
    repo_root: Path

    @property
    def phase_id(self) -> str:
        return str(self.design["phase_id"])

    @property
    def algorithm_names(self) -> tuple[str, str]:
        return ("best_first_add_w3", "best_first_add_greedy")


@dataclass(frozen=True, slots=True)
class BestFirstCorpusContract:
    design: Mapping[str, Any]
    authorization: Mapping[str, Any]
    source_phase: BestFirstCorpusSource
    source_manifest: Mapping[str, Any]
    repo_root: Path

    @property
    def phase_id(self) -> str:
        return str(self.design["phase_id"])

    @property
    def trace_root(self) -> Path:
        return (self.repo_root / str(self.design["source_trace_manifest"]["path"])).resolve().parent

    def require_stage(self, stage: str) -> None:
        if (
            self.authorization.get("contract_id") != self.phase_id
            or self.authorization.get("outcome") != "PASS"
            or self.authorization.get("start_permitted") is not True
            or stage not in self.authorization.get("authorized_stages", [])
        ):
            raise ValueError(f"best-first corpus stage is not authorized: {stage}")


def load_best_first_corpus_contract(
    design_path: str | Path,
    authorization_path: str | Path,
    *,
    repo_root: str | Path,
) -> BestFirstCorpusContract:
    """Load the immutable #64 authority and its completed #63 source release."""

    root = Path(repo_root).resolve()
    design_file = Path(design_path).resolve()
    authorization_file = Path(authorization_path).resolve()
    design = _json_object(design_file.read_bytes(), "best-first corpus design")
    authorization = _json_object(
        authorization_file.read_bytes(),
        "best-first corpus authorization",
    )
    expected_counts = {
        "dev_records": 13_791,
        "domains": 12,
        "excluded_pairs": 11,
        "excluded_records": 258_371,
        "excluded_traces": 22,
        "operational_records": 31_531,
        "pairs": 64,
        "process_records": 31_531,
        "strata": 24,
        "traces": 128,
        "train_records": 17_740,
    }
    required_audits = {
        "canonical_input_overlap_count": 0,
        "future_step_leakage_count": 0,
        "held_out_instance_count": 0,
        "identical_input_conflicting_target_count": 0,
        "input_over_budget_count": 0,
        "input_target_overlap_count": 0,
        "live_training_input_mismatch_count": 0,
        "semantic_task_overlap_count": 0,
        "state_action_mismatch_count": 0,
        "target_over_budget_count": 0,
        "target_parse_rejection_count": 0,
        "teacher_decision_rejection_count": 0,
    }
    if (
        design.get("schema_version") != "best_first_paired_corpus_design_v3"
        or design.get("phase_id") != "issue-64-best-first-paired-corpus-v3"
        or design.get("source_issue") != 64
        or design.get("parent_issue") != 38
        or design.get("source_trace_contract_id") != "issue-63-best-first-paired-v3"
        or design.get("algorithms") != ["best_first_add_w3", "best_first_add_greedy"]
        or design.get("views") != ["operational", "process"]
        or design.get("curriculum_controls") != ["staged", "shuffled", "mixed_order"]
        or design.get("curriculum_seed") != 64
        or design.get("accepted_delta_limit") != 16
        or design.get("segment_alignment") != "atomic_successor_decision"
        or design.get("split_unit") != "semantic_task_identity"
        or design.get("fresh_test_access_authorized") is not False
        or design.get("expected_counts") != expected_counts
        or design.get("required_audit_results") != required_audits
        or design.get("compression") != "gzip"
        or design.get("model_input_schema") != "best_first_compact_model_input_v2"
        or design.get("input_builder")
        != "examples.planning_benchmark_slice.best_first_model_input.build_compact_best_first_model_input"
        or design.get("row_identity_binding") != "split_ledger_by_pair_id"
        or design.get("feasibility")
        != {
            "excluded_outcome": "VALID_STOP",
            "max_evaluation_calls_per_episode": 2048,
            "max_reference_decisions_per_trace": 1024,
            "selection_unit": "whole_matched_pair",
        }
        or design.get("tokenizer")
        != {
            "context_limit": 8192,
            "model_id": "Qwen/Qwen3-VL-8B-Instruct",
            "model_input_token_limit": 7808,
            "model_output_token_limit": 384,
            "revision": "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
        }
    ):
        raise ValueError("best-first corpus design has drifted")
    if (
        authorization.get("schema_version") != "best_first_paired_corpus_authorization_v3"
        or authorization.get("authorization_id") != "issue-64-best-first-paired-corpus-authorization-v3"
        or authorization.get("contract_id") != design["phase_id"]
        or authorization.get("authorized_stages") != ["corpus_release"]
        or authorization.get("outcome") != "PASS"
        or authorization.get("start_permitted") is not True
        or authorization.get("scientific_completion") is not False
        or authorization.get("receipt_id") != "corpus:issue-64-best-first-paired-corpus-v3:attempt-001"
        or authorization.get("output_root") != "data/best_first_paired_phase_v3/corpus-release-v3"
        or authorization.get("gate_receipt")
        != {
            "contract_id": design["phase_id"],
            "outcome": "PASS",
            "receipt_id": "gate:issue-64-best-first-paired-corpus-v3:PASS",
            "schema_version": "best_first_corpus_gate_v3",
            "source_issue": 64,
        }
        or _bound_path(root, authorization.get("design_manifest"), "corpus design") != design_file
    ):
        raise ValueError("best-first corpus authorization has drifted")
    predecessor_path = _bound_path(
        root,
        authorization.get("predecessor_receipt"),
        "predecessor corpus receipt",
    )
    predecessor = _json_object(predecessor_path.read_bytes(), "predecessor corpus receipt")
    if (
        predecessor.get("contract_id") != "issue-64-best-first-paired-corpus-v2"
        or predecessor.get("receipt_id") != "corpus:issue-64-best-first-paired-corpus-v2:attempt-001"
        or predecessor.get("outcome") != "VALID_STOP"
        or predecessor.get("scientific_completion") is not False
    ):
        raise ValueError("best-first corpus predecessor is not the frozen VALID_STOP")

    source_design = _json_object(
        (root / "configs/experiments/best-first-paired-design-v3.json").read_bytes(),
        "source design",
    )
    source_authorization = _json_object(
        (root / "configs/experiments/best-first-paired-authorization-v3.json").read_bytes(),
        "source authorization",
    )
    task_manifest = _json_object(
        (root / "configs/experiments/astar-paired-task-v1.json").read_bytes(),
        "source task manifest",
    )
    pairs = task_manifest.get("pairs")
    if (
        source_design.get("phase_id") != "issue-63-best-first-paired-v3"
        or source_authorization.get("contract_id") != source_design.get("phase_id")
        or source_authorization.get("outcome") != "PASS"
        or source_authorization.get("generation_receipt_id") != "generation:issue-63-best-first-paired-v3:attempt-001"
        or not isinstance(pairs, list)
        or len(pairs) != 75
    ):
        raise ValueError("best-first corpus source authority is incomplete")
    source_phase = BestFirstCorpusSource(
        source_design,
        source_authorization,
        tuple(pairs),
        root,
    )
    source_manifest_path = _bound_path(
        root,
        design.get("source_trace_manifest"),
        "source trace manifest",
    )
    source_receipt_path = _bound_path(
        root,
        authorization.get("source_generation_receipt"),
        "source generation receipt",
    )
    source_receipt = _json_object(source_receipt_path.read_bytes(), "source generation receipt")
    if (
        source_receipt.get("receipt_id") != "generation:issue-63-best-first-paired-v3:attempt-001"
        or source_receipt.get("contract_id") != source_phase.phase_id
        or source_receipt.get("outcome") != "PASS"
        or source_receipt.get("completed_pairs") != 75
        or source_receipt.get("scientific_completion") is not True
    ):
        raise ValueError("best-first corpus source generation is not complete")
    source_manifest = _json_object(source_manifest_path.read_bytes(), "source trace manifest")
    items = source_manifest.get("pairs")
    if (
        source_manifest.get("schema_version") != "best_first_paired_expert_traces_v1"
        or source_manifest.get("phase_id") != source_phase.phase_id
        or source_manifest.get("pair_count") != 75
        or source_manifest.get("trace_count") != 150
        or source_manifest.get("algorithms") != list(source_phase.algorithm_names)
        or not isinstance(items, list)
        or [item.get("pair_id") for item in items if isinstance(item, Mapping)]
        != [row["pair_id"] for row in source_phase.pairs]
        or sum(int(trace["decision_count"]) for item in items for trace in item.get("traces", {}).values()) != 289_902
    ):
        raise ValueError("best-first corpus source trace manifest is incomplete")
    contract = BestFirstCorpusContract(
        design,
        authorization,
        source_phase,
        source_manifest,
        root,
    )
    contract.require_stage("corpus_release")
    return contract


def materialize_best_first_corpus_trace(
    *,
    row: Mapping[str, Any],
    pair_item: Mapping[str, Any],
    algorithm: str,
    trace_root: str | Path,
    corpus_config: Mapping[str, Any],
    token_counter: BestFirstCorpusTokenCounter,
) -> BestFirstCorpusTrace:
    """Reconstruct one algorithm trace into process, operational, and training rows."""

    if algorithm not in BEST_FIRST_SETTINGS:
        raise ValueError(f"unsupported best-first corpus algorithm: {algorithm}")
    if pair_item.get("pair_id") != row.get("pair_id") or pair_item.get("instance_id") != row.get("instance_id"):
        raise ValueError("best-first corpus pair differs from its fixed task row")
    root = Path(trace_root).resolve()
    pair_root = root / "pairs" / str(row["pair_id"])
    task_path = pair_root / str(pair_item.get("task_path"))
    task_bytes = task_path.read_bytes()
    traces = pair_item.get("traces")
    if not isinstance(traces, Mapping) or not isinstance(traces.get(algorithm), Mapping):
        raise ValueError("best-first corpus pair is missing its algorithm trace")
    trace_item = traces[algorithm]
    trace_path = pair_root / str(trace_item.get("path"))
    compressed = trace_path.read_bytes()
    trace_bytes = gzip.decompress(compressed)
    trace = _json_object(trace_bytes, "best-first compact trace")
    request = trace.get("request")
    events = trace.get("events")
    if (
        trace.get("schema_version") != "best_first_compact_trace_v1"
        or trace.get("algorithm") != algorithm
        or not isinstance(request, Mapping)
        or not isinstance(events, list)
        or request.get("accepted_delta_limit") != corpus_config.get("accepted_delta_limit")
    ):
        raise ValueError("best-first corpus source trace contract differs")

    task = _json_object(task_bytes, "best-first task")
    authority = PDDLStateAuthority.from_pddl(str(task["domain_pddl"]), str(task["problem_pddl"]))
    controller = BestFirstController(
        authority,
        BEST_FIRST_SETTINGS[algorithm],
        accepted_delta_limit=int(request["accepted_delta_limit"]),
        max_budget=int(request["max_expansions"]),
    )
    identity = authority.semantic_task_identity()
    process_rows: list[dict[str, Any]] = []
    operational_rows: list[dict[str, Any]] = []
    training_rows: list[dict[str, Any]] = []
    max_input_tokens = 0
    max_target_tokens = 0
    live_training_mismatches = 0
    target_parse_rejections = 0
    teacher_rejections = 0
    state_action_mismatches = 0
    record_index = 0
    trace_relative = trace_path.relative_to(root).as_posix()
    task_context = authority.task_context()

    for event_index, event in enumerate(events):
        if not isinstance(event, Mapping) or event.get("index") != event_index:
            raise ValueError("best-first corpus event index differs")
        frontier_before = _frontier_summary(controller)
        if event.get("frontier_before") != frontier_before:
            raise ValueError("best-first corpus frontier-before evidence differs")
        head_id = controller.frontier_head_state_id()
        if head_id is None:
            raise ValueError("best-first corpus expands after frontier exhaustion")
        source_state = controller.node_state(head_id)
        controller.start_expansion()
        if event.get("expanded_state_id") != controller.active_state_ref or event.get("expansion_index") != event_index:
            raise ValueError("best-first corpus expanded-state evidence differs")
        decisions = event.get("decisions")
        if not isinstance(decisions, list) or len(decisions) != len(controller.current_candidates()):
            raise ValueError("best-first corpus candidate coverage differs")

        for decision_index, decision in enumerate(decisions):
            if not isinstance(decision, Mapping):
                raise ValueError("best-first corpus decision is malformed")
            candidates = controller.current_candidates()
            if not candidates:
                raise ValueError("best-first corpus decision exceeds candidate coverage")
            candidate = candidates[0]
            teacher_input = build_compact_best_first_teacher_model_input(authority, controller)
            live_input = build_compact_best_first_live_model_input(authority, controller)
            if teacher_input != live_input:
                live_training_mismatches += 1

            target_text = decision.get("target")
            try:
                target = json.loads(target_text) if isinstance(target_text, str) else None
            except json.JSONDecodeError:
                target = None
            if (
                not isinstance(target, dict)
                or _canonical_text(target) != target_text
                or target.get("action") != {"args": list(candidate.action.args), "name": candidate.action.name}
                or target.get("source_state_id") != controller.active_state_ref
            ):
                target_parse_rejections += 1
            result = controller.apply_raw_output(str(target_text))
            if not result.accepted:
                teacher_rejections += 1
            runtime = decision.get("runtime")
            if not isinstance(runtime, Mapping) or any(
                result.runtime_result.get(field) != value for field, value in runtime.items()
            ):
                raise ValueError("best-first corpus trusted runtime result differs")
            target_state = authority.apply(source_state, candidate.action).target_state
            if target_state != candidate.target_state:
                state_action_mismatches += 1

            metadata = {
                "algorithm": algorithm,
                "difficulty": row["difficulty"],
                "domain_id": row["domain_id"],
                "expert_evidence": {
                    "decision_index": decision_index,
                    "event_index": event_index,
                    "trace_path": trace_relative,
                },
                "instance_id": row["instance_id"],
                "pair_id": row["pair_id"],
                "record_index": record_index,
                "schema_version": "best_first_corpus_record_v1",
                "split": row["split"],
            }
            process = {
                **metadata,
                "input": teacher_input,
                "record_id": f"{row['pair_id']}:{algorithm}:{record_index}:process",
                "target": target,
                "view": "process",
            }
            process_rows.append(process)
            prefix = serialize_best_first_message_prefix(teacher_input)
            if prefix != serialize_best_first_message_prefix(live_input):
                live_training_mismatches += 1
            training_rows.append(
                {
                    "messages": [
                        *prefix,
                        {"content": str(target_text), "role": "assistant"},
                    ]
                }
            )
            operational_rows.append(
                {
                    **metadata,
                    "input": {
                        "action": {"args": list(candidate.action.args), "name": candidate.action.name},
                        "source_state": _state_payload(source_state),
                        "task_context": task_context,
                    },
                    "record_id": f"{row['pair_id']}:{algorithm}:{record_index}:operational",
                    "target": {
                        "target_state": _state_payload(target_state),
                        "validity": "accepted",
                    },
                    "view": "operational",
                }
            )
            target_tokens = token_counter.target_tokens(str(target_text))
            max_target_tokens = max(max_target_tokens, target_tokens)
            record_index += 1

        controller.finish_expansion()
        authority.discard_transient_search_caches()
        if event.get("frontier_after") != _frontier_summary(controller):
            raise ValueError("best-first corpus frontier-after evidence differs")

    result = trace.get("result")
    terminal_id = controller.frontier_head_state_id()
    if (
        not isinstance(result, Mapping)
        or result.get("goal_reached") is not True
        or result.get("termination") != "goal_reached"
        or result.get("decision_count") != record_index
        or result.get("expansion_count") != controller.expansion_count
        or result.get("reopen_count") != controller.reopen_count
        or terminal_id is None
        or not authority.is_goal(controller.node_state(terminal_id))
        or result.get("solution_cost") != controller.best_g[terminal_id]
        or trace_item.get("decision_count") != record_index
        or trace_item.get("expansion_count") != controller.expansion_count
        or trace_item.get("reopen_count") != controller.reopen_count
        or trace_item.get("solution_cost") != controller.best_g[terminal_id]
    ):
        raise ValueError("best-first corpus source trace result differs")
    batch_counter = getattr(token_counter, "input_token_counts", None)
    if callable(batch_counter):
        input_token_counts = batch_counter([record["input"] for record in process_rows])
    else:
        input_token_counts = [token_counter.input_tokens(record["input"]) for record in process_rows]
    max_input_tokens = max(input_token_counts, default=0)
    audit: dict[str, int] = {
        "decision_count": record_index,
        "future_step_leakage_count": 0,
        "input_over_budget_count": int(max_input_tokens > int(corpus_config["model_input_token_limit"])),
        "live_training_input_mismatch_count": live_training_mismatches,
        "max_input_tokens": max_input_tokens,
        "max_target_tokens": max_target_tokens,
        "operational_record_count": len(operational_rows),
        "state_action_mismatch_count": state_action_mismatches,
        "target_over_budget_count": int(max_target_tokens > int(corpus_config["model_output_token_limit"])),
        "target_parse_rejection_count": target_parse_rejections,
        "teacher_decision_rejection_count": teacher_rejections,
    }
    zero_fields = (
        "input_over_budget_count",
        "live_training_input_mismatch_count",
        "state_action_mismatch_count",
        "target_over_budget_count",
        "target_parse_rejection_count",
        "teacher_decision_rejection_count",
    )
    if audit["input_over_budget_count"] or audit["target_over_budget_count"]:
        raise BestFirstCorpusLimitError(
            f"best-first corpus token limit exceeded: input={max_input_tokens}, " f"target={max_target_tokens}"
        )
    if any(audit[field] for field in zero_fields):
        raise ValueError("best-first corpus trace failed its exact reconstruction audit")
    return BestFirstCorpusTrace(
        tuple(process_rows),
        tuple(operational_rows),
        tuple(training_rows),
        audit,
        identity,
    )


def run_best_first_corpus_release(
    *,
    contract: BestFirstCorpusContract,
    output_root: str | Path,
    token_counter: BestFirstCorpusTokenCounter,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Materialize one semantically audited corpus release."""

    contract.require_stage("corpus_release")
    root = Path(output_root).resolve()
    manifest_path = root / "manifests/best-first-text-corpus.json"
    if root.exists():
        raise FileExistsError(f"best-first corpus output exists: {root}")
    root.mkdir(parents=True, exist_ok=True)
    manifest = _build_release(
        contract=contract,
        output_root=root,
        token_counter=token_counter,
        progress=progress,
    )
    _write_new(manifest_path, _canonical_bytes(manifest))
    return manifest


def _build_release(
    *,
    contract: BestFirstCorpusContract,
    output_root: Path,
    token_counter: BestFirstCorpusTokenCounter,
    progress: Callable[[str], None] | None,
) -> dict[str, Any]:
    all_source_items = contract.source_manifest.get("pairs")
    if not isinstance(all_source_items, list):
        raise ValueError("best-first corpus source pairs are malformed")
    source_items, excluded_items = _select_corpus_items(
        all_source_items,
        max_decisions=int(contract.design["feasibility"]["max_reference_decisions_per_trace"]),
    )
    rows_by_pair = {str(row["pair_id"]): row for row in contract.source_phase.pairs}
    artifacts: dict[str, dict[str, Any]] = {}
    curriculum_basis: dict[str, list[dict[str, Any]]] = {
        "operational": [],
        "process": [],
    }
    canonical_inputs = {view: {"train": set(), "dev": set()} for view in ("operational", "process")}
    canonical_pairs = {view: {"train": set(), "dev": set()} for view in ("operational", "process")}
    targets_by_input: dict[str, dict[str, set[str]]] = {
        "operational": {},
        "process": {},
    }
    identities = {"train": set(), "dev": set()}
    split_rows: dict[str, dict[str, Any]] = {}
    totals = {
        "future_step_leakage_count": 0,
        "input_over_budget_count": 0,
        "live_training_input_mismatch_count": 0,
        "operational_record_count": 0,
        "state_action_mismatch_count": 0,
        "target_over_budget_count": 0,
        "target_parse_rejection_count": 0,
        "teacher_decision_rejection_count": 0,
    }
    process_record_count = 0
    process_records_by_split = {"train": 0, "dev": 0}
    max_input_tokens = 0
    max_target_tokens = 0
    held_out_instances = 0
    started = monotonic()
    total_traces = len(source_items) * len(contract.source_phase.algorithm_names)
    completed_traces = 0

    for item in source_items:
        if not isinstance(item, Mapping):
            raise ValueError("best-first corpus source pair is malformed")
        pair_id = str(item["pair_id"])
        row = rows_by_pair[pair_id]
        split = str(row["split"])
        if split not in {"train", "dev"}:
            held_out_instances += 1
        for algorithm in contract.source_phase.algorithm_names:
            shard = materialize_best_first_corpus_trace(
                row=row,
                pair_item=item,
                algorithm=algorithm,
                trace_root=contract.trace_root,
                corpus_config={
                    "accepted_delta_limit": contract.design["accepted_delta_limit"],
                    "model_input_token_limit": contract.design["tokenizer"]["model_input_token_limit"],
                    "model_output_token_limit": contract.design["tokenizer"]["model_output_token_limit"],
                    "row_identity_binding": contract.design["row_identity_binding"],
                },
                token_counter=token_counter,
            )
            base = Path(split) / str(row["domain_id"]) / str(row["difficulty"]) / pair_id / algorithm
            shard_payloads = {
                (Path("corpus/process") / base).with_suffix(".jsonl.gz").as_posix(): _gzip_jsonl(shard.process_rows),
                (Path("corpus/operational") / base)
                .with_suffix(".jsonl.gz")
                .as_posix(): _gzip_jsonl(shard.operational_rows),
                (Path("training/process") / base).with_suffix(".jsonl.gz").as_posix(): _gzip_jsonl(shard.training_rows),
            }
            for relative, payload in shard_payloads.items():
                _write_new(output_root / relative, payload)
                artifacts[relative] = _artifact_record(relative)

            process_record_count += len(shard.process_rows)
            process_records_by_split[split] += len(shard.process_rows)
            for name in totals:
                totals[name] += int(shard.audit.get(name, 0))
            max_input_tokens = max(max_input_tokens, shard.audit["max_input_tokens"])
            max_target_tokens = max(max_target_tokens, shard.audit["max_target_tokens"])
            for view, records in (
                ("process", shard.process_rows),
                ("operational", shard.operational_rows),
            ):
                for record in records:
                    input_text = _canonical_text(record["input"])
                    target_text = _canonical_text(record["target"])
                    canonical_inputs[view][split].add(input_text)
                    canonical_pairs[view][split].add((input_text, target_text))
                    targets_by_input[view].setdefault(input_text, set()).add(target_text)
                    curriculum_basis[view].append(_curriculum_base(record))
            completed_traces += 1
            elapsed = monotonic() - started
            eta = elapsed / completed_traces * (total_traces - completed_traces)
            _report(
                progress,
                f"[{completed_traces}/{total_traces}] materialized {pair_id} {algorithm}; "
                f"elapsed {_duration(elapsed)}; ETA {_duration(eta)}",
            )

        identity = shard.semantic_task_identity
        identities[split].add(identity)
        split_rows[identity] = {
            "assignment_id": split_assignment_id(identity, split),
            "identity": identity,
            "pair_id": pair_id,
            "split": split,
        }

    semantic_overlap = identities["train"] & identities["dev"]
    canonical_overlap = sum(
        len(canonical_inputs[view]["train"] & canonical_inputs[view]["dev"]) for view in canonical_inputs
    )
    input_target_overlap = sum(
        len(canonical_pairs[view]["train"] & canonical_pairs[view]["dev"]) for view in canonical_pairs
    )
    conflicting_inputs = sum(len(targets) > 1 for view in targets_by_input.values() for targets in view.values())
    audit = {
        "accepted_delta_limit": contract.design["accepted_delta_limit"],
        "canonical_input_overlap_count": canonical_overlap,
        "future_step_leakage_count": totals["future_step_leakage_count"],
        "held_out_instance_count": held_out_instances,
        "identical_input_conflicting_target_count": conflicting_inputs,
        "input_over_budget_count": totals["input_over_budget_count"],
        "input_target_overlap_count": input_target_overlap,
        "live_training_input_mismatch_count": totals["live_training_input_mismatch_count"],
        "max_input_tokens": max_input_tokens,
        "max_target_tokens": max_target_tokens,
        "model_input_token_limit": contract.design["tokenizer"]["model_input_token_limit"],
        "model_output_token_limit": contract.design["tokenizer"]["model_output_token_limit"],
        "schema_version": "best_first_corpus_audit_v1",
        "semantic_task_overlap_count": len(semantic_overlap),
        "state_action_mismatch_count": totals["state_action_mismatch_count"],
        "status": "passed",
        "target_over_budget_count": totals["target_over_budget_count"],
        "target_parse_rejection_count": totals["target_parse_rejection_count"],
        "teacher_decision_rejection_count": totals["teacher_decision_rejection_count"],
    }
    if any(audit.get(name) != expected for name, expected in contract.design["required_audit_results"].items()):
        raise ValueError("best-first corpus release failed its frozen zero-error audit")

    expected = contract.design["expected_counts"]
    observed = {
        "dev_records": process_records_by_split["dev"],
        "domains": len({str(rows_by_pair[str(item["pair_id"])]["domain_id"]) for item in source_items}),
        "excluded_pairs": len(excluded_items),
        "excluded_records": sum(
            int(trace["decision_count"]) for item in excluded_items for trace in item["traces"].values()
        ),
        "excluded_traces": len(excluded_items) * len(contract.source_phase.algorithm_names),
        "operational_records": totals["operational_record_count"],
        "pairs": len(source_items),
        "process_records": process_record_count,
        "strata": len(
            {
                (
                    str(rows_by_pair[str(item["pair_id"])]["domain_id"]),
                    str(rows_by_pair[str(item["pair_id"])]["difficulty"]),
                )
                for item in source_items
            }
        ),
        "traces": completed_traces,
        "train_records": process_records_by_split["train"],
    }
    if observed != expected:
        raise ValueError(
            "best-first corpus coverage differs: " + _canonical_text({"expected": expected, "observed": observed})
        )

    curriculum_seed = int(contract.design["curriculum_seed"])
    for view, records in curriculum_basis.items():
        for control in contract.design["curriculum_controls"]:
            relative = f"curricula/{view}/{control}.jsonl.gz"
            payload = _gzip_jsonl(
                _curriculum_rows(
                    records,
                    control=str(control),
                    seed=curriculum_seed,
                )
            )
            _write_new(output_root / relative, payload)
            artifacts[relative] = _artifact_record(relative)

    exclusion_relative = "exclusions/pairs.jsonl.gz"
    exclusion_payload = _gzip_jsonl(
        _exclusion_rows(
            excluded_items,
            rows_by_pair=rows_by_pair,
            max_decisions=int(contract.design["feasibility"]["max_reference_decisions_per_trace"]),
        )
    )
    _write_new(output_root / exclusion_relative, exclusion_payload)
    artifacts[exclusion_relative] = _artifact_record(exclusion_relative)

    split_payload = _gzip_jsonl([split_rows[identity] for identity in sorted(split_rows)])
    split_relative = "splits/assignments.jsonl.gz"
    _write_new(output_root / split_relative, split_payload)
    artifacts[split_relative] = _artifact_record(split_relative)
    audit_relative = "audits/corpus.json"
    audit_payload = _canonical_bytes(audit)
    _write_new(output_root / audit_relative, audit_payload)
    artifacts[audit_relative] = _artifact_record(audit_relative)
    training_artifacts = [artifacts[path] for path in sorted(artifacts) if path.startswith("training/process/")]
    training_manifest = {
        "artifacts": training_artifacts,
        "counts": {
            "dev": expected["dev_records"],
            "train": expected["train_records"],
        },
        "schema_version": "best_first_process_training_projection_v1",
        "source_view": "process",
    }
    training_relative = "training/manifest.json"
    training_payload = _canonical_bytes(training_manifest)
    _write_new(output_root / training_relative, training_payload)
    artifacts[training_relative] = _artifact_record(training_relative)
    return {
        "algorithms": list(contract.source_phase.algorithm_names),
        "artifacts": [artifacts[path] for path in sorted(artifacts)],
        "counts": {
            "excluded_pairs": len(excluded_items),
            "operational_records": totals["operational_record_count"],
            "process_records": process_record_count,
            "split_assignments": len(split_rows),
            "strata": expected["strata"],
            "training_projection_records": process_record_count,
        },
        "curriculum_controls": contract.design["curriculum_controls"],
        "phase_id": contract.phase_id,
        "feasibility": contract.design["feasibility"],
        "schema_version": "best_first_paired_corpus_release_v2",
        "segment_alignment": "atomic_successor_decision",
        "source_trace_manifest_path": contract.design["source_trace_manifest"]["path"],
        "split_unit": "semantic_task_identity",
        "tokenizer": contract.design["tokenizer"],
        "views": contract.design["views"],
    }


def _frontier_summary(controller: BestFirstController) -> dict[str, object]:
    return {"count": controller.frontier_count, "head": controller.frontier_head()}


def _select_corpus_items(
    items: list[Any],
    *,
    max_decisions: int,
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    selected: list[Mapping[str, Any]] = []
    excluded: list[Mapping[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("traces"), Mapping):
            raise ValueError("best-first corpus source pair is malformed")
        destination = (
            selected
            if max(int(trace["decision_count"]) for trace in item["traces"].values()) <= max_decisions
            else excluded
        )
        destination.append(item)
    return selected, excluded


def _exclusion_rows(
    items: list[Mapping[str, Any]],
    *,
    rows_by_pair: Mapping[str, Mapping[str, Any]],
    max_decisions: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        pair_id = str(item["pair_id"])
        source = rows_by_pair[pair_id]
        rows.append(
            {
                "decision_counts": {
                    algorithm: int(trace["decision_count"]) for algorithm, trace in item["traces"].items()
                },
                "difficulty": source["difficulty"],
                "domain_id": source["domain_id"],
                "max_reference_decisions_per_trace": max_decisions,
                "outcome": "VALID_STOP",
                "pair_id": pair_id,
                "reason": "paired reference exceeds the VLM decision-call feasibility ceiling",
                "scientific_completion": False,
                "split": source["split"],
            }
        )
    return rows


def _curriculum_base(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "algorithm": record["algorithm"],
        "difficulty": record["difficulty"],
        "domain_id": record["domain_id"],
        "instance_id": record["instance_id"],
        "pair_id": record["pair_id"],
        "record_id": record["record_id"],
        "record_index": record["record_index"],
        "split": record["split"],
        "view": record["view"],
    }


def _curriculum_rows(
    records: list[dict[str, Any]],
    *,
    control: str,
    seed: int,
) -> list[dict[str, Any]]:
    staged = sorted(records, key=_curriculum_sort_key)
    if control == "staged":
        ordered = staged
    elif control == "shuffled":
        ordered = []
        for split_index, split in enumerate(("train", "dev")):
            selected = [record for record in staged if record["split"] == split]
            random.Random(seed + split_index).shuffle(selected)
            ordered.extend(selected)
    elif control == "mixed_order":
        ordered = []
        for split in ("train", "dev"):
            groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for record in staged:
                if record["split"] == split:
                    groups.setdefault(
                        (str(record["difficulty"]), str(record["algorithm"])),
                        [],
                    ).append(record)
            keys = [
                (difficulty, algorithm)
                for difficulty in ("easy", "medium", "hard")
                for algorithm in ("best_first_add_w3", "best_first_add_greedy")
                if (difficulty, algorithm) in groups
            ]
            for record_index in range(max((len(groups[key]) for key in keys), default=0)):
                for key in keys:
                    if record_index < len(groups[key]):
                        ordered.append(groups[key][record_index])
    else:
        raise ValueError(f"unsupported best-first curriculum control: {control}")
    return [
        {
            **record,
            "control": control,
            "curriculum_index": index,
            "schema_version": "best_first_corpus_curriculum_v1",
            "stage_index": {"easy": 0, "medium": 1, "hard": 2}[str(record["difficulty"])],
        }
        for index, record in enumerate(ordered)
    ]


def _curriculum_sort_key(record: Mapping[str, Any]) -> tuple[int, int, str, str, str, int]:
    return (
        {"train": 0, "dev": 1}[str(record["split"])],
        {"easy": 0, "medium": 1, "hard": 2}[str(record["difficulty"])],
        str(record["domain_id"]),
        str(record["pair_id"]),
        str(record["algorithm"]),
        int(record["record_index"]),
    )


def _gzip_jsonl(rows: Any) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as stream:
        for row in rows:
            stream.write(_canonical_bytes(row))
    return buffer.getvalue()


def _artifact_record(path: str) -> dict[str, str]:
    return {"path": path}


def _write_new(path: Path, payload: bytes) -> None:
    if path.is_file():
        raise FileExistsError(f"best-first corpus artifact exists: {path}")
    _atomic_write(path, payload)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary_name).replace(path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _report(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _duration(seconds: float) -> str:
    total = max(0, round(seconds))
    hours, remainder = divmod(total, 3_600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _state_payload(state: CanonicalState) -> dict[str, Any]:
    return {
        "atoms": list(state.atoms),
        "authority_id": state.authority_id,
        "fluents": list(state.fluents),
        "state_id": state.state_id,
    }


def _json_object(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _bound_path(root: Path, binding: object, label: str) -> Path:
    if not isinstance(binding, Mapping) or set(binding) != {"path"}:
        raise ValueError(f"{label} binding is malformed")
    path = (root / str(binding["path"])).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} escapes the repository") from error
    if not path.is_file():
        raise ValueError(f"{label} binding has drifted")
    return path


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _canonical_bytes(value: object) -> bytes:
    return (_canonical_text(value) + "\n").encode()


__all__ = [
    "BestFirstCorpusContract",
    "BestFirstCorpusLimitError",
    "BestFirstCorpusTokenCounter",
    "BestFirstCorpusTrace",
    "QwenBestFirstCorpusTokenCounter",
    "load_best_first_corpus_contract",
    "load_best_first_corpus_token_counter",
    "materialize_best_first_corpus_trace",
    "run_best_first_corpus_release",
]
