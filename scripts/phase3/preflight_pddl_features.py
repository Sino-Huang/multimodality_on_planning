from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import preflight_pddl_features, print_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, default=Path("data/curriculum_pddl"))
    parser.add_argument("--accounting", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rows = preflight_pddl_features(args.input_root, args.accounting, args.output)
    print_payload({"rows_written": len(rows), "output": str(args.output)}, as_json=args.json)


if __name__ == "__main__":
    main()
