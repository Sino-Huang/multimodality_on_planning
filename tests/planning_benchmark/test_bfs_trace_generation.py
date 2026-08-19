from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from examples.planning_benchmark_slice.bfs_corpus import (
    regenerate_bfs_text_corpus,
    run_frozen_bfs_text_corpus_release,
)
from examples.planning_benchmark_slice.bfs_generation import run_frozen_bfs_trace_generation
from examples.planning_benchmark_slice.bfs_phase import BFSPhaseGate, load_bfs_phase_gate
from examples.planning_benchmark_slice.search_episode import replay_search_episode
from examples.planning_benchmark_slice.validate_instance import load_fixture
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome
from src.data_collect.splits import split_assignment_id, whole_instance_identity

REPO_ROOT = Path(__file__).resolve().parents[2]
FREEZE_MANIFEST = REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json"
AUTHORIZATION_MANIFEST = REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json"
TASK_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_nontrivial.json"
SIGNING_KEY = b"issue-50-bfs-trace-generation-test-key"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _frozen_curriculum(tmp_path: Path) -> tuple[BFSPhaseGate, Path]:
    fixture = load_fixture(TASK_FIXTURE)
    curriculum_root = tmp_path / "curriculum"
    rows: list[dict[str, object]] = []
    for difficulty in ("easy", "medium", "hard"):
        instance_id = f"blocksworld-train-{difficulty}-0000"
        instance_root = curriculum_root / "blocksworld" / "train" / difficulty / instance_id
        instance_root.mkdir(parents=True)
        domain_path = instance_root / "domain.pddl"
        problem_path = instance_root / "problem.pddl"
        domain_path.write_text(fixture.domain_pddl, encoding="utf-8")
        problem_path.write_text(fixture.problem_pddl, encoding="utf-8")
        rows.append(
            {
                "bucket": difficulty,
                "domain_hash": _sha256(domain_path.read_bytes()),
                "domain_id": "blocksworld",
                "domain_path": str(domain_path),
                "instance_id": instance_id,
                "problem_hash": _sha256(problem_path.read_bytes()),
                "problem_path": str(problem_path),
                "split": "train",
                "status": "accepted",
            }
        )
    rows.append(
        {
            "bucket": "easy",
            "domain_hash": "0" * 64,
            "domain_id": "blocksworld",
            "domain_path": str(curriculum_root / "held-out-domain-must-not-be-read.pddl"),
            "instance_id": "blocksworld-test-easy-0000",
            "problem_hash": "0" * 64,
            "problem_path": str(curriculum_root / "held-out-problem-must-not-be-read.pddl"),
            "split": "test",
            "status": "accepted",
        }
    )

    accepted_manifest = curriculum_root / "accepted_manifest.jsonl"
    accepted_manifest.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    committed = load_bfs_phase_gate(FREEZE_MANIFEST, AUTHORIZATION_MANIFEST)
    freeze = json.loads(json.dumps(committed.freeze))
    freeze["data"]["domains"] = ["blocksworld"]
    freeze["data"]["artifacts"] = [
        {"path": str(accepted_manifest), "sha256": _sha256(accepted_manifest.read_bytes())}
    ]
    freeze["data"]["development_counts_by_split_and_difficulty"] = {
        "train": {"easy": 1, "medium": 1, "hard": 1}
    }
    return replace(committed, freeze=freeze), accepted_manifest


def _request(
    tmp_path: Path,
    *,
    phase_gate: BFSPhaseGate,
    gate_outcome: StopOutcome = StopOutcome.PASS,
    contract_id: str | None = None,
) -> GenerationRequest:
    binding = ReceiptBinding(
        contract_id=contract_id or phase_gate.phase_id,
        attempt_id=f"issue-50-{gate_outcome.value.lower()}",
        output_root=(tmp_path / "bfs-traces").resolve(),
    )
    ancestor_digest = "a" * 64 if gate_outcome is StopOutcome.ANCESTOR_STOP else None
    gate = GateReceipt(
        binding=binding,
        outcome=gate_outcome,
        ancestor_receipt_digest=ancestor_digest,
    ).signed(SIGNING_KEY)
    authorization = None
    if gate_outcome is StopOutcome.PASS:
        authorization = AuthorizationReceipt(
            binding=binding,
            gate_receipt_digest=gate.digest,
        ).signed(SIGNING_KEY)
    return GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=SIGNING_KEY,
        receipt_root=(tmp_path / "receipts").resolve(),
        ancestor_receipt_digest=ancestor_digest,
    )


