"""Draw a native scene-only preview from a retained, replay-bound VFG."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.planimation_phase1_frames import render_vfg_to_local_png_frames  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--state", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=1536)
    args = parser.parse_args()
    with gzip.open(args.catalog, "rt") as source:
        catalog = json.load(source)
    binding = next(b for b in catalog["path_bindings"] if args.state in b["state_indices"])
    stage = binding["state_indices"].index(args.state)
    objects = frozenset(n for names in catalog["task_context"]["objects_by_type"].values() for n in names)
    render_vfg_to_local_png_frames(
        gzip.decompress((ROOT / binding["vfg"]).read_bytes()),
        args.output,
        stage,
        stage,
        canvas_size=args.size,
        label_font_size=24,
        object_names=objects,
    )
    print(
        json.dumps(
            {
                "stage": "preview:complete",
                "state": args.state,
                "output": str(args.output / "frame_000.png"),
                "model_calls": 0,
                "training_representation_activated": False,
            }
        )
    )


if __name__ == "__main__":
    main()
