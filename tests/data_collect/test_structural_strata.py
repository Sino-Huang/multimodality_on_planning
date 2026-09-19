from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from src.data_collect.structural import (
    StructuralCell,
    StructuralCoverageError,
    StructuralProfile,
    StructuralRange,
    StructuralRequirement,
    StructuralStrataPolicy,
    derive_structural_profile,
    verify_structural_coverage,
)


def _fixture_policy() -> StructuralStrataPolicy:
    """Committed test policy; these bounds are not corpus-wide thresholds."""

    return StructuralStrataPolicy(
        version="structural-fixture-v1",
        horizon_ranges=(
            StructuralRange("short", 1, 2),
            StructuralRange("long", 3, 4),
        ),
        branching_ranges=(
            StructuralRange("narrow", 1, 2),
            StructuralRange("wide", 3, 4),
        ),
        object_count_ranges=(
            StructuralRange("few", 2, 3),
            StructuralRange("many", 4, 5),
        ),
        required_cells=(
            StructuralRequirement(
                split="train",
                cell=StructuralCell("short", "narrow", "few"),
                minimum_count=2,
            ),
            StructuralRequirement(
                split="dev",
                cell=StructuralCell("long", "wide", "many"),
                minimum_count=1,
            ),
        ),
    )


def test_declared_policy_and_profiles_are_immutable_and_json_compatible() -> None:
    policy = _fixture_policy()
    profile = StructuralProfile(
        instance_id="train-001",
        split="train",
        horizon=2,
        branching_factor=1,
        object_count=3,
        legacy_bucket="hard",
    )

    assert policy.cell_for(profile) == StructuralCell("short", "narrow", "few")
    assert json.loads(json.dumps(policy.to_dict()))["version"] == "structural-fixture-v1"
    assert json.loads(json.dumps(profile.to_dict())) == {
        "instance_id": "train-001",
        "split": "train",
        "horizon": 2,
        "branching_factor": 1,
        "object_count": 3,
        "metadata": {"legacy_bucket": "hard"},
    }
    with pytest.raises(FrozenInstanceError):
        profile.horizon = 3  # type: ignore[misc]


def test_derive_structural_profile_is_case_insensitive_for_valid_pddl(tmp_path: Path) -> None:
    domain = """(define (domain tiny)
    (:predicates (ready ?x) (clear ?x))
    (:action move :parameters (?x) :precondition (ready ?x) :effect (clear ?x))
    (:action wait :parameters (?x) :precondition (clear ?x) :effect (ready ?x)))
"""
    problem = """(define (problem p)
    (:domain tiny)
    (:objects a b c - thing)
    (:init (ready a))
    (:goal (and (clear a) (ready b))))
"""
    lowercase_domain = tmp_path / "lower-domain.pddl"
    lowercase_problem = tmp_path / "lower-problem.pddl"
    mixed_case_domain = tmp_path / "mixed-domain.pddl"
    mixed_case_problem = tmp_path / "mixed-problem.pddl"
    lowercase_domain.write_text(domain, encoding="utf-8")
    lowercase_problem.write_text(problem, encoding="utf-8")
    mixed_case_domain.write_text(domain.upper(), encoding="utf-8")
    mixed_case_problem.write_text(problem.upper(), encoding="utf-8")

    lowercase = derive_structural_profile(
        instance_id="tiny-train-0000",
        split="train",
        domain_path=lowercase_domain,
        problem_path=lowercase_problem,
        legacy_bucket="easy",
    )
    mixed_case = derive_structural_profile(
        instance_id="tiny-train-0000",
        split="train",
        domain_path=mixed_case_domain,
        problem_path=mixed_case_problem,
        legacy_bucket="easy",
    )

    assert lowercase == StructuralProfile("tiny-train-0000", "train", 2, 2, 3, legacy_bucket="easy")
    assert mixed_case == lowercase


def test_coverage_uses_fixed_structural_cells_and_split_minimums() -> None:
    policy = _fixture_policy()
    profiles = (
        StructuralProfile("train-001", "train", 1, 1, 2, legacy_bucket="easy"),
        StructuralProfile("train-002", "train", 2, 2, 3, legacy_bucket="hard"),
        StructuralProfile("dev-001", "dev", 4, 4, 5, legacy_bucket="medium"),
    )

    coverage = verify_structural_coverage(policy, profiles)

    assert coverage.policy_version == "structural-fixture-v1"
    assert coverage.count_for("train", StructuralCell("short", "narrow", "few")) == 2
    assert coverage.count_for("dev", StructuralCell("long", "wide", "many")) == 1
    assert json.loads(json.dumps(coverage.to_dict()))["complete"] is True


def test_coverage_rejects_an_underfilled_required_cell() -> None:
    policy = _fixture_policy()
    profiles = (
        StructuralProfile("train-001", "train", 1, 1, 2),
        StructuralProfile("dev-001", "dev", 3, 3, 4),
    )

    with pytest.raises(StructuralCoverageError) as error:
        verify_structural_coverage(policy, profiles)

    assert error.value.unprofiled_instance_ids == ()
    assert error.value.gaps[0].split == "train"
    assert error.value.gaps[0].minimum_count == 2
    assert error.value.gaps[0].actual_count == 1


def test_coverage_rejects_values_outside_the_declared_ranges() -> None:
    policy = _fixture_policy()
    profiles = (
        StructuralProfile("train-001", "train", 1, 1, 2),
        StructuralProfile("train-002", "train", 9, 1, 2, legacy_bucket="short"),
        StructuralProfile("dev-001", "dev", 3, 3, 4),
    )

    with pytest.raises(StructuralCoverageError) as error:
        verify_structural_coverage(policy, profiles)

    assert error.value.unprofiled_instance_ids == ("train-002",)


def test_legacy_percentile_bucket_is_metadata_not_a_structural_stratum() -> None:
    policy = _fixture_policy()
    easy = StructuralProfile("train-001", "train", 1, 1, 2, legacy_bucket="easy")
    hard = StructuralProfile("train-002", "train", 1, 1, 2, legacy_bucket="hard")
    dev = StructuralProfile("dev-001", "dev", 3, 3, 4, legacy_bucket="easy")

    coverage = verify_structural_coverage(policy, (easy, hard, dev))

    required_train_cell = StructuralCell("short", "narrow", "few")
    assert policy.cell_for(easy) == policy.cell_for(hard) == required_train_cell
    assert coverage.count_for("train", required_train_cell) == 2
