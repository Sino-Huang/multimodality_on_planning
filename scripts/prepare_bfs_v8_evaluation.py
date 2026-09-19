"""Start the v8 global gate clock from its frozen panel and performance receipt."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v8.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v8.json"
_SELECTION = _REPO_ROOT / "data" / "bfs_eval_v8" / "performance-selection.json"


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)

    gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    gate.require_run(stage="performance_qualification", contract_id=gate.phase_id)
    payload = json.loads(_SELECTION.read_bytes())
    payload.update(
        {
            "gate_started_at_unix": time.time(),
            "phase_id": gate.phase_id,
            "schema_version": "bfs_v8_started_performance_selection_v1",
        }
    )
    if args.dry_run:
        print(json.dumps({**payload, "dry_run": True}, sort_keys=True))
        return 0
    output = args.output.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"v8 started qualification already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(
        (json.dumps(payload, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode()
    )
    temporary.replace(output)
    print(
        json.dumps(
            {
                "gate_started_at_unix": payload["gate_started_at_unix"],
                "output": str(output),
                "phase_id": gate.phase_id,
                "projected_rollout_seconds": payload["coverage"]["projected_rollout_seconds"],
                "task_count": len(payload["coverage"]["task_ids"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
