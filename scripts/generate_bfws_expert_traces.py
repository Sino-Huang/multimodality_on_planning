"""Generate the replay-verified issue-57 BFWS expert traces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from examples.planning_benchmark_slice.bfws_generation import (
    preflight_frozen_bfws_trace_generation,
    run_frozen_bfws_trace_generation,
    verify_frozen_bfws_trace_release,
)
from examples.planning_benchmark_slice.bfws_phase import load_bfws_phase_gate
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfws_phase_freeze_v1.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfws_phase_authorization_v1.json"
_OUTPUT_ROOT = _REPO_ROOT / "data" / "bfws_phase_v1" / "exact-traces"
_RECEIPT_ROOT = _REPO_ROOT / "data" / "bfws_phase_v1" / "execution-receipts"
_ATTEMPT_STEM = "issue-57-bfws-exact-traces-v1"


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="validate and print the planned run without writes")
    mode.add_argument("--check", action="store_true", help="replay every retained trace without writes")
    parser.add_argument("--resume", action="store_true", help="replay completed tasks and generate only missing traces")
    parser.add_argument("--attempt-id", help="governance attempt ID; resume chooses the next unused ID by default")
    parser.add_argument("--output-root", type=Path, default=_OUTPUT_ROOT)
    args = parser.parse_args(arguments)

    output_root = args.output_root.expanduser().resolve()
    phase_gate = load_bfws_phase_gate(_FREEZE, _AUTHORIZATION)
    rows = preflight_frozen_bfws_trace_generation(phase_gate)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "exact_reference_decision_count": sum(row["exact_reference_decision_count"] for row in rows),
                    "exact_reference_expansion_count": sum(row["exact_reference_expansion_count"] for row in rows),
                    "output_root": str(output_root),
                    "phase_id": phase_gate.phase_id,
                    "selected_instance_count": len(rows),
                    "selected_stratum_count": len({(row["domain_id"], row["difficulty"]) for row in rows}),
                    "test_instance_count": 0,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 0
    if args.check:
        manifest_path = output_root / "manifests" / "bfws-expert-traces.json"
        manifest = verify_frozen_bfws_trace_release(
            manifest_path,
            phase_gate=phase_gate,
            progress=lambda message: print(message, flush=True),
        )
        print(json.dumps(manifest["coverage"], sort_keys=True), flush=True)
        return 0

    receipt_root = (
        _RECEIPT_ROOT if output_root == _OUTPUT_ROOT else output_root.parent / f"{output_root.name}-execution-receipts"
    ).resolve()
    attempt_id = args.attempt_id or _next_attempt_id(receipt_root, resume=args.resume)
    binding = ReceiptBinding(phase_gate.phase_id, attempt_id, output_root)
    gate_receipt = GateReceipt(binding, StopOutcome.PASS)
    request = GenerationRequest(
        binding=binding,
        gate_receipt=gate_receipt,
        authorization_receipt=AuthorizationReceipt(binding, gate_receipt.receipt_id),
        receipt_root=receipt_root,
    )
    receipt = run_frozen_bfws_trace_generation(
        request=request,
        phase_gate=phase_gate,
        resume=args.resume,
        progress=lambda message: print(message, flush=True),
    )
    print(json.dumps(receipt.to_dict(), sort_keys=True), flush=True)
    return 0 if receipt.outcome is StopOutcome.PASS else 1


def _next_attempt_id(receipt_root: Path, *, resume: bool) -> str:
    if not resume:
        return _ATTEMPT_STEM
    index = 1
    while True:
        candidate = f"{_ATTEMPT_STEM}-resume-{index:03d}"
        receipt = receipt_root / f"generation-run-issue-56-bfws-development-v1-{candidate}.json"
        if not receipt.exists():
            return candidate
        index += 1


if __name__ == "__main__":
    raise SystemExit(main())
