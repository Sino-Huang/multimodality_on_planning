"""Issue-52 exact-classical and seeded random-valid BFS reference runs."""

from __future__ import annotations

import json
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Mapping, cast

from src.data_collect.generate import GenerationRequest, GenerationRunReceipt, run_authorized_generation
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, StopOutcome

from .bfs_generation import _load_candidates, _normalize_authority_input, _require_frozen_manifest, _source_path
from .bfs_phase import BFSPhaseGate
from .episode_evidence import (
    episode_result_summary,
    verify_episode_evidence,
    write_episode_evidence,
)
from .search_episode import SearchEpisodeVariant, run_search_episode_batch

_REFERENCE_SCHEMA = "bfs_base_and_references_v3"
_TASK_SCHEMA = "search_episode_task_v1"


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
    """Run or resume complete exact and five-seed random episodes on frozen dev."""

    def execute() -> dict[str, object]:
        phase_gate.require_run(stage="base_and_references", contract_id=request.binding.contract_id)
        output_root = Path(request.binding.output_root).resolve()
        manifest_path = output_root / "manifests" / "bfs-references.json"
        if manifest_path.exists():
            raise FileExistsError(f"BFS reference shard is already complete: {manifest_path}")
        all_tasks = frozen_bfs_development_tasks(accepted_manifest_path, phase_gate)
        if shard_count <= 0 or shard_index < 0 or shard_index >= shard_count:
            raise ValueError("shard index must be inside a positive shard count")
        if shard_count > len(all_tasks):
            raise ValueError("shard count must not exceed the frozen development task count")
        if isinstance(workers, bool) or not isinstance(workers, int) or workers <= 0:
            raise ValueError("BFS reference workers must be a positive integer")
        tasks = [row for index, row in enumerate(all_tasks) if index % shard_count == shard_index]
        output_root.mkdir(parents=True, exist_ok=True)

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
                        "output_root": output_root,
                        "seeds": tuple(phase_gate.freeze["seeds"]),
                        "frozen_binding": phase_gate.receipt(
                            stage="base_and_references",
                            difficulty=row["bucket"],
                        ),
                    }
                )
            if workers == 1:
                task_rows = [_run_reference_task(job) for job in jobs]
            else:
                with ProcessPoolExecutor(max_workers=workers) as executor:
                    task_rows = list(executor.map(_run_reference_task, jobs))
        rows = [row for task_row in task_rows for row in task_row]

        expected_paths = {output_root / row["evidence"]["path"] for row in rows}
        episode_root = output_root / "episodes"
        actual_paths = set(episode_root.rglob("*.jsonl.gz")) if episode_root.exists() else set()
        if actual_paths != expected_paths:
            raise ValueError("reference episode artifacts do not form the exact frozen product")

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
        _atomic_write_bytes(manifest_path, _canonical_bytes(manifest))
        return {
            "exact_reference_invariant_valid_success": exact_success_rate,
            "gate_outcome": gate_outcome.value,
            "manifest_path": str(manifest_path),
            "manifest_size_bytes": manifest_path.stat().st_size,
            "reference_count": len(rows),
            "task_count": len(tasks),
        }

    return run_authorized_generation(request, execute)


