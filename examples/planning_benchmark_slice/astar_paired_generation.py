"""Issue-63 gated, paired exact A* expert-trace generation."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from time import monotonic
from typing import Any, cast

from src.data_collect.generate import (
    GenerationRequest,
    GenerationRunReceipt,
    ValidExecutionStop,
    run_authorized_generation,
)
from src.data_collect.governance import AuthorizationReceipt, GateReceipt

from .astar_phase import ASTAR_PAIRED_ADAPTERS, AStarPairedPhaseGate, validate_astar_generation_budget
from .episode_evidence import materialize_episode_artifacts, read_episode_evidence, write_episode_evidence
from .search_episode import replay_search_episode, run_search_episode

_ADAPTERS = ASTAR_PAIRED_ADAPTERS
_CANONICAL_TIE_BREAK = ["f", "generation_serial"]
_MANIFEST_SCHEMA = "astar_paired_expert_trace_generation_v1"
_MANIFEST_RELATIVE = Path("manifests/astar-paired-expert-traces.json")


def preflight_frozen_astar_pair_generation(
    phase_gate: AStarPairedPhaseGate,
) -> tuple[dict[str, Any], ...]:
    """Return the ordered issue-62 pairs after validating their shared ceilings."""

    phase_gate.require_run(stage="trace_generation", contract_id=phase_gate.phase_id)
    rows = phase_gate.components["task"].get("pairs")
    budget = phase_gate.components["budget"].get("generation_budget")
    if not isinstance(rows, list) or not isinstance(budget, Mapping):
        raise ValueError("A* paired phase lacks its frozen task or generation budget")
    validated_budget = validate_astar_generation_budget(budget, tuple(rows))
    caps = validated_budget["max_expansions_by_difficulty"]
    result: list[dict[str, Any]] = []
    for row in rows:
        cap = row.get("generation_max_expansions") if isinstance(row, Mapping) else None
        if (
            cap != caps.get(row.get("difficulty"))
            or row.get("eligible_adapters") != list(_ADAPTERS)
        ):
            raise ValueError("A* pair does not bind one positive shared expansion ceiling")
        result.append(dict(row))
    return tuple(result)


def generate_frozen_astar_pair(
    *,
    row: Mapping[str, Any],
    request: GenerationRequest,
    phase_gate: AStarPairedPhaseGate,
    resume: bool,
    input_token_counter: Callable[[Mapping[str, Any]], int] | None = None,
    target_token_counter: Callable[[str], int] | None = None,
    fixture_only: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Generate, independently replay, and audit both adapters for one pair."""

    phase_gate.require_run(stage="trace_generation", contract_id=request.binding.contract_id)
    frozen = next(
        (item for item in preflight_frozen_astar_pair_generation(phase_gate) if item["pair_id"] == row.get("pair_id")),
        None,
    )
    if frozen is None or dict(row) != frozen:
        raise ValueError("A* pair is not an exact row from the frozen issue-62 task component")
    cap = frozen["generation_max_expansions"]
    output_root = Path(request.binding.output_root)
    pair_root = output_root / "pairs" / frozen["pair_id"]
    retained_paths = {
        adapter: (
            pair_root / adapter / "evidence.jsonl.gz",
            pair_root / adapter / "astar-trace-view.json.gz",
        )
        for adapter in _ADAPTERS
    }
    alignment_path = pair_root / "alignment.json"
    complete_path = pair_root / "pair.json"
    if pair_root.exists():
        if not resume:
            raise FileExistsError(f"A* paired trace already exists: {frozen['pair_id']}")
        if (
            not all(path.is_file() for paths in retained_paths.values() for path in paths)
            or not alignment_path.is_file()
            or not complete_path.is_file()
        ):
            quarantine_root = output_root / ".quarantine" / frozen["pair_id"]
            if quarantine_root.exists():
                raise FileExistsError(
                    f"A* incomplete-pair quarantine already exists: {quarantine_root}"
                )
            quarantine_root.parent.mkdir(parents=True, exist_ok=True)
            pair_root.replace(quarantine_root)
        else:
            item = _retained_pair_item(frozen, retained_paths, alignment_path, output_root, phase_gate)
            if complete_path.read_bytes() != _canonical_bytes(item):
                raise ValueError(f"retained complete A* pair differs immutably: {frozen['pair_id']}")
            from .astar_paired_trace_audit import audit_frozen_astar_pair

            audit = audit_frozen_astar_pair(
                row=frozen,
                pair_item=item,
                output_root=output_root,
                phase_gate=phase_gate,
                input_token_counter=input_token_counter,
                target_token_counter=target_token_counter,
                fixture_only=fixture_only,
                progress=progress,
            )
            _require_zero_audit(audit, frozen["pair_id"])
            return item

    staging_root = output_root / ".staging" / frozen["pair_id"]
    if staging_root.exists():
        retained_names = {
            "alignment.json",
            "astar-trace-view.json.gz",
            "evidence.jsonl.gz",
            "pair.json",
        }
        if any(path.name in retained_names for path in staging_root.rglob("*")):
            raise FileExistsError(
                f"A* pair staging contains retained evidence and cannot be discarded: {staging_root}"
            )
        shutil.rmtree(staging_root)

    episodes: dict[str, dict[str, Any]] = {}
    traces: dict[str, bytes] = {}
    task_path = phase_gate.repo_root / frozen["task_path"]
    adapter_started = monotonic()
    for adapter_index, adapter in enumerate(_ADAPTERS, start=1):
        _progress(progress, f"adapter_generation:{adapter}", adapter_index - 1, 2, adapter_started, frozen["pair_id"])
        episode = run_search_episode(
            task_path=task_path,
            algorithm=adapter,
            modality="text-state",
            policy="exact",
            max_expansions=cap,
            gate_receipt=cast(GateReceipt, request.gate_receipt),
            authorization_receipt=cast(AuthorizationReceipt | None, request.authorization_receipt),
            ancestor_receipt_id=request.ancestor_receipt_id,
            frozen_binding=phase_gate.receipt(stage="trace_generation"),
        )
        replay_search_episode(episode["evidence"])
        result = episode["result"]
        if result.get("termination") == "expansion_budget":
            raise ValidExecutionStop(
                "resource_exhaustion",
                execution_result={
                    "adapter": adapter,
                    "pair_id": frozen["pair_id"],
                    "termination": "expansion_budget",
                },
            )
        if (
            result.get("termination") != "goal_reached"
            or result.get("goal_reached") is not True
            or result.get("algorithm_invariants_hold") is not True
            or result.get("invalid_operation_count") != 0
        ):
            raise ValueError(f"A* pair did not produce two invariant-valid solved traces: {frozen['pair_id']}")
        episodes[adapter] = episode
        _task_bytes, traces[adapter] = materialize_episode_artifacts(episode["evidence"])
        _progress(progress, f"adapter_generation:{adapter}", adapter_index, 2, adapter_started, frozen["pair_id"])

    alignment = build_astar_pair_alignment(frozen, episodes)
    staging_paths = {
        adapter: (
            staging_root / adapter / "evidence.jsonl.gz",
            staging_root / adapter / "astar-trace-view.json.gz",
        )
        for adapter in _ADAPTERS
    }
    staging_alignment = staging_root / "alignment.json"
    try:
        for adapter in _ADAPTERS:
            evidence_path, trace_path = staging_paths[adapter]
            write_episode_evidence(evidence_path, episodes[adapter])
            _atomic_write(trace_path, gzip.compress(traces[adapter], compresslevel=9, mtime=0))
        _atomic_write(staging_alignment, _canonical_bytes(alignment))
        staging_item = _pair_item(
            frozen,
            episodes,
            staging_paths,
            staging_alignment,
            output_root,
            phase_gate,
        )
        from .astar_paired_trace_audit import audit_frozen_astar_pair

        audit = audit_frozen_astar_pair(
            row=frozen,
            pair_item=staging_item,
            output_root=output_root,
            phase_gate=phase_gate,
            input_token_counter=input_token_counter,
            target_token_counter=target_token_counter,
            fixture_only=fixture_only,
            progress=progress,
        )
        _require_zero_audit(audit, frozen["pair_id"])
        item = _published_pair_item(staging_item, frozen["pair_id"])
        _atomic_write(staging_root / "pair.json", _canonical_bytes(item))
        pair_root.parent.mkdir(parents=True, exist_ok=True)
        staging_root.replace(pair_root)
        return item
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)


