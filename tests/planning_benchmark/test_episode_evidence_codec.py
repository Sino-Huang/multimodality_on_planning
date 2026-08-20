from __future__ import annotations

import base64
import gzip
import hashlib
import json
import subprocess
import types
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_references import _write_task_fixture, frozen_bfs_development_tasks
from examples.planning_benchmark_slice.episode_evidence import (
    EVIDENCE_SCHEMA_VERSION,
    EpisodeEvidenceError,
    materialize_episode_artifacts,
    memory_sha256,
    migrate_v1_episode,
    read_episode_evidence,
    replay_episode,
    replay_episode_evidence,
    verify_episode_evidence,
    write_episode_evidence,
)
from examples.planning_benchmark_slice.search_episode import run_search_episode
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome
from src.data_collect.replay import parse_canonical_bundle

REPO_ROOT = Path(__file__).resolve().parents[2]
NONTRIVIAL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_nontrivial.json"
EMPTY_GOAL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_empty_goal.json"
SIGNING_KEY = b"issue-110-episode-evidence-test-key"


def _receipts(tmp_path: Path) -> tuple[GateReceipt, AuthorizationReceipt]:
    binding = ReceiptBinding(
        contract_id="issue-49-bfs-development-v1",
        attempt_id="issue-110-codec-test",
        output_root=(tmp_path / "episode-evidence").resolve(),
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS).signed(SIGNING_KEY)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_digest=gate.digest).signed(SIGNING_KEY)
    return gate, authorization


def test_v2_codec_is_deterministic_compact_and_replayable(tmp_path: Path) -> None:
    gate, authorization = _receipts(tmp_path)
    episode = run_search_episode(
        task_path=NONTRIVIAL_FIXTURE,
        algorithm="bfs",
        modality="text-state",
        policy="exact",
        max_expansions=64,
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=SIGNING_KEY,
    )

    first_path = tmp_path / "first.jsonl.gz"
    second_path = tmp_path / "second.jsonl.gz"
    first_manifest = write_episode_evidence(first_path, episode)
    second_manifest = write_episode_evidence(second_path, episode)

    first_bytes = first_path.read_bytes()
    streamed = verify_episode_evidence(first_path, signing_key=SIGNING_KEY)
    assert streamed["result"] == episode["result"]
    assert streamed["manifest"] == first_manifest
    assert "events" not in streamed
    assert first_bytes == second_path.read_bytes()
    assert first_manifest == second_manifest
    assert int.from_bytes(first_bytes[4:8], "little") == 0
    assert first_manifest["schema_version"] == EVIDENCE_SCHEMA_VERSION
    assert first_manifest["stored_size_bytes"] == len(first_bytes)
    assert read_episode_evidence(first_path) == episode
    assert replay_episode_evidence(first_path, signing_key=SIGNING_KEY) == episode

    logical_bytes = gzip.decompress(first_bytes)
    assert b'"expansions"' not in logical_bytes
    assert b'"frontier_before"' not in logical_bytes
    assert b'"frontier_after"' not in logical_bytes


@pytest.mark.parametrize(
    ("fixture", "budget", "expected_expansions", "expected_goal"),
    (
        (EMPTY_GOAL_FIXTURE, 4, 0, True),
        (NONTRIVIAL_FIXTURE, 1, 1, False),
    ),
)
def test_v2_round_trips_empty_and_budget_exhausted_traces(
    tmp_path: Path,
    fixture: Path,
    budget: int,
    expected_expansions: int,
    expected_goal: bool,
) -> None:
    gate, authorization = _receipts(tmp_path)
    episode = run_search_episode(
        fixture,
        "bfs",
        "text-state",
        "exact",
        budget,
        gate,
        authorization,
        SIGNING_KEY,
    )
    path = tmp_path / f"trace-{expected_expansions}.jsonl.gz"

    write_episode_evidence(path, episode)

    assert replay_episode_evidence(path, signing_key=SIGNING_KEY) == episode
    assert episode["result"]["expansion_count"] == expected_expansions
    assert episode["result"]["goal_reached"] is expected_goal


