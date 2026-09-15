"""Frozen DAgger correction, replay, and aggregation boundaries for the expanded study."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .modality_corpus import ModalityCorpus
from .modality_corpus_replay import canonical
from .scene_assets import read_json
from .search_trace import _serialize_operation, _serialize_result
from .visual_bfs import BFSOutputValidation
from .visual_episode import VisualSession

CORRECTION_SCHEMA = "expanded_dagger_correction_v1"
DECISION_SCHEMA = "expanded_dagger_collection_decision_v1"
EPISODE_SCHEMA = "expanded_dagger_collection_episode_v1"
UPDATE_SCHEMA = "expanded_dagger_update_membership_v1"


@dataclass(slots=True)
class DaggerRequest:
    model_input: dict[str, Any]
    example: dict[str, Any]


def _validation_payload(validation: BFSOutputValidation) -> dict[str, Any]:
    parsed = (
        {"status": "rejected", "error": validation.parse_error}
        if validation.parse_error is not None
        else {"status": "accepted", "operation": _serialize_operation(validation.operation)}
    )
    runtime = (
        _serialize_result(validation.result)
        if validation.result is not None
        else {"status": "not_run", "reason": "strict_parse_failed"}
    )
    return {"strict_parse_result": parsed, "trusted_runtime_result": runtime}


def _memory_payload(session: VisualSession) -> dict[str, Any]:
    return json.loads(session.session.context.memory.to_bytes())


class DaggerBFSSession:
    """Apply accepted student operations or an expert correction from the same pending state."""

    def __init__(
        self,
        session: VisualSession,
        protocol: Mapping[str, Any],
        *,
        task_id: str,
        split: str,
        modality: str,
        iteration: int,
        starting_checkpoint: str,
        collection_offset: int = 0,
    ) -> None:
        if session.algorithm != "bfs" or split != "train":
            raise ValueError("DAgger collection requires a BFS training-split session")
        if modality not in protocol["modalities"] or iteration not in protocol["iterations"]:
            raise ValueError("DAgger collection cell is outside the frozen protocol")
        if task_id not in protocol["collection"]["task_order"]:
            raise ValueError("DAgger collection task is outside the frozen training membership")
        if starting_checkpoint != collection_checkpoint(protocol, modality, iteration):
            raise ValueError("DAgger collection checkpoint differs from its iteration lineage")
        self.session = session
        self.protocol = dict(protocol)
        self.task_id = task_id
        self.split = split
        self.modality = modality
        self.iteration = iteration
        self.starting_checkpoint = starting_checkpoint
        self.collection_offset = collection_offset
        self.decisions: list[dict[str, Any]] = []
        self._pending: DaggerRequest | None = None
        self.stopped_without_correction = False

    def next_request(self, views=None, *, pixels: bool = True) -> DaggerRequest | None:
        if self._pending is not None:
            return self._pending
        if self.stopped_without_correction:
            return None
        request = self.session.next_request()
        if request is None:
            return None
        raw = dict(request.model_input)
        example = (
            views.observe(raw, "bfs", modality=self.modality, pixels=pixels)
            if views is not None
            else {"messages": [], "images": [], "binding": None}
        )
        self._pending = DaggerRequest(raw, example)
        return self._pending

    def submit_student(self, raw_output: str, *, allow_expert: bool = True) -> dict[str, Any]:
        request = self._pending
        if request is None:
            raise ValueError("DAgger submission requires an outstanding student request")
        if not isinstance(raw_output, str):
            raise TypeError("DAgger student output must be text")
        core = self.session.session
        before = core.context.memory.to_bytes()
        memory = json.loads(before)
        validation = core.validate_output(raw_output)
        if core.context.memory.to_bytes() != before:
            raise ValueError("DAgger validation mutated the last valid Search Memory")
        parsed = _validation_payload(validation)
        decision_index = self.collection_offset + len(self.decisions)
        invalid = not validation.accepted
        correction = None
        applied_source = None
        applied_event = None
        if validation.accepted:
            self.session.submit(raw_output, request.example["binding"])
            applied_source = "student"
            applied_event = self.session.events[-1]
        elif allow_expert:
            expert_output = self.session.reference_output()
            expert_validation = core.validate_output(expert_output)
            if not expert_validation.accepted or core.context.memory.to_bytes() != before:
                raise ValueError("observable BFS expert did not validate from the unchanged last-valid state")
            expert = _validation_payload(expert_validation)
            target = json.loads(expert_output)
            self.session.submit(expert_output, request.example["binding"])
            applied_source = "expert_correction"
            applied_event = self.session.events[-1]
            correction = {
                "schema_version": CORRECTION_SCHEMA,
                "correction_id": (
                    f"{self.protocol['protocol_id']}:{self.modality}:iteration-{self.iteration}:"
                    f"decision-{decision_index}"
                ),
                "protocol_id": self.protocol["protocol_id"],
                "algorithm": "bfs",
                "task_id": self.task_id,
                "split": self.split,
                "modality": self.modality,
                "iteration": self.iteration,
                "starting_checkpoint": self.starting_checkpoint,
                "collection_decision_index": decision_index,
                "last_valid_accepted_event_count": len(self.session.events) - 1,
                "last_valid_search_memory": memory,
                "student_input": request.model_input,
                "student_view": request.example["binding"],
                "student_raw_output": raw_output,
                **parsed,
                "invalid_operation_charge": 1,
                "expert_query_charge": 1,
                "expert_query": {
                    "model_input": request.model_input,
                    "view": request.example["binding"],
                    "raw_output": expert_output,
                    **expert,
                    "target": target,
                },
                "applied_rollout_event_index": len(self.session.events) - 1,
                "view_serializer": self.protocol["views"]["serializer"],
            }
        else:
            self.stopped_without_correction = True
        decision = {
            "schema_version": DECISION_SCHEMA,
            "collection_decision_index": decision_index,
            "student_input": request.model_input,
            "student_view": request.example["binding"],
            "student_raw_output": raw_output,
            **parsed,
            "invalid_operation_charge": int(invalid),
            "applied_operation_source": applied_source,
            "applied_rollout_event": applied_event,
            "correction": correction,
        }
        self.decisions.append(decision)
        self._pending = None
        return decision

    def finish(self, stop_reason: str) -> dict[str, Any]:
        if self._pending is not None:
            raise ValueError("cannot finish DAgger episode with an unsubmitted student output")
        allowed = {
            "session_complete",
            "collection_decision_quota",
            "correction_quota",
            "task_schedule_exhausted",
            "scheduler_cutoff",
        }
        if stop_reason not in allowed:
            raise ValueError("unknown DAgger collection stop reason")
        if stop_reason == "session_complete" and self.session.session.termination_reason is None:
            raise ValueError("session_complete requires a terminal trusted BFS session")
        corrections = sum(decision["correction"] is not None for decision in self.decisions)
        report = {
            "schema_version": EPISODE_SCHEMA,
            "protocol_id": self.protocol["protocol_id"],
            "algorithm": "bfs",
            "task_id": self.task_id,
            "split": self.split,
            "modality": self.modality,
            "iteration": self.iteration,
            "starting_checkpoint": self.starting_checkpoint,
            "collection_offset": self.collection_offset,
            "decisions": self.decisions,
            "result": {
                "stop_reason": stop_reason,
                "collection_decisions": len(self.decisions),
                "accepted_student_operations": sum(
                    decision["applied_operation_source"] == "student" for decision in self.decisions
                ),
                "invalid_student_operations": sum(
                    decision["invalid_operation_charge"] for decision in self.decisions
                ),
                "expert_queries": corrections,
                "corrections": corrections,
                "trusted_rollout_events": len(self.session.events),
                "trusted_session_termination_reason": self.session.session.termination_reason,
                "final_search_memory": _memory_payload(self.session),
            },
        }
        return report


def replay_dagger_episode(
    report: Mapping[str, Any], protocol: Mapping[str, Any], session: VisualSession, views=None
) -> dict[str, Any]:
    wrapper = DaggerBFSSession(
        session,
        protocol,
        task_id=report["task_id"],
        split=report["split"],
        modality=report["modality"],
        iteration=report["iteration"],
        starting_checkpoint=report["starting_checkpoint"],
        collection_offset=report["collection_offset"],
    )
    for expected in report["decisions"]:
        request = wrapper.next_request(views, pixels=False)
        if request is None or request.model_input != expected["student_input"]:
            raise ValueError("DAgger replay student input differs")
        if request.example["binding"] != expected["student_view"]:
            raise ValueError("DAgger replay view binding differs")
        actual = wrapper.submit_student(
            expected["student_raw_output"],
            allow_expert=expected["correction"] is not None,
        )
        if actual != expected:
            raise ValueError("DAgger replay decision or correction differs")
    replayed = wrapper.finish(report["result"]["stop_reason"])
    if replayed != report:
        raise ValueError("DAgger replay episode result differs")
    return replayed


def collection_checkpoint(protocol: Mapping[str, Any], modality: str, iteration: int) -> str:
    if iteration == 1:
        return protocol["starting_checkpoints"][modality]
    if iteration == 2:
        return protocol["checkpoint_lineage"]["dagger_iteration_1"].format(modality=modality)
    raise ValueError("DAgger iteration is not frozen")


def certify_corrections(
    corrections: Sequence[Mapping[str, Any]],
    protocol: Mapping[str, Any],
    *,
    modality: str,
    iteration: int,
    target_token_counter: Callable[[Mapping[str, Any]], int],
) -> list[dict[str, Any]]:
    if len(corrections) > protocol["collection"]["max_corrections_per_modality_iteration"]:
        raise ValueError("DAgger correction quota exceeded")
    seen_ids = set()
    targets_by_input: dict[str, str] = {}
    unique: list[dict[str, Any]] = []
    for raw in corrections:
        correction = dict(raw)
        if (
            correction.get("schema_version") != CORRECTION_SCHEMA
            or correction.get("protocol_id") != protocol["protocol_id"]
            or correction.get("algorithm") != "bfs"
            or correction.get("split") != "train"
            or correction.get("modality") != modality
            or correction.get("iteration") != iteration
            or correction.get("task_id") not in protocol["collection"]["task_order"]
            or correction.get("starting_checkpoint") != collection_checkpoint(protocol, modality, iteration)
            or correction.get("invalid_operation_charge") != 1
            or correction.get("expert_query_charge") != 1
            or correction.get("view_serializer") != protocol["views"]["serializer"]
        ):
            raise ValueError("DAgger correction provenance differs from the frozen cell")
        correction_id = correction["correction_id"]
        if correction_id in seen_ids:
            raise ValueError("duplicate DAgger correction ID")
        seen_ids.add(correction_id)
        expert = correction["expert_query"]
        if expert["model_input"] != correction["student_input"] or expert["view"] != correction["student_view"]:
            raise ValueError("DAgger expert query differs from the last-valid student observation")
        if correction["strict_parse_result"]["status"] == "accepted" and correction["trusted_runtime_result"][
            "status"
        ] != "rejected":
            raise ValueError("DAgger correction trigger was not a rejected student operation")
        if expert["strict_parse_result"]["status"] != "accepted" or expert["trusted_runtime_result"][
            "status"
        ] not in {"accepted", "retired"}:
            raise ValueError("DAgger expert target did not pass the trusted runtime")
        if canonical(expert["target"]) != expert["raw_output"]:
            raise ValueError("DAgger expert target differs from its raw canonical output")
        if target_token_counter(expert["target"]) > protocol["model"]["output_tokens"]:
            raise ValueError("DAgger correction target exceeds the frozen output allowance")
        input_key = canonical(correction["student_input"])
        target_key = canonical(expert["target"])
        prior = targets_by_input.get(input_key)
        if prior is not None and prior != target_key:
            raise ValueError("identical DAgger inputs have conflicting expert targets")
        if prior is None:
            targets_by_input[input_key] = target_key
            unique.append(correction)
    return unique


def aggregate_update(
    source_records: Sequence[Mapping[str, Any]],
    corrections: Sequence[Mapping[str, Any]],
    protocol: Mapping[str, Any],
    *,
    modality: str,
    through_iteration: int,
    arm: str,
    target_token_counter: Callable[[Mapping[str, Any]], int],
) -> dict[str, Any]:
    size = protocol["training"]["records_per_update"]
    if len(source_records) != size or [row["record_id"] for row in source_records] != protocol["source_record_ids"]:
        raise ValueError("DAgger aggregation source differs from the frozen BFS membership")
    if arm not in {"dagger", "continued_sft"} or through_iteration not in protocol["iterations"]:
        raise ValueError("DAgger update cell is outside the frozen protocol")
    selected_corrections: list[dict[str, Any]] = []
    if arm == "dagger":
        grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
        for correction in corrections:
            grouped[int(correction["iteration"])].append(correction)
        seen_inputs = set()
        for iteration in range(1, through_iteration + 1):
            certified = certify_corrections(
                grouped[iteration],
                protocol,
                modality=modality,
                iteration=iteration,
                target_token_counter=target_token_counter,
            )
            for correction in certified:
                key = canonical(correction["student_input"])
                if key not in seen_inputs:
                    seen_inputs.add(key)
                    selected_corrections.append(correction)
    if len(selected_corrections) > size:
        raise ValueError("DAgger cumulative corrections exceed the fixed update membership")
    original_count = size - len(selected_corrections)
    records = [
        {
            "schema_version": UPDATE_SCHEMA,
            "source_kind": "original_sft",
            "record_id": row["record_id"],
            "task_id": row["task_id"],
            "split": row["split"],
            "modality": modality,
            "input": row["authoritative_input"],
            "view": {
                "view_manifest": row["view_manifest"],
                "state": row["state"],
                "input_pages": row["input_pages"],
            },
            "target": row["target"],
        }
        for row in source_records[:original_count]
    ]
    records.extend(
        {
            "schema_version": UPDATE_SCHEMA,
            "source_kind": "dagger_correction",
            "record_id": correction["correction_id"],
            "task_id": correction["task_id"],
            "split": "train",
            "modality": modality,
            "input": correction["student_input"],
            "view": correction["student_view"],
            "target": correction["expert_query"]["target"],
        }
        for correction in selected_corrections
    )
    return {
        "schema_version": UPDATE_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "arm": arm,
        "modality": modality,
        "through_iteration": through_iteration,
        "records": records,
        "record_count": len(records),
        "original_sft_records": original_count,
        "unique_corrections": len(selected_corrections),
        "optimizer_updates": protocol["training"]["optimizer_updates"],
        "training_seed": protocol["training"]["seed"],
    }


def validate_protocol(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    study = read_json(root / protocol["source_study"])
    readiness = read_json(root / protocol["readiness"])
    membership = read_json(root / protocol["source_membership"])
    schedule = read_json(root / protocol["schedule"])
    source_ids = membership["training_record_ids"]["bfs"]
    checkpoints = {
        row["modality"]: row["checkpoint"] for row in readiness["checkpoints"] if row["algorithm"] == "bfs"
    }
    if (
        protocol["protocol_id"] != "expanded-dagger-v1"
        or protocol.get("goal5_runner_commit") != "f338b17589ce4454d255b68a4ef75b7eacedf772"
        or protocol["algorithm"] != "bfs"
        or protocol["modalities"] != ["text-state", "visual-state", "multimodal-state"]
        or protocol["iterations"] != [1, 2]
        or study["study_id"] != "matched-modalities-v5"
        or protocol["model"]["id"] != study["model_id"]
        or protocol["model"]["revision"] != study["model_revision"]
        or protocol["starting_checkpoints"] != checkpoints
        or protocol["source_record_ids"] != source_ids
        or len(source_ids) != 512
        or protocol["training"]["records_per_update"] != 512
        or protocol["training"]["optimizer_updates"] != 16
        or protocol["training"]["seed"] != 17
        or protocol["collection"]["max_decisions_per_modality_iteration"] != 512
        or protocol["collection"]["max_corrections_per_modality_iteration"] != 128
        or schedule["allocations_gpu_hours"]["dagger"] != protocol["budget"]["gpu_hours"] != 48
        or protocol["launch"]["master_port_pool"] != schedule["master_port_pool"]
        or protocol["launch"]["collection_worker_modalities"]
        != {"0": ["text-state", "multimodal-state"], "1": ["visual-state"]}
        or protocol["launch"]["collection_worker_max_seconds"] != {"0": 32400, "1": 18000}
    ):
        raise ValueError("expanded DAgger protocol differs from its inherited frozen contracts")
    corpus = ModalityCorpus(root, root / study["corpus_report"], scene_views=study["scene_views"])
    indexed = {row["record_id"]: row for row in corpus.records(algorithm="bfs", split="train")}
    corpus_report = read_json(root / study["corpus_report"])
    task_metadata = {row["task_id"]: row for row in corpus_report["results"]}
    source_records = []
    for record_id in source_ids:
        row = dict(indexed[record_id])
        metadata = task_metadata[row["task_id"]]
        if (
            metadata["split"] != "train"
            or metadata["view_manifest"] != row["view_manifest"]
            or metadata["source_trace_paths"]["bfs"] != row["source_trace_path"]
        ):
            raise ValueError("DAgger live task metadata differs from the frozen corpus record")
        row["trace_paths"] = metadata["source_trace_paths"]
        row["reference_costs"] = metadata["reference_costs"]
        source_records.append(row)
    task_order = []
    for row in source_records:
        if row["task_id"] not in task_order:
            task_order.append(row["task_id"])
    if task_order != protocol["collection"]["task_order"] or any(row["split"] != "train" for row in source_records):
        raise ValueError("DAgger collection order or source split differs from the frozen membership")
    return {
        "study": study,
        "readiness": readiness,
        "membership": membership,
        "corpus": corpus,
        "source_records": source_records,
    }
