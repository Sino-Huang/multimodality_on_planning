from __future__ import annotations

import random

from src.data_collect.metadata import AcceptedInstanceMetadata, build_candidate_id, build_instance_id
from src.data_collect.selection import select_stratified_by_measured_bucket


def _build_instance(
    *,
    domain_id: str,
    split: str,
    target_bucket: str,
    measured_bucket: str,
    index: int,
    measured_difficulty: float,
) -> AcceptedInstanceMetadata:
    return AcceptedInstanceMetadata(
        instance_id=build_instance_id(domain_id, split, target_bucket, index),
        candidate_id=build_candidate_id(domain_id, split, target_bucket, index),
        domain_id=domain_id,
        split=split,
        bucket=target_bucket,
        index=index,
        attempt_index=index,
        difficulty_target=target_bucket,
        difficulty_measured=measured_bucket,
        measured_bucket=measured_bucket,
        measured_difficulty=measured_difficulty,
        render_status="success",
    )


def test_stratified_selection_uses_measured_bucket_not_target_bucket() -> None:
    candidates = [
        _build_instance(
            domain_id="grid",
            split="train",
            target_bucket="hard",
            measured_bucket="easy",
            index=0,
            measured_difficulty=0.10,
        ),
        _build_instance(
            domain_id="grid",
            split="train",
            target_bucket="easy",
            measured_bucket="hard",
            index=1,
            measured_difficulty=0.95,
        ),
    ]

    result = select_stratified_by_measured_bucket(candidates, {"train": {"easy": 1, "medium": 0, "hard": 1}})

    assert [instance.candidate_id for instance in result.selected_instances] == [
        build_candidate_id("grid", "train", "hard", 0),
        build_candidate_id("grid", "train", "easy", 1),
    ]
    assert result.incomplete_buckets == ()


def test_selection_is_deterministic_when_bucket_has_surplus_candidates() -> None:
    ordered = [
        _build_instance(
            domain_id="grid",
            split="train",
            target_bucket="easy",
            measured_bucket="easy",
            index=index,
            measured_difficulty=value,
        )
        for index, value in enumerate((0.20, 0.05, 0.15))
    ]
    shuffled = list(ordered)
    random.Random(99).shuffle(shuffled)

    expected_ids = [instance.candidate_id for instance in select_stratified_by_measured_bucket(
        ordered,
        {"train": {"easy": 2, "medium": 0, "hard": 0}},
    ).selected_instances]
    actual_ids = [instance.candidate_id for instance in select_stratified_by_measured_bucket(
        shuffled,
        {"train": {"easy": 2, "medium": 0, "hard": 0}},
    ).selected_instances]

    assert expected_ids == actual_ids == [
        build_candidate_id("grid", "train", "easy", 1),
        build_candidate_id("grid", "train", "easy", 2),
    ]


def test_incomplete_bucket_summary() -> None:
    candidates = [
        _build_instance(
            domain_id="grid",
            split="test",
            target_bucket="medium",
            measured_bucket="hard",
            index=0,
            measured_difficulty=0.9,
        )
    ]

    result = select_stratified_by_measured_bucket(candidates, {"test": {"easy": 0, "medium": 0, "hard": 2}})

    assert len(result.selected_instances) == 1
    assert len(result.incomplete_buckets) == 1
    summary = result.incomplete_buckets[0]
    assert summary.domain_id == "grid"
    assert summary.split == "test"
    assert summary.bucket == "hard"
    assert summary.requested == 2
    assert summary.selected == 1
    assert summary.available == 1
