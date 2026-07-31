from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.phase3.cgas_characterization_checkpoint import build_checkpoint
from scripts.phase3.cgas_characterization_checkpoint_contracts import CheckpointExpectation
from scripts.phase3.cgas_characterization_contract import build_characterization_run_contract
from scripts.phase3.cgas_characterization_final_validation import expected_characterization_rows
from scripts.phase3.cgas_characterization_types import (
    CanonicalRowIndex,
    CharacterizationArtifactDigest,
    SourceManifestDigest,
)
from scripts.phase3.cgas_characterization_verifier import VerificationRequest
from scripts.phase3.cgas_serialization import canonical, canonical_json_object
from scripts.phase3.local_planner_types import JSONValue


def synthetic_request(root: Path) -> tuple[VerificationRequest, Path]:
    repository = root / "repository"
    repository.mkdir(parents=True, mode=0o700)
    repository.chmod(0o700)
    package = repository / "fixture"
    package.mkdir()
    (package / "__init__.py").write_text("\n", encoding="utf-8")
    (package / "runner.py").write_text("VALUE = 1\n", encoding="utf-8")
    domain = repository / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld) (:requirements :strips) (:predicates (clear ?x) (handempty)))\n",
        encoding="utf-8",
    )
    paths = {count: repository / f"problem-{count}.pddl" for count in (4, 8, 12)}
    for count, path in paths.items():
        objects = " ".join(f"b{index}" for index in range(count))
        clear = " ".join(f"(clear b{index})" for index in range(count))
        path.write_text(
            f"(define (problem p{count}) (:domain blocksworld) (:objects {objects}) (:init (handempty) {clear}) (:goal (and (handempty))))\n",
            encoding="utf-8",
        )
    rows: list[dict[str, JSONValue]] = []
    for split, count, size in (("train", 4, 190), ("train", 8, 198), ("train", 12, 14), ("dev", 12, 39), ("test", 12, 40)):
        bucket = f"bucket-{count}"
        for ordinal in range(size):
            rows.append(
                {
                    "attempt_index": ordinal,
                    "bucket": bucket,
                    "candidate_id": f"blocksworld-{split}-{bucket}-attempt-{ordinal:06d}",
                    "domain_id": "blocksworld",
                    "domain_path": domain.relative_to(repository).as_posix(),
                    "index": ordinal,
                    "instance_id": f"blocksworld-{split}-{bucket}-{ordinal:04d}",
                    "problem_path": paths[count].relative_to(repository).as_posix(),
                    "split": split,
                }
            )
    source = repository / "accepted.jsonl"
    source.write_bytes(b"".join(canonical_json_object(row) + b"\n" for row in rows))
    phase = repository / "scripts/phase3"
    phase.mkdir(parents=True)
    (repository / "scripts/__init__.py").write_text("\n", encoding="utf-8")
    (phase / "__init__.py").write_text("\n", encoding="utf-8")
    for name in ("cgas_partition_characterization", "cgas_characterization_contract", "cgas_characterization_imports", "cgas_bfs", "local_iw"):
        (phase / f"{name}.py").write_text("VALUE = 1\n", encoding="utf-8")
    checkpoint_root = root / "checkpoints"
    checkpoint_root.mkdir(mode=0o700)
    checkpoint_root.chmod(0o700)
    (checkpoint_root / "checkpoints").mkdir(mode=0o700)
    (checkpoint_root / "checkpoints").chmod(0o700)
    request = VerificationRequest(repository, source, checkpoint_root, None, ("fixture.runner",))
    contract = build_characterization_run_contract(source, repository, shard_count=1, module_roots=request.module_roots)
    contract_leaf = checkpoint_root / "run-contract.json"
    contract_leaf.write_bytes(contract.canonical_bytes)
    contract_leaf.chmod(0o600)
    state_root = repository / "tmp" / ".cgas-characterization"
    state_root.mkdir(parents=True, mode=0o700)
    state_root.chmod(0o700)
    private_root = state_root / "private-candidates"
    private_root.mkdir(mode=0o700)
    private_root.chmod(0o700)
    return request, private_root


def checkpoint_request(base: VerificationRequest, root: Path, *, shard_count: int = 1) -> VerificationRequest:
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    (root / "checkpoints").mkdir(mode=0o700)
    (root / "checkpoints").chmod(0o700)
    request = VerificationRequest(base.repository_root, base.source_manifest, root, None, base.module_roots)
    contract = build_characterization_run_contract(
        request.source_manifest, request.repository_root, shard_count=shard_count, module_roots=request.module_roots
    )
    contract_leaf = root / "run-contract.json"
    contract_leaf.write_bytes(contract.canonical_bytes)
    contract_leaf.chmod(0o600)
    return request


def write_checkpoint_history(request: VerificationRequest, indexes: tuple[int, ...], *, shard_count: int = 1) -> None:
    contract = build_characterization_run_contract(
        request.source_manifest, request.repository_root, shard_count=shard_count, module_roots=request.module_roots
    )
    rows = expected_characterization_rows(contract.payload, request.repository_root)
    records = contract.payload["source"]
    assert isinstance(records, dict)
    source_records = records["records"]
    assert isinstance(source_records, dict)
    instance_ids = tuple(sorted(source_records))
    for index in indexes:
        row = rows[index]
        checkpoint = build_checkpoint(
            CheckpointExpectation(
                SourceManifestDigest(contract.fingerprint),
                CanonicalRowIndex(index),
                instance_ids[index],
                CharacterizationArtifactDigest(hashlib.sha256(canonical(row).encode()).hexdigest()),
            ),
            row,
        )
        path = request.checkpoint_root / "checkpoints" / f"{index:04d}.json"
        path.write_bytes(checkpoint.canonical_bytes)
        path.chmod(0o600)
