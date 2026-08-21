"""Validate issue-52 evidence and emit the downstream BFS gate chain."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_references import frozen_bfs_development_tasks
from examples.planning_benchmark_slice.episode_evidence import verify_manifested_episode
from src.data_collect.governance import (
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
    parser.add_argument("--base-manifest", type=Path, action="append", required=True)
    parser.add_argument("--reference-manifest", type=Path, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    output_root = args.output_root.expanduser().resolve()
    if output_root.exists():
        raise FileExistsError(f"BFS adjudication output already exists: {output_root}")
    phase_gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    tasks = frozen_bfs_development_tasks(_MANIFEST, phase_gate)
    task_ids = {str(task["instance_id"]) for task in tasks}
    seeds = tuple(phase_gate.freeze["seeds"])

    base_records = _base_records(args.base_manifest)
    expected_base = {(instance_id, seed) for instance_id in task_ids for seed in seeds}
    actual_base = {(str(row["instance_id"]), int(row["seed"])) for _root, row in base_records}
    if actual_base != expected_base or len(base_records) != len(expected_base):
        raise ValueError("base manifests do not form the complete frozen task-by-seed product")

    reference_records = _reference_records(args.reference_manifest)
    expected_references = {(instance_id, "exact_classical", None) for instance_id in task_ids} | {
        (instance_id, "random_valid", seed) for instance_id in task_ids for seed in seeds
    }
    actual_references = {(str(row["instance_id"]), str(row["arm"]), row["seed"]) for _root, row in reference_records}
    if actual_references != expected_references or len(reference_records) != len(expected_references):
        raise ValueError("reference manifests do not form the complete frozen arm-by-task-by-seed product")

    for root, row in base_records:
        _verify_evidence(root, row)
    for root, row in reference_records:
        _verify_evidence(root, row)

    exact_rows = [row for _root, row in reference_records if row["arm"] == "exact_classical"]
    exact_success = sum(bool(row["result"]["goal_reached"]) for row in exact_rows) / len(exact_rows)
    threshold = phase_gate.freeze["thresholds"]["exact_reference_invariant_valid_success"]
    issue52_outcome = StopOutcome.PASS if exact_success >= threshold else StopOutcome.VALID_STOP

    issue52_binding = ReceiptBinding(
        phase_gate.phase_id,
        "issue-52-base-and-references-v1",
        output_root / "issue52",
    )
    issue52_gate = GateReceipt(issue52_binding, issue52_outcome)
    downstream = _downstream_receipts(output_root, phase_gate.phase_id, issue52_gate)
    report = {
        "base": _base_metrics(base_records, seeds),
        "framework_decision": {
            "name": "ms-swift",
            "version": "4.2.2",
            "training_started": False,
        },
        "issue52": {
            "exact_reference_invariant_valid_success": exact_success,
            "gate_receipt": issue52_gate.to_dict(),
            "outcome": issue52_outcome.value,
            "threshold": threshold,
        },
        **downstream,
        "references": _reference_metrics(reference_records, seeds),
        "schema_version": "bfs_issue_52_54_adjudication_v1",
    }
    _write_output(output_root, report)
    print(_canonical_text({"outcome": issue52_outcome.value, "output": str(output_root / "report.json")}))
    return 0


def _base_records(manifest_paths: list[Path]) -> list[tuple[Path, dict[str, Any]]]:
    records: list[tuple[Path, dict[str, Any]]] = []
    for path in manifest_paths:
        manifest_path = path.expanduser().resolve()
        manifest = _json_object(manifest_path)
        if manifest.get("schema_version") != "bfs_base_shard_v1":
            raise ValueError(f"unexpected base manifest schema: {manifest_path}")
        rows = manifest.get("records")
        if not isinstance(rows, list) or manifest.get("task_count") != len(rows):
            raise ValueError(f"malformed base manifest: {manifest_path}")
        records.extend((manifest_path.parent, _mapping(row, "base record")) for row in rows)
    return records


def _reference_records(manifest_paths: list[Path]) -> list[tuple[Path, dict[str, Any]]]:
    records: list[tuple[Path, dict[str, Any]]] = []
    shard_indices: set[int] = set()
    shard_count: int | None = None
    for path in manifest_paths:
        manifest_path = path.expanduser().resolve()
        manifest = _json_object(manifest_path)
        if manifest.get("schema_version") not in {
            "bfs_base_and_references_v1",
            "bfs_base_and_references_v2",
            "bfs_base_and_references_v3",
        }:
            raise ValueError(f"unexpected reference manifest schema: {manifest_path}")
        current_count = int(manifest["shard_count"])
        shard_count = current_count if shard_count is None else shard_count
        if current_count != shard_count:
            raise ValueError("reference manifests disagree on shard count")
        shard_indices.add(int(manifest["shard_index"]))
        rows = manifest.get("references")
        if not isinstance(rows, list):
            raise ValueError(f"malformed reference manifest: {manifest_path}")
        records.extend((manifest_path.parents[1], _mapping(row, "reference record")) for row in rows)
    if shard_count is None or shard_indices != set(range(shard_count)):
        raise ValueError("reference manifests are not a complete shard set")
    return records


def _verify_evidence(
    root: Path,
    row: dict[str, Any],
) -> None:
    evidence = _mapping(row.get("evidence"), "evidence artifact")
    relative = Path(str(evidence.get("path")))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("evidence path escapes its run root")
    path = root / relative
    if "codec_version" in evidence:
        verify_manifested_episode(path, evidence, _mapping(row.get("result"), "result"))
        return
    payload = path.read_bytes()
    if len(payload) != evidence.get("size_bytes"):
        raise ValueError(f"evidence artifact size differs from its manifest: {path}")
    episode = json.loads(payload)
    if episode.get("result") != row.get("result"):
        raise ValueError(f"evidence result differs from its manifest: {path}")


def _base_metrics(
    records: list[tuple[Path, dict[str, Any]]],
    seeds: tuple[int, ...],
) -> dict[str, object]:
    by_seed: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for _root, row in records:
        by_seed[int(row["seed"])].append(row)
    return {
        "episode_count": len(records),
        "per_seed": {
            str(seed): {
                "invariant_valid_success": sum(bool(row["result"]["goal_reached"]) for row in by_seed[seed])
                / len(by_seed[seed]),
                "mean_invalid_operation_rate": sum(
                    float(row["result"]["invalid_operation_rate"]) for row in by_seed[seed]
                )
                / len(by_seed[seed]),
            }
            for seed in seeds
        },
    }


def _reference_metrics(
    records: list[tuple[Path, dict[str, Any]]],
    seeds: tuple[int, ...],
) -> dict[str, object]:
    random_by_seed: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for _root, row in records:
        if row["arm"] == "random_valid":
            random_by_seed[int(row["seed"])].append(row)
    return {
        "episode_count": len(records),
        "random_valid_success_by_seed": {
            str(seed): sum(bool(row["result"]["goal_reached"]) for row in random_by_seed[seed])
            / len(random_by_seed[seed])
            for seed in seeds
        },
    }


def _downstream_receipts(output_root: Path, contract_id: str, issue52_gate: GateReceipt) -> dict[str, object]:
    issue53_binding = ReceiptBinding(contract_id, "issue-53-operational-sft-v1", output_root / "issue53")
    issue53_gate = GateReceipt(
        issue53_binding,
        StopOutcome.ANCESTOR_STOP,
        ancestor_receipt_id=issue52_gate.receipt_id,
    )
    issue53_run = evaluate_execution_permission(
        binding=issue53_binding,
        gate_receipt=issue53_gate,
        authorization_receipt=None,
        ancestor_receipt_id=issue52_gate.receipt_id,
    )
    issue54_binding = ReceiptBinding(contract_id, "issue-54-process-sft-v1", output_root / "issue54")
    issue54_gate = GateReceipt(
        issue54_binding,
        StopOutcome.ANCESTOR_STOP,
        ancestor_receipt_id=issue53_run.receipt_id,
    )
    issue54_run = evaluate_execution_permission(
        binding=issue54_binding,
        gate_receipt=issue54_gate,
        authorization_receipt=None,
        ancestor_receipt_id=issue53_run.receipt_id,
    )
    return {
        "issue53": {"gate_receipt": issue53_gate.to_dict(), "run_receipt": issue53_run.to_dict()},
        "issue54": {"gate_receipt": issue54_gate.to_dict(), "run_receipt": issue54_run.to_dict()},
    }


def _write_output(output_root: Path, report: dict[str, object]) -> None:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
    try:
        (staging / "report.json").write_text(_canonical_text(report) + "\n", encoding="utf-8")
        staging.replace(output_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _json_object(path: Path) -> dict[str, Any]:
    return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
