"""Diagnose retained issue-54 BFS model failures without running learning."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from examples.planning_benchmark_slice.model_search_episode import _parse_model_output
from examples.planning_benchmark_slice.qwen_text_policy import qwen_text_policy_messages

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUTPUTS = _REPO_ROOT / "outputs" / "bfs_phase"
_DATASET = _REPO_ROOT / "data" / "bfs_pilot_v3" / "ms-swift-process"
_MATERIALIZATION_REPORT = _REPO_ROOT / "data" / "bfs_pilot_v3" / "materialization-report.json"
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v3.json"
_DEFAULT_REPORT_ROOT = _OUTPUTS / "issue54-v3-diagnostics"
_SUCCESSOR_OUTPUT_TOKENS = 384


def classify_rejection(reason: str, raw_output: str) -> str:
    """Map one retained rejection to a stable diagnostic category."""

    try:
        json.loads(raw_output)
    except json.JSONDecodeError as error:
        if "Unterminated string" in reason or "Unterminated string" in error.msg:
            return "truncated_json"
        return "invalid_json"
    mappings = (
        ("successors must be appended at the frontier tail", "frontier_tail"),
        ("successor target was already visited", "already_visited"),
        ("retirement omitted unvisited successors", "omitted_successors"),
        ("first BFS successor must retire", "first_successor_retirement"),
        ("transition source must be the current expansion state", "wrong_source"),
        ("action is not applicable", "inapplicable_action"),
        ("retirement must retire the current frontier head", "wrong_retirement"),
    )
    for fragment, category in mappings:
        if fragment in reason:
            return category
    return "other_runtime_rejection"


def analyze_episode_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize policy failures without decoding the embedded evidence bundle."""

    evidence = payload.get("evidence")
    events = evidence.get("policy_events", []) if isinstance(evidence, dict) else []
    categories: Counter[str] = Counter()
    contracts: Counter[str] = Counter()
    rejected_pairs: Counter[str] = Counter()
    rejected_count = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        model_input = event.get("input")
        if isinstance(model_input, dict):
            search_memory = model_input.get("search_memory")
            if isinstance(search_memory, dict):
                contracts[str(search_memory.get("context_type") or "missing")] += 1
        if event.get("status") != "rejected":
            continue
        rejected_count += 1
        raw_output = str(event.get("raw_output") or "")
        runtime_result = event.get("runtime_result")
        reason = str(runtime_result.get("reason") or "") if isinstance(runtime_result, dict) else ""
        categories[classify_rejection(reason, raw_output)] += 1
        pair = json.dumps(
            {"input": model_input, "raw_output": raw_output},
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        rejected_pairs[pair] += 1
    return {
        "decision_count": len(events),
        "deterministic_replay_count": sum(count - 1 for count in rejected_pairs.values()),
        "failure_categories": dict(sorted(categories.items())),
        "goal_reached": bool(payload.get("result", {}).get("goal_reached")),
        "input_contracts": dict(sorted(contracts.items())),
        "rejected_count": rejected_count,
    }


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs-root", type=Path, default=_OUTPUTS)
    parser.add_argument("--dataset-root", type=Path, default=_DATASET)
    parser.add_argument("--freeze", type=Path, default=_FREEZE)
    parser.add_argument("--report-root", type=Path, default=_DEFAULT_REPORT_ROOT)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--skip-tokenizer", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)
    if args.progress_every <= 0:
        raise ValueError("progress interval must be positive")

    outputs_root = args.outputs_root.expanduser().resolve()
    dataset_root = args.dataset_root.expanduser().resolve()
    freeze_path = args.freeze.expanduser().resolve()
    report_root = args.report_root.expanduser().resolve()
    episode_paths = _episode_paths(outputs_root)
    plan = {
        "dataset_root": str(dataset_root),
        "episode_count": len(episode_paths),
        "freeze": str(freeze_path),
        "learning_commands": 0,
        "report_root": str(report_root),
        "skip_tokenizer": args.skip_tokenizer,
    }
    if args.dry_run:
        print(_canonical_text({**plan, "dry_run": True}))
        return 0
    if not episode_paths:
        raise FileNotFoundError(f"no retained issue-54 model episodes found under {outputs_root}")

    freeze = _json_object(freeze_path)
    retained = _retained_diagnostics(episode_paths, progress_every=args.progress_every)
    targets = _target_diagnostics(
        dataset_root,
        freeze,
        skip_tokenizer=args.skip_tokenizer,
        progress_every=max(args.progress_every, 500),
    )
    materialization = _json_object(_MATERIALIZATION_REPORT)
    adapter_probes = [
        _json_object(path) for path in sorted(report_root.glob("adapter-probe-seed-*-checkpoint-*.json"))
    ]
    adjudication_path = outputs_root / "issue54-v3-sanity-adjudication" / "report.json"
    report = {
        "adjudication": _json_object(adjudication_path) if adjudication_path.is_file() else None,
        "findings": {
            "adapter_checkpoint_changes_model_output": bool(adapter_probes)
            and all(probe.get("adapter_changes_any_output") is True for probe in adapter_probes),
            "deterministic_replay_amplification_present": retained["deterministic_replay_count"] > 0,
            "retained_evaluation_used_training_contract": set(retained["input_contracts"])
            == {"bounded_bfs_search_memory"},
            "targets_exceed_frozen_output_budget": targets["total_over_frozen_budget"] > 0,
            "teacher_targets_derive_from_replayed_traces": (
                materialization.get("trusted_trace_replay_count") == materialization.get("trace_count") == 90
                and materialization.get("corpus_regeneration_byte_identical") is True
                and materialization.get("ms_swift_projection_regeneration_byte_identical") is True
            ),
            "teacher_target_parse_failures_present": targets["total_parse_failures"] > 0,
        },
        "frozen_output_tokens": freeze["budgets"]["max_output_tokens_per_operation"],
        "adapter_probes": adapter_probes,
        "materialization": materialization,
        "plan": plan,
        "retained_evaluation": retained,
        "schema_version": "bfs_issue54_diagnostic_report_v1",
        "successor_output_tokens": _SUCCESSOR_OUTPUT_TOKENS,
        "training_contract": targets,
    }
    report_root.mkdir(parents=True, exist_ok=True)
    _write_text(report_root / "diagnostic-report.json", _canonical_text(report) + "\n")
    _write_text(report_root / "diagnostic-report.md", _markdown_report(report))
    print(
        _canonical_text(
            {
                "json_report": str(report_root / "diagnostic-report.json"),
                "markdown_report": str(report_root / "diagnostic-report.md"),
                "status": "completed",
            }
        )
    )
    return 0


def _episode_paths(outputs_root: Path) -> list[Path]:
    patterns = (
        "issue54-v3-base-seed-*/episodes/*.json",
        "issue54-v3-process-seed-*-checkpoint-*/episodes/*.json",
    )
    return sorted(path for pattern in patterns for path in outputs_root.glob(pattern))


def _retained_diagnostics(paths: list[Path], *, progress_every: int) -> dict[str, Any]:
    categories: Counter[str] = Counter()
    contracts: Counter[str] = Counter()
    decision_count = 0
    rejected_count = 0
    replay_count = 0
    goal_count = 0
    runs: dict[str, Counter[str]] = {}
    started = time.monotonic()
    for index, path in enumerate(paths, start=1):
        summary = analyze_episode_payload(_json_object(path))
        decision_count += summary["decision_count"]
        rejected_count += summary["rejected_count"]
        replay_count += summary["deterministic_replay_count"]
        goal_count += int(summary["goal_reached"])
        categories.update(summary["failure_categories"])
        contracts.update(summary["input_contracts"])
        run = runs.setdefault(path.parent.parent.name, Counter())
        run["episodes"] += 1
        run["decisions"] += summary["decision_count"]
        run["rejections"] += summary["rejected_count"]
        run["deterministic_replays"] += summary["deterministic_replay_count"]
        run["goals"] += int(summary["goal_reached"])
        if index % progress_every == 0 or index == len(paths):
            _print_progress("retained_episodes", index, len(paths), started)
    return {
        "decision_count": decision_count,
        "deterministic_replay_count": replay_count,
        "episode_count": len(paths),
        "failure_categories": dict(sorted(categories.items(), key=lambda item: (-item[1], item[0]))),
        "goal_reached_count": goal_count,
        "input_contracts": dict(sorted(contracts.items())),
        "rejected_count": rejected_count,
        "runs": {name: dict(counter) for name, counter in sorted(runs.items())},
    }


def _target_diagnostics(
    dataset_root: Path,
    freeze: dict[str, Any],
    *,
    skip_tokenizer: bool,
    progress_every: int,
) -> dict[str, Any]:
    processor = None
    if not skip_tokenizer:
        from transformers import AutoProcessor

        model = freeze["models"]["primary"]
        processor = AutoProcessor.from_pretrained(model["model_id"], revision=model["revision"])
    frozen_budget = freeze["budgets"]["max_output_tokens_per_operation"]
    split_reports: dict[str, Any] = {}
    total_over_frozen = 0
    total_parse_failures = 0
    prompt_parity: dict[str, bool | None] = {}
    for split in ("train", "dev"):
        path = dataset_root / "data" / f"{split}.jsonl"
        line_count = sum(1 for _line in path.open(encoding="utf-8"))
        lengths: list[int] = []
        parse_failures = 0
        started = time.monotonic()
        first_messages: list[dict[str, str]] | None = None
        with path.open(encoding="utf-8") as stream:
            for index, line in enumerate(stream, start=1):
                row = json.loads(line)
                messages = row["messages"]
                if first_messages is None:
                    first_messages = messages
                target = messages[-1]["content"]
                _parsed, error = _parse_model_output(target)
                parse_failures += int(error is not None)
                if processor is not None:
                    lengths.append(len(processor.tokenizer.encode(target, add_special_tokens=False)))
                if index % progress_every == 0 or index == line_count:
                    _print_progress(f"{split}_targets", index, line_count, started)
        over_frozen = sum(length > frozen_budget for length in lengths)
        over_successor = sum(length > _SUCCESSOR_OUTPUT_TOKENS for length in lengths)
        total_over_frozen += over_frozen
        total_parse_failures += parse_failures
        split_reports[split] = {
            "count": line_count,
            "max_tokens": max(lengths) if lengths else None,
            "over_frozen_budget": over_frozen if lengths else None,
            "over_successor_budget": over_successor if lengths else None,
            "p50_tokens": _percentile(lengths, 0.50),
            "p95_tokens": _percentile(lengths, 0.95),
            "parse_failures": parse_failures,
        }
        prompt_parity[split] = _prompt_token_parity(processor, first_messages) if processor is not None else None
    return {
        "prompt_token_parity": prompt_parity,
        "splits": split_reports,
        "total_over_frozen_budget": total_over_frozen,
        "total_parse_failures": total_parse_failures,
    }


def _prompt_token_parity(processor: Any, messages: list[dict[str, str]] | None) -> bool:
    if messages is None:
        return False
    model_input = json.loads(messages[1]["content"])
    evaluation = processor.apply_chat_template(
        qwen_text_policy_messages(model_input),
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    )["input_ids"][0].tolist()
    training = processor.tokenizer.apply_chat_template(
        messages[:2],
        tokenize=True,
        add_generation_prompt=True,
    )
    return evaluation == training


def _percentile(values: list[int], quantile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[int(quantile * (len(ordered) - 1))]


def _print_progress(stage: str, completed: int, total: int, started: float) -> None:
    elapsed = time.monotonic() - started
    remaining = (elapsed / completed) * (total - completed)
    print(
        _canonical_text(
            {
                "completed": completed,
                "elapsed_seconds": elapsed,
                "estimated_remaining_seconds": remaining,
                "stage": stage,
                "total": total,
            }
        ),
        flush=True,
    )


def _markdown_report(report: dict[str, Any]) -> str:
    retained = report["retained_evaluation"]
    targets = report["training_contract"]
    findings = report["findings"]
    lines = [
        "# Issue 54 BFS diagnostic report",
        "",
        f"- Retained episodes: {retained['episode_count']}",
        f"- Rejected decisions: {retained['rejected_count']} / {retained['decision_count']}",
        f"- Deterministic replayed rejections: {retained['deterministic_replay_count']}",
        f"- Retained input contracts: `{json.dumps(retained['input_contracts'], sort_keys=True)}`",
        f"- Targets above the frozen {report['frozen_output_tokens']}-token budget: "
        f"{targets['total_over_frozen_budget']}",
        f"- Teacher target parse failures: {targets['total_parse_failures']}",
        "",
        "## Findings",
        "",
    ]
    lines.extend(f"- {name}: {value}" for name, value in findings.items())
    lines.extend(["", "## Rejection categories", ""])
    lines.extend(f"- {name}: {count}" for name, count in retained["failure_categories"].items())
    return "\n".join(lines) + "\n"


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _write_text(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
