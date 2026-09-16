"""Resumable collection and immutable release of expanded successor records."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .expanded_successor import prediction_record, replay_prediction_record
from .expanded_successor_protocol import training_example
from .modality_corpus_replay import canonical
from .pddl_state import PDDLStateAuthority
from .scene_assets import load_scene_task, read_json

CELL_SCHEMA = "expanded_successor_collection_cell_v1"
INTERACTION_SCHEMA = "expanded_successor_interaction_v1"
JOURNAL_SCHEMA = "expanded_successor_batch_journal_v1"
LABEL_SCHEMA = "expanded_successor_training_label_v1"
RELEASE_SCHEMA = "expanded_successor_release_v1"
RELEASE_ID = "release-001"


def _json_bytes(value: Any) -> bytes:
    return canonical(value).encode()


def _gzip_bytes(value: Any) -> bytes:
    return gzip.compress(_json_bytes(value), compresslevel=9, mtime=0)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_exact(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"retained successor artifact differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(data)
    temporary.replace(path)


def _write_json(path: Path, value: Any) -> None:
    _write_exact(path, json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")


def _write_gzip(path: Path, value: Any) -> None:
    _write_exact(path, _gzip_bytes(value))


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def cell_root(root: Path, protocol: Mapping[str, Any], modality: str) -> Path:
    return root / protocol["output_root"] / "collection" / modality


def cell_report_path(root: Path, protocol: Mapping[str, Any], modality: str) -> Path:
    return cell_root(root, protocol, modality) / "collection.json"


def record_path(root: Path, protocol: Mapping[str, Any], modality: str, index: int) -> Path:
    return cell_root(root, protocol, modality) / "records" / f"{index:06d}.json.gz"


def _authority(root: Path, row: Mapping[str, Any]) -> PDDLStateAuthority:
    domain, problem, _traces = load_scene_task(root, dict(row))
    return PDDLStateAuthority.from_pddl(domain, problem)


def _close(example: Mapping[str, Any]) -> None:
    for image in example["images"]:
        close = getattr(image, "close", None)
        if close is not None:
            close()


def build_interaction(
    authority: PDDLStateAuthority,
    contract: Mapping[str, Any],
    raw_prediction: str,
    *,
    modality: str,
    view: Mapping[str, Any],
    collection_index: int,
    measurement: Mapping[str, Any],
    trajectory_links: Mapping[str, Any],
    runtime_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one raw output to its trusted transition without applying a wrong state."""

    retained = prediction_record(
        authority,
        contract,
        raw_prediction,
        modality=modality,
        view=view,
        source_path=contract["source_path"],
    )
    verification = retained["verification"]
    return {
        **retained,
        "interaction_schema_version": INTERACTION_SCHEMA,
        "interaction_id": f"{modality}:{collection_index:06d}:{contract['record_id']}",
        "collection_index": collection_index,
        "measurement": copy.deepcopy(dict(measurement)),
        "trajectory_links": copy.deepcopy(dict(trajectory_links)),
        "outcomes": {
            "operational": {"status": "model_output_returned", "failure": None},
            "structural": {
                "status": verification["status"],
                "failure_kind": verification["failure_kind"],
            },
        },
        "runtime_provenance": copy.deepcopy(dict(runtime_provenance)),
    }


