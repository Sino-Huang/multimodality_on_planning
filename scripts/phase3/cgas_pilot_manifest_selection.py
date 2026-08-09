from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, Sequence

from .cgas_candidate_characterization_models import JsonObject, JsonValue
from .cgas_pilot_manifest_models import PilotDiversity, PilotRecord, PilotSelection

OBJECT_COUNTS: Final = (4, 8, 12)
INSTANCES_PER_OBJECT_COUNT: Final = 30
HELD_OUT_PER_OBJECT_COUNT: Final = 5
STABILITY_BAR: Final = 10
HARVEST: Final = "off_plan"
CERTIFICATE_FAMILIES: Final = (
    "frontier_head",
    "frontier_order_summary",
    "visited_delta",
    "expanded_state",
    "novelty_tuple",
    "seen_feature_delta",
    "width_decision",
)


@dataclass(frozen=True, slots=True)
class PilotManifestError(RuntimeError):
    code: str
    path: Path

    def __str__(self) -> str:
        return f"{self.code}:{self.path}"


def select_pilot_rows(rows: Sequence[JsonObject]) -> PilotSelection:
    eligible = tuple(row for row in rows if _paired_exact(row))
    if len({_text(row.get("candidate_id"), "candidate_id") for row in eligible}) != len(eligible):
        raise PilotManifestError("pilot_candidate_identity_duplicate", Path("selection"))
    if len({_source_digest(row) for row in eligible}) != len(eligible):
        raise PilotManifestError("pilot_source_identity_duplicate", Path("selection"))
    records: list[PilotRecord] = []
    diversity: list[PilotDiversity] = []
    for object_count in OBJECT_COUNTS:
        candidates = sorted(
            (row for row in eligible if _integer(row.get("object_count"), "object_count") == object_count),
            key=lambda row: (_integer(row.get("raw_rank"), "raw_rank"), _text(row.get("candidate_id"), "candidate_id")),
        )
        if len(candidates) < INSTANCES_PER_OBJECT_COUNT:
            raise PilotManifestError("pilot_object_count_capacity_unavailable", Path(str(object_count)))
        selected = tuple(candidates[:INSTANCES_PER_OBJECT_COUNT])
        held_out = _held_out_signatures(selected, object_count)
        records.extend(
            _record(row, "held_out_calibration" if _signature(row) in held_out else "train")
            for row in selected
        )
        diversity.append(_diversity(selected, object_count))
    ordered = tuple(
        sorted(
            records,
            key=lambda record: (
                record.object_count,
                0 if record.role == "train" else 1,
                record.raw_rank,
                record.candidate_id,
            ),
        )
    )
    _audit(ordered, tuple(diversity))
    return PilotSelection(ordered, tuple(diversity))


def build_row_budget(selection: PilotSelection, manifest_sha256: str) -> JsonObject:
    _digest(manifest_sha256, "manifest_sha256")
    role_counts = Counter(record.role for record in selection.records)
    by_object_count = Counter(record.object_count for record in selection.records)
    on_plan = sum(record.on_plan_row_capacity for record in selection.records)
    off_plan = sum(record.off_plan_row_capacity for record in selection.records)
    return {
        "available_rows": {
            "off_plan_only": off_plan - on_plan,
            "off_plan_total": off_plan,
            "on_plan_total": on_plan,
        },
        "certificate_families": list(CERTIFICATE_FAMILIES),
        "harvest": HARVEST,
        "held_out_fraction": {"denominator": 481, "numerator": 79},
        "manifest_sha256": manifest_sha256,
        "matrix": {
            "certificate_family_count": len(CERTIFICATE_FAMILIES),
            "minimum_failure_observations": len(CERTIFICATE_FAMILIES) * len(OBJECT_COUNTS) * STABILITY_BAR,
            "object_count_count": len(OBJECT_COUNTS),
            "total_cells": len(CERTIFICATE_FAMILIES) * len(OBJECT_COUNTS),
        },
        "object_count_instances": {str(key): value for key, value in sorted(by_object_count.items())},
        "role_order": ["train", "held_out_calibration"],
        "sampling_order": "object_count_then_role_then_raw_rank_then_candidate_id_then_trace_order",
        "schema_version": "cgas_phase3_pilot_row_budget_v1",
        "source_instances": {
            "held_out_calibration": role_counts["held_out_calibration"],
            "total": len(selection.records),
            "train": role_counts["train"],
        },
        "stability_bar": STABILITY_BAR,
        "stop_rule": "minimum_failure_observations_per_cell_or_exhaustion",
    }


