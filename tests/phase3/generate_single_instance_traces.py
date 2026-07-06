from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Final, TypeAlias

from scripts.phase3.pipeline import DEFAULT_PLANNERS, generate_supervised_data

JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
DEFAULT_INSTANCE_ID: Final = "blocksworld-dev-easy-0004"
DEFAULT_LOCAL_MAX_APPLICABLE_ACTIONS: Final = 10000
DEFAULT_LOCAL_MAX_MUTEX_PAIRS: Final = 1000000
DEFAULT_MAX_JSONL_TARGET_CHARS: Final = 10000000
EXTERNAL_PLANNER_ENV_VARS: Final = ("PHASE3_FF_PLANNER", "PHASE3_IW_PLANNER", "PHASE3_GRAPHPLAN_PLANNER")


def main() -> int:
    args = _parse_args()
    instance_id = args.instance_id
    input_root = args.input_root or Path("tmp") / f"phase3_single_{instance_id}"
    output_root = args.output_root or Path("outputs") / "phase3_traces" / instance_id
    if not args.use_external_planners:
        for env_var in EXTERNAL_PLANNER_ENV_VARS:
            os.environ.pop(env_var, None)
    _prepare_input_root(args.manifest, input_root, instance_id)
    report = generate_supervised_data(input_root, output_root, planners=DEFAULT_PLANNERS, limits=_limits(args))
    extracted = _extract_traces(output_root)
    if not args.keep_input:
        shutil.rmtree(input_root)
    missing = sorted(set(DEFAULT_PLANNERS) - set(extracted))
    print(json.dumps({"report": report["summary"], "output_root": output_root.as_posix(), "trace_dir": (output_root / "traces").as_posix(), "extracted_planners": extracted}, indent=2, sort_keys=True))
    if missing:
        print(json.dumps({"missing_traces": missing, "planner_attempts": _planner_attempts(output_root)}, indent=2, sort_keys=True))
        return 1
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Phase 3 planner traces for one accepted curriculum instance.")
    parser.add_argument("--instance-id", default=DEFAULT_INSTANCE_ID)
    parser.add_argument("--manifest", type=Path, default=Path("data/curriculum_pddl/accepted_manifest.jsonl"))
    parser.add_argument("--input-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--local-max-applicable-actions", type=int, default=DEFAULT_LOCAL_MAX_APPLICABLE_ACTIONS)
    parser.add_argument("--local-max-mutex-pairs", type=int, default=DEFAULT_LOCAL_MAX_MUTEX_PAIRS)
    parser.add_argument("--max-jsonl-target-chars", type=int, default=DEFAULT_MAX_JSONL_TARGET_CHARS)
    parser.add_argument("--keep-input", action="store_true")
    parser.add_argument("--use-external-planners", action="store_true", help="Keep PHASE3_*_PLANNER env vars instead of forcing local full-trace fallback.")
    return parser.parse_args()


def _limits(args: argparse.Namespace) -> dict[str, int]:
    return {"local_max_applicable_actions": args.local_max_applicable_actions, "local_max_mutex_pairs": args.local_max_mutex_pairs, "max_jsonl_target_chars": args.max_jsonl_target_chars}


def _prepare_input_root(manifest_path: Path, input_root: Path, instance_id: str) -> None:
    selected = _manifest_row(manifest_path, instance_id)
    if input_root.exists():
        shutil.rmtree(input_root)
    input_root.mkdir(parents=True)
    (input_root / "accepted_manifest.jsonl").write_text(json.dumps(selected, sort_keys=True) + "\n", encoding="utf-8")
    (input_root / "summary.json").write_text(json.dumps({"accepted_total": 1}, sort_keys=True) + "\n", encoding="utf-8")


def _manifest_row(manifest_path: Path, instance_id: str) -> dict[str, JSONValue]:
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row: dict[str, JSONValue] = json.loads(line)
        if row.get("instance_id") == instance_id:
            return row
    raise RuntimeError(f"instance_id not found in {manifest_path}: {instance_id}")


def _extract_traces(output_root: Path) -> list[str]:
    trace_dir = output_root / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []
    for split in ("train", "dev", "test"):
        jsonl_path = output_root / f"{split}.jsonl"
        if not jsonl_path.exists():
            continue
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            planner = str(row["planner"])
            trace = row["supervised_target"]["planner_trace"]
            (trace_dir / f"{planner}.planner_trace.json").write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            (trace_dir / f"{planner}.full_example.json").write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            extracted.append(planner)
    return sorted(extracted)


def _planner_attempts(output_root: Path) -> list[dict[str, JSONValue]]:
    attempts_path = output_root / "diagnostics" / "planner_attempts.jsonl"
    return [json.loads(line) for line in attempts_path.read_text(encoding="utf-8").splitlines() if line]


if __name__ == "__main__":
    raise SystemExit(main())
