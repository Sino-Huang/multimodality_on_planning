from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.data_collect.hashing import AcceptedProblemHashIndex, build_pddl_hash_info, normalized_pddl_sha256
from src.data_collect.metadata import (
    DUPLICATE_HASH_REASON,
    AcceptedInstanceMetadata,
    build_candidate_id,
    build_duplicate_rejection,
    build_instance_id,
    build_summary_metadata,
    write_result_metadata,
)


def build_accepted_metadata(
    *,
    domain_id: str = "grid",
    split: str = "train",
    bucket: str = "easy",
    index: int = 0,
    attempt_index: int = 0,
    normalized_problem_hash: str = "problem-hash",
) -> AcceptedInstanceMetadata:
    return AcceptedInstanceMetadata(
        instance_id=build_instance_id(domain_id, split, bucket, index),
        candidate_id=build_candidate_id(domain_id, split, bucket, attempt_index),
        domain_id=domain_id,
        split=split,
        bucket=bucket,
        index=index,
        attempt_index=attempt_index,
        seed=123,
        domain_path=f"{domain_id}/domain.pddl",
        problem_path=f"{domain_id}/{split}-{bucket}-{index}.pddl",
        generator_command=("python", "generate.py"),
        generator_cwd=f"/tmp/{domain_id}",
        stdout_path=f"/tmp/{domain_id}/stdout.log",
        stderr_path=f"/tmp/{domain_id}/stderr.log",
        problem_hash=f"raw-{normalized_problem_hash}",
        normalized_problem_hash=normalized_problem_hash,
        render_status="success",
        render_artifact_paths=(f"/tmp/{domain_id}/trace.vfg.json", f"/tmp/{domain_id}/frame_000.png"),
        render_result_path=f"/tmp/{domain_id}/result.json",
        measured_difficulty=0.25,
        measured_bucket=bucket,
    )


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_identifier_helpers_are_deterministic() -> None:
    assert build_instance_id("grid", "train", "easy", 3) == "grid-train-easy-0003"
    assert build_instance_id("grid", "train", "easy", 3) == "grid-train-easy-0003"
    assert build_candidate_id("grid", "train", "easy", 12) == "grid-train-easy-attempt-000012"
    assert build_candidate_id("grid", "train", "easy", 12) == "grid-train-easy-attempt-000012"


def test_identifier_contract_rejects_mismatched_ids() -> None:
    with pytest.raises(ValueError, match="instance_id"):
        AcceptedInstanceMetadata(
            instance_id="grid-train-easy-9999",
            candidate_id=build_candidate_id("grid", "train", "easy", 0),
            domain_id="grid",
            split="train",
            bucket="easy",
            index=0,
            attempt_index=0,
        )


def test_normalized_pddl_hash_ignores_comments_and_whitespace() -> None:
    canonical_problem = """
    (define (problem p1)
      (:domain grid)
      (:init (at robot a))
      (:goal (and (at robot b))))
    """
    noisy_problem = """
    ; a full-line comment
    (define   (problem p1) ; inline comment
      (:domain grid)

      (:init   (at robot a)   )
      (:goal
        (and
          (at robot b)
        )
      )
    )
    """

    canonical_hashes = build_pddl_hash_info(canonical_problem)
    noisy_hashes = build_pddl_hash_info(noisy_problem)

    assert canonical_hashes.raw_sha256 != noisy_hashes.raw_sha256
    assert canonical_hashes.normalized_sha256 == noisy_hashes.normalized_sha256
    assert canonical_hashes.normalized_text == noisy_hashes.normalized_text


