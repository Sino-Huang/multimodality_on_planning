"""Frozen membership, views and validation for expanded successor prediction."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .expanded_successor import (
    project_successor_example,
    replay_source_path,
    select_transition_records,
    successor_contract,
)
from .modality_corpus import MODALITIES, ModalityCorpus, project_record
from .modality_corpus_replay import canonical
from .modality_pages import fact_blocks
from .modality_view_preparation import frozen_processor, validate_process_state, write_json
from .pddl_state import PDDLStateAuthority
from .scene_assets import load_scene_task, read_json
from .scene_only_preparation import check_task
from .scene_only_views import RECIPE_ID, SceneOnlyViews, materialize_task


def membership_id(record_ids: list[str]) -> str:
    return "sha256:" + hashlib.sha256(canonical(record_ids).encode()).hexdigest()


def source_path(root: Path, record: dict[str, Any]) -> list[dict[str, Any]]:
    """Recover the complete retained producing path for one source-state view."""

    manifest = read_json(root / record["view_manifest"])
    catalog = read_json(root / manifest["scene_catalog"])
    state = catalog["states"][record["state"]]
    actions = []
    while state["parent"] is not None:
        parent = state["parent"]
        match = re.fullmatch(r"\(([^\s()]+)(?:\s+([^()]*))?\)", parent["action"])
        if match is None:
            raise ValueError("successor source path contains a malformed retained action")
        actions.append(
            {
                "name": match.group(1),
                "args": [] if not match.group(2) else match.group(2).split(),
            }
        )
        state = catalog["states"][parent["state"]]
    return list(reversed(actions))


def validate_protocol(root: Path, protocol: dict[str, Any], *, require_frozen: bool = True) -> dict[str, Any]:
    study = read_json(root / protocol["source_study"])
    readiness = read_json(root / protocol["readiness"])
    membership = read_json(root / protocol["source_membership"])
    schedule = read_json(root / protocol["schedule"])
    checkpoints = {
        row["modality"]: row["checkpoint"] for row in readiness["checkpoints"] if row["algorithm"] == "bfs"
    }
    frozen = protocol.get("status") == "frozen_before_collection_and_training" and bool(
        protocol.get("goal7_runner_commit")
    )
    if (
        protocol.get("schema_version") != "expanded_successor_protocol_v1"
        or protocol.get("protocol_id") != "expanded-successor-v1"
        or protocol.get("algorithm") != "bfs"
        or protocol.get("modalities") != list(MODALITIES)
        or study.get("study_id") != "matched-modalities-v5"
        or protocol["model"]["id"] != study["model_id"]
        or protocol["model"]["revision"] != study["model_revision"]
        or protocol.get("starting_checkpoints") != checkpoints
        or len(protocol.get("source_record_ids", [])) != 512
        or len(set(protocol["source_record_ids"])) != 512
        or protocol["selection"]["records"] != 512
        or protocol["selection"]["allowed_split"] != "train"
        or protocol["selection"]["task_count"] != 25
        or protocol["model"]["output_tokens"] != 512
        or protocol["model"]["maximum_input_tokens"] + protocol["model"]["output_tokens"]
        != protocol["model"]["context_tokens"]
        or protocol["training"]["records_per_modality"] != 512
        or protocol["training"]["optimizer_updates"] != 16
        or protocol["training"]["seed"] != 17
        or schedule["allocations_gpu_hours"]["successor_prediction"] != protocol["budget"]["gpu_hours"] != 64
        or protocol["launch"]["master_port_pool"] != schedule["master_port_pool"]
        or protocol["launch"]["qualification_worker_modalities"]
        != {"0": ["text-state", "multimodal-state"], "1": ["visual-state"]}
        or (require_frozen and not frozen)
    ):
        raise ValueError("expanded successor protocol differs from its frozen contracts")

    corpus = ModalityCorpus(root, root / study["corpus_report"])
    all_records = list(corpus.records(algorithm="bfs", split="train"))
    selected = select_transition_records(
        all_records,
        membership["training_record_ids"]["bfs"],
        protocol["selection"]["task_order"],
    )
    if [row["record_id"] for row in selected] != protocol["source_record_ids"]:
        raise ValueError("successor membership differs from deterministic selection")
    metadata = {row["task_id"]: row for row in read_json(root / study["corpus_report"])["results"]}
    for row in selected:
        task = metadata[row["task_id"]]
        row["trace_paths"] = task["source_trace_paths"]
        row["reference_costs"] = task["reference_costs"]
    contracts = [successor_contract(row) for row in selected]
    authorities = {}
    for row, contract in zip(selected, contracts, strict=True):
        task_id = row["task_id"]
        if task_id not in authorities:
            domain, problem, _traces = load_scene_task(root, row)
            authorities[task_id] = PDDLStateAuthority.from_pddl(domain, problem)
        path = source_path(root, row)
        expected = contract["source_state"]
        actual = replay_source_path(authorities[task_id], path)
        if list(actual.atoms) != expected["atoms"] or list(actual.fluents) != expected.get("fluents", []):
            raise ValueError("successor source path differs from its retained source state")
        contract["source_path"] = path
    tokenizer = frozen_processor().processor.tokenizer
    target_lengths = [
        len(tokenizer(canonical(contract["target"]), add_special_tokens=False)["input_ids"])
        for contract in contracts
    ]
    declared = protocol["model"]["measured_target_tokens"]
    ordered = sorted(target_lengths)
    measured = {
        "records": 512,
        "minimum": min(ordered),
        "maximum": max(ordered),
        "safety_factor": 1.25,
        "allowance_rule": "ceil(measured maximum x 1.25) to the next 64-token boundary",
        "median": ordered[255],
        "p90": ordered[459],
        "p95": ordered[485],
        "p99": ordered[505],
    }
    allowance = math.ceil((max(ordered) * declared["safety_factor"]) / 64) * 64
    if declared != measured or allowance != protocol["model"]["output_tokens"]:
        raise ValueError("successor target measurements or output allowance differ")
    return {
        "study": study,
        "readiness": readiness,
        "membership": membership,
        "corpus": corpus,
        "records": selected,
        "contracts": contracts,
        "target_lengths": target_lengths,
        "membership_id": membership_id(protocol["source_record_ids"]),
    }


def load_views(root: Path, protocol: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], SceneOnlyViews]:
    report = read_json(root / protocol["views"]["successor_scene_report"])
    if (
        report.get("outcome") != "PASS"
        or not report.get("model_input_ready")
        or not report.get("complete_selected_coverage")
        or report.get("protocol_id") != protocol["protocol_id"]
        or report.get("membership_id") != context["membership_id"]
        or set(report.get("measurements", {})) != set(protocol["source_record_ids"])
        or set(report.get("decision_bindings", {})) != set(protocol["source_record_ids"])
        or report.get("counts", {}).get("records") != 512
    ):
        raise ValueError("successor scene/input preparation is incomplete")
    return report, SceneOnlyViews(root, report["tasks"], report["measurements"], report["decision_bindings"])


def training_example(
    root: Path,
    protocol: dict[str, Any],
    context: dict[str, Any],
    views: SceneOnlyViews,
    index: int,
    modality: str,
    *,
    pixels: bool = True,
) -> dict[str, Any]:
    if modality not in protocol["modalities"]:
        raise ValueError("successor modality is outside the frozen protocol")
    record = context["records"][index]
    contract = context["contracts"][index]
    task = views.tasks[record["task_id"]]
    binding = views.decision_bindings[record["record_id"]]
    if any(binding[key] != record[key] for key in ("task_id", "state", "algorithm", "decision_index", "split")):
        raise ValueError("successor decision binding differs from the source record")
    manifest = read_json(root / task["source_manifest"])
    catalog = read_json(root / manifest["scene_catalog"])
    project_record(record, manifest, catalog, modality)
    state = catalog["states"][record["state"]]
    validate_process_state(record["authoritative_input"], "bfs", state)
    semantic = fact_blocks(catalog["task_context"], state, manifest["source"])
    example = views.observe(
        record["task_id"],
        record["state"],
        record["authoritative_input"],
        "bfs",
        semantic,
        modality,
        pixels=pixels,
    )
    if example["binding"]["input_pages"] != binding["input_pages"]:
        raise ValueError("successor model-facing pages differ from preparation")
    example["messages"].append({"role": "assistant", "content": canonical(record["target"])})
    return project_successor_example(example, contract)


def _materialize(args: tuple[Path, str, str, set[int], Path]) -> dict[str, Any]:
    root, task_id, source, states, output = args
    return materialize_task(root, task_id, source, states, output, lambda *unused, **fields: None)


def prepare_views(
    root: Path,
    protocol: dict[str, Any],
    context: dict[str, Any],
    progress,
    *,
    workers: int = 4,
    check: bool = False,
) -> dict[str, Any]:
    required: dict[str, dict[str, Any]] = {}
    for record in context["records"]:
        task = required.setdefault(record["task_id"], {"source": record["view_manifest"], "states": set()})
        if task["source"] != record["view_manifest"]:
            raise ValueError("successor task records use different source manifests")
        task["states"].add(record["state"])
    output = root / protocol["output_root"] / "preparation"
    report_path = root / protocol["views"]["successor_scene_report"]
    if check:
        retained = read_json(report_path)
        tasks = retained["tasks"]
    else:
        tasks = {}
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    _materialize,
                    (root, task_id, row["source"], row["states"], output / RECIPE_ID / task_id.replace("/", "__")),
                )
                for task_id, row in required.items()
            ]
            for future in as_completed(futures):
                task = future.result()
                tasks[task["task_id"]] = task
                progress("successor_views:materialize", completed=len(tasks), total=len(required))
    if set(tasks) != set(required):
        raise ValueError("successor scene task coverage differs")
    for task_id, task in tasks.items():
        check_task(root, task, required[task_id]["states"])

    views = SceneOnlyViews(root, tasks)
    processor = frozen_processor()
    measurements: dict[str, Any] = {}
    decision_bindings: dict[str, Any] = {}
    maxima = Counter()
    cross_checked: set[str] = set()
    for index, (record, contract) in enumerate(zip(context["records"], context["contracts"], strict=True)):
        task = tasks[record["task_id"]]
        manifest = read_json(root / task["source_manifest"])
        catalog = read_json(root / manifest["scene_catalog"])
        project_record(record, manifest, catalog, "text-state")
        state = catalog["states"][record["state"]]
        semantic = fact_blocks(catalog["task_context"], state, manifest["source"])
        counts = {}
        page_bindings = None
        for modality in MODALITIES:
            example = views.observe(
                record["task_id"],
                record["state"],
                record["authoritative_input"],
                "bfs",
                semantic,
                modality,
                pixels=False,
            )
            example["messages"].append({"role": "assistant", "content": canonical(record["target"])})
            projected = project_successor_example(example, contract)
            prompt = projected["messages"][:-1]
            input_tokens = processor.count(prompt, image_sizes=projected["image_sizes"])
            full_tokens = processor.count(projected["messages"], image_sizes=projected["image_sizes"])
            if input_tokens > protocol["model"]["maximum_input_tokens"] or full_tokens > protocol["model"][
                "context_tokens"
            ]:
                raise RuntimeError("VALID_STOP: successor supervised example exceeds the frozen context")
            counts[modality] = {"input": input_tokens, "supervised": full_tokens}
            maxima[f"{modality}_input"] = max(maxima[f"{modality}_input"], input_tokens)
            maxima[f"{modality}_supervised"] = max(maxima[f"{modality}_supervised"], full_tokens)
            page_bindings = example["binding"]["input_pages"]
            if modality not in cross_checked:
                actual = views.observe(
                    record["task_id"],
                    record["state"],
                    record["authoritative_input"],
                    "bfs",
                    semantic,
                    modality,
                )
                actual["messages"].append({"role": "assistant", "content": canonical(record["target"])})
                actual = project_successor_example(actual, contract)
                processor.verify_complete(actual["messages"], actual["images"])
                for image in actual["images"]:
                    image.close()
                cross_checked.add(modality)
        measurements[record["record_id"]] = {
            "tokens": counts,
            "target": context["target_lengths"][index],
        }
        decision_bindings[record["record_id"]] = {
            key: record[key] for key in ("task_id", "state", "algorithm", "decision_index", "split")
        }
        decision_bindings[record["record_id"]]["input_pages"] = page_bindings
        progress("successor_views:measure", completed=index + 1, total=512)
    result = {
        "schema_version": "expanded_successor_views_v1",
        "protocol_id": protocol["protocol_id"],
        "membership_id": context["membership_id"],
        "outcome": "PASS",
        "complete_selected_coverage": True,
        "model_input_ready": True,
        "tasks": tasks,
        "measurements": measurements,
        "decision_bindings": decision_bindings,
        "processor_cross_checks": sorted(cross_checked),
        "max_tokens": dict(maxima),
        "counts": {
            "records": 512,
            "tasks": len(tasks),
            "states": sum(len(task["scenes"]) for task in tasks.values()),
        },
    }
    if check:
        if result != retained:
            raise ValueError("successor view/input replay differs from retained preparation")
    else:
        write_json(report_path, result)
    progress("successor_views:complete", completed=512, total=512, outcome="PASS")
    return result
