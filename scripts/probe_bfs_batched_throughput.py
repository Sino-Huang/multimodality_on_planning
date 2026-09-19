"""Run the outcome-blind v7 batching and coverage qualification probe."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from examples.planning_benchmark_slice.batched_search_evaluation import (
    PerformanceQualificationReceipt,
    evaluation_tasks_from_manifests,
    form_deterministic_batches,
    lower_95_throughput_bound,
    select_certified_coverage,
)
from examples.planning_benchmark_slice.bfs_generation import _normalize_authority_input
from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.model_search_episode import SearchPolicyRequest
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.qwen_text_policy import BatchedPolicyAdapter
from examples.planning_benchmark_slice.search_context import verify_incremental_replay_contexts
from examples.planning_benchmark_slice.search_episode import _trace_limits

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v7.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v7.json"
_CORPUS = _REPO_ROOT / "data" / "bfs_pilot_v6" / "process-release" / "corpus" / "process.jsonl"
_TRACE_ROOT = _REPO_ROOT / "data" / "bfs_pilot_v6" / "exact-traces"


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devices", nargs="+", default=("cuda:0", "cuda:1"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)

    gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    gate.require_run(stage="performance_qualification", contract_id=gate.phase_id)
    if len(args.devices) != 2 or len(set(args.devices)) != 2:
        raise ValueError("v7 qualification requires exactly two distinct A100 devices")
    gate_started_at_unix = time.time()
    probe_ids = tuple(probe["record_id"] for probe in gate.freeze["performance_probes"])
    adapter_paths = {
        f"seed-{seed}": (
            _REPO_ROOT
            / "outputs"
            / "bfs_phase"
            / f"issue54-v6-process-sft-seed-{seed}"
            / "checkpoints"
            / "checkpoint-1221"
        )
        for seed in gate.freeze["seeds"]
    }
    plan = {
        "adapter_paths": {name: str(path) for name, path in adapter_paths.items()},
        "devices": args.devices,
        "max_batch_input_tokens": 48_000,
        "max_batch_size": 8,
        "max_new_tokens": 384,
        "phase_id": gate.phase_id,
        "probe_ids": probe_ids,
        "unique_model_sessions_per_task": 6,
        "uses_success_outcomes": False,
    }
    if args.dry_run:
        print(json.dumps({**plan, "dry_run": True}, sort_keys=True))
        return 0
    missing = [str(path) for path in adapter_paths.values() if not path.is_dir()]
    if missing:
        raise FileNotFoundError(f"v7 final checkpoints are missing: {missing}")

    probe_inputs = _probe_inputs(probe_ids)
    model = gate.freeze["models"]["primary"]
    base_requests = tuple(
        SearchPolicyRequest(
            session_id=f"probe:base:{record_id}",
            adapter_id=None,
            seed=17,
            instance_id=record_id,
            decision_index=0,
            model_input=probe_inputs[record_id],
        )
        for record_id in probe_ids
    )
    parity_probes = base_requests[::3]
    model_load_samples: list[float] = []
    device_throughput_bounds: list[float] = []
    runtime_overheads: list[float] = []
    for device in args.devices:
        started = time.perf_counter()
        policy = BatchedPolicyAdapter(
            model_id=model["model_id"],
            revision=model["revision"],
            adapter_paths=adapter_paths,
            device=device,
            max_new_tokens=384,
            max_context_tokens=8_192,
            max_batch_size=8,
            max_batch_input_tokens=48_000,
        )
        model_load_samples.append(time.perf_counter() - started)
        if not policy.verify_scalar_parity(parity_probes):
            raise ValueError(f"fixed batched probes differ from scalar generation on {device}")
        if not policy.verify_determinism(parity_probes):
            raise ValueError(f"repeated batched probes are not byte-identical on {device}")

        throughput_samples: list[float] = []
        for adapter_id in (None, *adapter_paths):
            requests = tuple(
                SearchPolicyRequest(
                    session_id=f"probe:{adapter_id or 'base'}:{request.instance_id}",
                    adapter_id=adapter_id,
                    seed=17,
                    instance_id=request.instance_id,
                    decision_index=0,
                    model_input=request.model_input,
                )
                for request in base_requests[:8]
            )
            before = time.perf_counter()
            policy._generate_uncached(adapter_id, requests)
            throughput_samples.append(len(requests) / (time.perf_counter() - before))
        device_throughput_bounds.append(lower_95_throughput_bound(throughput_samples))

        runtime_started = time.perf_counter()
        for _ in range(100):
            form_deterministic_batches(base_requests, token_length=policy.input_token_length)
        runtime_overheads.append((time.perf_counter() - runtime_started) / (100 * len(base_requests)))
        del policy
        import torch

        torch.cuda.empty_cache()

    replay_samples = _replay_throughput_samples(probe_ids)
    receipt = PerformanceQualificationReceipt(
        model_load_seconds=max(model_load_samples),
        calls_per_second_lower_95=sum(device_throughput_bounds),
        runtime_overhead_seconds_per_call=max(runtime_overheads),
        replay_calls_per_second=lower_95_throughput_bound(replay_samples),
        probe_ids=probe_ids,
    )
    tasks = _evaluation_tasks()
    # Five learned adapters require distinct calls. The five base-seed receipts
    # follow one shared deterministic cache path, so they schedule one unique
    # base call rather than five.
    selection = select_certified_coverage(tasks, receipt, model_sessions_per_task=6)
    coverage_payload = {
        "maximum_scheduled_calls": selection.maximum_scheduled_calls,
        "mode": selection.mode,
        "outcome": selection.outcome.value,
        "projected_rollout_seconds": selection.projected_rollout_seconds,
        "task_ids": [task.instance_id for task in selection.tasks],
    }
    if time.time() - gate_started_at_unix > 60 * 60:
        coverage_payload.update(
            {"mode": None, "outcome": "VALID_STOP", "task_ids": [], "reason": "qualification_hour_exhausted"}
        )
    payload = {
        "coverage": coverage_payload,
        "performance_receipt": receipt.to_dict(),
        "gate_started_at_unix": gate_started_at_unix,
        "plan": plan,
        "schema_version": "bfs_v7_performance_selection_v1",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_bytes(
        (json.dumps(payload, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode()
    )
    temporary.replace(args.output)
    print(json.dumps({"output": str(args.output), **payload["coverage"]}, sort_keys=True))
    return 0


def _probe_inputs(probe_ids: tuple[str, ...]) -> dict[str, dict[str, object]]:
    wanted = set(probe_ids)
    inputs: dict[str, dict[str, object]] = {}
    for line in _CORPUS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["record_id"] in wanted:
            inputs[row["record_id"]] = row["input"]
    if set(inputs) != wanted:
        raise ValueError("frozen performance snapshots are missing from the v6 corpus")
    return inputs


def _evaluation_tasks():
    selected = [
        json.loads(line)
        for line in (
            (_REPO_ROOT / "data" / "bfs_pilot_v6" / "selected-manifest.jsonl").read_text(encoding="utf-8").splitlines()
        )
    ]
    trace_manifest = json.loads((_TRACE_ROOT / "manifests" / "bfs-expert-traces.json").read_bytes())

    def record_count(row: dict[str, object]) -> int:
        trace = json.loads((_TRACE_ROOT / row["search_trace"]["path"]).read_bytes())
        return int(trace["record_count"])

    return evaluation_tasks_from_manifests(selected, trace_manifest["traces"], trace_record_count=record_count)


def _replay_throughput_samples(probe_ids: tuple[str, ...]) -> list[float]:
    instance_ids = {record_id.split(":", 1)[0] for record_id in probe_ids}
    manifest = json.loads((_TRACE_ROOT / "manifests" / "bfs-expert-traces.json").read_bytes())
    rows = [row for row in manifest["traces"] if row["instance_id"] in instance_ids]
    samples: list[float] = []
    for row in rows:
        domain, problem, _ = _normalize_authority_input(
            Path(row["source"]["domain_path"]).read_text(encoding="utf-8"),
            Path(row["source"]["problem_path"]).read_text(encoding="utf-8"),
        )
        authority = PDDLStateAuthority.from_pddl(domain, problem)
        limits = _trace_limits(authority, int(row["max_expansions"]))
        trace = (_TRACE_ROOT / row["search_trace"]["path"]).read_bytes()
        record_count = json.loads(trace)["record_count"]
        before = time.perf_counter()
        verify_incremental_replay_contexts(
            trace,
            authority=authority,
            limits=limits,
            accepted_delta_limit=16,
        )
        samples.append(record_count / (time.perf_counter() - before))
    return samples


if __name__ == "__main__":
    raise SystemExit(main())
