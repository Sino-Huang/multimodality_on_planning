"""Replay and adjudicate complete selected coverage for a batched BFS gate."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from examples.planning_benchmark_slice.batched_search_evaluation import adjudicate_resource_bounded_gate
from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.episode_evidence import verify_manifested_episode
from examples.planning_benchmark_slice.model_search_episode import replay_model_search_episode
from scripts.adjudicate_bfs_sanity_v3 import _adjudicate
from src.data_collect.governance import GateReceipt, ReceiptBinding, StopOutcome, evaluate_execution_permission

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PHASES = {
    phase: (
        _REPO_ROOT / "configs" / "experiments" / f"bfs_phase_freeze_{phase}.json",
        _REPO_ROOT / "configs" / "experiments" / f"bfs_phase_authorization_{phase}.json",
    )
    for phase in ("v7", "v8")
}
_REFERENCES = _REPO_ROOT / "outputs" / "bfs_phase" / "issue54-v6-references" / "manifests" / "bfs-references.json"


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=tuple(_PHASES), default="v8")
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--rollout-root", type=Path, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)

    gate = load_bfs_phase_gate(*_PHASES[args.phase])
    gate.require_run(stage="replay_and_adjudication", contract_id=gate.phase_id)
    binding = ReceiptBinding(gate.phase_id, args.attempt_id, args.output_root.resolve())
    outcome = StopOutcome.INVALID
    report: dict[str, object]
    try:
        qualification = _json_object(args.qualification)
        qualification_phase = qualification.get("phase_id", qualification.get("plan", {}).get("phase_id"))
        if qualification_phase != gate.phase_id:
            raise ValueError("performance qualification belongs to a different phase")
        coverage = qualification["coverage"]
        expected_ids = set(coverage["task_ids"])
        if coverage["outcome"] != StopOutcome.PASS.value or len(expected_ids) not in {15, 45}:
            outcome = StopOutcome.VALID_STOP
            report = {"reason": "performance_qualification_did_not_certify_coverage"}
        else:
            base, process, manifests_complete = _model_records(args.rollout_root, expected_ids, gate.phase_id)
            references = _reference_records(expected_ids)
            expected_model_records = len(expected_ids) * 10
            coverage_complete = manifests_complete and len(base) + len(process) == expected_model_records
            elapsed = time.time() - float(qualification["gate_started_at_unix"])
            if coverage_complete:
                metrics = _adjudicate(
                    expected_ids=expected_ids,
                    seeds=tuple(gate.freeze["seeds"]),
                    references=references,
                    base=base,
                    process=process,
                    thresholds=gate.freeze["thresholds"],
                    bootstrap_resamples=gate.freeze["statistics"]["bootstrap_resamples"],
                    bootstrap_seed=gate.freeze["statistics"]["bootstrap_seed"],
                )
                threshold_outcome = StopOutcome(metrics["outcome"])
                outcome = adjudicate_resource_bounded_gate(
                    coverage_complete=True,
                    invariants_match=True,
                    provenance_matches=True,
                    replay_matches=True,
                    thresholds_pass=threshold_outcome is StopOutcome.PASS,
                    elapsed_seconds=elapsed,
                )
                report = {"metrics": metrics}
            else:
                outcome = StopOutcome.VALID_STOP
                report = {
                    "completed_model_records": len(base) + len(process),
                    "expected_model_records": expected_model_records,
                    "partial_results_scientific_completion": False,
                    "reason": "incomplete_selected_coverage",
                }
            report.update(
                {
                    "coverage_complete": coverage_complete,
                    "coverage_mode": coverage["mode"],
                    "elapsed_seconds": elapsed,
                    "selected_task_ids": sorted(expected_ids),
                }
            )
    except (KeyError, OSError, TypeError, ValueError) as error:
        outcome = StopOutcome.INVALID
        report = {"error": str(error), "reason": "invariant_provenance_or_replay_mismatch"}

    receipt = GateReceipt(binding, outcome)
    report.update(
        {
            "attempt_id": args.attempt_id,
            "gate_receipt": receipt.to_dict(),
            "outcome": outcome.value,
            "phase_id": gate.phase_id,
            "schema_version": f"bfs_{args.phase}_resource_bounded_adjudication_v1",
            "scientific_completion": outcome is StopOutcome.PASS,
        }
    )
    if outcome is not StopOutcome.PASS:
        report["downstream_run_receipt"] = evaluate_execution_permission(
            binding=binding,
            gate_receipt=receipt,
            authorization_receipt=None,
        ).to_dict()
    if args.dry_run:
        print(_canonical_text({**report, "dry_run": True}))
        return 1 if outcome is StopOutcome.INVALID else 0
    if args.output_root.exists():
        raise FileExistsError(f"adjudication output already exists: {args.output_root}")
    args.output_root.mkdir(parents=True)
    (args.output_root / "report.json").write_text(_canonical_text(report) + "\n", encoding="utf-8")
    (args.output_root / "gate-receipt.json").write_text(
        _canonical_text(receipt.to_dict()) + "\n",
        encoding="utf-8",
    )
    print(_canonical_text({"outcome": outcome.value, "output": str(args.output_root / "report.json")}))
    return 1 if outcome is StopOutcome.INVALID else 0


def _model_records(roots: list[Path], expected_ids: set[str], phase_id: str):
    base: list[dict[str, object]] = []
    process: list[dict[str, object]] = []
    shards: set[int] = set()
    manifests_complete = True
    for root in roots:
        manifest = _json_object(root / "manifest.json")
        if (
            manifest.get("schema_version")
            not in {
                "bfs_v7_batched_rollout_shard_v1",
                "bfs_v8_batched_rollout_shard_v1",
            }
            or manifest.get("phase_id") != phase_id
        ):
            raise ValueError(f"rollout manifest has the wrong schema: {root}")
        shards.add(int(manifest["device_shard_index"]))
        manifests_complete &= manifest.get("outcome") == StopOutcome.PASS.value
        for path in sorted((root / "episodes").rglob("*.json")):
            episode = _json_object(path)
            if replay_model_search_episode(episode["evidence"]) != episode:
                raise ValueError(f"model episode replay differs: {path}")
            parts = path.relative_to(root / "episodes").parts
            arm = parts[0]
            seed = int(parts[1].removeprefix("seed-"))
            instance_id = path.stem
            if instance_id not in expected_ids or arm not in {"base", "process_sft"}:
                raise ValueError(f"model episode is outside selected coverage: {path}")
            row = {
                "adapter_path": f"checkpoint-1221-seed-{seed}" if arm == "process_sft" else None,
                "arm": arm,
                "instance_id": instance_id,
                "result": episode["result"],
                "seed": seed,
            }
            (base if arm == "base" else process).append(row)
    return base, process, manifests_complete and shards == {0, 1}


def _reference_records(expected_ids: set[str]):
    manifest = _json_object(_REFERENCES)
    rows = [row for row in manifest["references"] if row["instance_id"] in expected_ids]
    for row in rows:
        evidence = row["evidence"]
        verify_manifested_episode(
            _REFERENCES.parents[1] / evidence["path"],
            evidence,
            row["result"],
        )
    return rows


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
