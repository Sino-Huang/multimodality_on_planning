from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Final, Literal, Sequence

from .cgas_candidate_characterization_models import JsonObject, JsonValue

Harvest = Literal["on_plan", "off_plan"]


@dataclass(frozen=True, slots=True)
class PilotScopeError(ValueError):
    code: str

    def __str__(self) -> str:
        return self.code


OBJECT_COUNTS: Final = (4, 8, 12)
INVARIANT_FAMILIES: Final = 7
HELD_OUT_FRACTION: Final = 79 / 481
FAILURE_RATES: Final = (0.4, 0.6)
STABILITY_BARS: Final = (10, 30)


@dataclass(frozen=True, slots=True)
class YieldSummary:
    total: int
    mean: float


@dataclass(frozen=True, slots=True)
class DistributionSummary:
    mean: float
    median: float
    maximum: int
    histogram: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class ObjectDiversity:
    object_count: int
    candidates: int
    composition_signatures: int
    repeated_composition_signatures: int
    structural_profiles: int
    goal_edge_levels: int
    mean_on_plan_rows: float
    mean_off_plan_rows: float


@dataclass(frozen=True, slots=True)
class DiversityFloor:
    min_instances_per_object_count: int
    min_repeated_composition_signatures_per_object_count: int
    min_instances_per_repeated_signature: int
    min_structural_profiles_per_object_count: int
    min_goal_edge_levels_per_object_count: int
    passed: bool
    failed_object_counts: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SizingAlternative:
    bar: int
    failure_rate: float
    harvest: Harvest
    raw_instances_by_object_count: tuple[tuple[int, int], ...]
    pilot_instances_by_object_count: tuple[tuple[int, int], ...]
    raw_instance_count: int
    pilot_instance_count: int
    candidate_pool_feasible: bool


@dataclass(frozen=True, slots=True)
class Recommendation:
    proposed_stability_bar: int
    stability_bar: Literal["owner_decision_required"]
    proposed_diversity_floor_instances: int
    pool_feasible_on_plan: bool
    pool_feasible_off_plan: bool


@dataclass(frozen=True, slots=True)
class PilotScopeReport:
    characterized_candidate_count: int
    paired_exact_count: int
    object_count_counts: tuple[tuple[int, int], ...]
    composition_signature_counts: tuple[tuple[int, int], ...]
    structural_profile_counts: tuple[tuple[int, int], ...]
    goal_edge_level_counts: tuple[tuple[int, int], ...]
    per_object_count: tuple[ObjectDiversity, ...]
    plan_length: DistributionSummary
    on_plan_certificate_rows: YieldSummary
    off_plan_certificate_rows: YieldSummary
    off_plan_only_certificate_rows: YieldSummary
    diversity_floor: DiversityFloor
    sizing: tuple[SizingAlternative, ...]
    recommendation: Recommendation


@dataclass(frozen=True, slots=True)
class _Candidate:
    object_count: int
    composition_signature: str
    structural_profile: tuple[int, ...]
    goal_edges: int
    bfs_plan_length: int
    bfs_expansions: int
    iw_plan_length: int
    iw_expansions: int


def analyze_rows(rows: Sequence[JsonObject]) -> PilotScopeReport:
    candidates = tuple(_candidate(row) for row in rows if _paired_exact(row))
    if not candidates:
        raise PilotScopeError("paired_exact_pool_empty")
    object_summaries = tuple(_object_diversity(candidates, count) for count in OBJECT_COUNTS)
    plans = tuple(candidate.bfs_plan_length for candidate in candidates)
    on_plan = tuple(candidate.bfs_plan_length + candidate.iw_plan_length for candidate in candidates)
    off_plan = tuple(candidate.bfs_expansions + candidate.iw_expansions for candidate in candidates)
    off_plan_only = tuple(
        max(candidate.bfs_expansions - candidate.bfs_plan_length, 0)
        + max(candidate.iw_expansions - candidate.iw_plan_length, 0)
        for candidate in candidates
    )
    floor = _diversity_floor(object_summaries)
    sizing = _sizing(object_summaries, floor)
    return PilotScopeReport(
        characterized_candidate_count=len(rows),
        paired_exact_count=len(candidates),
        object_count_counts=tuple((item.object_count, item.candidates) for item in object_summaries),
        composition_signature_counts=tuple(
            (item.object_count, item.composition_signatures) for item in object_summaries
        ),
        structural_profile_counts=tuple((item.object_count, item.structural_profiles) for item in object_summaries),
        goal_edge_level_counts=tuple((item.object_count, item.goal_edge_levels) for item in object_summaries),
        per_object_count=object_summaries,
        plan_length=_distribution(plans),
        on_plan_certificate_rows=_yield(on_plan),
        off_plan_certificate_rows=_yield(off_plan),
        off_plan_only_certificate_rows=_yield(off_plan_only),
        diversity_floor=floor,
        sizing=sizing,
        recommendation=Recommendation(
            proposed_stability_bar=10,
            stability_bar="owner_decision_required",
            proposed_diversity_floor_instances=30 * len(OBJECT_COUNTS),
            pool_feasible_on_plan=any(item.candidate_pool_feasible for item in sizing if item.harvest == "on_plan"),
            pool_feasible_off_plan=all(item.candidate_pool_feasible for item in sizing if item.harvest == "off_plan"),
        ),
    )


