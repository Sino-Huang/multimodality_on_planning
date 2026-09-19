"""Curriculum PDDL generation orchestration."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

from .adapters import GenerationSpec, GeneratorAdapter, GeneratorRejection, build_domain_registry
from .config import CurriculumConfig, DomainConfig
from .difficulty import DIFFICULTY_BUCKETS, hybrid_measured_percentile
from .governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    RunReceipt,
    StopOutcome,
    evaluate_execution_permission,
)
from .metadata import (
    DUPLICATE_PROBLEM_REASON,
    AcceptedInstanceMetadata,
    RejectedCandidateMetadata,
    SummaryMetadata,
    build_candidate_id,
    build_instance_id,
    build_summary_metadata,
    load_metadata_payload,
    write_result_metadata,
    write_summary_metadata,
)
from .normalization import AcceptedProblemIdentity, AcceptedProblemIndex, normalize_pddl
from .rendering import Renderer, gate_rendered_candidate, require_rendering_preflight
from .replay import ArtifactSet, build_canonical_bundle, build_replay_contract
from .selection import select_stratified_by_measured_bucket
from .splits import SplitLedger, whole_instance_identity
from .structural import StructuralProfile, StructuralStrataPolicy, derive_structural_profiles, verify_structural_coverage


def _canonical_json(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _governed_receipt_path(receipt_root: Path, binding: Mapping[str, object]) -> Path:
    return receipt_root / f"generation-run-{binding['contract_id']}-{binding['attempt_id']}.json"


def _validated_receipt_root(receipt_root: Path | str, binding: ReceiptBinding) -> Path:
    raw_root = os.fspath(receipt_root)
    if not raw_root or raw_root != raw_root.strip():
        raise ValueError("receipt_root must be non-empty canonical text")
    root = Path(raw_root)
    if not root.is_absolute():
        raise ValueError("receipt_root must be absolute")
    resolved_root = root.resolve()
    if root != resolved_root:
        raise ValueError("receipt_root must already be resolved")

    output_root = Path(binding.output_root).resolve()
    if resolved_root == output_root or output_root in resolved_root.parents:
        raise ValueError("receipt_root must not be binding.output_root or one of its descendants")
    return resolved_root


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """Authorization inputs for one governed generation attempt."""

    binding: ReceiptBinding
    gate_receipt: GateReceipt | object
    authorization_receipt: AuthorizationReceipt | object | None
    receipt_root: Path | str
    ancestor_receipt_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ReceiptBinding):
            raise TypeError("binding must be a ReceiptBinding")
        object.__setattr__(self, "receipt_root", _validated_receipt_root(self.receipt_root, self.binding))


@dataclass(frozen=True, slots=True)
class GenerationRunReceipt:
    """Persisted completion result layered on the authorization-only API."""

    outcome: StopOutcome
    status: str
    binding: ReceiptBinding
    scientific_completion: bool
    receipt_path: Path
    authorization_receipt: RunReceipt
    execution_result: dict[str, object] | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.outcome is StopOutcome.INVALID and self.scientific_completion:
            raise ValueError("INVALID can never claim scientific completion")
        if self.scientific_completion and not (
            self.outcome is StopOutcome.PASS and self.status == "completed"
        ):
            raise ValueError("scientific completion requires a completed PASS")

    def to_dict(self) -> dict[str, object]:
        return {
            "authorization_receipt": self.authorization_receipt.to_dict(),
            "binding": self.binding.to_dict(),
            "execution_result": self.execution_result,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "receipt_path": str(self.receipt_path),
            "receipt_type": "generation_run",
            "scientific_completion": self.scientific_completion,
            "status": self.status,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())


class ValidExecutionStop(Exception):
    """Typed, governed stop raised after an authorized execution has started."""

    def __init__(
        self,
        reason: str,
        *,
        status: str = "resource_exhaustion",
        execution_result: Mapping[str, object] | None = None,
    ) -> None:
        if not isinstance(reason, str) or not reason or reason != reason.strip():
            raise ValueError("valid execution stop reason must be non-empty canonical text")
        if not isinstance(status, str) or not status or status != status.strip():
            raise ValueError("valid execution stop status must be non-empty canonical text")
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.execution_result = None if execution_result is None else dict(execution_result)


def _persist_governed_receipt(receipt: GenerationRunReceipt) -> GenerationRunReceipt:
    _atomic_write(receipt.receipt_path, (receipt.canonical_json() + "\n").encode("utf-8"))
    return receipt


def _reservation_payload(request: GenerationRequest, receipt_path: Path) -> bytes:
    return _canonical_bytes(
        {
            "binding": request.binding.to_dict(),
            "receipt_path": str(receipt_path),
            "receipt_type": "generation_run_reservation",
            "status": "reserved",
        }
    )


def _reserve_attempt(request: GenerationRequest, receipt_path: Path) -> None:
    try:
        _atomic_create(receipt_path, _reservation_payload(request, receipt_path))
    except FileExistsError as error:
        raise _terminal_receipt_exists_error(receipt_path, request.binding) from error


def _terminal_receipt_exists_error(receipt_path: Path, binding: ReceiptBinding) -> FileExistsError:
    return FileExistsError(
        f"Terminal generation receipt already exists for attempt {binding.attempt_id!r} at "
        f"{receipt_path}; use a new attempt_id"
    )


def run_authorized_generation(
    request: GenerationRequest,
    execute: Callable[[], object],
) -> GenerationRunReceipt:
    """Authorize first, then persist a serializable completion receipt."""

    if not isinstance(request, GenerationRequest):
        raise TypeError("request must be a GenerationRequest")
    receipt_root = cast(Path, request.receipt_root)
    receipt_path = _governed_receipt_path(receipt_root, request.binding.to_dict())
    _reserve_attempt(request, receipt_path)

    authorization = evaluate_execution_permission(
        binding=request.binding,
        gate_receipt=request.gate_receipt,
        authorization_receipt=request.authorization_receipt,
        ancestor_receipt_id=request.ancestor_receipt_id,
    )
    if not authorization.start_permitted:
        return _persist_governed_receipt(
            GenerationRunReceipt(
                outcome=authorization.outcome,
                status=authorization.run_state.replace("-", "_"),
                binding=request.binding,
                scientific_completion=False,
                receipt_path=receipt_path,
                authorization_receipt=authorization,
                reason=authorization.reason,
            )
        )
    try:
        raw_result = execute()
        execution_result = json.loads(_canonical_json(raw_result))
    except ValidExecutionStop as stop:
        execution_result = (
            None
            if stop.execution_result is None
            else json.loads(_canonical_json(stop.execution_result))
        )
        return _persist_governed_receipt(
            GenerationRunReceipt(
                outcome=StopOutcome.VALID_STOP,
                status=stop.status,
                binding=request.binding,
                scientific_completion=False,
                receipt_path=receipt_path,
                authorization_receipt=authorization,
                execution_result=execution_result,
                reason=stop.reason,
            )
        )
    except Exception as error:
        return _persist_governed_receipt(
            GenerationRunReceipt(
                outcome=StopOutcome.INVALID,
                status="execution_failed",
                binding=request.binding,
                scientific_completion=False,
                receipt_path=receipt_path,
                authorization_receipt=authorization,
                reason=f"execute_raised:{type(error).__name__}",
            )
        )
    return _persist_governed_receipt(
        GenerationRunReceipt(
            outcome=StopOutcome.PASS,
            status="completed",
            binding=request.binding,
            scientific_completion=True,
            receipt_path=receipt_path,
            authorization_receipt=authorization,
            execution_result=execution_result,
        )
    )

GENERATION_REJECTION_STAGE = "generation"
DEDUPE_REJECTION_STAGE = "dedupe"
SELECTION_REJECTION_STAGE = "selection"
SELECTION_NOT_SELECTED_REASON = "selection_not_selected"
REJECTIONS_FILENAME = "rejections.jsonl"
ACCEPTED_MANIFEST_FILENAME = "accepted_manifest.jsonl"
SUMMARY_FILENAME = "summary.json"
STAGING_DIRNAME = ".staging"


@dataclass(frozen=True)
class GenerationRunResult:
    accepted_instances: tuple[AcceptedInstanceMetadata, ...]
    rejected_candidates: tuple[RejectedCandidateMetadata, ...]
    summary: SummaryMetadata
    output_root: Path
    accepted_manifest_path: Path
    rejections_path: Path
    summary_path: Path


def run_governed_generation(
    request: GenerationRequest,
    curriculum_config: CurriculumConfig,
    *,
    output_root: Path | str,
    renderer: Renderer | None,
    max_attempts_per_bucket: int,
    seed: int,
    split_ledger_path: Path | str,
    structural_policy: StructuralStrataPolicy | None = None,
    structural_profiles: Sequence[StructuralProfile] | None = None,
    structural_policy_path: Path | str | None = None,
    force: bool = False,
    domains: Sequence[str] | None = None,
    splits: Sequence[str] | None = None,
    quotas_by_split: Mapping[str, Mapping[str, int]] | None = None,
    candidate_multiplier: int | None = None,
    registry: Mapping[str, GeneratorAdapter] | None = None,
) -> GenerationRunReceipt:
    """Run the legacy orchestrator only after authorization and bind its outputs.

    A completed PASS requires artifact-derived structural coverage under the
    supplied policy. Supplied profiles are an optional exact assertion.
    """

    resolved_output_root = Path(output_root).resolve()
    resolved_ledger_path = Path(split_ledger_path).resolve()
    _validate_external_generation_path(resolved_ledger_path, output_root=resolved_output_root, name="split_ledger_path")

    def execute() -> dict[str, object]:
        if Path(request.binding.output_root).resolve() != resolved_output_root:
            raise ValueError("generation output_root must match the governance binding")
        if structural_policy is None:
            raise ValueError("structural_policy is required for PASS")
        if structural_policy_path is None:
            raise ValueError("structural_policy_path is required for PASS replay")
        resolved_policy_path = Path(structural_policy_path).resolve()
        if not resolved_policy_path.is_file():
            raise ValueError("structural policy must be a committed file for replay")
        policy_payload = json.loads(resolved_policy_path.read_text(encoding="utf-8"))
        if policy_payload != structural_policy.to_dict():
            raise ValueError("structural_policy_path must semantically match structural_policy")

        selected_domain_configs = _select_domains(curriculum_config, domains)
        selected_split_names = _select_splits(curriculum_config, splits)
        resolved_quotas = _resolve_quotas(curriculum_config, selected_split_names, quotas_by_split)
        resolved_candidate_multiplier = (
            curriculum_config.candidate_multiplier if candidate_multiplier is None else candidate_multiplier
        )
        replay_contract = build_replay_contract(
            contract_id=request.binding.contract_id,
            seed=seed,
            max_attempts_per_bucket=max_attempts_per_bucket,
            candidate_multiplier=resolved_candidate_multiplier,
            require_rendering=curriculum_config.require_rendering,
            selected_domains=[domain.domain_id for domain in selected_domain_configs],
            selected_splits=selected_split_names,
            quotas_by_split=resolved_quotas,
            source_artifacts=_replay_source_artifacts(
                curriculum_config=curriculum_config,
                selected_domains=selected_domain_configs,
                structural_policy_path=resolved_policy_path,
            ),
        )
        split_ledger = SplitLedger(resolved_ledger_path)

        def validate_split_assignments(instances: Sequence[AcceptedInstanceMetadata]) -> None:
            assignments = [
                (whole_instance_identity(Path(instance.domain_path), Path(instance.problem_path)), instance.split)
                for instance in instances
            ]
            for identity, split in assignments:
                existing = split_ledger.split_for(identity)
                if existing is not None and existing != split:
                    raise ValueError(
                        f"Identity {identity!r} is already assigned to {existing!r}; cannot reassign it to {split!r}"
                    )
            for identity, split in assignments:
                split_ledger.assign(identity, split)

        result = orchestrate_generation(
            curriculum_config,
            output_root=resolved_output_root,
            renderer=renderer,
            max_attempts_per_bucket=max_attempts_per_bucket,
            seed=seed,
            force=force,
            domains=domains,
            splits=splits,
            quotas_by_split=quotas_by_split,
            candidate_multiplier=candidate_multiplier,
            registry=registry,
            split_validator=validate_split_assignments,
        )
        return _bind_governed_outputs(
            result,
            split_ledger_path=resolved_ledger_path,
            structural_policy=structural_policy,
            structural_profiles=structural_profiles,
            replay_contract=replay_contract,
        )

    return run_authorized_generation(request, execute)


def _bind_governed_outputs(
    result: GenerationRunResult,
    *,
    split_ledger_path: Path | str,
    structural_policy: StructuralStrataPolicy,
    structural_profiles: Sequence[StructuralProfile] | None,
    replay_contract: bytes,
) -> dict[str, object]:
    output_root = result.output_root.resolve()
    ledger_path = Path(split_ledger_path).resolve()
    ledger = SplitLedger(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.open("a", encoding="utf-8").close()
    accepted_records: list[dict[str, str]] = []
    pddl_artifacts: dict[str, Path] = {}
    expected_assignments: dict[str, str] = {}

    for instance in result.accepted_instances:
        domain_path = Path(instance.domain_path).resolve()
        problem_path = Path(instance.problem_path).resolve()
        domain_relative = _relative_artifact_path(domain_path, output_root)
        problem_relative = _relative_artifact_path(problem_path, output_root)
        identity = whole_instance_identity(domain_path, problem_path)
        ledger.assign(identity, instance.split)
        expected_assignments[identity] = instance.split
        accepted_records.append(
            {
                "domain_path": domain_relative,
                "identity": identity,
                "instance_id": instance.instance_id,
                "problem_path": problem_relative,
                "split": instance.split,
            }
        )
        pddl_artifacts[domain_relative] = domain_path
        pddl_artifacts[problem_relative] = problem_path

    verified_ledger = SplitLedger(ledger_path)
    for identity, split in expected_assignments.items():
        if verified_ledger.split_for(identity) != split:
            raise ValueError(f"split ledger verification failed for {identity}")

    derived_profiles = derive_structural_profiles(result.accepted_instances)
    accepted_splits = {instance.instance_id: instance.split for instance in result.accepted_instances}
    derived_by_id = {profile.instance_id: profile for profile in derived_profiles}
    derived_splits = {instance_id: profile.split for instance_id, profile in derived_by_id.items()}
    if len(derived_by_id) != len(derived_profiles):
        raise ValueError("derived structural profiles must have unique instance ids")
    if derived_splits != accepted_splits:
        raise ValueError("derived structural profiles must exactly match accepted instance ids and splits")
    if structural_profiles is not None:
        asserted_by_id = {profile.instance_id: profile for profile in structural_profiles}
        if len(asserted_by_id) != len(structural_profiles) or asserted_by_id != derived_by_id:
            raise ValueError("supplied structural profiles must exactly match artifact-derived profiles")
    coverage = verify_structural_coverage(structural_policy, derived_profiles)
    structural_result = {"asserted": True, **coverage.to_dict()}
    structural_profiles_payload = [
        profile.to_dict() for profile in sorted(derived_profiles, key=lambda profile: profile.instance_id)
    ]

    accepted_records.sort(key=lambda item: (item["instance_id"], item["domain_path"], item["problem_path"]))
    summary_payload = _canonical_summary_payload(result.summary)
    artifacts: dict[str, bytes | Path] = {
        **pddl_artifacts,
        "contracts/generation-replay.json": replay_contract,
        "manifests/accepted.json": _canonical_bytes(accepted_records),
        "manifests/split-ledger.jsonl": ledger_path.read_bytes(),
        "manifests/structural-profiles.json": _canonical_bytes(structural_profiles_payload),
        "manifests/summary.json": _canonical_bytes(summary_payload),
    }
    bundle = build_canonical_bundle(artifacts)
    replay_root = output_root / ".replay"
    bundle_path = replay_root / "canonical-bundle.bin"
    bundle_manifest_path = replay_root / "canonical-bundle-manifest.json"
    bundle_manifest = {
        "artifacts": [
            {
                "path": path,
                "size_bytes": len(_artifact_bytes(source)),
            }
            for path, source in sorted(artifacts.items())
        ],
        "bundle_size_bytes": len(bundle),
        "format": "canonical-generation-replay-v1",
    }
    _atomic_write(bundle_path, bundle)
    _atomic_write(bundle_manifest_path, _canonical_bytes(bundle_manifest))

    return {
        "accepted_count": len(result.accepted_instances),
        "accepted_manifest_path": str(result.accepted_manifest_path),
        "canonical_bundle_manifest_path": str(bundle_manifest_path),
        "canonical_bundle_path": str(bundle_path),
        "output_root": str(output_root),
        "rejected_count": len(result.rejected_candidates),
        "rejections_path": str(result.rejections_path),
        "split_ledger_path": str(ledger_path),
        "structural_coverage": structural_result,
        "summary_path": str(result.summary_path),
    }


def _validate_external_generation_path(path: Path, *, output_root: Path, name: str) -> None:
    if path == output_root or output_root in path.parents:
        raise ValueError(f"{name} must be outside output_root")


def _canonical_summary_payload(summary: SummaryMetadata) -> dict[str, object]:
    return {
        "accepted_by_bucket": dict(summary.accepted_by_bucket),
        "accepted_by_domain": dict(summary.accepted_by_domain),
        "accepted_by_split": dict(summary.accepted_by_split),
        "accepted_total": summary.accepted_total,
        "domains_completed": summary.domains_completed,
        "duplicate_accepted_problems": summary.duplicate_accepted_problems,
        "rejected_by_reason": dict(summary.rejected_by_reason),
        "rejected_total": summary.rejected_total,
        "render_failed_accepted": summary.render_failed_accepted,
        "resumed_accepted_total": summary.resumed_accepted_total,
    }


def _replay_source_artifacts(
    *,
    curriculum_config: CurriculumConfig,
    selected_domains: Sequence[DomainConfig],
    structural_policy_path: Path,
) -> ArtifactSet:
    config_path = curriculum_config.config_path.resolve()
    if not config_path.is_file():
        raise ValueError("curriculum config must be a committed file for replay")
    artifacts: dict[str, Path] = {
        "config/curriculum": config_path,
        "policy/structural": structural_policy_path,
    }
    for domain in selected_domains:
        render_profile_path = domain.render_profile_path.resolve()
        if not render_profile_path.is_file():
            raise ValueError(f"render profile must be a committed file for replay: {render_profile_path}")
        artifacts[f"render-profiles/{domain.domain_id}.pddl"] = render_profile_path
    return artifacts


def _relative_artifact_path(path: Path, output_root: Path) -> str:
    relative = path.relative_to(output_root).as_posix()
    if path.suffix.lower() != ".pddl":
        raise ValueError(f"governed instance artifact is not PDDL: {relative}")
    return relative


def _canonical_bytes(value: object) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _artifact_bytes(source: bytes | Path) -> bytes:
    return source if isinstance(source, bytes) else source.read_bytes()


def _atomic_write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _atomic_create(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def orchestrate_generation(
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
    split_validator: Callable[[Sequence[AcceptedInstanceMetadata]], None] | None = None,
) -> GenerationRunResult:
    if max_attempts_per_bucket <= 0:
        raise ValueError("max_attempts_per_bucket must be positive")
    if curriculum_config.require_rendering and renderer is None:
        raise ValueError("renderer is required when curriculum_config.require_rendering is true")

    resolved_output_root = Path(output_root).resolve()
    if force and resolved_output_root.exists():
        shutil.rmtree(resolved_output_root)
    resolved_output_root.mkdir(parents=True, exist_ok=True)

    selected_domains = _select_domains(curriculum_config, domains)
    selected_splits = _select_splits(curriculum_config, splits)
    resolved_quotas = _resolve_quotas(curriculum_config, selected_splits, quotas_by_split)
    resolved_candidate_multiplier = (
        curriculum_config.candidate_multiplier if candidate_multiplier is None else candidate_multiplier
    )
    if resolved_candidate_multiplier <= 0:
        raise ValueError("candidate_multiplier must be positive")

    require_rendering_preflight(
        replace(curriculum_config, domains=selected_domains),
        renderer=renderer,
        timeout_seconds=curriculum_config.timeouts.render_seconds,
    )

    domain_registry = dict(registry or build_domain_registry(replace(curriculum_config, domains=selected_domains)))
    _require_adapter_readiness(domain_registry, selected_domains)
    resume_splits = tuple(curriculum_config.splits)
    existing_accepted = [] if force else _load_existing_accepted(resolved_output_root, selected_domains, resume_splits)
    existing_rejections = [] if force else _load_rejections(resolved_output_root / REJECTIONS_FILENAME)

    accepted_instances: list[AcceptedInstanceMetadata] = list(existing_accepted)
    rejected_candidates: list[RejectedCandidateMetadata] = list(existing_rejections)
    problem_index = AcceptedProblemIndex(
        AcceptedProblemIdentity(
            normalized_problem_text=instance.normalized_problem_text,
            instance_id=instance.instance_id,
            domain_id=instance.domain_id,
            split=instance.split,
            bucket=instance.bucket,
        )
        for instance in existing_accepted
        if instance.normalized_problem_text
    )

    next_attempt_index = _build_next_attempt_index(existing_accepted, existing_rejections, selected_domains, selected_splits)
    historical_attempt_counts = _build_historical_attempt_counts(existing_accepted, existing_rejections)
    selection_reports: dict[str, dict[str, dict[str, Any]]] = {}

    for domain in selected_domains:
        adapter = domain_registry.get(domain.domain_id)
        if adapter is None:
            raise KeyError(f"No adapter registered for domain '{domain.domain_id}'")
        adapter.prepare()

        for split in selected_splits:
            remaining_quotas = _remaining_quotas(accepted_instances, domain_id=domain.domain_id, split=split, quotas=resolved_quotas[split])
            if sum(remaining_quotas.values()) == 0:
                selection_reports.setdefault(domain.domain_id, {})[split] = {
                    "requested_counts": {bucket: int(count) for bucket, count in resolved_quotas[split].items()},
                    "remaining_quotas": {bucket: int(count) for bucket, count in remaining_quotas.items()},
                    "selected_counts": {bucket: 0 for bucket in DIFFICULTY_BUCKETS},
                    "available_counts": {bucket: 0 for bucket in DIFFICULTY_BUCKETS},
                    "incomplete_buckets": [],
                    "attempt_counts": {
                        bucket: historical_attempt_counts[(domain.domain_id, split, bucket)]
                        for bucket in DIFFICULTY_BUCKETS
                    },
                    "resumed_only": True,
                }
                continue

            pool_candidates: list[AcceptedInstanceMetadata] = []
            pool_by_text: dict[str, AcceptedInstanceMetadata] = {}
            current_attempt_counts = {
                bucket: historical_attempt_counts[(domain.domain_id, split, bucket)]
                for bucket in DIFFICULTY_BUCKETS
            }

            for target_bucket in DIFFICULTY_BUCKETS:
                pool_target_size = int(remaining_quotas.get(target_bucket, 0)) * resolved_candidate_multiplier
                if pool_target_size == 0:
                    continue
                bucket_pool_count = 0
                while bucket_pool_count < pool_target_size and current_attempt_counts[target_bucket] < max_attempts_per_bucket:
                    attempt_index = next_attempt_index[(domain.domain_id, split)]
                    next_attempt_index[(domain.domain_id, split)] += 1
                    current_attempt_counts[target_bucket] += 1

                    source_candidate_id = build_candidate_id(domain.domain_id, split, target_bucket, attempt_index)
                    candidate_output_dir = _candidate_output_dir(
                        resolved_output_root,
                        domain_id=domain.domain_id,
                        split=split,
                        target_bucket=target_bucket,
                        candidate_id=source_candidate_id,
                    )
                    candidate_seed = _derive_candidate_seed(
                        seed=seed,
                        domain_id=domain.domain_id,
                        split=split,
                        target_bucket=target_bucket,
                        attempt_index=attempt_index,
                        seed_range=curriculum_config.seed_range,
                    )
                    spec = GenerationSpec(
                        candidate_id=source_candidate_id,
                        output_dir=candidate_output_dir,
                        timeout_seconds=curriculum_config.timeouts.generator_seconds,
                        seed=candidate_seed if adapter.supports_seed() else None,
                        extra={
                            "domain_id": domain.domain_id,
                            "preset_id": target_bucket,
                            "split": split,
                            "target_bucket": target_bucket,
                            "attempt_index": attempt_index,
                            "bucket_attempt_index": current_attempt_counts[target_bucket] - 1,
                        },
                    )

                    normalized_or_rejection = adapter.normalize_outputs(adapter.generate_candidate(spec))
                    if isinstance(normalized_or_rejection, GeneratorRejection):
                        rejected_candidates.append(
                            _build_generation_rejection(
                                rejection=normalized_or_rejection,
                                domain_id=domain.domain_id,
                                split=split,
                                bucket=target_bucket,
                                attempt_index=attempt_index,
                            )
                        )
                        continue

                    candidate_renderer = cast(Renderer, renderer)
                    rendered_or_rejection = gate_rendered_candidate(
                        candidate=normalized_or_rejection,
                        split=split,
                        bucket=target_bucket,
                        index=attempt_index,
                        attempt_index=attempt_index,
                        renderer=candidate_renderer,
                        render_profile_path=domain.render_profile_path,
                        timeout_seconds=curriculum_config.timeouts.render_seconds,
                        extra={
                            "orchestrator": {
                                "source_candidate_id": source_candidate_id,
                                "source_target_bucket": target_bucket,
                                "staging_output_dir": str(candidate_output_dir),
                            }
                        },
                    )
                    if isinstance(rendered_or_rejection, RejectedCandidateMetadata):
                        rejected_candidates.append(rendered_or_rejection)
                        continue

                    normalized_candidate = _annotate_identity(rendered_or_rejection)
                    duplicate_rejection = _check_duplicate_candidate(
                        candidate=normalized_candidate,
                        accepted_problem_index=problem_index,
                        pool_by_text=pool_by_text,
                    )
                    if duplicate_rejection is not None:
                        rejected_candidates.append(duplicate_rejection)
                        continue

                    pool_by_text[normalized_candidate.normalized_problem_text] = normalized_candidate
                    pool_candidates.append(normalized_candidate)
                    bucket_pool_count += 1

            measured_pool = hybrid_measured_percentile(pool_candidates) if pool_candidates else ()
            selection_result = select_stratified_by_measured_bucket(
                measured_pool,
                {split: remaining_quotas},
            )
            selected_candidate_ids = {instance.candidate_id for instance in selection_result.selected_instances}
            for candidate in measured_pool:
                if candidate.candidate_id in selected_candidate_ids:
                    continue
                rejected_candidates.append(_build_selection_rejection(candidate))

            if split_validator is not None:
                split_validator(selection_result.selected_instances)

            for selected in selection_result.selected_instances:
                finalized = _finalize_selected_candidate(
                    candidate=selected,
                    output_root=resolved_output_root,
                    force=force,
                    existing_instances=accepted_instances,
                )
                write_result_metadata(_accepted_result_path(resolved_output_root, finalized), finalized, force=force)
                accepted_instances.append(finalized)
                if finalized.normalized_problem_text:
                    problem_index.register(
                        normalized_problem_text=finalized.normalized_problem_text,
                        instance_id=finalized.instance_id,
                        domain_id=finalized.domain_id,
                        split=finalized.split,
                        bucket=finalized.bucket,
                        duplicate_identifier=finalized.candidate_id,
                    )

            selection_reports.setdefault(domain.domain_id, {})[split] = {
                "requested_counts": {bucket: int(count) for bucket, count in selection_result.requested_counts.get(domain.domain_id, {}).get(split, {}).items()},
                "remaining_quotas": {bucket: int(count) for bucket, count in remaining_quotas.items()},
                "selected_counts": {bucket: int(count) for bucket, count in selection_result.selected_counts.get(domain.domain_id, {}).get(split, {}).items()},
                "available_counts": {bucket: int(count) for bucket, count in selection_result.available_counts.get(domain.domain_id, {}).get(split, {}).items()},
                "incomplete_buckets": [
                    summary.to_dict()
                    for summary in selection_result.incomplete_buckets
                    if summary.domain_id == domain.domain_id and summary.split == split
                ],
                "attempt_counts": {bucket: int(count) for bucket, count in current_attempt_counts.items()},
                "pool_size": len(pool_candidates),
                "selected_pool_size": len(selection_result.selected_instances),
                "resumed_only": False,
            }

    duplicate_accepted_problems = _count_duplicate_problems(accepted_instances)
    domains_completed = _count_completed_domains(accepted_instances, selected_domains, selected_splits, resolved_quotas)
    summary = build_summary_metadata(
        accepted_instances=_sorted_accepted_instances(accepted_instances),
        rejected_candidates=_sorted_rejections(rejected_candidates),
        duplicate_accepted_problems=duplicate_accepted_problems,
        resumed_accepted_total=len(existing_accepted),
        domains_completed=domains_completed,
        extra={
            "selection": selection_reports,
            "selected_domains": [domain.domain_id for domain in selected_domains],
            "selected_splits": list(selected_splits),
            "max_attempts_per_bucket": max_attempts_per_bucket,
            "candidate_multiplier": resolved_candidate_multiplier,
        },
    )

    accepted_manifest_path = resolved_output_root / ACCEPTED_MANIFEST_FILENAME
    rejections_path = resolved_output_root / REJECTIONS_FILENAME
    summary_path = resolved_output_root / SUMMARY_FILENAME
    _write_jsonl(accepted_manifest_path, [instance.to_dict() for instance in _sorted_accepted_instances(accepted_instances)])
    _write_jsonl(rejections_path, [rejection.to_dict() for rejection in _sorted_rejections(rejected_candidates)])
    write_summary_metadata(summary_path, summary)

    return GenerationRunResult(
        accepted_instances=tuple(_sorted_accepted_instances(accepted_instances)),
        rejected_candidates=tuple(_sorted_rejections(rejected_candidates)),
        summary=summary,
        output_root=resolved_output_root,
        accepted_manifest_path=accepted_manifest_path,
        rejections_path=rejections_path,
        summary_path=summary_path,
    )


def _select_domains(curriculum_config: CurriculumConfig, domains: Sequence[str] | None) -> tuple[DomainConfig, ...]:
    if domains is None:
        return curriculum_config.domains
    requested = tuple(domain.strip() for domain in domains if domain.strip())
    domain_map = {domain.domain_id: domain for domain in curriculum_config.domains}
    missing = [domain_id for domain_id in requested if domain_id not in domain_map]
    if missing:
        raise KeyError(f"Unknown domain ids requested: {missing}")
    return tuple(domain_map[domain_id] for domain_id in requested)


def _require_adapter_readiness(
    domain_registry: Mapping[str, GeneratorAdapter],
    selected_domains: Sequence[DomainConfig],
) -> None:
    issues: list[str] = []
    for domain in selected_domains:
        adapter = domain_registry.get(domain.domain_id)
        if adapter is None:
            continue

        inspect_readiness = getattr(adapter, "inspect_readiness", None)
        if not callable(inspect_readiness):
            continue

        capability = inspect_readiness()
        if bool(getattr(capability, "ready", True)):
            continue

        failures = cast(Sequence[object], getattr(capability, "readiness_failures", ()))
        if not failures:
            issues.append(f"{domain.domain_id}: adapter readiness failed")
            continue

        for failure in failures:
            code = str(getattr(failure, "code", "unknown"))
            message = str(getattr(failure, "message", "adapter readiness failed"))
            path = getattr(failure, "path", None)
            path_suffix = f" ({path})" if path else ""
            issues.append(f"{domain.domain_id}: {code}: {message}{path_suffix}")

    if issues:
        raise RuntimeError("Generator readiness preflight failed: " + "; ".join(issues))


def _select_splits(curriculum_config: CurriculumConfig, splits: Sequence[str] | None) -> tuple[str, ...]:
    if splits is None:
        return tuple(curriculum_config.splits)
    requested = tuple(split.strip() for split in splits if split.strip())
    missing = [split for split in requested if split not in curriculum_config.splits]
    if missing:
        raise KeyError(f"Unknown splits requested: {missing}")
    return requested


def _resolve_quotas(
    curriculum_config: CurriculumConfig,
    selected_splits: Sequence[str],
    quotas_by_split: Mapping[str, Mapping[str, int]] | None,
) -> dict[str, dict[str, int]]:
    resolved: dict[str, dict[str, int]] = {}
    for split in selected_splits:
        base = dict(curriculum_config.splits[split].buckets)
        if quotas_by_split and split in quotas_by_split:
            override = quotas_by_split[split]
            base = {bucket: int(override.get(bucket, 0)) for bucket in DIFFICULTY_BUCKETS}
        resolved[split] = base
    return resolved


def _build_next_attempt_index(
    accepted_instances: Sequence[AcceptedInstanceMetadata],
    rejected_candidates: Sequence[RejectedCandidateMetadata],
    selected_domains: Sequence[DomainConfig],
    selected_splits: Sequence[str],
) -> dict[tuple[str, str], int]:
    next_attempt_index = {(domain.domain_id, split): 0 for domain in selected_domains for split in selected_splits}
    for instance in accepted_instances:
        key = (instance.domain_id, instance.split)
        next_attempt_index[key] = max(next_attempt_index.get(key, 0), instance.attempt_index + 1)
    for rejection in rejected_candidates:
        key = (rejection.domain_id, rejection.split)
        next_attempt_index[key] = max(next_attempt_index.get(key, 0), rejection.attempt_index + 1)
    return next_attempt_index


def _build_historical_attempt_counts(
    accepted_instances: Sequence[AcceptedInstanceMetadata],
    rejected_candidates: Sequence[RejectedCandidateMetadata],
) -> Counter[tuple[str, str, str]]:
    counts: Counter[tuple[str, str, str]] = Counter()
    for instance in accepted_instances:
        target_bucket = instance.difficulty_target or instance.extra.get("orchestrator", {}).get("source_target_bucket") or instance.bucket
        counts[(instance.domain_id, instance.split, str(target_bucket))] += 1
    for rejection in rejected_candidates:
        counts[(rejection.domain_id, rejection.split, rejection.bucket)] += 1
    return counts


def _remaining_quotas(
    accepted_instances: Sequence[AcceptedInstanceMetadata],
    *,
    domain_id: str,
    split: str,
    quotas: Mapping[str, int],
) -> dict[str, int]:
    accepted_counts = Counter(
        instance.bucket
        for instance in accepted_instances
        if instance.domain_id == domain_id and instance.split == split
    )
    return {
        bucket: max(0, int(quotas.get(bucket, 0)) - int(accepted_counts.get(bucket, 0)))
        for bucket in DIFFICULTY_BUCKETS
    }


def _candidate_output_dir(
    output_root: Path,
    *,
    domain_id: str,
    split: str,
    target_bucket: str,
    candidate_id: str,
) -> Path:
    return output_root / STAGING_DIRNAME / domain_id / split / target_bucket / candidate_id


def _derive_candidate_seed(
    *,
    seed: int,
    domain_id: str,
    split: str,
    target_bucket: str,
    attempt_index: int,
    seed_range: Any,
) -> int:
    span = int(seed_range.stop) - int(seed_range.start) + 1
    if span <= 0:
        raise ValueError("seed_range must span at least one integer")
    token = f"{seed}:{domain_id}:{split}:{target_bucket}:{attempt_index}"
    folded = sum((index + 1) * ord(character) for index, character in enumerate(token))
    return int(seed_range.start) + (folded % span)


def _build_generation_rejection(
    *,
    rejection: GeneratorRejection,
    domain_id: str,
    split: str,
    bucket: str,
    attempt_index: int,
) -> RejectedCandidateMetadata:
    return RejectedCandidateMetadata(
        candidate_id=rejection.candidate_id,
        domain_id=domain_id,
        split=split,
        bucket=bucket,
        attempt_index=attempt_index,
        seed=rejection.seed,
        rejection_reason=rejection.rejection_reason,
        rejection_stage=GENERATION_REJECTION_STAGE,
        message=rejection.message,
        generator_command=rejection.generator_command,
        generator_cwd=str(rejection.generator_cwd),
        stdout_path=str(rejection.stdout_path),
        stderr_path=str(rejection.stderr_path),
        details=dict(rejection.details),
    )


def _annotate_identity(candidate: AcceptedInstanceMetadata) -> AcceptedInstanceMetadata:
    return replace(
        candidate,
        normalized_problem_text=normalize_pddl(Path(candidate.problem_path).read_text(encoding="utf-8")),
    )


def _check_duplicate_candidate(
    *,
    candidate: AcceptedInstanceMetadata,
    accepted_problem_index: AcceptedProblemIndex,
    pool_by_text: Mapping[str, AcceptedInstanceMetadata],
) -> RejectedCandidateMetadata | None:
    if candidate.normalized_problem_text in pool_by_text:
        existing = pool_by_text[candidate.normalized_problem_text]
        return RejectedCandidateMetadata(
            candidate_id=candidate.candidate_id,
            domain_id=candidate.domain_id,
            split=candidate.split,
            bucket=candidate.bucket,
            attempt_index=candidate.attempt_index,
            seed=candidate.seed,
            rejection_reason=DUPLICATE_PROBLEM_REASON,
            rejection_stage=DEDUPE_REJECTION_STAGE,
            message="Normalized problem already exists in the current candidate pool.",
            normalized_problem_text=candidate.normalized_problem_text,
            duplicate_of_instance_id=existing.candidate_id,
            generator_command=candidate.generator_command,
            generator_cwd=candidate.generator_cwd,
            stdout_path=candidate.stdout_path,
            stderr_path=candidate.stderr_path,
            details={
                "existing_candidate_id": existing.candidate_id,
                "normalized_problem_text": candidate.normalized_problem_text,
                "source": "candidate_pool",
            },
        )

    existing = accepted_problem_index.get(candidate.normalized_problem_text)
    if existing is None:
        return None

    return RejectedCandidateMetadata(
        candidate_id=candidate.candidate_id,
        domain_id=candidate.domain_id,
        split=candidate.split,
        bucket=candidate.bucket,
        attempt_index=candidate.attempt_index,
        seed=candidate.seed,
        rejection_reason=DUPLICATE_PROBLEM_REASON,
        rejection_stage=DEDUPE_REJECTION_STAGE,
        message="Normalized problem already accepted in an existing output.",
        normalized_problem_text=candidate.normalized_problem_text,
        duplicate_of_instance_id=existing.instance_id,
        generator_command=candidate.generator_command,
        generator_cwd=candidate.generator_cwd,
        stdout_path=candidate.stdout_path,
        stderr_path=candidate.stderr_path,
        details={
            "existing_bucket": existing.bucket,
            "existing_domain_id": existing.domain_id,
            "existing_instance_id": existing.instance_id,
            "existing_split": existing.split,
            "normalized_problem_text": existing.normalized_problem_text,
            "source": "accepted_outputs",
        },
    )


def _build_selection_rejection(candidate: AcceptedInstanceMetadata) -> RejectedCandidateMetadata:
    return RejectedCandidateMetadata(
        candidate_id=candidate.candidate_id,
        domain_id=candidate.domain_id,
        split=candidate.split,
        bucket=candidate.bucket,
        attempt_index=candidate.attempt_index,
        seed=candidate.seed,
        rejection_reason=SELECTION_NOT_SELECTED_REASON,
        rejection_stage=SELECTION_REJECTION_STAGE,
        message="Candidate passed generation and rendering but was not selected for measured-difficulty quotas.",
        normalized_problem_text=candidate.normalized_problem_text,
        generator_command=candidate.generator_command,
        generator_cwd=candidate.generator_cwd,
        stdout_path=candidate.stdout_path,
        stderr_path=candidate.stderr_path,
        details={
            "difficulty_measured": candidate.difficulty_measured,
            "difficulty_target": candidate.difficulty_target,
            "measured_difficulty": candidate.measured_difficulty,
            "source_candidate_id": candidate.extra.get("orchestrator", {}).get("source_candidate_id", candidate.candidate_id),
        },
    )


def _finalize_selected_candidate(
    *,
    candidate: AcceptedInstanceMetadata,
    output_root: Path,
    force: bool,
    existing_instances: Sequence[AcceptedInstanceMetadata],
) -> AcceptedInstanceMetadata:
    final_bucket = candidate.difficulty_measured or candidate.measured_bucket
    if not final_bucket:
        raise ValueError(f"Selected candidate {candidate.candidate_id} is missing difficulty_measured")

    final_index = _next_available_index(
        existing_instances,
        domain_id=candidate.domain_id,
        split=candidate.split,
        bucket=final_bucket,
    )
    final_instance_id = build_instance_id(candidate.domain_id, candidate.split, final_bucket, final_index)
    final_candidate_id = build_candidate_id(candidate.domain_id, candidate.split, final_bucket, candidate.attempt_index)
    staging_dir = Path(candidate.domain_path).resolve().parent
    final_dir = output_root / candidate.domain_id / candidate.split / final_bucket / final_instance_id
    if force and final_dir.exists():
        shutil.rmtree(final_dir)
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(staging_dir, final_dir, dirs_exist_ok=True)

    final_extra = dict(candidate.extra)
    orchestrator_payload = dict(final_extra.get("orchestrator", {}))
    orchestrator_payload["source_candidate_id"] = candidate.candidate_id
    orchestrator_payload["source_target_bucket"] = candidate.difficulty_target or candidate.bucket
    orchestrator_payload["staging_output_dir"] = str(staging_dir)
    final_extra["orchestrator"] = orchestrator_payload

    return AcceptedInstanceMetadata(
        instance_id=final_instance_id,
        candidate_id=final_candidate_id,
        domain_id=candidate.domain_id,
        split=candidate.split,
        bucket=final_bucket,
        index=final_index,
        attempt_index=candidate.attempt_index,
        seed=candidate.seed,
        domain_path=str(final_dir / "domain.pddl"),
        problem_path=str(final_dir / "problem.pddl"),
        generator_command=candidate.generator_command,
        generator_cwd=candidate.generator_cwd,
        stdout_path=str(final_dir / Path(candidate.stdout_path).name),
        stderr_path=str(final_dir / Path(candidate.stderr_path).name),
        normalized_problem_text=candidate.normalized_problem_text,
        render_status=candidate.render_status,
        render_artifact_paths=tuple(_rebase_path(path, source_root=staging_dir, target_root=final_dir) for path in candidate.render_artifact_paths),
        render_result_path=_rebase_path(candidate.render_result_path, source_root=staging_dir, target_root=final_dir),
        difficulty_target=candidate.difficulty_target or candidate.bucket,
        difficulty_measured=final_bucket,
        measured_difficulty=candidate.measured_difficulty,
        measured_bucket=final_bucket,
        notes=candidate.notes,
        extra=final_extra,
    )


def _rebase_path(path_text: str, *, source_root: Path, target_root: Path) -> str:
    source_path = Path(path_text).resolve()
    relative_path = source_path.relative_to(source_root.resolve())
    return str((target_root / relative_path).resolve())


def _next_available_index(
    instances: Sequence[AcceptedInstanceMetadata],
    *,
    domain_id: str,
    split: str,
    bucket: str,
) -> int:
    used_indices = {
        instance.index
        for instance in instances
        if instance.domain_id == domain_id and instance.split == split and instance.bucket == bucket
    }
    next_index = 0
    while next_index in used_indices:
        next_index += 1
    return next_index


def _accepted_result_path(output_root: Path, instance: AcceptedInstanceMetadata) -> Path:
    return output_root / instance.domain_id / instance.split / instance.bucket / instance.instance_id / "result.json"


def _load_existing_accepted(
    output_root: Path,
    selected_domains: Sequence[DomainConfig],
    selected_splits: Sequence[str],
) -> list[AcceptedInstanceMetadata]:
    accepted_instances: list[AcceptedInstanceMetadata] = []
    domain_ids = {domain.domain_id for domain in selected_domains}
    split_ids = set(selected_splits)
    for domain_id in sorted(domain_ids):
        for split in sorted(split_ids):
            for bucket in DIFFICULTY_BUCKETS:
                bucket_root = output_root / domain_id / split / bucket
                if not bucket_root.exists():
                    continue
                for instance_dir in sorted(path for path in bucket_root.iterdir() if path.is_dir()):
                    payload = load_metadata_payload(instance_dir / "result.json")
                    if payload is None:
                        continue
                    accepted_instances.append(AcceptedInstanceMetadata.from_dict(payload))
    return _sorted_accepted_instances(accepted_instances)


def _load_rejections(path: Path) -> list[RejectedCandidateMetadata]:
    if not path.exists():
        return []
    rejections: list[RejectedCandidateMetadata] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rejections.append(RejectedCandidateMetadata.from_dict(json.loads(line)))
    return _sorted_rejections(rejections)


def _write_jsonl(path: Path, payloads: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(dict(payload), sort_keys=True) for payload in payloads]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _count_duplicate_problems(instances: Sequence[AcceptedInstanceMetadata]) -> int:
    counts = Counter(instance.normalized_problem_text for instance in instances if instance.normalized_problem_text)
    return sum(count - 1 for count in counts.values() if count > 1)


def _count_completed_domains(
    accepted_instances: Sequence[AcceptedInstanceMetadata],
    selected_domains: Sequence[DomainConfig],
    selected_splits: Sequence[str],
    quotas_by_split: Mapping[str, Mapping[str, int]],
) -> int:
    completed = 0
    for domain in selected_domains:
        domain_complete = True
        for split in selected_splits:
            remaining = _remaining_quotas(accepted_instances, domain_id=domain.domain_id, split=split, quotas=quotas_by_split[split])
            if any(remaining.values()):
                domain_complete = False
                break
        if domain_complete:
            completed += 1
    return completed


def _sorted_accepted_instances(instances: Sequence[AcceptedInstanceMetadata]) -> list[AcceptedInstanceMetadata]:
    return sorted(instances, key=lambda item: (item.domain_id, item.split, item.bucket, item.index, item.attempt_index))


def _sorted_rejections(rejections: Sequence[RejectedCandidateMetadata]) -> list[RejectedCandidateMetadata]:
    return sorted(rejections, key=lambda item: (item.domain_id, item.split, item.bucket, item.attempt_index, item.candidate_id))


__all__ = [
    "ACCEPTED_MANIFEST_FILENAME",
    "GENERATION_REJECTION_STAGE",
    "REJECTIONS_FILENAME",
    "SELECTION_NOT_SELECTED_REASON",
    "STAGING_DIRNAME",
    "SUMMARY_FILENAME",
    "GenerationRequest",
    "GenerationRunReceipt",
    "GenerationRunResult",
    "ValidExecutionStop",
    "orchestrate_generation",
    "run_authorized_generation",
    "run_governed_generation",
]
