from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path

import pytest

from cgas_characterization_runner_support import Sink, contract, execution, row, request

from scripts.phase3.cgas_characterization_contract import CharacterizationRunContract
from scripts.phase3.cgas_characterization_checkpoint import CheckpointEntry, VerifiedCheckpoint, build_checkpoint
from scripts.phase3.cgas_characterization_checkpoint_contracts import CheckpointExpectation, checkpoint_name
from scripts.phase3.cgas_characterization_runner import RunMode, RunRequest, RunnerError, RunnerExecution, run
from scripts.phase3.cgas_characterization_verifier import CharacterizationVerificationReport, VerificationRequest
from scripts.phase3.cgas_characterization_types import CanonicalRowIndex, CharacterizationArtifactDigest, SourceManifestDigest
from scripts.phase3.cgas_partition_contracts import CharacterizationInput
from scripts.phase3.cgas_serialization import canonical, canonical_json_object


def test_reverse_shards_then_resume_matches_forward_checkpoint_bytes(tmp_path: Path) -> None:
    # Given: forward and reverse source mappings for separate synthetic 481-row roots.
    forward_request = request(tmp_path, "forward", shard_count=2)
    reverse_request = request(tmp_path, "reverse", shard_count=2)
    forward_contract = contract()
    reverse_contract = contract(reverse=True)
    forward_calls: list[str] = []
    reverse_calls: list[str] = []
    forward_execution = execution(forward_contract, forward_calls, Sink())
    reverse_execution = execution(reverse_contract, reverse_calls, Sink())
    run(forward_request, RunMode.FRESH, forward_execution)
    run(reverse_request, RunMode.FRESH, reverse_execution)

    # When: forward shards, reversed shards, and a no-op resume complete independently.
    for shard_index in (0, 1):
        run(_with_shard(forward_request, shard_index), RunMode.SHARD, forward_execution)
    for shard_index in (1, 0):
        run(_with_shard(reverse_request, shard_index), RunMode.SHARD, reverse_execution)
    assert run(forward_request, RunMode.RESUME, forward_execution).characterized_count == 0
    assert run(reverse_request, RunMode.RESUME, reverse_execution).characterized_count == 0

    # Then: every independently published checkpoint byte is identical.
    assert _checkpoint_bytes(forward_request.final_root) == _checkpoint_bytes(reverse_request.final_root)


def test_resume_validates_work_then_fills_only_missing_in_ascending_order(tmp_path: Path) -> None:
    # Given: one precomputed shard and an injected verifier that records the work validation.
    run_request = request(tmp_path, "final", shard_count=2, shard_index=0)
    calls: list[str] = []
    verifications: list[Path] = []
    run_contract = contract()
    sink = Sink()
    run_execution = RunnerExecution(
        lambda instance: calls.append(instance.instance_id) or row(instance.instance_id),
        lambda _request: run_contract,
        lambda verification: verifications.append(verification.checkpoint_root)
        or CharacterizationVerificationReport(True, False, False, (), 0),
        sink,
    )
    run(run_request, RunMode.FRESH, run_execution)
    run(run_request, RunMode.SHARD, run_execution)
    calls.clear()
    verifications.clear()

    # When: resume chooses all rows that remain missing after verified work inspection.
    report = run(run_request, RunMode.RESUME, run_execution)

    # Then: it runs only odd canonical indices in ascending order and flushes each durable progress event.
    assert calls == [f"synthetic-{index:04d}" for index in range(1, 481, 2)]
    assert report.characterized_count == len(calls)
    assert verifications == [run_request.final_root.with_name("final.work"), run_request.final_root.with_name("final.work")]
    assert sink.flush_count == 481
    assert all(
        set(json.loads(line)) == {"completed", "index", "instance_id", "phase", "shard_count", "shard_index", "status", "total"}
        for line in sink.lines
    )


@pytest.mark.parametrize("valid", (False,))
def test_invalid_work_blocks_before_any_characterizer_call(tmp_path: Path, valid: bool) -> None:
    # Given: a fresh root followed by a malformed-or-stale verifier result.
    run_request = request(tmp_path, "final")
    calls: list[str] = []
    run_contract = contract()
    run(run_request, RunMode.FRESH, execution(run_contract, calls, Sink()))

    # When: resume asks the verifier to authorize persisted state.
    with pytest.raises(RunnerError, match="invalid_work_state"):
        run(run_request, RunMode.RESUME, execution(run_contract, calls, Sink(), valid=valid))

    # Then: no scientific call occurs after the failed-closed work boundary.
    assert calls == []