def run_frozen_astar_pair_generation(
    *,
    request: GenerationRequest,
    phase_gate: AStarPairedPhaseGate,
    resume: bool,
    progress: Callable[[str], None] | None = None,
) -> GenerationRunReceipt:
    """Run all pairs and publish a manifest only after the zero-error audit."""

    def execute() -> dict[str, object]:
        rows = preflight_frozen_astar_pair_generation(phase_gate)
        output_root = Path(request.binding.output_root)
        manifest_path = output_root / _MANIFEST_RELATIVE
        if manifest_path.is_file():
            if not resume:
                raise FileExistsError(f"A* paired release already exists: {manifest_path}")
            manifest = verify_frozen_astar_pair_release(manifest_path, phase_gate=phase_gate, progress=progress)
            return _execution_result(manifest_path, manifest)
        if output_root.exists() and not resume:
            raise FileExistsError(f"A* paired output already exists: {output_root}")

        started = monotonic()
        items: list[dict[str, Any]] = []
        total = len(rows)
        for completed, row in enumerate(rows, start=1):
            _progress(progress, "pair_generation", completed - 1, total, started, row["pair_id"])
            items.append(
                generate_frozen_astar_pair(
                    row=row,
                    request=request,
                    phase_gate=phase_gate,
                    resume=resume,
                    progress=progress,
                )
            )
            _progress(progress, "pair_generation", completed, total, started, row["pair_id"])
        manifest = _manifest(items, phase_gate)
        from .astar_paired_trace_audit import audit_astar_pair_items_release

        audit = audit_astar_pair_items_release(
            manifest=manifest,
            output_root=output_root,
            phase_gate=phase_gate,
            progress=progress,
            persist_audit_parts=True,
        )
        audit_path = output_root / "manifests/astar-paired-trace-audit.json"
        _atomic_write(audit_path, _canonical_bytes(audit))
        _atomic_write(manifest_path, _canonical_bytes(manifest))
        return _execution_result(manifest_path, manifest)

    return run_authorized_generation(request, execute)


