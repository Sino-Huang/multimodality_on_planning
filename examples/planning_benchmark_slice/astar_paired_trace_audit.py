"""Independent per-pair and release audits for issue-63 paired A* traces."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from time import monotonic
from typing import Any

from .astar_controller import AStarController
from .astar_hmax import HMaxHeuristic
from .astar_landmarks import LandmarkCountHeuristic
from .astar_model_input import (
    build_astar_live_model_input,
    build_astar_teacher_model_input,
    build_bounded_astar_live_model_input,
    build_bounded_astar_teacher_model_input,
    project_bounded_astar_model_input,
    serialize_astar_message_prefix,
)
from .astar_paired_generation import build_astar_pair_alignment, preflight_frozen_astar_pair_generation
from .astar_phase import AStarPairedPhaseGate
from .episode_evidence import materialize_episode_artifacts, read_episode_evidence
from .pddl_state import PDDLStateAuthority
from .search_episode import replay_search_episode

_ADAPTERS = ("astar_hmax", "astar_landmark_count")
_COUNTERS = (
    "canonical_byte_parity_error_count",
    "exact_count_error_count",
    "input_overflow_count",
    "pair_completeness_error_count",
    "parse_rejection_count",
    "provenance_error_count",
    "replay_error_count",
    "runtime_rejection_count",
    "target_overflow_count",
    "tie_break_error_count",
    "token_id_parity_error_count",
    "alignment_error_count",
)


def audit_frozen_astar_pair(
    *,
    row: Mapping[str, Any],
    pair_item: Mapping[str, Any],
    output_root: str | Path,
    phase_gate: AStarPairedPhaseGate,
    input_token_counter: Callable[[Mapping[str, Any]], int] | None = None,
    target_token_counter: Callable[[str], int] | None = None,
    input_token_ids: Callable[[Sequence[Mapping[str, str]]], Sequence[int]] | None = None,
    teacher_input_token_ids: Callable[[Sequence[Mapping[str, str]]], Sequence[int]] | None = None,
    fixture_only: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Independently replay and audit every decision in one complete pair."""

    phase_gate.require_run(stage="trace_generation", contract_id=phase_gate.phase_id)
    root = Path(output_root)
    adapters = pair_item.get("adapters")
    if (
        pair_item.get("pair_id") != row.get("pair_id")
        or pair_item.get("semantic_task_identity") != row.get("semantic_task_identity")
        or pair_item.get("canonical_tie_break") != ["f", "generation_serial"]
        or pair_item.get("generation_max_expansions") != row.get("generation_max_expansions")
        or pair_item.get("task")
        != {
            "path": row.get("task_path"),
            "sha256": row.get("task_sha256"),
            "size_bytes": row.get("task_bytes"),
        }
        or not isinstance(adapters, list)
        or [item.get("adapter") for item in adapters if isinstance(item, Mapping)] != list(_ADAPTERS)
    ):
        raise ValueError("A* pair manifest completeness, identity, or tie break differs")
    task_payload = (phase_gate.repo_root / row["task_path"]).read_bytes()
    if (
        len(task_payload) != row["task_bytes"]
        or hashlib.sha256(task_payload).hexdigest() != row["task_sha256"]
    ):
        raise ValueError("A* pair task bytes differ from the frozen pair binding")
    if input_token_counter is None or target_token_counter is None:
        if fixture_only:
            input_token_counter = _fixture_input_tokens
            target_token_counter = _fixture_target_tokens
        else:
            input_token_counter, target_token_counter, input_token_ids = _pinned_token_tools(phase_gate)
    if input_token_ids is None:
        input_token_ids = _fixture_message_token_ids
    if teacher_input_token_ids is None:
        teacher_input_token_ids = input_token_ids

    episodes: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    adapter_results: list[dict[str, Any]] = []
    counters = {name: 0 for name in _COUNTERS}
    adapter_started = monotonic()
    for adapter_index, (adapter, item) in enumerate(zip(_ADAPTERS, adapters, strict=True), start=1):
        _progress(
            progress,
            adapter_index - 1,
            len(_ADAPTERS),
            adapter_started,
            row["pair_id"],
            stage=f"adapter_audit:{adapter}",
        )
        evidence_path = _bound_artifact(root, item.get("evidence"), f"{adapter} evidence")
        trace_path = _bound_artifact(root, item.get("trace"), f"{adapter} trace")
        episode = read_episode_evidence(evidence_path)
        try:
            _validate_episode_provenance(episode, row=row, adapter=adapter, phase_gate=phase_gate)
        except ValueError:
            counters["provenance_error_count"] += 1
        result = episode["result"]
        if (
            result.get("decision_count") != item.get("decision_count")
            or result.get("expansion_count") != item.get("expansion_count")
            or result.get("goal_reached") is not True
            or result.get("termination") != "goal_reached"
            or result.get("algorithm_invariants_hold") is not True
        ):
            counters["exact_count_error_count"] += 1
        task = episode["evidence"]["header"]["task"]
        authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
        heuristic = HMaxHeuristic(authority) if adapter == "astar_hmax" else LandmarkCountHeuristic(authority)
        controller = AStarController(
            authority,
            heuristic,
            accepted_delta_limit=16,
            max_budget=row["generation_max_expansions"],
        )
        decision_count = 0
        max_input = 0
        max_target = 0
        for expansion_index, event in enumerate(episode["evidence"]["events"]):
            if event.get("expansion_index") != expansion_index or event.get("invariants", {}).get("hold") is not True:
                counters["replay_error_count"] += 1
            if event.get("expanded_state_id") != controller.frontier_head_state_id():
                counters["replay_error_count"] += 1
            if event.get("observation") != build_astar_live_model_input(authority, controller):
                counters["canonical_byte_parity_error_count"] += 1
            try:
                controller.start_expansion()
            except ValueError:
                counters["replay_error_count"] += 1
                break
            for decision_index, decision in enumerate(event["decisions"]):
                try:
                    persisted_input = project_bounded_astar_model_input(
                        decision["input"],
                        max_input_tokens=phase_gate.components["corpus"]["input_token_limit"],
                        token_counter=input_token_counter,
                    )
                    live_input = build_bounded_astar_live_model_input(
                        authority,
                        controller,
                        max_input_tokens=phase_gate.components["corpus"]["input_token_limit"],
                        token_counter=input_token_counter,
                    )
                    teacher_input = build_bounded_astar_teacher_model_input(
                        authority,
                        controller,
                        max_input_tokens=phase_gate.components["corpus"]["input_token_limit"],
                        token_counter=input_token_counter,
                    )
                except ValueError:
                    persisted_input = project_bounded_astar_model_input(
                        decision["input"], max_bytes=1_000_000_000
                    )
                    live_input = project_bounded_astar_model_input(
                        build_astar_live_model_input(authority, controller),
                        max_bytes=1_000_000_000,
                    )
                    teacher_input = project_bounded_astar_model_input(
                        build_astar_teacher_model_input(authority, controller),
                        max_bytes=1_000_000_000,
                    )
                _validate_authoritative_decision(teacher_input, decision)
                live_prefix = serialize_astar_message_prefix(live_input)
                teacher_prefix = serialize_astar_message_prefix(teacher_input)
                persisted_prefix = serialize_astar_message_prefix(persisted_input)
                if not (
                    _canonical_bytes(live_input)
                    == _canonical_bytes(teacher_input)
                    == _canonical_bytes(persisted_input)
                    and _canonical_bytes(live_prefix)
                    == _canonical_bytes(teacher_prefix)
                    == _canonical_bytes(persisted_prefix)
                ):
                    counters["canonical_byte_parity_error_count"] += 1
                if not (
                    tuple(input_token_ids(live_prefix))
                    == tuple(teacher_input_token_ids(teacher_prefix))
                    == tuple(teacher_input_token_ids(persisted_prefix))
                ):
                    counters["token_id_parity_error_count"] += 1
                target = {
                    "canonical_rationale": "exact_astar_canonical_successor",
                    "runtime_result": None,
                    "typed_operation": decision["operation"],
                }
                target_text = _canonical_text(target)
                try:
                    parsed = _strict_target(target_text)
                except (TypeError, ValueError, json.JSONDecodeError):
                    counters["parse_rejection_count"] += 1
                    parsed = None
                runtime = None
                if parsed is not None:
                    operation_text = _canonical_text(parsed["typed_operation"])
                    runtime = controller.apply_raw_output(operation_text)
                    if (
                        not runtime.accepted
                        or runtime.runtime_result != decision.get("trusted_runtime_result")
                        or parsed["typed_operation"] != decision.get("operation")
                    ):
                        counters["runtime_rejection_count"] += 1
                input_tokens = input_token_counter(teacher_input)
                target_tokens = target_token_counter(target_text)
                if input_tokens > phase_gate.components["corpus"]["input_token_limit"]:
                    counters["input_overflow_count"] += 1
                if target_tokens > phase_gate.components["corpus"]["output_token_limit"]:
                    counters["target_overflow_count"] += 1
                max_input = max(max_input, input_tokens)
                max_target = max(max_target, target_tokens)
                records.append(
                    {
                        "adapter": adapter,
                        "decision_index": decision_index,
                        "difficulty": row["difficulty"],
                        "expansion_index": expansion_index,
                        "input_tokens": input_tokens,
                        "input": teacher_input,
                        "pair_id": row["pair_id"],
                        "target": target,
                        "target_tokens": target_tokens,
                    }
                )
                decision_count += 1
            try:
                controller.finish_expansion()
            except ValueError:
                counters["replay_error_count"] += 1
                break
        if decision_count != result["decision_count"]:
            counters["exact_count_error_count"] += 1
        try:
            replay_search_episode(episode["evidence"])
            _task_bytes, exact_trace = materialize_episode_artifacts(episode["evidence"])
            if gzip.decompress(trace_path.read_bytes()) != exact_trace:
                counters["replay_error_count"] += 1
        except (OSError, ValueError):
            counters["replay_error_count"] += 1
        adapter_results.append(
            {
                "adapter": adapter,
                "decision_count": decision_count,
                "expansion_count": result["expansion_count"],
                "max_input_tokens": max_input,
                "max_target_tokens": max_target,
            }
        )
        episodes[adapter] = episode
        _progress(
            progress,
            adapter_index,
            len(_ADAPTERS),
            adapter_started,
            row["pair_id"],
            stage=f"adapter_audit:{adapter}",
        )

    alignment_path = _bound_artifact(root, pair_item.get("alignment"), "pair alignment")
    try:
        expected_alignment = build_astar_pair_alignment(row, episodes)
    except (KeyError, StopIteration, ValueError):
        counters["alignment_error_count"] += 1
    else:
        if alignment_path.read_bytes() != _canonical_bytes(expected_alignment):
            counters["alignment_error_count"] += 1
    return {
        "adapter_results": adapter_results,
        "audit_results": counters,
        "fixture_only": fixture_only,
        "pair_id": row["pair_id"],
        "teacher_records": records,
    }


