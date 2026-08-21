"""Generate, replay, and release the authorized issue-111 BFS v3 process corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from examples.planning_benchmark_slice.bfs_corpus import (
    _artifact_path,
    _validated_trace_items,
    regenerate_bfs_text_corpus,
    run_frozen_bfs_text_corpus_release,
)
from examples.planning_benchmark_slice.bfs_generation import (
    _load_candidates,
    _require_frozen_manifest,
    _source_path,
    run_frozen_bfs_trace_generation,
)
from examples.planning_benchmark_slice.bfs_phase import BFSPhaseGate, load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_sft import convert_bfs_corpus_to_ms_swift
from src.data_collect.generate import GenerationRequest
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome
from src.data_collect.splits import split_assignment_id, whole_instance_identity

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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate every committed input and planned stage without creating outputs",
    )
    parser.add_argument(
        "--resume-from-traces",
        action="store_true",
        help="reuse the completed authorized 90-trace manifest and start at corpus release",
    )
    args = parser.parse_args()
    phase_gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    trace_root = _RELEASE_ROOT / "exact-traces"
    corpus_root = _RELEASE_ROOT / "process-release"
    projection_root = _RELEASE_ROOT / "ms-swift-process"
    receipt_root = _RELEASE_ROOT / "execution-receipts"
    report_path = _RELEASE_ROOT / "materialization-report.json"
    output_paths = (trace_root, corpus_root, projection_root, receipt_root, report_path)
    if args.resume_from_traces:
        output_paths_clear = (
            trace_root.is_dir()
            and receipt_root.is_dir()
            and not any(path.exists() for path in (corpus_root, projection_root, report_path))
        )
    else:
        output_paths_clear = not any(path.exists() for path in output_paths)
    if not args.dry_run and not output_paths_clear:
        raise FileExistsError("BFS v3 materialization artifacts already exist")
    preflight = _preflight(
        phase_gate,
        workers=args.workers,
        output_paths=output_paths,
        output_paths_clear=output_paths_clear,
        resume_from_traces=args.resume_from_traces,
    )
    if args.dry_run:
        print(json.dumps(preflight, sort_keys=True))
        return 0

    if args.resume_from_traces:
        trace_manifest_path = trace_root / "manifests" / "bfs-expert-traces.json"
    else:
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
            attempt_id=(
                "issue-111-v3-process-corpus-resume-001" if args.resume_from_traces else "issue-111-v3-process-corpus"
            ),
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
        "resumed_from_traces": args.resume_from_traces,
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


def _preflight(
    phase_gate: BFSPhaseGate,
    *,
    workers: int,
    output_paths: tuple[Path, ...],
    output_paths_clear: bool,
    resume_from_traces: bool,
) -> dict[str, Any]:
    if isinstance(workers, bool) or not isinstance(workers, int) or workers <= 0:
        raise ValueError("BFS v3 workers must be a positive integer")
    manifest_sha256 = _require_frozen_manifest(_ACCEPTED_MANIFEST, phase_gate)
    candidates = _load_candidates(_ACCEPTED_MANIFEST, phase_gate)
    expected_cells = {
        (domain, difficulty, split)
        for domain in phase_gate.freeze["data"]["domains"]
        for difficulty in phase_gate.freeze["data"]["strata"]
        for split in phase_gate.freeze["data"]["allowed_splits"]
    }
    cells: set[tuple[str, str, str]] = set()
    identities: dict[str, str] = {}
    for (domain, difficulty), rows in candidates.items():
        for row in rows:
            split = str(row["split"])
            cells.add((domain, difficulty, split))
            domain_path = _source_path(row["domain_path"])
            problem_path = _source_path(row["problem_path"])
            domain_bytes = domain_path.read_bytes()
            problem_bytes = problem_path.read_bytes()
            identity = whole_instance_identity(domain_bytes, problem_bytes)
            prior_split = identities.get(identity)
            if (
                hashlib.sha256(domain_bytes).hexdigest() != row["domain_hash"]
                or hashlib.sha256(problem_bytes).hexdigest() != row["problem_hash"]
                or identity != row.get("whole_instance_id")
                or row.get("split_assignment_id") != split_assignment_id(identity, split)
                or (prior_split is not None and prior_split != split)
                or not row.get("plan")
            ):
                raise ValueError(f"BFS v3 selected task failed preflight: {domain}/{difficulty}/{split}")
            identities[identity] = split
    if cells != expected_cells or sum(len(rows) for rows in candidates.values()) != 90:
        raise ValueError("BFS v3 preflight does not cover the exact 90 selected cells")

    for stage in ("trace_generation", "corpus_release", "process_sft_and_sanity_gate"):
        phase_gate.require_run(stage=stage, contract_id=phase_gate.phase_id)
    budgets = {
        difficulty: phase_gate.require_run(
            stage="trace_generation",
            contract_id=phase_gate.phase_id,
            difficulty=difficulty,
        )
        for difficulty in phase_gate.freeze["data"]["strata"]
    }
    trace_manifest_path = output_paths[0] / "manifests" / "bfs-expert-traces.json"
    if resume_from_traces:
        reused_trace_count = _validate_reusable_traces(trace_manifest_path, phase_gate)
        trace_attempt_id = "issue-111-v3-exact-traces"
    else:
        reused_trace_count = 0
        trace_attempt_id = _request(
            phase_gate=phase_gate,
            attempt_id="issue-111-v3-exact-traces",
            output_root=output_paths[0],
            receipt_root=output_paths[3],
        ).binding.attempt_id
    corpus_request = _request(
        phase_gate=phase_gate,
        attempt_id=("issue-111-v3-process-corpus-resume-001" if resume_from_traces else "issue-111-v3-process-corpus"),
        output_root=output_paths[1],
        receipt_root=output_paths[3],
    )
    return {
        "authorization_manifest_sha256": _sha256(_AUTHORIZATION.read_bytes()),
        "budgets": budgets,
        "contract_id": phase_gate.phase_id,
        "corpus_attempt_id": corpus_request.binding.attempt_id,
        "dry_run": True,
        "freeze_manifest_sha256": _sha256(_FREEZE.read_bytes()),
        "output_paths_clear": output_paths_clear,
        "planned_stages": [
            *([] if resume_from_traces else ["trace_generation"]),
            "corpus_release",
            "corpus_byte_regeneration",
            "ms_swift_process_projection",
            "ms_swift_projection_byte_regeneration",
        ],
        "schema_version": "bfs_pilot_v3_materialization_preflight_v1",
        "selected_manifest_sha256": manifest_sha256,
        "selected_task_count": len(cells),
        "trace_attempt_id": trace_attempt_id,
        "reused_trace_count": reused_trace_count,
        "resume_from_traces": resume_from_traces,
        "workers": workers,
    }


def _validate_reusable_traces(path: Path, phase_gate: BFSPhaseGate) -> int:
    manifest = _json_object(path)
    traces = _validated_trace_items(manifest, phase_gate)
    trace_root = path.parent.parent
    for item in traces:
        _artifact_path(trace_root, item["evidence"])
        _artifact_path(trace_root, item["search_trace"])
    if len(traces) != 90:
        raise ValueError("BFS v3 resume requires the exact complete 90-trace product")
    return len(traces)


def _tree_payloads(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def _json_object(path: Path) -> dict[str, Any]:
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