def _object_diversity(candidates: Sequence[_Candidate], object_count: int) -> ObjectDiversity:
    members = tuple(candidate for candidate in candidates if candidate.object_count == object_count)
    signatures = Counter(candidate.composition_signature for candidate in members)
    return ObjectDiversity(
        object_count=object_count,
        candidates=len(members),
        composition_signatures=len(signatures),
        repeated_composition_signatures=sum(count >= 2 for count in signatures.values()),
        structural_profiles=len({candidate.structural_profile for candidate in members}),
        goal_edge_levels=len({candidate.goal_edges for candidate in members}),
        mean_on_plan_rows=_mean(tuple(candidate.bfs_plan_length + candidate.iw_plan_length for candidate in members)),
        mean_off_plan_rows=_mean(tuple(candidate.bfs_expansions + candidate.iw_expansions for candidate in members)),
    )


def _diversity_floor(summaries: Sequence[ObjectDiversity]) -> DiversityFloor:
    failed = tuple(
        item.object_count
        for item in summaries
        if item.candidates < 30
        or item.repeated_composition_signatures < 5
        or item.structural_profiles < 3
        or item.goal_edge_levels < 3
    )
    return DiversityFloor(30, 5, 2, 3, 3, not failed, failed)


def _sizing(summaries: Sequence[ObjectDiversity], floor: DiversityFloor) -> tuple[SizingAlternative, ...]:
    alternatives: list[SizingAlternative] = []
    for bar in STABILITY_BARS:
        for failure_rate in FAILURE_RATES:
            rows_per_object_count = INVARIANT_FAMILIES * bar / failure_rate / HELD_OUT_FRACTION
            for harvest in ("on_plan", "off_plan"):
                raw = tuple(
                    (
                        item.object_count,
                        _required_instances(
                            rows_per_object_count,
                            item.mean_on_plan_rows if harvest == "on_plan" else item.mean_off_plan_rows,
                        ),
                    )
                    for item in summaries
                )
                pilot = tuple((count, max(instances, 30)) for count, instances in raw)
                available = {item.object_count: item.candidates for item in summaries}
                feasible = floor.passed and all(available[count] >= instances for count, instances in pilot)
                alternatives.append(
                    SizingAlternative(
                        bar,
                        failure_rate,
                        harvest,
                        raw,
                        pilot,
                        sum(instances for _, instances in raw),
                        sum(instances for _, instances in pilot),
                        feasible,
                    )
                )
    return tuple(alternatives)


def _required_instances(rows: float, rows_per_instance: float) -> int:
    return math.ceil(rows / rows_per_instance) if rows_per_instance > 0 else 0


def _candidate(row: JsonObject) -> _Candidate:
    bfs = _mapping(row.get("bfs"), "bfs")
    bfs_exact = _mapping(bfs.get("exact_search"), "bfs.exact_search")
    iw = _mapping(row.get("iw_width_1"), "iw_width_1")
    iw_exact = _mapping(iw.get("exact_search"), "iw_width_1.exact_search")
    init = _mapping(row.get("init_descriptor"), "init_descriptor")
    goal = _mapping(row.get("goal_descriptor"), "goal_descriptor")
    profile = _integer_list(init.get("stack_heights"), "init_descriptor.stack_heights")
    return _Candidate(
        _integer(row.get("object_count"), "object_count"),
        _text(row.get("composition_signature"), "composition_signature"),
        profile,
        _integer(goal.get("on_edges"), "goal_descriptor.on_edges"),
        _integer(bfs_exact.get("plan_length"), "bfs.exact_search.plan_length"),
        _integer(bfs_exact.get("expansion_count"), "bfs.exact_search.expansion_count"),
        _integer(iw_exact.get("plan_length"), "iw_width_1.exact_search.plan_length"),
        _integer(iw_exact.get("expansion_count"), "iw_width_1.exact_search.expansion_count"),
    )


def _paired_exact(row: JsonObject) -> bool:
    if row.get("status") != "characterized":
        return False
    return all(_planner_exact(row.get(key)) for key in ("bfs", "iw_width_1"))


def _planner_exact(value: JsonValue | None) -> bool:
    planner = _mapping(value, "planner")
    exact = _mapping(planner.get("exact_search"), "exact_search")
    return exact.get("status") == "exact_solution_replayed"


def _distribution(values: Sequence[int]) -> DistributionSummary:
    return DistributionSummary(
        round(_mean(values), 6),
        float(statistics.median(values)),
        max(values),
        tuple(sorted(Counter(values).items())),
    )


def _yield(values: Sequence[int]) -> YieldSummary:
    return YieldSummary(sum(values), round(_mean(values), 6))


def _mean(values: Sequence[int]) -> float:
    return statistics.fmean(values) if values else 0.0


def _mapping(value: JsonValue | None, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise PilotScopeError(f"invalid_{label}")
    return value


def _integer(value: JsonValue | None, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PilotScopeError(f"invalid_{label}")
    return value


def _text(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PilotScopeError(f"invalid_{label}")
    return value


def _integer_list(value: JsonValue | None, label: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise PilotScopeError(f"invalid_{label}")
    return tuple(_integer(item, label) for item in value)
