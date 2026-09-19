from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, TypedDict, cast

import pytest

from examples.planning_benchmark_slice.episode_evidence import read_episode_evidence
from examples.planning_benchmark_slice.generation_orchestrator import (
    regenerate_corpus_fragment,
    run_bfs_generation_smoke,
)
from examples.planning_benchmark_slice.search_episode import SearchEpisodeError
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

REPO_ROOT = Path(__file__).resolve().parents[2]
NONTRIVIAL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_nontrivial.json"


class _GenerationExecutionResult(TypedDict):
    formal_task_paths: list[str]
    expert_trace_paths: list[str]
    atomic_segment_paths: list[str]
    artifact_manifest_path: str
    artifact_manifest_size_bytes: int
    corpus_manifest_path: str
    corpus_fragment_path: str
    episode_evidence_path: str


class _CorpusFragmentRegenerator(Protocol):
    def __call__(self, output_root: str | Path) -> bytes: ...


def test_bfs_generation_smoke_persists_a_regenerable_corpus_fragment(tmp_path: Path) -> None:
    output_root = (tmp_path / "corpus-output").resolve()
    receipt_root = (tmp_path / "generation-receipts").resolve()
    binding = ReceiptBinding(
        contract_id="issue-48-planning-corpus",
        attempt_id="bfs-smoke-001",
        output_root=output_root,
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    request = GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(
            binding=binding,
            gate_receipt_id=gate.receipt_id,
        ),
        receipt_root=receipt_root,
    )

    receipt = run_bfs_generation_smoke(
        task_path=NONTRIVIAL_FIXTURE,
        request=request,
        max_expansions=64,
    )

    assert receipt.outcome is StopOutcome.PASS
    assert receipt.status == "completed"
    assert receipt.scientific_completion is True

    execution_result = receipt.execution_result
    assert execution_result is not None
    execution_result = cast(_GenerationExecutionResult, execution_result)
    formal_task_paths = [Path(path) for path in execution_result["formal_task_paths"]]
    expert_trace_paths = [Path(path) for path in execution_result["expert_trace_paths"]]
    atomic_segment_paths = [Path(path) for path in execution_result["atomic_segment_paths"]]
    artifact_manifest_path = Path(execution_result["artifact_manifest_path"])
    corpus_manifest_path = Path(execution_result["corpus_manifest_path"])
    corpus_fragment_path = Path(execution_result["corpus_fragment_path"])
    episode_evidence_path = Path(execution_result["episode_evidence_path"])

    assert len(formal_task_paths) == 1
    assert formal_task_paths[0].is_file()
    assert len(expert_trace_paths) == 1
    assert expert_trace_paths[0].is_file()
    assert atomic_segment_paths
    assert all(path.is_file() for path in atomic_segment_paths)
    assert artifact_manifest_path.is_file()
    assert corpus_manifest_path.is_file()
    assert episode_evidence_path.is_file()
    assert isinstance(read_episode_evidence(episode_evidence_path), dict)

    corpus_fragment = corpus_fragment_path.read_bytes()
    assert corpus_fragment
    regenerate = cast(_CorpusFragmentRegenerator, regenerate_corpus_fragment)
    assert regenerate(output_root) == corpus_fragment

    assert corpus_fragment.endswith(b"\n")
    corpus_rows = corpus_fragment.splitlines()
    assert len(corpus_rows) == len(atomic_segment_paths)
    assert all(corpus_rows)
    for row in corpus_rows:
        assert (
            json.dumps(
                json.loads(row),
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            == row
        )

    artifact_manifest = artifact_manifest_path.read_bytes()
    assert execution_result["artifact_manifest_size_bytes"] == len(artifact_manifest)
    corpus_manifest_payload = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    artifact_manifest_payload = json.loads(artifact_manifest)
    assert isinstance(corpus_manifest_payload, dict)
    assert isinstance(artifact_manifest_payload, dict)
    assert artifact_manifest_payload["artifacts"]

    def assert_declared_artifacts(value: object) -> None:
        if isinstance(value, dict):
            if {"path", "size_bytes"} <= value.keys():
                relative_path = value["path"]
                assert isinstance(relative_path, str)
                artifact_path = output_root / relative_path
                assert artifact_path.resolve().is_relative_to(output_root)
                assert artifact_path.is_file()
                assert value["size_bytes"] == artifact_path.stat().st_size
            for child in value.values():
                assert_declared_artifacts(child)
        elif isinstance(value, list):
            for child in value:
                assert_declared_artifacts(child)

    assert_declared_artifacts(corpus_manifest_payload)
    assert_declared_artifacts(artifact_manifest_payload)


def test_bfs_generation_smoke_rejects_a_truncated_episode(tmp_path: Path) -> None:
    output_root = (tmp_path / "truncated-corpus-output").resolve()
    receipt_root = (tmp_path / "truncated-generation-receipts").resolve()
    binding = ReceiptBinding(
        contract_id="issue-48-planning-corpus",
        attempt_id="bfs-truncated-001",
        output_root=output_root,
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    request = GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(
            binding=binding,
            gate_receipt_id=gate.receipt_id,
        ),
        receipt_root=receipt_root,
    )

    receipt = run_bfs_generation_smoke(
        task_path=NONTRIVIAL_FIXTURE,
        request=request,
        max_expansions=1,
    )

    assert receipt.outcome is StopOutcome.INVALID
    assert receipt.status == "execution_failed"
    assert receipt.scientific_completion is False
    assert receipt.execution_result is None
    assert not output_root.exists()
    assert receipt.receipt_path.parent == receipt_root
    assert receipt.receipt_path.is_file()


def test_bfs_generation_smoke_does_not_overwrite_a_retained_corpus(tmp_path: Path) -> None:
    output_root = (tmp_path / "retained-corpus-output").resolve()
    receipt_root = (tmp_path / "retained-generation-receipts").resolve()

    def request_for(attempt_id: str) -> GenerationRequest:
        binding = ReceiptBinding(
            contract_id="issue-48-planning-corpus",
            attempt_id=attempt_id,
            output_root=output_root,
        )
        gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
        return GenerationRequest(
            binding=binding,
            gate_receipt=gate,
            authorization_receipt=AuthorizationReceipt(
                binding=binding,
                gate_receipt_id=gate.receipt_id,
            ),
            receipt_root=receipt_root,
        )

    first = run_bfs_generation_smoke(
        task_path=NONTRIVIAL_FIXTURE,
        request=request_for("bfs-retained-001"),
        max_expansions=64,
    )

    assert first.outcome is StopOutcome.PASS
    assert first.status == "completed"
    assert first.scientific_completion is True
    first_execution_result = first.execution_result
    assert first_execution_result is not None
    first_execution_result = cast(_GenerationExecutionResult, first_execution_result)
    corpus_fragment_path = Path(first_execution_result["corpus_fragment_path"])
    artifact_manifest_path = Path(first_execution_result["artifact_manifest_path"])
    retained_corpus_fragment = corpus_fragment_path.read_bytes()
    retained_artifact_manifest = artifact_manifest_path.read_bytes()

    second = run_bfs_generation_smoke(
        task_path=NONTRIVIAL_FIXTURE,
        request=request_for("bfs-retained-002"),
        max_expansions=64,
    )

    assert second.outcome is StopOutcome.INVALID
    assert second.status == "execution_failed"
    assert second.scientific_completion is False
    assert second.execution_result is None
    assert corpus_fragment_path.read_bytes() == retained_corpus_fragment
    assert artifact_manifest_path.read_bytes() == retained_artifact_manifest
    for receipt in (first, second):
        assert receipt.receipt_path.parent == receipt_root
        assert receipt.receipt_path.is_file()


def test_unpermitted_bfs_generation_does_not_create_corpus_output(tmp_path: Path) -> None:
    receipt_root = (tmp_path / "governed-receipts").resolve()
    cases: tuple[tuple[str, StopOutcome, StopOutcome, str, str | None, bool], ...] = (
        (
            "authorization-binding-mismatch",
            StopOutcome.PASS,
            StopOutcome.INVALID,
            "invalid_not_run",
            None,
            True,
        ),
        (
            "valid-stop",
            StopOutcome.VALID_STOP,
            StopOutcome.VALID_STOP,
            "gated_not_run",
            None,
            False,
        ),
        (
            "invalid",
            StopOutcome.INVALID,
            StopOutcome.INVALID,
            "invalid_not_run",
            None,
            False,
        ),
        (
            "ancestor-stop",
            StopOutcome.ANCESTOR_STOP,
            StopOutcome.ANCESTOR_STOP,
            "gated_not_run",
            "a" * 64,
            False,
        ),
    )

    for case_id, gate_outcome, expected_outcome, expected_status, ancestor_digest, mismatched_authorization in cases:
        output_root = (tmp_path / f"corpus-output-{case_id}").resolve()
        binding = ReceiptBinding(
            contract_id="issue-48-planning-corpus-stops",
            attempt_id=f"{case_id}-001",
            output_root=output_root,
        )
        gate = GateReceipt(
            binding=binding,
            outcome=gate_outcome,
            ancestor_receipt_id=ancestor_digest,
        )
        authorization: AuthorizationReceipt | None = None
        if mismatched_authorization:
            different_binding = ReceiptBinding(
                contract_id="issue-48-planning-corpus-stops",
                attempt_id=f"{case_id}-authorization",
                output_root=(tmp_path / f"different-output-{case_id}").resolve(),
            )
            authorization = AuthorizationReceipt(
                binding=different_binding,
                gate_receipt_id=gate.receipt_id,
            )
        request = GenerationRequest(
            binding=binding,
            gate_receipt=gate,
            authorization_receipt=authorization,
            receipt_root=receipt_root,
            ancestor_receipt_id=ancestor_digest,
        )

        receipt = run_bfs_generation_smoke(
            task_path=tmp_path / "intentionally-nonexistent-task.json",
            request=request,
            max_expansions=64,
        )

        assert receipt.outcome is expected_outcome
        assert receipt.status == expected_status
        assert receipt.scientific_completion is False
        assert receipt.execution_result is None
        assert not output_root.exists()
        assert receipt.receipt_path.parent == receipt_root
        assert receipt.receipt_path.is_file()
