"""Issue-52 exact-classical and seeded random-valid BFS reference runs."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, cast

from src.data_collect.generate import GenerationRequest, GenerationRunReceipt, run_authorized_generation
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, StopOutcome

from .bfs_generation import _load_candidates, _normalize_authority_input, _require_frozen_manifest
from .bfs_phase import BFSPhaseGate
from .search_episode import replay_search_episode, run_search_episode

_REFERENCE_SCHEMA = "bfs_base_and_references_v1"


def frozen_bfs_development_tasks(
    accepted_manifest_path: str | Path,
    phase_gate: BFSPhaseGate,
) -> list[dict[str, Any]]:
    """Return every frozen dev task in deterministic stratum/instance order."""

    manifest_path = Path(accepted_manifest_path).resolve()
    _require_frozen_manifest(manifest_path, phase_gate)
    candidates = _load_candidates(manifest_path, phase_gate)
    tasks = [row for stratum in sorted(candidates) for row in candidates[stratum] if row["split"] == "dev"]
    expected = sum(phase_gate.freeze["data"]["development_counts_by_split_and_difficulty"]["dev"].values())
    if len(tasks) != expected:
        raise ValueError(f"frozen BFS dev task count differs: expected {expected}, got {len(tasks)}")
    return tasks


def run_frozen_bfs_references(
    *,
    accepted_manifest_path: str | Path,
    request: GenerationRequest,
    phase_gate: BFSPhaseGate,
    shard_index: int = 0,
    shard_count: int = 1,
    workers: int = 1,
) -> GenerationRunReceipt:
    """Run complete exact and five-seed random reference episodes on frozen dev."""

    def execute() -> dict[str, object]:
        phase_gate.require_run(stage="base_and_references", contract_id=request.binding.contract_id)
        output_root = Path(request.binding.output_root).resolve()
        if output_root.exists():
            raise FileExistsError(f"BFS reference output root already exists: {output_root}")
        all_tasks = frozen_bfs_development_tasks(accepted_manifest_path, phase_gate)
        if shard_count <= 0 or shard_index < 0 or shard_index >= shard_count:
            raise ValueError("shard index must be inside a positive shard count")
        if shard_count > len(all_tasks):
            raise ValueError("shard count must not exceed the frozen development task count")
        if isinstance(workers, bool) or not isinstance(workers, int) or workers <= 0:
            raise ValueError("BFS reference workers must be a positive integer")
        tasks = [row for index, row in enumerate(all_tasks) if index % shard_count == shard_index]
        output_root.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
        rows: list[dict[str, Any]] = []
        try:
            with tempfile.TemporaryDirectory(prefix="bfs-reference-tasks-") as task_directory:
                fixture_root = Path(task_directory)
                jobs: list[dict[str, Any]] = []
                for row in tasks:
                    fixture_path = _write_task_fixture(row, fixture_root)
                    max_expansions = phase_gate.require_run(
                        stage="base_and_references",
                        contract_id=request.binding.contract_id,
                        difficulty=row["bucket"],
                    )
                    assert max_expansions is not None
                    jobs.append(
                        {
                            "row": row,
                            "fixture_path": fixture_path,
                            "max_expansions": max_expansions,
                            "request": request,
                            "staging": staging,
                            "seeds": tuple(phase_gate.freeze["seeds"]),
                        }
                    )
                if workers == 1:
                    task_rows = [_run_reference_task(job) for job in jobs]
                else:
                    with ProcessPoolExecutor(max_workers=workers) as executor:
                        task_rows = list(executor.map(_run_reference_task, jobs))
                rows = [row for task_row in task_rows for row in task_row]

            exact_rows = [row for row in rows if row["arm"] == "exact_classical"]
            exact_success_rate = sum(bool(row["result"]["goal_reached"]) for row in exact_rows) / len(exact_rows)
            threshold = phase_gate.freeze["thresholds"]["exact_reference_invariant_valid_success"]
            gate_outcome = StopOutcome.PASS if exact_success_rate >= threshold else StopOutcome.VALID_STOP
            manifest = {
                "counts": {
                    "exact_classical": len(exact_rows),
                    "random_valid": len(rows) - len(exact_rows),
                    "tasks": len(tasks),
                },
                "exact_reference_invariant_valid_success": exact_success_rate,
                "gate_outcome": gate_outcome.value,
                "phase_receipt": phase_gate.receipt(stage="base_and_references"),
                "references": rows,
                "schema_version": _REFERENCE_SCHEMA,
                "shard_count": shard_count,
                "shard_index": shard_index,
                "threshold": threshold,
            }
            manifest_path = staging / "manifests" / "bfs-references.json"
            _write_bytes(manifest_path, _canonical_bytes(manifest))
            manifest_sha256 = _sha256(manifest_path.read_bytes())
            staging.replace(output_root)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return {
            "exact_reference_invariant_valid_success": exact_success_rate,
            "gate_outcome": gate_outcome.value,
            "manifest_path": str(output_root / "manifests" / "bfs-references.json"),
            "manifest_sha256": manifest_sha256,
            "reference_count": len(rows),
            "task_count": len(tasks),
        }

    return run_authorized_generation(request, execute)


def _run_reference_task(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    common = {
        "row": arguments["row"],
        "fixture_path": arguments["fixture_path"],
        "max_expansions": arguments["max_expansions"],
        "request": arguments["request"],
        "staging": arguments["staging"],
    }
    rows = [
        _run_reference_episode(
            arm="exact_classical",
            policy="exact",
            seed=None,
            **common,
        )
    ]
    rows.extend(
        _run_reference_episode(
            arm="random_valid",
            policy="random",
            seed=seed,
            **common,
        )
        for seed in arguments["seeds"]
    )
    return rows


def _write_task_fixture(row: dict[str, Any], fixture_root: Path) -> Path:
    domain_path = Path(row["domain_path"]).resolve()
    problem_path = Path(row["problem_path"]).resolve()
    domain_bytes = domain_path.read_bytes()
    problem_bytes = problem_path.read_bytes()
    if _sha256(domain_bytes) != row["domain_hash"] or _sha256(problem_bytes) != row["problem_hash"]:
        raise ValueError(f"frozen BFS task PDDL has drifted: {row['instance_id']}")
    domain, problem, _transformations = _normalize_authority_input(
        domain_bytes.decode("utf-8"),
        problem_bytes.decode("utf-8"),
    )
    fixture_path = fixture_root / f"{row['instance_id']}.json"
    _write_bytes(
        fixture_path,
        _canonical_bytes(
            {
                "domain_pddl": domain,
                "instance_id": row["instance_id"],
                "problem_pddl": problem,
            }
        ),
    )
    return fixture_path


def _run_reference_episode(
    *,
    arm: str,
    policy: str,
    seed: int | None,
    row: dict[str, Any],
    fixture_path: Path,
    max_expansions: int,
    request: GenerationRequest,
    staging: Path,
) -> dict[str, Any]:
    episode = run_search_episode(
        task_path=fixture_path,
        algorithm="bfs",
        modality="text-state",
        policy=policy,
        max_expansions=max_expansions,
        gate_receipt=cast(GateReceipt, request.gate_receipt),
        authorization_receipt=cast(AuthorizationReceipt | None, request.authorization_receipt),
        signing_key=request.signing_key,
        random_seed=seed,
    )
    if replay_search_episode(episode["evidence"], signing_key=request.signing_key) != episode:
        raise ValueError(f"BFS reference replay differs: {row['instance_id']} {arm} {seed}")
    suffix = "exact" if seed is None else f"seed-{seed}"
    relative_path = Path("episodes") / arm / str(row["instance_id"]) / f"{suffix}.json"
    evidence_path = staging / relative_path
    payload = _canonical_bytes(episode)
    _write_bytes(evidence_path, payload)
    return {
        "arm": arm,
        "difficulty": row["bucket"],
        "domain_id": row["domain_id"],
        "evidence": {"path": relative_path.as_posix(), "sha256": _sha256(payload), "size_bytes": len(payload)},
        "instance_id": row["instance_id"],
        "result": episode["result"],
        "seed": seed,
    }


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


__all__ = ["frozen_bfs_development_tasks", "run_frozen_bfs_references"]
