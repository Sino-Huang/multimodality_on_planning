"""Convert an authorized BFS text-corpus release for ms-swift SFT."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_sft import convert_bfs_corpus_to_ms_swift

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FREEZE = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v1.json"
_AUTHORIZATION = _REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    output_root = args.output_root.expanduser().resolve()
    if output_root.exists():
        raise FileExistsError(f"BFS SFT conversion root already exists: {output_root}")
    phase_gate = load_bfs_phase_gate(_FREEZE, _AUTHORIZATION)
    manifests = {}
    for view in ("operational", "process"):
        manifests[view] = str(
            convert_bfs_corpus_to_ms_swift(
                corpus_root=args.corpus_root,
                output_root=output_root / view,
                phase_gate=phase_gate,
                view=view,
            )
        )
    print(json.dumps({"manifests": manifests, "schema_version": "bfs_ms_swift_conversion_set_v1"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
