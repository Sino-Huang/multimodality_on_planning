from __future__ import annotations

import json
import random
from pathlib import Path

from src.data_collect.difficulty import extract_difficulty_metrics, hybrid_measured_percentile
from src.data_collect.metadata import AcceptedInstanceMetadata, build_candidate_id, build_instance_id


def _write_problem(path: Path, *, object_count: int) -> None:
    objects = " ".join(f"o{index}" for index in range(object_count))
    path.write_text(
        f"""
        (define (problem p1)
          (:domain grid)
          (:objects {objects})
          (:init)
          (:goal (and))
        )
        """.strip()
        + "\n",
        encoding="utf-8",
    )


def _write_domain(path: Path, *, predicate_count: int) -> None:
    predicates = "\n    ".join(f"(p{index})" for index in range(predicate_count))
    path.write_text(
        f"""
        (define (domain grid)
          (:predicates
            {predicates}
          )
        )
        """.strip()
        + "\n",
        encoding="utf-8",
    )


def _build_trace(path: Path, *, plan_length: int, object_count: int) -> None:
    payload = {
        "visualStages": [
            {
                "visualSprites": [
                    {"name": f"obj-{sprite_index}", "prefabimage": "img"}
                    for sprite_index in range(object_count)
                ]
            }
            for _ in range(plan_length)
        ],
        "imageTable": {"m_keys": [], "m_values": []},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _build_metadata(
    tmp_path: Path,
    *,
    candidate_suffix: str,
    target_bucket: str,
    plan_length: int | None = None,
    frame_count: int | None = None,
    object_count: int = 3,
    grounded_action_count: int | None = None,
    pddl_object_count: int = 4,
    pddl_predicate_count: int = 2,
) -> AcceptedInstanceMetadata:
    candidate_dir = tmp_path / candidate_suffix
    candidate_dir.mkdir(parents=True, exist_ok=True)
    domain_path = candidate_dir / "domain.pddl"
    problem_path = candidate_dir / "problem.pddl"
    trace_path = candidate_dir / "trace.vfg.json"
    result_path = candidate_dir / "result.json"

    _write_domain(domain_path, predicate_count=pddl_predicate_count)
    _write_problem(problem_path, object_count=pddl_object_count)

    if plan_length is not None:
        _build_trace(trace_path, plan_length=plan_length, object_count=object_count)

    render_payload = {
        "frame_count": frame_count if frame_count is not None else 0,
        "trace_path": str(trace_path) if plan_length is not None else "",
        "result_path": str(result_path),
        "details": {},
    }
    if grounded_action_count is not None:
        render_payload["details"]["grounded_action_count"] = grounded_action_count
    result_path.write_text(json.dumps(render_payload), encoding="utf-8")

    return AcceptedInstanceMetadata(
        instance_id=build_instance_id("grid", "train", target_bucket, int(candidate_suffix.split("-")[-1])),
        candidate_id=build_candidate_id("grid", "train", target_bucket, int(candidate_suffix.split("-")[-1])),
        domain_id="grid",
        split="train",
        bucket=target_bucket,
        index=int(candidate_suffix.split("-")[-1]),
        attempt_index=int(candidate_suffix.split("-")[-1]),
        seed=123,
        domain_path=str(domain_path),
        problem_path=str(problem_path),
        generator_command=("python", "generate.py"),
        generator_cwd=str(tmp_path),
        stdout_path=str(candidate_dir / "generator.stdout"),
        stderr_path=str(candidate_dir / "generator.stderr"),
        render_status="success",
        render_artifact_paths=((str(trace_path),) if plan_length is not None else ())
        + tuple(str(candidate_dir / f"frame_{index:03d}.png") for index in range(frame_count or 0)),
        render_result_path=str(result_path),
        difficulty_target=target_bucket,
        extra={"render": render_payload},
    )


def test_percentile_assignment_is_deterministic(tmp_path: Path) -> None:
    ordered = [
        _build_metadata(tmp_path, candidate_suffix=f"candidate-{index}", target_bucket="medium", plan_length=index + 2, frame_count=1)
        for index in range(6)
    ]
    shuffled = list(ordered)
    random.Random(123).shuffle(shuffled)

    assigned_ordered = hybrid_measured_percentile(ordered)
    assigned_shuffled = hybrid_measured_percentile(shuffled)

    ordered_map = {instance.candidate_id: instance.difficulty_measured for instance in assigned_ordered}
    shuffled_map = {instance.candidate_id: instance.difficulty_measured for instance in assigned_shuffled}

    assert ordered_map == shuffled_map
    assert list(ordered_map.values()).count("easy") == 2
    assert list(ordered_map.values()).count("medium") == 2
    assert list(ordered_map.values()).count("hard") == 2


def test_target_and_measured_difficulty_are_both_preserved(tmp_path: Path) -> None:
    instances = [
        _build_metadata(tmp_path, candidate_suffix="candidate-0", target_bucket="hard", plan_length=1, frame_count=1),
        _build_metadata(tmp_path, candidate_suffix="candidate-1", target_bucket="easy", plan_length=9, frame_count=1),
        _build_metadata(tmp_path, candidate_suffix="candidate-2", target_bucket="medium", plan_length=10, frame_count=1),
    ]

    assigned = hybrid_measured_percentile(instances)
    by_candidate_id = {instance.candidate_id: instance for instance in assigned}
    low_metric_candidate = by_candidate_id[build_candidate_id("grid", "train", "hard", 0)]

    assert low_metric_candidate.difficulty_target == "hard"
    assert low_metric_candidate.difficulty_measured == "easy"
    assert low_metric_candidate.measured_bucket == "easy"
    assert low_metric_candidate.extra["difficulty"]["policy"] == "hybrid_measured_percentile"


def test_metric_extraction_falls_back_to_render_and_pddl_counts(tmp_path: Path) -> None:
    instance = _build_metadata(
        tmp_path,
        candidate_suffix="candidate-0",
        target_bucket="easy",
        plan_length=None,
        frame_count=4,
        object_count=7,
        grounded_action_count=11,
        pddl_object_count=5,
        pddl_predicate_count=3,
    )

    metrics = extract_difficulty_metrics(instance)

    assert metrics.plan_length is None
    assert metrics.frame_count == 4
    assert metrics.object_count is None
    assert metrics.grounded_action_count == 11
    assert metrics.pddl_object_count == 5
    assert metrics.pddl_predicate_count == 3
