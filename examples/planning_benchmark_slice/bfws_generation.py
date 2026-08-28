"""Issue-57-gated exact BFWS expert trace generation."""

from __future__ import annotations

import gzip
import json
import os
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from time import monotonic
from typing import Any, cast

from src.data_collect.generate import GenerationRequest, GenerationRunReceipt, run_authorized_generation
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, StopOutcome

from .bfws_phase import BFWSPhaseGate
from .episode_evidence import (
    materialize_episode_artifacts,
    read_episode_evidence,
    write_episode_evidence,
)
from .pddl_state import GroundedAction, PDDLStateAuthority
from .search_episode import run_search_episode

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL_TIE_BREAK = "novelty_goal_count_depth_generation_serial"
_TRACE_MANIFEST_PATH = Path("manifests/bfws-expert-traces.json")
_TRACE_MANIFEST_SCHEMA = "bfws_expert_trace_generation_v1"


def preflight_frozen_bfws_trace_generation(phase_gate: BFWSPhaseGate) -> tuple[dict[str, Any], ...]:
    """Return the complete authorized development panel after checking its frozen totals."""

    phase_gate.require_run(stage="trace_generation", contract_id=phase_gate.phase_id)
    manifest_path = _development_manifest_path(phase_gate)
    rows = tuple(json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line)
    if (
        len(rows) != 105
        or sum(row["exact_reference_decision_count"] for row in rows) != 69_019
        or sum(row["exact_reference_expansion_count"] for row in rows) != 25_573
        or {row["split"] for row in rows} != {"train", "dev"}
    ):
        raise ValueError("BFWS trace panel differs from the issue-56 freeze")
    return rows


def generate_frozen_bfws_trace(
    *,
    row: Mapping[str, Any],
    request: GenerationRequest,
    phase_gate: BFWSPhaseGate,
    resume: bool,
) -> dict[str, Any]:
    """Generate or replay one authorized member of the frozen BFWS panel."""

    phase_gate.require_run(
        stage="trace_generation",
        contract_id=request.binding.contract_id,
        split=str(row.get("split")),
    )
    frozen_rows = preflight_frozen_bfws_trace_generation(phase_gate)
    frozen = next((item for item in frozen_rows if item["instance_id"] == row.get("instance_id")), None)
    if frozen is None or dict(row) != frozen:
        raise ValueError("BFWS trace task is not an exact row from the frozen development manifest")

    output_root = Path(request.binding.output_root)
    relative_root = _trace_relative_root(frozen)
    evidence_path = output_root / relative_root / "evidence.jsonl.gz"
    search_trace_path = output_root / relative_root / "search-trace.json.gz"

    if evidence_path.is_file():
        if not resume:
            raise FileExistsError(f"BFWS trace already exists: {evidence_path}")
        episode = read_episode_evidence(evidence_path)
        _verify_episode(episode, frozen)
        _formal_task, expected_trace = materialize_episode_artifacts(episode["evidence"])
        if search_trace_path.is_file() and gzip.decompress(search_trace_path.read_bytes()) != expected_trace:
            raise ValueError(f"resumed BFWS search trace differs: {frozen['instance_id']}")
        if not search_trace_path.is_file():
            _atomic_write(search_trace_path, gzip.compress(expected_trace, compresslevel=9, mtime=0))
        return _trace_item(frozen, episode, evidence_path, search_trace_path, output_root, phase_gate)

    domain_pddl = (_REPO_ROOT / frozen["domain_path"]).read_text(encoding="utf-8")
    problem_pddl = (_REPO_ROOT / frozen["problem_path"]).read_text(encoding="utf-8")
    fixture = {
        "domain_pddl": domain_pddl,
        "instance_id": frozen["instance_id"],
        "problem_pddl": problem_pddl,
    }
    with tempfile.TemporaryDirectory(prefix="bfws-trace-task-") as temporary:
        fixture_path = Path(temporary) / "task.json"
        fixture_path.write_bytes(_canonical_bytes(fixture))
        episode = run_search_episode(
            task_path=fixture_path,
            algorithm="best_first_width",
            modality="text-state",
            policy="exact",
            max_expansions=frozen["exact_reference_expansion_count"],
            gate_receipt=cast(GateReceipt, request.gate_receipt),
            authorization_receipt=cast(AuthorizationReceipt | None, request.authorization_receipt),
            ancestor_receipt_id=request.ancestor_receipt_id,
            frozen_binding=phase_gate.receipt(stage="trace_generation"),
        )
    _verify_episode(episode, frozen)
    _formal_task, search_trace = materialize_episode_artifacts(episode["evidence"])
    write_episode_evidence(evidence_path, episode)
    _atomic_write(search_trace_path, gzip.compress(search_trace, compresslevel=9, mtime=0))
    return _trace_item(frozen, episode, evidence_path, search_trace_path, output_root, phase_gate)


