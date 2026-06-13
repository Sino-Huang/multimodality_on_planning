from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Sequence

from src.data_collect.metadata import AcceptedInstanceMetadata


DEFAULT_DATASET_ROOT = Path("data/curriculum_pddl")
MANIFEST_FILENAME = "accepted_manifest.jsonl"
SUMMARY_FILENAME = "summary.json"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"{path.name} is missing at {path}")
    records: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path} must contain JSON objects")
        records.append(payload)
    return records


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path.name} is missing at {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _strip_pddl_comments(text: str) -> str:
    return "\n".join(line.split(";", 1)[0] for line in text.splitlines())


def _extract_balanced_block(text: str, token: str) -> str | None:
    match = re.search(re.escape(token), text, flags=re.IGNORECASE)
    if match is None:
        return None
    start = match.start()
    depth = 0
    for index in range(start, len(text)):
        character = text[index]
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return text[start : index + 1].strip()
    return None


def _extract_pddl_name(text: str, label: str) -> str | None:
    match = re.search(rf"\(define\s*\({label}\s+([^\s()]+)\)", text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _extract_action_vocabulary(domain_text: str) -> tuple[list[str], str | None]:
    cleaned = _strip_pddl_comments(domain_text)
    actions: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"\(:action\s+([^\s()]+)", cleaned, flags=re.IGNORECASE):
        action_name = match.group(1)
        if action_name not in seen:
            seen.add(action_name)
            actions.append(action_name)
    if actions:
        return actions, None
    return [], "no parseable :action blocks were found in the domain PDDL"


def _build_problem_view(problem_text: str) -> dict[str, Any]:
    cleaned = _strip_pddl_comments(problem_text)
    problem_name = _extract_pddl_name(cleaned, "problem")
    domain_name_match = re.search(r"\(:domain\s+([^\s()]+)\)", cleaned, flags=re.IGNORECASE)
    domain_name = domain_name_match.group(1) if domain_name_match else None
    objects_block = _extract_balanced_block(cleaned, "(:objects")
    init_block = _extract_balanced_block(cleaned, "(:init")
    goal_block = _extract_balanced_block(cleaned, "(:goal")

    return {
        "problem_name": problem_name,
        "domain_name": domain_name,
        "objects_block": objects_block,
        "init_block": init_block,
        "goal_block": goal_block,
    }


def _normalize_instance_metadata(record: dict[str, Any]) -> AcceptedInstanceMetadata:
    return AcceptedInstanceMetadata.from_dict(record)


def _resolve_existing_path(raw_path: str, *, fallback_dir: Path | None = None) -> Path:
    path = Path(raw_path)
    if path.exists():
        return path
    if fallback_dir is not None:
        candidate = fallback_dir / raw_path
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"missing file: {raw_path}")


def load_example_slice(dataset_root: Path | str, domain: str, split: str, index: int) -> dict[str, Any]:
    root = Path(dataset_root)
    summary_path = root / SUMMARY_FILENAME
    manifest_path = root / MANIFEST_FILENAME
    summary = _load_json_object(summary_path)
    accepted_domains = set(summary.get("accepted_by_domain", {}))
    accepted_splits = set(summary.get("accepted_by_split", {}))

    if domain not in accepted_domains:
        raise ValueError(f"invalid domain {domain!r}; available domains: {sorted(accepted_domains)}")
    if split not in accepted_splits:
        raise ValueError(f"invalid split {split!r}; available splits: {sorted(accepted_splits)}")
    if index < 0:
        raise ValueError(f"index must be non-negative, got {index}")

    records = _load_jsonl(manifest_path)
    filtered_records = [record for record in records if record.get("domain_id") == domain and record.get("split") == split]
    if index >= len(filtered_records):
        raise IndexError(
            f"index {index} out of range for {domain}/{split}; only {len(filtered_records)} accepted instances exist"
        )

    record = filtered_records[index]
    instance = _normalize_instance_metadata(record)
    instance_dir = Path(instance.domain_path).parent

    domain_path = _resolve_existing_path(instance.domain_path)
    problem_path = _resolve_existing_path(instance.problem_path)
    render_result_path = _resolve_existing_path(instance.render_result_path)
    render_result = _load_json_object(render_result_path)

    trace_raw_path = ""
    for artifact_path in instance.render_artifact_paths:
        if artifact_path.endswith("trace.vfg.json"):
            trace_raw_path = artifact_path
            break
    if not trace_raw_path:
        trace_raw_path = str(render_result.get("trace_path") or "")
    trace_path = _resolve_existing_path(trace_raw_path, fallback_dir=instance_dir if trace_raw_path else None)

    frame_paths: list[str] = []
    for artifact_path in instance.render_artifact_paths:
        if artifact_path.endswith(".png"):
            frame_paths.append(artifact_path)
    if not frame_paths:
        render_frame_payload = render_result.get("frame_paths")
        if isinstance(render_frame_payload, list):
            frame_paths.extend(str(item) for item in render_frame_payload)
    if not frame_paths:
        raise ValueError(f"no render frame paths were recorded for {instance.instance_id}")

    resolved_frame_paths = [str(_resolve_existing_path(frame_path, fallback_dir=instance_dir)) for frame_path in frame_paths]

    domain_text = domain_path.read_text(encoding="utf-8")
    problem_text = problem_path.read_text(encoding="utf-8")
    action_vocabulary, action_vocabulary_empty_reason = _extract_action_vocabulary(domain_text)
    goal_or_problem_view = _build_problem_view(problem_text)
    problem_name = goal_or_problem_view.get("problem_name") or instance.instance_id
    goal_block = goal_or_problem_view.get("goal_block") or ""
    object_block = goal_or_problem_view.get("objects_block") or ""
    language_or_text_description = (
        f"{instance.domain_id}/{instance.split}/{instance.bucket} instance {problem_name}; "
        f"goal={goal_block or 'unknown'}; objects={object_block or 'unknown'}"
    )

    payload: dict[str, Any] = {
        "instance_id": instance.instance_id,
        "domain": instance.domain_id,
        "split": instance.split,
        "bucket": instance.bucket,
        "domain_pddl": domain_text,
        "problem_pddl": problem_text,
        "render_trace": str(trace_path),
        "render_trace_payload": json.loads(trace_path.read_text(encoding="utf-8")),
        "render_frames": resolved_frame_paths,
        "goal_or_problem_view": goal_or_problem_view,
        "language_or_text_description": language_or_text_description,
        "render_result_path": str(render_result_path),
        "domain_pddl_path": str(domain_path),
        "problem_pddl_path": str(problem_path),
    }
    if action_vocabulary:
        payload["action_vocabulary"] = action_vocabulary
    else:
        payload["action_vocabulary"] = []
        payload["action_vocabulary_empty_reason"] = action_vocabulary_empty_reason or "action vocabulary could not be parsed"
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect one accepted curriculum instance slice.")
    parser.add_argument("--dataset", type=str, default=str(DEFAULT_DATASET_ROOT), help="Merged curriculum dataset root.")
    parser.add_argument("--domain", type=str, required=True, help="Domain id to filter by.")
    parser.add_argument("--split", type=str, required=True, help="Split name to filter by.")
    parser.add_argument("--index", type=int, required=True, help="Zero-based index within the filtered slice.")
    parser.add_argument("--json", action="store_true", help="Emit JSON (default behavior is also JSON).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        payload = load_example_slice(args.dataset, args.domain, args.split, args.index)
    except (FileNotFoundError, IndexError, ValueError, json.JSONDecodeError) as error:
        parser.exit(status=1, message=f"{error}\n")

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


__all__ = ["build_parser", "load_example_slice", "main"]
