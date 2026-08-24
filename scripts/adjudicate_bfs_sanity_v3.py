"""Adjudicate the frozen issue-54 BFS process-SFT sanity gate."""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import tempfile
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_references import frozen_bfs_development_tasks
from examples.planning_benchmark_slice.episode_evidence import verify_manifested_episode
from examples.planning_benchmark_slice.model_search_episode import replay_model_search_episode
from src.data_collect.governance import GateReceipt, ReceiptBinding, StopOutcome, evaluate_execution_permission

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST = _REPO_ROOT / "data" / "bfs_pilot_v3" / "selected-manifest.jsonl"
_PHASES = {
    phase: (
        _REPO_ROOT / "configs" / "experiments" / f"bfs_phase_freeze_{phase}.json",
        _REPO_ROOT / "configs" / "experiments" / f"bfs_phase_authorization_{phase}.json",
    )
    for phase in ("v3", "v4")
}


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=tuple(_PHASES), default="v3")
    parser.add_argument("--reference-manifest", type=Path, action="append", required=True)
    parser.add_argument("--base-manifest", type=Path, action="append", default=[])
    parser.add_argument("--process-manifest", type=Path, action="append", default=[])
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)

    output_root = args.output_root.expanduser().resolve()
    if output_root.exists() and not args.dry_run:
        raise FileExistsError(f"BFS sanity adjudication output already exists: {output_root}")
    phase_gate = load_bfs_phase_gate(*_PHASES[args.phase])
    phase_gate.require_run(stage="process_sft_and_sanity_gate", contract_id=phase_gate.phase_id)
    binding = ReceiptBinding(phase_gate.phase_id, args.attempt_id, output_root)

    try:
        tasks = frozen_bfs_development_tasks(_MANIFEST, phase_gate)
        expected_ids = {str(task["instance_id"]) for task in tasks}
        references = _reference_records(args.reference_manifest, phase_gate.receipt(stage="base_and_references"))
        base = _model_records(args.base_manifest, "base", phase_gate.receipt(stage="base_and_references"))
        process = _model_records(
            args.process_manifest,
            "process_sft",
            phase_gate.receipt(stage="process_sft_and_sanity_gate"),
        )
        report = _adjudicate(
            expected_ids=expected_ids,
            seeds=tuple(phase_gate.freeze["seeds"]),
            references=references,
            base=base,
            process=process,
            thresholds=phase_gate.freeze["thresholds"],
            bootstrap_resamples=phase_gate.freeze["statistics"]["bootstrap_resamples"],
            bootstrap_seed=phase_gate.freeze["statistics"]["bootstrap_seed"],
        )
        outcome = StopOutcome(report["outcome"])
    except (KeyError, OSError, TypeError, ValueError) as error:
        outcome = StopOutcome.INVALID
        report = {
            "error": str(error),
            "outcome": outcome.value,
            "scientific_completion": False,
        }

    ancestor_gate = None
    if outcome is StopOutcome.ANCESTOR_STOP:
        ancestor_binding = ReceiptBinding(
            phase_gate.phase_id,
            f"{args.attempt_id}-exact-reference",
            output_root / "exact-reference",
        )
        ancestor_gate = GateReceipt(ancestor_binding, StopOutcome.VALID_STOP)
    gate = GateReceipt(
        binding,
        outcome,
        ancestor_receipt_id=ancestor_gate.receipt_id if ancestor_gate is not None else None,
    )
    report.update(
        {
            "attempt_id": args.attempt_id,
            "gate_receipt": gate.to_dict(),
            "phase_receipt": phase_gate.receipt(stage="process_sft_and_sanity_gate"),
            "schema_version": f"bfs_process_sft_sanity_adjudication_{args.phase}",
        }
    )
    if ancestor_gate is not None:
        report["ancestor_gate_receipt"] = ancestor_gate.to_dict()
    if outcome is not StopOutcome.PASS:
        stopped = evaluate_execution_permission(
            binding=binding,
            gate_receipt=gate,
            authorization_receipt=None,
            ancestor_receipt_id=gate.ancestor_receipt_id,
        )
        report["downstream_run_receipt"] = stopped.to_dict()
    if args.dry_run:
        print(_canonical_text({**report, "dry_run": True}))
        return 0 if outcome is not StopOutcome.INVALID else 1

    _write_output(output_root, report)
    print(_canonical_text({"outcome": outcome.value, "output": str(output_root / "report.json")}))
    return 0 if outcome is not StopOutcome.INVALID else 1