def test_duplicate_normalized_hash_rejected() -> None:
    accepted_hash_index = AcceptedProblemHashIndex()
    normalized_problem_hash = normalized_pddl_sha256("(define (problem p1) (:domain grid))")

    first_duplicate = accepted_hash_index.register(
        normalized_problem_hash=normalized_problem_hash,
        instance_id=build_instance_id("grid", "train", "easy", 0),
        domain_id="grid",
        split="train",
        bucket="easy",
        duplicate_identifier=build_candidate_id("grid", "train", "easy", 0),
    )

    assert first_duplicate is None

    duplicate = accepted_hash_index.register(
        normalized_problem_hash=normalized_problem_hash,
        instance_id=build_instance_id("grid", "dev", "medium", 0),
        domain_id="grid",
        split="dev",
        bucket="medium",
        duplicate_identifier=build_candidate_id("grid", "dev", "medium", 3),
    )

    assert duplicate is not None
    rejection = build_duplicate_rejection(
        candidate_id=build_candidate_id("grid", "dev", "medium", 3),
        domain_id="grid",
        split="dev",
        bucket="medium",
        attempt_index=3,
        normalized_problem_hash=normalized_problem_hash,
        duplicate=duplicate,
        seed=456,
    )

    assert rejection.rejection_reason == DUPLICATE_HASH_REASON
    assert rejection.duplicate_of_instance_id == "grid-train-easy-0000"
    assert rejection.details["existing_split"] == "train"
    assert rejection.details["existing_bucket"] == "easy"


def test_resume_does_not_overwrite_without_force(tmp_path: Path) -> None:
    result_path = tmp_path / "grid" / "result.json"
    original = build_accepted_metadata(index=0, attempt_index=0, normalized_problem_hash="hash-a")
    replacement = build_accepted_metadata(index=1, attempt_index=1, normalized_problem_hash="hash-b")

    initial_decision = write_result_metadata(result_path, original)
    original_payload = read_json(result_path)
    skipped_decision = write_result_metadata(result_path, replacement, force=False)
    skipped_payload = read_json(result_path)
    forced_decision = write_result_metadata(result_path, replacement, force=True)
    replaced_payload = read_json(result_path)

    assert initial_decision.action == "write_new"
    assert skipped_decision.action == "skip_existing_accepted"
    assert original_payload["instance_id"] == original.instance_id
    assert skipped_payload == original_payload
    assert forced_decision.action == "overwrite_forced"
    assert replaced_payload["instance_id"] == replacement.instance_id


def test_summary_metadata_aggregates_records() -> None:
    accepted_instances = [
        build_accepted_metadata(domain_id="grid", split="train", bucket="easy", index=0, attempt_index=0),
        build_accepted_metadata(domain_id="grid", split="dev", bucket="medium", index=0, attempt_index=1),
    ]
    accepted_hash_index = AcceptedProblemHashIndex()
    first_duplicate = accepted_hash_index.register(
        normalized_problem_hash="hash-2",
        instance_id=build_instance_id("grid", "train", "easy", 0),
        domain_id="grid",
        split="train",
        bucket="easy",
    )
    assert first_duplicate is None
    conflict = accepted_hash_index.register(
        normalized_problem_hash="hash-2",
        instance_id=build_instance_id("grid", "test", "hard", 0),
        domain_id="grid",
        split="test",
        bucket="hard",
        duplicate_identifier=build_candidate_id("grid", "test", "hard", 4),
    )
    assert conflict is not None
    rejected_candidates = [
        build_duplicate_rejection(
            candidate_id=build_candidate_id("grid", "test", "hard", 4),
            domain_id="grid",
            split="test",
            bucket="hard",
            attempt_index=4,
            normalized_problem_hash="hash-2",
            duplicate=conflict,
        )
    ]

    summary = build_summary_metadata(
        accepted_instances=accepted_instances,
        rejected_candidates=rejected_candidates,
        resumed_accepted_total=1,
        domains_completed=1,
        duplicate_accepted_problem_hashes=0,
    )

    assert summary.accepted_total == 2
    assert summary.rejected_total == 1
    assert summary.accepted_by_split == {"train": 1, "dev": 1}
    assert summary.accepted_by_bucket == {"easy": 1, "medium": 1}
    assert summary.accepted_by_domain == {"grid": 2}
    assert summary.rejected_by_reason == {DUPLICATE_HASH_REASON: 1}
    assert summary.resumed_accepted_total == 1