def run_frozen_bfws_trace_generation(
    *,
    request: GenerationRequest,
    phase_gate: BFWSPhaseGate,
    resume: bool,
    progress: Callable[[str], None] | None = None,
) -> GenerationRunReceipt:
    """Generate or resume all 105 traces and retain a governed completion receipt."""

    def execute() -> dict[str, object]:
        phase_gate.require_run(stage="trace_generation", contract_id=request.binding.contract_id)
        output_root = Path(request.binding.output_root)
        manifest_path = output_root / _TRACE_MANIFEST_PATH
        if output_root.exists() and not resume:
            raise FileExistsError(f"BFWS trace output already exists: {output_root}; pass resume=True to reuse it")
        if manifest_path.is_file():
            manifest = verify_frozen_bfws_trace_release(manifest_path, phase_gate=phase_gate)
            return _execution_result(manifest_path, manifest)
        output_root.mkdir(parents=True, exist_ok=True)

        rows = preflight_frozen_bfws_trace_generation(phase_gate)
        total_decisions = sum(row["exact_reference_decision_count"] for row in rows)
        completed_decisions = 0
        started = monotonic()
        trace_items: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            evidence_path = output_root / _trace_relative_root(row) / "evidence.jsonl.gz"
            reused = evidence_path.is_file()
            _report(
                progress,
                f"[{index}/{len(rows)}] starting {row['instance_id']} "
                f"({row['exact_reference_decision_count']} decisions)",
            )
            trace_items.append(
                generate_frozen_bfws_trace(
                    row=row,
                    request=request,
                    phase_gate=phase_gate,
                    resume=resume,
                )
            )
            completed_decisions += row["exact_reference_decision_count"]
            elapsed = monotonic() - started
            eta = (
                0.0
                if completed_decisions == total_decisions
                else elapsed * (total_decisions - completed_decisions) / completed_decisions
            )
            _report(
                progress,
                f"[{index}/{len(rows)}] {'replayed' if reused else 'completed'} {row['instance_id']}; "
                f"elapsed {_duration(elapsed)}; ETA {_duration(eta)}",
            )

        manifest = _trace_manifest(trace_items, phase_gate)
        _atomic_write(manifest_path, _canonical_bytes(manifest))
        return _execution_result(manifest_path, manifest)

    return run_authorized_generation(request, execute)


