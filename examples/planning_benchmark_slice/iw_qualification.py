from __future__ import annotations

import json
import signal
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
from typing import Any, Iterator, Sequence

from .bfws_episode import run_best_first_width
from .iw_episode import run_iterative_width
from .pddl_state import GroundedAction, PDDLStateAuthority

QUALIFICATION_SCHEMA_VERSION = "iw3_curriculum_qualification_v1"
BFWS_QUALIFICATION_SCHEMA_VERSION = "bfws_curriculum_qualification_v1"


class _QualificationTimeout(TimeoutError):
    pass


def qualify_curriculum(
    manifest_path: str | Path,
    output_root: str | Path,
    *,
    splits: Sequence[str] = ("train", "test"),
    max_expansions: int = 500,
    timeout_seconds: int = 60,
    retry_statuses: Sequence[str] = (),
    shard_index: int = 0,
    shard_count: int = 1,
) -> dict[str, Any]:
    """Qualify capped IW(1..3) over immutable curriculum instances, resumably."""

    _validate_shard(shard_index, shard_count)
    manifest = Path(manifest_path).resolve()
    output = Path(output_root).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows_path = output / "instance-results.jsonl"
    selected_splits = tuple(splits)
    completed = _completed_instance_ids(rows_path, retry_statuses=set(retry_statuses))

    with manifest.open(encoding="utf-8") as stream, rows_path.open("a", encoding="utf-8") as sink:
        for line_index, raw_line in enumerate(stream):
            if line_index % shard_count != shard_index:
                continue
            source = json.loads(raw_line)
            if source.get("split") not in selected_splits or source.get("instance_id") in completed:
                continue
            result = _qualify_instance(
                source,
                max_expansions=max_expansions,
                timeout_seconds=timeout_seconds,
            )
            sink.write(_canonical_json(result) + "\n")
            sink.flush()

    rows = list(_latest_results(rows_path).values())
    selected = [row for row in rows if row["split"] in selected_splits]
    status_counts = Counter(row["status"] for row in selected)
    migration_required = status_counts["width_cap_exhausted"] > 0
    conclusive = sum(status_counts[status] for status in ("solved", "width_cap_exhausted")) == len(selected)
    report = {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "source_manifest": str(manifest),
        "splits": list(selected_splits),
        "max_width": 3,
        "max_expansions_per_width": max_expansions,
        "timeout_seconds_per_instance": timeout_seconds,
        "instance_count": len(selected),
        "status_counts": dict(sorted(status_counts.items())),
        "status_by_split": {
            split: dict(sorted(Counter(row["status"] for row in selected if row["split"] == split).items()))
            for split in selected_splits
        },
        "status_by_domain": _grouped_status_counts(selected, "domain"),
        "status_by_bucket": _grouped_status_counts(selected, "bucket"),
        "migration_required": migration_required,
        "qualification_conclusive": conclusive,
        "test_split_consumed_for_algorithm_selection": "test" in selected_splits,
    }
    (output / "report.json").write_text(_canonical_json(report) + "\n", encoding="utf-8")
    return report