def _legacy_pddl_phase(tmp_path: Path) -> tuple[BFSPhaseGate, Path]:
    wanted = {("driverlog", "easy"), ("storage", "easy")}
    selected: dict[tuple[str, str], dict[str, object]] = {}
    for line in (REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        row = json.loads(line)
        stratum = (row["domain_id"], row["bucket"])
        if row["split"] in {"train", "dev"} and stratum in wanted and stratum not in selected:
            selected[stratum] = row
    assert set(selected) == wanted

    accepted_manifest = tmp_path / "legacy-accepted-manifest.jsonl"
    accepted_manifest.write_text(
        "".join(json.dumps(selected[stratum], sort_keys=True) + "\n" for stratum in sorted(selected)),
        encoding="utf-8",
    )
    committed = load_bfs_phase_gate(FREEZE_MANIFEST, AUTHORIZATION_MANIFEST)
    freeze = json.loads(json.dumps(committed.freeze))
    freeze["budgets"]["episode_max_expansions_by_difficulty"] = {"easy": 1}
    freeze["data"]["domains"] = ["driverlog", "storage"]
    freeze["data"]["strata"] = ["easy"]
    freeze["data"]["artifacts"] = [
        {"path": str(accepted_manifest), "sha256": _sha256(accepted_manifest.read_bytes())}
    ]
    return replace(committed, freeze=freeze), accepted_manifest


def test_generates_replayable_canonical_fifo_traces_for_every_frozen_stratum(tmp_path: Path) -> None:
    phase_gate, accepted_manifest = _frozen_curriculum(tmp_path)
    request = _request(tmp_path, phase_gate=phase_gate)

    receipt = run_frozen_bfs_trace_generation(
        accepted_manifest_path=accepted_manifest,
        request=request,
        phase_gate=phase_gate,
    )

    assert receipt.outcome is StopOutcome.PASS
    assert receipt.status == "completed"
    assert receipt.scientific_completion is True
    execution_result = cast(dict[str, Any], receipt.execution_result)
    trace_manifest_path = Path(execution_result["trace_manifest_path"])
    trace_manifest = json.loads(trace_manifest_path.read_text(encoding="utf-8"))
    assert trace_manifest["schema_version"] == "bfs_expert_trace_generation_v1"
    assert trace_manifest["coverage"] == {
        "covered_strata": 3,
        "minimum_traces_per_domain_difficulty": 1,
        "required_strata": 3,
    }
    assert [(item["domain_id"], item["difficulty"]) for item in trace_manifest["traces"]] == [
        ("blocksworld", "easy"),
        ("blocksworld", "hard"),
        ("blocksworld", "medium"),
    ]

    phase_receipt = phase_gate.receipt(stage="trace_generation")
    for item in trace_manifest["traces"]:
        assert item["algorithm"] == "bfs"
        assert item["canonical_tie_break"] == "grounded_actions_sorted_by_canonical_serialization"
        assert item["trace_scope"] == "bounded_search_trace_segment"
        assert item["phase_receipt"] == phase_receipt
        assert item["source"]["accepted_manifest_sha256"] == _sha256(accepted_manifest.read_bytes())
        assert item["source"]["domain_sha256"] == item["source"]["manifest_domain_sha256"]
        assert item["source"]["problem_sha256"] == item["source"]["manifest_problem_sha256"]

        evidence_path = Path(request.binding.output_root) / item["evidence"]["path"]
        trace_path = Path(request.binding.output_root) / item["search_trace"]["path"]
        assert _sha256(evidence_path.read_bytes()) == item["evidence"]["sha256"]
        assert _sha256(trace_path.read_bytes()) == item["search_trace"]["sha256"]
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        replayed = replay_search_episode(evidence, signing_key=SIGNING_KEY)
        assert replayed["result"]["outcome"] == StopOutcome.PASS.value
        for expansion in evidence["expansions"]:
            assert expansion["expanded_state_id"] == expansion["frontier_before"][0]
            assert expansion["frontier_after"] == [
                *expansion["frontier_before"][1:],
                *expansion["enqueued_state_ids"],
            ]


def test_normalizes_frozen_legacy_pddl_without_losing_source_provenance(tmp_path: Path) -> None:
    phase_gate, accepted_manifest = _legacy_pddl_phase(tmp_path)
    request = _request(tmp_path, phase_gate=phase_gate)

    receipt = run_frozen_bfs_trace_generation(
        accepted_manifest_path=accepted_manifest,
        request=request,
        phase_gate=phase_gate,
    )

    assert receipt.outcome is StopOutcome.PASS
    execution_result = cast(dict[str, Any], receipt.execution_result)
    trace_manifest = json.loads(Path(execution_result["trace_manifest_path"]).read_text(encoding="utf-8"))
    transformations = {
        item["domain_id"]: item["source"]["authority_transformations"] for item in trace_manifest["traces"]
    }
    assert transformations == {
        "driverlog": ["drop_undeclared_driverlog_metric_initializers"],
        "storage": ["replace_storage_either_with_surface_supertype"],
    }
    for item in trace_manifest["traces"]:
        assert item["source"]["domain_sha256"] == item["source"]["manifest_domain_sha256"]
        assert item["source"]["problem_sha256"] == item["source"]["manifest_problem_sha256"]
        assert item["source"]["authority_domain_sha256"]
        assert item["source"]["authority_problem_sha256"]


def test_stopped_gates_emit_gated_not_run_before_phase_or_curriculum_validation(tmp_path: Path) -> None:
    phase_gate, _ = _frozen_curriculum(tmp_path)
    for outcome in (StopOutcome.VALID_STOP, StopOutcome.ANCESTOR_STOP):
        request = _request(
            tmp_path / outcome.value.lower(),
            phase_gate=phase_gate,
            gate_outcome=outcome,
            contract_id="intentionally-not-the-phase-contract",
        )

        receipt = run_frozen_bfs_trace_generation(
            accepted_manifest_path=tmp_path / "intentionally-missing.jsonl",
            request=request,
            phase_gate=phase_gate,
        )

        assert receipt.outcome is outcome
        assert receipt.status == "gated_not_run"
        assert receipt.scientific_completion is False
        assert receipt.execution_result is None
        assert receipt.receipt_path.is_file()
        assert not Path(request.binding.output_root).exists()


def test_phase_contract_mismatch_emits_invalid_receipt_without_scientific_completion(tmp_path: Path) -> None:
    phase_gate, accepted_manifest = _frozen_curriculum(tmp_path)
    request = _request(
        tmp_path,
        phase_gate=phase_gate,
        contract_id="intentionally-not-the-phase-contract",
    )

    receipt = run_frozen_bfs_trace_generation(
        accepted_manifest_path=accepted_manifest,
        request=request,
        phase_gate=phase_gate,
    )

    assert receipt.outcome is StopOutcome.INVALID
    assert receipt.status == "execution_failed"
    assert receipt.scientific_completion is False
    assert receipt.execution_result is None
    assert receipt.reason == "execute_raised:BFSPhaseGateError"
    assert receipt.receipt_path.is_file()
    assert not Path(request.binding.output_root).exists()


def test_releases_separate_regenerable_views_with_immutable_splits_and_clean_leakage_audit(
    tmp_path: Path,
) -> None:
    phase_gate, accepted_manifest = _frozen_curriculum(tmp_path)
    trace_request = _request(tmp_path / "trace-run", phase_gate=phase_gate)
    trace_receipt = run_frozen_bfs_trace_generation(
        accepted_manifest_path=accepted_manifest,
        request=trace_request,
        phase_gate=phase_gate,
    )
    assert trace_receipt.outcome is StopOutcome.PASS
    assert trace_receipt.execution_result is not None
    trace_manifest_path = Path(trace_receipt.execution_result["trace_manifest_path"])

    release_root = (tmp_path / "bfs-text-corpus").resolve()
    release_binding = ReceiptBinding(
        contract_id=phase_gate.phase_id,
        attempt_id="issue-51-corpus-release",
        output_root=release_root,
    )
    release_gate = GateReceipt(binding=release_binding, outcome=StopOutcome.PASS).signed(SIGNING_KEY)
    release_request = GenerationRequest(
        binding=release_binding,
        gate_receipt=release_gate,
        authorization_receipt=AuthorizationReceipt(
            binding=release_binding,
            gate_receipt_digest=release_gate.digest,
        ).signed(SIGNING_KEY),
        signing_key=SIGNING_KEY,
        receipt_root=(tmp_path / "release-receipts").resolve(),
    )

    release_receipt = run_frozen_bfs_text_corpus_release(
        trace_manifest_path=trace_manifest_path,
        request=release_request,
        phase_gate=phase_gate,
    )

    assert release_receipt.outcome is StopOutcome.PASS
    assert release_receipt.status == "completed"
    assert release_receipt.scientific_completion is True
    assert release_receipt.execution_result is not None
    release_manifest_path = Path(release_receipt.execution_result["corpus_manifest_path"])
    release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
    assert release_manifest["schema_version"] == "bfs_text_corpus_release_v1"
    assert release_manifest["phase_receipt"] == phase_gate.receipt(stage="corpus_release")
    assert release_manifest["source_trace_manifest"]["sha256"] == _sha256(trace_manifest_path.read_bytes())

    released = {
        artifact["path"]: (release_root / artifact["path"]).read_bytes() for artifact in release_manifest["artifacts"]
    }
    regenerated = regenerate_bfs_text_corpus(
        trace_manifest_path=trace_manifest_path,
        signing_key=SIGNING_KEY,
        phase_gate=phase_gate,
    )
    assert regenerated == {
        **released,
        release_manifest_path.relative_to(release_root).as_posix(): release_manifest_path.read_bytes(),
    }

    audit = json.loads(released["audits/leakage.json"])
    assert audit == {
        "future_step_leakage_count": 0,
        "held_out_instance_count": 0,
        "operational_process_record_contamination": 0.0,
        "operational_process_record_contamination_count": 0,
        "schema_version": "bfs_text_corpus_leakage_audit_v1",
        "split_conflict_count": 0,
        "status": "passed",
    }

    operational_rows = [json.loads(line) for line in released["corpus/operational.jsonl"].splitlines()]
    process_rows = [json.loads(line) for line in released["corpus/process.jsonl"].splitlines()]
    assert operational_rows
    assert process_rows
    assert all(row["view"] == "operational" for row in operational_rows)
    assert all(set(row["input"]) == {"goal_atoms", "source_state"} for row in operational_rows)
    assert all(set(row["target"]) == {"action", "target_state", "validity"} for row in operational_rows)
    assert all(row["view"] == "process" for row in process_rows)
    assert all(set(row["input"]) == {"goal_atoms", "observation", "search_memory"} for row in process_rows)
    assert all(
        set(row["target"]) == {"canonical_rationale", "runtime_result", "typed_operation"} for row in process_rows
    )

    task = load_fixture(TASK_FIXTURE)
    instance_identity = whole_instance_identity(task.domain_pddl, task.problem_pddl)
    expected_assignment_id = split_assignment_id(instance_identity, "train")
    split_rows = [json.loads(line) for line in released["splits/assignments.jsonl"].splitlines()]
    assert split_rows == [
        {
            "assignment_id": expected_assignment_id,
            "identity": instance_identity,
            "split": "train",
        }
    ]
    for row in (*operational_rows, *process_rows):
        assert row["split"] == "train"
        assert row["split_assignment_id"] == expected_assignment_id
        assert row["whole_instance_id"] == instance_identity

    for view, rows in (("operational", operational_rows), ("process", process_rows)):
        curriculum = [json.loads(line) for line in released[f"curricula/{view}.jsonl"].splitlines()]
        assert [entry["record_id"] for entry in curriculum] == [row["record_id"] for row in rows]
        assert [entry["curriculum_index"] for entry in curriculum] == list(range(len(rows)))
        assert {entry["difficulty"] for entry in curriculum} == {"easy", "medium", "hard"}

    conflicting_manifest = json.loads(trace_manifest_path.read_text(encoding="utf-8"))
    conflicting_manifest["traces"][1]["source"]["split"] = "dev"
    conflicting_manifest_path = trace_manifest_path.with_name("split-conflict.json")
    conflicting_manifest_path.write_text(
        json.dumps(conflicting_manifest, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="leakage audit failed"):
        regenerate_bfs_text_corpus(
            trace_manifest_path=conflicting_manifest_path,
            signing_key=SIGNING_KEY,
            phase_gate=phase_gate,
        )


def test_corpus_release_stop_outcomes_never_read_traces_or_create_release_bytes(tmp_path: Path) -> None:
    phase_gate, _ = _frozen_curriculum(tmp_path)
    cases = (
        (StopOutcome.PASS, StopOutcome.INVALID, "invalid_not_run", None),
        (StopOutcome.VALID_STOP, StopOutcome.VALID_STOP, "gated_not_run", None),
        (StopOutcome.INVALID, StopOutcome.INVALID, "invalid_not_run", None),
        (StopOutcome.ANCESTOR_STOP, StopOutcome.ANCESTOR_STOP, "gated_not_run", "b" * 64),
    )
    for gate_outcome, expected_outcome, expected_status, ancestor_digest in cases:
        binding = ReceiptBinding(
            contract_id="intentionally-not-the-phase-contract",
            attempt_id=f"issue-51-{gate_outcome.value.lower()}",
            output_root=(tmp_path / gate_outcome.value.lower() / "corpus").resolve(),
        )
        gate = GateReceipt(
            binding=binding,
            outcome=gate_outcome,
            ancestor_receipt_digest=ancestor_digest,
        ).signed(SIGNING_KEY)
        request = GenerationRequest(
            binding=binding,
            gate_receipt=gate,
            authorization_receipt=None,
            signing_key=SIGNING_KEY,
            receipt_root=(tmp_path / gate_outcome.value.lower() / "receipts").resolve(),
            ancestor_receipt_digest=ancestor_digest,
        )

        receipt = run_frozen_bfs_text_corpus_release(
            trace_manifest_path=tmp_path / "must-not-be-read.json",
            request=request,
            phase_gate=phase_gate,
        )

        assert receipt.outcome is expected_outcome
        assert receipt.status == expected_status
        assert receipt.scientific_completion is False
        assert receipt.execution_result is None
        assert receipt.receipt_path.is_file()
        assert not Path(request.binding.output_root).exists()


def test_corpus_release_phase_mismatch_is_invalid_and_publishes_no_corpus(tmp_path: Path) -> None:
    phase_gate, _ = _frozen_curriculum(tmp_path)
    binding = ReceiptBinding(
        contract_id="not-the-frozen-phase",
        attempt_id="issue-51-phase-mismatch",
        output_root=(tmp_path / "phase-mismatch-corpus").resolve(),
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS).signed(SIGNING_KEY)
    request = GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(
            binding=binding,
            gate_receipt_digest=gate.digest,
        ).signed(SIGNING_KEY),
        signing_key=SIGNING_KEY,
        receipt_root=(tmp_path / "phase-mismatch-receipts").resolve(),
    )

    receipt = run_frozen_bfs_text_corpus_release(
        trace_manifest_path=tmp_path / "must-not-be-read.json",
        request=request,
        phase_gate=phase_gate,
    )

    assert receipt.outcome is StopOutcome.INVALID
    assert receipt.status == "execution_failed"
    assert receipt.scientific_completion is False
    assert receipt.execution_result is None
    assert receipt.reason == "execute_raised:BFSPhaseGateError"
    assert receipt.receipt_path.is_file()
    assert not Path(request.binding.output_root).exists()
