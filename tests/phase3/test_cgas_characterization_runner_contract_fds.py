from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from cgas_characterization_runner_support import Sink, contract, row, request

from scripts.phase3.cgas_characterization_runner import RunMode, RunnerError, RunnerExecution, run
from scripts.phase3.cgas_characterization_verifier import CharacterizationVerificationReport, VerificationRequest
from scripts.phase3.cgas_partition_contracts import CharacterizationInput


def test_runner_pins_contract_through_twenty_gpfs_same_byte_recreations() -> None:
    # Given: a repository-local work root whose verifier repeatedly unlinks and recreates its same-byte contract leaf.
    with TemporaryDirectory(prefix=".cgas-contract-pin-", dir=Path.cwd()) as temporary:
        root = Path(temporary)
        run_request = request(root, "final")
        run_contract = contract(count=1)
        calls: list[str] = []
        run(run_request, RunMode.FRESH, _execution(run_contract, calls))
        leaf = run_request.final_root.with_name("final.work") / "run-contract.json"
        descriptor_count = _descriptor_count()

        def verify(_request: VerificationRequest) -> CharacterizationVerificationReport:
            assert _descriptor_count() >= descriptor_count + 2
            contents = leaf.read_bytes()
            for _ in range(20):
                leaf.unlink()
                leaf.write_bytes(contents)
                leaf.chmod(0o600)
            return CharacterizationVerificationReport(True, False, False, (), 0)

        runner_execution = RunnerExecution(lambda instance: calls.append(instance.instance_id) or row(instance.instance_id), lambda _request: run_contract, verify, Sink())

        # When: resume holds its initial contract descriptor across verifier execution.
        with pytest.raises(RunnerError, match="run_contract_drift"):
            run(run_request, RunMode.RESUME, runner_execution)

        # Then: inode reuse attempts fail before characterization and release the pinned descriptor.
        assert calls == []
        assert _descriptor_count() == descriptor_count


@pytest.mark.parametrize("phase,mutation", (("verifier", "hardlink"), ("verifier", "removal"), ("verifier", "content"), ("row", "hardlink"), ("row", "removal"), ("row", "content")))
def test_runner_rejects_contract_mutation_while_pinned(tmp_path: Path, phase: str, mutation: str) -> None:
    # Given: a resumable root and an injected verifier or characterizer mutation.
    run_request = request(tmp_path, "final")
    run_contract = contract(count=1)
    calls: list[str] = []
    run(run_request, RunMode.FRESH, _execution(run_contract, calls))
    leaf = run_request.final_root.with_name("final.work") / "run-contract.json"
    descriptor_count = _descriptor_count()

    def verify(_request: VerificationRequest) -> CharacterizationVerificationReport:
        assert _descriptor_count() >= descriptor_count + 2
        if phase == "verifier":
            _mutate_contract(leaf, mutation)
        return CharacterizationVerificationReport(True, False, False, (), 0)

    def characterize(instance: CharacterizationInput) -> dict[str, object]:
        assert _descriptor_count() >= descriptor_count + 2
        calls.append(instance.instance_id)
        if phase == "row":
            _mutate_contract(leaf, mutation)
        return row(instance.instance_id)

    runner_execution = RunnerExecution(characterize, lambda _request: run_contract, verify, Sink())

    # When: resume crosses the selected mutation boundary.
    with pytest.raises(RunnerError, match="run_contract_drift"):
        run(run_request, RunMode.RESUME, runner_execution)

    # Then: every mutation fails closed and cleanup restores the descriptor baseline.
    assert _descriptor_count() == descriptor_count


def _execution(run_contract, calls: list[str]) -> RunnerExecution:
    return RunnerExecution(
        lambda instance: calls.append(instance.instance_id) or row(instance.instance_id),
        lambda _request: run_contract,
        lambda _request: CharacterizationVerificationReport(True, False, False, (), 0),
        Sink(),
    )


def _mutate_contract(leaf: Path, mutation: str) -> None:
    contents = leaf.read_bytes()
    match mutation:
        case "hardlink":
            target = leaf.with_name("contract-link-target.json")
            target.write_bytes(contents)
            target.chmod(0o600)
            leaf.unlink()
            os.link(target, leaf)
        case "removal":
            leaf.unlink()
        case "content":
            leaf.write_bytes(contents.replace(b"domain.pddl", b"domain.qddl"))
        case unreachable:
            raise AssertionError(unreachable)


def _descriptor_count() -> int:
    return len(os.listdir("/proc/self/fd"))
