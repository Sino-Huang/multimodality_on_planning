from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .io_utils import repo_root
from .save_fast_downward_plans import PlanSaveConfig, save_fast_downward_plans


DEFAULT_BUCKET_TARGETS = {
    "train": {"easy": 155, "medium": 178, "hard": 111},
    "dev": {"easy": 16, "medium": 18, "hard": 10},
    "test": {"easy": 11, "medium": 16, "hard": 18},
}
DEFAULT_DOMAIN_ORDER = (
    "blocksworld",
    "depot",
    "grid",
    "logistics",
    "sokoban",
    "storage",
    "snake",
    "visitall",
    "ferry",
    "elevators",
    "driverlog",
    "freecell",
    "15puzzle",
    "gripper",
    "towers_of_hanoi",
)
BUCKETS = ("easy", "medium", "hard")
SPLITS = ("train", "dev", "test")


@dataclass(frozen=True)
class WorkflowConfig:
    config_path: Path
    shards_root: Path
    candidate_root: Path
    target_total: int
    max_generate_commands: int
    command_timeout_seconds: int
    attempt_window: int
    max_attempts_per_bucket: int
    seed: int
    candidate_multiplier: int
    save_plans: bool
    plan_limit: int | None
    plan_timeout_seconds: int
    planner_path: Path
    planner_alias: str
    final_root: Path
    update_root: bool
    verbose: bool


@dataclass(frozen=True)
class ShardState:
    accepted_total: int
    duplicate_hashes: int
    missing_hashes: int
    staging_entries: int
    counts_by_domain_split_bucket: dict[tuple[str, str, str], int]
    attempts_by_domain_split_bucket: dict[tuple[str, str, str], int]


def run_workflow(config: WorkflowConfig) -> dict[str, Any]:
    root = repo_root()
    shards_root = _resolve(config.shards_root, root=root)
    config_path = _resolve(config.config_path, root=root)
    candidate_root = _resolve(config.candidate_root, root=root)
    planner_path = _resolve(config.planner_path, root=root)

    before = inspect_shards(shards_root)
    _log(config, f"Initial shard state: {_state_summary(before)}")
    generation_records = run_generation_batches(
        config,
        config_path=config_path,
        shards_root=shards_root,
        initial_state=before,
    )
    after = inspect_shards(shards_root)
    _log(config, f"Post-generation shard state: {_state_summary(after)}")
    _log(config, f"Safety merging shards into {candidate_root}")
    merge_summary = merge_shards(shards_root=shards_root, candidate_root=candidate_root)
    _log(
        config,
        "Safety merge complete: "
        f"accepted_total={merge_summary.get('accepted_total')} "
        f"duplicate_accepted_problem_hashes={merge_summary.get('duplicate_accepted_problem_hashes')}",
    )
    final_summary = None
    final_root = _resolve(config.final_root, root=root)
    if config.update_root:
        _log(config, f"Updating final root {final_root} from verified shards")
        final_summary = update_final_root(
            shards_root=shards_root,
            final_root=final_root,
            safety_summary=merge_summary,
        )
        _log(
            config,
            "Final root update complete: "
            f"accepted_total={final_summary.get('accepted_total')} "
            f"duplicate_accepted_problem_hashes={final_summary.get('duplicate_accepted_problem_hashes')}",
        )
    plan_root = final_root if final_summary is not None else candidate_root
    plan_summary = None
    if config.save_plans:
        _log(
            config,
            f"Saving Fast Downward plans under {plan_root} "
            f"(limit={config.plan_limit if config.plan_limit is not None else 'all'})",
        )
        plan_summary = save_fast_downward_plans(
            PlanSaveConfig(
                input_root=plan_root,
                alias=config.planner_alias,
                timeout_seconds=config.plan_timeout_seconds,
                force=False,
                limit=config.plan_limit,
                planner_path=planner_path,
            )
        )
        _log(config, f"Plan save summary: {plan_summary}")

    return {
        "before": _state_summary(before),
        "after": _state_summary(after),
        "generation_records": generation_records,
        "merge_summary": merge_summary,
        "plan_summary": plan_summary,
        "plan_root": str(plan_root),
        "candidate_root": str(candidate_root),
        "final_root": str(final_root),
        "final_summary": final_summary,
        "updated_root": final_summary is not None,
    }


