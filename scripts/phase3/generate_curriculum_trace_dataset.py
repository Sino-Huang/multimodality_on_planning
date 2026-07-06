from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Final, TypeAlias

from scripts.phase3.pipeline import DEFAULT_PLANNERS, generate_supervised_data

JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
JSONRecord: TypeAlias = dict[str, JSONValue]
DEFAULT_INPUT_ROOT: Final = Path("data/curriculum_pddl")
DEFAULT_OUTPUT_ROOT: Final = Path("outputs/phase3_curriculum_traces")
DEFAULT_LOCAL_MAX_APPLICABLE_ACTIONS: Final = 2000
DEFAULT_LOCAL_MAX_MUTEX_PAIRS: Final = 1000000
DEFAULT_LOCAL_GRAPHPLAN_MAX_EXPANSIONS: Final = 250000
DEFAULT_LOCAL_FF_BEST_FIRST_MAX_EXPANSIONS: Final = 500
DEFAULT_LOCAL_IW_WIDTH: Final = 3
DEFAULT_LOCAL_IW_MAX_WIDTH: Final = 3
DEFAULT_LOCAL_IW_NOVELTY_MAX_EXPANSIONS: Final = 500
DEFAULT_LOCAL_IW_RECOVERY_TRACE_STEPS: Final = 20
DEFAULT_LOCAL_SERIAL_RECOVERY_MAX_EXPANSIONS: Final = 250000
DEFAULT_MAX_JSONL_TARGET_CHARS: Final = 10000000
EXTERNAL_PLANNER_ENV_VARS: Final = ("PHASE3_FF_PLANNER", "PHASE3_IW_PLANNER", "PHASE3_GRAPHPLAN_PLANNER")


