from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.episode_evidence import (
    EVIDENCE_SCHEMA_VERSION,
    EpisodeEvidenceError,
    materialize_episode_artifacts,
    read_episode_evidence,
    replay_episode,
    replay_episode_evidence,
    verify_episode_evidence,
    write_episode_evidence,
)
from examples.planning_benchmark_slice.search_episode import run_search_episode
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

REPO_ROOT = Path(__file__).resolve().parents[2]
NONTRIVIAL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_nontrivial.json"
EMPTY_GOAL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_empty_goal.json"


def _receipts(tmp_path: Path) -> tuple[GateReceipt, AuthorizationReceipt]:
    binding = ReceiptBinding(
        contract_id="issue-49-bfs-development-v1",
        attempt_id="episode-codec-test",
        output_root=(tmp_path / "episode-evidence").resolve(),
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    return gate, AuthorizationReceipt(binding=binding, gate_receipt_id=gate.receipt_id)


def _run_exact(tmp_path: Path, fixture: Path, budget: int) -> dict:
    gate, authorization = _receipts(tmp_path)
    return run_search_episode(
        fixture,
        "bfs",
        "text-state",
        "exact",
        budget,
        gate,
        authorization,
    )


def test_codec_is_deterministic_compact_and_replayable(tmp_path: Path) -> None:
    episode = _run_exact(tmp_path, NONTRIVIAL_FIXTURE, 64)
    first_path = tmp_path / "first.json.gz"
    second_path = tmp_path / "second.json.gz"

    first_manifest = write_episode_evidence(first_path, episode)
    second_manifest = write_episode_evidence(second_path, episode)

    assert first_path.read_bytes() == second_path.read_bytes()
    assert first_manifest == second_manifest
    assert first_manifest == {
        "codec_version": "canonical_json_gzip_v4",
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "stored_size_bytes": first_path.stat().st_size,
    }
    assert read_episode_evidence(first_path) == episode
    assert replay_episode_evidence(first_path) == episode
    assert verify_episode_evidence(first_path)["result"] == episode["result"]
    logical_bytes = gzip.decompress(first_path.read_bytes())
    assert json.loads(logical_bytes) == episode


@pytest.mark.parametrize(
    ("fixture", "budget", "expected_expansions", "expected_goal"),
    (
        (EMPTY_GOAL_FIXTURE, 4, 0, True),
        (NONTRIVIAL_FIXTURE, 1, 1, False),
    ),
)
def test_codec_round_trips_empty_and_budget_exhausted_traces(
    tmp_path: Path,
    fixture: Path,
    budget: int,
    expected_expansions: int,
    expected_goal: bool,
) -> None:
    episode = _run_exact(tmp_path, fixture, budget)
    path = tmp_path / f"trace-{expected_expansions}.json.gz"

    write_episode_evidence(path, episode)

    assert replay_episode_evidence(path) == episode
    assert episode["result"]["expansion_count"] == expected_expansions
    assert episode["result"]["goal_reached"] is expected_goal


@pytest.mark.parametrize("tamper", ["flip", "truncate"])
def test_codec_rejects_broken_gzip(tmp_path: Path, tamper: str) -> None:
    episode = _run_exact(tmp_path, NONTRIVIAL_FIXTURE, 4)
    source = tmp_path / "source.json.gz"
    target = tmp_path / f"{tamper}.json.gz"
    write_episode_evidence(source, episode)
    payload = bytearray(source.read_bytes())
    if tamper == "flip":
        payload[len(payload) // 2] ^= 1
    else:
        del payload[-8:]
    target.write_bytes(payload)

    with pytest.raises(EpisodeEvidenceError):
        read_episode_evidence(target)


def test_semantic_replay_rejects_changed_operation(tmp_path: Path) -> None:
    episode = _run_exact(tmp_path, NONTRIVIAL_FIXTURE, 4)
    tampered = json.loads(json.dumps(episode))
    tampered["evidence"]["events"][0]["operation"]["source_state_id"] = "unknown-state"

    with pytest.raises(EpisodeEvidenceError):
        replay_episode(tampered["evidence"])


def test_interrupted_commit_leaves_no_final_or_staging_artifact(tmp_path: Path, monkeypatch) -> None:
    episode = _run_exact(tmp_path, NONTRIVIAL_FIXTURE, 4)
    target = tmp_path / "interrupted.json.gz"

    def interrupt(_self: Path, _target: Path) -> Path:
        raise OSError("simulated interruption before rename")

    monkeypatch.setattr(Path, "replace", interrupt)
    with pytest.raises(OSError, match="simulated interruption"):
        write_episode_evidence(target, episode)

    assert not target.exists()
    assert not list(tmp_path.glob(".interrupted.json.gz.*"))


def test_materialized_task_and_trace_replay(tmp_path: Path) -> None:
    episode = _run_exact(tmp_path, NONTRIVIAL_FIXTURE, 4)

    task, trace = materialize_episode_artifacts(episode["evidence"])

    assert json.loads(task)["instance_id"]
    assert json.loads(trace)["record_count"] == len(episode["evidence"]["events"])
