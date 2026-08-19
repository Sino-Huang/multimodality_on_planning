from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from examples.planning_benchmark_slice.bfs_generation import run_frozen_bfs_trace_generation
from examples.planning_benchmark_slice.bfs_phase import BFSPhaseGate, load_bfs_phase_gate
from examples.planning_benchmark_slice.search_episode import replay_search_episode
from examples.planning_benchmark_slice.validate_instance import load_fixture
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

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
) -> GenerationRequest:
    binding = ReceiptBinding(
        contract_id=phase_gate.phase_id,
        attempt_id=f"issue-50-{gate_outcome.value.lower()}",
        output_root=(tmp_path / "bfs-traces").resolve(),
    )
    gate = GateReceipt(binding=binding, outcome=gate_outcome).signed(SIGNING_KEY)
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


def test_valid_stop_gate_emits_gated_not_run_without_reading_curriculum(tmp_path: Path) -> None:
    phase_gate, _ = _frozen_curriculum(tmp_path)
    request = _request(tmp_path, phase_gate=phase_gate, gate_outcome=StopOutcome.VALID_STOP)

    receipt = run_frozen_bfs_trace_generation(
        accepted_manifest_path=tmp_path / "intentionally-missing.jsonl",
        request=request,
        phase_gate=phase_gate,
    )

    assert receipt.outcome is StopOutcome.VALID_STOP
    assert receipt.status == "gated_not_run"
    assert receipt.scientific_completion is False
    assert receipt.execution_result is None
    assert receipt.receipt_path.is_file()
    assert not Path(request.binding.output_root).exists()
