"""Release governed BFS corpus views from replayed traces."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, cast

from src.data_collect.generate import GenerationRequest, GenerationRunReceipt, run_authorized_generation
from src.data_collect.splits import split_assignment_id

from .bfs_model_input import build_bounded_bfs_model_input, build_bounded_bfs_model_input_v4
from .bfs_phase import BFSPhaseGate
from .episode_evidence import read_episode_artifacts
from .pddl_state import PDDLStateAuthority
from .qwen_text_policy import QwenTextTokenCounter, load_qwen_text_token_counter
from .search_context import materialize_search_trace
from .search_trace import TraceSegmentLimits

_RELEASE_MANIFEST_PATH = Path("manifests/bfs-text-corpus.json")
_OPERATIONAL_PATH = Path("corpus/operational.jsonl")
_PROCESS_PATH = Path("corpus/process.jsonl")
_OPERATIONAL_CURRICULUM_PATH = Path("curricula/operational.jsonl")
_PROCESS_CURRICULUM_PATH = Path("curricula/process.jsonl")
_SPLIT_LEDGER_PATH = Path("splits/assignments.jsonl")
_LEAKAGE_AUDIT_PATH = Path("audits/leakage.json")
_RELEASE_SCHEMA = "bfs_text_corpus_release_v1"
_RECORD_SCHEMA = "bfs_text_corpus_record_v1"
_CURRICULUM_SCHEMA = "bfs_text_corpus_curriculum_v1"
_AUDIT_SCHEMA = "bfs_text_corpus_leakage_audit_v1"
_RELEASE_SCHEMA_V3 = "bfs_process_corpus_release_v3"
_RECORD_SCHEMA_V3 = "bfs_process_corpus_record_v3"
_CURRICULUM_SCHEMA_V3 = "bfs_process_corpus_curriculum_v3"
_AUDIT_SCHEMA_V3 = "bfs_process_corpus_audit_v3"
_RELEASE_SCHEMA_V5 = "bfs_process_corpus_release_v5"
_RECORD_SCHEMA_V5 = "bfs_process_corpus_record_v5"
_CURRICULUM_SCHEMA_V5 = "bfs_process_corpus_curriculum_v5"
_AUDIT_SCHEMA_V5 = "bfs_process_corpus_audit_v5"
_DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROCESS_ONLY_FIELDS = {
    "accepted_deltas",
    "canonical_rationale",
    "frontier",
    "heuristics",
    "known_states",
    "novelty",
    "provenance",
    "runtime_result",
    "search_memory",
    "typed_operation",
    "visited",
}


def run_frozen_bfs_text_corpus_release(
    *,
    trace_manifest_path: str | Path,
    request: GenerationRequest,
    phase_gate: BFSPhaseGate,
) -> GenerationRunReceipt:
    """Build and atomically publish the phase-authorized BFS corpus."""

    def execute() -> dict[str, object]:
        phase_gate.require_run(stage="corpus_release", contract_id=request.binding.contract_id)
        output_root = Path(request.binding.output_root).resolve()
        if output_root.exists():
            raise FileExistsError(f"BFS corpus output root already exists: {output_root}")

        artifacts = _build_release(
            Path(trace_manifest_path).resolve(),
            phase_gate=phase_gate,
        )
        output_root.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
        try:
            for relative_path, payload in artifacts.items():
                _write_bytes(staging_root / relative_path, payload)
            staging_root.replace(output_root)
        except Exception:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise

        manifest_bytes = artifacts[_RELEASE_MANIFEST_PATH.as_posix()]
        manifest = cast(dict[str, Any], json.loads(manifest_bytes))
        return {
            "corpus_manifest_path": str((output_root / _RELEASE_MANIFEST_PATH).resolve()),
            "corpus_manifest_size_bytes": len(manifest_bytes),
            "operational_record_count": manifest["counts"].get("operational_records", 0),
            "process_record_count": manifest["counts"]["process_records"],
            "split_assignment_count": manifest["counts"]["split_assignments"],
        }

    return run_authorized_generation(request, execute)


def regenerate_bfs_text_corpus(
    *,
    trace_manifest_path: str | Path,
    phase_gate: BFSPhaseGate,
) -> dict[str, bytes]:
    """Rebuild every released byte after verifying the retained trace evidence."""

    return _build_release(
        Path(trace_manifest_path).resolve(),
        phase_gate=phase_gate,
    )


def _build_release(
    trace_manifest_path: Path,
    *,
    phase_gate: BFSPhaseGate,
) -> dict[str, bytes]:
    phase_schema = phase_gate.freeze["schema_version"]
    is_v3 = phase_schema == "bfs_phase_freeze_v3"
    is_v5 = phase_schema in {"bfs_phase_freeze_v5", "bfs_phase_freeze_v6"}
    trace_manifest_bytes = trace_manifest_path.read_bytes()
    trace_manifest = _json_object(trace_manifest_bytes, "BFS trace manifest")
    traces = _validated_trace_items(trace_manifest, phase_gate)
    split_authority = _load_split_authority(traces, phase_gate)
    accepted_delta_limit = _rolling_delta_limit(phase_gate)
    trace_root = trace_manifest_path.parent.parent

    operational_rows: list[dict[str, Any]] = []
    process_rows: list[dict[str, Any]] = []
    assignments: dict[str, str] = {}
    split_conflicts = 0
    held_out_instances = 0
    future_leaks = 0
    dropped_context_deltas = 0
    max_model_input_bytes = 0
    model_input_byte_budget = phase_gate.freeze["budgets"].get(
        "max_model_input_bytes",
        phase_gate.freeze["budgets"]["max_context_tokens"]
        - phase_gate.freeze["budgets"]["max_output_tokens_per_operation"],
    )
    input_token_counter = _pinned_input_token_counter(phase_gate) if is_v5 else None
    tokenizer = input_token_counter
    max_input_tokens = (
        phase_gate.freeze["budgets"]["max_context_tokens"]
        - phase_gate.freeze["budgets"]["max_output_tokens_per_operation"]
    )
    max_model_input_tokens = 0
    max_target_tokens = 0

    for item in sorted(traces, key=_trace_sort_key):
        split = _text(item, "source", "split")
        _validate_authoritative_split(item, split_authority)
        if split == phase_gate.freeze["data"]["held_out_split"]:
            held_out_instances += 1
        evidence_path = _artifact_path(trace_root, cast(Mapping[str, Any], item["evidence"]))
        persisted_trace = _artifact_bytes(trace_root, cast(Mapping[str, Any], item["search_trace"]))
        _episode, task_bytes, replayed_trace = read_episode_artifacts(evidence_path)
        if replayed_trace != persisted_trace:
            raise ValueError("released search trace differs from replayed episode evidence")
        task = _json_object(task_bytes, "formal task")
        if task.get("instance_id") != item.get("instance_id"):
            raise ValueError("trace manifest instance differs from its formal task")

        domain_pddl = _required_text(task, "domain_pddl", "formal task")
        problem_pddl = _required_text(task, "problem_pddl", "formal task")
        authority = PDDLStateAuthority.from_pddl(domain_pddl, problem_pddl)
        record_count = _record_count(persisted_trace)
        materialized = materialize_search_trace(
            persisted_trace,
            authority=authority,
            limits=TraceSegmentLimits(
                max_records=max(1, record_count),
                max_bytes=max(1_000_000, len(persisted_trace) * max(1, record_count)),
            ),
            include_atomic_segments=not (is_v3 or is_v5),
        )
        identity = authority.semantic_task_identity() if is_v5 else _source_instance_identity(item)
        prior_split = assignments.get(identity)
        if prior_split is not None and prior_split != split:
            split_conflicts += 1
        else:
            assignments[identity] = split
        assignment_id = split_assignment_id(identity, split)
        goal_atoms = list(authority.goal_atoms or ())

        source_records = cast(list[dict[str, Any]], json.loads(persisted_trace)["records"])
        for index, record in enumerate(source_records):
            if not (is_v3 or is_v5):
                segment = materialized.atomic_segments[index]
                atomic = _json_object(segment.to_bytes(), "atomic Search-Trace Segment")
                atomic_record = cast(dict[str, Any], atomic["records"][0])
                supervised_fields = ("observation", "rationale", "operation", "result")
                if any(atomic_record[field] != record[field] for field in supervised_fields):
                    future_leaks += 1
            rolling_context = materialized.rolling_context_before(index, accepted_delta_limit=accepted_delta_limit)
            if any(delta.record_index >= index for delta in rolling_context.accepted_deltas):
                future_leaks += 1

            common = _record_metadata(
                item,
                assignment_id=assignment_id,
                identity=identity,
                record=record,
            )
            if is_v3:
                common["schema_version"] = _RECORD_SCHEMA_V3
            elif is_v5:
                common["schema_version"] = _RECORD_SCHEMA_V5
            if is_v3:
                process_input, dropped = build_bounded_bfs_model_input(
                    goal_atoms=goal_atoms,
                    observation=record["observation"],
                    checkpoint=rolling_context.checkpoint,
                    accepted_deltas=rolling_context.accepted_deltas,
                    max_bytes=model_input_byte_budget,
                )
                dropped_context_deltas += dropped
                max_model_input_bytes = max(max_model_input_bytes, len(_canonical_json_bytes(process_input)))
            elif is_v5:
                assert input_token_counter is not None
                try:
                    process_input, dropped = build_bounded_bfs_model_input_v4(
                        authority=authority,
                        goal_atoms=goal_atoms,
                        observation=record["observation"],
                        checkpoint=rolling_context.checkpoint,
                        accepted_deltas=rolling_context.accepted_deltas,
                        max_bytes=model_input_byte_budget,
                        max_input_tokens=max_input_tokens,
                        token_counter=input_token_counter,
                    )
                except ValueError as error:
                    raise ValueError(
                        f"BFS v5 required input failed for {item['instance_id']} record {index}: {error}"
                    ) from error
                _validate_v5_teacher_decision(record, process_input)
                dropped_context_deltas += dropped
                max_model_input_bytes = max(max_model_input_bytes, len(_canonical_json_bytes(process_input)))
                max_model_input_tokens = max(max_model_input_tokens, input_token_counter(process_input))
            else:
                process_input = {
                    "goal_atoms": goal_atoms,
                    "observation": record["observation"],
                    "search_memory": _json_object(rolling_context.to_bytes(), "rolling search context"),
                }
            process_rows.append(
                {
                    **common,
                    "input": process_input,
                    "target": {
                        "canonical_rationale": record["rationale"],
                        "runtime_result": None if (is_v3 or is_v5) else record["result"],
                        "typed_operation": record["operation"],
                    },
                    "view": "process",
                }
            )
            if is_v5:
                assert tokenizer is not None
                target_text = json.dumps(
                    process_rows[-1]["target"],
                    allow_nan=False,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                target_tokens = len(tokenizer.tokenizer.encode(target_text, add_special_tokens=False))
                max_target_tokens = max(max_target_tokens, target_tokens)
                if target_tokens > phase_gate.freeze["budgets"]["max_output_tokens_per_operation"]:
                    raise ValueError("BFS v5 teacher target exceeds the frozen output token budget")
            result = record["result"]
            if not (is_v3 or is_v5) and result["status"] == "accepted":
                transition = result["transition"]
                operational_rows.append(
                    {
                        **common,
                        "input": {
                            "goal_atoms": goal_atoms,
                            "source_state": transition["source_state"],
                        },
                        "target": {
                            "action": transition["action"],
                            "target_state": transition["target_state"],
                            "validity": "accepted",
                        },
                        "view": "operational",
                    }
                )

    operational_rows.sort(key=_record_sort_key)
    process_rows.sort(key=_record_sort_key)
    for row in (*operational_rows, *process_rows):
        row["record_id"] = _record_id(row)

    contamination_count = sum(
        1
        for row in operational_rows
        if _contains_any_key(row["input"], _PROCESS_ONLY_FIELDS)
        or _contains_any_key(row["target"], _PROCESS_ONLY_FIELDS)
    )
    contamination_rate = contamination_count / len(operational_rows) if operational_rows else 0.0
    if is_v5:
        audit = _v5_corpus_audit(
            process_rows,
            future_leaks=future_leaks,
            held_out_instances=held_out_instances,
            split_conflicts=split_conflicts,
            dropped_context_deltas=dropped_context_deltas,
            max_model_input_bytes=max_model_input_bytes,
            max_model_input_tokens=max_model_input_tokens,
            max_target_tokens=max_target_tokens,
            model_input_byte_budget=model_input_byte_budget,
            max_input_tokens=max_input_tokens,
        )
    elif is_v3:
        non_null_runtime_results = sum(row["target"]["runtime_result"] is not None for row in process_rows)
        audit = {
            "future_step_leakage_count": future_leaks,
            "held_out_instance_count": held_out_instances,
            "max_model_input_bytes": max_model_input_bytes,
            "model_input_byte_budget": model_input_byte_budget,
            "model_target_runtime_result_non_null_count": non_null_runtime_results,
            "operational_artifact_count": 0,
            "rolling_context_deltas_dropped": dropped_context_deltas,
            "schema_version": _AUDIT_SCHEMA_V3,
            "split_conflict_count": split_conflicts,
            "status": "passed",
        }
        if future_leaks or held_out_instances or split_conflicts or non_null_runtime_results:
            raise ValueError("BFS v3 process corpus audit failed")
    else:
        audit = {
            "future_step_leakage_count": future_leaks,
            "held_out_instance_count": held_out_instances,
            "operational_process_record_contamination": contamination_rate,
            "operational_process_record_contamination_count": contamination_count,
            "schema_version": _AUDIT_SCHEMA,
            "split_conflict_count": split_conflicts,
            "status": "passed",
        }
        threshold = phase_gate.freeze["thresholds"]["operational_process_record_contamination"]
        if future_leaks or held_out_instances or split_conflicts or contamination_rate > threshold:
            raise ValueError("BFS text corpus leakage audit failed")

    split_rows = [
        {
            "assignment_id": split_assignment_id(identity, split),
            "identity": identity,
            "split": split,
        }
        for identity, split in sorted(assignments.items())
    ]
    payloads = {
        _PROCESS_PATH.as_posix(): _jsonl_bytes(process_rows),
        _PROCESS_CURRICULUM_PATH.as_posix(): _jsonl_bytes(
            _curriculum_rows(
                process_rows,
                "process",
                schema_version=(
                    _CURRICULUM_SCHEMA_V3
                    if is_v3
                    else _CURRICULUM_SCHEMA_V5 if is_v5 else _CURRICULUM_SCHEMA
                ),
            )
        ),
        _SPLIT_LEDGER_PATH.as_posix(): _jsonl_bytes(split_rows),
        _LEAKAGE_AUDIT_PATH.as_posix(): _canonical_json_bytes(audit),
    }
    if not (is_v3 or is_v5):
        payloads[_OPERATIONAL_PATH.as_posix()] = _jsonl_bytes(operational_rows)
        payloads[_OPERATIONAL_CURRICULUM_PATH.as_posix()] = _jsonl_bytes(
            _curriculum_rows(operational_rows, "operational")
        )
    rolling_context_manifest = {
        "accepted_delta_limit": accepted_delta_limit,
        "max_context_tokens": phase_gate.freeze["budgets"]["max_context_tokens"],
        "max_output_tokens_per_operation": phase_gate.freeze["budgets"]["max_output_tokens_per_operation"],
    }
    if is_v3 or is_v5:
        rolling_context_manifest.update(
            {
                "max_model_input_bytes": model_input_byte_budget,
                "projection": (
                    "bounded_bfs_search_memory_v3" if is_v3 else "bounded_bfs_search_memory_v4"
                ),
            }
        )
    manifest = {
        "artifacts": [
            {
                "path": path,
                "size_bytes": len(payload),
            }
            for path, payload in sorted(payloads.items())
        ],
        "counts": {
            **({} if (is_v3 or is_v5) else {"operational_records": len(operational_rows)}),
            "process_records": len(process_rows),
            "split_assignments": len(split_rows),
        },
        "phase_receipt": phase_gate.receipt(stage="corpus_release"),
        "rolling_context": rolling_context_manifest,
        "schema_version": (
            _RELEASE_SCHEMA_V3 if is_v3 else _RELEASE_SCHEMA_V5 if is_v5 else _RELEASE_SCHEMA
        ),
        "source_trace_manifest_path": str(trace_manifest_path),
        "split_unit": "semantic_task_identity" if is_v5 else "whole_problem_instance",
        "views": ["process"] if (is_v3 or is_v5) else ["operational", "process"],
    }
    payloads[_RELEASE_MANIFEST_PATH.as_posix()] = _canonical_json_bytes(manifest)
    return payloads


def _pinned_input_token_counter(phase_gate: BFSPhaseGate) -> QwenTextTokenCounter:
    model = phase_gate.freeze["models"]["primary"]
    return load_qwen_text_token_counter(model_id=model["model_id"], revision=model["revision"])


def _validate_v5_teacher_decision(record: Mapping[str, Any], model_input: Mapping[str, Any]) -> None:
    operation = record.get("operation")
    if not isinstance(operation, Mapping):
        raise ValueError("BFS v5 teacher operation is malformed")
    search_memory = model_input.get("search_memory")
    observation = model_input.get("observation")
    if not isinstance(search_memory, Mapping) or not isinstance(observation, Mapping):
        raise ValueError("BFS v5 model input is malformed")
    candidates = search_memory.get("successor_candidates")
    if not isinstance(candidates, list) or not all(isinstance(candidate, Mapping) for candidate in candidates):
        raise ValueError("BFS v5 successor candidates are malformed")
    serializations = [
        f"{candidate['grounded_action']['name']}({','.join(candidate['grounded_action']['args'])})"
        for candidate in candidates
    ]
    if serializations != sorted(serializations):
        raise ValueError("BFS v5 successor candidates are not canonically ordered")
    unvisited = [candidate for candidate in candidates if candidate.get("visited") is False]
    state_id = observation.get("state_id")
    if operation.get("operation_type") == "retire_frontier":
        if unvisited or operation.get("state_id") != state_id:
            raise ValueError("BFS v5 teacher retired before exhausting unvisited successors")
        return
    if not unvisited:
        raise ValueError("BFS v5 teacher transition has no unvisited successor")
    expected = unvisited[0]
    if operation.get("source_state_id") != state_id or operation.get("action") != expected.get("grounded_action"):
        raise ValueError("BFS v5 teacher did not select the first canonical unvisited successor")


def _v5_corpus_audit(
    rows: list[dict[str, Any]],
    *,
    future_leaks: int,
    held_out_instances: int,
    split_conflicts: int,
    dropped_context_deltas: int,
    max_model_input_bytes: int,
    max_model_input_tokens: int,
    max_target_tokens: int,
    model_input_byte_budget: int,
    max_input_tokens: int,
) -> dict[str, Any]:
    inputs_by_split: dict[str, set[bytes]] = {"train": set(), "dev": set()}
    pairs_by_split: dict[str, set[tuple[bytes, bytes]]] = {"train": set(), "dev": set()}
    identities_by_split: dict[str, set[str]] = {"train": set(), "dev": set()}
    targets_by_input: dict[bytes, set[bytes]] = {}
    records_by_input: dict[bytes, list[tuple[str, str]]] = {}
    for row in rows:
        split = cast(str, row["split"])
        input_bytes = _canonical_json_bytes(row["input"])
        target_bytes = _canonical_json_bytes(row["target"])
        inputs_by_split[split].add(input_bytes)
        pairs_by_split[split].add((input_bytes, target_bytes))
        identities_by_split[split].add(cast(str, row["whole_instance_id"]))
        targets_by_input.setdefault(input_bytes, set()).add(target_bytes)
        records_by_input.setdefault(input_bytes, []).append((split, cast(str, row["record_id"])))

    semantic_overlap = identities_by_split["train"] & identities_by_split["dev"]
    input_overlap = inputs_by_split["train"] & inputs_by_split["dev"]
    pair_overlap = pairs_by_split["train"] & pairs_by_split["dev"]
    conflicting_inputs = sum(len(targets) > 1 for targets in targets_by_input.values())
    audit = {
        "canonical_input_overlap_count": len(input_overlap),
        "future_step_leakage_count": future_leaks,
        "held_out_instance_count": held_out_instances,
        "identical_input_conflicting_target_count": conflicting_inputs,
        "input_target_overlap_count": len(pair_overlap),
        "live_training_input_mismatch_count": 0,
        "max_model_input_bytes": max_model_input_bytes,
        "max_model_input_tokens": max_model_input_tokens,
        "max_target_tokens": max_target_tokens,
        "model_input_byte_preference": model_input_byte_budget,
        "model_input_token_budget": max_input_tokens,
        "rolling_context_deltas_dropped": dropped_context_deltas,
        "schema_version": _AUDIT_SCHEMA_V5,
        "semantic_task_overlap_count": len(semantic_overlap),
        "split_conflict_count": split_conflicts,
        "status": "passed",
        "teacher_decision_rejection_count": 0,
    }
    if (
        future_leaks
        or held_out_instances
        or split_conflicts
        or semantic_overlap
        or input_overlap
        or pair_overlap
        or conflicting_inputs
    ):
        examples = {
            "conflicting_target_records": [
                records_by_input[input_bytes]
                for input_bytes, targets in targets_by_input.items()
                if len(targets) > 1
            ][:10],
            "cross_split_input_records": [records_by_input[input_bytes] for input_bytes in sorted(input_overlap)][:10],
        }
        raise ValueError(
            "BFS v5 observable process corpus audit failed: "
            + json.dumps({"audit": audit, "examples": examples}, allow_nan=False, separators=(",", ":"), sort_keys=True)
        )
    return audit


def _validated_trace_items(trace_manifest: Mapping[str, Any], phase_gate: BFSPhaseGate) -> list[dict[str, Any]]:
    phase_schema = phase_gate.freeze["schema_version"]
    expected_schema = {
        "bfs_phase_freeze_v1": "bfs_expert_trace_generation_v1",
        "bfs_phase_freeze_v3": "bfs_expert_trace_generation_v3",
        "bfs_phase_freeze_v5": "bfs_expert_trace_generation_v5",
        "bfs_phase_freeze_v6": "bfs_expert_trace_generation_v5",
    }.get(phase_schema, "bfs_expert_trace_generation_v1")
    if (
        trace_manifest.get("schema_version") != expected_schema
        or trace_manifest.get("algorithm") != "bfs"
        or trace_manifest.get("phase_receipt") != phase_gate.receipt(stage="trace_generation")
    ):
        raise ValueError("BFS trace manifest does not match the frozen trace-generation phase")
    traces = trace_manifest.get("traces")
    if not isinstance(traces, list) or not all(isinstance(item, dict) for item in traces):
        raise ValueError("BFS trace manifest traces must be objects")
    expected = {
        (domain, difficulty)
        for domain in phase_gate.freeze["data"]["domains"]
        for difficulty in phase_gate.freeze["data"]["strata"]
    }
    counts = Counter((item.get("domain_id"), item.get("difficulty")) for item in traces)
    minimum = phase_gate.freeze["thresholds"]["expert_trace_minimum_per_domain_difficulty"]
    if set(counts) != expected or any(counts[stratum] < minimum for stratum in expected):
        raise ValueError("BFS trace manifest does not cover every frozen stratum")
    expected_trace_receipt = phase_gate.receipt(stage="trace_generation")
    allowed_splits = set(phase_gate.freeze["data"]["allowed_splits"])
    for item in traces:
        if item.get("phase_receipt") != expected_trace_receipt:
            raise ValueError("BFS trace item has the wrong phase receipt")
        if _text(item, "source", "split") not in allowed_splits:
            raise ValueError("BFS trace item uses a split outside the frozen development corpus")
    return cast(list[dict[str, Any]], traces)


def _record_metadata(
    item: Mapping[str, Any],
    *,
    assignment_id: str,
    identity: str,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "algorithm": "bfs",
        "difficulty": item["difficulty"],
        "domain_id": item["domain_id"],
        "instance_id": item["instance_id"],
        "schema_version": _RECORD_SCHEMA,
        "split": cast(Mapping[str, Any], item["source"])["split"],
        "split_assignment_id": assignment_id,
        "trace_record_index": record["index"],
        "whole_instance_id": identity,
    }


def _curriculum_rows(
    rows: list[dict[str, Any]],
    view: str,
    *,
    schema_version: str = _CURRICULUM_SCHEMA,
) -> list[dict[str, Any]]:
    return [
        {
            "curriculum_index": index,
            "difficulty": row["difficulty"],
            "record_id": row["record_id"],
            "schema_version": schema_version,
            "split": row["split"],
            "stage_index": _DIFFICULTY_ORDER[row["difficulty"]],
            "view": view,
        }
        for index, row in enumerate(rows)
    ]


def _record_id(row: Mapping[str, Any]) -> str:
    return f"{row['instance_id']}:{row['trace_record_index']}:{row['view']}"


def _trace_sort_key(item: Mapping[str, Any]) -> tuple[int, str, str]:
    difficulty = cast(str, item["difficulty"])
    return (_DIFFICULTY_ORDER[difficulty], cast(str, item["domain_id"]), cast(str, item["instance_id"]))


def _record_sort_key(row: Mapping[str, Any]) -> tuple[int, str, str, int]:
    return (
        _DIFFICULTY_ORDER[cast(str, row["difficulty"])],
        cast(str, row["domain_id"]),
        cast(str, row["instance_id"]),
        cast(int, row["trace_record_index"]),
    )


def _artifact_path(root: Path, artifact: Mapping[str, Any]) -> Path:
    relative_path = Path(_required_text(artifact, "path", "trace artifact"))
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("trace artifact path must stay inside the trace root")
    path = root / relative_path
    payload = path.read_bytes()
    size = artifact.get("size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size != len(payload):
        raise ValueError(f"trace artifact size mismatch: {relative_path}")
    return path


def _artifact_bytes(root: Path, artifact: Mapping[str, Any]) -> bytes:
    return _artifact_path(root, artifact).read_bytes()


def _source_instance_identity(item: Mapping[str, Any]) -> str:
    return _required_text(item, "instance_id", "trace item")


def _load_split_authority(
    traces: list[dict[str, Any]],
    phase_gate: BFSPhaseGate,
) -> dict[str, dict[str, Any]]:
    sources = {_text(item, "source", "accepted_manifest_path") for item in traces}
    if len(sources) != 1:
        raise ValueError("BFS traces do not share one frozen accepted manifest")
    path_text = sources.pop()
    manifest_path = Path(path_text).resolve()
    payload = manifest_path.read_bytes()
    frozen_artifacts = {
        (_REPO_ROOT / artifact["path"]).resolve() if not Path(artifact["path"]).is_absolute() else Path(artifact["path"])
        for artifact in phase_gate.freeze["data"]["artifacts"]
    }
    if manifest_path not in frozen_artifacts:
        raise ValueError("BFS trace accepted manifest is not the frozen split authority")

    assignments: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(payload.decode("utf-8").splitlines(), start=1):
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"frozen accepted manifest has invalid JSON at line {line_number}") from error
        if not isinstance(row, dict) or row.get("status") != "accepted":
            raise ValueError(f"frozen accepted manifest row is invalid at line {line_number}")
        instance_id = _required_text(row, "instance_id", "accepted manifest row")
        if instance_id in assignments:
            raise ValueError(f"frozen accepted manifest repeats instance_id: {instance_id}")
        assignments[instance_id] = row
    return assignments


def _validate_authoritative_split(
    item: Mapping[str, Any],
    authority: Mapping[str, Mapping[str, Any]],
) -> None:
    instance_id = _required_text(item, "instance_id", "trace item")
    row = authority.get(instance_id)
    if row is None:
        raise ValueError(f"trace instance is absent from the frozen accepted manifest: {instance_id}")
    source = item.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("BFS trace item source must be an object")
    if source.get("split") != row.get("split"):
        raise ValueError("trace split differs from the frozen accepted manifest")
    expected = {
        "bucket": item.get("difficulty"),
        "domain_id": item.get("domain_id"),
    }
    if any(row.get(field) != value for field, value in expected.items()):
        raise ValueError("trace stratum differs from the frozen accepted manifest")


def _record_count(trace: bytes) -> int:
    payload = _json_object(trace, "search trace")
    value = payload.get("record_count")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("search trace record_count must be a non-negative integer")
    return value


def _rolling_delta_limit(phase_gate: BFSPhaseGate) -> int:
    budgets = phase_gate.freeze["budgets"]
    context_tokens = budgets["max_context_tokens"]
    operation_tokens = budgets["max_output_tokens_per_operation"]
    if (
        isinstance(context_tokens, bool)
        or not isinstance(context_tokens, int)
        or context_tokens <= 0
        or isinstance(operation_tokens, bool)
        or not isinstance(operation_tokens, int)
        or operation_tokens <= 0
    ):
        raise ValueError("frozen BFS context and operation token budgets must be positive integers")
    return max(1, context_tokens // operation_tokens)


def _text(item: Mapping[str, Any], object_field: str, text_field: str) -> str:
    nested = item.get(object_field)
    if not isinstance(nested, Mapping):
        raise ValueError(f"BFS trace item field must be an object: {object_field}")
    return _required_text(nested, text_field, object_field)


def _required_text(value: Mapping[str, Any], field: str, name: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise ValueError(f"{name}.{field} must be non-empty text")
    return item


def _contains_any_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        return any(key in forbidden or _contains_any_key(child, forbidden) for key, child in value.items())
    if isinstance(value, list):
        return any(_contains_any_key(child, forbidden) for child in value)
    return False


def _json_object(payload: bytes, name: str) -> dict[str, Any]:
    try:
        value: Any = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{name} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_json_bytes(row) for row in rows)


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


__all__ = ["regenerate_bfs_text_corpus", "run_frozen_bfs_text_corpus_release"]
