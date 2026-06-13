from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from src.data_collect.generate import ACCEPTED_MANIFEST_FILENAME, REJECTIONS_FILENAME, SUMMARY_FILENAME
from src.data_collect.merge import discover_finalized_shards, merge_shards
from src.data_collect.metadata import (
    AcceptedInstanceMetadata,
    RejectedCandidateMetadata,
    build_candidate_id,
    build_instance_id,
    build_summary_metadata,
    write_result_metadata,
    write_summary_metadata,
)


def test_merge_shards_rebases_paths_and_aggregates_counts(tmp_path: Path) -> None:
    shards_root = tmp_path / "shards"
    output_root = tmp_path / "merged"
    ignored_partial = shards_root / "driverlog"
    ignored_partial.mkdir(parents=True)
    (ignored_partial / ACCEPTED_MANIFEST_FILENAME).write_text("", encoding="utf-8")
    (shards_root / "15puzzle" / ".staging").mkdir(parents=True)
    blocksworld = _write_shard(
        shards_root,
        "blocksworld",
        accepted=[_accepted(shards_root / "blocksworld", domain_id="blocksworld", normalized_problem_hash="hash-a")],
        rejections=[_rejection(domain_id="blocksworld")],
    )
    ferry = _write_shard(
        shards_root,
        "ferry",
        accepted=[_accepted(shards_root / "ferry", domain_id="ferry", normalized_problem_hash="hash-b")],
        rejections=[],
    )

    assert discover_finalized_shards(shards_root) == (blocksworld, ferry)

    result = merge_shards(shards_root, output_root)
    manifest_payloads = _read_jsonl(output_root / ACCEPTED_MANIFEST_FILENAME)
    blocksworld_result = _read_json(
        output_root / "blocksworld" / "train" / "easy" / "blocksworld-train-easy-0000" / "result.json"
    )

    assert result.summary.accepted_total == 2
    assert result.summary.rejected_total == 1
    assert result.summary.domains_completed == 2
    assert result.summary.accepted_by_domain == {"blocksworld": 1, "ferry": 1}
    assert result.summary.rejected_by_reason == {"invalid_pddl": 1}
    assert [Path(path).name for path in result.summary.extra["merge"]["shard_roots"]] == ["blocksworld", "ferry"]
    assert len(manifest_payloads) == 2
    for payload in manifest_payloads:
        assert str(output_root.resolve()) in payload["domain_path"]
        assert str(shards_root.resolve()) not in payload["domain_path"]
        assert all(str(output_root.resolve()) in path for path in payload["render_artifact_paths"])
        assert all(str(shards_root.resolve()) not in path for path in payload["render_artifact_paths"])
    assert blocksworld_result["domain_path"] == str(
        output_root.resolve() / "blocksworld" / "train" / "easy" / "blocksworld-train-easy-0000" / "domain.pddl"
    )
    assert blocksworld_result["render_artifact_paths"] == [
        str(
            output_root.resolve()
            / "blocksworld"
            / "train"
            / "easy"
            / "blocksworld-train-easy-0000"
            / "render"
            / "trace.vfg.json"
        ),
        str(
            output_root.resolve()
            / "blocksworld"
            / "train"
            / "easy"
            / "blocksworld-train-easy-0000"
            / "render"
            / "frames"
            / "frame_000.png"
        ),
    ]
    assert (output_root / REJECTIONS_FILENAME).read_text(encoding="utf-8").count("invalid_pddl") == 1
    assert (output_root / SUMMARY_FILENAME).exists()


def test_merge_shards_fails_on_duplicate_normalized_hashes(tmp_path: Path) -> None:
    shards_root = tmp_path / "shards"
    _write_shard(
        shards_root,
        "blocksworld",
        accepted=[_accepted(shards_root / "blocksworld", domain_id="blocksworld", normalized_problem_hash="same-hash")],
        rejections=[],
    )
    _write_shard(
        shards_root,
        "ferry",
        accepted=[_accepted(shards_root / "ferry", domain_id="ferry", normalized_problem_hash="same-hash")],
        rejections=[],
    )

    with pytest.raises(RuntimeError, match="Duplicate normalized_problem_hash"):
        merge_shards(shards_root, tmp_path / "merged")

    assert not (tmp_path / "merged" / ACCEPTED_MANIFEST_FILENAME).exists()