def verify_frozen_astar_pair_release(
    manifest_path: str | Path,
    *,
    phase_gate: AStarPairedPhaseGate,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Verify pair coverage, artifact hashes, replay, alignment, and release audit."""

    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_bytes())
    rows = preflight_frozen_astar_pair_generation(phase_gate)
    if not isinstance(manifest, dict) or manifest != _manifest(manifest.get("pairs", []), phase_gate):
        raise ValueError("A* paired release manifest is malformed")
    by_id = {item.get("pair_id"): item for item in manifest["pairs"] if isinstance(item, dict)}
    if len(by_id) != len(rows) or list(by_id) != [row["pair_id"] for row in rows]:
        raise ValueError("A* paired release is incomplete or nondeterministically ordered")
    output_root = path.parent.parent
    from .astar_paired_trace_audit import audit_astar_pair_items_release

    audit = audit_astar_pair_items_release(
        manifest=manifest,
        output_root=output_root,
        phase_gate=phase_gate,
        progress=progress,
    )
    audit_path = output_root / "manifests/astar-paired-trace-audit.json"
    if not audit_path.is_file() or audit_path.read_bytes() != _canonical_bytes(audit):
        raise ValueError("A* paired release audit is absent or differs from independent audit")
    return manifest


def build_astar_pair_alignment(
    row: Mapping[str, Any], episodes: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Align only world-state sources occurring exactly once in each adapter trace."""

    per_adapter: dict[str, dict[str, list[list[dict[str, Any]]]]] = {}
    for adapter in _ADAPTERS:
        episode = episodes.get(adapter)
        if not isinstance(episode, Mapping):
            raise ValueError("A* alignment requires exactly one trace from each adapter")
        header = episode["evidence"]["header"]
        task = header["task"]
        if header.get("authority_id") != episodes[_ADAPTERS[0]]["evidence"]["header"].get("authority_id"):
            raise ValueError("A* alignment task semantic identity differs")
        if hashlib.sha256(_canonical_bytes(task)).hexdigest() != hashlib.sha256(
            _canonical_bytes(episodes[_ADAPTERS[0]]["evidence"]["header"]["task"])
        ).hexdigest():
            raise ValueError("A* alignment task bytes differ")
        sources: dict[str, list[list[dict[str, Any]]]] = {}
        for event in episode["evidence"]["events"]:
            source = event["expanded_state_id"]
            action_targets: list[dict[str, Any]] = []
            for decision in event["decisions"]:
                candidate = next(
                    candidate
                    for candidate in decision["input"]["successor_candidates"]
                    if candidate["action"] == decision["operation"]["action"]
                )
                action_targets.append(
                    {
                        "action": decision["operation"]["action"],
                        "target_state_id": candidate["target_state_id"],
                    }
                )
            action_targets.sort(key=lambda item: _canonical_bytes(item["action"]))
            sources.setdefault(source, []).append(action_targets)
        per_adapter[adapter] = sources
    aligned: list[dict[str, Any]] = []
    all_sources = sorted(set().union(*(set(value) for value in per_adapter.values())))
    unmatched: dict[str, list[str]] = {adapter: [] for adapter in _ADAPTERS}
    for source in all_sources:
        halves = [per_adapter[adapter].get(source, []) for adapter in _ADAPTERS]
        if all(len(half) == 1 for half in halves):
            if halves[0][0] != halves[1][0]:
                raise ValueError("A* aligned unique world-state successors differ")
            aligned.append({"action_targets": halves[0][0], "source_state_id": source})
        else:
            for adapter, half in zip(_ADAPTERS, halves, strict=True):
                if half:
                    unmatched[adapter].append(source)
    return {
        "aligned": aligned,
        "pair_id": row["pair_id"],
        "schema_version": "astar_paired_trace_alignment_v1",
        "semantic_task_identity": row["semantic_task_identity"],
        "unmatched_source_state_ids": unmatched,
    }


def _retained_pair_item(
    row: Mapping[str, Any],
    paths: Mapping[str, tuple[Path, Path]],
    alignment_path: Path,
    output_root: Path,
    phase_gate: AStarPairedPhaseGate,
) -> dict[str, Any]:
    episodes = {adapter: read_episode_evidence(paths[adapter][0]) for adapter in _ADAPTERS}
    for adapter in _ADAPTERS:
        replay_search_episode(episodes[adapter]["evidence"])
        _task, trace = materialize_episode_artifacts(episodes[adapter]["evidence"])
        if gzip.decompress(paths[adapter][1].read_bytes()) != trace:
            raise ValueError(f"retained A* trace differs from replay: {row['pair_id']} {adapter}")
    expected_alignment = build_astar_pair_alignment(row, episodes)
    if alignment_path.read_bytes() != _canonical_bytes(expected_alignment):
        raise ValueError(f"retained A* alignment differs: {row['pair_id']}")
    return _pair_item(row, episodes, paths, alignment_path, output_root, phase_gate)


def _pair_item(
    row: Mapping[str, Any],
    episodes: Mapping[str, Mapping[str, Any]],
    paths: Mapping[str, tuple[Path, Path]],
    alignment_path: Path,
    output_root: Path,
    phase_gate: AStarPairedPhaseGate,
) -> dict[str, Any]:
    adapters: list[dict[str, Any]] = []
    for adapter in _ADAPTERS:
        result = episodes[adapter]["result"]
        adapters.append(
            {
                "adapter": adapter,
                "decision_count": result["decision_count"],
                "evidence": _artifact(paths[adapter][0], output_root),
                "expansion_count": result["expansion_count"],
                "result": {
                    key: result[key]
                    for key in (
                        "algorithm_invariants_hold", "goal_reached", "outcome",
                        "scientific_completion", "termination",
                    )
                },
                "trace": _artifact(paths[adapter][1], output_root),
            }
        )
    return {
        "adapters": adapters,
        "alignment": _artifact(alignment_path, output_root),
        "canonical_tie_break": _CANONICAL_TIE_BREAK,
        "difficulty": row["difficulty"],
        "generation_max_expansions": row["generation_max_expansions"],
        "instance_id": row["instance_id"],
        "pair_id": row["pair_id"],
        "phase_receipt": phase_gate.receipt(stage="trace_generation"),
        "semantic_task_identity": row["semantic_task_identity"],
        "split": row["split"],
        "task": {
            "path": row["task_path"],
            "sha256": row["task_sha256"],
            "size_bytes": row["task_bytes"],
        },
    }


def _manifest(items: list[dict[str, Any]], phase_gate: AStarPairedPhaseGate) -> dict[str, Any]:
    return {
        "canonical_tie_break": _CANONICAL_TIE_BREAK,
        "evidence_schema": "search_episode_evidence_v4",
        "pair_count": len(items),
        "pairs": items,
        "phase_receipt": phase_gate.receipt(stage="trace_generation"),
        "schema_version": _MANIFEST_SCHEMA,
        "source_issue": 63,
        "trace_schema": "astar_trace_view_v1",
    }


def _published_pair_item(staging_item: Mapping[str, Any], pair_id: str) -> dict[str, Any]:
    item = json.loads(_canonical_bytes(staging_item))
    staging_prefix = f".staging/{pair_id}/"
    published_prefix = f"pairs/{pair_id}/"
    bindings = [item["alignment"]]
    for adapter in item["adapters"]:
        bindings.extend((adapter["evidence"], adapter["trace"]))
    for binding in bindings:
        path = binding["path"]
        if not path.startswith(staging_prefix):
            raise ValueError("A* staging artifact path is outside its pair staging directory")
        binding["path"] = published_prefix + path.removeprefix(staging_prefix)
    return item


def _require_zero_audit(audit: Mapping[str, Any], pair_id: str) -> None:
    counters = audit.get("audit_results")
    if not isinstance(counters, Mapping) or any(value != 0 for value in counters.values()):
        raise ValueError(f"A* pair audit has nonzero rejection counters: {pair_id}")


def _execution_result(path: Path, manifest: Mapping[str, Any]) -> dict[str, object]:
    return {
        "pair_count": manifest["pair_count"],
        "trace_count": 2 * int(manifest["pair_count"]),
        "trace_manifest_path": str(path.resolve()),
        "trace_manifest_size_bytes": path.stat().st_size,
    }


def _artifact(path: Path, root: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def _progress(
    progress: Callable[[str], None] | None,
    stage: str,
    completed: int,
    total: int,
    started: float,
    pair_id: str | None,
) -> None:
    if progress is None:
        return
    elapsed = monotonic() - started
    remaining = 0.0 if completed == total or completed == 0 else elapsed * (total - completed) / completed
    progress(json.dumps({
        "completed": completed,
        "elapsed_seconds": round(elapsed, 6),
        "estimated_remaining_seconds": round(remaining, 6),
        "pair_id": pair_id,
        "stage": stage,
        "total": total,
    }, sort_keys=True, separators=(",", ":")))


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode()


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
    "build_astar_pair_alignment",
    "generate_frozen_astar_pair",
    "preflight_frozen_astar_pair_generation",
    "run_frozen_astar_pair_generation",
    "verify_frozen_astar_pair_release",
]
