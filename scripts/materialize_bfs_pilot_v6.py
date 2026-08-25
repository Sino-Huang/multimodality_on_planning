"""Generate and deterministically release the 8,192-token observable BFS corpus."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from examples.planning_benchmark_slice.bfs_corpus import regenerate_bfs_text_corpus, run_frozen_bfs_text_corpus_release
from examples.planning_benchmark_slice.bfs_generation import _normalize_authority_input, run_frozen_bfs_trace_generation
from examples.planning_benchmark_slice.bfs_phase import BFSPhaseGate, load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_sft import convert_bfs_corpus_to_ms_swift
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v6.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v6.json"
_DATA_ROOT = _REPO_ROOT / "data" / "bfs_pilot_v6"
_MANIFEST = _DATA_ROOT / "selected-manifest.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume-from-traces", action="store_true")
    args = parser.parse_args()
    phase_gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    _preflight_selected_tasks()
    trace_root = _DATA_ROOT / "exact-traces"
    corpus_root = _DATA_ROOT / "process-release"
    projection_root = _DATA_ROOT / "ms-swift-process"
    receipt_root = _DATA_ROOT / "execution-receipts"
    report_path = _DATA_ROOT / "materialization-report.json"
    outputs = (trace_root, corpus_root, projection_root, receipt_root, report_path)
    if args.resume_from_traces:
        outputs_clear = (
            trace_root.is_dir()
            and receipt_root.is_dir()
            and not any(path.exists() for path in (corpus_root, projection_root, report_path))
        )
    else:
        outputs_clear = not any(path.exists() for path in outputs)
    if not outputs_clear:
        raise FileExistsError("BFS v6 materialization output state does not match the requested mode")
    for stage in ("trace_generation", "corpus_release", "process_sft_and_sanity_gate"):
        phase_gate.require_run(stage=stage, contract_id=phase_gate.phase_id)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "contract_id": phase_gate.phase_id,
                    "learning_commands": 0,
                    "planned_stages": [
                        *([] if args.resume_from_traces else ["trace_generation"]),
                        "corpus_release",
                        "ms_swift_projection",
                    ],
                    "resume_from_traces": args.resume_from_traces,
                    "selected_task_count": 90,
                },
                sort_keys=True,
            )
        )
        return 0

    if args.resume_from_traces:
        trace_manifest_path = trace_root / "manifests" / "bfs-expert-traces.json"
    else:
        trace_receipt = run_frozen_bfs_trace_generation(
            accepted_manifest_path=_MANIFEST,
            request=_request(phase_gate, "issue-111-v6-exact-traces", trace_root, receipt_root),
            phase_gate=phase_gate,
            workers=args.workers,
        )
        if trace_receipt.outcome is not StopOutcome.PASS or trace_receipt.execution_result is None:
            raise RuntimeError("BFS v6 trace generation did not PASS")
        trace_manifest_path = Path(trace_receipt.execution_result["trace_manifest_path"])
    corpus_receipt = run_frozen_bfs_text_corpus_release(
        trace_manifest_path=trace_manifest_path,
        request=_request(
            phase_gate,
            "issue-111-v6-process-corpus-attempt-002" if args.resume_from_traces else "issue-111-v6-process-corpus",
            corpus_root,
            receipt_root,
        ),
        phase_gate=phase_gate,
    )
    if corpus_receipt.outcome is not StopOutcome.PASS or corpus_receipt.execution_result is None:
        raise RuntimeError("BFS v6 corpus release did not PASS")
    corpus_manifest_path = Path(corpus_receipt.execution_result["corpus_manifest_path"])
    if regenerate_bfs_text_corpus(trace_manifest_path=trace_manifest_path, phase_gate=phase_gate) != _tree_payloads(
        corpus_root
    ):
        raise ValueError("BFS v6 corpus regeneration differs from released bytes")
    projection_manifest = convert_bfs_corpus_to_ms_swift(
        corpus_root=corpus_root,
        output_root=projection_root,
        phase_gate=phase_gate,
        view="process",
    )
    with tempfile.TemporaryDirectory(prefix="bfs-v6-ms-swift-replay-") as temporary:
        replay_root = Path(temporary) / "projection"
        convert_bfs_corpus_to_ms_swift(
            corpus_root=corpus_root,
            output_root=replay_root,
            phase_gate=phase_gate,
            view="process",
        )
        if _tree_payloads(projection_root) != _tree_payloads(replay_root):
            raise ValueError("BFS v6 ms-swift projection regeneration differs from released bytes")
    trace_manifest = _json_object(trace_manifest_path)
    corpus_manifest = _json_object(corpus_manifest_path)
    projection = _json_object(projection_manifest)
    report = {
        "authorization_manifest_path": _relative(_AUTHORIZATION),
        "corpus_manifest_path": _relative(corpus_manifest_path),
        "corpus_regeneration_byte_identical": True,
        "dev_projection_count": projection["counts"]["dev"],
        "freeze_manifest_path": _relative(_FREEZE),
        "learning_commands": 0,
        "ms_swift_manifest_path": _relative(projection_manifest),
        "ms_swift_projection_regeneration_byte_identical": True,
        "phase_id": phase_gate.phase_id,
        "process_record_count": corpus_manifest["counts"]["process_records"],
        "resumed_from_traces": args.resume_from_traces,
        "schema_version": "bfs_pilot_v6_materialization_report_v1",
        "trace_count": len(trace_manifest["traces"]),
        "trace_manifest_path": _relative(trace_manifest_path),
        "train_projection_count": projection["counts"]["train"],
        "trusted_trace_replay_count": len(trace_manifest["traces"]),
    }
    report_path.write_bytes(_canonical_bytes(report))
    print(json.dumps(report, sort_keys=True))
    return 0


def _preflight_selected_tasks() -> None:
    rows = [json.loads(line) for line in _MANIFEST.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 90:
        raise ValueError("BFS v6 preflight requires exactly 90 selected tasks")
    identities = {"train": set(), "dev": set()}
    for row in rows:
        domain_pddl, problem_pddl, _transformations = _normalize_authority_input(
            (_REPO_ROOT / row["domain_path"]).read_text(encoding="utf-8"),
            (_REPO_ROOT / row["problem_path"]).read_text(encoding="utf-8"),
        )
        authority = PDDLStateAuthority.from_pddl(domain_pddl, problem_pddl)
        identity = authority.semantic_task_identity()
        if identity != row["semantic_task_identity"]:
            raise ValueError("BFS v6 selected task semantic identity mismatch")
        identities[row["split"]].add(identity)
    if identities["train"] & identities["dev"]:
        raise ValueError("BFS v6 selected tasks cross semantic splits")


def _request(
    phase_gate: BFSPhaseGate,
    attempt_id: str,
    output_root: Path,
    receipt_root: Path,
) -> GenerationRequest:
    binding = ReceiptBinding(phase_gate.phase_id, attempt_id, output_root)
    gate = GateReceipt(binding, StopOutcome.PASS)
    return GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(binding, gate.receipt_id),
        receipt_root=receipt_root,
    )


def _tree_payloads(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _relative(path: Path) -> str:
    return path.resolve().relative_to(_REPO_ROOT).as_posix()


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode()


if __name__ == "__main__":
    raise SystemExit(main())