def test_merge_shards_requires_resume_or_force_for_existing_output(tmp_path: Path) -> None:
    shards_root = tmp_path / "shards"
    output_root = tmp_path / "merged"
    _write_shard(
        shards_root,
        "blocksworld",
        accepted=[_accepted(shards_root / "blocksworld", domain_id="blocksworld", normalized_problem_hash="hash-a")],
        rejections=[],
    )
    output_root.mkdir()
    stale_file = output_root / "stale.txt"
    stale_file.write_text("stale", encoding="utf-8")

    with pytest.raises(RuntimeError, match="--resume or --force"):
        merge_shards(shards_root, output_root)

    resumed = merge_shards(shards_root, output_root, resume=True)
    assert resumed.summary.accepted_total == 1
    assert resumed.summary.resumed_accepted_total == 0
    assert stale_file.exists()

    forced_file = output_root / "forced-stale.txt"
    forced_file.write_text("stale", encoding="utf-8")
    forced = merge_shards(shards_root, output_root, force=True)

    assert forced.summary.accepted_total == 1
    assert not forced_file.exists()

    with pytest.raises(ValueError, match="force and resume"):
        merge_shards(shards_root, output_root, force=True, resume=True)


def _accepted(shard_root: Path, *, domain_id: str, normalized_problem_hash: str) -> AcceptedInstanceMetadata:
    split = "train"
    bucket = "easy"
    index = 0
    attempt_index = 0
    instance_id = build_instance_id(domain_id, split, bucket, index)
    candidate_id = build_candidate_id(domain_id, split, bucket, attempt_index)
    instance_dir = shard_root / domain_id / split / bucket / instance_id
    render_dir = instance_dir / "render"
    frames_dir = render_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "domain.pddl").write_text(f"(define (domain {domain_id}))\n", encoding="utf-8")
    (instance_dir / "problem.pddl").write_text(f"(define (problem {instance_id}) (:domain {domain_id}))\n", encoding="utf-8")
    (instance_dir / "generator.stdout").write_text("ok\n", encoding="utf-8")
    (instance_dir / "generator.stderr").write_text("", encoding="utf-8")
    (render_dir / "trace.vfg.json").write_text("{}\n", encoding="utf-8")
    (frames_dir / "frame_000.png").write_bytes(b"png")

    return AcceptedInstanceMetadata(
        instance_id=instance_id,
        candidate_id=candidate_id,
        domain_id=domain_id,
        split=split,
        bucket=bucket,
        index=index,
        attempt_index=attempt_index,
        seed=123,
        domain_path=str(instance_dir / "domain.pddl"),
        problem_path=str(instance_dir / "problem.pddl"),
        generator_command=("generate", domain_id),
        generator_cwd=str(shard_root / "generators" / domain_id),
        stdout_path=str(instance_dir / "generator.stdout"),
        stderr_path=str(instance_dir / "generator.stderr"),
        domain_hash=f"domain-{normalized_problem_hash}",
        normalized_domain_hash=f"normalized-domain-{normalized_problem_hash}",
        problem_hash=f"problem-{normalized_problem_hash}",
        normalized_problem_hash=normalized_problem_hash,
        render_status="success",
        render_artifact_paths=(str(render_dir / "trace.vfg.json"), str(frames_dir / "frame_000.png")),
        render_result_path=str(render_dir / "result.json"),
        difficulty_target=bucket,
        difficulty_measured=bucket,
        measured_difficulty=0.1,
        measured_bucket=bucket,
    )


def _rejection(domain_id: str) -> RejectedCandidateMetadata:
    return RejectedCandidateMetadata(
        candidate_id=build_candidate_id(domain_id, "train", "easy", 1),
        domain_id=domain_id,
        split="train",
        bucket="easy",
        attempt_index=1,
        rejection_reason="invalid_pddl",
        rejection_stage="generation",
        message="synthetic invalid PDDL",
    )


def _write_shard(
    shards_root: Path,
    shard_name: str,
    *,
    accepted: list[AcceptedInstanceMetadata],
    rejections: list[RejectedCandidateMetadata],
) -> Path:
    shard_root = (shards_root / shard_name).resolve()
    shard_root.mkdir(parents=True, exist_ok=True)
    for instance in accepted:
        write_result_metadata(Path(instance.domain_path).parent / "result.json", instance, force=True)
    _write_jsonl(shard_root / ACCEPTED_MANIFEST_FILENAME, [instance.to_dict() for instance in accepted])
    _write_jsonl(shard_root / REJECTIONS_FILENAME, [rejection.to_dict() for rejection in rejections])
    write_summary_metadata(
        shard_root / SUMMARY_FILENAME,
        build_summary_metadata(
            accepted_instances=accepted,
            rejected_candidates=rejections,
            duplicate_accepted_problem_hashes=0,
        ),
    )
    return shard_root


def _write_jsonl(path: Path, payloads: Sequence[Mapping[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(payload, sort_keys=True) for payload in payloads) + ("\n" if payloads else ""), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
