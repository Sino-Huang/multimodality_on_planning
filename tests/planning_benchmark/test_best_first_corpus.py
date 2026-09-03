from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.best_first_corpus import (
    BestFirstCorpusContract,
    materialize_best_first_corpus_trace,
    run_best_first_corpus_release,
    verify_best_first_corpus_release,
)
from examples.planning_benchmark_slice.best_first_episode import (
    run_best_first,
    serialize_best_first_trace,
)
from examples.planning_benchmark_slice.best_first_model_input import (
    serialize_best_first_message_prefix,
)
from examples.planning_benchmark_slice.best_first_phase import load_best_first_phase
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority

ROOT = Path(__file__).resolve().parents[2]


class _FixtureTokenCounter:
    def input_tokens(self, model_input) -> int:
        return len(json.dumps(model_input, sort_keys=True)) // 4

    def target_tokens(self, target_text: str) -> int:
        return len(target_text) // 4


def test_compact_trace_materializes_process_operational_and_training_views(tmp_path: Path) -> None:
    source_task = ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json"
    task_bytes = source_task.read_bytes()
    task = json.loads(task_bytes)
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    search = run_best_first(
        authority,
        algorithm="best_first_add_w3",
        max_expansions=64,
        max_trace_records=256,
        max_trace_bytes=1_000_000,
    )
    trace_bytes = serialize_best_first_trace(search.trace_payload)
    pair_id = "fixture-pair"
    pair_root = tmp_path / "pairs" / pair_id
    pair_root.mkdir(parents=True)
    (pair_root / "task.json").write_bytes(task_bytes)
    trace_path = pair_root / "best_first_add_w3.json.gz"
    trace_path.write_bytes(gzip.compress(trace_bytes, compresslevel=9, mtime=0))
    pair_item = {
        "instance_id": task["instance_id"],
        "pair_id": pair_id,
        "schema_version": "best_first_paired_trace_item_v1",
        "task_path": "task.json",
        "task_sha256": hashlib.sha256(task_bytes).hexdigest(),
        "traces": {
            "best_first_add_w3": {
                "decision_count": search.decision_count,
                "expansion_count": search.expansion_count,
                "path": trace_path.name,
                "reopen_count": search.controller.reopen_count,
                "sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
                "solution_cost": search.trace_payload["result"]["solution_cost"],
                "stored_size_bytes": trace_path.stat().st_size,
                "uncompressed_size_bytes": len(trace_bytes),
            }
        },
    }
    row = {
        "difficulty": "easy",
        "domain_id": "blocksworld",
        "instance_id": task["instance_id"],
        "pair_id": pair_id,
        "split": "dev",
        "task_sha256": pair_item["task_sha256"],
    }
    corpus_config = {
        "accepted_delta_limit": 16,
        "model_input_token_limit": 7_808,
        "model_output_token_limit": 384,
    }

    shard = materialize_best_first_corpus_trace(
        row=row,
        pair_item=pair_item,
        algorithm="best_first_add_w3",
        trace_root=tmp_path,
        corpus_config=corpus_config,
        token_counter=_FixtureTokenCounter(),
    )

    assert len(shard.process_rows) == search.decision_count == 6
    assert len(shard.operational_rows) == search.decision_count
    assert len(shard.training_rows) == search.decision_count
    assert shard.audit["input_digest_mismatch_count"] == 0
    assert shard.audit["live_training_input_mismatch_count"] == 0
    assert shard.audit["target_parse_rejection_count"] == 0
    assert shard.audit["teacher_decision_rejection_count"] == 0

    process = shard.process_rows[0]
    assert process["algorithm"] == "best_first_add_w3"
    assert process["view"] == "process"
    assert process["target"] == {
        "action": {"args": ["a"], "name": "pickup"},
        "source_state_id": "s0",
    }
    assert process["expert_evidence"] == {
        "decision_index": 0,
        "event_index": 0,
        "trace_path": "pairs/fixture-pair/best_first_add_w3.json.gz",
    }
    assert shard.training_rows[0]["messages"][:2] == serialize_best_first_message_prefix(process["input"])

    operational = shard.operational_rows[0]
    assert operational["view"] == "operational"
    assert set(operational["input"]) == {"action", "source_state", "task_context"}
    assert operational["target"]["validity"] == "accepted"
    assert operational["input"]["source_state"] != operational["target"]["target_state"]


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
        "contract_id": "issue-64-best-first-paired-corpus-v1",
        "curriculum_controls": ["staged", "shuffled", "mixed_order"],
        "fresh_test_access_authorized": False,
        "operational_records": 289_902,
        "output_root": str((ROOT / "data/best_first_paired_phase_v3/corpus-release-v1").resolve()),
        "pair_count": 75,
        "process_records": 289_902,
        "source_generation_receipt": "generation:issue-63-best-first-paired-v3:attempt-001",
        "trace_count": 150,
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
        "byte_identical_regeneration": True,
        "operational_records": 16,
        "pair_count": 1,
        "process_records": 16,
        "status": "fixture_contract_checked",
        "trace_count": 2,
        "writes": 0,
    }


