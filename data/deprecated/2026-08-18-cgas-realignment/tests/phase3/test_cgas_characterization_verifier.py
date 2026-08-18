from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.phase3.cgas_characterization_contract import build_characterization_run_contract
from scripts.phase3.cgas_characterization_checkpoint import build_checkpoint
from scripts.phase3.cgas_characterization_checkpoint_contracts import CheckpointExpectation
from scripts.phase3.cgas_characterization_types import CanonicalRowIndex, CharacterizationArtifactDigest, SourceManifestDigest
from scripts.phase3.cgas_characterization_verifier import VerificationRequest, main, verify_characterization
from scripts.phase3.cgas_characterization_final_validation import expected_characterization_rows
from scripts.phase3.cgas_characterization_rows import CHARACTERIZATION_LIMITS
from scripts.phase3.cgas_partition_contracts import SCHEMA_VERSION
from scripts.phase3.cgas_serialization import canonical, canonical_json_object, digest_text


def test_verify_accepts_current_empty_checkpoint_root_without_mutation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Given: a synthetic current source contract with no completed checkpoint leaves.
    repository, source = _repository(tmp_path)
    checkpoint_root = tmp_path / "checkpoints"
    checkpoint_root.mkdir(mode=0o700)
    contract = build_characterization_run_contract(source, repository, shard_count=1, module_roots=("fixture.runner",))
    (checkpoint_root / "run-contract.json").write_bytes(contract.canonical_bytes)
    (checkpoint_root / "run-contract.json").chmod(0o600)
    (checkpoint_root / "checkpoints").mkdir(mode=0o700)
    before = _snapshot(checkpoint_root)

    # When: the verifier observes the incomplete root through its public boundary.
    report = verify_characterization(VerificationRequest(repository, source, checkpoint_root, None, ("fixture.runner",)))

    # Then: a current, incomplete checkpoint state is valid and the root is unchanged.
    assert (report.valid, report.complete, report.publishable) == (True, False, False)
    assert _snapshot(checkpoint_root) == before
    assert main(("--repository-root", str(repository), "--source-manifest", str(source), "--checkpoint-root", str(checkpoint_root), "--module-root", "fixture.runner")) == 0
    assert json.loads(capsys.readouterr().out) == {"checkpoint_count": 0, "complete": False, "errors": {}, "publishable": False, "valid": True}
    assert _snapshot(checkpoint_root) == before


@pytest.mark.parametrize("name", ("000.json", "0481.json", "wrong.json"))
def test_verify_rejects_noncanonical_or_extra_checkpoint_leaf_names(tmp_path: Path, name: str) -> None:
    # Given: a current checkpoint root with one invalid leaf name.
    request = _checkpoint_request(tmp_path)
    (request.checkpoint_root / "checkpoints" / name).write_bytes(b"{}")

    # When: the descriptor-rooted tree profile is inspected.
    report = verify_characterization(request)

    # Then: noncanonical or extra names fail closed.
    assert report.valid is False


def test_verify_rejects_forged_checkpoint_row_digest(tmp_path: Path) -> None:
    # Given: a canonical checkpoint envelope with a self-consistent but forged row digest.
    request = _checkpoint_request(tmp_path)
    contract = build_characterization_run_contract(request.source_manifest, request.repository_root, shard_count=1, module_roots=request.module_roots)
    source_payload = contract.payload["source"]
    assert isinstance(source_payload, dict)
    records = source_payload["records"]
    assert isinstance(records, dict)
    instance_id = sorted(records)[0]
    checkpoint = build_checkpoint(CheckpointExpectation(SourceManifestDigest(contract.fingerprint), CanonicalRowIndex(0), instance_id, CharacterizationArtifactDigest("b" * 64)))
    leaf = request.checkpoint_root / "checkpoints" / "0000.json"
    leaf.write_bytes(checkpoint.canonical_bytes)
    leaf.chmod(0o600)

    # When: the work verifier checks only the envelope binding.
    report = verify_characterization(request)

    # Then: this must fail once digest truth is recomputed from the scientific row.
    assert report.valid is False


