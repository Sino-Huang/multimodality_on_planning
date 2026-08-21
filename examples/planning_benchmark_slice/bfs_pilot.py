"""Expansion-qualified candidate gate for the issue-111 BFS pilot."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections import deque
from dataclasses import dataclass, replace
from functools import lru_cache
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
    _sokoban_template_problem,
    build_domain_registry,
)
from src.data_collect.config import load_curriculum_config
from src.data_collect.normalization import normalize_pddl
from src.data_collect.splits import whole_instance_identity

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
SCHEMA_VERSION = "bfs_pilot_qualification_v3"
GATE_RECEIPT_SCHEMA_VERSION = "bfs_pilot_gate_receipt_v3"
PHASE_ID = "issue-111-bfs-expansion-qualified-pilot-v3"
ATTEMPT_ID = "qualification-attempt-002"
_TIER_QUOTAS = (32, 64, 404)
_CURRICULUM_CONFIG = Path("src/data_collect/configs/curriculum_15_domains.yaml")
_PUBLISHED_ROOT = Path("data/bfs_pilot_v3")


@dataclass(frozen=True, slots=True)
class ExactBFSResult:
    expansion_count: int
    goal_reached: bool
    plan: tuple[str, ...]
    expanded_state_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QualifiedCandidate:
    candidate_id: str
    domain_id: str
    split: str
    size_tier: str
    seed: int | None
    normalized_problem: str
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
    def whole_instance_id(self) -> str:
        return whole_instance_identity(self.domain_pddl, self.problem_pddl)


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
        PilotProfile(("-f", "6", "-p", "3"), {"floors": 6, "passengers": 3}),
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
        PilotProfile(("-n", "5", "-b", "1", "-w", "0"), {"grid_size": 5}),
        PilotProfile(("-n", "5", "-b", "1", "-w", "0"), {"grid_size": 5}),
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


def select_qualified_tasks(candidates: Iterable[QualifiedCandidate]) -> dict[tuple[str, str, str], QualifiedCandidate]:
    grouped: dict[tuple[str, str], dict[str, list[QualifiedCandidate]]] = {}
    for candidate in candidates:
        if candidate.split not in SPLITS:
            raise ValueError("BFS pilot candidates may only use train or dev")
        grouped.setdefault((candidate.domain_id, candidate.band), {split: [] for split in SPLITS})[
            candidate.split
        ].append(candidate)

    selected: dict[tuple[str, str, str], QualifiedCandidate] = {}
    for (domain_id, band), by_split in grouped.items():
        pairs = (
            (train, dev)
            for train in by_split["train"]
            for dev in by_split["dev"]
            if train.whole_instance_id != dev.whole_instance_id
        )
        try:
            train, dev = min(
                pairs,
                key=lambda pair: (_candidate_order(pair[0]), _candidate_order(pair[1])),
            )
        except ValueError:
            continue
        selected[(domain_id, band, "train")] = train
        selected[(domain_id, band, "dev")] = dev
    return selected


def exact_fifo_bfs(domain_pddl: str, problem_pddl: str, *, max_expansions: int = 1024) -> ExactBFSResult:
    authority = PDDLStateAuthority.from_pddl(domain_pddl, problem_pddl)
    start = authority.initial_state
    if authority.is_goal(start):
        return ExactBFSResult(0, True, (), ())

    frontier = deque([start])
    visited = {start.state_id}
    parents: dict[str, tuple[str, str]] = {}
    expanded_state_ids: list[str] = []
    expansion_count = 0
    while frontier and expansion_count < max_expansions:
        state = frontier.popleft()
        if authority.is_goal(state):
            return ExactBFSResult(
                expansion_count,
                True,
                _reconstruct_plan(state.state_id, parents),
                tuple(expanded_state_ids),
            )
        enqueued: list[str] = []
        for action in authority.applicable_actions(state):
            target = authority.apply(state, action).target_state
            if target.state_id in visited:
                continue
            visited.add(target.state_id)
            parents[target.state_id] = (state.state_id, action.serialize())
            frontier.append(target)
            enqueued.append(target.state_id)
        expanded_state_ids.append(state.state_id)
        expansion_count += 1
    if frontier and authority.is_goal(frontier[0]):
        state = frontier[0]
        return ExactBFSResult(
            expansion_count,
            True,
            _reconstruct_plan(state.state_id, parents),
            tuple(expanded_state_ids),
        )
    return ExactBFSResult(expansion_count, False, (), tuple(expanded_state_ids))


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
                candidate_indices = {split: 0 for split in SPLITS}
                domain_required = {(domain_id, band, split) for band in BANDS for split in SPLITS}
                domain_selected: dict[tuple[str, str, str], QualifiedCandidate] = {}
                for tier_index, quota in enumerate(_TIER_QUOTAS):
                    tier = BANDS[tier_index]
                    for tier_attempt in range(quota):
                        for split in SPLITS:
                            candidate_index = candidate_indices[split]
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
                            candidate_indices[split] += 1
                            inspected[domain_id][split] = candidate_indices[split]
                            if isinstance(candidate, QualifiedCandidate):
                                qualified.append(candidate)
                                candidate_rows.append(_candidate_row(candidate, "qualified"))
                            else:
                                candidate_rows.append(candidate)
                        domain_selected = select_qualified_tasks(
                            item for item in qualified if item.domain_id == domain_id
                        )
                        if domain_required <= set(domain_selected):
                            break
                    if domain_required <= set(domain_selected):
                        break
                if any(count > CANDIDATE_CEILING for count in candidate_indices.values()):
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
            "attempt_id": ATTEMPT_ID,
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
            "attempt_id": ATTEMPT_ID,
            "phase_id": PHASE_ID,
            "schema_version": GATE_RECEIPT_SCHEMA_VERSION,
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
    normalized_problem = normalize_pddl(problem_pddl)
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
        normalized_problem=normalized_problem,
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
    if domain_id == "15puzzle":
        builder = _npuzzle_builder(metadata)
    elif domain_id == "sokoban":
        builder = _sokoban_builder(metadata)
    elif domain_id in {"gripper", "towers_of_hanoi"}:
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


def _npuzzle_builder(metadata: Any):
    executable = str(Path(metadata.generator_path))

    def build(spec: GenerationSpec) -> PreparedCommand:
        tier = str(spec.extra["preset_id"])
        split = str(spec.extra["split"])
        attempt = int(spec.extra["bucket_attempt_index"])
        size = 2 if tier == "easy" else 3
        depth_range = {"easy": (1, 5), "medium": (7, 8), "hard": (9, 10)}[tier]
        states = _partitioned_npuzzle_states(size, depth_range, split)
        state = states[attempt % len(states)]
        command = [executable, "-n", str(size)]
        if spec.seed is not None:
            command.extend(["-s", str(spec.seed)])
        return PreparedCommand(
            command=tuple(command),
            stdout_transform=lambda _text: _npuzzle_problem(size, state, split=split, tier=tier, attempt=attempt),
        )

    return build


def _sokoban_builder(metadata: Any):
    executable = str(Path(metadata.generator_path))

    def build(spec: GenerationSpec) -> PreparedCommand:
        tier = str(spec.extra["preset_id"])
        split = str(spec.extra["split"])
        attempt = int(spec.extra["bucket_attempt_index"])
        command = [executable, "-n", "5", "-b", "1", "-w", "0"]
        if spec.seed is not None:
            command.extend(["-s", str(spec.seed)])
        if tier == "easy":

            def transform(_text: str) -> str:
                return _easy_sokoban_problem(split, attempt)
        else:
            variant_index = (SPLITS.index(split) * 10_000) + (BANDS.index(tier) * 3_000) + attempt

            def transform(text: str) -> str:
                return _sokoban_template_problem(text, variant_index=variant_index)

        return PreparedCommand(command=tuple(command), stdout_transform=transform)

    return build


@lru_cache(maxsize=None)
def _partitioned_npuzzle_states(
    size: int,
    depth_range: tuple[int, int],
    split: str,
) -> tuple[tuple[int, ...], ...]:
    goal = tuple((*range(1, size * size), 0))
    frontier = deque([(goal, 0)])
    visited = {goal}
    matching: list[tuple[int, ...]] = []
    while frontier:
        state, depth = frontier.popleft()
        if depth_range[0] <= depth <= depth_range[1]:
            matching.append(state)
        if depth >= depth_range[1]:
            continue
        blank = state.index(0)
        row, column = divmod(blank, size)
        for delta_row, delta_column in ((-1, 0), (0, -1), (0, 1), (1, 0)):
            target_row = row + delta_row
            target_column = column + delta_column
            if not (0 <= target_row < size and 0 <= target_column < size):
                continue
            target = target_row * size + target_column
            successor = list(state)
            successor[blank], successor[target] = successor[target], successor[blank]
            value = tuple(successor)
            if value not in visited:
                visited.add(value)
                frontier.append((value, depth + 1))
    partition = tuple(
        state for index, state in enumerate(sorted(matching)) if index % len(SPLITS) == SPLITS.index(split)
    )
    if not partition:
        raise ValueError("N-puzzle split partition is empty")
    return partition


def _npuzzle_problem(
    size: int,
    state: tuple[int, ...],
    *,
    split: str,
    tier: str,
    attempt: int,
) -> str:
    positions = [f"p_{row}_{column}" for row in range(1, size + 1) for column in range(1, size + 1)]
    tiles = [f"t_{value}" for value in range(1, size * size)]
    initial = [
        f"    ({'empty' if value == 0 else 'at'} {' ' if value == 0 else f't_{value} '}{positions[index]})"
        for index, value in enumerate(state)
    ]
    neighbors: list[str] = []
    for row in range(size):
        for column in range(size):
            source = f"p_{row + 1}_{column + 1}"
            for delta_row, delta_column in ((-1, 0), (0, -1), (0, 1), (1, 0)):
                target_row = row + delta_row
                target_column = column + delta_column
                if 0 <= target_row < size and 0 <= target_column < size:
                    neighbors.append(f"    (neighbor {source} p_{target_row + 1}_{target_column + 1})")
    goal = [f"    (at t_{value} {positions[value - 1]})" for value in range(1, size * size)]
    return (
        f"(define (problem n-puzzle-{size}-{split}-{tier}-{attempt})\n"
        "  (:domain n-puzzle-typed)\n"
        f"  (:objects {' '.join(positions)} - position {' '.join(tiles)} - tile)\n"
        "  (:init\n" + "\n".join((*initial, *neighbors)) + "\n  )\n  (:goal (and\n" + "\n".join(goal) + "\n  ))\n)\n"
    )


def _easy_sokoban_problem(split: str, attempt: int) -> str:
    layouts = {
        "train": (((3, 1), (3, 2), (3, 3)), ((1, 2), (2, 2), (4, 2))),
        "dev": (((3, 5), (3, 4), (3, 3)), ((5, 4), (4, 4), (2, 4))),
    }
    player, box, button = layouts[split][attempt % 2]
    positions = [f"pos{row}_{column}" for row in range(1, 6) for column in range(1, 6)]
    directions: list[str] = []
    for row in range(1, 6):
        for column in range(1, 6):
            source = f"pos{row}_{column}"
            for name, delta_row, delta_column in (
                ("up", -1, 0),
                ("down", 1, 0),
                ("left", 0, -1),
                ("right", 0, 1),
            ):
                target_row = row + delta_row
                target_column = column + delta_column
                if 1 <= target_row <= 5 and 1 <= target_column <= 5:
                    directions.append(f"        ({name} {source} pos{target_row}_{target_column})")
    return (
        f"(define (problem sokoban-easy-{split}-{attempt})\n"
        "    (:domain template)\n"
        "    (:objects\n"
        f"        {' '.join(positions)} - pos\n"
        "        ply1 - player\n"
        "        blk1 - block\n"
        "        but1 - button\n"
        "    )\n"
        "    (:init\n"
        + "\n".join(f"        (position {position})" for position in positions)
        + "\n"
        + "\n".join(directions)
        + f"\n        (at ply1 pos{player[0]}_{player[1]})"
        + f"\n        (at blk1 pos{box[0]}_{box[1]})"
        + f"\n        (at but1 pos{button[0]}_{button[1]})"
        + "\n    )\n"
        "    (:goal (exists (?pos - pos) (and (at but1 ?pos) (at blk1 ?pos))))\n"
        ")\n"
    )


def _candidate_order(candidate: QualifiedCandidate) -> tuple[str, str]:
    return candidate.normalized_problem, candidate.candidate_id


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
                "bucket": band,
                "candidate_id": candidate.candidate_id,
                "domain_id": domain_id,
                "domain_path": (_PUBLISHED_ROOT / relative_root / "domain.pddl").as_posix(),
                "expansion_count": candidate.result.expansion_count,
                "instance_id": instance_id,
                "plan": list(candidate.result.plan),
                "problem_path": (_PUBLISHED_ROOT / relative_root / "problem.pddl").as_posix(),
                "seed": candidate.seed,
                "split": split,
                "status": "accepted",
            }
        )
    return rows


def _candidate_row(candidate: QualifiedCandidate, status: str) -> dict[str, Any]:
    return {
        "assigned_band": candidate.band,
        "candidate_id": candidate.candidate_id,
        "domain_id": candidate.domain_id,
        "expansion_count": candidate.result.expansion_count,
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
    return (
        SELECTION_SEED
        + DOMAINS.index(domain_id) * len(SPLITS) * CANDIDATE_CEILING
        + SPLITS.index(split) * CANDIDATE_CEILING
        + candidate_index
    )


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
]
