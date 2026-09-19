"""Inspect the issue71 freeze; no rendering, training, GPU work, or writes."""

# Standalone script needs the repository root before project imports.
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

from examples.planning_benchmark_slice.modality_phase import inspect_modality_sources, load_modality_phase


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", required=True, help="inspect settings and source coverage only"
    )
    parser.add_argument("--freeze", type=Path, default=ROOT / "configs/experiments/issue71/v2/freeze.json")
    args = parser.parse_args(argv)
    started = time.monotonic()

    def log(stage: str, **fields: object) -> None:
        print(
            json.dumps({"stage": stage, "elapsed_seconds": round(time.monotonic() - started, 3), **fields}), flush=True
        )

    log("phase_preflight", completed=0, total=2)
    try:
        phase = load_modality_phase(args.freeze)
        log("manifests_loaded", completed=1, total=2, cells=len(phase.cells))
        counts = inspect_modality_sources(phase)
        log(
            "preflight_complete",
            completed=2,
            total=2,
            dry_run_valid=True,
            outcome=phase.authorization["outcome"],
            phase_authorized=phase.authorization["start_permitted"],
            start_permitted=False,
            note="Dry-run is not run authorization; matching attempt receipts and predecessors are still required.",
            scientific_completion=False,
            reason=phase.authorization.get("reason"),
            sources=counts,
            writes=0,
        )
        # A working dry-run is distinct from permission to start production.
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        log("preflight_failed", outcome="INVALID", scientific_completion=False, reason=str(error), writes=0)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
