"""Evaluate one frozen v3 BFS base or process-SFT model shard."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import tempfile
import time
from pathlib import Path

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_references import _write_task_fixture, frozen_bfs_development_tasks
from examples.planning_benchmark_slice.model_search_episode import replay_model_search_episode, run_model_search_episode
from examples.planning_benchmark_slice.qwen_text_policy import QwenTextPolicy
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST = _REPO_ROOT / "data" / "bfs_pilot_v3" / "selected-manifest.jsonl"
_PHASES = {
    phase: (
        _REPO_ROOT / "configs" / "experiments" / f"bfs_phase_freeze_{phase}.json",
        _REPO_ROOT / "configs" / "experiments" / f"bfs_phase_authorization_{phase}.json",
    )
    for phase in ("v3", "v4")
}


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=tuple(_PHASES), default="v3")
    parser.add_argument("--arm", choices=("base", "process_sft"), required=True)
    parser.add_argument("--adapter-path", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)

    if args.shard_count <= 0 or args.shard_index < 0 or args.shard_index >= args.shard_count:
        raise ValueError("shard index must be inside a positive shard count")
    if (args.arm == "process_sft") != (args.adapter_path is not None):
        raise ValueError("process_sft requires --adapter-path and base forbids it")

    output_root = args.output_root.expanduser().resolve()
    adapter_path = args.adapter_path.expanduser().resolve() if args.adapter_path is not None else None
    if adapter_path is not None and not adapter_path.is_dir():
        raise ValueError(f"BFS process-SFT adapter does not exist: {adapter_path}")

    phase_gate = load_bfs_phase_gate(*_PHASES[args.phase])
    if args.seed not in phase_gate.freeze["seeds"]:
        raise ValueError("model evaluation seed is not in the frozen BFS seed set")
    stage = "base_and_references" if args.arm == "base" else "process_sft_and_sanity_gate"
    phase_gate.require_run(stage=stage, contract_id=phase_gate.phase_id)
    tasks = frozen_bfs_development_tasks(_MANIFEST, phase_gate)
    shard_tasks = [row for index, row in enumerate(tasks) if index % args.shard_count == args.shard_index]
    budgets = phase_gate.freeze["budgets"]
    max_input_bytes = budgets.get(
        "max_model_input_bytes",
        budgets["max_context_tokens"] - budgets["max_output_tokens_per_operation"],
    )
    accepted_delta_limit = budgets.get(
        "accepted_delta_limit",
        budgets["max_context_tokens"] // budgets["max_output_tokens_per_operation"],
    )
    plan = {
        "adapter_path": str(adapter_path) if adapter_path is not None else None,
        "arm": args.arm,
        "attempt_id": args.attempt_id,
        "device": args.device,
        "dry_run": False,
        "accepted_delta_limit": accepted_delta_limit,
        "max_input_bytes": max_input_bytes,
        "max_output_tokens": budgets["max_output_tokens_per_operation"],
        "model_input_projection": phase_gate.freeze["implementation"]["process_memory_projection"],
        "output_root": str(output_root),
        "phase_receipt": phase_gate.receipt(stage=stage),
        "seed": args.seed,
        "shard_count": args.shard_count,
        "shard_index": args.shard_index,
        "task_count": len(shard_tasks),
    }
    output_state = _output_state(output_root, plan, resume=args.resume)
    if args.dry_run:
        print(json.dumps({**plan, "dry_run": True, "output_state": output_state}, sort_keys=True))
        return 0
    if output_state == "complete":
        print(json.dumps({"output": str(output_root / "manifest.json"), "status": "already_complete"}, sort_keys=True))
        return 0

    binding = ReceiptBinding(phase_gate.phase_id, args.attempt_id, output_root)
    gate = GateReceipt(binding, StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding, gate.receipt_id)
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    torch.use_deterministic_algorithms(True)
    model = phase_gate.freeze["models"]["primary"]
    policy = QwenTextPolicy(
        model_id=model["model_id"],
        revision=model["revision"],
        max_new_tokens=budgets["max_output_tokens_per_operation"],
        device=args.device,
        adapter_path=adapter_path,
    )
    policy.set_seed(args.seed)
    output_root.mkdir(parents=True, exist_ok=output_state == "resume")
    if output_state == "fresh":
        (output_root / "launch.json").write_text(_canonical_text(plan) + "\n", encoding="utf-8")
    started = time.monotonic() - _prior_elapsed_seconds(output_root)
    records: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix=f"bfs-{args.arm}-shard-{args.shard_index}-") as task_directory:
        fixture_root = Path(task_directory)
        for task_index, row in enumerate(shard_tasks, start=1):
            relative_path = Path("episodes") / f"{row['instance_id']}.json"
            episode_path = output_root / relative_path
            if episode_path.exists():
                episode = json.loads(episode_path.read_text(encoding="utf-8"))
                if replay_model_search_episode(episode["evidence"]) != episode:
                    raise ValueError(f"BFS resumed model episode replay differs: {row['instance_id']}")
                records.append(
                    _model_record(args.arm, args.seed, row, relative_path, episode_path.stat().st_size, episode)
                )
                _write_progress(output_root, task_index, len(shard_tasks), row["instance_id"], started)
                continue
            fixture_path = _write_task_fixture(row, fixture_root)
            max_expansions = phase_gate.require_run(
                stage=stage,
                contract_id=phase_gate.phase_id,
                difficulty=row["bucket"],
            )
            assert max_expansions is not None
            episode = run_model_search_episode(
                fixture_path,
                algorithm="bfs",
                modality="text-state",
                arm=args.arm,
                model_identity=policy.identity,
                policy=policy,
                max_expansions=max_expansions,
                max_input_bytes=max_input_bytes,
                max_output_tokens=budgets["max_output_tokens_per_operation"],
                accepted_delta_limit=accepted_delta_limit,
                model_input_projection=phase_gate.freeze["implementation"]["process_memory_projection"],
                seed=args.seed,
                gate_receipt=gate,
                authorization_receipt=authorization,
            )
            if replay_model_search_episode(episode["evidence"]) != episode:
                raise ValueError(f"BFS model episode replay differs: {row['instance_id']}")
            payload = _canonical_bytes(episode)
            _write_bytes(episode_path, payload)
            records.append(_model_record(args.arm, args.seed, row, relative_path, len(payload), episode))
            _write_progress(output_root, task_index, len(shard_tasks), row["instance_id"], started)

    manifest = {
        "adapter_path": str(adapter_path) if adapter_path is not None else None,
        "arm": args.arm,
        "attempt_id": args.attempt_id,
        "authorization_receipt": authorization.to_dict(),
        "device": {"name": torch.cuda.get_device_name(torch.device(args.device).index or 0)},
        "elapsed_seconds": time.monotonic() - started,
        "framework": {
            package: importlib.metadata.version(package)
            for package in ("accelerate", "ms-swift", "peft", "torch", "transformers")
        },
        "gate_receipt": gate.to_dict(),
        "model_identity": policy.identity,
        "phase_receipt": phase_gate.receipt(stage=stage),
        "records": records,
        "schema_version": "bfs_model_eval_shard_v3",
        "seed": args.seed,
        "shard_count": args.shard_count,
        "shard_index": args.shard_index,
        "task_count": len(records),
    }
    _write_bytes(output_root / "manifest.json", _canonical_bytes(manifest))
    print(json.dumps({"output": str(output_root / "manifest.json"), "task_count": len(records)}, sort_keys=True))
    return 0


def _output_state(output_root: Path, plan: dict[str, object], *, resume: bool) -> str:
    if not output_root.exists():
        return "fresh"
    if not resume:
        raise FileExistsError(f"BFS model shard output already exists: {output_root}; pass --resume to reuse it")
    launch_path = output_root / "launch.json"
    if not launch_path.is_file() or json.loads(launch_path.read_text(encoding="utf-8")) != plan:
        raise ValueError(f"BFS model resume launch differs from the existing attempt: {output_root}")
    return "complete" if (output_root / "manifest.json").is_file() else "resume"


def _prior_elapsed_seconds(output_root: Path) -> float:
    progress_path = output_root / "progress.json"
    if not progress_path.is_file():
        return 0.0
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    return float(progress.get("elapsed_seconds", 0.0))


def _model_record(
    arm: str,
    seed: int,
    row: dict[str, object],
    relative_path: Path,
    size_bytes: int,
    episode: dict[str, object],
) -> dict[str, object]:
    return {
        "arm": arm,
        "difficulty": row["bucket"],
        "domain_id": row["domain_id"],
        "evidence": {"path": relative_path.as_posix(), "size_bytes": size_bytes},
        "instance_id": row["instance_id"],
        "result": episode["result"],
        "seed": seed,
    }


def _write_progress(output_root: Path, completed: int, total: int, instance_id: str, started: float) -> None:
    elapsed = time.monotonic() - started
    record = {
        "completed_tasks": completed,
        "elapsed_seconds": elapsed,
        "estimated_remaining_seconds": (elapsed / completed) * (total - completed),
        "instance_id": instance_id,
        "recorded_at_unix": time.time(),
        "schema_version": "bfs_model_eval_progress_v1",
        "total_tasks": total,
    }
    temporary = output_root / "progress.json.tmp"
    temporary.write_text(_canonical_text(record) + "\n", encoding="utf-8")
    temporary.replace(output_root / "progress.json")
    with (output_root / "progress.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(_canonical_text(record) + "\n")
    print(_canonical_text(record), flush=True)


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _canonical_bytes(value: object) -> bytes:
    return (_canonical_text(value) + "\n").encode("utf-8")


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