def main() -> int:
    args = _parse_args()
    if not args.use_external_planners:
        for env_var in EXTERNAL_PLANNER_ENV_VARS:
            os.environ.pop(env_var, None)
    selected_rows = _selected_manifest_rows(args)
    if not selected_rows:
        raise RuntimeError("no accepted curriculum instances matched the requested filters")
    if _needs_filtered_input(args):
        Path("tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="phase3_curriculum_trace_input_", dir="tmp") as temp_root:
            input_root = Path(temp_root)
            _write_filtered_input(input_root, selected_rows)
            result = _generate_and_extract(input_root, args.output_root, args, selected_rows)
    else:
        result = _generate_and_extract(args.input_root, args.output_root, args, selected_rows)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if int(result["extracted_trace_count"]) > 0 else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Phase 3 planner trace dataset files for accepted curriculum PDDL instances.")
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--planner", choices=DEFAULT_PLANNERS, action="append", dest="planners")
    parser.add_argument("--domain", action="append", default=[])
    parser.add_argument("--split", choices=("train", "dev", "test"), action="append", default=[])
    parser.add_argument("--bucket", action="append", default=[])
    parser.add_argument("--instance-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--local-max-applicable-actions", type=int, default=DEFAULT_LOCAL_MAX_APPLICABLE_ACTIONS)
    parser.add_argument("--local-graphplan-max-expansions", type=int, default=DEFAULT_LOCAL_GRAPHPLAN_MAX_EXPANSIONS)
    parser.add_argument("--local-ff-best-first-max-expansions", type=int, default=DEFAULT_LOCAL_FF_BEST_FIRST_MAX_EXPANSIONS)
    parser.add_argument("--local-iw-width", type=int, default=DEFAULT_LOCAL_IW_WIDTH)
    parser.add_argument("--local-iw-max-width", type=int, default=DEFAULT_LOCAL_IW_MAX_WIDTH)
    parser.add_argument("--local-iw-novelty-max-expansions", type=int, default=DEFAULT_LOCAL_IW_NOVELTY_MAX_EXPANSIONS)
    parser.add_argument("--local-iw-recovery-trace-steps", type=int, default=DEFAULT_LOCAL_IW_RECOVERY_TRACE_STEPS)
    parser.add_argument("--local-serial-recovery-max-expansions", type=int, default=DEFAULT_LOCAL_SERIAL_RECOVERY_MAX_EXPANSIONS)
    parser.add_argument("--local-max-mutex-pairs", type=int, default=DEFAULT_LOCAL_MAX_MUTEX_PAIRS)
    parser.add_argument("--max-jsonl-target-chars", type=int, default=DEFAULT_MAX_JSONL_TARGET_CHARS)
    parser.add_argument("--quiet", action="store_true", help="Suppress JSON-lines progress logs on stderr.")
    parser.add_argument("--use-external-planners", action="store_true", help="Keep PHASE3_*_PLANNER env vars instead of forcing local full-trace fallback.")
    return parser.parse_args()


def _generate_and_extract(input_root: Path, output_root: Path, args: argparse.Namespace, selected_rows: list[JSONRecord]) -> JSONRecord:
    planners = tuple(args.planners or DEFAULT_PLANNERS)
    _log_progress(args, {"input_instance_count": len(selected_rows), "output_root": output_root.as_posix(), "phase": "generation_started", "planners": list(planners)})
    report = generate_supervised_data(input_root, output_root, planners=planners, limits=_limits(args), progress_callback=_progress_callback(args))
    _log_progress(args, {"phase": "trace_extraction_started", "output_root": output_root.as_posix()})
    extracted = _extract_traces(output_root)
    _log_progress(args, {"extracted_trace_count": len(extracted), "phase": "trace_extraction_finished", "trace_dir": (output_root / "traces").as_posix()})
    attempts = _planner_attempts(output_root)
    status_summary = Counter(str(row["status"]) for row in attempts)
    return {
        "attempt_status_summary": dict(sorted(status_summary.items())),
        "extracted_trace_count": len(extracted),
        "input_instance_count": len(selected_rows),
        "output_root": output_root.as_posix(),
        "planners": list(planners),
        "report": report["summary"],
        "trace_dir": (output_root / "traces").as_posix(),
    }


def _limits(args: argparse.Namespace) -> dict[str, int]:
    return {
        "local_max_applicable_actions": args.local_max_applicable_actions,
        "local_graphplan_max_expansions": args.local_graphplan_max_expansions,
        "local_ff_best_first_max_expansions": args.local_ff_best_first_max_expansions,
        "local_iw_width": args.local_iw_width,
        "local_iw_max_width": args.local_iw_max_width,
        "local_iw_novelty_max_expansions": args.local_iw_novelty_max_expansions,
        "local_iw_recovery_trace_steps": args.local_iw_recovery_trace_steps,
        "local_serial_recovery_max_expansions": args.local_serial_recovery_max_expansions,
        "local_max_mutex_pairs": args.local_max_mutex_pairs,
        "max_jsonl_target_chars": args.max_jsonl_target_chars,
    }


def _progress_callback(args: argparse.Namespace):
    if args.quiet:
        return None

    def callback(event: dict[str, JSONValue]) -> None:
        _log_progress(args, event)

    return callback


def _log_progress(args: argparse.Namespace, event: dict[str, JSONValue]) -> None:
    if args.quiet:
        return
    print(json.dumps(event, sort_keys=True), file=sys.stderr, flush=True)


def _selected_manifest_rows(args: argparse.Namespace) -> list[JSONRecord]:
    rows = _read_manifest(args.input_root / "accepted_manifest.jsonl")
    selected = [row for row in rows if _matches_filters(row, args)]
    selected.sort(key=lambda row: (str(row.get("domain_id", "")), str(row.get("split", "")), str(row.get("bucket", "")), str(row.get("instance_id", ""))))
    if args.limit is None:
        return selected
    return selected[: args.limit]


def _read_manifest(manifest_path: Path) -> list[JSONRecord]:
    return [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line]


def _matches_filters(row: JSONRecord, args: argparse.Namespace) -> bool:
    return (
        _matches_filter(row, "domain_id", args.domain)
        and _matches_filter(row, "split", args.split)
        and _matches_filter(row, "bucket", args.bucket)
        and _matches_filter(row, "instance_id", args.instance_id)
    )


def _matches_filter(row: JSONRecord, key: str, accepted: list[str]) -> bool:
    return not accepted or str(row.get(key, "")) in accepted


def _needs_filtered_input(args: argparse.Namespace) -> bool:
    return bool(args.domain or args.split or args.bucket or args.instance_id or args.limit is not None)


def _write_filtered_input(input_root: Path, rows: list[JSONRecord]) -> None:
    manifest_text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    input_root.mkdir(parents=True, exist_ok=True)
    (input_root / "accepted_manifest.jsonl").write_text(manifest_text, encoding="utf-8")
    (input_root / "summary.json").write_text(json.dumps({"accepted_total": len(rows)}, sort_keys=True) + "\n", encoding="utf-8")


def _extract_traces(output_root: Path) -> list[Path]:
    trace_root = output_root / "traces"
    trace_root.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    for split in ("train", "dev", "test"):
        for row in _read_jsonl_if_exists(output_root / f"{split}.jsonl"):
            planner = _safe_path_part(row["planner"], "planner")
            instance_id = _safe_path_part(row["instance_id"], "instance_id")
            destination = trace_root / _safe_path_part(row["domain"], "domain") / _safe_path_part(row["split"], "split") / instance_id
            destination.mkdir(parents=True, exist_ok=True)
            trace_path = destination / f"{planner}.planner_trace.json"
            example_path = destination / f"{planner}.full_example.json"
            trace_path.write_text(json.dumps(row["supervised_target"]["planner_trace"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
            example_path.write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            extracted.append(trace_path)
    return sorted(extracted)


def _safe_path_part(value: JSONValue, field: str) -> str:
    text = str(value)
    path = Path(text)
    if path.is_absolute() or text in {"", ".", ".."} or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeError(f"unsafe trace path component for {field}: {text}")
    return text


def _read_jsonl_if_exists(path: Path) -> list[JSONRecord]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _planner_attempts(output_root: Path) -> list[JSONRecord]:
    return _read_jsonl_if_exists(output_root / "diagnostics" / "planner_attempts.jsonl")


if __name__ == "__main__":
    raise SystemExit(main())
