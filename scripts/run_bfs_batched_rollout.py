"""Run one resumable GPU shard of a resource-bounded BFS rollout."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

from examples.planning_benchmark_slice.batched_search_evaluation import (
    DeterministicSearchScheduler,
    GateClock,
    SchedulerStopToken,
    cost_balanced_task_shards,
    evaluation_tasks_from_manifests,
    install_sigint_stop,
)
from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_references import _write_task_fixture
from examples.planning_benchmark_slice.model_search_episode import (
    SearchEpisodeSession,
    replay_model_search_episode,
)
from examples.planning_benchmark_slice.qwen_text_policy import BatchedPolicyAdapter
from examples.planning_benchmark_slice.search_episode import TASK_SCHEMA_VERSION, _authority_from_task
from examples.planning_benchmark_slice.validate_instance import load_fixture
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PHASES = {
    phase: (
        _REPO_ROOT / "configs" / "experiments" / f"bfs_phase_freeze_{phase}.json",
        _REPO_ROOT / "configs" / "experiments" / f"bfs_phase_authorization_{phase}.json",
    )
    for phase in ("v7", "v8")
}
_TRACE_ROOT = _REPO_ROOT / "data" / "bfs_pilot_v6" / "exact-traces"


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=tuple(_PHASES), default="v8")
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--device-shard-index", type=int, required=True)
    parser.add_argument("--device-shard-count", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)
    if args.device_shard_count != 2 or args.device_shard_index not in (0, 1):
        raise ValueError(f"{args.phase} is frozen to two device shards indexed 0 and 1")

    gate = load_bfs_phase_gate(*_PHASES[args.phase])
    gate.require_run(stage="batched_evaluation", contract_id=gate.phase_id)
    qualification = _json_object(args.qualification)
    coverage = qualification.get("coverage")
    if (
        not isinstance(coverage, dict)
        or coverage.get("outcome") != StopOutcome.PASS.value
        or coverage.get("mode") not in {"full", "panel", "cost_qualified_panel"}
        or not isinstance(coverage.get("task_ids"), list)
    ):
        raise ValueError("performance qualification did not certify a rollout task set")
    qualification_phase = qualification.get("phase_id", qualification.get("plan", {}).get("phase_id"))
    if qualification_phase != gate.phase_id:
        raise ValueError("performance qualification belongs to a different phase")
    selected_ids = set(coverage["task_ids"])
    all_selected_rows, all_evaluation_tasks = _selected_tasks(selected_ids)
    task_shards = cost_balanced_task_shards(all_evaluation_tasks, shard_count=2)
    assigned_ids = {task.instance_id for task in task_shards[args.device_shard_index]}
    selected_rows = [row for row in all_selected_rows if row["instance_id"] in assigned_ids]
    evaluation_tasks = tuple(task for task in all_evaluation_tasks if task.instance_id in assigned_ids)
    seeds = tuple(int(seed) for seed in gate.freeze["seeds"])
    adapter_paths = {
        f"seed-{seed}": (
            _REPO_ROOT
            / "outputs"
            / "bfs_phase"
            / f"issue54-v6-process-sft-seed-{seed}"
            / "checkpoints"
            / "checkpoint-1221"
        )
        for seed in seeds
    }
    if any(not path.is_dir() for path in adapter_paths.values()):
        raise FileNotFoundError("one or more assigned v6 final checkpoints are missing")
    assigned_arms = [f"base:seed-{seed}" for seed in seeds]
    assigned_arms.extend(f"process_sft:seed-{seed}" for seed in seeds)
    plan = {
        "assigned_arms": assigned_arms,
        "attempt_id": args.attempt_id,
        "coverage_mode": coverage["mode"],
        "device": args.device,
        "device_shard_count": 2,
        "device_shard_index": args.device_shard_index,
        "phase_id": gate.phase_id,
        "qualification": str(args.qualification.resolve()),
        "task_ids": sorted(assigned_ids),
    }
    if args.dry_run:
        print(json.dumps({**plan, "dry_run": True}, sort_keys=True))
        return 0

    output_root = args.output_root.resolve()
    _prepare_output_root(output_root, plan, resume=args.resume)
    binding = ReceiptBinding(gate.phase_id, args.attempt_id, output_root)
    gate_receipt = GateReceipt(binding, StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding, gate_receipt.receipt_id)
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    torch.use_deterministic_algorithms(True)
    model = gate.freeze["models"]["primary"]
    policy = BatchedPolicyAdapter(
        model_id=model["model_id"],
        revision=model["revision"],
        adapter_paths=adapter_paths,
        device=args.device,
        max_new_tokens=384,
        max_context_tokens=8_192,
        max_batch_size=8,
        max_batch_input_tokens=48_000,
    )
    call_limits = {task.instance_id: task.model_call_limit for task in evaluation_tasks}
    sessions: list[SearchEpisodeSession] = []
    already_complete: list[str] = []
    with tempfile.TemporaryDirectory(prefix=f"bfs-{args.phase}-shard-{args.device_shard_index}-") as directory:
        fixture_root = Path(directory)
        for row in selected_rows:
            fixture = load_fixture(_write_task_fixture(row, fixture_root))
            task = {
                "domain_pddl": fixture.domain_pddl,
                "instance_id": str(fixture.payload["instance_id"]),
                "problem_pddl": fixture.problem_pddl,
                "schema_version": TASK_SCHEMA_VERSION,
            }
            authority = _authority_from_task(task)
            for arm, seed, adapter_id in _assigned_variants(seeds, args.device_shard_index):
                relative = _episode_path(arm, seed, task["instance_id"])
                path = output_root / relative
                if path.is_file():
                    episode = _json_object(path)
                    if replay_model_search_episode(episode["evidence"]) != episode:
                        raise ValueError(f"resumed {args.phase} episode replay differs: {relative}")
                    already_complete.append(f"{arm}:{adapter_id or 'base'}:{seed}:{task['instance_id']}")
                    continue
                identity = dict(policy.identity)
                identity["adapter_path"] = adapter_id
                sessions.append(
                    SearchEpisodeSession(
                        task=task,
                        algorithm="bfs",
                        modality="text-state",
                        arm=arm,
                        model_identity=identity,
                        max_expansions=int(
                            gate.freeze["budgets"]["episode_max_expansions_by_difficulty"][row["bucket"]]
                        ),
                        max_model_calls=call_limits[task["instance_id"]],
                        max_input_bytes=3_840,
                        max_output_tokens=384,
                        accepted_delta_limit=16,
                        model_input_projection="bounded_bfs_search_memory_v4",
                        seed=seed,
                        gate_receipt=gate_receipt,
                        authorization_receipt=authorization,
                        adapter_id=adapter_id,
                        authority=authority,
                    )
                )

        gate_started = float(qualification.get("gate_started_at_unix", time.time()))
        clock = GateClock(now=time.time, started_at=gate_started)
        stop_token = SchedulerStopToken()
        restore_sigint = install_sigint_stop(stop_token)
        try:
            result = DeterministicSearchScheduler(
                policy,
                stop_token=stop_token,
                should_stop=lambda: not clock.can_launch_model_call(),
            ).run(
                sessions,
                on_episode_complete=lambda session, episode: _write_episode(output_root, session, episode),
            )
        finally:
            restore_sigint()

    total_assigned = len(selected_rows) * len(assigned_arms)
    completed_count = len(already_complete) + len(result.completed)
    manifest = {
        "assigned_episode_count": total_assigned,
        "authorization_receipt": authorization.to_dict(),
        "completed_episode_count": completed_count,
        "coverage_mode": coverage["mode"],
        "device_shard_count": 2,
        "device_shard_index": args.device_shard_index,
        "gate_receipt": gate_receipt.to_dict(),
        "incomplete_session_ids": list(result.incomplete_session_ids),
        "launched_batches": result.launched_batches,
        "outcome": (StopOutcome.PASS if completed_count == total_assigned else StopOutcome.VALID_STOP).value,
        "phase_id": gate.phase_id,
        "reference_conditions": "selected exact_classical and random_valid rows are replayed from immutable v6 receipts",
        "schema_version": f"bfs_{args.phase}_batched_rollout_shard_v1",
        "stop_reason": result.stop_reason,
    }
    _atomic_write(output_root / "manifest.json", manifest)
    print(json.dumps({"output": str(output_root / "manifest.json"), **manifest}, sort_keys=True))
    return 0


def _assigned_variants(seeds: tuple[int, ...], _shard_index: int):
    for seed in seeds:
        yield "base", seed, None
    for seed in seeds:
        yield "process_sft", seed, f"seed-{seed}"


def _selected_tasks(selected_ids: set[str]):
    rows = [
        json.loads(line)
        for line in (
            (_REPO_ROOT / "data" / "bfs_pilot_v6" / "selected-manifest.jsonl").read_text(encoding="utf-8").splitlines()
        )
    ]
    trace_manifest = _json_object(_TRACE_ROOT / "manifests" / "bfs-expert-traces.json")

    def record_count(row: dict[str, object]) -> int:
        return int(_json_object(_TRACE_ROOT / row["search_trace"]["path"])["record_count"])

    tasks = evaluation_tasks_from_manifests(rows, trace_manifest["traces"], trace_record_count=record_count)
    selected_rows = [row for row in rows if row["split"] == "dev" and row["instance_id"] in selected_ids]
    selected_tasks = tuple(task for task in tasks if task.instance_id in selected_ids)
    if len(selected_rows) != len(selected_ids) or len(selected_tasks) != len(selected_ids):
        raise ValueError("qualification selected unknown or duplicate tasks")
    return selected_rows, selected_tasks


def _episode_path(arm: str, seed: int, instance_id: str) -> Path:
    return Path("episodes") / arm / f"seed-{seed}" / f"{instance_id}.json"


def _write_episode(output_root: Path, session: SearchEpisodeSession, episode: dict[str, object]) -> None:
    _atomic_write(
        output_root / _episode_path(session.arm, session.seed, str(session.task["instance_id"])),
        episode,
    )


def _prepare_output_root(output_root: Path, plan: dict[str, object], *, resume: bool) -> None:
    launch = output_root / "launch.json"
    if output_root.exists():
        if not resume or not launch.is_file() or _json_object(launch) != plan:
            raise ValueError("existing rollout output requires --resume and a matching launch plan")
        manifest_path = output_root / "manifest.json"
        if manifest_path.exists():
            manifest = _json_object(manifest_path)
            if manifest.get("outcome") == StopOutcome.PASS.value:
                raise ValueError("rollout shard is already complete")
            if manifest.get("stop_reason") == "wall_clock_cutoff":
                raise ValueError("rollout shard exhausted the frozen wall-clock budget")
        return
    output_root.mkdir(parents=True)
    _atomic_write(launch, plan)


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _atomic_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