def audit_astar_pair_items_release(
    *,
    manifest: Mapping[str, Any],
    output_root: str | Path,
    phase_gate: AStarPairedPhaseGate,
    progress: Callable[[str], None] | None = None,
    input_token_counter: Callable[[Mapping[str, Any]], int] | None = None,
    target_token_counter: Callable[[str], int] | None = None,
    input_token_ids: Callable[[Sequence[Mapping[str, str]]], Sequence[int]] | None = None,
    teacher_input_token_ids: Callable[[Sequence[Mapping[str, str]]], Sequence[int]] | None = None,
    fixture_only: bool = False,
    persist_audit_parts: bool = False,
) -> dict[str, Any]:
    """Audit an in-memory complete manifest before final publication."""

    rows = preflight_frozen_astar_pair_generation(phase_gate)
    items = manifest.get("pairs")
    if not isinstance(items, list) or len(items) != len(rows):
        raise ValueError("A* paired release manifest has incomplete pair coverage")
    if [item.get("pair_id") for item in items if isinstance(item, Mapping)] != [row["pair_id"] for row in rows]:
        raise ValueError("A* paired release manifest order or coverage differs")
    started = monotonic()
    all_records: list[dict[str, Any]] = []
    per_pair: list[dict[str, Any]] = []
    for completed, (row, item) in enumerate(zip(rows, items, strict=True), start=1):
        result = audit_frozen_astar_pair(
            row=row,
            pair_item=item,
            output_root=output_root,
            phase_gate=phase_gate,
            input_token_counter=input_token_counter,
            target_token_counter=target_token_counter,
            input_token_ids=input_token_ids,
            teacher_input_token_ids=teacher_input_token_ids,
            fixture_only=fixture_only,
            progress=progress,
        )
        all_records.extend(result["teacher_records"])
        per_pair.append({key: value for key, value in result.items() if key != "teacher_records"})
        if persist_audit_parts:
            part = {
                "binding": {
                    "pair_id": row["pair_id"],
                    "phase_receipt": phase_gate.receipt(stage="trace_generation"),
                    "trace_item_sha256": hashlib.sha256(_canonical_bytes(item)).hexdigest(),
                },
                "result": per_pair[-1],
                "schema_version": "astar_paired_trace_audit_part_v1",
            }
            part_path = Path(output_root) / "audit-parts" / f"{row['pair_id']}.json"
            if part_path.is_file() and part_path.read_bytes() != _canonical_bytes(part):
                raise ValueError(f"A* retained audit part differs immutably: {row['pair_id']}")
            if not part_path.is_file():
                _atomic_write(part_path, _canonical_bytes(part))
        _progress(progress, completed, len(rows), started, row["pair_id"], stage="pair_audit")
    snapshots: list[dict[str, Any]] = []
    if not fixture_only:
        for adapter in _ADAPTERS:
            snapshots.extend(select_astar_teacher_snapshots([r for r in all_records if r["adapter"] == adapter]))
    counters = {
        name: sum(pair["audit_results"][name] for pair in per_pair)
        for name in _COUNTERS
    }
    if any(counters.values()):
        raise ValueError("A* paired release audit has nonzero measured rejection counters")
    return {
        "audit_results": counters,
        "fixture_only": fixture_only,
        "model_input_token_limit": phase_gate.components["corpus"]["input_token_limit"],
        "model_output_token_limit": phase_gate.components["corpus"]["output_token_limit"],
        "pair_count": len(per_pair),
        "pairs": per_pair,
        "phase_receipt": phase_gate.receipt(stage="trace_generation"),
        "schema_version": "astar_paired_trace_release_audit_v1",
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "source_issue": 63,
        "tokenizer": (
            {"claim": "deterministic_fixture_counter_only"}
            if fixture_only
            else {
                "model_id": "Qwen/Qwen3-VL-8B-Instruct",
                "revision": phase_gate.components["model"]["model_revision"],
            }
        ),
    }


