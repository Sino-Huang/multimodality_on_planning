from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .cgas_characterization_assembly_fs import CandidateFile, CandidateFilesystemError, create_candidate_root, write_candidate_files
from .cgas_characterization_rows import CHARACTERIZATION_LIMITS
from .cgas_characterization_verifier import VerificationRequest, verify_characterization
from .cgas_partition_contracts import CHARACTERIZATION_FILE, EXPECTED_ROW_COUNT, MANIFEST_FILE, SCHEMA_VERSION
from .cgas_serialization import canonical, canonical_json_object, digest_text


@dataclass(frozen=True, slots=True)
class CharacterizationAssemblyError(RuntimeError):
    rule: str
    candidate_root: Path | None = None

    def __str__(self) -> str:
        suffix = f"; candidate={self.candidate_root}" if self.candidate_root is not None else ""
        return f"characterization assembly {self.rule}{suffix}"


@dataclass(frozen=True, slots=True)
class CharacterizationCandidate:
    candidate_root: Path


def assemble_characterization_candidate(request: VerificationRequest, private_root: Path) -> CharacterizationCandidate:
    checkpoint_report = verify_characterization(request)
    if not checkpoint_report.valid or checkpoint_report.checkpoint_count != EXPECTED_ROW_COUNT:
        raise CharacterizationAssemblyError("checkpoint work is not verified and complete")
    if checkpoint_report.verified_checkpoints is None or any(checkpoint.row is None for checkpoint in checkpoint_report.verified_checkpoints):
        raise CharacterizationAssemblyError("checkpoint rows are unavailable")
    rows = tuple(checkpoint.row for checkpoint in checkpoint_report.verified_checkpoints if checkpoint.row is not None)
    artifact = b"".join(canonical(row).encode() + b"\n" for row in rows)
    manifest = _manifest(rows, artifact, request.repository_root)
    try:
        candidate = create_candidate_root(request.repository_root, request.checkpoint_root, private_root)
    except CandidateFilesystemError as error:
        raise CharacterizationAssemblyError(error.rule) from error
    try:
        write_candidate_files(
            candidate,
            (
                CandidateFile("run-contract.json", checkpoint_report.contract_bytes or b""),
                CandidateFile(CHARACTERIZATION_FILE, artifact),
                CandidateFile(MANIFEST_FILE, canonical_json_object(manifest) + b"\n"),
            ),
        )
    except CandidateFilesystemError as error:
        raise CharacterizationAssemblyError(error.rule, candidate) from error
    if frozenset(path.name for path in candidate.iterdir()) != {"run-contract.json", CHARACTERIZATION_FILE, MANIFEST_FILE}:
        raise CharacterizationAssemblyError("final verifier rejected candidate", candidate)
    return CharacterizationCandidate(candidate)


def _manifest(rows, artifact: bytes, repository: Path):
    files = {
        "bfs_sha256": "scripts/phase3/cgas_bfs.py",
        "iw_sha256": "scripts/phase3/local_iw.py",
        "module_sha256": "scripts/phase3/cgas_partition_characterization.py",
    }
    return {
        "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
        "counts_by_object": {str(key): value for key, value in sorted(Counter(row["object_count"] for row in rows).items())},
        "counts_by_split": dict(sorted(Counter(_row_split(row) for row in rows).items())),
        "implementation": {key: hashlib.sha256((repository / path).read_bytes()).hexdigest() for key, path in files.items()},
        "limits": CHARACTERIZATION_LIMITS,
        "owner_approved": False,
        "row_count": len(rows),
        "schema_version": SCHEMA_VERSION,
        "source_records_sha256": digest_text("|".join(sorted(_source_digest(row) for row in rows))),
    }


def _row_split(row) -> str:
    value = row.get("split")
    if not isinstance(value, str) or not value:
        raise CharacterizationAssemblyError("recomputed row has invalid split")
    return value


def _source_digest(row) -> str:
    identity = row.get("source_identity")
    if not isinstance(identity, dict):
        raise CharacterizationAssemblyError("recomputed row has invalid source identity")
    value = identity.get("source_record_sha256")
    if not isinstance(value, str) or not value:
        raise CharacterizationAssemblyError("recomputed row has invalid source digest")
    return value


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--checkpoint-root", required=True, type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--module-root", action="append", default=[])
    args = parser.parse_args(arguments)
    request = VerificationRequest(args.repository_root, args.source_manifest, args.checkpoint_root, None, tuple(args.module_root))
    try:
        candidate = assemble_characterization_candidate(request, args.private_root)
    except CharacterizationAssemblyError as error:
        print(str(error))
        return 1
    print(canonical_json_object({"candidate_root": str(candidate.candidate_root)}).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
