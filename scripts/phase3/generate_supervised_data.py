from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import DEFAULT_PLANNERS, generate_supervised_data, print_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, default=Path("data/curriculum_pddl"))
    parser.add_argument("--output-root", type=Path, default=Path("data/phase3_supervised_planning"))
    parser.add_argument("--planners", nargs="+", default=list(DEFAULT_PLANNERS), choices=list(DEFAULT_PLANNERS))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = generate_supervised_data(args.input_root, args.output_root, planners=tuple(args.planners))
    print_payload(payload["summary"], as_json=args.json)


if __name__ == "__main__":
    main()
