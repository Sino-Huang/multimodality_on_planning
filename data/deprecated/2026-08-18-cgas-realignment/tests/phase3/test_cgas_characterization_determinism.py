from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import scripts.phase3.cgas_characterization_cli as cli
from cgas_characterization_assembly_support import checkpoint_request, synthetic_request, write_checkpoint_history
from scripts.phase3.cgas_characterization_bundle import parse_bundle
from scripts.phase3.cgas_characterization_state_directory import open_trusted_state_directory
from scripts.phase3.cgas_characterization_verifier import VerificationRequest, verify_characterization


_BUNDLE_MAGIC = b"cgas-final-bundle-v1\n"


@dataclass(frozen=True, slots=True)
class BundleEvidence:
    contract_bytes: bytes
    contract_sha256: str
    bundle_bytes: bytes
    bundle_sha256: str
    run_fingerprint: str
    header_sha256: str
    member_table: tuple[tuple[str, int, str], ...]
    jsonl_bytes: bytes
    jsonl_sha256: str
    manifest_bytes: bytes
    manifest_sha256: str
    manifest: dict[str, object]


def test_finalization_is_byte_identical_for_synthetic_forward_reverse_and_resumed_histories(tmp_path: Path) -> None:
    # Given: three complete synthetic 481-row histories under one identical run contract.
    base, private_root = synthetic_request(tmp_path)
    histories = (
        (tuple(range(481)),),
        (tuple(reversed(range(481))),),
        (tuple(range(197)), tuple(range(197, 481))),
    )

    # When: each history is finalized and verified through the public lifecycle.
    evidence = tuple(
        _finalize_history(base, private_root, f"same-contract-{index}.cgas", history, shard_count=1)
        for index, history in enumerate(histories)
    )

    # Then: contract-scoped provenance and every parsed logical member are byte-identical.
    baseline = evidence[0]
    assert all(item.contract_bytes == baseline.contract_bytes for item in evidence[1:])
    assert all(item.contract_sha256 == baseline.contract_sha256 for item in evidence[1:])
    assert all(item.run_fingerprint == baseline.run_fingerprint for item in evidence[1:])
    assert all(item.bundle_bytes == baseline.bundle_bytes for item in evidence[1:])
    assert all(item.bundle_sha256 == baseline.bundle_sha256 for item in evidence[1:])
    assert all(item.header_sha256 == baseline.header_sha256 for item in evidence[1:])
    assert all(item.member_table == baseline.member_table for item in evidence[1:])
    assert all(item.jsonl_bytes == baseline.jsonl_bytes for item in evidence[1:])
    assert all(item.manifest_bytes == baseline.manifest_bytes for item in evidence[1:])


def test_synthetic_two_and_three_shard_finalizations_are_scientifically_equal_but_contract_distinct(tmp_path: Path) -> None:
    # Given: identical synthetic 481-row sources whose work contracts bind different shard counts.
    base, private_root = synthetic_request(tmp_path)

    # When: complete 2-shard and 3-shard histories are finalized and publicly verified.
    two_shards = _finalize_history(base, private_root, "two-shards.cgas", (tuple(range(481)),), shard_count=2)
    three_shards = _finalize_history(
        base,
        private_root,
        "three-shards.cgas",
        (tuple(range(0, 481, 3)) + tuple(range(1, 481, 3)) + tuple(range(2, 481, 3)),),
        shard_count=3,
    )

    # Then: provenance bundles differ, while all scientific outputs and aggregates remain exact.
    assert two_shards.contract_bytes != three_shards.contract_bytes
    assert two_shards.contract_sha256 != three_shards.contract_sha256
    assert two_shards.run_fingerprint != three_shards.run_fingerprint
    assert two_shards.bundle_bytes != three_shards.bundle_bytes
    assert two_shards.bundle_sha256 != three_shards.bundle_sha256
    assert two_shards.header_sha256 != three_shards.header_sha256
    assert two_shards.jsonl_bytes == three_shards.jsonl_bytes
    assert two_shards.jsonl_sha256 == three_shards.jsonl_sha256
    assert two_shards.manifest_bytes == three_shards.manifest_bytes
    assert two_shards.manifest_sha256 == three_shards.manifest_sha256
    for field in (
        "artifact_sha256",
        "source_records_sha256",
        "counts_by_object",
        "counts_by_split",
        "implementation",
    ):
        assert two_shards.manifest[field] == three_shards.manifest[field]


def _finalize_history(
    base: VerificationRequest,
    private_root: Path,
    bundle_name: str,
    history: tuple[tuple[int, ...], ...],
    *,
    shard_count: int,
) -> BundleEvidence:
    with open_trusted_state_directory(base.repository_root, create=False) as state:
        work = checkpoint_request(base, state.work_path(bundle_name), shard_count=shard_count)
        for batch in history:
            write_checkpoint_history(work, batch, shard_count=shard_count)
        bundle_path = state.final_path(bundle_name)
    command = (
        "finalize",
        "--repository-root",
        str(base.repository_root),
        "--source-manifest",
        str(base.source_manifest),
        "--bundle-name",
        bundle_name,
        "--private-root",
        str(private_root),
        "--module-root",
        "fixture.runner",
    )
    assert cli.main(command) == 0
    request = VerificationRequest(base.repository_root, base.source_manifest, work.checkpoint_root, bundle_path, base.module_roots)
    assert verify_characterization(request).publishable is True
    bundle_bytes = bundle_path.read_bytes()
    parsed = parse_bundle(bundle_bytes)
    header_start = len(_BUNDLE_MAGIC) + 4
    header_size = int.from_bytes(bundle_bytes[len(_BUNDLE_MAGIC) : header_start], "big")
    header = bundle_bytes[header_start : header_start + header_size]
    assert json.loads(header)["run_fingerprint"] == parsed.run_fingerprint
    members = {member.name: member.contents for member in parsed.members}
    contract_bytes = (work.checkpoint_root / "run-contract.json").read_bytes()
    assert members["run-contract.json"] == contract_bytes
    manifest_bytes = members["characterization_manifest.json"]
    manifest = json.loads(manifest_bytes)
    assert isinstance(manifest, dict)
    return BundleEvidence(
        contract_bytes,
        hashlib.sha256(contract_bytes).hexdigest(),
        bundle_bytes,
        hashlib.sha256(bundle_bytes).hexdigest(),
        parsed.run_fingerprint,
        hashlib.sha256(header).hexdigest(),
        tuple((member.name, len(member.contents), hashlib.sha256(member.contents).hexdigest()) for member in parsed.members),
        members["characterization.jsonl"],
        hashlib.sha256(members["characterization.jsonl"]).hexdigest(),
        manifest_bytes,
        hashlib.sha256(manifest_bytes).hexdigest(),
        manifest,
    )
