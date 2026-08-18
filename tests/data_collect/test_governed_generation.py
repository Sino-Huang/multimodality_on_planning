from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import TypedDict, cast

import pytest

from src.data_collect import generate
from src.data_collect.adapters import (
    GenerationSpec,
    GeneratorAdapter,
    GeneratorRejection,
    GeneratorRunResult,
    NormalizedCandidate,
)
from src.data_collect.config import CurriculumConfig, OutputPolicy, SeedRange, SplitConfig, TimeoutConfig
from src.data_collect.generate import (
    GenerationRequest,
    GenerationRunReceipt,
    GenerationRunResult,
    run_governed_generation,
)
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome
from src.data_collect.metadata import AcceptedInstanceMetadata, SummaryMetadata, build_candidate_id, build_instance_id
from src.data_collect.rendering import Renderer
from src.data_collect.replay import verify_canonical_replay
from src.data_collect.splits import SplitLedger, whole_instance_identity
from src.data_collect.structural import (
    StructuralCell,
    StructuralProfile,
    StructuralRange,
    StructuralRequirement,
    StructuralStrataPolicy,
)


SIGNING_KEY = b"governed-generation-test-key"
DOMAIN = b"(define (domain tiny) (:predicates (ready)))\n"
PROBLEM = b"(define (problem p) (:domain tiny) (:init (ready)) (:goal (ready)))\n"


class _CoverageCount(TypedDict):
    actual_count: int


class _StructuralCoverageResult(TypedDict, total=False):
    asserted: bool
    complete: bool
    counts: list[_CoverageCount]


class _ExecutionResult(TypedDict):
    accepted_count: int
    canonical_bundle_manifest_path: str
    canonical_bundle_path: str
    split_ledger_path: str
    structural_coverage: _StructuralCoverageResult


class TrackingAdapter(GeneratorAdapter):
    def __init__(self, generator_dir: Path) -> None:
        super().__init__(adapter_id="tiny", generator_dir=generator_dir)
        self.call_count = 0

    def prepare(self) -> None:
        self.call_count += 1

    def generate_candidate(self, spec: GenerationSpec) -> GeneratorRunResult:
        self.call_count += 1
        raise AssertionError(f"unexpected generation call for {spec.candidate_id}")

    def normalize_outputs(
        self,
        raw_result: GeneratorRunResult,
    ) -> NormalizedCandidate | GeneratorRejection:
        self.call_count += 1
        raise AssertionError(f"unexpected normalization call for {raw_result.candidate_id}")

    def supports_seed(self) -> bool:
        return True


def _curriculum_config(root: Path) -> CurriculumConfig:
    return CurriculumConfig(
        config_path=root / "config.json",
        workspace_root=root,
        generator_root=root / "generators",
        manifest_path=root / "manifest.json",
        dependency_config_path=root / "dependencies.json",
        require_rendering=False,
        candidate_multiplier=1,
        seed_range=SeedRange(start=0, stop=1),
        timeouts=TimeoutConfig(generator_seconds=1, render_seconds=1),
        output_policy=OutputPolicy(
            accepted_dir="accepted",
            rejected_dir="rejected",
            summaries_dir="summaries",
        ),
        splits={"train": SplitConfig(total=1, buckets={"easy": 1, "medium": 0, "hard": 0})},
        domains=(),
        dependencies={},
    )


def _execution_result(receipt: GenerationRunReceipt) -> _ExecutionResult:
    assert receipt.execution_result is not None
    return cast(_ExecutionResult, receipt.execution_result)


def _request(
    output_root: Path,
    *,
    authorized: bool = True,
    outcome: StopOutcome = StopOutcome.PASS,
    receipt_root: Path | str | None = None,
) -> GenerationRequest:
    binding = ReceiptBinding(
        contract_id="contract-v1",
        attempt_id="attempt-001",
        output_root=str(output_root.resolve()),
    )
    ancestor_digest = "a" * 64 if outcome is StopOutcome.ANCESTOR_STOP else None
    gate = GateReceipt(
        binding=binding,
        outcome=outcome,
        ancestor_receipt_digest=ancestor_digest,
    ).signed(SIGNING_KEY)
    authorization = (
        AuthorizationReceipt(binding=binding, gate_receipt_digest=gate.digest).signed(SIGNING_KEY)
        if authorized and outcome is StopOutcome.PASS
        else None
    )
    return GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=SIGNING_KEY,
        receipt_root=receipt_root if receipt_root is not None else output_root.parent / "governance",
        ancestor_receipt_digest=ancestor_digest,
    )