def test_verify_returns_invalid_report_for_forged_checkpoint_fingerprint(tmp_path: Path) -> None:
    # Given: a checkpoint with the true canonical row digest but a forged run fingerprint.
    request = _checkpoint_request(tmp_path)
    contract = build_characterization_run_contract(request.source_manifest, request.repository_root, shard_count=1, module_roots=request.module_roots)
    source_payload = contract.payload["source"]
    assert isinstance(source_payload, dict)
    records = source_payload["records"]
    assert isinstance(records, dict)
    instance_id = sorted(records)[0]
    rows = expected_characterization_rows(contract.payload, request.repository_root)
    digest = hashlib.sha256(canonical(rows[0]).encode()).hexdigest()
    checkpoint = build_checkpoint(CheckpointExpectation(SourceManifestDigest("a" * 64), CanonicalRowIndex(0), instance_id, CharacterizationArtifactDigest(digest)))
    leaf = request.checkpoint_root / "checkpoints" / "0000.json"
    leaf.write_bytes(checkpoint.canonical_bytes)
    leaf.chmod(0o600)

    # When: the parser rejects the binding mismatch.
    report = verify_characterization(request)

    # Then: no typed checkpoint exception escapes the terminal report boundary.
    assert (report.valid, report.errors) == (False, (str(report.errors[0]),))


def test_verify_rejects_permissive_root_and_leaf_modes(tmp_path: Path) -> None:
    # Given: a syntactically current checkpoint root with world-readable metadata.
    request = _checkpoint_request(tmp_path)
    request.checkpoint_root.chmod(0o755)

    # When: root and then contract leaf permissions are permissive.
    root_report = verify_characterization(request)
    request.checkpoint_root.chmod(0o700)
    (request.checkpoint_root / "run-contract.json").chmod(0o644)
    leaf_report = verify_characterization(request)

    # Then: descriptor reads fail closed before content trust.
    assert root_report.valid is False
    assert leaf_report.valid is False


def test_verify_rejects_stale_contract_and_symlinked_checkpoint_leaf(tmp_path: Path) -> None:
    # Given: a current root first made stale and then given a symlink leaf.
    request = _checkpoint_request(tmp_path)
    contract = request.checkpoint_root / "run-contract.json"
    contract.write_bytes(contract.read_bytes() + b"\n")

    # When: stale immutable contract bytes are inspected.
    stale = verify_characterization(request)

    # Then: noncanonical/stale contract bytes cannot be accepted.
    assert stale.valid is False
    _write_current_contract(request)
    target = tmp_path / "target.json"
    target.write_bytes(b"{}")
    (request.checkpoint_root / "checkpoints" / "0000.json").symlink_to(target)
    assert verify_characterization(request).valid is False


def test_verify_rejects_missing_extra_or_noncanonical_final_profile(tmp_path: Path) -> None:
    # Given: an otherwise current checkpoint root and malformed candidate final roots.
    request = _checkpoint_request(tmp_path)
    final_root = tmp_path / "final"
    final_root.mkdir()
    request = VerificationRequest(request.repository_root, request.source_manifest, request.checkpoint_root, final_root, request.module_roots)
    (final_root / "run-contract.json").write_bytes((request.checkpoint_root / "run-contract.json").read_bytes())

    # When: the final tree is incomplete, then contains an unexpected entry.
    missing = verify_characterization(request)
    (final_root / "extra").mkdir()
    extra = verify_characterization(request)

    # Then: neither tree is a valid final artifact profile.
    assert missing.valid is False
    assert extra.valid is False


