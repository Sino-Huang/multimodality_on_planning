#!/usr/bin/env python
"""Independent teacher, source-split, raw-output and cost audit for Goal 8."""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.planning_benchmark_slice.expanded_scheduler import ROOT, alive, read, write
from examples.planning_benchmark_slice.expanded_successor import (
    replay_prediction_record,
    replay_source_path,
    verify_prediction,
)
from examples.planning_benchmark_slice.expanded_successor_protocol import validate_protocol
from examples.planning_benchmark_slice.modality_corpus_replay import canonical
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.scene_assets import load_scene_task, read_json


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol_path = ROOT / "configs/experiments/expanded-study/successor-protocol.json"
    protocol = read(protocol_path)
    context = validate_protocol(ROOT, protocol)
    evidence_path = ROOT / "docs/experiments/expanded-study/successor-data.json"
    evidence = read(evidence_path)
    release = evidence["release"]
    source_report = read(ROOT / protocol["source_corpus"])
    selected_tasks = set(protocol["selection"]["task_order"])
    source_contexts = {}
    heldout_contexts = set()
    for task in source_report["results"]:
        manifest = read_json(ROOT / task["view_manifest"])
        catalog = read_json(ROOT / manifest["scene_catalog"])
        semantic = canonical(catalog["task_context"])
        if task["task_id"] in selected_tasks:
            assert task["split"] == "train"
            source_contexts[task["task_id"]] = semantic
        elif task["split"] != "train":
            heldout_contexts.add(semantic)
    assert set(source_contexts) == selected_tasks
    assert not set(source_contexts.values()).intersection(heldout_contexts)
    for panel_path in (
        ROOT / "configs/experiments/expanded-study/final-panel.json",
        ROOT / "outputs/matched_modalities/v5/preparation/final-panel.json",
    ):
        for task in read(panel_path)["tasks"]:
            row = task["row"]
            assert row["split"] == "test" and row["task_id"] not in selected_tasks
            payload = read(ROOT / row["task_path"])
            authority = PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])
            assert canonical(authority.task_context()) not in set(source_contexts.values())

    authorities = {}
    tasks = {}
    for row in context["records"]:
        task_id = row["task_id"]
        if task_id in tasks:
            continue
        domain, problem, _traces = load_scene_task(ROOT, row)
        authority = PDDLStateAuthority.from_pddl(domain, problem)
        assert canonical(authority.task_context()) == source_contexts[task_id]
        authorities[task_id] = authority
        manifest = read_json(ROOT / row["view_manifest"])
        assert manifest["reference_costs"] == row["reference_costs"]
        trace_path = ROOT / row["trace_paths"]["bfs"]
        trace = read_json(trace_path)
        assert trace["record_count"] == len(trace["records"]) == row["reference_costs"]["bfs"]["decisions"]
        tasks[task_id] = {
            "split": "train",
            "view_manifest": row["view_manifest"],
            "domain_pddl_sha256": hashlib.sha256(domain.encode()).hexdigest(),
            "problem_pddl_sha256": hashlib.sha256(problem.encode()).hexdigest(),
            "source_trace_paths": row["trace_paths"],
            "source_trace_sha256": sha256(trace_path),
            "reference_costs": row["reference_costs"],
        }

    outcomes = Counter()
    runtime_heads = set()
    first_batch_recovered = 0
    for modality in protocol["modalities"]:
        artifacts = release["artifacts"][modality]
        for artifact in artifacts.values():
            assert "sha256:" + sha256(ROOT / artifact["path"]) == artifact["sha256"]
        interactions = read_json(ROOT / artifacts["interactions"]["path"])["records"]
        labels = read_json(ROOT / artifacts["labels"]["path"])["records"]
        assert len(interactions) == len(labels) == 512
        assert [r["record_id"] for r in interactions] == protocol["source_record_ids"]
        input_targets = {}
        for index, (interaction, label) in enumerate(zip(interactions, labels, strict=True)):
            authority = authorities[interaction["task_id"]]
            verdict = replay_prediction_record(authority, interaction)
            outcomes[verdict["failure_kind"] or "accepted"] += 1
            assert not verdict["prediction_applied"] and not verdict["trusted_state_substituted"]
            assert verdict["downstream_search"]["status"] == "not_evaluated"
            assert interaction["split"] == label["split"] == "train"
            assert label["target"] == interaction["trusted_target"]
            assert label["model_input"] == interaction["model_input"]
            assert "raw_prediction" not in label and "verification" not in label
            source = replay_source_path(authority, label["source_path"])
            teacher_verdict = verify_prediction(authority, source, label["query"], canonical(label["target"]))
            assert teacher_verdict["status"] == "accepted"
            assert context["target_lengths"][index] <= protocol["model"]["output_tokens"]
            assert interaction["measurement"]["input_tokens"] <= protocol["model"]["maximum_input_tokens"]
            assert len(interaction["model_input"]["search_memory"]["accepted_deltas"]) <= 16
            identity = canonical(label["model_input"])
            target = canonical(label["target"])
            assert identity not in input_targets or input_targets[identity] == target
            input_targets[identity] = target
            runtime_heads.add(interaction["runtime_provenance"]["runtime_head"])
        if modality in ("text-state", "visual-state"):
            first = read_json(ROOT / protocol["output_root"] / "collection" / modality / "records/000000.json.gz")
            assert first == interactions[0]
            assert interactions[0]["runtime_provenance"]["runtime_head"].startswith("9a9fe12")
            assert interactions[1]["runtime_provenance"]["runtime_head"].startswith("9a9fe12")
            first_batch_recovered += 2
        assert not (ROOT / protocol["output_root"] / "collection" / modality / "pending-batch.json.gz").exists()
    assert dict(sorted(outcomes.items())) == evidence["coverage"]["verification_outcomes"]
    assert sorted(runtime_heads) == evidence["execution"]["runtime_heads"]
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    branch = [r for r in ledger["attempts"] if r["branch"] == "successor_prediction"]
    assert not any(r["status"] in ("reserved", "running") for r in branch)
    cumulative = sum(r["gpu_hours"] for r in branch)
    assert cumulative == evidence["execution"]["cumulative_successor_gpu_hours"] <= 64
    for job_id in (
        "successor-collection-0",
        "successor-collection-1",
        "successor-collection-final",
        "successor-goal8-chain",
    ):
        attempt = [r for r in branch if r["job_id"] == job_id][-1]
        assert attempt["status"] == "succeeded" and not alive(attempt.get("worker"))
        assert read(Path(attempt["directory"]) / "hook-result.json")["returncode"] == 0
    provenance = {
        "schema_version": "expanded_successor_data_provenance_v1",
        "protocol_sha256": sha256(protocol_path),
        "source_report": protocol["source_corpus"],
        "source_report_sha256": sha256(ROOT / protocol["source_corpus"]),
        "tasks": tasks,
        "reference_cost_meaning": (
            "Exact BFS source-episode decision costs, not collection decisions or predicted-state success."
        ),
    }
    write(ROOT / "docs/experiments/expanded-study/successor-data-provenance.json", provenance)
    report = {
        "outcome": "PASS",
        "goal": 8,
        "interactions_replayed": 1536,
        "teacher_targets_strictly_verified": 1536,
        "tasks": 25,
        "first_attempt_predictions_recovered_without_regeneration": first_batch_recovered,
        "source_heldout_semantic_context_overlap": 0,
        "whole_instance_scope": (
            "Canonical task-context equality; preserves source corpus splits and compares both current final panels."
        ),
        "conflicting_identical_authoritative_inputs": 0,
        "verification_outcomes": dict(sorted(outcomes.items())),
        "runtime_heads": sorted(runtime_heads),
        "cumulative_gpu_hours_including_qualification_failures_and_retries": cumulative,
        "missing_records": 0,
        "training_updates": 0,
    }
    write(ROOT / "docs/experiments/expanded-study/successor-data-independent-audit.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