def _assert_persisted_receipt(receipt: GenerationRunReceipt, receipt_root: Path) -> None:
    assert receipt.receipt_path.parent == receipt_root.resolve()
    assert receipt.receipt_path.exists()
    assert receipt.receipt_path.read_bytes() == (receipt.canonical_json() + "\n").encode("utf-8")
    payload = json.loads(receipt.receipt_path.read_text(encoding="utf-8"))
    assert payload["outcome"] == receipt.outcome.value


@pytest.mark.parametrize(
    "receipt_root",
    ["", "relative/governance"],
)
def test_generation_request_rejects_non_absolute_receipt_roots(
    tmp_path: Path,
    receipt_root: str,
) -> None:
    with pytest.raises(ValueError, match="receipt_root"):
        _request(tmp_path / "dataset", receipt_root=receipt_root)


def test_generation_request_rejects_unresolved_or_output_nested_receipt_roots(tmp_path: Path) -> None:
    output_root = (tmp_path / "dataset").resolve()

    with pytest.raises(ValueError, match="already be resolved"):
        _request(output_root, receipt_root=tmp_path / "governance" / ".." / "receipts")
    with pytest.raises(ValueError, match="binding.output_root"):
        _request(output_root, receipt_root=output_root / ".governance")


def _fake_orchestrator(call_count: list[int]):
    def run(
        curriculum_config: CurriculumConfig,
        *,
        output_root: Path | str,
        renderer: Renderer | None,
        max_attempts_per_bucket: int,
        seed: int,
        force: bool = False,
        domains: Sequence[str] | None = None,
        splits: Sequence[str] | None = None,
        quotas_by_split: Mapping[str, Mapping[str, int]] | None = None,
        candidate_multiplier: int | None = None,
        registry: Mapping[str, GeneratorAdapter] | None = None,
    ) -> GenerationRunResult:
        del (
            curriculum_config,
            renderer,
            max_attempts_per_bucket,
            seed,
            force,
            domains,
            splits,
            quotas_by_split,
            candidate_multiplier,
            registry,
        )
        call_count[0] += 1
        resolved_output_root = Path(output_root).resolve()
        instance_dir = resolved_output_root / "tiny" / "train" / "easy" / "tiny-train-easy-0000"
        instance_dir.mkdir(parents=True, exist_ok=True)
        domain_path = instance_dir / "domain.pddl"
        problem_path = instance_dir / "problem.pddl"
        domain_path.write_bytes(DOMAIN)
        problem_path.write_bytes(PROBLEM)
        accepted_manifest_path = resolved_output_root / generate.ACCEPTED_MANIFEST_FILENAME
        accepted_manifest_path.write_text('{"stdout_path":"/absolute/runtime.log"}\n', encoding="utf-8")
        summary_path = resolved_output_root / generate.SUMMARY_FILENAME
        summary_path.write_text('{"elapsed_seconds":123.4}\n', encoding="utf-8")
        rejections_path = resolved_output_root / generate.REJECTIONS_FILENAME
        rejections_path.write_bytes(b"")
        accepted = AcceptedInstanceMetadata(
            instance_id=build_instance_id("tiny", "train", "easy", 0),
            candidate_id=build_candidate_id("tiny", "train", "easy", 0),
            domain_id="tiny",
            split="train",
            bucket="easy",
            index=0,
            attempt_index=0,
            domain_path=str(domain_path),
            problem_path=str(problem_path),
        )
        summary = SummaryMetadata(
            accepted_total=1,
            rejected_total=0,
            duplicate_accepted_problems=0,
            domains_completed=1,
            accepted_by_split={"train": 1},
            accepted_by_bucket={"easy": 1},
            accepted_by_domain={"tiny": 1},
        )
        return GenerationRunResult(
            accepted_instances=(accepted,),
            rejected_candidates=(),
            summary=summary,
            output_root=resolved_output_root,
            accepted_manifest_path=accepted_manifest_path,
            rejections_path=rejections_path,
            summary_path=summary_path,
        )

    return run


def _run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    ledger_path: Path | None = None,
    structural_policy: StructuralStrataPolicy | None = None,
    structural_profiles: Sequence[StructuralProfile] | None = None,
) -> tuple[GenerationRunReceipt, list[int], Path]:
    output_root = tmp_path / "dataset"
    calls = [0]
    monkeypatch.setattr(generate, "orchestrate_generation", _fake_orchestrator(calls))
    receipt = run_governed_generation(
        _request(output_root),
        _curriculum_config(tmp_path),
        output_root=output_root,
        renderer=None,
        max_attempts_per_bucket=1,
        seed=7,
        split_ledger_path=ledger_path or tmp_path / "split-ledger.jsonl",
        structural_policy=structural_policy,
        structural_profiles=structural_profiles,
    )
    return receipt, calls, output_root


