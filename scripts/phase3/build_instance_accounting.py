from __future__ import annotations

import argparse

from .pipeline import add_common_generation_args, build_instance_accounting, print_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    add_common_generation_args(parser)
    args = parser.parse_args()
    rows = build_instance_accounting(args.input_root, args.output_root)
    print_payload({"rows_written": len(rows), "diagnostics": str(args.output_root / "diagnostics" / "instance_accounting.jsonl")}, as_json=args.json)


if __name__ == "__main__":
    main()