def qualify_bfws_curriculum(
    manifest_path: str | Path,
    output_root: str | Path,
    *,
    splits: Sequence[str] = ("train", "test"),
    max_expansions: int = 500,
    timeout_seconds: int = 60,
    retry_statuses: Sequence[str] = (),
    shard_index: int = 0,
    shard_count: int = 1,
) -> dict[str, Any]:
    """Qualify complete, unpruned BFWS over the same immutable curriculum."""

    _validate_shard(shard_index, shard_count)
    manifest = Path(manifest_path).resolve()
    output = Path(output_root).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows_path = output / "instance-results.jsonl"
    selected_splits = tuple(splits)
    completed = _completed_instance_ids(rows_path, retry_statuses=set(retry_statuses))

    with manifest.open(encoding="utf-8") as stream, rows_path.open("a", encoding="utf-8") as sink:
        for line_index, raw_line in enumerate(stream):
            if line_index % shard_count != shard_index:
                continue
            source = json.loads(raw_line)
            if source.get("split") not in selected_splits or source.get("instance_id") in completed:
                continue
            result = _qualify_bfws_instance(
                source,
                max_expansions=max_expansions,
                timeout_seconds=timeout_seconds,
            )
            sink.write(_canonical_json(result) + "\n")
            sink.flush()

    rows = list(_latest_results(rows_path).values())
    selected = [row for row in rows if row["split"] in selected_splits]
    status_counts = Counter(row["status"] for row in selected)
    solved_manifest_path = output / "solved-manifest.jsonl"
    _write_selected_manifest(
        manifest,
        solved_manifest_path,
        {row["instance_id"] for row in selected if row["status"] == "solved"},
    )
    report = {
        "schema_version": BFWS_QUALIFICATION_SCHEMA_VERSION,
        "algorithm": "best_first_width",
        "variant": "full_bfws_goal_count",
        "source_manifest": str(manifest),
        "splits": list(selected_splits),
        "novelty_precision": 2,
        "high_novelty_policy": "enqueue",
        "max_expansions": max_expansions,
        "timeout_seconds_per_instance": timeout_seconds,
        "instance_count": len(selected),
        "status_counts": dict(sorted(status_counts.items())),
        "status_by_split": {
            split: dict(sorted(Counter(row["status"] for row in selected if row["split"] == split).items()))
            for split in selected_splits
        },
        "status_by_domain": _grouped_status_counts(selected, "domain"),
        "status_by_bucket": _grouped_status_counts(selected, "bucket"),
        "all_solved": status_counts == Counter({"solved": len(selected)}),
        "solved_manifest": str(solved_manifest_path),
        "solved_manifest_instance_count": status_counts["solved"],
        "qualification_conclusive": sum(status_counts[status] for status in ("solved", "frontier_exhausted"))
        == len(selected),
        "test_split_consumed_for_algorithm_selection": "test" in selected_splits,
    }
    (output / "report.json").write_text(_canonical_json(report) + "\n", encoding="utf-8")
    return report


def _validate_shard(shard_index: int, shard_count: int) -> None:
    if shard_count <= 0:
        raise ValueError("shard_count must be positive")
    if not 0 <= shard_index < shard_count:
        raise ValueError("shard_index must be in [0, shard_count)")


def _write_selected_manifest(source_path: Path, target_path: Path, instance_ids: set[str]) -> None:
    selected_lines: list[str] = []
    with source_path.open(encoding="utf-8") as stream:
        for raw_line in stream:
            if json.loads(raw_line).get("instance_id") in instance_ids:
                selected_lines.append(raw_line if raw_line.endswith("\n") else raw_line + "\n")
    target_path.write_text("".join(selected_lines), encoding="utf-8")


