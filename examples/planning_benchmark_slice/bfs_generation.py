"""Issue-49-gated entry points for governed BFS generation."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, cast

from src.data_collect.generate import GenerationRequest, GenerationRunReceipt, run_authorized_generation
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, StopOutcome
from src.data_collect.replay import parse_canonical_bundle

from .bfs_phase import BFSPhaseGate
from .generation_orchestrator import run_bfs_generation_smoke
from .search_episode import replay_search_episode, run_search_episode

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TRACE_MANIFEST_PATH = Path("manifests/bfs-expert-traces.json")
_TRACE_MANIFEST_SCHEMA = "bfs_expert_trace_generation_v1"
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
) -> GenerationRunReceipt:
    """Generate replay-verified FIFO BFS traces for every frozen stratum."""

    def execute() -> dict[str, object]:
        phase_gate.require_run(
            stage="trace_generation",
            contract_id=request.binding.contract_id,
        )
        output_root = Path(request.binding.output_root).resolve()
        if output_root.exists():
            raise FileExistsError(f"BFS trace output root already exists: {output_root}")

        manifest_path = Path(accepted_manifest_path).resolve()
        manifest_sha256 = _require_frozen_manifest(manifest_path, phase_gate)
        candidates = _load_candidates(manifest_path, phase_gate)
        required = _required_strata(phase_gate)
        minimum = _minimum_per_stratum(phase_gate)
        for stratum in required:
            if len(candidates.get(stratum, ())) < minimum:
                raise ValueError(f"frozen curriculum stratum has insufficient accepted tasks: {stratum}")

        output_root.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
        trace_items: list[dict[str, object]] = []
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
                    for row in candidates[(domain_id, difficulty)][:minimum]:
                        trace_items.append(
                            _generate_trace(
                                row=row,
                                difficulty=difficulty,
                                manifest_path=manifest_path,
                                manifest_sha256=manifest_sha256,
                                max_expansions=max_expansions,
                                request=request,
                                phase_gate=phase_gate,
                                fixture_root=fixture_root,
                                staging_root=staging_root,
                            )
                        )

            trace_manifest = {
                "algorithm": "bfs",
                "coverage": {
                    "covered_strata": len({(item["domain_id"], item["difficulty"]) for item in trace_items}),
                    "minimum_traces_per_domain_difficulty": minimum,
                    "required_strata": len(required),
                },
                "phase_receipt": phase_gate.receipt(stage="trace_generation"),
                "schema_version": _TRACE_MANIFEST_SCHEMA,
                "traces": trace_items,
            }
            trace_manifest_path = staging_root / _TRACE_MANIFEST_PATH
            _write_bytes(trace_manifest_path, _canonical_json_bytes(trace_manifest))
            trace_manifest_bytes = trace_manifest_path.read_bytes()
            staging_root.replace(output_root)
        except Exception:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise

        return {
            "covered_strata": len(required),
            "trace_count": len(trace_items),
            "trace_manifest_path": str((output_root / _TRACE_MANIFEST_PATH).resolve()),
            "trace_manifest_sha256": _sha256(trace_manifest_bytes),
        }

    return run_authorized_generation(request, execute)


def _generate_trace(
    *,
    row: dict[str, Any],
    difficulty: str,
    manifest_path: Path,
    manifest_sha256: str,
    max_expansions: int,
    request: GenerationRequest,
    phase_gate: BFSPhaseGate,
    fixture_root: Path,
    staging_root: Path,
) -> dict[str, object]:
    domain_path = Path(row["domain_path"]).resolve()
    problem_path = Path(row["problem_path"]).resolve()
    domain_bytes = domain_path.read_bytes()
    problem_bytes = problem_path.read_bytes()
    domain_sha256 = _sha256(domain_bytes)
    problem_sha256 = _sha256(problem_bytes)
    if domain_sha256 != row["domain_hash"] or problem_sha256 != row["problem_hash"]:
        raise ValueError(f"curriculum PDDL bytes have drifted: {row['instance_id']}")

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
        signing_key=request.signing_key,
        ancestor_receipt_digest=request.ancestor_receipt_digest,
    )
    result = episode["result"]
    if (
        not isinstance(result, dict)
        or result.get("completion") != "completed"
        or result.get("outcome") != StopOutcome.PASS.value
        or result.get("scientific_completion") is not True
    ):
        raise ValueError(f"BFS trace generation did not complete: {row['instance_id']}")
    if replay_search_episode(episode["evidence"], signing_key=request.signing_key) != episode:
        raise ValueError(f"BFS trace replay differs: {row['instance_id']}")

    evidence = cast(dict[str, Any], episode["evidence"])
    bundle = base64.b64decode(cast(str, evidence["bundle"]).encode("ascii"), validate=True)
    search_trace = parse_canonical_bundle(bundle)["search-trace.json"]
    relative_root = Path("traces") / str(row["domain_id"]) / difficulty / str(row["instance_id"])
    evidence_path = staging_root / relative_root / "evidence.json"
    search_trace_path = staging_root / relative_root / "search-trace.json"
    _write_bytes(evidence_path, _canonical_json_bytes(evidence))
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
            "accepted_manifest_sha256": manifest_sha256,
            "authority_domain_sha256": _sha256(authority_domain.encode("utf-8")),
            "authority_problem_sha256": _sha256(authority_problem.encode("utf-8")),
            "authority_transformations": list(transformations),
            "domain_path": str(domain_path),
            "domain_sha256": domain_sha256,
            "manifest_domain_sha256": row["domain_hash"],
            "manifest_problem_sha256": row["problem_hash"],
            "problem_path": str(problem_path),
            "problem_sha256": problem_sha256,
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


def _require_frozen_manifest(path: Path, phase_gate: BFSPhaseGate) -> str:
    payload = path.read_bytes()
    digest = _sha256(payload)
    for artifact in phase_gate.freeze["data"]["artifacts"]:
        artifact_path = Path(artifact["path"])
        if not artifact_path.is_absolute():
            artifact_path = _REPO_ROOT / artifact_path
        if artifact_path.resolve() == path and artifact["sha256"] == digest:
            return digest
    raise ValueError("accepted curriculum manifest does not match the frozen phase artifact")


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
            "domain_hash",
            "domain_id",
            "domain_path",
            "instance_id",
            "problem_hash",
            "problem_path",
            "split",
            "status",
        }
        if not isinstance(row, dict) or not required_fields <= row.keys():
            raise ValueError(f"accepted curriculum row is malformed at line {line_number}")
        if row["status"] != "accepted":
            raise ValueError(f"frozen accepted manifest contains a non-accepted row at line {line_number}")
        if row["split"] not in allowed_splits:
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


def _artifact(path: Path, output_root: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(output_root).as_posix(),
        "sha256": _sha256(payload),
        "size_bytes": len(payload),
    }


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


__all__ = ["run_frozen_bfs_generation_smoke", "run_frozen_bfs_trace_generation"]
