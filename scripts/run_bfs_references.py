"""Run issue-52 exact-classical and random-valid BFS reference arms."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_references import run_frozen_bfs_references
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json"
_MANIFEST = _REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl"
_SIGNING_KEY = b"issue-52-bfs-reference-arms-v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    output_root = args.output_root.expanduser().resolve()
    phase_gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    binding = ReceiptBinding(phase_gate.phase_id, args.attempt_id, output_root)
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS).signed(_SIGNING_KEY)
    request = GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(binding, gate.digest).signed(_SIGNING_KEY),
        signing_key=_SIGNING_KEY,
        receipt_root=(output_root.parent / f"{output_root.name}-receipts").resolve(),
    )
    receipt = run_frozen_bfs_references(
        accepted_manifest_path=_MANIFEST,
        request=request,
        phase_gate=phase_gate,
        shard_index=args.shard_index,
        shard_count=args.shard_count,
        workers=args.workers,
    )
    print(json.dumps(receipt.to_dict(), sort_keys=True))
    return 0 if receipt.outcome is StopOutcome.PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
