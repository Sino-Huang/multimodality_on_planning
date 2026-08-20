from __future__ import annotations

import json
from pathlib import Path

import examples.planning_benchmark_slice.bfs_references as references
from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_references import frozen_bfs_development_tasks, run_frozen_bfs_references
from scripts.adjudicate_bfs_base_and_references import _verify_evidence
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_SIGNING_KEY = b"issue-110-reference-resume-test-key"


def test_frozen_reference_task_set_is_the_complete_declared_dev_split() -> None:
    phase_gate = load_bfs_phase_gate(
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json",
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json",
    )

    tasks = frozen_bfs_development_tasks(
        REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl",
        phase_gate,
    )

    assert len(tasks) == 475
    assert all(task["split"] == "dev" for task in tasks)
    assert {(task["domain_id"], task["bucket"]) for task in tasks} == {
        (domain, difficulty)
        for domain in phase_gate.freeze["data"]["domains"]
        for difficulty in phase_gate.freeze["data"]["strata"]
    }


def test_modulo_shards_form_an_exact_partition_of_frozen_reference_tasks() -> None:
    phase_gate = load_bfs_phase_gate(
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json",
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json",
    )
    tasks = frozen_bfs_development_tasks(
        REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl",
        phase_gate,
    )

    shards = [[task for index, task in enumerate(tasks) if index % 8 == shard] for shard in range(8)]

    assert sum(len(shard) for shard in shards) == len(tasks)
    assert {task["instance_id"] for shard in shards for task in shard} == {task["instance_id"] for task in tasks}


def _request(output_root: Path, attempt_id: str) -> GenerationRequest:
    binding = ReceiptBinding("issue-49-bfs-development-v1", attempt_id, output_root.resolve())
    gate = GateReceipt(binding, StopOutcome.PASS).signed(REFERENCE_SIGNING_KEY)
    return GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(binding, gate.digest).signed(REFERENCE_SIGNING_KEY),
        signing_key=REFERENCE_SIGNING_KEY,
        receipt_root=(output_root.parent / "receipts").resolve(),
    )


def test_reference_resume_verifies_and_skips_only_complete_v2_episodes(tmp_path: Path, monkeypatch) -> None:
    phase_gate = load_bfs_phase_gate(
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json",
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json",
    )
    task = frozen_bfs_development_tasks(
        REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl",
        phase_gate,
    )[0]
    monkeypatch.setattr(references, "frozen_bfs_development_tasks", lambda *_args: [task])
    output_root = tmp_path / "references"

    initial = run_frozen_bfs_references(
        accepted_manifest_path=REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl",
        request=_request(output_root, "issue-110-initial"),
        phase_gate=phase_gate,
    )
    assert initial.outcome is StopOutcome.PASS
    manifest_path = output_root / "manifests" / "bfs-references.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing_path = output_root / manifest["references"][-1]["evidence"]["path"]
    manifest_path.unlink()
    missing_path.unlink()

    calls = 0
    original = references.run_search_episode

    def counted_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(references, "run_search_episode", counted_run)
    resumed = run_frozen_bfs_references(
        accepted_manifest_path=REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl",
        request=_request(output_root, "issue-110-resumed"),
        phase_gate=phase_gate,
    )

    assert resumed.outcome is StopOutcome.PASS
    assert calls == 1
    completed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert completed["schema_version"] == "bfs_base_and_references_v2"
    assert len(completed["references"]) == 6
    assert all(
        set(row["evidence"])
        == {
            "codec_version",
            "logical_sha256",
            "path",
            "schema_version",
            "stored_size_bytes",
        }
        for row in completed["references"]
    )
    assert all(
        set(row["result"])
        == {
            "completion",
            "expansion_count",
            "goal_reached",
            "outcome",
            "scientific_completion",
        }
        for row in completed["references"]
    )
    for row in completed["references"]:
        _verify_evidence(output_root, row, signing_key=REFERENCE_SIGNING_KEY)

    manifest_path.unlink()
    corrupt_path = output_root / completed["references"][0]["evidence"]["path"]
    corrupt = bytearray(corrupt_path.read_bytes())
    corrupt[len(corrupt) // 2] ^= 1
    corrupt_path.write_bytes(corrupt)
    refused = run_frozen_bfs_references(
        accepted_manifest_path=REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl",
        request=_request(output_root, "issue-110-corrupt-resume"),
        phase_gate=phase_gate,
    )

    assert refused.outcome is StopOutcome.INVALID
    assert not manifest_path.exists()
