from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from .cgas_characterization_checkpoint import CheckpointError, checkpoint_entries, build_checkpoint, publish_checkpoint
from .cgas_characterization_checkpoint_contracts import CheckpointExpectation, checkpoint_name
from .cgas_characterization_contract import CharacterizationRunContract, build_characterization_run_contract
from .cgas_characterization_contract_pins import PinnedRunContract, pin_run_contract
from .cgas_characterization_types import CanonicalRowIndex, CharacterizationArtifactDigest, SourceManifestDigest
from .cgas_characterization_verifier import CharacterizationVerificationReport, VerificationRequest, verify_characterization
from .cgas_characterization_work import WorkRootError, initialize_work_root, require_work_root
from .cgas_partition_characterization import _characterize
from .cgas_partition_contracts import CharacterizationInput
from .cgas_serialization import canonical, canonical_json_object


class RunMode(str, Enum):
    FRESH = "fresh"
    SHARD = "shard"
    RESUME = "resume"


@dataclass(frozen=True, slots=True)
class RunRequest:
    repository_root: Path
    source_manifest: Path
    final_root: Path
    private_root: Path
    shard_count: int
    shard_index: int
    module_roots: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunReport:
    characterized_count: int
    work_root: Path


@dataclass(frozen=True, slots=True)
class RunnerError(RuntimeError):
    reason: str
    path: Path

    def __str__(self) -> str:
        return f"characterization_runner {self.reason}: {self.path}"


class Characterizer(Protocol):
    def __call__(self, instance: CharacterizationInput) -> dict[str, object]: ...


class ContractBuilder(Protocol):
    def __call__(self, request: RunRequest, /) -> CharacterizationRunContract: ...


class WorkVerifier(Protocol):
    def __call__(self, request: VerificationRequest, /) -> CharacterizationVerificationReport: ...