def test_verify_accepts_complete_synthetic_final_root_and_rejects_semantic_mutations(tmp_path: Path) -> None:
    # Given: test-only canonical final bytes built from 481 replayable synthetic PDDL rows.
    request, final_root = _complete_request(tmp_path)
    control = verify_characterization(request)

    # When: each independent persisted semantic claim is forged.
    assert (control.valid, control.complete, control.publishable) == (True, True, True)
    artifact = final_root / "characterization.jsonl"
    baseline = artifact.read_bytes()
    for key, value in (("partition", "x"), ("status", "failed"), ("domain_sha256", "0" * 64)):
        rows = [json.loads(line) for line in baseline.splitlines()]
        rows[0][key] = value
        artifact.write_bytes(b"".join(canonical(row).encode() + b"\n" for row in rows))
        assert verify_characterization(request).valid is False
        artifact.write_bytes(baseline)
    manifest = final_root / "characterization_manifest.json"
    original_manifest = manifest.read_bytes()
    for key, value in (("owner_approved", 0), ("row_count", 0), ("schema_version", "wrong")):
        payload = json.loads(original_manifest)
        payload[key] = value
        manifest.write_bytes(canonical_json_object(payload) + b"\n")
        assert verify_characterization(request).valid is False
        manifest.write_bytes(original_manifest)

    # Then: the restored control remains accepted without root mutation by verification.
    assert verify_characterization(request).valid is True


def test_verify_rejects_forged_expansion_count_with_recomputed_manifest(tmp_path: Path) -> None:
    # Given: a complete synthetic final root whose artifact digest is refreshed after a trace-accounting forgery.
    request, final_root = _complete_request(tmp_path)
    artifact = final_root / "characterization.jsonl"
    rows = [json.loads(line) for line in artifact.read_bytes().splitlines()]
    rows[0]["bfs"]["exact_search"]["expansion_count"] = 999
    changed = b"".join(canonical(row).encode() + b"\n" for row in rows)
    artifact.write_bytes(changed)
    manifest = json.loads((final_root / "characterization_manifest.json").read_bytes())
    manifest["artifact_sha256"] = hashlib.sha256(changed).hexdigest()
    (final_root / "characterization_manifest.json").write_bytes(canonical_json_object(manifest) + b"\n")

    # When: the manifest remains internally consistent with the forged JSONL bytes.
    report = verify_characterization(request)

    # Then: persisted accounting cannot be authoritative.
    assert report.valid is False


def _checkpoint_request(tmp_path: Path) -> VerificationRequest:
    repository, source = _repository(tmp_path)
    checkpoint_root = tmp_path / "checkpoints"
    checkpoint_root.mkdir(mode=0o700)
    (checkpoint_root / "checkpoints").mkdir(mode=0o700)
    request = VerificationRequest(repository, source, checkpoint_root, None, ("fixture.runner",))
    _write_current_contract(request)
    return request


def _write_current_contract(request: VerificationRequest) -> None:
    contract = build_characterization_run_contract(
        request.source_manifest, request.repository_root, shard_count=1, module_roots=request.module_roots
    )
    (request.checkpoint_root / "run-contract.json").write_bytes(contract.canonical_bytes)
    (request.checkpoint_root / "run-contract.json").chmod(0o600)