def _reference_records(paths: list[Path], expected_phase_receipt: Mapping[str, object]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    shards: set[int] = set()
    shard_count: int | None = None
    for supplied in paths:
        path = supplied.expanduser().resolve()
        manifest = _json_object(path)
        if (
            manifest.get("schema_version") != "bfs_base_and_references_v3"
            or manifest.get("phase_receipt") != expected_phase_receipt
        ):
            raise ValueError(f"reference manifest is not from the frozen v3 phase: {path}")
        current_count = int(manifest["shard_count"])
        if shard_count is None:
            shard_count = current_count
        if current_count != shard_count:
            raise ValueError("reference manifests disagree on shard count")
        shards.add(int(manifest["shard_index"]))
        rows = manifest.get("references")
        if not isinstance(rows, list):
            raise ValueError(f"reference manifest records are malformed: {path}")
        root = path.parents[1]
        for row in rows:
            record = _mapping(row, "reference record")
            if record.get("arm") not in {"exact_classical", "random_valid"}:
                raise ValueError(f"reference record has an unauthorized arm: {path}")
            evidence = _mapping(record.get("evidence"), "reference evidence")
            verify_manifested_episode(root / str(evidence["path"]), evidence, _mapping(record.get("result"), "result"))
            records.append(record)
    if shard_count is None or len(paths) != shard_count or shards != set(range(shard_count)):
        raise ValueError("reference manifests are not a complete shard set")
    return records


def _model_records(
    paths: list[Path],
    expected_arm: str,
    expected_phase_receipt: Mapping[str, object],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    shard_sets: dict[tuple[int, str | None], tuple[int, set[int]]] = {}
    for supplied in paths:
        path = supplied.expanduser().resolve()
        manifest = _json_object(path)
        if (
            manifest.get("schema_version") != "bfs_model_eval_shard_v3"
            or manifest.get("arm") != expected_arm
            or manifest.get("phase_receipt") != expected_phase_receipt
        ):
            raise ValueError(f"model manifest is not the expected frozen v3 arm: {path}")
        seed = int(manifest["seed"])
        adapter = manifest.get("adapter_path")
        key = (seed, str(adapter) if adapter is not None else None)
        count = int(manifest["shard_count"])
        known_count, indices = shard_sets.setdefault(key, (count, set()))
        if count != known_count:
            raise ValueError("model manifests disagree on shard count")
        index = int(manifest["shard_index"])
        if index in indices:
            raise ValueError("duplicate model-evaluation shard")
        indices.add(index)
        rows = manifest.get("records")
        if not isinstance(rows, list):
            raise ValueError(f"model manifest records are malformed: {path}")
        for row in rows:
            record = _mapping(row, "model record")
            if record.get("arm") != expected_arm or record.get("seed") != seed:
                raise ValueError(f"model record differs from its manifest arm or seed: {path}")
            evidence = _mapping(record.get("evidence"), "model evidence")
            evidence_path = path.parent / str(evidence["path"])
            payload = evidence_path.read_bytes()
            if len(payload) != evidence.get("size_bytes"):
                raise ValueError(f"model evidence size differs: {record.get('instance_id')}")
            episode = _json_object(evidence_path)
            if (
                episode.get("result") != record.get("result")
                or replay_model_search_episode(episode["evidence"]) != episode
            ):
                raise ValueError(f"model evidence replay differs: {record.get('instance_id')}")
            records.append({**record, "adapter_path": key[1]})
    for count, indices in shard_sets.values():
        if indices != set(range(count)):
            raise ValueError("model manifests are not a complete shard set")
    return records


def _adjudicate(
    *,
    expected_ids: set[str],
    seeds: tuple[int, ...],
    references: list[dict[str, Any]],
    base: list[dict[str, Any]],
    process: list[dict[str, Any]],
    thresholds: Mapping[str, Any],
    bootstrap_resamples: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    exact = [row for row in references if row.get("arm") == "exact_classical"]
    random_rows = [row for row in references if row.get("arm") == "random_valid"]
    _require_product(exact, expected_ids, (None,), label="exact reference")
    _require_product(random_rows, expected_ids, seeds, label="random-valid reference")

    exact_success = _mean([_success(row) for row in exact])
    if exact_success < float(thresholds["exact_reference_invariant_valid_success"]):
        if process:
            raise ValueError("process SFT ran before the exact-reference ancestor passed")
        return {
            "exact_reference_invariant_valid_success": exact_success,
            "outcome": StopOutcome.ANCESTOR_STOP.value,
            "scientific_completion": False,
        }

    _require_product(base, expected_ids, seeds, label="base model")

    by_candidate: dict[tuple[int, str | None], list[dict[str, Any]]] = defaultdict(list)
    for row in process:
        by_candidate[(int(row["seed"]), row.get("adapter_path"))].append(row)
    selected: list[dict[str, Any]] = []
    selected_adapters: dict[str, str | None] = {}
    for seed in seeds:
        candidates = []
        for (candidate_seed, adapter), rows in by_candidate.items():
            if candidate_seed != seed:
                continue
            _require_product(rows, expected_ids, (seed,), label=f"process SFT seed {seed} candidate")
            candidates.append((_mean([_success(row) for row in rows]), str(adapter), rows))
        if not candidates:
            raise ValueError(f"process SFT has no complete checkpoint candidate for seed {seed}")
        _success_rate, adapter_text, rows = min(
            candidates,
            key=lambda item: (-item[0], _checkpoint_order(item[1]), item[1]),
        )
        selected.extend(rows)
        selected_adapters[str(seed)] = adapter_text

    base_success = _mean([_success(row) for row in base])
    random_success = _mean([_success(row) for row in random_rows])
    process_success = _mean([_success(row) for row in selected])
    controls = {"base": base_success, "random_valid": random_success}
    best_control = max(controls, key=controls.get)
    absolute_gain = process_success - controls[best_control]
    process_by_task = _task_success(selected, expected_ids)
    control_rows = base if best_control == "base" else random_rows
    control_by_task = _task_success(control_rows, expected_ids)
    lower_bound = _paired_bootstrap_lower_bound(
        process_by_task,
        control_by_task,
        resamples=bootstrap_resamples,
        seed=bootstrap_seed,
    )
    invalid_rate = _aggregate_invalid_rate(selected)
    per_seed = {
        str(seed): {
            "base_invariant_valid_success": _mean([_success(row) for row in base if row["seed"] == seed]),
            "process_sft_invariant_valid_success": _mean([_success(row) for row in selected if row["seed"] == seed]),
            "process_sft_invalid_operation_rate": _aggregate_invalid_rate(
                [row for row in selected if row["seed"] == seed]
            ),
            "random_valid_invariant_valid_success": _mean([_success(row) for row in random_rows if row["seed"] == seed]),
            "selected_adapter": selected_adapters[str(seed)],
        }
        for seed in seeds
    }
    checks = {
        "absolute_gain": absolute_gain >= float(thresholds["process_sft_absolute_gain_over_best_control"]),
        "bootstrap_lower_bound": lower_bound >= float(thresholds["process_sft_gain_bootstrap_lower_bound"]),
        "invariant_valid_success": process_success >= float(thresholds["process_sft_invariant_valid_success"]),
        "invalid_operation_rate": invalid_rate <= float(thresholds["maximum_invalid_operation_rate"]),
    }
    outcome = StopOutcome.PASS if all(checks.values()) else StopOutcome.VALID_STOP
    return {
        "absolute_gain_over_best_control": absolute_gain,
        "base_invariant_valid_success": base_success,
        "best_control": best_control,
        "checks": checks,
        "exact_reference_invariant_valid_success": exact_success,
        "outcome": outcome.value,
        "paired_bootstrap_gain_lower_bound": lower_bound,
        "per_seed": per_seed,
        "process_sft_invariant_valid_success": process_success,
        "process_sft_invalid_operation_rate": invalid_rate,
        "random_valid_invariant_valid_success": random_success,
        "scientific_completion": outcome is StopOutcome.PASS,
        "selected_adapters": selected_adapters,
    }


def _checkpoint_order(path: str) -> int:
    match = re.search(r"checkpoint-(\d+)(?:/)?$", path)
    return int(match.group(1)) if match is not None else 2**63 - 1


def _require_product(
    rows: list[dict[str, Any]],
    expected_ids: set[str],
    seeds: tuple[int | None, ...],
    *,
    label: str,
) -> None:
    actual = {(str(row.get("instance_id")), row.get("seed")) for row in rows}
    expected = {(instance_id, seed) for instance_id in expected_ids for seed in seeds}
    if actual != expected or len(rows) != len(expected):
        raise ValueError(f"{label} records do not form the complete frozen task-by-seed product")


def _success(row: Mapping[str, Any]) -> float:
    result = _mapping(row.get("result"), "episode result")
    return float(bool(result.get("goal_reached")) and result.get("algorithm_invariants_hold", True) is True)


def _aggregate_invalid_rate(rows: list[dict[str, Any]]) -> float:
    invalid = 0
    decisions = 0
    for row in rows:
        result = _mapping(row.get("result"), "model result")
        invalid += int(result.get("invalid_operation_count", 0))
        decisions += int(result.get("decision_count", 0))
    return invalid / decisions if decisions else 0.0


def _task_success(rows: list[dict[str, Any]], expected_ids: set[str]) -> dict[str, float]:
    values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        values[str(row["instance_id"])].append(_success(row))
    if set(values) != expected_ids:
        raise ValueError("metric rows do not cover every frozen whole problem instance")
    return {instance_id: _mean(values[instance_id]) for instance_id in sorted(expected_ids)}


def _paired_bootstrap_lower_bound(
    treatment: Mapping[str, float],
    control: Mapping[str, float],
    *,
    resamples: int,
    seed: int,
) -> float:
    if treatment.keys() != control.keys() or resamples <= 0:
        raise ValueError("paired bootstrap inputs are malformed")
    differences = [treatment[key] - control[key] for key in sorted(treatment)]
    generator = random.Random(seed)
    draws = sorted(_mean([generator.choice(differences) for _ in differences]) for _ in range(resamples))
    index = int(0.025 * (resamples - 1))
    return draws[index]


def _mean(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot compute a mean over no records")
    return sum(values) / len(values)


def _write_output(output_root: Path, report: Mapping[str, Any]) -> None:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
    try:
        (staging / "report.json").write_text(_canonical_text(report) + "\n", encoding="utf-8")
        (staging / "gate-receipt.json").write_text(
            _canonical_text(report["gate_receipt"]) + "\n",
            encoding="utf-8",
        )
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