def test_contract_or_identity_drift_during_row_blocks_checkpoint_publication(tmp_path: Path) -> None:
    # Given: a row callback that changes the immutable contract and returns a wrong source identity.
    run_request = request(tmp_path, "final")
    baseline = contract()
    changed = CharacterizationRunContract(canonical_json_object({"changed": True}), "b" * 64, {"source": {"records": {}}})
    calls: list[str] = []
    use_changed = False

    def characterize(instance: CharacterizationInput) -> dict[str, object]:
        nonlocal use_changed
        use_changed = True
        calls.append("called")
        return row(instance.instance_id)

    def build(_request: RunRequest) -> CharacterizationRunContract:
        return changed if use_changed else baseline

    run_execution = RunnerExecution(
        characterize,
        build,
        lambda _request: CharacterizationVerificationReport(True, False, False, (), 0),
        Sink(),
    )
    run(run_request, RunMode.FRESH, run_execution)

    # When: the first row races a source/PDDL/implementation contract recheck.
    with pytest.raises(RunnerError, match="run_contract_drift"):
        run(run_request, RunMode.RESUME, run_execution)

    # Then: the row is never published after the post-characterization identity boundary.
    assert calls == ["called"]
    assert not list((run_request.final_root.with_name("final.work") / "checkpoints").iterdir())


@pytest.mark.parametrize("replacement", ("symlink", "hardlink", "regular"))
def test_runner_rejects_same_byte_contract_leaf_substitution_before_characterization(
    tmp_path: Path, replacement: str
) -> None:
    # Given: a verifier-approved one-row work root and an external same-byte contract substitute.
    run_request = request(tmp_path, "final")
    run_contract = contract(count=1)
    calls: list[str] = []
    run(run_request, RunMode.FRESH, execution(run_contract, calls, Sink()))
    leaf = run_request.final_root.with_name("final.work") / "run-contract.json"
    target = tmp_path / "contract-target.json"
    target.write_bytes(leaf.read_bytes())
    target.chmod(0o600)

    def verify_after_substitution(_request: VerificationRequest) -> CharacterizationVerificationReport:
        leaf.unlink()
        match replacement:
            case "symlink":
                leaf.symlink_to(target)
            case "hardlink":
                os.link(target, leaf)
            case "regular":
                leaf.write_bytes(target.read_bytes())
                leaf.chmod(0o600)
            case unreachable:
                raise AssertionError(unreachable)
        return CharacterizationVerificationReport(True, False, False, (), 0)

    run_execution = RunnerExecution(
        lambda instance: calls.append(instance.instance_id) or row(instance.instance_id),
        lambda _request: run_contract,
        verify_after_substitution,
        Sink(),
    )

    # When: resume performs its first per-row contract recheck.
    with pytest.raises(RunnerError, match="run_contract_drift"):
        run(run_request, RunMode.RESUME, run_execution)

    # Then: no same-byte substitute reaches the characterizer or checkpoint publication.
    assert calls == []
    assert not list((run_request.final_root.with_name("final.work") / "checkpoints").iterdir())


def test_runner_rejects_same_byte_contract_inode_replacement_after_characterization(tmp_path: Path) -> None:
    # Given: one row whose characterizer swaps the immutable contract for a same-byte new inode.
    run_request = request(tmp_path, "final")
    run_contract = contract(count=1)
    calls: list[str] = []
    run(run_request, RunMode.FRESH, execution(run_contract, calls, Sink()))
    leaf = run_request.final_root.with_name("final.work") / "run-contract.json"

    def characterize(instance: CharacterizationInput) -> dict[str, object]:
        contents = leaf.read_bytes()
        leaf.unlink()
        leaf.write_bytes(contents)
        leaf.chmod(0o600)
        calls.append(instance.instance_id)
        return row(instance.instance_id)

    run_execution = RunnerExecution(
        characterize,
        lambda _request: run_contract,
        lambda _request: CharacterizationVerificationReport(True, False, False, (), 0),
        Sink(),
    )

    # When: the post-characterization contract recheck observes the replacement.
    with pytest.raises(RunnerError, match="run_contract_drift"):
        run(run_request, RunMode.RESUME, run_execution)

    # Then: the row is never published despite byte-for-byte equality.
    assert calls == ["synthetic-0000"]
    assert not list((run_request.final_root.with_name("final.work") / "checkpoints").iterdir())