def test_pass_orchestrates_and_writes_bound_ledger_and_canonical_bundle(monkeypatch, tmp_path: Path) -> None:
    ledger_path = tmp_path / "governance" / "split-ledger.jsonl"

    receipt, calls, output_root = _run(monkeypatch, tmp_path, ledger_path=ledger_path)

    assert calls == [1]
    assert receipt.outcome == StopOutcome.PASS
    assert receipt.status == "completed"
    assert receipt.scientific_completion is True
    _assert_persisted_receipt(receipt, tmp_path / "governance")
    result = _execution_result(receipt)
    assert result["accepted_count"] == 1
    assert result["structural_coverage"] == {"asserted": False}
    assert Path(result["split_ledger_path"]) == ledger_path
    identity = whole_instance_identity(DOMAIN, PROBLEM)
    assert SplitLedger(ledger_path).assignments() == {identity: "train"}

    bundle = Path(result["canonical_bundle_path"]).read_bytes()
    bundle_manifest = json.loads(Path(result["canonical_bundle_manifest_path"]).read_text(encoding="utf-8"))
    artifact_paths = {item["path"] for item in bundle_manifest["artifacts"]}
    relative_instance = "tiny/train/easy/tiny-train-easy-0000"
    assert artifact_paths == {
        f"{relative_instance}/domain.pddl",
        f"{relative_instance}/problem.pddl",
        "manifests/accepted.json",
        "manifests/split-ledger.jsonl",
        "manifests/summary.json",
    }
    assert str(tmp_path).encode() not in bundle
    assert b"runtime.log" not in bundle
    assert b"elapsed_seconds" not in bundle
    assert output_root.joinpath(generate.ACCEPTED_MANIFEST_FILENAME).exists()


@pytest.mark.parametrize(
    ("outcome", "expected_orchestrator_calls"),
    [
        (StopOutcome.PASS, 1),
        (StopOutcome.VALID_STOP, 0),
        (StopOutcome.INVALID, 0),
        (StopOutcome.ANCESTOR_STOP, 0),
    ],
)
def test_terminal_receipts_are_write_once_per_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    outcome: StopOutcome,
    expected_orchestrator_calls: int,
) -> None:
    output_root = tmp_path / "dataset"
    receipt_root = tmp_path / "governance"
    request = _request(output_root, outcome=outcome, receipt_root=receipt_root)
    calls = [0]
    monkeypatch.setattr(generate, "orchestrate_generation", _fake_orchestrator(calls))
    inputs = {
        "output_root": output_root,
        "renderer": None,
        "max_attempts_per_bucket": 1,
        "seed": 7,
        "split_ledger_path": tmp_path / "split-ledger.jsonl",
    }

    receipt = run_governed_generation(request, _curriculum_config(tmp_path), **inputs)
    original_bytes = receipt.receipt_path.read_bytes()

    with pytest.raises(FileExistsError, match="new attempt_id"):
        run_governed_generation(request, _curriculum_config(tmp_path), **inputs)

    assert calls == [expected_orchestrator_calls]
    assert receipt.receipt_path.read_bytes() == original_bytes


def test_invalid_authorization_never_invokes_generation(monkeypatch, tmp_path: Path) -> None:
    output_root = tmp_path / "dataset"
    output_root.mkdir()
    sentinel = output_root / "must-survive.txt"
    sentinel.write_text("untouched\n", encoding="utf-8")
    receipt_root = tmp_path / "governance"
    calls = [0]
    adapter = TrackingAdapter(tmp_path / "generators" / "tiny")
    monkeypatch.setattr(generate, "orchestrate_generation", _fake_orchestrator(calls))

    receipt = run_governed_generation(
        _request(output_root, authorized=False, receipt_root=receipt_root),
        _curriculum_config(tmp_path),
        output_root=output_root,
        renderer=None,
        max_attempts_per_bucket=1,
        seed=7,
        split_ledger_path=tmp_path / "split-ledger.jsonl",
        registry={"tiny": adapter},
    )

    assert calls == [0]
    assert adapter.call_count == 0
    assert receipt.outcome == StopOutcome.INVALID
    assert receipt.scientific_completion is False
    _assert_persisted_receipt(receipt, receipt_root)
    assert sentinel.read_text(encoding="utf-8") == "untouched\n"
    assert list(output_root.iterdir()) == [sentinel]
    assert not (tmp_path / "split-ledger.jsonl").exists()
    with pytest.raises(ValueError, match="INVALID.*scientific completion"):
        replace(receipt, scientific_completion=True)


