from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from src.data_collect.metadata import AcceptedInstanceMetadata

from .cgas_characterization_imports import ImportClosureError, implementation_closure
from .cgas_characterization_rows import CHARACTERIZATION_LIMITS
from .cgas_partition_contracts import (
    EXPECTED_OBJECT_COUNTS,
    EXPECTED_ROW_COUNT,
    EXPECTED_SPLIT_COUNTS,
    SCHEMA_VERSION,
)
from .cgas_serialization import canonical_json_object
from .pddl import parse_task


RUN_CONTRACT_VERSION: Final = "cgas_characterization_run_contract_v1"
RUN_CONTRACT_SIZE_POLICY_VERSION: Final = "cgas_characterization_run_contract_size_v1"
MAX_RUN_CONTRACT_BYTES: Final = 2 * 1024 * 1024
SERIALIZATION_VERSION: Final = "canonical_json_object_v1"
POLICY_VERSION: Final = "characterization_source_policy_v1"
CHECKPOINT_PUBLICATION_POLICY_VERSION: Final = "otmpfile_procfd_linkat_v1"
FINAL_PUBLICATION_PROFILE: Final = "regular_bundle_linkat_trusted_state_v2"
STATE_DIRECTORY_POLICY_VERSION: Final = "repository_tmp_owner_safe_child0700_v1"
DEFAULT_PRODUCT_ROOTS: Final = (
    "scripts.phase3.cgas_partition_characterization",
    "scripts.phase3.cgas_characterization_contract",
    "scripts.phase3.cgas_characterization_imports",
)
VERIFIER_PRODUCT_ROOT: Final = "scripts.phase3.cgas_characterization_verifier"
RUNNER_PRODUCT_ROOTS: Final = (
    "scripts.phase3.cgas_characterization_runner",
    "scripts.phase3.cgas_characterization_work",
)


@dataclass(frozen=True, slots=True)
class CharacterizationRunContractError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class CharacterizationRunContract:
    canonical_bytes: bytes
    fingerprint: str
    payload: dict[str, object]


def build_characterization_run_contract(
    source_manifest: Path, repository_root: Path, *, shard_count: int, module_roots: tuple[str, ...] | None = None
) -> CharacterizationRunContract:
    _require_runtime()
    if shard_count < 1:
        raise CharacterizationRunContractError("invalid_shard_count")
    root = repository_root.resolve()
    manifest = source_manifest.resolve()
    if source_manifest.is_symlink():
        raise CharacterizationRunContractError("symlink_source_manifest")
    _require_within_root(manifest, root, "source_manifest_outside_repository")
    source_bytes = manifest.read_bytes()
    records = _source_records(source_bytes, manifest, root)
    try:
        files = implementation_closure(root, _module_roots(root, module_roots))
    except ImportClosureError as error:
        raise CharacterizationRunContractError(error.reason) from error
    payload: dict[str, object] = {
        "contract_version": RUN_CONTRACT_VERSION,
        "implementation": {"files": {file.path: file.sha256 for file in files}},
        "policies": {
            "characterization": POLICY_VERSION,
            "checkpoint_publication": CHECKPOINT_PUBLICATION_POLICY_VERSION,
            "final_publication_profile": FINAL_PUBLICATION_PROFILE,
            "limits": _limits(),
            "run_contract_size": RUN_CONTRACT_SIZE_POLICY_VERSION,
            "state_directory": STATE_DIRECTORY_POLICY_VERSION,
            "schema": SCHEMA_VERSION,
            "serialization": SERIALIZATION_VERSION,
        },
        "population": _population(records),
        "runtime": {"implementation": sys.implementation.name, "python": ".".join(str(part) for part in sys.version_info[:3]), "system": platform.system()},
        "shard_count": shard_count,
        "source": {
            "manifest_path": manifest.relative_to(root).as_posix(),
            "manifest_sha256": _sha256(source_bytes),
            "records": {str(record["instance_id"]): record for record in records},
        },
    }
    canonical_bytes = canonical_json_object(payload)
    return CharacterizationRunContract(canonical_bytes, _sha256(b"cgas-characterization-run-fingerprint\x00" + canonical_bytes), payload)