@pytest.mark.parametrize("mutation", ("dangling", "invalid", "valid"))
def test_runner_blocks_new_checkpoint_entry_after_verification_before_characterization(
    tmp_path: Path, mutation: str
) -> None:
    # Given: an empty verifier snapshot and a post-verification checkpoint-root mutation.
    run_request = request(tmp_path, "final")
    run_contract = contract()
    calls: list[str] = []
    run(run_request, RunMode.FRESH, execution(run_contract, calls, Sink()))

    def verify_after_mutation(_request: VerificationRequest) -> CharacterizationVerificationReport:
        _mutate_checkpoint(run_request, run_contract, mutation)
        return CharacterizationVerificationReport(True, False, False, (), 0, ())

    run_execution = RunnerExecution(
        lambda instance: calls.append(instance.instance_id) or row(instance.instance_id),
        lambda _request: run_contract,
        verify_after_mutation,
        Sink(),
    )

    # When: resume derives missing indices after the pinned verifier result.
    with pytest.raises(RunnerError, match="checkpoint_state_drift"):
        run(run_request, RunMode.RESUME, run_execution)

    # Then: dangling, malformed, and valid new checkpoint leaves all block before characterization.
    assert calls == []


def test_runner_blocks_replaced_checkpoint_after_verification_before_characterization(tmp_path: Path) -> None:
    # Given: a verifier-pinned valid checkpoint whose same-name leaf is replaced afterward.
    run_request = request(tmp_path, "final")
    run_contract = contract()
    calls: list[str] = []
    run(run_request, RunMode.FRESH, execution(run_contract, calls, Sink()))
    path = _write_valid_checkpoint(run_request, run_contract, 0)
    snapshot = (_entry(path),)

    def verify_after_replacement(_request: VerificationRequest) -> CharacterizationVerificationReport:
        path.unlink()
        _write_valid_checkpoint(run_request, run_contract, 0)
        return CharacterizationVerificationReport(True, False, False, (), 1, snapshot)

    run_execution = RunnerExecution(
        lambda instance: calls.append(instance.instance_id) or row(instance.instance_id),
        lambda _request: run_contract,
        verify_after_replacement,
        Sink(),
    )

    # When: resume rechecks the pinned checkpoint identity immediately before work.
    with pytest.raises(RunnerError, match="checkpoint_state_drift"):
        run(run_request, RunMode.RESUME, run_execution)

    # Then: same-name replacement cannot be silently treated as completed state.
    assert calls == []


def _with_shard(request_value: RunRequest, shard_index: int) -> RunRequest:
    return RunRequest(
        request_value.repository_root,
        request_value.source_manifest,
        request_value.final_root,
        request_value.private_root,
        request_value.shard_count,
        shard_index,
        request_value.module_roots,
    )


def _checkpoint_bytes(final_root: Path) -> tuple[bytes, ...]:
    return tuple(path.read_bytes() for path in sorted((final_root.with_name(f"{final_root.name}.work") / "checkpoints").iterdir()))


def _mutate_checkpoint(run_request: RunRequest, run_contract: CharacterizationRunContract, mutation: str) -> None:
    path = run_request.final_root.with_name("final.work") / "checkpoints" / "0000.json"
    match mutation:
        case "dangling":
            path.symlink_to(path.with_name("missing-target"))
        case "invalid":
            path.write_bytes(b"{}")
            path.chmod(0o600)
        case "valid":
            _write_valid_checkpoint(run_request, run_contract, 0)
        case unreachable:
            raise AssertionError(unreachable)


def _write_valid_checkpoint(run_request: RunRequest, run_contract: CharacterizationRunContract, index: int) -> Path:
    checkpoint = _checkpoint(run_contract, index)
    path = run_request.final_root.with_name("final.work") / "checkpoints" / checkpoint_name(CanonicalRowIndex(index))
    path.write_bytes(checkpoint.canonical_bytes)
    path.chmod(0o600)
    return path


def _checkpoint(run_contract: CharacterizationRunContract, index: int):
    instance_id = f"synthetic-{index:04d}"
    row_digest = CharacterizationArtifactDigest(hashlib.sha256(canonical(row(instance_id)).encode()).hexdigest())
    return build_checkpoint(
        CheckpointExpectation(SourceManifestDigest(run_contract.fingerprint), CanonicalRowIndex(index), instance_id, row_digest)
    )


def _entry(path: Path) -> CheckpointEntry:
    status = path.stat(follow_symlinks=False)
    return CheckpointEntry(path.name, status.st_dev, status.st_ino, status.st_size)
