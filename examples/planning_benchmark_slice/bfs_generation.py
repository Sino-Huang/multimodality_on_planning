"""Issue-49-gated entry points for governed BFS generation."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, cast

from src.data_collect.generate import GenerationRequest, GenerationRunReceipt, run_authorized_generation
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, StopOutcome

from .bfs_phase import BFSPhaseGate
from .episode_evidence import materialize_episode_artifacts, write_episode_evidence
from .generation_orchestrator import run_bfs_generation_smoke
from .search_episode import replay_search_episode, run_search_episode

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TRACE_MANIFEST_PATH = Path("manifests/bfs-expert-traces.json")
_TRACE_MANIFEST_SCHEMA_V1 = "bfs_expert_trace_generation_v1"
_TRACE_MANIFEST_SCHEMA_V3 = "bfs_expert_trace_generation_v3"
_TRACE_MANIFEST_SCHEMA_V5 = "bfs_expert_trace_generation_v5"
_CANONICAL_TIE_BREAK = "grounded_actions_sorted_by_canonical_serialization"


def run_frozen_bfs_generation_smoke(
    *,
    task_path: str | Path,
    request: GenerationRequest,
    phase_gate: BFSPhaseGate,
    difficulty: str,
) -> GenerationRunReceipt:
    """Run the T10 smoke only with the authorized issue-49 expansion budget."""

    max_expansions = phase_gate.require_run(
        stage="trace_generation",
        contract_id=request.binding.contract_id,
        difficulty=difficulty,
    )
    assert max_expansions is not None
    return run_bfs_generation_smoke(
        task_path=task_path,
        request=request,
        max_expansions=max_expansions,
    )


def run_frozen_bfs_trace_generation(
    *,
    accepted_manifest_path: str | Path,
    request: GenerationRequest,
    phase_gate: BFSPhaseGate,
    workers: int = 1,
) -> GenerationRunReceipt:
    """Generate replay-verified FIFO BFS traces for every frozen stratum."""

    def execute() -> dict[str, object]:
        phase_gate.require_run(
            stage="trace_generation",
            contract_id=request.binding.contract_id,
        )
        if isinstance(workers, bool) or not isinstance(workers, int) or workers <= 0:
            raise ValueError("BFS trace workers must be a positive integer")
        output_root = Path(request.binding.output_root).resolve()
        if output_root.exists():
            raise FileExistsError(f"BFS trace output root already exists: {output_root}")

        manifest_path = Path(accepted_manifest_path).resolve()
        _require_frozen_manifest(manifest_path, phase_gate)
        candidates = _load_candidates(manifest_path, phase_gate)
        required = _required_strata(phase_gate)
        minimum = _minimum_per_stratum(phase_gate)
        for stratum in required:
            if len(candidates.get(stratum, ())) < minimum:
                raise ValueError(f"frozen curriculum stratum has insufficient accepted tasks: {stratum}")

        output_root.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
        jobs: list[dict[str, Any]] = []
        try:
            with tempfile.TemporaryDirectory(prefix="bfs-trace-input-") as fixture_directory:
                fixture_root = Path(fixture_directory)
                for domain_id, difficulty in required:
                    max_expansions = phase_gate.require_run(
                        stage="trace_generation",
                        contract_id=request.binding.contract_id,
                        difficulty=difficulty,
                    )
                    assert max_expansions is not None
                    for row in _select_split_candidates(
                        candidates[(domain_id, difficulty)],
                        allowed_splits=phase_gate.freeze["data"]["allowed_splits"],
                        minimum=minimum,
                    ):
                        jobs.append(
                            {
                                "row": row,
                                "difficulty": difficulty,
                                "manifest_path": manifest_path,
                                "max_expansions": max_expansions,
                                "request": request,
                                "phase_gate": phase_gate,
                                "fixture_root": fixture_root,
                                "staging_root": staging_root,
                            }
                        )

                if workers == 1:
                    trace_items = [_generate_trace_job(job) for job in jobs]
                else:
                    with ProcessPoolExecutor(max_workers=workers) as executor:
                        trace_items = list(executor.map(_generate_trace_job, jobs))

            trace_manifest = {
                "algorithm": "bfs",
                "coverage": {
                    "covered_strata": len({(item["domain_id"], item["difficulty"]) for item in trace_items}),
                    "minimum_traces_per_domain_difficulty": minimum,
                    "required_strata": len(required),
                },
                "phase_receipt": phase_gate.receipt(stage="trace_generation"),
                "schema_version": {
                    "bfs_phase_freeze_v3": _TRACE_MANIFEST_SCHEMA_V3,
                    "bfs_phase_freeze_v5": _TRACE_MANIFEST_SCHEMA_V5,
                    "bfs_phase_freeze_v6": _TRACE_MANIFEST_SCHEMA_V5,
                }.get(phase_gate.freeze["schema_version"], _TRACE_MANIFEST_SCHEMA_V1),
                "traces": trace_items,
            }
            trace_manifest_path = staging_root / _TRACE_MANIFEST_PATH
            _write_bytes(trace_manifest_path, _canonical_json_bytes(trace_manifest))
            staging_root.replace(output_root)
        except Exception:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise

        return {
            "covered_strata": len(required),
            "trace_count": len(trace_items),
            "trace_manifest_path": str((output_root / _TRACE_MANIFEST_PATH).resolve()),
            "trace_manifest_size_bytes": (output_root / _TRACE_MANIFEST_PATH).stat().st_size,
        }

    return run_authorized_generation(request, execute)


def _generate_trace_job(arguments: dict[str, Any]) -> dict[str, object]:
    return _generate_trace(**arguments)


def _generate_trace(
    *,
    row: dict[str, Any],
    difficulty: str,
    manifest_path: Path,
    max_expansions: int,
    request: GenerationRequest,
    phase_gate: BFSPhaseGate,
    fixture_root: Path,
    staging_root: Path,
) -> dict[str, object]:
    domain_path = _source_path(row["domain_path"])
    problem_path = _source_path(row["problem_path"])
    domain_bytes = domain_path.read_bytes()
    problem_bytes = problem_path.read_bytes()
    authority_domain, authority_problem, transformations = _normalize_authority_input(
        domain_bytes.decode("utf-8"),
        problem_bytes.decode("utf-8"),
    )
    fixture_path = fixture_root / f"{row['instance_id']}.json"
    _write_bytes(
        fixture_path,
        _canonical_json_bytes(
            {
                "domain_pddl": authority_domain,
                "instance_id": row["instance_id"],
                "problem_pddl": authority_problem,
            }
        ),
    )
    episode = run_search_episode(
        task_path=fixture_path,
        algorithm="bfs",
        modality="text-state",
        policy="exact",
        max_expansions=max_expansions,
        gate_receipt=cast(GateReceipt, request.gate_receipt),
        authorization_receipt=cast(AuthorizationReceipt | None, request.authorization_receipt),
        ancestor_receipt_id=request.ancestor_receipt_id,
    )
    result = episode["result"]
    if (
        not isinstance(result, dict)
        or result.get("completion") != "completed"
        or result.get("outcome") != StopOutcome.PASS.value
        or result.get("scientific_completion") is not True
    ):
        raise ValueError(f"BFS trace generation did not complete: {row['instance_id']}")
    if replay_search_episode(episode["evidence"]) != episode:
        raise ValueError(f"BFS trace replay differs: {row['instance_id']}")

    evidence = cast(dict[str, Any], episode["evidence"])
    _formal_task, search_trace = materialize_episode_artifacts(evidence)
    relative_root = Path("traces") / str(row["domain_id"]) / difficulty / str(row["instance_id"])
    evidence_path = staging_root / relative_root / "evidence.jsonl.gz"
    search_trace_path = staging_root / relative_root / "search-trace.json"
    write_episode_evidence(evidence_path, episode)
    _write_bytes(search_trace_path, search_trace)

    return {
        "algorithm": "bfs",
        "canonical_tie_break": _CANONICAL_TIE_BREAK,
        "difficulty": difficulty,
        "domain_id": row["domain_id"],
        "evidence": _artifact(evidence_path, staging_root),
        "instance_id": row["instance_id"],
        "max_expansions": max_expansions,
        "phase_receipt": phase_gate.receipt(stage="trace_generation"),
        "result": {
            "expansion_count": result["expansion_count"],
            "goal_reached": result["goal_reached"],
            "outcome": result["outcome"],
            "scientific_completion": result["scientific_completion"],
        },
        "search_trace": _artifact(search_trace_path, staging_root),
        "trace_scope": "bounded_search_trace_segment",
        "source": {
            "accepted_manifest_path": str(manifest_path),
            "authority_transformations": list(transformations),
            "domain_path": str(domain_path),
            "problem_path": str(problem_path),
            "split": row["split"],
        },
    }


def _normalize_authority_input(domain_pddl: str, problem_pddl: str) -> tuple[str, str, tuple[str, ...]]:
    transformations: list[str] = []
    authority_domain = domain_pddl
    authority_problem = problem_pddl

    if "(:domain driverlog)" in problem_pddl.lower():
        normalized_problem, count = re.subn(
            r"\s*\(=\s+\(time-to-(?:walk|drive)\s+[^()]*\)\s+[^()\s]+\)",
            "",
            authority_problem,
            flags=re.IGNORECASE,
        )
        if count:
            authority_problem = normalized_problem
            transformations.append("drop_undeclared_driverlog_metric_initializers")

    if "(define (domain storage-propositional)" in domain_pddl.lower():
        normalized_domain, count = re.subn(
            r"\?x\s*-\s*\(either\s+storearea\s+crate\)",
            "?x - surface",
            authority_domain,
            count=1,
            flags=re.IGNORECASE,
        )
        if count:
            authority_domain = normalized_domain
            transformations.append("replace_storage_either_with_surface_supertype")

    return authority_domain, authority_problem, tuple(transformations)


def _require_frozen_manifest(path: Path, phase_gate: BFSPhaseGate) -> None:
    for artifact in phase_gate.freeze["data"]["artifacts"]:
        artifact_path = Path(artifact["path"])
        if not artifact_path.is_absolute():
            artifact_path = _REPO_ROOT / artifact_path
        if artifact_path.resolve() == path:
            return
    raise ValueError("accepted curriculum manifest is not declared by the phase")


def _load_candidates(path: Path, phase_gate: BFSPhaseGate) -> dict[tuple[str, str], list[dict[str, Any]]]:
    allowed_splits = set(phase_gate.freeze["data"]["allowed_splits"])
    domains = set(phase_gate.freeze["data"]["domains"])
    difficulties = set(phase_gate.freeze["data"]["strata"])
    candidates: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        required_fields = {
            "bucket",
            "domain_id",
            "domain_path",
            "instance_id",
            "problem_path",
            "split",
            "status",
        }
        if not isinstance(row, dict) or not required_fields <= row.keys():
            raise ValueError(f"accepted curriculum row is malformed at line {line_number}")
        if row["status"] != "accepted":
            raise ValueError(f"frozen accepted manifest contains a non-accepted row at line {line_number}")
        if row["split"] not in allowed_splits:
            if phase_gate.freeze["schema_version"] in {
                "bfs_phase_freeze_v3",
                "bfs_phase_freeze_v5",
                "bfs_phase_freeze_v6",
            }:
                raise ValueError(f"BFS v3 selected manifest contains a forbidden split at line {line_number}")
            continue
        if row["domain_id"] not in domains or row["bucket"] not in difficulties:
            raise ValueError(f"curriculum row uses an unfrozen stratum at line {line_number}")
        candidates.setdefault((row["domain_id"], row["bucket"]), []).append(row)
    for rows in candidates.values():
        rows.sort(key=lambda row: (row["split"], row["instance_id"]))
    return candidates


def _required_strata(phase_gate: BFSPhaseGate) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (domain, difficulty)
            for domain in phase_gate.freeze["data"]["domains"]
            for difficulty in phase_gate.freeze["data"]["strata"]
        )
    )


def _minimum_per_stratum(phase_gate: BFSPhaseGate) -> int:
    value = phase_gate.freeze["thresholds"]["expert_trace_minimum_per_domain_difficulty"]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("expert trace minimum must be a positive integer")
    return value


def _select_split_candidates(
    rows: list[dict[str, Any]],
    *,
    allowed_splits: list[str],
    minimum: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for split in allowed_splits:
        split_rows = [row for row in rows if row["split"] == split]
        if split_rows:
            selected.extend(split_rows[:minimum])
    return selected


def _artifact(path: Path, output_root: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(output_root).as_posix(),
        "size_bytes": len(payload),
    }


def _source_path(value: object) -> Path:
    path = Path(str(value))
    return path.resolve() if path.is_absolute() else (_REPO_ROOT / path).resolve()


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


__all__ = ["run_frozen_bfs_generation_smoke", "run_frozen_bfs_trace_generation"]
