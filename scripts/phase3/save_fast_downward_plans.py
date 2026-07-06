from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .io_utils import file_sha256, read_jsonl, relpath, repo_root, write_json, write_jsonl


DEFAULT_ALIAS = "lama-first"
DEFAULT_TIMEOUT_SECONDS = 120
PLAN_DIRNAME = "plan"
PLAN_PREFIX = "sas_plan"


@dataclass(frozen=True)
class PlanSaveConfig:
    input_root: Path
    alias: str
    timeout_seconds: int
    force: bool
    limit: int | None
    planner_path: Path


def save_fast_downward_plans(config: PlanSaveConfig) -> dict[str, Any]:
    root = config.input_root.resolve()
    rows = read_jsonl(root / "accepted_manifest.jsonl")
    if config.limit is not None:
        rows = rows[: config.limit]

    records: list[dict[str, Any]] = []
    for manifest_index, row in enumerate(rows):
        records.append(_save_one_plan(row, manifest_index=manifest_index, config=config))

    summary = _build_summary(records, config=config, root=root)
    write_jsonl(root / "diagnostics" / "fast_downward_plan_saves.jsonl", records)
    write_json(root / "reports" / "fast_downward_plan_saves_summary.json", summary)
    return summary


def _save_one_plan(row: dict[str, Any], *, manifest_index: int, config: PlanSaveConfig) -> dict[str, Any]:
    root = config.input_root.resolve()
    instance_id = str(row.get("instance_id", ""))
    domain_id = str(row.get("domain_id", ""))
    split = str(row.get("split", ""))
    bucket = str(row.get("bucket", ""))
    domain_path = _resolve_manifest_path(str(row.get("domain_path", "")), root=root)
    problem_path = _resolve_manifest_path(str(row.get("problem_path", "")), root=root)
    instance_dir = domain_path.parent if domain_path is not None else None
    plan_dir = instance_dir / PLAN_DIRNAME if instance_dir is not None else None
    plan_prefix = plan_dir / PLAN_PREFIX if plan_dir is not None else None

    base: dict[str, Any] = {
        "manifest_index": manifest_index,
        "domain": domain_id,
        "instance_id": instance_id,
        "split": split,
        "bucket": bucket,
        "alias": config.alias,
        "domain_path": relpath(domain_path) if domain_path is not None else "",
        "problem_path": relpath(problem_path) if problem_path is not None else "",
        "plan_prefix": relpath(plan_prefix) if plan_prefix is not None else "",
    }

    if domain_path is None or problem_path is None or plan_dir is None or plan_prefix is None:
        return {**base, "status": "failed_missing_paths", "plan_paths": [], "message": "Manifest row is missing domain_path or problem_path."}
    if not _is_relative_to(domain_path, root) or not _is_relative_to(problem_path, root):
        return {
            **base,
            "status": "failed_path_outside_input_root",
            "plan_paths": [],
            "message": "Domain and problem paths must resolve under the selected input root.",
        }
    if plan_dir.exists() and plan_dir.is_symlink():
        return {
            **base,
            "status": "failed_unsafe_plan_dir",
            "plan_paths": [],
            "message": "Refusing to write plans through a symlinked plan directory.",
        }
    if not _is_relative_to(plan_dir.resolve(strict=False), root):
        return {
            **base,
            "status": "failed_path_outside_input_root",
            "plan_paths": [],
            "message": "Plan directory must resolve under the selected input root.",
        }
    if not domain_path.exists() or not problem_path.exists():
        return {**base, "status": "failed_missing_pddl", "plan_paths": [], "message": "Domain or problem PDDL file does not exist."}

    existing_plans = _plan_files(plan_prefix)
    if existing_plans and not config.force:
        return _success_record(base, existing_plans, status="skipped_existing_plan", command=[])

    plan_dir.mkdir(parents=True, exist_ok=True)
    if config.force:
        _remove_plan_files(plan_prefix)
        plan_dir.mkdir(parents=True, exist_ok=True)

    command = [
        str(config.planner_path),
        "--alias",
        config.alias,
        "--plan-file",
        str(plan_prefix),
        str(domain_path),
        str(problem_path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
            cwd=repo_root(),
        )
    except subprocess.TimeoutExpired as exc:
        return {
            **base,
            "status": "failed_planner_timeout",
            "plan_paths": [],
            "command": _command_label(command),
            "returncode": None,
            "message": f"Fast Downward timed out after {config.timeout_seconds}s.",
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
        }
    except OSError as exc:
        return {
            **base,
            "status": "failed_planner_error",
            "plan_paths": [],
            "command": _command_label(command),
            "returncode": None,
            "message": f"Fast Downward could not be launched: {exc}",
            "stdout_tail": "",
            "stderr_tail": "",
        }

    saved_plans = _plan_files(plan_prefix)
    if completed.returncode == 0 and saved_plans:
        return _success_record(base, saved_plans, status="success_plan_saved", command=command, returncode=completed.returncode)

    return {
        **base,
        "status": "failed_no_plan_saved" if completed.returncode == 0 else "failed_planner_error",
        "plan_paths": [relpath(path) for path in saved_plans],
        "command": _command_label(command),
        "returncode": completed.returncode,
        "message": "Fast Downward completed without a saved plan." if completed.returncode == 0 else "Fast Downward returned a non-zero exit code.",
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def _success_record(
    base: dict[str, Any],
    plan_paths: list[Path],
    *,
    status: str,
    command: list[str],
    returncode: int | None = None,
) -> dict[str, Any]:
    return {
        **base,
        "status": status,
        "plan_paths": [relpath(path) for path in plan_paths],
        "plan_hashes": {relpath(path): file_sha256(path) for path in plan_paths},
        "plan_count": len(plan_paths),
        "command": _command_label(command) if command else [],
        "returncode": returncode,
    }


def _build_summary(records: list[dict[str, Any]], *, config: PlanSaveConfig, root: Path) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for record in records:
        status = str(record.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
    saved = sum(1 for record in records if record.get("status") in {"success_plan_saved", "skipped_existing_plan"})
    return {
        "input_root": relpath(root),
        "planner_path": relpath(config.planner_path),
        "alias": config.alias,
        "timeout_seconds": config.timeout_seconds,
        "force": config.force,
        "limit": config.limit,
        "attempted_total": len(records),
        "plan_available_total": saved,
        "status_counts": status_counts,
    }


def _plan_files(plan_prefix: Path) -> list[Path]:
    parent = plan_prefix.parent
    if not parent.exists():
        return []
    prefix_name = plan_prefix.name
    return sorted(path for path in parent.iterdir() if path.is_file() and (path.name == prefix_name or path.name.startswith(f"{prefix_name}.")))


def _remove_plan_files(plan_prefix: Path) -> None:
    plan_dir = plan_prefix.parent
    if not plan_dir.exists():
        return
    for plan_path in _plan_files(plan_prefix):
        plan_path.unlink()
    sas_file = plan_dir / "output.sas"
    if sas_file.exists():
        sas_file.unlink()


def _resolve_path(path_text: str) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text)
    if path.is_absolute():
        return path
    return repo_root() / path


def _resolve_manifest_path(path_text: str, *, root: Path) -> Path | None:
    path = _resolve_path(path_text)
    if path is None:
        return None
    resolved = path.resolve(strict=False)
    if _is_relative_to(resolved, root):
        return resolved
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _command_label(command: Iterable[str]) -> list[str]:
    return [relpath(part) for part in command]


def main() -> None:
    parser = argparse.ArgumentParser(description="Save Fast Downward plan files for accepted curriculum PDDL instances.")
    parser.add_argument("--input-root", type=Path, default=Path("data/curriculum_pddl"))
    parser.add_argument("--alias", default=DEFAULT_ALIAS)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--planner-path", type=Path, default=Path("modules/downward/fast-downward.py"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = save_fast_downward_plans(
        PlanSaveConfig(
            input_root=args.input_root,
            alias=args.alias,
            timeout_seconds=args.timeout_seconds,
            force=args.force,
            limit=args.limit,
            planner_path=_resolve_path(str(args.planner_path)) or args.planner_path,
        )
    )
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(
            "Saved/confirmed "
            f"{summary['plan_available_total']} Fast Downward plans "
            f"for {summary['attempted_total']} manifest rows under {summary['input_root']}"
        )


if __name__ == "__main__":
    main()
