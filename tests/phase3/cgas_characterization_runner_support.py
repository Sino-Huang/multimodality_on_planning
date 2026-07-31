from __future__ import annotations

from pathlib import Path

from scripts.phase3.cgas_characterization_contract import CharacterizationRunContract
from scripts.phase3.cgas_characterization_runner import RunRequest, RunnerExecution
from scripts.phase3.cgas_characterization_verifier import CharacterizationVerificationReport
from scripts.phase3.cgas_serialization import canonical_json_object


def request(root: Path, name: str, shard_count: int = 1, shard_index: int = 0) -> RunRequest:
    private_root = root / f"{name}-private"
    private_root.mkdir(mode=0o700)
    private_root.chmod(0o700)
    return RunRequest(root, root / "accepted.jsonl", root / name, private_root, shard_count, shard_index)


def contract(count: int = 481, reverse: bool = False, fingerprint: str = "a" * 64) -> CharacterizationRunContract:
    identifiers = [f"synthetic-{index:04d}" for index in range(count)]
    if reverse:
        identifiers.reverse()
    records = {
        identifier: {
            "domain_path": "domain.pddl",
            "domain_sha256": "d" * 64,
            "problem_path": "problem.pddl",
            "problem_sha256": "p" * 64,
            "source_record_sha256": "s" * 64,
            "split": "train",
        }
        for identifier in identifiers
    }
    payload: dict[str, object] = {"source": {"records": records}}
    return CharacterizationRunContract(canonical_json_object(payload), fingerprint, payload)


def row(instance_id: str, *, source_digest: str = "s" * 64) -> dict[str, object]:
    return {
        "domain_sha256": "d" * 64,
        "instance_id": instance_id,
        "problem_sha256": "p" * 64,
        "source_identity": {"source_record_sha256": source_digest},
        "split": "train",
    }


class Sink:
    def __init__(self) -> None:
        self.flush_count = 0
        self.lines: list[str] = []

    def flush(self) -> None:
        self.flush_count += 1

    def write(self, text: str, /) -> int:
        self.lines.append(text)
        return len(text)


def execution(
    run_contract: CharacterizationRunContract,
    calls: list[str],
    sink: Sink,
    *,
    valid: bool = True,
) -> RunnerExecution:
    return RunnerExecution(
        lambda instance: calls.append(instance.instance_id) or row(instance.instance_id),
        lambda _request: run_contract,
        lambda _request: CharacterizationVerificationReport(valid, False, False, () if valid else ("invalid",), 0),
        sink,
    )
