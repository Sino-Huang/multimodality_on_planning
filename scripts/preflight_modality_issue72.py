"""Measure frozen image feasibility with progress, before rendering any frames."""

# Standalone project imports.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.modality_phase import load_modality_phase
from examples.planning_benchmark_slice.modality_render_preflight import run_initial_layout_preflight
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="read-only; no receipt/output writes")
    parser.add_argument("--gate", type=Path, default=ROOT / "configs/experiments/issue72/gate.json")
    parser.add_argument("--authorization", type=Path, default=ROOT / "configs/experiments/issue72/authorization.json")
    args = parser.parse_args(argv)
    started = time.monotonic()

    def progress(event):
        elapsed = time.monotonic() - started
        completed, total = event.get("completed", 0), event.get("total", 0)
        eta = round(elapsed / completed * (total - completed), 2) if completed else None
        print(json.dumps({**event, "elapsed_seconds": round(elapsed, 2), "eta_seconds": eta}), flush=True)

    try:
        phase = load_modality_phase()
        payload = json.loads(args.gate.read_text())
        binding = ReceiptBinding(**{**payload["binding"], "output_root": ROOT / payload["binding"]["output_root"]})
        gate = GateReceipt(binding, StopOutcome(payload["outcome"]), payload.get("ancestor_receipt_id"))
        auth = json.loads(args.authorization.read_text()) if args.authorization.exists() else None
        authorization = (
            AuthorizationReceipt(
                ReceiptBinding(**{**auth["binding"], "output_root": ROOT / auth["binding"]["output_root"]}),
                auth["gate_receipt_id"],
            )
            if auth
            else None
        )
        output = Path(binding.output_root)
        if not args.dry_run and output.exists():
            raise ValueError("attempt output exists; use --dry-run or a newly authorized attempt")
        progress({"stage": "preflight_started", "dry_run": args.dry_run})
        report = run_initial_layout_preflight(
            phase, binding=binding, gate=gate, authorization=authorization, progress=progress
        )
        if not args.dry_run:
            output.mkdir(parents=True)
            (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        progress(
            {
                "stage": "preflight_complete",
                "outcome": report["outcome"],
                "reason": report.get("reason"),
                "counts": report.get("counts"),
                "scientific_completion": False,
                "rendered_frames": 0,
                "output": None if args.dry_run else str(output / "report.json"),
            }
        )
        return 2 if report["outcome"] == "VALID_STOP" else 1
    except (ValueError, OSError, KeyError) as error:
        progress(
            {"stage": "preflight_failed", "outcome": "INVALID", "reason": str(error), "scientific_completion": False}
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