@pytest.mark.parametrize("outcome", [StopOutcome.VALID_STOP, StopOutcome.ANCESTOR_STOP])
def test_governed_stop_returns_without_touching_the_output_root(
    monkeypatch,
    tmp_path: Path,
    outcome: StopOutcome,
) -> None:
    output_root = tmp_path / "dataset"
    output_root.mkdir()
    sentinel = output_root / "must-survive.txt"
    sentinel.write_text("untouched\n", encoding="utf-8")
    receipt_root = tmp_path / "governance"
    calls = [0]
    monkeypatch.setattr(generate, "orchestrate_generation", _fake_orchestrator(calls))

    receipt = run_governed_generation(
        _request(output_root, outcome=outcome, receipt_root=receipt_root),
        _curriculum_config(tmp_path),
        output_root=output_root,
        renderer=None,
        max_attempts_per_bucket=1,
        seed=7,
        split_ledger_path=tmp_path / "split-ledger.jsonl",
        force=True,
    )

    assert calls == [0]
    assert receipt.outcome is outcome
    assert receipt.status == "gated_not_run"
    assert receipt.scientific_completion is False
    _assert_persisted_receipt(receipt, receipt_root)
    assert sentinel.read_text(encoding="utf-8") == "untouched\n"
    assert list(output_root.iterdir()) == [sentinel]
    assert not (tmp_path / "split-ledger.jsonl").exists()


def test_conflicting_split_ledger_prevents_completed_pass_receipt(monkeypatch, tmp_path: Path) -> None:
    ledger_path = tmp_path / "split-ledger.jsonl"
    SplitLedger(ledger_path).assign(whole_instance_identity(DOMAIN, PROBLEM), "test")

    receipt, calls, _ = _run(monkeypatch, tmp_path, ledger_path=ledger_path)

    assert calls == [1]
    assert receipt.outcome == StopOutcome.INVALID
    assert receipt.status == "execution_failed"
    assert receipt.scientific_completion is False
    _assert_persisted_receipt(receipt, tmp_path / "governance")
    assert SplitLedger(ledger_path).assignments() == {whole_instance_identity(DOMAIN, PROBLEM): "test"}


def test_supplied_structural_policy_and_profiles_are_enforced(monkeypatch, tmp_path: Path) -> None:
    cell = StructuralCell("short", "narrow", "small")
    policy = StructuralStrataPolicy(
        version="v1",
        horizon_ranges=(StructuralRange("short", 0, 3),),
        branching_ranges=(StructuralRange("narrow", 0, 3),),
        object_count_ranges=(StructuralRange("small", 0, 3),),
        required_cells=(StructuralRequirement("train", cell, 1),),
    )
    profile = StructuralProfile(
        "tiny-train-easy-0000",
        "train",
        1,
        1,
        1,
        legacy_bucket="hard",
    )

    passed, _, _ = _run(
        monkeypatch,
        tmp_path / "pass",
        structural_policy=policy,
        structural_profiles=[profile],
    )
    failed, _, _ = _run(
        monkeypatch,
        tmp_path / "fail",
        structural_policy=policy,
        structural_profiles=[],
    )
    mismatched, _, _ = _run(
        monkeypatch,
        tmp_path / "mismatched",
        structural_policy=policy,
        structural_profiles=[StructuralProfile("unrelated", "train", 1, 1, 1)],
    )

    assert passed.outcome == StopOutcome.PASS
    passed_result = _execution_result(passed)
    coverage = passed_result["structural_coverage"]
    assert coverage.get("complete") is True
    counts = coverage.get("counts")
    assert counts is not None
    assert counts[0]["actual_count"] == 1
    assert failed.outcome == StopOutcome.INVALID
    assert failed.status == "execution_failed"
    assert failed.scientific_completion is False
    _assert_persisted_receipt(failed, tmp_path / "fail" / "governance")
    assert mismatched.outcome == StopOutcome.INVALID
    assert mismatched.scientific_completion is False
    _assert_persisted_receipt(mismatched, tmp_path / "mismatched" / "governance")


def test_canonical_pddl_and_contract_artifacts_replay_across_fresh_roots(monkeypatch, tmp_path: Path) -> None:
    first, _, first_root = _run(monkeypatch, tmp_path / "first")
    second, _, second_root = _run(monkeypatch, tmp_path / "second")

    def artifacts(receipt: GenerationRunReceipt, output_root: Path) -> dict[str, Path]:
        instance_root = output_root / "tiny" / "train" / "easy" / "tiny-train-easy-0000"
        execution_result = _execution_result(receipt)
        return {
            "pddl/domain.pddl": instance_root / "domain.pddl",
            "pddl/problem.pddl": instance_root / "problem.pddl",
            "contracts/canonical-bundle.bin": Path(execution_result["canonical_bundle_path"]),
            "contracts/canonical-bundle-manifest.json": Path(
                execution_result["canonical_bundle_manifest_path"]
            ),
        }

    bundle = verify_canonical_replay(
        artifacts(first, first_root),
        artifacts(second, second_root),
    )

    assert str(tmp_path).encode() not in bundle
    assert b"runtime.log" not in bundle
    assert b"elapsed_seconds" not in bundle
