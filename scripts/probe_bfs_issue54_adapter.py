"""Run a small non-learning base/adapter generation probe for issue 54."""

from __future__ import annotations

import argparse
import gc
import json
import time
from pathlib import Path
from typing import Any, Sequence

from examples.planning_benchmark_slice.model_search_episode import _parse_model_output
from examples.planning_benchmark_slice.qwen_text_policy import QwenTextPolicy

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v3.json"
_DATASET = _REPO_ROOT / "data" / "bfs_pilot_v3" / "ms-swift-process"
_OUTPUTS = _REPO_ROOT / "outputs" / "bfs_phase"


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-path", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-new-tokens", type=int, default=384)
    parser.add_argument(
        "--output",
        type=Path,
        default=_OUTPUTS / "issue54-v3-diagnostics" / "adapter-probe.json",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)
    adapter_path = args.adapter_path.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if not adapter_path.is_dir():
        raise FileNotFoundError(f"adapter checkpoint does not exist: {adapter_path}")
    if args.max_new_tokens <= 0:
        raise ValueError("max-new-tokens must be positive")

    prompts = _probe_prompts(args.seed, adapter_path.name)
    plan = {
        "adapter_path": str(adapter_path),
        "device": args.device,
        "learning_commands": 0,
        "max_new_tokens": args.max_new_tokens,
        "output": str(output_path),
        "prompt_labels": list(prompts),
        "seed": args.seed,
    }
    if args.dry_run:
        print(_canonical_text({**plan, "dry_run": True}))
        return 0

    freeze = _json_object(_FREEZE)
    model = freeze["models"]["primary"]
    results: dict[str, Any] = {}
    started = time.monotonic()
    for index, (arm, path) in enumerate((("base", None), ("process_sft", adapter_path)), start=1):
        policy = QwenTextPolicy(
            model_id=model["model_id"],
            revision=model["revision"],
            max_new_tokens=args.max_new_tokens,
            max_context_tokens=freeze["budgets"]["max_context_tokens"],
            device=args.device,
            adapter_path=path,
        )
        policy.set_seed(args.seed)
        results[arm] = {
            "identity": policy.identity,
            "outputs": {
                label: _output_diagnostic(policy(model_input), target)
                for label, (model_input, target) in prompts.items()
            },
        }
        del policy
        gc.collect()
        import torch

        torch.cuda.empty_cache()
        elapsed = time.monotonic() - started
        print(
            _canonical_text(
                {
                    "completed_models": index,
                    "elapsed_seconds": elapsed,
                    "estimated_remaining_seconds": elapsed / index * (2 - index),
                    "stage": "adapter_probe",
                    "total_models": 2,
                }
            ),
            flush=True,
        )

    base_outputs = results["base"]["outputs"]
    adapted_outputs = results["process_sft"]["outputs"]
    report = {
        "adapter_changes_any_output": any(
            base_outputs[label]["raw_output"] != adapted_outputs[label]["raw_output"] for label in prompts
        ),
        "plan": plan,
        "results": results,
        "schema_version": "bfs_issue54_adapter_probe_v1",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_text(output_path, _canonical_text(report) + "\n")
    print(_canonical_text({"output": str(output_path), "status": "completed"}))
    return 0


def _probe_prompts(seed: int, checkpoint_name: str) -> dict[str, tuple[dict[str, Any], str | None]]:
    train = _first_messages(_DATASET / "data" / "train.jsonl")
    dev = _first_messages(_DATASET / "data" / "dev.jsonl")
    retained_path = (
        _OUTPUTS
        / f"issue54-v3-process-seed-{seed}-{checkpoint_name}"
        / "episodes"
        / "15puzzle-dev-easy-0000.json"
    )
    retained = _json_object(retained_path)
    retained_events = retained["evidence"]["policy_events"]
    if not retained_events:
        raise ValueError(f"retained episode has no policy events: {retained_path}")
    return {
        "dev_bounded": (json.loads(dev[1]["content"]), dev[2]["content"]),
        "dev_retained_rolling": (retained_events[0]["input"], dev[2]["content"]),
        "train_bounded": (json.loads(train[1]["content"]), train[2]["content"]),
    }


def _first_messages(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as stream:
        return json.loads(next(stream))["messages"]


def _output_diagnostic(raw_output: str, target: str | None) -> dict[str, Any]:
    _parsed, error = _parse_model_output(raw_output)
    operation_match = False
    if error is None and target is not None:
        operation_match = json.loads(raw_output)["typed_operation"] == json.loads(target)["typed_operation"]
    return {
        "parse_error": error,
        "raw_output": raw_output,
        "target_operation_match": operation_match,
    }


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
