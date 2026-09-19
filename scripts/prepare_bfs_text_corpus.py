"""Materialize the authorized frozen BFS traces and text corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from examples.planning_benchmark_slice.bfs_corpus import run_frozen_bfs_text_corpus_release
from examples.planning_benchmark_slice.bfs_generation import run_frozen_bfs_trace_generation
from examples.planning_benchmark_slice.bfs_phase import BFSPhaseGate, load_bfs_phase_gate
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json"
_ACCEPTED_MANIFEST = _REPO_ROOT / "data" / "curriculum_pddl" / "accepted_manifest.jsonl"
def _request(
    *,
    phase_gate: BFSPhaseGate,
    attempt_id: str,
    output_root: Path,
    receipt_root: Path,
) -> GenerationRequest:
    binding = ReceiptBinding(
        contract_id=phase_gate.phase_id,
        attempt_id=attempt_id,
        output_root=output_root,
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_id=gate.receipt_id)
    return GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
        receipt_root=receipt_root,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--attempt-suffix", required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    root = args.output_root.expanduser().resolve()
    trace_root = root / "traces"
    corpus_root = root / "corpus-release"
    receipt_root = root / "receipts"
    if root.exists():
        raise FileExistsError(f"BFS corpus materialization root already exists: {root}")

    phase_gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    trace_request = _request(
        phase_gate=phase_gate,
        attempt_id=f"issue-50-traces-{args.attempt_suffix}",
        output_root=trace_root,
        receipt_root=receipt_root,
    )
    trace_receipt = run_frozen_bfs_trace_generation(
        accepted_manifest_path=_ACCEPTED_MANIFEST,
        request=trace_request,
        phase_gate=phase_gate,
        workers=args.workers,
    )
    if trace_receipt.outcome is not StopOutcome.PASS or trace_receipt.execution_result is None:
        print(trace_receipt.canonical_json())
        return 1

    corpus_request = _request(
        phase_gate=phase_gate,
        attempt_id=f"issue-51-corpus-{args.attempt_suffix}",
        output_root=corpus_root,
        receipt_root=receipt_root,
    )
    corpus_receipt = run_frozen_bfs_text_corpus_release(
        trace_manifest_path=Path(trace_receipt.execution_result["trace_manifest_path"]),
        request=corpus_request,
        phase_gate=phase_gate,
    )
    report = {
        "corpus_receipt": corpus_receipt.to_dict(),
        "schema_version": "bfs_text_corpus_materialization_v1",
        "trace_receipt": trace_receipt.to_dict(),
    }
    report_path = root / "materialization-report.json"
    report_path.write_text(
        json.dumps(report, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(report_path), "outcome": corpus_receipt.outcome.value}, sort_keys=True))
    return 0 if corpus_receipt.outcome is StopOutcome.PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
