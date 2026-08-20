"""Expansion-qualified candidate gate for the issue-111 BFS pilot."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.data_collect.adapters.base import GenerationSpec, GeneratorRejection
from src.data_collect.adapters.registry import (
    ADAPTER_TEMPLATES,
    CurriculumCommandAdapter,
    DomainSelection,
    PreparedCommand,
    TargetParameterPreset,
    _gripper_named_variant,
    _hanoi_named_variant,
    build_domain_registry,
)
from src.data_collect.config import load_curriculum_config
from src.data_collect.normalization import normalize_pddl
from src.data_collect.splits import split_assignment_id, whole_instance_identity

from .bfs_generation import _normalize_authority_input
from .pddl_state import PDDLStateAuthority

DOMAINS = (
    "15puzzle",
    "blocksworld",
    "depot",
    "driverlog",
    "elevators",
    "ferry",
    "freecell",
    "grid",
    "gripper",
    "logistics",
    "snake",
    "sokoban",
    "storage",
    "towers_of_hanoi",
    "visitall",
)
SPLITS = ("train", "dev")
BANDS = ("easy", "medium", "hard")
BAND_BOUNDS = {"easy": (1, 64), "medium": (65, 256), "hard": (257, 1024)}
CANDIDATE_CEILING = 500
SELECTION_SEED = 111
SCHEMA_VERSION = "bfs_pilot_qualification_v1"
PHASE_ID = "issue-111-bfs-expansion-qualified-pilot-v2"
_TIER_QUOTAS = (32, 64, 404)
_CURRICULUM_CONFIG = Path("src/data_collect/configs/curriculum_15_domains.yaml")


@dataclass(frozen=True, slots=True)
class ExactBFSResult:
    expansion_count: int
    goal_reached: bool
    plan: tuple[str, ...]
    trace_sha256: str


@dataclass(frozen=True, slots=True)
class QualifiedCandidate:
    candidate_id: str
    domain_id: str
    split: str
    size_tier: str
    seed: int | None
    normalized_problem_hash: str
    domain_pddl: str
    problem_pddl: str
    authority_domain_pddl: str
    authority_problem_pddl: str
    authority_transformations: tuple[str, ...]
    result: ExactBFSResult

    @property
    def band(self) -> str:
        band = expansion_band(self.result.expansion_count)
        if band is None:
            raise ValueError("candidate is not inside a qualified expansion band")
        return band

    @property
    def selection_key(self) -> str:
        return selection_key(self.normalized_problem_hash)


@dataclass(frozen=True, slots=True)
class PilotProfile:
    arguments: tuple[str, ...]
    parameters: Mapping[str, object]


_PROFILES: dict[str, tuple[PilotProfile, PilotProfile, PilotProfile]] = {
    "15puzzle": (
        PilotProfile(("-n", "2"), {"board_size": 2}),
        PilotProfile(("-n", "3"), {"board_size": 3}),
        PilotProfile(("-n", "3"), {"board_size": 3}),
    ),
    "blocksworld": (
        PilotProfile(("4", "3"), {"blocks": 3}),
        PilotProfile(("4", "4"), {"blocks": 4}),
        PilotProfile(("4", "5"), {"blocks": 5}),
    ),
    "depot": (
        PilotProfile(("-e", "1", "-i", "1", "-t", "1", "-p", "1", "-h", "1", "-c", "1"), {"crates": 1}),
        PilotProfile(("-e", "1", "-i", "1", "-t", "1", "-p", "2", "-h", "2", "-c", "2"), {"crates": 2}),
        PilotProfile(
            ("-e", "1", "-i", "2", "-t", "2", "-p", "2", "-h", "2", "-c", "2"),
            {"crates": 2, "distributors": 2},
        ),
    ),
    "driverlog": (
        PilotProfile(("3", "1", "1", "1"), {"junctions": 3, "packages": 1}),
        PilotProfile(("4", "1", "2", "1"), {"junctions": 4, "packages": 2}),
        PilotProfile(("5", "2", "2", "2"), {"junctions": 5, "packages": 2}),
    ),
    "elevators": (
        PilotProfile(("-f", "3", "-p", "1"), {"floors": 3, "passengers": 1}),
        PilotProfile(("-f", "4", "-p", "2"), {"floors": 4, "passengers": 2}),
        PilotProfile(("-f", "5", "-p", "3"), {"floors": 5, "passengers": 3}),
    ),
    "ferry": (
        PilotProfile(("-l", "2", "-c", "1"), {"locations": 2, "cars": 1}),
        PilotProfile(("-l", "3", "-c", "2"), {"locations": 3, "cars": 2}),
        PilotProfile(("-l", "4", "-c", "3"), {"locations": 4, "cars": 3}),
    ),
    "freecell": (
        PilotProfile(("-f", "1", "-c", "2", "-s", "1", "-0", "2", "-i", "1"), {"cards": 2}),
        PilotProfile(("-f", "2", "-c", "2", "-s", "2", "-0", "2", "-1", "2", "-i", "1"), {"cards": 4}),
        PilotProfile(("-f", "2", "-c", "3", "-s", "2", "-0", "3", "-1", "3", "-i", "2"), {"cards": 6}),
    ),
    "grid": (
        PilotProfile(("3", "3", "--shapes", "1", "--keys", "1", "--locks", "1", "--prob-goal", "0.4"), {"x": 3, "y": 3}),
        PilotProfile(("4", "4", "--shapes", "2", "--keys", "2", "--locks", "2", "--prob-goal", "0.5"), {"x": 4, "y": 4}),
        PilotProfile(("5", "5", "--shapes", "2", "--keys", "3", "--locks", "3", "--prob-goal", "0.6"), {"x": 5, "y": 5}),
    ),
    "gripper": (
        PilotProfile(("-n", "2"), {"balls": 2}),
        PilotProfile(("-n", "3"), {"balls": 3}),
        PilotProfile(("-n", "5"), {"balls": 5}),
    ),
    "logistics": (
        PilotProfile(("-a", "1", "-c", "1", "-s", "2", "-p", "1", "-t", "1"), {"packages": 1}),
        PilotProfile(("-a", "1", "-c", "2", "-s", "2", "-p", "2", "-t", "2"), {"packages": 2}),
        PilotProfile(("-a", "1", "-c", "2", "-s", "3", "-p", "3", "-t", "2"), {"packages": 3}),
    ),
    "snake": (
        PilotProfile(("empty-6x6", "2", "1", "0"), {"spawn_apples": 0}),
        PilotProfile(("empty-6x6", "2", "1", "1"), {"spawn_apples": 1}),
        PilotProfile(("empty-6x6", "2", "1", "2"), {"spawn_apples": 2}),
    ),
    "sokoban": (
        PilotProfile(("-n", "3", "-b", "1", "-w", "0"), {"grid_size": 3}),
        PilotProfile(("-n", "4", "-b", "1", "-w", "0"), {"grid_size": 4}),
        PilotProfile(("-n", "5", "-b", "1", "-w", "0"), {"grid_size": 5}),
    ),
    "storage": (
        PilotProfile((), {"variant_start": 0}),
        PilotProfile((), {"variant_start": 6}),
        PilotProfile((), {"variant_start": 12}),
    ),
    "towers_of_hanoi": (
        PilotProfile(("-n", "3"), {"discs": 3}),
        PilotProfile(("-n", "4"), {"discs": 4}),
        PilotProfile(("-n", "6"), {"discs": 6}),
    ),
    "visitall": (
        PilotProfile(("-n", "2", "-r", "0.5", "-u", "0"), {"grid_size": 2}),
        PilotProfile(("-n", "3", "-r", "0.5", "-u", "0"), {"grid_size": 3}),
        PilotProfile(("-n", "4", "-r", "0.75", "-u", "0"), {"grid_size": 4}),
    ),
}


def expansion_band(expansion_count: int) -> str | None:
    if isinstance(expansion_count, bool) or not isinstance(expansion_count, int):
        raise TypeError("expansion_count must be an integer")
    for band, (lower, upper) in BAND_BOUNDS.items():
        if lower <= expansion_count <= upper:
            return band
    return None


def selection_key(normalized_problem_hash: str, *, seed: int = SELECTION_SEED) -> str:
    return hashlib.sha256(f"{seed}:{normalized_problem_hash}".encode("ascii")).hexdigest()


def select_qualified_tasks(candidates: Iterable[QualifiedCandidate]) -> dict[tuple[str, str, str], QualifiedCandidate]:
    grouped: dict[tuple[str, str, str], list[QualifiedCandidate]] = {}
    for candidate in candidates:
        if candidate.split not in SPLITS:
            raise ValueError("BFS pilot candidates may only use train or dev")
        grouped.setdefault((candidate.domain_id, candidate.band, candidate.split), []).append(candidate)
    return {
        cell: min(rows, key=lambda row: (row.selection_key, row.normalized_problem_hash, row.candidate_id))
        for cell, rows in grouped.items()
    }


def exact_fifo_bfs(domain_pddl: str, problem_pddl: str, *, max_expansions: int = 1024) -> ExactBFSResult:
    authority = PDDLStateAuthority.from_pddl(domain_pddl, problem_pddl)
    start = authority.initial_state
    if authority.is_goal(start):
        return ExactBFSResult(0, True, (), _sha256(b""))

    frontier = deque([start])
    visited = {start.state_id}
    parents: dict[str, tuple[str, str]] = {}
    trace = hashlib.sha256()
    expansion_count = 0
    while frontier and expansion_count < max_expansions:
        state = frontier.popleft()
        if authority.is_goal(state):
            return ExactBFSResult(expansion_count, True, _reconstruct_plan(state.state_id, parents), trace.hexdigest())
        enqueued: list[str] = []
        for action in authority.applicable_actions(state):
            target = authority.apply(state, action).target_state
            if target.state_id in visited:
                continue
            visited.add(target.state_id)
            parents[target.state_id] = (state.state_id, action.serialize())
            frontier.append(target)
            enqueued.append(target.state_id)
        trace.update(_canonical_bytes({"expanded_state_id": state.state_id, "enqueued_state_ids": enqueued}))
        expansion_count += 1
    if frontier and authority.is_goal(frontier[0]):
        state = frontier[0]
        return ExactBFSResult(expansion_count, True, _reconstruct_plan(state.state_id, parents), trace.hexdigest())
    return ExactBFSResult(expansion_count, False, (), trace.hexdigest())


def replay_exact_fifo_bfs(candidate: QualifiedCandidate) -> bool:
    return exact_fifo_bfs(candidate.authority_domain_pddl, candidate.authority_problem_pddl) == candidate.result


def run_qualification(output_root: str | Path, *, repo_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()
    destination = Path(output_root).resolve()
    if destination.exists():
        raise FileExistsError(f"BFS pilot qualification root already exists: {destination}")
    config = load_curriculum_config(root / _CURRICULUM_CONFIG)
    registry = build_domain_registry(config)
    if tuple(registry) != DOMAINS:
        raise ValueError("BFS pilot domain registry differs from the governed 15-domain order")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    candidate_rows: list[dict[str, Any]] = []
    qualified: list[QualifiedCandidate] = []
    inspected: dict[str, dict[str, int]] = {domain: {split: 0 for split in SPLITS} for domain in DOMAINS}
    try:
        with tempfile.TemporaryDirectory(prefix="bfs-pilot-candidates-") as temporary:
            work_root = Path(temporary)
            for domain_id in DOMAINS:
                adapter = _pilot_adapter(domain_id, registry[domain_id])
                for split in SPLITS:
                    selected: dict[tuple[str, str, str], QualifiedCandidate] = {}
                    candidate_index = 0
                    for tier_index, quota in enumerate(_TIER_QUOTAS):
                        tier = BANDS[tier_index]
                        for tier_attempt in range(quota):
                            candidate = _generate_and_qualify(
                                adapter=adapter,
                                domain_id=domain_id,
                                split=split,
                                tier=tier,
                                tier_index=tier_index,
                                tier_attempt=tier_attempt,
                                candidate_index=candidate_index,
                                work_root=work_root,
                            )
                            candidate_index += 1
                            inspected[domain_id][split] = candidate_index
                            if isinstance(candidate, QualifiedCandidate):
                                qualified.append(candidate)
                                selected = select_qualified_tasks(
                                    item for item in qualified if item.domain_id == domain_id and item.split == split
                                )
                                candidate_rows.append(_candidate_row(candidate, "qualified"))
                            else:
                                candidate_rows.append(candidate)
                            if all((domain_id, band, split) in selected for band in BANDS):
                                break
                        if all((domain_id, band, split) in selected for band in BANDS):
                            break
                    if candidate_index > CANDIDATE_CEILING:
                        raise AssertionError("candidate ceiling exceeded")

        selection = select_qualified_tasks(qualified)
        required = {(domain, band, split) for domain in DOMAINS for band in BANDS for split in SPLITS}
        missing = sorted(required - set(selection))
        outcome = "PASS" if not missing else "VALID_STOP"
        selected_rows = _publish_selected(staging, selection) if not missing else []
        _write(staging / "candidates.jsonl", _jsonl(candidate_rows))
        _write(staging / "selected-manifest.jsonl", _jsonl(selected_rows))
        report = {
            "bands": {band: {"lower": lower, "upper": upper} for band, (lower, upper) in BAND_BOUNDS.items()},
            "candidate_ceiling_per_domain_split": CANDIDATE_CEILING,
            "inspected_counts": inspected,
            "missing_cells": [list(cell) for cell in missing],
            "outcome": outcome,
            "phase_id": PHASE_ID,
            "schema_version": SCHEMA_VERSION,
            "selected_count": len(selected_rows),
            "selection_seed": SELECTION_SEED,
            "test_data_accessed": False,
        }
        report_bytes = _canonical_bytes(report)
        _write(staging / "qualification-report.json", report_bytes)
        receipt = {
            "outcome": outcome,
            "phase_id": PHASE_ID,
            "qualification_report_sha256": _sha256(report_bytes),
            "schema_version": "bfs_pilot_gate_receipt_v1",
            "selected_manifest_sha256": _sha256(_jsonl(selected_rows)),
            "scientific_completion": False,
        }
        _write(staging / "gate-receipt.json", _canonical_bytes(receipt))
        staging.replace(destination)
        return {**report, "output_root": str(destination)}
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _generate_and_qualify(
    *,
    adapter: CurriculumCommandAdapter,
    domain_id: str,
    split: str,
    tier: str,
    tier_index: int,
    tier_attempt: int,
    candidate_index: int,
    work_root: Path,
) -> QualifiedCandidate | dict[str, Any]:
    candidate_id = f"{domain_id}-{split}-pilot-{candidate_index:06d}"
    seed = _candidate_seed(domain_id, split, candidate_index) if adapter.supports_seed() else None
    spec = GenerationSpec(
        candidate_id=candidate_id,
        output_dir=work_root / domain_id / split / candidate_id,
        timeout_seconds=30,
        seed=seed,
        extra={
            "attempt_index": candidate_index,
            "bucket_attempt_index": tier_attempt,
            "preset_id": tier,
            "split": split,
        },
    )
    raw = adapter.generate_candidate(spec)
    normalized = adapter.normalize_outputs(raw)
    if isinstance(normalized, GeneratorRejection):
        return _rejection_row(candidate_id, domain_id, split, tier, seed, normalized.rejection_reason)
    domain_pddl = normalized.domain_path.read_text(encoding="utf-8")
    problem_pddl = normalized.problem_path.read_text(encoding="utf-8")
    authority_domain, authority_problem, transformations = _normalize_authority_input(domain_pddl, problem_pddl)
    normalized_hash = _sha256(normalize_pddl(problem_pddl).encode("utf-8"))
    try:
        result = exact_fifo_bfs(authority_domain, authority_problem)
    except Exception as error:
        return _rejection_row(candidate_id, domain_id, split, tier, seed, f"authority_error:{type(error).__name__}")
    band = expansion_band(result.expansion_count)
    if result.expansion_count == 0:
        return _rejection_row(candidate_id, domain_id, split, tier, seed, "trivial_goal")
    if not result.goal_reached or band is None:
        return _rejection_row(candidate_id, domain_id, split, tier, seed, "over_budget_or_unsolved")
    return QualifiedCandidate(
        candidate_id=candidate_id,
        domain_id=domain_id,
        split=split,
        size_tier=tier,
        seed=seed,
        normalized_problem_hash=normalized_hash,
        domain_pddl=domain_pddl,
        problem_pddl=problem_pddl,
        authority_domain_pddl=authority_domain,
        authority_problem_pddl=authority_problem,
        authority_transformations=transformations,
        result=result,
    )


def _pilot_adapter(domain_id: str, base: CurriculumCommandAdapter) -> CurriculumCommandAdapter:
    metadata = replace(
        base.metadata,
        target_parameter_presets=tuple(
            TargetParameterPreset(tier, profile.arguments, dict(profile.parameters), "issue-111 BFS pilot size tier")
            for tier, profile in zip(BANDS, _PROFILES[domain_id], strict=True)
        ),
    )
    selection = DomainSelection(domain_id, base.generator_domain_id, base.generator_dir)
    if domain_id in {"gripper", "towers_of_hanoi"}:
        builder = _named_variant_builder(domain_id, metadata)
    else:
        builder = ADAPTER_TEMPLATES[domain_id].command_builder_factory(selection, metadata)
    return CurriculumCommandAdapter(
        adapter_id=domain_id,
        generator_domain_id=base.generator_domain_id,
        generator_dir=base.generator_dir,
        metadata=metadata,
        command_builder=builder,
    )


def _named_variant_builder(domain_id: str, metadata: Any):
    executable = str(Path(metadata.generator_path))
    transform = _gripper_named_variant if domain_id == "gripper" else _hanoi_named_variant
    sizes = {tier: int(_PROFILES[domain_id][index].arguments[-1]) for index, tier in enumerate(BANDS)}

    def build(spec: GenerationSpec) -> PreparedCommand:
        tier = str(spec.extra["preset_id"])
        size = sizes[tier]
        split_offset = SPLITS.index(str(spec.extra["split"]))
        variant_index = (int(spec.extra["bucket_attempt_index"]) * len(SPLITS)) + split_offset
        return PreparedCommand(
            command=(executable, "-n", str(size)),
            stdout_transform=lambda text: transform(text, size, variant_index),
        )

    return build


def _publish_selected(
    staging: Path, selection: Mapping[tuple[str, str, str], QualifiedCandidate]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    identities: dict[str, str] = {}
    for (domain_id, band, split), candidate in sorted(selection.items()):
        if not replay_exact_fifo_bfs(candidate):
            raise ValueError(f"exact FIFO replay failed: {candidate.candidate_id}")
        relative_root = Path("tasks") / domain_id / split / band
        domain_path = staging / relative_root / "domain.pddl"
        problem_path = staging / relative_root / "problem.pddl"
        _write(domain_path, candidate.domain_pddl.encode("utf-8"))
        _write(problem_path, candidate.problem_pddl.encode("utf-8"))
        identity = whole_instance_identity(candidate.domain_pddl, candidate.problem_pddl)
        prior = identities.get(identity)
        if prior is not None and prior != split:
            raise ValueError("whole-instance split isolation failed")
        identities[identity] = split
        instance_id = f"{domain_id}-{split}-{band}-0000"
        rows.append(
            {
                "authority_transformations": list(candidate.authority_transformations),
                "band": band,
                "candidate_id": candidate.candidate_id,
                "domain_hash": _sha256(candidate.domain_pddl.encode("utf-8")),
                "domain_id": domain_id,
                "domain_path": (relative_root / "domain.pddl").as_posix(),
                "expansion_count": candidate.result.expansion_count,
                "fifo_trace_sha256": candidate.result.trace_sha256,
                "instance_id": instance_id,
                "normalized_problem_hash": candidate.normalized_problem_hash,
                "plan": list(candidate.result.plan),
                "problem_hash": _sha256(candidate.problem_pddl.encode("utf-8")),
                "problem_path": (relative_root / "problem.pddl").as_posix(),
                "seed": candidate.seed,
                "selection_key": candidate.selection_key,
                "split": split,
                "split_assignment_id": split_assignment_id(identity, split),
                "status": "accepted",
                "whole_instance_id": identity,
            }
        )
    return rows


def _candidate_row(candidate: QualifiedCandidate, status: str) -> dict[str, Any]:
    return {
        "assigned_band": candidate.band,
        "candidate_id": candidate.candidate_id,
        "domain_id": candidate.domain_id,
        "expansion_count": candidate.result.expansion_count,
        "normalized_problem_hash": candidate.normalized_problem_hash,
        "seed": candidate.seed,
        "size_tier": candidate.size_tier,
        "split": candidate.split,
        "status": status,
    }


def _rejection_row(
    candidate_id: str, domain_id: str, split: str, tier: str, seed: int | None, reason: str
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "domain_id": domain_id,
        "reason": reason,
        "seed": seed,
        "size_tier": tier,
        "split": split,
        "status": "rejected",
    }


def _candidate_seed(domain_id: str, split: str, candidate_index: int) -> int:
    payload = f"{SELECTION_SEED}:{domain_id}:{split}:{candidate_index}".encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big") & 0x7FFFFFFF


def _reconstruct_plan(goal_state_id: str, parents: Mapping[str, tuple[str, str]]) -> tuple[str, ...]:
    actions: list[str] = []
    current = goal_state_id
    while current in parents:
        current, action = parents[current]
        actions.append(action)
    actions.reverse()
    return tuple(actions)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _jsonl(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(row) + b"\n" for row in rows)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


__all__ = [
    "BANDS",
    "BAND_BOUNDS",
    "CANDIDATE_CEILING",
    "DOMAINS",
    "SPLITS",
    "ExactBFSResult",
    "QualifiedCandidate",
    "exact_fifo_bfs",
    "expansion_band",
    "replay_exact_fifo_bfs",
    "run_qualification",
    "select_qualified_tasks",
    "selection_key",
]