def _repository(root: Path) -> tuple[Path, Path]:
    repository = root / "repository"
    package = repository / "fixture"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("\n", encoding="utf-8")
    (package / "runner.py").write_text("VALUE = 1\n", encoding="utf-8")
    domain = repository / "domain.pddl"
    domain.write_text("(define (domain blocksworld) (:requirements :strips) (:predicates (clear ?x) (handempty)))\n", encoding="utf-8")
    paths = {count: repository / f"problem-{count}.pddl" for count in (4, 8, 12)}
    for count, path in paths.items():
        objects = " ".join(f"b{index}" for index in range(count))
        clear = " ".join(f"(clear b{index})" for index in range(count))
        path.write_text(
            f"(define (problem p{count}) (:domain blocksworld) (:objects {objects}) (:init (handempty) {clear}) (:goal (and (handempty))))\n",
            encoding="utf-8",
        )
    rows: list[dict[str, object]] = []
    for split, count, size in (("train", 4, 190), ("train", 8, 198), ("train", 12, 14), ("dev", 12, 39), ("test", 12, 40)):
        bucket = f"bucket-{count}"
        for ordinal in range(size):
            rows.append({"attempt_index": ordinal, "bucket": bucket, "candidate_id": f"blocksworld-{split}-{bucket}-attempt-{ordinal:06d}", "domain_id": "blocksworld", "domain_path": str(domain), "index": ordinal, "instance_id": f"blocksworld-{split}-{bucket}-{ordinal:04d}", "problem_path": str(paths[count]), "split": split})
    source = repository / "accepted.jsonl"
    source.write_bytes(b"".join(canonical_json_object(row) + b"\n" for row in rows))
    phase = repository / "scripts/phase3"
    phase.mkdir(parents=True)
    (repository / "scripts/__init__.py").write_text("\n", encoding="utf-8")
    (phase / "__init__.py").write_text("\n", encoding="utf-8")
    for name in ("cgas_partition_characterization", "cgas_characterization_contract", "cgas_characterization_imports", "cgas_bfs", "local_iw"):
        (phase / f"{name}.py").write_text("VALUE = 1\n", encoding="utf-8")
    return repository, source


def _complete_request(tmp_path: Path) -> tuple[VerificationRequest, Path]:
    base = _checkpoint_request(tmp_path)
    repository, source = base.repository_root, base.source_manifest
    final_root = tmp_path / "final"
    final_root.mkdir(mode=0o700)
    (final_root / "run-contract.json").write_bytes((base.checkpoint_root / "run-contract.json").read_bytes())
    (final_root / "run-contract.json").chmod(0o600)
    contract = build_characterization_run_contract(source, repository, shard_count=1, module_roots=base.module_roots)
    rows = list(expected_characterization_rows(contract.payload, repository))
    artifact = b"".join(canonical(row).encode() + b"\n" for row in rows)
    (final_root / "characterization.jsonl").write_bytes(artifact)
    (final_root / "characterization.jsonl").chmod(0o600)
    implementation = {key: hashlib.sha256((repository / path).read_bytes()).hexdigest() for key, path in {"bfs_sha256": "scripts/phase3/cgas_bfs.py", "iw_sha256": "scripts/phase3/local_iw.py", "module_sha256": "scripts/phase3/cgas_partition_characterization.py"}.items()}
    source_digests = []
    for row in rows:
        identity = row["source_identity"]
        assert isinstance(identity, dict)
        digest = identity["source_record_sha256"]
        assert isinstance(digest, str)
        source_digests.append(digest)
    manifest = {"artifact_sha256": hashlib.sha256(artifact).hexdigest(), "counts_by_object": {"4": 190, "8": 198, "12": 93}, "counts_by_split": {"dev": 39, "test": 40, "train": 402}, "implementation": implementation, "limits": CHARACTERIZATION_LIMITS, "owner_approved": False, "row_count": len(rows), "schema_version": SCHEMA_VERSION, "source_records_sha256": digest_text("|".join(sorted(source_digests)))}
    (final_root / "characterization_manifest.json").write_bytes(canonical_json_object(manifest) + b"\n")
    (final_root / "characterization_manifest.json").chmod(0o600)
    return VerificationRequest(repository, source, base.checkpoint_root, final_root, base.module_roots), final_root


def _snapshot(root: Path) -> tuple[tuple[str, int, int, str], ...]:
    return tuple(
        sorted(
            (path.relative_to(root).as_posix(), path.stat(follow_symlinks=False).st_mode, path.stat(follow_symlinks=False).st_size, hashlib.sha256(path.read_bytes()).hexdigest())
            for path in root.rglob("*")
            if path.is_file()
        )
    )
