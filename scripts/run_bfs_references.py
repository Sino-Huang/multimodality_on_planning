"""Run issue-52 exact-classical and random-valid BFS reference arms."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_references import frozen_bfs_development_tasks, run_frozen_bfs_references
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PHASES = {
    "v1": (
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json",
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json",
        _REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl",
    ),
    "v3": (
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v3.json",
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v3.json",
        _REPO_ROOT / "data" / "bfs_pilot_v3" / "selected-manifest.jsonl",
    ),
    "v4": (
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v4.json",
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v4.json",
        _REPO_ROOT / "data" / "bfs_pilot_v3" / "selected-manifest.jsonl",
    ),
    "v6": (
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v6.json",
        _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v6.json",
        _REPO_ROOT / "data" / "bfs_pilot_v6" / "selected-manifest.jsonl",
    ),
}


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=tuple(_PHASES), required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)
    output_root = args.output_root.expanduser().resolve()
    freeze, authorization_manifest, accepted_manifest = _PHASES[args.phase]
    phase_gate = load_bfs_phase_gate(freeze, authorization_manifest)
    tasks = frozen_bfs_development_tasks(accepted_manifest, phase_gate)
    if args.shard_count <= 0 or args.shard_index < 0 or args.shard_index >= args.shard_count:
        raise ValueError("shard index must be inside a positive shard count")
    if args.shard_count > len(tasks) or args.workers <= 0:
        raise ValueError("shard count and workers must fit the frozen development task set")
    shard_tasks = [row for index, row in enumerate(tasks) if index % args.shard_count == args.shard_index]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "attempt_id": args.attempt_id,
                    "dry_run": True,
                    "output_root": str(output_root),
                    "phase_id": phase_gate.phase_id,
                    "reference_episode_count": len(shard_tasks) * (1 + len(phase_gate.freeze["seeds"])),
                    "shard_task_count": len(shard_tasks),
                    "workers": args.workers,
                },
                sort_keys=True,
            )
        )
        return 0
    binding = ReceiptBinding(phase_gate.phase_id, args.attempt_id, output_root)
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    request = GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(binding, gate.receipt_id),
        receipt_root=(output_root.parent / f"{output_root.name}-receipts").resolve(),
    )
    receipt = run_frozen_bfs_references(
        accepted_manifest_path=accepted_manifest,
        request=request,
        phase_gate=phase_gate,
        shard_index=args.shard_index,
        shard_count=args.shard_count,
        workers=args.workers,
        progress=_ProgressLogger(output_root.parent / f"{output_root.name}-progress.jsonl"),
    )
    print(json.dumps(receipt.to_dict(), sort_keys=True))
    return 0 if receipt.outcome is StopOutcome.PASS else 1


class _ProgressLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.started = time.monotonic()

    def __call__(self, completed: int, total: int, item: str) -> None:
        elapsed = time.monotonic() - self.started
        record = {
            "completed_tasks": completed,
            "elapsed_seconds": elapsed,
            "estimated_remaining_seconds": (elapsed / completed) * (total - completed),
            "instance_id": item,
            "recorded_at_unix": time.time(),
            "schema_version": "bfs_reference_progress_v1",
            "total_tasks": total,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        current = self.path.with_suffix(".json")
        temporary = current.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(current)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        print(json.dumps(record, sort_keys=True), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