def verify_frozen_bfws_trace_release(
    manifest_path: str | Path,
    *,
    phase_gate: BFWSPhaseGate,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Replay every released trace and require exact frozen counters and artifacts."""

    phase_gate.require_run(stage="trace_generation", contract_id=phase_gate.phase_id)
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_bytes())
    rows = preflight_frozen_bfws_trace_generation(phase_gate)
    if not isinstance(manifest, dict) or not _manifest_summary_matches(manifest, rows, phase_gate):
        raise ValueError("BFWS trace release manifest differs from the frozen phase")
    output_root = path.parent.parent
    items_by_instance = {item.get("instance_id"): item for item in manifest["traces"]}
    if len(items_by_instance) != len(rows):
        raise ValueError("BFWS trace release contains duplicate or missing instances")

    for index, row in enumerate(rows, start=1):
        retained = items_by_instance.get(row["instance_id"])
        if not isinstance(retained, dict):
            raise ValueError(f"BFWS trace release is missing: {row['instance_id']}")
        evidence_path = output_root / retained["evidence"]["path"]
        search_trace_path = output_root / retained["search_trace"]["path"]
        episode = read_episode_evidence(evidence_path)
        _verify_episode(episode, row)
        _formal_task, search_trace = materialize_episode_artifacts(episode["evidence"])
        if not search_trace_path.is_file() or gzip.decompress(search_trace_path.read_bytes()) != search_trace:
            raise ValueError(f"BFWS released search trace differs from replay: {row['instance_id']}")
        expected = _trace_item(row, episode, evidence_path, search_trace_path, output_root, phase_gate)
        if retained != expected:
            raise ValueError(f"BFWS released trace metadata differs: {row['instance_id']}")
        _report(progress, f"[{index}/{len(rows)}] replayed {row['instance_id']}")
    return manifest


def _verify_episode(episode: Mapping[str, Any], row: Mapping[str, Any]) -> None:
    result = episode.get("result")
    expected = {
        "decision_count": row["exact_reference_decision_count"],
        "duplicate_count": row["exact_reference_duplicate_count"],
        "expansion_count": row["exact_reference_expansion_count"],
        "generated_count": row["exact_reference_generated_count"],
        "peak_frontier": row["exact_reference_peak_frontier"],
    }
    if not isinstance(result, Mapping) or any(result.get(name) != value for name, value in expected.items()):
        raise ValueError(f"BFWS trace counters differ from the frozen reference: {row['instance_id']}")
    if (
        result.get("completion") != "completed"
        or result.get("goal_reached") is not True
        or result.get("termination") != "goal_reached"
        or result.get("outcome") != StopOutcome.PASS.value
        or result.get("scientific_completion") is not True
        or result.get("algorithm_invariants_hold") is not True
        or result.get("novelty_pruned_count") != 0
    ):
        raise ValueError(f"BFWS trace did not produce a replay-valid solved episode: {row['instance_id']}")

    evidence = episode.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError(f"BFWS trace evidence is missing: {row['instance_id']}")
    task = evidence["header"]["task"]
    authority = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"])
    if authority.semantic_task_identity() != row["semantic_task_identity"]:
        raise ValueError(f"BFWS trace semantic task identity differs: {row['instance_id']}")
    if _evidence_plan(evidence, authority) != row["exact_reference_plan"]:
        raise ValueError(f"BFWS trace plan differs from the frozen reference: {row['instance_id']}")


def _evidence_plan(evidence: Mapping[str, Any], authority: PDDLStateAuthority) -> list[str]:
    parents: dict[str, tuple[str, GroundedAction]] = {}
    goal_state_id: str | None = None
    for event in evidence["events"]:
        targets = event["newly_enqueued_state_ids"]
        if not targets:
            continue
        operation = event["operation"]
        action = operation["action"]
        target_state_id = targets[0]
        parents[target_state_id] = (
            operation["source_state_id"],
            GroundedAction(action["name"], tuple(action["args"])),
        )
        goal_state_id = target_state_id
    if goal_state_id is None:
        return []
    plan: list[str] = []
    state_id = goal_state_id
    while state_id != authority.initial_state.state_id:
        state_id, action = parents[state_id]
        plan.append(action.serialize())
    plan.reverse()
    return plan


def _trace_item(
    row: Mapping[str, Any],
    episode: Mapping[str, Any],
    evidence_path: Path,
    search_trace_path: Path,
    output_root: Path,
    phase_gate: BFWSPhaseGate,
) -> dict[str, Any]:
    result = episode["result"]
    return {
        "algorithm": "best_first_width",
        "canonical_tie_break": _CANONICAL_TIE_BREAK,
        "difficulty": row["difficulty"],
        "domain_id": row["domain_id"],
        "evidence": _artifact(evidence_path, output_root),
        "exact_reference_decision_count": row["exact_reference_decision_count"],
        "instance_id": row["instance_id"],
        "max_expansions": row["exact_reference_expansion_count"],
        "phase_receipt": phase_gate.receipt(stage="trace_generation"),
        "result": {
            name: result[name]
            for name in (
                "decision_count",
                "duplicate_count",
                "expansion_count",
                "generated_count",
                "goal_reached",
                "outcome",
                "peak_frontier",
                "scientific_completion",
                "termination",
            )
        },
        "search_trace": _artifact(search_trace_path, output_root),
        "semantic_task_identity": row["semantic_task_identity"],
        "source": {
            "development_manifest_path": phase_gate.components["trace"]["development_manifest_path"],
            "domain_path": row["domain_path"],
            "problem_path": row["problem_path"],
            "split": row["split"],
        },
        "split": row["split"],
        "trace_scope": "complete_exact_bfws_episode",
        "variant": "full_bfws_goal_count",
    }


def _trace_manifest(trace_items: list[dict[str, Any]], phase_gate: BFWSPhaseGate) -> dict[str, Any]:
    split_counts = Counter(item["split"] for item in trace_items)
    return {
        "algorithm": dict(phase_gate.components["trace"]["algorithm"]),
        "coverage": {
            "exact_reference_decision_count": sum(item["exact_reference_decision_count"] for item in trace_items),
            "instance_count": len(trace_items),
            "replay_verified_instance_count": len(trace_items),
            "split_counts": dict(sorted(split_counts.items())),
            "stratum_count": len({(item["domain_id"], item["difficulty"]) for item in trace_items}),
        },
        "evidence_schema": phase_gate.components["trace"]["evidence_schema"],
        "phase_receipt": phase_gate.receipt(stage="trace_generation"),
        "schema_version": _TRACE_MANIFEST_SCHEMA,
        "source_issue": 57,
        "traces": trace_items,
    }


def _manifest_summary_matches(
    manifest: Mapping[str, Any],
    rows: tuple[dict[str, Any], ...],
    phase_gate: BFWSPhaseGate,
) -> bool:
    return (
        set(manifest)
        == {"algorithm", "coverage", "evidence_schema", "phase_receipt", "schema_version", "source_issue", "traces"}
        and manifest.get("algorithm") == phase_gate.components["trace"]["algorithm"]
        and manifest.get("coverage")
        == {
            "exact_reference_decision_count": sum(row["exact_reference_decision_count"] for row in rows),
            "instance_count": len(rows),
            "replay_verified_instance_count": len(rows),
            "split_counts": dict(sorted(Counter(row["split"] for row in rows).items())),
            "stratum_count": len({(row["domain_id"], row["difficulty"]) for row in rows}),
        }
        and manifest.get("evidence_schema") == phase_gate.components["trace"]["evidence_schema"]
        and manifest.get("phase_receipt") == phase_gate.receipt(stage="trace_generation")
        and manifest.get("schema_version") == _TRACE_MANIFEST_SCHEMA
        and manifest.get("source_issue") == 57
        and isinstance(manifest.get("traces"), list)
        and len(manifest["traces"]) == len(rows)
    )


def _execution_result(manifest_path: Path, manifest: Mapping[str, Any]) -> dict[str, object]:
    coverage = manifest["coverage"]
    return {
        "exact_reference_decision_count": coverage["exact_reference_decision_count"],
        "replay_verified_instance_count": coverage["replay_verified_instance_count"],
        "trace_count": coverage["instance_count"],
        "trace_manifest_path": str(manifest_path.resolve()),
        "trace_manifest_size_bytes": manifest_path.stat().st_size,
    }


def _trace_relative_root(row: Mapping[str, Any]) -> Path:
    return Path("traces") / row["domain_id"] / row["difficulty"] / row["split"] / row["instance_id"]


def _development_manifest_path(phase_gate: BFWSPhaseGate) -> Path:
    return _REPO_ROOT / phase_gate.components["trace"]["development_manifest_path"]


def _artifact(path: Path, output_root: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(output_root).as_posix(),
        "size_bytes": path.stat().st_size,
    }


def _report(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _duration(seconds: float) -> str:
    total = max(0, round(seconds))
    hours, remainder = divmod(total, 3_600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary_name).replace(path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


__all__ = [
    "generate_frozen_bfws_trace",
    "preflight_frozen_bfws_trace_generation",
    "run_frozen_bfws_trace_generation",
    "verify_frozen_bfws_trace_release",
]
