from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Literal

import pytest
from typing_extensions import assert_never

import scripts.phase3.cgas_characterization_assembly as assembly
import scripts.phase3.cgas_characterization_assembly_fs as assembly_fs
from cgas_characterization_assembly_support import checkpoint_request, synthetic_request, write_checkpoint_history
from scripts.phase3.cgas_characterization_verifier import verify_characterization


def test_synthetic_checkpoint_fixture_uses_hardened_root_and_leaf_metadata(tmp_path: Path) -> None:
    # Given: explicitly synthetic work and its current checkpoint contract.
    request, _private_root = synthetic_request(tmp_path)
    write_checkpoint_history(request, (0,))

    # When: the test-only fixture is inspected at the verifier filesystem boundary.
    roots = (request.repository_root, request.checkpoint_root, request.checkpoint_root / "checkpoints")
    leaves = (request.checkpoint_root / "run-contract.json", request.checkpoint_root / "checkpoints" / "0000.json")

    # Then: roots and leaves meet the hardened ownership, permission, and link-count profile.
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o700 and path.stat().st_uid == os.geteuid() for path in roots)
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 and path.stat().st_uid == os.geteuid() and path.stat().st_nlink == 1 for path in leaves)


def test_assembly_is_byte_identical_for_clean_reverse_sharded_and_resumed_histories(tmp_path: Path) -> None:
    # Given: four complete test-only checkpoint histories with distinct creation orders.
    histories = (
        tuple(range(481)),
        tuple(reversed(range(481))),
        tuple(range(0, 481, 3)) + tuple(range(1, 481, 3)) + tuple(range(2, 481, 3)),
        tuple(range(197)) + tuple(range(197, 481)),
    )
    candidates: list[Path] = []
    base, private_root = synthetic_request(tmp_path)
    for index, history in enumerate(histories):
        request = checkpoint_request(base, tmp_path / f"checkpoints-{index}")
        write_checkpoint_history(request, history)

        # When: each verified complete history is assembled into a private candidate.
        candidate = assembly.assemble_characterization_candidate(request, private_root)
        candidates.append(candidate.candidate_root)

        # Then: final verification accepts the private, exact three-file artifact.
        report = verify_characterization(
            request.__class__(request.repository_root, request.source_manifest, request.checkpoint_root, candidate.candidate_root, request.module_roots)
        )
        assert (report.valid, report.complete, report.publishable) == (True, True, True)
        assert stat.S_IMODE(candidate.candidate_root.stat().st_mode) == 0o700
        assert {path.name for path in candidate.candidate_root.iterdir()} == {
            "characterization.jsonl",
            "characterization_manifest.json",
            "run-contract.json",
        }
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in candidate.candidate_root.iterdir())
        assert (candidate.candidate_root / "characterization.jsonl").read_bytes().endswith(b"\n")
        assert (candidate.candidate_root / "characterization_manifest.json").read_bytes().endswith(b"\n")
        rows = [json.loads(line) for line in (candidate.candidate_root / "characterization.jsonl").read_bytes().splitlines()]
        assert all(set(row).isdisjoint({"row_digest", "row_index", "run_fingerprint"}) for row in rows)
        assert json.loads((candidate.candidate_root / "characterization_manifest.json").read_bytes())["owner_approved"] is False
    baseline = tuple((candidate / name).read_bytes() for name in ("characterization.jsonl", "characterization_manifest.json", "run-contract.json") for candidate in candidates[:1])
    for candidate in candidates[1:]:
        assert tuple((candidate / name).read_bytes() for name in ("characterization.jsonl", "characterization_manifest.json", "run-contract.json")) == baseline


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "foreign", "stale", "newline"))
def test_assembly_rejects_unverified_checkpoint_histories(
    tmp_path: Path, mutation: Literal["missing", "duplicate", "foreign", "stale", "newline"]
) -> None:
    # Given: a test-only complete history with one invalid checkpoint condition.
    request, private_root = synthetic_request(tmp_path)
    write_checkpoint_history(request, tuple(range(481)))
    leaves = request.checkpoint_root / "checkpoints"
    match mutation:
        case "missing":
            (leaves / "0480.json").unlink()
        case "duplicate":
            (leaves / "0001.json").write_bytes((leaves / "0000.json").read_bytes())
        case "foreign":
            (leaves / "0000.json").write_bytes(b'{"instance_id":"foreign","row_digest":"' + b"0" * 64 + b'","row_index":0,"run_fingerprint":"' + b"0" * 64 + b'"}')
        case "stale":
            (request.checkpoint_root / "run-contract.json").write_bytes(b"{}")
        case "newline":
            leaf = leaves / "0000.json"
            leaf.write_bytes(leaf.read_bytes() + b"\n")
        case unreachable:
            assert_never(unreachable)

    # When: assembly requires the independently verified complete work state.
    with pytest.raises(assembly.CharacterizationAssemblyError):
        assembly.assemble_characterization_candidate(request, private_root)

    # Then: no candidate is created and no final root is exposed.
    assert not tuple(private_root.iterdir())


def test_assembly_retains_private_candidate_when_artifact_fsync_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: verified work and a write path that fails during the first candidate artifact fsync.
    request, private_root = synthetic_request(tmp_path)
    write_checkpoint_history(request, tuple(range(481)))
    original_fsync = assembly_fs.os.fsync
    calls = 0

    def fail_artifact_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected artifact fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(assembly_fs.os, "fsync", fail_artifact_fsync)

    # When: assembly reaches its durable artifact write boundary.
    with pytest.raises(assembly.CharacterizationAssemblyError, match="fsync") as raised:
        assembly.assemble_characterization_candidate(request, private_root)

    # Then: the incomplete candidate stays private and its path is reported.
    assert raised.value.candidate_root is not None
    assert raised.value.candidate_root.parent == private_root
    assert raised.value.candidate_root.exists()


def test_assembly_retains_candidate_when_final_verifier_rejects_extra_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: verified work and an injected unexpected candidate entry after durable assembly.
    request, private_root = synthetic_request(tmp_path)
    write_checkpoint_history(request, tuple(range(481)))
    original_write = assembly.write_candidate_files

    def add_extra_after_write(candidate: Path, files: tuple[assembly.CandidateFile, ...]) -> None:
        original_write(candidate, files)
        (candidate / "unexpected").write_bytes(b"not-final")

    monkeypatch.setattr(assembly, "write_candidate_files", add_extra_after_write)

    # When: the standalone final verifier evaluates the corrupted candidate profile.
    with pytest.raises(assembly.CharacterizationAssemblyError, match="final verifier") as raised:
        assembly.assemble_characterization_candidate(request, private_root)

    # Then: no final root is published and the rejected private candidate is retained.
    assert raised.value.candidate_root is not None
    assert (raised.value.candidate_root / "unexpected").read_bytes() == b"not-final"