def _run_reference_task(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    row = arguments["row"]
    fixture_path = arguments["fixture_path"]
    max_expansions = arguments["max_expansions"]
    request = arguments["request"]
    output_root = arguments["output_root"]
    frozen_binding = arguments["frozen_binding"]
    variants = (
        ("exact_classical", "exact", None),
        *(("random_valid", "random", seed) for seed in arguments["seeds"]),
    )
    records: dict[tuple[str, int | None], dict[str, Any]] = {}
    missing: list[tuple[str, str, int | None, Path, Path]] = []

    for arm, policy, seed in variants:
        suffix = "exact" if seed is None else f"seed-{seed}"
        relative_path = Path("episodes") / arm / str(row["instance_id"]) / f"{suffix}.jsonl.gz"
        evidence_path = output_root / relative_path
        if not evidence_path.exists():
            missing.append((arm, policy, seed, relative_path, evidence_path))
            continue
        verified = verify_episode_evidence(evidence_path)
        _verify_resumed_episode(
            verified,
            arm=arm,
            policy=policy,
            seed=seed,
            row=row,
            fixture_path=fixture_path,
            max_expansions=max_expansions,
            request=request,
            frozen_binding=frozen_binding,
        )
        records[(arm, seed)] = _reference_record(
            arm=arm,
            seed=seed,
            row=row,
            relative_path=relative_path,
            evidence_manifest=verified["manifest"],
            result=verified["result"],
        )

    if missing:
        episodes = run_search_episode_batch(
            task_path=fixture_path,
            algorithm="bfs",
            modality="text-state",
            variants=tuple(SearchEpisodeVariant(policy, seed) for _arm, policy, seed, _relative, _path in missing),
            max_expansions=max_expansions,
            gate_receipt=cast(GateReceipt, request.gate_receipt),
            authorization_receipt=cast(AuthorizationReceipt | None, request.authorization_receipt),
            frozen_binding=frozen_binding,
        )
        for (arm, _policy, seed, relative_path, evidence_path), episode in zip(missing, episodes, strict=True):
            records[(arm, seed)] = _reference_record(
                arm=arm,
                seed=seed,
                row=row,
                relative_path=relative_path,
                evidence_manifest=write_episode_evidence(evidence_path, episode),
                result=episode["result"],
            )

    return [records[(arm, seed)] for arm, _policy, seed in variants]


def _write_task_fixture(row: dict[str, Any], fixture_root: Path) -> Path:
    domain_path = _source_path(row["domain_path"])
    problem_path = _source_path(row["problem_path"])
    domain_bytes = domain_path.read_bytes()
    problem_bytes = problem_path.read_bytes()
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


def _reference_record(
    *,
    arm: str,
    seed: int | None,
    row: Mapping[str, Any],
    relative_path: Path,
    evidence_manifest: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "arm": arm,
        "difficulty": row["bucket"],
        "domain_id": row["domain_id"],
        "evidence": {"path": relative_path.as_posix(), **dict(evidence_manifest)},
        "instance_id": row["instance_id"],
        "result": episode_result_summary(result),
        "seed": seed,
    }


def _verify_resumed_episode(
    verified: Mapping[str, Any],
    *,
    arm: str,
    policy: str,
    seed: int | None,
    row: Mapping[str, Any],
    fixture_path: Path,
    max_expansions: int,
    request: GenerationRequest,
    frozen_binding: Mapping[str, Any],
) -> None:
    header = verified["header"]
    fixture = json.loads(fixture_path.read_bytes())
    expected_task = {**fixture, "schema_version": _TASK_SCHEMA}
    expected_request = {
        "algorithm": "bfs",
        "max_expansions": max_expansions,
        "modality": "text-state",
        "policy": policy,
        "schema_version": "search_episode_request_v1",
    }
    if seed is not None:
        expected_request["random_seed"] = seed
    binding = header["gate_receipt"]["binding"]
    current_binding = request.binding.to_dict()
    if (
        header["task"] != expected_task
        or header["request"] != expected_request
        or header["frozen_binding"] != frozen_binding
        or binding["attempt_id"] == current_binding["attempt_id"]
        or binding["contract_id"] != current_binding["contract_id"]
        or binding["output_root"] != current_binding["output_root"]
        or not isinstance(verified["result"], Mapping)
        or arm not in {"exact_classical", "random_valid"}
        or row["instance_id"] != expected_task["instance_id"]
    ):
        raise ValueError(f"existing reference episode does not match frozen inputs: {row['instance_id']} {arm} {seed}")


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_bytes(payload)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


__all__ = ["frozen_bfs_development_tasks", "run_frozen_bfs_references"]
