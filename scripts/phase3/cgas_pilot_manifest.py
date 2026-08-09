from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from . import cgas_trace_contract_v3
from .cgas_candidate_characterization_contracts import canonical_bytes, parse_canonical_model
from .cgas_candidate_characterization_models import CheckpointModel, JsonObject, JsonValue
from .cgas_gate0b_verifier import verify_gate0b_round
from .cgas_pilot_manifest_approval import read_bytes, read_json, sha256, validate_pilot_approval
from .cgas_pilot_manifest_models import PilotRecord, PilotSelection
from .cgas_pilot_manifest_selection import (
    PilotManifestError,
    build_row_budget,
    pilot_config,
    records_json,
    select_pilot_rows,
    selection_record,
)
from .cgas_pilot_scope_evidence import _rows

__all__ = [
    "PilotManifestError",
    "PilotManifestReport",
    "PilotManifestRequest",
    "PilotRecord",
    "PilotSelection",
    "build_row_budget",
    "publish_once",
    "run",
    "select_pilot_rows",
    "validate_pilot_approval",
]


@dataclass(frozen=True, slots=True)
class PilotManifestRequest:
    repository_root: Path
    characterization_root: Path
    approved_trace_path: Path
    candidate_config_path: Path
    scope_report_path: Path
    owner_approval_path: Path
    output_root: Path
    checkpoint_path: Path | None = None
    checkpoint_index_path: Path | None = None


@dataclass(frozen=True, slots=True)
class PilotManifestReport:
    manifest_path: Path
    row_budget_path: Path
    report_path: Path
    read_only: bool


def publish_once(path: Path, contents: bytes) -> bool:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != contents:
            raise PilotManifestError("pilot_publication_collision", path)
        return True
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as error:
        raise PilotManifestError("pilot_publication_failed", path) from error
    finally:
        temporary.unlink(missing_ok=True)
    return False


def run(request: PilotManifestRequest) -> PilotManifestReport:
    repository = request.repository_root.resolve()
    approval_digest = validate_pilot_approval(request.scope_report_path, request.owner_approval_path)
    scope, scope_contents = read_json(request.scope_report_path, "pilot_scope_report_invalid")
    gate = verify_gate0b_round(
        repository,
        request.characterization_root,
        request.approved_trace_path,
        request.candidate_config_path,
        request.checkpoint_path,
    )
    expected_index = (request.characterization_root / "current.json").resolve()
    if request.checkpoint_index_path is not None and request.checkpoint_index_path.resolve() != expected_index:
        raise PilotManifestError("pilot_checkpoint_index_path_invalid", request.checkpoint_index_path)
    _verify_scope_inputs(repository, scope, gate.checkpoint_path, gate.checkpoint_sha256)
    checkpoint, _ = parse_canonical_model(gate.checkpoint_path, CheckpointModel, "pilot_checkpoint_invalid")
    selection = select_pilot_rows(_rows(checkpoint, gate.checkpoint_path))
    config = pilot_config()
    bindings = _mapping(scope.get("bindings"), request.scope_report_path, "pilot_scope_bindings_invalid")
    bindings = {
        **bindings,
        "pilot_approval_implementation_sha256": sha256(
            Path(__file__).with_name("cgas_pilot_manifest_approval.py").read_bytes()
        ),
        "pilot_config_sha256": sha256(canonical_bytes(config)),
        "pilot_manifest_implementation_sha256": sha256(Path(__file__).read_bytes()),
        "pilot_models_implementation_sha256": sha256(
            Path(__file__).with_name("cgas_pilot_manifest_models.py").read_bytes()
        ),
        "pilot_owner_approval_sha256": approval_digest,
        "pilot_selection_implementation_sha256": sha256(
            Path(__file__).with_name("cgas_pilot_manifest_selection.py").read_bytes()
        ),
        "scope_report_sha256": sha256(scope_contents),
    }
    manifest: JsonObject = {
        "bindings": bindings,
        "config": config,
        "owner_approved": True,
        "records": records_json(selection),
        "schema_version": "cgas_phase3_pilot_source_manifest_v1",
        "selection": selection_record(selection),
        "status": "approved_pilot_source_manifest",
    }
    manifest_contents = canonical_bytes(manifest) + b"\n"
    budget = build_row_budget(selection, sha256(manifest_contents))
    budget_contents = canonical_bytes(budget) + b"\n"
    report: JsonObject = {
        "gate0b": {
            "candidate_count": gate.candidate_count,
            "checkpoint_sha256": gate.checkpoint_sha256,
            "stream_count": gate.stream_count,
            "total_stream_bytes": gate.total_stream_bytes,
        },
        "manifest_sha256": sha256(manifest_contents),
        "owner_approval_sha256": approval_digest,
        "row_budget_sha256": sha256(budget_contents),
        "schema_version": "cgas_phase3_pilot_manifest_report_v1",
        "selection": selection_record(selection),
        "status": "approved_read_only_source_selection",
    }
    report_contents = canonical_bytes(report) + b"\n"
    request.output_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if request.output_root.is_symlink() or not stat.S_ISDIR(request.output_root.lstat().st_mode):
        raise PilotManifestError("pilot_output_directory_invalid", request.output_root)
    paths = (
        request.output_root / "pilot-source-manifest.json",
        request.output_root / "pilot-row-budget.json",
        request.output_root / "pilot-manifest-report.json",
    )
    read_only = tuple(
        publish_once(path, contents)
        for path, contents in zip(paths, (manifest_contents, budget_contents, report_contents), strict=True)
    )
    return PilotManifestReport(paths[0], paths[1], paths[2], all(read_only))