def run_generation_batches(
    config: WorkflowConfig,
    *,
    config_path: Path,
    shards_root: Path,
    initial_state: ShardState,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    state = initial_state
    commands_run = 0
    for domain in DEFAULT_DOMAIN_ORDER:
        shard_root = shards_root / domain
        if not shard_root.is_dir():
            continue
        for split in SPLITS:
            for bucket in BUCKETS:
                if commands_run >= config.max_generate_commands or state.accepted_total >= config.target_total:
                    _log(
                        config,
                        f"Stopping generation loop: commands_run={commands_run}, accepted_total={state.accepted_total}",
                    )
                    return records
                current = state.counts_by_domain_split_bucket.get((domain, split, bucket), 0)
                target = DEFAULT_BUCKET_TARGETS[split][bucket]
                if current >= target:
                    _log(config, f"Skip {domain} {split}/{bucket}: current={current} target={target}")
                    continue
                current_attempts = state.attempts_by_domain_split_bucket.get((domain, split, bucket), 0)
                if current_attempts >= config.max_attempts_per_bucket:
                    _log(
                        config,
                        f"Skip {domain} {split}/{bucket}: attempts={current_attempts} cap={config.max_attempts_per_bucket}",
                    )
                    records.append(
                        {
                            "domain": domain,
                            "split": split,
                            "bucket": bucket,
                            "status": "skipped_attempt_cap",
                            "current": current,
                            "target": target,
                            "attempts": current_attempts,
                        }
                    )
                    continue
                max_attempts = min(current_attempts + config.attempt_window, config.max_attempts_per_bucket)
                _log(
                    config,
                    f"Run {commands_run + 1}: {domain} {split}/{bucket} "
                    f"current={current} target={target} attempts={current_attempts}->{max_attempts}",
                )
                command = [
                    sys.executable,
                    "-m",
                    "src.data_collect",
                    "generate",
                    "--config",
                    str(config_path),
                    "--output",
                    str(shard_root),
                    "--domains",
                    domain,
                    "--splits",
                    split,
                    "--quota",
                    f"{bucket}={target}",
                    "--seed",
                    str(config.seed),
                    "--max-attempts-per-bucket",
                    str(max_attempts),
                    "--candidate-multiplier",
                    str(config.candidate_multiplier),
                    "--json",
                ]
                record = _run_generate_command(
                    command,
                    timeout_seconds=config.command_timeout_seconds,
                    domain=domain,
                    split=split,
                    bucket=bucket,
                    current=current,
                    target=target,
                    attempts_before=current_attempts,
                    attempts_after=max_attempts,
                )
                commands_run += 1
                state = inspect_shards(shards_root)
                record["accepted_total_after"] = state.accepted_total
                record["duplicate_hashes_after"] = state.duplicate_hashes
                records.append(record)
                _log(
                    config,
                    f"Result {domain} {split}/{bucket}: status={record['status']} "
                    f"accepted_total={state.accepted_total} duplicate_hashes={state.duplicate_hashes}",
                )
                if state.duplicate_hashes or state.missing_hashes:
                    raise RuntimeError(f"Shard integrity failed after generation: {_state_summary(state)}")
    return records


def _log(config: WorkflowConfig, message: str) -> None:
    if config.verbose:
        print(f"[extend-curriculum] {message}", file=sys.stderr, flush=True)


def inspect_shards(shards_root: Path) -> ShardState:
    rows_by_hash: list[str | None] = []
    counts: Counter[tuple[str, str, str]] = Counter()
    attempts: Counter[tuple[str, str, str]] = Counter()
    accepted_total = 0
    for shard_root in sorted(path for path in shards_root.iterdir() if path.is_dir()):
        domain = shard_root.name
        accepted = _read_jsonl(shard_root / "accepted_manifest.jsonl")
        rejections = _read_jsonl(shard_root / "rejections.jsonl")
        accepted_total += len(accepted)
        for row in accepted:
            split = str(row["split"])
            bucket = str(row["bucket"])
            target_bucket = str(row.get("difficulty_target") or bucket)
            rows_by_hash.append(row.get("normalized_problem_hash"))
            counts[(domain, split, bucket)] += 1
            attempts[(domain, split, target_bucket)] += 1
        for row in rejections:
            attempts[(domain, str(row["split"]), str(row["bucket"]))] += 1
    return ShardState(
        accepted_total=accepted_total,
        duplicate_hashes=len(rows_by_hash) - len(set(rows_by_hash)),
        missing_hashes=sum(1 for value in rows_by_hash if not value),
        staging_entries=sum(1 for _ in shards_root.glob("**/.staging/**")),
        counts_by_domain_split_bucket=dict(counts),
        attempts_by_domain_split_bucket=dict(attempts),
    )


def merge_shards(*, shards_root: Path, candidate_root: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "src.data_collect",
        "merge-shards",
        "--shards-root",
        str(shards_root),
        "--output",
        str(candidate_root),
        "--force",
        "--json",
    ]
    completed = subprocess.run(command, check=False, text=True, capture_output=True, cwd=repo_root())
    if completed.returncode != 0:
        raise RuntimeError(f"merge-shards failed:\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
    payload = json.loads(completed.stdout)
    summary = dict(payload["summary"])
    if int(summary.get("duplicate_accepted_problem_hashes", -1)) != 0:
        raise RuntimeError(f"Staged merge has duplicate hashes: {summary}")
    return summary


def update_final_root(
    *,
    shards_root: Path,
    final_root: Path,
    safety_summary: dict[str, Any],
) -> dict[str, Any]:
    if int(safety_summary.get("duplicate_accepted_problem_hashes", -1)) != 0:
        raise RuntimeError("Refusing to update final root because safety merge has duplicate hashes")
    if int(safety_summary.get("accepted_total", 0)) <= 0:
        raise RuntimeError("Refusing to update final root from an empty safety merge")
    if final_root == shards_root or final_root in shards_root.parents:
        raise RuntimeError("Refusing to update final root inside the shard root")
    command = [
        sys.executable,
        "-m",
        "src.data_collect",
        "merge-shards",
        "--shards-root",
        str(shards_root),
        "--output",
        str(final_root),
        "--force",
        "--json",
    ]
    completed = subprocess.run(command, check=False, text=True, capture_output=True, cwd=repo_root())
    if completed.returncode != 0:
        raise RuntimeError(f"final root update failed:\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
    payload = json.loads(completed.stdout)
    summary = dict(payload["summary"])
    if int(summary.get("accepted_total", -1)) != int(safety_summary.get("accepted_total", -2)):
        raise RuntimeError(f"Final root total differs from safety merge: final={summary} safety={safety_summary}")
    if int(summary.get("duplicate_accepted_problem_hashes", -1)) != 0:
        raise RuntimeError(f"Final root update has duplicate hashes: {summary}")
    return summary


def _run_generate_command(
    command: list[str],
    *,
    timeout_seconds: int,
    domain: str,
    split: str,
    bucket: str,
    current: int,
    target: int,
    attempts_before: int,
    attempts_after: int,
) -> dict[str, Any]:
    base = {
        "domain": domain,
        "split": split,
        "bucket": bucket,
        "current": current,
        "target": target,
        "attempts_before": attempts_before,
        "attempts_after": attempts_after,
        "command": command,
    }
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            cwd=repo_root(),
        )
    except subprocess.TimeoutExpired:
        return {**base, "status": "timeout"}
    if completed.returncode != 0:
        raise RuntimeError(
            f"generation command failed for {domain} {split}/{bucket}:\n"
            f"STDOUT:\n{completed.stdout[-2000:]}\nSTDERR:\n{completed.stderr[-4000:]}"
        )
    payload = json.loads(completed.stdout)
    return {**base, "status": "completed", "summary": payload.get("summary", {})}


def _state_summary(state: ShardState) -> dict[str, int]:
    return {
        "accepted_total": state.accepted_total,
        "duplicate_hashes": state.duplicate_hashes,
        "missing_hashes": state.missing_hashes,
        "staging_entries": state.staging_entries,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _resolve(path: Path, *, root: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def _positive_int(raw_value: str) -> int:
    value = int(raw_value)
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return value


def _optional_non_negative_int(raw_value: str) -> int:
    value = int(raw_value)
    if value < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resumably extend curriculum PDDL shards, staged-merge, verify duplicates, and optionally save Fast Downward plans.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", type=Path, default=Path("src/data_collect/configs/curriculum_15_domains.yaml"))
    parser.add_argument("--shards-root", type=Path, default=Path("data/curriculum_pddl_shards"))
    parser.add_argument("--candidate-root", type=Path, default=Path("/tmp/opencode/curriculum_pddl_candidate_auto"))
    parser.add_argument("--target-total", type=_positive_int, default=7995)
    parser.add_argument("--max-generate-commands", type=_optional_non_negative_int, default=60)
    parser.add_argument("--command-timeout-seconds", type=_positive_int, default=180)
    parser.add_argument("--attempt-window", type=_positive_int, default=120)
    parser.add_argument("--max-attempts-per-bucket", type=_positive_int, default=1600)
    parser.add_argument("--seed", type=int, default=20260628)
    parser.add_argument("--candidate-multiplier", type=_positive_int, default=1)
    parser.add_argument("--save-plans", action="store_true")
    parser.add_argument(
        "--plan-limit",
        type=_optional_non_negative_int,
        default=None,
        help="Maximum accepted manifest rows to plan-save. Omit to attempt all rows.",
    )
    parser.add_argument("--plan-timeout-seconds", type=_positive_int, default=120)
    parser.add_argument("--planner-path", type=Path, default=Path("modules/downward/fast-downward.py"))
    parser.add_argument("--planner-alias", default="lama-first")
    parser.add_argument("--final-root", type=Path, default=Path("data/curriculum_pddl"))
    parser.add_argument(
        "--update-root",
        action="store_true",
        help="After a successful safety merge, update --final-root from the shards. This replaces the final root with the merged superset.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print live progress logs to stderr.")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(tuple(argv) if argv is not None else None)
    config = WorkflowConfig(
        config_path=args.config,
        shards_root=args.shards_root,
        candidate_root=args.candidate_root,
        target_total=args.target_total,
        max_generate_commands=args.max_generate_commands,
        command_timeout_seconds=args.command_timeout_seconds,
        attempt_window=args.attempt_window,
        max_attempts_per_bucket=args.max_attempts_per_bucket,
        seed=args.seed,
        candidate_multiplier=args.candidate_multiplier,
        save_plans=args.save_plans,
        plan_limit=args.plan_limit,
        plan_timeout_seconds=args.plan_timeout_seconds,
        planner_path=args.planner_path,
        planner_alias=args.planner_alias,
        final_root=args.final_root,
        update_root=args.update_root,
        verbose=args.verbose,
    )
    result = run_workflow(config)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        after = result["after"]
        merge = result["merge_summary"]
        print(
            "Workflow complete: "
            f"shards={after['accepted_total']} duplicate_hashes={after['duplicate_hashes']} "
            f"candidate={result['candidate_root']} merged={merge['accepted_total']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
