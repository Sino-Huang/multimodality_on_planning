"""Run issue #110's frozen 18-episode legacy/current integration gate."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import tempfile
import types
from pathlib import Path
from typing import Any

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_references import (
    _write_task_fixture,
    frozen_bfs_development_tasks,
)
from examples.planning_benchmark_slice.episode_evidence import (
    episode_result_summary,
    memory_sha256,
    replay_episode,
    replay_episode_evidence,
    write_episode_evidence,
)
from examples.planning_benchmark_slice.search_episode import run_search_episode
from scripts.adjudicate_bfs_base_and_references import _verify_evidence
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome
from src.data_collect.replay import parse_canonical_bundle

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json"
_MANIFEST = _REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl"
_LEGACY_COMMIT = "f941faa"
_SIGNING_KEY = b"issue-110-v2-integration-gate"
_INSTANCE_IDS = tuple(f"towers_of_hanoi-dev-{difficulty}-0000" for difficulty in ("easy", "medium", "hard"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    output_root = args.output_root.expanduser().resolve()
    if output_root.exists():
        raise FileExistsError(f"integration output already exists: {output_root}")
    output_root.mkdir(parents=True)

    phase_gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    tasks = {
        str(row["instance_id"]): row
        for row in frozen_bfs_development_tasks(_MANIFEST, phase_gate)
        if row["instance_id"] in _INSTANCE_IDS
    }
    if set(tasks) != set(_INSTANCE_IDS) or any(row["split"] != "dev" for row in tasks.values()):
        raise ValueError("integration tasks do not match the frozen development subset")
    binding = ReceiptBinding(phase_gate.phase_id, args.attempt_id, output_root)
    gate = GateReceipt(binding, StopOutcome.PASS).signed(_SIGNING_KEY)
    authorization = AuthorizationReceipt(binding, gate.digest).signed(_SIGNING_KEY)
    legacy = _legacy_module()

    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="issue110-integration-tasks-") as directory:
        fixture_root = Path(directory)
        for instance_id in _INSTANCE_IDS:
            row = tasks[instance_id]
            fixture = _write_task_fixture(row, fixture_root)
            budget = phase_gate.require_run(
                stage="base_and_references",
                contract_id=phase_gate.phase_id,
                difficulty=row["bucket"],
            )
            assert budget is not None
            arms = (
                ("exact_classical", "exact", None),
                *(("random_valid", "random", seed) for seed in phase_gate.freeze["seeds"]),
            )
            for arm, policy, seed in arms:
                request = {
                    "task_path": fixture,
                    "algorithm": "bfs",
                    "modality": "text-state",
                    "policy": policy,
                    "max_expansions": budget,
                    "gate_receipt": gate,
                    "authorization_receipt": authorization,
                    "signing_key": _SIGNING_KEY,
                    "random_seed": seed,
                }
                legacy_episode = legacy.run_search_episode(**request)
                frozen_binding = phase_gate.receipt(stage="base_and_references", difficulty=row["bucket"])
                first = run_search_episode(**request, frozen_binding=frozen_binding)
                second = run_search_episode(**request, frozen_binding=frozen_binding)
                if first != second or first["result"] != legacy_episode["result"]:
                    raise ValueError(f"legacy/current scientific result differs: {instance_id} {arm} {seed}")

                suffix = "exact" if seed is None else f"seed-{seed}"
                relative = Path(row["bucket"]) / instance_id / f"{suffix}.jsonl.gz"
                repeat_relative = Path("repeat") / relative
                first_path = output_root / relative
                second_path = output_root / repeat_relative
                first_manifest = write_episode_evidence(first_path, first)
                second_manifest = write_episode_evidence(second_path, second)
                if first_path.read_bytes() != second_path.read_bytes() or first_manifest != second_manifest:
                    raise ValueError(f"current generation is not byte-identical: {instance_id} {arm} {seed}")
                if replay_episode_evidence(first_path, signing_key=_SIGNING_KEY) != first:
                    raise ValueError(f"current persisted replay differs: {instance_id} {arm} {seed}")
                _verify_evidence(
                    output_root,
                    {
                        "evidence": {"path": relative.as_posix(), **first_manifest},
                        "result": episode_result_summary(first["result"]),
                    },
                    signing_key=_SIGNING_KEY,
                )

                legacy_payload = _canonical_bytes(legacy_episode)
                legacy_bundle = base64.b64decode(legacy_episode["evidence"]["bundle"], validate=True)
                legacy_records = json.loads(parse_canonical_bundle(legacy_bundle)["search-trace.json"])["records"]
                if [event["operation"] for event in first["evidence"]["events"]] != [
                    record["operation"] for record in legacy_records
                ]:
                    raise ValueError(f"legacy/current operation order differs: {instance_id} {arm} {seed}")
                final_memory = replay_episode(first["evidence"], signing_key=_SIGNING_KEY)
                if memory_sha256(final_memory) != legacy_records[-1]["result"]["memory_sha256"]:
                    raise ValueError(f"legacy/current final memory differs: {instance_id} {arm} {seed}")
                records.append(
                    {
                        "adjudication_verified": True,
                        "arm": arm,
                        "difficulty": row["bucket"],
                        "instance_id": instance_id,
                        "logical_sha256": first_manifest["logical_sha256"],
                        "result": first["result"],
                        "seed": seed,
                        "v1_size_bytes": len(legacy_payload),
                        "current_path": relative.as_posix(),
                        "current_size_bytes": first_manifest["stored_size_bytes"],
                    }
                )
                print(
                    _canonical_text({"completed": len(records), "instance_id": instance_id, "arm": arm, "seed": seed}),
                    flush=True,
                )

    v1_size = sum(record["v1_size_bytes"] for record in records)
    current_size = sum(record["current_size_bytes"] for record in records)
    if len(records) != 18 or current_size * 4 > v1_size:
        raise ValueError("18-episode integration size gate failed")
    report = {
        "attempt_id": args.attempt_id,
        "episode_count": len(records),
        "freeze_manifest_sha256": hashlib.sha256(phase_gate.freeze_manifest_bytes).hexdigest(),
        "authorization_manifest_sha256": hashlib.sha256(phase_gate.authorization_manifest_bytes).hexdigest(),
        "legacy_commit": _LEGACY_COMMIT,
        "records": records,
        "schema_version": "issue110_episode_evidence_integration_v2",
        "v1_size_bytes": v1_size,
        "current_fraction_of_v1": current_size / v1_size,
        "current_size_bytes": current_size,
    }
    (output_root / "report.json").write_bytes(_canonical_bytes(report))
    print(_canonical_text({"episode_count": len(records), "report": str(output_root / "report.json")}))
    return 0


def _legacy_module() -> types.ModuleType:
    source = subprocess.check_output(
        ["git", "show", f"{_LEGACY_COMMIT}:examples/planning_benchmark_slice/search_episode.py"],
        cwd=_REPO_ROOT,
        text=True,
    )
    module = types.ModuleType("examples.planning_benchmark_slice._issue110_legacy_integration")
    module.__package__ = "examples.planning_benchmark_slice"
    exec(compile(source, f"{_LEGACY_COMMIT}/search_episode.py", "exec"), module.__dict__)
    return module


def _canonical_bytes(value: object) -> bytes:
    return (_canonical_text(value) + "\n").encode("utf-8")


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