def selection_record(selection: PilotSelection) -> JsonObject:
    return {
        "diversity": [asdict(item) for item in selection.diversity],
        "object_count_counts": {str(count): INSTANCES_PER_OBJECT_COUNT for count in OBJECT_COUNTS},
        "role_counts": {"held_out_calibration": 15, "train": 75},
    }


def pilot_config() -> JsonObject:
    return {
        "harvest": HARVEST,
        "held_out_fraction": {"denominator": 481, "numerator": 79},
        "held_out_per_object_count": HELD_OUT_PER_OBJECT_COUNT,
        "instances_per_object_count": INSTANCES_PER_OBJECT_COUNT,
        "object_counts": list(OBJECT_COUNTS),
        "selection_order": "raw_rank_then_candidate_id",
        "stability_bar": STABILITY_BAR,
    }


def records_json(selection: PilotSelection) -> list[JsonValue]:
    return [asdict(record) for record in selection.records]


def _held_out_signatures(rows: Sequence[JsonObject], object_count: int) -> frozenset[str]:
    groups: defaultdict[str, list[JsonObject]] = defaultdict(list)
    for row in rows:
        groups[_signature(row)].append(row)
    choices: dict[int, tuple[str, ...]] = {0: ()}
    for signature in sorted(groups, key=lambda value: hashlib.sha256(value.encode()).hexdigest()):
        size = len(groups[signature])
        for count, selected in tuple(sorted(choices.items(), reverse=True)):
            target = count + size
            if target <= HELD_OUT_PER_OBJECT_COUNT and target not in choices:
                choices[target] = (*selected, signature)
    if HELD_OUT_PER_OBJECT_COUNT not in choices:
        raise PilotManifestError("pilot_composition_isolated_split_unavailable", Path(str(object_count)))
    return frozenset(choices[HELD_OUT_PER_OBJECT_COUNT])


def _diversity(rows: Sequence[JsonObject], object_count: int) -> PilotDiversity:
    signatures = Counter(_signature(row) for row in rows)
    profiles = {
        _integer_tuple(_mapping(row.get("init_descriptor"), "init_descriptor").get("stack_heights"))
        for row in rows
    }
    goal_levels = {
        _integer(_mapping(row.get("goal_descriptor"), "goal_descriptor").get("on_edges"), "on_edges")
        for row in rows
    }
    return PilotDiversity(
        object_count,
        len(rows),
        sum(count >= 2 for count in signatures.values()),
        len(profiles),
        len(goal_levels),
    )


def _audit(records: tuple[PilotRecord, ...], diversity: tuple[PilotDiversity, ...]) -> None:
    roles = Counter(record.role for record in records)
    matrix = Counter((record.object_count, record.role) for record in records)
    if len(records) != 90 or len({record.instance_id for record in records}) != 90:
        raise PilotManifestError("pilot_selection_count_invalid", Path("selection"))
    if roles != Counter({"train": 75, "held_out_calibration": 15}):
        raise PilotManifestError("pilot_role_count_invalid", Path("selection"))
    expected = Counter({(count, "train"): 25 for count in OBJECT_COUNTS})
    expected.update({(count, "held_out_calibration"): 5 for count in OBJECT_COUNTS})
    if matrix != expected:
        raise PilotManifestError("pilot_role_matrix_invalid", Path("selection"))
    roles_by_signature: defaultdict[str, set[str]] = defaultdict(set)
    for record in records:
        roles_by_signature[record.composition_signature].add(record.role)
    if any(len(value) != 1 for value in roles_by_signature.values()):
        raise PilotManifestError("pilot_composition_role_overlap", Path("selection"))
    if any(
        item.instances != 30
        or item.repeated_composition_signatures < 5
        or item.stack_profiles < 3
        or item.goal_edge_levels < 3
        for item in diversity
    ):
        raise PilotManifestError("pilot_diversity_floor_unmet", Path("selection"))


