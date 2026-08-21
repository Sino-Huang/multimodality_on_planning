"""Run one deterministic shard of the issue-52 Qwen base arm."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import tempfile
import time
from pathlib import Path

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_references import (
    _write_task_fixture,
    frozen_bfs_development_tasks,
)
from examples.planning_benchmark_slice.model_search_episode import (
    replay_model_search_episode,
    run_model_search_episode,
)
from examples.planning_benchmark_slice.qwen_text_policy import QwenTextPolicy
from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    StopOutcome,
    evaluate_execution_permission,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json"
_MANIFEST = _REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    args = parser.parse_args()
    if args.shard_count <= 0 or args.shard_index < 0 or args.shard_index >= args.shard_count:
        raise ValueError("shard index must be inside a positive shard count")
    output_root = args.output_root.expanduser().resolve()
    if output_root.exists():
        raise FileExistsError(f"BFS base shard output already exists: {output_root}")

    phase_gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    phase_gate.require_run(stage="base_and_references", contract_id=phase_gate.phase_id)
    binding = ReceiptBinding(phase_gate.phase_id, args.attempt_id, output_root)
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding, gate.receipt_id)
    permission = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )
    if not permission.start_permitted:
        raise RuntimeError("frozen BFS authorization did not permit the base shard")
    tasks = frozen_bfs_development_tasks(_MANIFEST, phase_gate)
    shard_tasks = [row for index, row in enumerate(tasks) if index % args.shard_count == args.shard_index]

    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    torch.use_deterministic_algorithms(True)
    model = phase_gate.freeze["models"]["primary"]
    seed = phase_gate.freeze["seeds"][0] if args.seed is None else args.seed
    if seed not in phase_gate.freeze["seeds"]:
        raise ValueError("base seed is not in the frozen BFS seed set")
    policy = QwenTextPolicy(
        model_id=model["model_id"],
        revision=model["revision"],
        max_new_tokens=phase_gate.freeze["budgets"]["max_output_tokens_per_operation"],
        device=args.device,
    )
    policy.set_seed(seed)
    output_root.mkdir(parents=True)
    started = time.monotonic()
    records: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix=f"bfs-base-shard-{args.shard_index}-") as task_directory:
        fixture_root = Path(task_directory)
        for task_index, row in enumerate(shard_tasks, start=1):
            fixture_path = _write_task_fixture(row, fixture_root)
            max_expansions = phase_gate.require_run(
                stage="base_and_references",
                contract_id=phase_gate.phase_id,
                difficulty=row["bucket"],
            )
            assert max_expansions is not None
            episode = run_model_search_episode(
                fixture_path,
                algorithm="bfs",
                modality="text-state",
                arm="base",
                model_identity=policy.identity,
                policy=policy,
                max_expansions=max_expansions,
                max_output_tokens=phase_gate.freeze["budgets"]["max_output_tokens_per_operation"],
                accepted_delta_limit=(
                    phase_gate.freeze["budgets"]["max_context_tokens"]
                    // phase_gate.freeze["budgets"]["max_output_tokens_per_operation"]
                ),
                seed=seed,
                gate_receipt=gate,
                authorization_receipt=authorization,
            )
            if replay_model_search_episode(episode["evidence"]) != episode:
                raise ValueError(f"BFS base episode replay differs: {row['instance_id']}")
            relative_path = Path("episodes") / f"{row['instance_id']}.json"
            payload = _canonical_bytes(episode)
            _write_bytes(output_root / relative_path, payload)
            records.append(
                {
                    "difficulty": row["bucket"],
                    "domain_id": row["domain_id"],
                    "evidence": {
                        "path": relative_path.as_posix(),
                        "size_bytes": len(payload),
                    },
                    "instance_id": row["instance_id"],
                    "result": episode["result"],
                    "seed": seed,
                }
            )
            print(
                json.dumps(
                    {
                        "completed": task_index,
                        "goal_reached": episode["result"]["goal_reached"],
                        "instance_id": row["instance_id"],
                        "shard_count": len(shard_tasks),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

    manifest = {
        "attempt_id": args.attempt_id,
        "authorization_receipt": authorization.to_dict(),
        "device": {"name": torch.cuda.get_device_name(torch.device(args.device).index or 0)},
        "elapsed_seconds": time.monotonic() - started,
        "framework": {
            package: importlib.metadata.version(package)
            for package in ("accelerate", "ms-swift", "peft", "torch", "transformers")
        },
        "gate_receipt": gate.to_dict(),
        "phase_receipt": phase_gate.receipt(stage="base_and_references"),
        "records": records,
        "schema_version": "bfs_base_shard_v1",
        "shard_count": args.shard_count,
        "shard_index": args.shard_index,
        "task_count": len(records),
    }
    _write_bytes(output_root / "manifest.json", _canonical_bytes(manifest))
    print(json.dumps({"output": str(output_root / "manifest.json"), "task_count": len(records)}, sort_keys=True))
    return 0


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
