from __future__ import annotations

from typing import Any

from scripts.adjudicate_bfs_sanity_v3 import _adjudicate


def _result(success: bool, *, invalid: int = 0, decisions: int = 10) -> dict[str, Any]:
    return {
        "algorithm_invariants_hold": True,
        "decision_count": decisions,
        "goal_reached": success,
        "invalid_operation_count": invalid,
    }


def _rows(arm: str, instance_ids: set[str], seeds: tuple[int, ...], success: bool) -> list[dict[str, Any]]:
    return [
        {
            "adapter_path": f"adapter-{seed}" if arm == "process_sft" else None,
            "arm": arm,
            "instance_id": instance_id,
            "result": _result(success),
            "seed": seed,
        }
        for instance_id in sorted(instance_ids)
        for seed in seeds
    ]


def _references(instance_ids: set[str], seeds: tuple[int, ...]) -> list[dict[str, Any]]:
    exact = [
        {"arm": "exact_classical", "instance_id": instance_id, "result": _result(True), "seed": None}
        for instance_id in sorted(instance_ids)
    ]
    return [*exact, *_rows("random_valid", instance_ids, seeds, False)]


def _thresholds() -> dict[str, float]:
    return {
        "exact_reference_invariant_valid_success": 1.0,
        "maximum_invalid_operation_rate": 0.05,
        "process_sft_absolute_gain_over_best_control": 0.1,
        "process_sft_gain_bootstrap_lower_bound": 0.0,
        "process_sft_invariant_valid_success": 0.8,
    }


def test_process_sanity_passes_all_frozen_thresholds_and_selects_each_seed_adapter() -> None:
    instance_ids = {"task-a", "task-b"}
    seeds = (17, 29)

    report = _adjudicate(
        expected_ids=instance_ids,
        seeds=seeds,
        references=_references(instance_ids, seeds),
        base=_rows("base", instance_ids, seeds, False),
        process=_rows("process_sft", instance_ids, seeds, True),
        thresholds=_thresholds(),
        bootstrap_resamples=100,
        bootstrap_seed=1729,
    )

    assert report["outcome"] == "PASS"
    assert report["process_sft_invariant_valid_success"] == 1.0
    assert report["selected_adapters"] == {"17": "adapter-17", "29": "adapter-29"}
    assert all(report["checks"].values())


def test_process_sanity_issues_valid_stop_when_the_frozen_gain_is_missed() -> None:
    instance_ids = {"task-a", "task-b"}
    seeds = (17, 29)
    base = _rows("base", instance_ids, seeds, True)

    report = _adjudicate(
        expected_ids=instance_ids,
        seeds=seeds,
        references=_references(instance_ids, seeds),
        base=base,
        process=_rows("process_sft", instance_ids, seeds, True),
        thresholds=_thresholds(),
        bootstrap_resamples=100,
        bootstrap_seed=1729,
    )

    assert report["outcome"] == "VALID_STOP"
    assert report["checks"]["absolute_gain"] is False


def test_process_sanity_issues_ancestor_stop_before_model_runs_when_exact_reference_misses() -> None:
    instance_ids = {"task-a", "task-b"}
    seeds = (17, 29)
    references = _references(instance_ids, seeds)
    for row in references:
        if row["arm"] == "exact_classical":
            row["result"] = _result(False)

    report = _adjudicate(
        expected_ids=instance_ids,
        seeds=seeds,
        references=references,
        base=[],
        process=[],
        thresholds=_thresholds(),
        bootstrap_resamples=100,
        bootstrap_seed=1729,
    )

    assert report["outcome"] == "ANCESTOR_STOP"
    assert report["scientific_completion"] is False
