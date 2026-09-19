from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.best_first_controller import (
    BEST_FIRST_SETTINGS,
    BestFirstController,
)
from examples.planning_benchmark_slice.best_first_corpus import (
    BestFirstCorpusContract,
    load_best_first_corpus_contract,
    materialize_best_first_corpus_trace,
    run_best_first_corpus_release,
)
from examples.planning_benchmark_slice.best_first_model_input import (
    build_compact_best_first_live_model_input,
    build_compact_best_first_teacher_model_input,
    expand_compact_best_first_facts,
    serialize_best_first_message_prefix,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority

ROOT = Path(__file__).resolve().parents[2]


class _FixtureTokenCounter:
    def input_tokens(self, model_input) -> int:
        return len(json.dumps(model_input, sort_keys=True)) // 4

    def target_tokens(self, target_text: str) -> int:
        return len(target_text) // 4


def _load_contract() -> BestFirstCorpusContract:
    return load_best_first_corpus_contract(
        ROOT / "configs/experiments/best-first-paired-corpus-design-v3.json",
        ROOT / "configs/experiments/best-first-paired-corpus-authorization-v3.json",
        repo_root=ROOT,
    )


def test_compact_trace_materializes_process_operational_and_training_views() -> None:
    contract = _load_contract()
    pair_id = "astar-pair-15205002a905be45f6de13ba"
    pair_item = next(item for item in contract.source_manifest["pairs"] if item["pair_id"] == pair_id)
    row = next(item for item in contract.source_phase.pairs if item["pair_id"] == pair_id)
    task = json.loads((contract.trace_root / "pairs" / pair_id / str(pair_item["task_path"])).read_bytes())
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])

    shard = materialize_best_first_corpus_trace(
        row=row,
        pair_item=pair_item,
        algorithm="best_first_add_w3",
        trace_root=contract.trace_root,
        corpus_config={
            "accepted_delta_limit": contract.design["accepted_delta_limit"],
            "model_input_token_limit": contract.design["tokenizer"]["model_input_token_limit"],
            "model_output_token_limit": contract.design["tokenizer"]["model_output_token_limit"],
            "row_identity_binding": contract.design["row_identity_binding"],
        },
        token_counter=_FixtureTokenCounter(),
    )

    assert len(shard.process_rows) == pair_item["traces"]["best_first_add_w3"]["decision_count"] == 8
    assert len(shard.operational_rows) == len(shard.process_rows)
    assert len(shard.training_rows) == len(shard.process_rows)
    assert shard.audit["live_training_input_mismatch_count"] == 0
    assert shard.audit["target_parse_rejection_count"] == 0
    assert shard.audit["teacher_decision_rejection_count"] == 0
    assert shard.semantic_task_identity == authority.semantic_task_identity()

    process = shard.process_rows[0]
    assert process["algorithm"] == "best_first_add_w3"
    assert process["view"] == "process"
    assert set(process["target"]) == {"action", "source_state_id"}
    assert process["expert_evidence"] == {
        "decision_index": 0,
        "event_index": 0,
        "trace_path": f"pairs/{pair_id}/best_first_add_w3.json.gz",
    }
    assert "split_assignment_id" not in process
    assert "whole_instance_id" not in process
    assert shard.training_rows[0]["messages"][:2] == serialize_best_first_message_prefix(process["input"])

    operational = shard.operational_rows[0]
    assert operational["view"] == "operational"
    assert set(operational["input"]) == {"action", "source_state", "task_context"}
    assert operational["target"]["validity"] == "accepted"
    assert operational["input"]["source_state"] != operational["target"]["target_state"]


def test_compact_v2_input_round_trips_hard_visitall_facts_and_matches_live() -> None:
    pair_root = ROOT / "data/best_first_paired_phase_v3/exact-traces/pairs" / "astar-pair-d1dcee3d1a6d2d3e7f6219fd"
    task = json.loads((pair_root / "task.json").read_bytes())
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    controller = BestFirstController(
        authority,
        BEST_FIRST_SETTINGS["best_first_add_w3"],
        accepted_delta_limit=16,
        max_budget=15_000,
    )
    controller.start_expansion()

    teacher = build_compact_best_first_teacher_model_input(authority, controller)
    live = build_compact_best_first_live_model_input(authority, controller)
    legacy_context = authority.task_context()

    assert teacher == live
    assert teacher["schema_version"] == "best_first_compact_model_input_v2"
    assert expand_compact_best_first_facts(teacher["current"]["state_facts"]) == list(authority.initial_state.atoms)
    assert expand_compact_best_first_facts(teacher["task_context"]["goal_facts"]) == list(authority.goal_atoms or ())
    assert expand_compact_best_first_facts(teacher["task_context"]["static_facts"]) == list(
        legacy_context["static_initial_facts"]
    )
    assert expand_compact_best_first_facts(teacher["task_context"]["initial_dynamic_facts"]) == list(
        legacy_context["initial_dynamic_atoms"]
    )
    assert teacher["successor_candidates"]["columns"] == [
        "action",
        "best_cost",
        "closed",
        "dominated",
        "frontier",
        "g",
        "h",
        "priority",
        "pruned",
        "target_state_id",
    ]
    assert len(teacher["successor_candidates"]["rows"]) == len(controller.current_candidates())
    assert len(json.dumps(teacher, sort_keys=True, separators=(",", ":"))) < 8_500