@pytest.mark.parametrize(
    ("tamper", "logical"),
    (
        ("flip", False),
        ("truncate", False),
        ("event", True),
        ("state", True),
        ("digest", True),
    ),
)
def test_v2_rejects_compressed_and_logical_tampering(tmp_path: Path, tamper: str, logical: bool) -> None:
    gate, authorization = _receipts(tmp_path)
    episode = run_search_episode(
        NONTRIVIAL_FIXTURE,
        "bfs",
        "text-state",
        "exact",
        4,
        gate,
        authorization,
        SIGNING_KEY,
    )
    source = tmp_path / "source.jsonl.gz"
    target = tmp_path / f"{tamper}.jsonl.gz"
    write_episode_evidence(source, episode)
    payload = bytearray(source.read_bytes())

    if tamper == "flip":
        payload[len(payload) // 2] ^= 1
    elif tamper == "truncate":
        del payload[-8:]
    else:
        records = [json.loads(line) for line in gzip.decompress(payload).splitlines()]
        if tamper == "event":
            next(record for record in records if record["record_type"] == "event")["event"]["rationale"] += "-tampered"
        elif tamper == "state":
            next(record for record in records if record["record_type"] == "state")["state"]["atoms"].append("tampered")
        else:
            next(record for record in records if record["record_type"] == "digest")["logical_sha256"] = "0" * 64
        logical_payload = b"".join(
            json.dumps(record, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
            + b"\n"
            for record in records
        )
        payload = bytearray(gzip.compress(logical_payload, compresslevel=9, mtime=0))
    target.write_bytes(payload)

    with pytest.raises(EpisodeEvidenceError):
        read_episode_evidence(target)
    with pytest.raises(EpisodeEvidenceError):
        verify_episode_evidence(target, signing_key=SIGNING_KEY)


def test_v2_interrupted_commit_leaves_no_final_or_staging_artifact(tmp_path: Path, monkeypatch) -> None:
    gate, authorization = _receipts(tmp_path)
    episode = run_search_episode(
        NONTRIVIAL_FIXTURE,
        "bfs",
        "text-state",
        "exact",
        4,
        gate,
        authorization,
        SIGNING_KEY,
    )
    target = tmp_path / "interrupted.jsonl.gz"

    def interrupt(_self: Path, _target: Path) -> Path:
        raise OSError("simulated interruption before rename")

    monkeypatch.setattr(Path, "replace", interrupt)
    with pytest.raises(OSError, match="simulated interruption"):
        write_episode_evidence(target, episode)

    assert not target.exists()
    assert not list(tmp_path.glob(".interrupted.jsonl.gz.*"))


def test_verified_v1_migration_preserves_semantics_and_source_bytes(tmp_path: Path) -> None:
    source_code = subprocess.check_output(
        ["git", "show", "f941faa:examples/planning_benchmark_slice/search_episode.py"],
        cwd=REPO_ROOT,
        text=True,
    )
    legacy = types.ModuleType("examples.planning_benchmark_slice._issue110_legacy_search_episode")
    legacy.__package__ = "examples.planning_benchmark_slice"
    exec(compile(source_code, "f941faa/search_episode.py", "exec"), legacy.__dict__)

    gate, authorization = _receipts(tmp_path)
    v1_episode = legacy.run_search_episode(
        NONTRIVIAL_FIXTURE,
        "bfs",
        "text-state",
        "exact",
        4,
        gate,
        authorization,
        SIGNING_KEY,
    )
    source = tmp_path / "legacy-v1.json"
    target = tmp_path / "migrated-v2.jsonl.gz"
    source.write_bytes(
        (
            json.dumps(v1_episode, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode()
    )
    original = source.read_bytes()

    manifest = migrate_v1_episode(source, target, signing_key=SIGNING_KEY)
    migrated = replay_episode_evidence(target, signing_key=SIGNING_KEY)

    assert source.read_bytes() == original
    assert manifest["source_sha256"] == hashlib.sha256(original).hexdigest()
    assert migrated["result"] == v1_episode["result"]
    v1_bundle = base64.b64decode(v1_episode["evidence"]["bundle"], validate=True)
    v1_artifacts = parse_canonical_bundle(v1_bundle)
    v1_records = json.loads(v1_artifacts["search-trace.json"])["records"]
    task_bytes, trace_bytes = materialize_episode_artifacts(migrated["evidence"], signing_key=SIGNING_KEY)
    assert task_bytes == v1_artifacts["task.json"]
    assert trace_bytes == v1_artifacts["search-trace.json"]
    assert [event["operation"] for event in migrated["evidence"]["events"]] == [
        record["operation"] for record in v1_records
    ]
    replayed_memory = replay_episode(migrated["evidence"], signing_key=SIGNING_KEY)
    assert memory_sha256(replayed_memory) == v1_records[-1]["result"]["memory_sha256"]


def _frozen_medium_fixture(tmp_path: Path) -> Path:
    phase_gate = load_bfs_phase_gate(
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json",
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json",
    )
    task = next(
        row
        for row in frozen_bfs_development_tasks(
            REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl",
            phase_gate,
        )
        if row["instance_id"] == "blocksworld-dev-medium-0014"
    )
    assert task["split"] == "dev"
    return _write_task_fixture(task, tmp_path / "fixture")


def _synthetic_growing_frontier_fixture(tmp_path: Path) -> Path:
    node_count = 256
    objects = " ".join([*(f"n{index}" for index in range(node_count)), "unreachable"])
    edges = "\n".join(
        f"    (edge n{parent} n{child})"
        for parent in range(node_count // 2)
        for child in (parent * 2 + 1, parent * 2 + 2)
        if child < node_count
    )
    domain = """(define (domain synthetic-growing-frontier)
  (:requirements :strips)
  (:predicates (at ?node) (edge ?from ?to))
  (:action move
    :parameters (?from ?to)
    :precondition (and (at ?from) (edge ?from ?to))
    :effect (and (not (at ?from)) (at ?to)))
)
"""
    problem = f"""(define (problem synthetic-growing-frontier-256)
  (:domain synthetic-growing-frontier)
  (:objects {objects})
  (:init
    (at n0)
{edges})
  (:goal (and (at unreachable)))
)
"""
    fixture = tmp_path / "synthetic-growing-frontier.json"
    fixture.write_text(
        json.dumps(
            {
                "domain_pddl": domain,
                "instance_id": "synthetic-growing-frontier-256",
                "problem_pddl": problem,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return fixture


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
        SIGNING_KEY,
    )


def test_frozen_medium_v2_is_at_most_one_quarter_of_v1(tmp_path: Path) -> None:
    episode = _run_exact(tmp_path, _frozen_medium_fixture(tmp_path), 256)
    path = tmp_path / "medium-256.jsonl.gz"

    manifest = write_episode_evidence(path, episode)

    assert episode["result"]["expansion_count"] == 256
    assert manifest["stored_size_bytes"] <= 17_557_492 // 4


def test_synthetic_growing_frontier_v2_size_scales_linearly(tmp_path: Path) -> None:
    fixture = _synthetic_growing_frontier_fixture(tmp_path)
    sizes = []
    for budget in (64, 128):
        episode = _run_exact(tmp_path, fixture, budget)
        path = tmp_path / f"medium-{budget}.jsonl.gz"
        sizes.append(write_episode_evidence(path, episode)["stored_size_bytes"])
        assert episode["result"]["expansion_count"] == budget

    assert sizes[1] <= sizes[0] * 2.5