def _record(row: JsonObject, role: str) -> PilotRecord:
    bfs = _mapping(row.get("bfs"), "bfs")
    iw = _mapping(row.get("iw_width_1"), "iw_width_1")
    bfs_exact = _mapping(bfs.get("exact_search"), "bfs_exact_search")
    iw_exact = _mapping(iw.get("exact_search"), "iw_exact_search")
    return PilotRecord(
        _digest_text(row.get("candidate_id"), "candidate_id"),
        _text(row.get("instance_id"), "instance_id"),
        _integer(row.get("raw_rank"), "raw_rank"),
        _integer(row.get("object_count"), "object_count"),
        _signature(row),
        _source_digest(row),
        _text(row.get("split"), "split"),
        _digest_text(row.get("domain_sha256"), "domain_sha256"),
        _digest_text(_mapping(bfs.get("trace_v3"), "bfs_trace").get("stream_sha256"), "bfs_trace_sha256"),
        _digest_text(_mapping(iw.get("trace_v3"), "iw_trace").get("stream_sha256"), "iw_trace_sha256"),
        _integer(bfs_exact.get("plan_length"), "bfs_plan_length")
        + _integer(iw_exact.get("plan_length"), "iw_plan_length"),
        _integer(bfs_exact.get("expansion_count"), "bfs_expansions")
        + _integer(iw_exact.get("expansion_count"), "iw_expansions"),
        role,
    )


def _paired_exact(row: JsonObject) -> bool:
    return row.get("status") == "characterized" and all(_planner_exact(row.get(key)) for key in ("bfs", "iw_width_1"))


def _planner_exact(value: JsonValue | None) -> bool:
    try:
        planner = _mapping(value, "planner")
        exact = _mapping(planner.get("exact_search"), "exact_search")
        replay = _mapping(planner.get("replay"), "replay")
    except PilotManifestError:
        return False
    return (
        planner.get("source_eligibility") == "eligible_complete_trace"
        and exact.get("status") == "exact_solution_replayed"
        and replay.get("replay_ok") is True
        and replay.get("goal_satisfied") is True
    )


def _source_digest(row: JsonObject) -> str:
    identity = _mapping(row.get("source_identity"), "source_identity")
    return _digest_text(identity.get("source_record_sha256"), "source_record_sha256")


def _signature(row: JsonObject) -> str:
    return _text(row.get("composition_signature"), "composition_signature")


def _mapping(value: JsonValue | None, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise PilotManifestError(f"pilot_{label}_invalid", Path("selection"))
    return value


def _text(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PilotManifestError(f"pilot_{label}_invalid", Path("selection"))
    return value


def _integer(value: JsonValue | None, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PilotManifestError(f"pilot_{label}_invalid", Path("selection"))
    return value


def _integer_tuple(value: JsonValue | None) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise PilotManifestError("pilot_stack_heights_invalid", Path("selection"))
    return tuple(_integer(item, "stack_height") for item in value)


def _digest_text(value: JsonValue | None, label: str) -> str:
    text = _text(value, label)
    _digest(text, label)
    return text


def _digest(value: str, label: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise PilotManifestError(f"pilot_{label}_invalid", Path("selection"))