class ProgressSink(Protocol):
    def write(self, text: str, /) -> int: ...

    def flush(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RunnerExecution:
    characterizer: Characterizer
    contract_builder: ContractBuilder
    verifier: WorkVerifier
    progress_sink: ProgressSink


def run(request: RunRequest, mode: RunMode, execution: RunnerExecution | None = None) -> RunReport:
    """Initialize or fill one deterministic checkpoint workspace without final publication."""
    dependencies = execution or RunnerExecution(_characterize, _build_contract, verify_characterization, sys.stderr)
    _validate_request(request)
    contract = dependencies.contract_builder(request)
    if mode is RunMode.FRESH:
        try:
            work_root = initialize_work_root(request.final_root, contract.canonical_bytes)
        except WorkRootError as error:
            raise RunnerError(error.reason, error.path) from error
        return RunReport(0, work_root)
    try:
        work_root = require_work_root(request.final_root, contract.canonical_bytes)
    except WorkRootError as error:
        raise RunnerError(error.reason, error.path) from error
    try:
        allowed_names = _checkpoint_names(contract, work_root)
        with pin_run_contract(work_root) as contract_pin:
            contract_pin.require_contract(contract)
            completed_names = _verified_checkpoint_names(request, work_root, dependencies.verifier, contract, contract_pin, allowed_names)
            rows = _selected_rows(contract, request, mode, work_root, completed_names)
            for completed, (index, instance_id, record) in enumerate(rows, start=1):
                _require_contract(dependencies, request, contract, work_root, contract_pin)
                row = dependencies.characterizer(_instance(request.repository_root, instance_id, record))
                _require_contract(dependencies, request, contract, work_root, contract_pin)
                _require_row_identity(row, instance_id, record)
                digest = CharacterizationArtifactDigest(hashlib.sha256(canonical(row).encode()).hexdigest())
                expectation = CheckpointExpectation(SourceManifestDigest(contract.fingerprint), CanonicalRowIndex(index), instance_id, digest)
                publish_checkpoint(work_root / "checkpoints", request.private_root, build_checkpoint(expectation, row))
                _progress(dependencies.progress_sink, mode, request, index, instance_id, completed, len(rows))
            _verified_checkpoint_names(request, work_root, dependencies.verifier, contract, contract_pin, allowed_names)
    except CheckpointError as error:
        raise RunnerError("checkpoint_state_drift", work_root) from error
    except WorkRootError as error:
        raise RunnerError("run_contract_drift", work_root) from error
    return RunReport(len(rows), work_root)


def _build_contract(request: RunRequest) -> CharacterizationRunContract:
    return build_characterization_run_contract(
        request.source_manifest,
        request.repository_root,
        shard_count=request.shard_count,
        module_roots=request.module_roots or None,
    )


def _validate_request(request: RunRequest) -> None:
    if request.shard_count < 1 or request.shard_index < 0 or request.shard_index >= request.shard_count:
        raise RunnerError("invalid_shard_index", request.final_root)
    for path in (request.repository_root, request.source_manifest, request.final_root, request.private_root):
        try:
            path.resolve().relative_to(request.repository_root.resolve())
        except ValueError as error:
            raise RunnerError("path_outside_repository", path) from error


def _verified_checkpoint_names(request: RunRequest, work_root: Path, verifier: WorkVerifier, contract: CharacterizationRunContract, contract_pin: PinnedRunContract, allowed_names: frozenset[str]) -> frozenset[str]:
    report = verifier(VerificationRequest(request.repository_root, request.source_manifest, work_root, None, request.module_roots))
    if not report.valid:
        raise RunnerError("invalid_work_state", work_root)
    contract_pin.require_contract(contract)
    if report.contract_bytes is not None and report.contract_bytes != contract.canonical_bytes:
        raise RunnerError("run_contract_drift", work_root)
    if report.contract_fingerprint is not None and report.contract_fingerprint != contract.fingerprint:
        raise RunnerError("run_contract_drift", work_root)
    try:
        entries = checkpoint_entries(work_root / "checkpoints", allowed_names)
    except CheckpointError as error:
        raise RunnerError("checkpoint_state_drift", work_root) from error
    if report.checkpoint_entries is not None:
        if len(entries) != report.checkpoint_count or report.checkpoint_entries != entries:
            raise RunnerError("checkpoint_state_drift", work_root)
    return frozenset(entry.name for entry in entries)


def _require_contract(dependencies: RunnerExecution, request: RunRequest, expected: CharacterizationRunContract, work_root: Path, contract_pin: PinnedRunContract) -> None:
    contract_pin.require_contract(expected)
    if dependencies.contract_builder(request).canonical_bytes != expected.canonical_bytes:
        raise RunnerError("run_contract_drift", work_root)


def _selected_rows(contract: CharacterizationRunContract, request: RunRequest, mode: RunMode, work_root: Path, completed_names: frozenset[str]) -> tuple[tuple[int, str, dict[str, object]], ...]:
    source = _mapping(contract.payload.get("source"), "contract_source", work_root)
    records = _mapping(source.get("records"), "contract_records", work_root)
    selected: list[tuple[int, str, dict[str, object]]] = []
    for index, instance_id in enumerate(sorted(records)):
        record = _mapping(records[instance_id], "contract_record", work_root)
        selected_for_shard = index % request.shard_count == request.shard_index
        should_run = mode is RunMode.RESUME or selected_for_shard
        if should_run and checkpoint_name(CanonicalRowIndex(index)) not in completed_names:
            selected.append((index, instance_id, record))
    return tuple(selected)


def _checkpoint_names(contract: CharacterizationRunContract, work_root: Path) -> frozenset[str]:
    source = _mapping(contract.payload.get("source"), "contract_source", work_root)
    records = _mapping(source.get("records"), "contract_records", work_root)
    return frozenset(checkpoint_name(CanonicalRowIndex(index)) for index in range(len(records)))


def _instance(repository: Path, instance_id: str, record: dict[str, object]) -> CharacterizationInput:
    return CharacterizationInput(
        instance_id,
        _text(record.get("split"), "split", repository),
        repository / _text(record.get("domain_path"), "domain_path", repository),
        repository / _text(record.get("problem_path"), "problem_path", repository),
        _text(record.get("source_record_sha256"), "source_record_sha256", repository),
    )


def _require_row_identity(row: dict[str, object], instance_id: str, record: dict[str, object]) -> None:
    identity = _mapping(row.get("source_identity"), "row_source_identity", Path(instance_id))
    expected = {
        "instance_id": instance_id,
        "split": record.get("split"),
        "domain_sha256": record.get("domain_sha256"),
        "problem_sha256": record.get("problem_sha256"),
        "source_record_sha256": record.get("source_record_sha256"),
    }
    actual = {**row, "source_record_sha256": identity.get("source_record_sha256")}
    if any(actual[key] != value for key, value in expected.items()):
        raise RunnerError("row_identity_drift", Path(instance_id))


def _progress(sink: ProgressSink, mode: RunMode, request: RunRequest, index: int, instance_id: str, completed: int, total: int) -> None:
    sink.write(
        canonical_json_object(
            {
                "completed": completed,
                "index": index,
                "instance_id": instance_id,
                "phase": mode.value,
                "shard_count": request.shard_count,
                "shard_index": request.shard_index,
                "status": "published",
                "total": total,
            }
        ).decode()
        + "\n"
    )
    sink.flush()


def _mapping(value: object, label: str, path: Path) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RunnerError(f"invalid_{label}", path)
    return value


def _text(value: object, label: str, path: Path) -> str:
    if not isinstance(value, str) or not value:
        raise RunnerError(f"invalid_{label}", path)
    return value