def _verify_scope_inputs(repository: Path, scope: JsonObject, checkpoint: Path, checkpoint_digest: str) -> None:
    bindings = _mapping(scope.get("bindings"), checkpoint, "pilot_scope_bindings_invalid")
    paths = {
        "analysis_implementation_sha256": repository / "scripts/phase3/cgas_pilot_scope.py",
        "evidence_adapter_sha256": repository / "scripts/phase3/cgas_pilot_scope_evidence.py",
        "selector_implementation_sha256": repository / "scripts/phase3/cgas_partition_selection.py",
    }
    if bindings.get("checkpoint_sha256") != checkpoint_digest:
        raise PilotManifestError("pilot_checkpoint_binding_invalid", checkpoint)
    for key, path in paths.items():
        if bindings.get(key) != sha256(read_bytes(path, "pilot_bound_input_unreadable")):
            raise PilotManifestError("pilot_bound_input_drift", path)
    if bindings.get("release_sha256") != cgas_trace_contract_v3.TRACE_V1_RELEASE_SHA256:
        raise PilotManifestError("pilot_release_binding_invalid", checkpoint)


def _mapping(value: JsonValue | None, path: Path, code: str) -> JsonObject:
    if not isinstance(value, dict):
        raise PilotManifestError(code, path)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze the approved CGAS Phase 3 pilot source manifest.")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint-index", type=Path, required=True)
    parser.add_argument("--scope-report", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    repository = args.repository.resolve()
    checkpoint = args.checkpoint.resolve()
    report = run(
        PilotManifestRequest(
            repository,
            checkpoint.parent.parent,
            repository / ".claude/evidence/cgas-trace-contract-v3/approved-trace-v3.json",
            repository / "configs/cgas/production_p0_candidates.json",
            args.scope_report.resolve(),
            args.approval.resolve(),
            args.output.resolve(),
            checkpoint,
            args.checkpoint_index.resolve(),
        )
    )
    print(
        json.dumps(
            {
                "manifest": report.manifest_path.as_posix(),
                "read_only": report.read_only,
                "row_budget": report.row_budget_path.as_posix(),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
