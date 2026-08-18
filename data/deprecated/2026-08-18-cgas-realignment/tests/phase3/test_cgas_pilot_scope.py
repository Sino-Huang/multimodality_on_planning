from __future__ import annotations

from scripts.phase3.cgas_candidate_characterization_models import JsonObject, JsonValue
from scripts.phase3.cgas_pilot_scope import analyze_rows


def _row(
    object_count: int,
    signature: str,
    stack_profile: list[int],
    goal_edges: int,
    plan_length: int,
    bfs_expansions: int,
    iw_expansions: int | None = None,
) -> JsonObject:
    bfs_exact: JsonObject = {
        "expansion_count": bfs_expansions,
        "plan_length": plan_length,
        "status": "exact_solution_replayed",
    }
    iw_exact: JsonObject = {
        "expansion_count": bfs_expansions if iw_expansions is None else iw_expansions,
        "plan_length": plan_length,
        "status": "exact_solution_replayed",
    }
    bfs: JsonObject = {"exact_search": bfs_exact}
    iw: JsonObject = {"exact_search": iw_exact}
    goal: JsonObject = {"on_edges": goal_edges}
    profile: list[JsonValue] = list(stack_profile)
    init: JsonObject = {"stack_heights": profile}
    return {
        "bfs": bfs,
        "candidate_id": f"{object_count:02d}-{signature}-{plan_length}",
        "composition_signature": signature,
        "goal_descriptor": goal,
        "init_descriptor": init,
        "iw_width_1": iw,
        "object_count": object_count,
        "status": "characterized",
    }


def test_analyze_rows_reports_object_and_composition_diversity() -> None:
    rows = (
        _row(4, "four-a", [4], 1, 4, 12, 8),
        _row(4, "four-b", [2, 2], 2, 6, 18, 10),
        _row(8, "eight-a", [1, 7], 3, 4, 30),
        _row(12, "twelve-a", [2, 10], 7, 8, 40),
        _row(12, "twelve-a", [2, 10], 7, 8, 40),
        _row(12, "twelve-b", [1, 1, 1, 9], 8, 10, 50),
        {**_row(8, "eight-inexact", [8], 1, 2, 2), "iw_width_1": {"exact_search": {"status": "failed"}}},
    )

    report = analyze_rows(rows)

    assert report.characterized_candidate_count == 7
    assert report.paired_exact_count == 6
    assert report.object_count_counts == ((4, 2), (8, 1), (12, 3))
    assert report.composition_signature_counts == ((4, 2), (8, 1), (12, 2))
    assert report.structural_profile_counts == ((4, 2), (8, 1), (12, 2))


def test_analyze_rows_evaluates_the_diversity_floor() -> None:
    rows = tuple(
        _row(object_count, f"{object_count}-{signature}", [signature + 1], signature + 1, 4, 12)
        for object_count in (4, 8, 12)
        for signature in range(5)
        for _ in range(2)
    )

    report = analyze_rows(rows)

    assert report.diversity_floor.min_instances_per_object_count == 30
    assert report.diversity_floor.min_repeated_composition_signatures_per_object_count == 5
    assert report.diversity_floor.passed is False
    assert report.diversity_floor.failed_object_counts == (4, 8, 12)


def test_analyze_rows_reports_plan_and_certificate_yields() -> None:
    rows = (
        _row(4, "four-a", [4], 1, 4, 12, 8),
        _row(4, "four-b", [2, 2], 2, 6, 18, 10),
    )

    report = analyze_rows(rows)

    assert report.plan_length.mean == 5.0
    assert report.plan_length.median == 5.0
    assert report.plan_length.maximum == 6
    assert report.on_plan_certificate_rows.mean == 10.0
    assert report.off_plan_certificate_rows.mean == 24.0
    assert report.off_plan_only_certificate_rows.mean == 14.0


def test_analyze_rows_prices_both_stability_bars_without_selecting_owner_bar() -> None:
    rows = tuple(
        _row(object_count, f"{object_count}-{signature}", [signature + 1], signature + 1, 4, 12)
        for object_count in (4, 8, 12)
        for signature in range(5)
        for _ in range(6)
    )

    report = analyze_rows(rows)

    alternatives = {(item.bar, item.failure_rate, item.harvest): item for item in report.sizing}
    assert len(alternatives) == 8
    assert alternatives[(10, 0.4, "on_plan")].pilot_instance_count == 402
    assert alternatives[(30, 0.4, "on_plan")].pilot_instance_count == 1200
    assert alternatives[(10, 0.4, "off_plan")].pilot_instance_count == 135
    assert alternatives[(30, 0.4, "off_plan")].pilot_instance_count == 402
    assert report.recommendation.stability_bar == "owner_decision_required"
