"""Deterministic stratified selection helpers for curriculum data collection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from .difficulty import DIFFICULTY_BUCKETS
from .metadata import AcceptedInstanceMetadata


@dataclass(frozen=True)
class IncompleteBucketSummary:
    """Describes one underfilled measured-difficulty bucket."""

    domain_id: str
    split: str
    bucket: str
    requested: int
    selected: int
    available: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "domain_id": self.domain_id,
            "split": self.split,
            "bucket": self.bucket,
            "requested": self.requested,
            "selected": self.selected,
            "available": self.available,
        }


@dataclass(frozen=True)
class StratifiedSelectionResult:
    """Selection output plus exact accounting for incomplete measured buckets."""

    selected_instances: tuple[AcceptedInstanceMetadata, ...]
    incomplete_buckets: tuple[IncompleteBucketSummary, ...]
    requested_counts: dict[str, dict[str, dict[str, int]]]
    available_counts: dict[str, dict[str, dict[str, int]]]
    selected_counts: dict[str, dict[str, dict[str, int]]]

    def to_dict(self) -> dict[str, object]:
        return {
            "selected_instances": [instance.instance_id for instance in self.selected_instances],
            "incomplete_buckets": [summary.to_dict() for summary in self.incomplete_buckets],
            "requested_counts": self.requested_counts,
            "available_counts": self.available_counts,
            "selected_counts": self.selected_counts,
        }


def _measured_bucket(instance: AcceptedInstanceMetadata) -> str:
    measured_bucket = instance.difficulty_measured or instance.measured_bucket
    if not measured_bucket:
        raise ValueError(
            f"Instance {instance.instance_id} is missing difficulty_measured/measured_bucket; "
            "run hybrid_measured_percentile before stratified selection"
        )
    return measured_bucket


def _selection_sort_key(instance: AcceptedInstanceMetadata) -> tuple[str, float, str]:
    measured_bucket = _measured_bucket(instance)
    score = instance.measured_difficulty if instance.measured_difficulty is not None else -1.0
    if measured_bucket == "hard":
        score = -score
    return (measured_bucket, score, instance.candidate_id)


def _clone_nested_counts(source: dict[str, dict[str, dict[str, int]]]) -> dict[str, dict[str, dict[str, int]]]:
    return {
        domain_id: {
            split: dict(bucket_counts)
            for split, bucket_counts in split_counts.items()
        }
        for domain_id, split_counts in source.items()
    }


def select_stratified_by_measured_bucket(
    instances: Sequence[AcceptedInstanceMetadata],
    quotas_by_split: dict[str, dict[str, int]],
) -> StratifiedSelectionResult:
    """Select deterministic per-domain/per-split measured-difficulty quotas."""

    grouped: dict[tuple[str, str, str], list[AcceptedInstanceMetadata]] = defaultdict(list)
    available_counts: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for instance in instances:
        bucket = _measured_bucket(instance)
        grouped[(instance.domain_id, instance.split, bucket)].append(instance)
        available_counts[instance.domain_id][instance.split][bucket] += 1

    selected_instances: list[AcceptedInstanceMetadata] = []
    incomplete_buckets: list[IncompleteBucketSummary] = []
    requested_counts: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
    selected_counts: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))

    selected_domain_splits = sorted({(instance.domain_id, instance.split) for instance in instances})
    for domain_id, split in selected_domain_splits:
        split_quotas = quotas_by_split.get(split, {})
        for bucket in DIFFICULTY_BUCKETS:
            requested = int(split_quotas.get(bucket, 0))
            requested_counts[domain_id][split][bucket] = requested
            available = available_counts[domain_id][split].get(bucket, 0)
            if requested <= 0:
                selected_counts[domain_id][split][bucket] = 0
                continue

            candidates = sorted(grouped.get((domain_id, split, bucket), []), key=_selection_sort_key)
            chosen = candidates[:requested]
            selected_instances.extend(chosen)
            selected_counts[domain_id][split][bucket] = len(chosen)

            if len(chosen) < requested:
                incomplete_buckets.append(
                    IncompleteBucketSummary(
                        domain_id=domain_id,
                        split=split,
                        bucket=bucket,
                        requested=requested,
                        selected=len(chosen),
                        available=available,
                    )
                )

    return StratifiedSelectionResult(
        selected_instances=tuple(selected_instances),
        incomplete_buckets=tuple(incomplete_buckets),
        requested_counts=_clone_nested_counts(requested_counts),
        available_counts=_clone_nested_counts(available_counts),
        selected_counts=_clone_nested_counts(selected_counts),
    )


__all__ = [
    "IncompleteBucketSummary",
    "StratifiedSelectionResult",
    "select_stratified_by_measured_bucket",
]
