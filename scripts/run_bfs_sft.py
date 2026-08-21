"""Launch one authorized frozen BFS LoRA SFT run through ms-swift."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import time
from pathlib import Path

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_sft import build_ms_swift_sft_command
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
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--view", choices=("operational", "process"), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--world-size", type=int, required=True)
    parser.add_argument("--devices", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    dataset_root = args.dataset_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    if output_root.exists():
        raise FileExistsError(f"BFS SFT output root already exists: {output_root}")
    phase_gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    stage = "operational_sft" if args.view == "operational" else "process_sft_and_sanity_gate"
    phase_gate.require_run(stage=stage, contract_id=phase_gate.phase_id)
    _validate_conversion(dataset_root, phase_gate.receipt(stage=stage), args.view)

    binding = ReceiptBinding(
        contract_id=phase_gate.phase_id,
        attempt_id=args.attempt_id,
        output_root=output_root,
    )
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding=binding, gate_receipt_id=gate.receipt_id)
    permission = evaluate_execution_permission(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )
    if not permission.start_permitted:
        raise RuntimeError("frozen BFS authorization did not permit SFT")

    checkpoint_root = output_root / "checkpoints"
    command = build_ms_swift_sft_command(
        dataset_root=dataset_root,
        output_root=checkpoint_root,
        phase_gate=phase_gate,
        seed=args.seed,
        world_size=args.world_size,
        smoke=args.smoke,
    )
    environment = os.environ.copy()
    environment.update(
        {
            "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
            "CUDA_VISIBLE_DEVICES": args.devices,
            "NPROC_PER_NODE": str(args.world_size),
            "PYTHONHASHSEED": str(args.seed),
        }
    )
    output_root.mkdir(parents=True)
    launch = {
        "authorization_receipt": authorization.to_dict(),
        "command": command,
        "environment": {
            key: environment[key]
            for key in sorted(environment)
            if key
            in {
                "CUBLAS_WORKSPACE_CONFIG",
                "CUDA_VISIBLE_DEVICES",
                "NPROC_PER_NODE",
                "PYTHONHASHSEED",
            }
        },
        "framework": {
            package: importlib.metadata.version(package)
            for package in ("accelerate", "ms-swift", "peft", "torch", "transformers")
        },
        "gate_receipt": gate.to_dict(),
        "phase_receipt": phase_gate.receipt(stage=stage),
        "schema_version": "bfs_ms_swift_launch_v1",
        "seed": args.seed,
        "smoke": args.smoke,
        "view": args.view,
    }
    (output_root / "launch.json").write_text(_canonical_text(launch) + "\n", encoding="utf-8")

    started = time.monotonic()
    with (output_root / "training.log").open("wb") as log:
        completed = subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT, check=False)
    report = {
        "elapsed_seconds": time.monotonic() - started,
        "outcome": StopOutcome.PASS.value if completed.returncode == 0 else StopOutcome.INVALID.value,
        "returncode": completed.returncode,
        "schema_version": "bfs_ms_swift_training_report_v1",
        "scientific_completion": False,
        "status": "training_completed" if completed.returncode == 0 else "training_failed",
    }
    (output_root / "training-report.json").write_text(_canonical_text(report) + "\n", encoding="utf-8")
    print(_canonical_text({**report, "output_root": str(output_root)}))
    return completed.returncode


def _validate_conversion(dataset_root: Path, expected_phase_receipt: dict[str, object], view: str) -> None:
    manifest_path = dataset_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("schema_version") != "bfs_ms_swift_conversion_v1"
        or manifest.get("framework") != {"name": "ms-swift", "version": "4.2.2"}
        or manifest.get("phase_receipt") != expected_phase_receipt
        or manifest.get("view") != view
        or not manifest.get("counts", {}).get("train")
        or not manifest.get("counts", {}).get("dev")
    ):
        raise ValueError("ms-swift dataset conversion does not match this frozen SFT run")


def _canonical_text(value: object) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