def _source_records(source_bytes: bytes, manifest: Path, root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line_number, raw_line in enumerate(source_bytes.splitlines(), start=1):
        if not raw_line:
            continue
        try:
            raw = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise CharacterizationRunContractError("malformed_source_manifest") from error
        if not isinstance(raw, dict):
            raise CharacterizationRunContractError("source_row_not_object")
        try:
            metadata = AcceptedInstanceMetadata.from_dict(raw)
        except (KeyError, TypeError, ValueError) as error:
            raise CharacterizationRunContractError("invalid_source_record") from error
        if metadata.domain_id == "blocksworld":
            records.append(_record(metadata, raw_line, line_number, manifest, root))
    _validate_records(records)
    return sorted(records, key=lambda record: str(record["instance_id"]))


def _record(metadata: AcceptedInstanceMetadata, raw_line: bytes, line_number: int, manifest: Path, root: Path) -> dict[str, object]:
    domain = _source_path(metadata.domain_path, manifest, root)
    problem = _source_path(metadata.problem_path, manifest, root)
    try:
        task = parse_task(domain, problem)
    except (OSError, ValueError) as error:
        raise CharacterizationRunContractError("invalid_pddl_source") from error
    return {
        "domain_path": domain.relative_to(root).as_posix(),
        "domain_sha256": _sha256(domain.read_bytes()),
        "instance_id": metadata.instance_id,
        "line_number": line_number,
        "object_count": len(task.objects_by_type.get("object", ())),
        "problem_path": problem.relative_to(root).as_posix(),
        "problem_sha256": _sha256(problem.read_bytes()),
        "source_record_sha256": _sha256(raw_line),
        "split": metadata.split,
    }


def _source_path(raw_path: str, manifest: Path, root: Path) -> Path:
    candidate = Path(raw_path)
    path = candidate if candidate.is_absolute() else manifest.parent / candidate
    resolved = path.resolve()
    _require_within_root(resolved, root, "source_path_outside_repository")
    if not resolved.is_file() or resolved.is_symlink():
        raise CharacterizationRunContractError("invalid_source_path")
    return resolved


def _validate_records(records: list[dict[str, object]]) -> None:
    if len(records) != EXPECTED_ROW_COUNT:
        raise CharacterizationRunContractError("unexpected_accepted_blocksworld_row_count")
    instance_ids = [str(record["instance_id"]) for record in records]
    if len(instance_ids) != len(set(instance_ids)):
        raise CharacterizationRunContractError("duplicate_instance_id")
    split_counts = _counts(records, "split")
    object_counts = _counts(records, "object_count")
    if split_counts != EXPECTED_SPLIT_COUNTS:
        raise CharacterizationRunContractError("unexpected_accepted_blocksworld_split_counts")
    if object_counts != EXPECTED_OBJECT_COUNTS:
        raise CharacterizationRunContractError("unexpected_accepted_blocksworld_object_counts")


def _counts(records: list[dict[str, object]], key: str) -> dict[object, int]:
    counts: dict[object, int] = {}
    for record in records:
        value = record[key]
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _population(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "object_counts": {str(key): value for key, value in _counts(records, "object_count").items()},
        "row_count": len(records),
        "split_counts": _counts(records, "split"),
    }


def _limits() -> dict[str, object]:
    return {key: value.value if hasattr(value, "value") else value for key, value in sorted(CHARACTERIZATION_LIMITS.items())}


def _module_roots(root: Path, supplied: tuple[str, ...] | None) -> tuple[str, ...]:
    optional = tuple(module for module in RUNNER_PRODUCT_ROOTS + (VERIFIER_PRODUCT_ROOT,) if _module_path(root, module) is not None)
    if supplied is not None:
        mandatory = {
            module
            for module in DEFAULT_PRODUCT_ROOTS + (VERIFIER_PRODUCT_ROOT,)
            if _module_path(root, module) is not None
        }
        return tuple(sorted(set(supplied) | mandatory | set(optional)))
    return DEFAULT_PRODUCT_ROOTS + optional


def _module_path(root: Path, module: str) -> Path | None:
    base = root.joinpath(*module.split("."))
    file_path = base.with_suffix(".py")
    package_path = base / "__init__.py"
    if file_path.is_file() and package_path.is_file():
        raise CharacterizationRunContractError("ambiguous_local_import")
    return file_path if file_path.is_file() else package_path if package_path.is_file() else None


def _require_runtime() -> None:
    if platform.system() != "Linux":
        raise CharacterizationRunContractError("unsupported_runtime_system")
    if sys.implementation.name != "cpython":
        raise CharacterizationRunContractError("unsupported_runtime_implementation")


def _require_within_root(path: Path, root: Path, reason: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as error:
        raise CharacterizationRunContractError(reason) from error


def _sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()
