"""Materialize, resume, or verify the authorized issue-58 BFWS text corpus."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from examples.planning_benchmark_slice.bfws_corpus import (
    run_frozen_bfws_corpus_release,
    verify_frozen_bfws_corpus_release,
)
from examples.planning_benchmark_slice.bfws_generation import preflight_frozen_bfws_trace_generation
from examples.planning_benchmark_slice.bfws_phase import BFWSPhaseGate, load_bfws_phase_gate
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfws_phase_freeze_v1.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfws_phase_authorization_v1.json"
_TRACE_MANIFEST = (
    _REPO_ROOT / "data" / "bfws_phase_v1" / "exact-traces" / "manifests" / "bfws-expert-traces.json"
)
_OUTPUT_ROOT = _REPO_ROOT / "data" / "bfws_phase_v1" / "corpus-release"
_RECEIPT_ROOT = _REPO_ROOT / "data" / "bfws_phase_v1" / "execution-receipts"


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--attempt-id", default="issue-58-bfws-text-corpus-v1")
    parser.add_argument("--output-root", type=Path, default=_OUTPUT_ROOT)
    args = parser.parse_args(arguments)
    phase_gate = load_bfws_phase_gate(_FREEZE, _AUTHORIZATION)
    rows = preflight_frozen_bfws_trace_generation(phase_gate)
    output_root = args.output_root.expanduser().resolve()
    if args.dry_run:
        print(
            json.dumps(
                {
                    "authorized_stage": "corpus_release",
                    "contract_id": phase_gate.phase_id,
                    "exact_decision_count": sum(row["exact_reference_decision_count"] for row in rows),
                    "fresh_test_access_authorized": False,
                    "learning_commands": 0,
                    "output_root": str(output_root),
                    "planned_artifacts": [
                        "operational_corpus",
                        "process_corpus",
                        "curricula",
                        "split_ledger",
                        "process_training_projection",
                    ],
                    "split_counts": {
                        split: sum(row["split"] == split for row in rows) for split in ("train", "dev")
                    },
                    "stratum_count": len({(row["domain_id"], row["difficulty"]) for row in rows}),
                    "task_count": len(rows),
                    "trace_manifest_path": str(_TRACE_MANIFEST),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 0
    if args.check:
        manifest = verify_frozen_bfws_corpus_release(
            trace_manifest_path=_TRACE_MANIFEST,
            corpus_root=output_root,
            phase_gate=phase_gate,
            progress=_progress,
        )
        print(
            json.dumps(
                {
                    "byte_identical_regeneration": True,
                    "counts": manifest["counts"],
                    "output_root": str(output_root),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 0

    receipt = run_frozen_bfws_corpus_release(
        trace_manifest_path=_TRACE_MANIFEST,
        request=_request(phase_gate, args.attempt_id, output_root),
        phase_gate=phase_gate,
        resume=args.resume,
        progress=_progress,
    )
    print(receipt.canonical_json(), flush=True)
    return 0 if receipt.outcome is StopOutcome.PASS else 1


def _request(phase_gate: BFWSPhaseGate, attempt_id: str, output_root: Path) -> GenerationRequest:
    binding = ReceiptBinding(phase_gate.phase_id, attempt_id, output_root)
    gate = GateReceipt(binding, StopOutcome.PASS)
    return GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(binding, gate.receipt_id),
        receipt_root=_RECEIPT_ROOT,
    )


def _progress(message: str) -> None:
    print(message, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
