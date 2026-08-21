"""Generate, replay, and release the authorized issue-111 BFS v3 process corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from examples.planning_benchmark_slice.bfs_corpus import (
    regenerate_bfs_text_corpus,
    run_frozen_bfs_text_corpus_release,
)
from examples.planning_benchmark_slice.bfs_generation import run_frozen_bfs_trace_generation
from examples.planning_benchmark_slice.bfs_phase import BFSPhaseGate, load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_sft import convert_bfs_corpus_to_ms_swift
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v3.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v3.json"
_ACCEPTED_MANIFEST = _REPO_ROOT / "data" / "bfs_pilot_v3" / "selected-manifest.jsonl"
_RELEASE_ROOT = _REPO_ROOT / "data" / "bfs_pilot_v3"
_SIGNING_KEY = b"issue-111-bfs-expansion-qualified-pilot-v3"


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
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS).signed(_SIGNING_KEY)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_digest=gate.digest).signed(_SIGNING_KEY)
    return GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
        signing_key=_SIGNING_KEY,
        receipt_root=receipt_root,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    phase_gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    trace_root = _RELEASE_ROOT / "exact-traces"
    corpus_root = _RELEASE_ROOT / "process-release"
    projection_root = _RELEASE_ROOT / "ms-swift-process"
    receipt_root = _RELEASE_ROOT / "execution-receipts"
    report_path = _RELEASE_ROOT / "materialization-report.json"
    if any(path.exists() for path in (trace_root, corpus_root, projection_root, receipt_root, report_path)):
        raise FileExistsError("BFS v3 materialization artifacts already exist")

    trace_receipt = run_frozen_bfs_trace_generation(
        accepted_manifest_path=_ACCEPTED_MANIFEST,
        request=_request(
            phase_gate=phase_gate,
            attempt_id="issue-111-v3-exact-traces",
            output_root=trace_root,
            receipt_root=receipt_root,
        ),
        phase_gate=phase_gate,
        workers=args.workers,
    )
    if trace_receipt.outcome is not StopOutcome.PASS or trace_receipt.execution_result is None:
        raise RuntimeError("BFS v3 trace generation did not PASS")
    trace_manifest_path = Path(trace_receipt.execution_result["trace_manifest_path"])

    corpus_receipt = run_frozen_bfs_text_corpus_release(
        trace_manifest_path=trace_manifest_path,
        request=_request(
            phase_gate=phase_gate,
            attempt_id="issue-111-v3-process-corpus",
            output_root=corpus_root,
            receipt_root=receipt_root,
        ),
        phase_gate=phase_gate,
    )
    if corpus_receipt.outcome is not StopOutcome.PASS or corpus_receipt.execution_result is None:
        raise RuntimeError("BFS v3 process corpus release did not PASS")
    corpus_manifest_path = Path(corpus_receipt.execution_result["corpus_manifest_path"])
    regenerated_corpus = regenerate_bfs_text_corpus(
        trace_manifest_path=trace_manifest_path,
        signing_key=_SIGNING_KEY,
        phase_gate=phase_gate,
    )
    released_corpus = _tree_payloads(corpus_root)
    if regenerated_corpus != released_corpus:
        raise ValueError("BFS v3 process corpus regeneration differs from released bytes")

    projection_manifest = convert_bfs_corpus_to_ms_swift(
        corpus_root=corpus_root,
        output_root=projection_root,
        phase_gate=phase_gate,
        view="process",
    )
    with tempfile.TemporaryDirectory(prefix="bfs-v3-ms-swift-replay-") as temporary:
        replay_root = Path(temporary) / "projection"
        convert_bfs_corpus_to_ms_swift(
            corpus_root=corpus_root,
            output_root=replay_root,
            phase_gate=phase_gate,
            view="process",
        )
        if _tree_payloads(projection_root) != _tree_payloads(replay_root):
            raise ValueError("BFS v3 ms-swift projection regeneration differs from released bytes")

    trace_manifest = _json_object(trace_manifest_path)
    corpus_manifest = _json_object(corpus_manifest_path)
    projection = _json_object(projection_manifest)
    if len(trace_manifest["traces"]) != 90 or corpus_manifest["views"] != ["process"]:
        raise ValueError("BFS v3 materialization does not cover the required process-only product")
    report = {
        "authorization_manifest_sha256": _sha256(_AUTHORIZATION.read_bytes()),
        "corpus_manifest_sha256": _sha256(corpus_manifest_path.read_bytes()),
        "corpus_regeneration_byte_identical": True,
        "freeze_manifest_sha256": _sha256(_FREEZE.read_bytes()),
        "ms_swift_manifest_sha256": _sha256(projection_manifest.read_bytes()),
        "ms_swift_projection_regeneration_byte_identical": True,
        "phase_id": phase_gate.phase_id,
        "process_record_count": corpus_manifest["counts"]["process_records"],
        "schema_version": "bfs_pilot_v3_materialization_report_v1",
        "trace_count": len(trace_manifest["traces"]),
        "trace_manifest_sha256": _sha256(trace_manifest_path.read_bytes()),
        "train_projection_count": projection["counts"]["train"],
        "dev_projection_count": projection["counts"]["dev"],
        "trusted_trace_replay_count": len(trace_manifest["traces"]),
    }
    report_path.write_bytes(_canonical_bytes(report))
    print(json.dumps(report, sort_keys=True))
    return 0


def _tree_payloads(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