def test_release_emits_all_curriculum_controls_and_regenerates_byte_identically(
    tmp_path: Path,
) -> None:
    source_phase = load_best_first_phase(
        ROOT / "configs/experiments/best-first-paired-design-v3.json",
        ROOT / "configs/experiments/best-first-paired-authorization-v3.json",
        repo_root=ROOT,
    )
    pair_id = "astar-pair-15205002a905be45f6de13ba"
    source_manifest = json.loads((ROOT / "data/best_first_paired_phase_v3/exact-traces/manifest.json").read_bytes())
    item = next(pair for pair in source_manifest["pairs"] if pair["pair_id"] == pair_id)
    record_count = sum(trace["decision_count"] for trace in item["traces"].values())
    contract = BestFirstCorpusContract(
        design={
            "accepted_delta_limit": 16,
            "byte_identical_regeneration_required": [
                "corpus",
                "curricula",
                "split_ledger",
                "training_projection",
            ],
            "compression": {"format": "gzip", "mtime": 0},
            "curriculum_controls": ["staged", "shuffled", "mixed_order"],
            "curriculum_seed": 64,
            "expected_counts": {
                "dev_records": record_count,
                "operational_records": record_count,
                "pairs": 1,
                "process_records": record_count,
                "strata": 1,
                "traces": 2,
                "train_records": 0,
            },
            "phase_id": "issue-64-best-first-paired-corpus-v1",
            "required_audit_results": {
                "canonical_input_overlap_count": 0,
                "future_step_leakage_count": 0,
                "held_out_instance_count": 0,
                "identical_input_conflicting_target_count": 0,
                "input_digest_mismatch_count": 0,
                "input_target_overlap_count": 0,
                "live_training_input_mismatch_count": 0,
                "semantic_task_overlap_count": 0,
                "state_action_mismatch_count": 0,
                "target_parse_rejection_count": 0,
                "teacher_decision_rejection_count": 0,
            },
            "source_trace_manifest": {"path": "data/best_first_paired_phase_v3/exact-traces/manifest.json"},
            "tokenizer": {
                "model_input_token_limit": 7_808,
                "model_output_token_limit": 384,
            },
            "views": ["operational", "process"],
        },
        authorization={
            "authorized_stages": ["corpus_release"],
            "contract_id": "issue-64-best-first-paired-corpus-v1",
            "outcome": "PASS",
            "start_permitted": True,
        },
        source_phase=source_phase,
        source_manifest={**source_manifest, "pair_count": 1, "trace_count": 2, "pairs": [item]},
        repo_root=ROOT,
    )
    output_root = tmp_path / "release"

    manifest = run_best_first_corpus_release(
        contract=contract,
        output_root=output_root,
        token_counter=_FixtureTokenCounter(),
        resume=False,
    )

    assert manifest["counts"] == {
        "operational_records": record_count,
        "process_records": record_count,
        "split_assignments": 1,
        "strata": 1,
        "training_projection_records": record_count,
    }
    assert manifest["curriculum_controls"] == ["staged", "shuffled", "mixed_order"]
    assert all(set(artifact) == {"path", "size_bytes"} for artifact in manifest["artifacts"])
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
    assert (
        verify_best_first_corpus_release(
            contract=contract,
            corpus_root=output_root,
            token_counter=_FixtureTokenCounter(),
        )
        == manifest
    )