def test_corpus_command_dry_run_binds_the_complete_issue63_release() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/materialize_best_first_paired_corpus.py"),
            "--dry-run",
        ],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "authorized_stage": "corpus_release",
        "contract_id": "issue-64-best-first-paired-corpus-v3",
        "curriculum_controls": ["staged", "shuffled", "mixed_order"],
        "excluded_pair_count": 11,
        "fresh_test_access_authorized": False,
        "max_reference_decisions_per_trace": 1_024,
        "operational_records": 31_531,
        "output_root": str((ROOT / "data/best_first_paired_phase_v3/corpus-release-v3").resolve()),
        "pair_count": 64,
        "process_records": 31_531,
        "source_generation_receipt": "generation:issue-63-best-first-paired-v3:attempt-001",
        "trace_count": 128,
        "views": ["operational", "process"],
        "writes": 0,
    }


def test_corpus_command_fixture_dry_run_materializes_and_checks_without_repository_writes() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/materialize_best_first_paired_corpus.py"),
            "--fixture-dry-run",
        ],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "operational_records": 16,
        "pair_count": 1,
        "process_records": 16,
        "status": "fixture_contract_validated",
        "trace_count": 2,
        "writes": 0,
    }


def test_release_emits_selected_curriculum_controls_and_semantic_audit(
    tmp_path: Path,
) -> None:
    full_contract = _load_contract()
    pair_id = "astar-pair-15205002a905be45f6de13ba"
    source_manifest = full_contract.source_manifest
    item = next(pair for pair in source_manifest["pairs"] if pair["pair_id"] == pair_id)
    excluded_item = next(
        pair for pair in source_manifest["pairs"] if pair["pair_id"] == "astar-pair-d1dcee3d1a6d2d3e7f6219fd"
    )
    record_count = sum(trace["decision_count"] for trace in item["traces"].values())
    excluded_record_count = sum(trace["decision_count"] for trace in excluded_item["traces"].values())
    contract = BestFirstCorpusContract(
        design={
            **full_contract.design,
            "expected_counts": {
                "dev_records": record_count,
                "domains": 1,
                "excluded_pairs": 1,
                "excluded_records": excluded_record_count,
                "excluded_traces": 2,
                "operational_records": record_count,
                "pairs": 1,
                "process_records": record_count,
                "strata": 1,
                "traces": 2,
                "train_records": 0,
            },
        },
        authorization=full_contract.authorization,
        source_phase=full_contract.source_phase,
        source_manifest={
            **source_manifest,
            "pair_count": 2,
            "trace_count": 4,
            "pairs": [item, excluded_item],
        },
        repo_root=ROOT,
    )
    output_root = tmp_path / "release"

    manifest = run_best_first_corpus_release(
        contract=contract,
        output_root=output_root,
        token_counter=_FixtureTokenCounter(),
    )

    assert manifest["counts"] == {
        "operational_records": record_count,
        "process_records": record_count,
        "excluded_pairs": 1,
        "split_assignments": 1,
        "strata": 1,
        "training_projection_records": record_count,
    }
    assert manifest["curriculum_controls"] == ["staged", "shuffled", "mixed_order"]
    assert all(set(artifact) == {"path"} for artifact in manifest["artifacts"])
    curriculum_paths = [
        artifact["path"] for artifact in manifest["artifacts"] if artifact["path"].startswith("curricula/")
    ]
    assert curriculum_paths == [
        f"curricula/{view}/{control}.jsonl.gz"
        for view in ("operational", "process")
        for control in ("mixed_order", "shuffled", "staged")
    ]
    for relative in curriculum_paths:
        rows = [json.loads(line) for line in gzip.decompress((output_root / relative).read_bytes()).splitlines()]
        assert len(rows) == record_count
        assert len({row["record_id"] for row in rows}) == record_count

    audit = json.loads((output_root / "audits/corpus.json").read_bytes())
    assert audit["status"] == "passed"
    assert all(audit[name] == 0 for name in contract.design["required_audit_results"])
    exclusion_rows = [
        json.loads(line)
        for line in gzip.decompress((output_root / "exclusions/pairs.jsonl.gz").read_bytes()).splitlines()
    ]
    assert exclusion_rows == [
        {
            "decision_counts": {
                "best_first_add_greedy": 26_372,
                "best_first_add_w3": 38_011,
            },
            "difficulty": "hard",
            "domain_id": "visitall",
            "max_reference_decisions_per_trace": 1_024,
            "outcome": "VALID_STOP",
            "pair_id": "astar-pair-d1dcee3d1a6d2d3e7f6219fd",
            "reason": "paired reference exceeds the VLM decision-call feasibility ceiling",
            "scientific_completion": False,
            "split": "dev",
        }
    ]


def test_corpus_command_has_no_integrity_check_mode() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/materialize_best_first_paired_corpus.py"), "--check"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert completed.returncode == 2
    assert "--fixture-dry-run --dry-run --materialize is required" in completed.stderr
