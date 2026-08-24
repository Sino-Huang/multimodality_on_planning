"""Authorized one-episode Qwen3-VL GPU smoke for the frozen BFS phase."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import time
from pathlib import Path
from typing import Any

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.model_search_episode import run_model_search_episode
from examples.planning_benchmark_slice.qwen_text_policy import QwenTextPolicy
from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    StopOutcome,
    evaluate_execution_permission,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json"
_TASK = _REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_nontrivial.json"
def _initialize_cuda_memory_stats(torch_module: Any, *, device: str, device_index: int) -> None:
    allocation = torch_module.empty(1, device=device)
    del allocation
    torch_module.cuda.reset_peak_memory_stats(device_index)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--attempt-id", required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"smoke output already exists: {output}")

    phase_gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    phase_gate.require_run(stage="base_and_references", contract_id=phase_gate.phase_id, difficulty="easy")
    binding = ReceiptBinding(
        contract_id=phase_gate.phase_id,
        attempt_id=args.attempt_id,
        output_root=output.parent,
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_id=gate.receipt_id)
    permission = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )
    if not permission.start_permitted:
        raise RuntimeError("frozen BFS authorization did not permit the GPU smoke")

    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

    import torch

    device = torch.device(args.device)
    device_index = device.index if device.index is not None else torch.cuda.current_device()
    torch.use_deterministic_algorithms(True)
    _initialize_cuda_memory_stats(torch, device=str(device), device_index=device_index)
    frozen_model = phase_gate.freeze["models"]["primary"]
    started = time.monotonic()
    policy = QwenTextPolicy(
        model_id=frozen_model["model_id"],
        revision=frozen_model["revision"],
        max_new_tokens=phase_gate.freeze["budgets"]["max_output_tokens_per_operation"],
        device=str(device),
    )
    policy.set_seed(phase_gate.freeze["seeds"][0])
    episode = run_model_search_episode(
        _TASK,
        algorithm="bfs",
        modality="text-state",
        arm="base",
        model_identity=policy.identity,
        policy=policy,
        max_expansions=1,
        max_input_bytes=(
            phase_gate.freeze["budgets"]["max_context_tokens"]
            - phase_gate.freeze["budgets"]["max_output_tokens_per_operation"]
        ),
        max_output_tokens=phase_gate.freeze["budgets"]["max_output_tokens_per_operation"],
        accepted_delta_limit=(
            phase_gate.freeze["budgets"]["max_context_tokens"]
            // phase_gate.freeze["budgets"]["max_output_tokens_per_operation"]
        ),
        model_input_projection="rolling_search_context_v1",
        seed=phase_gate.freeze["seeds"][0],
        gate_receipt=gate,
        authorization_receipt=authorization,
    )
    elapsed = time.monotonic() - started
    report = {
        "device": {
            "name": torch.cuda.get_device_name(device_index),
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(device_index),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(device_index),
        },
        "elapsed_seconds": elapsed,
        "environment": {"CUBLAS_WORKSPACE_CONFIG": os.environ["CUBLAS_WORKSPACE_CONFIG"]},
        "episode": episode,
        "framework": {
            package: importlib.metadata.version(package)
            for package in ("accelerate", "ms-swift", "peft", "torch", "transformers")
        },
        "phase_receipt": phase_gate.receipt(stage="base_and_references", difficulty="easy"),
        "schema_version": "issue_52_qwen_base_gpu_smoke_v1",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "elapsed_seconds": elapsed,
                "goal_reached": episode["result"]["goal_reached"],
                "invalid_operation_rate": episode["result"]["invalid_operation_rate"],
                "output": str(output),
                "peak_allocated_bytes": report["device"]["peak_allocated_bytes"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