def training_label(interaction: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize the trusted label separately from the retained prediction."""

    return {
        "schema_version": LABEL_SCHEMA,
        "record_id": interaction["record_id"],
        "task_id": interaction["task_id"],
        "split": interaction["split"],
        "modality": interaction["modality"],
        "collection_index": interaction["collection_index"],
        "model_input": copy.deepcopy(interaction["model_input"]),
        "view": copy.deepcopy(interaction["view"]),
        "query": copy.deepcopy(interaction["query"]),
        "source_state": copy.deepcopy(interaction["source_state"]),
        "source_path": copy.deepcopy(interaction["source_path"]),
        "target": copy.deepcopy(interaction["trusted_target"]),
    }


def _expected_view(example: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "binding": copy.deepcopy(example["binding"]),
        "view_manifest": contract["view_manifest"],
        "state": contract["state"],
        "input_pages": copy.deepcopy(contract["input_pages"]),
    }


def _record_paths(root: Path, protocol: Mapping[str, Any], modality: str) -> list[Path]:
    count = protocol["collection"]["records_per_modality"]
    return [record_path(root, protocol, modality, index) for index in range(count)]


def _commit_journal(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    views: Any,
    modality: str,
    journal: Mapping[str, Any],
    authorities: dict[str, PDDLStateAuthority],
) -> None:
    if (
        journal.get("schema_version") != JOURNAL_SCHEMA
        or journal.get("protocol_id") != protocol["protocol_id"]
        or journal.get("modality") != modality
        or len(journal.get("indices", [])) != len(journal.get("raw_predictions", []))
        or len(journal["indices"]) != len(journal.get("input_tokens", []))
    ):
        raise ValueError("successor pending batch journal differs from the collection contract")
    for position, (index, raw_prediction, input_tokens) in enumerate(
        zip(journal["indices"], journal["raw_predictions"], journal["input_tokens"], strict=True)
    ):
        row = context["records"][index]
        contract = context["contracts"][index]
        if contract["record_id"] != protocol["source_record_ids"][index]:
            raise ValueError("successor journal index differs from frozen membership")
        example = training_example(root, dict(protocol), dict(context), views, index, modality, pixels=False)
        try:
            expected_input = example["binding"]["input_tokens"]
            if input_tokens != expected_input:
                raise ValueError("successor model-call input accounting differs from the live example")
            if row["task_id"] not in authorities:
                authorities[row["task_id"]] = _authority(root, row)
            authority = authorities[row["task_id"]]
            measurement = {
                "model_call_id": journal["model_call_id"],
                "batch_position": position,
                "batch_size": len(journal["indices"]),
                "input_tokens": input_tokens,
                "generated_sequence_tokens": journal["generated_sequence_tokens"],
            }
            trajectory = {
                "source_record_id": contract["source_record_id"],
                "source_path": copy.deepcopy(contract["source_path"]),
                "view_manifest": contract["view_manifest"],
                "state": contract["state"],
                "decision_index": row["decision_index"],
                "source_trace_paths": copy.deepcopy(row["trace_paths"]),
            }
            interaction = build_interaction(
                authority,
                contract,
                raw_prediction,
                modality=modality,
                view=_expected_view(example, contract),
                collection_index=index,
                measurement=measurement,
                trajectory_links=trajectory,
                runtime_provenance=journal["runtime_provenance"],
            )
            _write_gzip(record_path(root, protocol, modality, index), interaction)
        finally:
            _close(example)


def collect_cell(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    views: Any,
    *,
    modality: str,
    generate: Callable[[Sequence[dict[str, Any]]], tuple[list[str], Mapping[str, Any]]],
    progress: Callable[..., None],
    runtime_provenance: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Collect a fixed cell in batches of two with a persisted output journal."""

    report_path = cell_report_path(root, protocol, modality)
    if report_path.exists():
        return verify_cell(root, protocol, context, views, modality=modality), True
    paths = _record_paths(root, protocol, modality)
    present = [path.exists() for path in paths]
    completed = next((index for index, exists in enumerate(present) if not exists), len(paths))
    if any(present[completed:]):
        raise ValueError("successor retained records are not a contiguous frozen prefix")
    base = cell_root(root, protocol, modality)
    journal_path = base / "pending-batch.json.gz"
    authorities: dict[str, PDDLStateAuthority] = {}
    if journal_path.exists():
        journal = read_json(journal_path)
        indices = journal.get("indices", [])
        if (
            not indices
            or indices != list(range(indices[0], min(indices[0] + 2, len(paths))))
            or not indices[0] <= completed <= indices[-1] + 1
        ):
            raise ValueError("successor pending batch does not overlap the retained prefix boundary")
        _commit_journal(root, protocol, context, views, modality, journal, authorities)
        journal_path.unlink()
        completed = indices[-1] + 1
        progress(completed=completed, total=len(paths), record_id=protocol["source_record_ids"][completed - 1])
    while completed < len(paths):
        indices = list(range(completed, min(completed + 2, len(paths))))
        examples = []
        try:
            for index in indices:
                example = training_example(root, dict(protocol), dict(context), views, index, modality)
                examples.append({**example, "messages": example["messages"][:-1]})
            raw_predictions, usage = generate(examples)
            if len(raw_predictions) != len(indices) or usage.get("batch_size") != len(indices):
                raise ValueError("successor generator returned incomplete batch output")
            input_tokens = usage.get("input_tokens")
            generated = usage.get("generated_sequence_tokens")
            if (
                not isinstance(input_tokens, list)
                or len(input_tokens) != len(indices)
                or not isinstance(generated, int)
                or generated <= 0
                or generated > protocol["model"]["output_tokens"]
            ):
                raise ValueError("successor generator usage differs from frozen allowances")
            journal = {
                "schema_version": JOURNAL_SCHEMA,
                "protocol_id": protocol["protocol_id"],
                "modality": modality,
                "indices": indices,
                "model_call_id": f"{modality}:batch-{indices[0] // 2:06d}",
                "raw_predictions": raw_predictions,
                "input_tokens": input_tokens,
                "generated_sequence_tokens": generated,
                "runtime_provenance": copy.deepcopy(dict(runtime_provenance)),
            }
            _write_gzip(journal_path, journal)
        finally:
            for example in examples:
                _close(example)
        _commit_journal(root, protocol, context, views, modality, journal, authorities)
        journal_path.unlink()
        completed += len(journal["indices"])
        progress(completed=completed, total=len(paths), record_id=protocol["source_record_ids"][completed - 1])
    report = _verify_records(root, protocol, context, views, modality)
    _write_json(report_path, report)
    return report, False


def _verify_records(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    views: Any,
    modality: str,
) -> dict[str, Any]:
    authorities: dict[str, PDDLStateAuthority] = {}
    interactions = []
    failure_kinds: Counter[str] = Counter()
    paths = _record_paths(root, protocol, modality)
    if not all(path.exists() for path in paths):
        raise ValueError("successor cell is missing frozen records")
    for index, path in enumerate(paths):
        interaction = read_json(path)
        row = context["records"][index]
        contract = context["contracts"][index]
        example = training_example(root, dict(protocol), dict(context), views, index, modality, pixels=False)
        try:
            expected_view = _expected_view(example, contract)
            measurement = interaction.get("measurement", {})
            provenance = interaction.get("runtime_provenance", {})
            model_identity = provenance.get("model_identity", {})
            if (
                interaction.get("interaction_schema_version") != INTERACTION_SCHEMA
                or interaction.get("interaction_id") != f"{modality}:{index:06d}:{contract['record_id']}"
                or interaction.get("collection_index") != index
                or interaction.get("record_id") != protocol["source_record_ids"][index]
                or interaction.get("task_id") != row["task_id"]
                or interaction.get("split") != "train"
                or interaction.get("modality") != modality
                or interaction.get("model_input") != contract["model_input"]
                or interaction.get("query") != contract["query"]
                or interaction.get("trusted_target") != contract["target"]
                or interaction.get("source_path") != contract["source_path"]
                or interaction.get("view") != expected_view
                or measurement.get("model_call_id") != f"{modality}:batch-{index // 2:06d}"
                or measurement.get("batch_position") != index % 2
                or measurement.get("batch_size") != min(2, len(paths) - index + index % 2)
                or measurement.get("input_tokens") != example["binding"]["input_tokens"]
                or not 0 < measurement.get("generated_sequence_tokens", 0) <= protocol["model"]["output_tokens"]
                or provenance.get("checkpoint") != protocol["starting_checkpoints"][modality]
                or provenance.get("master_port") not in protocol["launch"]["master_port_pool"]
                or not provenance.get("runtime_head")
                or model_identity.get("model_id") != protocol["model"].get("id")
                or model_identity.get("revision") != protocol["model"].get("revision")
                or model_identity.get("max_context_tokens") != protocol["model"].get("context_tokens")
                or model_identity.get("max_new_tokens") != protocol["model"].get("output_tokens")
                or model_identity.get("max_batch_size") != 2
                or model_identity.get("max_batch_input_tokens") != 24000
                or model_identity.get("memoize_identical_inputs") is not False
            ):
                raise ValueError("successor interaction identity, input, accounting or provenance differs")
            expected_links = {
                "source_record_id": contract["source_record_id"],
                "source_path": contract["source_path"],
                "view_manifest": contract["view_manifest"],
                "state": contract["state"],
                "decision_index": row["decision_index"],
                "source_trace_paths": row["trace_paths"],
            }
            if interaction.get("trajectory_links") != expected_links:
                raise ValueError("successor interaction trajectory links differ")
            if row["task_id"] not in authorities:
                authorities[row["task_id"]] = _authority(root, row)
            authority = authorities[row["task_id"]]
            verification = replay_prediction_record(authority, interaction)
            expected_outcomes = {
                "operational": {"status": "model_output_returned", "failure": None},
                "structural": {
                    "status": verification["status"],
                    "failure_kind": verification["failure_kind"],
                },
            }
            if interaction.get("outcomes") != expected_outcomes:
                raise ValueError("successor operational or structural outcome differs")
            failure_kinds[verification["failure_kind"] or "accepted"] += 1
            interactions.append(interaction)
        finally:
            _close(example)
    return {
        "schema_version": CELL_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "modality": modality,
        "records": len(interactions),
        "tasks": len({record["task_id"] for record in interactions}),
        "membership_id": context["membership_id"],
        "record_paths": [_relative(path, root) for path in paths],
        "record_file_sha256": [_sha256(path.read_bytes()) for path in paths],
        "verification_outcomes": dict(sorted(failure_kinds.items())),
        "raw_predictions_retained": len(interactions),
        "trusted_targets_retained_separately": len(interactions),
        "training_updates": 0,
    }


def verify_cell(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    views: Any,
    *,
    modality: str,
) -> dict[str, Any]:
    actual = _verify_records(root, protocol, context, views, modality)
    retained = read_json(cell_report_path(root, protocol, modality))
    if retained != actual:
        raise ValueError("successor collection cell differs from independent replay")
    return actual


def _release_payloads(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    modalities: Sequence[str],
) -> dict[str, dict[str, Any]]:
    payloads = {}
    for modality in modalities:
        interactions = [read_json(path) for path in _record_paths(root, protocol, modality)]
        labels = [training_label(record) for record in interactions]
        inputs: dict[str, str] = {}
        for label in labels:
            identity = canonical({"model_input": label["model_input"], "view": label["view"]})
            target = canonical(label["target"])
            if identity in inputs and inputs[identity] != target:
                raise ValueError("successor release contains conflicting identical training inputs")
            inputs[identity] = target
        payloads[modality] = {
            "interactions": {
                "schema_version": "expanded_successor_interaction_set_v1",
                "protocol_id": protocol["protocol_id"],
                "release_id": RELEASE_ID,
                "modality": modality,
                "membership_id": context["membership_id"],
                "records": interactions,
            },
            "labels": {
                "schema_version": "expanded_successor_training_set_v1",
                "protocol_id": protocol["protocol_id"],
                "release_id": RELEASE_ID,
                "modality": modality,
                "membership_id": context["membership_id"],
                "records": labels,
            },
        }
    return payloads


def release_root(root: Path, protocol: Mapping[str, Any]) -> Path:
    return root / protocol["output_root"] / "dataset" / RELEASE_ID


def publish_release(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    views: Any,
) -> dict[str, Any]:
    """Publish release-001 once all cells independently replay."""

    cells = {
        modality: verify_cell(root, protocol, context, views, modality=modality)
        for modality in protocol["modalities"]
    }
    payloads = _release_payloads(root, protocol, context, protocol["modalities"])
    output = release_root(root, protocol)
    artifacts = {}
    for modality, grouped in payloads.items():
        modality_artifacts = {}
        for name, payload in grouped.items():
            path = output / modality / f"{name}.json.gz"
            data = _gzip_bytes(payload)
            _write_exact(path, data)
            modality_artifacts[name] = {
                "path": _relative(path, root),
                "sha256": _sha256(data),
                "records": len(payload["records"]),
            }
        artifacts[modality] = modality_artifacts
    report = {
        "schema_version": RELEASE_SCHEMA,
        "outcome": "PASS",
        "release_id": RELEASE_ID,
        "protocol_id": protocol["protocol_id"],
        "membership_id": context["membership_id"],
        "source_split": "train",
        "modalities": list(protocol["modalities"]),
        "records_per_modality": protocol["collection"]["records_per_modality"],
        "total_interactions": len(protocol["modalities"]) * protocol["collection"]["records_per_modality"],
        "training_labels_separate_from_predictions": True,
        "raw_predictions_unmodified": True,
        "trusted_state_substitutions": 0,
        "whole_instance_split_isolation": True,
        "byte_identical_regeneration_verified": True,
        "historical_releases_overwritten": False,
        "cells": cells,
        "artifacts": artifacts,
    }
    _write_json(output / "report.json", report)
    return report


def verify_release(
    root: Path,
    protocol: Mapping[str, Any],
    context: Mapping[str, Any],
    views: Any,
) -> dict[str, Any]:
    output = release_root(root, protocol)
    retained = read_json(output / "report.json")
    cells = {
        modality: verify_cell(root, protocol, context, views, modality=modality)
        for modality in protocol["modalities"]
    }
    payloads = _release_payloads(root, protocol, context, protocol["modalities"])
    artifacts = {}
    for modality, grouped in payloads.items():
        artifacts[modality] = {}
        for name, payload in grouped.items():
            path = output / modality / f"{name}.json.gz"
            expected = _gzip_bytes(payload)
            if not path.exists() or path.read_bytes() != expected:
                raise ValueError("successor release does not regenerate byte-identically")
            artifacts[modality][name] = {
                "path": _relative(path, root),
                "sha256": _sha256(expected),
                "records": len(payload["records"]),
            }
    expected_report = {
        "schema_version": RELEASE_SCHEMA,
        "outcome": "PASS",
        "release_id": RELEASE_ID,
        "protocol_id": protocol["protocol_id"],
        "membership_id": context["membership_id"],
        "source_split": "train",
        "modalities": list(protocol["modalities"]),
        "records_per_modality": protocol["collection"]["records_per_modality"],
        "total_interactions": len(protocol["modalities"]) * protocol["collection"]["records_per_modality"],
        "training_labels_separate_from_predictions": True,
        "raw_predictions_unmodified": True,
        "trusted_state_substitutions": 0,
        "whole_instance_split_isolation": True,
        "byte_identical_regeneration_verified": True,
        "historical_releases_overwritten": False,
        "cells": cells,
        "artifacts": artifacts,
    }
    if retained != expected_report:
        raise ValueError("successor release report differs from independent reconstruction")
    return retained