def _qualify_instance(
    source: dict[str, Any],
    *,
    max_expansions: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = monotonic()
    base = {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "instance_id": source["instance_id"],
        "domain": source["domain_id"],
        "split": source["split"],
        "bucket": source["bucket"],
        "normalized_problem_hash": source.get("normalized_problem_hash"),
        "max_expansions_per_width": max_expansions,
        "timeout_seconds": timeout_seconds,
    }
    try:
        with _deadline(timeout_seconds):
            authority = PDDLStateAuthority.from_pddl(
                Path(source["domain_path"]).read_text(encoding="utf-8"),
                Path(source["problem_path"]).read_text(encoding="utf-8"),
            )
            search = run_iterative_width(authority, max_expansions=max_expansions)
            replay_valid = _replay_plan(authority, search.plan) if search.goal_reached else False
    except _QualificationTimeout:
        return {**base, "status": "timeout", "elapsed_seconds": monotonic() - started}
    except Exception as error:
        return {
            **base,
            "status": "unsupported_task",
            "error_type": type(error).__name__,
            "error": str(error),
            "elapsed_seconds": monotonic() - started,
        }

    attempts = [
        {
            "width": attempt.width,
            "expansion_count": attempt.expansion_count,
            "decision_count": attempt.decision_count,
            "generated_count": attempt.generated_count,
            "novelty_pruned_count": attempt.novelty_pruned_count,
            "duplicate_count": attempt.duplicate_count,
            "peak_frontier": attempt.peak_frontier,
            "termination": attempt.termination,
        }
        for attempt in search.attempts
    ]
    if search.goal_reached:
        status = "solved" if replay_valid else "invalid_replay"
    elif search.attempts[-1].termination == "frontier_exhausted":
        status = "width_cap_exhausted"
    else:
        status = "expansion_limit"
    return {
        **base,
        "status": status,
        "elapsed_seconds": monotonic() - started,
        "attempts": attempts,
        "solving_width": search.solving_width,
        "plan": [action.serialize() for action in search.plan],
        "replay_valid": replay_valid,
    }


def _qualify_bfws_instance(
    source: dict[str, Any],
    *,
    max_expansions: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = monotonic()
    base = {
        "schema_version": BFWS_QUALIFICATION_SCHEMA_VERSION,
        "instance_id": source["instance_id"],
        "domain": source["domain_id"],
        "split": source["split"],
        "bucket": source["bucket"],
        "normalized_problem_hash": source.get("normalized_problem_hash"),
        "max_expansions": max_expansions,
        "timeout_seconds": timeout_seconds,
    }
    try:
        with _deadline(timeout_seconds):
            authority = PDDLStateAuthority.from_pddl(
                Path(source["domain_path"]).read_text(encoding="utf-8"),
                Path(source["problem_path"]).read_text(encoding="utf-8"),
            )
            search = run_best_first_width(authority, max_expansions=max_expansions)
            replay_valid = _replay_plan(authority, search.plan) if search.goal_reached else False
    except _QualificationTimeout:
        return {**base, "status": "timeout", "elapsed_seconds": monotonic() - started}
    except Exception as error:
        return {
            **base,
            "status": "unsupported_task",
            "error_type": type(error).__name__,
            "error": str(error),
            "elapsed_seconds": monotonic() - started,
        }

    status = (
        "solved"
        if search.goal_reached and replay_valid
        else "invalid_replay"
        if search.goal_reached
        else "frontier_exhausted"
        if search.termination == "frontier_exhausted"
        else "expansion_limit"
    )
    return {
        **base,
        "status": status,
        "elapsed_seconds": monotonic() - started,
        "expansion_count": search.expansion_count,
        "decision_count": search.decision_count,
        "generated_count": search.generated_count,
        "duplicate_count": search.duplicate_count,
        "novelty_pruned_count": search.novelty_pruned_count,
        "residual_novelty_retained_count": search.residual_novelty_retained_count,
        "peak_frontier": search.peak_frontier,
        "termination": search.termination,
        "plan": [action.serialize() for action in search.plan],
        "replay_valid": replay_valid,
    }


def _replay_plan(authority: PDDLStateAuthority, plan: tuple[GroundedAction, ...]) -> bool:
    state = authority.initial_state
    for action in plan:
        state = authority.apply(state, action).target_state
    return authority.is_goal(state)


def _completed_instance_ids(path: Path, *, retry_statuses: set[str]) -> set[str]:
    return {
        instance_id
        for instance_id, row in _latest_results(path).items()
        if row["status"] not in retry_statuses
    }


def _latest_results(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    latest: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line:
            row = json.loads(line)
            latest[row["instance_id"]] = row
    return latest


def _grouped_status_counts(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, int]]:
    return {
        value: dict(sorted(Counter(row["status"] for row in rows if row[field] == value).items()))
        for value in sorted({str(row[field]) for row in rows})
    }


@contextmanager
def _deadline(seconds: int) -> Iterator[None]:
    def timeout_handler(_signum: int, _frame: object) -> None:
        raise _QualificationTimeout

    previous = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


__all__ = [
    "BFWS_QUALIFICATION_SCHEMA_VERSION",
    "QUALIFICATION_SCHEMA_VERSION",
    "qualify_bfws_curriculum",
    "qualify_curriculum",
]