def audit_frozen_astar_pair_release(
    manifest_path: str | Path,
    *,
    phase_gate: AStarPairedPhaseGate,
    audit_path: str | Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Public independent release-audit seam."""

    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_bytes())
    audit = audit_astar_pair_items_release(
        manifest=manifest,
        output_root=path.parent.parent,
        phase_gate=phase_gate,
        progress=progress,
    )
    if audit_path is not None:
        target = Path(audit_path)
        _atomic_write(target, _canonical_bytes(audit))
    return audit


def select_astar_teacher_snapshots(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Select difficulty medians and equal-count token-rank tertile medians."""

    if any("input" not in record or "target" not in record for record in records):
        raise ValueError("A* snapshot records require bounded input and canonical target payloads")
    selections: list[dict[str, Any]] = []
    for difficulty in ("easy", "medium", "hard"):
        ranked = _ranked(record for record in records if record.get("difficulty") == difficulty)
        if not ranked:
            raise ValueError(f"A* snapshot selection lacks {difficulty} coverage")
        selections.append({**ranked[len(ranked) // 2], "selection_axis": "difficulty", "selection_bin": difficulty})
    ranked = _ranked(records)
    if len(ranked) < 3:
        raise ValueError("A* snapshot selection requires at least three records")
    for index, label in enumerate(("low", "middle", "high")):
        start = index * len(ranked) // 3
        stop = (index + 1) * len(ranked) // 3
        members = ranked[start:stop]
        selections.append(
            {**members[len(members) // 2], "selection_axis": "input_token_bin", "selection_bin": label}
        )
    return selections


def _ranked(records: Any) -> list[dict[str, Any]]:
    return sorted(
        (dict(record) for record in records),
        key=lambda record: (
            record["input_tokens"], record["pair_id"], record["expansion_index"], record["decision_index"]
        ),
    )


def _validate_episode_provenance(
    episode: Mapping[str, Any],
    *,
    row: Mapping[str, Any],
    adapter: str,
    phase_gate: AStarPairedPhaseGate,
) -> None:
    header = episode["evidence"]["header"]
    task = header["task"]
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    if (
        header["request"].get("algorithm") != adapter
        or header["request"].get("max_expansions") != row["generation_max_expansions"]
        or header["request"].get("accepted_delta_limit") != 16
        or header.get("frozen_binding") != phase_gate.receipt(stage="trace_generation")
        or authority.semantic_task_identity() != row["semantic_task_identity"]
    ):
        raise ValueError(f"A* {adapter} provenance or shared ceiling differs")


def _validate_authoritative_decision(model_input: Mapping[str, Any], decision: Mapping[str, Any]) -> None:
    current = model_input.get("current")
    candidates = model_input.get("successor_candidates")
    if not isinstance(current, Mapping) or not {
        "f", "g", "h", "state_atoms", "state_id"
    } <= set(current):
        raise ValueError("A* decision lacks authoritative current-state facts")
    if not isinstance(model_input.get("task_context"), Mapping) or not isinstance(candidates, list) or not candidates:
        raise ValueError("A* decision lacks authoritative task or candidate facts")
    required = {
        "action",
        "best_cost",
        "closed",
        "dominated",
        "f",
        "frontier",
        "g",
        "h",
        "pruned",
        "target_node_id",
        "target_state_id",
    }
    if any(not isinstance(candidate, Mapping) or not required <= set(candidate) for candidate in candidates):
        raise ValueError("A* decision candidate lacks exact replay fields")
    if "heuristic_context" in model_input and any(
        not {"progression", "progression_delta", "target_node_id"} <= set(candidate)
        for candidate in candidates
    ):
        raise ValueError("landmark A* decision lacks authoritative progression fields")
def _strict_target(payload: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("A* teacher target contains a duplicate key")
            result[key] = value
        return result

    value = json.loads(
        payload,
        object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    if (
        not isinstance(value, dict)
        or set(value) != {"canonical_rationale", "runtime_result", "typed_operation"}
        or value["canonical_rationale"] != "exact_astar_canonical_successor"
        or value["runtime_result"] is not None
        or not isinstance(value["typed_operation"], dict)
        or set(value["typed_operation"]) != {"action", "source_state_id"}
    ):
        raise ValueError("A* teacher target failed strict parsing")
    operation = value["typed_operation"]
    action = operation["action"]
    if (
        not isinstance(operation["source_state_id"], str)
        or not isinstance(action, dict)
        or set(action) != {"args", "name"}
        or not isinstance(action["name"], str)
        or not isinstance(action["args"], list)
        or any(not isinstance(argument, str) for argument in action["args"])
    ):
        raise ValueError("A* teacher target typed operation is malformed")
    return value


def _bound_artifact(root: Path, binding: object, label: str) -> Path:
    if not isinstance(binding, Mapping) or set(binding) != {"path", "sha256", "size_bytes"}:
        raise ValueError(f"A* {label} binding is malformed")
    relative = Path(str(binding["path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"A* {label} path is unsafe")
    path = root / relative
    payload = path.read_bytes()
    if len(payload) != binding["size_bytes"] or hashlib.sha256(payload).hexdigest() != binding["sha256"]:
        raise ValueError(f"A* {label} hash or size differs")
    return path


def _pinned_token_tools(
    phase_gate: AStarPairedPhaseGate,
) -> tuple[
    Callable[[Mapping[str, Any]], int],
    Callable[[str], int],
    Callable[[Sequence[Mapping[str, str]]], Sequence[int]],
]:
    from transformers import AutoProcessor

    tokenizer = AutoProcessor.from_pretrained(
        "Qwen/Qwen3-VL-8B-Instruct",
        revision=phase_gate.components["model"]["model_revision"],
    ).tokenizer

    def count_input(value: Mapping[str, Any]) -> int:
        return len(
            tokenizer.apply_chat_template(
                serialize_astar_message_prefix(value),
                tokenize=True,
                add_generation_prompt=True,
            )
        )

    def count_target(value: str) -> int:
        return len(tokenizer.encode(value, add_special_tokens=False))

    def message_token_ids(messages: Sequence[Mapping[str, str]]) -> Sequence[int]:
        return tokenizer.apply_chat_template(
            list(messages),
            tokenize=True,
            add_generation_prompt=True,
        )

    return count_input, count_target, message_token_ids


def _fixture_input_tokens(value: Mapping[str, Any]) -> int:
    return max(1, len(_canonical_bytes(serialize_astar_message_prefix(value))) // 16)


def _fixture_target_tokens(value: str) -> int:
    return max(1, len(value.encode()) // 8)


def _fixture_message_token_ids(messages: Sequence[Mapping[str, str]]) -> Sequence[int]:
    return tuple(_canonical_bytes(list(messages)))


def _progress(
    progress: Callable[[str], None] | None,
    completed: int,
    total: int,
    started: float,
    pair_id: str | None,
    *,
    stage: str,
) -> None:
    if progress is None:
        return
    elapsed = monotonic() - started
    remaining = (
        0.0
        if completed == total or completed == 0
        else elapsed * (total - completed) / completed
    )
    progress(_canonical_text({
        "completed": completed,
        "elapsed_seconds": round(elapsed, 6),
        "estimated_remaining_seconds": round(remaining, 6),
        "pair_id": pair_id,
        "stage": stage,
        "total": total,
    }))


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _canonical_bytes(value: object) -> bytes:
    return (_canonical_text(value) + "\n").encode()


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


__all__ = [
    "audit_astar_pair_items_release",
    "audit_frozen_astar_pair",
    "audit_frozen_astar_pair_release",
    "select_astar_teacher_snapshots",
]
