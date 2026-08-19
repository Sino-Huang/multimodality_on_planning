"""Release governed operational and process corpus views from BFS traces."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, cast

from src.data_collect.generate import GenerationRequest, GenerationRunReceipt, run_authorized_generation
from src.data_collect.replay import parse_canonical_bundle
from src.data_collect.splits import split_assignment_id, whole_instance_identity

from .bfs_phase import BFSPhaseGate
from .pddl_state import PDDLStateAuthority
from .search_context import materialize_search_trace
from .search_episode import replay_search_episode
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
    """Build and atomically publish the issue-49-authorized BFS text corpus."""

    def execute() -> dict[str, object]:
        phase_gate.require_run(stage="corpus_release", contract_id=request.binding.contract_id)
        output_root = Path(request.binding.output_root).resolve()
        if output_root.exists():
            raise FileExistsError(f"BFS corpus output root already exists: {output_root}")

        artifacts = _build_release(
            Path(trace_manifest_path).resolve(),
            signing_key=request.signing_key,
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
            "corpus_manifest_sha256": _sha256(manifest_bytes),
            "operational_record_count": manifest["counts"]["operational_records"],
            "process_record_count": manifest["counts"]["process_records"],
            "split_assignment_count": manifest["counts"]["split_assignments"],
        }

    return run_authorized_generation(request, execute)


def regenerate_bfs_text_corpus(
    *,
    trace_manifest_path: str | Path,
    signing_key: bytes | str,
    phase_gate: BFSPhaseGate,
) -> dict[str, bytes]:
    """Rebuild every released byte after verifying the retained trace evidence."""

    return _build_release(
        Path(trace_manifest_path).resolve(),
        signing_key=signing_key,
        phase_gate=phase_gate,
    )


def _build_release(
    trace_manifest_path: Path,
    *,
    signing_key: bytes | str,
    phase_gate: BFSPhaseGate,
) -> dict[str, bytes]:
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

    for item in sorted(traces, key=_trace_sort_key):
        split = _text(item, "source", "split")
        _validate_authoritative_split(item, split_authority)
        if split == phase_gate.freeze["data"]["held_out_split"]:
            held_out_instances += 1
        evidence_bytes = _artifact_bytes(trace_root, cast(Mapping[str, Any], item["evidence"]))
        persisted_trace = _artifact_bytes(trace_root, cast(Mapping[str, Any], item["search_trace"]))
        evidence = _json_object(evidence_bytes, "trace evidence")
        episode = replay_search_episode(evidence, signing_key=signing_key)
        bundle = base64.b64decode(episode["evidence"]["bundle"].encode("ascii"), validate=True)
        bundle_artifacts = parse_canonical_bundle(bundle)
        if bundle_artifacts["search-trace.json"] != persisted_trace:
            raise ValueError("released search trace differs from its replayed Evidence Bundle")
        task = _json_object(bundle_artifacts["task.json"], "formal task")
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
        )
        identity = _source_instance_identity(item)
        prior_split = assignments.get(identity)
        if prior_split is not None and prior_split != split:
            split_conflicts += 1
        else:
            assignments[identity] = split
        assignment_id = split_assignment_id(identity, split)
        goal_atoms = list(authority.goal_atoms or ())

        source_records = cast(list[dict[str, Any]], json.loads(persisted_trace)["records"])
        for segment in materialized.atomic_segments:
            atomic = _json_object(segment.to_bytes(), "atomic Search-Trace Segment")
            atomic_record = cast(dict[str, Any], atomic["records"][0])
            index = segment.record_index
            record = source_records[index]
            supervised_fields = ("observation", "rationale", "operation", "result")
            if any(atomic_record[field] != record[field] for field in supervised_fields):
                future_leaks += 1
            rolling = _json_object(
                materialized.rolling_context_before(index, accepted_delta_limit=accepted_delta_limit).to_bytes(),
                "rolling search context",
            )
            if any(delta["record_index"] >= index for delta in rolling["accepted_deltas"]):
                future_leaks += 1

            common = _record_metadata(
                item,
                assignment_id=assignment_id,
                identity=identity,
                record=record,
            )
            process_rows.append(
                {
                    **common,
                    "input": {
                        "goal_atoms": goal_atoms,
                        "observation": record["observation"],
                        "search_memory": rolling,
                    },
                    "target": {
                        "canonical_rationale": record["rationale"],
                        "runtime_result": record["result"],
                        "typed_operation": record["operation"],
                    },
                    "view": "process",
                }
            )
            result = record["result"]
            if result["status"] == "accepted":
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
        _OPERATIONAL_PATH.as_posix(): _jsonl_bytes(operational_rows),
        _PROCESS_PATH.as_posix(): _jsonl_bytes(process_rows),
        _OPERATIONAL_CURRICULUM_PATH.as_posix(): _jsonl_bytes(_curriculum_rows(operational_rows, "operational")),
        _PROCESS_CURRICULUM_PATH.as_posix(): _jsonl_bytes(_curriculum_rows(process_rows, "process")),
        _SPLIT_LEDGER_PATH.as_posix(): _jsonl_bytes(split_rows),
        _LEAKAGE_AUDIT_PATH.as_posix(): _canonical_json_bytes(audit),
    }
    manifest = {
        "artifacts": [
            {
                "path": path,
                "sha256": _sha256(payload),
                "size_bytes": len(payload),
            }
            for path, payload in sorted(payloads.items())
        ],
        "counts": {
            "operational_records": len(operational_rows),
            "process_records": len(process_rows),
            "split_assignments": len(split_rows),
        },
        "phase_receipt": phase_gate.receipt(stage="corpus_release"),
        "rolling_context": {
            "accepted_delta_limit": accepted_delta_limit,
            "max_context_tokens": phase_gate.freeze["budgets"]["max_context_tokens"],
            "max_output_tokens_per_operation": phase_gate.freeze["budgets"]["max_output_tokens_per_operation"],
        },
        "schema_version": _RELEASE_SCHEMA,
        "source_trace_manifest": {"sha256": _sha256(trace_manifest_bytes)},
        "split_unit": "whole_problem_instance",
        "views": ["operational", "process"],
    }
    payloads[_RELEASE_MANIFEST_PATH.as_posix()] = _canonical_json_bytes(manifest)
    return payloads


def _validated_trace_items(trace_manifest: Mapping[str, Any], phase_gate: BFSPhaseGate) -> list[dict[str, Any]]:
    if (
        trace_manifest.get("schema_version") != "bfs_expert_trace_generation_v1"
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
        "source_record_hash": record["record_hash"],
        "split": cast(Mapping[str, Any], item["source"])["split"],
        "split_assignment_id": assignment_id,
        "trace_record_index": record["index"],
        "whole_instance_id": identity,
    }


def _curriculum_rows(rows: list[dict[str, Any]], view: str) -> list[dict[str, Any]]:
    return [
        {
            "curriculum_index": index,
            "difficulty": row["difficulty"],
            "record_id": row["record_id"],
            "schema_version": _CURRICULUM_SCHEMA,
            "split": row["split"],
            "stage_index": _DIFFICULTY_ORDER[row["difficulty"]],
            "view": view,
        }
        for index, row in enumerate(rows)
    ]


def _record_id(row: Mapping[str, Any]) -> str:
    identity = {
        "difficulty": row["difficulty"],
        "instance_id": row["instance_id"],
        "source_record_hash": row["source_record_hash"],
        "split_assignment_id": row["split_assignment_id"],
        "view": row["view"],
    }
    return "sha256:" + _sha256(_canonical_json_bytes(identity).rstrip(b"\n"))


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


def _artifact_bytes(root: Path, artifact: Mapping[str, Any]) -> bytes:
    relative_path = Path(_required_text(artifact, "path", "trace artifact"))
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("trace artifact path must stay inside the trace root")
    path = root / relative_path
    payload = path.read_bytes()
    if _sha256(payload) != _required_text(artifact, "sha256", "trace artifact"):
        raise ValueError(f"trace artifact digest mismatch: {relative_path}")
    size = artifact.get("size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size != len(payload):
        raise ValueError(f"trace artifact size mismatch: {relative_path}")
    return payload


def _source_instance_identity(item: Mapping[str, Any]) -> str:
    source = item.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("BFS trace item source must be an object")
    domain_path = Path(_required_text(source, "domain_path", "trace source"))
    problem_path = Path(_required_text(source, "problem_path", "trace source"))
    domain_bytes = domain_path.read_bytes()
    problem_bytes = problem_path.read_bytes()
    if (
        _sha256(domain_bytes) != _required_text(source, "domain_sha256", "trace source")
        or _sha256(problem_bytes) != _required_text(source, "problem_sha256", "trace source")
    ):
        raise ValueError("trace source PDDL differs from its retained provenance")
    return whole_instance_identity(domain_bytes, problem_bytes)


def _load_split_authority(
    traces: list[dict[str, Any]],
    phase_gate: BFSPhaseGate,
) -> dict[str, dict[str, Any]]:
    sources = {
        (
            _text(item, "source", "accepted_manifest_path"),
            _text(item, "source", "accepted_manifest_sha256"),
        )
        for item in traces
    }
    if len(sources) != 1:
        raise ValueError("BFS traces do not share one frozen accepted manifest")
    path_text, expected_digest = sources.pop()
    manifest_path = Path(path_text).resolve()
    payload = manifest_path.read_bytes()
    frozen_artifacts = {
        (_REPO_ROOT / artifact["path"]).resolve() if not Path(artifact["path"]).is_absolute() else Path(artifact["path"])
        for artifact in phase_gate.freeze["data"]["artifacts"]
        if artifact["sha256"] == expected_digest
    }
    if _sha256(payload) != expected_digest or manifest_path not in frozen_artifacts:
        raise ValueError("BFS trace accepted manifest differs from the frozen split authority")

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
        "domain_hash": source.get("manifest_domain_sha256"),
        "domain_id": item.get("domain_id"),
        "problem_hash": source.get("manifest_problem_sha256"),
    }
    if any(row.get(field) != value for field, value in expected.items()):
        raise ValueError("trace stratum or PDDL digest differs from the frozen accepted manifest")


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


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


__all__ = ["regenerate_bfs_text_corpus", "run_frozen_bfs_text_corpus_release"]
